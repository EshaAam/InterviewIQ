"""Integrity signals — advisory hints that an answer may not be the candidate's
own typing (design spec §6).

Two of the spec's three signals, both computed from telemetry the client
already sends with every answer:

- **mostly_pasted** — keystrokes account for too little of the text.
- **too_fast** — more characters per second than a person types.

(The third, a perplexity band, needs token log-probabilities for arbitrary
text, which the Gemini API doesn't expose.)

Signals are derived when read, never stored: telemetry doesn't change and the
check is cheap, so storing results would only freeze today's thresholds into
old rows. And they're advisory by construction — the numbers are
client-reported and forgeable, so they flag a session for a human to look at
and never change a score.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import Answer, Question

SignalCode = Literal["mostly_pasted", "too_fast"]


@dataclass(frozen=True)
class IntegritySignal:
    code: SignalCode
    detail: str  # a sentence a recruiter can read as-is


def assess_answer(
    *,
    chars: int,
    time_taken_ms: int | None,
    paste_events: int,
    keystroke_count: int | None,
    min_chars: int,
    min_typed_share: float,
    max_chars_per_second: float,
) -> list[IntegritySignal]:
    """Pure policy: telemetry in, signals out. No DB, no settings."""
    if chars < min_chars:
        return []

    signals: list[IntegritySignal] = []

    # Missing telemetry (an old client, or a direct API call) means "unknown",
    # not "suspicious" — each check only runs when its inputs are present.
    if keystroke_count is not None:
        # Backspaces count as keystrokes too, so this *over*-estimates typing:
        # the error runs in the candidate's favour.
        typed_share = min(1.0, keystroke_count / chars)
        if typed_share < min_typed_share:
            untyped = chars - min(keystroke_count, chars)
            pastes = f"{paste_events} paste{'' if paste_events == 1 else 's'}"
            signals.append(
                IntegritySignal(
                    "mostly_pasted",
                    f"{untyped} of {chars} characters were not typed ({pastes}).",
                )
            )

    if time_taken_ms is not None and time_taken_ms > 0:
        seconds = time_taken_ms / 1000
        rate = chars / seconds
        if rate > max_chars_per_second:
            signals.append(
                IntegritySignal(
                    "too_fast",
                    f"{chars} characters in {seconds:.0f} s ({rate:.0f} chars/s; "
                    "fast typists sustain about 8).",
                )
            )

    return signals


def assess(answer: Answer) -> list[IntegritySignal]:
    """`assess_answer` for a stored answer, with thresholds from config."""
    return assess_answer(
        chars=len(answer.text),
        time_taken_ms=answer.time_taken_ms,
        paste_events=answer.paste_events,
        keystroke_count=answer.keystroke_count,
        min_chars=settings.INTEGRITY_MIN_CHARS,
        min_typed_share=settings.INTEGRITY_MIN_TYPED_SHARE,
        max_chars_per_second=settings.INTEGRITY_MAX_CHARS_PER_SECOND,
    )


async def flagged_sessions(
    db: AsyncSession, session_ids: Iterable[uuid.UUID]
) -> set[uuid.UUID]:
    """Which of these sessions have at least one answer with a signal.
    One query for the whole list, however many sessions it covers."""
    ids = list(session_ids)
    if not ids:
        return set()
    rows = await db.execute(
        select(Question.session_id, Answer)
        .join(Answer, Answer.question_id == Question.id)
        .where(Question.session_id.in_(ids))
    )
    return {session_id for session_id, answer in rows.all() if assess(answer)}
