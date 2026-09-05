"""Acceptance commands come from the base captured before implementation."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from claude_dispatcher import orchestrator as orch, worktree
from test_verification_reentry import _commit, _events, _git, _run_retry, repo
from test_orchestrator_panel import _CRITICAL_TASK_YAML, _seed_yaml


@pytest.mark.parametrize("replacement", [None, "test: 'true'\n", "e2e: unused\n"])
@pytest.mark.parametrize("advance_base", [False, True])
def test_worker_cannot_choose_or_remove_its_mechanical_command(
    repo, monkeypatch, replacement, advance_base,
):
    policy_bases = []

    def change_policy(root, count, env):
        if count != 1:
            return
        policy_bases.append(_git(root, "rev-parse", "main"))
        path = root / ".dispatcher.yaml"
        if replacement is None:
            path.unlink()
        else:
            path.write_text(replacement, encoding="utf-8")
        _commit(root, "worker changes its verification configuration")
        if advance_base:
            _git(root, "update-ref", "refs/heads/main", _git(root, "rev-parse", "HEAD"))

    rc, row, stages, spawns = _run_retry(
        repo, monkeypatch, origin="mechanical", regression=True,
        on_spawn=change_policy,
        task_overrides={"owns": [
            "correctness.txt", "implemented-*.txt", "correction.txt", ".dispatcher.yaml",
        ]},
    )
    assert rc != 0 and row["status"] == "Blocked", row
    assert row["mechanical_verification"] == "failed", row
    assert len(spawns) == 2
    events = [e.payload for e in _events(repo) if e.event_type == "verification_mechanical"]
    assert len(events) == 2
    assert all(p["outcome"] == "failed" for p in events)
    assert all(p["policy_base_sha"] == policy_bases[0] for p in events)


def _seal_case(repo, monkeypatch, replacement):
    (repo / ".dispatcher.yaml").write_text("test: trusted-command\n", encoding="utf-8")
    _seed_yaml(repo, _CRITICAL_TASK_YAML)
    base = _git(repo, "rev-parse", "HEAD")
    if replacement is None:
        (repo / ".dispatcher.yaml").unlink()
    else:
        (repo / ".dispatcher.yaml").write_text(replacement, encoding="utf-8")
    _commit(repo, "candidate configuration")
    calls, events = [], []

    def invert(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(outcome="passed", detail="scripted inversion")

    monkeypatch.setattr(orch.sv_mod, "run_seal_inversion", invert)
    monkeypatch.setattr(orch, "_emit_event", lambda cfg, kind, payload, **kw: events.append(payload))
    cfg = SimpleNamespace(verify_test_timeout_seconds=10)
    snap = orch.TaskSnapshot(key="FIX-1", summary="fix", description="fix", type="Task", labels=[])
    wt = worktree.Worktree(path=repo, branch="main")
    return base, cfg, snap, wt, calls, events


@pytest.mark.parametrize("replacement", [None, "test: 'true'\n", "test: [invalid\n"])
def test_seal_uses_the_same_pinned_policy_source(repo, monkeypatch, replacement):
    base, cfg, snap, wt, calls, events = _seal_case(repo, monkeypatch, replacement)
    outcome, detail = orch._verify_seal(cfg, snap, wt, base, repo.parent / "seal.log")
    assert outcome == "passed", detail
    assert len(calls) == 1
    assert calls[0]["test_command"] == "trusted-command"
    assert events[0]["policy_base_sha"] == base


def test_unavailable_policy_base_cannot_fall_back_to_candidate(repo, monkeypatch):
    base, cfg, snap, wt, calls, events = _seal_case(repo, monkeypatch, "test: 'true'\n")
    outcome, detail = orch._verify_seal(cfg, snap, wt, "f" * 40, repo.parent / "seal.log")
    assert outcome == "error" and detail
    assert calls == []
    assert events[0]["outcome"] == "error"


def test_unpinnable_policy_base_stops_before_worker_spawn(repo, monkeypatch):
    original = orch._branch_sha

    def no_base(root, branch, log_path, task_key):
        if branch == "main":
            return None
        return original(root, branch, log_path, task_key)

    monkeypatch.setattr(orch, "_branch_sha", no_base)
    rc, row, stages, spawns = _run_retry(repo, monkeypatch, origin="none")
    assert rc != 0 and row["status"] == "Blocked", row
    assert "verification_policy_unavailable" in row["blocked_reason"]
    assert spawns == [] and stages == []


def test_cascade_does_not_adopt_a_workers_new_policy(repo, monkeypatch):
    bases = []
    monkeypatch.setattr(orch, "_implementer_cascade", lambda *a, **kw: [
        ("claude", "medium"), ("claude", "high"),
    ])

    def weaken(root, count, env):
        if count not in (1, 3):
            return
        bases.append(_git(root, "rev-parse", "main"))
        (root / ".dispatcher.yaml").write_text("test: 'true'\n", encoding="utf-8")
        _commit(root, "weaken candidate policy")
        _git(root, "update-ref", "refs/heads/main", _git(root, "rev-parse", "HEAD"))

    rc, row, stages, spawns = _run_retry(
        repo, monkeypatch, origin="mechanical", regression=True, on_spawn=weaken,
    )
    assert rc != 0 and row["status"] == "Blocked", row
    assert row["mechanical_verification"] == "failed"
    assert len(spawns) == 4
    events = [e.payload for e in _events(repo) if e.event_type == "verification_mechanical"]
    assert len(events) == 4
    assert all(p["policy_base_sha"] == bases[0] for p in events)
