from datetime import date as date_type
from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, Field


Units = Literal["celsius", "fahrenheit"]
SourceQuality = Literal["live", "fallback"]


class WeatherQuery(BaseModel):
    city: str = Field(..., min_length=1, description="City name, e.g. 'New York'")
    state: Optional[str] = Field(None, description="State or admin region, e.g. 'NY'")
    country: str = Field(..., min_length=1, description="Country name or ISO-2 code, e.g. 'US'")
    date: Optional[date_type] = Field(None, description="Target date (YYYY-MM-DD); defaults to today")
    units: Units = Field("celsius", description="Temperature units")


class TransformedInputs(BaseModel):
    lat: float
    lon: float
    timezone: Optional[str] = None
    resolved_name: Optional[str] = None
    country_code: Optional[str] = None
    date: date_type
    units: Units


class WeatherSnapshot(BaseModel):
    """Canonical, provider-agnostic weather snapshot for one location/date.

    Always stored in canonical units (Celsius, km/h, mm) regardless of the
    output units the user requested. Aggregator does display-time conversion.

    `source_quality="fallback"` means this snapshot is example data the
    provider returned because the upstream API was unreachable or returned
    a non-2xx status. Keep that flag visible in any consumer UI.
    """

    temperature_c: Optional[float] = None
    feels_like_c: Optional[float] = None
    humidity_pct: Optional[float] = None
    wind_kph: Optional[float] = None
    wind_direction_deg: Optional[float] = None
    precipitation_mm: Optional[float] = None
    cloud_cover_pct: Optional[float] = None
    conditions: Optional[str] = None
    is_forecast: bool = False
    forecast_for_date: Optional[date_type] = None
    source_quality: SourceQuality = "live"
    notes: Optional[str] = None


class ProviderResult(BaseModel):
    status: Literal["ok", "error"]
    data: Optional[Any] = None
    error: Optional[str] = None
    elapsed_ms: Optional[int] = None
    normalized: Optional[WeatherSnapshot] = None


class AggregatedResult(BaseModel):
    providers: Dict[str, ProviderResult]
    normalized: Dict[str, WeatherSnapshot]
    summary: str


class WeatherResponse(BaseModel):
    raw_input: WeatherQuery
    transformed_inputs: TransformedInputs
    result: Dict[str, Any]
