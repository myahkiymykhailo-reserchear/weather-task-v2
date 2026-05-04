from datetime import date

import httpx
import pytest
import respx

from app.geocoding import GeocodingError, geocode
from app.models import WeatherQuery


@pytest.mark.asyncio
@respx.mock
async def test_geocode_returns_coordinates(sample_geocoding_response):
    respx.get("https://geocoding-api.open-meteo.com/v1/search").mock(
        return_value=httpx.Response(200, json=sample_geocoding_response)
    )
    async with httpx.AsyncClient() as client:
        out = await geocode(client, WeatherQuery(city="New York", country="US", units="celsius"))

    assert out.lat == pytest.approx(40.71427)
    assert out.lon == pytest.approx(-74.00597)
    assert out.timezone == "America/New_York"
    assert out.country_code == "US"
    assert out.date == date.today()


@pytest.mark.asyncio
@respx.mock
async def test_geocode_prefers_state_match(sample_geocoding_response):
    # Both rows share country=US; admin1='New York'. Pick the one whose name matches city exactly first
    # by giving it a higher score. Add a third dud entry to confirm scoring still picks the right one.
    payload = {
        "results": [
            {
                "name": "New York",
                "latitude": 1.0,
                "longitude": 1.0,
                "country": "United States",
                "country_code": "US",
                "admin1": "California",
            },
            {
                "name": "New York",
                "latitude": 40.71,
                "longitude": -74.0,
                "country": "United States",
                "country_code": "US",
                "admin1": "New York",
            },
        ]
    }
    respx.get("https://geocoding-api.open-meteo.com/v1/search").mock(
        return_value=httpx.Response(200, json=payload)
    )
    async with httpx.AsyncClient() as client:
        out = await geocode(
            client,
            WeatherQuery(city="New York", state="New York", country="US", units="celsius"),
        )
    assert out.lat == pytest.approx(40.71)


@pytest.mark.asyncio
@respx.mock
async def test_geocode_raises_on_no_results():
    respx.get("https://geocoding-api.open-meteo.com/v1/search").mock(
        return_value=httpx.Response(200, json={"results": []})
    )
    async with httpx.AsyncClient() as client:
        with pytest.raises(GeocodingError):
            await geocode(
                client,
                WeatherQuery(city="Nowhereville", country="ZZ", units="celsius"),
            )


@pytest.mark.asyncio
@respx.mock
async def test_geocode_uses_query_date():
    payload = {
        "results": [
            {
                "name": "Berlin",
                "latitude": 52.52,
                "longitude": 13.41,
                "country": "Germany",
                "country_code": "DE",
                "admin1": "Berlin",
                "timezone": "Europe/Berlin",
            }
        ]
    }
    respx.get("https://geocoding-api.open-meteo.com/v1/search").mock(
        return_value=httpx.Response(200, json=payload)
    )
    async with httpx.AsyncClient() as client:
        out = await geocode(
            client,
            WeatherQuery(city="Berlin", country="DE", date=date(2026, 6, 1), units="celsius"),
        )
    assert out.date == date(2026, 6, 1)
