"""The report as a PDF.

A pure function: plain data in, PDF bytes out. No DB and no HTTP, so it is
testable on its own and the route runs it in a thread (drawing a PDF is CPU
work).

Rendered on demand, never stored. A recruiter override rebuilds the report,
and a stored PDF would quietly go stale; rendering a one-page document takes
milliseconds.

Uses fpdf2's built-in Helvetica, which only covers Latin-1. Rather than ship
a font file, text goes through `_latin1()`: common typography (— “ ” …) maps
to plain equivalents and anything else becomes "?". The PDF holds scores,
topic names and our own sentences — not free-form answer text.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from fpdf import FPDF

# Mirrors frontend/src/app/globals.css so the PDF looks like the app.
_INK = (24, 24, 27)
_INK_2 = (82, 82, 91)
_INK_3 = (111, 111, 118)
_LINE = (228, 228, 231)
_CANVAS = (244, 244, 245)
_ACCENT = (79, 70, 229)
_OK = (21, 128, 61)
_WARN = (180, 83, 9)
_WARN_SUBTLE = (254, 243, 199)
_INFO_SUBTLE = (219, 234, 254)

STRENGTH_AT = 0.7  # same cut-offs as pipeline.summarize()
GAP_BELOW = 0.5


@dataclass(frozen=True)
class IntegrityLine:
    question: int  # 1-based, as shown to people
    topic: str
    detail: str


@dataclass(frozen=True)
class ReportPdfData:
    session_id: str
    created_at: datetime
    state: str
    overall: float
    per_topic: dict[str, float]
    strengths: list[str]
    gaps: list[str]
    human_reviewed: bool
    candidate_email: str | None = None
    # None = leave the section out (the candidate's copy). [] = "no signals".
    integrity: list[IntegrityLine] | None = None
    generated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


def render_report_pdf(data: ReportPdfData) -> bytes:
    pdf = FPDF(format="A4", unit="mm")
    pdf.set_margins(18, 18, 18)
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.set_title(f"InterviewIQ report {data.session_id[:8]}")
    pdf.set_author("InterviewIQ")
    pdf.add_page()
    width = pdf.epw  # usable width between the margins

    # --- Header ---
    _text(pdf, "InterviewIQ", size=10, style="B", color=_ACCENT)
    _text(pdf, "Interview report", size=22, style="B", height=11)
    meta = [f"Session {data.session_id[:8]}", data.created_at.strftime("%d %b %Y")]
    if data.candidate_email:
        meta.insert(0, data.candidate_email)
    _text(pdf, "  ·  ".join(meta), size=10, color=_INK_2)
    pdf.ln(4)

    # --- Status banner ---
    if data.state == "NEEDS_HUMAN_REVIEW":
        _banner(
            pdf,
            "At least one answer is with a recruiter. The two grading passes disagreed, "
            "so a person is reading it instead of averaging - the scores may change.",
            _WARN_SUBTLE,
        )
    elif data.human_reviewed:
        _banner(
            pdf,
            "Reviewed by a recruiter. A person read the answers the graders disagreed "
            "on and set their scores; the numbers below include those decisions.",
            _INFO_SUBTLE,
        )

    # --- Overall ---
    _text(pdf, "OVERALL SCORE", size=8, style="B", color=_INK_3)
    _text(pdf, f"{data.overall:.2f}", size=34, style="B", height=15)
    _text(pdf, "out of 1.00 - the mean of the topic scores below", size=9, color=_INK_2)
    pdf.ln(5)

    # --- Score by topic ---
    _section(pdf, "Score by topic")
    if not data.per_topic:
        _text(pdf, "No per-topic scores recorded.", size=10, color=_INK_2)
    label_w, value_w = 48, 14
    bar_w = width - label_w - value_w - 4
    for topic, score in sorted(data.per_topic.items(), key=lambda kv: -kv[1]):
        clamped = min(max(score, 0.0), 1.0)
        y = pdf.get_y()
        pdf.set_font("Helvetica", "", 10)
        pdf.set_text_color(*_INK)
        pdf.cell(label_w, 7, _latin1(topic))
        bar_x = pdf.get_x() + 2
        pdf.set_fill_color(*_CANVAS)
        pdf.rect(bar_x, y + 2, bar_w, 3, style="F")
        pdf.set_fill_color(*_bar_color(clamped))
        pdf.rect(bar_x, y + 2, bar_w * clamped, 3, style="F")
        pdf.set_x(bar_x + bar_w + 2)
        pdf.cell(value_w, 7, f"{score:.2f}", align="R", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)

    # --- Strengths and gaps ---
    _section(pdf, f"Strengths (>= {STRENGTH_AT:.2f})")
    _bullets(pdf, data.strengths)
    _section(pdf, f"Gaps (< {GAP_BELOW:.2f})")
    _bullets(pdf, data.gaps)

    # --- Integrity (recruiter copy only) ---
    if data.integrity is not None:
        _section(pdf, "Integrity signals (advisory)")
        _text(
            pdf,
            "Computed from typing telemetry the browser reports (keystrokes, pastes, "
            "time). A signal is a reason to look, not a finding - it never changes a score.",
            size=9,
            color=_INK_2,
        )
        pdf.ln(1)
        if not data.integrity:
            _text(pdf, "No signals.", size=10)
        for line in data.integrity:
            _text(pdf, f"Q{line.question} - {line.topic}: {line.detail}", size=10)

    # --- Footer ---
    pdf.ln(6)
    pdf.set_draw_color(*_LINE)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.l_margin + width, pdf.get_y())
    pdf.ln(2)
    _text(
        pdf,
        f"Generated {data.generated_at.strftime('%d %b %Y %H:%M UTC')} · "
        "Every answer is graded twice (rule-based and model); scores run 0-1.",
        size=8,
        color=_INK_3,
    )

    return bytes(pdf.output())


# --- drawing helpers ---

def _text(
    pdf: FPDF,
    text: str,
    *,
    size: float,
    style: str = "",
    color: tuple[int, int, int] = _INK,
    height: float | None = None,
) -> None:
    pdf.set_font("Helvetica", style, size)
    pdf.set_text_color(*color)
    pdf.multi_cell(0, height or size * 0.5, _latin1(text), new_x="LMARGIN", new_y="NEXT")


def _section(pdf: FPDF, title: str) -> None:
    pdf.ln(2)
    _text(pdf, title, size=12, style="B", height=8)


def _bullets(pdf: FPDF, items: list[str]) -> None:
    if not items:
        _text(pdf, "None recorded.", size=10, color=_INK_2)
    for item in items:
        _text(pdf, f"-  {item}", size=10)
    pdf.ln(1)


def _banner(pdf: FPDF, text: str, fill: tuple[int, int, int]) -> None:
    pdf.set_fill_color(*fill)
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(*_INK)
    pdf.multi_cell(
        0, 5.5, _latin1(text), fill=True, padding=3, new_x="LMARGIN", new_y="NEXT"
    )
    pdf.ln(4)


def _bar_color(score: float) -> tuple[int, int, int]:
    if score >= STRENGTH_AT:
        return _OK
    if score < GAP_BELOW:
        return _WARN
    return _ACCENT


_REPLACEMENTS = str.maketrans(
    {
        "—": "-",
        "–": "-",
        "‘": "'",
        "’": "'",
        "“": '"',
        "”": '"',
        "…": "...",
        "•": "-",
        "→": "->",
        " ": " ",
    }
)


def _latin1(text: str) -> str:
    return text.translate(_REPLACEMENTS).encode("latin-1", "replace").decode("latin-1")
