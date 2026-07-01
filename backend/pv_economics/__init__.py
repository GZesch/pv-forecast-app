"""Public API for the pure PV energy model."""

from .models import (
    BatteryConfig,
    EnergyBalance,
    EnergyModelError,
    EnergyModelResult,
    HourlyEnergyFlow,
    ScenarioResult,
)
from .simulation import calculate_energy_scenarios
from .pv_generation import (
    ConstantShading, MonthlyHourlyShading, PVGenerationError, PVPlantResult,
    PVSurface, PVSurfaceResult, calculate_pv_plant, calculate_pv_surface,
    calculate_pv_surface_from_poa,
)
from .pvgis import (
    PVGISError, PVGISHistoricalClient, PVGISResponseError, PVGISTMYClient,
    PVGISTemporaryError, PVGISTimeoutError, parse_pvgis_historical,
    pvgis_series_azimuth,
)
from .weather import (
    HistoricalMetadata, HistoricalPOAWeather, HistoricalYear, POAWeatherHour,
    TMYMetadata, TMYWeather, WeatherDataError, WeatherHour,
)
from .load_profiles import (
    H25DataUnavailableError, LoadProfileError, LoadProfileResult, ProfileKind,
    generate_household_load_profile,
)
from .degradation import (
    DegradationError, GeometricBatteryDegradation, PVDegradation,
    WarrantyBatteryDegradation,
)
from .projection import EnergyProjection, ProjectionYear, project_energy
from .economics import (
    CostAllocation, EconomicInputs, EconomicResult, EconomicsError,
    FinancialMetrics, OneTimeCost, ResolvedInvestments, calculate_economics,
    resolve_investments,
)
from .eeg import (
    EEGTariffError, EEGTariffResult, annual_feed_in_tariffs,
    resolve_eeg_surplus_tariff,
)

__all__ = [
    "BatteryConfig", "EnergyBalance", "EnergyModelError", "EnergyModelResult",
    "HourlyEnergyFlow", "ScenarioResult", "calculate_energy_scenarios",
    "ConstantShading", "MonthlyHourlyShading", "PVGenerationError",
    "PVPlantResult", "PVSurface", "PVSurfaceResult", "calculate_pv_plant",
    "calculate_pv_surface", "calculate_pv_surface_from_poa", "PVGISError",
    "PVGISHistoricalClient", "PVGISResponseError", "PVGISTMYClient",
    "PVGISTemporaryError", "PVGISTimeoutError", "parse_pvgis_historical",
    "pvgis_series_azimuth", "HistoricalMetadata", "HistoricalPOAWeather",
    "HistoricalYear", "POAWeatherHour",
    "TMYMetadata", "TMYWeather", "WeatherDataError", "WeatherHour",
    "H25DataUnavailableError", "LoadProfileError",
    "LoadProfileResult", "ProfileKind", "generate_household_load_profile",
    "DegradationError", "GeometricBatteryDegradation", "PVDegradation",
    "WarrantyBatteryDegradation", "EnergyProjection", "ProjectionYear",
    "project_energy", "CostAllocation", "EconomicInputs", "EconomicResult",
    "EconomicsError", "FinancialMetrics", "OneTimeCost", "calculate_economics",
    "ResolvedInvestments", "resolve_investments",
    "EEGTariffError", "EEGTariffResult", "annual_feed_in_tariffs",
    "resolve_eeg_surplus_tariff",
]
