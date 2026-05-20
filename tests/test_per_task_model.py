"""Tests for per-task `model:` YAML field.

Verifies:
  - plan.load_tasks() reads `model` off task rows when present.
  - Tasks without `model` leave the field as None.
  - Empty / whitespace model values become None (no spurious --model flag).
  - The orchestrator threads task.model → TaskSnapshot.model → spawn
    extra_args as `--model <value>` appended after run-level extras.
"""

from __future__ import annotations

from pathlib import Path

from claude_dispatcher import plan as plan_mod
from claude_dispatcher import yaml_io


def _make_yaml(tmp_path: Path, tasks_yaml: str) -> Path:
    p = tmp_path / "tasks.yaml"
    p.write_text(tasks_yaml)
    return p


def test_load_tasks_reads_model_field(tmp_path: Path):
    """A task row with `model: claude-sonnet-4-6` populates Task.model."""
    p = _make_yaml(tmp_path, """
project: TEST
tasks:
  - key: T-1
    summary: trivial
    description: ok
    type: Task
    labels: [size:XS]
    model: claude-sonnet-4-6
  - key: T-2
    summary: complex
    description: ok
    type: Task
    labels: [size:XL]
    model: claude-opus-4-7
""")
    doc = yaml_io.load(p)
    tasks = plan_mod.load_tasks(doc)
    by_key = {t.key: t for t in tasks}
    assert by_key["T-1"].model == "claude-sonnet-4-6"
    assert by_key["T-2"].model == "claude-opus-4-7"


def test_missing_model_field_stays_none(tmp_path: Path):
    """A task row without `model` leaves Task.model = None — the orchestrator
    won't append --model, and the run-level default (or CLI default) applies."""
    p = _make_yaml(tmp_path, """
project: TEST
tasks:
  - key: T-1
    summary: trivial
    description: ok
    type: Task
    labels: [size:XS]
""")
    tasks = plan_mod.load_tasks(yaml_io.load(p))
    assert tasks[0].model is None


def test_empty_model_becomes_none(tmp_path: Path):
    """An empty-string or whitespace-only model field is treated as absent.
    Prevents accidentally passing `--model ` with no value."""
    p = _make_yaml(tmp_path, """
project: TEST
tasks:
  - key: T-1
    summary: trivial
    description: ok
    type: Task
    labels: [size:XS]
    model: ""
  - key: T-2
    summary: trivial
    description: ok
    type: Task
    labels: [size:XS]
    model: "   "
""")
    tasks = plan_mod.load_tasks(yaml_io.load(p))
    assert tasks[0].model is None
    assert tasks[1].model is None


def test_model_field_is_stripped(tmp_path: Path):
    """Surrounding whitespace on the value is stripped; the dispatcher
    passes the clean value to --model."""
    p = _make_yaml(tmp_path, """
project: TEST
tasks:
  - key: T-1
    summary: trivial
    description: ok
    type: Task
    labels: [size:XS]
    model: "  claude-sonnet-4-6  "
""")
    tasks = plan_mod.load_tasks(yaml_io.load(p))
    assert tasks[0].model == "claude-sonnet-4-6"


def test_snapshot_carries_model():
    """TaskSnapshot is the frozen handoff to the worker; it must carry the
    model so the spawn-time logic can append --model."""
    from claude_dispatcher.orchestrator import TaskSnapshot
    snap = TaskSnapshot(
        key="T-1", summary="x", description="x", type="Task",
        labels=["size:XS"], model="claude-sonnet-4-6",
    )
    assert snap.model == "claude-sonnet-4-6"
    # Default is None.
    snap2 = TaskSnapshot(key="T-2", summary="x", description="x",
                         type="Task", labels=["size:XS"])
    assert snap2.model is None
