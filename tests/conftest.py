from datetime import date

import pytest

from app.models import TransformedInputs, WeatherQuery


@pytest.fixture
def sample_geocoding_response():
    return {
        "results": [
            {
                "id": 5128581,
                "name": "New York",
                "latitude": 40.71427,
                "longitude": -74.00597,
                "country": "United States",
                "country_code": "US",
                "admin1": "New York",
                "timezone": "America/New_York",
            },
            {
                "id": 6332428,
                "name": "New York Mills",
                "latitude": 43.10592,
                "longitude": -75.29159,
                "country": "United States",
                "country_code": "US",
                "admin1": "New York",
                "timezone": "America/New_York",
            },
        ]
    }


@pytest.fixture
def query():
    return WeatherQuery(city="New York", country="US", units="celsius")


@pytest.fixture
def transformed():
    return TransformedInputs(
        lat=40.71,
        lon=-74.0,
        timezone="America/New_York",
        resolved_name="New York, New York, United States",
        country_code="US",
        date=date(2026, 5, 4),
        units="celsius",
    )
