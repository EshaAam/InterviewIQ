"""The signed-in candidate's skill evidence map."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession
from app.schemas.interview import SkillMapRead
from app.services.skill_map import build_skill_map

router = APIRouter(prefix="/skill-map", tags=["skills"])


@router.get("", response_model=SkillMapRead)
async def my_skill_map(db: DbSession, user: CurrentUser) -> SkillMapRead:
    """Every skill the user has been graded on, across all their interviews,
    plus the résumé skills no interview has asked about yet."""
    return await build_skill_map(db, user.id)
