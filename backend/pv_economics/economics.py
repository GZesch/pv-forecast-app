"""Nominal cashflows and financial metrics for projected PV scenarios."""

from dataclasses import dataclass
from enum import StrEnum
from math import isfinite

from .projection import EnergyProjection

INVESTMENT_TOLERANCE_EUR = 0.01


class EconomicsError(ValueError):
    pass


class CostAllocation(StrEnum):
    PV = "pv"
    BATTERY = "battery"
    PACKAGE = "package"


@dataclass(frozen=True, slots=True)
class OneTimeCost:
    operating_year: int
    amount_eur: float
    allocation: CostAllocation
    label: str


@dataclass(frozen=True, slots=True)
class EconomicInputs:
    electricity_price_year1_eur_per_kwh: float
    electricity_price_growth_rate: float
    feed_in_tariff_eur_per_kwh: tuple[float, ...]
    nominal_discount_rate: float
    pv_investment_eur: float | None = None
    battery_incremental_investment_eur: float | None = None
    package_investment_eur: float | None = None
    pv_operating_cost_year1_eur: float = 0.0
    battery_operating_cost_year1_eur: float = 0.0
    operating_cost_growth_rate: float = 0.0
    one_time_costs: tuple[OneTimeCost, ...] = ()


@dataclass(frozen=True, slots=True)
class AnnualEconomics:
    operating_year: int
    electricity_price_eur_per_kwh: float
    feed_in_tariff_eur_per_kwh: float
    reference_electricity_cost_eur: float
    avoided_grid_cost_eur: float
    feed_in_revenue_eur: float
    operating_cost_eur: float
    one_time_cost_eur: float
    cashflow_eur: float
    cumulative_cashflow_eur: float
    discounted_cashflow_eur: float


@dataclass(frozen=True, slots=True)
class FinancialMetrics:
    available: bool
    unavailable_reason: str | None
    nominal_total_eur: float | None
    net_present_value_eur: float | None
    payback_years: float | None


@dataclass(frozen=True, slots=True)
class ScenarioEconomics:
    year_zero_cashflow_eur: float | None
    annual: tuple[AnnualEconomics, ...]
    metrics: FinancialMetrics


@dataclass(frozen=True, slots=True)
class EconomicResult:
    pv: ScenarioEconomics
    package: ScenarioEconomics
    incremental_battery: ScenarioEconomics


def calculate_economics(
    projection: EnergyProjection, inputs: EconomicInputs,
) -> EconomicResult:
    years = len(projection.years)
    _validate_inputs(inputs, years)
    has_battery = projection.original_battery_capacity_kwh is not None
    pv_investment, battery_investment, total_investment = _resolve_investments(inputs)
    if not has_battery:
        if battery_investment is not None and battery_investment > INVESTMENT_TOLERANCE_EUR:
            raise EconomicsError("Battery investment is not allowed without a battery projection.")
        if inputs.battery_operating_cost_year1_eur > 0:
            raise EconomicsError("Battery operating costs are not allowed without a battery projection.")
        if any(event.allocation == CostAllocation.BATTERY for event in inputs.one_time_costs):
            raise EconomicsError("Battery cost events are not allowed without a battery projection.")

    pv_rows: list[dict[str, float]] = []
    package_rows: list[dict[str, float]] = []
    battery_rows: list[dict[str, float]] = []
    for index, projected in enumerate(projection.years):
        year = index + 1
        try:
            price = inputs.electricity_price_year1_eur_per_kwh * (1 + inputs.electricity_price_growth_rate) ** index
            pv_opex = inputs.pv_operating_cost_year1_eur * (1 + inputs.operating_cost_growth_rate) ** index
            battery_opex = (inputs.battery_operating_cost_year1_eur
                * (1 + inputs.operating_cost_growth_rate) ** index if has_battery else 0.0)
        except OverflowError as exc:
            raise EconomicsError("Escalation produced an overflowing price or cost.") from exc
        reference = projected.energy.without_pv
        pv = projected.energy.pv_only
        stored = projected.energy.pv_with_battery
        tariff = inputs.feed_in_tariff_eur_per_kwh[index]
        if any(not isfinite(value) for value in (price, pv_opex, battery_opex)):
            raise EconomicsError("Escalation produced a non-finite price or cost.")
        reference_cost = reference.grid_import_kwh * price
        pv_avoided = (reference.grid_import_kwh - pv.grid_import_kwh) * price
        pv_revenue = pv.feed_in_kwh * tariff
        pv_events = _event_cost(inputs.one_time_costs, year, {CostAllocation.PV})
        pv_cashflow = pv_avoided + pv_revenue - pv_opex - pv_events
        pv_rows.append(_raw(year, price, tariff, reference_cost, pv_avoided,
                            pv_revenue, pv_opex, pv_events, pv_cashflow))
        if stored is None:
            total_avoided, total_revenue = pv_avoided, pv_revenue
        else:
            total_avoided = (reference.grid_import_kwh - stored.grid_import_kwh) * price
            total_revenue = stored.feed_in_kwh * tariff
        package_events = _event_cost(
            inputs.one_time_costs, year,
            {CostAllocation.PV, CostAllocation.BATTERY, CostAllocation.PACKAGE})
        total_cashflow = (total_avoided + total_revenue - pv_opex
                          - battery_opex - package_events)
        package_rows.append(_raw(year, price, tariff, reference_cost, total_avoided,
                                 total_revenue, pv_opex + battery_opex,
                                 package_events, total_cashflow))
        battery_rows.append(_raw(
            year, price, tariff, reference_cost,
            total_avoided - pv_avoided, total_revenue - pv_revenue,
            battery_opex, package_events - pv_events,
            total_cashflow - pv_cashflow,
        ))
    return EconomicResult(
        _scenario(pv_rows, pv_investment, inputs.nominal_discount_rate,
                  "PV investment cost is unavailable."),
        _scenario(package_rows, total_investment, inputs.nominal_discount_rate,
                  "Total package investment cost is unavailable."),
        _scenario(battery_rows, battery_investment if has_battery else None,
                  inputs.nominal_discount_rate,
                  "Battery incremental investment cost is unavailable."),
    )


def _scenario(rows: list[dict[str, float]], investment: float | None,
              discount: float, reason: str) -> ScenarioEconomics:
    if investment is None:
        return ScenarioEconomics(None, _annual(rows, 0.0, discount),
                                 FinancialMetrics(False, reason, None, None, None))
    year_zero = -investment
    annual = _annual(rows, year_zero, discount)
    cashflows = (year_zero,) + tuple(row.cashflow_eur for row in annual)
    nominal = sum(cashflows)
    npv = sum(value / (1 + discount) ** year for year, value in enumerate(cashflows))
    payback = None if investment == 0 else _payback(cashflows)
    unavailable = "Payback is not meaningful for zero investment." if investment == 0 else None
    return ScenarioEconomics(year_zero, annual,
        FinancialMetrics(True, unavailable, nominal, npv, payback))


def _annual(rows: list[dict[str, float]], initial: float,
            discount: float) -> tuple[AnnualEconomics, ...]:
    cumulative = initial
    result = []
    for row in rows:
        cumulative += row["cashflow"]
        result.append(AnnualEconomics(
            int(row["year"]), row["price"], row["tariff"], row["reference"],
            row["avoided"], row["revenue"], row["opex"], row["events"],
            row["cashflow"], cumulative,
            row["cashflow"] / (1 + discount) ** int(row["year"]),
        ))
    return tuple(result)


def _payback(cashflows: tuple[float, ...]) -> float | None:
    cumulative = cashflows[0]
    for year, cashflow in enumerate(cashflows[1:], 1):
        previous = cumulative
        cumulative += cashflow
        if cumulative >= -1e-12 and cashflow > 0:
            return (year - 1) + max(0.0, -previous / cashflow)
    return None


def _event_cost(events: tuple[OneTimeCost, ...], year: int,
                allocations: set[CostAllocation]) -> float:
    return sum(event.amount_eur for event in events
               if event.operating_year == year and event.allocation in allocations)


def _raw(year: int, price: float, tariff: float, reference: float,
         avoided: float, revenue: float, opex: float, events: float,
         cashflow: float) -> dict[str, float]:
    return {"year": float(year), "price": price, "tariff": tariff,
            "reference": reference, "avoided": avoided, "revenue": revenue,
            "opex": opex, "events": events, "cashflow": cashflow}


def _validate_inputs(inputs: EconomicInputs, years: int) -> None:
    monetary = (inputs.electricity_price_year1_eur_per_kwh,
                inputs.pv_operating_cost_year1_eur,
                inputs.battery_operating_cost_year1_eur)
    optional = (inputs.pv_investment_eur, inputs.battery_incremental_investment_eur,
                inputs.package_investment_eur)
    rates = (inputs.electricity_price_growth_rate,
             inputs.operating_cost_growth_rate, inputs.nominal_discount_rate)
    if any(not isfinite(value) or value < 0 for value in monetary):
        raise EconomicsError("Prices and operating costs must be finite and non-negative.")
    if any(value is not None and (not isfinite(value) or value < 0) for value in optional):
        raise EconomicsError("Investments must be finite and non-negative.")
    if any(not isfinite(value) or value <= -1 for value in rates):
        raise EconomicsError("Growth and discount rates must be finite and greater than -1.")
    if len(inputs.feed_in_tariff_eur_per_kwh) != years or any(
        not isfinite(value) or value < 0 for value in inputs.feed_in_tariff_eur_per_kwh):
        raise EconomicsError("Feed-in tariff series must cover all years with valid prices.")
    for event in inputs.one_time_costs:
        if not isinstance(event.allocation, CostAllocation):
            raise EconomicsError("One-time cost allocation must be a CostAllocation.")
        if not isinstance(event.label, str) or not event.label.strip():
            raise EconomicsError("One-time cost label must be a non-empty string.")
        try:
            valid_amount = isfinite(event.amount_eur) and event.amount_eur >= 0
        except TypeError as exc:
            raise EconomicsError("One-time cost amount must be numeric.") from exc
        if (not isinstance(event.operating_year, int)
                or not 1 <= event.operating_year <= years or not valid_amount):
            raise EconomicsError("One-time costs must be valid and within the projection.")


def _resolve_investments(
    inputs: EconomicInputs,
) -> tuple[float | None, float | None, float | None]:
    """Resolve PV, battery and package investment without estimating a split."""
    pv = inputs.pv_investment_eur
    battery = inputs.battery_incremental_investment_eur
    package = inputs.package_investment_eur
    if pv is not None and battery is not None:
        calculated = pv + battery
        if package is None:
            package = calculated
        elif abs(package - calculated) > INVESTMENT_TOLERANCE_EUR:
            raise EconomicsError("Package investment must equal PV plus battery investment.")
        else:
            package = calculated
    elif pv is not None and package is not None:
        battery = package - pv
    elif battery is not None and package is not None:
        pv = package - battery
    if any(value is not None and value < 0
           for value in (pv, battery, package)):
        raise EconomicsError("Derived investment components must not be negative.")
    return pv, battery, package
