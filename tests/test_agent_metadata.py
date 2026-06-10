"""Agent/version provenance on terminal rows + terminal journal events (OPS-4).

Every terminal task YAML row (Done/Blocked/Escalated) and every terminal
journal event (task_done / task_blocked) must carry:
  - agent              — spawn.AGENT_NAME ("claude")
  - dispatcher_version — claude_dispatcher.__version__
  - agent_version      — the claude CLI's `--version` line, captured exactly
                         ONCE per run at run setup. OMITTED (never None/null)
                         when capture fails — degrade-to-absent.

capture_agent_version() is contractually non-raising: any failure (missing
binary, timeout, non-zero exit, empty output) warns once to stderr and
returns None; the run itself must be unaffected.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from claude_dispatcher import (
    __version__,
    journal as journal_mod,
    orchestrator,
    spawn as spawn_mod,
    yaml_io,
)
from claude_dispatcher.cli import build_parser


FIXTURE_DIR = Path(__file__).parent / "fixtures"
FAKE_CLAUDE = FIXTURE_DIR / "fake_claude.py"


# --- repo + harness (mirrors test_orchestrator_journal) ----------------------


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A git repo seeded with the three-task smoke fixture."""
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo_dir)],
                   check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=repo_dir,
                   check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=repo_dir,
                   check=True, capture_output=True)
    roles = repo_dir / ".claude" / "workflow" / "roles"
    roles.mkdir(parents=True)
    (roles / "tasker.md").write_text("stub", encoding="utf-8")
    (repo_dir / "tasks.yaml").write_text(
        (FIXTURE_DIR / "three_task.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "."], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=repo_dir,
                   check=True, capture_output=True)
    return repo_dir


def _args(repo: Path, **overrides):
    parser = build_parser()
    argv = [
        "run", str(repo / "tasks.yaml"),
        "--mode", "unattended", "--max-parallel", "1",
        "--max-iterations", "2",
        "--run-id", "agent-meta-test",
        "--runs-dir", str(repo / "_runs"),
        "--worktree-base", str(repo.parent / "wt"),
        "--claude-bin", sys.executable,
    ]
    for k, v in overrides.items():
        if v is None:
            continue
        flag = f"--{k.replace('_', '-')}"
        if v is True:
            argv += [flag]
        else:
            argv += [flag, str(v)]
    return parser.parse_args(argv)


def _patch_spawn(monkeypatch) -> None:
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


def _journal_path(repo: Path) -> Path:
    return repo / "_runs" / "agent-meta-test" / journal_mod.JOURNAL_FILENAME


def _events(repo: Path) -> list[journal_mod.JournalEvent]:
    return list(journal_mod.read_events(_journal_path(repo)))


def _row(repo: Path, key: str) -> dict:
    doc = yaml_io.load(repo / "tasks.yaml")
    return next(t for t in doc["tasks"] if t["key"] == key)


def _make_bin(tmp_path: Path, name: str, body: str) -> str:
    """Write an executable shell script and return its path."""
    p = tmp_path / name
    p.write_text("#!/bin/sh\n" + body, encoding="utf-8")
    p.chmod(0o755)
    return str(p)


# --- capture_agent_version unit tests ----------------------------------------


def test_capture_strips_trailing_newline_and_extra_lines(tmp_path: Path) -> None:
    """Edge case 2: first non-empty line, stripped, wins."""
    bin_path = _make_bin(tmp_path, "claude-multiline", (
        'echo ""\n'
        'echo "  2.5.0 (test-claude)  "\n'
        'echo "extra diagnostics line"\n'
    ))
    assert spawn_mod.capture_agent_version(bin_path) == "2.5.0 (test-claude)"


def test_capture_via_fake_claude_fixture(tmp_path: Path) -> None:
    """fake_claude answers --version before reading stdin (no hang, fixed
    string). Wrapped in a shell script because capture takes one binary path."""
    bin_path = _make_bin(
        tmp_path, "claude-fake",
        f'exec "{sys.executable}" "{FAKE_CLAUDE}" "$@"\n',
    )
    assert spawn_mod.capture_agent_version(bin_path) == "1.0.0 (fake-claude)"


def test_capture_nonexistent_binary_warns_returns_none(
    tmp_path: Path, capsys,
) -> None:
    """Edge case 1 (unit half): missing binary → None + one stderr warning."""
    missing = str(tmp_path / "no-such-claude")
    assert spawn_mod.capture_agent_version(missing) is None
    err = capsys.readouterr().err
    assert err.count("warning: agent version capture failed") == 1


def test_capture_nonzero_exit_warns_returns_none(tmp_path: Path, capsys) -> None:
    bin_path = _make_bin(tmp_path, "claude-fails", 'echo "9.9.9"\nexit 3\n')
    assert spawn_mod.capture_agent_version(bin_path) is None
    assert "warning: agent version capture failed" in capsys.readouterr().err


def test_capture_empty_output_warns_returns_none(tmp_path: Path, capsys) -> None:
    bin_path = _make_bin(tmp_path, "claude-silent", "exit 0\n")
    assert spawn_mod.capture_agent_version(bin_path) is None
    assert "warning: agent version capture failed" in capsys.readouterr().err


def test_capture_timeout_warns_returns_none(monkeypatch, capsys) -> None:
    """Edge case 6: a subprocess timeout never propagates."""
    def boom(*a, **k):
        raise subprocess.TimeoutExpired(cmd=["claude", "--version"], timeout=30)

    monkeypatch.setattr(spawn_mod.subprocess, "run", boom)
    assert spawn_mod.capture_agent_version("claude") is None
    assert "warning: agent version capture failed" in capsys.readouterr().err


def test_capture_unexpected_exception_warns_returns_none(
    monkeypatch, capsys,
) -> None:
    """Edge case 6: ANY exception inside subprocess.run degrades to None."""
    def boom(*a, **k):
        raise RuntimeError("simulated interpreter weirdness")

    monkeypatch.setattr(spawn_mod.subprocess, "run", boom)
    assert spawn_mod.capture_agent_version("claude") is None
    assert "warning: agent version capture failed" in capsys.readouterr().err


def test_capture_does_not_hang_on_stdin_reader(tmp_path: Path) -> None:
    """stdin=DEVNULL: a binary that reads stdin (like the real claude / the
    fake without --version) must not hang the capture. `cat` blocks forever
    on an open pipe; with DEVNULL it sees EOF immediately."""
    bin_path = _make_bin(tmp_path, "claude-stdin-reader", (
        "cat > /dev/null\n"
        'echo "3.0.0 (stdin-reader)"\n'
    ))
    assert spawn_mod.capture_agent_version(
        bin_path, timeout_seconds=10,
    ) == "3.0.0 (stdin-reader)"


# --- end-to-end: Done path ----------------------------------------------------


def test_done_row_and_task_done_event_carry_all_fields(
    repo: Path, monkeypatch,
) -> None:
    """Edge case 5: Done row + task_done payload carry agent, agent_version,
    dispatcher_version; the journal chain still verifies."""
    _patch_spawn(monkeypatch)
    rc = orchestrator.execute(_args(repo, only="SMOKE-A"))
    assert rc == 0

    # --claude-bin is sys.executable here, so capture returns a Python
    # version line — provenance honesty over fixture aesthetics.
    row = _row(repo, "SMOKE-A")
    assert row["status"] == "Done"
    assert row["agent"] == "claude"
    assert row["dispatcher_version"] == __version__
    assert row["agent_version"].startswith("Python 3")

    assert journal_mod.verify(_journal_path(repo)).ok
    done = next(e for e in _events(repo) if e.event_type == "task_done")
    assert done.payload["agent"] == "claude"
    assert done.payload["dispatcher_version"] == __version__
    assert done.payload["agent_version"].startswith("Python 3")


# --- end-to-end: early-return Blocked path ------------------------------------


def test_blocked_malformed_row_and_event_carry_fields(
    repo: Path, monkeypatch,
) -> None:
    """Edge case 4: the early-return Blocked path (_mark_blocked) stamps the
    row and the task_blocked journal payload."""
    monkeypatch.setenv("FAKE_CLAUDE_SCENARIO", "blocked-malformed")
    _patch_spawn(monkeypatch)
    rc = orchestrator.execute(_args(repo, only="SMOKE-A"))
    assert rc == 1

    row = _row(repo, "SMOKE-A")
    assert row["status"] == "Blocked"
    assert row["agent"] == "claude"
    assert row["dispatcher_version"] == __version__
    assert row["agent_version"].startswith("Python 3")

    assert journal_mod.verify(_journal_path(repo)).ok
    blocked = next(e for e in _events(repo) if e.event_type == "task_blocked")
    assert "summary_malformed" in blocked.payload["reason"]
    assert blocked.payload["agent"] == "claude"
    assert blocked.payload["dispatcher_version"] == __version__
    assert blocked.payload["agent_version"].startswith("Python 3")


# --- end-to-end: in-worker Blocked path (task_blocked from _run_task) ---------


def test_unattended_pr_gate_blocked_event_carries_fields(
    repo: Path, monkeypatch,
) -> None:
    """The _run_task else-branch task_blocked (awaiting-PR-in-unattended-mode)
    also carries the provenance fields."""
    monkeypatch.setenv("FAKE_CLAUDE_SCENARIO", "awaiting-human-pr")
    _patch_spawn(monkeypatch)
    rc = orchestrator.execute(_args(repo, only="SMOKE-A"))
    assert rc == 1

    row = _row(repo, "SMOKE-A")
    assert row["status"] == "Blocked"
    assert row["agent"] == "claude"
    assert row["dispatcher_version"] == __version__

    blocked = next(e for e in _events(repo) if e.event_type == "task_blocked")
    assert "awaiting human PR approval" in blocked.payload["reason"]
    assert blocked.payload["agent"] == "claude"
    assert blocked.payload["dispatcher_version"] == __version__
    assert blocked.payload["agent_version"].startswith("Python 3")


# --- end-to-end: capture failure degrades, never blocks -----------------------


def test_capture_failure_run_completes_fields_degrade(
    repo: Path, monkeypatch, capsys,
) -> None:
    """Edge case 1: nonexistent claude-bin → version capture fails with a
    stderr warning; the run completes, rows carry agent + dispatcher_version
    but NOT agent_version, and nothing is blocked because of it."""
    _patch_spawn(monkeypatch)  # spawning is stubbed, so the bad bin only
    # affects capture_agent_version.
    rc = orchestrator.execute(_args(
        repo, only="SMOKE-A",
        claude_bin=str(repo / "no-such-claude-binary"),
    ))
    assert rc == 0, "version-capture failure must never fail the run"
    assert "warning: agent version capture failed" in capsys.readouterr().err

    row = _row(repo, "SMOKE-A")
    assert row["status"] == "Done"
    assert row["agent"] == "claude"
    assert row["dispatcher_version"] == __version__
    assert "agent_version" not in row, "absent, never null"

    assert journal_mod.verify(_journal_path(repo)).ok
    done = next(e for e in _events(repo) if e.event_type == "task_done")
    assert done.payload["agent"] == "claude"
    assert done.payload["dispatcher_version"] == __version__
    assert "agent_version" not in done.payload


# --- once-per-run capture ------------------------------------------------------


def test_capture_called_exactly_once_for_multi_task_run(
    repo: Path, monkeypatch,
) -> None:
    """Edge case 3: a three-task run calls capture_agent_version exactly once
    (at run setup), never per task."""
    _patch_spawn(monkeypatch)
    calls = {"n": 0}
    real = spawn_mod.capture_agent_version

    def counting(claude_bin, timeout_seconds=30):
        calls["n"] += 1
        return real(claude_bin, timeout_seconds=timeout_seconds)

    monkeypatch.setattr(spawn_mod, "capture_agent_version", counting)

    rc = orchestrator.execute(_args(repo))
    assert rc == 0
    assert calls["n"] == 1

    # All three terminal rows still carry the once-captured version.
    for key in ("SMOKE-A", "SMOKE-B", "SMOKE-C"):
        row = _row(repo, key)
        assert row["agent"] == "claude"
        assert row["agent_version"].startswith("Python 3")
        assert row["dispatcher_version"] == __version__
