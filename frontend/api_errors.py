from typing import Any


WEATHER_BUSY_MESSAGE = (
    "Der Wetterdienst ist kurzzeitig ausgelastet. "
    "Bitte in einigen Minuten erneut versuchen."
)


def response_error_message(response: Any, fallback: str) -> str:
    """Return a user-facing API error without leaking rate-limit internals."""
    try:
        detail = response.json().get("detail")
    except (ValueError, AttributeError):
        detail = None

    if response.status_code == 503:
        normalized_detail = str(detail or "").lower()
        if "429" in normalized_detail or "http" in normalized_detail:
            return WEATHER_BUSY_MESSAGE

    return detail if isinstance(detail, str) and detail else fallback

