from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

import plotly.graph_objects as go


DISPLAY_TIMEZONE = ZoneInfo("Europe/Berlin")
GERMAN_WEEKDAYS = (
    "Montag",
    "Dienstag",
    "Mittwoch",
    "Donnerstag",
    "Freitag",
    "Samstag",
    "Sonntag",
)
ENERGY_KEYS = ("hourly_energy_kwh", "interval_energy_kwh", "energy_kwh")
FORECAST_VIEW_DAYS = {
    "1 Tag": 1,
    "3 Tage": 3,
    "7 Tage": 7,
}


def parse_timestamp(value: str | datetime) -> datetime:
    """Parse an API timestamp and convert it to Europe/Berlin."""
    parsed = (
        value
        if isinstance(value, datetime)
        else datetime.fromisoformat(value.replace("Z", "+00:00"))
    )
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(DISPLAY_TIMEZONE)


def parse_date(value: str | date) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(value)


def format_german_date(value: str | date) -> str:
    parsed = parse_date(value)
    return f"{GERMAN_WEEKDAYS[parsed.weekday()]}, {parsed:%d.%m.%Y}"


def format_short_german_date(value: str | date) -> str:
    parsed = parse_date(value)
    return f"{parsed:%d.%m.}"


def format_german_datetime(value: str | datetime) -> str:
    parsed = parse_timestamp(value)
    return f"{GERMAN_WEEKDAYS[parsed.weekday()]}, {parsed:%d.%m.%Y %H:%M}"


def today_in_display_timezone() -> date:
    return datetime.now(DISPLAY_TIMEZONE).date()


def _positive_float(value: Any) -> float:
    return max(float(value), 0.0)


def _energy_from_row(row: dict[str, Any], interval_hours: float) -> float:
    for key in ENERGY_KEYS:
        if key in row and row[key] is not None:
            return _positive_float(row[key])
    return _positive_float(row["predicted_power_kw"]) * interval_hours


def forecast_rows_to_hourly_energy(
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Convert power forecast rows to interval energy rows.

    The API currently returns hourly power values. The frontend checks the actual
    timestamp spacing and converts power to energy via kW * interval hours.
    """
    if not rows:
        return []

    parsed_rows = sorted(
        ((parse_timestamp(row["timestamp"]), row) for row in rows),
        key=lambda item: item[0],
    )
    positive_deltas = sorted(
        (later[0] - earlier[0]).total_seconds() / 3600
        for earlier, later in zip(parsed_rows, parsed_rows[1:], strict=False)
        if (later[0] - earlier[0]).total_seconds() > 0
    )
    if positive_deltas:
        middle = len(positive_deltas) // 2
        if len(positive_deltas) % 2:
            interval_hours = positive_deltas[middle]
        else:
            interval_hours = (
                positive_deltas[middle - 1] + positive_deltas[middle]
            ) / 2
    else:
        interval_hours = 1.0

    return [
        {
            "timestamp": row["timestamp"],
            "local_timestamp": timestamp,
            "chart_timestamp": timestamp.replace(tzinfo=None),
            "interval_hours": interval_hours,
            "interval_energy_kwh": round(_energy_from_row(row, interval_hours), 6),
        }
        for timestamp, row in parsed_rows
    ]


def sum_hourly_energy_series(
    series: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Sum interval energy rows from multiple component series by timestamp."""
    totals: dict[datetime, float] = defaultdict(float)
    source_timestamp: dict[datetime, str] = {}
    for item in series:
        for row in forecast_rows_to_hourly_energy(item.get("hourly", [])):
            chart_timestamp = row["chart_timestamp"]
            totals[chart_timestamp] += row["interval_energy_kwh"]
            source_timestamp[chart_timestamp] = row["timestamp"]

    return [
        {
            "timestamp": source_timestamp[chart_timestamp],
            "chart_timestamp": chart_timestamp,
            "interval_energy_kwh": round(total, 6),
        }
        for chart_timestamp, total in sorted(totals.items())
    ]


def filter_forecast_rows_by_days(
    rows: list[dict[str, Any]], days: int
) -> list[dict[str, Any]]:
    """Keep forecast rows from the first displayed timestamp for the selected days."""
    if not rows:
        return []

    sorted_rows = sorted(rows, key=lambda row: parse_timestamp(row["timestamp"]))
    start = parse_timestamp(sorted_rows[0]["timestamp"])
    end = start + timedelta(days=days)
    return [
        row
        for row in sorted_rows
        if start <= parse_timestamp(row["timestamp"]) < end
    ]


def filter_component_series_by_days(
    series: list[dict[str, Any]], days: int
) -> list[dict[str, Any]]:
    return [
        {
            **component,
            "hourly": filter_forecast_rows_by_days(
                component.get("hourly", []), days
            ),
        }
        for component in series
    ]


def tick_interval_for_view_days(days: int, *, compact: bool = False) -> int:
    if compact:
        if days <= 1:
            return 3
        return 12
    if days <= 1:
        return 1
    if days <= 3:
        return 3
    return 6


def sort_component_series_by_energy(
    series: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Sort components descending by interval energy so the largest stack is lowest."""
    return sorted(
        series,
        key=lambda component: sum(
            row["interval_energy_kwh"]
            for row in forecast_rows_to_hourly_energy(component.get("hourly", []))
        ),
        reverse=True,
    )


def summarize_daily_power(
    rows: list[dict[str, Any]], start_date: date | None = None
) -> list[dict[str, Any]]:
    """Build energy and peak metrics for three local calendar days."""
    grouped: dict[date, list[tuple[datetime, float]]] = defaultdict(list)
    for row in rows:
        timestamp = parse_timestamp(row["timestamp"])
        grouped[timestamp.date()].append(
            (timestamp, _positive_float(row["predicted_power_kw"]))
        )
    energy_by_day: dict[date, float] = defaultdict(float)
    for row in forecast_rows_to_hourly_energy(rows):
        timestamp = row["local_timestamp"]
        energy_by_day[timestamp.date()] += row["interval_energy_kwh"]

    first_date = start_date or today_in_display_timezone()
    summaries: list[dict[str, Any]] = []
    for offset in range(3):
        current_date = first_date + timedelta(days=offset)
        points = grouped.get(current_date, [])
        if not points:
            summaries.append(
                {
                    "date": current_date,
                    "energy_kwh": None,
                    "peak_power_kw": None,
                    "peak_timestamp": None,
                }
            )
            continue

        peak_timestamp, peak_power = max(points, key=lambda item: item[1])
        summaries.append(
            {
                "date": current_date,
                "energy_kwh": round(energy_by_day[current_date], 3),
                "peak_power_kw": peak_power,
                "peak_timestamp": peak_timestamp,
            }
        )

    return summaries


def _tick_interval_hours(chart_times: list[datetime]) -> int:
    if len(chart_times) < 2:
        return 1
    duration_hours = (
        max(chart_times) - min(chart_times)
    ).total_seconds() / 3600
    if duration_hours <= 30:
        return 1
    if duration_hours <= 72:
        return 3
    return 6


def time_axis_tick_text(
    tick_values: list[datetime], *, compact: bool = False, view_days: int | None = None
) -> list[str]:
    if compact and (view_days or 0) in (3, 7):
        return [
            format_short_german_date(value.date())
            if value.hour == 12
            else value.strftime("%H:%M")
            for value in tick_values
        ]
    return [value.strftime("%H:%M") for value in tick_values]


def should_show_day_annotations(*, compact: bool = False, view_days: int | None = None) -> bool:
    if compact:
        return False
    return view_days in (3, 7)


def apply_time_axis(
    figure: go.Figure,
    chart_times: list[datetime],
    *,
    tick_interval_hours: int | None = None,
    compact: bool = False,
    view_days: int | None = None,
) -> None:
    if not chart_times:
        return

    interval = tick_interval_hours or _tick_interval_hours(chart_times)
    if compact and (view_days or 0) in (3, 7):
        tick_values = [
            chart_time
            for chart_time in chart_times
            if chart_time.minute == 0 and chart_time.hour % 12 == 0
        ]
    else:
        tick_values = [
            chart_time
            for chart_time in chart_times
            if chart_time.minute == 0 and chart_time.hour % interval == 0
        ]
    tick_text = time_axis_tick_text(
        tick_values, compact=compact, view_days=view_days
    )

    figure.update_xaxes(
        tickmode="array",
        tickvals=tick_values,
        ticktext=tick_text,
        tickangle=0,
        ticks="outside",
        showgrid=True,
        gridcolor="rgba(120, 120, 120, 0.16)",
        gridwidth=0.6,
        title=None,
        tickfont={"size": 12 if compact else 14},
    )

    if not should_show_day_annotations(compact=compact, view_days=view_days):
        return

    times_by_day: dict[date, list[datetime]] = defaultdict(list)
    for chart_time in chart_times:
        times_by_day[chart_time.date()].append(chart_time)

    for day, day_times in sorted(times_by_day.items()):
        noon_values = [
            day_time
            for day_time in day_times
            if day_time.hour == 12 and day_time.minute == 0
        ]
        if compact and view_days in (3, 7) and not noon_values:
            continue
        first, last = min(day_times), max(day_times)
        center = noon_values[0] if compact and view_days in (3, 7) else first + (last - first) / 2
        figure.add_annotation(
            x=center,
            y=-0.22,
            xref="x",
            yref="paper",
            text=format_short_german_date(day),
            showarrow=False,
            xanchor="center",
            yanchor="top",
            font={"size": 14, "color": "#4b5563"},
        )


def create_hourly_chart(
    rows: list[dict[str, Any]],
    *,
    value_key: str,
    trace_name: str,
    y_axis_title: str,
    additional_series: list[dict[str, Any]] | None = None,
) -> go.Figure:
    """Create an hourly chart with 3-hour ticks and centered day labels."""
    local_times = [parse_timestamp(row["timestamp"]) for row in rows]
    # Naive local values prevent the browser from applying another timezone conversion.
    chart_times = [timestamp.replace(tzinfo=None) for timestamp in local_times]
    values = [row[value_key] for row in rows]
    hover_labels = [format_german_datetime(row["timestamp"]) for row in rows]

    figure = go.Figure(
        go.Scatter(
            x=chart_times,
            y=values,
            mode="lines",
            name=trace_name,
            customdata=hover_labels,
            hovertemplate=(
                "%{customdata}<br>"
                + trace_name
                + ": %{y:.2f}<extra></extra>"
            ),
        )
    )

    for series in additional_series or []:
        series_rows = series.get("hourly", [])
        series_times = [
            parse_timestamp(row["timestamp"]).replace(tzinfo=None)
            for row in series_rows
        ]
        series_hover = [
            format_german_datetime(row["timestamp"]) for row in series_rows
        ]
        series_name = str(series.get("name", "Einzelanlage"))
        figure.add_trace(
            go.Scatter(
                x=series_times,
                y=[row[value_key] for row in series_rows],
                mode="lines",
                name=series_name,
                line={"dash": "dot"},
                customdata=series_hover,
                hovertemplate=(
                    "%{customdata}<br>"
                    + series_name
                    + ": %{y:.2f}<extra></extra>"
                ),
            )
        )

    apply_time_axis(figure, chart_times, tick_interval_hours=3)

    figure.update_layout(
        height=430,
        margin={"l": 20, "r": 20, "t": 20, "b": 105},
        hovermode="x unified",
        showlegend=bool(additional_series),
        yaxis_title=y_axis_title,
        font={"size": 13},
        legend={"font": {"size": 13}},
        hoverlabel={"font_size": 14},
    )
    figure.update_yaxes(
        gridcolor="rgba(120, 120, 120, 0.16)",
        gridwidth=0.6,
        title={"font": {"size": 16}},
        tickfont={"size": 13},
        zerolinecolor="rgba(120, 120, 120, 0.25)",
    )
    return figure


def create_hourly_energy_chart(
    rows: list[dict[str, Any]],
    *,
    trace_name: str = "Ertrag pro Stunde",
    component_series: list[dict[str, Any]] | None = None,
    stack_components: bool = False,
    tick_interval_hours: int | None = None,
    compact: bool = False,
    view_days: int | None = None,
) -> go.Figure:
    """Create the main PV chart as interval energy bars."""
    components = sort_component_series_by_energy(component_series or [])
    if stack_components and components:
        energy_rows = sum_hourly_energy_series(components)
    else:
        energy_rows = forecast_rows_to_hourly_energy(rows)

    chart_times = [row["chart_timestamp"] for row in energy_rows]
    total_by_time = {
        row["chart_timestamp"]: row["interval_energy_kwh"] for row in energy_rows
    }
    figure = go.Figure()

    if stack_components and components:
        for component in components:
            component_name = str(component.get("name", "Einzelanlage"))
            component_rows = forecast_rows_to_hourly_energy(component.get("hourly", []))
            figure.add_trace(
                go.Bar(
                    x=[row["chart_timestamp"] for row in component_rows],
                    y=[row["interval_energy_kwh"] for row in component_rows],
                    name=component_name,
                    customdata=[
                        [
                            format_german_datetime(row["timestamp"]),
                            total_by_time.get(row["chart_timestamp"], 0.0),
                        ]
                        for row in component_rows
                    ],
                    hovertemplate=(
                        "%{customdata[0]}<br>"
                        + component_name
                        + ": %{y:.2f} kWh<br>"
                        "Gesamt: %{customdata[1]:.2f} kWh<extra></extra>"
                    ),
                    marker_line_width=0,
                    opacity=0.86,
                )
            )
    else:
        figure.add_trace(
            go.Bar(
                x=chart_times,
                y=[row["interval_energy_kwh"] for row in energy_rows],
                name=trace_name,
                customdata=[
                    format_german_datetime(row["timestamp"]) for row in energy_rows
                ],
                hovertemplate=(
                    "%{customdata}<br>"
                    "Ertrag: %{y:.2f} kWh<extra></extra>"
                ),
                marker_color="#f59e0b",
                marker_line_width=0,
                opacity=0.9,
            )
        )

    apply_time_axis(
        figure,
        chart_times,
        tick_interval_hours=tick_interval_hours,
        compact=compact,
        view_days=view_days,
    )
    figure.update_layout(
        title={
            "text": "",
        },
        barmode="stack",
        bargap=0.12,
        height=420 if compact else 480,
        margin=(
            {"l": 26, "r": 12, "t": 30, "b": 58}
            if compact
            else {"l": 44, "r": 24, "t": 18, "b": 116}
        ),
        hovermode="x unified",
        showlegend=bool(stack_components and components),
        yaxis_title="" if compact else "Ertrag [kWh]",
        font={"size": 13 if compact else 15},
        legend={
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.02,
            "xanchor": "right",
            "x": 1,
            "font": {"size": 12 if compact else 14},
            "bgcolor": "rgba(255,255,255,0.65)",
        },
        hoverlabel={"font_size": 13 if compact else 14},
        plot_bgcolor="white",
    )
    figure.update_yaxes(
        gridcolor="rgba(120, 120, 120, 0.16)",
        gridwidth=0.6,
        title={"font": {"size": 1 if compact else 18}},
        tickfont={"size": 12 if compact else 15},
        ticklabelposition="outside",
        zerolinecolor="rgba(120, 120, 120, 0.25)",
        rangemode="tozero",
    )
    if compact:
        figure.add_annotation(
            x=0,
            y=1.08,
            xref="paper",
            yref="paper",
            text="Ertrag [kWh]",
            showarrow=False,
            xanchor="left",
            yanchor="bottom",
            font={"size": 12, "color": "#4b5563"},
        )
    return figure
