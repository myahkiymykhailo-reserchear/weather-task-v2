from typing import Any, List, Optional

import httpx

from app.config import settings
from app.models import TransformedInputs, WeatherQuery, WeatherSnapshot
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

    def normalize(self, raw: Any, transformed: TransformedInputs) -> WeatherSnapshot:
        raw = raw or {}
        boxes = raw.get("boxes") or []

        temps: list[float] = []
        humidities: list[float] = []
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

        notes = None
        if not temps and not humidities:
            notes = (
                f"{raw.get('nearby_box_count', 0)} box(es) found but none reported "
                "temperature or humidity in canonical units."
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
