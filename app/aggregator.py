import asyncio
from typing import List, Optional

import httpx

from app.geocoding import geocode
from app.insight import build_insight
from app.models import AggregatedResult, WeatherQuery, WeatherResponse
from app.providers import DEFAULT_PROVIDERS, WeatherProvider


async def aggregate_weather(
    query: WeatherQuery,
    providers: Optional[List[WeatherProvider]] = None,
) -> WeatherResponse:
    """Geocode the query, then fan out to all providers in parallel."""
    providers_list = providers if providers is not None else DEFAULT_PROVIDERS

    async with httpx.AsyncClient() as client:
        transformed = await geocode(client, query)

        provider_results = await asyncio.gather(
            *(p.safe_fetch(client, query, transformed) for p in providers_list)
        )

    by_name = {p.name: r for p, r in zip(providers_list, provider_results)}
    normalized = {name: pr.normalized for name, pr in by_name.items() if pr.normalized}
    summary = build_insight(transformed, by_name)

    return WeatherResponse(
        raw_input=query,
        transformed_inputs=transformed,
        result=AggregatedResult(
            providers=by_name,
            normalized=normalized,
            summary=summary,
        ),
    )
