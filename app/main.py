import logging
from contextlib import asynccontextmanager
from datetime import date as date_type
from pathlib import Path
from typing import Optional

import httpx
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from app.aggregator import aggregate_weather
from app.config import settings
from app.geocoding import GeocodingError
from app.models import Units, WeatherQuery, WeatherResponse

STATIC_DIR = Path(__file__).resolve().parent / "static"


def _configure_logging() -> None:
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    _configure_logging()
    app.state.http_client = httpx.AsyncClient(
        limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
        timeout=httpx.Timeout(settings.request_timeout_seconds),
    )
    try:
        yield
    finally:
        await app.state.http_client.aclose()


app = FastAPI(
    title="Weather Prediction Service",
    version="0.2.0",
    description="Aggregates forecasts from Open-Meteo, wttr (goweather), "
    "openSenseMap, OceanDrivers and 7Timer.",
    lifespan=lifespan,
)


_cors_origins = [o.strip() for o in settings.cors_allow_origins.split(",") if o.strip()]
if _cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_methods=["GET"],
        allow_headers=["*"],
    )


# Static UI: served at "/" and "/static/*". Path is resolved relative to this file
# so the app finds its assets regardless of cwd.
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
async def root():
    return FileResponse(STATIC_DIR / "index.html")


def get_http_client(request: Request) -> httpx.AsyncClient:
    return request.app.state.http_client


@app.get("/livez")
async def livez():
    """Liveness probe — process is alive. Always 200 unless the process is dead."""
    return {"status": "ok"}


@app.get("/readyz")
async def readyz(client: httpx.AsyncClient = Depends(get_http_client)):
    """Readiness probe — verifies the geocoder (the one upstream we cannot live without)."""
    try:
        resp = await client.get(
            settings.geocoding_url,
            params={"name": "Berlin", "count": 1, "format": "json"},
            timeout=2.0,
        )
        resp.raise_for_status()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"geocoder unhealthy: {exc}") from exc
    return {"status": "ok"}


@app.get("/health")
async def health():
    """Backwards-compatible alias of /livez."""
    return {"status": "ok"}


@app.get("/weather", response_model=WeatherResponse)
async def get_weather(
    city: str = Query(..., min_length=1, description="City name, e.g. 'New York'"),
    country: str = Query(..., min_length=1, description="Country name or ISO-2 code"),
    state: Optional[str] = Query(None, description="State / admin region"),
    date: Optional[date_type] = Query(None, description="YYYY-MM-DD; defaults to today"),
    units: Units = Query("celsius"),
    client: httpx.AsyncClient = Depends(get_http_client),
) -> WeatherResponse:
    try:
        query = WeatherQuery(city=city, country=country, state=state, date=date, units=units)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc

    try:
        return await aggregate_weather(query, client)
    except GeocodingError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
