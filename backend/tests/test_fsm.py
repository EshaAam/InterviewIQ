"""Session FSM — table-driven legality tests.

The machine is the domain spine, so its edges are tested exhaustively:
every (source, target) pair is either declared legal or must raise.
"""

from __future__ import annotations

import itertools

import pytest

from app.models.session import InterviewSession, SessionState
from app.services.session_service import (
    _TRANSITIONS,
    IllegalTransition,
    SessionService,
    can_transition,
)

S = SessionState


def _session(state: SessionState) -> InterviewSession:
    return InterviewSession(state=state)


# Every legal edge in the design-doc diagram.
LEGAL_EDGES = [
    (S.CREATED, S.PARSING),
    (S.PARSING, S.GENERATING_QS),
    (S.GENERATING_QS, S.READY),
    (S.READY, S.IN_PROGRESS),
    (S.IN_PROGRESS, S.EVALUATING),
    (S.EVALUATING, S.COMPLETED),
    (S.EVALUATING, S.NEEDS_HUMAN_REVIEW),
    (S.PARSING, S.FAILED),
    (S.GENERATING_QS, S.FAILED),
    (S.EVALUATING, S.FAILED),
    (S.CREATED, S.EXPIRED),
    (S.PARSING, S.EXPIRED),
    (S.GENERATING_QS, S.EXPIRED),
    (S.READY, S.EXPIRED),
    (S.IN_PROGRESS, S.EXPIRED),
    (S.EVALUATING, S.EXPIRED),
]


@pytest.mark.parametrize("src,dst", LEGAL_EDGES)
def test_legal_transitions_apply(src: SessionState, dst: SessionState) -> None:
    reason = "boom" if dst in (S.FAILED, S.EXPIRED) else None
    session = SessionService.transition(_session(src), dst, reason=reason)
    assert session.state == dst


def test_every_illegal_edge_raises() -> None:
    legal = set(LEGAL_EDGES)
    for src, dst in itertools.product(SessionState, repeat=2):
        if src == dst or (src, dst) in legal:
            continue
        with pytest.raises(IllegalTransition):
            SessionService.transition(_session(src), dst, reason="x")


def test_reentering_same_state_is_idempotent_noop() -> None:
    session = _session(S.EVALUATING)
    result = SessionService.transition(session, S.EVALUATING)
    assert result.state == S.EVALUATING


def test_failure_state_requires_reason() -> None:
    with pytest.raises(ValueError):
        SessionService.transition(_session(S.PARSING), S.FAILED)


def test_failure_reason_recorded_and_cleared_on_recovery() -> None:
    session = _session(S.EVALUATING)
    SessionService.transition(session, S.FAILED, reason="llm timeout")
    assert session.failure_reason == "llm timeout"

    # A non-failure transition clears the reason.
    fresh = _session(S.EVALUATING)
    SessionService.transition(fresh, S.COMPLETED)
    assert fresh.failure_reason is None


def test_illegal_transition_does_not_mutate() -> None:
    session = _session(S.COMPLETED)
    with pytest.raises(IllegalTransition):
        SessionService.transition(session, S.READY)
    assert session.state == S.COMPLETED


def test_terminal_states_have_no_outgoing_edges() -> None:
    for terminal in (S.COMPLETED, S.NEEDS_HUMAN_REVIEW, S.FAILED, S.EXPIRED):
        assert _TRANSITIONS[terminal] == frozenset()


def test_can_transition_matches_service() -> None:
    assert can_transition(S.CREATED, S.PARSING) is True
    assert can_transition(S.CREATED, S.COMPLETED) is False
