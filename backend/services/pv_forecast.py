from collections.abc import Sequence
from datetime import date, datetime

import numpy as np
import pandas as pd
import pvlib

from backend.models import (
    DailyEnergyYield,
    PVForecastMetrics,
    PVForecastRow,
    WeatherForecastRow,
)


class PVForecastError(Exception):
    """Raised when a PV forecast cannot be calculated."""


class PVForecastService:
    """Calculate a simple, deterministic PVWatts-based power forecast."""

    def calculate(
        self,
        *,
        latitude: float,
        longitude: float,
        peak_power_kwp: float,
        azimuth: float,
        tilt: float,
        weather: Sequence[WeatherForecastRow],
    ) -> list[PVForecastRow]:
        if peak_power_kwp <= 0:
            raise PVForecastError("Die Nennleistung der PV-Anlage muss positiv sein.")
        if not weather:
            raise PVForecastError("Es sind keine Wetterdaten für die Prognose vorhanden.")

        self._validate_weather(weather)

        times = pd.DatetimeIndex([row.timestamp for row in weather])
        if times.tz is None:
            times = times.tz_localize("UTC")
        else:
            times = times.tz_convert("UTC")

        try:
            solar_position = pvlib.solarposition.get_solarposition(
                times, latitude=latitude, longitude=longitude
            )
            apparent_zenith = solar_position["apparent_zenith"]
            solar_azimuth = solar_position["azimuth"]

            direct_horizontal = pd.Series(
                [float(row.direct_radiation) for row in weather], index=times
            ).clip(lower=0.0)
            diffuse_horizontal = pd.Series(
                [float(row.diffuse_radiation) for row in weather], index=times
            ).clip(lower=0.0)
            global_horizontal = direct_horizontal + diffuse_horizontal

            cosine_zenith = np.cos(np.radians(apparent_zenith))
            direct_normal = pd.Series(0.0, index=times)
            sun_is_high_enough = cosine_zenith > 0.065
            direct_normal.loc[sun_is_high_enough] = (
                direct_horizontal.loc[sun_is_high_enough]
                / cosine_zenith.loc[sun_is_high_enough]
            )
            direct_normal = direct_normal.clip(lower=0.0, upper=1400.0)

            poa = pvlib.irradiance.get_total_irradiance(
                surface_tilt=tilt,
                surface_azimuth=azimuth,
                solar_zenith=apparent_zenith,
                solar_azimuth=solar_azimuth,
                dni=direct_normal,
                ghi=global_horizontal,
                dhi=diffuse_horizontal,
                albedo=0.2,
                model="isotropic",
            )["poa_global"].fillna(0.0).clip(lower=0.0)

            ambient_temperature = pd.Series(
                [float(row.temperature_2m) for row in weather], index=times
            )
            wind_speed = pd.Series(
                [max(float(row.wind_speed_10m), 0.0) for row in weather], index=times
            )
            cell_temperature = pvlib.temperature.faiman(
                poa, ambient_temperature, wind_speed
            )

            dc_power_w = pvlib.pvsystem.pvwatts_dc(
                effective_irradiance=poa,
                temp_cell=cell_temperature,
                pdc0=peak_power_kwp * 1000.0,
                gamma_pdc=-0.004,
            )
            power_kw = np.clip(
                np.nan_to_num(dc_power_w, nan=0.0),
                0.0,
                peak_power_kwp * 1000.0,
            ) / 1000.0
        except (KeyError, TypeError, ValueError, FloatingPointError) as exc:
            raise PVForecastError(
                "Die PV-Prognose konnte aus den Wetterdaten nicht berechnet werden."
            ) from exc

        return [
            PVForecastRow(
                timestamp=weather[index].timestamp,
                predicted_power_kw=round(float(value), 3),
            )
            for index, value in enumerate(power_kw)
        ]

    @staticmethod
    def calculate_daily_energy(
        hourly_forecast: Sequence[PVForecastRow],
    ) -> list[DailyEnergyYield]:
        """Sum hourly mean power values to daily energy in kWh."""
        totals: dict[date, float] = {}
        for row in hourly_forecast:
            forecast_date = row.timestamp.date()
            totals[forecast_date] = totals.get(forecast_date, 0.0) + max(
                row.predicted_power_kw, 0.0
            )

        return [
            DailyEnergyYield(
                date=forecast_date,
                daily_energy_kwh=round(energy_kwh, 3),
            )
            for forecast_date, energy_kwh in sorted(totals.items())
        ]

    @staticmethod
    def calculate_metrics(
        hourly_forecast: Sequence[PVForecastRow],
    ) -> PVForecastMetrics:
        """Return the maximum forecast power and its first timestamp."""
        if not hourly_forecast:
            raise PVForecastError(
                "Es sind keine Stundenwerte für die Kennzahlen vorhanden."
            )

        peak_row = max(hourly_forecast, key=lambda row: row.predicted_power_kw)
        return PVForecastMetrics(
            peak_power_kw=peak_row.predicted_power_kw,
            peak_timestamp=peak_row.timestamp,
        )

    @staticmethod
    def aggregate_hourly_forecasts(
        forecasts: Sequence[Sequence[PVForecastRow]],
    ) -> list[PVForecastRow]:
        """Sum component forecasts by timestamp."""
        totals: dict[datetime, float] = {}
        for forecast in forecasts:
            for point in forecast:
                totals[point.timestamp] = (
                    totals.get(point.timestamp, 0.0) + point.predicted_power_kw
                )

        if not totals:
            raise PVForecastError(
                "Für das Kraftwerk sind keine Prognosewerte vorhanden."
            )

        return [
            PVForecastRow(
                timestamp=timestamp,
                predicted_power_kw=round(max(power, 0.0), 3),
            )
            for timestamp, power in sorted(totals.items())
        ]

    @staticmethod
    def _validate_weather(weather: Sequence[WeatherForecastRow]) -> None:
        required_values = (
            "temperature_2m",
            "direct_radiation",
            "diffuse_radiation",
            "wind_speed_10m",
        )
        for row in weather:
            if any(getattr(row, field) is None for field in required_values):
                raise PVForecastError(
                    "Die Wetterdaten sind für eine PV-Prognose unvollständig."
                )


pv_forecast_service = PVForecastService()
