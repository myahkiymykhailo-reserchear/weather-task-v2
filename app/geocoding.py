from datetime import date as date_type
from typing import Any, Optional, Tuple

import httpx

from app.config import settings
from app.models import TransformedInputs, WeatherQuery


class GeocodingError(Exception):
    pass


COUNTRY_ALIASES: dict[str, str] = {
    "usa": "us",
    "u.s.": "us",
    "u.s.a.": "us",
    "united states": "us",
    "united states of america": "us",
    "uk": "gb",
    "u.k.": "gb",
    "great britain": "gb",
    "britain": "gb",
    "united kingdom": "gb",
    "deutschland": "de",
    "germany": "de",
    "espana": "es",
    "españa": "es",
    "spain": "es",
}


def normalize_country(country: str) -> Tuple[str, Optional[str]]:
    """Return (raw_lower, iso2_or_None). ISO-2 lookup is best-effort."""
    raw = (country or "").strip().lower()
    if not raw:
        return raw, None
    if len(raw) == 2 and raw.isalpha():
        return raw, raw
    return raw, COUNTRY_ALIASES.get(raw)


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

    chosen, score = _pick_best(results, query)

    if query.country and score == 0:
        raise GeocodingError(
            f"No geocoding result for city='{query.city}' matched country="
            f"'{query.country}'. Top candidate was "
            f"'{chosen.get('name')}, {chosen.get('country')}'. "
            "Try the ISO-3166 alpha-2 code (e.g. 'US', 'DE')."
        )

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


def _pick_best(results: list, query: WeatherQuery) -> Tuple[dict, int]:
    country_raw, country_iso = normalize_country(query.country or "")
    state = (query.state or "").strip().lower()

    def score(r: dict[str, Any]) -> int:
        s = 0
        if country_raw:
            cc = (r.get("country_code") or "").lower()
            cn = (r.get("country") or "").lower()
            if country_iso and cc == country_iso:
                s += 10
            elif cn == country_raw or cc == country_raw:
                s += 9
        if state and (r.get("admin1") or "").lower() == state:
            s += 5
        return s

    best = max(results, key=score)
    return best, score(best)
