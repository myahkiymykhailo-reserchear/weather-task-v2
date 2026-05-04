# Code Review — weather-prediction (initial commit)

Reviewer: senior-engineer pass over `83e3e5b` (the `main` initial commit).
Scope: full repo, with focus on correctness, production readiness, and team extensibility.
Status: code works for the happy path on the local machine; this review lists what should change before it goes near a real deployment or before more developers start adding providers on top.

Findings are grouped by severity. Each item links to file/line and includes a concrete fix. **P1** = correctness or data-loss bugs, **P2** = production readiness gaps, **P3** = architecture/extensibility, **P4** = testing gaps, **P5** = tooling.

---

## P1 — Correctness bugs

### 1.1 `build_insight` averages mixed temperature units

[app/insight.py:18-29](app/insight.py#L18-L29)

`OpenMeteoProvider` honours `transformed.units` (`celsius` / `fahrenheit`), but `wttr` always returns Celsius and `7Timer`'s `temp2m` is always Celsius regardless of the requested unit. When a user calls `/weather?units=fahrenheit`, the summary averages a Fahrenheit value from Open-Meteo with two Celsius values from the other providers and prints `°F` next to the result — silently wrong.

**Fix:** normalise every sample to a canonical unit before averaging. Either (a) always store the average internally in Celsius and convert once at output, or (b) only include providers that respect the requested unit. Add a unit-test that asserts `units=fahrenheit` does not pull `wttr`/`seven_timer` into the average without conversion.

### 1.2 `wttr` URL is not path-encoded

[app/providers/wttr.py:19](app/providers/wttr.py#L19)

```python
url = f"{settings.wttr_url}/{query.city}"
```

For cities with spaces, slashes, or diacritics (`São Paulo`, `Washington, D.C.`), this builds an invalid URL. `httpx` does some normalisation but you should not rely on it. The current test only uses `New York`, which happens to work.

**Fix:** build the URL with `httpx.URL` or `urllib.parse.quote(query.city, safe='')`. Add a test case for `Köln` / `São Paulo`.

### 1.3 `s.get("latitude") or s.get("lat")` falls through on `0.0`

[app/providers/oceandrivers.py:74-75](app/providers/oceandrivers.py#L74-L75)

```python
slat = float(s.get("latitude") or s.get("lat"))
slon = float(s.get("longitude") or s.get("lon"))
```

Python treats `0.0` as falsy, so a station that is exactly on the equator (`latitude=0.0`) would skip the canonical key and read the alias — and a station on the prime meridian gets the same fate. Same trap appears for the station identifier on [line 52](app/providers/oceandrivers.py#L52).

**Fix:** explicit `None` checks:

```python
raw_lat = s.get("latitude")
if raw_lat is None:
    raw_lat = s.get("lat")
```

### 1.4 Geocoding tie-breaker is undefined

[app/geocoding.py:53-67](app/geocoding.py#L53-L67)

When no result matches the country (e.g. Open-Meteo returns `country="Germany"` but the user typed `country="Deutschland"`), every candidate scores 0 and `max(results, key=score)` returns the first one — possibly a city of the same name in a completely different country. The user gets weather for the wrong place with no warning.

**Fix:** if the best score is 0 and a country was supplied, either (a) raise `GeocodingError` with a "country mismatch" message, or (b) attach a `low_confidence: true` flag to `TransformedInputs`. I'd lean toward (a) because silently wrong geo is worse than a 404. Test by passing a deliberate country mismatch.

### 1.5 `country` field accepts both ISO codes and free text without normalisation

[app/models.py:13](app/models.py#L13), [app/geocoding.py:50](app/geocoding.py#L50)

`"US"`, `"USA"`, and `"United States"` all reach the scorer with different match paths. `"USA"` matches neither `country_code` (`US`) nor `country` (`United States`) → score 0 → see 1.4.

**Fix:** normalise to ISO-3166 alpha-2 at the model boundary using a small lookup (or `pycountry`). Reject obviously invalid country strings up front with a 422.

---

## P2 — Production readiness

### 2.1 `httpx.AsyncClient` is created per request

[app/aggregator.py:19](app/aggregator.py#L19)

Every `/weather` call constructs and tears down a fresh client → no connection pool reuse, extra TLS handshakes, slower under load.

**Fix:** create a single `AsyncClient` in a FastAPI `lifespan` context, expose it via dependency injection, and pass it into `aggregate_weather`. Set `limits=httpx.Limits(max_connections=100, max_keepalive_connections=20)`.

### 2.2 No total request budget

[app/aggregator.py:22-24](app/aggregator.py#L22-L24)

The per-call timeout is 8 s, but `OceanDriversProvider` does two sequential GETs (stations + meteo), so its worst case is ~16 s. `asyncio.gather` waits for the slowest. A single sluggish upstream can hold the whole response.

**Fix:** wrap the gather in `asyncio.wait_for(..., timeout=total_budget)` and `return_exceptions=True` on `gather` so any provider that overran is recorded as `status="error"` rather than cancelling siblings.

### 2.3 No structured logging

[app/providers/base.py:42-47](app/providers/base.py#L42-L47)

`safe_fetch` catches every exception, formats it as a string, and returns. There is no `logger.exception(...)` call anywhere in the project. In production you cannot tell why a provider is failing without reproducing locally.

**Fix:** add `logging.getLogger(__name__)` per module; in `safe_fetch`, call `logger.warning("provider %s failed", self.name, exc_info=True)`. Configure JSON logging via `uvicorn --log-config` or `python-json-logger`.

### 2.4 Settings are hardcoded with no env-var override

[app/config.py](app/config.py)

A frozen dataclass with literal URLs and timeouts. Changing the OceanDrivers base URL (we already know it's likely wrong) requires editing source and redeploying. No way to point the service at a mock or a staging endpoint.

**Fix:** switch to `pydantic-settings.BaseSettings`. Same field names, but each one auto-reads from `WEATHER_<UPPER>` env vars. Costs ~10 lines and unlocks 12-factor config.

### 2.5 `/health` advertises readiness it doesn't verify

[app/main.py:19-21](app/main.py#L19-L21)

Returns `{"status": "ok"}` unconditionally — process is alive, but tells you nothing about whether geocoding works.

**Fix:** split into `/livez` (always 200) and `/readyz` (does a HEAD against `geocoding-api.open-meteo.com` with a 1 s timeout, returns 503 if it fails). Standard Kubernetes pattern.

### 2.6 No CORS middleware

[app/main.py](app/main.py)

If the team plans a browser-side caller, they'll hit CORS immediately.

**Fix:** add `fastapi.middleware.cors.CORSMiddleware`, default `allow_origins=[]`, set via env var.

### 2.7 No rate limiting / no auth

[app/main.py](app/main.py)

If this is exposed publicly, every `/weather` hit fans 5 upstream calls. The free APIs (`goweather.xyz`, `7timer.info`) will rate-limit *us* before we know it.

**Fix:** add `slowapi` middleware or sit behind an API gateway. Add an `X-API-Key` header check at minimum.

---

## P3 — Architecture & extensibility

### 3.1 `safe_fetch` swallows exceptions silently

[app/providers/base.py:42-47](app/providers/base.py#L42-L47)

Same lines as 2.3 but the architectural concern is different: by catching `Exception` without distinguishing, programmer errors (an `AttributeError` from a typo in a new provider) look identical to upstream 5xx. Hard to tell apart in alerting.

**Fix:** in addition to logging, classify: known-network errors (`httpx.HTTPError`, `asyncio.TimeoutError`) → `status="error"`; everything else → re-raise so the team sees real bugs in CI/dev. Optionally tag the result with `error_kind: "network" | "upstream" | "client"`.

### 3.2 `WeatherResponse.result` is `dict[str, Any]`

[app/models.py:38](app/models.py#L38)

The `summary` string is shoved into the same dict as `ProviderResult` payloads. Clients have to know that one key is a string and the others are objects. The OpenAPI schema is useless for downstream codegen.

**Fix:** introduce a typed model:

```python
class AggregatedResult(BaseModel):
    providers: dict[str, ProviderResult]
    summary: str

class WeatherResponse(BaseModel):
    raw_input: WeatherQuery
    transformed_inputs: TransformedInputs
    result: AggregatedResult
```

### 3.3 `build_insight` couples to every provider's individual schema

[app/insight.py](app/insight.py)

Each provider's response shape is inspected explicitly. Adding a sixth provider means editing this file *and* the new provider — the abstraction leaks.

**Fix:** add an optional hook to `WeatherProvider`:

```python
def extract_current_temperature_c(self, raw: Any) -> float | None: ...
```

Default returns `None`. Aggregator iterates providers, asks each for its current-temp-in-celsius, averages whatever it gets.

### 3.4 `DEFAULT_PROVIDERS` is a hardcoded list

[app/providers/__init__.py](app/providers/__init__.py)

For a project explicitly designed for team extension, this is a friction point. Two engineers adding providers in parallel will collide on this file.

**Fix:** registry decorator:

```python
PROVIDER_REGISTRY: list[type[WeatherProvider]] = []

def register(cls):
    PROVIDER_REGISTRY.append(cls)
    return cls

@register
class OpenMeteoProvider(WeatherProvider): ...
```

Or use `importlib.metadata` entry points if external plugins are wanted later.

### 3.5 Open-Meteo is both geocoder and a provider — single point of failure

[app/aggregator.py:20](app/aggregator.py#L20), [app/main.py:39-40](app/main.py#L39-L40)

If `geocoding-api.open-meteo.com` is down, the endpoint returns 404 even though the other four providers might still respond (some — `wttr` — accept city names directly).

**Fix:** options, in order of complexity:
1. Allow the user to provide `lat` + `lon` directly, bypassing geocoding;
2. Add a fallback geocoder (Nominatim is free for low volume);
3. Cache successful geocoding results for ~24 h (Redis or `cachetools.TTLCache`).

### 3.6 Provider response shapes are not normalised

[app/providers/](app/providers/)

Every provider returns its raw upstream JSON. Downstream consumers have to learn five different schemas to read "current temperature." Acceptable for v0 (preserves data), but plan a v1 normalised envelope.

**Fix:** alongside the raw payload, return a small typed `Normalized` block per provider with `temperature_c`, `wind_kph`, `summary_text` where available.

---

## P4 — Testing gaps

### 4.1 `insight.py` has no direct tests

Only covered indirectly through `tests/test_api.py`, which mocks all providers with the same shape every time. Edge cases (no samples, malformed data, mixed units — see 1.1) are unverified.

**Fix:** add `tests/test_insight.py` with cases: empty results, all-error results, mixed-unit averaging (regression test for 1.1), missing daily data.

### 4.2 No timeout test

`safe_fetch` is supposed to convert an upstream timeout into `status="error"`. No test verifies this. respx supports `side_effect=httpx.ReadTimeout(...)`.

### 4.3 No test for cities with spaces / diacritics

See 1.2.

### 4.4 No test for the all-zero-score geocoding tie-break

See 1.4.

### 4.5 No live / contract test

Every test mocks the upstream. The team won't notice when goweather.xyz changes its response shape until users complain. Add an opt-in `pytest -m live` suite (one test per provider) that runs against the real APIs in a nightly CI job — it should not gate PRs.

### 4.6 No load / concurrency test

The point of the parallel fan-out is throughput. Locust / wrk smoke test (~50 RPS for 30 s) before the first deploy would catch obvious leaks (e.g. the per-request `AsyncClient` in 2.1).

---

## P5 — Tooling & developer experience

### 5.1 No linter or formatter

[pyproject.toml](pyproject.toml)

For a team-extended codebase, agree on style up front to avoid drift. Suggest `ruff check` + `ruff format` — fast, single tool, replaces black + isort + flake8.

**Fix:** add to `[project.optional-dependencies].dev` and a `lint` job in CI.

### 5.2 No type checker

`mypy --strict app` (or `pyright`) on this code would surface 1.3 (the `or 0.0` falsy pitfall) once the dict types are tightened. Worth wiring up before the codebase grows.

### 5.3 CI matrix includes Python 3.9 (past EOL)

[.github/workflows/ci.yml](.github/workflows/ci.yml#L19)

Python 3.9 reached EOL Oct 2025. Keeping it in the matrix slows CI for no real coverage benefit.

**Fix:** drop 3.9 from the matrix and bump `requires-python = ">=3.10"` in `pyproject.toml`. (Was lowered to 3.9 only because the local laptop happens to have 3.9; CI has all versions.)

### 5.4 No Dockerfile

[.github/workflows/ci.yml](.github/workflows/ci.yml)

The CI's `deploy` job builds an sdist + wheel and stops. Without a Dockerfile, "deploy" is a hand-wave. Add a slim `python:3.12-slim` Dockerfile and have the deploy job push to GHCR; that turns the placeholder step into a working artifact.

### 5.5 `requires-python` mismatch

[pyproject.toml:5](pyproject.toml#L5)

Declares `>=3.9`; the codebase uses PEP 585 generics (`dict[str, Any]`, `list[X]`) which only became runtime-evaluable in 3.9, but lint tools targeting older stdlibs will warn. Either add `from __future__ import annotations` to every module or bump the floor (recommended; see 5.3).

### 5.6 Deploy job in CI is unlabelled placeholder

[.github/workflows/ci.yml](.github/workflows/ci.yml)

Reads as a real deploy step but only `echo`s. Add an explicit `# TODO(team): wire real target` comment and consider renaming the job `build-artifact` until it actually deploys, so green CI on `main` doesn't lull the team into a false sense of "shipped."

---

## Summary of recommended next sprint

If I were ordering the work:

1. **1.1, 1.2, 1.3, 1.4** — bugs that produce wrong answers. Half a day.
2. **2.1, 2.2, 2.3, 2.4** — get to "deployable" baseline. One day.
3. **3.2, 3.3, 3.4** — clean up the team-extension surface before the second engineer touches it. Half a day.
4. **5.1, 5.2** — lint + type check in CI. Two hours.
5. Everything else as it becomes painful.

Estimated: 2–3 days of focused work to take this from "demo" to "could responsibly deploy behind an API gateway."
