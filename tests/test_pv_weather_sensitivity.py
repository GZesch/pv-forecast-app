from datetime import datetime, timezone

import pytest

from backend.pv_economics.pv_generation import (
    ConstantShading, MonthlyHourlyShading, PVSurface,
    calculate_pv_surface_from_poa,
)
from backend.pv_economics.sensitivity import (
    HistoricalPlantYear, WeatherSensitivityError, select_weather_years,
)
from backend.pv_economics.weather import POAWeatherHour


def surface(**changes):
    values = dict(identifier="surface", peak_power_kwp=1, azimuth_deg=180,
                  tilt_deg=30, inverter_efficiency=1,
                  system_loss_fraction=0, shading=ConstantShading(0))
    values.update(changes)
    return PVSurface(**values)


def poa(stamp, direct=500, diffuse=100, ground=20):
    return POAWeatherHour(stamp, direct, diffuse, ground, 20, 2)


def test_direct_shading_preserves_diffuse_and_ground_components():
    stamp = datetime(2001, 6, 21, 12, tzinfo=timezone.utc)
    clear = calculate_pv_surface_from_poa((poa(stamp),), surface())
    shaded = calculate_pv_surface_from_poa(
        (poa(stamp),), surface(shading=ConstantShading(1)))
    assert shaded.hourly[0].poa_direct_after_shading_wh_m2 == 0
    assert shaded.hourly[0].poa_sky_diffuse_wh_m2 == clear.hourly[0].poa_sky_diffuse_wh_m2
    assert shaded.hourly[0].poa_ground_diffuse_wh_m2 == clear.hourly[0].poa_ground_diffuse_wh_m2


def test_poa_path_uses_local_matrix_and_shared_losses_and_clipping():
    stamp = datetime(2001, 6, 21, 12, tzinfo=timezone.utc)  # 14:00 CEST
    factors = [list(row) for row in MonthlyHourlyShading.constant(0).factors]
    factors[5][14] = 1
    shaded = calculate_pv_surface_from_poa(
        (poa(stamp),), surface(shading=MonthlyHourlyShading(
            tuple(tuple(row) for row in factors))))
    base = calculate_pv_surface_from_poa((poa(stamp),), surface())
    lossy = calculate_pv_surface_from_poa(
        (poa(stamp),), surface(inverter_efficiency=.9, system_loss_fraction=.1))
    clipped = calculate_pv_surface_from_poa(
        (poa(stamp),), surface(max_ac_power_kw=.1))
    assert shaded.hourly[0].poa_direct_after_shading_wh_m2 == 0
    assert lossy.ac_energy_kwh[0] == pytest.approx(base.ac_energy_kwh[0] * .81)
    assert clipped.ac_energy_kwh[0] == .1
    assert clipped.hourly[0].ac_clipping_loss_kwh > 0


def historical(year, annual):
    return HistoricalPlantYear(year, ((annual,),), annual)


def test_nearest_rank_selects_real_years_deterministically():
    years = tuple(historical(2000 + index, float(index)) for index in range(1, 11))
    selected = select_weather_years(years)
    assert [(item.label, item.nearest_rank, item.year.source_year)
            for item in selected] == [
                ("low", 1, 2001), ("median", 5, 2005), ("high", 9, 2009)]
    assert all(item.year in years for item in selected)


def test_nearest_rank_ties_use_calendar_year_and_small_samples_fail():
    tied = tuple(historical(year, 100) for year in range(2010, 2020))
    selected = select_weather_years(tuple(reversed(tied)))
    assert [item.year.source_year for item in selected] == [2010, 2014, 2018]
    with pytest.raises(WeatherSensitivityError, match="10"):
        select_weather_years(tied[:9])
