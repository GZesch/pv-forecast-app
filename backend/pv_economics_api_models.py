"""Pydantic transport models for the stateless PV economics endpoint."""

from datetime import date
from math import isfinite
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class PVSurfaceInput(BaseModel):
    identifier: str = Field(min_length=1, max_length=100)
    peak_power_kwp: float = Field(gt=0, le=100)
    azimuth_deg: float = Field(ge=0, le=360)
    tilt_deg: float = Field(ge=0, le=90)
    inverter_efficiency: float = Field(gt=0, le=1)
    system_loss_fraction: float = Field(ge=0, lt=1)
    max_ac_power_kw: float | None = Field(default=None, gt=0)
    constant_shading_factor: float | None = Field(default=0, ge=0, le=1)
    shading_matrix: list[list[float]] | None = None

    @model_validator(mode="after")
    def validate_shading(self) -> "PVSurfaceInput":
        if self.shading_matrix is not None:
            if self.constant_shading_factor not in (None, 0):
                raise ValueError(
                    "Shading matrix and non-zero constant shading are mutually exclusive."
                )
            if len(self.shading_matrix) != 12 or any(len(row) != 24 for row in self.shading_matrix):
                raise ValueError("Shading matrix must contain 12 rows of 24 values.")
            if any(not isfinite(value) or not 0 <= value <= 1
                   for row in self.shading_matrix for value in row):
                raise ValueError("Shading matrix values must be finite and between 0 and 1.")
        return self


class BatteryInput(BaseModel):
    usable_capacity_kwh: float = Field(gt=0)
    round_trip_efficiency: float = Field(default=.90, gt=0, le=1)
    max_charge_power_kw: float | None = Field(default=None, ge=0)
    max_discharge_power_kw: float | None = Field(default=None, ge=0)
    degradation_kind: Literal["standard", "warranty"] = "standard"
    residual_capacity_fraction: float | None = Field(default=None, ge=0, le=1)
    warranty_years: float | None = Field(default=None, gt=0)
    warranted_throughput_kwh: float | None = Field(default=None, gt=0)
    warranted_efc: float | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_warranty(self) -> "BatteryInput":
        if self.degradation_kind == "warranty":
            if self.residual_capacity_fraction is None or self.warranty_years is None:
                raise ValueError("Warranty degradation requires residual capacity and years.")
            if (self.warranted_throughput_kwh is None) == (self.warranted_efc is None):
                raise ValueError("Warranty degradation requires exactly one throughput or EFC limit.")
        elif any(value is not None for value in (
            self.residual_capacity_fraction, self.warranty_years,
            self.warranted_throughput_kwh, self.warranted_efc,
        )):
            raise ValueError("Warranty parameters are not allowed in standard degradation mode.")
        return self


class CostEventInput(BaseModel):
    operating_year: int = Field(ge=1)
    amount_eur: float = Field(ge=0)
    allocation: Literal["pv", "battery", "package"]
    label: str = Field(min_length=1, max_length=200)


class ExpertAssumptionsInput(BaseModel):
    years: int = Field(default=20, ge=1, le=40)
    pv_degradation_rate: float = Field(default=.005, ge=0, lt=1)
    battery_capacity_loss_rate: float = Field(default=.02, ge=0, lt=1)
    electricity_price_growth_rate: float = Field(default=.02, gt=-1)
    operating_cost_growth_rate: float = Field(default=.02, gt=-1)
    nominal_discount_rate: float = Field(default=.03, gt=-1)
    pv_operating_cost_year1_eur: float | None = Field(default=None, ge=0)
    battery_operating_cost_year1_eur: float = Field(default=0, ge=0)
    post_eeg_value_eur_per_kwh: float = Field(default=0, ge=0)
    max_feed_in_power_kw: float | None = Field(default=None, ge=0)
    max_feed_in_percent: float | None = Field(default=None, ge=0, le=100)
    feed_in_limit_years: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def one_feed_in_limit(self) -> "ExpertAssumptionsInput":
        if self.max_feed_in_power_kw is not None and self.max_feed_in_percent is not None:
            raise ValueError("Specify feed-in limit as kW or percent, not both.")
        has_limit = (self.max_feed_in_power_kw is not None
                     or self.max_feed_in_percent is not None)
        if has_limit and self.feed_in_limit_years <= 0:
            raise ValueError("A feed-in limit requires a positive number of affected years.")
        if not has_limit and self.feed_in_limit_years > 0:
            raise ValueError("Positive feed-in-limit years require a kW or percent limit.")
        if self.feed_in_limit_years > self.years:
            raise ValueError("Feed-in-limit years must not exceed the projection horizon.")
        return self


class PVEconomicsRequest(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    federal_state: str = Field(min_length=2, max_length=2)
    annual_consumption_kwh: float = Field(gt=0)
    profile_kind: Literal["h25", "exergypulse_daytime", "exergypulse_evening", "exergypulse_flatter"] = "h25"
    has_heat_pump: bool = False
    has_electric_vehicle: bool = False
    pv_surfaces: list[PVSurfaceInput] = Field(min_length=1)
    battery: BatteryInput | None = None
    electricity_price_eur_per_kwh: float = Field(gt=0)
    commissioning_date: date
    manual_feed_in_tariff_eur_per_kwh: float | None = Field(default=None, ge=0)
    pv_investment_eur: float | None = Field(default=None, ge=0)
    battery_incremental_investment_eur: float | None = Field(default=None, ge=0)
    package_investment_eur: float | None = Field(default=None, ge=0)
    assumptions: ExpertAssumptionsInput = Field(default_factory=ExpertAssumptionsInput)
    one_time_costs: list[CostEventInput] = Field(default_factory=list)
    include_weather_sensitivity: bool = False


class WeatherFinancialMetrics(BaseModel):
    available: bool
    nominal_total_eur: float | None
    net_present_value_eur: float | None
    payback_years: float | None


class WeatherScenarioEconomics(BaseModel):
    pv: WeatherFinancialMetrics
    package: WeatherFinancialMetrics
    incremental_battery: WeatherFinancialMetrics


class WeatherSensitivityScenario(BaseModel):
    label: Literal["low", "median", "high"]
    display_label: str
    source_year: int
    quantile: float
    nearest_rank: int
    annual_pv_generation_kwh: float
    deviation_from_tmy_percent: float | None
    first_year: dict[str, object]
    economics: WeatherScenarioEconomics


class WeatherSensitivityDistribution(BaseModel):
    complete_year_count: int
    minimum_kwh: float
    median_kwh: float
    maximum_kwh: float


class WeatherSensitivityResponse(BaseModel):
    scenarios: list[WeatherSensitivityScenario]
    distribution: WeatherSensitivityDistribution
    source_period: str
    radiation_database: str
    api_endpoint: str
    retrieved_at: str
    quantile_method: str
    leap_day_normalization: str
    notice: str


class PVEconomicsResponse(BaseModel):
    metadata: dict[str, object]
    first_year: dict[str, object]
    economics: dict[str, object]
    feed_in_limit_comparison: dict[str, object]
    warnings: list[dict[str, object]]
    disclaimers: list[str]
    weather_sensitivity: WeatherSensitivityResponse | None = None
