import httpx

from app.config import settings
from app.models import TransformedInputs, WeatherQuery
from app.providers.base import WeatherProvider


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
