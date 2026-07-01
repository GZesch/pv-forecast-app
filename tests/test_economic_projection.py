import pytest

from backend.pv_economics.economics import (
    CostAllocation, EconomicInputs, EconomicsError, OneTimeCost,
    calculate_economics,
)
from backend.pv_economics.degradation import PVDegradation
from backend.pv_economics.models import BatteryConfig
from backend.pv_economics.projection import project_energy


def projection(years=2, battery=True):
    return project_energy(
        [0, 4], [[4, 0]], years,
        battery=BatteryConfig(4, 4, 4, 1) if battery else None,
        pv_degradation=PVDegradation(0),
    )


def inputs(years=2, **changes):
    values = dict(
        electricity_price_year1_eur_per_kwh=.30,
        electricity_price_growth_rate=0,
        feed_in_tariff_eur_per_kwh=(.10,) * years,
        nominal_discount_rate=.10,
        pv_investment_eur=1,
        battery_incremental_investment_eur=1,
    )
    values.update(changes)
    return EconomicInputs(**values)


def test_reference_avoided_cost_feed_in_and_storage_contribution():
    result = calculate_economics(projection(), inputs())
    pv = result.pv.annual[0]
    package = result.package.annual[0]
    storage = result.incremental_battery.annual[0]
    assert pv.reference_electricity_cost_eur == pytest.approx(1.2)
    assert pv.avoided_grid_cost_eur == 0
    assert pv.feed_in_revenue_eur == pytest.approx(.4)
    assert package.avoided_grid_cost_eur == pytest.approx(1.2)
    assert package.feed_in_revenue_eur == 0
    # Storage value includes avoided import and lost feed-in revenue.
    assert storage.cashflow_eur == pytest.approx(.8)


def test_price_and_operating_cost_escalation():
    result = calculate_economics(projection(), inputs(
        electricity_price_growth_rate=.1, pv_operating_cost_year1_eur=10,
        operating_cost_growth_rate=.2))
    assert result.pv.annual[1].electricity_price_eur_per_kwh == pytest.approx(.33)
    assert result.pv.annual[1].operating_cost_eur == pytest.approx(12)


def test_year_zero_nominal_npv_and_interpolated_payback():
    result = calculate_economics(projection(), inputs(
        pv_investment_eur=.6, nominal_discount_rate=.1))
    metrics = result.pv.metrics
    assert result.pv.year_zero_cashflow_eur == -.6
    assert metrics.nominal_total_eur == pytest.approx(.2)
    assert metrics.net_present_value_eur == pytest.approx(-.6 + .4/1.1 + .4/1.1**2)
    assert metrics.payback_years == pytest.approx(1.5)


def test_no_payback_and_replacement_cost():
    result = calculate_economics(projection(), inputs(
        pv_investment_eur=10,
        one_time_costs=(OneTimeCost(2, 2, CostAllocation.PV, "inverter"),)))
    assert result.pv.metrics.payback_years is None
    assert result.pv.annual[1].one_time_cost_eur == 2


def test_only_package_price_makes_separate_investment_metrics_unavailable():
    result = calculate_economics(projection(), inputs(
        pv_investment_eur=None, battery_incremental_investment_eur=None,
        package_investment_eur=10))
    assert not result.pv.metrics.available
    assert result.package.metrics.available
    assert not result.incremental_battery.metrics.available
    assert result.incremental_battery.annual[0].cashflow_eur == pytest.approx(.8)


def test_derives_battery_investment_from_package_minus_pv():
    result = calculate_economics(projection(), inputs(
        pv_investment_eur=6, battery_incremental_investment_eur=None,
        package_investment_eur=10))
    assert result.pv.year_zero_cashflow_eur == -6
    assert result.incremental_battery.year_zero_cashflow_eur == -4
    assert result.package.year_zero_cashflow_eur == -10


def test_derives_package_investment_from_pv_plus_battery():
    result = calculate_economics(projection(), inputs(
        pv_investment_eur=6, battery_incremental_investment_eur=4,
        package_investment_eur=None))
    assert result.package.year_zero_cashflow_eur == -10


def test_derives_pv_investment_from_package_minus_battery():
    result = calculate_economics(projection(), inputs(
        pv_investment_eur=None, battery_incremental_investment_eur=4,
        package_investment_eur=10))
    assert result.pv.year_zero_cashflow_eur == -6


def test_rejects_inconsistent_or_negative_derived_investments():
    with pytest.raises(EconomicsError, match="must equal"):
        calculate_economics(projection(), inputs(
            pv_investment_eur=6, battery_incremental_investment_eur=5,
            package_investment_eur=10))
    with pytest.raises(EconomicsError, match="must not be negative"):
        calculate_economics(projection(), inputs(
            pv_investment_eur=11, battery_incremental_investment_eur=None,
            package_investment_eur=10))


def test_package_minus_pv_equals_battery_cashflow_including_year_zero():
    result = calculate_economics(projection(), inputs(
        pv_investment_eur=6, battery_incremental_investment_eur=4))
    assert (result.package.year_zero_cashflow_eur
            - result.pv.year_zero_cashflow_eur
            == result.incremental_battery.year_zero_cashflow_eur)
    assert all(
        package.cashflow_eur - pv.cashflow_eur == pytest.approx(battery.cashflow_eur)
        for package, pv, battery in zip(
            result.package.annual, result.pv.annual,
            result.incremental_battery.annual,
        )
    )


@pytest.mark.parametrize("changes", [
    dict(battery_incremental_investment_eur=1),
    dict(battery_incremental_investment_eur=None,
         battery_operating_cost_year1_eur=1),
    dict(battery_incremental_investment_eur=None,
         one_time_costs=(OneTimeCost(1, 1, CostAllocation.BATTERY, "battery"),)),
])
def test_projection_without_battery_rejects_battery_costs(changes):
    with pytest.raises(EconomicsError, match="without a battery projection"):
        calculate_economics(projection(battery=False), inputs(**changes))


def test_projection_without_battery_has_no_storage_economics():
    result = calculate_economics(projection(battery=False), inputs(
        battery_incremental_investment_eur=None))
    assert not result.incremental_battery.metrics.available
    assert result.incremental_battery.year_zero_cashflow_eur is None


@pytest.mark.parametrize("event", [
    OneTimeCost(1, 1, "battery", "invalid allocation"),  # type: ignore[arg-type]
    OneTimeCost(1, 1, CostAllocation.PV, ""),
    OneTimeCost(1, 1, CostAllocation.PV, "   "),
    OneTimeCost(1, 1, CostAllocation.PV, None),  # type: ignore[arg-type]
])
def test_invalid_event_allocation_or_label(event):
    with pytest.raises(EconomicsError):
        calculate_economics(projection(), inputs(one_time_costs=(event,)))


def test_zero_investment_payback_is_explicitly_not_meaningful():
    result = calculate_economics(projection(), inputs(pv_investment_eur=0))
    assert result.pv.metrics.available
    assert result.pv.metrics.payback_years is None
    assert "zero investment" in result.pv.metrics.unavailable_reason


@pytest.mark.parametrize("changes", [
    dict(electricity_price_year1_eur_per_kwh=-1),
    dict(electricity_price_growth_rate=-1),
    dict(nominal_discount_rate=float("nan")),
    dict(feed_in_tariff_eur_per_kwh=(.1,)),
    dict(pv_investment_eur=-1),
    dict(one_time_costs=(OneTimeCost(3, 1, CostAllocation.PV, "late"),)),
])
def test_invalid_economic_inputs(changes):
    with pytest.raises(EconomicsError):
        calculate_economics(projection(), inputs(**changes))
