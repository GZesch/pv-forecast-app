from datetime import datetime, timedelta, timezone

import pytest

from backend.pv_economics import (
    BatteryConfig,
    ConstantShading,
    EnergyModelError,
    MonthlyHourlyShading,
    PVGenerationError,
    PVSurface,
    calculate_pv_plant,
    calculate_energy_scenarios,
    calculate_pv_surface,
)
from backend.pv_economics.weather import TMYMetadata, TMYWeather, WeatherHour


def surface(**changes):
    values = dict(identifier="south", peak_power_kwp=10, azimuth_deg=180,
                  tilt_deg=30, inverter_efficiency=1, system_loss_fraction=0,
                  shading=ConstantShading(0))
    values.update(changes)
    return PVSurface(**values)


def weather(stamps, *, ghi=700, dni=800, dhi=100):
    return tuple(WeatherHour(stamp, ghi, dni, dhi, 20, 2) for stamp in stamps)


def test_horizontal_and_tilted_surfaces_produce_finite_energy():
    hours = weather((datetime(2001, 6, 21, 12, tzinfo=timezone.utc),))
    horizontal = calculate_pv_surface(hours, 52.5, 13.4, surface(tilt_deg=0))
    tilted = calculate_pv_surface(hours, 52.5, 13.4, surface(tilt_deg=30))
    assert horizontal.ac_energy_kwh[0] > 0
    assert tilted.ac_energy_kwh[0] > 0


def test_shading_only_reduces_direct_component_and_preserves_diffuse():
    hours = weather((datetime(2001, 6, 21, 12, tzinfo=timezone.utc),))
    clear = calculate_pv_surface(hours, 52.5, 13.4, surface())
    shaded = calculate_pv_surface(hours, 52.5, 13.4,
                                  surface(shading=ConstantShading(1)))
    assert shaded.hourly[0].poa_direct_after_shading_wh_m2 == 0
    assert shaded.hourly[0].poa_sky_diffuse_wh_m2 == pytest.approx(clear.hourly[0].poa_sky_diffuse_wh_m2)
    assert shaded.hourly[0].poa_ground_diffuse_wh_m2 == pytest.approx(clear.hourly[0].poa_ground_diffuse_wh_m2)
    assert shaded.ac_energy_kwh[0] > 0


def test_matrix_uses_berlin_local_hour_in_summer_and_winter():
    matrix = [list(row) for row in MonthlyHourlyShading.constant(0).factors]
    matrix[5][14] = 1  # June 12 UTC is 14 CEST.
    matrix[11][13] = 1  # December 12 UTC is 13 CET.
    shade = MonthlyHourlyShading(tuple(tuple(row) for row in matrix))
    stamps = (datetime(2001, 6, 21, 12, tzinfo=timezone.utc),
              datetime(2001, 12, 21, 12, tzinfo=timezone.utc))
    result = calculate_pv_surface(weather(stamps), 52.5, 13.4,
                                  surface(shading=shade))
    assert all(hour.poa_direct_after_shading_wh_m2 == 0 for hour in result.hourly)


def test_half_hour_irradiance_offset_shifts_solar_time_not_shading_time(monkeypatch):
    matrix = [list(row) for row in MonthlyHourlyShading.constant(0).factors]
    matrix[5][14] = 1  # 12:45 UTC is 14:45 CEST before the irradiance offset.
    shading = MonthlyHourlyShading(tuple(tuple(row) for row in matrix))
    stamp = datetime(2001, 6, 21, 12, 45, tzinfo=timezone.utc)
    captured = {}
    from backend.pv_economics import pv_generation

    original = pv_generation.pvlib.solarposition.get_solarposition

    def capture_solar_time(times, latitude, longitude):
        captured["time"] = times[0].to_pydatetime()
        return original(times, latitude, longitude)

    monkeypatch.setattr(
        pv_generation.pvlib.solarposition, "get_solarposition", capture_solar_time
    )
    result = calculate_pv_surface(
        weather((stamp,)), 52.5, 13.4, surface(shading=shading),
        irradiance_time_offset_hours=0.5,
    )
    assert captured["time"] == stamp + timedelta(minutes=30)
    assert result.hourly[0].poa_direct_after_shading_wh_m2 == 0


def test_efficiency_losses_and_clipping_are_separate():
    hours = weather((datetime(2001, 6, 21, 12, tzinfo=timezone.utc),))
    base = calculate_pv_surface(hours, 52.5, 13.4, surface())
    lossy = calculate_pv_surface(hours, 52.5, 13.4,
                                 surface(inverter_efficiency=.9, system_loss_fraction=.1))
    clipped = calculate_pv_surface(hours, 52.5, 13.4,
                                   surface(max_ac_power_kw=.5))
    assert lossy.ac_energy_kwh[0] == pytest.approx(base.ac_energy_kwh[0] * .81)
    assert clipped.ac_energy_kwh[0] == .5
    assert clipped.hourly[0].ac_clipping_loss_kwh > 0


def test_night_has_zero_generation():
    hours = weather((datetime(2001, 6, 21, 0, tzinfo=timezone.utc),), ghi=0, dni=0, dhi=0)
    assert calculate_pv_surface(hours, 52.5, 13.4, surface()).ac_energy_kwh == (0.0,)


def test_annual_plant_aggregates_multiple_surface_series():
    start = datetime(2001, 1, 1, tzinfo=timezone.utc)
    hours = weather(tuple(start + timedelta(hours=index) for index in range(8760)),
                    ghi=0, dni=0, dhi=0)
    metadata = TMYMetadata("PVGIS-SARAH3", "2005-2023", (), start,
                           "https://example.test/tmy")
    climate = TMYWeather(52.5, 13.4, hours, metadata)
    result = calculate_pv_plant(
        climate,
        (surface(identifier="east", peak_power_kwp=6, azimuth_deg=90),
         surface(identifier="west", peak_power_kwp=4, azimuth_deg=270)),
    )
    assert len(result.surfaces) == 2
    assert len(result.hourly_ac_energy_kwh) == 8760
    assert result.total_peak_power_kwp == 10
    assert result.annual_ac_energy_kwh == result.specific_yield_kwh_per_kwp == 0
    assert result.hourly_ac_energy_kwh == tuple(
        east + west for east, west in zip(
            result.surfaces[0].ac_energy_kwh, result.surfaces[1].ac_energy_kwh
        )
    )


@pytest.mark.parametrize("bad", [
    dict(peak_power_kwp=0), dict(azimuth_deg=-1), dict(tilt_deg=91),
    dict(inverter_efficiency=0), dict(system_loss_fraction=1),
    dict(max_ac_power_kw=0), dict(shading=ConstantShading(1.1)),
    dict(shading=MonthlyHourlyShading(((0,) * 24,) * 11)),
])
def test_invalid_surface_parameters_are_rejected(bad):
    with pytest.raises(PVGenerationError):
        calculate_pv_surface(weather((datetime(2001, 6, 21, 12, tzinfo=timezone.utc),)),
                             50, 8, surface(**bad))


def test_battery_non_numeric_parameters_raise_domain_error():
    invalid = BatteryConfig("ten", 2, 2, .9)  # type: ignore[arg-type]
    with pytest.raises(EnergyModelError, match="numeric"):
        calculate_energy_scenarios([1], [[0]], invalid)
