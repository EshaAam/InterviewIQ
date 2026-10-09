"""The transcriber contract.

Speech-to-text gets its own seam for the same reason embeddings did: it is a
local, CPU-bound model with nothing to do with prompts or providers, and the
test suite must be able to replace it without downloading anything.

A transcript is a *draft*. The candidate reads it, fixes what the model misheard
and submits it through the ordinary answer endpoint — so a spoken answer is
graded by exactly the same pipeline as a typed one, and nothing here decides a
score.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class Transcript:
    text: str
    duration_seconds: float
    language: str


class TranscriptionError(Exception):
    """Base for everything a caller can explain to the person speaking."""


class AudioUnreadable(TranscriptionError):
    """Not audio, or a format the decoder cannot open."""


class AudioTooLong(TranscriptionError):
    """Longer than `VOICE_MAX_SECONDS`."""


class TranscriberUnavailable(TranscriptionError):
    """The feature is configured on, but the model cannot run here."""


@runtime_checkable
class Transcriber(Protocol):
    #: Identifies the model, for logs and the recruiter's view.
    name: str

    async def transcribe(self, audio: bytes, *, hint: str = "") -> Transcript:
        """`hint` biases vocabulary (the question text) — never the answer key."""
        ...
