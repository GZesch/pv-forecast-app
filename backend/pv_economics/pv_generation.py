"""Pure PV generation model using pvlib Perez transposition and PVWatts DC."""

from dataclasses import dataclass
from datetime import timedelta
from math import isfinite
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pvlib

from .weather import POAWeatherHour, TMYWeather, WeatherHour

BERLIN = ZoneInfo("Europe/Berlin")


class PVGenerationError(ValueError):
    """Raised for invalid PV-surface inputs or non-physical model results."""


@dataclass(frozen=True, slots=True)
class ConstantShading:
    """Constant blocked fraction of direct plane-of-array irradiance."""

    factor: float


@dataclass(frozen=True, slots=True)
class MonthlyHourlyShading:
    """Blocked direct fraction indexed by local German month and hour."""

    factors: tuple[tuple[float, ...], ...]

    @classmethod
    def constant(cls, factor: float) -> "MonthlyHourlyShading":
        """Create a complete 12 by 24 matrix from one blocked fraction."""
        return cls(tuple(tuple(float(factor) for _ in range(24)) for _ in range(12)))


Shading = ConstantShading | MonthlyHourlyShading


@dataclass(frozen=True, slots=True)
class PVSurface:
    """Immutable surface; azimuth follows pvlib (north=0, east=90, south=180)."""

    identifier: str
    peak_power_kwp: float
    azimuth_deg: float
    tilt_deg: float
    inverter_efficiency: float
    system_loss_fraction: float
    shading: Shading
    max_ac_power_kw: float | None = None


@dataclass(frozen=True, slots=True)
class PVHourResult:
    ac_energy_kwh: float
    poa_direct_before_shading_wh_m2: float
    poa_direct_after_shading_wh_m2: float
    poa_sky_diffuse_wh_m2: float
    poa_ground_diffuse_wh_m2: float
    poa_global_wh_m2: float
    shaded_direct_loss_wh_m2: float
    ac_clipping_loss_kwh: float


@dataclass(frozen=True, slots=True)
class PVSurfaceResult:
    surface: PVSurface
    hourly: tuple[PVHourResult, ...]
    ac_energy_kwh: tuple[float, ...]
    annual_ac_energy_kwh: float
    specific_yield_kwh_per_kwp: float


@dataclass(frozen=True, slots=True)
class PVPlantResult:
    surfaces: tuple[PVSurfaceResult, ...]
    hourly_ac_energy_kwh: tuple[float, ...]
    total_peak_power_kwp: float
    annual_ac_energy_kwh: float
    specific_yield_kwh_per_kwp: float


def calculate_pv_plant(
    weather: TMYWeather, surfaces: tuple[PVSurface, ...], *, albedo: float = 0.2,
) -> PVPlantResult:
    """Calculate each surface separately and retain AP1-compatible AC series."""
    if len(weather.hours) != 8760:
        raise PVGenerationError("Public annual PV calculation requires 8,760 hours.")
    if not surfaces:
        raise PVGenerationError("At least one PV surface is required.")
    results = tuple(calculate_pv_surface(weather.hours, weather.latitude,
                                        weather.longitude, surface, albedo=albedo,
                                        irradiance_time_offset_hours=weather.metadata.irradiance_time_offset_hours)
                    for surface in surfaces)
    combined = tuple(sum(values) for values in zip(*(item.ac_energy_kwh for item in results)))
    peak = sum(item.surface.peak_power_kwp for item in results)
    annual = sum(combined)
    return PVPlantResult(results, combined, peak, annual, annual / peak)


def calculate_pv_surface(
    hours: tuple[WeatherHour, ...], latitude: float, longitude: float,
    surface: PVSurface, *, albedo: float = 0.2,
    irradiance_time_offset_hours: float | None = None,
) -> PVSurfaceResult:
    """Calculate hourly mean kW; over a one-hour PVGIS interval this equals kWh."""
    _validate_surface(surface)
    if not all(isfinite(value) for value in (latitude, longitude)) or not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        raise PVGenerationError("Coordinates are outside valid latitude/longitude ranges.")
    if not hours:
        raise PVGenerationError("Weather series must not be empty.")
    if not isfinite(albedo) or not 0 <= albedo <= 1:
        raise PVGenerationError("Albedo must be finite and between 0 and 1.")
    times = pd.DatetimeIndex([hour.timestamp for hour in hours])
    if times.tz is None or any(stamp.utcoffset() != timedelta(0) for stamp in times):
        raise PVGenerationError("Weather timestamps must be timezone-aware UTC.")
    if not times.is_monotonic_increasing or times.has_duplicates:
        raise PVGenerationError("Weather timestamps must be unique and chronological.")
    weather_values = np.asarray([
        value for hour in hours for value in (
            hour.ghi_w_m2, hour.dni_w_m2, hour.dhi_w_m2,
            hour.temperature_c, hour.wind_speed_m_s,
        )
    ], dtype=float)
    if not np.all(np.isfinite(weather_values)):
        raise PVGenerationError("Weather values must be finite.")
    if any(hour.ghi_w_m2 < 0 or hour.dni_w_m2 < 0 or hour.dhi_w_m2 < 0
           or hour.wind_speed_m_s < 0 for hour in hours):
        raise PVGenerationError("Irradiance and wind speed must not be negative.")
    solar_times = times
    if irradiance_time_offset_hours is not None:
        solar_times = times + timedelta(hours=irradiance_time_offset_hours)
    solar = pvlib.solarposition.get_solarposition(solar_times, latitude, longitude)
    dni = np.asarray([hour.dni_w_m2 for hour in hours], dtype=float)
    ghi = np.asarray([hour.ghi_w_m2 for hour in hours], dtype=float)
    dhi = np.asarray([hour.dhi_w_m2 for hour in hours], dtype=float)
    dni_extra = pvlib.irradiance.get_extra_radiation(solar_times)
    airmass = pvlib.atmosphere.get_relative_airmass(solar["apparent_zenith"])
    poa = pvlib.irradiance.get_total_irradiance(
        surface.tilt_deg, surface.azimuth_deg, solar["apparent_zenith"],
        solar["azimuth"], dni, ghi, dhi, dni_extra=dni_extra, airmass=airmass,
        albedo=albedo, model="perez",
    )
    dark = (ghi == 0) & (dni == 0) & (dhi == 0)
    direct = _poa_component(poa["poa_direct"].to_numpy(), dark, "direct POA")
    sky = _poa_component(poa["poa_sky_diffuse"].to_numpy(), dark,
                         "sky-diffuse POA")
    ground = _poa_component(poa["poa_ground_diffuse"].to_numpy(), dark,
                            "ground POA")
    return _calculate_from_poa(
        surface, times, direct, sky, ground,
        np.asarray([h.temperature_c for h in hours]),
        np.asarray([h.wind_speed_m_s for h in hours]),
    )


def calculate_pv_surface_from_poa(
    hours: tuple[POAWeatherHour, ...], surface: PVSurface,
) -> PVSurfaceResult:
    """Calculate AC generation from PVGIS components already transposed to POA."""
    _validate_surface(surface)
    if not hours:
        raise PVGenerationError("Historical POA series must not be empty.")
    times = pd.DatetimeIndex([hour.timestamp for hour in hours])
    if times.tz is None or any(stamp.utcoffset() != timedelta(0) for stamp in times):
        raise PVGenerationError("Historical POA timestamps must be timezone-aware UTC.")
    if not times.is_monotonic_increasing or times.has_duplicates:
        raise PVGenerationError("Historical POA timestamps must be unique and chronological.")
    values = np.asarray([
        value for hour in hours for value in (
            hour.direct_poa_w_m2, hour.diffuse_poa_w_m2,
            hour.ground_reflected_poa_w_m2, hour.temperature_c,
            hour.wind_speed_m_s,
        )
    ], dtype=float)
    if not np.all(np.isfinite(values)):
        raise PVGenerationError("Historical POA values must be finite.")
    if any(hour.direct_poa_w_m2 < 0 or hour.diffuse_poa_w_m2 < 0
           or hour.ground_reflected_poa_w_m2 < 0 or hour.wind_speed_m_s < 0
           for hour in hours):
        raise PVGenerationError("Historical irradiance and wind speed must not be negative.")
    return _calculate_from_poa(
        surface, times,
        np.asarray([hour.direct_poa_w_m2 for hour in hours]),
        np.asarray([hour.diffuse_poa_w_m2 for hour in hours]),
        np.asarray([hour.ground_reflected_poa_w_m2 for hour in hours]),
        np.asarray([hour.temperature_c for hour in hours]),
        np.asarray([hour.wind_speed_m_s for hour in hours]),
    )


def _calculate_from_poa(surface: PVSurface, times: pd.DatetimeIndex,
                        direct: np.ndarray, sky: np.ndarray,
                        ground: np.ndarray, temperature: np.ndarray,
                        wind: np.ndarray) -> PVSurfaceResult:
    """Shared shading, thermal, DC, loss and clipping path for all POA sources."""
    direct = _nonnegative(direct, "direct POA")
    sky = _nonnegative(sky, "diffuse POA")
    ground = _nonnegative(ground, "ground-reflected POA")
    shade = np.asarray([_shade_factor(surface.shading, stamp) for stamp in times])
    direct_after = direct * (1 - shade)
    global_after = direct_after + sky + ground
    temp = pvlib.temperature.sapm_cell(
        global_after, temperature, wind, -3.47, -0.0594, 3.0,
    )
    dc = pvlib.pvsystem.pvwatts_dc(global_after, temp, surface.peak_power_kwp,
                                   gamma_pdc=-0.004)
    ac_unclipped = _nonnegative(np.asarray(dc) * surface.inverter_efficiency
                                * (1 - surface.system_loss_fraction), "AC power")
    ac = ac_unclipped if surface.max_ac_power_kw is None else np.minimum(
        ac_unclipped, surface.max_ac_power_kw)
    clipping = ac_unclipped - ac
    hourly = tuple(PVHourResult(*map(float, values)) for values in zip(
        ac, direct, direct_after, sky, ground, global_after, direct - direct_after,
        clipping,
    ))
    energy = tuple(item.ac_energy_kwh for item in hourly)
    annual = sum(energy)
    return PVSurfaceResult(surface, hourly, energy, annual,
                           annual / surface.peak_power_kwp)


def _shade_factor(shading: Shading, timestamp: pd.Timestamp) -> float:
    if isinstance(shading, ConstantShading):
        return shading.factor
    local = timestamp.to_pydatetime().astimezone(BERLIN)
    return shading.factors[local.month - 1][local.hour]


def _validate_surface(surface: PVSurface) -> None:
    numeric = (surface.peak_power_kwp, surface.azimuth_deg, surface.tilt_deg,
               surface.inverter_efficiency, surface.system_loss_fraction)
    if not surface.identifier or not all(isfinite(value) for value in numeric):
        raise PVGenerationError("PV surface identifier and values must be valid and finite.")
    if surface.peak_power_kwp <= 0 or not 0 <= surface.azimuth_deg <= 360 or not 0 <= surface.tilt_deg <= 90:
        raise PVGenerationError("PV peak power, azimuth, or tilt is outside its valid range.")
    if not 0 < surface.inverter_efficiency <= 1 or not 0 <= surface.system_loss_fraction < 1:
        raise PVGenerationError("PV efficiencies or loss fractions are invalid.")
    if surface.max_ac_power_kw is not None and (not isfinite(surface.max_ac_power_kw)
                                                 or surface.max_ac_power_kw <= 0):
        raise PVGenerationError("Maximum AC power must be positive and finite.")
    matrix = surface.shading.factors if isinstance(surface.shading, MonthlyHourlyShading) else None
    factors = ([surface.shading.factor] if isinstance(surface.shading, ConstantShading)
               else [value for row in matrix or () for value in row])
    if matrix is not None and (len(matrix) != 12 or any(len(row) != 24 for row in matrix)):
        raise PVGenerationError("Shading matrix must contain 12 rows of 24 hours.")
    if any(not isfinite(value) or not 0 <= value <= 1 for value in factors):
        raise PVGenerationError("Shading factors must be finite and between 0 and 1.")


def _nonnegative(values: np.ndarray, label: str) -> np.ndarray:
    array = np.asarray(values, dtype=float)
    if not np.all(np.isfinite(array)):
        raise PVGenerationError(f"{label} contains non-finite results.")
    if np.any(array < -1e-7):
        raise PVGenerationError(f"{label} contains materially negative results.")
    return np.maximum(array, 0.0)


def _poa_component(values: np.ndarray, dark: np.ndarray, label: str) -> np.ndarray:
    """Resolve Perez undefined values only when all source irradiance is zero."""
    array = np.asarray(values, dtype=float)
    array = np.where(dark & ~np.isfinite(array), 0.0, array)
    return _nonnegative(array, label)
