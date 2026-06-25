from typing import Any


WEATHER_VARIABLES = {
    "direct_radiation": ("Direktstrahlung", "Strahlung [W/m²]"),
    "diffuse_radiation": ("Diffusstrahlung", "Strahlung [W/m²]"),
    "shortwave_radiation": ("Globalstrahlung", "Strahlung [W/m²]"),
    "direct_normal_irradiance": ("DNI", "Strahlung [W/m²]"),
    "cloud_cover": ("Bewölkung", "Bewölkung [%]"),
    "temperature_2m": ("Temperatur", "Temperatur [°C]"),
    "wind_speed_10m": ("Wind 10 m", "Windgeschwindigkeit [km/h]"),
}


def available_weather_variables(
    weather_rows: list[dict[str, Any]],
) -> dict[str, tuple[str, str]]:
    available_keys = {
        key for row in weather_rows for key, value in row.items() if value is not None
    }
    return {
        key: metadata
        for key, metadata in WEATHER_VARIABLES.items()
        if key in available_keys
    }
