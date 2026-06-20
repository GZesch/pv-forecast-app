import asyncio

import httpx
import pytest

from backend.services.open_meteo import OpenMeteoService, WeatherServiceError


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
