import httpx
import pytest
import respx

from app.providers.oceandrivers import OceanDriversProvider, haversine
from app.providers.open_meteo import OpenMeteoProvider
from app.providers.opensensemap import OpenSenseMapProvider
from app.providers.seven_timer import SevenTimerProvider
from app.providers.wttr import WttrProvider


@pytest.mark.asyncio
@respx.mock
async def test_open_meteo_fetch_passes_units_and_date(query, transformed):
    route = respx.get("https://api.open-meteo.com/v1/forecast").mock(
        return_value=httpx.Response(
            200,
            json={
                "current": {"temperature_2m": 18.4},
                "daily": {
                    "temperature_2m_max": [22],
                    "temperature_2m_min": [12],
                    "precipitation_sum": [0.0],
                },
            },
        )
    )
    async with httpx.AsyncClient() as client:
        result = await OpenMeteoProvider().safe_fetch(client, query, transformed)

    assert result.status == "ok"
    assert result.data["current"]["temperature_2m"] == 18.4
    sent = route.calls.last.request
    assert sent.url.params["temperature_unit"] == "celsius"
    assert sent.url.params["start_date"] == transformed.date.isoformat()
    assert sent.url.params["end_date"] == transformed.date.isoformat()


@pytest.mark.asyncio
@respx.mock
async def test_wttr_uses_city_in_path(query, transformed):
    respx.get("https://goweather.xyz/weather/New%20York").mock(
        return_value=httpx.Response(200, json={"temperature": "+18 °C", "wind": "10 km/h"})
    )
    async with httpx.AsyncClient() as client:
        result = await WttrProvider().safe_fetch(client, query, transformed)
    assert result.status == "ok"
    assert result.data["temperature"] == "+18 °C"


@pytest.mark.asyncio
@respx.mock
async def test_wttr_url_encodes_city_with_spaces_and_diacritics(transformed):
    from app.models import WeatherQuery

    sao_paulo = WeatherQuery(city="São Paulo", country="BR", units="celsius")
    route = respx.get("https://goweather.xyz/weather/S%C3%A3o%20Paulo").mock(
        return_value=httpx.Response(200, json={"temperature": "+22 °C"})
    )
    async with httpx.AsyncClient() as client:
        result = await WttrProvider().safe_fetch(client, sao_paulo, transformed)
    assert result.status == "ok"
    assert route.called


@pytest.mark.asyncio
@respx.mock
async def test_provider_records_error_on_5xx(query, transformed):
    respx.get("https://goweather.xyz/weather/New%20York").mock(return_value=httpx.Response(500))
    async with httpx.AsyncClient() as client:
        result = await WttrProvider().safe_fetch(client, query, transformed)
    assert result.status == "error"
    assert "HTTPStatusError" in result.error or "500" in result.error


@pytest.mark.asyncio
@respx.mock
async def test_opensensemap_slims_response(query, transformed):
    body = [
        {
            "name": "Sense-Box-1",
            "exposure": "outdoor",
            "currentLocation": {"coordinates": [-74.0, 40.71]},
            "sensors": [
                {
                    "title": "Temperature",
                    "unit": "°C",
                    "lastMeasurement": {"value": "20.1"},
                }
            ],
        },
        {"name": "Sense-Box-2", "exposure": "indoor", "sensors": []},
    ]
    respx.get("https://api.opensensemap.org/boxes").mock(
        return_value=httpx.Response(200, json=body)
    )
    async with httpx.AsyncClient() as client:
        result = await OpenSenseMapProvider().safe_fetch(client, query, transformed)
    assert result.status == "ok"
    assert result.data["nearby_box_count"] == 2
    assert len(result.data["boxes"]) == 2
    assert result.data["boxes"][0]["name"] == "Sense-Box-1"


@pytest.mark.asyncio
@respx.mock
async def test_seven_timer_passes_lat_lon(query, transformed):
    route = respx.get("https://www.7timer.info/bin/api.pl").mock(
        return_value=httpx.Response(200, json={"dataseries": [{"temp2m": 16}]})
    )
    async with httpx.AsyncClient() as client:
        result = await SevenTimerProvider().safe_fetch(client, query, transformed)
    assert result.status == "ok"
    assert result.data["dataseries"][0]["temp2m"] == 16
    sent = route.calls.last.request
    assert float(sent.url.params["lat"]) == pytest.approx(round(transformed.lat, 2))
    assert float(sent.url.params["lon"]) == pytest.approx(round(transformed.lon, 2))


def test_haversine_zero():
    assert haversine(0, 0, 0, 0) == 0


def test_haversine_known_distance():
    # New York to Los Angeles ≈ 3940 km
    d = haversine(40.71, -74.0, 34.05, -118.24)
    assert 3900 < d < 4000


@pytest.mark.asyncio
@respx.mock
async def test_oceandrivers_returns_message_when_no_nearby_station(query, transformed):
    respx.get("https://api.oceandrivers.com/v1.0/getStations/").mock(
        return_value=httpx.Response(
            200,
            json=[{"stationName": "PalmaPort", "latitude": 39.56, "longitude": 2.65}],
        )
    )
    async with httpx.AsyncClient() as client:
        result = await OceanDriversProvider().safe_fetch(client, query, transformed)
    assert result.status == "ok"
    assert "No station within" in result.data["message"]
    assert result.data["stations_checked"] == 1


@pytest.mark.asyncio
@respx.mock
async def test_oceandrivers_handles_zero_coordinate_station():
    """Regression: 0.0 latitude/longitude must not be treated as missing."""
    from datetime import date

    from app.models import TransformedInputs, WeatherQuery

    near_equator = TransformedInputs(
        lat=0.5, lon=0.5, timezone="UTC", resolved_name="Test", country_code="XX",
        date=date(2026, 5, 4), units="celsius",
    )
    q = WeatherQuery(city="Test", country="XX", units="celsius")

    respx.get("https://api.oceandrivers.com/v1.0/getStations/").mock(
        return_value=httpx.Response(
            200,
            json=[{"stationName": "EquatorStation", "latitude": 0.0, "longitude": 0.0}],
        )
    )
    respx.get("https://api.oceandrivers.com/v1.0/getMeteo/EquatorStation/en/json").mock(
        return_value=httpx.Response(200, json={"temperatureC": 28.0})
    )
    async with httpx.AsyncClient() as client:
        result = await OceanDriversProvider().safe_fetch(client, q, near_equator)
    assert result.status == "ok"
    assert result.data["station"] == "EquatorStation"


@pytest.mark.asyncio
@respx.mock
async def test_oceandrivers_fetches_meteo_when_station_close(query, transformed):
    respx.get("https://api.oceandrivers.com/v1.0/getStations/").mock(
        return_value=httpx.Response(
            200,
            json=[{"stationName": "ManhattanMarina", "latitude": 40.72, "longitude": -74.01}],
        )
    )
    respx.get("https://api.oceandrivers.com/v1.0/getMeteo/ManhattanMarina/en/json").mock(
        return_value=httpx.Response(200, json={"temperatureC": 19.0})
    )
    async with httpx.AsyncClient() as client:
        result = await OceanDriversProvider().safe_fetch(client, query, transformed)
    assert result.status == "ok"
    assert result.data["station"] == "ManhattanMarina"
    assert result.data["meteo"]["temperatureC"] == 19.0
