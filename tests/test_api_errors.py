import httpx

from frontend.api_errors import (
    WEATHER_BUSY_MESSAGE,
    WEATHER_UNAVAILABLE_MESSAGE,
    response_error_message,
)


def test_frontend_displays_friendly_backend_503_message() -> None:
    response = httpx.Response(
        503,
        json={"detail": WEATHER_BUSY_MESSAGE},
    )

    assert response_error_message(response, "Fallback") == WEATHER_BUSY_MESSAGE


def test_frontend_hides_raw_http_429_details() -> None:
    response = httpx.Response(
        503,
        json={"detail": "Open-Meteo HTTP 429 Too Many Requests"},
    )

    message = response_error_message(response, "Fallback")

    assert message == WEATHER_BUSY_MESSAGE
    assert "429" not in message


def test_frontend_hides_upstream_technical_details() -> None:
    response = httpx.Response(
        502,
        json={"detail": "Open-Meteo JSON parsing error at cloud_cover"},
    )

    message = response_error_message(response, "Forecast fehlgeschlagen")

    assert message == WEATHER_UNAVAILABLE_MESSAGE
    assert "JSON" not in message
    assert "HTTP" not in message
