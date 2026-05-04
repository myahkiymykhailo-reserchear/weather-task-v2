import asyncio
from typing import Optional

import httpx

from app.geocoding import geocode
from app.insight import build_insight
from app.models import WeatherQuery, WeatherResponse
from app.providers import DEFAULT_PROVIDERS, WeatherProvider


async def aggregate_weather(
    query: WeatherQuery,
    providers: Optional[list[WeatherProvider]] = None,
) -> WeatherResponse:
    """Geocode the query, then fan out to all providers in parallel."""
    providers = providers if providers is not None else DEFAULT_PROVIDERS

    async with httpx.AsyncClient() as client:
        transformed = await geocode(client, query)

        results = await asyncio.gather(
            *(p.safe_fetch(client, query, transformed) for p in providers)
        )

    by_name = {p.name: r.model_dump(exclude_none=True) for p, r in zip(providers, results)}
    by_name["summary"] = build_insight(transformed, by_name)

    return WeatherResponse(
        raw_input=query,
        transformed_inputs=transformed,
        result=by_name,
    )
