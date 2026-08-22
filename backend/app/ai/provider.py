from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from backend.app.ai.models import (
    LLMAnswerDraft,
    TrustedEvidence,
)


@dataclass(frozen=True)
class AIProviderRequest:
    """
    Provider-neutral request for one grounded Ask FlowGuard answer.

    Only selected trusted evidence is supplied here.
    The provider never receives raw CSV paths, benchmark data,
    manifests, or application secrets.
    """

    question: str

    evidence: tuple[
        TrustedEvidence,
        ...]

    source_type: str

    as_of_date: str

    import_id: str | None = None

    fingerprint: str | None = None


class AIProvider(ABC):
    """
    Abstract boundary between FlowGuard and a language-model provider.

    The finance engine and safety validators remain independent from
    OpenAI or any other model vendor.
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        raise NotImplementedError

    @property
    @abstractmethod
    def model_name(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def generate_draft(
        self,
        request: AIProviderRequest,
    ) -> LLMAnswerDraft:
        """
        Generate one structured draft.

        IMPORTANT:
        Returning a draft does NOT mean the answer is trusted.

        FlowGuard must subsequently validate:
        - evidence references;
        - numeric claims;
        - human-review preservation;
        - application safety rules.
        """

        raise NotImplementedError
