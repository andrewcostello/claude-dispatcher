"""Phase 2 (--no-claude / cascade terminal) + Phase 4 quality level tests."""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from ruamel.yaml import YAML

from claude_dispatcher import orchestrator
from claude_dispatcher import plan
from claude_dispatcher import quality_levels as ql
from claude_dispatcher import spawn
from claude_dispatcher.cli import build_parser


def _snap(**kwargs) -> orchestrator.TaskSnapshot:
    base = dict(
        key="T", summary="s", description="d", type="Task",
        labels=["size:S"], agent="grok", effort=None,
    )
    base.update(kwargs)
    return orchestrator.TaskSnapshot(**base)


def test_cascade_terminal_grok_never_appends_claude():
    snap = _snap(agent="grok", labels=["size:S"])
    rungs = orchestrator._implementer_cascade(snap, cascade_terminal="grok")
    agents = [a for a, _ in rungs]
    assert "claude" not in agents
    assert agents[0] == "grok"
    assert agents[-1] == "grok"


def test_cascade_terminal_claude_still_closes():
    snap = _snap(agent="grok", labels=["size:S"])
    rungs = orchestrator._implementer_cascade(snap, cascade_terminal="claude")
    assert rungs[-1] == ("claude", "high")


def test_build_config_no_claude_defaults():
    parser = build_parser()
    args = parser.parse_args([
        "run", "tasks.yaml", "--mode", "unattended", "--no-claude",
    ])
    cfg = orchestrator._build_config(args)
    assert cfg.no_claude is True
    assert cfg.implementer == "grok"
    assert cfg.cascade_terminal == "grok"
    assert cfg.skip_verification is True
    assert cfg.haiku_summary is False


def test_parse_grok_usage_object():
    raw = '{"model":"grok-build","usage":{"input_tokens":3,"output_tokens":7},"total_cost_usd":0}'
    u = spawn.parse_grok_usage(raw)
    assert u.input_tokens == 3
    assert u.output_tokens == 7
    assert u.model == "grok-build"


def test_parse_grok_usage_ndjson_tail():
    raw = 'noise\n{"usage":{"input_tokens":1},"model":"g"}\n'
    u = spawn.parse_grok_usage(raw)
    assert u.input_tokens == 1


def test_quality_task_override_wins():
    levels = ql.resolve_quality_levels(
        labels=["size:S", "security"],
        task_verify="mechanical",
        task_panel="never",
        design_verify="llm_strict",
        design_panel="full",
        run_verify="llm",
        run_panel="auto",
    )
    assert levels.verify == "mechanical"
    assert levels.panel == "never"
    assert levels.source == "task"


def test_quality_design_raises_not_lowers():
    levels = ql.resolve_quality_levels(
        labels=["size:S", "security"],  # critical floor
        design_verify="none",
        design_panel="never",
        run_verify="mechanical",
        run_panel="never",
    )
    # Floor for critical is llm_strict + full; design cannot sink below.
    assert levels.verify == "llm_strict"
    assert levels.panel == "full"


def test_load_verify_panel_fields():
    doc = YAML().load(io.StringIO("""
tasks:
  - key: T1
    summary: s
    description: d
    type: Task
    labels: [size:S]
    verify: mechanical
    panel: never
"""))
    (t,) = plan.load_tasks(doc)
    assert t.verify == "mechanical"
    assert t.panel == "never"


def test_unknown_verify_rejected():
    with pytest.raises(plan.ValidationError, match="unknown verify"):
        plan.load_tasks(YAML().load(io.StringIO("""
tasks:
  - key: T1
    summary: s
    description: d
    type: Task
    labels: [size:S]
    verify: extreme
""")))


def test_panel_should_run_honors_task_never():
    cfg = orchestrator.RunConfig(
        tasks_path=Path("t.yaml"),
        runs_dir=Path("r"),
        run_id="r",
        mode="unattended",
        max_parallel=1,
        max_iterations=1,
        reviewer_count=None,
        skip_design=False,
        skip_security_linter=False,
        financial_paths="",
        claude_bin="claude",
        worktree_base=None,
        label_filter=[],
        only_keys=None,
        cross_family_panel="always",
    )
    snap = _snap(labels=["size:M", "security"], panel="never")
    assert orchestrator._panel_should_run(cfg, snap) is False


def test_design_required_critical_and_leaf():
    assert ql.design_required(["size:S", "security"]) is True
    assert ql.design_required(["size:XS"]) is False
    assert ql.design_required(["size:M"], task_design=True) is True
    assert ql.design_required(
        ["size:M"], description="Introduce a new contract for X",
    ) is True
    assert ql.design_required(["size:M"], task_design=False) is False


def test_panel_should_run_honors_task_full():
    cfg = orchestrator.RunConfig(
        tasks_path=Path("t.yaml"),
        runs_dir=Path("r"),
        run_id="r",
        mode="unattended",
        max_parallel=1,
        max_iterations=1,
        reviewer_count=None,
        skip_design=False,
        skip_security_linter=False,
        financial_paths="",
        claude_bin="claude",
        worktree_base=None,
        label_filter=[],
        only_keys=None,
        cross_family_panel="never",
    )
    snap = _snap(labels=["size:M"], panel="full")
    assert orchestrator._panel_should_run(cfg, snap) is True
