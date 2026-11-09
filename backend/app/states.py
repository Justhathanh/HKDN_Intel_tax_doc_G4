"""State machine theo hop dong trang thai o Annex B cua RFP.

"exported" la su kien tren phien ban da duyet, khong phai trang thai (RFP Annex B).
"""
from enum import StrEnum


class State(StrEnum):
    RECEIVED = "received"
    QUARANTINED = "quarantined"
    PROCESSING = "processing"
    NEEDS_REVIEW = "needs_review"
    APPROVED = "approved"
    SUPERSEDED = "superseded"
    REJECTED = "rejected"


ALLOWED: dict[State, set[State]] = {
    State.RECEIVED: {State.PROCESSING, State.QUARANTINED, State.REJECTED},
    State.PROCESSING: {State.NEEDS_REVIEW, State.REJECTED},
    State.NEEDS_REVIEW: {State.APPROVED, State.REJECTED, State.PROCESSING},
    State.APPROVED: {State.SUPERSEDED},
    State.QUARANTINED: set(),
    State.REJECTED: set(),
    State.SUPERSEDED: set(),
}


class IllegalTransition(ValueError):
    pass


def check_transition(current: State, target: State) -> None:
    if target not in ALLOWED[current]:
        raise IllegalTransition(f"{current} -> {target}")
