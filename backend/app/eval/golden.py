"""The grading golden set: load, save, and be honest about where labels came from.

JSONL rather than one big JSON array, for two reasons: a hand edit touches one
line, and `git diff` after a labelling session shows exactly which items moved
instead of reflowing the whole file.

Every item records `labeled_by`. That field is the difference between a metric
that means something and one that doesn't: a set labelled by the same family of
model being measured can only report self-consistency. The bootstrap labels
exist so the harness is runnable today, and `python -m app.cli label-grading`
exists so they can be replaced.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

#: Repo-relative default, resolved from this file so it works from any cwd.
_GOLDEN_DIR = Path(__file__).resolve().parents[2] / "eval" / "golden"
DEFAULT_GOLDEN_PATH = _GOLDEN_DIR / "grading.jsonl"
DEFAULT_RETRIEVAL_PATH = _GOLDEN_DIR / "retrieval.jsonl"
DEFAULT_UNCOVERED_PATH = _GOLDEN_DIR / "retrieval_uncovered.jsonl"

LabelSource = Literal["ai-bootstrap", "human"]


class GoldenItem(BaseModel):
    """One (question, answer, score) triple."""

    id: str
    topic: str
    question: str
    expected_concepts: list[str] = Field(min_length=1)
    answer: str
    #: The reference score on the 0/0.25/0.5/0.75/1.0 scale.
    label: float = Field(ge=0.0, le=1.0)
    labeled_by: LabelSource = "ai-bootstrap"
    #: Why this score — the thing that makes a later re-label quick to sanity check.
    note: str = ""


def load_golden(path: Path | None = None) -> list[GoldenItem]:
    target = path or DEFAULT_GOLDEN_PATH
    if not target.exists():
        raise FileNotFoundError(
            f"No golden set at {target}. It ships with the repo; if it is missing, "
            f"restore it from git."
        )
    items: list[GoldenItem] = []
    for line_no, raw in enumerate(target.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("//"):
            continue
        try:
            items.append(GoldenItem.model_validate_json(line))
        except Exception as exc:  # noqa: BLE001 - point at the line, then re-raise
            raise ValueError(f"{target}:{line_no} is not a valid golden item: {exc}") from exc
    return items


def save_golden(items: list[GoldenItem], path: Path | None = None) -> None:
    """Rewrite the file. Called after a labelling session."""
    target = path or DEFAULT_GOLDEN_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    body = "\n".join(item.model_dump_json() for item in items)
    target.write_text(body + "\n", encoding="utf-8")


def label_source(items: list[GoldenItem]) -> str:
    """One word (or a count) describing what produced the labels in this set."""
    human = sum(1 for i in items if i.labeled_by == "human")
    if human == len(items) and items:
        return "human"
    if human == 0:
        return "ai-bootstrap"
    return f"mixed ({human}/{len(items)} human)"


class RetrievalItem(BaseModel):
    """One (query -> the passages that should come back) pair.

    `relevant` holds **heading paths**, not chunk ids. Chunk ids are UUIDs
    minted at ingest time and change every time the corpus is rebuilt, so a
    golden set keyed on them would rot on the next `ingest-kb`. A heading path
    is derived from the content and survives re-chunking.
    """

    id: str
    query: str
    expect_topic: str
    relevant: list[str] = Field(min_length=1)
    #: Which retriever this query is meant to stress. `exact-term` queries are
    #: where vector search alone is weak and keyword search carries it, and vice
    #: versa for `paraphrase` - a set made only of paraphrases would make hybrid
    #: look pointless by construction.
    kind: Literal["paraphrase", "exact-term", "mixed"] = "mixed"


def load_retrieval_golden(path: Path | None = None) -> list[RetrievalItem]:
    target = path or DEFAULT_RETRIEVAL_PATH
    if not target.exists():
        raise FileNotFoundError(f"No retrieval golden set at {target}.")
    items: list[RetrievalItem] = []
    for line_no, raw in enumerate(target.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("//"):
            continue
        try:
            items.append(RetrievalItem.model_validate_json(line))
        except Exception as exc:  # noqa: BLE001 - point at the line, then re-raise
            raise ValueError(f"{target}:{line_no} is not a valid retrieval item: {exc}") from exc
    return items


def load_uncovered_queries(path: Path | None = None) -> list[str]:
    """Queries the knowledge base deliberately does not cover.

    Without negatives a relevance cut-off cannot be calibrated: every query in
    the positive set has a right answer, so any floor that keeps them all looks
    perfect while silently grounding Kubernetes questions in the SQL chapter.
    """
    target = path or DEFAULT_UNCOVERED_PATH
    if not target.exists():
        raise FileNotFoundError(f"No uncovered-query set at {target}.")
    queries: list[str] = []
    for raw in target.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("//"):
            queries.append(json.loads(line)["query"])
    return queries
