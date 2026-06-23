"""Unit tests for the run cost ceiling (BUDGET-1).

Covers the pure cost helpers, the notification builder, and the config/CLI
wiring. The end-to-end "loop holds when the ceiling is reached" behavior is
exercised in test_orchestrator.py against the fake-claude harness.
"""
from __future__ import annotations

from types import SimpleNamespace as NS

from claude_dispatcher import notify as notify_mod
from claude_dispatcher import orchestrator as orch
from claude_dispatcher.cli import build_parser


def _task(cost):
    return NS(raw={"cost_usd": cost} if cost is not None else {})


# --- _cumulative_cost_usd -----------------------------------------------------
def test_cumulative_cost_sums_numeric_costs():
    tasks = [_task(1.5), _task(0.25), _task(3)]
    assert orch._cumulative_cost_usd(tasks) == 4.75


def test_cumulative_cost_ignores_missing_and_non_numeric():
    # No cost yet, explicit None, a stray string, and a bool all contribute 0.
    tasks = [_task(None), NS(raw={}), _task("oops"), _task(True), _task(2.0)]
    assert orch._cumulative_cost_usd(tasks) == 2.0


def test_cumulative_cost_empty_is_zero():
    assert orch._cumulative_cost_usd([]) == 0.0


# --- _add_task_cost (accumulation core of spawn-complete accounting) ----------
def test_add_task_cost_accumulates_across_spawns(tmp_path):
    import pytest
    from claude_dispatcher import yaml_io
    p = tmp_path / "t.yaml"
    p.write_text(
        "project: X\nepic: e\ntasks:\n  - key: T1\n    summary: s\n"
        "    description: d\n    type: Task\n    labels: [size:S]\n",
        encoding="utf-8")
    args = build_parser().parse_args(
        ["run", str(p), "--runs-dir", str(tmp_path / "r")])
    cfg = orch._build_config(args)
    orch._add_task_cost(cfg, "T1", 0.10)   # implementer
    orch._add_task_cost(cfg, "T1", 0.05)   # e.g. a commit-retry
    orch._add_task_cost(cfg, "T1", None)   # no-usage spawn → no-op
    orch._add_task_cost(cfg, "T1", 0)      # no-op
    row = next(t for t in yaml_io.load(p)["tasks"] if t["key"] == "T1")
    assert row["cost_usd"] == pytest.approx(0.15)


# --- _budget_exceeded ---------------------------------------------------------
def test_budget_none_disables_gate():
    assert orch._budget_exceeded([_task(1000.0)], None) is False


def test_budget_zero_or_negative_disables_gate_defensively():
    # The CLI rejects non-positive ceilings (see the parse tests below); this
    # guard is defense-in-depth for a resume whose genesis somehow carried one.
    assert orch._budget_exceeded([_task(1000.0)], 0) is False
    assert orch._budget_exceeded([_task(1000.0)], -5) is False


def test_budget_trips_at_or_above_ceiling():
    # Reaching the ceiling exactly trips (>=), as does exceeding it.
    assert orch._budget_exceeded([_task(5.0)], 5.0) is True
    assert orch._budget_exceeded([_task(5.01)], 5.0) is True


def test_budget_under_ceiling_does_not_trip():
    assert orch._budget_exceeded([_task(4.99)], 5.0) is False


# --- notification -------------------------------------------------------------
def test_budget_notification_is_high_urgency_and_tagged():
    n = notify_mod.budget_exceeded_notification(
        run_id="R1", cost_usd=12.34, ceiling_usd=10.0,
        in_flight=["T-7"], tasks_yaml="/x/tasks.yaml",
    )
    assert n.urgency == "high"
    assert "budget" in n.tags
    assert "12.34" in n.title and "10.00" in n.title
    assert "T-7" in n.body  # in-flight tasks surfaced for the human


def test_budget_notification_without_in_flight():
    n = notify_mod.budget_exceeded_notification(
        run_id="R1", cost_usd=1.0, ceiling_usd=0.5)
    assert n.urgency == "high" and "Still in flight" not in n.body


# --- config / CLI wiring ------------------------------------------------------
def test_max_cost_usd_defaults_off():
    # Default OFF so the dispatch loop is byte-identical to before.
    from claude_dispatcher.orchestrator import RunConfig
    import inspect
    sig_default = RunConfig.__dataclass_fields__["max_cost_usd"].default
    assert sig_default is None


def test_cli_parses_max_cost_usd_as_float():
    args = build_parser().parse_args(
        ["run", "t.yaml", "--max-cost-usd", "25.50"])
    assert args.max_cost_usd == 25.5


def test_cli_max_cost_usd_optional():
    args = build_parser().parse_args(["run", "t.yaml"])
    assert args.max_cost_usd is None


def test_cli_rejects_nonpositive_ceiling():
    import pytest
    for bad in ("0", "-1", "-0.5"):
        with pytest.raises(SystemExit):  # argparse turns the type error into exit 2
            build_parser().parse_args(["run", "t.yaml", "--max-cost-usd", bad])


def test_cli_rejects_nonnumeric_ceiling():
    import pytest
    with pytest.raises(SystemExit):
        build_parser().parse_args(["run", "t.yaml", "--max-cost-usd", "lots"])


def test_cli_rejects_nonfinite_ceiling():
    # nan/inf parse as floats but would silently disable the gate — reject them.
    import pytest
    for bad in ("inf", "-inf", "nan"):
        with pytest.raises(SystemExit):
            build_parser().parse_args(["run", "t.yaml", "--max-cost-usd", bad])


def test_resume_accepts_max_cost_usd_override():
    # gemini HIGH: a budget-held run must be resumable under a raised ceiling.
    args = build_parser().parse_args(
        ["resume", "some-run", "--max-cost-usd", "50"])
    assert args.max_cost_usd == 50.0


def test_resume_max_cost_usd_optional_and_validated():
    import pytest
    assert build_parser().parse_args(["resume", "r"]).max_cost_usd is None
    with pytest.raises(SystemExit):
        build_parser().parse_args(["resume", "r", "--max-cost-usd", "0"])
