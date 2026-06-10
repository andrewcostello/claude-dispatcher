"""Tests for `dispatcher resume`.

Covers:
  - clean no-op on a completed run
  - missing-journal / missing-genesis error handling
  - the liveness guard (refuse on a fresh journal, override with --force)
  - the `mark-blocked` strategy
  - the headline acceptance case: a kill -9 mid-run leaves a row In Progress,
    and resume drives the run to the SAME final YAML as an uninterrupted run.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from claude_dispatcher import journal as journal_mod, orchestrator, resume
from claude_dispatcher import spawn as spawn_mod, yaml_io
from claude_dispatcher.cli import build_parser


FAKE_CLAUDE = Path(__file__).parent / "fixtures" / "fake_claude.py"
SRC_DIR = Path(__file__).resolve().parents[1] / "src"
THREE_TASK = Path(__file__).parent / "fixtures" / "three_task.yaml"


# --- shared helpers ---------------------------------------------------------


def _make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)],
                   check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test"],
                   cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"],
                   cwd=repo, check=True, capture_output=True)
    roles = repo / ".claude" / "workflow" / "roles"
    roles.mkdir(parents=True)
    (roles / "tasker.md").write_text("stub", encoding="utf-8")
    (repo / "tasks.yaml").write_text(THREE_TASK.read_text(), encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"],
                   cwd=repo, check=True, capture_output=True)
    return repo


def _patch_spawn(monkeypatch) -> None:
    """In-process spawn replacement that runs fake_claude (normal Done)."""
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


def _run_args(repo: Path, run_id: str, **overrides):
    parser = build_parser()
    argv = [
        "run", str(repo / "tasks.yaml"),
        "--mode", "unattended", "--max-parallel", "1",
        "--run-id", run_id,
        "--runs-dir", str(repo / "_runs"),
        "--worktree-base", str(repo.parent / "wt"),
        "--claude-bin", sys.executable,
        "--cross-family-panel", "never",
    ]
    for k, v in overrides.items():
        argv += [f"--{k.replace('_', '-')}", str(v)]
    return parser.parse_args(argv)


def _resume_args(runs_dir: Path, run_id: str, **overrides):
    parser = build_parser()
    argv = ["resume", run_id, "--runs-dir", str(runs_dir)]
    for k, v in overrides.items():
        if v is True:
            argv.append(f"--{k.replace('_', '-')}")
        elif v is not False and v is not None:
            argv += [f"--{k.replace('_', '-')}", str(v)]
    return parser.parse_args(argv)


def _statuses(yaml_path: Path) -> dict[str, str]:
    doc = yaml_io.load(yaml_path)
    return {t["key"]: t.get("status") for t in doc["tasks"]}


def _backdate_journal(journal_path: Path, seconds_ago: int) -> None:
    """Rewrite every event's ts to `seconds_ago` in the past so the liveness
    guard sees a stale journal."""
    old = (dt.datetime.now(dt.timezone.utc)
           - dt.timedelta(seconds=seconds_ago)).isoformat(timespec="seconds")
    lines = journal_path.read_text(encoding="utf-8").splitlines()
    out = []
    for line in lines:
        if not line.strip():
            continue
        ev = json.loads(line)
        ev["ts"] = old
        out.append(json.dumps(ev))
    journal_path.write_text("\n".join(out) + "\n", encoding="utf-8")


# --- no-op / error paths ----------------------------------------------------


def test_resume_completed_run_is_noop(tmp_path: Path, monkeypatch, capsys) -> None:
    """A fully-completed run resumes to a clean no-op with a clear message."""
    repo = _make_repo(tmp_path)
    _patch_spawn(monkeypatch)
    rc = orchestrator.execute(_run_args(repo, "R-done"))
    assert rc == 0
    assert _statuses(repo / "tasks.yaml") == {
        "SMOKE-A": "Done", "SMOKE-B": "Done", "SMOKE-C": "Done"}

    capsys.readouterr()  # drop run output
    rc = resume.execute(_resume_args(repo / "_runs", "R-done", force=True))
    assert rc == 0
    out = capsys.readouterr().out
    assert "already complete" in out
    assert "nothing to resume" in out
    # Statuses untouched.
    assert _statuses(repo / "tasks.yaml") == {
        "SMOKE-A": "Done", "SMOKE-B": "Done", "SMOKE-C": "Done"}


def test_resume_missing_journal_errors(tmp_path: Path) -> None:
    rc = resume.execute(_resume_args(tmp_path, "no-such-run"))
    assert rc == 2


def test_resume_missing_genesis_errors(tmp_path: Path) -> None:
    run_dir = tmp_path / "R-x"
    run_dir.mkdir()
    j = journal_mod.Journal(run_dir / "journal.jsonl")
    j.append(journal_mod.HEARTBEAT)  # events but no run_started
    rc = resume.execute(_resume_args(tmp_path, "R-x"))
    assert rc == 2


# --- liveness guard ---------------------------------------------------------


def test_resume_refuses_when_run_looks_active(tmp_path: Path, monkeypatch, capsys) -> None:
    """A fresh journal (recent last event) with work outstanding → refuse
    without --force; the message points the user at --force."""
    repo = _make_repo(tmp_path)
    # Build a genesis + an In Progress row, with a fresh (just-now) journal.
    run_dir = repo / "_runs" / "R-live"
    run_dir.mkdir(parents=True)
    args = _run_args(repo, "R-live")
    j = journal_mod.Journal(run_dir / "journal.jsonl")
    j.append(journal_mod.RUN_STARTED, run_id="R-live", mode="unattended",
             tasks_yaml=str(repo / "tasks.yaml"), base_branch="main",
             config=orchestrator._genesis_config(args, orchestrator._build_config(args)))
    j.append(journal_mod.TASK_DISPATCHED, key="SMOKE-A")
    # Mark SMOKE-A In Progress so there is something to resume.
    doc = yaml_io.load(repo / "tasks.yaml")
    next(t for t in doc["tasks"] if t["key"] == "SMOKE-A")["status"] = "In Progress"
    yaml_io.dump(doc, repo / "tasks.yaml")

    rc = resume.execute(_resume_args(repo / "_runs", "R-live"))
    assert rc == 4
    err = capsys.readouterr().err
    assert "still active" in err
    assert "--force" in err
    # Nothing was dispatched — the row is still In Progress.
    assert _statuses(repo / "tasks.yaml")["SMOKE-A"] == "In Progress"


def test_resume_stale_journal_resumes_without_force(tmp_path: Path, monkeypatch) -> None:
    """A journal whose last event aged past the threshold (a dead run) resumes
    with no --force needed."""
    repo = _make_repo(tmp_path)
    _patch_spawn(monkeypatch)
    run_dir = repo / "_runs" / "R-stale"
    run_dir.mkdir(parents=True)
    args = _run_args(repo, "R-stale")
    j = journal_mod.Journal(run_dir / "journal.jsonl")
    j.append(journal_mod.RUN_STARTED, run_id="R-stale", mode="unattended",
             tasks_yaml=str(repo / "tasks.yaml"), base_branch="main",
             config=orchestrator._genesis_config(args, orchestrator._build_config(args)))
    j.append(journal_mod.TASK_DISPATCHED, key="SMOKE-A")
    doc = yaml_io.load(repo / "tasks.yaml")
    next(t for t in doc["tasks"] if t["key"] == "SMOKE-A")["status"] = "In Progress"
    yaml_io.dump(doc, repo / "tasks.yaml")
    # Age every event well past the guard window.
    _backdate_journal(run_dir / "journal.jsonl",
                      resume.RUN_ACTIVE_THRESHOLD_SECONDS + 60)

    rc = resume.execute(_resume_args(repo / "_runs", "R-stale"))  # no --force
    assert rc == 0
    assert _statuses(repo / "tasks.yaml") == {
        "SMOKE-A": "Done", "SMOKE-B": "Done", "SMOKE-C": "Done"}


def test_resume_force_overrides_liveness_guard(tmp_path: Path, monkeypatch) -> None:
    """--force resumes even with a fresh journal."""
    repo = _make_repo(tmp_path)
    _patch_spawn(monkeypatch)
    run_dir = repo / "_runs" / "R-force"
    run_dir.mkdir(parents=True)
    args = _run_args(repo, "R-force")
    j = journal_mod.Journal(run_dir / "journal.jsonl")
    j.append(journal_mod.RUN_STARTED, run_id="R-force", mode="unattended",
             tasks_yaml=str(repo / "tasks.yaml"), base_branch="main",
             config=orchestrator._genesis_config(args, orchestrator._build_config(args)))
    doc = yaml_io.load(repo / "tasks.yaml")
    next(t for t in doc["tasks"] if t["key"] == "SMOKE-A")["status"] = "In Progress"
    yaml_io.dump(doc, repo / "tasks.yaml")

    rc = resume.execute(_resume_args(repo / "_runs", "R-force", force=True))
    assert rc == 0
    assert _statuses(repo / "tasks.yaml") == {
        "SMOKE-A": "Done", "SMOKE-B": "Done", "SMOKE-C": "Done"}
    # The resume_started event linked back to the genesis run.
    events = j.read()
    resume_ev = next(e for e in events if e["event"] == journal_mod.RESUME_STARTED)
    assert resume_ev["genesis_run_id"] == "R-force"


# --- strategies -------------------------------------------------------------


def test_resume_mark_blocked_strategy(tmp_path: Path, monkeypatch) -> None:
    """--strategy mark-blocked blocks the In Progress row instead of
    re-dispatching it, then runs the rest."""
    repo = _make_repo(tmp_path)
    _patch_spawn(monkeypatch)
    run_dir = repo / "_runs" / "R-mb"
    run_dir.mkdir(parents=True)
    args = _run_args(repo, "R-mb")
    j = journal_mod.Journal(run_dir / "journal.jsonl")
    j.append(journal_mod.RUN_STARTED, run_id="R-mb", mode="unattended",
             tasks_yaml=str(repo / "tasks.yaml"), base_branch="main",
             config=orchestrator._genesis_config(args, orchestrator._build_config(args)))
    doc = yaml_io.load(repo / "tasks.yaml")
    next(t for t in doc["tasks"] if t["key"] == "SMOKE-B")["status"] = "In Progress"
    yaml_io.dump(doc, repo / "tasks.yaml")

    rc = resume.execute(_resume_args(repo / "_runs", "R-mb",
                                     force=True, strategy="mark-blocked"))
    # SMOKE-B blocked → partial completion exit.
    assert rc == 1
    statuses = _statuses(repo / "tasks.yaml")
    assert statuses["SMOKE-B"] == "Blocked"
    assert statuses["SMOKE-A"] == "Done"
    assert statuses["SMOKE-C"] == "Done"
    doc = yaml_io.load(repo / "tasks.yaml")
    row_b = next(t for t in doc["tasks"] if t["key"] == "SMOKE-B")
    assert "mark-blocked" in row_b.get("blocked_reason", "")


# --- headline acceptance: kill -9 mid-run -----------------------------------


def test_kill9_midrun_then_resume_matches_uninterrupted(tmp_path: Path, monkeypatch) -> None:
    """A real dispatcher subprocess is SIGKILL'd mid-run (fake_claude kills its
    parent on SMOKE-B). The YAML is left with SMOKE-A Done, SMOKE-B In Progress.
    `dispatcher resume --force` drives the run to completion, and the final YAML
    statuses match an uninterrupted run of the same fixture.
    """
    # 1. Golden uninterrupted run in a separate repo.
    golden_repo = _make_repo(tmp_path / "golden")
    _patch_spawn(monkeypatch)
    assert orchestrator.execute(_run_args(golden_repo, "GOLD")) == 0
    golden = _statuses(golden_repo / "tasks.yaml")
    assert golden == {"SMOKE-A": "Done", "SMOKE-B": "Done", "SMOKE-C": "Done"}

    # 2. Interrupted run as a real subprocess that gets SIGKILL'd on SMOKE-B.
    repo = _make_repo(tmp_path / "killed")
    fake_bin = tmp_path / "fake_claude_bin.py"
    fake_bin.write_text(FAKE_CLAUDE.read_text(), encoding="utf-8")
    fake_bin.chmod(0o755)

    env = dict(os.environ)
    env["PYTHONPATH"] = str(SRC_DIR)
    env["FAKE_CLAUDE_KILL_KEY"] = "SMOKE-B"
    env["FAKE_CLAUDE_SCENARIO"] = "done"
    proc = subprocess.run(
        [sys.executable, "-m", "claude_dispatcher", "run",
         str(repo / "tasks.yaml"),
         "--mode", "unattended", "--max-parallel", "1",
         "--run-id", "KILLED", "--runs-dir", str(repo / "_runs"),
         "--worktree-base", str(repo.parent / "wt"),
         "--claude-bin", str(fake_bin),
         "--cross-family-panel", "never"],
        env=env, capture_output=True, text=True, timeout=120,
    )
    # The dispatcher was killed by SIGKILL → negative returncode.
    assert proc.returncode < 0, (
        f"expected dispatcher to be killed, got rc={proc.returncode}\n"
        f"stdout={proc.stdout}\nstderr={proc.stderr}")

    interrupted = _statuses(repo / "tasks.yaml")
    assert interrupted["SMOKE-A"] == "Done"
    assert interrupted["SMOKE-B"] == "In Progress"

    # Genesis was written before any dispatch.
    j = journal_mod.Journal(repo / "_runs" / "KILLED" / "journal.jsonl")
    assert j.genesis() is not None

    # 3. Resume (in-process; fake_claude runs normally — no KILL_KEY in env).
    _patch_spawn(monkeypatch)
    rc = resume.execute(_resume_args(repo / "_runs", "KILLED", force=True))
    assert rc == 0, "resume should complete the remaining tasks"

    resumed = _statuses(repo / "tasks.yaml")
    assert resumed == golden, (
        f"resumed YAML {resumed} should match uninterrupted {golden}")
