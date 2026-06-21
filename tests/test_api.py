import duckdb
from fastapi.testclient import TestClient as FastAPITestClient
from uuid import UUID

from backend.geocoding import Coordinates, LocationNotFoundError
from backend.database import initialize_database, list_installations
from backend.main import app
from backend.models import PVForecastRow, WeatherForecastRow
from backend.services.open_meteo import (
    WeatherServiceError,
    WeatherServiceRateLimitError,
)


SESSION_HEADERS = {"X-Session-ID": "11111111-1111-1111-1111-111111111111"}
OTHER_SESSION_HEADERS = {"X-Session-ID": "22222222-2222-2222-2222-222222222222"}


class TestClient(FastAPITestClient):
    def __init__(self, application, **kwargs) -> None:
        headers = {**SESSION_HEADERS, **kwargs.pop("headers", {})}
        super().__init__(application, headers=headers, **kwargs)


def test_weather_forecast_route_is_registered() -> None:
    matching_routes = [
        route
        for route in app.routes
        if getattr(route, "path", None)
        == "/installations/{installation_id}/weather-forecast"
    ]

    assert len(matching_routes) == 1
    assert "GET" in matching_routes[0].methods


def test_debug_open_meteo_endpoint(monkeypatch) -> None:
    captured: dict = {}

    async def fake_forecast(**kwargs) -> list[WeatherForecastRow]:
        captured.update(kwargs)
        return [
            WeatherForecastRow(
                timestamp="2026-06-21T00:00:00Z",
                temperature_2m=15.0,
                cloud_cover=20.0,
                direct_radiation=0.0,
                diffuse_radiation=0.0,
                wind_speed_10m=2.0,
            )
        ]

    monkeypatch.setattr(
        "backend.main.open_meteo_service.get_hourly_forecast", fake_forecast
    )
    with TestClient(app) as client:
        response = client.get(
            "/debug/open-meteo?lat=59.32512&lon=18.07109"
        )

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["hourly_rows"] == 1
    assert captured == {
        "latitude": 59.32512,
        "longitude": 18.07109,
        "forecast_days": 1,
        "force_refresh": True,
    }


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
        assert created["location_label"] == payload["location"]
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


def test_update_installation_regeocodes_and_updates_all_values(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.duckdb"))

    async def fake_geocode(location: str) -> Coordinates:
        if location == "Uppsala":
            return Coordinates(latitude=59.8586, longitude=17.6389)
        return Coordinates(latitude=59.3293, longitude=18.0686)

    monkeypatch.setattr("backend.main.geocode_location", fake_geocode)
    create_payload = {
        "name": "Dach Stockholm",
        "location": "Stockholm",
        "peak_power_kwp": 5.0,
        "azimuth": 180.0,
        "tilt": 30.0,
    }
    update_payload = {
        "name": "Dach Uppsala",
        "location": "Uppsala",
        "peak_power_kwp": 8.5,
        "azimuth": 135.0,
        "tilt": 42.0,
    }

    with TestClient(app) as client:
        installation = client.post(
            "/installations", json=create_payload
        ).json()
        response = client.put(
            f"/installations/{installation['id']}", json=update_payload
        )
        listed = client.get("/installations").json()[0]

    assert response.status_code == 200
    updated = response.json()
    assert updated["name"] == "Dach Uppsala"
    assert updated["location_label"] == "Uppsala"
    assert updated["latitude"] == 59.8586
    assert updated["longitude"] == 17.6389
    assert updated["peak_power_kwp"] == 8.5
    assert updated["azimuth"] == 135.0
    assert updated["tilt"] == 42.0
    assert listed == updated


def test_update_unknown_installation_returns_404(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.duckdb"))
    payload = {
        "name": "Unbekannt",
        "location": "Berlin",
        "peak_power_kwp": 5.0,
        "azimuth": 180.0,
        "tilt": 30.0,
    }

    with TestClient(app) as client:
        response = client.put(
            "/installations/00000000-0000-0000-0000-000000000000",
            json=payload,
        )

    assert response.status_code == 404
    assert response.json() == {"detail": "PV-Anlage wurde nicht gefunden."}


def test_update_installation_accepts_expert_coordinates_for_same_location(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.duckdb"))
    geocode_calls = 0

    async def fake_geocode(_: str) -> Coordinates:
        nonlocal geocode_calls
        geocode_calls += 1
        return Coordinates(latitude=52.52, longitude=13.405)

    monkeypatch.setattr("backend.main.geocode_location", fake_geocode)
    payload = {
        "name": "Dach",
        "location": "Berlin",
        "peak_power_kwp": 5.0,
        "azimuth": 180.0,
        "tilt": 30.0,
    }

    with TestClient(app) as client:
        installation = client.post("/installations", json=payload).json()
        response = client.put(
            f"/installations/{installation['id']}",
            json={
                **payload,
                "latitude": 52.5001,
                "longitude": 13.4001,
            },
        )

    assert response.status_code == 200
    assert response.json()["latitude"] == 52.5001
    assert response.json()["longitude"] == 13.4001
    assert geocode_calls == 1


def test_original_stockholm_location_is_persisted_and_listed(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.duckdb"))

    async def fake_geocode(_: str) -> Coordinates:
        return Coordinates(
            latitude=59.3293,
            longitude=18.0686,
            location_label="Stockholm, Sverige",
        )

    monkeypatch.setattr("backend.main.geocode_location", fake_geocode)
    payload = {
        "name": "Anlage Stockholm",
        "location": "Stockholm",
        "peak_power_kwp": 8.0,
        "azimuth": 180.0,
        "tilt": 30.0,
    }

    with TestClient(app) as client:
        response = client.post("/installations", json=payload)
        list_response = client.get("/installations")

    assert response.status_code == 201
    assert response.json()["location_label"] == "Stockholm"
    assert list_response.status_code == 200
    assert list_response.json()[0]["location_label"] == "Stockholm"


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


def test_installation_endpoints_require_session_header(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.duckdb"))
    unknown_id = "00000000-0000-0000-0000-000000000000"

    with FastAPITestClient(app) as client:
        responses = [
            client.post(
                "/installations",
                json={
                    "name": "Ohne Session",
                    "location": "Berlin",
                    "peak_power_kwp": 5.0,
                    "azimuth": 180.0,
                    "tilt": 30.0,
                },
            ),
            client.get("/installations"),
            client.get(f"/installations/{unknown_id}"),
            client.put(
                f"/installations/{unknown_id}",
                json={
                    "name": "Ohne Session",
                    "location": "Berlin",
                    "peak_power_kwp": 5.0,
                    "azimuth": 180.0,
                    "tilt": 30.0,
                },
            ),
            client.delete(f"/installations/{unknown_id}"),
            client.get(f"/installations/{unknown_id}/weather-forecast"),
            client.get(f"/installations/{unknown_id}/pv-forecast"),
            client.get(f"/installations/{unknown_id}/forecast-history"),
            client.get("/plants"),
            client.get(f"/plants/{unknown_id}"),
            client.get(f"/plants/{unknown_id}/pv-forecast"),
        ]

    assert all(response.status_code == 400 for response in responses)
    assert all("X-Session-ID" in response.json()["detail"] for response in responses)


def test_invalid_session_header_returns_400(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.duckdb"))

    with FastAPITestClient(
        app, headers={"X-Session-ID": "keine-uuid"}
    ) as client:
        response = client.get("/installations")

    assert response.status_code == 400
    assert "gültige UUID" in response.json()["detail"]


def test_sessions_cannot_access_each_others_installations(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.duckdb"))

    async def fake_geocode(_: str) -> Coordinates:
        return Coordinates(latitude=52.52, longitude=13.405)

    monkeypatch.setattr("backend.main.geocode_location", fake_geocode)
    payload = {
        "name": "Private Anlage",
        "location": "Berlin",
        "peak_power_kwp": 8.0,
        "azimuth": 180.0,
        "tilt": 30.0,
    }

    with TestClient(app) as owner:
        installation = owner.post("/installations", json=payload).json()
        assert installation["location_label"] == "Berlin"

    with TestClient(app, headers=OTHER_SESSION_HEADERS) as visitor:
        assert visitor.get("/installations").json() == []
        protected_responses = [
            visitor.get(f"/installations/{installation['id']}"),
            visitor.put(
                f"/installations/{installation['id']}",
                json={
                    "name": "Fremd geändert",
                    "location": "Hamburg",
                    "peak_power_kwp": 10.0,
                    "azimuth": 90.0,
                    "tilt": 20.0,
                },
            ),
            visitor.delete(f"/installations/{installation['id']}"),
            visitor.get(
                f"/installations/{installation['id']}/weather-forecast"
            ),
            visitor.get(f"/installations/{installation['id']}/pv-forecast"),
            visitor.get(
                f"/installations/{installation['id']}/forecast-history"
            ),
        ]

    assert all(response.status_code == 404 for response in protected_responses)

    with TestClient(app) as owner:
        assert owner.get(f"/installations/{installation['id']}").status_code == 200


def test_database_migration_adds_optional_location_label(tmp_path, monkeypatch) -> None:
    database_path = tmp_path / "legacy.duckdb"
    monkeypatch.setenv("DATABASE_PATH", str(database_path))
    session_id = UUID("11111111-1111-1111-1111-111111111111")

    with duckdb.connect(str(database_path)) as connection:
        connection.execute(
            """
            CREATE TABLE installations (
                id UUID PRIMARY KEY,
                session_id UUID NOT NULL,
                name TEXT NOT NULL,
                latitude DOUBLE NOT NULL,
                longitude DOUBLE NOT NULL,
                peak_power_kwp DOUBLE NOT NULL,
                azimuth DOUBLE NOT NULL,
                tilt DOUBLE NOT NULL,
                created_at TIMESTAMP NOT NULL
            )
            """
        )
        connection.execute(
            """
            INSERT INTO installations VALUES (
                'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
                ?, 'Legacy-Anlage', 52.52, 13.405, 8.0, 180.0, 30.0,
                '2026-01-01 12:00:00'
            )
            """,
            [session_id],
        )

    initialize_database()

    with duckdb.connect(str(database_path), read_only=True) as connection:
        columns = {
            row[1]
            for row in connection.execute(
                "PRAGMA table_info('installations')"
            ).fetchall()
        }

    assert "session_id" in columns
    assert "location_label" in columns
    assert "plant_id" in columns
    with duckdb.connect(str(database_path), read_only=True) as connection:
        plant_table_exists = connection.execute(
            """
            SELECT count(*) FROM information_schema.tables
            WHERE table_name = 'plants'
            """
        ).fetchone()[0]
    assert plant_table_exists == 1
    legacy_installations = list_installations(session_id)
    assert len(legacy_installations) == 1
    assert legacy_installations[0]["name"] == "Legacy-Anlage"
    assert legacy_installations[0]["location_label"].startswith("52.52, 13.4")


def test_plant_crud_and_installation_assignment(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.duckdb"))

    async def fake_geocode(_: str) -> Coordinates:
        return Coordinates(latitude=52.52, longitude=13.405)

    monkeypatch.setattr("backend.main.geocode_location", fake_geocode)
    installation_payload = {
        "name": "Hausdach Ost",
        "location": "Berlin",
        "peak_power_kwp": 5.0,
        "azimuth": 90.0,
        "tilt": 30.0,
    }

    with TestClient(app) as client:
        installation = client.post(
            "/installations", json=installation_payload
        ).json()
        create_response = client.post(
            "/plants",
            json={"name": "Wohnhaus", "location_label": "Berlin"},
        )
        plant = create_response.json()

        assert create_response.status_code == 201
        assert client.get("/plants").json() == [plant]
        assert client.get(f"/plants/{plant['id']}").json() == plant

        assign_response = client.post(
            f"/plants/{plant['id']}/installations/{installation['id']}"
        )
        assigned_installation = client.get(
            f"/installations/{installation['id']}"
        ).json()
        assert assign_response.status_code == 204
        assert assigned_installation["plant_id"] == plant["id"]

        remove_response = client.delete(
            f"/plants/{plant['id']}/installations/{installation['id']}"
        )
        unassigned_installation = client.get(
            f"/installations/{installation['id']}"
        ).json()
        assert remove_response.status_code == 204
        assert unassigned_installation["plant_id"] is None

        assert client.post(
            f"/plants/{plant['id']}/installations/{installation['id']}"
        ).status_code == 204
        assert client.delete(f"/plants/{plant['id']}").status_code == 204
        assert client.get(f"/plants/{plant['id']}").status_code == 404
        assert client.get(f"/installations/{installation['id']}").json()[
            "plant_id"
        ] is None


def test_update_plant_and_reject_unknown_or_foreign_id(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.duckdb"))

    with TestClient(app) as owner:
        plant = owner.post(
            "/plants",
            json={"name": "Alt", "location_label": "Berlin"},
        ).json()
        response = owner.put(
            f"/plants/{plant['id']}",
            json={"name": "Wohnhaus", "location_label": "Potsdam"},
        )
        unknown_response = owner.put(
            "/plants/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            json={"name": "Unbekannt", "location_label": None},
        )

    assert response.status_code == 200
    assert response.json()["name"] == "Wohnhaus"
    assert response.json()["location_label"] == "Potsdam"
    assert unknown_response.status_code == 404

    with TestClient(app, headers=OTHER_SESSION_HEADERS) as visitor:
        foreign_response = visitor.put(
            f"/plants/{plant['id']}",
            json={"name": "Übernommen", "location_label": "Hamburg"},
        )
        assert foreign_response.status_code == 404

    with TestClient(app) as owner:
        unchanged = owner.get(f"/plants/{plant['id']}").json()
        assert unchanged["name"] == "Wohnhaus"
        assert unchanged["location_label"] == "Potsdam"


def test_plant_forecast_sums_component_installations(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.duckdb"))

    async def fake_geocode(_: str) -> Coordinates:
        return Coordinates(latitude=52.52, longitude=13.405)

    weather_calls = 0

    async def fake_weather(**_) -> list[WeatherForecastRow]:
        nonlocal weather_calls
        weather_calls += 1
        return [
            WeatherForecastRow(
                timestamp="2026-06-20T10:00:00Z",
                temperature_2m=20.0,
                cloud_cover=10.0,
                direct_radiation=500.0,
                diffuse_radiation=100.0,
                wind_speed_10m=2.0,
            )
        ]

    def fake_calculate(**kwargs) -> list[PVForecastRow]:
        if kwargs["peak_power_kwp"] == 5.0:
            powers = (1.0, 2.0)
        elif kwargs["peak_power_kwp"] == 6.0:
            powers = (3.0, 1.0)
        else:
            powers = (2.0, 2.0)
        return [
            PVForecastRow(
                timestamp="2026-06-20T10:00:00Z", predicted_power_kw=powers[0]
            ),
            PVForecastRow(
                timestamp="2026-06-20T11:00:00Z", predicted_power_kw=powers[1]
            ),
        ]

    monkeypatch.setattr("backend.main.geocode_location", fake_geocode)
    monkeypatch.setattr(
        "backend.main.open_meteo_service.get_hourly_forecast", fake_weather
    )
    monkeypatch.setattr("backend.main.pv_forecast_service.calculate", fake_calculate)

    with TestClient(app) as client:
        plant = client.post("/plants", json={"name": "Gesamt"}).json()
        installations = []
        for name, peak, azimuth in (
            ("Ost", 5.0, 90.0),
            ("West", 6.0, 270.0),
            ("Gartenschuppen", 2.5, 180.0),
        ):
            installation = client.post(
                "/installations",
                json={
                    "name": name,
                    "location": "Berlin",
                    "peak_power_kwp": peak,
                    "azimuth": azimuth,
                    "tilt": 30.0,
                },
            ).json()
            installations.append(installation)
            assert client.post(
                f"/plants/{plant['id']}/installations/{installation['id']}"
            ).status_code == 204

        response = client.get(f"/plants/{plant['id']}/pv-forecast")

    assert response.status_code == 200
    assert weather_calls == 1
    payload = response.json()
    assert payload["hourly"] == [
        {"timestamp": "2026-06-20T10:00:00Z", "predicted_power_kw": 6.0},
        {"timestamp": "2026-06-20T11:00:00Z", "predicted_power_kw": 5.0},
    ]
    assert payload["daily"] == [
        {"date": "2026-06-20", "daily_energy_kwh": 11.0}
    ]
    assert payload["metrics"] == {
        "peak_power_kw": 6.0,
        "peak_timestamp": "2026-06-20T10:00:00Z",
    }
    assert [component["name"] for component in payload["components"]] == [
        "Ost",
        "West",
        "Gartenschuppen",
    ]


def test_plant_session_isolation(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.duckdb"))

    async def fake_geocode(_: str) -> Coordinates:
        return Coordinates(latitude=52.52, longitude=13.405)

    monkeypatch.setattr("backend.main.geocode_location", fake_geocode)

    with TestClient(app) as owner:
        plant = owner.post("/plants", json={"name": "Privates Kraftwerk"}).json()
        installation = owner.post(
            "/installations",
            json={
                "name": "Private Anlage",
                "location": "Berlin",
                "peak_power_kwp": 5.0,
                "azimuth": 180.0,
                "tilt": 30.0,
            },
        ).json()

    with TestClient(app, headers=OTHER_SESSION_HEADERS) as visitor:
        assert visitor.get("/plants").json() == []
        assert visitor.get(f"/plants/{plant['id']}").status_code == 404
        assert visitor.delete(f"/plants/{plant['id']}").status_code == 404
        assert visitor.get(f"/plants/{plant['id']}/pv-forecast").status_code == 404
        visitor_plant = visitor.post(
            "/plants", json={"name": "Fremdes Kraftwerk"}
        ).json()
        assert visitor.post(
            f"/plants/{visitor_plant['id']}/installations/{installation['id']}"
        ).status_code == 404


def test_plant_forecast_returns_friendly_rate_limit_error(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.duckdb"))

    async def fake_geocode(_: str) -> Coordinates:
        return Coordinates(latitude=52.52, longitude=13.405)

    async def rate_limited_weather(**_) -> list[WeatherForecastRow]:
        raise WeatherServiceRateLimitError(
            "Der Wetterdienst ist kurzzeitig ausgelastet. "
            "Bitte in einigen Minuten erneut versuchen."
        )

    monkeypatch.setattr("backend.main.geocode_location", fake_geocode)
    monkeypatch.setattr(
        "backend.main.open_meteo_service.get_hourly_forecast",
        rate_limited_weather,
    )

    with TestClient(app) as client:
        plant = client.post("/plants", json={"name": "Gesamt"}).json()
        installation = client.post(
            "/installations",
            json={
                "name": "Dach",
                "location": "Berlin",
                "peak_power_kwp": 5.0,
                "azimuth": 180.0,
                "tilt": 30.0,
            },
        ).json()
        client.post(
            f"/plants/{plant['id']}/installations/{installation['id']}"
        )
        response = client.get(f"/plants/{plant['id']}/pv-forecast")

    assert response.status_code == 503
    assert response.json() == {
        "detail": (
            "Der Wetterdienst ist kurzzeitig ausgelastet. "
            "Bitte in einigen Minuten erneut versuchen."
        )
    }
