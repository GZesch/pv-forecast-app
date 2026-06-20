from datetime import date, datetime, timedelta, timezone

from frontend.time_display import (
    create_hourly_chart,
    format_german_date,
    format_german_datetime,
    summarize_daily_power,
)


def test_timestamp_is_converted_to_berlin_and_formatted_in_german() -> None:
    assert (
        format_german_datetime("2026-06-26T12:00:00Z")
        == "Freitag, 26.06.2026 14:00"
    )
    assert format_german_date("2026-06-26") == "Freitag, 26.06.2026"


def test_hourly_chart_uses_three_hour_ticks_and_centered_day_label() -> None:
    first_utc = datetime(2026, 6, 25, 22, tzinfo=timezone.utc)
    rows = [
        {
            "timestamp": (first_utc + timedelta(hours=hour)).isoformat(),
            "predicted_power_kw": float(hour),
        }
        for hour in range(22)
    ]

    figure = create_hourly_chart(
        rows,
        value_key="predicted_power_kw",
        trace_name="PV-Leistung",
        y_axis_title="Leistung (kW)",
    )

    assert list(figure.layout.xaxis.ticktext) == [
        "00:00",
        "03:00",
        "06:00",
        "09:00",
        "12:00",
        "15:00",
        "18:00",
        "21:00",
    ]
    assert len(figure.layout.annotations) == 1
    assert figure.layout.annotations[0].text == "Freitag, 26.06.2026"
    assert figure.layout.annotations[0].xref == "x"
    assert figure.layout.annotations[0].yref == "paper"


def test_daily_summary_calculates_energy_and_peak_per_local_day() -> None:
    rows = [
        {"timestamp": "2026-06-26T08:00:00Z", "predicted_power_kw": 2.0},
        {"timestamp": "2026-06-26T09:00:00Z", "predicted_power_kw": 5.5},
        {"timestamp": "2026-06-26T10:00:00Z", "predicted_power_kw": 4.0},
        {"timestamp": "2026-06-27T09:00:00Z", "predicted_power_kw": 3.0},
    ]

    summaries = summarize_daily_power(rows, start_date=date(2026, 6, 26))

    assert summaries[0]["energy_kwh"] == 11.5
    assert summaries[0]["peak_power_kw"] == 5.5
    assert summaries[0]["peak_timestamp"].strftime("%H:%M") == "11:00"
    assert summaries[1]["energy_kwh"] == 3.0
    assert summaries[2]["energy_kwh"] is None
