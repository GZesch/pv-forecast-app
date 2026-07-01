"""Normalized, timezone-aware PVGIS TMY weather data."""

from dataclasses import dataclass
from datetime import datetime


class WeatherDataError(ValueError):
    """Raised when external weather data cannot be normalized safely."""


@dataclass(frozen=True, slots=True)
class WeatherHour:
    """One UTC hour of irradiance and ambient conditions."""

    timestamp: datetime
    ghi_w_m2: float
    dni_w_m2: float
    dhi_w_m2: float
    temperature_c: float
    wind_speed_m_s: float


@dataclass(frozen=True, slots=True)
class TMYMetadata:
    """Provenance retained from the PVGIS 5.3 TMY response."""

    radiation_database: str
    source_period: str | None
    selected_months: tuple[tuple[int, int], ...]
    retrieved_at: datetime
    api_endpoint: str
    irradiance_time_offset_minutes: float | None = None


@dataclass(frozen=True, slots=True)
class TMYWeather:
    """A canonical non-leap year (2001) containing exactly 8,760 UTC hours."""

    latitude: float
    longitude: float
    hours: tuple[WeatherHour, ...]
    metadata: TMYMetadata
