"""Epic capstone synthesis: trigger rules, idempotence, drain ordering."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from claude_dispatcher import orchestrator
from claude_dispatcher import yaml_io

from test_mechanical_verify import _args, _events, _patch_spawn, repo  # noqa: F401


def _cfg(tasks_path: Path, base: str = "main") -> SimpleNamespace:
    return SimpleNamespace(
        base_branch=base, tasks_path=tasks_path, lock_timeout_seconds=10,
    )


def _keys(tasks_path: Path) -> list[str]:
    return [t["key"] for t in yaml_io.load(tasks_path)["tasks"]]


def test_capstone_appended_for_flagged_yaml(repo: Path) -> None:
    tasks_path = repo / "tasks.yaml"
    doc = yaml_io.load(tasks_path)
    doc["capstone"] = True
    yaml_io.dump(doc, tasks_path)

    out = orchestrator._maybe_append_capstone(_cfg(tasks_path), doc)

    keys = _keys(tasks_path)
    assert orchestrator.CAPSTONE_KEY in keys
    row = next(t for t in yaml_io.load(tasks_path)["tasks"]
               if t["key"] == orchestrator.CAPSTONE_KEY)
    assert sorted(row["blockedBy"]) == ["SMOKE-A", "SMOKE-B", "SMOKE-C"]
    assert "seam" in row["summary"]
    # The returned doc reflects the file.
    assert orchestrator.CAPSTONE_KEY in [t["key"] for t in out["tasks"]]


def test_capstone_appended_for_epic_base_branch(repo: Path) -> None:
    tasks_path = repo / "tasks.yaml"
    doc = yaml_io.load(tasks_path)
    orchestrator._maybe_append_capstone(
        _cfg(tasks_path, base="epic/bay-session-v2"), doc)
    assert orchestrator.CAPSTONE_KEY in _keys(tasks_path)


def test_capstone_not_appended_for_plain_run(repo: Path) -> None:
    tasks_path = repo / "tasks.yaml"
    doc = yaml_io.load(tasks_path)
    orchestrator._maybe_append_capstone(_cfg(tasks_path), doc)
    assert orchestrator.CAPSTONE_KEY not in _keys(tasks_path)


def test_capstone_idempotent(repo: Path) -> None:
    tasks_path = repo / "tasks.yaml"
    doc = yaml_io.load(tasks_path)
    doc["capstone"] = True
    yaml_io.dump(doc, tasks_path)
    doc = orchestrator._maybe_append_capstone(_cfg(tasks_path), doc)
    doc = orchestrator._maybe_append_capstone(_cfg(tasks_path), doc)
    assert _keys(tasks_path).count(orchestrator.CAPSTONE_KEY) == 1


def test_capstone_runs_last_in_drain(repo: Path, monkeypatch) -> None:
    """Full live-path run with capstone: the synthesized task dispatches
    only after every other task is Done, and lands Done itself."""
    tasks_path = repo / "tasks.yaml"
    doc = yaml_io.load(tasks_path)
    doc["capstone"] = True
    yaml_io.dump(doc, tasks_path)

    monkeypatch.setenv("FAKE_CLAUDE_SCENARIO", "done")
    _patch_spawn(monkeypatch)

    rc = orchestrator.execute(_args(repo, only="SMOKE-A,SMOKE-B,SMOKE-C,"
                                               + orchestrator.CAPSTONE_KEY))
    assert rc == 0

    started = [e.task_key for e in _events(repo)
               if e.event_type == "task_started"]
    assert started[-1] == orchestrator.CAPSTONE_KEY
    assert set(started[:-1]) == {"SMOKE-A", "SMOKE-B", "SMOKE-C"}

    rows = {t["key"]: t for t in yaml_io.load(tasks_path)["tasks"]}
    assert rows[orchestrator.CAPSTONE_KEY]["status"] == "Done"
