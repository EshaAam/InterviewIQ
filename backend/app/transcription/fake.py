"""FakeTranscriber — offline, instant, and deterministic, for the test suite.

"Audio" is `b"FAKEAUDIO:" + the words`. Anything else is unreadable, which is
enough to exercise every path the real decoder has: success, garbage, too long.
Speech runs at about 2.5 words a second, so the duration is derived from the
word count and a long enough script trips the length limit like real audio.
"""

from __future__ import annotations

from app.transcription.base import AudioTooLong, AudioUnreadable, Transcript

PREFIX = b"FAKEAUDIO:"
WORDS_PER_SECOND = 2.5


def fake_audio(words: str) -> bytes:
    return PREFIX + words.encode("utf-8")


class FakeTranscriber:
    name = "fake"

    def __init__(self, *, max_seconds: int = 180) -> None:
        self._max_seconds = max_seconds
        #: (hint, text) per call, for tests that check what biased the model.
        self.calls: list[tuple[str, str]] = []

    async def transcribe(self, audio: bytes, *, hint: str = "") -> Transcript:
        if not audio.startswith(PREFIX):
            raise AudioUnreadable("that recording could not be read as audio")
        text = audio[len(PREFIX) :].decode("utf-8").strip()
        duration = len(text.split()) / WORDS_PER_SECOND
        if duration > self._max_seconds:
            raise AudioTooLong(
                f"recordings can be up to {self._max_seconds} seconds; "
                f"this one is {duration:.0f}"
            )
        self.calls.append((hint, text))
        return Transcript(text=text, duration_seconds=round(duration, 2), language="en")
