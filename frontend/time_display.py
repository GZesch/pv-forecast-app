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


def format_german_datetime(value: str | datetime) -> str:
    parsed = parse_timestamp(value)
    return f"{GERMAN_WEEKDAYS[parsed.weekday()]}, {parsed:%d.%m.%Y %H:%M}"


def today_in_display_timezone() -> date:
    return datetime.now(DISPLAY_TIMEZONE).date()


def summarize_daily_power(
    rows: list[dict[str, Any]], start_date: date | None = None
) -> list[dict[str, Any]]:
    """Build energy and peak metrics for three local calendar days."""
    grouped: dict[date, list[tuple[datetime, float]]] = defaultdict(list)
    for row in rows:
        timestamp = parse_timestamp(row["timestamp"])
        grouped[timestamp.date()].append(
            (timestamp, max(float(row["predicted_power_kw"]), 0.0))
        )

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
                "energy_kwh": round(sum(power for _, power in points), 3),
                "peak_power_kw": peak_power,
                "peak_timestamp": peak_timestamp,
            }
        )

    return summaries


def create_hourly_chart(
    rows: list[dict[str, Any]],
    *,
    value_key: str,
    trace_name: str,
    y_axis_title: str,
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

    tick_values = [
        chart_time
        for chart_time in chart_times
        if chart_time.minute == 0 and chart_time.hour % 3 == 0
    ]
    figure.update_xaxes(
        tickmode="array",
        tickvals=tick_values,
        ticktext=[value.strftime("%H:%M") for value in tick_values],
        tickangle=0,
        ticks="outside",
        showgrid=True,
        title=None,
    )

    times_by_day: dict[date, list[datetime]] = defaultdict(list)
    for chart_time in chart_times:
        times_by_day[chart_time.date()].append(chart_time)

    for day, day_times in sorted(times_by_day.items()):
        first, last = min(day_times), max(day_times)
        center = first + (last - first) / 2
        figure.add_annotation(
            x=center,
            y=-0.2,
            xref="x",
            yref="paper",
            text=format_german_date(day),
            showarrow=False,
            xanchor="center",
            yanchor="top",
        )

    figure.update_layout(
        height=430,
        margin={"l": 20, "r": 20, "t": 20, "b": 105},
        hovermode="x unified",
        showlegend=False,
        yaxis_title=y_axis_title,
    )
    return figure
