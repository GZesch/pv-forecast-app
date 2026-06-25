from typing import Any


def forecast_warning(payload: dict[str, Any]) -> str | None:
    """Return a non-empty, user-facing warning from a forecast response."""
    warning = payload.get("warning")
    if not isinstance(warning, str):
        return None
    normalized = warning.strip()
    return normalized or None
