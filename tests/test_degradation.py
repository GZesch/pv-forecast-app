import pytest

from backend.pv_economics.degradation import (
    DegradationError, GeometricBatteryDegradation, PVDegradation,
    WarrantyBatteryDegradation,
)
from backend.pv_economics.models import BatteryConfig
from backend.pv_economics.projection import project_energy


def test_geometric_pv_and_battery_degradation():
    pv = PVDegradation(0.005)
    battery = GeometricBatteryDegradation(0.02)
    assert pv.factor(1) == 1
    assert pv.factor(3) == pytest.approx(0.995 ** 2)
    assert battery.capacity_factor(1, 0, 0) == 1
    assert battery.capacity_factor(3, 0, 0) == pytest.approx(0.98 ** 2)


def test_warranty_model_uses_minimum_without_double_counting():
    model = WarrantyBatteryDegradation(.8, 10, warranted_efc=1000)
    assert model.capacity_factor(6, 200, 100) == pytest.approx(.9)
    assert model.capacity_factor(2, 200, 750) == pytest.approx(.85)
    assert model.capacity_factor(6, 200, 750) == pytest.approx(.85)
    assert model.capacity_factor(21, 0, 0) == pytest.approx(.6)


def test_throughput_warranty_curve():
    model = WarrantyBatteryDegradation(.8, 10, warranted_throughput_kwh=5000)
    assert model.capacity_factor(1, 2500, .0) == pytest.approx(.9)


@pytest.mark.parametrize("model", [
    PVDegradation(-.1), PVDegradation(1), GeometricBatteryDegradation(float("nan")),
])
def test_invalid_geometric_degradation_is_rejected_when_used(model):
    with pytest.raises(DegradationError):
        if isinstance(model, PVDegradation):
            model.factor(1)
        else:
            model.capacity_factor(1, 0, 0)


@pytest.mark.parametrize("kwargs", [
    dict(residual_capacity_fraction=1.1, warranty_years=10, warranted_efc=1000),
    dict(residual_capacity_fraction=.8, warranty_years=0, warranted_efc=1000),
    dict(residual_capacity_fraction=.8, warranty_years=10),
    dict(residual_capacity_fraction=.8, warranty_years=10,
         warranted_efc=1000, warranted_throughput_kwh=5000),
])
def test_invalid_warranty_model_is_rejected(kwargs):
    with pytest.raises(DegradationError):
        WarrantyBatteryDegradation(**kwargs)


def test_projection_reruns_dispatch_and_accumulates_original_capacity_efc():
    result = project_energy(
        [0, 4], [[4, 0]], 3,
        battery=BatteryConfig(4, 4, 4, 1),
        pv_degradation=PVDegradation(.5),
        battery_degradation=GeometricBatteryDegradation(.5),
    )
    assert [year.pv_degradation_factor for year in result.years] == [1, .5, .25]
    assert [year.usable_battery_capacity_kwh for year in result.years] == [4, 2, 1]
    assert result.years[0].energy.pv_with_battery.grid_import_kwh == 0
    assert result.years[1].energy.pv_with_battery.grid_import_kwh == 2
    assert result.years[2].energy.pv_with_battery.grid_import_kwh == 3
    assert result.years[0].cumulative_battery_throughput_before_kwh == 0
    assert result.years[-1].cumulative_battery_throughput_after_kwh == 7
    assert result.years[-1].cumulative_equivalent_full_cycles == pytest.approx(7 / 4)


def test_projection_without_battery():
    result = project_energy([1, 1], [[2, 0]], 2)
    assert all(year.usable_battery_capacity_kwh is None for year in result.years)
    assert all(year.energy.pv_with_battery is None for year in result.years)


def test_expert_projection_uses_only_completed_year_throughput():
    model = WarrantyBatteryDegradation(.5, 100, warranted_throughput_kwh=4)
    result = project_energy([0, 4], [[4, 0]], 2,
        battery=BatteryConfig(4, 4, 4, 1), battery_degradation=model)
    assert result.years[0].usable_battery_capacity_kwh == 4
    assert result.years[1].usable_battery_capacity_kwh == 2
