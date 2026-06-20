from fastapi.testclient import TestClient
import duckdb

from backend.geocoding import Coordinates, LocationNotFoundError
from backend.main import app
from backend.models import PVForecastRow, WeatherForecastRow
from backend.services.open_meteo import WeatherServiceError


def test_weather_forecast_route_is_registered() -> None:
    matching_routes = [
        route
        for route in app.routes
        if getattr(route, "path", None)
        == "/installations/{installation_id}/weather-forecast"
    ]

    assert len(matching_routes) == 1
    assert "GET" in matching_routes[0].methods


def test_delete_installation_route_is_registered() -> None:
    matching_routes = [
        route
        for route in app.routes
        if getattr(route, "path", None) == "/installations/{installation_id}"
        and "DELETE" in getattr(route, "methods", set())
    ]

    assert len(matching_routes) == 1


def test_pv_forecast_route_is_registered() -> None:
    matching_routes = [
        route
        for route in app.routes
        if getattr(route, "path", None)
        == "/installations/{installation_id}/pv-forecast"
    ]

    assert len(matching_routes) == 1
    assert "GET" in matching_routes[0].methods


def test_forecast_history_route_is_registered() -> None:
    matching_routes = [
        route
        for route in app.routes
        if getattr(route, "path", None)
        == "/installations/{installation_id}/forecast-history"
    ]

    assert len(matching_routes) == 1
    assert "GET" in matching_routes[0].methods


def test_health_check(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.duckdb"))

    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_root(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.duckdb"))

    with TestClient(app) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {"message": "PV Forecast API"}


def test_installation_endpoints(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.duckdb"))

    async def fake_geocode(_: str) -> Coordinates:
        return Coordinates(latitude=52.52, longitude=13.405)

    monkeypatch.setattr("backend.main.geocode_location", fake_geocode)
    payload = {
        "name": "Hausdach Süd",
        "location": "Berlin",
        "peak_power_kwp": 9.8,
        "azimuth": 180.0,
        "tilt": 32.0,
    }

    with TestClient(app) as client:
        create_response = client.post("/installations", json=payload)
        assert create_response.status_code == 201
        created = create_response.json()
        assert created["name"] == payload["name"]
        assert created["latitude"] == 52.52
        assert created["longitude"] == 13.405
        assert created["id"]
        assert created["created_at"]

        list_response = client.get("/installations")
        assert list_response.status_code == 200
        assert list_response.json() == [created]

        get_response = client.get(f"/installations/{created['id']}")
        assert get_response.status_code == 200
        assert get_response.json() == created


def test_unknown_installation_returns_404(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.duckdb"))

    with TestClient(app) as client:
        response = client.get("/installations/00000000-0000-0000-0000-000000000000")

    assert response.status_code == 404
    assert response.json() == {"detail": "PV-Anlage wurde nicht gefunden."}


def test_delete_installation(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.duckdb"))

    async def fake_geocode(_: str) -> Coordinates:
        return Coordinates(latitude=52.52, longitude=13.405)

    monkeypatch.setattr("backend.main.geocode_location", fake_geocode)
    payload = {
        "name": "Zu löschende Anlage",
        "location": "Berlin",
        "peak_power_kwp": 8.0,
        "azimuth": 180.0,
        "tilt": 30.0,
    }

    with TestClient(app) as client:
        created = client.post("/installations", json=payload).json()
        delete_response = client.delete(f"/installations/{created['id']}")
        get_response = client.get(f"/installations/{created['id']}")
        list_response = client.get("/installations")

    assert delete_response.status_code == 204
    assert delete_response.content == b""
    assert get_response.status_code == 404
    assert list_response.json() == []


def test_delete_unknown_installation_returns_404(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.duckdb"))

    with TestClient(app) as client:
        response = client.delete(
            "/installations/00000000-0000-0000-0000-000000000000"
        )

    assert response.status_code == 404
    assert response.json() == {"detail": "PV-Anlage wurde nicht gefunden."}


def test_unknown_location_returns_clear_error(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.duckdb"))

    async def fake_geocode(_: str) -> Coordinates:
        raise LocationNotFoundError("Für diesen Standort wurde kein Ort gefunden.")

    monkeypatch.setattr("backend.main.geocode_location", fake_geocode)
    payload = {
        "name": "Unbekannte Anlage",
        "location": "Nirgendwo 12345",
        "peak_power_kwp": 5.0,
        "azimuth": 180.0,
        "tilt": 30.0,
    }

    with TestClient(app) as client:
        response = client.post("/installations", json=payload)

    assert response.status_code == 422
    assert response.json() == {
        "detail": "Für diesen Standort wurde kein Ort gefunden."
    }


def test_weather_forecast_endpoint(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.duckdb"))

    async def fake_geocode(_: str) -> Coordinates:
        return Coordinates(latitude=48.137, longitude=11.575)

    captured: dict[str, float | int] = {}

    async def fake_forecast(
        *, latitude: float, longitude: float, forecast_days: int
    ) -> list[WeatherForecastRow]:
        captured.update(
            latitude=latitude,
            longitude=longitude,
            forecast_days=forecast_days,
        )
        return [
            WeatherForecastRow(
                timestamp="2026-06-19T12:00:00Z",
                temperature_2m=23.5,
                cloud_cover=20.0,
                direct_radiation=650.0,
                diffuse_radiation=90.0,
                wind_speed_10m=8.5,
            )
        ]

    monkeypatch.setattr("backend.main.geocode_location", fake_geocode)
    monkeypatch.setattr(
        "backend.main.open_meteo_service.get_hourly_forecast", fake_forecast
    )
    payload = {
        "name": "Anlage München",
        "location": "München",
        "peak_power_kwp": 12.0,
        "azimuth": 180.0,
        "tilt": 30.0,
    }

    with TestClient(app) as client:
        installation = client.post("/installations", json=payload).json()
        response = client.get(
            f"/installations/{installation['id']}/weather-forecast",
            params={"forecast_days": 3},
        )

    assert response.status_code == 200
    assert response.json() == [
        {
            "timestamp": "2026-06-19T12:00:00Z",
            "temperature_2m": 23.5,
            "cloud_cover": 20.0,
            "direct_radiation": 650.0,
            "diffuse_radiation": 90.0,
            "wind_speed_10m": 8.5,
        }
    ]
    assert captured == {
        "latitude": 48.137,
        "longitude": 11.575,
        "forecast_days": 3,
    }


def test_weather_forecast_for_unknown_installation_returns_404(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.duckdb"))

    with TestClient(app) as client:
        response = client.get(
            "/installations/00000000-0000-0000-0000-000000000000/weather-forecast"
        )

    assert response.status_code == 404
    assert response.json() == {"detail": "PV-Anlage wurde nicht gefunden."}


def test_weather_forecast_handles_missing_weather_data(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.duckdb"))

    async def fake_geocode(_: str) -> Coordinates:
        return Coordinates(latitude=48.137, longitude=11.575)

    async def fake_forecast(
        *, latitude: float, longitude: float, forecast_days: int
    ) -> list[WeatherForecastRow]:
        raise WeatherServiceError(
            "Open-Meteo hat keine vollständigen Wetterdaten geliefert."
        )

    monkeypatch.setattr("backend.main.geocode_location", fake_geocode)
    monkeypatch.setattr(
        "backend.main.open_meteo_service.get_hourly_forecast", fake_forecast
    )
    payload = {
        "name": "Anlage ohne Wetterdaten",
        "location": "München",
        "peak_power_kwp": 12.0,
        "azimuth": 180.0,
        "tilt": 30.0,
    }

    with TestClient(app) as client:
        installation = client.post("/installations", json=payload).json()
        response = client.get(
            f"/installations/{installation['id']}/weather-forecast"
        )

    assert response.status_code == 502
    assert response.json() == {
        "detail": "Open-Meteo hat keine vollständigen Wetterdaten geliefert."
    }


def test_pv_forecast_endpoint(tmp_path, monkeypatch) -> None:
    database_path = tmp_path / "test.duckdb"
    monkeypatch.setenv("DATABASE_PATH", str(database_path))

    async def fake_geocode(_: str) -> Coordinates:
        return Coordinates(latitude=48.137, longitude=11.575)

    weather = [
        WeatherForecastRow(
            timestamp="2026-06-19T12:00:00Z",
            temperature_2m=23.5,
            cloud_cover=20.0,
            direct_radiation=650.0,
            diffuse_radiation=90.0,
            wind_speed_10m=8.5,
        )
    ]

    async def fake_weather(
        *, latitude: float, longitude: float, forecast_days: int
    ) -> list[WeatherForecastRow]:
        assert (latitude, longitude, forecast_days) == (48.137, 11.575, 2)
        return weather

    captured: dict = {}

    def fake_calculate(**kwargs) -> list[PVForecastRow]:
        captured.update(kwargs)
        return [
            PVForecastRow(
                timestamp="2026-06-19T12:00:00Z",
                predicted_power_kw=7.25,
            )
        ]

    monkeypatch.setattr("backend.main.geocode_location", fake_geocode)
    monkeypatch.setattr(
        "backend.main.open_meteo_service.get_hourly_forecast", fake_weather
    )
    monkeypatch.setattr("backend.main.pv_forecast_service.calculate", fake_calculate)
    payload = {
        "name": "PV München",
        "location": "München",
        "peak_power_kwp": 12.0,
        "azimuth": 180.0,
        "tilt": 30.0,
    }

    with TestClient(app) as client:
        installation = client.post("/installations", json=payload).json()
        response = client.get(
            f"/installations/{installation['id']}/pv-forecast",
            params={"forecast_days": 2},
        )
        history_response = client.get(
            f"/installations/{installation['id']}/forecast-history"
        )

    assert response.status_code == 200
    assert response.json() == {
        "hourly": [
            {
                "timestamp": "2026-06-19T12:00:00Z",
                "predicted_power_kw": 7.25,
            }
        ],
        "daily": [
            {
                "date": "2026-06-19",
                "daily_energy_kwh": 7.25,
            }
        ],
        "metrics": {
            "peak_power_kw": 7.25,
            "peak_timestamp": "2026-06-19T12:00:00Z",
        },
    }
    assert captured["latitude"] == 48.137
    assert captured["longitude"] == 11.575
    assert captured["peak_power_kwp"] == 12.0
    assert captured["azimuth"] == 180.0
    assert captured["tilt"] == 30.0
    assert captured["weather"] == weather
    assert history_response.status_code == 200
    history = history_response.json()
    assert len(history) == 1
    assert history[0]["forecast_start"] == "2026-06-19T12:00:00Z"
    assert history[0]["forecast_end"] == "2026-06-19T12:00:00Z"
    assert history[0]["daily"] == [
        {"date": "2026-06-19", "daily_energy_kwh": 7.25}
    ]
    assert history[0]["peak_power_kw"] == 7.25
    assert history[0]["peak_timestamp"] == "2026-06-19T12:00:00Z"

    with duckdb.connect(str(database_path), read_only=True) as connection:
        assert connection.execute("SELECT count(*) FROM forecast_runs").fetchone()[
            0
        ] == 1
        assert connection.execute("SELECT count(*) FROM forecast_points").fetchone()[
            0
        ] == 1

    with TestClient(app) as client:
        delete_response = client.delete(f"/installations/{installation['id']}")

    assert delete_response.status_code == 204
    with duckdb.connect(str(database_path), read_only=True) as connection:
        assert connection.execute("SELECT count(*) FROM forecast_runs").fetchone()[
            0
        ] == 0
        assert connection.execute("SELECT count(*) FROM forecast_points").fetchone()[
            0
        ] == 0


def test_pv_forecast_for_unknown_installation_returns_404(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.duckdb"))

    with TestClient(app) as client:
        response = client.get(
            "/installations/00000000-0000-0000-0000-000000000000/pv-forecast"
        )

    assert response.status_code == 404
    assert response.json() == {"detail": "PV-Anlage wurde nicht gefunden."}


def test_forecast_history_for_unknown_installation_returns_404(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.duckdb"))

    with TestClient(app) as client:
        response = client.get(
            "/installations/00000000-0000-0000-0000-000000000000/forecast-history"
        )

    assert response.status_code == 404
    assert response.json() == {"detail": "PV-Anlage wurde nicht gefunden."}
