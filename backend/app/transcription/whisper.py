"""WhisperTranscriber — speech-to-text on the CPU, for free.

faster-whisper runs OpenAI's Whisper through CTranslate2 with int8 weights:
`base.en` is ~145 MB and transcribes a minute of speech in a few seconds on a
laptop CPU, with no API key and no audio leaving the machine. PyAV (bundled
with it) decodes the browser's webm/opus directly, so no system ffmpeg either.

The model is loaded once per process, lazily, and **pre-downloaded into the
image** (see `backend/Dockerfile`): a request that waits on a 145 MB fetch is a
request that times out.

**The hint is the question, never the answer key.** Whisper accepts a prompt
that biases its vocabulary, which is what turns "a SINGCO" back into "asyncio".
Feeding it the expected concepts would do that job better — and would also nudge
a mumble towards exactly the words the grader rewards. The question text is
already on the candidate's screen, so it biases nothing they could not see.
"""

from __future__ import annotations

import asyncio
import io
import threading
from typing import Any

from app.transcription.base import (
    AudioTooLong,
    AudioUnreadable,
    TranscriberUnavailable,
    Transcript,
)

SAMPLE_RATE = 16_000


class WhisperTranscriber:
    def __init__(
        self,
        *,
        model_name: str = "base.en",
        compute_type: str = "int8",
        cache_dir: str | None = None,
        threads: int = 0,
        language: str = "en",
        max_seconds: int = 180,
        concurrency: int = 1,
    ) -> None:
        self.name = f"faster-whisper/{model_name}"
        self._model_name = model_name
        self._compute_type = compute_type
        self._cache_dir = cache_dir
        self._threads = threads
        self._language = language
        self._max_seconds = max_seconds
        self._model: Any | None = None
        self._load_lock = threading.Lock()
        # A thread semaphore, not an asyncio one: the work runs in a thread and
        # this stays correct whichever event loop called it.
        self._slots = threading.BoundedSemaphore(max(1, concurrency))

    def _load(self) -> Any:
        with self._load_lock:
            if self._model is None:
                try:
                    from faster_whisper import WhisperModel
                except ImportError as exc:  # pragma: no cover - deployment error
                    raise TranscriberUnavailable(
                        "voice answers need the `voice` extra: uv sync --extra voice"
                    ) from exc
                self._model = WhisperModel(
                    self._model_name,
                    device="cpu",
                    compute_type=self._compute_type,
                    download_root=self._cache_dir,
                    cpu_threads=self._threads,
                )
        return self._model

    async def transcribe(self, audio: bytes, *, hint: str = "") -> Transcript:
        return await asyncio.to_thread(self._transcribe_sync, audio, hint)

    def _transcribe_sync(self, audio: bytes, hint: str) -> Transcript:
        from faster_whisper import decode_audio

        # Decode first: it is cheap next to inference, and it is where both
        # "this is not audio" and "this is too long" are discovered — before
        # spending seconds of CPU on a clip that will be refused anyway.
        try:
            samples = decode_audio(io.BytesIO(audio), sampling_rate=SAMPLE_RATE)
        except Exception as exc:  # noqa: BLE001 - PyAV raises many types
            raise AudioUnreadable("that recording could not be read as audio") from exc
        duration = len(samples) / SAMPLE_RATE
        if duration > self._max_seconds:
            raise AudioTooLong(
                f"recordings can be up to {self._max_seconds} seconds; "
                f"this one is {duration:.0f}"
            )

        model = self._load()
        with self._slots:
            segments, info = model.transcribe(
                samples,
                language=self._language,
                # Silence skipped by voice-activity detection, which also stops
                # Whisper inventing words over a long pause.
                vad_filter=True,
                beam_size=1,
                initial_prompt=hint[:400] or None,
                condition_on_previous_text=False,
            )
            text = " ".join(segment.text.strip() for segment in segments).strip()
        return Transcript(text=text, duration_seconds=round(duration, 2), language=info.language)
