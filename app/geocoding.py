from datetime import date as date_type
from typing import Any

import httpx

from app.config import settings
from app.models import TransformedInputs, WeatherQuery


class GeocodingError(Exception):
    pass


async def geocode(client: httpx.AsyncClient, query: WeatherQuery) -> TransformedInputs:
    """Resolve city/state/country into lat/lon via Open-Meteo's geocoding API."""
    params = {
        "name": query.city,
        "count": 10,
        "language": "en",
        "format": "json",
    }
    resp = await client.get(
        settings.geocoding_url,
        params=params,
        timeout=settings.request_timeout_seconds,
    )
    resp.raise_for_status()
    payload = resp.json()
    results = payload.get("results") or []
    if not results:
        raise GeocodingError(f"No geocoding results for city='{query.city}'")

    chosen = _pick_best(results, query)

    name_parts = [chosen.get("name"), chosen.get("admin1"), chosen.get("country")]
    resolved_name = ", ".join(p for p in name_parts if p)

    return TransformedInputs(
        lat=float(chosen["latitude"]),
        lon=float(chosen["longitude"]),
        timezone=chosen.get("timezone"),
        resolved_name=resolved_name or None,
        country_code=chosen.get("country_code"),
        date=query.date or date_type.today(),
        units=query.units,
    )


def _pick_best(results: list[dict[str, Any]], query: WeatherQuery) -> dict[str, Any]:
    country = (query.country or "").strip().lower()
    state = (query.state or "").strip().lower()

    def score(r: dict[str, Any]) -> int:
        s = 0
        if country:
            cc = (r.get("country_code") or "").lower()
            cn = (r.get("country") or "").lower()
            if cc == country:
                s += 10
            elif cn == country:
                s += 9
        if state:
            if (r.get("admin1") or "").lower() == state:
                s += 5
        return s

    return max(results, key=score)
