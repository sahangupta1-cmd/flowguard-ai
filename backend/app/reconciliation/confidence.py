from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


# ============================================================
# CONFIDENCE OUTCOMES
# ============================================================


class ConfidenceBand(str, Enum):
    """
    Operational decision produced from a fuzzy-match score.
    """

    AUTO_MATCH = "AUTO_MATCH"
    HUMAN_REVIEW = "HUMAN_REVIEW"
    REJECT = "REJECT"


# ============================================================
# POLICY
# ============================================================


@dataclass(frozen=True, slots=True)
class ConfidencePolicy:
    """
    Centralized fuzzy-matching confidence policy.

    Keeping thresholds in one place makes them measurable
    and tunable later using the evaluation benchmark.
    """

    auto_match_threshold: float = 90.0
    review_threshold: float = 75.0

    # Even a high-scoring candidate must clearly beat
    # the second-best candidate before automatic acceptance.
    minimum_auto_margin: float = 8.0

    minimum_review_margin: float = 3.0


DEFAULT_POLICY = ConfidencePolicy()


# ============================================================
# RESULT MODEL
# ============================================================


@dataclass(frozen=True, slots=True)
class ConfidenceAssessment:
    """
    Result of confidence-policy evaluation.
    """

    band: ConfidenceBand

    score: float

    second_best_score: float | None

    margin: float | None

    accepted: bool

    requires_review: bool

    reason: str


# ============================================================
# HELPERS
# ============================================================


def clamp_score(
    value: float,
) -> float:
    """
    Force scores into the range 0-100.
    """

    return max(
        0.0,
        min(100.0, float(value)),
    )


def weighted_score(
    *,
    amount: float,
    customer: float,
    date: float,
    reference: float,
    amount_weight: float,
    customer_weight: float,
    date_weight: float,
    reference_weight: float,
) -> float:
    """
    Produce a transparent weighted confidence score.

    Component scores must each be between 0 and 100.
    Weights must total 1.0.
    """

    weights = (
        amount_weight
        + customer_weight
        + date_weight
        + reference_weight
    )

    if abs(weights - 1.0) > 0.000001:
        raise ValueError(
            "Confidence weights must total 1.0."
        )

    result = (
        clamp_score(amount) * amount_weight
        + clamp_score(customer) * customer_weight
        + clamp_score(date) * date_weight
        + clamp_score(reference) * reference_weight
    )

    return round(
        clamp_score(result),
        2,
    )


# ============================================================
# POLICY ASSESSMENT
# ============================================================


def assess_confidence(
    best_score: float,
    second_best_score: float | None = None,
    *,
    policy: ConfidencePolicy = DEFAULT_POLICY,
) -> ConfidenceAssessment:
    """
    Convert candidate scores into an operational decision.

    Safety principles:

    1. A strong score alone is not enough.
    2. Ambiguous candidates are never auto-matched.
    3. Medium-confidence candidates require human review.
    4. Low-confidence candidates are rejected.
    """

    best = clamp_score(
        best_score
    )

    second = (
        None
        if second_best_score is None
        else clamp_score(second_best_score)
    )

    margin = (
        None
        if second is None
        else round(best - second, 2)
    )

    # --------------------------------------------------------
    # AUTO MATCH
    # --------------------------------------------------------

    if best >= policy.auto_match_threshold:

        if (
            margin is None
            or margin >= policy.minimum_auto_margin
        ):

            return ConfidenceAssessment(
                band=ConfidenceBand.AUTO_MATCH,
                score=best,
                second_best_score=second,
                margin=margin,
                accepted=True,
                requires_review=False,
                reason=(
                    "High confidence with sufficient "
                    "separation from competing candidates."
                ),
            )

        return ConfidenceAssessment(
            band=ConfidenceBand.HUMAN_REVIEW,
            score=best,
            second_best_score=second,
            margin=margin,
            accepted=False,
            requires_review=True,
            reason=(
                "Top candidate is high confidence but "
                "too close to another candidate."
            ),
        )

    # --------------------------------------------------------
    # REVIEW
    # --------------------------------------------------------

    if best >= policy.review_threshold:

        if (
            margin is not None
            and margin < policy.minimum_review_margin
        ):

            return ConfidenceAssessment(
                band=ConfidenceBand.HUMAN_REVIEW,
                score=best,
                second_best_score=second,
                margin=margin,
                accepted=False,
                requires_review=True,
                reason=(
                    "Candidate is plausible but highly "
                    "ambiguous."
                ),
            )

        return ConfidenceAssessment(
            band=ConfidenceBand.HUMAN_REVIEW,
            score=best,
            second_best_score=second,
            margin=margin,
            accepted=False,
            requires_review=True,
            reason=(
                "Candidate has moderate confidence and "
                "requires human confirmation."
            ),
        )

    # --------------------------------------------------------
    # REJECT
    # --------------------------------------------------------

    return ConfidenceAssessment(
        band=ConfidenceBand.REJECT,
        score=best,
        second_best_score=second,
        margin=margin,
        accepted=False,
        requires_review=True,
        reason=(
            "Candidate confidence is below the minimum "
            "safe matching threshold."
        ),
    )
    