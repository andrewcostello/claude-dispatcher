"""Tests for the automatic implementer fallback.

When a task's implementer agent produces no usable result (spawn error /
non-zero exit / missing summary — e.g. a cheap cross-family agent hit its
spend cap and stopped), the dispatcher falls back to the next rung of the
chain, ending at claude (the quality backstop). claude is terminal: if it
fails, the task blocks.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from claude_dispatcher import orchestrator
from claude_dispatcher import spawn as spawn_mod
from claude_dispatcher import yaml_io
from claude_dispatcher.cli import build_parser


def _snap(agent: str | None) -> orchestrator.TaskSnapshot:
    return orchestrator.TaskSnapshot(
        key="T", summary="s", description="d", type="Task",
        labels=[], model=None, agent=agent, blocked_by=[],
    )


# --- pure chain ------------------------------------------------------------

def test_chain_claude_is_terminal():
    assert orchestrator._implementer_fallback_chain(_snap(None)) == ["claude"]
    assert orchestrator._implementer_fallback_chain(_snap("claude")) == ["claude"]


def test_chain_cross_family_falls_back_to_claude():
    assert orchestrator._implementer_fallback_chain(_snap("grok")) == ["grok", "claude"]
    assert orchestrator._implementer_fallback_chain(_snap("gemini")) == ["gemini", "claude"]
    assert orchestrator._implementer_fallback_chain(_snap("codex")) == ["codex", "claude"]


# --- end-to-end fallback ---------------------------------------------------

@pytest.fixture
def repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q", "-b", "main", str(tmp_path)],
                   check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test"],
                   cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"],
                   cwd=tmp_path, check=True, capture_output=True)
    roles = tmp_path / ".claude" / "workflow" / "roles"
    roles.mkdir(parents=True)
    (roles / "tasker.md").write_text("# Tasker stub", encoding="utf-8")
    return tmp_path


def _seed_single_task(repo: Path, agent: str) -> None:
    (repo / "tasks.yaml").write_text(
        "project: TEST\n"
        "epic: FB\n"
        "tasks:\n"
        "  - key: FB-1\n"
        "    summary: \"fallback smoke\"\n"
        "    description: \"trivial task to exercise implementer fallback\"\n"
        "    type: Task\n"
        "    estimate: 5m\n"
        f"    labels: [size:XS, area:smoke]\n"
        f"    agent: {agent}\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-q", "-m", "seed"], cwd=repo, check=True, capture_output=True)


def _args(repo: Path, **overrides) -> Any:
    parser = build_parser()
    argv = [
        "run", str(repo / "tasks.yaml"),
        "--mode", "unattended",
        "--max-parallel", "1",
        "--run-id", "fallback-test-run",
        "--runs-dir", str(repo / "_runs"),
        "--worktree-base", str(repo.parent / "worktrees-fallback"),
        "--claude-bin", sys.executable,
        # keep the panel out of this hermetic test — no real reviewer CLIs
        "--cross-family-panel", "never",
        "--claude-extra-args=--permission-mode bypassPermissions",
    ]
    for k, v in overrides.items():
        if v is not None:
            argv += [f"--{k.replace('_', '-')}", str(v)]
    return parser.parse_args(argv)


def _read_journal_event_types(repo: Path) -> list[str]:
    jpath = repo / "_runs" / "fallback-test-run" / "journal.jsonl"
    types = []
    for line in jpath.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                types.append(json.loads(line).get("event_type"))
            except json.JSONDecodeError:
                pass
    return types


def test_fallback_to_claude_when_primary_stops(repo: Path, monkeypatch) -> None:
    """grok stops (exit 1, no summary) -> dispatcher falls back to claude,
    which completes the task. The row records claude as the agent and the
    journal carries an agent_fallback event."""
    _seed_single_task(repo, agent="grok")
    calls: list[str] = []

    def fake_spawn_agent(*, agent, claude_bin, cwd, env, prompt,
                         model=None, extra_args=None, timeout_seconds=3600):
        calls.append(agent)
        sp = Path(env["SUMMARY_PATH"])
        sp.parent.mkdir(parents=True, exist_ok=True)
        if agent != "claude":
            # simulate a spend-cap stop: non-zero exit, no summary written
            return spawn_mod.SpawnResult(
                exit_code=1, summary_path=sp, stdout="", stderr="stopped: spend cap")
        # claude backstop completes: write summary + a real commit
        sp.write_text("**Status:** Done\n\n## What landed\nfallback work\n",
                      encoding="utf-8")
        (Path(cwd) / "fallback.txt").write_text("done\n", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=cwd, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-q", "-m", "fallback work"],
                       cwd=cwd, check=True, capture_output=True)
        return spawn_mod.SpawnResult(
            exit_code=0, summary_path=sp, stdout="ok", stderr="")

    monkeypatch.setattr(spawn_mod, "spawn_agent", fake_spawn_agent)

    rc = orchestrator.execute(_args(repo))
    assert rc == 0, "task should complete via the claude fallback"
    assert calls == ["grok", "claude"], "grok tried first, then claude"

    doc = yaml_io.load(repo / "tasks.yaml")
    row = next(t for t in doc["tasks"] if t["key"] == "FB-1")
    assert row["status"] == "Done"
    assert row["agent"] == "claude", "row records the agent that actually did the work"
    assert "agent_fallback" in _read_journal_event_types(repo)


def test_no_fallback_after_claude_blocks(repo: Path, monkeypatch) -> None:
    """A claude-authored task has no rung after it: a stop blocks the task
    (fallback must not loop or invent a rung)."""
    _seed_single_task(repo, agent="claude")
    calls: list[str] = []

    def always_stop(*, agent, claude_bin, cwd, env, prompt,
                    model=None, extra_args=None, timeout_seconds=3600):
        calls.append(agent)
        sp = Path(env["SUMMARY_PATH"])
        sp.parent.mkdir(parents=True, exist_ok=True)
        return spawn_mod.SpawnResult(
            exit_code=1, summary_path=sp, stdout="", stderr="stopped")

    monkeypatch.setattr(spawn_mod, "spawn_agent", always_stop)

    rc = orchestrator.execute(_args(repo))
    assert rc != 0, "a blocked task is a non-clean run"
    assert calls == ["claude"], "claude is terminal — no extra fallback attempt"

    doc = yaml_io.load(repo / "tasks.yaml")
    row = next(t for t in doc["tasks"] if t["key"] == "FB-1")
    assert row["status"] == "Blocked"
    assert "session_exit_code_1" in str(row.get("blocked_reason", ""))
    assert "agent_fallback" not in _read_journal_event_types(repo)
