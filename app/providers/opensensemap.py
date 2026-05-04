import httpx

from app.config import settings
from app.models import TransformedInputs, WeatherQuery
from app.providers.base import WeatherProvider


class OpenSenseMapProvider(WeatherProvider):
    """Returns nearby citizen-science sensor boxes and their latest measurements."""

    name = "opensensemap"
    max_boxes_returned = 5

    async def fetch(
        self,
        client: httpx.AsyncClient,
        query: WeatherQuery,
        transformed: TransformedInputs,
    ):
        params = {
            "near": f"{transformed.lon},{transformed.lat}",
            "maxDistance": settings.opensensemap_max_distance_m,
            "format": "json",
        }
        resp = await client.get(
            settings.opensensemap_url,
            params=params,
            timeout=settings.request_timeout_seconds,
        )
        resp.raise_for_status()
        boxes = resp.json() or []

        slim = [
            {
                "name": box.get("name"),
                "exposure": box.get("exposure"),
                "currentLocation": box.get("currentLocation"),
                "sensors": [
                    {
                        "title": s.get("title"),
                        "unit": s.get("unit"),
                        "lastMeasurement": s.get("lastMeasurement"),
                    }
                    for s in (box.get("sensors") or [])
                ],
            }
            for box in boxes[: self.max_boxes_returned]
        ]
        return {"nearby_box_count": len(boxes), "boxes": slim}
