from datetime import date, datetime, timedelta, timezone

from frontend.time_display import (
    create_hourly_energy_chart,
    create_hourly_chart,
    filter_component_series_by_days,
    filter_forecast_rows_by_days,
    forecast_rows_to_hourly_energy,
    format_german_date,
    format_german_datetime,
    format_short_german_date,
    summarize_daily_power,
    sum_hourly_energy_series,
    time_axis_tick_text,
    tick_interval_for_view_days,
)


def test_timestamp_is_converted_to_berlin_and_formatted_in_german() -> None:
    assert (
        format_german_datetime("2026-06-26T12:00:00Z")
        == "Freitag, 26.06.2026 14:00"
    )
    assert format_german_date("2026-06-26") == "Freitag, 26.06.2026"
    assert format_short_german_date("2026-06-26") == "26.06."


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
    assert len(figure.layout.annotations) == 0


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


def test_hourly_energy_uses_power_and_detected_interval() -> None:
    rows = [
        {"timestamp": "2026-06-26T08:00:00Z", "predicted_power_kw": 2.0},
        {"timestamp": "2026-06-26T10:00:00Z", "predicted_power_kw": 3.0},
        {"timestamp": "2026-06-26T12:00:00Z", "predicted_power_kw": 4.0},
    ]

    energy_rows = forecast_rows_to_hourly_energy(rows)

    assert [row["interval_hours"] for row in energy_rows] == [2.0, 2.0, 2.0]
    assert [row["interval_energy_kwh"] for row in energy_rows] == [4.0, 6.0, 8.0]


def test_hourly_energy_prefers_existing_backend_energy() -> None:
    rows = [
        {
            "timestamp": "2026-06-26T08:00:00Z",
            "predicted_power_kw": 10.0,
            "hourly_energy_kwh": 3.25,
        }
    ]

    assert forecast_rows_to_hourly_energy(rows)[0]["interval_energy_kwh"] == 3.25


def test_hourly_energy_series_are_summed_by_timestamp() -> None:
    components = [
        {
            "name": "Ost",
            "hourly": [
                {"timestamp": "2026-06-26T08:00:00Z", "predicted_power_kw": 2.0},
                {"timestamp": "2026-06-26T09:00:00Z", "predicted_power_kw": 3.0},
            ],
        },
        {
            "name": "West",
            "hourly": [
                {"timestamp": "2026-06-26T08:00:00Z", "predicted_power_kw": 1.5},
                {"timestamp": "2026-06-26T09:00:00Z", "predicted_power_kw": 2.5},
            ],
        },
    ]

    total = sum_hourly_energy_series(components)

    assert [row["interval_energy_kwh"] for row in total] == [3.5, 5.5]


def test_forecast_rows_are_filtered_by_selected_days() -> None:
    first_utc = datetime(2026, 6, 26, 0, tzinfo=timezone.utc)
    rows = [
        {
            "timestamp": (first_utc + timedelta(hours=hour)).isoformat(),
            "predicted_power_kw": float(hour),
        }
        for hour in range(8 * 24)
    ]

    assert len(filter_forecast_rows_by_days(rows, 1)) == 24
    assert len(filter_forecast_rows_by_days(rows, 3)) == 72
    assert len(filter_forecast_rows_by_days(rows, 7)) == 168


def test_component_series_are_filtered_by_selected_days() -> None:
    first_utc = datetime(2026, 6, 26, 0, tzinfo=timezone.utc)
    components = [
        {
            "name": "Ost",
            "hourly": [
                {
                    "timestamp": (first_utc + timedelta(hours=hour)).isoformat(),
                    "predicted_power_kw": 1.0,
                }
                for hour in range(48)
            ],
        }
    ]

    filtered = filter_component_series_by_days(components, 1)

    assert filtered[0]["name"] == "Ost"
    assert len(filtered[0]["hourly"]) == 24


def test_tick_interval_matches_selected_view_days() -> None:
    assert tick_interval_for_view_days(1) == 1
    assert tick_interval_for_view_days(3) == 3
    assert tick_interval_for_view_days(7) == 6
    assert tick_interval_for_view_days(1, compact=True) == 3
    assert tick_interval_for_view_days(3, compact=True) == 12
    assert tick_interval_for_view_days(7, compact=True) == 12


def test_hourly_energy_chart_uses_single_bar_trace_for_installation() -> None:
    rows = [
        {"timestamp": "2026-06-26T08:00:00Z", "predicted_power_kw": 2.0},
        {"timestamp": "2026-06-26T09:00:00Z", "predicted_power_kw": 4.0},
    ]

    figure = create_hourly_energy_chart(rows)

    assert figure.layout.title.text == ""
    assert figure.layout.yaxis.title.text == "Ertrag [kWh]"
    assert len(figure.data) == 1
    assert figure.data[0].type == "bar"
    assert list(figure.data[0].y) == [2.0, 4.0]


def test_hourly_energy_chart_stacks_component_bars_for_plant() -> None:
    total_rows = [
        {"timestamp": "2026-06-26T08:00:00Z", "predicted_power_kw": 3.5},
    ]
    components = [
        {
            "name": "Ost",
            "hourly": [
                {"timestamp": "2026-06-26T08:00:00Z", "predicted_power_kw": 2.0}
            ],
        },
        {
            "name": "West",
            "hourly": [
                {"timestamp": "2026-06-26T08:00:00Z", "predicted_power_kw": 1.5}
            ],
        },
    ]

    figure = create_hourly_energy_chart(
        total_rows, component_series=components, stack_components=True
    )

    assert figure.layout.barmode == "stack"
    assert [trace.name for trace in figure.data] == ["Ost", "West"]
    assert [trace.type for trace in figure.data] == ["bar", "bar"]
    assert sum(trace.y[0] for trace in figure.data) == 3.5


def test_hourly_energy_chart_standard_mode_shows_sum_not_components() -> None:
    total_rows = [
        {"timestamp": "2026-06-26T08:00:00Z", "predicted_power_kw": 3.5},
    ]
    components = [
        {
            "name": "Ost",
            "hourly": [
                {"timestamp": "2026-06-26T08:00:00Z", "predicted_power_kw": 2.0}
            ],
        },
        {
            "name": "West",
            "hourly": [
                {"timestamp": "2026-06-26T08:00:00Z", "predicted_power_kw": 1.5}
            ],
        },
    ]

    figure = create_hourly_energy_chart(
        total_rows, component_series=components, stack_components=False
    )

    assert len(figure.data) == 1
    assert figure.data[0].name == "Ertrag pro Stunde"
    assert list(figure.data[0].y) == [3.5]
    assert figure.layout.showlegend is False


def test_hourly_energy_chart_sorts_components_by_displayed_energy_descending() -> None:
    total_rows = [
        {"timestamp": "2026-06-26T08:00:00Z", "predicted_power_kw": 10.0},
        {"timestamp": "2026-06-26T09:00:00Z", "predicted_power_kw": 10.0},
    ]
    components = [
        {
            "name": "Klein",
            "hourly": [
                {"timestamp": "2026-06-26T08:00:00Z", "predicted_power_kw": 1.0},
                {"timestamp": "2026-06-26T09:00:00Z", "predicted_power_kw": 1.0},
            ],
        },
        {
            "name": "Groß",
            "hourly": [
                {"timestamp": "2026-06-26T08:00:00Z", "predicted_power_kw": 4.0},
                {"timestamp": "2026-06-26T09:00:00Z", "predicted_power_kw": 5.0},
            ],
        },
        {
            "name": "Mittel",
            "hourly": [
                {"timestamp": "2026-06-26T08:00:00Z", "predicted_power_kw": 2.0},
                {"timestamp": "2026-06-26T09:00:00Z", "predicted_power_kw": 3.0},
            ],
        },
    ]

    figure = create_hourly_energy_chart(
        total_rows, component_series=components, stack_components=True
    )

    assert [trace.name for trace in figure.data] == ["Groß", "Mittel", "Klein"]
    assert figure.layout.showlegend is True


def test_hourly_energy_chart_uses_explicit_tick_interval() -> None:
    first_utc = datetime(2026, 6, 26, 0, tzinfo=timezone.utc)
    rows = [
        {
            "timestamp": (first_utc + timedelta(hours=hour)).isoformat(),
            "predicted_power_kw": 1.0,
        }
        for hour in range(24)
    ]

    one_day = create_hourly_energy_chart(rows, tick_interval_hours=1)
    weekly = create_hourly_energy_chart(rows, tick_interval_hours=6)

    assert len(one_day.layout.xaxis.ticktext) > len(weekly.layout.xaxis.ticktext)
    assert "01:00" in list(one_day.layout.xaxis.ticktext)
    assert "01:00" not in list(weekly.layout.xaxis.ticktext)


def test_hourly_energy_chart_compact_mode_reduces_labels_and_day_annotations() -> None:
    first_utc = datetime(2026, 6, 26, 0, tzinfo=timezone.utc)
    rows = [
        {
            "timestamp": (first_utc + timedelta(hours=hour)).isoformat(),
            "predicted_power_kw": 1.0,
        }
        for hour in range(24)
    ]

    desktop = create_hourly_energy_chart(rows, tick_interval_hours=1)
    compact = create_hourly_energy_chart(
        rows,
        tick_interval_hours=tick_interval_for_view_days(1, compact=True),
        compact=True,
        view_days=1,
    )

    assert len(desktop.layout.xaxis.ticktext) > len(compact.layout.xaxis.ticktext)
    assert len(desktop.layout.annotations) == 0
    assert [annotation.text for annotation in compact.layout.annotations] == [
        "Ertrag [kWh]"
    ]
    assert compact.layout.margin.b < desktop.layout.margin.b


def test_compact_time_axis_for_multi_day_views_labels_noon_with_dates() -> None:
    tick_values = [
        datetime(2026, 6, 25, 0),
        datetime(2026, 6, 26, 12),
    ]

    assert time_axis_tick_text(tick_values, compact=True, view_days=3) == [
        "00:00",
        "26.06.",
    ]
    assert time_axis_tick_text(tick_values, compact=True, view_days=7) == [
        "00:00",
        "26.06.",
    ]


def test_compact_three_day_chart_uses_visible_noon_date_tick_labels() -> None:
    first_utc = datetime(2026, 6, 26, 0, tzinfo=timezone.utc)
    rows = [
        {
            "timestamp": (first_utc + timedelta(hours=hour)).isoformat(),
            "predicted_power_kw": 1.0,
        }
        for hour in range(72)
    ]

    figure = create_hourly_energy_chart(
        rows,
        tick_interval_hours=tick_interval_for_view_days(3, compact=True),
        compact=True,
        view_days=3,
    )

    tick_labels = list(figure.layout.xaxis.ticktext)
    tick_values = list(figure.layout.xaxis.tickvals)
    assert tick_labels
    assert all(label for label in tick_labels)
    assert all(value.hour in (0, 12) for value in tick_values)
    assert all(
        label == f"{value:%d.%m.}"
        for label, value in zip(tick_labels, tick_values, strict=True)
        if value.hour == 12
    )
    assert "00:00" in tick_labels
    assert not any(
        annotation.text.endswith(".") for annotation in figure.layout.annotations
    )


def test_compact_seven_day_chart_uses_visible_noon_date_tick_labels() -> None:
    first_utc = datetime(2026, 6, 26, 0, tzinfo=timezone.utc)
    rows = [
        {
            "timestamp": (first_utc + timedelta(hours=hour)).isoformat(),
            "predicted_power_kw": 1.0,
        }
        for hour in range(7 * 24)
    ]

    figure = create_hourly_energy_chart(
        rows,
        tick_interval_hours=tick_interval_for_view_days(7, compact=True),
        compact=True,
        view_days=7,
    )

    tick_labels = list(figure.layout.xaxis.ticktext)
    tick_values = list(figure.layout.xaxis.tickvals)
    noon_labels = [
        label
        for label, value in zip(tick_labels, tick_values, strict=True)
        if value.hour == 12
    ]
    assert all(label for label in tick_labels)
    assert all(value.hour in (0, 12) for value in tick_values)
    assert len(noon_labels) >= 7
    assert all(label.endswith(".") and "2026" not in label for label in noon_labels)
    assert not any(
        annotation.text.endswith(".") for annotation in figure.layout.annotations
    )
    assert any(
        annotation.text == "Ertrag [kWh]" for annotation in figure.layout.annotations
    )
    assert figure.layout.yaxis.title.text == ""
    assert figure.layout.yaxis.ticklabelposition == "outside"
    assert figure.layout.margin.l <= 30


def test_hourly_chart_can_add_component_curves() -> None:
    total = [
        {"timestamp": "2026-06-20T10:00:00Z", "predicted_power_kw": 5.0}
    ]
    components = [
        {
            "name": "Ost",
            "hourly": [
                {
                    "timestamp": "2026-06-20T10:00:00Z",
                    "predicted_power_kw": 2.0,
                }
            ],
        },
        {
            "name": "West",
            "hourly": [
                {
                    "timestamp": "2026-06-20T10:00:00Z",
                    "predicted_power_kw": 3.0,
                }
            ],
        },
    ]

    figure = create_hourly_chart(
        total,
        value_key="predicted_power_kw",
        trace_name="Gesamtleistung",
        y_axis_title="Leistung (kW)",
        additional_series=components,
    )

    assert [trace.name for trace in figure.data] == [
        "Gesamtleistung",
        "Ost",
        "West",
    ]
    assert figure.layout.showlegend is True
