"""Password hashing and JWT issuance/verification.

Isolated here so the rest of the app never touches bcrypt or PyJWT directly.
Access and refresh tokens share a signing key but differ in `type` and TTL;
verification enforces the expected type so a refresh token can't be used as
an access token or vice versa.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Literal

import bcrypt
import jwt

from app.core.config import settings

TokenType = Literal["access", "refresh"]


# --- Passwords ---

def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    except ValueError:
        # Malformed hash on record — treat as a failed check, never raise.
        return False


# --- Tokens ---

def _create_token(subject: uuid.UUID, token_type: TokenType, ttl: timedelta) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(subject),
        "type": token_type,
        "iat": int(now.timestamp()),
        "exp": int((now + ttl).timestamp()),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_access_token(subject: uuid.UUID) -> str:
    return _create_token(
        subject, "access", timedelta(minutes=settings.ACCESS_TOKEN_TTL_MINUTES)
    )


def create_refresh_token(subject: uuid.UUID) -> str:
    return _create_token(
        subject, "refresh", timedelta(days=settings.REFRESH_TOKEN_TTL_DAYS)
    )


class TokenError(Exception):
    """Raised when a token is invalid, expired, or the wrong type."""


def decode_token(token: str, expected_type: TokenType) -> uuid.UUID:
    """Return the subject id, or raise TokenError."""
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
        )
    except jwt.PyJWTError as exc:
        raise TokenError("invalid or expired token") from exc

    if payload.get("type") != expected_type:
        raise TokenError(f"expected {expected_type} token")

    try:
        return uuid.UUID(payload["sub"])
    except (KeyError, ValueError) as exc:
        raise TokenError("malformed token subject") from exc
