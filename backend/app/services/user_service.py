"""User/account operations: registration and credential verification.

Services own business rules and persistence; routes stay thin. Errors are
raised as domain exceptions and translated to HTTP status in the route layer.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password, verify_password
from app.models.user import User, UserRole


class EmailAlreadyRegistered(Exception):
    pass


class InvalidCredentials(Exception):
    pass


class UserService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        return await self.db.get(User, user_id)

    async def get_by_email(self, email: str) -> User | None:
        result = await self.db.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def register(
        self, email: str, password: str, role: UserRole
    ) -> User:
        if await self.get_by_email(email) is not None:
            raise EmailAlreadyRegistered(email)

        user = User(
            email=email,
            hashed_password=hash_password(password),
            role=role,
        )
        self.db.add(user)
        await self.db.flush()  # assigns PK without ending the request transaction
        return user

    async def authenticate(self, email: str, password: str) -> User:
        user = await self.get_by_email(email)
        # Verify even when the user is missing to keep timing uniform.
        placeholder = "$2b$12$" + "." * 53
        if not verify_password(password, user.hashed_password if user else placeholder):
            raise InvalidCredentials()
        if user is None:  # pragma: no cover - defensive; unreachable when hash matches
            raise InvalidCredentials()
        return user
