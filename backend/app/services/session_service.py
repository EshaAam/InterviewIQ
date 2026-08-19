"""Session state machine — the single authority over `InterviewSession.state`.

Every legal edge in the design-doc diagram is declared in `_TRANSITIONS`.
`transition()` is the one place state changes; it rejects illegal edges,
is idempotent (re-entering the current state is a no-op), and records a
`failure_reason` on the failure edges.

Keeping the transition map as data — not scattered `if` statements across
routes and workers — is what makes the machine testable and auditable.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.models.session import InterviewSession, SessionState

S = SessionState

# Allowed target states for each source state. The empty frozensets are the
# terminal states — nothing leaves COMPLETED / FAILED / EXPIRED / NEEDS_HUMAN.
_TRANSITIONS: dict[SessionState, frozenset[SessionState]] = {
    S.CREATED: frozenset({S.PARSING, S.EXPIRED}),
    S.PARSING: frozenset({S.GENERATING_QS, S.FAILED, S.EXPIRED}),
    S.GENERATING_QS: frozenset({S.READY, S.FAILED, S.EXPIRED}),
    S.READY: frozenset({S.IN_PROGRESS, S.EXPIRED}),
    S.IN_PROGRESS: frozenset({S.EVALUATING, S.EXPIRED}),
    S.EVALUATING: frozenset(
        {S.COMPLETED, S.NEEDS_HUMAN_REVIEW, S.FAILED, S.EXPIRED}
    ),
    S.COMPLETED: frozenset(),
    S.NEEDS_HUMAN_REVIEW: frozenset(),
    S.FAILED: frozenset(),
    S.EXPIRED: frozenset(),
}

# States that must carry a human-readable reason when entered.
_FAILURE_STATES: frozenset[SessionState] = frozenset({S.FAILED, S.EXPIRED})


class IllegalTransition(Exception):
    """Raised when a state edge is not permitted by the machine."""

    def __init__(self, current: SessionState, target: SessionState) -> None:
        self.current = current
        self.target = target
        super().__init__(f"illegal transition: {current.value} -> {target.value}")


def can_transition(current: SessionState, target: SessionState) -> bool:
    return target in _TRANSITIONS.get(current, frozenset())


class SessionService:
    """Domain operations over interview sessions.

    Phase 1 only needs the transition primitive; later phases add creation,
    question fetching, and answer submission on top of the same machine.
    """

    @staticmethod
    def transition(
        session: InterviewSession,
        target: SessionState,
        *,
        reason: str | None = None,
    ) -> InterviewSession:
        """Move `session` to `target`, mutating it in place.

        - Re-entering the current state is an idempotent no-op (so a retried
          worker task doesn't fail).
        - Illegal edges raise `IllegalTransition` and change nothing.
        - Failure states require a `reason`; it's cleared on any recovery edge.
        """
        current = session.state

        if target == current:
            return session

        if not can_transition(current, target):
            raise IllegalTransition(current, target)

        if target in _FAILURE_STATES and not reason:
            raise ValueError(f"entering {target.value} requires a reason")

        session.state = target
        session.failure_reason = reason if target in _FAILURE_STATES else None
        return session

    @staticmethod
    def is_expired(session: InterviewSession) -> bool:
        """True if the server-side deadline has passed. The client never decides this."""
        if session.expires_at is None:
            return False
        deadline = session.expires_at
        # SQLite (tests) drops tzinfo on read; treat a naive deadline as UTC so
        # the comparison against an aware `now` is valid on both backends.
        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=UTC)
        return datetime.now(UTC) >= deadline

    @classmethod
    def maybe_expire(cls, session: InterviewSession) -> bool:
        """Move a still-active session to EXPIRED if its deadline passed.

        Returns True if it transitioned. Terminal states are left untouched.
        """
        if session.state in _FAILURE_STATES or not _TRANSITIONS.get(session.state):
            return False
        if cls.is_expired(session):
            cls.transition(session, SessionState.EXPIRED, reason="deadline passed")
            return True
        return False
