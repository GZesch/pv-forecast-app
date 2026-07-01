import pytest

from backend.pv_economics import BatteryConfig, calculate_energy_scenarios


def test_no_limit_has_no_curtailment():
    result = calculate_energy_scenarios([0], [[10]])
    assert result.pv_only.feed_in_kwh == 10
    assert result.pv_only.curtailed_pv_kwh == 0


def test_limit_without_storage_and_energy_balance():
    result = calculate_energy_scenarios([0], [[10]], max_grid_feed_in_power_kw=6)
    assert result.pv_only.feed_in_kwh == 6
    assert result.pv_only.curtailed_pv_kwh == 4
    assert result.pv_only.curtailment_ratio == pytest.approx(.4)
    result.pv_only.balance.assert_valid()


def test_storage_charges_before_feed_in_curtailment():
    result = calculate_energy_scenarios(
        [0, 10], [[10, 0]], BatteryConfig(4, 4, 4, 1),
        max_grid_feed_in_power_kw=3).pv_with_battery
    assert result.hourly[0].battery_charge_from_pv == 4
    assert result.hourly[0].feed_in == 3
    assert result.hourly[0].curtailed_pv == 3
    result.balance.assert_valid()


def test_sixty_percent_comparison():
    base = calculate_energy_scenarios([0], [[10]])
    limited = calculate_energy_scenarios([0], [[10]],
                                         max_grid_feed_in_power_kw=6)
    assert base.pv_only.curtailed_pv_kwh == 0
    assert limited.pv_only.curtailed_pv_kwh == 4
