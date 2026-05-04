import time
from abc import ABC, abstractmethod
from typing import Any

import httpx

from app.models import ProviderResult, TransformedInputs, WeatherQuery


class WeatherProvider(ABC):
    """Base class for weather data providers.

    Subclasses set ``name`` and implement ``fetch``. The orchestrator calls
    ``safe_fetch`` so a single provider failure cannot break the aggregation.
    """

    name: str = "provider"

    @abstractmethod
    async def fetch(
        self,
        client: httpx.AsyncClient,
        query: WeatherQuery,
        transformed: TransformedInputs,
    ) -> Any:
        ...

    async def safe_fetch(
        self,
        client: httpx.AsyncClient,
        query: WeatherQuery,
        transformed: TransformedInputs,
    ) -> ProviderResult:
        start = time.perf_counter()
        try:
            data = await self.fetch(client, query, transformed)
            return ProviderResult(
                status="ok",
                data=data,
                elapsed_ms=int((time.perf_counter() - start) * 1000),
            )
        except Exception as exc:
            return ProviderResult(
                status="error",
                error=f"{type(exc).__name__}: {exc}",
                elapsed_ms=int((time.perf_counter() - start) * 1000),
            )
