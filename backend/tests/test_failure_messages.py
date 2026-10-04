"""Telling someone why it failed, not just that it did.

The distinction that matters is **retry now** versus **come back later**. A
daily provider quota takes hours to clear, so a UI that says "this is taking
longer than usual" sends the person to refresh a page for the rest of the
afternoon. These pin that the right message reaches them, and that the raw
provider error — which carries model names, quota identifiers and sometimes key
hints — does not.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.core.config import settings
from app.models import Resume
from app.models.resume import ParseStatus
from app.providers import FakeProvider
from app.providers.base import (
    LLMCircuitOpen,
    LLMRateLimited,
    LLMTransientError,
    LLMValidationError,
)
from app.schemas.pipeline import SkillExtractionResult
from app.services.pipeline import describe_failure, give_up_resume

API = settings.API_V1_PREFIX


# --- the explainer ---------------------------------------------------------


def test_a_rate_limit_says_come_back_later_not_keep_waiting():
    """The case that prompted this. Retrying in a minute will not help."""
    message = describe_failure("Reading your resume", LLMRateLimited("all keys 429"))
    assert "limit has been reached" in message
    assert "try again later" in message.lower()
    assert "saved" in message  # the upload is not lost, and that is worth saying


def test_a_provider_outage_says_try_again_in_a_few_minutes():
    message = describe_failure("Reading your resume", LLMCircuitOpen("breaker open"))
    assert "not responding" in message
    assert "few minutes" in message


def test_a_generic_transient_failure_names_the_attempt_count():
    message = describe_failure("Grading your answers", LLMTransientError("503"))
    assert str(settings.TASK_MAX_RETRIES + 1) in message
    assert "Grading your answers" in message


def test_a_terminal_failure_suggests_re_uploading():
    message = describe_failure("Reading your resume", LLMValidationError("garbage"))
    assert "upload the file afresh" in message


@pytest.mark.parametrize(
    "exc",
    [
        LLMRateLimited("quota: 20/day, project foo, key AIzaSyXXXX"),
        LLMCircuitOpen("upstream 503 from gemini-3.6-flash"),
        LLMTransientError("RESOURCE_EXHAUSTED quotaId=GenerateRequestsPerDay"),
        LLMValidationError("failed to parse {'api_key': 'AIza...'}"),
    ],
)
def test_the_raw_provider_message_never_reaches_the_user(exc):
    """Provider errors carry model names, quota ids and sometimes key hints."""
    message = describe_failure("Reading your resume", exc)
    assert str(exc) not in message
    assert "AIza" not in message
    assert "quotaId" not in message


def test_the_stage_is_always_named():
    """"Something failed" is not actionable; "reading your resume failed" is."""
    for stage in ("Reading your resume", "Generating your questions"):
        assert stage in describe_failure(stage, LLMRateLimited("x"))


# --- it reaches the resume row ---------------------------------------------


async def test_give_up_records_the_reason_on_the_resume(db_session):
    resume = Resume(user_id=None, file_uri="inline://text", mime="text/plain")
    resume.user_id = __import__("uuid").uuid4()
    db_session.add(resume)
    await db_session.flush()

    await give_up_resume(db_session, resume.id, LLMRateLimited("all keys 429"))

    await db_session.refresh(resume)
    assert resume.parse_status is ParseStatus.failed
    assert "limit has been reached" in (resume.failure_reason or "")


async def test_give_up_without_an_exception_leaves_no_reason(db_session):
    """Backwards compatible: a caller that cannot say why records nothing
    rather than inventing a cause."""
    import uuid

    resume = Resume(
        user_id=uuid.uuid4(), file_uri="inline://text", mime="text/plain"
    )
    db_session.add(resume)
    await db_session.flush()

    await give_up_resume(db_session, resume.id)

    await db_session.refresh(resume)
    assert resume.parse_status is ParseStatus.failed
    assert resume.failure_reason is None


# --- end to end, through the API -------------------------------------------


async def test_a_rate_limited_upload_surfaces_the_real_reason(
    auth_client: AsyncClient, provider: FakeProvider
):
    """What the candidate actually sees after the quota wall."""
    provider.register(SkillExtractionResult, LLMRateLimited("all 3 keys rate-limited"))

    created = await auth_client.post(f"{API}/resumes", json={"text": "python fastapi"})
    resume_id = created.json()["id"]

    body = (await auth_client.get(f"{API}/resumes/{resume_id}")).json()
    assert body["parse_status"] == "failed"
    assert "limit has been reached" in body["failure_reason"]
    assert "all 3 keys rate-limited" not in body["failure_reason"]


async def test_a_successful_parse_reports_no_reason(auth_client: AsyncClient):
    created = await auth_client.post(f"{API}/resumes", json={"text": "python fastapi"})
    body = (await auth_client.get(f"{API}/resumes/{created.json()['id']}")).json()
    assert body["parse_status"] == "parsed"
    assert body["failure_reason"] is None


async def test_a_retry_that_succeeds_clears_an_earlier_reason(
    auth_client: AsyncClient, provider: FakeProvider, db_session
):
    """Otherwise a recovered résumé keeps showing a stale explanation."""
    import uuid

    from app.providers.canned import default_canned_responses

    provider.register(SkillExtractionResult, LLMRateLimited("429"))
    created = await auth_client.post(f"{API}/resumes", json={"text": "python"})
    resume_id = uuid.UUID(created.json()["id"])

    resume = await db_session.get(Resume, resume_id)
    assert resume.failure_reason

    # The quota clears; parse runs again and succeeds.
    resume.parse_status = ParseStatus.pending
    await db_session.flush()
    provider.register(
        SkillExtractionResult, default_canned_responses()[SkillExtractionResult]
    )

    from app.services.pipeline import parse_resume

    await parse_resume(db_session, provider, resume_id)

    await db_session.refresh(resume)
    assert resume.parse_status is ParseStatus.parsed
    assert resume.failure_reason is None
