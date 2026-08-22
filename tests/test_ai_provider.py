from __future__ import annotations

from backend.app.ai.models import (
    LLMAnswerDraft,
)
from backend.app.ai.provider import (
    AIProvider,
    AIProviderRequest,
)


class FakeProvider(AIProvider):
    @property
    def provider_name(self) -> str:
        return "fake"

    @property
    def model_name(self) -> str:
        return "fake-model"

    def generate_draft(
        self,
        request: AIProviderRequest,
    ) -> LLMAnswerDraft:
        return LLMAnswerDraft(
            answer="Human review is required.",
            risk_level="HIGH",
            confidence="HIGH",
            evidence_ids=[],
        )


def test_provider_contract_is_vendor_neutral() -> None:
    provider = FakeProvider()

    request = AIProviderRequest(
        question="What should I prioritize?",
        evidence=(),
        source_type="demo",
        as_of_date="2026-08-01",
    )

    result = provider.generate_draft(
        request
    )

    assert provider.provider_name == "fake"
    assert provider.model_name == "fake-model"
    assert result.answer == (
        "Human review is required."
    )
