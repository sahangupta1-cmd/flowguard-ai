from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


ImportSourceType = Literal["demo", "uploaded_import"]

FinanceDomain = Literal[
    "reconciliation",
    "receivables",
    "cashflow",
    "liquidity",
    "priority",
    "system",
]

EvidenceUnit = Literal[
    "INR",
    "percent",
    "count",
    "days",
    "date",
    "severity",
    "boolean",
    "text",
]

AIRiskLevel = Literal[
    "INFORMATIONAL",
    "LOW",
    "MEDIUM",
    "HIGH",
    "CRITICAL",
]

AIConfidenceLevel = Literal[
    "LOW",
    "MODERATE",
    "HIGH",
]

AISafetyState = Literal[
    "GROUNDED",
    "LIMITED",
    "REFUSED",
]


class StrictAIModel(BaseModel):
    """
    Base model for Ask FlowGuard contracts.

    Unknown fields are rejected so that browser input, provider output,
    and internal AI objects cannot silently introduce unexpected data.
    """

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )


class AskFlowGuardRequest(StrictAIModel):
    """
    User request for grounded operational-finance reasoning.

    The browser supplies only the question and analysis parameters.
    It never supplies the financial intelligence snapshot itself.
    That snapshot is rebuilt server-side from trusted FlowGuard data.
    """

    question: str = Field(
        min_length=3,
        max_length=2000,
    )

    import_id: str | None = Field(
        default=None,
        pattern=r"^imp_[0-9a-f]{12}$",
        description=(
            "Validated isolated import to use. "
            "If omitted, the bundled operational demo dataset is used."
        ),
    )

    as_of_date: date

    opening_cash_balance: Decimal = Field(
        default=Decimal("500000.00"),
        ge=Decimal("0.00"),
    )

    horizon_days: int = Field(
        default=90,
        ge=1,
        le=365,
    )


class AIDataProvenance(StrictAIModel):
    """
    Identifies the exact operational source used for an AI answer.

    Raw filesystem paths are intentionally never exposed.
    """

    source_type: ImportSourceType

    as_of_date: date

    import_id: str | None = Field(
        default=None,
        pattern=r"^imp_[0-9a-f]{12}$",
    )

    fingerprint: str | None = Field(
        default=None,
        min_length=1,
        max_length=128,
    )

    opening_cash_balance: str

    horizon_days: int = Field(
        ge=1,
        le=365,
    )


class TrustedEvidence(StrictAIModel):
    """
    One deterministic financial fact available to Ask FlowGuard.

    Evidence values originate from FlowGuard's finance engines,
    not from the language model.
    """

    evidence_id: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[a-z0-9_.-]+$",
    )

    domain: FinanceDomain

    metric: str = Field(
        min_length=1,
        max_length=160,
    )

    value: str = Field(
        min_length=1,
        max_length=500,
    )

    unit: EvidenceUnit

    source_field: str = Field(
        min_length=1,
        max_length=200,
    )

    as_of_date: date


class AIRecommendationDraft(StrictAIModel):
    """
    Recommendation proposed by the reasoning model.

    Recommendations are advisory only and cannot mutate finance data.
    """

    action: str = Field(
        min_length=1,
        max_length=500,
    )

    rationale: str = Field(
        min_length=1,
        max_length=1000,
    )

    priority: Literal[
        "LOW",
        "MEDIUM",
        "HIGH",
        "CRITICAL",
    ]


class LLMAnswerDraft(StrictAIModel):
    """
    Structured output that the LLM is allowed to generate.

    Crucially, the model references evidence IDs rather than supplying
    financial evidence values itself. The application resolves those IDs
    against the trusted evidence catalogue after generation.
    """

    answer: str = Field(
        min_length=1,
        max_length=5000,
    )

    risk_level: AIRiskLevel

    confidence: AIConfidenceLevel

    evidence_ids: list[str] = Field(
        default_factory=list,
        max_length=18,
    )

    recommended_actions: list[AIRecommendationDraft] = Field(
        default_factory=list,
        max_length=5,
    )

    limitations: list[str] = Field(
        default_factory=list,
        max_length=5,
    )


class AIValidationReport(StrictAIModel):
    """
    Server-generated validation result.

    The LLM never controls these fields.
    """

    grounded: bool

    numeric_claims_validated: bool

    evidence_references_validated: bool

    unsupported_claims_detected: int = Field(
        ge=0,
    )

    benchmark_data_accessed: bool = False

    human_review_preserved: bool = True


class AskFlowGuardResponse(StrictAIModel):
    """
    Final reviewer-safe Ask FlowGuard API response.

    The response combines provider-generated reasoning with deterministic
    evidence, provenance and application-generated safety validation.
    """

    answer: str

    risk_level: AIRiskLevel

    confidence: AIConfidenceLevel

    evidence: list[TrustedEvidence] = Field(
        default_factory=list,
        max_length=18,
    )

    recommended_actions: list[AIRecommendationDraft] = Field(
        default_factory=list,
        max_length=5,
    )

    limitations: list[str] = Field(
        default_factory=list,
        max_length=5,
    )

    provenance: AIDataProvenance

    safety: AIValidationReport

    safety_state: AISafetyState
