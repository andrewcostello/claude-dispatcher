"""Damaged rows must not crash reporting; decision inputs remain strict."""

from __future__ import annotations

from pathlib import Path

import pytest

from claude_dispatcher import orchestrator as orch
from claude_dispatcher import plan as plan_mod

GOOD = """tasks:
  - key: A-1
    summary: fine
    description: d
    type: Task
    labels: [size:S]
    agent: grok
    model: grok-4.6
"""
# The exact defect the cascade wrote: a claude agent holding grok's model.
DEFECTIVE = GOOD + """  - key: A-2
    summary: broken
    description: d
    type: Task
    labels: [size:S]
    agent: claude
    model: grok-4.6
"""


def _cfg(tmp_path: Path, text: str):
    y = tmp_path / "tasks.yaml"
    y.write_text(text)
    return orch.RunConfig(
        tasks_path=y, runs_dir=tmp_path / "runs", run_id="r", mode="unattended",
        max_parallel=1, max_iterations=1, reviewer_count=None,
        skip_design=False, skip_security_linter=False, financial_paths="",
        claude_bin="claude", worktree_base=None,
        label_filter=plan_mod.parse_label_filter(None), only_keys=None,
        cross_family_panel="full",
    )


def test_a_defective_row_does_not_raise_out_of_the_rollup_reader(tmp_path) -> None:
    """The property. A raise here reached _run_loop and ended a run whose work
    was already complete."""
    tasks = orch._load_tasks_for_rollup(_cfg(tmp_path, DEFECTIVE))
    assert [t.key for t in tasks] == ["A-1"]


def test_the_healthy_rows_survive(tmp_path) -> None:
    """Refusing the whole file to punish one row destroys the other 72 rows'
    state — which is the cost this seal exists to prevent."""
    tasks = orch._load_tasks_for_rollup(_cfg(tmp_path, DEFECTIVE))
    assert len(tasks) == 1 and tasks[0].agent == "grok"


def test_startup_stays_strict(tmp_path) -> None:
    """A worklist that does not validate must never START a run. Tolerance is
    for work already in flight, never for launching new work."""
    with pytest.raises(plan_mod.ValidationError):
        orch._load_tasks_snapshot_strict(_cfg(tmp_path, DEFECTIVE))


def test_a_valid_worklist_is_unchanged(tmp_path) -> None:
    tasks = orch._load_tasks_snapshot(_cfg(tmp_path, GOOD))
    assert [t.key for t in tasks] == ["A-1"]


def test_an_unreadable_file_yields_nothing_rather_than_raising(tmp_path) -> None:
    cfg = _cfg(tmp_path, GOOD)
    cfg.tasks_path.write_text("this: [is not: valid yaml\n")
    assert orch._load_tasks_for_rollup(cfg) == []


def test_the_startup_path_uses_the_strict_loader() -> None:
    """WIRING. Making startup tolerant would let a run BEGIN on a worklist the
    dispatcher knows is broken — the opposite of the intent."""
    import inspect
    src = inspect.getsource(orch.execute)
    assert "_load_tasks_snapshot_strict(cfg)" in src, (
        "run startup must use the strict loader")


def test_a_lock_timeout_still_propagates(tmp_path, monkeypatch) -> None:
    """A lock timeout is NOT a defective worklist — it means another writer
    holds the file right now. Swallowing it would report an empty worklist
    while the real file is intact, which is a worse lie than the crash this
    guard replaces. Caught by test_lock_timeout_flows_to_filelock when the
    guard was first widened to `except Exception`."""
    from claude_dispatcher import yaml_io

    cfg = _cfg(tmp_path, GOOD)

    def boom(*a, **k):
        raise yaml_io.LockTimeout("held by another writer")

    monkeypatch.setattr(orch, "_load_tasks_snapshot_strict", boom)
    with pytest.raises(yaml_io.LockTimeout):
        orch._load_tasks_snapshot(cfg)
