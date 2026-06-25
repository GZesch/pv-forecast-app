import csv
import json
from datetime import date
from io import StringIO
from typing import Any

try:
    from .session_identity import normalize_user_code
    from .time_display import forecast_rows_to_hourly_energy, format_german_datetime
except ImportError:
    from session_identity import normalize_user_code
    from time_display import forecast_rows_to_hourly_energy, format_german_datetime


def _rows_by_timestamp(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(row["timestamp"]): row for row in rows}


def build_forecast_export_rows(
    forecast_rows: list[dict[str, Any]],
    *,
    component_series: list[dict[str, Any]] | None = None,
    weather_rows: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    energy_rows = forecast_rows_to_hourly_energy(forecast_rows)
    forecast_by_timestamp = _rows_by_timestamp(forecast_rows)
    weather_by_timestamp = _rows_by_timestamp(weather_rows or [])
    component_energy = {
        str(component.get("name", "Einzelanlage")): _rows_by_timestamp(
            forecast_rows_to_hourly_energy(component.get("hourly", []))
        )
        for component in component_series or []
    }

    export_rows: list[dict[str, Any]] = []
    for energy_row in energy_rows:
        timestamp = str(energy_row["timestamp"])
        source_row = forecast_by_timestamp.get(timestamp, {})
        export_row: dict[str, Any] = {
            "Zeitpunkt": format_german_datetime(timestamp),
            "Timestamp": timestamp,
            "Gesamt-Ertrag [kWh]": round(
                float(energy_row["interval_energy_kwh"]), 3
            ),
            "Intervall [h]": float(energy_row["interval_hours"]),
        }
        if "predicted_power_kw" in source_row:
            export_row["Gesamt-Leistung [kW]"] = source_row["predicted_power_kw"]

        for component_name, rows_by_timestamp in component_energy.items():
            component_row = rows_by_timestamp.get(timestamp)
            if component_row is not None:
                export_row[f"{component_name} Ertrag [kWh]"] = round(
                    float(component_row["interval_energy_kwh"]), 3
                )

        weather_row = weather_by_timestamp.get(timestamp)
        if weather_row:
            for key in (
                "temperature_2m",
                "cloud_cover",
                "direct_radiation",
                "diffuse_radiation",
                "direct_normal_irradiance",
                "shortwave_radiation",
                "wind_speed_10m",
            ):
                if key in weather_row:
                    export_row[key] = weather_row[key]
        export_rows.append(export_row)

    return export_rows


def forecast_rows_to_csv(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return ""
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


def forecast_rows_to_json(rows: list[dict[str, Any]]) -> str:
    return json.dumps(rows, ensure_ascii=False, indent=2)


def export_filename(project_code: str | None, extension: str, today: date) -> str:
    safe_code = "".join(
        character if character.isalnum() or character in ("-", "_") else "-"
        for character in normalize_user_code(project_code)
    ).strip("-")
    return f"pv_forecast_{safe_code or 'demo'}_{today:%Y-%m-%d}.{extension}"
