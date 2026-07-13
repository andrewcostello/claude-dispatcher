"""Orchestrator → event-journal wiring (DISP-9).

These tests drive the live-spawn dispatch loop through the fake_claude
binary (no real LLM tasker) and assert that the orchestrator emits a
chain-verified journal whose event sequence matches the task lifecycle.

Acceptance coverage:
  - A full fake-claude run produces a journal whose event sequence matches
    the lifecycle, chain-verified end to end (`verify().ok`).
  - A panel-blocked run and a malformed-summary run emit the corresponding
    events with their *reasons* carried in the payloads.
  - A journal-creation failure degrades to a stderr warning and the run
    still completes (journaling is best-effort, never load-bearing).
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from claude_dispatcher import (
    cross_family_reviewer as cfr,
    journal as journal_mod,
    orchestrator,
    spawn as spawn_mod,
    yaml_io,
)
from claude_dispatcher.cli import build_parser


FIXTURE_DIR = Path(__file__).parent / "fixtures"
FAKE_CLAUDE = FIXTURE_DIR / "fake_claude.py"


# --- repo + harness ---------------------------------------------------------


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A git repo seeded with the three-task smoke fixture.

    Nested under tmp_path/"repo" so that ``repo.parent`` (the worktree base
    used by `_args`) is unique per test — otherwise sibling tests sharing
    SMOKE-* keys would collide on the same `worktree-SMOKE-A` directory.
    """
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
    # With --auto-integrate, auto_integrate.integrate() pristines the working
    # tree (`git clean -fd`) before merging; that removes any untracked,
    # non-ignored path — which would wipe the dispatcher's `_runs/` dir mid-run
    # and make the next `_log` fail with FileNotFoundError. Production keeps the
    # runs dir gitignored (see the auto_integrate `git clean -fd` comment, which
    # lists `docs/runs` among the preserved ignored paths), so mirror that.
    (repo_dir / ".gitignore").write_text("_runs/\n", encoding="utf-8")
    (repo_dir / "tasks.yaml").write_text(
        (FIXTURE_DIR / "three_task.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "."], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=repo_dir,
                   check=True, capture_output=True)
    return repo_dir


def _seed_yaml(repo: Path, content: str) -> None:
    (repo / "tasks.yaml").write_text(content, encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-q", "-m", "seed"], cwd=repo,
                   check=True, capture_output=True)


def _args(repo: Path, **overrides):
    parser = build_parser()
    argv = [
        "run", str(repo / "tasks.yaml"),
        "--mode", "unattended", "--max-parallel", "1",
        "--max-iterations", "2",
        "--run-id", "journal-test",
        "--runs-dir", str(repo / "_runs"),
        "--worktree-base", str(repo.parent / "wt"),
        "--claude-bin", sys.executable,
        # Preflight-clean: the journal harness runs WITH preflight enabled.
        "--claude-extra-args=--permission-mode bypassPermissions",
    ]
    for k, v in overrides.items():
        if v is None:
            continue
        flag = f"--{k.replace('_', '-')}"
        if v is True:        # store_true flag (e.g. --auto-integrate)
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
    return repo / "_runs" / "journal-test" / journal_mod.JOURNAL_FILENAME


def _events(repo: Path) -> list[journal_mod.JournalEvent]:
    return list(journal_mod.read_events(_journal_path(repo)))


def _types(events) -> list[str]:
    return [e.event_type for e in events]


def _types_for(events, task_key: str) -> list[str]:
    return [e.event_type for e in events if e.task_key == task_key]


# --- panel stub (mirrors test_orchestrator_panel) ---------------------------


_CRITICAL_TASK_YAML = """\
project: TEST
epic: J

tasks:
  - key: J-CRIT
    summary: "journal-test: high-risk ticket"
    description: A high-risk ticket; the cross-family panel fires under auto.
    type: Task
    estimate: 5m
    labels: [size:XS, risk:critical]
"""

_APPROVE_OUTPUT = textwrap.dedent("""\
    ## Verdict
    APPROVE

    ## Dimension scores
    - Correctness: 5
    - Security: 5
    - Compliance: 5
    - Resilience: 4
    - Idempotency: 4
    - Observability: 4
    - Performance: 4
    - Maintainability: 4

    ## Findings
""")

_CHANGES_REQUESTED_OUTPUT = textwrap.dedent("""\
    ## Verdict
    CHANGES_REQUESTED

    ## Dimension scores
    - Correctness: 3
    - Security: 4
    - Compliance: 4
    - Resilience: 4
    - Idempotency: 4
    - Observability: 4
    - Performance: 4
    - Maintainability: 4

    ## Findings

    ### HIGH: apps/wallet/service.go:42
    Description: Concurrent debit path lacks SELECT FOR UPDATE; the race
    can drive the balance negative under contention.
    Fix: Wrap the debit in a row-level lock.
""")


class _StubReviewer(cfr.Reviewer):
    def __init__(self, family: str, output: str) -> None:
        super().__init__()
        self.family = family
        self._output = output

    def _invoke_cli(self, prompt: str) -> str:
        return self._output


@pytest.fixture(autouse=True)
def _reset_reviewers():
    orchestrator.set_panel_reviewers(None)
    yield
    orchestrator.set_panel_reviewers(None)


# --- acceptance 1: full run, chain-verified lifecycle sequence --------------


def test_full_run_journal_chain_and_sequence(repo: Path, monkeypatch) -> None:
    """A clean three-task run produces a chain-verified journal whose event
    sequence matches the lifecycle."""
    _patch_spawn(monkeypatch)
    rc = orchestrator.execute(_args(repo))
    assert rc == 0

    jpath = _journal_path(repo)
    assert jpath.exists(), "journal.jsonl must be written next to run.log"

    # Chain integrity: hashes link, seqs run 0..N-1, genesis is well-formed.
    result = journal_mod.verify(jpath)
    assert result.ok, f"journal failed verification: {result.error} @ {result.error_seq}"

    events = _events(repo)
    types = _types(events)

    # Genesis is run_started carrying this run's provenance + run_id.
    assert events[0].event_type == "run_started"
    assert events[0].seq == 0
    assert events[0].payload["run_id"] == "journal-test"
    for key in journal_mod.GENESIS_PROVENANCE_KEYS:
        assert key in events[0].payload

    # Terminal event is run_complete with the run tallies.
    assert types[-1] == "run_complete"
    assert events[-1].payload["done"] == 3
    assert events[-1].payload["blocked"] == 0

    # Each task contributes its lifecycle subsequence, in order. These tasks
    # carry no risk labels, so no panel fires.
    for key in ("SMOKE-A", "SMOKE-B", "SMOKE-C"):
        assert _types_for(events, key) == [
            "task_started",
            "task_spawn_finished",
            "summary_parsed",
            "verification_mechanical",  # no .dispatcher.yaml → skipped
            "verification_started",     # VG-4 LLM verifier (VERIFIED stub)
            "task_spawn_finished",      # verifier spawn (cost folds into rollup)
            "verification_verdict",
            "push_verify",     # no remote in the fixture → skipped-no-remote
            "task_done",
        ], f"unexpected lifecycle for {key}"

    # Dependency ordering is reflected: SMOKE-A starts before SMOKE-C.
    assert types.index("task_started") < len(types)
    a_start = next(i for i, e in enumerate(events)
                   if e.event_type == "task_started" and e.task_key == "SMOKE-A")
    c_start = next(i for i, e in enumerate(events)
                   if e.event_type == "task_started" and e.task_key == "SMOKE-C")
    assert a_start < c_start

    # The spawn-finished event carries the usage/cost payload shape (values
    # may be None when the fake CLI emits no JSON usage block).
    spawn_ev = next(e for e in events if e.event_type == "task_spawn_finished")
    for field in ("exit_code", "cost_usd", "input_tokens", "output_tokens",
                  "duration_ms", "num_turns", "model"):
        assert field in spawn_ev.payload
    assert spawn_ev.payload["exit_code"] == 0

    # summary_parsed records the parsed status.
    parsed_ev = next(e for e in events if e.event_type == "summary_parsed")
    assert parsed_ev.payload["status"] == "Done"
    assert parsed_ev.payload["malformed"] is False


def test_single_task_exact_sequence(repo: Path, monkeypatch) -> None:
    """Pin the exact global event order for a single Done task (incl. the
    run-complete notify_sent that precedes the terminal run_complete)."""
    _patch_spawn(monkeypatch)
    rc = orchestrator.execute(_args(repo, only="SMOKE-A"))
    assert rc == 0
    assert _types(_events(repo)) == [
        "run_started",
        "preflight",       # run-start preflight outcome (OPS-3)
        "task_started",
        "task_spawn_finished",
        "summary_parsed",
        "verification_mechanical",  # no .dispatcher.yaml → skipped
        "verification_started",     # VG-4 LLM verifier (VERIFIED stub)
        "task_spawn_finished",      # verifier spawn (cost folds into rollup)
        "verification_verdict",
        "push_verify",     # no remote in the fixture → skipped-no-remote
        "task_done",
        "notify_sent",     # run-complete rollup notification
        "run_complete",
    ]


# --- acceptance 2a: malformed summary -> reason in payload ------------------


def test_malformed_summary_events_and_reason(repo: Path, monkeypatch) -> None:
    monkeypatch.setenv("FAKE_CLAUDE_SCENARIO", "blocked-malformed")
    _patch_spawn(monkeypatch)
    rc = orchestrator.execute(_args(repo, only="SMOKE-A"))
    assert rc == 1

    assert journal_mod.verify(_journal_path(repo)).ok
    events = _events(repo)

    parsed = next(e for e in events if e.event_type == "summary_parsed")
    assert parsed.payload["malformed"] is True
    # DISP-3 reasons ride along so the journal explains *why* it was rejected.
    assert parsed.payload["problems"], "malformed parse must carry problems"
    assert any("status" in p.lower() for p in parsed.payload["problems"])

    blocked = next(e for e in events if e.event_type == "task_blocked")
    assert "summary_malformed" in blocked.payload["reason"]
    # No task_done for a blocked task.
    assert "task_done" not in _types_for(events, "SMOKE-A")


# --- acceptance 2b: panel block -> verdict event with reason ----------------


def test_panel_block_events_and_reason(repo: Path, monkeypatch) -> None:
    _seed_yaml(repo, _CRITICAL_TASK_YAML)
    _patch_spawn(monkeypatch)
    # J-CRIT panel:
    # the corroboration gate needs >=2 available families to raise a blocking
    # HIGH, so both surviving families (gemini, codex) must dissent to block.
    orchestrator.set_panel_reviewers([
        _StubReviewer("gemini", _CHANGES_REQUESTED_OUTPUT),
        _StubReviewer("codex", _CHANGES_REQUESTED_OUTPUT),
    ])

    rc = orchestrator.execute(_args(repo, only="J-CRIT", cross_family_panel="auto"))
    assert rc == 1, "corroborated dissent must block the task"

    assert journal_mod.verify(_journal_path(repo)).ok
    events = _events(repo)
    types = _types_for(events, "J-CRIT")

    assert "panel_started" in types
    verdict = next(e for e in events if e.event_type == "panel_verdict")
    assert verdict.payload["consensus"] == "block"
    assert verdict.payload["verdicts"]["gemini"] == "CHANGES_REQUESTED"
    # The blocking finding's location is carried so the reason is
    # reconstructable from the journal alone.
    assert verdict.payload["blocking_locations"], "block must record finding locations"
    assert any("service.go" in loc for loc in verdict.payload["blocking_locations"])

    blocked = next(e for e in events if e.event_type == "task_blocked")
    assert "cross_family_panel" in blocked.payload["reason"]


# --- acceptance 3: journal failure degrades to a warning --------------------


def test_journal_creation_failure_does_not_abort_run(
    repo: Path, monkeypatch, capsys,
) -> None:
    """If the journal cannot be created, the run still completes; a warning
    is emitted and cfg.journal stays None (every later emit is a no-op)."""
    _patch_spawn(monkeypatch)

    def boom(*a, **k):
        raise OSError("simulated unwritable journal dir")

    monkeypatch.setattr(journal_mod.Journal, "create", staticmethod(boom))

    rc = orchestrator.execute(_args(repo, only="SMOKE-A"))
    assert rc == 0, "run must complete even when journaling fails"

    # No journal file, and the task still landed Done.
    assert not _journal_path(repo).exists()
    doc = yaml_io.load(repo / "tasks.yaml")
    row = next(t for t in doc["tasks"] if t["key"] == "SMOKE-A")
    assert row["status"] == "Done"

    # The failure surfaced as a stderr warning, not an exception.
    assert "journal creation failed" in capsys.readouterr().err


# --- additional lifecycle points: commit_retry, pr_gate, integrate_result --


def test_commit_retry_event(repo: Path, monkeypatch) -> None:
    """A Done-but-uncommitted first spawn triggers a commit_retry event, and
    a second summary_parsed (flagged after_commit_retry)."""
    monkeypatch.setenv("FAKE_CLAUDE_SCENARIO", "done-commit-retry")
    _patch_spawn(monkeypatch)
    rc = orchestrator.execute(_args(repo, only="SMOKE-A"))
    assert rc == 0

    assert journal_mod.verify(_journal_path(repo)).ok
    events = _events(repo)

    retry = next(e for e in events if e.event_type == "commit_retry")
    assert retry.payload["outcome"] == "committed"
    # Two summary_parsed events: the initial parse + the post-retry re-parse.
    parses = [e for e in events if e.event_type == "summary_parsed"]
    assert len(parses) == 2
    assert parses[1].payload["after_commit_retry"] is True
    assert "task_done" in _types_for(events, "SMOKE-A")


def test_pr_gate_event_unattended_deferral(repo: Path, monkeypatch) -> None:
    """The human PR gate trips in unattended mode → pr_gate(deferred) +
    task_blocked, run continues."""
    monkeypatch.setenv("FAKE_CLAUDE_SCENARIO", "awaiting-human-pr")
    _patch_spawn(monkeypatch)
    rc = orchestrator.execute(_args(repo, only="SMOKE-A"))
    assert rc == 1

    assert journal_mod.verify(_journal_path(repo)).ok
    events = _events(repo)

    gate = next(e for e in events if e.event_type == "pr_gate")
    assert gate.payload["decision"] == "deferred-unattended"
    assert gate.payload["mode"] == "unattended"
    assert gate.payload["pr_branch"] == "feat/SMOKE-A-smoke-test"

    blocked = next(e for e in events if e.event_type == "task_blocked")
    assert "awaiting human PR approval" in blocked.payload["reason"]


def test_integrate_result_event(repo: Path, monkeypatch) -> None:
    """With --auto-integrate, a Done task emits an integrate_result event
    carrying the integration status."""
    _patch_spawn(monkeypatch)
    rc = orchestrator.execute(_args(repo, only="SMOKE-A", auto_integrate=True))
    assert rc == 0

    assert journal_mod.verify(_journal_path(repo)).ok
    events = _events(repo)

    integ = next(e for e in events if e.event_type == "integrate_result")
    assert integ.payload["status"] == "integrated"
    assert "task_done" in _types_for(events, "SMOKE-A")


def test_emit_event_swallows_append_failure(repo: Path, monkeypatch, capsys) -> None:
    """A mid-run append failure warns to stderr and does not propagate."""
    _patch_spawn(monkeypatch)

    real_create = journal_mod.Journal.create
    created = {}

    def make_flaky(*a, **k):
        j = real_create(*a, **k)

        def flaky_append(*aa, **kk):
            raise OSError("disk full mid-run")

        monkeypatch.setattr(j, "append", flaky_append)
        created["j"] = j
        return j

    monkeypatch.setattr(journal_mod.Journal, "create", staticmethod(make_flaky))

    rc = orchestrator.execute(_args(repo, only="SMOKE-A"))
    assert rc == 0, "append failures must never crash the run"
    assert "journal append failed" in capsys.readouterr().err
