# weather-prediction

A small FastAPI service that takes human-friendly inputs (`city`, `state`, `country`, `date`, `units`) and returns weather data **aggregated in parallel** from five public APIs, with a unified per-provider snapshot you can scan side-by-side. Ships with a **browser UI** at `/` and is deployable as a Docker container; the UI can additionally be published to GitHub Pages.

- **Geocoding** is done first via Open-Meteo (sequential).
- **5 weather providers** then run concurrently via `asyncio.gather`: Open-Meteo (forecast), wttr.in, openSenseMap (citizen-science sensors), OceanDrivers (Spanish marine), 7Timer.
- **Per-provider failures are isolated** — a non-2xx upstream is converted into a fallback `WeatherSnapshot` (clearly tagged `source_quality="fallback"`) so the response is always complete.

> The response shape changed in `v0.2`: `result.providers`, `result.normalized`, `result.summary` — see [FIXES_SUMMARY.md](FIXES_SUMMARY.md) if you're upgrading.

### Provider notes

- **wttr** uses [`wttr.in`](https://wttr.in/) (the well-maintained `chubin/wttr.in`). The originally-listed `robertoduessmann/weather-api` host (`goweather.xyz`) has been offline since 2026-05; every path returns 404.
- **OceanDrivers** is regional — its public API effectively serves a single station at Palma de Mallorca. For queries within ~200 km of Palma the provider returns live AEMET station data; further away it returns a "covered region" notice (still `source_quality="live"`, just `temperature_c=null`). Tunable via `WEATHER_OCEANDRIVERS_MAX_STATION_KM`.
- **openSenseMap** does a two-step fetch (fast minimal list + parallel detail) to stay well under the request budget even in dense areas.

---

## Requirements

- **Python 3.9+** (3.10+ recommended)
- macOS / Linux (Windows works too — the commands below assume bash/zsh)
- An internet connection for the upstream APIs
- Optional: Docker, if you want to run the container

---

## Quick start

```bash
git clone https://github.com/myahkiymykhailo-reserchear/weather-task-v2.git
cd weather-task-v2
git checkout dev

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

uvicorn app.main:app --reload
```

Server is now on **http://127.0.0.1:8000**. In another terminal:

```bash
curl 'http://127.0.0.1:8000/weather?city=Berlin&country=DE'
```

OpenAPI / Swagger UI: **http://127.0.0.1:8000/docs**
Browser UI: **http://127.0.0.1:8000/** (described below).

---

## The browser UI

Open **http://127.0.0.1:8000/** in a browser. The page shows a short *How to use* block, a collapsible *Use from terminal / Postman* reference, and the form. The submit button stays disabled until both `city` and `country` are filled in.

After submit you'll see five panels appear in sequence:

1. **Transformed input (geocoded)** — the resolved name, lat/lon, timezone, country code, target date and units that the API derived from your raw input.
2. **Provider fan-out** — five cards, one per upstream API. Each animates from "loading" to "complete" in order of its server-reported `elapsed_ms`, so you can watch the parallel fan-out unfold visually. Cards are colour-coded: green = live, amber = fallback example data, red = hard error (still with a fallback snapshot).
3. **Parallelism proof** — three numbers (sum of all `elapsed_ms` if sequential, actual JS-measured wall-clock, computed speedup) plus a horizontal bar chart with one bar per provider scaled to the longest one.
4. **Aggregated summary** — the human sentence the API already produces.
5. **Per-API details** — each provider's normalised snapshot (temperature, humidity, wind, conditions, fallback-flag, notes) and its raw upstream response in a collapsible panel.

### "API server" field

At the top of the form there is an *API server* input. Default behaviour:

- Empty (= same origin) when the page is served by FastAPI itself.
- `http://127.0.0.1:8000` when the page is served from `*.github.io`.

You can override via `?api=https://my-api.example.com` in the URL or by typing in the field; the value persists in `localStorage`. This is what makes the UI work both locally and when published to GitHub Pages.

---

## Detailed setup

### 1. Get the code

```bash
git clone https://github.com/myahkiymykhailo-reserchear/weather-task-v2.git
cd weather-task-v2
git checkout dev
```

### 2. Create a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate     # on Windows: .venv\Scripts\activate
```

Verify Python is at least 3.9:

```bash
python --version
```

### 3. Install dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Run the server

```bash
uvicorn app.main:app --reload
```

`--reload` re-loads the app whenever you save a file. Drop it for a stable run:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### 5. (Optional) configure via environment variables

Every setting is overridable. All env vars use the `WEATHER_` prefix:

| Variable                                  | Default                                              | What it does                                       |
|-------------------------------------------|------------------------------------------------------|----------------------------------------------------|
| `WEATHER_REQUEST_TIMEOUT_SECONDS`         | `8.0`                                                | Per-call HTTP timeout to each upstream.            |
| `WEATHER_TOTAL_REQUEST_BUDGET_SECONDS`    | `12.0`                                               | Hard cap per provider; on overrun, returns fallback. |
| `WEATHER_LOG_LEVEL`                       | `INFO`                                               | `DEBUG` to see every upstream call.                |
| `WEATHER_CORS_ALLOW_ORIGINS`              | `""`                                                 | Comma-separated explicit origin allow-list. Use for production lock-down. |
| `WEATHER_CORS_ALLOW_ORIGIN_REGEX`         | localhost + `*.github.io` (see below)                | Regex matched against `Origin`. Default permits dev origins; set to `""` to disable. |
| `WEATHER_GEOCODING_URL`                   | Open-Meteo geocoding                                 | Swap geocoder.                                     |
| `WEATHER_OPEN_METEO_FORECAST_URL`         | Open-Meteo forecast                                  |                                                    |
| `WEATHER_WTTR_URL`                        | `https://goweather.xyz/weather`                      |                                                    |
| `WEATHER_OPENSENSEMAP_URL`                | `https://api.opensensemap.org/boxes`                 |                                                    |
| `WEATHER_SEVEN_TIMER_URL`                 | `https://www.7timer.info/bin/api.pl`                 |                                                    |
| `WEATHER_OCEANDRIVERS_STATIONS_URL`       | `https://api.oceandrivers.com/v1.0/getStations/`     |                                                    |
| `WEATHER_OCEANDRIVERS_MAX_STATION_KM`     | `100.0`                                              | Skip OceanDrivers if no station within this range. |

Example:

```bash
WEATHER_REQUEST_TIMEOUT_SECONDS=15 \
WEATHER_LOG_LEVEL=DEBUG \
uvicorn app.main:app --reload
```

---

## API reference (compact)

### `GET /weather`

| Query param | Required | Type    | Default       | Notes                                                       |
|-------------|----------|---------|---------------|-------------------------------------------------------------|
| `city`      | yes      | string  | —             | Free text. UTF-8 OK (`São Paulo`, `Köln`).                 |
| `country`   | yes      | string  | —             | ISO-2 (`US`, `DE`, `JP`) or free text (`Germany`, `USA`).   |
| `state`     | no       | string  | —             | State / region; helps disambiguate (`Springfield, IL`).     |
| `date`      | no       | date    | today         | `YYYY-MM-DD`. Open-Meteo / 7Timer forecast on this date.    |
| `units`     | no       | string  | `celsius`     | `celsius` or `fahrenheit`. Affects only the summary line; `result.normalized.*.temperature_c` is always Celsius. |

**Response shape:**

```json
{
  "raw_input": { "city": "...", "country": "...", "state": null, "date": null, "units": "celsius" },
  "transformed_inputs": {
    "lat": 52.52, "lon": 13.41, "timezone": "Europe/Berlin",
    "resolved_name": "Berlin, State of Berlin, Germany",
    "country_code": "DE", "date": "2026-05-04", "units": "celsius"
  },
  "result": {
    "providers": {
      "open_meteo":   { "status": "ok",    "data": { ... raw upstream ... }, "normalized": { ... }, "elapsed_ms": 184 },
      "wttr":         { "status": "error", "error": "ReadTimeout: ...",       "normalized": { ... }, "elapsed_ms": 8002 },
      "opensensemap": { "status": "ok",    "data": { ... }, "normalized": { ... }, "elapsed_ms": 410 },
      "oceandrivers": { "status": "ok",    "data": { ... }, "normalized": { ... }, "elapsed_ms": 322 },
      "seven_timer":  { "status": "ok",    "data": { ... }, "normalized": { ... }, "elapsed_ms": 240 }
    },
    "normalized": {
      "open_meteo":   { "temperature_c": 18.4, "humidity_pct": 65, "wind_kph": 12, "conditions": "Partly cloudy", "source_quality": "live", ... },
      "wttr":         { "temperature_c": 14.0, "wind_kph":  8.0, "conditions": "Sunny (example)", "source_quality": "fallback", "notes": "goweather.xyz unavailable; placeholder example data." },
      ...
    },
    "summary": "Berlin, State of Berlin, Germany on 2026-05-04: average ~18.7°C across 4 source(s) (open_meteo, opensensemap, oceandrivers, seven_timer). Conditions: Partly cloudy. Wind: ~12 km/h. Note: 1 of 5 source(s) returned fallback example data (wttr)."
  }
}
```

**Error responses:**

- `404` — geocoder found no city, **or** country was supplied but no result matched it (with a helpful message naming the top candidate).
- `422` — query validation failed (missing `city` or `country`, or invalid `date`).
- `503` — only on `/readyz` when the geocoder is unreachable.

### `GET /livez`, `GET /readyz`, `GET /health`

| Endpoint   | Purpose                                                          |
|------------|------------------------------------------------------------------|
| `/livez`   | Process is alive. Always 200 unless the process is dead.         |
| `/readyz`  | Pings the geocoder; 503 if it is unreachable. K8s readiness.     |
| `/health`  | Backwards-compat alias of `/livez`.                              |

---

## 5 usage examples

> Examples assume the server is running on `http://127.0.0.1:8000`. Pipe through `python -m json.tool` (built-in) or `jq` to pretty-print.

### Example 1 — Quick happy path: current weather for Berlin

The simplest possible call. Defaults to today and Celsius.

```bash
curl -s 'http://127.0.0.1:8000/weather?city=Berlin&country=DE' | python -m json.tool
```

What you get:
- `transformed_inputs.lat` ≈ `52.52`, `lon` ≈ `13.41`
- All 5 providers attempted in parallel
- `result.summary` reads like `"Berlin, State of Berlin, Germany on 2026-05-04: average ~18.7°C across 4 source(s) ..."`
- Any provider that 404s / times out shows `status: "error"` but still has a `normalized` snapshot tagged `source_quality: "fallback"`

### Example 2 — Disambiguating with `state`

Springfield exists in many US states. Without `state`, the geocoder returns the most-populous match; `state` pins the city you mean.

```bash
curl -s 'http://127.0.0.1:8000/weather?city=Springfield&state=Illinois&country=US' \
  | python -m json.tool
```

Watch `transformed_inputs.resolved_name` — it should say `Springfield, Illinois, United States`. Compare with `state=Massachusetts` to see the geocoder pick a completely different lat/lon.

### Example 3 — Forecast for a future date

`date` ISO-formatted. Open-Meteo and 7Timer forecasts will populate `result.normalized.*` for that date.

```bash
# Day-of-week-after-tomorrow, here as a literal date — adjust as needed.
curl -s 'http://127.0.0.1:8000/weather?city=Paris&country=FR&date=2026-05-10' \
  | python -m json.tool
```

Look at `result.normalized.open_meteo.is_forecast` — should be `true`. The summary line uses the forecast date.

### Example 4 — Fahrenheit units, looking only at the normalised side-by-side view

`units=fahrenheit` only changes how the **summary string** is rendered. The per-provider `temperature_c` in `normalized` stays Celsius, so consumers can do their own conversion.

```bash
# Pretty side-by-side view of just the normalized snapshots:
curl -s 'http://127.0.0.1:8000/weather?city=Tokyo&country=JP&units=fahrenheit' \
  | python -c 'import json,sys; d=json.load(sys.stdin); print(json.dumps(d["result"]["normalized"], indent=2))'

# Just the summary:
curl -s 'http://127.0.0.1:8000/weather?city=Tokyo&country=JP&units=fahrenheit' \
  | python -c 'import json,sys; print(json.load(sys.stdin)["result"]["summary"])'
```

The summary will say `~XX.X°F`; the underlying `temperature_c` numbers are still Celsius. P1.1 fix in [FIXES_SUMMARY.md](FIXES_SUMMARY.md).

### Example 5 — City name with spaces and diacritics

Cities with non-ASCII names are URL-encoded by the service. Easiest from the shell with `curl -G --data-urlencode`:

```bash
curl -sG 'http://127.0.0.1:8000/weather' \
  --data-urlencode 'city=São Paulo' \
  --data-urlencode 'country=BR' \
  | python -m json.tool
```

`transformed_inputs.resolved_name` should read `São Paulo, São Paulo, Brazil`. Try `Köln`, `Москва`, `北京` for further proof. (P1.2 fix.)

---

## Running the tests

```bash
pytest -v
```

Expected: **31 passed**.

Run a subset:

```bash
pytest tests/test_insight.py -v          # just insight tests
pytest -k geocoding -v                    # any test with "geocoding" in the name
```

---

## Linting and formatting

```bash
pip install -r requirements.txt        # ruff is in the dev extras
ruff check app tests                   # static checks
ruff format app tests                  # auto-format (apply changes)
ruff format --check app tests          # CI-style: fail if reformat needed
```

CI runs both `ruff check` and `ruff format --check` and gates the test job behind it.

---

## Running with Docker

The recommended path is `docker compose`, which wires environment variables, port mapping, healthcheck, and DNS in one file.

```bash
docker compose up --build
# in another terminal:
curl 'http://127.0.0.1:8000/livez'
curl 'http://127.0.0.1:8000/weather?city=Berlin&country=DE'
```

Why use compose: macOS Docker (and corporate VPNs) sometimes pushes IPv6-only DNS into the Docker VM, which intermittently fails to resolve the upstream provider hosts. [`docker-compose.yml`](docker-compose.yml) pins public resolvers (`1.1.1.1` and `8.8.8.8`) so the container reproducibly reaches the APIs regardless of host network state. Comment the `dns:` block out if your environment already resolves cleanly.

You can also build and run without compose:

```bash
docker build -t weather-prediction:dev .
docker run --rm -p 8000:8000 \
  -e WEATHER_LOG_LEVEL=INFO \
  weather-prediction:dev
```

The image:

- Runs as a non-root user (`app`, uid 1000) for defense-in-depth.
- Uses [`tini`](https://github.com/krallin/tini) as PID 1 so signals are forwarded promptly (Ctrl-C / `docker stop` shuts uvicorn down quickly).
- Has a `HEALTHCHECK` that pings `/livez` every 30 s.

Environment variables are listed in the [Detailed setup → Configuration](#5-optional-configure-via-environment-variables) section above.

---

## Hosting the UI on GitHub Pages

The `app/static/` UI is published to GitHub Pages on every push to `main` by [`.github/workflows/pages.yml`](.github/workflows/pages.yml). Once enabled, the site lives at `https://USER.github.io/weather-task-v2/`.

**One-time enable on GitHub:**

1. Repository → *Settings* → *Pages*.
2. Set *Source* to **GitHub Actions**.
3. Push to `main` (or trigger the workflow manually from the *Actions* tab).

**Connecting the hosted UI to your API:**

The Pages site only contains the UI — there is no FastAPI backend on `github.io`. Two options:

1. **Run the API locally** (simplest, good for personal use). Just run:

   ```bash
   uvicorn app.main:app
   ```

   The default CORS configuration already accepts `localhost` and `*.github.io` origins, so the Pages UI can call the local API with no extra setup. Open the Pages URL — the *API server* field is pre-filled with `http://127.0.0.1:8000` automatically when on `*.github.io`.

2. **Host the API somewhere reachable** (Fly.io, Cloud Run, Render, …) and set the *API server* field on the Pages UI to that URL. For production, lock down CORS to your specific UI origin:

   ```bash
   WEATHER_CORS_ALLOW_ORIGINS="https://your-ui.example.com" \
     WEATHER_CORS_ALLOW_ORIGIN_REGEX="" \
     uvicorn app.main:app
   ```

The *API server* field value persists in `localStorage`, and you can also pre-fill it via `?api=https://my-api.example.com` in the page URL.

---

## Project layout

```
weather-task-v2/
├── app/
│   ├── main.py            # FastAPI app, lifespan, /weather + /livez + /readyz + UI mount
│   ├── aggregator.py      # asyncio.gather fan-out + total-budget guard
│   ├── geocoding.py       # Open-Meteo geocoder + country normalisation
│   ├── insight.py         # Build human-readable summary from snapshots
│   ├── models.py          # WeatherQuery, WeatherSnapshot, AggregatedResult, ...
│   ├── config.py          # Settings (pydantic-settings) — env-var driven
│   ├── providers/
│   │   ├── base.py        # WeatherProvider ABC + safe_fetch wrapper
│   │   ├── open_meteo.py
│   │   ├── wttr.py        # uses wttr.in (?format=j1)
│   │   ├── opensensemap.py # two-step fetch: minimal list + parallel detail
│   │   ├── oceandrivers.py # AreaPalma AEMET station; regional (Spanish marine)
│   │   └── seven_timer.py
│   └── static/
│       ├── index.html     # browser UI served at /
│       ├── style.css
│       └── app.js
├── tests/                 # 31 tests across providers, insight, geocoding, API
├── .github/workflows/
│   ├── ci.yml             # lint + test (Py 3.9–3.12) + build-image
│   └── pages.yml          # publish UI to GitHub Pages on push to main
├── Dockerfile             # python:3.12-slim, non-root, tini, curl healthcheck
├── docker-compose.yml     # one-command run with pinned DNS resolvers
├── pyproject.toml
├── requirements.txt
├── CODE_REVIEW.md         # Senior-engineer review (the inputs to v0.2)
└── FIXES_SUMMARY.md       # What changed in v0.2, anchored to commits
```

---

## Adding a new provider

The team-extension surface is the `WeatherProvider` ABC.

1. Create `app/providers/your_provider.py`:

   ```python
   import httpx
   from app.providers.base import WeatherProvider
   from app.models import WeatherSnapshot

   class YourProvider(WeatherProvider):
       name = "your_provider"

       async def fetch(self, client, query, transformed):
           resp = await client.get("https://your.api/endpoint", ...)
           resp.raise_for_status()
           return resp.json()

       def normalize(self, raw, transformed) -> WeatherSnapshot:
           return WeatherSnapshot(
               temperature_c=raw["temp_celsius"],
               # ... whichever canonical fields you can populate
               is_forecast=False,
               forecast_for_date=transformed.date,
               source_quality="live",
           )

       def fallback(self, transformed) -> WeatherSnapshot:
           return WeatherSnapshot(
               temperature_c=15.0,
               source_quality="fallback",
               notes="your_provider unavailable; placeholder example data.",
               forecast_for_date=transformed.date,
           )
   ```

2. Register in `app/providers/__init__.py`:

   ```python
   from app.providers.your_provider import YourProvider
   DEFAULT_PROVIDERS.append(YourProvider())
   ```

3. Add tests in `tests/test_providers.py` — happy path, fallback path, normalisation.

The aggregator and `build_insight` need no changes; they read snapshots, not raw schemas.

---

## Troubleshooting

| Symptom                                                   | Likely cause / fix                                                                |
|-----------------------------------------------------------|-----------------------------------------------------------------------------------|
| `ModuleNotFoundError: No module named 'app'`              | `pytest` from repo root, or `pip install -e .`.                                   |
| Tests hang or `pytest` doesn't return                     | Hit Ctrl-C; ensure no leftover `uvicorn` process from a previous run.             |
| `Address already in use` on port 8000                     | `uvicorn app.main:app --port 8001` or kill the previous process.                  |
| All providers report errors with `[fallback]` data only   | Network is blocked or the upstream APIs are flaky. Check `/readyz`.               |
| 404 with `"No geocoding result for city='X' matched country='Y'"` | Try the country's ISO-2 code (`US`, `DE`); the matcher prefers it over free text. |

---

## License

No license set yet — add one before publishing externally.
