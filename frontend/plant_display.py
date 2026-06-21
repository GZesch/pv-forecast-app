from typing import Any


def calculate_total_peak_power(
    plant_id: str, installations: list[dict[str, Any]]
) -> float:
    """Sum the nominal power of all installations assigned to a plant."""
    return sum(
        float(installation["peak_power_kwp"])
        for installation in installations
        if str(installation.get("plant_id")) == str(plant_id)
    )
