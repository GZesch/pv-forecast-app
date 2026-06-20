import httpx

from frontend.api_errors import WEATHER_BUSY_MESSAGE, response_error_message


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
    assert "HTTP" not in message
