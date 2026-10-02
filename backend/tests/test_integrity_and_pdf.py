"""Phase 5 — advisory integrity signals, and the PDF report."""

from __future__ import annotations

import io

from httpx import AsyncClient
from pypdf import PdfReader

from app.core.config import settings
from app.services.integrity import assess_answer

API = settings.API_V1_PREFIX
PASSWORD = "hunter2secret"


# --- the pure policy ---

LIMITS = {"min_chars": 120, "min_typed_share": 0.4, "max_chars_per_second": 12.0}


def test_typed_answer_raises_nothing() -> None:
    assert (
        assess_answer(
            chars=600, time_taken_ms=180_000, paste_events=0, keystroke_count=650, **LIMITS
        )
        == []
    )


def test_pasted_answer_is_flagged() -> None:
    (signal,) = assess_answer(
        chars=600, time_taken_ms=180_000, paste_events=1, keystroke_count=40, **LIMITS
    )
    assert signal.code == "mostly_pasted"
    assert "560 of 600" in signal.detail


def test_impossibly_fast_answer_is_flagged() -> None:
    (signal,) = assess_answer(
        chars=600, time_taken_ms=20_000, paste_events=0, keystroke_count=600, **LIMITS
    )
    assert signal.code == "too_fast"


def test_short_answers_and_missing_telemetry_are_never_flagged() -> None:
    assert assess_answer(
        chars=60, time_taken_ms=1_000, paste_events=3, keystroke_count=0, **LIMITS
    ) == []
    assert assess_answer(
        chars=600, time_taken_ms=None, paste_events=0, keystroke_count=None, **LIMITS
    ) == []


# --- end to end ---


async def _login(client: AsyncClient, email: str) -> dict:
    """Register (always a candidate) and sign in. Recruiters: the `recruiter` fixture."""
    payload = {"email": email, "password": PASSWORD}
    await client.post(f"{API}/auth/register", json=payload)
    token = (
        await client.post(f"{API}/auth/login", json={"email": email, "password": PASSWORD})
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def _interview(client: AsyncClient, headers: dict, *, pasted: bool) -> str:
    """Two questions (python, fastapi). The first answer is typed normally;
    the second is typed or pasted depending on `pasted`."""
    rid = (
        await client.post(
            f"{API}/resumes", json={"text": "python and fastapi"}, headers=headers
        )
    ).json()["id"]
    sid = (
        await client.post(f"{API}/sessions", json={"resume_id": rid}, headers=headers)
    ).json()["id"]
    await client.post(f"{API}/sessions/{sid}/start", headers=headers)

    long_answer = "fundamentals tradeoffs in production " * 10  # 370 chars
    telemetry = [
        {"time_taken_ms": 120_000, "paste_events": 0, "keystroke_count": 400},
        {"time_taken_ms": 4_000, "paste_events": 1, "keystroke_count": 3}
        if pasted
        else {"time_taken_ms": 120_000, "paste_events": 0, "keystroke_count": 400},
    ]
    for i, signals in enumerate(telemetry):
        q = (
            await client.get(f"{API}/sessions/{sid}/questions/next", headers=headers)
        ).json()
        await client.post(
            f"{API}/sessions/{sid}/answers",
            json={"question_id": q["id"], "text": long_answer, **signals},
            headers={**headers, "Idempotency-Key": f"k{i}"},
        )
    await client.post(f"{API}/sessions/{sid}/finish", headers=headers)
    return sid


async def test_recruiter_sees_signals_candidate_does_not(
    client: AsyncClient, recruiter
) -> None:
    cand = await _login(client, "paster@example.com")
    sid = await _interview(client, cand, pasted=True)
    rec = await recruiter("rec-int@example.com")

    detail = (await client.get(f"{API}/recruiter/sessions/{sid}", headers=rec)).json()
    assert detail["integrity_flag"] is True
    first, second = (q["answers"][0]["integrity"] for q in detail["questions"])
    assert first == []
    assert {s["code"] for s in second} == {"mostly_pasted", "too_fast"}

    rows = (await client.get(f"{API}/recruiter/sessions", headers=rec)).json()
    assert next(r for r in rows if r["id"] == sid)["integrity_flag"] is True

    # Nothing about integrity reaches the candidate.
    report = (await client.get(f"{API}/sessions/{sid}/report", headers=cand)).json()
    assert not any("integrity" in key for key in report)


async def test_clean_session_is_not_flagged(client: AsyncClient, recruiter) -> None:
    cand = await _login(client, "typist@example.com")
    sid = await _interview(client, cand, pasted=False)
    rec = await recruiter("rec-clean@example.com")
    detail = (await client.get(f"{API}/recruiter/sessions/{sid}", headers=rec)).json()
    assert detail["integrity_flag"] is False


def _pdf_text(data: bytes) -> str:
    return "\n".join(page.extract_text() for page in PdfReader(io.BytesIO(data)).pages)


async def test_report_pdf_for_candidate_and_recruiter(
    client: AsyncClient, recruiter
) -> None:
    cand = await _login(client, "pdf@example.com")
    sid = await _interview(client, cand, pasted=True)

    resp = await client.get(f"{API}/sessions/{sid}/report.pdf", headers=cand)
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert "attachment" in resp.headers["content-disposition"]
    assert resp.content.startswith(b"%PDF")
    text = _pdf_text(resp.content)
    assert "Interview report" in text and "python" in text
    assert "Integrity" not in text  # the candidate's copy leaves it out

    rec = await recruiter("rec-pdf@example.com")
    resp = await client.get(f"{API}/recruiter/sessions/{sid}/report.pdf", headers=rec)
    assert resp.status_code == 200
    text = _pdf_text(resp.content)
    assert "pdf@example.com" in text
    assert "Integrity signals" in text and "not typed" in text


async def test_report_pdf_is_owner_only_and_needs_a_report(client: AsyncClient) -> None:
    owner = await _login(client, "owner@example.com")
    stranger = await _login(client, "stranger@example.com")
    rid = (
        await client.post(f"{API}/resumes", json={"text": "python"}, headers=owner)
    ).json()["id"]
    sid = (
        await client.post(f"{API}/sessions", json={"resume_id": rid}, headers=owner)
    ).json()["id"]

    # No report before the interview is finished.
    assert (
        await client.get(f"{API}/sessions/{sid}/report.pdf", headers=owner)
    ).status_code == 404
    assert (
        await client.get(f"{API}/sessions/{sid}/report.pdf", headers=stranger)
    ).status_code == 404
    assert (
        await client.get(f"{API}/recruiter/sessions/{sid}/report.pdf", headers=owner)
    ).status_code == 403
