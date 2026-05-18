"""Tests for runnable-set computation, label filtering, and wave planning."""

from __future__ import annotations

import pytest

from claude_dispatcher import plan, yaml_io


# --- helpers ----------------------------------------------------------------

def _yaml(tasks_block: str) -> dict:
    """Parse a YAML snippet that's just a tasks list. Returns the doc."""
    import io
    from ruamel.yaml import YAML
    y = YAML(typ="rt")
    return y.load(io.StringIO("tasks:\n" + tasks_block))


# --- validation -------------------------------------------------------------

def test_load_tasks_requires_size_label() -> None:
    doc = _yaml(
        "  - key: A\n"
        "    summary: x\n"
        "    description: y\n"
        "    type: Task\n"
        "    labels: [area:schema]\n"  # no size:
    )
    with pytest.raises(plan.ValidationError, match="size:"):
        plan.load_tasks(doc)


def test_load_tasks_rejects_duplicate_keys() -> None:
    doc = _yaml(
        "  - key: A\n"
        "    summary: x\n"
        "    description: y\n"
        "    type: Task\n"
        "    labels: [size:S]\n"
        "  - key: A\n"  # duplicate
        "    summary: x2\n"
        "    description: y2\n"
        "    type: Task\n"
        "    labels: [size:M]\n"
    )
    with pytest.raises(plan.ValidationError, match="duplicate task key"):
        plan.load_tasks(doc)


def test_load_tasks_rejects_unknown_blockedby() -> None:
    doc = _yaml(
        "  - key: A\n"
        "    summary: x\n"
        "    description: y\n"
        "    type: Task\n"
        "    labels: [size:S]\n"
        "    blockedBy: [DOES_NOT_EXIST]\n"
    )
    with pytest.raises(plan.ValidationError, match="DOES_NOT_EXIST"):
        plan.load_tasks(doc)


def test_load_tasks_rejects_cycles() -> None:
    doc = _yaml(
        "  - key: A\n    summary: x\n    description: y\n    type: Task\n"
        "    labels: [size:S]\n    blockedBy: [B]\n"
        "  - key: B\n    summary: x\n    description: y\n    type: Task\n"
        "    labels: [size:S]\n    blockedBy: [A]\n"
    )
    with pytest.raises(plan.ValidationError, match="cycle"):
        plan.load_tasks(doc)


def test_load_tasks_defaults_status_to_todo() -> None:
    doc = _yaml(
        "  - key: A\n    summary: x\n    description: y\n    type: Task\n"
        "    labels: [size:S]\n"
    )
    tasks = plan.load_tasks(doc)
    assert tasks[0].status == plan.TODO


def test_load_tasks_preserves_explicit_status() -> None:
    doc = _yaml(
        "  - key: A\n    summary: x\n    description: y\n    type: Task\n"
        "    labels: [size:S]\n    status: Done\n"
    )
    tasks = plan.load_tasks(doc)
    assert tasks[0].status == plan.DONE


# --- runnable-set -----------------------------------------------------------

def test_runnable_now_picks_no_blocker_tasks() -> None:
    doc = _yaml(
        "  - key: A\n    summary: x\n    description: y\n    type: Task\n"
        "    labels: [size:S]\n"
        "  - key: B\n    summary: x\n    description: y\n    type: Task\n"
        "    labels: [size:S]\n    blockedBy: [A]\n"
    )
    tasks = plan.load_tasks(doc)
    assert {t.key for t in plan.runnable_now(tasks)} == {"A"}


def test_runnable_now_unblocks_once_dependency_done() -> None:
    doc = _yaml(
        "  - key: A\n    summary: x\n    description: y\n    type: Task\n"
        "    labels: [size:S]\n    status: Done\n"
        "  - key: B\n    summary: x\n    description: y\n    type: Task\n"
        "    labels: [size:S]\n    blockedBy: [A]\n"
    )
    tasks = plan.load_tasks(doc)
    assert {t.key for t in plan.runnable_now(tasks)} == {"B"}


def test_runnable_now_skips_in_progress() -> None:
    """In Progress is not runnable — it's already in flight."""
    doc = _yaml(
        "  - key: A\n    summary: x\n    description: y\n    type: Task\n"
        "    labels: [size:S]\n    status: In Progress\n"
    )
    tasks = plan.load_tasks(doc)
    assert plan.runnable_now(tasks) == []


# --- wave planning ----------------------------------------------------------

def test_plan_waves_orders_by_dependency() -> None:
    doc = _yaml(
        "  - key: A\n    summary: x\n    description: y\n    type: Task\n"
        "    labels: [size:S]\n"
        "  - key: B\n    summary: x\n    description: y\n    type: Task\n"
        "    labels: [size:S]\n"
        "  - key: C\n    summary: x\n    description: y\n    type: Task\n"
        "    labels: [size:S]\n    blockedBy: [A]\n"
        "  - key: D\n    summary: x\n    description: y\n    type: Task\n"
        "    labels: [size:S]\n    blockedBy: [A, B]\n"
    )
    tasks = plan.load_tasks(doc)
    waves = plan.plan_waves(tasks)
    assert [sorted(t.key for t in w.tasks) for w in waves] == [
        ["A", "B"],
        ["C", "D"],
    ]


def test_plan_waves_handles_blocked_root() -> None:
    """A task with status Blocked never lets its dependents reach a wave."""
    doc = _yaml(
        "  - key: A\n    summary: x\n    description: y\n    type: Task\n"
        "    labels: [size:S]\n    status: Blocked\n"
        "  - key: B\n    summary: x\n    description: y\n    type: Task\n"
        "    labels: [size:S]\n    blockedBy: [A]\n"
    )
    tasks = plan.load_tasks(doc)
    waves = plan.plan_waves(tasks)
    assert waves == []
    assert {t.key for t in plan.unreachable(tasks, waves)} == {"B"}


def test_parallelism_estimate() -> None:
    doc = _yaml(
        "  - key: A\n    summary: x\n    description: y\n    type: Task\n"
        "    labels: [size:S]\n"
        "  - key: B\n    summary: x\n    description: y\n    type: Task\n"
        "    labels: [size:S]\n"
        "  - key: C\n    summary: x\n    description: y\n    type: Task\n"
        "    labels: [size:S]\n"
    )
    tasks = plan.load_tasks(doc)
    waves = plan.plan_waves(tasks)
    assert plan.parallelism_estimate(waves) == 3


# --- filtering --------------------------------------------------------------

def test_parse_label_filter_basic() -> None:
    assert plan.parse_label_filter("size:M,area:schema") == [
        ("size", "M"),
        ("area", "schema"),
    ]


def test_parse_label_filter_rejects_bad_clause() -> None:
    with pytest.raises(plan.ValidationError, match="prefix:value"):
        plan.parse_label_filter("size_M")


def test_filter_tasks_by_label() -> None:
    doc = _yaml(
        "  - key: A\n    summary: x\n    description: y\n    type: Task\n"
        "    labels: [size:S, area:schema]\n"
        "  - key: B\n    summary: x\n    description: y\n    type: Task\n"
        "    labels: [size:M, area:rpc]\n"
    )
    tasks = plan.load_tasks(doc)
    filtered = plan.filter_tasks(tasks, [("area", "schema")])
    assert [t.key for t in filtered] == ["A"]


def test_filter_tasks_by_only() -> None:
    doc = _yaml(
        "  - key: A\n    summary: x\n    description: y\n    type: Task\n"
        "    labels: [size:S]\n"
        "  - key: B\n    summary: x\n    description: y\n    type: Task\n"
        "    labels: [size:M]\n"
    )
    tasks = plan.load_tasks(doc)
    filtered = plan.filter_tasks(tasks, None, only_keys=["B"])
    assert [t.key for t in filtered] == ["B"]
