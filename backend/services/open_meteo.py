import asyncio
import os
import time
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


class WeatherServiceRateLimitError(WeatherServiceError):
    """Raised when Open-Meteo temporarily rate-limits requests."""


class OpenMeteoService:
    def __init__(
        self,
        base_url: str | None = None,
        client: httpx.AsyncClient | None = None,
        cache_ttl_seconds: float | None = None,
        cache_max_entries: int = 512,
    ) -> None:
        self.base_url = base_url or os.getenv(
            "OPEN_METEO_URL", "https://api.open-meteo.com/v1/forecast"
        )
        self._client = client
        self.cache_ttl_seconds = (
            cache_ttl_seconds
            if cache_ttl_seconds is not None
            else float(os.getenv("OPEN_METEO_CACHE_TTL_SECONDS", "900"))
        )
        self._cache: dict[
            tuple[float, float, int],
            tuple[float, tuple[WeatherForecastRow, ...]],
        ] = {}
        self.cache_max_entries = max(cache_max_entries, 1)
        self._cache_lock = asyncio.Lock()

    async def get_hourly_forecast(
        self,
        latitude: float,
        longitude: float,
        forecast_days: int,
    ) -> list[WeatherForecastRow]:
        """Load an hourly weather forecast for a location and period."""
        if not 1 <= forecast_days <= 16:
            raise ValueError("forecast_days must be between 1 and 16")

        cache_key = (round(latitude, 4), round(longitude, 4), forecast_days)

        async with self._cache_lock:
            cached = self._cache.get(cache_key)
            now = time.monotonic()
            expired_keys = [
                key
                for key, (cached_at, _) in self._cache.items()
                if now - cached_at >= self.cache_ttl_seconds
            ]
            for expired_key in expired_keys:
                self._cache.pop(expired_key, None)
            if cached is not None:
                cached_at, cached_rows = cached
                if now - cached_at < self.cache_ttl_seconds:
                    return list(cached_rows)

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
                if exc.response.status_code == 429:
                    raise WeatherServiceRateLimitError(
                        "Der Wetterdienst ist kurzzeitig ausgelastet. "
                        "Bitte in einigen Minuten erneut versuchen."
                    ) from exc
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

            rows = self._parse_hourly_data(payload)
            if len(self._cache) >= self.cache_max_entries:
                oldest_key = min(
                    self._cache, key=lambda key: self._cache[key][0]
                )
                self._cache.pop(oldest_key, None)
            self._cache[cache_key] = (time.monotonic(), tuple(rows))
            return list(rows)

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
