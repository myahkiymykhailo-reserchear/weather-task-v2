import httpx

from app.config import settings
from app.models import TransformedInputs, WeatherQuery
from app.providers.base import WeatherProvider


class WttrProvider(WeatherProvider):
    """robertoduessmann/weather-api — hosted at goweather.xyz, takes a city name."""

    name = "wttr"

    async def fetch(
        self,
        client: httpx.AsyncClient,
        query: WeatherQuery,
        transformed: TransformedInputs,
    ):
        url = f"{settings.wttr_url}/{query.city}"
        resp = await client.get(url, timeout=settings.request_timeout_seconds)
        resp.raise_for_status()
        return resp.json()
