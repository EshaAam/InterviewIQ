"""Match a job description against a candidate's extracted skills.

An interview that asks about what the résumé already evidences is largely
wasted: the answer is on the page. What a hiring decision actually needs is the
*gap* — requirements the role asks for that the résumé does not support. This
finds them, and question generation then targets those.

**Entirely local.** Requirements and skills are compared with the embedding
model running on the CPU, not by asking an LLM. That is not only cheaper, it is
the difference between the feature being usable and not: the free Gemini tier
allows twenty requests per day, and spending several of them re-deriving a
comparison that cosine similarity answers for nothing would be a poor trade.

**Not calibrated like the retrieval floor.** `RAG_MIN_SIMILARITY` was measured
against a golden set with deliberate negatives; this threshold is reasoned by
analogy from the same measurements — under bge-small two unrelated texts score
around 0.44 and a genuine match 0.73 or better, so 0.65 sits in the same place
relative to the distribution. It is a defensible starting value, not a measured
one, and `docs/rag-plan.md` records what calibrating it properly would need.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.core.config import settings
from app.embedders import Embedder
from app.models import ExtractedSkill
from app.services.scoring import cosine

#: Lines shorter than this are headings or noise ("Requirements:", "About us").
MIN_REQUIREMENT_CHARS = 20
#: A hard cap. A long JD would otherwise dominate the retrieval budget and the
#: prompt, and the first twenty lines carry the role.
MAX_REQUIREMENTS = 20

_BULLET = re.compile(r"^\s*(?:[-*•·]|\d+[.)])\s*")


@dataclass(frozen=True)
class RequirementMatch:
    requirement: str
    #: The résumé skill that best supports it, or None when nothing came close.
    best_skill: str | None
    similarity: float

    @property
    def covered(self) -> bool:
        return self.similarity >= settings.JD_MATCH_THRESHOLD


def split_requirements(text: str) -> list[str]:
    """One requirement per line or bullet.

    Deliberately not sentence splitting: job descriptions are written as lists,
    and a sentence splitter turns "5+ years with Python, Django and Postgres"
    into fragments that embed into noise.
    """
    requirements: list[str] = []
    for raw in text.splitlines():
        line = _BULLET.sub("", raw).strip()
        if len(line) < MIN_REQUIREMENT_CHARS:
            continue
        # A trailing colon marks a heading introducing a list, not a requirement.
        if line.endswith(":"):
            continue
        requirements.append(line)
        if len(requirements) >= MAX_REQUIREMENTS:
            break
    return requirements


async def match(
    embedder: Embedder,
    job_description: str,
    skills: list[ExtractedSkill],
) -> list[RequirementMatch]:
    """Score every requirement against the best-supporting résumé skill."""
    requirements = split_requirements(job_description)
    if not requirements:
        return []

    if not skills:
        # No skills extracted: every requirement is a gap, which is the correct
        # reading rather than an error — nothing on the résumé supports anything.
        return [RequirementMatch(r, None, 0.0) for r in requirements]

    # The evidence span carries the context the bare skill name lacks, the same
    # reason grounding uses it to build retrieval queries.
    skill_texts = [f"{s.name} {s.evidence_span}".strip() for s in skills]
    vectors = await embedder.embed(requirements + skill_texts)
    requirement_vectors = vectors[: len(requirements)]
    skill_vectors = vectors[len(requirements) :]

    matches: list[RequirementMatch] = []
    for requirement, vector in zip(requirements, requirement_vectors, strict=True):
        best_index, best_score = -1, 0.0
        for index, skill_vector in enumerate(skill_vectors):
            score = cosine(vector, skill_vector)
            if score > best_score:
                best_index, best_score = index, score
        matches.append(
            RequirementMatch(
                requirement=requirement,
                best_skill=skills[best_index].name if best_index >= 0 else None,
                similarity=round(best_score, 4),
            )
        )
    return matches


def gaps(matches: list[RequirementMatch]) -> list[str]:
    """Requirements no résumé skill supports, weakest first.

    Weakest first because the retrieval and prompt budgets are finite, so if
    something has to be dropped it should be the requirement the candidate is
    closest to already demonstrating.
    """
    return [m.requirement for m in sorted(matches, key=lambda m: m.similarity) if not m.covered]
