"""Orchestrator integration of the LLM verification gate (VG-4).

These tests drive the live-spawn dispatch loop through fake_claude (so no
real LLM Tasker is invoked) and inject a stub verifier via
``orchestrator.set_verifier`` (so no real LLM verifier is invoked), mirroring
how test_orchestrator_panel.py injects stub reviewers.

Acceptance coverage:
  - VERIFIED path: Done, verified=true, verification_iterations=0
  - INCOMPLETE → iterate → VERIFIED: Done, verified=true, iterations=1
  - INCOMPLETE → exhausted → Blocked: verification_incomplete, gaps in detail
  - Event ordering: verification_* precede panel_* (mechanical → verifier →
    panel), and a verifier block short-circuits the panel entirely
  - Verifier cost folds into the row cost_usd and emits a task_spawn_finished
  - --skip-verification is journaled and runs no verifier
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from claude_dispatcher import (
    cross_family_reviewer as cfr,
    journal as journal_mod,
    orchestrator,
    spawn as spawn_mod,
    verifier as v,
    yaml_io,
)
from claude_dispatcher.cli import build_parser
from claude_dispatcher.spawn import SpawnUsage


FIXTURE_DIR = Path(__file__).parent / "fixtures"
FAKE_CLAUDE = FIXTURE_DIR / "fake_claude.py"


_PLAIN_TASK_YAML = """\
project: TEST
epic: VERIFY

tasks:
  - key: VER-A
    summary: "verify-test: a plain ticket"
    description: |
      A plain ticket with no risk labels — the cross-family panel does NOT
      fire under mode=auto, so these tests isolate the verifier.
    type: Task
    estimate: 5m
    labels: [size:XS]
"""

_CRITICAL_TASK_YAML = """\
project: TEST
epic: VERIFY

tasks:
  - key: VER-C
    summary: "verify-test: a high-risk ticket"
    description: |
      A high-risk ticket. The cross-family panel fires under mode=auto, so
      this fixture exercises the verifier→panel ordering.
    type: Task
    estimate: 5m
    labels: [size:XS, risk:critical]
"""


@pytest.fixture
def repo(tmp_path: Path) -> Path:
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
    return repo_dir


def _seed_yaml(repo: Path, content: str) -> None:
    (repo / "tasks.yaml").write_text(content, encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=repo,
                   check=True, capture_output=True)


def _args(repo: Path, *, key: str, panel_mode: str = "auto", **overrides):
    parser = build_parser()
    argv = [
        "run", str(repo / "tasks.yaml"),
        "--mode", "unattended", "--max-parallel", "1",
        "--run-id", "verify-test",
        "--runs-dir", str(repo / "_runs"),
        "--worktree-base", str(repo.parent / "wt"),
        "--claude-bin", sys.executable,
        "--only", key,
        "--cross-family-panel", panel_mode,
        "--claude-extra-args=--permission-mode bypassPermissions",
    ]
    for k, val in overrides.items():
        flag = f"--{k.replace('_', '-')}"
        if val is True:
            argv.append(flag)          # store_true flag (e.g. --skip-verification)
        elif val is False:
            continue
        else:
            argv += [flag, str(val)]
    return parser.parse_args(argv)


def _patch_spawn(monkeypatch) -> list[str]:
    """Route the Tasker spawn through fake_claude; record each prompt so
    iterate-prompt content can be asserted."""
    prompts: list[str] = []

    def fake(claude_bin, cwd, env, prompt, extra_args=None, timeout_seconds=3600):
        prompts.append(prompt)
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
    return prompts


class _SequencedVerifier:
    """A stub verifier returning a scripted sequence of VerifierResults, one
    per call (the last entry repeats once the sequence is exhausted). Records
    call_count and the diffs it was handed."""

    def __init__(self, results: list[v.VerifierResult]) -> None:
        self._results = results
        self.call_count = 0
        self.diffs: list[str] = []

    def __call__(self, **kwargs):
        self.diffs.append(kwargs.get("diff", ""))
        idx = min(self.call_count, len(self._results) - 1)
        self.call_count += 1
        return self._results[idx]


def _verified(cost: float | None = None) -> v.VerifierResult:
    return v.VerifierResult(
        verdict=v.VerifierVerdict(verdict=v.VerdictKind.VERIFIED),
        usage=SpawnUsage(cost_usd=cost),
    )


def _incomplete(cost: float | None = None) -> v.VerifierResult:
    return v.VerifierResult(
        verdict=v.VerifierVerdict(
            verdict=v.VerdictKind.INCOMPLETE,
            gaps=[v.Gap(index=1, location="main.py:42",
                        description="stub left where real logic was required")],
        ),
        usage=SpawnUsage(cost_usd=cost),
    )


def _row(repo: Path, key: str) -> dict:
    doc = yaml_io.load(repo / "tasks.yaml")
    return next(t for t in doc["tasks"] if t["key"] == key)


def _events(repo: Path) -> list[journal_mod.JournalEvent]:
    jpath = repo / "_runs" / "verify-test" / journal_mod.JOURNAL_FILENAME
    return list(journal_mod.read_events(jpath))


def _types_for(events, key: str) -> list[str]:
    return [e.event_type for e in events if e.task_key == key]


# --- acceptance 1: VERIFIED path --------------------------------------------


def test_verified_first_try_lands_done(repo: Path, monkeypatch) -> None:
    _seed_yaml(repo, _PLAIN_TASK_YAML)
    _patch_spawn(monkeypatch)
    stub = _SequencedVerifier([_verified()])
    orchestrator.set_verifier(stub)

    rc = orchestrator.execute(_args(repo, key="VER-A"))
    assert rc == 0
    row = _row(repo, "VER-A")
    assert row["status"] == "Done"
    assert row["verified"] is True
    assert row["verification_iterations"] == 0
    assert "verification_detail" not in row
    assert stub.call_count == 1

    types = _types_for(_events(repo), "VER-A")
    assert "verification_started" in types
    assert "verification_verdict" in types
    assert "verification_iterate" not in types
    # The verdict event carries the verdict + iteration.
    verdict_ev = next(e for e in _events(repo)
                      if e.event_type == "verification_verdict")
    assert verdict_ev.payload["verdict"] == "VERIFIED"
    assert verdict_ev.payload["iteration"] == 0
    assert verdict_ev.payload["gaps"] == 0


# --- acceptance 2: INCOMPLETE → iterate → VERIFIED --------------------------


def test_incomplete_then_iterate_then_verified(repo: Path, monkeypatch) -> None:
    _seed_yaml(repo, _PLAIN_TASK_YAML)
    prompts = _patch_spawn(monkeypatch)
    # Block on the first verify, pass on the second (after the Tasker iterated).
    stub = _SequencedVerifier([_incomplete(), _verified()])
    orchestrator.set_verifier(stub)

    rc = orchestrator.execute(_args(repo, key="VER-A", max_verify_iterations=2))
    assert rc == 0
    row = _row(repo, "VER-A")
    assert row["status"] == "Done"
    assert row["verified"] is True
    assert row["verification_iterations"] == 1
    # Two verifier runs (initial block + post-iterate pass).
    assert stub.call_count == 2
    # Two Tasker spawns: the initial run + the one corrective iterate.
    assert len(prompts) == 2

    # The corrective prompt carries the verifier's gap text.
    iterate_prompt = prompts[1]
    assert "independent verifier" in iterate_prompt.lower()
    assert "main.py:42" in iterate_prompt
    assert "stub left where real logic was required" in iterate_prompt

    types = _types_for(_events(repo), "VER-A")
    assert types.count("verification_started") == 2
    assert types.count("verification_verdict") == 2
    assert types.count("verification_iterate") == 1
    assert "task_done" in types


# --- acceptance 3: INCOMPLETE → exhausted → Blocked with gaps ---------------


def test_incomplete_exhausts_budget_blocks_with_gaps(repo: Path, monkeypatch) -> None:
    _seed_yaml(repo, _PLAIN_TASK_YAML)
    prompts = _patch_spawn(monkeypatch)
    stub = _SequencedVerifier([_incomplete()])  # always INCOMPLETE
    orchestrator.set_verifier(stub)

    rc = orchestrator.execute(_args(repo, key="VER-A", max_verify_iterations=2))
    assert rc == 1
    row = _row(repo, "VER-A")
    assert row["status"] == "Blocked"
    assert row["blocked_reason"] == "verification_incomplete"
    assert row["verified"] is False
    assert row["verification_iterations"] == 2
    # Gaps land in the YAML detail for human triage.
    assert "main.py:42" in row["verification_detail"]
    assert "stub left" in row["verification_detail"]

    # Per cascade rung: up to max_verify_iterations+1 verifier runs.
    # Effort cascade may repeat the verifier path on a second claude@high rung.
    assert stub.call_count >= 3
    assert len(prompts) >= 3

    types = _types_for(_events(repo), "VER-A")
    assert types.count("verification_iterate") >= 2
    # Terminal is task_blocked; no panel ran (plain ticket) and no task_done.
    assert "task_done" not in types
    assert "panel_started" not in types
    assert types[-2:] == ["task_blocked", "notify_sent"]


# --- ordering relative to the panel -----------------------------------------


def test_verifier_runs_before_panel(repo: Path, monkeypatch) -> None:
    """For a risk-gated ticket the panel fires; the verifier must run first:
    verification_mechanical → verification_* → panel_*.
    """
    _seed_yaml(repo, _CRITICAL_TASK_YAML)
    _patch_spawn(monkeypatch)
    orchestrator.set_verifier(_SequencedVerifier([_verified()]))
    orchestrator.set_panel_reviewers([
        _StubReviewer("claude"), _StubReviewer("gemini"), _StubReviewer("codex"),
    ])

    rc = orchestrator.execute(_args(repo, key="VER-C", panel_mode="auto"))
    assert rc == 0
    row = _row(repo, "VER-C")
    assert row["status"] == "Done"
    assert row["verified"] is True
    assert row["panel_consensus"] == "approve"

    types = _types_for(_events(repo), "VER-C")
    # Mechanical gate precedes the verifier; the verifier precedes the panel.
    assert (types.index("verification_mechanical")
            < types.index("verification_started")
            < types.index("verification_verdict")
            < types.index("panel_started")
            < types.index("panel_verdict"))


def test_verifier_block_short_circuits_panel(repo: Path, monkeypatch) -> None:
    """A verifier block flips the task to Blocked before the panel — the panel
    (even on a risk-gated ticket) never runs."""
    _seed_yaml(repo, _CRITICAL_TASK_YAML)
    _patch_spawn(monkeypatch)
    orchestrator.set_verifier(_SequencedVerifier([_incomplete()]))
    revs = [_StubReviewer("claude"), _StubReviewer("gemini"), _StubReviewer("codex")]
    orchestrator.set_panel_reviewers(revs)

    rc = orchestrator.execute(_args(repo, key="VER-C", panel_mode="auto",
                                    max_verify_iterations=0))
    assert rc == 1
    row = _row(repo, "VER-C")
    assert row["status"] == "Blocked"
    assert row["blocked_reason"] == "verification_incomplete"
    # Panel never ran.
    assert "panel_consensus" not in row
    assert all(r.call_count == 0 for r in revs)
    assert "panel_started" not in _types_for(_events(repo), "VER-C")


def test_max_verify_iterations_zero_blocks_immediately(repo: Path, monkeypatch) -> None:
    """--max-verify-iterations 0: an INCOMPLETE blocks at once, no Tasker
    re-spawn."""
    _seed_yaml(repo, _PLAIN_TASK_YAML)
    prompts = _patch_spawn(monkeypatch)
    stub = _SequencedVerifier([_incomplete()])
    orchestrator.set_verifier(stub)

    rc = orchestrator.execute(_args(repo, key="VER-A", max_verify_iterations=0))
    assert rc == 1
    row = _row(repo, "VER-A")
    assert row["status"] == "Blocked"
    assert row["verification_iterations"] == 0
    # No in-rung iterate; cascade may still re-verify on a higher-effort rung.
    assert stub.call_count >= 1
    assert "verification_iterate" not in _types_for(_events(repo), "VER-A")


# --- cost folding -----------------------------------------------------------


def test_verifier_cost_folds_into_row_and_emits_spawn_event(
    repo: Path, monkeypatch,
) -> None:
    """Verifier cost folds into the row cost_usd and emits a
    task_spawn_finished (so the report rollup sums it)."""
    _seed_yaml(repo, _PLAIN_TASK_YAML)
    _patch_spawn(monkeypatch)
    # Two verify spawns, each costing 0.01 → 0.02 folded onto the row (the
    # fake Tasker spawn reports no usage, so the verifier cost is the total).
    orchestrator.set_verifier(_SequencedVerifier([_incomplete(0.01), _verified(0.01)]))

    rc = orchestrator.execute(_args(repo, key="VER-A", max_verify_iterations=1))
    assert rc == 0
    row = _row(repo, "VER-A")
    assert row["status"] == "Done"
    assert row["cost_usd"] == pytest.approx(0.02)

    # A verifier task_spawn_finished event is tagged spawn_kind=verifier.
    spawn_evs = [e for e in _events(repo)
                 if e.event_type == "task_spawn_finished"
                 and e.payload.get("spawn_kind") == "verifier"]
    assert len(spawn_evs) == 2
    assert all(e.payload["cost_usd"] == pytest.approx(0.01) for e in spawn_evs)


# --- skip-verification ------------------------------------------------------


def test_skip_verification_journaled_and_runs_no_verifier(
    repo: Path, monkeypatch,
) -> None:
    _seed_yaml(repo, _PLAIN_TASK_YAML)
    _patch_spawn(monkeypatch)
    stub = _SequencedVerifier([_incomplete()])  # would block IF it ran
    orchestrator.set_verifier(stub)

    rc = orchestrator.execute(_args(repo, key="VER-A", skip_verification=True))
    assert rc == 0
    row = _row(repo, "VER-A")
    assert row["status"] == "Done"
    # The gate never ran: no verdict stamped, no verifier invoked.
    assert "verified" not in row
    assert "verification_iterations" not in row
    assert stub.call_count == 0

    types = _types_for(_events(repo), "VER-A")
    assert "verification_skipped" in types
    assert "verification_started" not in types
    assert "verification_verdict" not in types
    skip_ev = next(e for e in _events(repo)
                   if e.event_type == "verification_skipped")
    assert skip_ev.payload["reason"] == "--skip-verification"


# --- a verifier stub reviewer (panel approve) -------------------------------


class _StubReviewer(cfr.Reviewer):
    """Approving reviewer for the verifier→panel ordering tests."""

    _APPROVE = (
        "## Verdict\nAPPROVE\n\n## Dimension scores\n"
        "- Correctness: 5\n- Security: 5\n- Compliance: 5\n- Resilience: 4\n"
        "- Idempotency: 4\n- Observability: 4\n- Performance: 4\n"
        "- Maintainability: 4\n\n## Findings\n"
    )

    def __init__(self, family: str) -> None:
        super().__init__()
        self.family = family
        self.call_count = 0

    def _invoke_cli(self, prompt: str) -> str:
        self.call_count += 1
        return self._APPROVE


@pytest.fixture(autouse=True)
def _reset_panel_reviewers():
    orchestrator.set_panel_reviewers(None)
    yield
    orchestrator.set_panel_reviewers(None)
