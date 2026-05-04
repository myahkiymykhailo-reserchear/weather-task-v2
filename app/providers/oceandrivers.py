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

        station_id = _first_non_none(
            nearest.get("stationName"), nearest.get("name"), nearest.get("id")
        )
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

    def normalize(self, raw: Any, transformed: TransformedInputs) -> WeatherSnapshot:
        raw = raw or {}
        meteo = raw.get("meteo")
        if not isinstance(meteo, dict):
            # No usable station — surface as a "no data" snapshot, but live (not fallback).
            return WeatherSnapshot(
                is_forecast=False,
                forecast_for_date=transformed.date,
                source_quality="live",
                notes=raw.get("message") or "No marine station data available.",
            )

        # OceanDrivers schemas vary by station. Probe likely keys defensively.
        temp = _first_number(meteo, "temperatureC", "temperature_c", "temperature", "tempC", "temp")
        humid = _first_number(meteo, "humidity", "relativeHumidity", "humidityPct", "rh")
        wind = _first_number(meteo, "windSpeedKph", "windSpeed", "windSpeed_kph", "wind")
        return WeatherSnapshot(
            temperature_c=temp,
            humidity_pct=humid,
            wind_kph=wind,
            is_forecast=False,
            forecast_for_date=transformed.date,
            source_quality="live",
            notes=f"Station {raw.get('station')} at {raw.get('distance_km')}km",
        )

    def fallback(self, transformed: TransformedInputs) -> WeatherSnapshot:
        return WeatherSnapshot(
            temperature_c=17.0,
            wind_kph=15.0,
            humidity_pct=70.0,
            is_forecast=False,
            forecast_for_date=transformed.date,
            source_quality="fallback",
            notes="OceanDrivers unavailable; placeholder example data.",
        )

    @staticmethod
    def _find_nearest(stations: list, lat: float, lon: float):
        best, best_d = None, float("inf")
        for s in stations:
            raw_lat = _first_non_none(s.get("latitude"), s.get("lat"))
            raw_lon = _first_non_none(s.get("longitude"), s.get("lon"))
            if raw_lat is None or raw_lon is None:
                continue
            try:
                slat = float(raw_lat)
                slon = float(raw_lon)
            except (TypeError, ValueError):
                continue
            d = haversine(lat, lon, slat, slon)
            if d < best_d:
                best_d = d
                best = s
        return best, best_d


def _first_non_none(*values):
    for v in values:
        if v is not None:
            return v
    return None


def _first_number(d: dict, *keys: str) -> Optional[float]:
    for k in keys:
        if k in d:
            try:
                return float(d[k])
            except (TypeError, ValueError):
                continue
    return None
