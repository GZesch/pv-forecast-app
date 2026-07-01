"""Typed inputs and outputs for the PV energy model."""

from dataclasses import dataclass


class EnergyModelError(ValueError):
    """Raised when energy-model inputs or balances are invalid."""


@dataclass(frozen=True, slots=True)
class BatteryConfig:
    """Usable battery limits; power values apply to one-hour intervals."""

    usable_capacity_kwh: float
    max_charge_power_kw: float
    max_discharge_power_kw: float
    round_trip_efficiency: float


@dataclass(frozen=True, slots=True)
class HourlyEnergyFlow:
    """Energy flows for one hourly interval, in kWh."""

    load: float
    pv_generation: float
    direct_pv_consumption: float
    battery_charge_from_pv: float
    battery_delivery_to_load: float
    battery_internal_charge: float
    battery_internal_discharge: float
    battery_losses: float
    feed_in: float
    curtailed_pv: float
    grid_import: float
    state_of_charge_end: float


@dataclass(frozen=True, slots=True)
class EnergyBalance:
    """Residuals of the three model-wide energy conservation equations."""

    pv_residual_kwh: float
    load_residual_kwh: float
    battery_residual_kwh: float

    def assert_valid(self, tolerance: float = 1e-9) -> None:
        """Raise if any conservation residual exceeds ``tolerance``."""
        if tolerance < 0:
            raise EnergyModelError("Balance tolerance must not be negative.")
        if max(map(abs, (self.pv_residual_kwh, self.load_residual_kwh,
                         self.battery_residual_kwh))) > tolerance:
            raise EnergyModelError(f"Energy balance violated: {self!r}")


@dataclass(frozen=True, slots=True)
class ScenarioResult:
    """Aggregated and hourly results of one energy scenario."""

    name: str
    household_consumption_kwh: float
    pv_generation_kwh: float
    direct_pv_consumption_kwh: float
    battery_charge_from_pv_kwh: float
    battery_delivery_to_load_kwh: float
    battery_losses_kwh: float
    feed_in_kwh: float
    curtailed_pv_kwh: float
    curtailment_ratio: float
    grid_import_kwh: float
    self_used_pv_kwh: float
    self_consumption_ratio: float
    autonomy_ratio: float
    battery_internal_throughput_kwh: float
    equivalent_full_cycles: float
    initial_state_of_charge_kwh: float
    final_state_of_charge_kwh: float
    hourly: tuple[HourlyEnergyFlow, ...]
    balance: EnergyBalance


@dataclass(frozen=True, slots=True)
class EnergyModelResult:
    """The three comparable scenarios."""

    without_pv: ScenarioResult
    pv_only: ScenarioResult
    pv_with_battery: ScenarioResult | None
