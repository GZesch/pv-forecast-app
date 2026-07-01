"""Stateless orchestration for the PV economics offer check."""

import os
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from backend.pv_economics.degradation import (
    GeometricBatteryDegradation, PVDegradation, WarrantyBatteryDegradation,
)
from backend.pv_economics.defaults import (
    DEFAULTS_DATA_DATE, MODEL_VERSION, STANDARD_ASSUMPTIONS,
)
from backend.pv_economics.economics import (
    CostAllocation, EconomicInputs, EconomicsError, OneTimeCost,
    calculate_economics, resolve_investments,
)
from backend.pv_economics.eeg import annual_feed_in_tariffs, resolve_eeg_surplus_tariff
from backend.pv_economics.load_profiles import generate_household_load_profile
from backend.pv_economics.models import BatteryConfig
from backend.pv_economics.pv_generation import (
    ConstantShading, MonthlyHourlyShading, PVSurface, calculate_pv_plant,
)
from backend.pv_economics.pvgis import PVGISTMYClient
from backend.pv_economics.projection import project_energy
from backend.pv_economics.simulation import calculate_energy_scenarios
from backend.pv_economics.warnings import derive_warnings
from backend.pv_economics_api_models import PVEconomicsRequest, PVEconomicsResponse


class PVEconomicsService:
    def __init__(self, *, pvgis_client: PVGISTMYClient | None = None,
                 load_provider: Callable[..., object] = generate_household_load_profile,
                 h25_csv_path: str | Path | None = None,
                 clock: Callable[[], datetime] | None = None) -> None:
        self.pvgis_client = pvgis_client or PVGISTMYClient()
        self.load_provider = load_provider
        self.h25_csv_path = h25_csv_path or os.getenv("BDEW_H25_CSV_PATH")
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    async def calculate(self, request: PVEconomicsRequest) -> PVEconomicsResponse:
        # Validate the local, provenance-checked load source before any network I/O.
        load = self.load_provider(
            request.annual_consumption_kwh, request.federal_state,
            request.profile_kind, h25_csv_path=self.h25_csv_path)
        weather = await self.pvgis_client.fetch(request.latitude, request.longitude)
        surfaces = tuple(self._surface(item) for item in request.pv_surfaces)
        plant = calculate_pv_plant(weather, surfaces)
        peak = plant.total_peak_power_kwp
        battery, battery_degradation = self._battery(request)
        assumptions = request.assumptions
        limit = assumptions.max_feed_in_power_kw
        if assumptions.max_feed_in_percent is not None:
            limit = peak * assumptions.max_feed_in_percent / 100
        projection = project_energy(
            load.hourly_consumption_kwh,
            tuple(item.ac_energy_kwh for item in plant.surfaces), assumptions.years,
            battery=battery, pv_degradation=PVDegradation(assumptions.pv_degradation_rate),
            battery_degradation=battery_degradation,
            max_grid_feed_in_power_kw=limit,
            feed_in_limit_years=assumptions.feed_in_limit_years,
        )
        tariff = resolve_eeg_surplus_tariff(
            peak, request.commissioning_date,
            manual_override_eur_per_kwh=request.manual_feed_in_tariff_eur_per_kwh)
        tariffs = annual_feed_in_tariffs(
            tariff, request.commissioning_date, assumptions.years,
            post_eeg_value_eur_per_kwh=assumptions.post_eeg_value_eur_per_kwh)
        events = tuple(OneTimeCost(item.operating_year, item.amount_eur,
                                   CostAllocation(item.allocation), item.label)
                       for item in request.one_time_costs)
        investment_inputs = EconomicInputs(
            request.electricity_price_eur_per_kwh,
            assumptions.electricity_price_growth_rate, tariffs,
            assumptions.nominal_discount_rate,
            request.pv_investment_eur, request.battery_incremental_investment_eur,
            request.package_investment_eur,
        )
        resolved_investments = resolve_investments(investment_inputs)
        pv_opex = assumptions.pv_operating_cost_year1_eur
        if pv_opex is None:
            if resolved_investments.pv_investment_eur is None:
                raise EconomicsError(
                    "PV investment cannot be resolved from the package price. "
                    "Enter annual PV operating costs explicitly."
                )
            pv_opex = resolved_investments.pv_investment_eur * .01
        economics = calculate_economics(projection, EconomicInputs(
            request.electricity_price_eur_per_kwh,
            assumptions.electricity_price_growth_rate, tariffs,
            assumptions.nominal_discount_rate,
            request.pv_investment_eur, request.battery_incremental_investment_eur,
            request.package_investment_eur, pv_opex,
            assumptions.battery_operating_cost_year1_eur,
            assumptions.operating_cost_growth_rate, events,
        ))
        first = projection.years[0].energy
        comparison = calculate_energy_scenarios(
            load.hourly_consumption_kwh,
            tuple(item.ac_energy_kwh for item in plant.surfaces), battery, peak * .60)
        warnings = derive_warnings(
            profile_kind=request.profile_kind,
            has_heat_pump=request.has_heat_pump,
            has_ev=request.has_electric_vehicle,
            package_only=(resolved_investments.package_investment_eur is not None
                          and (resolved_investments.pv_investment_eur is None
                               or (battery is not None and
                                   resolved_investments.battery_incremental_investment_eur is None))),
            manual_tariff=tariff.manual_override,
            pv_metrics_available=economics.pv.metrics.available,
            pv_payback=economics.pv.metrics.payback_years,
            battery_metrics_available=economics.incremental_battery.metrics.available,
            battery_npv=economics.incremental_battery.metrics.net_present_value_eur,
            battery_payback=economics.incremental_battery.metrics.payback_years,
            warranty_battery=bool(request.battery and request.battery.degradation_kind == "warranty"),
            feed_in_limit_in_base_case=(limit is not None
                                        and assumptions.feed_in_limit_years > 0),
        )
        return PVEconomicsResponse(
            metadata={
                "model_version": MODEL_VERSION,
                "calculated_at": self.clock().isoformat(), "market": "DE",
                "defaults_data_date": DEFAULTS_DATA_DATE,
                "assumptions": [asdict(item) for item in STANDARD_ASSUMPTIONS],
                "used_assumptions": {
                    **assumptions.model_dump(mode="json"),
                    "resolved_pv_operating_cost_year1_eur": pv_opex,
                    "resolved_battery": asdict(battery) if battery else None,
                },
                "profile_source": load.metadata.source_name,
                "profile": {
                    "type": load.metadata.source_type,
                    "id": load.profile_id,
                    "source": load.metadata.source_name,
                    "version": load.metadata.source_version,
                    "source_url": load.metadata.source_url,
                    "source_xlsx_sha256": load.metadata.source_xlsx_sha256,
                    "source_csv_sha256": load.metadata.source_csv_sha256,
                },
                "weather_source": weather.metadata.api_endpoint,
                "weather": {
                    "radiation_database": weather.metadata.radiation_database,
                    "source_period": weather.metadata.source_period,
                    "api_endpoint": weather.metadata.api_endpoint,
                    "selected_tmy_months": weather.metadata.selected_months,
                    "irradiance_time_offset_hours": weather.metadata.irradiance_time_offset_hours,
                    "retrieved_at": weather.metadata.retrieved_at.isoformat(),
                },
                "eeg": asdict(tariff),
            },
            first_year={
                "without_pv": _scenario(first.without_pv),
                "pv_only": _scenario(first.pv_only),
                "pv_with_battery": _scenario(first.pv_with_battery) if first.pv_with_battery else None,
            },
            economics={"pv": _economics(economics.pv),
                       "package": _economics(economics.package),
                       "incremental_battery": _economics(economics.incremental_battery)},
            feed_in_limit_comparison={
                "limit_kw": peak * .60,
                "base_pv_curtailed_kwh": first.pv_only.curtailed_pv_kwh,
                "limited_pv_curtailed_kwh": comparison.pv_only.curtailed_pv_kwh,
                "limited_battery_curtailed_kwh": (
                    comparison.pv_with_battery.curtailed_pv_kwh
                    if comparison.pv_with_battery else None),
            },
            warnings=[asdict(item) for item in warnings],
            disclaimers=["Orientation only; no financing, taxes or individual legal advice.",
                         "A partial final EEG year is represented by day-weighting in the annual model."],
        )

    @staticmethod
    def _surface(item):
        shading = (MonthlyHourlyShading(tuple(tuple(row) for row in item.shading_matrix))
                   if item.shading_matrix is not None
                   else ConstantShading(item.constant_shading_factor or 0))
        return PVSurface(item.identifier, item.peak_power_kwp, item.azimuth_deg,
                         item.tilt_deg, item.inverter_efficiency,
                         item.system_loss_fraction, shading, item.max_ac_power_kw)

    @staticmethod
    def _battery(request):
        item = request.battery
        if item is None:
            return None, None
        charge = item.max_charge_power_kw if item.max_charge_power_kw is not None else item.usable_capacity_kwh * .5
        discharge = item.max_discharge_power_kw if item.max_discharge_power_kw is not None else item.usable_capacity_kwh * .5
        config = BatteryConfig(item.usable_capacity_kwh, charge, discharge,
                               item.round_trip_efficiency)
        if item.degradation_kind == "warranty":
            model = WarrantyBatteryDegradation(
                item.residual_capacity_fraction, item.warranty_years,
                item.warranted_throughput_kwh, item.warranted_efc)
        else:
            model = GeometricBatteryDegradation(request.assumptions.battery_capacity_loss_rate)
        return config, model


def _scenario(value):
    return {key: getattr(value, key) for key in (
        "household_consumption_kwh", "pv_generation_kwh",
        "direct_pv_consumption_kwh", "battery_delivery_to_load_kwh",
        "battery_losses_kwh", "feed_in_kwh", "curtailed_pv_kwh",
        "curtailment_ratio", "grid_import_kwh", "self_consumption_ratio",
        "autonomy_ratio", "equivalent_full_cycles")}


def _economics(value):
    return {"year_zero_cashflow_eur": value.year_zero_cashflow_eur,
            "annual": [asdict(item) for item in value.annual],
            "metrics": asdict(value.metrics)}


pv_economics_service = PVEconomicsService()
