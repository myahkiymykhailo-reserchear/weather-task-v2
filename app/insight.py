import re
from typing import Any, Optional

from app.models import TransformedInputs


def build_insight(transformed: TransformedInputs, results: dict[str, Any]) -> str:
    """Produce a short human-friendly summary across providers that returned data."""
    samples: list[tuple[str, float]] = []

    om = results.get("open_meteo") or {}
    if om.get("status") == "ok":
        cur = (om.get("data") or {}).get("current") or {}
        t = cur.get("temperature_2m")
        if isinstance(t, (int, float)):
            samples.append(("open_meteo", float(t)))

    wttr = results.get("wttr") or {}
    if wttr.get("status") == "ok":
        t = (wttr.get("data") or {}).get("temperature")
        n = _extract_temp_number(t) if isinstance(t, str) else None
        if n is not None:
            samples.append(("wttr", n))

    seven = results.get("seven_timer") or {}
    if seven.get("status") == "ok":
        series = (seven.get("data") or {}).get("dataseries") or []
        if series and isinstance(series[0].get("temp2m"), (int, float)):
            samples.append(("seven_timer", float(series[0]["temp2m"])))

    unit_label = "°C" if transformed.units == "celsius" else "°F"
    location = transformed.resolved_name or f"({transformed.lat:.2f}, {transformed.lon:.2f})"

    if not samples:
        return f"No temperature samples available for {location} on {transformed.date}."

    avg = sum(t for _, t in samples) / len(samples)
    sources = ", ".join(s for s, _ in samples)
    pieces = [
        f"{location} on {transformed.date}: average ~{avg:.1f}{unit_label} "
        f"across {len(samples)} source(s) ({sources})."
    ]
    daily_extra = _describe_open_meteo_daily(om, unit_label)
    if daily_extra:
        pieces.append(daily_extra)
    return " ".join(pieces)


def _extract_temp_number(s: Optional[str]) -> Optional[float]:
    if not s:
        return None
    m = re.search(r"-?\d+(?:\.\d+)?", s)
    return float(m.group()) if m else None


def _describe_open_meteo_daily(om: dict, unit_label: str) -> str:
    if om.get("status") != "ok":
        return ""
    daily = (om.get("data") or {}).get("daily") or {}
    tmax = (daily.get("temperature_2m_max") or [None])[0]
    tmin = (daily.get("temperature_2m_min") or [None])[0]
    precip = (daily.get("precipitation_sum") or [None])[0]
    parts = []
    if tmin is not None and tmax is not None:
        parts.append(f"high {tmax}{unit_label} / low {tmin}{unit_label}")
    if precip is not None:
        parts.append(f"precipitation {precip} mm")
    return ("Open-Meteo daily: " + ", ".join(parts) + ".") if parts else ""
