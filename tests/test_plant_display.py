from frontend.plant_display import calculate_total_peak_power


def test_calculate_total_peak_power_for_assigned_installations() -> None:
    installations = [
        {"plant_id": "plant-1", "peak_power_kwp": 15.5},
        {"plant_id": "plant-1", "peak_power_kwp": 24.5},
        {"plant_id": "plant-2", "peak_power_kwp": 8.0},
        {"plant_id": None, "peak_power_kwp": 3.0},
    ]

    assert calculate_total_peak_power("plant-1", installations) == 40.0
    assert calculate_total_peak_power("empty-plant", installations) == 0.0
