"""Orchestrator integration of the cross-family reviewer panel.

These tests drive the live-spawn dispatch loop through the fake_claude
binary (so no real LLM tasker is invoked) and inject stub reviewers via
`orchestrator.set_panel_reviewers` (so no real LLM reviewer is invoked).

We verify:
  - Panel fires only for risk-gated tickets in mode=auto
  - Mode=always fires for every Done ticket
  - Mode=never skips the panel entirely
  - A unanimous APPROVE leaves the task Done (panel acts like a no-op)
  - A single dissenter flips the task to Blocked with a clear reason
  - A reviewer that times out → "incomplete" → still blocks (does not auto-integrate)
  - Panel findings are appended to the summary.md
  - YAML row carries panel_consensus + per-family verdicts
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from claude_dispatcher import (
    cross_family_reviewer as cfr,
    orchestrator,
    spawn as spawn_mod,
    yaml_io,
)
from claude_dispatcher.cli import build_parser


FIXTURE_DIR = Path(__file__).parent / "fixtures"
FAKE_CLAUDE = FIXTURE_DIR / "fake_claude.py"


# A small per-task YAML where the only task has a `risk:critical` label —
# so panel_required() returns True under mode=auto. Mirrors what a real
# financial-domain task row looks like.
_CRITICAL_TASK_YAML = """\
project: TEST
epic: PANEL

tasks:
  - key: PANEL-A
    summary: "panel-test: high-risk ticket"
    description: |
      A high-risk ticket. The cross-family panel must fire for this one
      under mode=auto.
    type: Task
    estimate: 5m
    labels: [size:XS, risk:critical]
"""

_LOW_RISK_TASK_YAML = """\
project: TEST
epic: PANEL

tasks:
  - key: PANEL-B
    summary: "panel-test: low-risk ticket"
    description: A docs change. Panel should NOT fire under mode=auto.
    type: Task
    estimate: 5m
    labels: [size:XS, risk:low]
"""


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A git repo with a configurable tasks.yaml, gitless until populated."""
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
        "--run-id", "panel-test",
        "--runs-dir", str(repo / "_runs"),
        "--worktree-base", str(repo.parent / "wt"),
        "--claude-bin", sys.executable,
        "--only", key,
        "--cross-family-panel", panel_mode,
        "--claude-extra-args=--permission-mode bypassPermissions",
    ]
    for k, v in overrides.items():
        argv += [f"--{k.replace('_', '-')}", str(v)]
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


class _StubReviewer(cfr.Reviewer):
    """Returns a canned parse-ready output. Records call_count for assertions."""

    def __init__(self, family: str, output: str) -> None:
        super().__init__()
        self.family = family
        self._output = output
        self.call_count = 0

    def _invoke_cli(self, prompt: str) -> str:
        self.call_count += 1
        return self._output


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
    Fix: Wrap the debit in a row-level lock and check balance >= amount
    before issuing the UPDATE.
""")


def _set_reviewers(monkeypatch, families_and_outputs: list[tuple[str, str]]) -> list[_StubReviewer]:
    revs = [_StubReviewer(fam, out) for fam, out in families_and_outputs]
    orchestrator.set_panel_reviewers(revs)
    monkeypatch.setattr(
        orchestrator, "set_panel_reviewers",
        orchestrator.set_panel_reviewers,  # keep symbol
    )
    # Ensure cleanup so a later test doesn't see stale reviewers.
    monkeypatch.setattr(
        orchestrator, "_panel_reviewers_override",
        orchestrator._panel_reviewers_override,
        raising=False,
    )
    return revs


@pytest.fixture(autouse=True)
def _reset_reviewers():
    """Make sure each test starts and ends with no global override."""
    orchestrator.set_panel_reviewers(None)
    yield
    orchestrator.set_panel_reviewers(None)


# --- panel gating per mode --------------------------------------------------


def test_panel_auto_fires_on_risk_critical_label(repo: Path, monkeypatch) -> None:
    _seed_yaml(repo, _CRITICAL_TASK_YAML)
    _patch_spawn(monkeypatch)
    # The task is authored by claude (default agent), so the panel excludes the
    # claude reviewer from its own jury — only the non-author families run.
    revs = _set_reviewers(monkeypatch, [
        ("gemini", _APPROVE_OUTPUT),
        ("codex", _APPROVE_OUTPUT),
    ])

    rc = orchestrator.execute(_args(repo, key="PANEL-A", panel_mode="auto"))
    assert rc == 0, "all-approve panel should leave task Done"
    doc = yaml_io.load(repo / "tasks.yaml")
    row = next(t for t in doc["tasks"] if t["key"] == "PANEL-A")

    assert row["status"] == "Done"
    assert row["panel_consensus"] == "approve"
    # claude is the author → excluded from the panel, so no verdict is stamped.
    assert "panel_verdict_claude" not in row
    assert row["panel_verdict_gemini"] == "APPROVE"
    assert row["panel_verdict_codex"] == "APPROVE"
    assert all(r.call_count == 1 for r in revs)


def test_panel_auto_skips_low_risk(repo: Path, monkeypatch) -> None:
    _seed_yaml(repo, _LOW_RISK_TASK_YAML)
    _patch_spawn(monkeypatch)
    revs = _set_reviewers(monkeypatch, [
        ("claude", _APPROVE_OUTPUT),
        ("gemini", _APPROVE_OUTPUT),
        ("codex", _APPROVE_OUTPUT),
    ])

    rc = orchestrator.execute(_args(repo, key="PANEL-B", panel_mode="auto"))
    assert rc == 0
    doc = yaml_io.load(repo / "tasks.yaml")
    row = next(t for t in doc["tasks"] if t["key"] == "PANEL-B")
    assert row["status"] == "Done"
    # No panel ran — no panel_* fields stamped.
    assert "panel_consensus" not in row
    assert all(r.call_count == 0 for r in revs)


def test_panel_always_fires_for_low_risk(repo: Path, monkeypatch) -> None:
    _seed_yaml(repo, _LOW_RISK_TASK_YAML)
    _patch_spawn(monkeypatch)
    revs = _set_reviewers(monkeypatch, [
        ("claude", _APPROVE_OUTPUT),
        ("gemini", _APPROVE_OUTPUT),
        ("codex", _APPROVE_OUTPUT),
    ])

    rc = orchestrator.execute(_args(repo, key="PANEL-B", panel_mode="always"))
    assert rc == 0
    doc = yaml_io.load(repo / "tasks.yaml")
    row = next(t for t in doc["tasks"] if t["key"] == "PANEL-B")
    assert row["status"] == "Done"
    assert row["panel_consensus"] == "approve"
    # claude (author) is excluded; only the non-author reviewers ran.
    assert all(r.call_count == 1 for r in revs if r.family != "claude")
    assert all(r.call_count == 0 for r in revs if r.family == "claude")


def test_panel_never_skips_even_for_critical(repo: Path, monkeypatch) -> None:
    _seed_yaml(repo, _CRITICAL_TASK_YAML)
    _patch_spawn(monkeypatch)
    revs = _set_reviewers(monkeypatch, [
        ("claude", _APPROVE_OUTPUT),
        ("gemini", _APPROVE_OUTPUT),
        ("codex", _APPROVE_OUTPUT),
    ])

    rc = orchestrator.execute(_args(repo, key="PANEL-A", panel_mode="never"))
    assert rc == 0
    doc = yaml_io.load(repo / "tasks.yaml")
    row = next(t for t in doc["tasks"] if t["key"] == "PANEL-A")
    assert row["status"] == "Done"
    assert "panel_consensus" not in row
    assert all(r.call_count == 0 for r in revs)


# --- dissent / block path ---------------------------------------------------


def test_panel_dissenter_flips_task_to_blocked(repo: Path, monkeypatch) -> None:
    """A corroborated HIGH finding — two non-author families each flag it — must
    Block the task, with panel_consensus=block and findings appended to
    summary.md. (claude is the author, so it is excluded from its own jury; the
    corroboration gate requires ≥2 available families to raise a blocking HIGH,
    so both surviving reviewers must dissent to block on a non-CRITICAL.)
    """
    _seed_yaml(repo, _CRITICAL_TASK_YAML)
    _patch_spawn(monkeypatch)
    revs = _set_reviewers(monkeypatch, [
        ("gemini", _CHANGES_REQUESTED_OUTPUT),
        ("codex", _CHANGES_REQUESTED_OUTPUT),
    ])

    rc = orchestrator.execute(_args(repo, key="PANEL-A", panel_mode="auto"))
    assert rc == 1, "expected partial completion (task Blocked by panel)"
    doc = yaml_io.load(repo / "tasks.yaml")
    row = next(t for t in doc["tasks"] if t["key"] == "PANEL-A")

    assert row["status"] == "Blocked"
    assert "cross_family_panel" in row.get("blocked_reason", "")
    assert row["panel_consensus"] == "block"
    assert row["panel_verdict_codex"] == "CHANGES_REQUESTED"
    assert row["panel_verdict_gemini"] == "CHANGES_REQUESTED"
    # claude authored the task → excluded, so no claude verdict is stamped.
    assert "panel_verdict_claude" not in row
    assert row["panel_blocking_findings"] >= 1

    # Findings appended to summary.md
    summary_text = Path(row["summary_path"]).read_text(encoding="utf-8")
    assert "Cross-family panel" in summary_text
    assert "block" in summary_text.lower()
    assert "HIGH" in summary_text
    assert "service.go:42" in summary_text


def test_panel_unavailable_yields_incomplete_and_blocks(repo: Path, monkeypatch) -> None:
    """If the panel can reach NO available reviewer, it returns 'incomplete'.
    Incomplete is treated as block — task does NOT proceed to Done.

    claude authors the task and is excluded, so the panel is just
    [gemini, codex]; the corroboration gate only reports "incomplete" when
    every AVAILABLE seat is gone, so both surviving CLIs must be missing.
    """
    _seed_yaml(repo, _CRITICAL_TASK_YAML)
    _patch_spawn(monkeypatch)

    class _UnavailableGemini(cfr.Reviewer):
        family = "gemini"
        def _invoke_cli(self, prompt: str) -> str:
            raise FileNotFoundError("gemini not installed")

    class _UnavailableCodex(cfr.Reviewer):
        family = "codex"
        def _invoke_cli(self, prompt: str) -> str:
            raise FileNotFoundError("codex not installed")

    revs = [
        _StubReviewer("claude", _APPROVE_OUTPUT),
        _UnavailableGemini(),
        _UnavailableCodex(),
    ]
    orchestrator.set_panel_reviewers(revs)

    rc = orchestrator.execute(_args(repo, key="PANEL-A", panel_mode="auto"))
    assert rc == 1
    doc = yaml_io.load(repo / "tasks.yaml")
    row = next(t for t in doc["tasks"] if t["key"] == "PANEL-A")

    assert row["status"] == "Blocked"
    assert row["panel_consensus"] == "incomplete"
    assert row["panel_verdict_codex"] == "UNAVAILABLE"
    assert "not installed" in (row.get("panel_error_codex") or "")


def test_panel_block_short_circuits_auto_integrate(repo: Path, monkeypatch) -> None:
    """When the panel blocks, auto-integrate must not fire — even if
    the run was configured with --auto-integrate.
    """
    _seed_yaml(repo, _CRITICAL_TASK_YAML)
    _patch_spawn(monkeypatch)
    # claude (author) is excluded; a corroborated block needs both surviving
    # families to dissent.
    _set_reviewers(monkeypatch, [
        ("gemini", _CHANGES_REQUESTED_OUTPUT),
        ("codex", _CHANGES_REQUESTED_OUTPUT),
    ])
    args = _args(repo, key="PANEL-A", panel_mode="auto")
    args.auto_integrate = True  # simulate --auto-integrate

    orchestrator.execute(args)
    doc = yaml_io.load(repo / "tasks.yaml")
    row = next(t for t in doc["tasks"] if t["key"] == "PANEL-A")
    assert row["status"] == "Blocked"
    # auto_integrate_* must NOT be stamped — it never ran.
    assert "auto_integrate_status" not in row


def test_panel_findings_not_double_appended(repo: Path, monkeypatch) -> None:
    """Re-running the dispatcher on a Blocked task should not double-append
    panel findings to summary.md (defense against summary growth on retry).
    """
    _seed_yaml(repo, _CRITICAL_TASK_YAML)
    _patch_spawn(monkeypatch)

    # Pre-seed the summary.md with a panel block.
    summary_dir = repo / "_runs" / "panel-test" / "PANEL-A"
    summary_dir.mkdir(parents=True)
    summary_path = summary_dir / "summary.md"
    summary_path.write_text(textwrap.dedent("""\
        # PANEL-A: stub

        **Status:** Done

        ## Cross-family panel

        Verdict: APPROVE (consensus=approve | claude=APPROVE | gemini=APPROVE | codex=APPROVE)
    """), encoding="utf-8")

    panel = cfr.aggregate([
        cfr.ReviewerVerdict(
            family="claude", verdict=cfr.Verdict.APPROVE,
            dimensions={d: 4 for d in cfr.DIMENSION_NAMES},
        ),
        cfr.ReviewerVerdict(
            family="gemini", verdict=cfr.Verdict.APPROVE,
            dimensions={d: 4 for d in cfr.DIMENSION_NAMES},
        ),
        cfr.ReviewerVerdict(
            family="codex", verdict=cfr.Verdict.APPROVE,
            dimensions={d: 4 for d in cfr.DIMENSION_NAMES},
        ),
    ])

    from claude_dispatcher.orchestrator import _append_panel_findings_to_summary
    _append_panel_findings_to_summary(
        summary_path, panel, repo / "_runs" / "panel-test" / "log", "PANEL-A",
    )

    text = summary_path.read_text(encoding="utf-8")
    # Only ONE "## Cross-family panel" section.
    assert text.count("## Cross-family panel") == 1


# --- panel iterate ----------------------------------------------------------


class _SequencedStubReviewer(cfr.Reviewer):
    """Returns a different canned output per call. Used to model a panel
    that blocks on the first run and approves on the second after the
    Tasker iterated.
    """

    def __init__(self, family: str, outputs: list[str]) -> None:
        super().__init__()
        self.family = family
        self._outputs = list(outputs)
        self.call_count = 0

    def _invoke_cli(self, prompt: str) -> str:
        idx = min(self.call_count, len(self._outputs) - 1)
        self.call_count += 1
        return self._outputs[idx]


def test_panel_iterate_block_then_approve_lands_done(repo: Path, monkeypatch) -> None:
    """N=1: panel blocks, Tasker re-spawn produces a new commit, panel
    re-runs and approves. Final status is Done. panel_iterations_used=1.
    """
    _seed_yaml(repo, _CRITICAL_TASK_YAML)
    _patch_spawn(monkeypatch)
    # claude (author) is excluded; a corroborated round-1 block needs BOTH
    # surviving families to dissent, then both approve post-iterate.
    revs = [
        _SequencedStubReviewer("gemini", [_CHANGES_REQUESTED_OUTPUT, _APPROVE_OUTPUT]),
        _SequencedStubReviewer("codex", [_CHANGES_REQUESTED_OUTPUT, _APPROVE_OUTPUT]),
    ]
    orchestrator.set_panel_reviewers(revs)

    rc = orchestrator.execute(_args(
        repo, key="PANEL-A", panel_mode="auto",
        cross_family_panel_iterate=1,
    ))
    assert rc == 0, "panel iterate should recover and land Done"
    doc = yaml_io.load(repo / "tasks.yaml")
    row = next(t for t in doc["tasks"] if t["key"] == "PANEL-A")

    assert row["status"] == "Done"
    assert row["panel_consensus"] == "approve"
    assert row.get("panel_iterations_used") == 1
    # Each reviewer ran twice (initial + post-iterate).
    assert all(r.call_count == 2 for r in revs)


def test_panel_iterate_exhausts_budget_stays_blocked(repo: Path, monkeypatch) -> None:
    """N=2: panel keeps blocking on every iteration. After 2 iterations,
    task is Blocked. panel_iterations_used should equal the budget.
    """
    _seed_yaml(repo, _CRITICAL_TASK_YAML)
    _patch_spawn(monkeypatch)
    # claude (author) is excluded; both surviving families block every round so
    # the corroboration gate blocks on each pass.
    revs = [
        _StubReviewer("gemini", _CHANGES_REQUESTED_OUTPUT),
        # Codex always blocks.
        _StubReviewer("codex", _CHANGES_REQUESTED_OUTPUT),
    ]
    orchestrator.set_panel_reviewers(revs)

    rc = orchestrator.execute(_args(
        repo, key="PANEL-A", panel_mode="auto",
        cross_family_panel_iterate=2,
    ))
    assert rc == 1
    doc = yaml_io.load(repo / "tasks.yaml")
    row = next(t for t in doc["tasks"] if t["key"] == "PANEL-A")

    assert row["status"] == "Blocked"
    assert row["panel_consensus"] == "block"
    assert row.get("panel_iterations_used") == 2
    assert "after 2 iterate attempt(s)" in row.get("blocked_reason", "")
    # Codex was called 3x (initial + 2 iterations).
    codex = next(r for r in revs if r.family == "codex")
    assert codex.call_count == 3


def test_panel_iterate_default_zero_blocks_immediately(repo: Path, monkeypatch) -> None:
    """N=0 (default): panel block flips straight to Blocked without
    re-spawning the Tasker. No panel_iterations_used field stamped.
    """
    _seed_yaml(repo, _CRITICAL_TASK_YAML)
    _patch_spawn(monkeypatch)
    # claude (author) is excluded; both surviving families block → corroborated.
    revs = [
        _StubReviewer("gemini", _CHANGES_REQUESTED_OUTPUT),
        _StubReviewer("codex", _CHANGES_REQUESTED_OUTPUT),
    ]
    orchestrator.set_panel_reviewers(revs)

    # No --cross-family-panel-iterate flag → default 0.
    rc = orchestrator.execute(_args(repo, key="PANEL-A", panel_mode="auto"))
    assert rc == 1
    doc = yaml_io.load(repo / "tasks.yaml")
    row = next(t for t in doc["tasks"] if t["key"] == "PANEL-A")

    assert row["status"] == "Blocked"
    assert "panel_iterations_used" not in row
    # Reviewers ran exactly once each.
    assert all(r.call_count == 1 for r in revs)


def test_panel_iterate_short_circuits_when_tasker_produces_no_commits(
    repo: Path, monkeypatch,
) -> None:
    """If the iterate spawn exits but doesn't produce a new commit (the
    Tasker decided no fix was needed or got confused), the orchestrator
    must stop iterating instead of looping forever on the same diff.
    """
    _seed_yaml(repo, _CRITICAL_TASK_YAML)

    # Initial fake_claude scenario produces a commit; the iterate spawn
    # should NOT produce a commit (use done-no-commit so the spawn exits
    # cleanly but commits nothing).
    spawn_call_count = {"n": 0}
    original_spawn = None

    def fake(claude_bin, cwd, env, prompt, extra_args=None, timeout_seconds=3600):
        spawn_call_count["n"] += 1
        # First spawn: normal (commits). Second spawn (the iterate): skip commit.
        env_local = dict(env)
        if spawn_call_count["n"] >= 2:
            env_local["FAKE_CLAUDE_SCENARIO"] = "done-no-commit"
        proc = subprocess.run(
            [sys.executable, str(FAKE_CLAUDE)],
            input=prompt, capture_output=True, text=True,
            cwd=str(cwd), env=env_local, timeout=timeout_seconds,
        )
        return spawn_mod.SpawnResult(
            exit_code=proc.returncode,
            summary_path=Path(env["SUMMARY_PATH"]),
            stdout=proc.stdout, stderr=proc.stderr,
        )

    monkeypatch.setattr(spawn_mod, "spawn_claude", fake)

    # claude (author) is excluded; both surviving families block → corroborated.
    revs = [
        _StubReviewer("gemini", _CHANGES_REQUESTED_OUTPUT),
        _StubReviewer("codex", _CHANGES_REQUESTED_OUTPUT),
    ]
    orchestrator.set_panel_reviewers(revs)

    rc = orchestrator.execute(_args(
        repo, key="PANEL-A", panel_mode="auto",
        cross_family_panel_iterate=3,
    ))
    assert rc == 1
    doc = yaml_io.load(repo / "tasks.yaml")
    row = next(t for t in doc["tasks"] if t["key"] == "PANEL-A")
    assert row["status"] == "Blocked"
    # Only ONE iterate attempt should have run (then short-circuited).
    assert row.get("panel_iterations_used") == 1
    # Codex called 2x: initial panel + one re-run after the no-op iterate
    # spawn aborted. Wait, no — the no-op iterate aborts BEFORE the panel
    # re-runs. So codex was called exactly 1x.
    codex = next(r for r in revs if r.family == "codex")
    assert codex.call_count == 1


class _BlockThenUnavailableReviewer(cfr.Reviewer):
    """Blocks (CHANGES_REQUESTED) on the first panel run — so the
    orchestrator iterates — then its CLI vanishes on the re-run, modelling a
    reviewer that becomes unavailable *partway through* the iterate loop.
    """

    def __init__(self, family: str, block_output: str) -> None:
        super().__init__()
        self.family = family
        self._block_output = block_output
        self.call_count = 0

    def _invoke_cli(self, prompt: str) -> str:
        self.call_count += 1
        if self.call_count == 1:
            return self._block_output
        raise FileNotFoundError("codex vanished mid-iteration")


def test_panel_iterate_exhaustion_attaches_findings_to_summary(
    repo: Path, monkeypatch,
) -> None:
    """Scenario 2: the iterate budget is exhausted while the panel keeps
    blocking → task Blocked AND the blocking findings are appended to
    summary.md, so the human triaging the Blocked row sees exactly what the
    panel flagged (not just an opaque blocked_reason in the YAML).
    """
    _seed_yaml(repo, _CRITICAL_TASK_YAML)
    _patch_spawn(monkeypatch)
    # claude (author) is excluded; both surviving families block on every round,
    # so iterating never clears the corroborated block.
    revs = [
        _StubReviewer("gemini", _CHANGES_REQUESTED_OUTPUT),
        _StubReviewer("codex", _CHANGES_REQUESTED_OUTPUT),
    ]
    orchestrator.set_panel_reviewers(revs)

    rc = orchestrator.execute(_args(
        repo, key="PANEL-A", panel_mode="auto",
        cross_family_panel_iterate=1,
    ))
    assert rc == 1
    doc = yaml_io.load(repo / "tasks.yaml")
    row = next(t for t in doc["tasks"] if t["key"] == "PANEL-A")

    assert row["status"] == "Blocked"
    assert row["panel_consensus"] == "block"
    assert row.get("panel_iterations_used") == 1
    assert "after 1 iterate attempt(s)" in row.get("blocked_reason", "")

    # The crux of this scenario: findings reach summary.md after exhaustion.
    summary_text = Path(row["summary_path"]).read_text(encoding="utf-8")
    assert "## Cross-family panel" in summary_text
    assert "HIGH" in summary_text
    assert "service.go:42" in summary_text


def test_panel_iterate_reviewer_unavailable_mid_iteration_blocks(
    repo: Path, monkeypatch,
) -> None:
    """Scenario 3: a reviewer blocks on round 1 (triggering the iterate),
    then goes UNAVAILABLE on the post-iterate re-run. The panel can no
    longer prove 3/3 agreement → consensus "incomplete" → task Blocked.
    The Tasker's committed work is preserved (never lost to a missing CLI).
    """
    _seed_yaml(repo, _CRITICAL_TASK_YAML)
    _patch_spawn(monkeypatch)
    # claude (author) is excluded. Both surviving families corroborate a block on
    # round 1 (triggering the iterate), then both vanish on the re-run — so the
    # re-run panel has NO available seat → consensus "incomplete".
    codex = _BlockThenUnavailableReviewer("codex", _CHANGES_REQUESTED_OUTPUT)
    revs = [
        _BlockThenUnavailableReviewer("gemini", _CHANGES_REQUESTED_OUTPUT),
        codex,
    ]
    orchestrator.set_panel_reviewers(revs)

    rc = orchestrator.execute(_args(
        repo, key="PANEL-A", panel_mode="auto",
        cross_family_panel_iterate=1,
    ))
    assert rc == 1
    doc = yaml_io.load(repo / "tasks.yaml")
    row = next(t for t in doc["tasks"] if t["key"] == "PANEL-A")

    assert row["status"] == "Blocked"
    # Round 1 blocked → one iterate fired → round 2 found codex unavailable.
    assert row.get("panel_iterations_used") == 1
    # The FINAL panel verdict (stamped on the row) is from the re-run, where
    # a reviewer was UNAVAILABLE → incomplete, not a plain block.
    assert row["panel_consensus"] == "incomplete"
    assert row["panel_verdict_codex"] == "UNAVAILABLE"
    assert "vanished" in (row.get("panel_error_codex") or "")
    # Codex ran exactly twice: the initial block + the re-run where it died.
    assert codex.call_count == 2


def test_panel_iterate_findings_text_reaches_respawn_prompt(
    repo: Path, monkeypatch,
) -> None:
    """Scenario 4: the blocking findings must be rendered into the
    corrective prompt handed to the re-spawned Tasker — otherwise the
    Tasker has no idea what to fix. Capture every spawn prompt and assert
    the second one (the iterate spawn) carries the finding's location,
    problem, and suggested fix.
    """
    _seed_yaml(repo, _CRITICAL_TASK_YAML)
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

    # claude (author) is excluded. Both surviving families block on round 1
    # (corroborated) then approve on round 2, so the run lands Done with exactly
    # one iterate spawn to inspect.
    revs = [
        _SequencedStubReviewer("gemini", [_CHANGES_REQUESTED_OUTPUT, _APPROVE_OUTPUT]),
        _SequencedStubReviewer("codex", [_CHANGES_REQUESTED_OUTPUT, _APPROVE_OUTPUT]),
    ]
    orchestrator.set_panel_reviewers(revs)

    rc = orchestrator.execute(_args(
        repo, key="PANEL-A", panel_mode="auto",
        cross_family_panel_iterate=1,
    ))
    assert rc == 0, "block → iterate → approve should land Done"

    # Two spawns: the initial Tasker run + the corrective iterate spawn.
    assert len(prompts) == 2
    initial_prompt, iterate_prompt = prompts[0], prompts[1]

    # The corrective prompt frames the panel verdict...
    assert "cross-family review panel" in iterate_prompt
    assert "blocking finding" in iterate_prompt.lower()
    # ...and carries the ACTUAL finding location, problem, and fix text.
    assert "apps/wallet/service.go:42" in iterate_prompt
    assert "SELECT FOR UPDATE" in iterate_prompt
    assert "row-level lock" in iterate_prompt
    # Sanity: the initial spawn could not have carried the findings — they
    # didn't exist until the first panel ran.
    assert "apps/wallet/service.go:42" not in initial_prompt


def test_panel_runner_exception_marks_blocked_not_crash(repo: Path, monkeypatch) -> None:
    """If the panel framework itself raises (not a reviewer dissent), the
    Tasker's work must be preserved and the task Blocked with a clear
    reason — never lose the work.
    """
    _seed_yaml(repo, _CRITICAL_TASK_YAML)
    _patch_spawn(monkeypatch)

    def _raise_panel(*a, **kw):
        raise RuntimeError("synthetic panel framework failure")

    monkeypatch.setattr(orchestrator.cfr_mod, "run_panel", _raise_panel)

    rc = orchestrator.execute(_args(repo, key="PANEL-A", panel_mode="always"))
    assert rc == 1
    doc = yaml_io.load(repo / "tasks.yaml")
    row = next(t for t in doc["tasks"] if t["key"] == "PANEL-A")
    assert row["status"] == "Blocked"
    assert "cross_family_panel_error" in row.get("blocked_reason", "")
    assert "synthetic" in row.get("blocked_reason", "")


# --- notifier integration ---------------------------------------------------


def _install_recording_notifier(monkeypatch):
    """Wrap orchestrator._build_config so the returned cfg has a
    NullNotifier we can introspect. Returns the notifier instance.
    """
    from claude_dispatcher import notify

    recording = notify.NullNotifier()
    orig = orchestrator._build_config

    def patched(args):
        cfg = orig(args)
        cfg.notifier = recording
        return cfg

    monkeypatch.setattr(orchestrator, "_build_config", patched)
    return recording


def test_notifier_fires_run_complete_on_clean_done(repo: Path, monkeypatch) -> None:
    """A clean run (all tasks Done) fires one run-complete notification.
    No task-blocked or worker-exception events for this happy path.
    """
    _seed_yaml(repo, _CRITICAL_TASK_YAML)
    _patch_spawn(monkeypatch)
    _set_reviewers(monkeypatch, [
        ("claude", _APPROVE_OUTPUT),
        ("gemini", _APPROVE_OUTPUT),
        ("codex", _APPROVE_OUTPUT),
    ])
    recording = _install_recording_notifier(monkeypatch)

    rc = orchestrator.execute(_args(repo, key="PANEL-A", panel_mode="auto"))
    assert rc == 0

    titles = [n.title for n in recording.sent]
    # Exactly one event: run complete.
    assert len(titles) == 1
    assert "run complete" in titles[0]
    rc_note = recording.sent[0]
    assert "1 done" in rc_note.title
    assert rc_note.urgency == "default"  # clean run = default urgency


def test_notifier_fires_task_blocked_and_run_complete(repo: Path, monkeypatch) -> None:
    """Panel block → task_blocked notification AND run_complete rollup
    listing the blocked task with its reason.
    """
    _seed_yaml(repo, _CRITICAL_TASK_YAML)
    _patch_spawn(monkeypatch)
    # claude (author) is excluded; both surviving families block → corroborated.
    _set_reviewers(monkeypatch, [
        ("gemini", _CHANGES_REQUESTED_OUTPUT),
        ("codex", _CHANGES_REQUESTED_OUTPUT),
    ])
    recording = _install_recording_notifier(monkeypatch)

    rc = orchestrator.execute(_args(repo, key="PANEL-A", panel_mode="auto"))
    assert rc == 1

    titles = [n.title for n in recording.sent]
    # task_blocked event for PANEL-A + run_complete rollup.
    assert any("Blocked" in t for t in titles)
    assert any("run complete" in t for t in titles)
    blocked_note = next(n for n in recording.sent if "Blocked" in n.title)
    assert "PANEL-A" in blocked_note.title
    assert "cross_family_panel" in blocked_note.body
    assert blocked_note.click_url is not None
    rc_note = next(n for n in recording.sent if "run complete" in n.title)
    assert rc_note.urgency == "high"  # has blocked tasks
    assert "PANEL-A" in rc_note.body


def test_notifier_fires_awaiting_pr_approval_in_unattended(repo: Path, monkeypatch) -> None:
    """When the Tasker parks awaiting human PR approval, the notification
    fires regardless of mode (we want to wake up the human via phone
    even in unattended).
    """
    _seed_yaml(repo, _CRITICAL_TASK_YAML)
    monkeypatch.setenv("FAKE_CLAUDE_SCENARIO", "awaiting-human-pr")
    _patch_spawn(monkeypatch)
    # No reviewers — panel won't fire because PR-gate path Blocks first.
    recording = _install_recording_notifier(monkeypatch)

    rc = orchestrator.execute(_args(repo, key="PANEL-A", panel_mode="never"))
    assert rc == 1
    titles = [n.title for n in recording.sent]
    assert any("awaiting PR approval" in t for t in titles)
    pr_note = next(n for n in recording.sent if "awaiting PR approval" in n.title)
    assert pr_note.urgency == "high"
    assert "PANEL-A" in pr_note.title


def test_notifier_no_op_when_no_channel_configured(repo: Path, monkeypatch) -> None:
    """Default RunConfig has NullNotifier; events are recorded but no
    network calls happen. (We verify this end-to-end by NOT installing
    the recording notifier and checking the dispatcher exits clean.)
    """
    _seed_yaml(repo, _LOW_RISK_TASK_YAML)
    _patch_spawn(monkeypatch)
    # No reviewer override → panel skipped on low-risk.
    rc = orchestrator.execute(_args(repo, key="PANEL-B", panel_mode="auto"))
    assert rc == 0  # silent success path


# --- advisory (probationary) reviewers — VG-5 --------------------------------


from claude_dispatcher import journal as journal_mod  # noqa: E402
from claude_dispatcher import repo_config  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_advisory_reviewers():
    """Each test starts and ends with the config-derived advisory behaviour
    (override None). Mirrors _reset_reviewers."""
    orchestrator.set_panel_advisory_reviewers(None)
    yield
    orchestrator.set_panel_advisory_reviewers(None)


def _journal_events(repo: Path) -> list[journal_mod.JournalEvent]:
    jpath = repo / "_runs" / "panel-test" / journal_mod.JOURNAL_FILENAME
    return list(journal_mod.read_events(jpath))


_ADVISORY_CRITICAL_OUTPUT = textwrap.dedent("""\
    ## Verdict
    CHANGES_REQUESTED

    ## Dimension scores
    - Correctness: 2

    ## Findings

    ### CRITICAL: apps/wallet/payout.go:7
    Description: Advisory-only: payout rounding favours the house.
    Fix: Use banker's rounding for the payout calculation.
""")


def test_advisory_blocker_never_blocks_or_iterates(repo: Path, monkeypatch) -> None:
    """Edge 2 (e2e): advisory CHANGES_REQUESTED with a CRITICAL finding,
    authoritative 3/3 APPROVE, iterate budget available → task lands Done,
    NO panel_iterate fires, the finding is journaled as
    panel_advisory_finding and rendered in the advisory appendix only.
    """
    _seed_yaml(repo, _CRITICAL_TASK_YAML)
    _patch_spawn(monkeypatch)
    # claude (author) is excluded from the authoritative panel; advisory
    # reviewers are NOT author-filtered, so grok still runs.
    _set_reviewers(monkeypatch, [
        ("gemini", _APPROVE_OUTPUT),
        ("codex", _APPROVE_OUTPUT),
    ])
    adv = _StubReviewer("grok", _ADVISORY_CRITICAL_OUTPUT)
    orchestrator.set_panel_advisory_reviewers([adv])

    rc = orchestrator.execute(_args(
        repo, key="PANEL-A", panel_mode="auto",
        cross_family_panel_iterate=1,
    ))
    assert rc == 0, "advisory dissent must never block the task"
    doc = yaml_io.load(repo / "tasks.yaml")
    row = next(t for t in doc["tasks"] if t["key"] == "PANEL-A")

    assert row["status"] == "Done"
    assert row["panel_consensus"] == "approve"
    assert row["panel_blocking_findings"] == 0
    assert "panel_iterations_used" not in row
    # Advisory verdicts must NOT leak into the authoritative YAML columns.
    assert "panel_verdict_grok" not in row
    # claude authored the task → excluded, so a surviving family carries the
    # authoritative APPROVE column instead.
    assert "panel_verdict_claude" not in row
    assert row["panel_verdict_gemini"] == "APPROVE"
    assert adv.call_count == 1

    events = _journal_events(repo)
    types = [e.event_type for e in events]
    assert "panel_iterate" not in types, "advisory findings must not trigger iterate"
    pv = next(e for e in events if e.event_type == "panel_verdict")
    assert pv.payload["advisory_verdicts"] == {"grok": "CHANGES_REQUESTED"}
    assert pv.payload["verdicts"] == {
        "gemini": "APPROVE", "codex": "APPROVE",
    }
    assert pv.payload["blocking_findings"] == 0

    adv_events = [e for e in events if e.event_type == "panel_advisory_finding"]
    assert len(adv_events) == 1
    payload = adv_events[0].payload
    assert payload["family"] == "grok"
    assert payload["severity"] == "CRITICAL"
    assert payload["location"] == "apps/wallet/payout.go:7"
    assert "rounding" in payload["description"]
    assert "banker" in payload["fix"]
    assert payload["advisory_verdict"] == "CHANGES_REQUESTED"
    assert adv_events[0].task_key == "PANEL-A"

    # Findings live in the clearly-labelled advisory appendix of summary.md,
    # and there is no blocking-findings section at all.
    summary_text = Path(row["summary_path"]).read_text(encoding="utf-8")
    assert "### Advisory reviewers (non-blocking, probationary)" in summary_text
    assert "payout.go:7" in summary_text
    assert "### Blocking findings" not in summary_text


def test_advisory_unavailable_panel_still_approves(repo: Path, monkeypatch) -> None:
    """Edge 1 (e2e): advisory CLI missing while authoritative 3/3 APPROVE →
    consensus "approve" (NOT "incomplete"); advisory_verdicts records
    UNAVAILABLE; no advisory finding events.
    """
    _seed_yaml(repo, _CRITICAL_TASK_YAML)
    _patch_spawn(monkeypatch)
    _set_reviewers(monkeypatch, [
        ("claude", _APPROVE_OUTPUT),
        ("gemini", _APPROVE_OUTPUT),
        ("codex", _APPROVE_OUTPUT),
    ])

    class _MissingGrok(cfr.Reviewer):
        family = "grok"
        def _invoke_cli(self, prompt: str) -> str:
            raise FileNotFoundError("grok not installed")

    orchestrator.set_panel_advisory_reviewers([_MissingGrok()])

    rc = orchestrator.execute(_args(repo, key="PANEL-A", panel_mode="auto"))
    assert rc == 0
    doc = yaml_io.load(repo / "tasks.yaml")
    row = next(t for t in doc["tasks"] if t["key"] == "PANEL-A")
    assert row["status"] == "Done"
    assert row["panel_consensus"] == "approve"

    events = _journal_events(repo)
    pv = next(e for e in events if e.event_type == "panel_verdict")
    assert pv.payload["advisory_verdicts"] == {"grok": "UNAVAILABLE"}
    assert not [e for e in events if e.event_type == "panel_advisory_finding"]


def test_advisory_findings_never_reach_iterate_prompt(repo: Path, monkeypatch) -> None:
    """Edge 3 (e2e): an authoritative reviewer blocks while advisory raises
    its own CRITICAL → consensus "block", and the corrective iterate prompt
    contains ONLY the authoritative findings.
    """
    _seed_yaml(repo, _CRITICAL_TASK_YAML)
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
    # claude (author) is excluded; both surviving families block (corroborated).
    revs = [
        _StubReviewer("gemini", _CHANGES_REQUESTED_OUTPUT),  # always blocks
        _StubReviewer("codex", _CHANGES_REQUESTED_OUTPUT),  # always blocks
    ]
    orchestrator.set_panel_reviewers(revs)
    orchestrator.set_panel_advisory_reviewers(
        [_StubReviewer("grok", _ADVISORY_CRITICAL_OUTPUT)]
    )

    rc = orchestrator.execute(_args(
        repo, key="PANEL-A", panel_mode="auto",
        cross_family_panel_iterate=1,
    ))
    assert rc == 1
    doc = yaml_io.load(repo / "tasks.yaml")
    row = next(t for t in doc["tasks"] if t["key"] == "PANEL-A")
    assert row["status"] == "Blocked"
    assert row["panel_consensus"] == "block"

    # Two spawns: initial + one iterate. The iterate prompt carries the
    # authoritative finding and NOT the advisory one.
    assert len(prompts) == 2
    iterate_prompt = prompts[1]
    assert "apps/wallet/service.go:42" in iterate_prompt
    assert "payout.go:7" not in iterate_prompt


def test_no_advisory_configured_is_noop(repo: Path, monkeypatch) -> None:
    """Edge 4 (e2e): no .dispatcher.yaml, no override → behaviour identical
    to today; advisory_verdicts is {} and no advisory events fire.
    """
    _seed_yaml(repo, _CRITICAL_TASK_YAML)
    _patch_spawn(monkeypatch)
    _set_reviewers(monkeypatch, [
        ("claude", _APPROVE_OUTPUT),
        ("gemini", _APPROVE_OUTPUT),
        ("codex", _APPROVE_OUTPUT),
    ])
    # Override deliberately left at None — config-derived path with no config.

    rc = orchestrator.execute(_args(repo, key="PANEL-A", panel_mode="auto"))
    assert rc == 0
    doc = yaml_io.load(repo / "tasks.yaml")
    row = next(t for t in doc["tasks"] if t["key"] == "PANEL-A")
    assert row["status"] == "Done"
    assert row["panel_consensus"] == "approve"

    events = _journal_events(repo)
    pv = next(e for e in events if e.event_type == "panel_verdict")
    assert pv.payload["advisory_verdicts"] == {}
    assert not [e for e in events if e.event_type == "panel_advisory_finding"]


def test_unknown_advisory_name_in_config_skipped_and_logged(repo: Path, monkeypatch) -> None:
    """Edge 5 (e2e): `.dispatcher.yaml` lists an unknown advisory family →
    it is skipped + logged and the authoritative panel runs normally.
    """
    (repo / ".dispatcher.yaml").write_text(
        "panel:\n  advisory: [foo]\n", encoding="utf-8",
    )
    _seed_yaml(repo, _CRITICAL_TASK_YAML)
    _patch_spawn(monkeypatch)
    _set_reviewers(monkeypatch, [
        ("claude", _APPROVE_OUTPUT),
        ("gemini", _APPROVE_OUTPUT),
        ("codex", _APPROVE_OUTPUT),
    ])

    rc = orchestrator.execute(_args(repo, key="PANEL-A", panel_mode="auto"))
    assert rc == 0
    doc = yaml_io.load(repo / "tasks.yaml")
    row = next(t for t in doc["tasks"] if t["key"] == "PANEL-A")
    assert row["status"] == "Done"
    assert row["panel_consensus"] == "approve"

    pv = next(e for e in _journal_events(repo)
              if e.event_type == "panel_verdict")
    assert pv.payload["advisory_verdicts"] == {}

    log_text = (repo / "_runs" / "panel-test" / "run.log").read_text(encoding="utf-8")
    assert "unknown advisory reviewer 'foo'" in log_text


def test_malformed_dispatcher_yaml_does_not_break_panel(repo: Path, monkeypatch) -> None:
    """A malformed `.dispatcher.yaml` (panel not a mapping) must be logged
    and the authoritative panel must still run — with no advisory seats.

    Since VG-2, the same malformed config (correctly) fails the mechanical
    verification gate FIRST — executable config rots loudly — so the task
    blocks before any panel fires and the run exits 1. The malformed-config-
    reaches-the-panel scenario is unreachable through the orchestrator now;
    the advisory loader's own graceful handling stays covered by its direct
    unit tests. This test asserts the gate-blocks-first ordering.
    """
    (repo / ".dispatcher.yaml").write_text(
        "panel: [not, a, mapping]\n", encoding="utf-8",
    )
    _seed_yaml(repo, _CRITICAL_TASK_YAML)
    _patch_spawn(monkeypatch)
    _set_reviewers(monkeypatch, [
        ("claude", _APPROVE_OUTPUT),
        ("gemini", _APPROVE_OUTPUT),
        ("codex", _APPROVE_OUTPUT),
    ])

    rc = orchestrator.execute(_args(repo, key="PANEL-A", panel_mode="auto"))
    assert rc == 1  # mechanical gate blocks on malformed config (VG-2)
    doc = yaml_io.load(repo / "tasks.yaml")
    row = next(t for t in doc["tasks"] if t["key"] == "PANEL-A")
    assert row["status"] == "Blocked"
    assert row["mechanical_verification"] == "failed"
    # Gate blocks BEFORE the panel: no panel events were emitted at all.
    assert not [e for e in _journal_events(repo)
                if e.event_type.startswith("panel_")]
    log_text = (repo / "_runs" / "panel-test" / "run.log").read_text(encoding="utf-8")
    assert "invalid .dispatcher.yaml" in log_text


def test_advisory_empty_list_override_forces_none(repo: Path, monkeypatch) -> None:
    """set_panel_advisory_reviewers([]) forces zero advisory seats even when
    the repo config asks for grok — [] and None are deliberately distinct,
    and this is also what keeps the real grok binary out of the test run.
    """
    (repo / ".dispatcher.yaml").write_text(
        "panel:\n  advisory: [grok]\n", encoding="utf-8",
    )
    _seed_yaml(repo, _CRITICAL_TASK_YAML)
    _patch_spawn(monkeypatch)
    _set_reviewers(monkeypatch, [
        ("claude", _APPROVE_OUTPUT),
        ("gemini", _APPROVE_OUTPUT),
        ("codex", _APPROVE_OUTPUT),
    ])
    orchestrator.set_panel_advisory_reviewers([])  # force NO advisory

    rc = orchestrator.execute(_args(repo, key="PANEL-A", panel_mode="auto"))
    assert rc == 0
    pv = next(e for e in _journal_events(repo)
              if e.event_type == "panel_verdict")
    assert pv.payload["advisory_verdicts"] == {}


def test_advisory_factory_reads_repo_config(tmp_path: Path) -> None:
    """Unit: the orchestrator factory resolves `panel: {advisory: [grok]}`
    from a repo root into a real GrokReviewer carrying the panel timeout —
    without running the panel.
    """
    (tmp_path / ".dispatcher.yaml").write_text(
        "panel:\n  advisory: [grok]\n", encoding="utf-8",
    )

    class _Cfg:
        cross_family_panel_timeout = 321

    reviewers = orchestrator._panel_advisory_reviewer_factory(
        _Cfg(), tmp_path, tmp_path / "run.log", "VG-T",
    )
    assert len(reviewers) == 1
    assert isinstance(reviewers[0], cfr.GrokReviewer)
    assert reviewers[0].timeout_seconds == 321
    # Sanity: the loader saw exactly what the factory consumed.
    assert repo_config.load(tmp_path).panel_advisory == ("grok",)
