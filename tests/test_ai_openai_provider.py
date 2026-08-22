from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import pytest

from backend.app.ai.dataset import (
    build_ai_finance_context,
)
from backend.app.ai.models import (
    AskFlowGuardRequest,
    LLMAnswerDraft,
)
from backend.app.ai.openai_provider import (
    OpenAIProvider,
)
from backend.app.ai.provider import (
    AIProviderRequest,
)


@dataclass
class _FakeResponse:
    output_parsed: object


class _FakeResponses:
    def __init__(
        self,
        parsed: object,
    ) -> None:
        self.parsed = parsed
        self.calls: list[dict] = []

    def parse(
        self,
        **kwargs,
    ):
        self.calls.append(kwargs)

        return _FakeResponse(
            output_parsed=self.parsed
        )


class _FakeOpenAI:
    def __init__(
        self,
        parsed: object,
    ) -> None:
        self.responses = _FakeResponses(
            parsed
        )


def _trusted_evidence():
    request = AskFlowGuardRequest(
        question="Build provider test evidence.",
        import_id=None,
        as_of_date=date(2026, 8, 1),
        opening_cash_balance=Decimal("500000.00"),
        horizon_days=90,
    )

    context = build_ai_finance_context(
        request
    )

    return context.evidence_index[
        "receivables.high_risk_amount"
    ]


def _provider_request() -> AIProviderRequest:
    return AIProviderRequest(
        question="Why are receivables high risk?",
        evidence=(
            _trusted_evidence(),
        ),
        source_type="demo",
        as_of_date="2026-08-01",
    )


def test_openai_provider_returns_structured_draft() -> None:
    expected = LLMAnswerDraft(
        answer=(
            "High-risk receivables represent "
            "₹71.94L."
        ),
        risk_level="HIGH",
        confidence="HIGH",
        evidence_ids=[
            "receivables.high_risk_amount"
        ],
    )

    client = _FakeOpenAI(
        expected
    )

    provider = OpenAIProvider(
        model="test-model",
        client=client,
    )

    result = provider.generate_draft(
        _provider_request()
    )

    assert result == expected
    assert provider.provider_name == "openai"
    assert provider.model_name == "test-model"

    assert len(
        client.responses.calls
    ) == 1

    call = client.responses.calls[0]

    assert call["model"] == "test-model"
    assert call["text_format"] is LLMAnswerDraft

    assert (
        "receivables.high_risk_amount"
        in call["input"]
    )

    assert "7194400.00" in call["input"]

    assert "data/raw" not in call["input"]
    assert "data/imports" not in call["input"]


def test_zero_evidence_fails_before_openai_call() -> None:
    client = _FakeOpenAI(
        None
    )

    provider = OpenAIProvider(
        client=client
    )

    request = AIProviderRequest(
        question="What is our financial position?",
        evidence=(),
        source_type="demo",
        as_of_date="2026-08-01",
    )

    with pytest.raises(
        ValueError,
        match="requires trusted evidence",
    ):
        provider.generate_draft(
            request
        )

    assert client.responses.calls == []


def test_missing_structured_output_fails_closed() -> None:
    provider = OpenAIProvider(
        client=_FakeOpenAI(None)
    )

    with pytest.raises(
        RuntimeError,
        match="no structured FlowGuard answer",
    ):
        provider.generate_draft(
            _provider_request()
        )


def test_model_is_configurable() -> None:
    provider = OpenAIProvider(
        model="gpt-5.6-sol",
        client=_FakeOpenAI(None),
    )

    assert provider.model_name == "gpt-5.6-sol"
