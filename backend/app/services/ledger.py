"""Where `LLMCall` ledger rows get written.

The ledger records money that has already been spent. That gives it a
different lifetime from the work that spent it: when a task fails and its
transaction rolls back, the questions or grades it wrote should disappear —
the record of the provider calls it paid for should not. Otherwise a task that
retries three times leaves no trace of the first three bills, and the budget
undercounts exactly when things go wrong.

By default a row joins the caller's transaction (fine for request handlers and
tests). Inside `independent_ledger(writer)` — set up by the Celery task runner
— rows go to `writer` instead, which commits each one on its own.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import LLMCall

LedgerWriter = Callable[[LLMCall], Awaitable[None]]

_writer: ContextVar[LedgerWriter | None] = ContextVar("ledger_writer", default=None)


@contextmanager
def independent_ledger(writer: LedgerWriter) -> Iterator[None]:
    token = _writer.set(writer)
    try:
        yield
    finally:
        _writer.reset(token)


async def record(db: AsyncSession, row: LLMCall) -> None:
    writer = _writer.get()
    if writer is None:
        db.add(row)
    else:
        await writer(row)
