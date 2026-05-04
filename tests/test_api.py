import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    # `with` triggers FastAPI lifespan (startup/shutdown) so app.state.http_client exists.
    with TestClient(app) as c:
        yield c


@respx.mock
def test_weather_endpoint_aggregates_all_providers(client):
    respx.get("https://geocoding-api.open-meteo.com/v1/search").mock(
        return_value=httpx.Response(
            200,
            json={
                "results": [
                    {
                        "name": "New York",
                        "latitude": 40.7,
                        "longitude": -74.0,
                        "country": "United States",
                        "country_code": "US",
                        "admin1": "New York",
                        "timezone": "America/New_York",
                    }
                ]
            },
        )
    )
    respx.get("https://api.open-meteo.com/v1/forecast").mock(
        return_value=httpx.Response(
            200,
            json={
                "current": {"temperature_2m": 18.0},
                "daily": {
                    "temperature_2m_max": [22],
                    "temperature_2m_min": [12],
                    "precipitation_sum": [0.0],
                },
            },
        )
    )
    respx.get(url__startswith="https://goweather.xyz/weather/").mock(
        return_value=httpx.Response(
            200,
            json={"temperature": "+19 °C", "wind": "5 km/h", "description": "Sunny"},
        )
    )
    respx.get("https://api.opensensemap.org/boxes").mock(return_value=httpx.Response(200, json=[]))
    respx.get("https://api.oceandrivers.com/v1.0/getStations/").mock(
        return_value=httpx.Response(200, json=[])
    )
    respx.get("https://www.7timer.info/bin/api.pl").mock(
        return_value=httpx.Response(200, json={"dataseries": [{"temp2m": 17}]})
    )

    resp = client.get(
        "/weather",
        params={"city": "New York", "country": "US", "state": "NY"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["raw_input"]["city"] == "New York"
    assert data["raw_input"]["units"] == "celsius"
    assert data["transformed_inputs"]["lat"] == 40.7
    assert data["transformed_inputs"]["lon"] == -74.0

    providers = data["result"]["providers"]
    normalized = data["result"]["normalized"]
    for name in ["open_meteo", "wttr", "opensensemap", "oceandrivers", "seven_timer"]:
        assert name in providers, f"missing provider {name}"
        assert providers[name]["status"] in {"ok", "error"}
        # Every provider — ok or error — exposes a normalised snapshot.
        assert "normalized" in providers[name]
        assert name in normalized
        assert normalized[name]["source_quality"] in {"live", "fallback"}

    assert "summary" in data["result"]
    assert "average" in data["result"]["summary"]


@respx.mock
def test_weather_endpoint_handles_missing_geocode(client):
    respx.get("https://geocoding-api.open-meteo.com/v1/search").mock(
        return_value=httpx.Response(200, json={"results": []})
    )
    resp = client.get("/weather", params={"city": "Nowhereville", "country": "ZZ"})
    assert resp.status_code == 404


@respx.mock
def test_weather_endpoint_isolates_provider_failure(client):
    """One failing provider must not break the response."""
    respx.get("https://geocoding-api.open-meteo.com/v1/search").mock(
        return_value=httpx.Response(
            200,
            json={
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
            },
        )
    )
    respx.get("https://api.open-meteo.com/v1/forecast").mock(return_value=httpx.Response(500))
    respx.get(url__startswith="https://goweather.xyz/weather/").mock(
        return_value=httpx.Response(200, json={"temperature": "+15 °C"})
    )
    respx.get("https://api.opensensemap.org/boxes").mock(return_value=httpx.Response(200, json=[]))
    respx.get("https://api.oceandrivers.com/v1.0/getStations/").mock(
        return_value=httpx.Response(200, json=[])
    )
    respx.get("https://www.7timer.info/bin/api.pl").mock(
        return_value=httpx.Response(200, json={"dataseries": [{"temp2m": 14}]})
    )

    resp = client.get("/weather", params={"city": "Berlin", "country": "DE"})
    assert resp.status_code == 200
    body = resp.json()
    providers = body["result"]["providers"]
    assert providers["open_meteo"]["status"] == "error"
    assert providers["wttr"]["status"] == "ok"
    assert providers["seven_timer"]["status"] == "ok"
    # The failed provider still returns a normalised fallback snapshot.
    assert providers["open_meteo"]["normalized"]["source_quality"] == "fallback"
    assert providers["wttr"]["normalized"]["source_quality"] == "live"


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_missing_required_city_param(client):
    resp = client.get("/weather", params={"country": "US"})
    assert resp.status_code == 422


def test_root_serves_html_ui(client):
    """Smoke test: the UI is served at / and references the static assets."""
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")
    body = resp.text
    assert "<title>Weather Aggregator</title>" in body
    assert '/static/style.css' in body
    assert '/static/app.js' in body


def test_static_assets_are_served(client):
    """Both CSS and JS load with the right content types."""
    css = client.get("/static/style.css")
    assert css.status_code == 200
    assert "css" in css.headers["content-type"]

    js = client.get("/static/app.js")
    assert js.status_code == 200
    assert "javascript" in js.headers["content-type"]
