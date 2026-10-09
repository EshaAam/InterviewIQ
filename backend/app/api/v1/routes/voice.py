"""Voice answers: transcribe a spoken clip into a draft the candidate can edit.

There is deliberately no "submit a voice answer" endpoint. The transcript comes
back to the browser, the candidate corrects whatever the model misheard, and the
text is submitted through `POST /sessions/{id}/answers` like any other answer —
so the deadline, idempotency, injection detection and both grading passes apply
unchanged, and a spoken answer is graded by exactly the same pipeline.

Transcription runs here, in the request, rather than in a worker: it is local,
spends no provider quota, and takes a few seconds for a minute of speech — the
same trade the résumé upload makes when it extracts text before responding.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile, status
from sqlalchemy import func, select

from app.api.deps import CurrentUser, DbSession
from app.api.v1.routes.sessions import _load_owned_session
from app.core.config import settings
from app.models import Question, VoiceTranscription
from app.models.session import SessionState
from app.schemas.interview import FeaturesRead, TranscriptRead
from app.transcription import (
    AudioTooLong,
    AudioUnreadable,
    Transcriber,
    TranscriberUnavailable,
    get_transcriber,
    voice_available,
)

router = APIRouter(tags=["voice"])


def voice_enabled() -> bool:
    """A dependency, so tests can switch the feature without the package."""
    return voice_available()


def transcriber() -> Transcriber:
    try:
        return get_transcriber()
    except TranscriberUnavailable as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc).capitalize()) from exc


VoiceEnabled = Annotated[bool, Depends(voice_enabled)]
ActiveTranscriber = Annotated[Transcriber, Depends(transcriber)]


@router.get("/features", response_model=FeaturesRead)
async def features(enabled: VoiceEnabled) -> FeaturesRead:
    return FeaturesRead(voice_answers=enabled, voice_max_seconds=settings.VOICE_MAX_SECONDS)


@router.post("/sessions/{session_id}/transcribe", response_model=TranscriptRead)
async def transcribe_answer(
    session_id: uuid.UUID,
    question_id: Annotated[uuid.UUID, Form()],
    audio: UploadFile,
    db: DbSession,
    user: CurrentUser,
    enabled: VoiceEnabled,
    model: ActiveTranscriber,
) -> TranscriptRead:
    if not enabled:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Voice answers are not enabled")

    session = await _load_owned_session(db, user.id, session_id)
    if session.state != SessionState.IN_PROGRESS:
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"Session is {session.state.value}, not IN_PROGRESS"
        )
    question = await db.get(Question, question_id)
    if question is None or question.session_id != session_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Question not found")

    # Free to run, but not free for the CPU: cap what one question can take.
    clips = await db.scalar(
        select(func.count(VoiceTranscription.id)).where(
            VoiceTranscription.question_id == question_id
        )
    )
    if (clips or 0) >= settings.VOICE_MAX_CLIPS_PER_QUESTION:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "That is the most recordings one question allows — type the rest.",
        )

    # One byte past the cap is enough to know it is too big.
    data = await audio.read(settings.VOICE_MAX_BYTES + 1)
    if len(data) > settings.VOICE_MAX_BYTES:
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE,
            f"Recordings can be up to {settings.VOICE_MAX_BYTES // (1024 * 1024)} MB.",
        )
    if not data:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "The recording is empty.")

    try:
        transcript = await model.transcribe(data, hint=question.text)
    except AudioTooLong as exc:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, str(exc).capitalize() + ".") from exc
    except AudioUnreadable as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc).capitalize() + "."
        ) from exc
    except TranscriberUnavailable as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc

    db.add(
        VoiceTranscription(
            session_id=session_id,
            question_id=question_id,
            text=transcript.text,
            duration_ms=int(transcript.duration_seconds * 1000),
            model=model.name,
        )
    )
    await db.flush()
    return TranscriptRead(
        text=transcript.text,
        duration_seconds=transcript.duration_seconds,
        language=transcript.language,
    )
