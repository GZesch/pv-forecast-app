from datetime import datetime, timedelta, timezone

from frontend.weather_display import (
    available_weather_variables,
    create_weather_chart,
    default_weather_source_installation_id,
    default_weather_variable_selection,
    installations_share_same_location,
    weather_axis_for_variable,
)


def test_available_weather_variables_only_returns_present_values() -> None:
    variables = available_weather_variables(
        [
            {
                "timestamp": "2026-06-26T08:00:00Z",
                "direct_radiation": 500.0,
                "cloud_cover": 20.0,
                "temperature_2m": None,
            }
        ]
    )

    assert variables["direct_radiation"][0] == "Direktstrahlung"
    assert variables["cloud_cover"][1] == "Bewölkung [%]"
    assert "temperature_2m" not in variables


def test_weather_variables_are_categorized_by_axis() -> None:
    assert weather_axis_for_variable("direct_radiation") == "radiation"
    assert weather_axis_for_variable("diffuse_radiation") == "radiation"
    assert weather_axis_for_variable("cloud_cover") == "weather"
    assert weather_axis_for_variable("temperature_2m") == "weather"
    assert weather_axis_for_variable("wind_speed_10m") == "weather"


def test_default_weather_selection_prefers_radiation_and_cloud_cover() -> None:
    variables = available_weather_variables(
        [
            {
                "direct_radiation": 500.0,
                "diffuse_radiation": 100.0,
                "cloud_cover": 20.0,
                "temperature_2m": 18.0,
            }
        ]
    )

    assert default_weather_variable_selection(variables) == [
        "direct_radiation",
        "diffuse_radiation",
        "cloud_cover",
    ]


def test_weather_chart_uses_two_axes_for_radiation_and_weather_values() -> None:
    rows = [
        {
            "timestamp": "2026-06-26T08:00:00Z",
            "direct_radiation": 500.0,
            "cloud_cover": 20.0,
        },
        {
            "timestamp": "2026-06-26T09:00:00Z",
            "direct_radiation": 600.0,
            "cloud_cover": 25.0,
        },
    ]

    figure = create_weather_chart(
        rows,
        selected_variables=["direct_radiation", "cloud_cover"],
        view_days=1,
    )

    assert [trace.name for trace in figure.data] == ["Direktstrahlung", "Bewölkung"]
    assert figure.data[0].yaxis == "y"
    assert figure.data[1].yaxis == "y2"
    assert figure.layout.yaxis.title.text == "Strahlung [W/m²]"
    assert figure.layout.yaxis2.visible is True


def test_weather_chart_uses_weather_axis_as_primary_when_no_radiation_selected() -> None:
    rows = [
        {"timestamp": "2026-06-26T08:00:00Z", "temperature_2m": 18.0},
    ]

    figure = create_weather_chart(
        rows,
        selected_variables=["temperature_2m"],
        view_days=1,
    )

    assert figure.data[0].yaxis == "y"
    assert figure.layout.yaxis.title.text == "Temperatur [°C]"
    assert figure.layout.yaxis2.visible is False


def test_weather_chart_tick_density_and_compact_labels_follow_view_days() -> None:
    rows = [
        {
            "timestamp": f"2026-06-{26 + day:02d}T{hour:02d}:00:00Z",
            "direct_radiation": 100.0,
        }
        for day in range(3)
        for hour in range(24)
    ]

    desktop = create_weather_chart(
        rows,
        selected_variables=["direct_radiation"],
        view_days=1,
    )
    compact = create_weather_chart(
        rows,
        selected_variables=["direct_radiation"],
        view_days=1,
        compact=True,
    )

    assert len(desktop.layout.xaxis.ticktext) > len(compact.layout.xaxis.ticktext)
    assert "01:00" in list(desktop.layout.xaxis.ticktext)
    assert "01:00" not in list(compact.layout.xaxis.ticktext)


def test_weather_chart_reuses_compact_seven_day_noon_labels_and_date_annotations() -> None:
    first_utc = datetime(2026, 6, 26, 0, tzinfo=timezone.utc)
    rows = [
        {
            "timestamp": (first_utc + timedelta(hours=hour)).isoformat(),
            "direct_radiation": 100.0,
        }
        for hour in range(7 * 24)
    ]

    figure = create_weather_chart(
        rows,
        selected_variables=["direct_radiation"],
        view_days=7,
        compact=True,
    )

    assert set(figure.layout.xaxis.ticktext) == {"12:00"}
    assert len(figure.layout.annotations) >= 7
    assert all(annotation.text.endswith(".") for annotation in figure.layout.annotations)
    assert figure.layout.yaxis.title.text == ""
    assert figure.layout.yaxis2.title.text == ""
    assert figure.layout.yaxis.ticklabelposition == "inside"
    assert figure.layout.yaxis2.ticklabelposition == "inside"
    assert figure.layout.margin.l < 12


def test_default_weather_source_prefers_largest_component_energy() -> None:
    installations = [
        {"id": "east-id", "name": "Ost"},
        {"id": "west-id", "name": "West"},
    ]
    components = [
        {"name": "Ost", "hourly": [{"predicted_power_kw": 1.0}]},
        {"name": "West", "hourly": [{"predicted_power_kw": 3.0}]},
    ]

    assert default_weather_source_installation_id(installations, components) == "west-id"


def test_installations_share_same_location_by_rounded_coordinates() -> None:
    assert installations_share_same_location(
        [
            {"latitude": 52.52001, "longitude": 13.40501},
            {"latitude": 52.52002, "longitude": 13.40502},
        ]
    )
    assert not installations_share_same_location(
        [
            {"latitude": 52.52, "longitude": 13.405},
            {"latitude": 48.137, "longitude": 11.575},
        ]
    )
