import asyncio
import os
import time
from dataclasses import dataclass

import httpx


class LocationNotFoundError(Exception):
    """Raised when Nominatim has no result for a location query."""


class GeocodingServiceError(Exception):
    """Raised when the geocoding provider cannot process a request."""


@dataclass(frozen=True)
class Coordinates:
    latitude: float
    longitude: float


NOMINATIM_URL = os.getenv(
    "NOMINATIM_URL", "https://nominatim.openstreetmap.org/search"
)
NOMINATIM_USER_AGENT = os.getenv(
    "NOMINATIM_USER_AGENT", "pv-forecast-app/0.1"
)

_request_lock = asyncio.Lock()
_last_request_at = 0.0


async def geocode_location(location: str) -> Coordinates:
    """Resolve a free-text location to coordinates using Nominatim."""
    global _last_request_at

    query = location.strip()
    if not query:
        raise LocationNotFoundError("Es wurde kein Standort angegeben.")

    async with _request_lock:
        elapsed = time.monotonic() - _last_request_at
        if elapsed < 1.0:
            await asyncio.sleep(1.0 - elapsed)

        try:
            async with httpx.AsyncClient(
                headers={"User-Agent": NOMINATIM_USER_AGENT}, timeout=10.0
            ) as client:
                response = await client.get(
                    NOMINATIM_URL,
                    params={
                        "q": query,
                        "format": "jsonv2",
                        "limit": 1,
                    },
                )
                response.raise_for_status()
                results = response.json()
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            raise GeocodingServiceError(
                "Der Geocoding-Dienst ist derzeit nicht erreichbar."
            ) from exc
        finally:
            _last_request_at = time.monotonic()

    if not isinstance(results, list) or not results:
        raise LocationNotFoundError(
            f"Für den Standort „{query}“ wurde kein Ort gefunden."
        )

    try:
        return Coordinates(
            latitude=float(results[0]["lat"]),
            longitude=float(results[0]["lon"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise GeocodingServiceError(
            "Der Geocoding-Dienst hat ungültige Koordinaten geliefert."
        ) from exc

