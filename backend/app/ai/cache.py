from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from time import monotonic
from typing import Callable

from backend.app.ai.dataset import (
    AIFinanceContext,
    DEFAULT_DEMO_RAW_DIR,
    DEFAULT_IMPORT_ROOT,
    build_ai_finance_context,
    resolve_ai_dataset,
)
from backend.app.ai.models import AskFlowGuardRequest


DEFAULT_CACHE_TTL_SECONDS = 300.0
DEFAULT_CACHE_MAX_ENTRIES = 128


@dataclass(frozen=True)
class AIContextCacheKey:
    """
    Identity of one deterministic FlowGuard finance snapshot.

    import_id is retained in addition to fingerprint so two separate
    imports of identical data never share incorrect provenance.
    """

    source_type: str
    import_id: str | None
    fingerprint: str | None
    as_of_date: str
    opening_cash_balance: str
    horizon_days: int


@dataclass(frozen=True)
class AIContextCacheStats:
    hits: int
    misses: int
    evictions: int
    entries: int


@dataclass
class _CacheEntry:
    context: AIFinanceContext
    expires_at: float


ContextBuilder = Callable[
    [
        AskFlowGuardRequest,
        Path,
        Path,
    ],
    AIFinanceContext,
]


def _canonical_money(
    request: AskFlowGuardRequest,
) -> str:
    return format(
        request.opening_cash_balance,
        ".2f",
    )


def build_ai_cache_key(
    request: AskFlowGuardRequest,
    *,
    demo_raw_dir: Path = DEFAULT_DEMO_RAW_DIR,
    import_root: Path = DEFAULT_IMPORT_ROOT,
) -> AIContextCacheKey:
    """
    Resolve only the lightweight dataset identity required for caching.

    On an uploaded dataset this validates the import and reads its manifest,
    but does not execute the finance engines.
    """

    resolved = resolve_ai_dataset(
        request,
        demo_raw_dir=demo_raw_dir,
        import_root=import_root,
    )

    provenance = resolved.provenance

    return AIContextCacheKey(
        source_type=provenance.source_type,
        import_id=provenance.import_id,
        fingerprint=provenance.fingerprint,
        as_of_date=request.as_of_date.isoformat(),
        opening_cash_balance=_canonical_money(
            request
        ),
        horizon_days=request.horizon_days,
    )


def _default_context_builder(
    request: AskFlowGuardRequest,
    demo_raw_dir: Path,
    import_root: Path,
) -> AIFinanceContext:
    return build_ai_finance_context(
        request,
        demo_raw_dir=demo_raw_dir,
        import_root=import_root,
    )


class AIContextCache:
    """
    Small thread-safe in-memory LRU + TTL cache.

    It caches deterministic FlowGuard finance contexts, never LLM answers.

    This means:
    - financial computation can be reused;
    - every new user question still receives fresh language-model reasoning;
    - cached data remains tied to exact dataset provenance and parameters.
    """

    def __init__(
        self,
        *,
        ttl_seconds: float = DEFAULT_CACHE_TTL_SECONDS,
        max_entries: int = DEFAULT_CACHE_MAX_ENTRIES,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError(
                "ttl_seconds must be greater than zero."
            )

        if max_entries < 1:
            raise ValueError(
                "max_entries must be at least 1."
            )

        self.ttl_seconds = float(
            ttl_seconds
        )

        self.max_entries = int(
            max_entries
        )

        self._clock = clock

        self._entries: OrderedDict[
            AIContextCacheKey,
            _CacheEntry,
        ] = OrderedDict()

        self._lock = RLock()

        self._hits = 0
        self._misses = 0
        self._evictions = 0

    def _remove_expired_locked(
        self,
        now: float,
    ) -> None:
        expired = [
            key
            for key, entry in self._entries.items()
            if entry.expires_at <= now
        ]

        for key in expired:
            self._entries.pop(
                key,
                None,
            )

    def _get_locked(
        self,
        key: AIContextCacheKey,
        now: float,
    ) -> AIFinanceContext | None:
        self._remove_expired_locked(
            now
        )

        entry = self._entries.get(
            key
        )

        if entry is None:
            self._misses += 1
            return None

        self._entries.move_to_end(
            key
        )

        self._hits += 1

        return entry.context

    def _put_locked(
        self,
        key: AIContextCacheKey,
        context: AIFinanceContext,
        now: float,
    ) -> None:
        self._entries[
            key
        ] = _CacheEntry(
            context=context,
            expires_at=(
                now
                + self.ttl_seconds
            ),
        )

        self._entries.move_to_end(
            key
        )

        while len(
            self._entries
        ) > self.max_entries:
            self._entries.popitem(
                last=False
            )

            self._evictions += 1

    def get_or_build(
        self,
        request: AskFlowGuardRequest,
        *,
        demo_raw_dir: Path = DEFAULT_DEMO_RAW_DIR,
        import_root: Path = DEFAULT_IMPORT_ROOT,
        context_builder: ContextBuilder = _default_context_builder,
    ) -> AIFinanceContext:
        """
        Return a cached deterministic finance context or build one.

        The lock is intentionally not held while finance engines execute.
        This avoids blocking unrelated requests during a cache miss.
        """

        key = build_ai_cache_key(
            request,
            demo_raw_dir=demo_raw_dir,
            import_root=import_root,
        )

        now = self._clock()

        with self._lock:
            cached = self._get_locked(
                key,
                now,
            )

        if cached is not None:
            return cached

        context = context_builder(
            request,
            demo_raw_dir,
            import_root,
        )

        provenance = context.provenance

        if (
            provenance.source_type
            != key.source_type
            or provenance.import_id
            != key.import_id
            or provenance.fingerprint
            != key.fingerprint
        ):
            raise RuntimeError(
                "Built AI finance context does not match "
                "the resolved dataset identity."
            )

        now = self._clock()

        with self._lock:
            self._put_locked(
                key,
                context,
                now,
            )

        return context

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()

    def stats(self) -> AIContextCacheStats:
        with self._lock:
            self._remove_expired_locked(
                self._clock()
            )

            return AIContextCacheStats(
                hits=self._hits,
                misses=self._misses,
                evictions=self._evictions,
                entries=len(
                    self._entries
                ),
            )


DEFAULT_AI_CONTEXT_CACHE = AIContextCache()


def get_cached_ai_finance_context(
    request: AskFlowGuardRequest,
    *,
    demo_raw_dir: Path = DEFAULT_DEMO_RAW_DIR,
    import_root: Path = DEFAULT_IMPORT_ROOT,
) -> AIFinanceContext:
    """
    Application-level entry point used by the future Ask FlowGuard service.
    """

    return DEFAULT_AI_CONTEXT_CACHE.get_or_build(
        request,
        demo_raw_dir=demo_raw_dir,
        import_root=import_root,
    )
