import logging
import time
from abc import ABC, abstractmethod
from typing import Any, Optional

import httpx

from app.models import (
    ProviderResult,
    TransformedInputs,
    WeatherQuery,
    WeatherSnapshot,
)

logger = logging.getLogger(__name__)


class WeatherProvider(ABC):
    """Base class for weather data providers.

    Subclasses must:
      * set ``name``
      * implement ``fetch`` — async GET against the upstream
      * implement ``normalize`` — convert raw upstream JSON to a
        canonical ``WeatherSnapshot`` (always in Celsius, km/h, mm)
      * implement ``fallback`` — return an example ``WeatherSnapshot``
        when the upstream is unreachable; the snapshot must carry
        ``source_quality="fallback"``

    The orchestrator only calls ``safe_fetch``: it isolates per-provider
    failures, populates ``normalized`` on both the happy path and the
    error path (using ``fallback``), and logs failures so the team can
    see what went wrong in production.
    """

    name: str = "provider"

    @abstractmethod
    async def fetch(
        self,
        client: httpx.AsyncClient,
        query: WeatherQuery,
        transformed: TransformedInputs,
    ) -> Any: ...

    @abstractmethod
    def normalize(
        self,
        raw: Any,
        transformed: TransformedInputs,
    ) -> WeatherSnapshot: ...

    @abstractmethod
    def fallback(self, transformed: TransformedInputs) -> WeatherSnapshot: ...

    async def safe_fetch(
        self,
        client: httpx.AsyncClient,
        query: WeatherQuery,
        transformed: TransformedInputs,
    ) -> ProviderResult:
        start = time.perf_counter()
        try:
            data = await self.fetch(client, query, transformed)
            normalized: Optional[WeatherSnapshot]
            try:
                normalized = self.normalize(data, transformed)
            except Exception as norm_exc:
                logger.warning("%s: normalize() failed: %s", self.name, norm_exc, exc_info=True)
                normalized = self.fallback(transformed)
                normalized.source_quality = "fallback"
                normalized.notes = (
                    (normalized.notes or "") + " (normalize failed: see logs)"
                ).strip()
            return ProviderResult(
                status="ok",
                data=data,
                normalized=normalized,
                elapsed_ms=int((time.perf_counter() - start) * 1000),
            )
        except (httpx.HTTPError, TimeoutError) as exc:
            logger.warning(
                "%s: upstream failure (%s): %s",
                self.name,
                type(exc).__name__,
                exc,
            )
            fb = self.fallback(transformed)
            fb.source_quality = "fallback"
            return ProviderResult(
                status="error",
                error=f"{type(exc).__name__}: {exc}",
                normalized=fb,
                elapsed_ms=int((time.perf_counter() - start) * 1000),
            )
        except Exception as exc:
            # Unexpected (programmer error): record but don't crash the request.
            logger.exception("%s: unexpected error", self.name)
            fb = self.fallback(transformed)
            fb.source_quality = "fallback"
            return ProviderResult(
                status="error",
                error=f"{type(exc).__name__}: {exc}",
                normalized=fb,
                elapsed_ms=int((time.perf_counter() - start) * 1000),
            )
