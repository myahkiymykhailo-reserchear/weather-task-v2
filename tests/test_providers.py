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


_WTTR_BERLIN_BODY = {
    "current_condition": [
        {
            "temp_C": "18",
            "FeelsLikeC": "17",
            "humidity": "65",
            "windspeedKmph": "12",
            "cloudcover": "30",
            "precipMM": "0.0",
            "weatherDesc": [{"value": "Partly cloudy"}],
        }
    ]
}


@pytest.mark.asyncio
@respx.mock
async def test_wttr_uses_city_in_path_and_normalises_j1_schema(query, transformed):
    route = respx.get("https://wttr.in/New%20York").mock(
        return_value=httpx.Response(200, json=_WTTR_BERLIN_BODY)
    )
    async with httpx.AsyncClient() as client:
        result = await WttrProvider().safe_fetch(client, query, transformed)
    assert result.status == "ok"
    # Normalisation should pick up the wttr.in j1 schema.
    assert result.normalized.temperature_c == 18.0
    assert result.normalized.humidity_pct == 65.0
    assert result.normalized.wind_kph == 12.0
    assert result.normalized.conditions == "Partly cloudy"
    # Confirm format=j1 is sent.
    assert route.calls.last.request.url.params["format"] == "j1"


@pytest.mark.asyncio
@respx.mock
async def test_wttr_url_encodes_city_with_spaces_and_diacritics(transformed):
    from app.models import WeatherQuery

    sao_paulo = WeatherQuery(city="São Paulo", country="BR", units="celsius")
    route = respx.get("https://wttr.in/S%C3%A3o%20Paulo").mock(
        return_value=httpx.Response(200, json=_WTTR_BERLIN_BODY)
    )
    async with httpx.AsyncClient() as client:
        result = await WttrProvider().safe_fetch(client, sao_paulo, transformed)
    assert result.status == "ok"
    assert route.called


@pytest.mark.asyncio
@respx.mock
async def test_provider_returns_fallback_on_read_timeout(query, transformed):
    """P4.2: an httpx.ReadTimeout from upstream is converted to a
    fallback ProviderResult so the rest of the response is unaffected."""
    respx.get("https://wttr.in/New%20York").mock(
        side_effect=httpx.ReadTimeout("upstream took too long")
    )
    async with httpx.AsyncClient() as client:
        result = await WttrProvider().safe_fetch(client, query, transformed)
    assert result.status == "error"
    assert "ReadTimeout" in result.error
    assert result.normalized is not None
    assert result.normalized.source_quality == "fallback"
    assert result.normalized.notes and "unavailable" in result.normalized.notes


@pytest.mark.asyncio
@respx.mock
async def test_provider_records_error_on_5xx(query, transformed):
    respx.get("https://wttr.in/New%20York").mock(return_value=httpx.Response(500))
    async with httpx.AsyncClient() as client:
        result = await WttrProvider().safe_fetch(client, query, transformed)
    assert result.status == "error"
    assert "HTTPStatusError" in result.error or "500" in result.error


@pytest.mark.asyncio
@respx.mock
async def test_opensensemap_two_step_fetch_aggregates_sensor_values(query, transformed):
    """Provider does GET /boxes?...&minimal=true then parallel GET /boxes/{id}."""
    minimal_list = [
        {"_id": "box-a", "name": "Box-A"},
        {"_id": "box-b", "name": "Box-B"},
    ]
    respx.get("https://api.opensensemap.org/boxes").mock(
        return_value=httpx.Response(200, json=minimal_list)
    )
    respx.get("https://api.opensensemap.org/boxes/box-a").mock(
        return_value=httpx.Response(
            200,
            json={
                "_id": "box-a",
                "name": "Box-A",
                "exposure": "outdoor",
                "sensors": [
                    {"title": "Temperature", "unit": "°C", "lastMeasurement": {"value": "20.0"}},
                    {"title": "Humidity",    "unit": "%",  "lastMeasurement": {"value": "60"}},
                ],
            },
        )
    )
    respx.get("https://api.opensensemap.org/boxes/box-b").mock(
        return_value=httpx.Response(
            200,
            json={
                "_id": "box-b",
                "name": "Box-B",
                "exposure": "outdoor",
                "sensors": [
                    {"title": "Temperatur",  "unit": "°C", "lastMeasurement": {"value": "22.0"}},
                ],
            },
        )
    )
    async with httpx.AsyncClient() as client:
        result = await OpenSenseMapProvider().safe_fetch(client, query, transformed)
    assert result.status == "ok"
    assert result.data["nearby_box_count"] == 2
    assert len(result.data["boxes"]) == 2
    # Normalised: average temperature across both boxes (20 + 22) / 2 = 21
    assert result.normalized.temperature_c == 21.0
    assert result.normalized.humidity_pct == 60.0


@pytest.mark.asyncio
@respx.mock
async def test_opensensemap_handles_no_nearby_boxes(query, transformed):
    respx.get("https://api.opensensemap.org/boxes").mock(
        return_value=httpx.Response(200, json=[])
    )
    async with httpx.AsyncClient() as client:
        result = await OpenSenseMapProvider().safe_fetch(client, query, transformed)
    assert result.status == "ok"
    assert result.data["nearby_box_count"] == 0
    assert result.normalized.notes and "No openSenseMap boxes" in result.normalized.notes


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
async def test_oceandrivers_returns_out_of_region_for_far_query(query, transformed):
    """transformed fixture is New York; OceanDrivers' single station is in Mallorca,
    well over the 200 km coverage radius — provider should not call upstream."""
    route = respx.get(
        "https://api.oceandrivers.com/v1.0/getAemetStation/AreaPalma/lastdata/"
    ).mock(return_value=httpx.Response(200, json={"TEMPERATURE": 20.0}))
    async with httpx.AsyncClient() as client:
        result = await OceanDriversProvider().safe_fetch(client, query, transformed)
    assert result.status == "ok"
    assert not route.called  # never called: out of region
    assert result.data["in_region"] is False
    assert result.normalized.source_quality == "live"
    assert "OceanDrivers covers Spanish marine waters" in result.normalized.notes


@pytest.mark.asyncio
@respx.mock
async def test_oceandrivers_fetches_data_when_query_within_region():
    """A query near Palma should successfully fetch the AreaPalma station."""
    from datetime import date

    from app.models import TransformedInputs, WeatherQuery

    near_palma = TransformedInputs(
        lat=39.6, lon=2.65, timezone="Europe/Madrid",
        resolved_name="Palma, ES", country_code="ES",
        date=date(2026, 5, 4), units="celsius",
    )
    q = WeatherQuery(city="Palma", country="ES", units="celsius")

    respx.get(
        "https://api.oceandrivers.com/v1.0/getAemetStation/AreaPalma/lastdata/"
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "TEMPERATURE": 20.2,
                "HUMIDITY": 83.0,
                "TWS": 6.667,           # m/s ≈ 24 km/h
                "TWD": 225,
                "RAIN_DAY": 0.0,
            },
        )
    )
    async with httpx.AsyncClient() as client:
        result = await OceanDriversProvider().safe_fetch(client, q, near_palma)
    assert result.status == "ok"
    assert result.data["in_region"] is True
    snap = result.normalized
    assert snap.temperature_c == 20.2
    assert snap.humidity_pct == 83.0
    assert snap.wind_kph == pytest.approx(6.667 * 3.6)
    assert snap.wind_direction_deg == 225.0
