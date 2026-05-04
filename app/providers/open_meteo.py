from typing import Any, Optional

import httpx

from app.config import settings
from app.models import TransformedInputs, WeatherQuery, WeatherSnapshot
from app.providers.base import WeatherProvider

# Open-Meteo WMO weather codes — minimal grouping for human-readable text.
# https://open-meteo.com/en/docs#api_form (Weather code section)
_WMO_GROUPS = {
    0: "Clear",
    1: "Mostly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Fog",
    51: "Drizzle",
    53: "Drizzle",
    55: "Drizzle",
    61: "Rain",
    63: "Rain",
    65: "Heavy rain",
    71: "Snow",
    73: "Snow",
    75: "Heavy snow",
    80: "Rain showers",
    81: "Rain showers",
    82: "Heavy rain showers",
    95: "Thunderstorm",
    96: "Thunderstorm with hail",
    99: "Thunderstorm with hail",
}


class OpenMeteoProvider(WeatherProvider):
    name = "open_meteo"

    async def fetch(
        self,
        client: httpx.AsyncClient,
        query: WeatherQuery,
        transformed: TransformedInputs,
    ):
        target = transformed.date.isoformat()
        params = {
            "latitude": transformed.lat,
            "longitude": transformed.lon,
            "current": "temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m",
            "daily": "temperature_2m_max,temperature_2m_min,weather_code,precipitation_sum,wind_speed_10m_max",
            # Always Celsius internally — display-time conversion happens later.
            "temperature_unit": "celsius",
            "wind_speed_unit": "kmh",
            "timezone": "auto",
            "start_date": target,
            "end_date": target,
        }
        resp = await client.get(
            settings.open_meteo_forecast_url,
            params=params,
            timeout=settings.request_timeout_seconds,
        )
        resp.raise_for_status()
        return resp.json()

    def normalize(self, raw: Any, transformed: TransformedInputs) -> WeatherSnapshot:
        raw = raw or {}
        cur = raw.get("current") or {}
        daily = raw.get("daily") or {}
        weather_code = cur.get("weather_code")
        if weather_code is None:
            weather_code = _first_or_none(daily.get("weather_code"))

        temp_c = _as_float(cur.get("temperature_2m"))
        if temp_c is None:
            tmax = _as_float(_first_or_none(daily.get("temperature_2m_max")))
            tmin = _as_float(_first_or_none(daily.get("temperature_2m_min")))
            if tmax is not None and tmin is not None:
                temp_c = (tmax + tmin) / 2.0

        return WeatherSnapshot(
            temperature_c=temp_c,
            humidity_pct=_as_float(cur.get("relative_humidity_2m")),
            wind_kph=_as_float(cur.get("wind_speed_10m"))
            or _as_float(_first_or_none(daily.get("wind_speed_10m_max"))),
            precipitation_mm=_as_float(_first_or_none(daily.get("precipitation_sum"))),
            conditions=_WMO_GROUPS.get(weather_code) if isinstance(weather_code, int) else None,
            is_forecast=True,
            forecast_for_date=transformed.date,
            source_quality="live",
        )

    def fallback(self, transformed: TransformedInputs) -> WeatherSnapshot:
        return WeatherSnapshot(
            temperature_c=15.0,
            humidity_pct=65.0,
            wind_kph=12.0,
            precipitation_mm=0.0,
            cloud_cover_pct=50.0,
            conditions="Partly cloudy (example)",
            is_forecast=True,
            forecast_for_date=transformed.date,
            source_quality="fallback",
            notes="Open-Meteo unavailable; placeholder example data.",
        )


def _as_float(v) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _first_or_none(seq):
    if not seq:
        return None
    return seq[0] if isinstance(seq, (list, tuple)) else None
