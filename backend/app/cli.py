"""Admin commands that must not be reachable over HTTP.

    python -m app.cli create-recruiter alice@company.com
    python -m app.cli promote bob@company.com

In Docker: `docker compose exec api python -m app.cli create-recruiter ...`.

Recruiters can read every candidate's answers, so the role is granted by
someone with shell access to the server — never chosen on a sign-up form.
The password is prompted for (not passed as an argument, which would land in
shell history); set INTERVIEWIQ_PASSWORD to script it.
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import os
import sys

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import async_session_factory
from app.models.user import UserRole
from app.services.user_service import EmailAlreadyRegistered, UserService


async def create_recruiter(db: AsyncSession, email: str, password: str) -> str:
    try:
        user = await UserService(db).register(email, password, role=UserRole.recruiter)
    except EmailAlreadyRegistered:
        return f"{email} already has an account — use `promote` instead."
    return f"Created recruiter {user.email}."


async def promote(db: AsyncSession, email: str) -> str:
    service = UserService(db)
    user = await service.get_by_email(email)
    if user is None:
        return f"No account for {email}."
    await service.set_role(user, UserRole.recruiter)
    return f"{user.email} is now a recruiter."


def _password() -> str:
    if from_env := os.environ.get("INTERVIEWIQ_PASSWORD"):
        return from_env
    first = getpass.getpass("Password (min 8 characters): ")
    if len(first) < 8 or first != getpass.getpass("Repeat password: "):
        sys.exit("Passwords must match and be at least 8 characters.")
    return first


async def _run(args: argparse.Namespace) -> str:
    async with async_session_factory() as db:
        if args.command == "create-recruiter":
            message = await create_recruiter(db, args.email, _password())
        else:
            message = await promote(db, args.email)
        await db.commit()
        return message


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("create-recruiter", help="new recruiter account").add_argument("email")
    commands.add_parser("promote", help="make an existing account a recruiter").add_argument(
        "email"
    )
    print(asyncio.run(_run(parser.parse_args())))


if __name__ == "__main__":
    main()
