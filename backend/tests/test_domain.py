from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone

import pytest

from app.domain import (
    EvidenceCertainty,
    Finding,
    FindingSource,
    FindingStatus,
    InvalidReviewTransition,
    Review,
    ReviewSourceType,
    ReviewStatus,
    ReviewSummary,
    Severity,
    stable_finding_id,
)


def make_finding(**overrides) -> Finding:
    values = {
        "rule_id": "SEC001",
        "source": FindingSource.STATIC,
        "severity": Severity.HIGH,
        "category": "Security",
        "message": "A sensitive value may be exposed.",
        "file_path": "src/auth.py",
        "start_line": 12,
        "end_line": 14,
        "confidence": 90,
        "evidence": "logger.debug(token)",
        "suggested_fix": "Log a request identifier instead.",
    }
    return Finding(**(values | overrides))


def make_review(**overrides) -> Review:
    values = {
        "id": "review-123",
        "source_type": ReviewSourceType.PULL_REQUEST,
        "repository": "owner/repository",
        "ref": "refs/pull/12/head",
    }
    return Review(**(values | overrides))


def test_review_moves_through_valid_lifecycle_and_summarizes_findings() -> None:
    utc = timezone(timedelta(0))
    started_at = datetime.now(utc) + timedelta(seconds=1)
    completed_at = started_at + timedelta(seconds=1)
    review = make_review().start(at=started_at)
    review = review.with_findings([make_finding()])
    completed = review.complete(at=completed_at, summary="One high-severity issue.")

    assert completed.status is ReviewStatus.COMPLETED
    assert completed.completed_at == completed_at
    assert completed.summary == ReviewSummary(
        text="One high-severity issue.", high=1, total_findings=1
    )
    assert review.status is ReviewStatus.RUNNING  # Each transition returns a new snapshot.


@pytest.mark.parametrize(
    ("initial", "target"),
    [
        (ReviewStatus.QUEUED, ReviewStatus.COMPLETED),
        (ReviewStatus.COMPLETED, ReviewStatus.RUNNING),
        (ReviewStatus.FAILED, ReviewStatus.RUNNING),
    ],
)
def test_invalid_review_transitions_are_rejected(
    initial: ReviewStatus, target: ReviewStatus
) -> None:
    completed_at = datetime.now(timezone(timedelta(0)))
    kwargs = {"status": initial}
    if initial is ReviewStatus.COMPLETED:
        kwargs["created_at"] = completed_at - timedelta(seconds=1)
        kwargs["completed_at"] = completed_at
        kwargs["updated_at"] = completed_at
    review = make_review(**kwargs)

    with pytest.raises(InvalidReviewTransition):
        review.transition_to(target, at=completed_at + timedelta(seconds=1))


def test_queued_review_can_fail_without_running() -> None:
    failed = make_review().fail()
    assert failed.status is ReviewStatus.FAILED
    with pytest.raises(InvalidReviewTransition):
        failed.with_findings([make_finding()])


def test_completed_review_and_findings_are_immutable() -> None:
    completed = (
        make_review()
        .start()
        .with_findings([make_finding()])
        .complete()
    )

    with pytest.raises(InvalidReviewTransition):
        completed.with_findings([])
    with pytest.raises(InvalidReviewTransition):
        completed.fail()
    with pytest.raises(FrozenInstanceError):
        completed.status = ReviewStatus.RUNNING
    with pytest.raises(FrozenInstanceError):
        completed.findings[0].message = "rewritten"


def test_finding_id_is_stable_for_same_rule_provenance_and_location() -> None:
    original = make_finding()
    repeated = make_finding(message="Different wording, same source location")

    assert original.id == repeated.id
    assert original.id == stable_finding_id(
        rule_id="SEC001",
        source=FindingSource.STATIC,
        file_path="src/auth.py",
        start_line=12,
        end_line=14,
    )
    assert make_finding(end_line=15).id != original.id


@pytest.mark.parametrize(
    "overrides",
    [
        {"start_line": 0},
        {"end_line": 11},
        {"confidence": -1},
        {"confidence": 101},
        {"confidence": True},
        {"severity": "urgent"},
        {"source": "unknown"},
        {"rule_id": " "},
        {"message": ""},
        {"evidence": ""},
        {"file_path": "../outside.py"},
        {"file_path": "C:\\secrets.py"},
        {"id": "caller-controlled-id"},
        {"status": "new"},
    ],
)
def test_malformed_findings_are_rejected(overrides: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        make_finding(**overrides)


def test_ai_findings_default_to_hypothesis_and_static_to_confirmed() -> None:
    assert make_finding().certainty is EvidenceCertainty.CONFIRMED
    assert make_finding(source=FindingSource.AI).certainty is EvidenceCertainty.HYPOTHESIS
    assert make_finding(source=FindingSource.AI, status=FindingStatus.ACCEPTED).status is FindingStatus.ACCEPTED


def test_review_metadata_and_timestamps_are_validated() -> None:
    with pytest.raises(ValueError, match="timezone"):
        make_review(created_at=datetime(2026, 1, 1), updated_at=datetime(2026, 1, 1))
    with pytest.raises(ValueError, match="earlier"):
        make_review(
            created_at=datetime(2026, 1, 2, tzinfo=timezone(timedelta(0))),
            updated_at=datetime(2026, 1, 1, tzinfo=timezone(timedelta(0))),
        )


def test_summary_counts_must_be_consistent() -> None:
    with pytest.raises(ValueError, match="sum"):
        ReviewSummary(high=1, total_findings=2)

