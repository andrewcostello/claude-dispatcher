"""Tests for the post-Done mechanical verification gate (repo tests green).

Two layers, mirroring test_push_verify.py / test_commit_retry.py:
  * Unit tests drive ``mechanical_verify.run_test_command`` directly —
    exit-code capture, tail truncation, timeout, launch failure.
  * Integration tests drive the live dispatch loop through fake_claude
    against a repo whose ``.dispatcher.yaml`` declares a `test:` command,
    asserting the four acceptance paths: green; red→fix→green; red→red
    Blocked (output tail in the YAML detail); and the no-config skip that
    preserves pre-gate behavior.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from claude_dispatcher import (
    journal as journal_mod,
    mechanical_verify as mv,
    orchestrator,
    spawn as spawn_mod,
    yaml_io,
)
from claude_dispatcher.cli import build_parser


FAKE_CLAUDE = Path(__file__).parent / "fixtures" / "fake_claude.py"


# --------------------------------------------------------------------------
# Unit tests: mechanical_verify.run_test_command.
# --------------------------------------------------------------------------


def test_exit_zero_passes(tmp_path: Path) -> None:
    res = mv.run_test_command("echo all-green", worktree=tmp_path,
                              timeout_seconds=30)
    assert res.passed
    assert res.exit_code == 0
    assert "all-green" in res.output_tail
    assert res.duration_seconds >= 0


def test_nonzero_exit_captured(tmp_path: Path) -> None:
    res = mv.run_test_command("echo boom; exit 3", worktree=tmp_path,
                              timeout_seconds=30)
    assert not res.passed
    assert res.exit_code == 3
    assert "boom" in res.output_tail


def test_stderr_merged_into_tail(tmp_path: Path) -> None:
    """stdout and stderr are combined — the tail reflects what a human at
    the terminal would have seen last."""
    res = mv.run_test_command("echo to-stderr 1>&2; exit 1",
                              worktree=tmp_path, timeout_seconds=30)
    assert res.exit_code == 1
    assert "to-stderr" in res.output_tail


def test_tail_truncation_keeps_only_last_chars(tmp_path: Path) -> None:
    """Output beyond TAIL_CHARS is dropped from the FRONT — the end of the
    output (where test runners print their failure summary) survives."""
    cmd = (f"{sys.executable} -c "
           "\"print('x' * 5000, end=''); print('END-MARKER', end='')\"")
    res = mv.run_test_command(cmd, worktree=tmp_path, timeout_seconds=30)
    assert res.exit_code == 0
    assert len(res.output_tail) == mv.TAIL_CHARS
    assert res.output_tail.endswith("END-MARKER")


def test_timeout_is_failure_with_partial_output_and_note(tmp_path: Path) -> None:
    """A timed-out command is a failed execution: exit_code None, whatever
    partial output was captured, and an explicit timed-out annotation."""
    res = mv.run_test_command("echo partial-before-hang && sleep 5",
                              worktree=tmp_path, timeout_seconds=1)
    assert not res.passed
    assert res.exit_code is None
    assert "timed out after 1s" in res.output_tail
    assert "partial-before-hang" in res.output_tail
    # The note is appended after truncation, so the effective bound is
    # TAIL_CHARS plus small slack.
    assert len(res.output_tail) <= mv.TAIL_CHARS + 100


def test_launch_failure_is_failed_execution(tmp_path: Path) -> None:
    """An OSError from the subprocess launch (here: a missing worktree dir)
    is a failed execution with the error text standing in for output."""
    res = mv.run_test_command("echo never-runs",
                              worktree=tmp_path / "does-not-exist",
                              timeout_seconds=30)
    assert not res.passed
    assert res.exit_code is None
    assert "failed to launch" in res.output_tail


# --------------------------------------------------------------------------
# Integration: the gate in the live dispatch loop, via fake_claude.
# --------------------------------------------------------------------------


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A git repo seeded with the three-task smoke fixture, NO .dispatcher.yaml.

    Nested under tmp_path/"repo" so repo.parent (the worktree base used by
    _args) is unique per test — sibling tests share SMOKE-* keys and would
    otherwise collide on the same worktree directory.
    """
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo_dir)],
                   check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test"],
                   cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"],
                   cwd=repo_dir, check=True, capture_output=True)
    roles = repo_dir / ".claude" / "workflow" / "roles"
    roles.mkdir(parents=True)
    (roles / "tasker.md").write_text("stub", encoding="utf-8")
    src = Path(__file__).parent / "fixtures" / "three_task.yaml"
    (repo_dir / "tasks.yaml").write_text(src.read_text(), encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=repo_dir,
                   check=True, capture_output=True)
    return repo_dir


def _write_dispatcher_config(repo: Path, content: str) -> None:
    """Commit a .dispatcher.yaml on main so every task worktree contains it."""
    (repo / ".dispatcher.yaml").write_text(content, encoding="utf-8")
    subprocess.run(["git", "add", ".dispatcher.yaml"], cwd=repo,
                   check=True, capture_output=True)
    subprocess.run(["git", "commit", "-q", "-m", "add dispatcher config"],
                   cwd=repo, check=True, capture_output=True)


def _args(repo: Path, **overrides):
    parser = build_parser()
    argv = [
        "run", str(repo / "tasks.yaml"),
        "--mode", "unattended", "--max-parallel", "1",
        "--run-id", "mech-test",
        "--runs-dir", str(repo / "_runs"),
        "--worktree-base", str(repo.parent / "wt"),
        "--claude-bin", sys.executable,
        "--only", "SMOKE-A",
        "--claude-extra-args=--permission-mode bypassPermissions",
    ]
    for k, v in overrides.items():
        argv += [f"--{k.replace('_', '-')}", str(v)]
    return parser.parse_args(argv)


def _patch_spawn(monkeypatch, *, hook=None):
    """Route spawn_claude through fake_claude.py.

    ``hook(call_n, cwd)`` runs before each spawn (1-based call counter) and
    may raise to simulate a spawn failure; returns the recorded call count
    list so tests can assert how many spawns fired.
    """
    calls: list[int] = []

    def fake(claude_bin, cwd, env, prompt, extra_args=None, timeout_seconds=3600):
        calls.append(len(calls) + 1)
        if hook is not None:
            hook(len(calls), Path(cwd))
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
    return calls


def _row(repo: Path, key: str = "SMOKE-A") -> dict:
    doc = yaml_io.load(repo / "tasks.yaml")
    return next(t for t in doc["tasks"] if t["key"] == key)


def _events(repo: Path) -> list[journal_mod.JournalEvent]:
    jpath = repo / "_runs" / "mech-test" / journal_mod.JOURNAL_FILENAME
    return list(journal_mod.read_events(jpath))


def _mech_events(repo: Path) -> list[journal_mod.JournalEvent]:
    return [e for e in _events(repo)
            if e.event_type == "verification_mechanical"]


def _types_for(events, task_key: str) -> list[str]:
    return [e.event_type for e in events if e.task_key == task_key]


# --- acceptance 1: green path ------------------------------------------------


def test_tests_green_passes_gate(repo: Path, monkeypatch) -> None:
    """Green suite on the first run: Done, row stamped passed, exactly one
    verification_mechanical event echoing the command. The unknown config
    key rides along in the payload (the loader's forward-compat note)."""
    _write_dispatcher_config(
        repo,
        'test: "test -f tests-green.txt"\nfuture_section: true\n',
    )
    monkeypatch.setenv("FAKE_CLAUDE_SCENARIO", "done-tests-green")
    _patch_spawn(monkeypatch)

    rc = orchestrator.execute(_args(repo))
    assert rc == 0
    row = _row(repo)
    assert row["status"] == "Done"
    assert row["mechanical_verification"] == "passed"
    assert "mechanical_verification_detail" not in row

    evs = _mech_events(repo)
    assert len(evs) == 1
    p = evs[0].payload
    assert p["outcome"] == "passed"
    assert p["retried"] is False
    assert p["exit_code"] == 0
    assert p["command"] == "test -f tests-green.txt"
    assert p["unknown_keys"] == ["future_section"]
    assert "duration_seconds" in p


# --- acceptance 2: red → fix → green retry path ------------------------------


def test_tests_red_then_fixed_recovers(repo: Path, monkeypatch) -> None:
    """First run leaves the suite red; the fix-the-tests retry commits the
    green file; the re-run passes. Task lands Done with TWO events."""
    _write_dispatcher_config(repo, 'test: "test -f tests-green.txt"\n')
    monkeypatch.setenv("FAKE_CLAUDE_SCENARIO", "done-tests-red-then-fixed")
    calls = _patch_spawn(monkeypatch)

    rc = orchestrator.execute(_args(repo))
    assert rc == 0
    row = _row(repo)
    assert row["status"] == "Done"
    assert row["mechanical_verification"] == "passed"

    evs = _mech_events(repo)
    assert len(evs) == 2
    assert evs[0].payload["outcome"] == "failed"
    assert evs[0].payload["retried"] is False
    assert evs[1].payload["outcome"] == "passed"
    assert evs[1].payload["retried"] is True
    # Initial spawn + the fix-the-tests retry spawn.
    assert len(calls) == 2


# --- acceptance 3: red → red Blocked path ------------------------------------


def test_tests_red_after_retry_blocks_with_tail(repo: Path, monkeypatch) -> None:
    """Still red after the one retry: Blocked, short blocked_reason label,
    the failing output tail (bounded) in mechanical_verification_detail."""
    _write_dispatcher_config(
        repo, 'test: "echo RED-GATE-MARKER; test -f tests-green.txt"\n',
    )
    monkeypatch.setenv("FAKE_CLAUDE_SCENARIO", "done-tests-red")
    calls = _patch_spawn(monkeypatch)

    rc = orchestrator.execute(_args(repo))
    assert rc == 1
    row = _row(repo)
    assert row["status"] == "Blocked"
    assert "mechanical_verification_failed" in row["blocked_reason"]
    assert row["mechanical_verification"] == "failed"
    detail = row["mechanical_verification_detail"]
    # The TAIL (not the full output) lands in the detail, bounded.
    assert "RED-GATE-MARKER" in detail
    assert len(detail) <= mv.TAIL_CHARS + 100

    evs = _mech_events(repo)
    # Quality cascade may re-run the gate on a second effort rung (e.g.
    # claude@default then claude@high); each rung does fail + one fix retry.
    assert len(evs) >= 2
    assert all(e.payload["outcome"] == "failed" for e in evs)
    assert all(e.payload["exit_code"] == 1 for e in evs)
    # First pair of a rung is always fail then retried fail.
    assert evs[0].payload["retried"] is False
    assert any(e.payload.get("retried") for e in evs)

    # Terminal per-task event is task_blocked; the red gate prevented the
    # cross-family panel and auto-integrate from running (ordering edge:
    # the gate sits before both in _run_task).
    types = _types_for(_events(repo), "SMOKE-A")
    # task_blocked is the terminal lifecycle event (followed only by its
    # best-effort notify_sent).
    assert types[-2:] == ["task_blocked", "notify_sent"]
    assert "task_done" not in types
    assert "panel_started" not in types
    assert "integrate_result" not in types
    # Initial spawn + fix retry; cascade may add a few more implementer rungs
    # but must not runaway.
    assert 2 <= len(calls) <= 8


# --- acceptance 4: no-config skip path ----------------------------------------


def test_no_config_skips_and_preserves_done_flow(repo: Path, monkeypatch) -> None:
    """No .dispatcher.yaml: gate skips with a journaled reason and the run
    behaves exactly as the pre-gate `done` scenario otherwise."""
    _patch_spawn(monkeypatch)

    rc = orchestrator.execute(_args(repo))
    assert rc == 0
    row = _row(repo)
    assert row["status"] == "Done"
    assert row["mechanical_verification"] == "skipped"
    assert "blocked_reason" not in row
    assert "mechanical_verification_detail" not in row

    evs = _mech_events(repo)
    assert len(evs) == 1
    assert evs[0].payload == {"outcome": "skipped", "reason": "no .dispatcher.yaml"}

    # Lifecycle identical to the pre-gate `done` scenario, plus the mechanical
    # skip event and the VG-4 LLM verifier events (VERIFIED stub) between
    # summary_parsed and push_verify.
    assert _types_for(_events(repo), "SMOKE-A") == [
        "task_started",
        "task_spawn_finished",
        "summary_parsed",
        "verification_mechanical",
        "verification_started",
        "task_spawn_finished",  # verifier spawn
        "verification_verdict",
        "push_verify",
        "task_done",
    ]


# --- edge cases ---------------------------------------------------------------


def test_config_without_test_key_skips_with_distinct_reason(
    repo: Path, monkeypatch,
) -> None:
    """A .dispatcher.yaml that declares no test: command skips with a reason
    DISTINCT from the absent-file skip."""
    _write_dispatcher_config(repo, 'future_section: true\n')
    _patch_spawn(monkeypatch)

    rc = orchestrator.execute(_args(repo))
    assert rc == 0
    row = _row(repo)
    assert row["status"] == "Done"
    assert row["mechanical_verification"] == "skipped"

    evs = _mech_events(repo)
    assert len(evs) == 1
    assert evs[0].payload["reason"] == "no test command"


def test_malformed_config_blocks_without_retry(repo: Path, monkeypatch) -> None:
    """A malformed .dispatcher.yaml fails the gate WITHOUT a fix-the-tests
    retry spawn — a corrective prompt can't fix a config the dispatcher
    can't parse. Error string lands in journal + row detail."""
    _write_dispatcher_config(repo, "test: [not, a, string]\n")
    calls = _patch_spawn(monkeypatch)

    rc = orchestrator.execute(_args(repo))
    assert rc == 1
    row = _row(repo)
    assert row["status"] == "Blocked"
    assert "mechanical_verification_failed" in row["blocked_reason"]
    assert row["mechanical_verification"] == "failed"
    assert "must be a non-empty string" in row["mechanical_verification_detail"]

    evs = _mech_events(repo)
    assert len(evs) >= 1
    p = evs[0].payload
    assert p["outcome"] == "failed"
    assert p["exit_code"] is None
    assert p["retried"] is False
    assert "must be a non-empty string" in p["error"]
    # Malformed config never triggers a fix-the-tests spawn; cascade may
    # re-spawn the implementer at a higher effort rung only.
    assert sum("test-fix" in str(c) for c in calls) == 0


def test_timeout_is_red_and_retried_once(repo: Path, monkeypatch) -> None:
    """A timed-out test command is a failure like any red run: retried once,
    then Blocked, with the timeout note in the detail. Also exercises the
    --verify-test-timeout CLI flag threading."""
    _write_dispatcher_config(
        repo, 'test: "echo TIMEOUT-MARKER; sleep 30"\n',
    )
    monkeypatch.setenv("FAKE_CLAUDE_SCENARIO", "done-tests-red")
    calls = _patch_spawn(monkeypatch)

    rc = orchestrator.execute(_args(repo, verify_test_timeout=1))
    assert rc == 1
    row = _row(repo)
    assert row["status"] == "Blocked"
    assert row["mechanical_verification"] == "failed"
    assert "timed out after 1s" in row["mechanical_verification_detail"]
    assert "TIMEOUT-MARKER" in row["mechanical_verification_detail"]

    evs = _mech_events(repo)
    assert len(evs) >= 2
    assert all(e.payload["outcome"] == "failed" for e in evs)
    assert all(e.payload["exit_code"] is None for e in evs)
    assert 2 <= len(calls) <= 8


def test_fix_retry_spawn_failure_verdict_from_rerun(repo: Path, monkeypatch) -> None:
    """A raising fix-retry spawn must not decide the verdict: the test
    command is re-run regardless, and a green re-run lands Done even though
    the retry spawn exploded."""
    _write_dispatcher_config(repo, 'test: "test -f tests-green.txt"\n')
    monkeypatch.setenv("FAKE_CLAUDE_SCENARIO", "done-tests-red")

    def hook(call_n: int, cwd: Path) -> None:
        if call_n == 2:
            # The fix retry: simulate a Tasker that DID fix the suite (the
            # green file appears in the worktree) but whose session crashed.
            (cwd / "tests-green.txt").write_text("fixed\n", encoding="utf-8")
            raise RuntimeError("simulated retry-spawn crash")

    calls = _patch_spawn(monkeypatch, hook=hook)

    rc = orchestrator.execute(_args(repo))
    assert rc == 0, "verdict must come from the re-run, not the spawn outcome"
    row = _row(repo)
    assert row["status"] == "Done"
    assert row["mechanical_verification"] == "passed"

    evs = _mech_events(repo)
    assert len(evs) == 2
    assert evs[0].payload["outcome"] == "failed"
    assert evs[1].payload["outcome"] == "passed"
    assert evs[1].payload["retried"] is True
    assert len(calls) == 2


def test_non_done_summary_never_runs_gate(repo: Path, monkeypatch) -> None:
    """A non-Done outcome (Escalated) never evaluates the gate: no row stamp,
    no verification_mechanical event — even with a config present."""
    _write_dispatcher_config(repo, 'test: "true"\n')
    monkeypatch.setenv("FAKE_CLAUDE_SCENARIO", "escalated")
    _patch_spawn(monkeypatch)

    rc = orchestrator.execute(_args(repo))
    assert rc == 1
    row = _row(repo)
    assert row["status"] == "Escalated"
    assert "mechanical_verification" not in row
    assert _mech_events(repo) == []


def test_long_output_tail_capped_everywhere(repo: Path, monkeypatch) -> None:
    """Output far beyond the cap: only the tail reaches the journal payload
    and the YAML detail."""
    # ~12k chars of noise, then the marker, then fail.
    _write_dispatcher_config(
        repo,
        "test: \"for i in $(seq 400); do echo noise-$i-aaaaaaaaaaaaaaaaaaaaaa; "
        "done; echo FINAL-TAIL-MARKER; false\"\n",
    )
    monkeypatch.setenv("FAKE_CLAUDE_SCENARIO", "done-tests-red")
    _patch_spawn(monkeypatch)

    rc = orchestrator.execute(_args(repo))
    assert rc == 1
    row = _row(repo)
    detail = row["mechanical_verification_detail"]
    assert len(detail) <= mv.TAIL_CHARS + 100
    assert "FINAL-TAIL-MARKER" in detail

    for e in _mech_events(repo):
        assert len(e.payload["output_tail"]) <= mv.TAIL_CHARS + 100
        assert "FINAL-TAIL-MARKER" in e.payload["output_tail"]
