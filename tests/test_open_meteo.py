import asyncio

import httpx
import pytest

from backend.services.open_meteo import (
    OpenMeteoService,
    WeatherServiceError,
    WeatherServiceRateLimitError,
)


def test_open_meteo_maps_hourly_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["latitude"] == "48.137"
        assert request.url.params["longitude"] == "11.575"
        assert request.url.params["forecast_days"] == "2"
        assert request.url.params["timezone"] == "UTC"
        return httpx.Response(
            200,
            json={
                "hourly": {
                    "time": ["2026-06-19T12:00"],
                    "temperature_2m": [23.5],
                    "cloud_cover": [20.0],
                    "direct_radiation": [650.0],
                    "diffuse_radiation": [90.0],
                    "wind_speed_10m": [8.5],
                }
            },
        )

    async def run_test() -> None:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler)
        ) as client:
            service = OpenMeteoService(base_url="https://weather.test", client=client)
            rows = await service.get_hourly_forecast(48.137, 11.575, 2)

        assert len(rows) == 1
        assert rows[0].timestamp.isoformat() == "2026-06-19T12:00:00+00:00"
        assert rows[0].direct_radiation == 650.0

    asyncio.run(run_test())


def test_open_meteo_rejects_incomplete_hourly_response() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "hourly": {
                    "time": ["2026-06-19T12:00"],
                    "temperature_2m": [23.5],
                }
            },
        )

    async def run_test() -> None:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler)
        ) as client:
            service = OpenMeteoService(base_url="https://weather.test", client=client)
            with pytest.raises(WeatherServiceError, match="cloud_cover"):
                await service.get_hourly_forecast(48.137, 11.575, 2)

    asyncio.run(run_test())


def test_open_meteo_caches_nearby_coordinates() -> None:
    request_count = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        return httpx.Response(
            200,
            json={
                "hourly": {
                    "time": ["2026-06-19T12:00"],
                    "temperature_2m": [23.5],
                    "cloud_cover": [20.0],
                    "direct_radiation": [650.0],
                    "diffuse_radiation": [90.0],
                    "wind_speed_10m": [8.5],
                }
            },
        )

    async def run_test() -> None:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler)
        ) as client:
            service = OpenMeteoService(
                base_url="https://weather.test",
                client=client,
                cache_ttl_seconds=3600,
            )
            first = await service.get_hourly_forecast(48.13701, 11.57501, 2)
            second = await service.get_hourly_forecast(48.13702, 11.57502, 2)

        assert first == second

    asyncio.run(run_test())
    assert request_count == 1


def test_open_meteo_default_cache_ttl_is_one_hour(monkeypatch) -> None:
    monkeypatch.delenv("OPEN_METEO_CACHE_TTL_SECONDS", raising=False)
    service = OpenMeteoService(base_url="https://weather.test")

    assert service.cache_ttl_seconds == 3600


def test_open_meteo_translates_http_429() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"reason": "rate limit"})

    async def run_test() -> None:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler)
        ) as client:
            service = OpenMeteoService(
                base_url="https://weather.test", client=client
            )
            with pytest.raises(
                WeatherServiceRateLimitError,
                match="Wetterdienst ist kurzzeitig ausgelastet",
            ):
                await service.get_hourly_forecast(48.137, 11.575, 2)

    asyncio.run(run_test())


def test_open_meteo_logs_http_error_context(caplog) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="upstream unavailable")

    async def run_test() -> None:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler)
        ) as client:
            service = OpenMeteoService(
                base_url="https://weather.test/forecast", client=client
            )
            with pytest.raises(WeatherServiceError):
                await service.get_hourly_forecast(59.32512, 18.07109, 3)

    caplog.set_level("ERROR", logger="backend.services.open_meteo")
    asyncio.run(run_test())

    log_text = caplog.text
    assert "status_code=503" in log_text
    assert "https://weather.test/forecast" in log_text
    assert "latitude=59.32512" in log_text
    assert "longitude=18.07109" in log_text
    assert "forecast_days=3" in log_text
    assert "response_body=upstream unavailable" in log_text


def test_open_meteo_logs_request_and_json_errors(caplog) -> None:
    def connection_error(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("DNS lookup failed", request=request)

    def invalid_json(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="not-json")

    async def run_test() -> None:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(connection_error)
        ) as client:
            service = OpenMeteoService(
                base_url="https://weather.test/connect", client=client
            )
            with pytest.raises(WeatherServiceError):
                await service.get_hourly_forecast(59.32512, 18.07109, 1)

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(invalid_json)
        ) as client:
            service = OpenMeteoService(
                base_url="https://weather.test/json", client=client
            )
            with pytest.raises(WeatherServiceError):
                await service.get_hourly_forecast(59.32512, 18.07109, 2)

    caplog.set_level("ERROR", logger="backend.services.open_meteo")
    asyncio.run(run_test())

    log_text = caplog.text
    assert "exception_type=ConnectError" in log_text
    assert "exception_message=DNS lookup failed" in log_text
    assert "https://weather.test/connect" in log_text
    assert "JSON parsing error" in log_text
    assert "https://weather.test/json" in log_text
    assert "response_body=not-json" in log_text
