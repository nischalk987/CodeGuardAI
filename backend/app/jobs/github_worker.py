"""Background GitHub PR fetch and deterministic changed-line scan."""

from __future__ import annotations

import logging
from dataclasses import replace
from pathlib import PurePosixPath
import re

from sqlalchemy.orm import Session

from app.analysis import BuiltinAnalyzer
from app.application.reviews import ReviewService
from app.core.config import get_settings
from app.core.logging import redact_sensitive_text
from app.domain.enums import ReviewStatus
from app.infrastructure.github.client import (
    GitHubAppClient,
    GitHubClientError,
    GitHubDiffLimitError,
    GitHubPermissionError,
    GitHubRateLimitError,
)
from app.infrastructure.persistence.database import get_engine
from app.infrastructure.persistence.repository import SqlAlchemyReviewRepository
from app.jobs.queue import celery_app

logger = logging.getLogger(__name__)
_SUPPORTED = {".py", ".js", ".jsx", ".ts", ".tsx"}


def enqueue_github_review(
    review_id: str, repository: str, number: int, commit_sha: str, installation_id: int
) -> None:
    execute_github_review.apply_async(
        args=[review_id, repository, number, commit_sha, installation_id],
        argsrepr=f"({review_id!r}, {repository!r}, {number}, {commit_sha!r}, {installation_id})",
    )


@celery_app.task(name="codeguard.execute_github_review", max_retries=0)
def execute_github_review(
    review_id: str, repository: str, number: int, commit_sha: str, installation_id: int
) -> str:
    """Fetch bounded PR patches and run local checks against added source lines only."""
    with Session(get_engine(), expire_on_commit=False) as session:
        repository_adapter = SqlAlchemyReviewRepository(session)
        service = ReviewService(repository_adapter)
        review = repository_adapter.claim_queued(review_id)
        if review is None:
            return service.get(review_id).status.value
        client = GitHubAppClient(get_settings())
        try:
            files = client.fetch_pull_request_files(
                repository, number, installation_id, expected_sha=commit_sha
            )
            findings = []
            analyzer = BuiltinAnalyzer()
            for changed_file in files:
                path = PurePosixPath(changed_file.path)
                if (
                    path.suffix.lower() not in _SUPPORTED
                    or path.is_absolute()
                    or ".." in path.parts
                    or re.match(r"^[A-Za-z]:", changed_file.path)
                ):
                    continue
                if not changed_file.additions:
                    continue
                snippet = "\n".join(changed_file.additions)
                for finding in analyzer.analyze_source(snippet, changed_file.path):
                    start_index = min(finding.start_line - 1, len(changed_file.line_numbers) - 1)
                    end_index = min(finding.end_line - 1, len(changed_file.line_numbers) - 1)
                    if start_index < 0 or end_index < 0:
                        continue
                    findings.append(
                        replace(
                            finding,
                            id="",
                            start_line=changed_file.line_numbers[start_index],
                            end_line=max(
                                changed_file.line_numbers[start_index],
                                changed_file.line_numbers[end_index],
                            ),
                            evidence=redact_sensitive_text(finding.evidence),
                        )
                    )
            completed = review.with_findings(tuple(findings)).complete(
                summary=(
                    f"Local deterministic checks scanned added lines for PR #{number} at "
                    f"commit {commit_sha[:12]}. No AI provider was called."
                )
            )
            repository_adapter.save(completed)
            logger.info("GitHub review completed", extra={"review_id": review_id})
            return ReviewStatus.COMPLETED.value
        except GitHubRateLimitError:
            return _fail(repository_adapter, review, review_id, "GitHub API rate limit reached; retry later.")
        except GitHubPermissionError:
            return _fail(repository_adapter, review, review_id, "GitHub App lacks pull-request read permission.")
        except GitHubDiffLimitError:
            return _fail(repository_adapter, review, review_id, "Pull request exceeds configured diff limits.")
        except GitHubClientError:
            return _fail(repository_adapter, review, review_id, "GitHub could not provide the pull-request diff.")
        except Exception as exc:
            logger.error(
                "GitHub review failed",
                extra={"review_id": review_id, "error_type": type(exc).__name__},
            )
            return _fail(repository_adapter, review, review_id, "The pull-request review could not be completed.")
        finally:
            client.close()


def _fail(repository: SqlAlchemyReviewRepository, review, review_id: str, reason: str) -> str:
    if review.status is ReviewStatus.RUNNING:
        repository.save(review.fail(reason=reason))
    logger.warning("GitHub review did not complete", extra={"review_id": review_id})
    return ReviewStatus.FAILED.value
