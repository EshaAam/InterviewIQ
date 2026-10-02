"""Shared FastAPI dependencies: DB session and the authenticated user.

`get_current_user` decodes the bearer access token, loads the user, and
401s on any failure. Role gating builds on top via `require_role`.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import TokenError, decode_token
from app.db.session import get_db
from app.models.user import User, UserRole
from app.services.user_service import UserService

oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_PREFIX}/auth/login")

# scope="function": get_db's commit runs when the route returns, *before* the
# response is sent. With the default ("request") it ran after: a client could
# read "201 Created", send its next request, and get there before the commit —
# the Phase 7 load test hit exactly that (a login 401 right after register, a
# 409 right after start). It also means a failing commit becomes the client's
# error response instead of failing silently after a success was reported.
DbSession = Annotated[AsyncSession, Depends(get_db, scope="function")]


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: DbSession,
) -> User:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        user_id = decode_token(token, expected_type="access")
    except TokenError:
        raise credentials_error from None

    user = await UserService(db).get_by_id(user_id)
    if user is None:
        raise credentials_error
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def require_budget(user: CurrentUser, db: DbSession) -> None:
    """Reject with 429 before spending if the user is over their daily token cap."""
    from app.services.budget import tokens_used_today

    if await tokens_used_today(db, user.id) >= settings.USER_DAILY_TOKEN_BUDGET:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Daily token budget exceeded",
        )


def require_role(*roles: UserRole):
    """Dependency factory: allow only the given roles."""

    async def _guard(user: CurrentUser) -> User:
        if user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role"
            )
        return user

    return _guard
