"""Stateless orchestration for the PV economics offer check."""

import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
from math import ceil

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
    calculate_pv_surface_from_poa,
)
from backend.pv_economics.pvgis import (
    PVGISHistoricalClient, PVGISResponseError, PVGISTMYClient,
)
from backend.pv_economics.projection import project_energy
from backend.pv_economics.simulation import calculate_energy_scenarios
from backend.pv_economics.warnings import derive_warnings
from backend.pv_economics.sensitivity import (
    HistoricalPlantYear, WeatherSensitivityError, select_weather_years,
)
from backend.pv_economics_api_models import PVEconomicsRequest, PVEconomicsResponse


@dataclass(frozen=True, slots=True)
class _Evaluation:
    projection: object
    economics: object


class PVEconomicsService:
    def __init__(self, *, pvgis_client: PVGISTMYClient | None = None,
                 historical_client: PVGISHistoricalClient | None = None,
                 load_provider: Callable[..., object] = generate_household_load_profile,
                 h25_csv_path: str | Path | None = None,
                 clock: Callable[[], datetime] | None = None) -> None:
        self.pvgis_client = pvgis_client or PVGISTMYClient()
        self.historical_client = historical_client or PVGISHistoricalClient()
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
        evaluation = self._evaluate(
            request, load.hourly_consumption_kwh,
            tuple(item.ac_energy_kwh for item in plant.surfaces), battery,
            battery_degradation, limit, tariffs, events, pv_opex,
        )
        projection, economics = evaluation.projection, evaluation.economics
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
        weather_sensitivity = None
        if request.include_weather_sensitivity:
            weather_sensitivity = await self._weather_sensitivity(
                request, surfaces, plant.annual_ac_energy_kwh,
                load.hourly_consumption_kwh, battery, battery_degradation,
                limit, tariffs, events, pv_opex,
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
            weather_sensitivity=weather_sensitivity,
        )

    @staticmethod
    def _evaluate(request, load_series, pv_areas, battery,
                  battery_degradation, limit, tariffs, events, pv_opex):
        assumptions = request.assumptions
        projection = project_energy(
            load_series, pv_areas, assumptions.years, battery=battery,
            pv_degradation=PVDegradation(assumptions.pv_degradation_rate),
            battery_degradation=battery_degradation,
            max_grid_feed_in_power_kw=limit,
            feed_in_limit_years=assumptions.feed_in_limit_years,
        )
        economics = calculate_economics(projection, EconomicInputs(
            request.electricity_price_eur_per_kwh,
            assumptions.electricity_price_growth_rate, tariffs,
            assumptions.nominal_discount_rate,
            request.pv_investment_eur, request.battery_incremental_investment_eur,
            request.package_investment_eur, pv_opex,
            assumptions.battery_operating_cost_year1_eur,
            assumptions.operating_cost_growth_rate, events,
        ))
        return _Evaluation(projection, economics)

    async def _weather_sensitivity(
        self, request, surfaces, tmy_generation, load_series, battery,
        battery_degradation, limit, tariffs, events, pv_opex,
    ):
        histories = []
        for surface in surfaces:
            histories.append(await self.historical_client.fetch(
                request.latitude, request.longitude, tilt_deg=surface.tilt_deg,
                azimuth_deg=surface.azimuth_deg,
            ))
        common_years = set(item.source_year for item in histories[0].years)
        for history in histories[1:]:
            common_years &= {item.source_year for item in history.years}
        metadata = histories[0].metadata
        if any((history.metadata.radiation_database != metadata.radiation_database
                or history.metadata.api_endpoint != metadata.api_endpoint
                or history.metadata.source_period != metadata.source_period)
               for history in histories[1:]):
            raise PVGISResponseError("Historical surface provenance is inconsistent.")
        plant_years = []
        for year in sorted(common_years):
            area_results = []
            for surface, history in zip(surfaces, histories):
                source = next(item for item in history.years if item.source_year == year)
                area_results.append(calculate_pv_surface_from_poa(source.hours, surface))
            timestamps = [tuple(hour.timestamp for hour in next(
                item for item in history.years if item.source_year == year).hours)
                for history in histories]
            if any(stamps != timestamps[0] for stamps in timestamps[1:]):
                raise PVGISResponseError("Historical surface timestamps are inconsistent.")
            plant_years.append(HistoricalPlantYear(
                year, tuple(item.ac_energy_kwh for item in area_results),
                sum(item.annual_ac_energy_kwh for item in area_results),
            ))
        try:
            selected = select_weather_years(tuple(plant_years))
        except WeatherSensitivityError as exc:
            raise PVGISResponseError(str(exc)) from exc
        ordered = sorted(item.annual_ac_energy_kwh for item in plant_years)
        median_rank = max(1, ceil(.5 * len(ordered)))
        scenarios = []
        for choice in selected:
            evaluation = self._evaluate(
                request, load_series, choice.year.surface_ac_energy_kwh, battery,
                battery_degradation, limit, tariffs, events, pv_opex,
            )
            first = evaluation.projection.years[0].energy
            economics = evaluation.economics
            deviation = ((choice.year.annual_ac_energy_kwh / tmy_generation - 1) * 100
                         if tmy_generation > 0 else None)
            scenarios.append({
                "label": choice.label, "display_label": choice.display_label,
                "source_year": choice.year.source_year,
                "quantile": choice.quantile, "nearest_rank": choice.nearest_rank,
                "annual_pv_generation_kwh": choice.year.annual_ac_energy_kwh,
                "deviation_from_tmy_percent": deviation,
                "first_year": _first_year(first),
                "economics": {
                    "pv": _metrics(economics.pv),
                    "package": _metrics(economics.package),
                    "incremental_battery": _metrics(economics.incremental_battery),
                },
            })
        return {
            "scenarios": scenarios,
            "distribution": {
                "complete_year_count": len(plant_years), "minimum_kwh": ordered[0],
                "median_kwh": ordered[median_rank - 1], "maximum_kwh": ordered[-1],
            },
            "source_period": metadata.source_period,
            "radiation_database": metadata.radiation_database,
            "api_endpoint": metadata.api_endpoint,
            "retrieved_at": metadata.retrieved_at.isoformat(),
            "quantile_method": "Nearest rank: rank = ceil(p × n), sorted by annual AC production then calendar year; p = 0.10, 0.50, 0.90.",
            "leap_day_normalization": metadata.leap_day_normalization,
            "notice": "Historical weather range from real years; not a forecast or guarantee. Degradation, soiling and additional shading are not mixed into year selection.",
        }

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


def _first_year(value):
    return {
        "without_pv": _scenario(value.without_pv),
        "pv_only": _scenario(value.pv_only),
        "pv_with_battery": (_scenario(value.pv_with_battery)
                            if value.pv_with_battery else None),
    }


def _metrics(value):
    metrics = value.metrics
    return {"available": metrics.available,
            "nominal_total_eur": metrics.nominal_total_eur,
            "net_present_value_eur": metrics.net_present_value_eur,
            "payback_years": metrics.payback_years}


def _economics(value):
    return {"year_zero_cashflow_eur": value.year_zero_cashflow_eur,
            "annual": [asdict(item) for item in value.annual],
            "metrics": asdict(value.metrics)}


pv_economics_service = PVEconomicsService()
