from datetime import date as date_type
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


Units = Literal["celsius", "fahrenheit"]


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


class ProviderResult(BaseModel):
    status: Literal["ok", "error"]
    data: Optional[Any] = None
    error: Optional[str] = None
    elapsed_ms: Optional[int] = None


class WeatherResponse(BaseModel):
    raw_input: WeatherQuery
    transformed_inputs: TransformedInputs
    result: dict[str, Any]
