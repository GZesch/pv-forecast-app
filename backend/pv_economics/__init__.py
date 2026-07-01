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
)
from .pvgis import (
    PVGISError, PVGISResponseError, PVGISTMYClient, PVGISTemporaryError,
    PVGISTimeoutError,
)
from .weather import TMYMetadata, TMYWeather, WeatherDataError, WeatherHour
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
    FinancialMetrics, OneTimeCost, calculate_economics,
)

__all__ = [
    "BatteryConfig", "EnergyBalance", "EnergyModelError", "EnergyModelResult",
    "HourlyEnergyFlow", "ScenarioResult", "calculate_energy_scenarios",
    "ConstantShading", "MonthlyHourlyShading", "PVGenerationError",
    "PVPlantResult", "PVSurface", "PVSurfaceResult", "calculate_pv_plant",
    "calculate_pv_surface", "PVGISError", "PVGISResponseError",
    "PVGISTMYClient", "PVGISTemporaryError", "PVGISTimeoutError",
    "TMYMetadata", "TMYWeather", "WeatherDataError", "WeatherHour",
    "H25DataUnavailableError", "LoadProfileError",
    "LoadProfileResult", "ProfileKind", "generate_household_load_profile",
    "DegradationError", "GeometricBatteryDegradation", "PVDegradation",
    "WarrantyBatteryDegradation", "EnergyProjection", "ProjectionYear",
    "project_energy", "CostAllocation", "EconomicInputs", "EconomicResult",
    "EconomicsError", "FinancialMetrics", "OneTimeCost", "calculate_economics",
]
