from datetime import date, datetime
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


class InstallationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    location: str = Field(min_length=1, max_length=500)
    peak_power_kwp: float = Field(gt=0)
    azimuth: float = Field(ge=0, le=360)
    tilt: float = Field(ge=0, le=90)

    @field_validator("name", "location", mode="before")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        return value.strip() if isinstance(value, str) else value


class InstallationUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    location: str = Field(min_length=1, max_length=500)
    peak_power_kwp: float = Field(gt=0)
    azimuth: float = Field(ge=0, le=360)
    tilt: float = Field(ge=0, le=90)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)

    @field_validator("name", "location", mode="before")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def validate_coordinate_pair(self) -> "InstallationUpdate":
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError(
                "Breitengrad und Längengrad müssen gemeinsam angegeben werden."
            )
        return self


class Installation(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    plant_id: UUID | None = None
    name: str
    location_label: str | None = None
    latitude: float
    longitude: float
    peak_power_kwp: float
    azimuth: float
    tilt: float
    created_at: datetime


class WeatherForecastRow(BaseModel):
    timestamp: datetime
    temperature_2m: float | None
    cloud_cover: float | None
    direct_radiation: float | None
    diffuse_radiation: float | None
    wind_speed_10m: float | None


class PVForecastRow(BaseModel):
    timestamp: datetime
    predicted_power_kw: float


class DailyEnergyYield(BaseModel):
    date: date
    daily_energy_kwh: float


class PVForecastMetrics(BaseModel):
    peak_power_kw: float
    peak_timestamp: datetime


class PVForecastResponse(BaseModel):
    hourly: list[PVForecastRow]
    daily: list[DailyEnergyYield]
    metrics: PVForecastMetrics


class ForecastHistoryRun(BaseModel):
    id: UUID
    created_at: datetime
    forecast_start: datetime
    forecast_end: datetime
    daily: list[DailyEnergyYield]
    peak_power_kw: float
    peak_timestamp: datetime


class PlantCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    location_label: str | None = Field(default=None, max_length=500)

    @field_validator("name", mode="before")
    @classmethod
    def strip_name(cls, value: str) -> str:
        return value.strip() if isinstance(value, str) else value


class PlantUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    location_label: str | None = Field(default=None, max_length=500)

    @field_validator("name", mode="before")
    @classmethod
    def strip_name(cls, value: str) -> str:
        return value.strip() if isinstance(value, str) else value


class Plant(BaseModel):
    id: UUID
    name: str
    location_label: str | None = None
    created_at: datetime


class PlantForecastComponent(BaseModel):
    installation_id: UUID
    name: str
    hourly: list[PVForecastRow]


class PlantPVForecastResponse(PVForecastResponse):
    components: list[PlantForecastComponent]
