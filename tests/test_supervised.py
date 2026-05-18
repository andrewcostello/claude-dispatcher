"""Tests for supervised mode — human-gate prompt + gh pr create + reject/skip."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from claude_dispatcher import orchestrator, pr as pr_mod, spawn as spawn_mod
from claude_dispatcher.cli import build_parser


FAKE_CLAUDE = Path(__file__).parent / "fixtures" / "fake_claude.py"


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """Minimal git repo with tasks.yaml. Same shape as the orchestrator fixture."""
    subprocess.run(["git", "init", "-q", "-b", "main", str(tmp_path)],
                   check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True, capture_output=True)
    roles = tmp_path / ".claude" / "roles"
    roles.mkdir(parents=True)
    (roles / "tasker.md").write_text("stub", encoding="utf-8")
    src = Path(__file__).parent / "fixtures" / "three_task.yaml"
    (tmp_path / "tasks.yaml").write_text(src.read_text(), encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=tmp_path, check=True, capture_output=True)
    return tmp_path


def _args(repo: Path, **overrides):
    parser = build_parser()
    argv = [
        "run", str(repo / "tasks.yaml"),
        "--mode", "supervised",
        "--run-id", "sup-test-run",
        "--runs-dir", str(repo / "_runs"),
        "--worktree-base", str(repo.parent / "worktrees-sup"),
        "--claude-bin", sys.executable,
        "--only", "SMOKE-A",
    ]
    for k, v in overrides.items():
        argv += [f"--{k.replace('_', '-')}", str(v)]
    return parser.parse_args(argv)


def _patch_spawn(monkeypatch):
    """Force spawn_claude to invoke the fake claude script."""

    def fake(claude_bin, cwd, env, prompt, extra_args=None, timeout_seconds=3600):
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


def _patch_pr(monkeypatch, url: str | None, error: str | None = None):
    """Stub gh pr create with a deterministic result."""

    def fake_pr(*, cwd, title, body, branch, base="main", gh_bin="gh"):
        return pr_mod.PRResult(url=url, error=error)

    monkeypatch.setattr(pr_mod, "raise_pr", fake_pr)


def _scripted(answers: list[str]):
    """Return a responder that yields scripted answers in order."""
    it = iter(answers)

    def responder(prompt, choices):
        try:
            return next(it)
        except StopIteration:
            pytest.fail(f"unexpected prompt: {prompt!r}")

    return responder


def test_supervised_approve_raises_pr_and_marks_done(repo, monkeypatch):
    """Human types approve → dispatcher runs gh pr create → status Done."""
    monkeypatch.setenv("FAKE_CLAUDE_SCENARIO", "awaiting-human-pr")
    _patch_spawn(monkeypatch)
    _patch_pr(monkeypatch, url="https://github.com/test/repo/pull/42")
    orchestrator.set_prompt_responder(_scripted(["approve"]))

    rc = orchestrator.execute(_args(repo))
    orchestrator.set_prompt_responder(None)  # cleanup

    assert rc == 0, "approve path should exit clean"

    from claude_dispatcher import yaml_io
    doc = yaml_io.load(repo / "tasks.yaml")
    row = next(t for t in doc["tasks"] if t["key"] == "SMOKE-A")
    assert row["status"] == "Done"
    assert row["pr_url"] == "https://github.com/test/repo/pull/42"


def test_supervised_reject_marks_blocked(repo, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE_SCENARIO", "awaiting-human-pr")
    _patch_spawn(monkeypatch)
    _patch_pr(monkeypatch, url=None, error="should not be called")
    orchestrator.set_prompt_responder(_scripted(["reject"]))

    rc = orchestrator.execute(_args(repo))
    orchestrator.set_prompt_responder(None)

    assert rc == 1
    from claude_dispatcher import yaml_io
    row = next(t for t in yaml_io.load(repo / "tasks.yaml")["tasks"] if t["key"] == "SMOKE-A")
    assert row["status"] == "Blocked"
    assert row["blocked_reason"] == "human rejected PR"


def test_supervised_skip_marks_blocked(repo, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE_SCENARIO", "awaiting-human-pr")
    _patch_spawn(monkeypatch)
    _patch_pr(monkeypatch, url=None, error="should not be called")
    orchestrator.set_prompt_responder(_scripted(["skip"]))

    rc = orchestrator.execute(_args(repo))
    orchestrator.set_prompt_responder(None)

    assert rc == 1
    from claude_dispatcher import yaml_io
    row = next(t for t in yaml_io.load(repo / "tasks.yaml")["tasks"] if t["key"] == "SMOKE-A")
    assert row["status"] == "Blocked"
    assert row["blocked_reason"] == "human skipped PR approval"


def test_supervised_gh_failure_marks_blocked(repo, monkeypatch):
    """If gh pr create fails after approval, the task is Blocked, not Done."""
    monkeypatch.setenv("FAKE_CLAUDE_SCENARIO", "awaiting-human-pr")
    _patch_spawn(monkeypatch)
    _patch_pr(monkeypatch, url=None, error="auth failed")
    orchestrator.set_prompt_responder(_scripted(["approve"]))

    rc = orchestrator.execute(_args(repo))
    orchestrator.set_prompt_responder(None)

    assert rc == 1
    from claude_dispatcher import yaml_io
    row = next(t for t in yaml_io.load(repo / "tasks.yaml")["tasks"] if t["key"] == "SMOKE-A")
    assert row["status"] == "Blocked"
    assert "gh pr create failed" in row["blocked_reason"]
