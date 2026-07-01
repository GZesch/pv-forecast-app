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

    radiation_database: str | None
    source_period: str | None
    selected_months: tuple[tuple[int, int], ...]
    retrieved_at: datetime
    api_endpoint: str
    irradiance_time_offset_hours: float | None = None


@dataclass(frozen=True, slots=True)
class TMYWeather:
    """A canonical non-leap year (2001) containing exactly 8,760 UTC hours."""

    latitude: float
    longitude: float
    hours: tuple[WeatherHour, ...]
    metadata: TMYMetadata


@dataclass(frozen=True, slots=True)
class POAWeatherHour:
    """One UTC hour with irradiance already transposed to a PV surface."""

    timestamp: datetime
    direct_poa_w_m2: float
    diffuse_poa_w_m2: float
    ground_reflected_poa_w_m2: float
    temperature_c: float
    wind_speed_m_s: float


@dataclass(frozen=True, slots=True)
class HistoricalYear:
    """One real source year normalized to canonical non-leap calendar positions."""

    source_year: int
    hours: tuple[POAWeatherHour, ...]


@dataclass(frozen=True, slots=True)
class HistoricalMetadata:
    radiation_database: str
    source_period: str
    source_start_year: int
    source_end_year: int
    retrieved_at: datetime
    api_endpoint: str
    leap_day_normalization: str


@dataclass(frozen=True, slots=True)
class HistoricalPOAWeather:
    latitude: float
    longitude: float
    years: tuple[HistoricalYear, ...]
    metadata: HistoricalMetadata
