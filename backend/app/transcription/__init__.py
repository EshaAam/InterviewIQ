"""Speech-to-text for voice answers. See `base` for the contract."""

from __future__ import annotations

import importlib.util
from functools import lru_cache

from app.core.config import settings
from app.transcription.base import (
    AudioTooLong,
    AudioUnreadable,
    Transcriber,
    TranscriberUnavailable,
    Transcript,
    TranscriptionError,
)

__all__ = [
    "AudioTooLong",
    "AudioUnreadable",
    "Transcriber",
    "TranscriberUnavailable",
    "Transcript",
    "TranscriptionError",
    "get_transcriber",
    "voice_available",
]


def voice_available() -> bool:
    """Whether voice answers can be offered at all.

    Both the switch and the package: an image built without the `voice` extra
    must not show a microphone that fails on first use.
    """
    return settings.VOICE_ENABLED and importlib.util.find_spec("faster_whisper") is not None


@lru_cache
def get_transcriber() -> Transcriber:
    """The process-wide transcriber. Cached: the model loads once."""
    if not voice_available():
        raise TranscriberUnavailable("voice answers are not enabled on this server")
    from app.transcription.whisper import WhisperTranscriber

    return WhisperTranscriber(
        model_name=settings.WHISPER_MODEL,
        compute_type=settings.WHISPER_COMPUTE_TYPE,
        cache_dir=settings.WHISPER_CACHE_DIR or None,
        threads=settings.WHISPER_THREADS,
        language=settings.VOICE_LANGUAGE,
        max_seconds=settings.VOICE_MAX_SECONDS,
        concurrency=settings.VOICE_CONCURRENCY,
    )
