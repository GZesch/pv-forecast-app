from decimal import Decimal, ROUND_HALF_UP
from typing import Any


def _format_coordinate(value: Any) -> str:
    return str(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def format_installation_location(installation: dict[str, Any]) -> str:
    """Return a readable location without exposing an empty placeholder."""
    for key in ("location_label", "location"):
        value = installation.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    latitude = installation.get("latitude")
    longitude = installation.get("longitude")
    if latitude is not None and longitude is not None:
        return f"{_format_coordinate(latitude)}, {_format_coordinate(longitude)}"

    return "Unbekannter Ort"


def location_columns(
    installation: dict[str, Any], *, expert_mode: bool
) -> dict[str, str]:
    """Return location columns permitted in the selected UI mode."""
    columns = {"Ort": format_installation_location(installation)}
    if expert_mode:
        latitude = installation.get("latitude")
        longitude = installation.get("longitude")
        columns["Breitengrad"] = (
            f"{float(latitude):.5f}" if latitude is not None else "—"
        )
        columns["Längengrad"] = (
            f"{float(longitude):.5f}" if longitude is not None else "—"
        )
    return columns
