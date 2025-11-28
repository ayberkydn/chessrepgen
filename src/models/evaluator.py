from typing import NamedTuple


class TerminationDecision(NamedTuple):
    should_stop: bool
    reason: str
    applies_to_position: bool
