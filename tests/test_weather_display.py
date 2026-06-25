from frontend.weather_display import available_weather_variables


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
