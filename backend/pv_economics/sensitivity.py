"""Deterministic selection of real historical PV production years."""

from dataclasses import dataclass
from math import ceil, isfinite


class WeatherSensitivityError(ValueError):
    """Historical coverage is insufficient or structurally inconsistent."""


@dataclass(frozen=True, slots=True)
class HistoricalPlantYear:
    source_year: int
    surface_ac_energy_kwh: tuple[tuple[float, ...], ...]
    annual_ac_energy_kwh: float


@dataclass(frozen=True, slots=True)
class SelectedWeatherYear:
    label: str
    display_label: str
    quantile: float
    nearest_rank: int
    year: HistoricalPlantYear


def select_weather_years(
    years: tuple[HistoricalPlantYear, ...], *, minimum_years: int = 10,
) -> tuple[SelectedWeatherYear, ...]:
    """Select actual observations using ceil(p*n), ordered by yield then year."""
    if len(years) < minimum_years:
        raise WeatherSensitivityError(
            f"At least {minimum_years} complete historical years are required."
        )
    if len({item.source_year for item in years}) != len(years):
        raise WeatherSensitivityError("Historical source years must be unique.")
    if any(not isfinite(item.annual_ac_energy_kwh)
           or item.annual_ac_energy_kwh < 0 for item in years):
        raise WeatherSensitivityError("Historical annual production must be finite and non-negative.")
    ordered = sorted(years, key=lambda item: (item.annual_ac_energy_kwh,
                                              item.source_year))
    definitions = (("low", "ertragsschwach", .10),
                   ("median", "mittel", .50),
                   ("high", "ertragreich", .90))
    return tuple(SelectedWeatherYear(label, display, quantile,
        max(1, ceil(quantile * len(ordered))),
        ordered[max(1, ceil(quantile * len(ordered))) - 1])
        for label, display, quantile in definitions)
