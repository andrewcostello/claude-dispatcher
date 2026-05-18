"""Tests for --max-parallel > 1 — verifies parallel dispatch and YAML-write
serialization. Uses the fake_claude binary with a small sleep so multiple
workers actually overlap.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from claude_dispatcher import orchestrator, spawn as spawn_mod
from claude_dispatcher.cli import build_parser


FAKE_CLAUDE = Path(__file__).parent / "fixtures" / "fake_claude.py"


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q", "-b", "main", str(tmp_path)],
                   check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test"],
                   cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"],
                   cwd=tmp_path, check=True, capture_output=True)
    roles = tmp_path / ".claude" / "roles"
    roles.mkdir(parents=True)
    (roles / "tasker.md").write_text("stub", encoding="utf-8")
    src = Path(__file__).parent / "fixtures" / "three_task.yaml"
    (tmp_path / "tasks.yaml").write_text(src.read_text(), encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"],
                   cwd=tmp_path, check=True, capture_output=True)
    return tmp_path


def _args(repo: Path, max_parallel: int):
    parser = build_parser()
    argv = [
        "run", str(repo / "tasks.yaml"),
        "--mode", "unattended",
        "--run-id", f"conc-test-{max_parallel}",
        "--runs-dir", str(repo / "_runs"),
        "--worktree-base", str(repo.parent / f"worktrees-conc-{max_parallel}"),
        "--claude-bin", sys.executable,
        "--max-parallel", str(max_parallel),
    ]
    return parser.parse_args(argv)


def _patch_spawn(monkeypatch, sleep_seconds: float = 0.5):
    """Replace spawn_claude with a version that sleeps before writing the
    summary. The sleep makes parallel workers visibly overlap.
    """

    def fake(claude_bin, cwd, env, prompt, extra_args=None, timeout_seconds=3600):
        # Trace the worker's timing into a per-run file so the test can
        # assert overlap.
        trace_dir = Path(os.environ.get("CONCURRENCY_TRACE_DIR", "/tmp"))
        trace_dir.mkdir(parents=True, exist_ok=True)
        trace = trace_dir / "trace.txt"
        with trace.open("a") as fh:
            fh.write(f"{time.time():.4f} {env['TASK_KEY']} start\n")
        time.sleep(sleep_seconds)
        with trace.open("a") as fh:
            fh.write(f"{time.time():.4f} {env['TASK_KEY']} end\n")

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


def test_max_parallel_2_dispatches_independent_tasks_in_overlap(
    repo: Path, monkeypatch, tmp_path: Path
) -> None:
    """SMOKE-A and SMOKE-B are independent (no blockedBy). With max-parallel=2,
    their spawn windows must overlap. SMOKE-C is blocked by SMOKE-A and only
    starts after A finishes.
    """
    trace_dir = tmp_path / "trace"
    monkeypatch.setenv("CONCURRENCY_TRACE_DIR", str(trace_dir))
    _patch_spawn(monkeypatch, sleep_seconds=0.5)

    rc = orchestrator.execute(_args(repo, max_parallel=2))
    assert rc == 0

    trace = (trace_dir / "trace.txt").read_text(encoding="utf-8").splitlines()
    events = []
    for line in trace:
        ts, key, kind = line.split()
        events.append((float(ts), key, kind))
    events.sort()

    starts = {e[1]: e[0] for e in events if e[2] == "start"}
    ends = {e[1]: e[0] for e in events if e[2] == "end"}

    # Independent tasks overlap: A and B both started before either ended.
    assert starts["SMOKE-A"] < ends["SMOKE-B"]
    assert starts["SMOKE-B"] < ends["SMOKE-A"]

    # SMOKE-C waits for SMOKE-A to finish (its blockedBy dependency).
    assert starts["SMOKE-C"] >= ends["SMOKE-A"]


def test_yaml_writes_serialize_under_lock(repo: Path, monkeypatch, tmp_path: Path) -> None:
    """With max-parallel=2 and concurrent writes, the YAML stays well-formed
    and the final state has all three tasks at Status: Done.
    """
    trace_dir = tmp_path / "trace"
    monkeypatch.setenv("CONCURRENCY_TRACE_DIR", str(trace_dir))
    _patch_spawn(monkeypatch, sleep_seconds=0.3)

    rc = orchestrator.execute(_args(repo, max_parallel=2))
    assert rc == 0

    # Final YAML loads cleanly and has all tasks Done.
    from claude_dispatcher import yaml_io
    doc = yaml_io.load(repo / "tasks.yaml")
    statuses = {t["key"]: t.get("status") for t in doc["tasks"]}
    assert statuses == {"SMOKE-A": "Done", "SMOKE-B": "Done", "SMOKE-C": "Done"}

    # All three have completed_at — serialization didn't drop fields.
    for t in doc["tasks"]:
        assert t.get("completed_at"), f"{t['key']} lost completed_at"
        assert t.get("pr_url"), f"{t['key']} lost pr_url"


def test_max_parallel_higher_than_runnable_set_doesnt_crash(
    repo: Path, monkeypatch, tmp_path: Path
) -> None:
    """--max-parallel=8 with only 2 initially runnable tasks should not crash."""
    trace_dir = tmp_path / "trace"
    monkeypatch.setenv("CONCURRENCY_TRACE_DIR", str(trace_dir))
    _patch_spawn(monkeypatch, sleep_seconds=0.2)

    rc = orchestrator.execute(_args(repo, max_parallel=8))
    assert rc == 0

    from claude_dispatcher import yaml_io
    doc = yaml_io.load(repo / "tasks.yaml")
    assert all(t.get("status") == "Done" for t in doc["tasks"])
