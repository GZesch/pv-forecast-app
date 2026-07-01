"""Deterministic, stable warning identifiers for offer-check results."""

from dataclasses import dataclass
from enum import StrEnum


class WarningSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"


@dataclass(frozen=True, slots=True)
class CalculationWarning:
    code: str
    severity: WarningSeverity
    text: str


WARNING_TEXT = {
    "STANDARD_LOAD_PROFILE": "H25 is a standard load profile, not an individual measurement.",
    "SYNTHETIC_LOAD_PROFILE": "The selected ExergyPulse profile is a scenario and not derived from measurements.",
    "HEAT_PUMP_NOT_MODELLED": "Heat-pump consumption is not modelled separately.",
    "EV_NOT_MODELLED": "Electric-vehicle consumption is not modelled separately.",
    "PACKAGE_PRICE_NOT_SPLIT": "The package price cannot be split into PV and battery investments.",
    "BATTERY_NEGATIVE_NPV": "The incremental battery NPV is negative under the entered assumptions.",
    "BATTERY_NO_PAYBACK": "The incremental battery does not pay back within the horizon.",
    "PV_NO_PAYBACK": "PV does not pay back within the horizon.",
    "REPLACEMENT_COSTS_NOT_INCLUDED": "No automatic battery or inverter replacement is included.",
    "FEED_IN_LIMIT_NOT_IN_BASE_CASE": "The base case has no feed-in power limit; a 60% first-year comparison is shown.",
    "FEED_IN_TARIFF_MANUAL_OVERRIDE": "The feed-in tariff is a manual user assumption.",
    "EEG_TARIFF_UNAVAILABLE": "No published EEG tariff is available for the commissioning date.",
    "TMY_NOT_FORECAST": "PVGIS TMY is a typical meteorological year, not a weather forecast.",
    "SHADING_SIMPLIFIED": "Shading affects only direct plane-of-array irradiance.",
    "ELECTRICAL_PARTIAL_SHADING_NOT_MODELLED": "Modules, strings and bypass diodes are not modelled.",
    "BATTERY_WARRANTY_IS_BOUNDARY": "Warranty degradation is a boundary, not an expected forecast.",
    "CALCULATION_ORIENTATION_ONLY": "The calculation provides orientation and is not an offer verdict.",
}


def derive_warnings(*, profile_kind: str, has_heat_pump: bool, has_ev: bool,
                    package_only: bool, manual_tariff: bool,
                    pv_metrics_available: bool, pv_payback: float | None,
                    battery_metrics_available: bool,
                    battery_npv: float | None, battery_payback: float | None,
                    warranty_battery: bool,
                    feed_in_limit_in_base_case: bool = False) -> tuple[CalculationWarning, ...]:
    codes = ["STANDARD_LOAD_PROFILE" if profile_kind == "h25" else "SYNTHETIC_LOAD_PROFILE"]
    if has_heat_pump: codes.append("HEAT_PUMP_NOT_MODELLED")
    if has_ev: codes.append("EV_NOT_MODELLED")
    if package_only: codes.append("PACKAGE_PRICE_NOT_SPLIT")
    if battery_metrics_available and battery_npv is not None and battery_npv < 0: codes.append("BATTERY_NEGATIVE_NPV")
    if battery_metrics_available and battery_payback is None: codes.append("BATTERY_NO_PAYBACK")
    if pv_metrics_available and pv_payback is None: codes.append("PV_NO_PAYBACK")
    if manual_tariff: codes.append("FEED_IN_TARIFF_MANUAL_OVERRIDE")
    if warranty_battery: codes.append("BATTERY_WARRANTY_IS_BOUNDARY")
    codes.append("REPLACEMENT_COSTS_NOT_INCLUDED")
    if not feed_in_limit_in_base_case:
        codes.append("FEED_IN_LIMIT_NOT_IN_BASE_CASE")
    codes.extend(("TMY_NOT_FORECAST", "SHADING_SIMPLIFIED",
                  "ELECTRICAL_PARTIAL_SHADING_NOT_MODELLED",
                  "CALCULATION_ORIENTATION_ONLY"))
    return tuple(CalculationWarning(code, WarningSeverity.WARNING if "NO_PAYBACK" in code or "NEGATIVE" in code else WarningSeverity.INFO, WARNING_TEXT[code]) for code in codes)
