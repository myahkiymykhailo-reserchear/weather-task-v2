"""Direct tests for app.insight (P4.1)."""
from datetime import date

import pytest

from app.insight import build_insight
from app.models import ProviderResult, TransformedInputs, WeatherSnapshot


def _transformed(units="celsius"):
    return TransformedInputs(
        lat=40.71,
        lon=-74.0,
        timezone="America/New_York",
        resolved_name="New York, NY, US",
        country_code="US",
        date=date(2026, 5, 4),
        units=units,
    )


def _ok(snap: WeatherSnapshot) -> ProviderResult:
    return ProviderResult(status="ok", normalized=snap, elapsed_ms=10)


def test_build_insight_no_providers():
    summary = build_insight(_transformed(), {})
    assert "No weather snapshots" in summary


def test_build_insight_averages_in_celsius():
    """P1.1 regression: even with units=fahrenheit, averaging happens in
    canonical Celsius and is converted exactly once at display time."""
    providers = {
        "open_meteo": _ok(WeatherSnapshot(temperature_c=20.0, source_quality="live")),
        "wttr": _ok(WeatherSnapshot(temperature_c=18.0, source_quality="live")),
        "seven_timer": _ok(WeatherSnapshot(temperature_c=22.0, source_quality="live")),
    }
    summary_c = build_insight(_transformed("celsius"), providers)
    summary_f = build_insight(_transformed("fahrenheit"), providers)

    # Average of 20, 18, 22 = 20.0°C = 68.0°F
    assert "20.0°C" in summary_c
    assert "68.0°F" in summary_f
    assert "3 source(s)" in summary_c


def test_build_insight_flags_fallback_sources():
    providers = {
        "open_meteo": _ok(WeatherSnapshot(temperature_c=15.0, source_quality="fallback")),
        "wttr": _ok(WeatherSnapshot(temperature_c=18.0, source_quality="live")),
    }
    summary = build_insight(_transformed(), providers)
    assert "fallback" in summary.lower()
    assert "open_meteo" in summary  # named so user knows which one


def test_build_insight_consensus_conditions():
    providers = {
        "a": _ok(WeatherSnapshot(temperature_c=10.0, conditions="Sunny")),
        "b": _ok(WeatherSnapshot(temperature_c=11.0, conditions="Sunny")),
        "c": _ok(WeatherSnapshot(temperature_c=12.0, conditions="Cloudy")),
    }
    summary = build_insight(_transformed(), providers)
    assert "Sunny" in summary  # majority


def test_build_insight_includes_precipitation_and_wind_when_available():
    providers = {
        "a": _ok(
            WeatherSnapshot(
                temperature_c=10.0, precipitation_mm=2.5, wind_kph=20.0
            )
        ),
        "b": _ok(
            WeatherSnapshot(
                temperature_c=12.0, precipitation_mm=1.5, wind_kph=10.0
            )
        ),
    }
    summary = build_insight(_transformed(), providers)
    assert "2.0mm" in summary  # avg precip
    assert "15 km/h" in summary  # avg wind


def test_build_insight_handles_no_temperature_samples():
    """If providers reported snapshots but none had temperature_c, we still
    emit a usable summary — just without an average line."""
    providers = {
        "a": _ok(WeatherSnapshot(conditions="Foggy", source_quality="live")),
    }
    summary = build_insight(_transformed(), providers)
    assert "no temperature samples" in summary.lower()
    assert "Foggy" in summary
