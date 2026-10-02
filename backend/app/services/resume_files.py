"""Turning an uploaded résumé file into text.

Pure and synchronous (the route runs it in a thread): bytes in, text out, or a
typed error the route maps to an HTTP status.

The file *type* is decided from the bytes. The filename and the client's
Content-Type are both chosen by the caller, so they only break ties — a
`.pdf` that doesn't start like a PDF is rejected, whatever it claims to be.
"""

from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass

from docx import Document
from pypdf import PdfReader
from pypdf.errors import PdfReadError


class UnsupportedFile(ValueError):
    """Not a PDF, DOCX or plain-text file we can open. → 415"""


class NoTextFound(ValueError):
    """A valid file, but with no usable text (e.g. a scanned PDF). → 422"""


@dataclass(frozen=True)
class ResumeFile:
    extension: str  # "pdf" | "docx" | "txt"
    mime: str
    text: str


_MIME = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "txt": "text/plain",
}

# A DOCX is a zip. Refuse archives that inflate past this — a small upload
# must not be able to expand into gigabytes of XML in memory.
_MAX_DOCX_UNCOMPRESSED = 20 * 1024 * 1024
_MAX_PDF_PAGES = 30


def read_resume_file(data: bytes, filename: str, *, min_chars: int) -> ResumeFile:
    kind = _sniff(data, filename)
    if kind == "pdf":
        text = _pdf_text(data)
    elif kind == "docx":
        text = _docx_text(data)
    else:
        text = _txt_text(data)

    text = _clean(text)
    if len(text) < min_chars:
        raise NoTextFound(
            "No readable text found in this file — if it's a scan, paste the text instead."
        )
    return ResumeFile(extension=kind, mime=_MIME[kind], text=text)


def _sniff(data: bytes, filename: str) -> str:
    name = filename.lower()
    # The PDF header may be preceded by a little junk; the spec allows 1 KB.
    if b"%PDF-" in data[:1024]:
        return "pdf"
    if data.startswith(b"PK\x03\x04") and name.endswith(".docx"):
        return "docx"
    if name.endswith(".txt") and b"\x00" not in data[:4096]:
        return "txt"
    raise UnsupportedFile("Upload a PDF, DOCX or TXT file.")


def _pdf_text(data: bytes) -> str:
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted and not reader.decrypt(""):
            raise UnsupportedFile("This PDF is password-protected.")
        pages = reader.pages[:_MAX_PDF_PAGES]
        return "\n".join(page.extract_text() or "" for page in pages)
    except UnsupportedFile:
        raise
    except (PdfReadError, ValueError, KeyError, TypeError) as exc:
        raise UnsupportedFile("This PDF could not be opened.") from exc


def _docx_text(data: bytes) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            if sum(info.file_size for info in archive.infolist()) > _MAX_DOCX_UNCOMPRESSED:
                raise UnsupportedFile("This DOCX is too large once unpacked.")
        document = Document(io.BytesIO(data))
    except UnsupportedFile:
        raise
    except Exception as exc:  # python-docx raises a variety of errors on bad input
        raise UnsupportedFile("This DOCX could not be opened.") from exc

    parts = [p.text for p in document.paragraphs]
    # Résumés often put skills and dates in tables.
    for table in document.tables:
        for row in table.rows:
            parts.append(" | ".join(cell.text for cell in row.cells))
    return "\n".join(parts)


def _txt_text(data: bytes) -> str:
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise UnsupportedFile("This text file isn't UTF-8 or Windows-1252.")


def _clean(text: str) -> str:
    # Postgres TEXT cannot store NUL, and PDF extraction sometimes emits it.
    text = text.replace("\x00", "")
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    return text.strip()
