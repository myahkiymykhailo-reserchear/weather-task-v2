from collections import Counter
from typing import Dict, List, Tuple

from app.models import ProviderResult, TransformedInputs, WeatherSnapshot


def build_insight(transformed: TransformedInputs, providers: Dict[str, ProviderResult]) -> str:
    """Produce a short human-friendly summary across providers.

    Reads each provider's normalised ``WeatherSnapshot`` (always Celsius)
    so the average is unit-safe regardless of which APIs respect the
    user's requested unit. Display-time conversion to Fahrenheit (if
    requested) happens once at the end.

    Snapshots flagged as ``source_quality="fallback"`` (i.e. the upstream
    failed and the provider returned example data) are still shown but
    a count is appended so the user knows how much of the answer was
    placeholder data.
    """
    snapshots: Dict[str, WeatherSnapshot] = {
        name: pr.normalized for name, pr in providers.items() if pr.normalized
    }
    location = transformed.resolved_name or f"({transformed.lat:.2f}, {transformed.lon:.2f})"

    if not snapshots:
        return f"No weather snapshots available for {location} on {transformed.date}."

    temps_c: List[Tuple[str, float]] = [
        (name, snap.temperature_c)
        for name, snap in snapshots.items()
        if snap.temperature_c is not None
    ]
    fallback_sources = [
        name for name, snap in snapshots.items() if snap.source_quality == "fallback"
    ]

    parts: List[str] = []

    if temps_c:
        avg_c = sum(t for _, t in temps_c) / len(temps_c)
        if transformed.units == "fahrenheit":
            avg_display = avg_c * 9 / 5 + 32
            unit = "°F"
        else:
            avg_display = avg_c
            unit = "°C"
        sources = ", ".join(name for name, _ in temps_c)
        parts.append(
            f"{location} on {transformed.date}: average ~{avg_display:.1f}{unit} "
            f"across {len(temps_c)} source(s) ({sources})."
        )
    else:
        parts.append(f"{location} on {transformed.date}: no temperature samples.")

    conditions = [snap.conditions for snap in snapshots.values() if snap.conditions]
    if conditions:
        most_common, _ = Counter(conditions).most_common(1)[0]
        parts.append(f"Conditions: {most_common}.")

    precip_values = [
        snap.precipitation_mm for snap in snapshots.values() if snap.precipitation_mm is not None
    ]
    if precip_values:
        avg_precip = sum(precip_values) / len(precip_values)
        parts.append(f"Precipitation: ~{avg_precip:.1f}mm.")

    wind_values = [snap.wind_kph for snap in snapshots.values() if snap.wind_kph is not None]
    if wind_values:
        avg_wind = sum(wind_values) / len(wind_values)
        parts.append(f"Wind: ~{avg_wind:.0f} km/h.")

    if fallback_sources:
        parts.append(
            f"Note: {len(fallback_sources)} of {len(snapshots)} source(s) returned "
            f"fallback example data ({', '.join(fallback_sources)})."
        )

    return " ".join(parts)
