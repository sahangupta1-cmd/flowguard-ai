from __future__ import annotations

import logging
from functools import lru_cache

from fastapi import APIRouter, HTTPException

from backend.app.ai.models import (
    AskFlowGuardRequest,
    AskFlowGuardResponse,
)
from backend.app.ai.openai_provider import OpenAIProvider
from backend.app.ai.service import AskFlowGuardService


logger = logging.getLogger(__name__)

router = APIRouter()


@lru_cache(maxsize=1)
def _get_ask_flowguard_service() -> AskFlowGuardService:
    """
    Lazily construct one Ask FlowGuard service.

    The service contains the shared deterministic finance-context cache.
    OpenAI is therefore not initialized merely because the FastAPI
    application starts.
    """
    return AskFlowGuardService(
        provider=OpenAIProvider(),
    )


@router.post(
    "/api/v1/ai/ask",
    response_model=AskFlowGuardResponse,
    tags=["ai"],
)
def ask_flowguard(
    request: AskFlowGuardRequest,
) -> AskFlowGuardResponse:
    """
    Ask FlowGuard a grounded operational-finance question.

    Flow:
        user question
        -> request guardrails
        -> trusted dataset resolution
        -> deterministic finance context
        -> relevant evidence selection
        -> language-model draft
        -> independent grounding validation
        -> reviewer-safe response

    The browser never supplies trusted financial evidence directly.
    """

    try:
        service = _get_ask_flowguard_service()

        return service.ask(
            request
        )

    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail="The requested operational dataset was not found.",
        ) from exc

    except ValueError as exc:
        # Includes advisory-only / financial-mutation guardrail refusals.
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    except RuntimeError as exc:
        logger.exception(
            "Ask FlowGuard grounding or validation failed."
        )

        raise HTTPException(
            status_code=502,
            detail=(
                "Ask FlowGuard could not produce a validated "
                "grounded answer."
            ),
        ) from exc

    except Exception as exc:
        logger.exception(
            "Ask FlowGuard provider unavailable."
        )

        raise HTTPException(
            status_code=503,
            detail="Ask FlowGuard provider is unavailable.",
        ) from exc
