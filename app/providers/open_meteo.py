import httpx

from app.config import settings
from app.models import TransformedInputs, WeatherQuery
from app.providers.base import WeatherProvider


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
            "temperature_unit": transformed.units,
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
