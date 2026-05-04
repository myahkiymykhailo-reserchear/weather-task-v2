from typing import Any, Optional

import httpx

from app.config import settings
from app.models import TransformedInputs, WeatherQuery, WeatherSnapshot
from app.providers.base import WeatherProvider


# 7Timer's `civil` product reports cloudcover and wind speed on integer scales:
#   cloudcover: 1=0-6%, 2=6-19%, 3=19-31%, 4=31-44%, 5=44-56%, 6=56-69%, 7=69-81%, 8=81-94%, 9=94-100%
#   wind10m.speed: Beaufort-ish band index 1..8; map midpoints to km/h.
# Source: https://www.7timer.info/doc.php?lang=en#variables
_CLOUDCOVER_PCT_MIDPOINTS = {1: 3, 2: 12, 3: 25, 4: 37, 5: 50, 6: 62, 7: 75, 8: 87, 9: 97}
_WIND_BAND_KPH = {1: 1, 2: 6, 3: 14, 4: 26, 5: 39, 6: 55, 7: 72, 8: 90}

_WEATHER_TEXT = {
    "clearday": "Clear",
    "clearnight": "Clear",
    "pcloudyday": "Partly cloudy",
    "pcloudynight": "Partly cloudy",
    "mcloudyday": "Mostly cloudy",
    "mcloudynight": "Mostly cloudy",
    "cloudyday": "Cloudy",
    "cloudynight": "Cloudy",
    "humidday": "Humid",
    "humidnight": "Humid",
    "lightrainday": "Light rain",
    "lightrainnight": "Light rain",
    "oshowerday": "Showers",
    "oshowernight": "Showers",
    "ishowerday": "Showers",
    "ishowernight": "Showers",
    "lightsnowday": "Light snow",
    "lightsnownight": "Light snow",
    "rainday": "Rain",
    "rainnight": "Rain",
    "snowday": "Snow",
    "snownight": "Snow",
    "rainsnowday": "Rain and snow",
    "rainsnownight": "Rain and snow",
    "tsday": "Thunderstorm",
    "tsnight": "Thunderstorm",
    "tsrainday": "Thunderstorm with rain",
    "tsrainnight": "Thunderstorm with rain",
}


class SevenTimerProvider(WeatherProvider):
    name = "seven_timer"

    async def fetch(
        self,
        client: httpx.AsyncClient,
        query: WeatherQuery,
        transformed: TransformedInputs,
    ):
        params = {
            "lon": round(transformed.lon, 2),
            "lat": round(transformed.lat, 2),
            "product": "civil",
            "output": "json",
        }
        resp = await client.get(
            settings.seven_timer_url,
            params=params,
            timeout=settings.request_timeout_seconds,
        )
        resp.raise_for_status()
        return resp.json()

    def normalize(self, raw: Any, transformed: TransformedInputs) -> WeatherSnapshot:
        raw = raw or {}
        series = raw.get("dataseries") or []
        if not series:
            return WeatherSnapshot(
                is_forecast=True,
                forecast_for_date=transformed.date,
                source_quality="live",
                notes="7Timer returned no dataseries.",
            )
        # First entry is closest forecast to "now". Good enough for current snapshot.
        first = series[0] or {}
        cloud = first.get("cloudcover")
        wind10m = first.get("wind10m") or {}
        weather_key = first.get("weather")
        return WeatherSnapshot(
            temperature_c=_as_float(first.get("temp2m")),
            humidity_pct=_parse_pct(first.get("rh2m")),
            wind_kph=_WIND_BAND_KPH.get(wind10m.get("speed")) if isinstance(wind10m.get("speed"), int) else None,
            wind_direction_deg=None,  # 7Timer reports compass letters, not degrees.
            cloud_cover_pct=_CLOUDCOVER_PCT_MIDPOINTS.get(cloud) if isinstance(cloud, int) else None,
            conditions=_WEATHER_TEXT.get(weather_key, weather_key) if isinstance(weather_key, str) else None,
            is_forecast=True,
            forecast_for_date=transformed.date,
            source_quality="live",
        )

    def fallback(self, transformed: TransformedInputs) -> WeatherSnapshot:
        return WeatherSnapshot(
            temperature_c=15.0,
            humidity_pct=60.0,
            wind_kph=14.0,
            cloud_cover_pct=50.0,
            conditions="Mostly cloudy (example)",
            is_forecast=True,
            forecast_for_date=transformed.date,
            source_quality="fallback",
            notes="7Timer unavailable; placeholder example data.",
        )


def _as_float(v) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _parse_pct(v) -> Optional[float]:
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        try:
            return float(v.rstrip("%").strip())
        except ValueError:
            return None
    return None
