"""Aggregates every v1 route module into a single router.

New feature routers get registered here and nowhere else, so there is
exactly one place to see the whole API surface.
"""

from fastapi import APIRouter

from app.api.v1.routes import auth, health, recruiter, resumes, sessions

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(resumes.router)
api_router.include_router(sessions.router)
api_router.include_router(recruiter.router)
