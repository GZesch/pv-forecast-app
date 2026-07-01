import math

import pytest

from backend.pv_economics import BatteryConfig, EnergyModelError, calculate_energy_scenarios


def battery(capacity=10.0, charge=10.0, discharge=10.0, rte=1.0):
    return BatteryConfig(capacity, charge, discharge, rte)


def test_without_pv_and_exact_pv_coverage():
    result = calculate_energy_scenarios([1, 2], [[1, 2]])
    assert result.without_pv.grid_import_kwh == 3
    assert result.without_pv.pv_generation_kwh == 0
    assert result.pv_only.direct_pv_consumption_kwh == 3
    assert result.pv_only.grid_import_kwh == result.pv_only.feed_in_kwh == 0
    assert result.pv_only.autonomy_ratio == result.pv_only.self_consumption_ratio == 1


def test_pv_surplus_and_multiple_areas_are_added():
    result = calculate_energy_scenarios([1, 1], [[2, 0], [1, 2]])
    assert result.pv_only.pv_generation_kwh == 5
    assert result.pv_only.direct_pv_consumption_kwh == 2
    assert result.pv_only.feed_in_kwh == 3
    assert result.pv_only.self_consumption_ratio == pytest.approx(0.4)


def test_battery_never_charges_from_grid_and_obeys_capacity():
    result = calculate_energy_scenarios([2, 0, 2], [[0, 20, 0]], battery(capacity=3)).pv_with_battery
    assert result is not None
    assert result.hourly[0].battery_charge_from_pv == 0
    assert max(hour.state_of_charge_end for hour in result.hourly) <= 3
    assert result.hourly[1].battery_charge_from_pv == 3


def test_charge_and_discharge_power_limits():
    charge_limited = calculate_energy_scenarios(
        [0, 5], [[5, 0]], battery(charge=2, discharge=2)
    ).pv_with_battery
    discharge_limited = calculate_energy_scenarios(
        [0, 5], [[5, 0]], battery(charge=1, discharge=1)
    ).pv_with_battery
    assert charge_limited is not None and discharge_limited is not None
    assert charge_limited.hourly[0].battery_charge_from_pv == 2
    assert discharge_limited.hourly[1].battery_delivery_to_load == 1


def test_round_trip_losses_and_equivalent_full_cycles():
    result = calculate_energy_scenarios([0, 10], [[10, 0]], battery(capacity=10, rte=0.81)).pv_with_battery
    assert result is not None
    assert result.battery_charge_from_pv_kwh == pytest.approx(10)
    assert result.battery_delivery_to_load_kwh == pytest.approx(8.1)
    assert result.battery_losses_kwh == pytest.approx(1.9)
    assert result.battery_internal_throughput_kwh == pytest.approx(9)
    assert result.equivalent_full_cycles == pytest.approx(0.9)


def test_periodic_warmup_removes_arbitrary_empty_start():
    result = calculate_energy_scenarios([2, 0], [[0, 2]], battery(capacity=5)).pv_with_battery
    assert result is not None
    assert result.initial_state_of_charge_kwh == pytest.approx(2)
    assert result.final_state_of_charge_kwh == pytest.approx(2)
    assert result.grid_import_kwh == 0


@pytest.mark.parametrize("scenario", ["without_pv", "pv_only", "pv_with_battery"])
def test_energy_conservation_for_every_scenario(scenario):
    results = calculate_energy_scenarios([2, 0, 3], [[0, 5, 0]], battery(rte=0.81))
    selected = getattr(results, scenario)
    assert selected is not None
    selected.balance.assert_valid()


@pytest.mark.parametrize(
    ("load", "pv", "config", "message"),
    [
        ([], [[]], None, "must not be empty"),
        ([1], [], None, "At least one PV area"),
        ([1], [[1, 2]], None, "equal lengths"),
        ([math.nan], [[0]], None, "NaN or infinite"),
        ([-1], [[0]], None, "negative"),
        ([1], [[-1]], None, "negative"),
        ([1], [[0]], battery(capacity=0), "capacity must be positive"),
        ([1], [[0]], battery(charge=-1), "power must not be negative"),
        ([1], [[0]], battery(rte=0), "efficiency"),
        ([1], [[0]], battery(rte=1.1), "efficiency"),
    ],
)
def test_invalid_inputs_are_rejected(load, pv, config, message):
    with pytest.raises(EnergyModelError, match=message):
        calculate_energy_scenarios(load, pv, config)
