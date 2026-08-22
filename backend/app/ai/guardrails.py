from __future__ import annotations

import json
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Literal

from backend.app.ai.context import resolve_evidence_ids
from backend.app.ai.models import (
    AISafetyState,
    AIValidationReport,
    LLMAnswerDraft,
    TrustedEvidence,
)


# ----------------------------------------------------------------------
# Request-level safety
# ----------------------------------------------------------------------

_INJECTION_PATTERNS = (
    re.compile(
        r"\b(?:ignore|disregard|forget|override)\s+(?:all\s+)?(?:previous|prior|system|developer)"
        r"\s+(?:instructions?|messages?|prompts?)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\breveal\s+(?:the\s+)?(?:system|developer|hidden)"
        r"\s+(?:prompt|instructions?|message)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:jailbreak|developer\s+mode|system\s+prompt)\b",
        re.IGNORECASE,
    ),
)

_PROTECTED_DATA_TERM_RE = re.compile(
    r"\b(?:"
    r"benchmark(?:s)?|"
    r"ground[\s_-]?truth|"
    r"evaluation\s+(?:data|labels?|dataset)|"
    r"scenario\s+labels?|"
    r"expected\s+outcomes?"
    r")\b",
    re.IGNORECASE,
)

_EXFILTRATION_VERB_RE = re.compile(
    r"\b(?:"
    r"show|reveal|display|list|dump|export|extract|"
    r"read|access|give|tell|what|which|print|return"
    r")\b",
    re.IGNORECASE,
)

_FINANCE_OBJECT_RE = (
    r"(?:"
    r"transactions?|payments?|invoices?|settlements?|"
    r"refunds?|chargebacks?|reconciliation\s+cases?|"
    r"records?|finance\s+data"
    r")"
)

_MUTATION_START_RE = re.compile(
    rf"^\s*(?:"
    rf"auto(?:matically)?[-\s]?close|"
    rf"close|resolve|reconcile|modify|edit|change|delete|mark|approve|update|"
    rf"overwrite|execute|send|transfer|pay|refund|reverse"
    rf")\b.{{0,100}}\b{_FINANCE_OBJECT_RE}\b",
    re.IGNORECASE,
)

_MUTATION_REQUEST_RE = re.compile(
    rf"\b(?:"
    rf"please|can\s+you|could\s+you|would\s+you|"
    rf"go\s+ahead\s+and|automatically|just"
    rf")\b.{{0,80}}\b(?:"
    rf"auto(?:matically)?[-\s]?close|"
    rf"close|resolve|reconcile|modify|edit|change|delete|mark|approve|update|"
    rf"overwrite|execute|send|transfer|pay|refund|reverse"
    rf")\b.{{0,100}}\b{_FINANCE_OBJECT_RE}\b",
    re.IGNORECASE,
)

_HUMAN_REVIEW_BYPASS_PATTERNS = (
    re.compile(
        r"\bbypass\s+(?:the\s+)?human\s+review\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bskip\s+(?:the\s+)?human\s+review\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bwithout\s+human\s+review\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\boverride\s+(?:the\s+)?(?:manual|human)\s+review\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bauto(?:matically)?[-\s]?close\s+all\b",
        re.IGNORECASE,
    ),
)


@dataclass(frozen=True)
class RequestGuardrailResult:
    allowed: bool
    safety_state: AISafetyState
    reason: str | None
    flags: tuple[str, ...]


def screen_user_question(
    question: str,
) -> RequestGuardrailResult:
    """
    Screen a user question before it reaches the reasoning provider.

    Advisory questions remain allowed. Requests that attempt to alter
    financial records, exfiltrate protected evaluation data or override
    the model's instruction hierarchy are blocked before an LLM call.
    """

    normalized = " ".join(
        str(question).split()
    )

    flags: list[str] = []

    if any(
        pattern.search(normalized)
        for pattern in _INJECTION_PATTERNS
    ):
        flags.append(
            "PROMPT_INJECTION"
        )

    if (
        _PROTECTED_DATA_TERM_RE.search(normalized)
        and _EXFILTRATION_VERB_RE.search(normalized)
    ):
        flags.append(
            "PROTECTED_DATA_REQUEST"
        )

    if (
        _MUTATION_START_RE.search(normalized)
        or _MUTATION_REQUEST_RE.search(normalized)
    ):
        flags.append(
            "FINANCIAL_MUTATION_REQUEST"
        )

    if any(
        pattern.search(normalized)
        for pattern in _HUMAN_REVIEW_BYPASS_PATTERNS
    ):
        flags.append(
            "HUMAN_REVIEW_BYPASS_REQUEST"
        )

    if not flags:
        return RequestGuardrailResult(
            allowed=True,
            safety_state="GROUNDED",
            reason=None,
            flags=(),
        )

    reasons: list[str] = []

    if "PROMPT_INJECTION" in flags:
        reasons.append(
            "The request attempts to override protected AI instructions."
        )

    if "PROTECTED_DATA_REQUEST" in flags:
        reasons.append(
            "Benchmark, ground-truth and evaluation data are not available "
            "to the operational AI assistant."
        )

    if "FINANCIAL_MUTATION_REQUEST" in flags:
        reasons.append(
            "Ask FlowGuard is advisory and cannot modify or execute "
            "financial records or transactions."
        )

    if "HUMAN_REVIEW_BYPASS_REQUEST" in flags:
        reasons.append(
            "Required human review cannot be bypassed by "
            "Ask FlowGuard."
        )

    return RequestGuardrailResult(
        allowed=False,
        safety_state="REFUSED",
        reason=" ".join(reasons),
        flags=tuple(flags),
    )


# ----------------------------------------------------------------------
# Controlled-context safety
# ----------------------------------------------------------------------

_FORBIDDEN_CONTEXT_TERMS = (
    "benchmark",
    "ground_truth",
    "ground-truth",
    "data/evaluation",
    "evaluation/ground",
    "normalized_path",
    "manifest_path",
    "raw_dir",
)


def validate_llm_context_payload(
    payload: dict,
) -> None:
    """
    Fail closed if protected internal/evaluation metadata enters the
    provider context.

    This validation is deliberately performed immediately before the
    provider boundary as defense in depth.
    """

    serialized = json.dumps(
        payload,
        sort_keys=True,
        default=str,
    ).lower()

    violations = [
        term
        for term in _FORBIDDEN_CONTEXT_TERMS
        if term in serialized
    ]

    if violations:
        raise RuntimeError(
            "Unsafe AI context payload contains protected metadata: "
            + ", ".join(violations)
        )


# ----------------------------------------------------------------------
# Numeric-grounding validation
# ----------------------------------------------------------------------

NumericClaimKind = Literal[
    "money",
    "percent",
    "date",
    "number",
]


@dataclass(frozen=True)
class NumericClaim:
    kind: NumericClaimKind
    raw: str
    numeric_value: Decimal | None = None
    suffix: str | None = None


_DATE_RE = re.compile(
    r"\b\d{4}-\d{2}-\d{2}\b"
)

_MONEY_RE = re.compile(
    r"₹\s*"
    r"(?P<number>\d[\d,]*(?:\.\d+)?)"
    r"\s*"
    r"(?P<suffix>"
    r"cr|crore|crores|"
    r"l|lakh|lakhs"
    r")?",
    re.IGNORECASE,
)

_PERCENT_RE = re.compile(
    r"(?P<number>\d+(?:\.\d+)?)\s*%"
)

_GENERIC_NUMBER_RE = re.compile(
    r"(?<![A-Za-z0-9_.-])"
    r"(?P<number>\d+(?:\.\d+)?)"
    r"(?![A-Za-z0-9_.-])"
)


def _decimal_from_text(
    value: str,
) -> Decimal:
    cleaned = (
        str(value)
        .replace(",", "")
        .strip()
    )

    return Decimal(cleaned)


def extract_numeric_claims(
    text: str,
) -> list[NumericClaim]:
    """
    Extract financial/date/numeric claims from generated prose.

    Specific forms are extracted first and masked before generic-number
    detection, preventing one monetary or date claim from being counted
    several times.
    """

    working = list(
        str(text)
    )

    claims: list[NumericClaim] = []

    def mask(
        start: int,
        end: int,
    ) -> None:
        for index in range(
            start,
            end,
        ):
            working[index] = " "

    original = str(text)

    for match in _DATE_RE.finditer(
        original
    ):
        claims.append(
            NumericClaim(
                kind="date",
                raw=match.group(0),
            )
        )

        mask(
            match.start(),
            match.end(),
        )

    masked_text = "".join(
        working
    )

    for match in _MONEY_RE.finditer(
        masked_text
    ):
        number = _decimal_from_text(
            match.group("number")
        )

        suffix = match.group(
            "suffix"
        )

        claims.append(
            NumericClaim(
                kind="money",
                raw=match.group(0),
                numeric_value=number,
                suffix=(
                    suffix.lower()
                    if suffix
                    else None
                ),
            )
        )

        mask(
            match.start(),
            match.end(),
        )

    masked_text = "".join(
        working
    )

    for match in _PERCENT_RE.finditer(
        masked_text
    ):
        claims.append(
            NumericClaim(
                kind="percent",
                raw=match.group(0),
                numeric_value=_decimal_from_text(
                    match.group(
                        "number"
                    )
                ),
            )
        )

        mask(
            match.start(),
            match.end(),
        )

    masked_text = "".join(
        working
    )

    for match in _GENERIC_NUMBER_RE.finditer(
        masked_text
    ):
        claims.append(
            NumericClaim(
                kind="number",
                raw=match.group(0),
                numeric_value=_decimal_from_text(
                    match.group(
                        "number"
                    )
                ),
            )
        )

    return claims


def _evidence_decimal(
    evidence: TrustedEvidence,
) -> Decimal | None:
    if evidence.unit not in {
        "INR",
        "percent",
        "count",
        "days",
    }:
        return None

    try:
        return _decimal_from_text(
            evidence.value
        )

    except InvalidOperation:
        return None


def _money_claim_supported(
    claim: NumericClaim,
    evidence: TrustedEvidence,
) -> bool:
    if (
        evidence.unit != "INR"
        or claim.numeric_value is None
    ):
        return False

    evidence_value = _evidence_decimal(
        evidence
    )

    if evidence_value is None:
        return False

    suffix = (
        claim.suffix or ""
    ).lower()

    if suffix in {
        "l",
        "lakh",
        "lakhs",
    }:
        displayed = (
            evidence_value
            / Decimal("100000")
        ).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )

        return (
            claim.numeric_value
            == displayed
        )

    if suffix in {
        "cr",
        "crore",
        "crores",
    }:
        displayed = (
            evidence_value
            / Decimal("10000000")
        ).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )

        return (
            claim.numeric_value
            == displayed
        )

    return (
        claim.numeric_value
        == evidence_value
    )


def _claim_supported_by_evidence(
    claim: NumericClaim,
    evidence: TrustedEvidence,
) -> bool:
    if claim.kind == "date":
        return (
            evidence.unit == "date"
            and evidence.value == claim.raw
        )

    if claim.kind == "money":
        return _money_claim_supported(
            claim,
            evidence,
        )

    if claim.numeric_value is None:
        return False

    evidence_value = _evidence_decimal(
        evidence
    )

    if evidence_value is None:
        return False

    if claim.kind == "percent":
        return (
            evidence.unit == "percent"
            and claim.numeric_value
            == evidence_value
        )

    return (
        claim.numeric_value
        == evidence_value
    )


def find_unsupported_numeric_claims(
    *,
    text: str,
    evidence: list[TrustedEvidence],
) -> list[NumericClaim]:
    """
    Return generated numeric claims that cannot be supported by any of the
    evidence IDs explicitly selected by the reasoning model.
    """

    unsupported: list[NumericClaim] = []

    for claim in extract_numeric_claims(
        text
    ):
        if any(
            _claim_supported_by_evidence(
                claim,
                item,
            )
            for item in evidence
        ):
            continue

        unsupported.append(
            claim
        )

    return unsupported


# ----------------------------------------------------------------------
# Draft-level safety validation
# ----------------------------------------------------------------------

@dataclass(frozen=True)
class DraftValidationResult:
    valid: bool

    safety_state: AISafetyState

    report: AIValidationReport

    resolved_evidence: tuple[
        TrustedEvidence,
        ...,
    ]

    violations: tuple[
        str,
        ...,
    ]

    unsupported_numeric_claims: tuple[
        str,
        ...,
    ]


def _draft_text(
    draft: LLMAnswerDraft,
) -> str:
    parts: list[str] = [
        draft.answer,
    ]

    for action in (
        draft.recommended_actions
    ):
        parts.append(
            action.action
        )

        parts.append(
            action.rationale
        )

    parts.extend(
        draft.limitations
    )

    return "\n".join(
        parts
    )


def _preserves_human_review(
    text: str,
) -> bool:
    return not any(
        pattern.search(text)
        for pattern
        in _HUMAN_REVIEW_BYPASS_PATTERNS
    )


def validate_llm_draft(
    *,
    draft: LLMAnswerDraft,
    evidence_index: dict[
        str,
        TrustedEvidence,
    ],
) -> DraftValidationResult:
    """
    Validate one provider-generated structured response.

    The model is never trusted to self-certify grounding. Evidence
    resolution, numeric verification and human-review preservation are
    all application-controlled checks.
    """

    violations: list[str] = []

    try:
        resolved = (
            resolve_evidence_ids(
                draft.evidence_ids,
                evidence_index,
            )
        )

        evidence_validated = True

    except ValueError:
        resolved = []

        evidence_validated = False

        violations.append(
            "UNKNOWN_EVIDENCE_REFERENCE"
        )

    generated_text = _draft_text(
        draft
    )

    unsupported_claims = (
        find_unsupported_numeric_claims(
            text=generated_text,
            evidence=resolved,
        )
    )

    numeric_validated = (
        len(unsupported_claims) == 0
    )

    if not numeric_validated:
        violations.append(
            "UNSUPPORTED_NUMERIC_CLAIM"
        )

    human_review_preserved = (
        _preserves_human_review(
            generated_text
        )
    )

    if not human_review_preserved:
        violations.append(
            "HUMAN_REVIEW_BYPASS"
        )

    has_evidence = len(resolved) > 0

    if not has_evidence:
        violations.append(
            "NO_EVIDENCE_SELECTED"
        )

    grounded = (
        evidence_validated
        and has_evidence
        and numeric_validated
        and human_review_preserved
    )

    report = AIValidationReport(
        grounded=grounded,
        numeric_claims_validated=(
            numeric_validated
        ),
        evidence_references_validated=(
            evidence_validated
        ),
        unsupported_claims_detected=len(
            unsupported_claims
        ),
        benchmark_data_accessed=False,
        human_review_preserved=(
            human_review_preserved
        ),
    )

    return DraftValidationResult(
        valid=grounded,
        safety_state=(
            "GROUNDED"
            if grounded
            else "LIMITED"
        ),
        report=report,
        resolved_evidence=tuple(
            resolved
        ),
        violations=tuple(
            violations
        ),
        unsupported_numeric_claims=tuple(
            claim.raw.strip()
            for claim
            in unsupported_claims
        ),
    )
