"""SQLAlchemy implementation of the application review repository contract."""

from __future__ import annotations

from datetime import timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.domain import Finding, Review, ReviewSourceType, ReviewStatus, ReviewSummary, Severity
from app.domain.enums import EvidenceCertainty, FindingSource, FindingStatus
from app.infrastructure.persistence.models import FindingRow, ReviewRow


class SqlAlchemyReviewRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def save(self, review: Review) -> None:
        row = ReviewRow(
            id=review.id,
            source_type=review.source_type.value,
            repository=review.repository or "local",
            branch=review.ref or "local",
            status=review.status.value,
            risk_score=_risk_score(review),
            summary_text=review.summary.text,
            created_at=review.created_at,
            updated_at=review.updated_at,
            completed_at=review.completed_at,
            findings=[_finding_row(review.id, finding) for finding in review.findings],
        )
        self._session.add(row)
        self._session.commit()

    def get(self, review_id: str) -> Review | None:
        row = self._session.scalar(
            select(ReviewRow)
            .where(ReviewRow.id == review_id)
            .options(selectinload(ReviewRow.findings))
        )
        return _to_domain(row) if row else None

    def list(self, *, limit: int, offset: int) -> list[Review]:
        rows = self._session.scalars(
            select(ReviewRow)
            .order_by(ReviewRow.created_at.desc(), ReviewRow.id.desc())
            .offset(offset)
            .limit(limit)
            .options(selectinload(ReviewRow.findings))
        )
        return [_to_domain(row) for row in rows]

    def findings(
        self,
        review_id: str,
        *,
        severity: str | None,
        category: str | None,
        status: str | None,
        limit: int,
        offset: int,
    ) -> list[Finding]:
        statement = select(FindingRow).where(FindingRow.review_id == review_id)
        if severity:
            statement = statement.where(FindingRow.severity == severity)
        if category:
            statement = statement.where(func.lower(FindingRow.category) == category.strip().lower())
        if status:
            statement = statement.where(FindingRow.status == status)
        rows = self._session.scalars(
            statement.order_by(FindingRow.file_path, FindingRow.line)
            .offset(offset)
            .limit(limit)
        )
        return [_finding_to_domain(row) for row in rows]


def _finding_row(review_id: str, finding: Finding) -> FindingRow:
    title = finding.rule_id.rsplit(".", 1)[-1].replace("_", " ").title()
    return FindingRow(
        review_id=review_id,
        id=finding.id,
        rule_id=finding.rule_id,
        source=finding.source.value,
        severity=finding.severity.value,
        category=finding.category,
        status=finding.status.value,
        file_path=finding.file_path,
        line=finding.start_line,
        end_line=finding.end_line,
        title=title,
        message=finding.message,
        explanation=finding.message,
        suggested_fix=finding.suggested_fix,
        confidence=finding.confidence,
        evidence=finding.evidence,
        analyzer_name=finding.analyzer_name,
        analyzer_version=finding.analyzer_version,
        certainty=finding.certainty.value,
    )


def _finding_to_domain(row: FindingRow) -> Finding:
    return Finding(
        id=row.id,
        rule_id=row.rule_id,
        source=FindingSource(row.source),
        severity=Severity(row.severity),
        category=row.category,
        status=FindingStatus(row.status),
        file_path=row.file_path,
        start_line=row.line,
        end_line=row.end_line,
        message=row.message,
        confidence=row.confidence,
        evidence=row.evidence,
        suggested_fix=row.suggested_fix,
        analyzer_name=row.analyzer_name,
        analyzer_version=row.analyzer_version,
        certainty=EvidenceCertainty(row.certainty),
    )


def _to_domain(row: ReviewRow) -> Review:
    findings = tuple(_finding_to_domain(item) for item in row.findings)
    status = ReviewStatus(row.status)
    return Review(
        id=row.id,
        source_type=ReviewSourceType(row.source_type),
        repository=row.repository,
        ref=row.branch,
        status=status,
        created_at=_aware_utc(row.created_at),
        updated_at=_aware_utc(row.updated_at),
        completed_at=_aware_utc(row.completed_at) if row.completed_at else None,
        findings=findings,
        summary=ReviewSummary.from_findings(findings, row.summary_text),
    )


def _risk_score(review: Review) -> int:
    weights = {
        Severity.CRITICAL: 35,
        Severity.HIGH: 20,
        Severity.MEDIUM: 10,
        Severity.LOW: 3,
    }
    return min(100, sum(weights[item.severity] for item in review.findings))


def _aware_utc(value):
    """SQLite drops timezone markers on read; interpret stored UTC timestamps consistently."""
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
