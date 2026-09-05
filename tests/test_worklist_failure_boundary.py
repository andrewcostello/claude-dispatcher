"""Partial worklist recovery is reporting, never dispatch authority."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import threading

import pytest

from claude_dispatcher import orchestrator as orch
from claude_dispatcher import plan as plan_mod
from claude_dispatcher import yaml_io


def _row(key: str, status: str = "To Do") -> dict:
    return {
        "key": key, "summary": key, "description": "d", "type": "Task",
        "labels": ["size:S"], "status": status,
    }


def _cfg(tmp_path: Path, rows: list[dict]) -> orch.RunConfig:
    path = tmp_path / "tasks.yaml"
    yaml_io.dump({"tasks": rows}, path)
    return orch.RunConfig(
        tasks_path=path, runs_dir=tmp_path / "runs", run_id="boundary",
        mode="unattended", max_parallel=1, max_iterations=1,
        reviewer_count=None, skip_design=False, skip_security_linter=False,
        financial_paths="", claude_bin="claude", worktree_base=None,
        label_filter=plan_mod.parse_label_filter(None), only_keys=None,
    )


def _break_row(cfg: orch.RunConfig, key: str) -> None:
    with yaml_io.FileLock(cfg.tasks_path):
        doc = yaml_io.load(cfg.tasks_path)
        row = next(row for row in doc["tasks"] if row["key"] == key)
        row.update(agent="claude", model="grok-4.6")
        yaml_io.dump(doc, cfg.tasks_path)


def _loop(cfg, tmp_path, monkeypatch, worker):
    cfg.runs_dir.mkdir(exist_ok=True)
    events = []
    monkeypatch.setattr(orch, "_run_task", worker)
    monkeypatch.setattr(orch, "_heartbeat_loop", lambda *args: None)
    monkeypatch.setattr(
        orch, "_emit_event",
        lambda _cfg, kind, payload, **kwargs: events.append((kind.value, payload)),
    )
    rc = orch._run_loop(cfg, cfg.runs_dir, tmp_path / "run.log", tmp_path)
    return rc, events


def test_real_loader_stops_new_dispatch_after_a_worker_corrupts_a_row(
    tmp_path, monkeypatch,
):
    cfg = _cfg(tmp_path, [_row("A"), _row("B")])
    started = []

    def worker(snap, *_args):
        started.append(snap.key)
        with yaml_io.FileLock(cfg.tasks_path):
            doc = yaml_io.load(cfg.tasks_path)
            row = next(row for row in doc["tasks"] if row["key"] == snap.key)
            row["status"] = "Done"
            yaml_io.dump(doc, cfg.tasks_path)
        if snap.key == "A":
            _break_row(cfg, "A")
        return "Done"

    # Use the real loader, lock, parser and executor; the worker is scripted.
    _loop(cfg, tmp_path, monkeypatch, worker)
    assert started == ["A"], "a salvageable B is not permission to dispatch B"


def test_invalid_final_worklist_cannot_report_success(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, [_row("A", "Done"), _row("B", "Done")])
    _break_row(cfg, "B")
    rc, events = _loop(cfg, tmp_path, monkeypatch, lambda *args: "Done")
    assert rc == 1
    assert events[-1][0] == "run_complete"
    assert events[-1][1]["done"] == 1
    assert events[-1][1]["worklist_invalid"] is True


def test_dependency_resolution_never_uses_partial_rows(tmp_path):
    dependency = _row("SEAL", "Done")
    dependency["branch"] = "feat/seal"
    cfg = _cfg(tmp_path, [dependency, _row("OTHER")])
    _break_row(cfg, "OTHER")
    with pytest.raises(plan_mod.ValidationError):
        orch._resolve_dependency_branches(cfg, ["SEAL"])


@pytest.mark.parametrize("text", ["scalar\n", "[one, two]\n", "tasks: 42\n"])
def test_malformed_shape_is_reported_without_a_rollup_crash(
    tmp_path, monkeypatch, text,
):
    cfg = _cfg(tmp_path, [])
    cfg.tasks_path.write_text(text)
    rc, events = _loop(cfg, tmp_path, monkeypatch, lambda *args: "Done")
    assert rc == 1
    assert events[-1][0] == "run_complete"
    assert events[-1][1]["worklist_invalid"] is True


@pytest.mark.parametrize("text", [
    "tasks: [unclosed\n", "", "null\n", "tasks: [42]\n",
    "tasks: {}\n", "tasks: ''\n",
])
def test_unreadable_worklist_finishes_held(tmp_path, monkeypatch, text):
    cfg = _cfg(tmp_path, [])
    cfg.tasks_path.write_text(text)
    rc, events = _loop(cfg, tmp_path, monkeypatch, lambda *args: "Done")
    assert rc == 1
    assert events[-1] == ("run_complete", {
        "done": 0, "blocked": 0, "escalated": 0, "blocked_rollup": [],
        "worklist_invalid": True,
    })


def test_missing_worklist_finishes_held(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, [])
    cfg.tasks_path.unlink()
    rc, events = _loop(cfg, tmp_path, monkeypatch, lambda *args: "Done")
    assert rc == 1
    assert events[-1][1]["worklist_invalid"] is True


@pytest.mark.parametrize("tasks", [None, [], ()])
def test_supported_empty_worklists_stay_empty(tasks):
    assert plan_mod.load_tasks({"tasks": tasks}) == []


@pytest.mark.parametrize("tasks", [{}, "", 42, False, set()])
def test_non_sequence_task_collections_are_refused(tasks):
    with pytest.raises(plan_mod.ValidationError, match="sequence"):
        plan_mod.load_tasks({"tasks": tasks})


@pytest.mark.parametrize("status", ["Done", "Awaiting Review", "Merged"])
def test_healthy_real_worklist_retains_success(tmp_path, monkeypatch, status):
    cfg = _cfg(tmp_path, [_row("A", status)])
    cfg.integration = "pr" if status != "Done" else "branch"
    rc, events = _loop(cfg, tmp_path, monkeypatch, lambda *args: "Done")
    assert rc == 0
    assert events[-1][1]["done"] == 1
    assert "worklist_invalid" not in events[-1][1]
    assert not cfg._worklist_invalid.is_set()


@pytest.mark.parametrize("damaged", [True, False])
def test_hold_stops_feature_review_and_merge_passes(
    tmp_path, monkeypatch, damaged,
):
    cfg = _cfg(tmp_path, [_row("A", "Done")])
    cfg.integration = "pr"
    cfg.feature_branch = "feature/test"
    cfg.feature_review = True
    if damaged:
        _break_row(cfg, "A")
    effects = []
    monkeypatch.setattr(
        orch.merge_mod, "merge_pass", lambda *args, **kw: effects.append("merge"),
    )
    monkeypatch.setattr(
        orch, "_feature_review_round",
        lambda *args: effects.append("review") or False,
    )
    rc, _events = _loop(cfg, tmp_path, monkeypatch, lambda *args: "Done")
    assert effects == ([] if damaged else ["merge", "review"])
    assert rc == int(damaged)


def test_in_flight_work_finishes_but_repair_does_not_release_the_hold(
    tmp_path, monkeypatch,
):
    cfg = _cfg(tmp_path, [_row("A"), _row("B"), _row("C")])
    cfg.max_parallel = 2
    b_started = threading.Event()
    failure_observed = threading.Event()
    finished = []

    def worker(snap, *_args):
        if snap.key == "A":
            assert b_started.wait(2), "B never started"
            _break_row(cfg, "A")
            with pytest.raises(plan_mod.ValidationError):
                orch._load_tasks_snapshot(cfg)
            failure_observed.set()
        elif snap.key == "B":
            b_started.set()
            assert failure_observed.wait(2), "A never recorded the failure"
        with yaml_io.FileLock(cfg.tasks_path):
            doc = yaml_io.load(cfg.tasks_path)
            for row in doc["tasks"]:
                if row["key"] == "A":
                    row.pop("agent", None)
                    row.pop("model", None)
                if row["key"] == snap.key:
                    row["status"] = "Done"
            yaml_io.dump(doc, cfg.tasks_path)
        finished.append(snap.key)
        return "Done"

    rc, events = _loop(cfg, tmp_path, monkeypatch, worker)
    assert sorted(finished) == ["A", "B"]
    assert {t.key: t.status for t in orch._load_tasks_snapshot_strict(cfg)} == {
        "A": "Done", "B": "Done", "C": "To Do",
    }
    assert rc == 1
    assert events[-1][1]["worklist_invalid"] is True
    assert "worker_exception" not in (tmp_path / "run.log").read_text()
    # Holds are invocation-local, not a new persistent source of task state.
    assert not replace(cfg)._worklist_invalid.is_set()


def test_invalid_worklist_notification_is_not_a_green_completion(
    tmp_path, monkeypatch,
):
    cfg = _cfg(tmp_path, [_row("A", "Done"), _row("B", "Done")])
    _break_row(cfg, "B")
    notifications = []
    monkeypatch.setattr(
        orch, "_send_notification",
        lambda _cfg, notification, **kw: notifications.append(notification),
    )
    _loop(cfg, tmp_path, monkeypatch, lambda *args: "Done")
    assert len(notifications) == 1
    notification = notifications[0]
    assert "held" in notification.title
    assert "partial" in notification.body
    assert notification.urgency == "high"
    assert "white_check_mark" not in notification.tags


@pytest.mark.parametrize("reader", [
    "_load_tasks_snapshot", "_load_tasks_for_rollup", "_rows_that_still_parse",
])
def test_lock_timeouts_are_never_a_partial_snapshot(tmp_path, monkeypatch, reader):
    cfg = _cfg(tmp_path, [])

    def locked(*args, **kwargs):
        raise yaml_io.LockTimeout("another writer owns the lock")

    monkeypatch.setattr(yaml_io, "FileLock", locked)
    with pytest.raises(yaml_io.LockTimeout):
        getattr(orch, reader)(cfg)
    assert not cfg._worklist_invalid.is_set()


def test_rollup_second_read_also_propagates_lock_timeout(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, [_row("A")])
    _break_row(cfg, "A")
    actual_lock = yaml_io.FileLock
    calls = []

    def lock(*args, **kwargs):
        calls.append(True)
        if len(calls) == 2:
            raise yaml_io.LockTimeout("writer acquired the salvage lock")
        return actual_lock(*args, **kwargs)

    monkeypatch.setattr(yaml_io, "FileLock", lock)
    with pytest.raises(yaml_io.LockTimeout):
        orch._load_tasks_for_rollup(cfg)
    assert len(calls) == 2
    assert cfg._worklist_invalid.is_set()


def test_a_failure_first_seen_at_rollup_still_prevents_success(
    tmp_path, monkeypatch,
):
    cfg = _cfg(tmp_path, [_row("A", "Done"), _row("B", "Done")])
    drain = orch._dispatch_drain

    def finish_then_damage(*args, **kwargs):
        result = drain(*args, **kwargs)
        _break_row(cfg, "B")
        return result

    monkeypatch.setattr(orch, "_dispatch_drain", finish_then_damage)
    rc, events = _loop(cfg, tmp_path, monkeypatch, lambda *args: "Done")
    assert rc == 1
    assert events[-1][1]["worklist_invalid"] is True
    assert events[-1][1]["done"] == 1


@pytest.mark.parametrize("damaged", [True, False])
def test_declared_hole_gate_never_turns_corruption_into_no_check(
    tmp_path, damaged,
):
    scaffold = _row("S")
    scaffold.update(role="scaffold", declares={"holes": ["code.py::decide"]})
    cfg = _cfg(tmp_path, [scaffold, _row("OTHER")])
    snap = orch.TaskSnapshot(
        key="S", summary="S", description="d", type="Task", labels=["size:S"],
        role_specs=[orch.role_protocol_mod.parse_task_role_spec(
            scaffold, task_key="S",
        )],
    )
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    (candidate / "code.py").write_text("def decide():\n    return 1\n")
    wt = orch.wt_mod.Worktree(path=candidate, branch="feat/test")
    if damaged:
        _break_row(cfg, "S")
        with pytest.raises(plan_mod.ValidationError):
            orch._check_declared_holes(cfg, snap, wt, tmp_path / "gate.log")
    else:
        reason = orch._check_declared_holes(cfg, snap, wt, tmp_path / "gate.log")
        assert reason is not None and reason.startswith("declared_holes_scaffold:")
