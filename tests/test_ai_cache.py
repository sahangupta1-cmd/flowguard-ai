from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from backend.app.ai.cache import (
    AIContextCache,
    build_ai_cache_key,
)
from backend.app.ai.dataset import (
    AIFinanceContext,
    build_ai_finance_context,
)
from backend.app.ai.models import AskFlowGuardRequest


def _request(
    *,
    question: str = "What should I prioritize?",
    opening_cash: str = "500000.00",
    horizon_days: int = 90,
    as_of_date: date = date(2026, 8, 1),
) -> AskFlowGuardRequest:
    return AskFlowGuardRequest(
        question=question,
        import_id=None,
        as_of_date=as_of_date,
        opening_cash_balance=Decimal(
            opening_cash
        ),
        horizon_days=horizon_days,
    )


def test_same_finance_snapshot_is_reused_across_questions() -> None:
    calls = 0

    def builder(
        request: AskFlowGuardRequest,
        demo_raw_dir: Path,
        import_root: Path,
    ) -> AIFinanceContext:
        nonlocal calls
        calls += 1

        return build_ai_finance_context(
            request,
            demo_raw_dir=demo_raw_dir,
            import_root=import_root,
        )

    cache = AIContextCache(
        ttl_seconds=300,
        max_entries=8,
    )

    first = cache.get_or_build(
        _request(
            question="Why are receivables risky?"
        ),
        context_builder=builder,
    )

    second = cache.get_or_build(
        _request(
            question="What should I prioritize?"
        ),
        context_builder=builder,
    )

    stats = cache.stats()

    assert calls == 1
    assert first is second
    assert stats.hits == 1
    assert stats.misses == 1
    assert stats.entries == 1


def test_question_is_not_part_of_cache_key() -> None:
    first = build_ai_cache_key(
        _request(
            question="Why are receivables risky?"
        )
    )

    second = build_ai_cache_key(
        _request(
            question="Explain liquidity."
        )
    )

    assert first == second


@pytest.mark.parametrize(
    (
        "first_request",
        "second_request",
    ),
    [
        (
            _request(
                opening_cash="500000.00"
            ),
            _request(
                opening_cash="600000.00"
            ),
        ),
        (
            _request(
                horizon_days=90
            ),
            _request(
                horizon_days=30
            ),
        ),
        (
            _request(
                as_of_date=date(
                    2026,
                    8,
                    1,
                )
            ),
            _request(
                as_of_date=date(
                    2026,
                    8,
                    2,
                )
            ),
        ),
    ],
)
def test_finance_configuration_changes_cache_key(
    first_request: AskFlowGuardRequest,
    second_request: AskFlowGuardRequest,
) -> None:
    assert (
        build_ai_cache_key(
            first_request
        )
        != build_ai_cache_key(
            second_request
        )
    )


def test_different_finance_configuration_rebuilds_context() -> None:
    calls = 0

    def builder(
        request: AskFlowGuardRequest,
        demo_raw_dir: Path,
        import_root: Path,
    ) -> AIFinanceContext:
        nonlocal calls
        calls += 1

        return build_ai_finance_context(
            request,
            demo_raw_dir=demo_raw_dir,
            import_root=import_root,
        )

    cache = AIContextCache(
        ttl_seconds=300,
        max_entries=8,
    )

    cache.get_or_build(
        _request(
            horizon_days=90
        ),
        context_builder=builder,
    )

    cache.get_or_build(
        _request(
            horizon_days=30
        ),
        context_builder=builder,
    )

    stats = cache.stats()

    assert calls == 2
    assert stats.hits == 0
    assert stats.misses == 2
    assert stats.entries == 2


def test_expired_snapshot_is_rebuilt() -> None:
    now = 100.0
    calls = 0

    def clock() -> float:
        return now

    def builder(
        request: AskFlowGuardRequest,
        demo_raw_dir: Path,
        import_root: Path,
    ) -> AIFinanceContext:
        nonlocal calls
        calls += 1

        return build_ai_finance_context(
            request,
            demo_raw_dir=demo_raw_dir,
            import_root=import_root,
        )

    cache = AIContextCache(
        ttl_seconds=10,
        max_entries=8,
        clock=clock,
    )

    request = _request()

    first = cache.get_or_build(
        request,
        context_builder=builder,
    )

    now = 105.0

    second = cache.get_or_build(
        request,
        context_builder=builder,
    )

    assert first is second
    assert calls == 1

    now = 111.0

    third = cache.get_or_build(
        request,
        context_builder=builder,
    )

    assert third is not first
    assert calls == 2


def test_lru_cache_evicts_oldest_snapshot() -> None:
    cache = AIContextCache(
        ttl_seconds=300,
        max_entries=2,
    )

    cache.get_or_build(
        _request(
            horizon_days=30
        )
    )

    cache.get_or_build(
        _request(
            horizon_days=60
        )
    )

    cache.get_or_build(
        _request(
            horizon_days=90
        )
    )

    stats = cache.stats()

    assert stats.entries == 2
    assert stats.evictions == 1


def test_clear_removes_cached_snapshots() -> None:
    cache = AIContextCache(
        ttl_seconds=300,
        max_entries=8,
    )

    cache.get_or_build(
        _request()
    )

    assert cache.stats().entries == 1

    cache.clear()

    assert cache.stats().entries == 0


def test_invalid_cache_configuration_fails_closed() -> None:
    with pytest.raises(
        ValueError,
        match="ttl_seconds must be greater than zero",
    ):
        AIContextCache(
            ttl_seconds=0,
        )

    with pytest.raises(
        ValueError,
        match="max_entries must be at least 1",
    ):
        AIContextCache(
            max_entries=0,
        )
