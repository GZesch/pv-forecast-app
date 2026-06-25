from typing import Any

import plotly.graph_objects as go

try:
    from .time_display import (
        apply_time_axis,
        filter_forecast_rows_by_days,
        format_german_datetime,
        parse_timestamp,
        tick_interval_for_view_days,
    )
except ImportError:
    from time_display import (
        apply_time_axis,
        filter_forecast_rows_by_days,
        format_german_datetime,
        parse_timestamp,
        tick_interval_for_view_days,
    )


WEATHER_VARIABLES = {
    "direct_radiation": ("Direktstrahlung", "Strahlung [W/m²]", "radiation", "W/m²"),
    "diffuse_radiation": ("Diffusstrahlung", "Strahlung [W/m²]", "radiation", "W/m²"),
    "shortwave_radiation": ("Globalstrahlung", "Strahlung [W/m²]", "radiation", "W/m²"),
    "direct_normal_irradiance": ("DNI", "Strahlung [W/m²]", "radiation", "W/m²"),
    "cloud_cover": ("Bewölkung", "Bewölkung [%]", "weather", "%"),
    "temperature_2m": ("Temperatur", "Temperatur [°C]", "weather", "°C"),
    "wind_speed_10m": ("Wind 10 m", "Windgeschwindigkeit [km/h]", "weather", "km/h"),
}
DEFAULT_WEATHER_KEYS = ("direct_radiation", "diffuse_radiation", "cloud_cover")


def available_weather_variables(
    weather_rows: list[dict[str, Any]],
) -> dict[str, tuple[str, str, str, str]]:
    available_keys = {
        key for row in weather_rows for key, value in row.items() if value is not None
    }
    return {
        key: metadata
        for key, metadata in WEATHER_VARIABLES.items()
        if key in available_keys
    }


def default_weather_variable_selection(
    available_variables: dict[str, tuple[str, str, str, str]]
) -> list[str]:
    defaults = [key for key in DEFAULT_WEATHER_KEYS if key in available_variables]
    return defaults or list(available_variables)[:1]


def weather_axis_for_variable(key: str) -> str:
    return WEATHER_VARIABLES[key][2]


def default_weather_source_installation_id(
    plant_installations: list[dict[str, Any]],
    component_series: list[dict[str, Any]],
) -> str | None:
    if not plant_installations:
        return None
    energy_by_name: dict[str, float] = {}
    for component in component_series:
        name = str(component.get("name", ""))
        energy_by_name[name] = sum(
            max(float(row.get("predicted_power_kw", 0.0)), 0.0)
            for row in component.get("hourly", [])
        )
    return max(
        plant_installations,
        key=lambda installation: energy_by_name.get(str(installation.get("name")), 0.0),
    )["id"]


def installations_share_same_location(
    installations: list[dict[str, Any]], *, decimals: int = 4
) -> bool:
    coordinates = {
        (
            round(float(installation["latitude"]), decimals),
            round(float(installation["longitude"]), decimals),
        )
        for installation in installations
        if installation.get("latitude") is not None
        and installation.get("longitude") is not None
    }
    return bool(coordinates) and len(coordinates) == 1


def create_weather_chart(
    weather_rows: list[dict[str, Any]],
    *,
    selected_variables: list[str],
    view_days: int,
    compact: bool = False,
) -> go.Figure:
    rows = filter_forecast_rows_by_days(weather_rows, view_days)
    chart_times = [
        parse_timestamp(row["timestamp"]).replace(tzinfo=None) for row in rows
    ]
    figure = go.Figure()
    has_radiation = any(
        weather_axis_for_variable(key) == "radiation"
        for key in selected_variables
        if key in WEATHER_VARIABLES
    )
    has_weather = any(
        weather_axis_for_variable(key) == "weather"
        for key in selected_variables
        if key in WEATHER_VARIABLES
    )

    for key in selected_variables:
        if key not in WEATHER_VARIABLES:
            continue
        label, _, axis_group, unit = WEATHER_VARIABLES[key]
        yaxis = "y" if axis_group == "radiation" or not has_radiation else "y2"
        figure.add_trace(
            go.Scatter(
                x=chart_times,
                y=[row.get(key) for row in rows],
                mode="lines",
                name=label,
                yaxis=yaxis,
                customdata=[format_german_datetime(row["timestamp"]) for row in rows],
                hovertemplate=(
                    "%{customdata}<br>"
                    + label
                    + ": %{y:.2f} "
                    + unit
                    + "<extra></extra>"
                ),
            )
        )

    primary_title = (
        "Strahlung [W/m²]"
        if has_radiation
        else WEATHER_VARIABLES[selected_variables[0]][1]
        if selected_variables
        else ""
    )
    apply_time_axis(
        figure,
        chart_times,
        tick_interval_hours=tick_interval_for_view_days(view_days, compact=compact),
        compact=compact,
        view_days=view_days,
    )
    figure.update_layout(
        title={"text": ""},
        height=400 if compact else 450,
        margin=(
            {"l": 26, "r": 30, "t": 36, "b": 58}
            if compact
            else {"l": 44, "r": 56, "t": 18, "b": 96}
        ),
        hovermode="x unified",
        yaxis={
            "title": {
                "text": "" if compact else primary_title,
                "font": {"size": 1 if compact else 18},
            },
            "tickfont": {"size": 11 if compact else 15},
            "ticklabelposition": "outside",
            "gridcolor": "rgba(120, 120, 120, 0.16)",
            "gridwidth": 0.6,
            "rangemode": "tozero",
        },
        yaxis2={
            "title": {
                "text": "" if compact else "Wetterwerte",
                "font": {"size": 1 if compact else 18},
            },
            "tickfont": {"size": 11 if compact else 15},
            "ticklabelposition": "outside",
            "overlaying": "y",
            "side": "right",
            "showgrid": False,
            "visible": has_weather and has_radiation,
        },
        legend={
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.02,
            "xanchor": "right",
            "x": 1,
            "font": {"size": 12 if compact else 14},
        },
        hoverlabel={"font_size": 13 if compact else 14},
        plot_bgcolor="white",
        font={"size": 13 if compact else 15},
    )
    if compact:
        figure.add_annotation(
            x=0,
            y=1.08,
            xref="paper",
            yref="paper",
            text=primary_title,
            showarrow=False,
            xanchor="left",
            yanchor="bottom",
            font={"size": 12, "color": "#4b5563"},
        )
        if has_weather and has_radiation:
            figure.add_annotation(
                x=1,
                y=1.08,
                xref="paper",
                yref="paper",
                text="Wetterwerte",
                showarrow=False,
                xanchor="right",
                yanchor="bottom",
                font={"size": 12, "color": "#4b5563"},
            )
    return figure
