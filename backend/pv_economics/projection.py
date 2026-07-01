"""Multi-year energy projection that reruns the hourly dispatch every year."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from .degradation import GeometricBatteryDegradation, PVDegradation
from .models import BatteryConfig, EnergyModelResult
from .simulation import calculate_energy_scenarios


class BatteryDegradationModel(Protocol):
    def capacity_factor(self, operating_year: int,
                        cumulative_throughput_kwh: float,
                        cumulative_efc: float) -> float: ...


@dataclass(frozen=True, slots=True)
class ProjectionYear:
    operating_year: int
    pv_degradation_factor: float
    usable_battery_capacity_kwh: float | None
    cumulative_battery_throughput_before_kwh: float
    cumulative_battery_throughput_after_kwh: float
    cumulative_equivalent_full_cycles: float
    energy: EnergyModelResult


@dataclass(frozen=True, slots=True)
class EnergyProjection:
    years: tuple[ProjectionYear, ...]
    original_battery_capacity_kwh: float | None


def project_energy(
    household_load_kwh: Sequence[float],
    pv_areas_first_year_ac_kwh: Sequence[Sequence[float]],
    years: int, *, battery: BatteryConfig | None = None,
    pv_degradation: PVDegradation = PVDegradation(),
    battery_degradation: BatteryDegradationModel | None = None,
    max_grid_feed_in_power_kw: float | None = None,
    feed_in_limit_years: int = 0,
) -> EnergyProjection:
    """Scale only PV/capacity inputs and rerun the complete dispatch per year."""
    if not isinstance(years, int) or years <= 0:
        raise ValueError("Projection years must be a positive integer.")
    if battery_degradation is not None and battery is None:
        raise ValueError("Battery degradation requires a battery configuration.")
    if not isinstance(feed_in_limit_years, int) or not 0 <= feed_in_limit_years <= years:
        raise ValueError("Feed-in limit years must be between zero and projection years.")
    model = battery_degradation or GeometricBatteryDegradation()
    original_capacity = battery.usable_capacity_kwh if battery else None
    cumulative = 0.0
    projected: list[ProjectionYear] = []
    for operating_year in range(1, years + 1):
        pv_factor = pv_degradation.factor(operating_year)
        pv_areas = tuple(tuple(float(value) * pv_factor for value in area)
                         for area in pv_areas_first_year_ac_kwh)
        configured_battery = None
        capacity = None
        if battery is not None and original_capacity is not None:
            cumulative_efc_before = cumulative / original_capacity
            capacity_factor = model.capacity_factor(
                operating_year, cumulative, cumulative_efc_before)
            capacity = original_capacity * capacity_factor
            # Zero residual capacity is a transparent end state, represented by
            # disabling storage because BatteryConfig requires positive capacity.
            if capacity > 0:
                configured_battery = BatteryConfig(
                    capacity, battery.max_charge_power_kw,
                    battery.max_discharge_power_kw, battery.round_trip_efficiency)
        limit = max_grid_feed_in_power_kw if operating_year <= feed_in_limit_years else None
        energy = calculate_energy_scenarios(
            household_load_kwh, pv_areas, configured_battery, limit)
        before = cumulative
        if energy.pv_with_battery is not None:
            cumulative += energy.pv_with_battery.battery_internal_throughput_kwh
        cumulative_efc = cumulative / original_capacity if original_capacity else 0.0
        projected.append(ProjectionYear(
            operating_year, pv_factor, capacity, before, cumulative,
            cumulative_efc, energy,
        ))
    return EnergyProjection(tuple(projected), original_capacity)
