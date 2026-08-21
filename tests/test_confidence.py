from backend.app.reconciliation.confidence import (
    ConfidenceBand,
    assess_confidence,
    weighted_score,
)


def test_high_clear_score_auto_matches():

    result = assess_confidence(
        96,
        82,
    )

    assert (
        result.band
        == ConfidenceBand.AUTO_MATCH
    )

    assert result.accepted is True

    assert result.requires_review is False


def test_high_but_ambiguous_score_requires_review():

    result = assess_confidence(
        96,
        92,
    )

    assert (
        result.band
        == ConfidenceBand.HUMAN_REVIEW
    )

    assert result.accepted is False

    assert result.requires_review is True


def test_moderate_score_requires_review():

    result = assess_confidence(
        82,
        60,
    )

    assert (
        result.band
        == ConfidenceBand.HUMAN_REVIEW
    )


def test_low_score_is_rejected():

    result = assess_confidence(
        60,
        None,
    )

    assert (
        result.band
        == ConfidenceBand.REJECT
    )

    assert result.accepted is False


def test_weighted_score_is_transparent():

    score = weighted_score(
        amount=100,
        customer=100,
        date=60,
        reference=80,
        amount_weight=0.40,
        customer_weight=0.30,
        date_weight=0.10,
        reference_weight=0.20,
    )

    assert score == 92.0


def test_invalid_weights_raise_error():

    try:

        weighted_score(
            amount=100,
            customer=100,
            date=100,
            reference=100,
            amount_weight=0.50,
            customer_weight=0.30,
            date_weight=0.20,
            reference_weight=0.20,
        )

        assert False

    except ValueError:
        assert True