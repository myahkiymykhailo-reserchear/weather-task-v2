import asyncio
from typing import Any, List, Optional

import httpx

from app.config import settings
from app.models import TransformedInputs, WeatherQuery, WeatherSnapshot
from app.providers.base import WeatherProvider


class OpenSenseMapProvider(WeatherProvider):
    """Citizen-science sensor boxes near the location.

    Two-step fetch — much faster than asking for full sensors directly:

      1. ``GET /boxes?near=lon,lat&maxDistance=...&minimal=true`` returns a
         lightweight list (id, name, location) in ~200 ms even for dense
         areas. The full sensor-rich response can be 800 KB and 8+ s.
      2. For the N nearest boxes, ``GET /boxes/{id}`` is fetched in
         parallel via ``asyncio.gather``. Each detail fetch is small
         (1–3 KB) and fast (~150 ms), so even N=5 stays well under
         our per-call timeout.
    """

    name = "opensensemap"
    max_boxes_returned = 3

    async def fetch(
        self,
        client: httpx.AsyncClient,
        query: WeatherQuery,
        transformed: TransformedInputs,
    ):
        list_resp = await client.get(
            settings.opensensemap_url,
            params={
                "near": f"{transformed.lon},{transformed.lat}",
                "maxDistance": settings.opensensemap_max_distance_m,
                "minimal": "true",
            },
            timeout=settings.request_timeout_seconds,
        )
        list_resp.raise_for_status()
        boxes = list_resp.json() or []

        if not boxes:
            return {"nearby_box_count": 0, "boxes": []}

        nearest_ids = [b.get("_id") for b in boxes[: self.max_boxes_returned] if b.get("_id")]
        detail_responses = await asyncio.gather(
            *(
                client.get(
                    f"{settings.opensensemap_url}/{box_id}",
                    timeout=settings.request_timeout_seconds,
                )
                for box_id in nearest_ids
            ),
            return_exceptions=True,
        )

        detailed = []
        for r in detail_responses:
            if isinstance(r, Exception):
                continue
            if r.status_code != 200:
                continue
            box = r.json()
            detailed.append(
                {
                    "_id": box.get("_id"),
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
            )

        return {"nearby_box_count": len(boxes), "boxes": detailed}

    def normalize(self, raw: Any, transformed: TransformedInputs) -> WeatherSnapshot:
        raw = raw or {}
        boxes = raw.get("boxes") or []

        temps: List[float] = []
        humidities: List[float] = []
        for box in boxes:
            for sensor in box.get("sensors") or []:
                value = _measurement_value(sensor)
                if value is None:
                    continue
                title = (sensor.get("title") or "").lower()
                unit = (sensor.get("unit") or "").lower()
                if _is_temperature(title, unit):
                    temps.append(value)
                elif _is_humidity(title, unit):
                    humidities.append(value)

        nearby_count = raw.get("nearby_box_count", 0)
        notes = None
        if not boxes:
            notes = f"No openSenseMap boxes within {settings.opensensemap_max_distance_m / 1000:.0f} km."
        elif not temps and not humidities:
            notes = (
                f"{nearby_count} box(es) found, "
                f"{len(boxes)} fetched, but none reported temperature or humidity in canonical units."
            )

        return WeatherSnapshot(
            temperature_c=_avg(temps),
            humidity_pct=_avg(humidities),
            is_forecast=False,
            forecast_for_date=transformed.date,
            source_quality="live",
            notes=notes,
        )

    def fallback(self, transformed: TransformedInputs) -> WeatherSnapshot:
        return WeatherSnapshot(
            temperature_c=16.0,
            humidity_pct=55.0,
            is_forecast=False,
            forecast_for_date=transformed.date,
            source_quality="fallback",
            notes="openSenseMap unavailable; placeholder example data.",
        )


def _measurement_value(sensor: dict) -> Optional[float]:
    last = sensor.get("lastMeasurement")
    if not isinstance(last, dict):
        return None
    raw = last.get("value")
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _is_temperature(title: str, unit: str) -> bool:
    return ("temp" in title or "temperatur" in title) and ("°c" in unit or unit in {"c", ""})


def _is_humidity(title: str, unit: str) -> bool:
    return ("humid" in title or "feucht" in title or "luftfeucht" in title) and "%" in unit


def _avg(values: List[float]) -> Optional[float]:
    return sum(values) / len(values) if values else None
