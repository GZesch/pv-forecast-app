from datetime import date
import json

from frontend.export_data import (
    build_forecast_export_rows,
    export_filename,
    forecast_rows_to_csv,
    forecast_rows_to_json,
)


def test_export_rows_include_energy_power_components_and_weather() -> None:
    forecast_rows = [
        {"timestamp": "2026-06-26T08:00:00Z", "predicted_power_kw": 3.0},
        {"timestamp": "2026-06-26T09:00:00Z", "predicted_power_kw": 4.0},
    ]
    components = [
        {
            "name": "Ost",
            "hourly": [
                {"timestamp": "2026-06-26T08:00:00Z", "predicted_power_kw": 1.0},
                {"timestamp": "2026-06-26T09:00:00Z", "predicted_power_kw": 1.5},
            ],
        }
    ]
    weather_rows = [
        {
            "timestamp": "2026-06-26T08:00:00Z",
            "direct_radiation": 500.0,
            "cloud_cover": 20.0,
        }
    ]

    rows = build_forecast_export_rows(
        forecast_rows, component_series=components, weather_rows=weather_rows
    )

    assert rows[0]["Gesamt-Ertrag [kWh]"] == 3.0
    assert rows[0]["Gesamt-Leistung [kW]"] == 3.0
    assert rows[0]["Ost Ertrag [kWh]"] == 1.0
    assert rows[0]["direct_radiation"] == 500.0
    assert rows[0]["cloud_cover"] == 20.0
    assert rows[1]["Gesamt-Ertrag [kWh]"] == 4.0


def test_export_rows_can_be_serialized_as_csv_and_json() -> None:
    rows = [{"Timestamp": "2026-06-26T08:00:00Z", "Gesamt-Ertrag [kWh]": 3.0}]

    csv_text = forecast_rows_to_csv(rows)
    json_text = forecast_rows_to_json(rows)

    assert "Timestamp,Gesamt-Ertrag [kWh]" in csv_text
    assert "2026-06-26T08:00:00Z" in csv_text
    assert json.loads(json_text) == rows


def test_export_filename_uses_normalized_project_code() -> None:
    assert (
        export_filename(" Test Familie ", "csv", date(2026, 6, 25))
        == "pv_forecast_test-familie_2026-06-25.csv"
    )
