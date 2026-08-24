"""Resume routes — upload (as text) and poll parse status.

`POST /resumes` returns 202: the resume row exists immediately, parsing runs
asynchronously, and the client polls `GET /resumes/{id}` for status + skills.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.models import ExtractedSkill, Resume
from app.schemas.interview import ResumeCreate, ResumeRead, SkillRead
from app.workers.dispatch import PipelineDispatcher, get_dispatcher

router = APIRouter(prefix="/resumes", tags=["resumes"])

Dispatcher = Annotated[PipelineDispatcher, Depends(get_dispatcher)]


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
) -> ResumeRead:
    resume = Resume(
        user_id=user.id,
        file_uri="inline://text",
        mime=payload.mime,
        text_content=payload.text,
    )
    db.add(resume)
    await db.flush()
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
