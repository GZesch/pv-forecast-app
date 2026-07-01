"""Visible, versioned ExergyPulse model defaults."""

from dataclasses import dataclass

MODEL_VERSION = "pv-economics-1.0"
DEFAULTS_DATA_DATE = "2026-07-01"


@dataclass(frozen=True, slots=True)
class ModelAssumption:
    key: str
    value: float | int | str
    unit: str
    rationale: str
    source: str


STANDARD_ASSUMPTIONS = (
    ModelAssumption("pv_degradation", .005, "fraction/year", "Geometric PV ageing", "ExergyPulse model assumption"),
    ModelAssumption("battery_rte", .90, "fraction", "Round-trip efficiency", "ExergyPulse model assumption"),
    ModelAssumption("battery_charge_c_rate", .5, "C", "Maximum charging power", "ExergyPulse model assumption"),
    ModelAssumption("battery_discharge_c_rate", .5, "C", "Maximum discharging power", "ExergyPulse model assumption"),
    ModelAssumption("battery_capacity_loss", .02, "fraction/year", "Geometric capacity ageing", "ExergyPulse model assumption"),
    ModelAssumption("albedo", .2, "fraction", "Ground reflectance", "ExergyPulse model assumption"),
    ModelAssumption("projection_years", 20, "years", "Economic horizon", "ExergyPulse model assumption"),
    ModelAssumption("electricity_price_growth", .02, "fraction/year", "Nominal escalation", "ExergyPulse model assumption"),
    ModelAssumption("operating_cost_growth", .02, "fraction/year", "Nominal escalation", "ExergyPulse model assumption"),
    ModelAssumption("nominal_discount_rate", .03, "fraction/year", "Nominal discount rate", "ExergyPulse model assumption"),
    ModelAssumption("pv_opex_share", .01, "fraction of PV investment/year", "PV operating cost", "ExergyPulse model assumption"),
    ModelAssumption("battery_opex", 0.0, "EUR/year", "Additional battery operating cost", "ExergyPulse model assumption"),
    ModelAssumption("automatic_battery_replacement", "none", "-", "No automatic replacement", "ExergyPulse model assumption"),
    ModelAssumption("automatic_inverter_replacement", "none", "-", "No automatic replacement", "ExergyPulse model assumption"),
    ModelAssumption("financing", "equity", "-", "No financing model", "ExergyPulse model assumption"),
)
