import os
from datetime import datetime, timezone
from typing import Any

import httpx

from backend.models import WeatherForecastRow


HOURLY_FIELDS = (
    "temperature_2m",
    "cloud_cover",
    "direct_radiation",
    "diffuse_radiation",
    "wind_speed_10m",
)


class WeatherServiceError(Exception):
    """Base error for failures while loading or parsing weather data."""


class WeatherServiceTimeoutError(WeatherServiceError):
    """Raised when Open-Meteo does not respond in time."""


class OpenMeteoService:
    def __init__(
        self,
        base_url: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = base_url or os.getenv(
            "OPEN_METEO_URL", "https://api.open-meteo.com/v1/forecast"
        )
        self._client = client

    async def get_hourly_forecast(
        self,
        latitude: float,
        longitude: float,
        forecast_days: int,
    ) -> list[WeatherForecastRow]:
        """Load an hourly weather forecast for a location and period."""
        if not 1 <= forecast_days <= 16:
            raise ValueError("forecast_days must be between 1 and 16")

        params = {
            "latitude": latitude,
            "longitude": longitude,
            "hourly": ",".join(HOURLY_FIELDS),
            "forecast_days": forecast_days,
            "timezone": "UTC",
        }

        try:
            if self._client is not None:
                response = await self._client.get(self.base_url, params=params)
            else:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    response = await client.get(self.base_url, params=params)
            response.raise_for_status()
            payload = response.json()
        except httpx.TimeoutException as exc:
            raise WeatherServiceTimeoutError(
                "Open-Meteo hat nicht rechtzeitig geantwortet."
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise WeatherServiceError(
                f"Open-Meteo hat mit HTTP {exc.response.status_code} geantwortet."
            ) from exc
        except httpx.RequestError as exc:
            raise WeatherServiceError(
                "Open-Meteo ist derzeit nicht erreichbar."
            ) from exc
        except ValueError as exc:
            raise WeatherServiceError(
                "Open-Meteo hat keine gültige JSON-Antwort geliefert."
            ) from exc

        return self._parse_hourly_data(payload)

    @staticmethod
    def _parse_hourly_data(payload: Any) -> list[WeatherForecastRow]:
        if not isinstance(payload, dict) or not isinstance(payload.get("hourly"), dict):
            raise WeatherServiceError(
                "Die Open-Meteo-Antwort enthält keine stündlichen Wetterdaten."
            )

        hourly = payload["hourly"]
        times = hourly.get("time")
        if not isinstance(times, list):
            raise WeatherServiceError(
                "Die Open-Meteo-Antwort enthält keine gültigen Zeitstempel."
            )

        expected_length = len(times)
        for field in HOURLY_FIELDS:
            values = hourly.get(field)
            if not isinstance(values, list) or len(values) != expected_length:
                raise WeatherServiceError(
                    f"Das Wetterfeld „{field}“ fehlt oder ist unvollständig."
                )

        rows: list[WeatherForecastRow] = []
        try:
            for index, timestamp in enumerate(times):
                parsed_timestamp = datetime.fromisoformat(timestamp)
                if parsed_timestamp.tzinfo is None:
                    parsed_timestamp = parsed_timestamp.replace(tzinfo=timezone.utc)
                rows.append(
                    WeatherForecastRow(
                        timestamp=parsed_timestamp,
                        temperature_2m=hourly["temperature_2m"][index],
                        cloud_cover=hourly["cloud_cover"][index],
                        direct_radiation=hourly["direct_radiation"][index],
                        diffuse_radiation=hourly["diffuse_radiation"][index],
                        wind_speed_10m=hourly["wind_speed_10m"][index],
                    )
                )
        except (TypeError, ValueError, KeyError) as exc:
            raise WeatherServiceError(
                "Die Open-Meteo-Antwort enthält ungültige Wetterwerte."
            ) from exc

        return rows


open_meteo_service = OpenMeteoService()
