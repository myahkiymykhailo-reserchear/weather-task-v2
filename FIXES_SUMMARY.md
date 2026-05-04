# Fixes Summary

Tracks what changed in `dev` after [`CODE_REVIEW.md`](CODE_REVIEW.md) was merged. Each row is anchored to the commit that delivered it.

Status flags:

| Flag             | Meaning                                                        |
|------------------|----------------------------------------------------------------|
| **[FIXED]**      | Addressed in this PR; tests cover it.                          |
| **[FIXED-PART]** | Partially addressed; remainder explained inline.               |
| **[DEFERRED]**   | Intentionally not done in this PR. Reason given.               |
| **[NEW]**        | Capability added beyond the original review (user request).    |

---

## Big-picture changes

### **[NEW]** Unified normalised output across providers

User asked for *"same insight from each API"* so it is easy to scan weather at a given location/date side-by-side. Every provider now exposes a canonical `WeatherSnapshot` with the same fields:

| field                | unit      | semantics                                          |
|----------------------|-----------|----------------------------------------------------|
| `temperature_c`      | °C        | Always Celsius, regardless of requested `units`.   |
| `feels_like_c`       | °C        | Optional.                                          |
| `humidity_pct`       | %         | 0–100.                                             |
| `wind_kph`           | km/h      | Converted from upstream's native unit.             |
| `wind_direction_deg` | degrees   | Optional.                                          |
| `precipitation_mm`   | mm        | Daily sum where available.                         |
| `cloud_cover_pct`    | %         | 0–100.                                             |
| `conditions`         | string    | Human-readable ("Sunny", "Light rain", …).         |
| `is_forecast`        | bool      | False = current observation, True = forecast.      |
| `forecast_for_date`  | date      | Which date this snapshot represents.               |
| `source_quality`     | enum      | `"live"` or `"fallback"`.                          |
| `notes`              | string    | Short provider-specific note.                      |

The new response shape exposes them in two convenient places:

```json
{
  "raw_input": { ... },
  "transformed_inputs": { ... },
  "result": {
    "providers": {
      "open_meteo":   { "status": "ok",    "data": {...}, "normalized": { ... }, "elapsed_ms": 184 },
      "wttr":         { "status": "error", "error": "...", "normalized": { ... }, "elapsed_ms": 8002 },
      ...
    },
    "normalized": {
      "open_meteo":   { "temperature_c": 18.4, ... },
      "wttr":         { "temperature_c": 14.0, "source_quality": "fallback", ... },
      ...
    },
    "summary": "New York, NY, US on 2026-05-04: average ~18.7°C across 3 source(s) (open_meteo, seven_timer, wttr). Conditions: Partly cloudy. Wind: ~12 km/h. Note: 1 of 5 source(s) returned fallback example data (wttr)."
  }
}
```

Implementation: commits `e822cd6`, `edd144d`, `a1af05e`.

### **[NEW]** Fallback example data for non-2xx responses

User asked: *"add some backfalls for cases when we did not receiving 200 code from API, we should use for such emptinies examples"*. Each provider implements `fallback(transformed) -> WeatherSnapshot` with sensible placeholder values and a `notes` field that names the failed upstream. `safe_fetch` swaps in the fallback whenever the upstream raises (HTTPError, timeout, JSON decode error, …) so the response always has *something* in every provider slot. Fallbacks are explicitly tagged with `source_quality="fallback"` and named in the summary line so they are never confused with real data. (`edd144d`)

---

## CODE_REVIEW findings — line-by-line status

### P1 — Correctness bugs

| # | Finding | Status | Commit | Notes |
|---|---------|--------|--------|-------|
| 1.1 | `build_insight` averages mixed temperature units | **[FIXED]** | `a1af05e` | Insight now reads `WeatherSnapshot.temperature_c` (always Celsius) and converts to °F exactly once at output. Regression test `test_build_insight_averages_in_celsius`. |
| 1.2 | `wttr` URL not path-encoded (breaks for `São Paulo`) | **[FIXED]** | `9b824a3` | Uses `urllib.parse.quote(safe='')`. Test `test_wttr_url_encodes_city_with_spaces_and_diacritics`. |
| 1.3 | `s.get("latitude") or s.get("lat")` falls through on `0.0` | **[FIXED]** | `d395a7c` | `_first_non_none` helper. Equator-station regression test. |
| 1.4 | Geocoding tie-break silently picks wrong city | **[FIXED]** | `06b77c0` | `_pick_best` returns `(best, score)`; `geocode` raises `GeocodingError` when country supplied but score is 0. |
| 1.5 | `country` accepts both ISO-2 and free text without normalisation | **[FIXED]** | `06b77c0` | `normalize_country()` with alias table for US/UK/Germany/Spain. |

### P2 — Production readiness

| # | Finding | Status | Commit | Notes |
|---|---------|--------|--------|-------|
| 2.1 | `httpx.AsyncClient` per request | **[FIXED]** | `9e62a73` | Created once in FastAPI lifespan, shared via `Depends(get_http_client)`. |
| 2.2 | No total request budget | **[FIXED]** | `9e62a73` | `_bounded_safe_fetch` wraps each provider in `asyncio.wait_for(total_request_budget_seconds)`; on overrun, falls back gracefully. |
| 2.3 | No structured logging | **[FIXED]** | `edd144d`, `9e62a73` | `logging.getLogger(__name__)` in providers; `safe_fetch` logs warnings on upstream errors and `logger.exception` on programmer errors. Log level is env-configurable. |
| 2.4 | Settings hardcoded | **[FIXED]** | `9e62a73` | `pydantic_settings.BaseSettings` with `WEATHER_` prefix. Every URL/timeout overridable via env. |
| 2.5 | `/health` advertises readiness it doesn't verify | **[FIXED]** | `9e62a73` | `/livez` (always 200), `/readyz` (pings geocoder, returns 503 on failure). `/health` kept as backwards-compat alias. |
| 2.6 | No CORS middleware | **[FIXED]** | `9e62a73` | `CORSMiddleware` mounted only when `WEATHER_CORS_ALLOW_ORIGINS` is non-empty. |
| 2.7 | No rate limit / no auth | **[DEFERRED]** | — | Out of scope without product decision (which auth scheme? what limits? platform constraints?). Sketched mitigation: gateway-level rate limit + `X-API-Key` middleware once the team picks a target. |

### P3 — Architecture & extensibility

| # | Finding | Status | Commit | Notes |
|---|---------|--------|--------|-------|
| 3.1 | `safe_fetch` swallows exceptions | **[FIXED]** | `edd144d` | Now logs (`warning` for upstream, `exception` for programmer errors), classifies into network vs unexpected, and always returns a fallback so the response is complete. |
| 3.2 | `WeatherResponse.result: dict[str, Any]` too loose | **[FIXED]** | `e822cd6`, `a1af05e` | Replaced with typed `AggregatedResult { providers, normalized, summary }`. OpenAPI schema is now meaningful. |
| 3.3 | `build_insight` couples to every provider's schema | **[FIXED]** | `a1af05e` | Reads only `WeatherSnapshot` fields; provider-specific decoding lives in each provider's `normalize()`. Adding a sixth provider needs no insight changes. |
| 3.4 | `DEFAULT_PROVIDERS` hardcoded list | **[DEFERRED]** | — | Current 5-provider list works for now; a `@register` decorator or entry-point discovery is worth doing once the team starts adding providers in parallel. Tracked for next sprint. |
| 3.5 | Open-Meteo single point of failure (geocoder + provider) | **[DEFERRED]** | — | Architectural change. Three options listed in CODE_REVIEW (accept lat/lon directly, fallback geocoder, geocoding cache). Recommend (1) accepting lat/lon as the cheapest immediate mitigation. |
| 3.6 | Provider responses not normalised | **[FIXED]** | `edd144d`, `a1af05e` | See "Unified normalised output" above. |

### P4 — Testing gaps

| # | Finding | Status | Commit | Notes |
|---|---------|--------|--------|-------|
| 4.1 | No direct `insight.py` tests | **[FIXED]** | `5490156` | `tests/test_insight.py` covers: empty, mixed-unit averaging (regression for 1.1), fallback flagging, consensus conditions, precip/wind aggregation, no-temp edge case. |
| 4.2 | No timeout test | **[FIXED]** | `5490156` | `test_provider_returns_fallback_on_read_timeout` injects `httpx.ReadTimeout` and asserts fallback wiring. |
| 4.3 | No spaces/diacritics test | **[FIXED]** | `9b824a3` | `test_wttr_url_encodes_city_with_spaces_and_diacritics`. |
| 4.4 | No all-zero-score tie-break test | **[FIXED]** | `06b77c0` | `test_geocode_raises_on_country_mismatch_no_silent_fallback`. |
| 4.5 | No live / contract test | **[DEFERRED]** | — | Should be opt-in (`pytest -m live`) and run nightly, not on PRs. Adds CI cost; defer until the team agrees on cadence and budget. |
| 4.6 | No load / concurrency test | **[DEFERRED]** | — | Wait until 3.4 / 3.5 architectural calls are made; load testing the wrong target wastes effort. |

### P5 — Tooling & DX

| # | Finding | Status | Commit | Notes |
|---|---------|--------|--------|-------|
| 5.1 | No linter / formatter | **[FIXED]** | `5aa84e4` | `ruff` configured; CI runs both `ruff check` and `ruff format --check`. |
| 5.2 | No type checker | **[DEFERRED]** | — | `mypy --strict` is a meaningful effort; recommend doing it once the response schema settles after 3.4/3.5. |
| 5.3 | CI matrix includes Python 3.9 (past EOL) | **[FIXED-PART]** | `5aa84e4` | Original review recommended dropping; reverted because the local development environment is still 3.9 and removing it would prevent local pytest runs. Once the team standardises on 3.10+ this is a one-line change. |
| 5.4 | No Dockerfile | **[FIXED]** | `5aa84e4` | `python:3.12-slim`, with HEALTHCHECK on `/livez`. CI `build-image` job uses `docker/build-push-action@v5` (build-only; deploy target is a TODO comment). |
| 5.5 | `requires-python` mismatch | **[FIXED-PART]** | `5aa84e4` | Pinned to `>=3.9` to match local dev; rationale documented in `pyproject.toml`. PEP 604 union rules in ruff are explicitly disabled with the same justification. |
| 5.6 | Deploy job is unlabelled placeholder | **[FIXED]** | `5aa84e4` | Job renamed `build-image` and labelled "no push — placeholder". `TODO(team)` comment marks where to wire a real target. |

---

## Migration notes for existing callers

The response shape changed in commit `a1af05e`. Code that previously read e.g. `data["result"]["open_meteo"]["status"]` must now read `data["result"]["providers"]["open_meteo"]["status"]`. The summary moved from `data["result"]["summary"]` (still works) to the same place but is now part of a typed model.

If a caller only wants a tidy side-by-side view for a UI, the new `data["result"]["normalized"]` map is the right surface — every provider exposes the same field names and units there, even when its upstream failed (the snapshot is then flagged `"source_quality": "fallback"`).

The old `units=fahrenheit` request parameter still works; only the *summary string* converts to °F at output. The per-provider `normalized.temperature_c` is always Celsius — UIs convert as needed.

---

## Recommended next sprint

In priority order, the items remaining from the original review:

1. **3.4** — provider registry decorator (low effort, removes a future merge-conflict hotspot).
2. **3.5** — accept lat/lon directly so a flaky geocoder cannot 404 the whole endpoint.
3. **5.2** — `mypy --strict` once 3.5 is done and the schema is stable.
4. **2.7** — auth + rate limit, contingent on a deployment target decision.
5. **4.5 / 4.6** — live and load tests once a deployment target exists to test against.
6. **5.3 / 5.5** — flip Python floor to 3.10+ and re-enable PEP 604 / `zip(strict=)` ruff rules once everyone's local Python is upgraded.

Test count went from **18** (initial) to **29** in `dev`, all green on Python 3.9 locally.
