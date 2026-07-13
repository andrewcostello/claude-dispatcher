"""Tests for agent-native implementer prompts, effort plumbing, quality cascade
triggers, and relaxed panel risk/size gating.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from ruamel.yaml import YAML

from claude_dispatcher import cross_family_reviewer as cfr
from claude_dispatcher import orchestrator
from claude_dispatcher import plan
from claude_dispatcher import spawn


# --- 1. agent-native prompts -------------------------------------------------


def _prompt(**kwargs) -> str:
    defaults = dict(
        task_key="T-1",
        task_summary="sum",
        task_type="Task",
        task_labels=["size:S"],
        task_description="Implement the foo helper.",
        branch="feat/t-1",
        summary_path=Path("/tmp/summary.md"),
        run_id="r1",
        max_iterations=1,
        financial_paths="",
        skip_design=False,
        skip_security_linter=False,
        reviewer_count=None,
    )
    defaults.update(kwargs)
    return spawn.build_prompt(**defaults)


def test_all_agents_use_unified_implementer_prompt_not_tasker():
    """Single-orchestrator: no family adopts tasker.md under dispatcher run."""
    for agent in (None, "claude", "grok", "codex", "gemini"):
        p = _prompt(agent=agent)
        assert "tasker.md" not in p, f"agent={agent!r} must not load Tasker"
        assert "adopt the Tasker" not in p
        assert "autonomous implementer" in p
        assert "Implement the foo helper." in p
        assert "/tmp/summary.md" in p
        assert "WORKER" in p or "not an orchestrator" in p


def test_claude_and_grok_share_same_job_shape():
    claude = _prompt(agent="claude")
    grok = _prompt(agent="grok")
    # Same instructions / summary contract; only family name differs.
    assert "Commit your work" in claude and "Commit your work" in grok
    assert "Do NOT push" in claude and "Do NOT push" in grok
    assert "**Status:** Done" in claude and "**Status:** Done" in grok
    assert "agent family:\nclaude" in claude or "claude" in claude.lower()
    assert "grok" in grok


# --- 3. effort field ---------------------------------------------------------


def _load(yaml_text: str):
    return plan.load_tasks(YAML().load(io.StringIO(yaml_text)))


_BASE = """tasks:
  - key: T1
    summary: s
    description: d
    type: Task
    labels: [size:S]
"""


def test_effort_loaded_and_validated():
    (t,) = _load(_BASE + "    effort: high\n")
    assert t.effort == "high"
    (t2,) = _load(_BASE + "    effort: LOW\n")
    assert t2.effort == "low"
    (t3,) = _load(_BASE)
    assert t3.effort is None


def test_unknown_effort_rejected():
    with pytest.raises(plan.ValidationError, match="unknown effort"):
        _load(_BASE + "    effort: extreme\n")


def test_empty_effort_becomes_none():
    (t,) = _load(_BASE + '    effort: ""\n')
    assert t.effort is None


# --- 5. panel skip + helpers -------------------------------------------------


def test_is_small_leaf_and_has_risk_label():
    assert cfr.is_small_leaf(["size:XS", "area:ui"]) is True
    assert cfr.is_small_leaf(["size:S"]) is True
    assert cfr.is_small_leaf(["size:M"]) is False
    assert cfr.has_risk_label(["size:S", "security"]) is True
    assert cfr.has_risk_label(["size:S"]) is False
    assert cfr.has_risk_label(["risk:critical"]) is True


def _cfg(mode: str):
    return type("C", (), {"cross_family_panel": mode})()


def _snap(labels, task_type="Task"):
    return orchestrator.TaskSnapshot(
        key="T", summary="s", description="d", type=task_type, labels=labels,
    )


def test_panel_skips_xs_even_when_always_unless_risk():
    assert orchestrator._panel_should_run(_cfg("always"), _snap(["size:XS"])) is False
    assert orchestrator._panel_should_run(
        _cfg("always"), _snap(["size:XS", "security"])
    ) is True


def test_panel_always_still_runs_medium_without_risk():
    assert orchestrator._panel_should_run(_cfg("always"), _snap(["size:M"])) is True


def test_panel_auto_requires_risk_label():
    assert orchestrator._panel_should_run(_cfg("auto"), _snap(["size:M"])) is False
    assert orchestrator._panel_should_run(
        _cfg("auto"), _snap(["size:M", "critical"])
    ) is True


def test_panel_never_always_false():
    assert orchestrator._panel_should_run(
        _cfg("never"), _snap(["size:L", "security"])
    ) is False


# --- 4. quality cascade context (unit: cascade rungs + reason labels) --------


def test_cascade_respects_configured_high_effort():
    snap = orchestrator.TaskSnapshot(
        key="T", summary="s", description="d", type="Task",
        labels=["size:S"], agent="grok", effort="high",
    )
    # Already high — no effort-bump rung
    assert orchestrator._implementer_cascade(snap) == [
        ("grok", "high"), ("claude", "high"),
    ]


def test_is_hard_task_size_and_risk():
    assert orchestrator._is_hard_task(_snap(["size:L"])) is True
    assert orchestrator._is_hard_task(_snap(["size:S", "auth"])) is False
    assert orchestrator._is_hard_task(_snap(["size:S", "financial"])) is True
    assert orchestrator._is_hard_task(_snap(["size:S", "risk:high"])) is True
