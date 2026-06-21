from contextlib import asynccontextmanager
from typing import Annotated, AsyncIterator

from uuid import UUID

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Response, status

from backend.database import (
    ForecastPersistenceError,
    assign_installation_to_plant,
    create_installation,
    create_plant,
    delete_installation,
    delete_plant,
    get_installation,
    get_plant,
    initialize_database,
    list_forecast_runs,
    list_installations,
    list_plant_installations,
    list_plants,
    remove_installation_from_plant,
    save_forecast_run,
    update_installation,
    update_plant,
)
from backend.geocoding import (
    GeocodingServiceError,
    LocationNotFoundError,
    geocode_location,
)
from backend.models import (
    ForecastHistoryRun,
    Installation,
    InstallationCreate,
    InstallationUpdate,
    Plant,
    PlantCreate,
    PlantUpdate,
    PlantForecastComponent,
    PlantPVForecastResponse,
    PVForecastResponse,
    WeatherForecastRow,
)
from backend.services.open_meteo import (
    WeatherServiceError,
    WeatherServiceRateLimitError,
    WeatherServiceTimeoutError,
    open_meteo_service,
)
from backend.services.pv_forecast import (
    PVForecastError,
    pv_forecast_service,
)

INSTALLATION_NOT_FOUND = "PV-Anlage wurde nicht gefunden."
SESSION_HEADER = "X-Session-ID"


def require_session_id(
    value: Annotated[str | None, Header(alias=SESSION_HEADER)] = None,
) -> UUID:
    if value is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Der Header {SESSION_HEADER} fehlt.",
        )
    try:
        return UUID(value)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Der Header {SESSION_HEADER} enthält keine gültige UUID.",
        ) from exc


SessionId = Annotated[UUID, Depends(require_session_id)]


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    initialize_database()
    yield


app = FastAPI(
    title="PV Forecast API",
    description="API for photovoltaic power forecasts",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/", tags=["general"])
async def root() -> dict[str, str]:
    return {"message": "PV Forecast API"}


@app.get("/health", tags=["general"])
async def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.post(
    "/installations",
    response_model=Installation,
    status_code=status.HTTP_201_CREATED,
    tags=["installations"],
)
async def add_installation(
    data: InstallationCreate, session_id: SessionId
) -> Installation:
    try:
        coordinates = await geocode_location(data.location)
    except LocationNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except GeocodingServiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    return Installation.model_validate(
        create_installation(
            data,
            coordinates.latitude,
            coordinates.longitude,
            session_id,
        )
    )


@app.get(
    "/installations",
    response_model=list[Installation],
    tags=["installations"],
)
async def get_installations(session_id: SessionId) -> list[Installation]:
    return [
        Installation.model_validate(item)
        for item in list_installations(session_id)
    ]


@app.get(
    "/installations/{installation_id}",
    response_model=Installation,
    tags=["installations"],
)
async def get_installation_by_id(
    installation_id: UUID, session_id: SessionId
) -> Installation:
    installation = get_installation(installation_id, session_id)
    if installation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=INSTALLATION_NOT_FOUND,
        )
    return Installation.model_validate(installation)


@app.put(
    "/installations/{installation_id}",
    response_model=Installation,
    tags=["installations"],
)
async def update_installation_by_id(
    installation_id: UUID,
    data: InstallationUpdate,
    session_id: SessionId,
) -> Installation:
    installation = get_installation(installation_id, session_id)
    if installation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=INSTALLATION_NOT_FOUND,
        )

    location = data.location.strip()
    current_location = (installation.get("location_label") or "").strip()
    if location.casefold() != current_location.casefold():
        try:
            coordinates = await geocode_location(location)
        except LocationNotFoundError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(exc),
            ) from exc
        except GeocodingServiceError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(exc),
            ) from exc
        latitude = coordinates.latitude
        longitude = coordinates.longitude
    elif data.latitude is not None and data.longitude is not None:
        latitude = data.latitude
        longitude = data.longitude
    else:
        latitude = installation["latitude"]
        longitude = installation["longitude"]

    updated = update_installation(
        installation_id,
        session_id,
        data,
        latitude,
        longitude,
    )
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=INSTALLATION_NOT_FOUND,
        )
    return Installation.model_validate(updated)


@app.delete(
    "/installations/{installation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["installations"],
)
async def delete_installation_by_id(
    installation_id: UUID, session_id: SessionId
) -> Response:
    if not delete_installation(installation_id, session_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=INSTALLATION_NOT_FOUND,
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get(
    "/installations/{installation_id}/weather-forecast",
    response_model=list[WeatherForecastRow],
    tags=["weather"],
)
async def get_weather_forecast(
    installation_id: UUID,
    session_id: SessionId,
    forecast_days: int = Query(default=7, ge=1, le=16),
) -> list[WeatherForecastRow]:
    installation = get_installation(installation_id, session_id)
    if installation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=INSTALLATION_NOT_FOUND,
        )

    try:
        return await open_meteo_service.get_hourly_forecast(
            latitude=installation["latitude"],
            longitude=installation["longitude"],
            forecast_days=forecast_days,
        )
    except WeatherServiceTimeoutError as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=str(exc),
        ) from exc
    except WeatherServiceRateLimitError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except WeatherServiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc


@app.get(
    "/installations/{installation_id}/pv-forecast",
    response_model=PVForecastResponse,
    tags=["forecast"],
)
async def get_pv_forecast(
    installation_id: UUID,
    session_id: SessionId,
    forecast_days: int = Query(default=7, ge=1, le=16),
) -> PVForecastResponse:
    installation = get_installation(installation_id, session_id)
    if installation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=INSTALLATION_NOT_FOUND,
        )

    try:
        weather = await open_meteo_service.get_hourly_forecast(
            latitude=installation["latitude"],
            longitude=installation["longitude"],
            forecast_days=forecast_days,
        )
        hourly_forecast = pv_forecast_service.calculate(
            latitude=installation["latitude"],
            longitude=installation["longitude"],
            peak_power_kwp=installation["peak_power_kwp"],
            azimuth=installation["azimuth"],
            tilt=installation["tilt"],
            weather=weather,
        )
        daily_energy = pv_forecast_service.calculate_daily_energy(hourly_forecast)
        metrics = pv_forecast_service.calculate_metrics(hourly_forecast)
        forecast = PVForecastResponse(
            hourly=hourly_forecast,
            daily=daily_energy,
            metrics=metrics,
        )
        save_forecast_run(installation_id, forecast)
        return forecast
    except WeatherServiceTimeoutError as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=str(exc),
        ) from exc
    except WeatherServiceRateLimitError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except WeatherServiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    except PVForecastError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except ForecastPersistenceError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc


@app.get(
    "/installations/{installation_id}/forecast-history",
    response_model=list[ForecastHistoryRun],
    tags=["forecast"],
)
async def get_forecast_history(
    installation_id: UUID,
    session_id: SessionId,
    limit: int = Query(default=20, ge=1, le=100),
) -> list[ForecastHistoryRun]:
    if get_installation(installation_id, session_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=INSTALLATION_NOT_FOUND,
        )

    try:
        return [
            ForecastHistoryRun.model_validate(run)
            for run in list_forecast_runs(installation_id, limit)
        ]
    except ForecastPersistenceError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc


@app.post(
    "/plants",
    response_model=Plant,
    status_code=status.HTTP_201_CREATED,
    tags=["plants"],
)
async def add_plant(data: PlantCreate, session_id: SessionId) -> Plant:
    return Plant.model_validate(create_plant(data, session_id))


@app.get("/plants", response_model=list[Plant], tags=["plants"])
async def get_plants(session_id: SessionId) -> list[Plant]:
    return [Plant.model_validate(item) for item in list_plants(session_id)]


@app.get("/plants/{plant_id}", response_model=Plant, tags=["plants"])
async def get_plant_by_id(plant_id: UUID, session_id: SessionId) -> Plant:
    plant = get_plant(plant_id, session_id)
    if plant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Kraftwerk wurde nicht gefunden.",
        )
    return Plant.model_validate(plant)


@app.put("/plants/{plant_id}", response_model=Plant, tags=["plants"])
async def update_plant_by_id(
    plant_id: UUID, data: PlantUpdate, session_id: SessionId
) -> Plant:
    plant = update_plant(plant_id, session_id, data)
    if plant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Kraftwerk wurde nicht gefunden.",
        )
    return Plant.model_validate(plant)


@app.delete(
    "/plants/{plant_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["plants"],
)
async def delete_plant_by_id(plant_id: UUID, session_id: SessionId) -> Response:
    if not delete_plant(plant_id, session_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Kraftwerk wurde nicht gefunden.",
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.post(
    "/plants/{plant_id}/installations/{installation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["plants"],
)
async def add_installation_to_plant(
    plant_id: UUID, installation_id: UUID, session_id: SessionId
) -> Response:
    if not assign_installation_to_plant(plant_id, installation_id, session_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Kraftwerk oder PV-Anlage wurde nicht gefunden.",
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.delete(
    "/plants/{plant_id}/installations/{installation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["plants"],
)
async def delete_installation_from_plant(
    plant_id: UUID, installation_id: UUID, session_id: SessionId
) -> Response:
    if not remove_installation_from_plant(plant_id, installation_id, session_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Zuordnung wurde nicht gefunden.",
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get(
    "/plants/{plant_id}/pv-forecast",
    response_model=PlantPVForecastResponse,
    tags=["plants", "forecast"],
)
async def get_plant_pv_forecast(
    plant_id: UUID,
    session_id: SessionId,
    forecast_days: int = Query(default=7, ge=1, le=16),
) -> PlantPVForecastResponse:
    plant = get_plant(plant_id, session_id)
    if plant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Kraftwerk wurde nicht gefunden.",
        )

    installations = list_plant_installations(plant_id, session_id)
    if not installations:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Dem Kraftwerk sind noch keine PV-Anlagen zugeordnet.",
        )

    try:
        components: list[PlantForecastComponent] = []
        component_forecasts = []
        weather_by_location: dict[tuple[float, float, int], list[WeatherForecastRow]] = {}
        for installation in installations:
            weather_key = (
                round(installation["latitude"], 4),
                round(installation["longitude"], 4),
                forecast_days,
            )
            weather = weather_by_location.get(weather_key)
            if weather is None:
                weather = await open_meteo_service.get_hourly_forecast(
                    latitude=installation["latitude"],
                    longitude=installation["longitude"],
                    forecast_days=forecast_days,
                )
                weather_by_location[weather_key] = weather
            hourly = pv_forecast_service.calculate(
                latitude=installation["latitude"],
                longitude=installation["longitude"],
                peak_power_kwp=installation["peak_power_kwp"],
                azimuth=installation["azimuth"],
                tilt=installation["tilt"],
                weather=weather,
            )
            component_forecasts.append(hourly)
            components.append(
                PlantForecastComponent(
                    installation_id=installation["id"],
                    name=installation["name"],
                    hourly=hourly,
                )
            )

        hourly_total = pv_forecast_service.aggregate_hourly_forecasts(
            component_forecasts
        )
        daily_total = pv_forecast_service.calculate_daily_energy(hourly_total)
        metrics = pv_forecast_service.calculate_metrics(hourly_total)
        return PlantPVForecastResponse(
            hourly=hourly_total,
            daily=daily_total,
            metrics=metrics,
            components=components,
        )
    except WeatherServiceTimeoutError as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=str(exc),
        ) from exc
    except WeatherServiceRateLimitError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except WeatherServiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    except PVForecastError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
