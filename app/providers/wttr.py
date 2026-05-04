import re
from typing import Any, Optional
from urllib.parse import quote

import httpx

from app.config import settings
from app.models import TransformedInputs, WeatherQuery, WeatherSnapshot
from app.providers.base import WeatherProvider


_NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")


class WttrProvider(WeatherProvider):
    """robertoduessmann/weather-api — hosted at goweather.xyz, takes a city name."""

    name = "wttr"

    async def fetch(
        self,
        client: httpx.AsyncClient,
        query: WeatherQuery,
        transformed: TransformedInputs,
    ):
        url = f"{settings.wttr_url}/{quote(query.city, safe='')}"
        resp = await client.get(url, timeout=settings.request_timeout_seconds)
        resp.raise_for_status()
        return resp.json()

    def normalize(self, raw: Any, transformed: TransformedInputs) -> WeatherSnapshot:
        raw = raw or {}
        # goweather.xyz always reports Celsius and km/h (no unit options).
        return WeatherSnapshot(
            temperature_c=_extract_number(raw.get("temperature")),
            wind_kph=_extract_number(raw.get("wind")),
            conditions=raw.get("description") or None,
            is_forecast=False,
            forecast_for_date=transformed.date,
            source_quality="live",
        )

    def fallback(self, transformed: TransformedInputs) -> WeatherSnapshot:
        return WeatherSnapshot(
            temperature_c=14.0,
            wind_kph=8.0,
            conditions="Sunny (example)",
            is_forecast=False,
            forecast_for_date=transformed.date,
            source_quality="fallback",
            notes="goweather.xyz unavailable; placeholder example data.",
        )


def _extract_number(s: Any) -> Optional[float]:
    if not isinstance(s, str):
        return None
    m = _NUM_RE.search(s)
    return float(m.group()) if m else None
