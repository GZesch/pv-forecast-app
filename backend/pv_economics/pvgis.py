"""Async infrastructure adapter for the official PVGIS 5.3 TMY API."""

from datetime import datetime, timedelta, timezone
from collections import defaultdict
from calendar import isleap
from math import isfinite
from typing import Any

import httpx

from .weather import (
    HistoricalMetadata, HistoricalPOAWeather, HistoricalYear, POAWeatherHour,
    TMYMetadata, TMYWeather, WeatherDataError, WeatherHour,
)

PVGIS_TMY_URL = "https://re.jrc.ec.europa.eu/api/v5_3/tmy"
PVGIS_SERIES_URL = "https://re.jrc.ec.europa.eu/api/v5_3/seriescalc"
CANONICAL_TMY_YEAR = 2001
EXPECTED_HOURS = 8760
NEGATIVE_IRRADIANCE_TOLERANCE = -0.1
_TMY_TIMESTAMP_FIELDS = ("time", "time(UTC)")


class PVGISError(Exception):
    """Base error for PVGIS access and response failures."""


class PVGISTimeoutError(PVGISError):
    """PVGIS did not answer within the configured timeout."""


class PVGISTemporaryError(PVGISError):
    """A retryable external PVGIS overload (HTTP 529)."""


class PVGISResponseError(PVGISError):
    """PVGIS returned an unusable response."""


class PVGISTMYClient:
    """Fetch non-persistent SARAH3 TMY data using coordinates only."""

    def __init__(
        self, *, base_url: str = PVGIS_TMY_URL,
        client: httpx.AsyncClient | None = None, timeout_seconds: float = 20.0,
    ) -> None:
        self.base_url = base_url
        self._client = client
        self.timeout_seconds = timeout_seconds

    async def fetch(self, latitude: float, longitude: float) -> TMYWeather:
        _validate_coordinates(latitude, longitude)
        params = {"lat": latitude, "lon": longitude, "outputformat": "json",
                  "raddatabase": "PVGIS-SARAH3", "usehorizon": 1}
        headers = {"User-Agent": "ExergyPulse-PV-Economics/1.0"}
        try:
            if self._client is None:
                async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                    response = await client.get(self.base_url, params=params, headers=headers)
            else:
                response = await self._client.get(
                    self.base_url, params=params, headers=headers,
                    timeout=self.timeout_seconds,
                )
        except httpx.TimeoutException as exc:
            raise PVGISTimeoutError("PVGIS did not respond in time.") from exc
        except httpx.RequestError as exc:
            raise PVGISError("PVGIS is currently unreachable.") from exc
        if response.status_code == 529:
            raise PVGISTemporaryError("PVGIS is temporarily overloaded; retry later.")
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise PVGISError(f"PVGIS returned HTTP status {response.status_code}.") from exc
        try:
            payload = response.json()
        except ValueError as exc:
            raise PVGISResponseError("PVGIS returned invalid JSON.") from exc
        try:
            return parse_pvgis_tmy(payload, latitude, longitude, self.base_url)
        except WeatherDataError as exc:
            raise PVGISResponseError(str(exc)) from exc


def pvgis_series_azimuth(exergypulse_azimuth_deg: float) -> float:
    """Convert north-clockwise azimuth to PVGIS south-zero (-90 east, +90 west)."""
    if not isfinite(exergypulse_azimuth_deg) or not 0 <= exergypulse_azimuth_deg <= 360:
        raise PVGISError("PV surface azimuth is outside the valid range.")
    converted = (exergypulse_azimuth_deg - 180 + 180) % 360 - 180
    return -180.0 if converted == 180 else float(converted)


class PVGISHistoricalClient:
    """Fetch non-persistent, surface-specific SARAH3 seriescalc data."""

    def __init__(self, *, base_url: str = PVGIS_SERIES_URL,
                 client: httpx.AsyncClient | None = None,
                 timeout_seconds: float = 60.0,
                 start_year: int = 2005, end_year: int = 2023) -> None:
        self.base_url = base_url
        self._client = client
        self.timeout_seconds = timeout_seconds
        self.start_year = start_year
        self.end_year = end_year

    async def fetch(self, latitude: float, longitude: float, *,
                    tilt_deg: float, azimuth_deg: float) -> HistoricalPOAWeather:
        _validate_coordinates(latitude, longitude)
        if not isfinite(tilt_deg) or not 0 <= tilt_deg <= 90:
            raise PVGISError("PV surface tilt is outside the valid range.")
        params = {
            "lat": latitude, "lon": longitude, "raddatabase": "PVGIS-SARAH3",
            "usehorizon": 1, "startyear": self.start_year, "endyear": self.end_year,
            "pvcalculation": 0, "components": 1, "outputformat": "json",
            "angle": tilt_deg, "aspect": pvgis_series_azimuth(azimuth_deg),
        }
        headers = {"User-Agent": "ExergyPulse-PV-Economics/1.0"}
        try:
            if self._client is None:
                async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                    response = await client.get(self.base_url, params=params, headers=headers)
            else:
                response = await self._client.get(self.base_url, params=params,
                                                  headers=headers, timeout=self.timeout_seconds)
        except httpx.TimeoutException as exc:
            raise PVGISTimeoutError("PVGIS historical request timed out.") from exc
        except httpx.RequestError as exc:
            raise PVGISError("PVGIS historical data is currently unreachable.") from exc
        if response.status_code == 529:
            raise PVGISTemporaryError("PVGIS is temporarily overloaded; retry later.")
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise PVGISError(f"PVGIS returned HTTP status {response.status_code}.") from exc
        try:
            payload = response.json()
        except ValueError as exc:
            raise PVGISResponseError("PVGIS returned invalid JSON.") from exc
        try:
            result = parse_pvgis_historical(
                payload, latitude, longitude, self.base_url)
        except WeatherDataError as exc:
            raise PVGISResponseError(str(exc)) from exc
        expected_years = tuple(range(self.start_year, self.end_year + 1))
        actual_years = tuple(year.source_year for year in result.years)
        if actual_years != expected_years:
            raise PVGISResponseError(
                "PVGIS historical response does not cover the exact requested period."
            )
        if (result.metadata.source_start_year != self.start_year
                or result.metadata.source_end_year != self.end_year):
            raise PVGISResponseError(
                "PVGIS historical period metadata does not match the requested period."
            )
        return result


def parse_pvgis_historical(payload: Any, latitude: float, longitude: float,
                           endpoint: str = PVGIS_SERIES_URL, *,
                           retrieved_at: datetime | None = None) -> HistoricalPOAWeather:
    """Validate complete real years and remove only all 24 hours of 29 February."""
    if not isinstance(payload, dict) or not isinstance(payload.get("outputs"), dict):
        raise WeatherDataError("PVGIS historical response is missing outputs.")
    rows = payload["outputs"].get("hourly")
    if not isinstance(rows, list) or not rows:
        raise WeatherDataError("PVGIS historical response contains no hourly data.")
    grouped: dict[int, list[tuple[datetime, POAWeatherHour]]] = defaultdict(list)
    for row in rows:
        if not isinstance(row, dict):
            raise WeatherDataError("PVGIS historical response contains an invalid row.")
        try:
            stamp = datetime.strptime(str(row["time"]), "%Y%m%d:%H%M").replace(tzinfo=timezone.utc)
            direct = _historical_irradiance(row["Gb(i)"], "direct POA")
            diffuse = _historical_irradiance(row["Gd(i)"], "diffuse POA")
            ground = _historical_irradiance(row["Gr(i)"], "ground-reflected POA")
            temperature = _finite(row["T2m"], "temperature")
            wind = _finite(row["WS10m"], "wind speed")
        except (KeyError, TypeError, ValueError) as exc:
            if isinstance(exc, WeatherDataError):
                raise
            raise WeatherDataError("PVGIS historical row has missing or invalid fields.") from exc
        if wind < 0:
            raise WeatherDataError("PVGIS historical wind speed must not be negative.")
        grouped[stamp.year].append((stamp, POAWeatherHour(stamp, direct, diffuse,
                                                         ground, temperature, wind)))
    years: list[HistoricalYear] = []
    for year, values in sorted(grouped.items()):
        expected_count = 8784 if isleap(year) else 8760
        stamps = [stamp for stamp, _ in values]
        if len(values) != expected_count or len(set(stamps)) != expected_count or stamps != sorted(stamps):
            raise WeatherDataError(f"PVGIS historical year {year} is incomplete or duplicated.")
        minute = stamps[0].minute
        expected = [datetime(year, 1, 1, 0, minute, tzinfo=timezone.utc) + i * _ONE_HOUR
                    for i in range(expected_count)]
        if stamps != expected:
            raise WeatherDataError(f"PVGIS historical year {year} contains gaps or invalid positions.")
        if isleap(year):
            leap_hours = [item for item in values if item[0].month == 2 and item[0].day == 29]
            if len(leap_hours) != 24:
                raise WeatherDataError(f"PVGIS leap year {year} lacks a complete 29 February.")
            values = [item for item in values if not (item[0].month == 2 and item[0].day == 29)]
        normalized = tuple(POAWeatherHour(
            hour.timestamp.replace(year=CANONICAL_TMY_YEAR), hour.direct_poa_w_m2,
            hour.diffuse_poa_w_m2, hour.ground_reflected_poa_w_m2,
            hour.temperature_c, hour.wind_speed_m_s) for _, hour in values)
        if len(normalized) != EXPECTED_HOURS:
            raise WeatherDataError(f"PVGIS historical year {year} did not normalize to 8,760 hours.")
        years.append(HistoricalYear(year, normalized))
    inputs = payload.get("inputs") if isinstance(payload.get("inputs"), dict) else {}
    meteo = inputs.get("meteo_data") if isinstance(inputs.get("meteo_data"), dict) else {}
    database = str(meteo.get("radiation_db", "")).strip()
    if database != "PVGIS-SARAH3":
        raise WeatherDataError("PVGIS historical response does not confirm PVGIS-SARAH3.")
    source_period = _source_period(meteo, payload.get("meta") if isinstance(payload.get("meta"), dict) else {})
    try:
        period_start = int(meteo.get("year_min", min(grouped)))
        period_end = int(meteo.get("year_max", max(grouped)))
    except (TypeError, ValueError) as exc:
        raise WeatherDataError("PVGIS historical source period is invalid.") from exc
    if set(grouped) != set(range(period_start, period_end + 1)):
        raise WeatherDataError("PVGIS historical response omits one or more complete years.")
    if source_period is None:
        source_period = f"{min(grouped)}-{max(grouped)}"
    metadata = HistoricalMetadata(database, source_period,
        period_start, period_end,
        retrieved_at or datetime.now(timezone.utc), endpoint,
        "Complete 29 February removed; remaining UTC calendar positions mapped to canonical year 2001.")
    return HistoricalPOAWeather(latitude, longitude, tuple(years), metadata)


def _historical_irradiance(value: Any, label: str) -> float:
    number = _finite(value, label)
    if number < 0:
        raise WeatherDataError(f"PVGIS historical {label} must not be negative.")
    return number


def parse_pvgis_tmy(
    payload: Any, latitude: float, longitude: float, endpoint: str = PVGIS_TMY_URL,
    *, retrieved_at: datetime | None = None,
) -> TMYWeather:
    """Normalize PVGIS source years to 2001 without changing month/day/hour."""
    if not isinstance(payload, dict) or not isinstance(payload.get("outputs"), dict):
        raise WeatherDataError("PVGIS response is missing outputs.")
    rows = payload["outputs"].get("tmy_hourly")
    if not isinstance(rows, list) or not rows:
        raise WeatherDataError("PVGIS response contains no TMY hourly data.")
    if len(rows) != EXPECTED_HOURS:
        raise WeatherDataError("PVGIS TMY must contain exactly 8,760 hours.")
    hours = tuple(_parse_hour(row) for row in rows)
    timestamps = tuple(hour.timestamp for hour in hours)
    if timestamps != tuple(sorted(timestamps)) or len(set(timestamps)) != EXPECTED_HOURS:
        raise WeatherDataError("PVGIS TMY timestamps are duplicated or not chronological.")
    expected = tuple(
        datetime(CANONICAL_TMY_YEAR, 1, 1, tzinfo=timezone.utc)
        + index * _ONE_HOUR for index in range(EXPECTED_HOURS)
    )
    if timestamps != expected:
        raise WeatherDataError("PVGIS TMY contains gaps or invalid calendar positions.")

    meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
    inputs = payload.get("inputs") if isinstance(payload.get("inputs"), dict) else {}
    meteo = inputs.get("meteo_data") if isinstance(inputs.get("meteo_data"), dict) else {}
    location = inputs.get("location") if isinstance(inputs.get("location"), dict) else {}
    selected_present = "months_selected" in payload["outputs"]
    selected_raw = payload["outputs"].get("months_selected", [])
    if selected_present and not isinstance(selected_raw, list):
        raise WeatherDataError("PVGIS selected-month metadata must be a list.")
    try:
        selected = tuple(
            (int(item["month"]), int(item["year"])) for item in selected_raw
            if isinstance(item, dict) and "month" in item and "year" in item
        )
    except (TypeError, ValueError) as exc:
        raise WeatherDataError("PVGIS selected-month metadata is invalid.") from exc
    if selected_present and (
        len(selected) != 12 or {month for month, _ in selected} != set(range(1, 13))
    ):
        raise WeatherDataError(
            "PVGIS selected-month metadata must contain every month exactly once."
        )
    source_period = _source_period(meteo, meta)
    offset = location.get("irradiance_time_offset")
    if offset is not None:
        offset = _finite(offset, "irradiance time offset")
    radiation_database = meteo.get("radiation_db")
    if radiation_database is not None:
        radiation_database = str(radiation_database).strip() or None
    metadata = TMYMetadata(
        radiation_database, source_period, selected,
        retrieved_at or datetime.now(timezone.utc), endpoint, offset,
    )
    return TMYWeather(latitude, longitude, hours, metadata)


_ONE_HOUR = timedelta(hours=1)


def _parse_hour(row: Any) -> WeatherHour:
    if not isinstance(row, dict):
        raise WeatherDataError("PVGIS TMY contains an invalid hourly row.")
    try:
        source = datetime.strptime(_tmy_timestamp_value(row), "%Y%m%d:%H%M")
        timestamp = source.replace(year=CANONICAL_TMY_YEAR, tzinfo=timezone.utc)
        ghi = _irradiance(row["G(h)"], "GHI")
        dni = _irradiance(row["Gb(n)"], "DNI")
        dhi = _irradiance(row["Gd(h)"], "DHI")
        temperature = _finite(row["T2m"], "temperature")
        wind = _finite(row["WS10m"], "wind speed")
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, WeatherDataError):
            raise
        raise WeatherDataError("PVGIS TMY contains missing or invalid fields.") from exc
    if wind < 0:
        raise WeatherDataError("PVGIS wind speed must not be negative.")
    return WeatherHour(timestamp, ghi, dni, dhi, temperature, wind)


def _tmy_timestamp_value(row: dict[str, Any]) -> str:
    values = [row[field] for field in _TMY_TIMESTAMP_FIELDS if field in row]
    if not values:
        raise WeatherDataError("PVGIS TMY contains no supported timestamp field.")
    if any(not isinstance(value, str) for value in values):
        raise WeatherDataError("PVGIS TMY timestamp must be a string.")
    if len(set(values)) != 1:
        raise WeatherDataError("PVGIS TMY timestamp fields contain conflicting values.")
    return values[0]


def _finite(value: Any, label: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise WeatherDataError(f"PVGIS {label} must be numeric.") from exc
    if not isfinite(number):
        raise WeatherDataError(f"PVGIS {label} must be finite.")
    return number


def _irradiance(value: Any, label: str) -> float:
    number = _finite(value, label)
    if number < NEGATIVE_IRRADIANCE_TOLERANCE:
        raise WeatherDataError(f"PVGIS {label} is materially negative.")
    return max(0.0, number)


def _validate_coordinates(latitude: float, longitude: float) -> None:
    if not all(isfinite(value) for value in (latitude, longitude)):
        raise PVGISError("Coordinates must be finite.")
    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        raise PVGISError("Coordinates are outside valid latitude/longitude ranges.")


def _source_period(meteo: dict[str, Any], meta: dict[str, Any]) -> str | None:
    start = meteo.get("year_min") or meta.get("year_min")
    end = meteo.get("year_max") or meta.get("year_max")
    return f"{start}-{end}" if start is not None and end is not None else None
