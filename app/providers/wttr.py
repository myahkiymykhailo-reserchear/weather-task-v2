from typing import Any, Optional
from urllib.parse import quote

import httpx

from app.config import settings
from app.models import TransformedInputs, WeatherQuery, WeatherSnapshot
from app.providers.base import WeatherProvider


class WttrProvider(WeatherProvider):
    """wttr.in (chubin/wttr.in) JSON API.

    The originally-listed robertoduessmann/weather-api at goweather.xyz is
    offline (404 for every path as of 2026-05; underlying Heroku app gone).
    wttr.in is the well-known alternative — accepts city names as the path
    and returns rich JSON via `?format=j1`:

        GET https://wttr.in/Berlin?format=j1
    """

    name = "wttr"

    async def fetch(
        self,
        client: httpx.AsyncClient,
        query: WeatherQuery,
        transformed: TransformedInputs,
    ):
        url = f"{settings.wttr_url}/{quote(query.city, safe='')}"
        resp = await client.get(
            url,
            params={"format": "j1"},
            timeout=settings.request_timeout_seconds,
        )
        resp.raise_for_status()
        return resp.json()

    def normalize(self, raw: Any, transformed: TransformedInputs) -> WeatherSnapshot:
        raw = raw or {}
        cur = (raw.get("current_condition") or [{}])[0] or {}
        weather_desc = ((cur.get("weatherDesc") or [{}])[0] or {}).get("value")

        return WeatherSnapshot(
            temperature_c=_as_float(cur.get("temp_C")),
            feels_like_c=_as_float(cur.get("FeelsLikeC")),
            humidity_pct=_as_float(cur.get("humidity")),
            wind_kph=_as_float(cur.get("windspeedKmph")),
            cloud_cover_pct=_as_float(cur.get("cloudcover")),
            precipitation_mm=_as_float(cur.get("precipMM")),
            conditions=weather_desc,
            is_forecast=False,
            forecast_for_date=transformed.date,
            source_quality="live",
        )

    def fallback(self, transformed: TransformedInputs) -> WeatherSnapshot:
        return WeatherSnapshot(
            temperature_c=14.0,
            wind_kph=8.0,
            humidity_pct=60.0,
            conditions="Sunny (example)",
            is_forecast=False,
            forecast_for_date=transformed.date,
            source_quality="fallback",
            notes="wttr.in unavailable; placeholder example data.",
        )


def _as_float(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
