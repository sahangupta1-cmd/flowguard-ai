from __future__ import annotations

from backend.app.ai.cache import AIContextCache
from backend.app.ai.guardrails import (
    screen_user_question,
    validate_llm_draft,
)
from backend.app.ai.models import (
    AskFlowGuardRequest,
    AskFlowGuardResponse,
)
from backend.app.ai.provider import (
    AIProvider,
    AIProviderRequest,
)
from backend.app.ai.routing import select_relevant_evidence
from backend.app.ai.dataset import resolve_ai_dataset
from backend.app.ai.question_evidence import build_question_evidence


class AskFlowGuardService:
    """
    Application-level orchestration for Ask FlowGuard.

    Flow:
        request guardrail
        -> deterministic finance context
        -> evidence routing
        -> model provider
        -> deterministic output validation
        -> reviewer-safe response

    The language model is never treated as the source of financial truth.
    """

    def __init__(
        self,
        *,
        provider: AIProvider,
        context_cache: AIContextCache | None = None,
    ) -> None:
        self._provider = provider
        self._context_cache = (
            context_cache
            if context_cache is not None
            else AIContextCache()
        )

    def ask(
        self,
        request: AskFlowGuardRequest,
    ) -> AskFlowGuardResponse:
        # ------------------------------------------------------------
        # 1. Block unsafe requests before any provider/API call.
        # ------------------------------------------------------------
        guardrail = screen_user_question(
            request.question
        )

        if not guardrail.allowed:
            raise ValueError(
                guardrail.reason
                or "Ask FlowGuard request was refused."
            )

        # ------------------------------------------------------------
        # 2. Rebuild or reuse trusted deterministic finance context.
        # ------------------------------------------------------------
        context = self._context_cache.get_or_build(
            request
        )

        # ------------------------------------------------------------
        # 3. Expose only the evidence relevant to this question.
        # ------------------------------------------------------------
        resolved_dataset = resolve_ai_dataset(request)

        dynamic_evidence = build_question_evidence(
            question=request.question,
            raw_dir=resolved_dataset.raw_dir,
            as_of_date=request.as_of_date,
            opening_cash_balance=request.opening_cash_balance,
            horizon_days=request.horizon_days,
        )

        validation_evidence_index = dict(
            context.evidence_index
        )

        for item in dynamic_evidence:
            validation_evidence_index[
                item.evidence_id
            ] = item

        if dynamic_evidence:
            selected_evidence = list(
                dynamic_evidence[:18]
            )
        else:
            _, selected_evidence = select_relevant_evidence(
                question=request.question,
                evidence_index=validation_evidence_index,
            )

        if not selected_evidence:
            raise RuntimeError(
                "No trusted finance evidence was selected."
            )

        # ------------------------------------------------------------
        # 4. Build the vendor-neutral provider request.
        #
        # No raw CSV path, manifest path, benchmark data or complete
        # finance context is exposed to the model.
        # ------------------------------------------------------------
        provider_request = AIProviderRequest(
            question=request.question,
            evidence=tuple(selected_evidence),
            source_type=context.provenance.source_type,
            as_of_date=context.provenance.as_of_date.isoformat(),
            import_id=context.provenance.import_id,
            fingerprint=context.provenance.fingerprint,
        )

        # ------------------------------------------------------------
        # 5. Generate a candidate answer.
        #
        # This result is NOT trusted yet.
        # ------------------------------------------------------------
        draft = self._provider.generate_draft(
            provider_request
        )

        # ------------------------------------------------------------
        # 6. Independently validate the model output.
        # ------------------------------------------------------------
        validation = validate_llm_draft(
            draft=draft,
            evidence_index=validation_evidence_index,
        )

        if not validation.valid:
            raise RuntimeError(
                "AI response failed FlowGuard grounding validation."
            )

        # ------------------------------------------------------------
        # 7. Return only the validated final response.
        # ------------------------------------------------------------
        return AskFlowGuardResponse(
            answer=draft.answer,
            risk_level=draft.risk_level,
            confidence=draft.confidence,
            evidence=list(
                validation.resolved_evidence
            ),
            recommended_actions=draft.recommended_actions,
            limitations=draft.limitations,
            provenance=context.provenance,
            safety=validation.report,
            safety_state=validation.safety_state,
        )
