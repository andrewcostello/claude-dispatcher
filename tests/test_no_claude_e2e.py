"""Hermetic end-to-end seal for the --no-claude contract.

Runs a real `dispatcher run --no-claude` through the REAL spawn_agent path —
fake_grok stands in as the grok CLI (via AGENT_BINS), and the claude binary is
a poison script that records any invocation. The PR's central claim is that a
--no-claude run never touches Claude: this test proves it at the process
boundary, not by asserting config fields.
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

FAKE_GROK = Path(__file__).parent / "fixtures" / "fake_grok.py"


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=tmp_path,
                   check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t"],
                   cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "t"],
                   cwd=tmp_path, check=True, capture_output=True)
    (tmp_path / "README.md").write_text("seed\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path,
                   check=True, capture_output=True)
    subprocess.run(["git", "commit", "-q", "-m", "seed"],
                   cwd=tmp_path, check=True, capture_output=True)
    return tmp_path


def _seed_task(repo: Path) -> None:
    # Unpinned agent: --no-claude routing must pick grok by itself.
    # verify: mechanical keeps the run hermetic (no LLM-verifier spawn, which
    # would reach for a real grok binary rather than the AGENT_BINS stub).
    (repo / "tasks.yaml").write_text(
        "project: TEST\n"
        "epic: NC\n"
        "tasks:\n"
        "  - key: NC-1\n"
        "    summary: \"no-claude smoke\"\n"
        "    description: \"trivial task for the no-claude hermetic seal\"\n"
        "    type: Task\n"
        "    estimate: 5m\n"
        "    labels: [size:XS, area:smoke]\n"
        "    verify: mechanical\n"
        "    panel: never\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "."], cwd=repo, check=True,
                   capture_output=True)
    subprocess.run(["git", "commit", "-q", "-m", "seed tasks"], cwd=repo,
                   check=True, capture_output=True)


def _args(repo: Path, poison_claude: Path) -> Any:
    parser = build_parser()
    return parser.parse_args([
        "run", str(repo / "tasks.yaml"),
        "--mode", "unattended",
        "--no-claude",
        "--max-parallel", "1",
        "--run-id", "no-claude-e2e",
        "--runs-dir", str(repo / "_runs"),
        "--worktree-base", str(repo.parent / "worktrees-no-claude"),
        "--claude-bin", str(poison_claude),
        "--cross-family-panel", "never",
    ])


def test_no_claude_run_completes_without_any_claude_invocation(
        repo: Path, tmp_path: Path, monkeypatch) -> None:
    _seed_task(repo)

    # grok CLI = fake_grok, via the same AGENT_BINS registry preflight and
    # spawn_agent both read — the real argv/auto-commit path is exercised.
    wrapper = tmp_path / "bin" / "fake-grok"
    wrapper.parent.mkdir(parents=True, exist_ok=True)
    wrapper.write_text(
        f"#!/bin/sh\nexec {sys.executable} {FAKE_GROK} \"$@\"\n",
        encoding="utf-8")
    wrapper.chmod(0o755)
    monkeypatch.setitem(spawn_mod.AGENT_BINS, "grok", str(wrapper))

    # claude CLI = poison: records any invocation, exits 127.
    canary = tmp_path / "claude-was-invoked"
    poison = tmp_path / "bin" / "claude"
    poison.write_text(
        f"#!/bin/sh\ntouch {canary}\necho 'claude must not run' >&2\nexit 127\n",
        encoding="utf-8")
    poison.chmod(0o755)

    rc = orchestrator.execute(_args(repo, poison))
    assert rc == 0, "no-claude run should complete cleanly"

    doc = yaml_io.load(repo / "tasks.yaml")
    row = next(t for t in doc["tasks"] if t["key"] == "NC-1")
    assert row["status"] == "Done"
    assert row["agent"] == "grok"

    assert not canary.exists(), (
        "--no-claude contract violated: the claude binary was invoked"
    )

    # Journal provenance carries the grok family end to end.
    jpath = repo / "_runs" / "no-claude-e2e" / "journal.jsonl"
    done = [json.loads(l) for l in jpath.read_text().splitlines()
            if l.strip() and json.loads(l).get("event_type") == "task_done"]
    assert done and done[0]["payload"]["agent"] == "grok"
