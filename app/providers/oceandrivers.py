import math
from typing import Any, Optional

import httpx

from app.config import settings
from app.models import TransformedInputs, WeatherQuery, WeatherSnapshot
from app.providers.base import WeatherProvider


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two lat/lon points, in kilometres."""
    radius = 6371.0
    lat1r, lat2r = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1r) * math.cos(lat2r) * math.sin(dlon / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(a))


class OceanDriversProvider(WeatherProvider):
    """OceanDrivers AEMET station — Spanish marine weather (regional).

    Background: v0.2 of this provider fetched a non-existent
    ``/v1.0/getStations/`` endpoint and 404'd on every call. The real API
    documented at https://api.oceandrivers.com/static/docs.html exposes
    ``/v1.0/getAemetStation/{stationName}/{period}/`` and friends. The
    public catalogue effectively serves a single usable station,
    ``AreaPalma`` at (39.5604, 2.7417) in Mallorca; other names alias to
    the same data.

    Strategy: compute distance from the user's query to that station.
    If within ``oceandrivers_max_station_km`` (default 200 km), fetch
    the station's last data. Otherwise emit a *live* (not fallback)
    snapshot whose ``notes`` make clear the data is genuinely
    unavailable for the queried region.
    """

    name = "oceandrivers"

    async def fetch(
        self,
        client: httpx.AsyncClient,
        query: WeatherQuery,
        transformed: TransformedInputs,
    ):
        distance_km = haversine(
            transformed.lat,
            transformed.lon,
            settings.oceandrivers_station_lat,
            settings.oceandrivers_station_lon,
        )

        if distance_km > settings.oceandrivers_max_station_km:
            return {
                "in_region": False,
                "nearest_station": settings.oceandrivers_station_name,
                "nearest_station_km": round(distance_km, 1),
                "limit_km": settings.oceandrivers_max_station_km,
            }

        url = (
            f"{settings.oceandrivers_url}/v1.0/getAemetStation/"
            f"{settings.oceandrivers_station_name}/lastdata/"
        )
        resp = await client.get(url, timeout=settings.request_timeout_seconds)
        resp.raise_for_status()
        return {
            "in_region": True,
            "station": settings.oceandrivers_station_name,
            "distance_km": round(distance_km, 1),
            "data": resp.json(),
        }

    def normalize(self, raw: Any, transformed: TransformedInputs) -> WeatherSnapshot:
        raw = raw or {}

        if not raw.get("in_region"):
            d = raw.get("nearest_station_km")
            return WeatherSnapshot(
                is_forecast=False,
                forecast_for_date=transformed.date,
                source_quality="live",
                notes=(
                    f"OceanDrivers covers Spanish marine waters. Nearest station "
                    f"({raw.get('nearest_station')}) is {d} km away — outside the "
                    f"{raw.get('limit_km')} km coverage radius for this query."
                ),
            )

        data = raw.get("data") or {}
        return WeatherSnapshot(
            temperature_c=_as_float(data.get("TEMPERATURE")),
            humidity_pct=_as_float(data.get("HUMIDITY")),
            wind_kph=_ms_to_kph(_as_float(data.get("TWS"))),
            wind_direction_deg=_as_float(data.get("TWD")),
            precipitation_mm=_as_float(data.get("RAIN_DAY")),
            is_forecast=False,
            forecast_for_date=transformed.date,
            source_quality="live",
            notes=f"AEMET station {raw.get('station')} at {raw.get('distance_km')} km",
        )

    def fallback(self, transformed: TransformedInputs) -> WeatherSnapshot:
        return WeatherSnapshot(
            temperature_c=18.0,
            humidity_pct=70.0,
            wind_kph=12.0,
            is_forecast=False,
            forecast_for_date=transformed.date,
            source_quality="fallback",
            notes="OceanDrivers unavailable; placeholder example data.",
        )


def _as_float(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _ms_to_kph(v: Optional[float]) -> Optional[float]:
    return v * 3.6 if v is not None else None
