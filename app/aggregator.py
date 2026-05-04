import asyncio
import logging
from typing import List, Optional

import httpx

from app.config import settings
from app.geocoding import geocode
from app.insight import build_insight
from app.models import (
    AggregatedResult,
    ProviderResult,
    WeatherQuery,
    WeatherResponse,
)
from app.providers import DEFAULT_PROVIDERS, WeatherProvider

logger = logging.getLogger(__name__)


async def aggregate_weather(
    query: WeatherQuery,
    client: httpx.AsyncClient,
    providers: Optional[List[WeatherProvider]] = None,
) -> WeatherResponse:
    """Geocode the query, then fan out to all providers in parallel.

    The shared ``httpx.AsyncClient`` is owned by the FastAPI lifespan so
    every request reuses the connection pool. Each provider runs under
    a per-provider total-budget cap; if a provider exceeds it the
    bound coroutine returns a fallback ProviderResult so the slow API
    cannot block the rest of the response.
    """
    providers_list = providers if providers is not None else DEFAULT_PROVIDERS

    transformed = await geocode(client, query)

    budget = settings.total_request_budget_seconds
    provider_results = await asyncio.gather(
        *(_bounded_safe_fetch(p, client, query, transformed, budget) for p in providers_list)
    )

    # noqa: B905 — providers_list and provider_results are zipped in order from the same gather call.
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


async def _bounded_safe_fetch(
    provider: WeatherProvider,
    client: httpx.AsyncClient,
    query: WeatherQuery,
    transformed,
    budget_seconds: float,
) -> ProviderResult:
    try:
        return await asyncio.wait_for(
            provider.safe_fetch(client, query, transformed),
            timeout=budget_seconds,
        )
    except asyncio.TimeoutError:
        logger.warning(
            "%s: total budget of %.1fs exceeded; using fallback",
            provider.name,
            budget_seconds,
        )
        fb = provider.fallback(transformed)
        fb.source_quality = "fallback"
        return ProviderResult(
            status="error",
            error=f"TimeoutError: provider exceeded {budget_seconds}s total budget",
            normalized=fb,
            elapsed_ms=int(budget_seconds * 1000),
        )
