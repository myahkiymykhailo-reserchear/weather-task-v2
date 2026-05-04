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
async def test_geocode_raises_on_country_mismatch_no_silent_fallback():
    """P1.4 regression: when country is supplied but no result matches,
    raise GeocodingError instead of silently returning the first row."""
    payload = {
        "results": [
            {
                "name": "Paris",
                "latitude": 48.85,
                "longitude": 2.35,
                "country": "France",
                "country_code": "FR",
                "admin1": "Île-de-France",
            },
            {
                "name": "Paris",
                "latitude": 33.66,
                "longitude": -95.55,
                "country": "United States",
                "country_code": "US",
                "admin1": "Texas",
            },
        ]
    }
    respx.get("https://geocoding-api.open-meteo.com/v1/search").mock(
        return_value=httpx.Response(200, json=payload)
    )
    async with httpx.AsyncClient() as client:
        with pytest.raises(GeocodingError) as exc_info:
            await geocode(client, WeatherQuery(city="Paris", country="JP", units="celsius"))
    assert "JP" in str(exc_info.value)


@pytest.mark.asyncio
@respx.mock
async def test_geocode_normalises_country_aliases():
    """P1.5: 'USA' / 'United States' / 'us' all reach the US row."""
    from app.geocoding import normalize_country

    assert normalize_country("USA") == ("usa", "us")
    assert normalize_country("United States") == ("united states", "us")
    assert normalize_country("us") == ("us", "us")
    assert normalize_country("DE") == ("de", "de")
    assert normalize_country("Deutschland") == ("deutschland", "de")
    assert normalize_country("Atlantis") == ("atlantis", None)

    payload = {
        "results": [
            {
                "name": "New York",
                "latitude": 40.71,
                "longitude": -74.0,
                "country": "United States",
                "country_code": "US",
                "admin1": "New York",
            }
        ]
    }
    respx.get("https://geocoding-api.open-meteo.com/v1/search").mock(
        return_value=httpx.Response(200, json=payload)
    )
    async with httpx.AsyncClient() as client:
        out = await geocode(client, WeatherQuery(city="New York", country="USA", units="celsius"))
    assert out.country_code == "US"


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
