from contextlib import asynccontextmanager
from typing import AsyncIterator

from uuid import UUID

from fastapi import FastAPI, HTTPException, Query, Response, status

from backend.database import (
    ForecastPersistenceError,
    create_installation,
    delete_installation,
    get_installation,
    initialize_database,
    list_forecast_runs,
    list_installations,
    save_forecast_run,
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
    PVForecastResponse,
    WeatherForecastRow,
)
from backend.services.open_meteo import (
    WeatherServiceError,
    WeatherServiceTimeoutError,
    open_meteo_service,
)
from backend.services.pv_forecast import (
    PVForecastError,
    pv_forecast_service,
)

INSTALLATION_NOT_FOUND = "PV-Anlage wurde nicht gefunden."


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
async def add_installation(data: InstallationCreate) -> Installation:
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
        create_installation(data, coordinates.latitude, coordinates.longitude)
    )


@app.get(
    "/installations",
    response_model=list[Installation],
    tags=["installations"],
)
async def get_installations() -> list[Installation]:
    return [Installation.model_validate(item) for item in list_installations()]


@app.get(
    "/installations/{installation_id}",
    response_model=Installation,
    tags=["installations"],
)
async def get_installation_by_id(installation_id: UUID) -> Installation:
    installation = get_installation(installation_id)
    if installation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=INSTALLATION_NOT_FOUND,
        )
    return Installation.model_validate(installation)


@app.delete(
    "/installations/{installation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["installations"],
)
async def delete_installation_by_id(installation_id: UUID) -> Response:
    if not delete_installation(installation_id):
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
    forecast_days: int = Query(default=7, ge=1, le=16),
) -> list[WeatherForecastRow]:
    installation = get_installation(installation_id)
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
    forecast_days: int = Query(default=7, ge=1, le=16),
) -> PVForecastResponse:
    installation = get_installation(installation_id)
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
    limit: int = Query(default=20, ge=1, le=100),
) -> list[ForecastHistoryRun]:
    if get_installation(installation_id) is None:
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
