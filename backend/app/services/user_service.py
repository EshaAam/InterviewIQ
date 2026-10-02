"""User/account operations: registration and credential verification.

Services own business rules and persistence; routes stay thin. Errors are
raised as domain exceptions and translated to HTTP status in the route layer.
"""

from __future__ import annotations

import asyncio
import uuid

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password, verify_password
from app.models.user import User, UserRole


class EmailAlreadyRegistered(Exception):
    pass


class InvalidCredentials(Exception):
    pass


def normalize_email(email: str) -> str:
    """One spelling per address: `A@X.com` and `a@x.com` are the same account."""
    return email.strip().lower()


class UserService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        return await self.db.get(User, user_id)

    async def get_by_email(self, email: str) -> User | None:
        # Compare lowercased on both sides so rows stored before emails were
        # normalised (mixed case) are still found.
        result = await self.db.execute(
            select(User).where(func.lower(User.email) == normalize_email(email))
        )
        return result.scalar_one_or_none()

    async def register(
        self, email: str, password: str, role: UserRole = UserRole.candidate
    ) -> User:
        """Create an account. The public route never passes `role` — only the
        CLI does, which is how recruiter accounts come into existence."""
        if await self.get_by_email(email) is not None:
            raise EmailAlreadyRegistered(email)

        user = User(
            email=normalize_email(email),
            hashed_password=await asyncio.to_thread(hash_password, password),
            role=role,
        )
        # Two concurrent registrations can both pass the check above; the
        # unique index decides. A savepoint keeps the loser's IntegrityError
        # from poisoning the request's transaction, and it becomes a clean 409.
        try:
            async with self.db.begin_nested():
                self.db.add(user)
                await self.db.flush()
        except IntegrityError:
            raise EmailAlreadyRegistered(email) from None
        return user

    async def set_role(self, user: User, role: UserRole) -> User:
        user.role = role
        await self.db.flush()
        return user

    async def authenticate(self, email: str, password: str) -> User:
        user = await self.get_by_email(email)
        # Verify even when the user is missing to keep timing uniform.
        placeholder = "$2b$12$" + "." * 53
        # bcrypt is ~250 ms of CPU *by design*. On the event loop it froze every
        # other request in the process for that long (the Phase 7 load test
        # showed 3 s tails on unrelated endpoints during a burst of sign-ins);
        # a thread keeps the loop free while it grinds.
        ok = await asyncio.to_thread(
            verify_password, password, user.hashed_password if user else placeholder
        )
        if not ok:
            raise InvalidCredentials()
        if user is None:  # pragma: no cover - defensive; unreachable when hash matches
            raise InvalidCredentials()
        return user
