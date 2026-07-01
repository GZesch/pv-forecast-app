"""Deterministic hourly simulation of household PV energy flows."""

from collections.abc import Sequence
from math import isfinite, sqrt

from .models import (
    BatteryConfig,
    EnergyBalance,
    EnergyModelError,
    EnergyModelResult,
    HourlyEnergyFlow,
    ScenarioResult,
)

BALANCE_TOLERANCE = 1e-9
WARMUP_TOLERANCE_KWH = 1e-9
MAX_WARMUP_ITERATIONS = 100


def calculate_energy_scenarios(
    household_load_kwh: Sequence[float],
    pv_areas_ac_kwh: Sequence[Sequence[float]],
    battery: BatteryConfig | None = None,
) -> EnergyModelResult:
    """Calculate without-PV, PV-only, and optionally PV-with-battery scenarios."""
    load = _validated_series(household_load_kwh, "Household load")
    if not pv_areas_ac_kwh:
        raise EnergyModelError("At least one PV area time series is required.")
    areas = tuple(
        _validated_series(area, f"PV area {index}")
        for index, area in enumerate(pv_areas_ac_kwh, start=1)
    )
    if any(len(area) != len(load) for area in areas):
        raise EnergyModelError("Household load and all PV areas must have equal lengths.")
    pv = tuple(sum(values) for values in zip(*areas)) if areas else (0.0,) * len(load)

    without_pv = _simulate(load, (0.0,) * len(load), "without_pv", None, 0.0)
    pv_only = _simulate(load, pv, "pv_only", None, 0.0)
    with_battery = None
    if battery is not None:
        _validate_battery(battery)
        initial_soc = _periodic_initial_soc(load, pv, battery)
        with_battery = _simulate(load, pv, "pv_with_battery", battery, initial_soc)
    return EnergyModelResult(without_pv, pv_only, with_battery)


def _validated_series(values: Sequence[float], label: str) -> tuple[float, ...]:
    if not values:
        raise EnergyModelError(f"{label} time series must not be empty.")
    try:
        result = tuple(float(value) for value in values)
    except (TypeError, ValueError) as exc:
        raise EnergyModelError(f"{label} must contain only numeric values.") from exc
    if any(not isfinite(value) for value in result):
        raise EnergyModelError(f"{label} contains NaN or infinite values.")
    if any(value < 0 for value in result):
        raise EnergyModelError(f"{label} contains negative energy values.")
    return result


def _validate_battery(config: BatteryConfig) -> None:
    values = (config.usable_capacity_kwh, config.max_charge_power_kw,
              config.max_discharge_power_kw, config.round_trip_efficiency)
    try:
        finite = all(isfinite(value) for value in values)
    except TypeError as exc:
        raise EnergyModelError("Battery parameters must be numeric.") from exc
    if not finite:
        raise EnergyModelError("Battery parameters must be finite numbers.")
    if config.usable_capacity_kwh <= 0:
        raise EnergyModelError("Usable battery capacity must be positive.")
    if config.max_charge_power_kw < 0 or config.max_discharge_power_kw < 0:
        raise EnergyModelError("Battery charge and discharge power must not be negative.")
    if not 0 < config.round_trip_efficiency <= 1:
        raise EnergyModelError("Round-trip efficiency must be greater than 0 and at most 1.")


def _periodic_initial_soc(
    load: tuple[float, ...], pv: tuple[float, ...], config: BatteryConfig
) -> float:
    # Replaying the same period converges to its periodic boundary state and avoids
    # assigning an arbitrary charge level to the first reported hour.
    soc = 0.0
    for _ in range(MAX_WARMUP_ITERATIONS):
        end_soc = _run_battery(load, pv, config, soc, collect=False)[1]
        if abs(end_soc - soc) <= WARMUP_TOLERANCE_KWH:
            return end_soc
        soc = end_soc
    return soc


def _simulate(
    load: tuple[float, ...], pv: tuple[float, ...], name: str,
    battery: BatteryConfig | None, initial_soc: float,
) -> ScenarioResult:
    if battery is None:
        hourly = tuple(_hour_without_battery(demand, generation) for demand, generation in zip(load, pv))
        final_soc = 0.0
    else:
        hourly, final_soc = _run_battery(load, pv, battery, initial_soc, collect=True)
    result = _aggregate(name, hourly, initial_soc, final_soc, battery)
    result.balance.assert_valid(BALANCE_TOLERANCE)
    return result


def _hour_without_battery(load: float, pv: float) -> HourlyEnergyFlow:
    direct = min(load, pv)
    return HourlyEnergyFlow(load, pv, direct, 0.0, 0.0, 0.0, 0.0, 0.0,
                            pv - direct, load - direct, 0.0)


def _run_battery(
    load: tuple[float, ...], pv: tuple[float, ...], config: BatteryConfig,
    initial_soc: float, *, collect: bool,
) -> tuple[tuple[HourlyEnergyFlow, ...], float]:
    eta_charge = sqrt(config.round_trip_efficiency)
    eta_discharge = eta_charge
    soc = initial_soc
    flows: list[HourlyEnergyFlow] = []
    for demand, generation in zip(load, pv):
        direct = min(demand, generation)
        surplus = generation - direct
        remaining_load = demand - direct
        charge_input = min(surplus, config.max_charge_power_kw,
                           (config.usable_capacity_kwh - soc) / eta_charge)
        internal_charge = charge_input * eta_charge
        soc += internal_charge
        delivery = min(remaining_load, config.max_discharge_power_kw, soc * eta_discharge)
        internal_discharge = delivery / eta_discharge
        soc -= internal_discharge
        soc = min(config.usable_capacity_kwh, max(0.0, soc))
        losses = charge_input - internal_charge + internal_discharge - delivery
        if collect:
            flows.append(HourlyEnergyFlow(
                demand, generation, direct, charge_input, delivery, internal_charge,
                internal_discharge, losses, surplus - charge_input,
                remaining_load - delivery, soc,
            ))
    return tuple(flows), soc


def _aggregate(
    name: str, hourly: tuple[HourlyEnergyFlow, ...], initial_soc: float,
    final_soc: float, battery: BatteryConfig | None,
) -> ScenarioResult:
    total = lambda field: sum(getattr(hour, field) for hour in hourly)
    load = total("load")
    pv = total("pv_generation")
    direct = total("direct_pv_consumption")
    charge = total("battery_charge_from_pv")
    delivery = total("battery_delivery_to_load")
    losses = total("battery_losses")
    feed_in = total("feed_in")
    grid = total("grid_import")
    internal_discharge = total("battery_internal_discharge")
    balance = EnergyBalance(
        pv - direct - charge - feed_in,
        load - direct - delivery - grid,
        charge - (final_soc - initial_soc) - delivery - losses,
    )
    # Self-used PV is useful energy delivered to the household. The self-consumption
    # ratio instead follows the generator-side convention: PV that was not exported.
    self_used = direct + delivery
    return ScenarioResult(
        name, load, pv, direct, charge, delivery, losses, feed_in, grid, self_used,
        (direct + charge) / pv if pv else 0.0,
        self_used / load if load else 0.0,
        internal_discharge,
        internal_discharge / battery.usable_capacity_kwh if battery else 0.0,
        initial_soc, final_soc, hourly, balance,
    )
