"""Contract tests for the bake-off harness pure-logic body-fills.

Each test is skipped in the skeleton; the dispatched body-fill task that
implements its function removes the skip (so the pytest gate stays green for
sibling tasks until each is filled). Keep these pure — no subprocess/network/fs.
"""
from types import SimpleNamespace

import pytest

from claude_dispatcher import bakeoff
from claude_dispatcher import plan as plan_mod


def _task(key="T1", labels=None, description="", summary="s"):
    return plan_mod.Task(
        key=key, summary=summary, description=description, type="Task",
        labels=labels or ["size:M"], blocked_by=[], status="To Do", raw={},
    )


def _panel(blocking=0):
    # Minimal stand-in for cfr.PanelVerdict: only .blocking_findings is read.
    return SimpleNamespace(blocking_findings=[{"severity": "HIGH"}] * blocking)


# --- infer_stack (BKO-1) ---------------------------------------------------
@pytest.mark.skip(reason="BKO body-fill: infer_stack")
def test_infer_stack_go_from_label():
    assert bakeoff.infer_stack(_task(labels=["size:S", "area:bay-session"])) == "go"


@pytest.mark.skip(reason="BKO body-fill: infer_stack")
def test_infer_stack_react_from_label():
    assert bakeoff.infer_stack(_task(labels=["size:M", "area:mobile"])) == "react"


@pytest.mark.skip(reason="BKO body-fill: infer_stack")
def test_infer_stack_react_from_path_when_no_label():
    t = _task(labels=["size:S"], description="edit apps/skillstrike-mobile/src/x.tsx")
    assert bakeoff.infer_stack(t) == "react"


@pytest.mark.skip(reason="BKO body-fill: infer_stack")
def test_infer_stack_unknown():
    assert bakeoff.infer_stack(_task(labels=["size:S"], description="docs only")) == "unknown"


# --- compute_relaxed_pass (BKO-2) ------------------------------------------
@pytest.mark.skip(reason="BKO body-fill: compute_relaxed_pass")
def test_relaxed_pass_gate_and_no_blocking():
    assert bakeoff.compute_relaxed_pass(True, _panel(blocking=0)) is True


@pytest.mark.skip(reason="BKO body-fill: compute_relaxed_pass")
def test_relaxed_pass_blocked_by_critical():
    assert bakeoff.compute_relaxed_pass(True, _panel(blocking=2)) is False


@pytest.mark.skip(reason="BKO body-fill: compute_relaxed_pass")
def test_relaxed_pass_requires_gate():
    assert bakeoff.compute_relaxed_pass(False, _panel(blocking=0)) is False


@pytest.mark.skip(reason="BKO body-fill: compute_relaxed_pass")
def test_relaxed_pass_none_panel_counts_as_no_blocking():
    assert bakeoff.compute_relaxed_pass(True, None) is True


# --- evaluate_reviewers (BKO-3) --------------------------------------------
def _cell(agent, gate, reviewers):
    return bakeoff.CellResult(
        task_key="T1", agent=agent, gate_passed=gate, reviewers=reviewers)


def test_evaluate_reviewers_counts_gate_failing_approvals():
    # codex approves a solution that FAILED the gate -> objective false-negative
    cells = [
        _cell("grok", False, [
            {"family": "codex", "verdict": "approve", "findings": []},
            {"family": "claude", "verdict": "block",
             "findings": [{"severity": "HIGH", "location": "x:1"}]},
        ]),
    ]
    stats = bakeoff.evaluate_reviewers(cells)
    assert stats["codex"]["approvals_of_gate_failing"] == 1
    assert stats["codex"]["approve_rate"] == 1.0
    assert stats["claude"]["blocking_findings_total"] == 1
    assert stats["claude"]["approvals_of_gate_failing"] == 0


def test_evaluate_reviewers_unique_blocking():
    cells = [
        _cell("grok", True, [
            {"family": "claude", "verdict": "block",
             "findings": [{"severity": "HIGH", "location": "a:1"}]},
            {"family": "codex", "verdict": "approve", "findings": []},
        ]),
    ]
    stats = bakeoff.evaluate_reviewers(cells)
    assert stats["claude"]["unique_blocking"] == 1


# --- render_report (BKO-4) -------------------------------------------------
@pytest.mark.skip(reason="BKO body-fill: render_report")
def test_render_report_has_sections_and_totals():
    cells = [
        bakeoff.CellResult(task_key="T1", agent="grok", effort="high", stack="react",
                           gate_passed=True, relaxed_pass=True, duration_s=200.0,
                           cost_usd=0.0, input_tokens=10, output_tokens=20, reviewers=[]),
        bakeoff.CellResult(task_key="T1", agent="claude", effort="high", stack="react",
                           gate_passed=True, relaxed_pass=True, duration_s=900.0,
                           cost_usd=6.0, input_tokens=100, output_tokens=200, reviewers=[]),
    ]
    md = bakeoff.render_report(cells)
    assert isinstance(md, str)
    assert "agent" in md.lower() and "effort" in md.lower()
    assert "react" in md.lower()           # per-stack section
    assert "reviewer" in md.lower()        # reviewer-eval section
    assert "claude" in md and "grok" in md
