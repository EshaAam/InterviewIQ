"""Phase 5 — résumé file upload, and parse failures being recorded."""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from docx import Document
from fpdf import FPDF
from httpx import AsyncClient

from app.core.config import settings
from app.main import app
from app.providers import FakeProvider, LLMValidationError
from app.schemas.pipeline import SkillExtractionResult
from app.services.resume_files import NoTextFound, UnsupportedFile, read_resume_file
from app.services.storage import LocalFileStorage, get_storage

API = settings.API_V1_PREFIX
RESUME = (
    "Backend engineer. Five years of Python and FastAPI, PostgreSQL schema design, "
    "Redis caching and Celery workers in production."
)


def _pdf(text: str | None) -> bytes:
    pdf = FPDF()
    pdf.add_page()
    if text is None:
        pdf.rect(20, 20, 50, 50)  # a page with no text layer, like a scan
    else:
        pdf.set_font("Helvetica", size=11)
        pdf.multi_cell(0, 6, text)
    return bytes(pdf.output())


def _docx(text: str) -> bytes:
    document = Document()
    document.add_paragraph(text)
    table = document.add_table(rows=1, cols=2)
    table.rows[0].cells[0].text = "Skills"
    table.rows[0].cells[1].text = "Docker, asyncio"
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


@pytest.fixture
def uploads(client: AsyncClient, tmp_path: Path) -> Path:
    """Point file storage at a temp dir (the client fixture clears overrides)."""
    app.dependency_overrides[get_storage] = lambda: LocalFileStorage(tmp_path)
    return tmp_path


async def _upload(client: AsyncClient, name: str, data: bytes, mime: str):
    return await client.post(f"{API}/resumes/upload", files={"file": (name, data, mime)})


# --- the pure extractor ---


def test_extracts_pdf_docx_and_txt() -> None:
    assert "FastAPI" in read_resume_file(_pdf(RESUME), "cv.pdf", min_chars=40).text
    docx = read_resume_file(_docx(RESUME), "cv.docx", min_chars=40)
    assert "FastAPI" in docx.text and "Docker, asyncio" in docx.text  # tables too
    txt = read_resume_file(RESUME.encode(), "cv.txt", min_chars=40)
    assert txt.mime == "text/plain"


def test_type_comes_from_the_bytes_not_the_name() -> None:
    with pytest.raises(UnsupportedFile):
        read_resume_file(b"MZ\x90\x00 not a pdf at all", "cv.pdf", min_chars=1)
    with pytest.raises(UnsupportedFile):
        read_resume_file(_docx(RESUME), "cv.exe", min_chars=1)


def test_file_without_text_is_rejected() -> None:
    with pytest.raises(NoTextFound):
        read_resume_file(_pdf(None), "scan.pdf", min_chars=40)


# --- the endpoint ---


async def test_upload_pdf_stores_file_and_parses(
    auth_client: AsyncClient, uploads: Path
) -> None:
    resp = await _upload(auth_client, "cv.pdf", _pdf(RESUME), "application/pdf")
    assert resp.status_code == 202, resp.text
    resume_id = resp.json()["id"]

    # Inline dispatcher: parsing has already run.
    body = (await auth_client.get(f"{API}/resumes/{resume_id}")).json()
    assert body["parse_status"] == "parsed"
    assert {"python", "fastapi"} <= {s["name"] for s in body["skills"]}

    stored = list(uploads.rglob("*.pdf"))
    assert len(stored) == 1 and stored[0].stem == resume_id
    assert stored[0].read_bytes().startswith(b"%PDF")


async def test_upload_docx(auth_client: AsyncClient, uploads: Path) -> None:
    resp = await _upload(auth_client, "cv.docx", _docx(RESUME), "application/octet-stream")
    assert resp.status_code == 202, resp.text


async def test_disguised_file_is_415(auth_client: AsyncClient, uploads: Path) -> None:
    resp = await _upload(auth_client, "cv.pdf", b"\x7fELF binary", "application/pdf")
    assert resp.status_code == 415
    assert not list(uploads.rglob("*"))  # nothing stored


async def test_oversize_file_is_413(
    auth_client: AsyncClient, uploads: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "RESUME_MAX_BYTES", 1024)
    resp = await _upload(auth_client, "cv.txt", b"x" * 2048, "text/plain")
    assert resp.status_code == 413


async def test_scanned_pdf_is_422(auth_client: AsyncClient, uploads: Path) -> None:
    resp = await _upload(auth_client, "scan.pdf", _pdf(None), "application/pdf")
    assert resp.status_code == 422
    assert "paste" in resp.json()["detail"]


async def test_upload_requires_auth(client: AsyncClient, uploads: Path) -> None:
    resp = await _upload(client, "cv.txt", RESUME.encode(), "text/plain")
    assert resp.status_code == 401


# --- parse failures are recorded, not left hanging ---


async def test_failed_parse_is_marked_failed(
    auth_client: AsyncClient, provider: FakeProvider
) -> None:
    provider.register(SkillExtractionResult, LLMValidationError("unparseable"))
    resume_id = (
        await auth_client.post(f"{API}/resumes", json={"text": RESUME})
    ).json()["id"]
    body = (await auth_client.get(f"{API}/resumes/{resume_id}")).json()
    assert body["parse_status"] == "failed"

    # A session on it fails with a reason instead of generating from nothing.
    sid = (
        await auth_client.post(f"{API}/sessions", json={"resume_id": resume_id})
    ).json()["id"]
    session = (await auth_client.get(f"{API}/sessions/{sid}")).json()
    assert session["state"] == "FAILED"
    assert "resume" in session["failure_reason"]
