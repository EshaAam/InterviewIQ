"""Resume routes — submit (pasted text or a file) and poll parse status.

`POST /resumes` (JSON text) and `POST /resumes/upload` (multipart file) both
return 202: the resume row exists immediately, skill extraction runs in a
worker, and the client polls `GET /resumes/{id}` for status + skills.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession, require_budget
from app.core.config import settings
from app.models import ExtractedSkill, Resume
from app.schemas.interview import ResumeCreate, ResumeRead, SkillRead
from app.services.resume_files import NoTextFound, UnsupportedFile, read_resume_file
from app.services.storage import FileStorage, get_storage
from app.workers.dispatch import PipelineDispatcher, get_dispatcher

router = APIRouter(prefix="/resumes", tags=["resumes"])

Dispatcher = Annotated[PipelineDispatcher, Depends(get_dispatcher)]
Storage = Annotated[FileStorage, Depends(get_storage)]
# Parsing a résumé spends tokens, so starting one is budget-gated like a session.
Budget = Annotated[None, Depends(require_budget)]


async def _load_owned_resume(
    db: DbSession, user_id: uuid.UUID, resume_id: uuid.UUID
) -> Resume:
    resume = await db.get(Resume, resume_id)
    if resume is None or resume.user_id != user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Resume not found")
    return resume


@router.post("", response_model=ResumeRead, status_code=status.HTTP_202_ACCEPTED)
async def create_resume(
    payload: ResumeCreate,
    db: DbSession,
    user: CurrentUser,
    dispatcher: Dispatcher,
    _budget: Budget = None,
) -> ResumeRead:
    resume = Resume(
        user_id=user.id,
        file_uri="inline://text",
        mime=payload.mime,
        text_content=payload.text,
    )
    db.add(resume)
    await db.commit()  # commit, then dispatch — see sessions.create_session
    await dispatcher.parse_resume(resume.id)
    return ResumeRead(id=resume.id, parse_status=resume.parse_status, skills=[])


@router.post(
    "/upload", response_model=ResumeRead, status_code=status.HTTP_202_ACCEPTED
)
async def upload_resume(
    file: UploadFile,
    db: DbSession,
    user: CurrentUser,
    dispatcher: Dispatcher,
    storage: Storage,
    _budget: Budget = None,
) -> ResumeRead:
    """A PDF, DOCX or TXT résumé. Text is extracted here, before responding,
    so an unreadable file is a 422 now rather than a failed parse later."""
    # Read one byte past the cap: enough to know it's too big, without
    # pulling an arbitrarily large body into memory.
    data = await file.read(settings.RESUME_MAX_BYTES + 1)
    if len(data) > settings.RESUME_MAX_BYTES:
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE,
            f"File is larger than {settings.RESUME_MAX_BYTES // (1024 * 1024)} MB",
        )

    try:
        # PDF/DOCX parsing is CPU work — keep it off the event loop.
        parsed = await run_in_threadpool(
            read_resume_file,
            data,
            file.filename or "",
            min_chars=settings.RESUME_MIN_TEXT_CHARS,
        )
    except UnsupportedFile as exc:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, str(exc)) from None
    except NoTextFound as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from None

    # File first, row second: if storing fails there is no row pointing at a
    # missing file. (The reverse failure leaves an orphaned file, which is harmless.)
    resume_id = uuid.uuid4()
    file_uri = await storage.save(
        f"resumes/{user.id}/{resume_id}.{parsed.extension}", data
    )
    resume = Resume(
        id=resume_id,
        user_id=user.id,
        file_uri=file_uri,
        mime=parsed.mime,
        text_content=parsed.text,
    )
    db.add(resume)
    await db.commit()  # commit, then dispatch — see sessions.create_session
    await dispatcher.parse_resume(resume.id)
    return ResumeRead(id=resume.id, parse_status=resume.parse_status, skills=[])


@router.get("/{resume_id}", response_model=ResumeRead)
async def get_resume(
    resume_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> ResumeRead:
    resume = await _load_owned_resume(db, user.id, resume_id)
    skills = list(
        await db.scalars(
            select(ExtractedSkill).where(ExtractedSkill.resume_id == resume_id)
        )
    )
    return ResumeRead(
        id=resume.id,
        parse_status=resume.parse_status,
        skills=[SkillRead.model_validate(s) for s in skills],
    )
