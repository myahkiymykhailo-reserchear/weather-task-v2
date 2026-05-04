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
    respx.get(url__startswith="https://wttr.in/").mock(
        return_value=httpx.Response(
            200,
            json={
                "current_condition": [
                    {
                        "temp_C": "19",
                        "humidity": "60",
                        "windspeedKmph": "5",
                        "weatherDesc": [{"value": "Sunny"}],
                    }
                ]
            },
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
    respx.get(url__startswith="https://wttr.in/").mock(
        return_value=httpx.Response(
            200,
            json={
                "current_condition": [
                    {
                        "temp_C": "15",
                        "humidity": "70",
                        "windspeedKmph": "8",
                        "weatherDesc": [{"value": "Cloudy"}],
                    }
                ]
            },
        )
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
    # Relative paths so the same HTML works under FastAPI (/) and on GitHub Pages (/REPO/).
    assert "static/style.css" in body
    assert "static/app.js" in body


def test_cors_default_allows_github_pages_origin(client):
    """Default cors_allow_origin_regex must let *.github.io call /weather."""
    resp = client.get(
        "/weather",
        params={"city": "Berlin", "country": "DE"},
        headers={"Origin": "https://myahkiymykhailo-reserchear.github.io"},
    )
    # respx isn't mocked here so the upstream calls would fail, but FastAPI
    # still emits the CORS header on every response — that's all we check.
    allow_origin = resp.headers.get("access-control-allow-origin")
    assert allow_origin == "https://myahkiymykhailo-reserchear.github.io"


def test_cors_default_allows_localhost_origin(client):
    resp = client.get(
        "/livez",
        headers={"Origin": "http://localhost:8765"},
    )
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:8765"


def test_cors_preflight_returns_allow_methods(client):
    """Browsers send an OPTIONS preflight before a cross-origin GET."""
    resp = client.options(
        "/weather",
        headers={
            "Origin": "https://x.github.io",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert resp.status_code == 200
    assert "GET" in resp.headers.get("access-control-allow-methods", "")
    assert resp.headers.get("access-control-allow-origin") == "https://x.github.io"


def test_static_assets_are_served(client):
    """Both CSS and JS load with the right content types."""
    css = client.get("/static/style.css")
    assert css.status_code == 200
    assert "css" in css.headers["content-type"]

    js = client.get("/static/app.js")
    assert js.status_code == 200
    assert "javascript" in js.headers["content-type"]
