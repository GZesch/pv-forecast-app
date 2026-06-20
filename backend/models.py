from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class InstallationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    location: str = Field(min_length=1, max_length=500)
    peak_power_kwp: float = Field(gt=0)
    azimuth: float = Field(ge=0, le=360)
    tilt: float = Field(ge=0, le=90)


class Installation(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
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
