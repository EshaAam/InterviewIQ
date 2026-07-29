"""Model registry.

Importing every model here guarantees `Base.metadata` is complete before
Alembic autogenerate or `create_all` inspects it. Import the package, not
individual modules, wherever the full metadata is needed.
"""

from app.db.base import Base
from app.models.answer import Answer
from app.models.evaluation import Evaluation
from app.models.extracted_skill import ExtractedSkill
from app.models.llm_call import LLMCall
from app.models.question import Question
from app.models.report import Report
from app.models.resume import ParseStatus, Resume
from app.models.session import InterviewSession, SessionState
from app.models.user import User, UserRole

__all__ = [
    "Base",
    "User",
    "UserRole",
    "Resume",
    "ParseStatus",
    "ExtractedSkill",
    "InterviewSession",
    "SessionState",
    "Question",
    "Answer",
    "Evaluation",
    "Report",
    "LLMCall",
]
