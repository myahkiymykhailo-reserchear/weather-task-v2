import math

import httpx

from app.config import settings
from app.models import TransformedInputs, WeatherQuery
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
    """Marine weather. Looks up the nearest known station, then queries it."""

    name = "oceandrivers"

    async def fetch(
        self,
        client: httpx.AsyncClient,
        query: WeatherQuery,
        transformed: TransformedInputs,
    ):
        resp = await client.get(
            settings.oceandrivers_stations_url,
            timeout=settings.request_timeout_seconds,
        )
        resp.raise_for_status()
        stations = resp.json()

        if not isinstance(stations, list) or not stations:
            return {"message": "No stations available", "stations_checked": 0}

        nearest, distance_km = self._find_nearest(stations, transformed.lat, transformed.lon)
        if nearest is None:
            return {"message": "No usable station coordinates", "stations_checked": len(stations)}

        if distance_km > settings.oceandrivers_max_station_km:
            return {
                "message": f"No station within {settings.oceandrivers_max_station_km}km",
                "stations_checked": len(stations),
                "nearest_distance_km": round(distance_km, 2),
            }

        station_id = nearest.get("stationName") or nearest.get("name") or nearest.get("id")
        if not station_id:
            return {
                "message": "Nearest station has no identifier",
                "nearest": nearest,
                "distance_km": round(distance_km, 2),
            }

        meteo_url = f"{settings.oceandrivers_meteo_url}/{station_id}/en/json"
        meteo_resp = await client.get(meteo_url, timeout=settings.request_timeout_seconds)
        meteo_resp.raise_for_status()
        return {
            "station": station_id,
            "distance_km": round(distance_km, 2),
            "meteo": meteo_resp.json(),
        }

    @staticmethod
    def _find_nearest(stations: list[dict], lat: float, lon: float):
        best, best_d = None, float("inf")
        for s in stations:
            try:
                slat = float(s.get("latitude") or s.get("lat"))
                slon = float(s.get("longitude") or s.get("lon"))
            except (TypeError, ValueError):
                continue
            d = haversine(lat, lon, slat, slon)
            if d < best_d:
                best_d = d
                best = s
        return best, best_d
