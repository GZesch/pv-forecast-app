from frontend.installation_display import (
    format_installation_location,
    location_columns,
)


def test_location_label_is_used_first() -> None:
    assert (
        format_installation_location(
            {
                "location_label": "München, Deutschland",
                "location": "Marienplatz 1",
                "latitude": 48.137,
                "longitude": 11.575,
            }
        )
        == "München, Deutschland"
    )


def test_original_location_is_used_when_label_is_empty() -> None:
    assert (
        format_installation_location(
            {
                "location_label": "",
                "location": "München",
                "latitude": 48.137,
                "longitude": 11.575,
            }
        )
        == "München"
    )


def test_coordinates_are_used_as_last_location_fallback() -> None:
    assert (
        format_installation_location(
            {"location_label": None, "latitude": 48.137, "longitude": 11.575}
        )
        == "48.14, 11.58"
    )


def test_standard_mode_contains_location_but_no_coordinates() -> None:
    columns = location_columns(
        {
            "location_label": "Stockholm",
            "latitude": 59.3293,
            "longitude": 18.0686,
        },
        expert_mode=False,
    )

    assert columns == {"Ort": "Stockholm"}
    assert "Breitengrad" not in columns
    assert "Längengrad" not in columns


def test_expert_mode_contains_location_and_coordinates() -> None:
    columns = location_columns(
        {
            "location_label": "Stockholm",
            "latitude": 59.3293,
            "longitude": 18.0686,
        },
        expert_mode=True,
    )

    assert columns == {
        "Ort": "Stockholm",
        "Breitengrad": "59.32930",
        "Längengrad": "18.06860",
    }
