"""Tests for `dispatcher resume` (ported from PR #10 / DISP-11 onto the
canonical hash-chained journal).

Covers:
  - clean no-op on a completed run
  - missing-journal / missing-genesis error handling
  - the liveness guard (refuse on a fresh journal, override with --force)
  - the `mark-blocked` strategy
  - the resume_started event linking back to the prior genesis
  - the headline acceptance case: a kill -9 mid-run leaves a row In Progress,
    and resume drives the run to the SAME final YAML as an uninterrupted run.

Note on the canonical journal: it is hash-chained, so we cannot fabricate a
stale journal by rewriting timestamps on disk (that breaks every hash and
Journal.resume's verify would reject it). Instead we seed the genesis with an
injected `clock` returning an old timestamp — the chain is then valid AND old,
so the liveness guard sees it as stale.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path

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
        "--claude-extra-args=--permission-mode bypassPermissions",
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


def _seed_genesis(repo: Path, run_id: str, *, clock=None):
    """Write a canonical genesis (run_started carrying run_config) for `run_id`,
    optionally with an injected `clock` so the chain is valid but timestamped in
    the past (for the stale-journal path). Returns the open Journal."""
    args = _run_args(repo, run_id)
    cfg = orchestrator._build_config(args)
    run_config = orchestrator._genesis_config(args, cfg)
    journal_path = repo / "_runs" / run_id / journal_mod.JOURNAL_FILENAME
    create_kwargs = {"clock": clock} if clock is not None else {}
    return journal_mod.Journal.create(
        journal_path,
        tasks_yaml_path=repo / "tasks.yaml",
        reviewer_prompts_dir=repo,  # any directory hash_tree can walk
        run_id=run_id,
        run_config=run_config,
        **create_kwargs,
    )


def _set_status(yaml_path: Path, key: str, status: str) -> None:
    doc = yaml_io.load(yaml_path)
    next(t for t in doc["tasks"] if t["key"] == key)["status"] = status
    yaml_io.dump(doc, yaml_path)


def _statuses(yaml_path: Path) -> dict[str, str]:
    doc = yaml_io.load(yaml_path)
    return {t["key"]: t.get("status") for t in doc["tasks"]}


def _old_clock(seconds_ago: int):
    """A clock returning a fixed timestamp `seconds_ago` in the past."""
    stamp = (dt.datetime.now(dt.timezone.utc)
             - dt.timedelta(seconds=seconds_ago)).astimezone().isoformat(timespec="seconds")
    return lambda: stamp


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


def test_genesis_config_excludes_notifier_secrets(tmp_path: Path) -> None:
    """Notifier credentials passed on argv must NOT be persisted into the
    hash-covered genesis run_config (a secret-at-rest leak that cannot be
    redacted once chained)."""
    repo = _make_repo(tmp_path)
    args = _run_args(repo, "R-sec",
                     slack_webhook_url="https://hooks.example/secret",
                     ntfy_topic="super-secret-topic",
                     ntfy_server="https://ntfy.example")
    cfg = orchestrator._build_config(args)
    config = orchestrator._genesis_config(args, cfg)
    assert "slack_webhook_url" not in config
    assert "ntfy_topic" not in config
    assert "ntfy_server" not in config
    # Non-secret args still round-trip.
    assert config["mode"] == "unattended"
    assert config["run_id"] == "R-sec"

    # And it never reaches the on-disk journal payload.
    j = journal_mod.Journal.create(
        repo / "_runs" / "R-sec" / journal_mod.JOURNAL_FILENAME,
        tasks_yaml_path=repo / "tasks.yaml",
        reviewer_prompts_dir=repo,
        run_id="R-sec",
        run_config=config,
    )
    payload = list(journal_mod.read_events(j.path))[0].payload
    serialized = json.dumps(payload)
    assert "super-secret-topic" not in serialized
    assert "hooks.example" not in serialized


def test_resume_missing_journal_errors(tmp_path: Path) -> None:
    rc = resume.execute(_resume_args(tmp_path, "no-such-run"))
    assert rc == 2


def test_resume_missing_genesis_errors(tmp_path: Path) -> None:
    """A journal whose first event is not a run_started genesis → exit 2."""
    run_dir = tmp_path / "R-x"
    run_dir.mkdir()
    # Hand-write a well-formed (parseable) but non-genesis first event; the
    # canonical writer would refuse to put a non-run_started event at seq 0,
    # so we craft the file directly.
    ev = {
        "seq": 0, "timestamp": "2026-01-01T00:00:00+00:00",
        "event_type": "heartbeat", "task_key": None, "payload": {},
        "prev_hash": journal_mod.GENESIS_PREV_HASH, "hash": "deadbeef",
    }
    (run_dir / journal_mod.JOURNAL_FILENAME).write_text(
        json.dumps(ev) + "\n", encoding="utf-8")
    rc = resume.execute(_resume_args(tmp_path, "R-x"))
    assert rc == 2


def test_resume_missing_run_config_errors(tmp_path: Path) -> None:
    """A genesis without an embedded run_config can't be replayed → exit 2."""
    repo = _make_repo(tmp_path)
    # Seed a genesis the normal way then re-create one WITHOUT run_config by
    # using the lower-level create (no run_config kwarg).
    journal_path = repo / "_runs" / "R-noc" / journal_mod.JOURNAL_FILENAME
    journal_mod.Journal.create(
        journal_path,
        tasks_yaml_path=repo / "tasks.yaml",
        reviewer_prompts_dir=repo,
        run_id="R-noc",
    )
    rc = resume.execute(_resume_args(repo / "_runs", "R-noc", force=True))
    assert rc == 2


# --- liveness guard ---------------------------------------------------------


def test_resume_refuses_when_run_looks_active(tmp_path: Path, capsys) -> None:
    """A fresh journal (recent last event) with work outstanding → refuse
    without --force; the message points the user at --force."""
    repo = _make_repo(tmp_path)
    j = _seed_genesis(repo, "R-live")  # default clock → fresh
    j.append(journal_mod.EventType.task_started, {}, task_key="SMOKE-A")
    _set_status(repo / "tasks.yaml", "SMOKE-A", "In Progress")

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
    j = _seed_genesis(repo, "R-stale",
                      clock=_old_clock(resume.RUN_ACTIVE_THRESHOLD_SECONDS + 60))
    j.append(journal_mod.EventType.task_started, {}, task_key="SMOKE-A")
    _set_status(repo / "tasks.yaml", "SMOKE-A", "In Progress")

    rc = resume.execute(_resume_args(repo / "_runs", "R-stale"))  # no --force
    assert rc == 0
    assert _statuses(repo / "tasks.yaml") == {
        "SMOKE-A": "Done", "SMOKE-B": "Done", "SMOKE-C": "Done"}


def test_resume_force_overrides_liveness_guard(tmp_path: Path, monkeypatch) -> None:
    """--force resumes even with a fresh journal, and links the resume_started
    event back to the genesis by run-id and chain hash."""
    repo = _make_repo(tmp_path)
    _patch_spawn(monkeypatch)
    j = _seed_genesis(repo, "R-force")  # fresh
    genesis_hash = j.last_hash
    _set_status(repo / "tasks.yaml", "SMOKE-A", "In Progress")

    rc = resume.execute(_resume_args(repo / "_runs", "R-force", force=True))
    assert rc == 0
    assert _statuses(repo / "tasks.yaml") == {
        "SMOKE-A": "Done", "SMOKE-B": "Done", "SMOKE-C": "Done"}

    # The resume_started event linked back to the genesis run, and the chain
    # is still valid end-to-end.
    journal_path = repo / "_runs" / "R-force" / journal_mod.JOURNAL_FILENAME
    assert journal_mod.verify(journal_path).ok
    events = list(journal_mod.read_events(journal_path))
    resume_ev = next(e for e in events
                     if e.event_type == journal_mod.EventType.resume_started.value)
    assert resume_ev.payload["genesis_run_id"] == "R-force"
    assert resume_ev.payload["genesis_hash"] == genesis_hash
    assert "SMOKE-A" in resume_ev.payload["in_progress"]


# --- strategies -------------------------------------------------------------


def test_resume_mark_blocked_strategy(tmp_path: Path, monkeypatch) -> None:
    """--strategy mark-blocked blocks the In Progress row instead of
    re-dispatching it, then runs the rest."""
    repo = _make_repo(tmp_path)
    _patch_spawn(monkeypatch)
    _seed_genesis(repo, "R-mb")
    _set_status(repo / "tasks.yaml", "SMOKE-B", "In Progress")

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

    # This test spawns a REAL dispatcher subprocess. Under dogfood, the test
    # suite itself runs inside a dispatcher session, so the outer session's
    # contract env (TASK_KEY, SUMMARY_PATH, ...) would otherwise leak into
    # the child — and fake_claude would overwrite the real session's summary
    # and commit into the developer's checkout. Strip every dispatcher
    # contract / fake_claude var before setting this test's own, and pin
    # cwd to tmp_path so nothing the child does can land in the real repo.
    _leaky = {"TASK_KEY", "SUMMARY_PATH", "DISPATCHER_RUN_ID", "MAX_ITERATIONS"}
    env = {k: v for k, v in os.environ.items()
           if k not in _leaky and not k.startswith("FAKE_CLAUDE_")}
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
         "--cross-family-panel", "never",
         "--claude-extra-args=--permission-mode bypassPermissions"],
        cwd=str(tmp_path), env=env, capture_output=True, text=True, timeout=120,
    )
    # The dispatcher was killed by SIGKILL → negative returncode.
    assert proc.returncode < 0, (
        f"expected dispatcher to be killed, got rc={proc.returncode}\n"
        f"stdout={proc.stdout}\nstderr={proc.stderr}")

    interrupted = _statuses(repo / "tasks.yaml")
    assert interrupted["SMOKE-A"] == "Done"
    assert interrupted["SMOKE-B"] == "In Progress"

    # Genesis was written before any dispatch, carrying the run_config.
    journal_path = repo / "_runs" / "KILLED" / journal_mod.JOURNAL_FILENAME
    events = list(journal_mod.read_events(journal_path))
    assert events[0].event_type == "run_started"
    assert "run_config" in events[0].payload

    # 3. Resume (in-process; fake_claude runs normally — no KILL_KEY in env).
    _patch_spawn(monkeypatch)
    rc = resume.execute(_resume_args(repo / "_runs", "KILLED", force=True))
    assert rc == 0, "resume should complete the remaining tasks"

    resumed = _statuses(repo / "tasks.yaml")
    assert resumed == golden, (
        f"resumed YAML {resumed} should match uninterrupted {golden}")

    # The continued chain still verifies end-to-end.
    assert journal_mod.verify(journal_path).ok
