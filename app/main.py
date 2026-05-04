from datetime import date as date_type
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from pydantic import ValidationError

from app.aggregator import aggregate_weather
from app.geocoding import GeocodingError
from app.models import Units, WeatherQuery, WeatherResponse

app = FastAPI(
    title="Weather Prediction Service",
    version="0.1.0",
    description="Aggregates forecasts from Open-Meteo, wttr (goweather), "
    "openSenseMap, OceanDrivers and 7Timer.",
)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/weather", response_model=WeatherResponse)
async def get_weather(
    city: str = Query(..., min_length=1, description="City name, e.g. 'New York'"),
    country: str = Query(..., min_length=1, description="Country name or ISO-2 code"),
    state: Optional[str] = Query(None, description="State / admin region"),
    date: Optional[date_type] = Query(None, description="YYYY-MM-DD; defaults to today"),
    units: Units = Query("celsius"),
) -> WeatherResponse:
    try:
        query = WeatherQuery(city=city, country=country, state=state, date=date, units=units)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc

    try:
        return await aggregate_weather(query)
    except GeocodingError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
