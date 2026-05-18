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

    roles = tmp_path / ".claude" / "roles"
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
