"""How much of a submitted answer was spoken, measured by the server.

The typing-based integrity signals assume every character was typed: a spoken
answer has almost no keystrokes and arrives faster than anyone types, so without
this every voice answer would be flagged `mostly_pasted` and `too_fast`.

The browser could simply report "I dictated this", but then it could report it
for a pasted answer too. Instead the server compares the submitted text with the
transcripts *it* produced for that question and counts the overlap. Editing a
transcript (fixing "a SINGCO" to "asyncio") only loses the edited span; text
pasted from elsewhere matches no transcript and is still counted as not typed.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from difflib import SequenceMatcher

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import VoiceTranscription

#: Matches shorter than this are coincidence — common letters and short words
#: line up between any two English texts.
MIN_BLOCK = 8
#: SequenceMatcher is quadratic in the worst case; answers longer than this are
#: compared on their first MAX_COMPARE characters. Far beyond a spoken answer.
MAX_COMPARE = 20_000


def dictated_chars(answer: str, transcripts: Sequence[str]) -> int:
    """Characters of `answer` that appear, in runs, in the transcripts."""
    spoken = "\n".join(t for t in transcripts if t)
    if not spoken or not answer:
        return 0
    matcher = SequenceMatcher(None, answer[:MAX_COMPARE], spoken[:MAX_COMPARE], autojunk=False)
    return sum(block.size for block in matcher.get_matching_blocks() if block.size >= MIN_BLOCK)


async def measure(db: AsyncSession, question_id: uuid.UUID, answer: str) -> int:
    transcripts = list(
        await db.scalars(
            select(VoiceTranscription.text)
            .where(VoiceTranscription.question_id == question_id)
            .order_by(VoiceTranscription.created_at)
        )
    )
    return dictated_chars(answer, transcripts)
