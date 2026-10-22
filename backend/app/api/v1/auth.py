"""Email/password registration and login endpoints.

This is a minimal first-party auth foundation. It does not provide email verification,
password reset, social login, or refresh-token rotation.
"""
import base64
import hashlib
import hmac
import os
import re
import secrets
import time
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infrastructure.persistence.database import get_session
from app.infrastructure.persistence.models import UserRow

router = APIRouter(prefix="/auth", tags=["authentication"])
bearer = HTTPBearer(auto_error=False)
_EMAIL = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
_TOKEN_TTL = 60 * 60 * 12


class RegisterRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    email: str = Field(min_length=3, max_length=254)
    display_name: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=10, max_length=128)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        value = value.lower()
        if not _EMAIL.fullmatch(value):
            raise ValueError("Enter a valid email address")
        return value


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=128)


class UserResponse(BaseModel):
    id: str
    email: str
    display_name: str


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = _TOKEN_TTL
    user: UserResponse


def _secret() -> bytes:
    value = os.getenv("AUTH_SECRET_KEY", "").strip()
    if len(value) < 32:
        raise HTTPException(
            status_code=503,
            detail="Authentication is not configured. Set AUTH_SECRET_KEY to a random secret of at least 32 characters.",
        )
    return value.encode()


def _password_hash(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return "scrypt$" + base64.urlsafe_b64encode(salt).decode() + "$" + base64.urlsafe_b64encode(digest).decode()


def _password_matches(password: str, stored: str) -> bool:
    try:
        algorithm, salt_text, digest_text = stored.split("$", 2)
        if algorithm != "scrypt":
            return False
        salt = base64.urlsafe_b64decode(salt_text.encode())
        expected = base64.urlsafe_b64decode(digest_text.encode())
        actual = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def _issue_token(user: UserRow) -> str:
    expires = int(time.time()) + _TOKEN_TTL
    subject = f"{user.id}:{expires}"
    signature = hmac.new(_secret(), subject.encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(subject.encode()).decode().rstrip("=") + "." + base64.urlsafe_b64encode(signature).decode().rstrip("=")


def _user_from_token(token: str, session: Session) -> UserRow:
    try:
        encoded_subject, encoded_signature = token.split(".", 1)
        subject = base64.urlsafe_b64decode((encoded_subject + "=" * (-len(encoded_subject) % 4)).encode()).decode()
        signature = base64.urlsafe_b64decode((encoded_signature + "=" * (-len(encoded_signature) % 4)).encode())
        user_id, expires_text = subject.rsplit(":", 1)
        expected = hmac.new(_secret(), subject.encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(signature, expected) or int(expires_text) < int(time.time()):
            raise ValueError("invalid token")
    except (ValueError, TypeError, UnicodeDecodeError):
        raise HTTPException(status_code=401, detail="Invalid or expired access token") from None
    user = session.get(UserRow, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="Account no longer exists")
    return user


def current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    session: Session = Depends(get_session),
) -> UserRow:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Sign in required", headers={"WWW-Authenticate": "Bearer"})
    return _user_from_token(credentials.credentials, session)


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, session: Session = Depends(get_session)) -> AuthResponse:
    _secret()
    existing = session.scalar(select(UserRow).where(UserRow.email == payload.email))
    if existing is not None:
        raise HTTPException(status_code=409, detail="An account with this email already exists")
    user = UserRow(
        id=str(uuid4()),
        email=payload.email,
        display_name=payload.display_name,
        password_hash=_password_hash(payload.password),
        created_at=datetime.now(timezone.utc),
    )
    session.add(user)
    try:
        session.commit()
    except Exception:
        session.rollback()
        # Do not expose database internals to callers.
        raise HTTPException(status_code=409, detail="Could not create account; the email may already be registered") from None
    session.refresh(user)
    return AuthResponse(access_token=_issue_token(user), user=UserResponse(id=user.id, email=user.email, display_name=user.display_name))


@router.post("/login", response_model=AuthResponse)
def login(payload: LoginRequest, session: Session = Depends(get_session)) -> AuthResponse:
    _secret()
    user = session.scalar(select(UserRow).where(UserRow.email == payload.email.strip().lower()))
    # Run a dummy scrypt operation for unknown accounts to reduce timing differences.
    if user is None:
        _password_hash(payload.password)
        raise HTTPException(status_code=401, detail="Email or password is incorrect")
    if not _password_matches(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Email or password is incorrect")
    return AuthResponse(access_token=_issue_token(user), user=UserResponse(id=user.id, email=user.email, display_name=user.display_name))


@router.get("/me", response_model=UserResponse)
def me(user: UserRow = Depends(current_user)) -> UserResponse:
    return UserResponse(id=user.id, email=user.email, display_name=user.display_name)
