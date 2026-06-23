"""Live-spawn smoke tests using a fake `claude` binary.

The fake binary (tests/fixtures/fake_claude.py) writes a synthetic summary
file matching what the Tasker would write. The orchestrator end-to-end
exercises:
  - worktree creation
  - env-var handoff
  - prompt rendering
  - summary parsing
  - YAML write-back

A real git repository is required for `git worktree add`. The test fixtures
build one in tmp_path on demand.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from claude_dispatcher import orchestrator
from claude_dispatcher.cli import build_parser


FAKE_CLAUDE = Path(__file__).parent / "fixtures" / "fake_claude.py"


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """Build a minimal git repo with a tasks YAML and a .claude/workflow/roles/tasker.md stub.

    The Tasker stub doesn't matter (the fake claude binary doesn't read it),
    but we need it on disk so the orchestrator's later assertions don't trip.
    """
    subprocess.run(
        ["git", "init", "-q", "-b", "main", str(tmp_path)],
        check=True, capture_output=True,
    )
    # git wants an identity to make commits
    subprocess.run(["git", "config", "user.email", "test@test"],
                   cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"],
                   cwd=tmp_path, check=True, capture_output=True)

    # Tracked at the canonical path so the run-start preflight's role-file
    # check passes without needing a probe worktree.
    roles = tmp_path / ".claude" / "workflow" / "roles"
    roles.mkdir(parents=True)
    (roles / "tasker.md").write_text("# Tasker stub for testing", encoding="utf-8")

    fixture = Path(__file__).parent / "fixtures" / "three_task.yaml"
    yaml_dst = tmp_path / "tasks.yaml"
    yaml_dst.write_text(fixture.read_text(encoding="utf-8"), encoding="utf-8")

    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"],
                   cwd=tmp_path, check=True, capture_output=True)
    return tmp_path


def _build_args(repo: Path, **overrides) -> Any:
    parser = build_parser()
    runs_dir = str(repo / "_runs")
    argv = [
        "run", str(repo / "tasks.yaml"),
        "--mode", "unattended",
        "--max-parallel", "1",
        "--max-iterations", "2",
        "--run-id", "smoke-test-run",
        "--runs-dir", runs_dir,
        "--worktree-base", str(repo.parent / "worktrees-test"),
        "--claude-bin", f"{sys.executable}",
        # Permission-bypass flag so the run-start preflight passes; the smoke
        # harness runs WITH preflight enabled (more realistic than skipping).
        "--claude-extra-args=--permission-mode bypassPermissions",
    ]
    for k, v in overrides.items():
        if v is None:
            continue
        argv += [f"--{k.replace('_', '-')}", str(v)]
    args = parser.parse_args(argv)
    # The fake binary is a python script; spoof claude_bin to invoke it via python.
    args.claude_bin_path = str(FAKE_CLAUDE)
    return args


def _patched_spawn(monkeypatch):
    """Replace spawn_claude so it invokes the fake_claude script with python."""
    from claude_dispatcher import spawn as spawn_mod

    real = spawn_mod.spawn_claude

    def fake(claude_bin: str, cwd: Path, env: dict, prompt: str,
             extra_args=None, timeout_seconds: int = 3600):
        # Always invoke the fake script via the test's python interpreter, regardless
        # of what --claude-bin says. This keeps the test hermetic.
        proc = subprocess.run(
            [sys.executable, str(FAKE_CLAUDE)],
            input=prompt,
            capture_output=True,
            text=True,
            cwd=str(cwd),
            env=env,
            timeout=timeout_seconds,
        )
        return spawn_mod.SpawnResult(
            exit_code=proc.returncode,
            summary_path=Path(env["SUMMARY_PATH"]),
            stdout=proc.stdout,
            stderr=proc.stderr,
        )

    monkeypatch.setattr(spawn_mod, "spawn_claude", fake)


def test_smoke_three_tasks_end_to_end(repo: Path, monkeypatch) -> None:
    """All three tasks dispatch, complete Done, YAML updated, run.log present."""
    _patched_spawn(monkeypatch)
    args = _build_args(repo)
    rc = orchestrator.execute(args)
    assert rc == 0, "expected clean exit (all Done)"

    # YAML now has all three tasks Done with completed_at + iteration_count + pr_url
    from claude_dispatcher import yaml_io
    doc = yaml_io.load(repo / "tasks.yaml")
    statuses = {t["key"]: t.get("status") for t in doc["tasks"]}
    assert statuses == {"SMOKE-A": "Done", "SMOKE-B": "Done", "SMOKE-C": "Done"}

    for t in doc["tasks"]:
        assert t.get("completed_at"), f"{t['key']} missing completed_at"
        assert t.get("iteration_count") == 1
        assert t.get("dispatcher_run_id") == "smoke-test-run"
        assert "pr_url" in t

    # run.log present and non-empty
    log = (repo / "_runs" / "smoke-test-run" / "run.log").read_text(encoding="utf-8")
    assert "dispatch SMOKE-A" in log
    assert "dispatch SMOKE-B" in log
    assert "dispatch SMOKE-C" in log
    assert "start run smoke-test-run" in log


def test_smoke_respects_blockedby_ordering(repo: Path, monkeypatch) -> None:
    """SMOKE-C must not start until SMOKE-A is Done.

    The fake binary doesn't enforce ordering itself; the orchestrator's
    runnable_now() loop does. We verify by checking the run.log line order.
    """
    _patched_spawn(monkeypatch)
    args = _build_args(repo)
    orchestrator.execute(args)
    log = (repo / "_runs" / "smoke-test-run" / "run.log").read_text(encoding="utf-8")
    # SMOKE-A must appear before SMOKE-C
    a_idx = log.index("dispatch SMOKE-A")
    c_idx = log.index("dispatch SMOKE-C")
    assert a_idx < c_idx


def test_smoke_unattended_leaves_human_gate_task_blocked(
    repo: Path, monkeypatch
) -> None:
    """When the Tasker writes a Prepared PR, unattended mode leaves it Blocked."""
    monkeypatch.setenv("FAKE_CLAUDE_SCENARIO", "awaiting-human-pr")
    _patched_spawn(monkeypatch)
    args = _build_args(repo, only="SMOKE-A")
    rc = orchestrator.execute(args)
    assert rc == 1, "expected partial-completion exit (task Blocked)"

    from claude_dispatcher import yaml_io
    doc = yaml_io.load(repo / "tasks.yaml")
    smoke_a = next(t for t in doc["tasks"] if t["key"] == "SMOKE-A")
    assert smoke_a["status"] == "Blocked"
    assert smoke_a.get("blocked_reason") == "awaiting human PR approval"
    assert smoke_a.get("prepared_pr_title", "").startswith("feat(test):")
    assert smoke_a.get("prepared_pr_branch") == "feat/SMOKE-A-smoke-test"


def test_smoke_malformed_summary_marks_blocked(repo: Path, monkeypatch) -> None:
    """Fake binary writes invalid Status → orchestrator marks Blocked, run continues."""
    monkeypatch.setenv("FAKE_CLAUDE_SCENARIO", "blocked-malformed")
    _patched_spawn(monkeypatch)
    args = _build_args(repo, only="SMOKE-A,SMOKE-B")
    rc = orchestrator.execute(args)
    assert rc == 1
    from claude_dispatcher import yaml_io
    doc = yaml_io.load(repo / "tasks.yaml")
    for key in ("SMOKE-A", "SMOKE-B"):
        row = next(t for t in doc["tasks"] if t["key"] == key)
        assert row["status"] == "Blocked"
        assert "summary_malformed" in row.get("blocked_reason", "")


# --- cost ceiling (BUDGET-1) -----------------------------------------------


def _patched_spawn_with_cost(monkeypatch, cost_usd: float) -> None:
    """Like _patched_spawn but every spawn reports a fixed cost_usd, so the
    run accumulates spend the budget ceiling can act on."""
    from claude_dispatcher import spawn as spawn_mod

    def fake(claude_bin: str, cwd: Path, env: dict, prompt: str,
             extra_args=None, timeout_seconds: int = 3600):
        proc = subprocess.run(
            [sys.executable, str(FAKE_CLAUDE)],
            input=prompt, capture_output=True, text=True,
            cwd=str(cwd), env=env, timeout=timeout_seconds,
        )
        return spawn_mod.SpawnResult(
            exit_code=proc.returncode,
            summary_path=Path(env["SUMMARY_PATH"]),
            stdout=proc.stdout, stderr=proc.stderr,
            usage=spawn_mod.SpawnUsage(cost_usd=cost_usd),
        )

    monkeypatch.setattr(spawn_mod, "spawn_claude", fake)


def test_budget_ceiling_holds_run_after_first_task(repo: Path, monkeypatch) -> None:
    """A tiny ceiling trips after the first task completes: the run stops
    starting new tasks, exits non-zero, and journals budget_exceeded. The
    remaining tasks are parked (never reach Done)."""
    _patched_spawn_with_cost(monkeypatch, cost_usd=1.0)
    # Ceiling far below one task's cost → trips as soon as the first task's
    # cost lands, regardless of how many spawns (impl + verifier) it took.
    args = _build_args(repo, max_cost_usd=0.01)
    rc = orchestrator.execute(args)
    assert rc == 1, "a budget hold is an incomplete run → non-zero exit"

    from claude_dispatcher import yaml_io
    doc = yaml_io.load(repo / "tasks.yaml")
    done = [t["key"] for t in doc["tasks"] if t.get("status") == "Done"]
    assert len(done) == 1, f"only the first task should land; got {done}"

    log = (repo / "_runs" / "smoke-test-run" / "run.log").read_text(encoding="utf-8")
    assert "BUDGET:" in log and "BUDGET-HELD" in log

    # The hold is journaled (hash-chained) with the spend + ceiling.
    import json
    journal = (repo / "_runs" / "smoke-test-run" / "journal.jsonl").read_text(
        encoding="utf-8")
    events = [json.loads(line) for line in journal.splitlines() if line.strip()]
    budget_evs = [e for e in events if e["event_type"] == "budget_exceeded"]
    assert len(budget_evs) == 1, "exactly one budget_exceeded event (idempotent trip)"
    assert budget_evs[0]["payload"]["ceiling_usd"] == 0.01
    assert budget_evs[0]["payload"]["cost_usd"] >= 1.0


def test_no_ceiling_runs_all_tasks(repo: Path, monkeypatch) -> None:
    """Without --max-cost-usd the run completes normally even with reported
    cost — the gate is off by default (no regression)."""
    _patched_spawn_with_cost(monkeypatch, cost_usd=999.0)
    args = _build_args(repo)  # no max_cost_usd
    rc = orchestrator.execute(args)
    assert rc == 0
    from claude_dispatcher import yaml_io
    doc = yaml_io.load(repo / "tasks.yaml")
    assert all(t.get("status") == "Done" for t in doc["tasks"])


def test_budget_no_false_hold_when_all_work_done(repo: Path, monkeypatch) -> None:
    """A run whose only task pushes cost over the ceiling but leaves no further
    runnable work is COMPLETE, not held — no false BUDGET-HELD, clean exit.
    (Panel HIGH: the gate must fire only when there is work to suppress.)"""
    _patched_spawn_with_cost(monkeypatch, cost_usd=1.0)
    args = _build_args(repo, only="SMOKE-B", max_cost_usd=0.01)  # one independent task
    rc = orchestrator.execute(args)
    assert rc == 0, "all selected work done → clean exit, not a budget hold"
    from claude_dispatcher import yaml_io
    doc = yaml_io.load(repo / "tasks.yaml")
    row = next(t for t in doc["tasks"] if t["key"] == "SMOKE-B")
    assert row["status"] == "Done"
    log = (repo / "_runs" / "smoke-test-run" / "run.log").read_text(encoding="utf-8")
    assert "BUDGET" not in log


def test_budget_counts_cost_of_blocked_task(repo: Path, monkeypatch) -> None:
    """A task that spawns (burning tokens) then blocks still has its cost
    stamped on the row, so it counts toward the ceiling. (Panel HIGH: blocked-
    task spend must not be invisible.)"""
    monkeypatch.setenv("FAKE_CLAUDE_SCENARIO", "blocked-malformed")
    _patched_spawn_with_cost(monkeypatch, cost_usd=1.0)
    args = _build_args(repo, only="SMOKE-A")
    orchestrator.execute(args)
    from claude_dispatcher import yaml_io
    row = next(t for t in yaml_io.load(repo / "tasks.yaml")["tasks"]
               if t["key"] == "SMOKE-A")
    assert row["status"] == "Blocked"
    assert row.get("cost_usd") == 1.0, "blocked task's spend must be recorded"


def test_corrective_spawn_cost_is_accounted(repo: Path, monkeypatch) -> None:
    """A commit-retry corrective spawn's cost is added to the row AND emits a
    task_spawn_finished tagged spawn_kind=commit-retry — so intra-task retry
    spend counts toward the ceiling + report rollup (spawn-complete accounting,
    the panel's gemini 5xHIGH theme)."""
    import json
    monkeypatch.setenv("FAKE_CLAUDE_SCENARIO", "done-commit-retry")
    _patched_spawn_with_cost(monkeypatch, cost_usd=1.0)
    # Isolated worktree base: done-commit-retry's first-skip/second-commit hinges
    # on a fresh worktree sentinel, so a worktree reused from another test would
    # commit immediately and skip the retry. (worktree_base override wins — it's
    # appended after the helper's default.)
    orchestrator.execute(_build_args(
        repo, only="SMOKE-A", worktree_base=str(repo / "wt_iso")))

    from claude_dispatcher import yaml_io
    row = next(t for t in yaml_io.load(repo / "tasks.yaml")["tasks"]
               if t["key"] == "SMOKE-A")
    # implementer (1.0) + commit-retry (1.0) are both accounted, at minimum.
    assert row.get("cost_usd", 0) >= 2.0

    journal = (repo / "_runs" / "smoke-test-run" / "journal.jsonl").read_text(
        encoding="utf-8")
    kinds = [
        json.loads(line)["payload"].get("spawn_kind")
        for line in journal.splitlines() if line.strip()
        and json.loads(line)["event_type"] == "task_spawn_finished"
    ]
    assert "implementer" in kinds and "commit-retry" in kinds


def test_budget_held_run_resumes_under_raised_ceiling(repo: Path, monkeypatch) -> None:
    """The documented recovery path works end-to-end: a budget-held run resumes
    under a raised --max-cost-usd and completes the parked tasks. (Panel HIGH:
    resume must be able to carry a raised ceiling.)"""
    from claude_dispatcher import resume as resume_cmd, yaml_io

    _patched_spawn_with_cost(monkeypatch, cost_usd=1.0)
    # First run: tiny ceiling holds after the first task; the rest park To Do.
    rc = orchestrator.execute(_build_args(repo, max_cost_usd=0.01))
    assert rc == 1
    doc = yaml_io.load(repo / "tasks.yaml")
    done_first = [t["key"] for t in doc["tasks"] if t.get("status") == "Done"]
    assert len(done_first) == 1, f"expected a hold after one task; got {done_first}"

    # Resume with a raised ceiling: already-spent cost is now under it, so the
    # parked tasks dispatch and complete.
    resume_args = build_parser().parse_args([
        "resume", "smoke-test-run",
        "--runs-dir", str(repo / "_runs"),
        "--max-cost-usd", "9999",
        "--force",  # the just-written journal looks "active"
    ])
    rc2 = resume_cmd.execute(resume_args)
    assert rc2 == 0, "raised ceiling lets the resumed run finish"
    doc = yaml_io.load(repo / "tasks.yaml")
    assert all(t.get("status") == "Done" for t in doc["tasks"]), \
        "all parked tasks complete after the ceiling is raised"


def test_budget_resume_without_enough_ceiling_fails_fast(repo: Path, monkeypatch) -> None:
    """Resuming a budget-held run without a ceiling above what's already spent
    refuses fast (exit 2) instead of spinning up the loop to re-hold. (codex
    HIGH: the hold must not just re-emit and re-hold on resume.)"""
    from claude_dispatcher import resume as resume_cmd, yaml_io

    _patched_spawn_with_cost(monkeypatch, cost_usd=1.0)
    assert orchestrator.execute(_build_args(repo, max_cost_usd=0.01)) == 1
    done_before = [t["key"] for t in yaml_io.load(repo / "tasks.yaml")["tasks"]
                   if t.get("status") == "Done"]

    # Resume with a ceiling still below the ~1.0 already spent → fail fast.
    resume_args = build_parser().parse_args([
        "resume", "smoke-test-run", "--runs-dir", str(repo / "_runs"),
        "--max-cost-usd", "0.50", "--force",
    ])
    rc = resume_cmd.execute(resume_args)
    assert rc == 2, "insufficient ceiling on resume should refuse, not re-hold"
    # No further work happened.
    done_after = [t["key"] for t in yaml_io.load(repo / "tasks.yaml")["tasks"]
                  if t.get("status") == "Done"]
    assert done_after == done_before


# --- configurable timeouts (DISP-4) ----------------------------------------


def test_config_timeout_defaults_unchanged() -> None:
    """Without the flags, defaults stay 30s lock / 4h spawn."""
    parser = build_parser()
    args = parser.parse_args(["run", "tasks.yaml"])
    assert args.lock_timeout_seconds == 30.0
    assert args.task_timeout_seconds == 60 * 60 * 4

    cfg = orchestrator._build_config(args)
    assert cfg.lock_timeout_seconds == 30.0
    assert cfg.task_timeout_seconds == 60 * 60 * 4


def test_task_timeout_flows_to_spawn(repo: Path, monkeypatch) -> None:
    """--task-timeout-seconds reaches the spawn_claude call site."""
    from claude_dispatcher import spawn as spawn_mod

    captured: dict[str, int] = {}

    def recording_spawn(claude_bin: str, cwd: Path, env: dict, prompt: str,
                        extra_args=None, timeout_seconds: int = 3600):
        captured["timeout_seconds"] = timeout_seconds
        proc = subprocess.run(
            [sys.executable, str(FAKE_CLAUDE)],
            input=prompt, capture_output=True, text=True,
            cwd=str(cwd), env=env, timeout=timeout_seconds,
        )
        return spawn_mod.SpawnResult(
            exit_code=proc.returncode,
            summary_path=Path(env["SUMMARY_PATH"]),
            stdout=proc.stdout, stderr=proc.stderr,
        )

    monkeypatch.setattr(spawn_mod, "spawn_claude", recording_spawn)
    args = _build_args(repo, only="SMOKE-A", task_timeout_seconds=123)
    orchestrator.execute(args)
    assert captured["timeout_seconds"] == 123


def test_lock_timeout_flows_to_filelock(repo: Path) -> None:
    """--lock-timeout-seconds reaches the FileLock and fails fast when held."""
    import time

    from claude_dispatcher import yaml_io

    args = _build_args(repo, only="SMOKE-A", lock_timeout_seconds=0.3)
    cfg = orchestrator._build_config(args)
    assert cfg.lock_timeout_seconds == 0.3

    # Hold the lock so the snapshot load must wait, then time out.
    lock_path = Path(str(cfg.tasks_path) + ".lock")
    lock_path.write_text("99999\n", encoding="utf-8")
    try:
        start = time.monotonic()
        with pytest.raises(yaml_io.LockTimeout):
            orchestrator._load_tasks_snapshot(cfg)
        elapsed = time.monotonic() - start
    finally:
        lock_path.unlink()
    # Proves the 0.3s budget was honored, not the 30s default.
    assert elapsed < 5.0
