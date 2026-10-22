"""Authenticated workspace repository and review endpoints."""
import re
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.v1.auth import current_user
from app.infrastructure.persistence.database import get_session
from app.infrastructure.persistence.models import RepositoryRow, ReviewRow, UserRow

router = APIRouter(prefix="/workspace", tags=["workspace"])
_GITHUB_REPO = re.compile(r"^https://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)/?$")


class RepositoryCreate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    url: str = Field(min_length=20, max_length=300)
    default_branch: str = Field(default="main", min_length=1, max_length=100)


class RepositoryResponse(BaseModel):
    id: str
    name: str
    url: str
    default_branch: str
    created_at: datetime


class ReviewSummaryResponse(BaseModel):
    review_id: str
    repository: str
    branch: str
    status: str
    risk_score: int
    created_at: datetime
    failure_reason: str | None = None


@router.get("/repositories", response_model=list[RepositoryResponse])
def list_repositories(
    user: UserRow = Depends(current_user),
    session: Session = Depends(get_session),
) -> list[RepositoryResponse]:
    rows = session.scalars(
        select(RepositoryRow).where(RepositoryRow.owner_user_id == user.id).order_by(RepositoryRow.created_at.desc())
    ).all()
    return [RepositoryResponse(id=row.id, name=row.name, url=row.url, default_branch=row.default_branch, created_at=row.created_at) for row in rows]


@router.post("/repositories", response_model=RepositoryResponse, status_code=status.HTTP_201_CREATED)
def add_repository(
    payload: RepositoryCreate,
    user: UserRow = Depends(current_user),
    session: Session = Depends(get_session),
) -> RepositoryResponse:
    normalized = payload.url.strip().removesuffix(".git").rstrip("/")
    match = _GITHUB_REPO.fullmatch(normalized)
    if not match or match.group(1).lower() in {"settings", "login", "signup"} or match.group(2) in {".", ".."}:
        raise HTTPException(status_code=422, detail="Enter a valid GitHub repository URL")
    name = (payload.name or f"{match.group(1)}/{match.group(2)}").strip()
    if not name:
        raise HTTPException(status_code=422, detail="Repository name cannot be empty")
    row = RepositoryRow(
        id=str(uuid4()),
        owner_user_id=user.id,
        name=name,
        url=normalized,
        default_branch=payload.default_branch.strip() or "main",
        created_at=datetime.now(timezone.utc),
    )
    session.add(row)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(status_code=409, detail="This repository is already saved in your workspace") from None
    session.refresh(row)
    return RepositoryResponse(id=row.id, name=row.name, url=row.url, default_branch=row.default_branch, created_at=row.created_at)


@router.delete("/repositories/{repository_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_repository(
    repository_id: str,
    user: UserRow = Depends(current_user),
    session: Session = Depends(get_session),
) -> None:
    row = session.scalar(select(RepositoryRow).where(
        RepositoryRow.id == repository_id,
        RepositoryRow.owner_user_id == user.id,
    ))
    if row is None:
        raise HTTPException(status_code=404, detail="Repository not found")
    session.delete(row)
    session.commit()


@router.get("/reviews", response_model=list[ReviewSummaryResponse])
def list_user_reviews(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=100_000),
    user: UserRow = Depends(current_user),
    session: Session = Depends(get_session),
) -> list[ReviewSummaryResponse]:
    rows = session.scalars(
        select(ReviewRow)
        .where(ReviewRow.owner_user_id == user.id)
        .order_by(ReviewRow.created_at.desc())
        .offset(offset)
        .limit(limit)
    ).all()
    return [ReviewSummaryResponse(
        review_id=row.id,
        repository=row.repository,
        branch=row.branch,
        status=row.status,
        risk_score=row.risk_score,
        created_at=row.created_at,
        failure_reason=row.failure_reason,
    ) for row in rows]
