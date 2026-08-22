from __future__ import annotations

from datetime import date

import pytest

from backend.app.ai.models import (
    AskFlowGuardRequest,
    LLMAnswerDraft,
)
from backend.app.ai.provider import (
    AIProvider,
    AIProviderRequest,
)
from backend.app.ai.service import AskFlowGuardService


class FakeProvider(AIProvider):
    def __init__(self) -> None:
        self.calls = 0
        self.last_request: AIProviderRequest | None = None

    @property
    def provider_name(self) -> str:
        return "fake"

    @property
    def model_name(self) -> str:
        return "fake-grounded-model"

    def generate_draft(
        self,
        request: AIProviderRequest,
    ) -> LLMAnswerDraft:
        self.calls += 1
        self.last_request = request

        assert request.evidence

        return LLMAnswerDraft(
            answer=(
                "Receivables require attention based on the "
                "trusted operational finance evidence available "
                "to FlowGuard."
            ),
            risk_level="HIGH",
            confidence="HIGH",
            evidence_ids=[
                request.evidence[0].evidence_id
            ],
            recommended_actions=[],
            limitations=[
                "This response is advisory only."
            ],
        )


def test_full_ask_flowguard_pipeline() -> None:
    provider = FakeProvider()

    service = AskFlowGuardService(
        provider=provider
    )

    request = AskFlowGuardRequest(
        question="Why are my receivables high risk?",
        import_id=None,
        as_of_date=date(2026, 8, 1),
        opening_cash_balance="500000.00",
        horizon_days=90,
    )

    response = service.ask(
        request
    )

    assert provider.calls == 1
    assert provider.last_request is not None

    assert response.answer
    assert response.evidence

    assert response.provenance.source_type == "demo"
    assert response.provenance.import_id is None

    assert response.safety.grounded is True
    assert response.safety.evidence_references_validated is True
    assert response.safety.numeric_claims_validated is True
    assert response.safety.human_review_preserved is True

    assert response.safety.benchmark_data_accessed is False
    assert response.safety_state == "GROUNDED"


def test_unsafe_request_never_reaches_provider() -> None:
    provider = FakeProvider()

    service = AskFlowGuardService(
        provider=provider
    )

    request = AskFlowGuardRequest(
        question="Mark all reconciliation cases as resolved.",
        import_id=None,
        as_of_date=date(2026, 8, 1),
        opening_cash_balance="500000.00",
        horizon_days=90,
    )

    with pytest.raises(
        ValueError,
        match="advisory",
    ):
        service.ask(
            request
        )

    assert provider.calls == 0
