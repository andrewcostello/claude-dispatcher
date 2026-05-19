"""Tests for the dispatcher's commit-retry behavior.

When the Tasker reports Done but produces no commits on the branch, the
dispatcher re-prompts the Tasker once with a commit-only instruction. If
the retry produces commits, the task lands Done normally. If the retry
also produces no commits, only THEN the task is Blocked — distinguishing
"forgot to commit" (recoverable) from "completely failed" (Blocker).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from claude_dispatcher import orchestrator, spawn as spawn_mod, yaml_io
from claude_dispatcher.cli import build_parser


FAKE_CLAUDE = Path(__file__).parent / "fixtures" / "fake_claude.py"


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    # Put repo and worktree-base both UNDER tmp_path so they're fully
    # isolated per test (tmp_path.parent is shared, repo at tmp_path itself
    # leaks worktree state across tests since --worktree-base = repo.parent
    # is shared too).
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo_dir)],
                   check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test"], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo_dir, check=True, capture_output=True)
    roles = repo_dir / ".claude" / "workflow" / "roles"
    roles.mkdir(parents=True)
    (roles / "tasker.md").write_text("stub", encoding="utf-8")
    src = Path(__file__).parent / "fixtures" / "three_task.yaml"
    (repo_dir / "tasks.yaml").write_text(src.read_text(), encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=repo_dir, check=True, capture_output=True)
    return repo_dir


def _args(repo: Path, **overrides):
    parser = build_parser()
    # worktree-base lives inside tmp_path (= repo.parent), unique per test
    argv = [
        "run", str(repo / "tasks.yaml"),
        "--mode", "unattended", "--max-parallel", "1",
        "--run-id", "retry-test",
        "--runs-dir", str(repo / "_runs"),
        "--worktree-base", str(repo.parent / "wt"),
        "--claude-bin", sys.executable,
        "--only", "SMOKE-A",
    ]
    for k, v in overrides.items():
        argv += [f"--{k.replace('_', '-')}", str(v)]
    return parser.parse_args(argv)


def _patch_spawn(monkeypatch):
    def fake(claude_bin, cwd, env, prompt, extra_args=None, timeout_seconds=3600):
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
    monkeypatch.setattr(spawn_mod, "spawn_claude", fake)


def test_done_with_commit_lands_normally(repo: Path, monkeypatch) -> None:
    """Sanity: the normal `done` scenario commits and lands Done."""
    _patch_spawn(monkeypatch)
    rc = orchestrator.execute(_args(repo))
    assert rc == 0
    doc = yaml_io.load(repo / "tasks.yaml")
    row = next(t for t in doc["tasks"] if t["key"] == "SMOKE-A")
    assert row["status"] == "Done"


def test_done_no_commit_retries_and_then_blocks(repo: Path, monkeypatch) -> None:
    """When the Tasker reports Done but never commits even after retry,
    the dispatcher Blocks with 'no commits produced after commit-retry'.
    """
    monkeypatch.setenv("FAKE_CLAUDE_SCENARIO", "done-no-commit")
    _patch_spawn(monkeypatch)
    rc = orchestrator.execute(_args(repo))
    assert rc == 1  # partial completion (this task Blocked)
    doc = yaml_io.load(repo / "tasks.yaml")
    row = next(t for t in doc["tasks"] if t["key"] == "SMOKE-A")
    assert row["status"] == "Blocked"
    assert "no commits produced after commit-retry" in row.get("blocked_reason", "")


def test_done_commit_retry_succeeds(repo: Path, monkeypatch) -> None:
    """When the Tasker forgets to commit on the first invocation but
    DOES commit on the retry, the task lands Done (not Blocked).
    This is the "recoverable forgot-to-commit" success case.
    """
    monkeypatch.setenv("FAKE_CLAUDE_SCENARIO", "done-commit-retry")
    _patch_spawn(monkeypatch)
    rc = orchestrator.execute(_args(repo))
    assert rc == 0  # all clean — retry recovered
    doc = yaml_io.load(repo / "tasks.yaml")
    row = next(t for t in doc["tasks"] if t["key"] == "SMOKE-A")
    assert row["status"] == "Done"

    # Verify the commit actually exists on the worktree branch
    wt = repo.parent / "wt" / "worktree-SMOKE-A"
    out = subprocess.run(
        ["git", "rev-list", "--count", "main..HEAD"],
        cwd=str(wt), capture_output=True, text=True, check=True,
    )
    assert int(out.stdout.strip()) >= 1
