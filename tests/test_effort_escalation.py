"""Seals for forgetting a cascade-chosen effort (D-64, last piece).

Measured in wave 1: DF-4-3 carried `effort: high` written by an earlier cascade,
so every future dispatch of that task began at high effort — "a permanent cost
increase caused by a transient failure, carried in the plan file with nothing
marking it as a consequence rather than a choice."

Nothing marking it is the crux: once written, an escalated effort and an author's
deliberate one are the same string. So provenance is stamped at escalation time,
which is the only moment the difference exists.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from claude_dispatcher import orchestrator as orch, plan as plan_mod

STAMP = orch.EFFORT_ESCALATED_STAMP


def test_an_escalated_effort_is_forgotten_on_done() -> None:
    """The defect. Measured under: drop the `row.pop("effort")` and this reddens
    — the task starts every later dispatch at the escalated tier.
    """
    row = {"effort": "high", STAMP: True, "status": "Done"}
    orch._forget_escalated_effort(row, plan_mod.DONE)
    assert "effort" not in row
    assert STAMP not in row, "the marker must go with the thing it marks"


def test_an_AUTHORS_effort_is_never_touched() -> None:
    """The reason provenance exists at all. A plan author who wrote `effort: high`
    meant it, and a task that succeeds must not silently lose it.

    Measured under: clear `effort` unconditionally on Done and this reddens.
    """
    row = {"effort": "high", "status": "Done"}
    orch._forget_escalated_effort(row, plan_mod.DONE)
    assert row["effort"] == "high"


def test_a_blocked_task_KEEPS_its_escalation() -> None:
    """On Done only, and deliberately. A task that failed at a higher tier should
    start there next time — the defect was an escalation surviving SUCCESS, not
    one surviving failure.

    Measured under: clear on every terminal status and this reddens.
    """
    for status in (plan_mod.BLOCKED, "Escalated", "In Progress"):
        row = {"effort": "high", STAMP: True}
        orch._forget_escalated_effort(row, status)
        assert row["effort"] == "high", status
        assert row[STAMP] is True, status


def test_a_row_with_no_effort_is_untouched() -> None:
    row = {"status": "Done"}
    orch._forget_escalated_effort(row, plan_mod.DONE)
    assert row == {"status": "Done"}


def test_the_stamp_is_only_written_when_the_effort_actually_CHANGED() -> None:
    """A cascade that lands on the same effort the plan asked for has escalated
    nothing, so stamping there would make a deliberate effort look like a
    consequence and lose it on Done.

    Measured under: stamp unconditionally beside the effort write and this
    reddens.
    """
    src = Path(orch.__file__).read_text()
    at = src.index("def _stamp_agent_effort(")
    block = src[at:at + 1200]
    assert "if e != planned:" in block
    assert f'row[EFFORT_ESCALATED_STAMP] = True' in block


def test_the_planned_effort_is_captured_before_the_cascade_can_overwrite_it() -> None:
    """`snap.effort` is reassigned as rungs advance, so reading it at stamp time
    would compare the escalated value against itself and never stamp.

    Measured under: use `snap.effort` instead of the captured value and this
    reddens.
    """
    src = Path(orch.__file__).read_text()
    capture_at = src.index("snap_planned_effort = snap.effort")
    loop_at = src.index("for idx, (attempt_agent, attempt_effort) in enumerate(cascade):")
    assert capture_at < loop_at, "must be captured BEFORE the cascade loop"


def test_the_completion_writer_calls_it() -> None:
    """Wiring: recorded provenance that nothing acts on is the D-72 shape."""
    src = Path(orch.__file__).read_text()
    at = src.index('row["status"] = final_status')
    assert "_forget_escalated_effort(row, final_status)" in src[at:at + 400]
