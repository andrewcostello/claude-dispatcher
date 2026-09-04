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
from dataclasses import replace
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
            # D8 + P4 ruling on dispute P3-2, 2026-08-12. The role loop gate
            # journals on EVERY task, including when the run has it switched
            # off (`not_enabled`), which is what this fixture exercises — no
            # `--enable-role-loop-gate`. Emitting only when the gate RAN was
            # measured to leave the run's only append-only per-task record
            # unable to distinguish "gate off" from "every branch clean", and
            # the two substitutes (the YAML row stamp, run.log) are both erased
            # by `dispatcher unblock`. Sits here, before the mechanical gate,
            # because that is where the hook is: `_retry_for_test_fix` commits,
            # so a gate after it judges a diff two agents wrote.
            "role_diff_loop_gate",
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
        # D8 + P4 ruling on dispute P3-2, 2026-08-12. See the note on the
        # sibling row above: the loop gate journals per task whether or not the
        # run enabled it, because a status nobody can read after an unblock is
        # not a named state.
        "role_diff_loop_gate",
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


def test_a_rows_jira_key_reaches_the_dispatched_branch(repo: Path, monkeypatch) -> None:
    """END TO END: a row's `jira_key` must reach the branch the dispatcher
    actually creates.

    Sealed here rather than on TaskSnapshot because deleting the row->snapshot
    population SURVIVED a unit test that built the snapshot itself — the same
    correct-but-inert shape as the account rotation that never rotated and the
    known-red check nobody fed. evenplay-mono's CI requires the branch, the PR
    title and every commit to name the ticket; 26 of 26 dispatched PRs failed
    it.
    """
    monkeypatch.setenv("FAKE_CLAUDE_SCENARIO", "awaiting-human-pr")
    _patch_spawn(monkeypatch)
    _seed_yaml(repo, textwrap.dedent("""\
        project: SMOKE
        tasks:
          - key: SMOKE-A
            summary: smoke test
            description: d
            type: Task
            labels: [size:S]
            jira_key: SMG-4257
            status: To Do
        """))
    orchestrator.execute(_args(repo, only="SMOKE-A"))
    # The DISPATCHER-computed branch, stamped back on the row. Deliberately
    # not the pr_gate `pr_branch`: that is the agent's own proposal out of its
    # summary and would pass this test whatever the dispatcher did.
    from claude_dispatcher import yaml_io
    doc = yaml_io.load(repo / "tasks.yaml")
    row = next(t for t in doc["tasks"] if t["key"] == "SMOKE-A")
    branch = row.get("branch")
    assert branch, f"no branch stamped on the row: {dict(row)}"
    assert branch.startswith("feat/SMG-4257-"), branch
    assert "SMOKE-A" in branch, "the dispatcher key must survive for audit"


# --- the operator's pin survives the run's observations --------------------


def test_requeue_keeps_the_pin_and_drops_the_observation() -> None:
    """`requeue` clears run state so the next attempt is fresh. The authored
    `model:` is NOT run state -- clearing it dispatches unpinned, which is how
    WAL-LEDGER-3 lost its routing three times.

    NOTE ON COVERAGE. The other half of this change -- the usage write-back
    recording `model_used` instead of overwriting `model` -- has NO test. It
    lives in an inline `_apply(row)` closure that cannot be called directly,
    and the fake CLI reports no usage, so the end-to-end fixture never reaches
    it. An assertion there passes whatever the code does, which is worse than
    no assertion; it was written, found vacuous, and removed rather than kept
    as false coverage. Verified by inspection only.
    """
    from claude_dispatcher import unblock
    assert "model" not in unblock.RUN_STATE_FIELDS, \
        "clearing the authored pin makes the next dispatch unpinned"
    assert "model_used" in unblock.RUN_STATE_FIELDS, \
        "the observed model IS run state and must be cleared"


# --- inheriting another model's work: fix it, or start over? ---------------


def test_cascade_context_offers_the_fix_or_restart_judgement() -> None:
    """A cascading model inherits the previous model's WORKTREE (created once,
    before the cascade loop) plus the review of it. So it is already in the
    position of a senior picking up junior work -- but the prompt only ever
    said "this was blocked, here are the findings", which reads as an
    instruction to patch.

    A model handed genuinely bad foundations then has no sanctioned way to say
    so, and patches around them instead. That is the force-fit the deviation
    model exists to prevent, so the choice has to be offered explicitly.

    Asserted over EVERY cascade-context builder, because the judgement is
    needed at each boundary -- a mechanical failure, a panel block, a verifier
    refusal -- not just the one that happened to be edited.
    """
    import inspect, re
    from claude_dispatcher import orchestrator as orch
    src = inspect.getsource(orch)
    builders = re.findall(
        r"cascade_context = \(\n(.*?)\n\s*\)", src, re.DOTALL)
    assert len(builders) >= 4, f"expected every builder, found {len(builders)}"
    missing = [i for i, b in enumerate(builders)
               if "CASCADE_JUDGEMENT" not in b]
    assert not missing, (
        f"{len(missing)} of {len(builders)} cascade-context builders do not "
        "offer the fix-or-restart judgement"
    )


def test_the_judgement_names_both_options_and_the_deviation_route() -> None:
    """It must be a real choice: keep and fix, or discard and rewrite -- and
    say that discarding is legitimate, since the default reading of 'here are
    the findings' is 'patch them'."""
    from claude_dispatcher import orchestrator as orch
    t = orch.CASCADE_JUDGEMENT.lower()
    assert "start over" in t or "rewrite" in t or "discard" in t
    assert "fix" in t or "keep" in t
    # Seal the ACTIONABLE clauses, which is where the force is. Renaming the
    # classification word alone is an equivalent mutant: "record it under
    # `## Deviation`" and "do not force-fit" both survive it and both carry
    # the instruction, so it changes nothing a model would do.
    assert "contract is wrong" in t, \
        "must tell the model that a wrong CONTRACT is not a code defect"
    assert "## deviation" in t, "must name the heading to record it under"
    assert "force-fit" in t, "must forbid patching around a wrong contract"


def test_the_role_gate_payload_names_the_signature_changes() -> None:
    """A gate that BLOCKS must name what it blocked on.

    Measured 2026-09-03: WAL-LEDGER-3's payload was
    `violations: []` with `detail: "0 forbidden path(s) and 4 changed
    scaffolded signature(s)"`. `violations` holds PATH violations only, so the
    four signature changes that actually caused the block appeared nowhere
    machine-readable — the count lived in a prose string. Neither the operator
    nor the next agent could tell WHICH four, and reconstructing them took a
    hand diff.
    """
    import inspect
    from claude_dispatcher import orchestrator as orch
    src = inspect.getsource(orch)
    i = src.index('"status": role_loop.status.value')
    payload = src[i:i + 1400]
    assert '"signature_changes"' in payload, (
        "the role-gate payload must carry the signature changes, not only the "
        "path violations"
    )


def test_a_cascaded_agent_is_forgotten_on_success() -> None:
    """The cascade stamps `agent` and, unlike `effort`, never un-stamps it.

    D-64 already ruled this for effort: "an effort the CASCADE chose is a
    consequence, not a choice, and it outlived its cause". `agent` needed the
    same and did not have it, so a task that cascaded codex -> claude kept
    agent=claude forever — and #89 protects `model`, so the row ends up
    agent=claude with model=gpt-5.6-sol. That is codex's model on the claude
    CLI, which fails or silently runs something else. Measured 2026-09-03 on
    WAL-LEDGER-3; I repaired it by hand three times before fixing it.

    On DONE only, exactly as effort: a task that ended Blocked keeps the
    escalation, because the next dispatch of something that failed on a
    weaker family should start on the stronger one.
    """
    from claude_dispatcher import orchestrator as orch
    from claude_dispatcher import plan as plan_mod

    # A cascade-chosen agent, stamped as such, is dropped on success.
    row = {"agent": "claude", orch.AGENT_ESCALATED_STAMP: True}
    orch._forget_escalated_effort(row, plan_mod.DONE)
    assert "agent" not in row, row
    assert orch.AGENT_ESCALATED_STAMP not in row

    # Blocked keeps it.
    row = {"agent": "claude", orch.AGENT_ESCALATED_STAMP: True}
    orch._forget_escalated_effort(row, plan_mod.BLOCKED)
    assert row["agent"] == "claude"

    # An author's own agent carries no stamp and is never touched.
    row = {"agent": "codex"}
    orch._forget_escalated_effort(row, plan_mod.DONE)
    assert row["agent"] == "codex", "a deliberate agent must survive"


def test_a_cascaded_agent_is_stamped_as_the_cascades_choice() -> None:
    """The forget only fires on a row that was STAMPED, so not stamping is a
    silent way to keep the cascade's agent forever.

    Sealing `_forget_escalated_effort` alone left that hole: removing the
    stamp survived mutation, because the forget test hands it a row with the
    stamp already set. This drives the closure the cascade actually runs.
    """
    import inspect, re
    from claude_dispatcher import orchestrator as orch
    src = inspect.getsource(orch)
    i = src.index("def _stamp_agent_effort(")
    block = src[i:i + 1600]
    assert "AGENT_ESCALATED_STAMP" in block, (
        "the cascade must record that IT chose the agent, or the stamp-and-"
        "forget rule has nothing to forget"
    )
    # Only when it actually differs from the author's — an author's own agent
    # carries no stamp and must survive success.
    assert re.search(r"if planned_agent and a != planned_agent:", block), block[-400:]


def test_a_cross_family_cascade_drops_the_previous_familys_model() -> None:
    """A model id belongs to ONE family. Carrying it across a family change
    hands the new CLI an id it rejects.

    Measured 2026-09-04, WAL-CHAIN-3. Cascade went codex@max -> claude@high
    while `model` stayed `gpt-5.6-sol`, so the claude CLI was invoked with
    codex's model. The spawn died in 952ms: exit_code 1, 0 input tokens, 0
    output tokens, $0.00 -- it never ran a turn. The dispatcher read that as
    "panel-iterate spawn failed" and left the task Blocked.

    Its verifier had said VERIFIED with 0 gaps sixteen minutes earlier, so the
    work was sound and the block was entirely this bug. Every cross-family
    cascade has the same dead rung; WAL-LEDGER-3 escaped only by landing at
    codex@max before reaching a claude rung.

    Remapped, not cleared: None would mean "inherit whatever the CLI defaults
    to", which no run report shows -- the invisible-default trap. The map lives
    in `quality_levels` so `plan`'s declared-floor check reads it too.
    """
    from claude_dispatcher import orchestrator as orch
    # Cross-family: the new family's OWN model, not the old one and not None.
    # Operator ruling 2026-09-04 — fable "was performing well", and it wrote
    # every scaffold and seal that passed. None would mean "inherit whatever
    # the CLI defaults to", which is invisible in a run report and is what put
    # an epic at ~$72/task in July 2026.
    assert orch._model_for_cascade_rung("codex", "claude", "gpt-5.6-sol") \
        == "claude-fable-5-1", "a claude rung runs fable, not codex's model"
    assert orch._model_for_cascade_rung("grok", "claude", "grok-4.6") \
        == "claude-fable-5-1"
    assert orch._model_for_cascade_rung("claude", "codex", "claude-fable-5-1") \
        == "gpt-5.6-sol"
    # Same family: the pin is the operator's and must be kept.
    assert orch._model_for_cascade_rung(
        "codex", "codex", "gpt-5.6-sol") == "gpt-5.6-sol"
    assert orch._model_for_cascade_rung("claude", "claude", "claude-opus-5") \
        == "claude-opus-5"
    # The floor is "nothing BELOW Opus" -- Opus is IN (operator correction,
    # 2026-09-04; my first reading excluded it and rewrote ten Opus pins down
    # to fable). Substring matching is deliberately gone: "sol" matches any id
    # containing it, so the old check would have passed a model named
    # "console-mini". Exact ids, and the run-level enforcement of this rule now
    # lives in plan.model_floor rather than in a comment.
    financial_floor = {
        "claude-opus-5", "claude-fable-5-1", "gpt-5.6-sol", "grok-4.6",
    }
    for fam, want in orch.CASCADE_FAMILY_MODEL.items():
        assert want in financial_floor, (fam, want)



def test_the_cascade_actually_applies_the_family_model() -> None:
    """WIRING, sealed separately. Deleting `model=` from the cascade's
    `replace(...)` survived the helper's own seal — the same correct-but-inert
    shape as PR #93. The rung then keeps the previous family's model and dies
    in under a second."""
    import inspect, re
    from claude_dispatcher import orchestrator as orch
    src = inspect.getsource(orch)
    # There is more than one `snap = replace(...)`; the CASCADE one is the one
    # that sets agent=used_agent. Matching the first blindly picked the design
    # stage's call and passed whatever the cascade did.
    calls = [c for c in re.findall(r"snap = replace\(\n(.*?)\n\s*\)", src,
                                   re.DOTALL) if "agent=used_agent" in c]
    assert len(calls) == 1, f"expected one cascade replace(), found {len(calls)}"
    assert "_model_for_cascade_rung" in calls[0], (
        "the cascade must recompute the model for the rung it moves to; "
        f"got:\n{calls[0]}"
    )
