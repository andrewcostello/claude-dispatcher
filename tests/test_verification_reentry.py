"""Corrective spawns must re-enter acceptance over their resulting revision."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from claude_dispatcher import journal, orchestrator as orch, spawn, verifier, yaml_io
from test_orchestrator_panel import (
    FAKE_CLAUDE, _APPROVE_OUTPUT, _CHANGES_REQUESTED_OUTPUT,
    _CRITICAL_TASK_YAML, _SequencedStubReviewer, _args, _seed_yaml, repo,
)


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True,
        text=True, timeout=30,
    ).stdout.strip()


def _commit(root: Path, message: str) -> None:
    _git(root, "add", ".")
    _git(root, "-c", "commit.gpgsign=false", "commit", "-m", message)


def _run_retry(
    repo, monkeypatch, *, origin, regression=False, foreign_delete=False,
    on_spawn=None, on_stage=None, verify_outcomes=None, panel_outputs=None,
    seal_outcomes=None, run_overrides=None, verifier_cost=None, retry_exit=0,
):
    _git(repo, "config", "core.hooksPath", "/dev/null")
    (repo / "correctness.txt").write_text("good\n", encoding="utf-8")
    (repo / "foreign.txt").write_text("must survive\n", encoding="utf-8")
    (repo / "check.py").write_text(
        "from pathlib import Path\n"
        "assert Path('correctness.txt').read_text() == 'good\\n'\n",
        encoding="utf-8",
    )
    (repo / ".dispatcher.yaml").write_text(
        f"test: {sys.executable} -B check.py\n", encoding="utf-8",
    )
    task = _CRITICAL_TASK_YAML.replace(
        "labels: [size:XS, risk:critical]",
        "labels: [size:XS, risk:critical, seal-check]\n"
        "    owns: [correctness.txt, 'implemented-*.txt', correction.txt]",
    )
    _seed_yaml(repo, task)
    monkeypatch.setenv("FAKE_CLAUDE_SCENARIO", "done")
    monkeypatch.delenv("FAKE_CLAUDE_KILL_KEY", raising=False)
    stages: list[tuple[str, str]] = []
    spawns: list[Path] = []

    def record(stage, root):
        stages.append((stage, _git(root, "rev-parse", "HEAD")))
        if on_stage is not None:
            on_stage(stage, root)

    def fake_spawn(claude_bin, cwd, env, prompt, extra_args=None, timeout_seconds=3600):
        proc = subprocess.run(
            [sys.executable, str(FAKE_CLAUDE)], input=prompt, capture_output=True,
            text=True, cwd=cwd, env=env, timeout=30,
        )
        root = Path(cwd)
        spawns.append(root)
        if len(spawns) > 12:
            pytest.fail("acceptance restarts did not retain their retry budgets")
        if len(spawns) == 1 and origin == "mechanical":
            (root / "correctness.txt").write_text("broken\n", encoding="utf-8")
            _commit(root, "initial defect")
        if len(spawns) >= 2:
            (root / "correctness.txt").write_text(
                "broken\n" if regression else "good\n", encoding="utf-8",
            )
            (root / "correction.txt").write_text(
                f"correction {len(spawns)}\n", encoding="utf-8",
            )
            if foreign_delete:
                (root / "foreign.txt").unlink()
            _commit(root, "corrective change")
        if on_spawn is not None:
            on_spawn(root, len(spawns), env)
        return spawn.SpawnResult(
            exit_code=retry_exit if len(spawns) == 2 else proc.returncode,
            summary_path=Path(env["SUMMARY_PATH"]),
            stdout=proc.stdout, stderr=proc.stderr,
        )

    monkeypatch.setattr(spawn, "spawn_claude", fake_spawn)
    original_role = orch.loop_gate_mod.check_after_implementer

    def role(**kwargs):
        record("role", kwargs["repo_root"])
        return original_role(**kwargs)

    monkeypatch.setattr(orch.loop_gate_mod, "check_after_implementer", role)
    original_holes = orch._check_declared_holes

    def holes(cfg, snap, wt, log_path):
        record("holes", wt.path)
        return original_holes(cfg, snap, wt, log_path)

    monkeypatch.setattr(orch, "_check_declared_holes", holes)
    original_test = orch.mv_mod.run_test_command

    def test_command(*args, **kwargs):
        record("mechanical", kwargs["worktree"])
        return original_test(*args, **kwargs)

    monkeypatch.setattr(orch.mv_mod, "run_test_command", test_command)

    def seal(cfg, snap, wt, base_sha, log_path):
        record("seal", wt.path)
        if seal_outcomes:
            count = sum(stage == "seal" for stage, _ in stages)
            outcome = seal_outcomes[min(count - 1, len(seal_outcomes) - 1)]
            return outcome, "seal regression" if outcome != "passed" else None
        return "passed", None

    monkeypatch.setattr(orch, "_verify_seal", seal)
    verifier_calls = []

    def verify(**kwargs):
        verifier_calls.append(kwargs)
        record("verifier", spawns[-1])
        if verify_outcomes:
            incomplete = verify_outcomes[min(len(verifier_calls) - 1, len(verify_outcomes) - 1)] == "incomplete"
        else:
            incomplete = origin == "verifier" and len(verifier_calls) == 1
        return verifier.VerifierResult(verdict=verifier.VerifierVerdict(
            verdict=verifier.VerdictKind.INCOMPLETE if incomplete else verifier.VerdictKind.VERIFIED,
            gaps=[verifier.Gap(index=1, location="correctness.txt", description="complete the change")] if incomplete else [],
        ), usage=spawn.SpawnUsage(cost_usd=verifier_cost))

    orch.set_verifier(verify)
    original_panel = orch._run_cross_family_panel

    def panel(**kwargs):
        record("panel", kwargs["wt"].path)
        return original_panel(**kwargs)

    monkeypatch.setattr(orch, "_run_cross_family_panel", panel)
    outputs = panel_outputs or ([_CHANGES_REQUESTED_OUTPUT, _APPROVE_OUTPUT]
               if origin == "panel" else [_APPROVE_OUTPUT])
    orch.set_panel_reviewers([_SequencedStubReviewer(f, outputs) for f in ("gemini", "codex")])
    try:
        options = {"cross_family_panel_iterate": 1, **(run_overrides or {})}
        rc = orch.execute(_args(repo, key="PANEL-A", **options))
    finally:
        orch.set_panel_reviewers(None)
    row = yaml_io.load(repo / "tasks.yaml")["tasks"][0]
    return rc, row, stages, spawns


@pytest.mark.parametrize("origin", ["mechanical", "verifier", "panel"])
def test_correction_rechecks_every_acceptance_stage(repo, monkeypatch, origin):
    rc, row, stages, spawns = _run_retry(repo, monkeypatch, origin=origin)
    assert rc == 0 and row["status"] == "Done", row
    assert len(spawns) == 2
    head = _git(spawns[-1], "rev-parse", "HEAD")
    current = [stage for stage, sha in stages if sha == head]
    assert current == ["role", "holes", "mechanical", "seal", "verifier", "panel"], stages


def test_panel_regression_cannot_keep_earlier_green_evidence(repo, monkeypatch):
    rc, row, stages, spawns = _run_retry(repo, monkeypatch, origin="panel", regression=True)
    assert rc != 0 and row["status"] == "Blocked", row
    assert row.get("mechanical_verification") == "failed", row
    assert row.get("verified") is not True, row
    assert row.get("panel_consensus") != "approve", row
    assert [stage for stage, _ in stages].count("panel") == 1, stages


@pytest.mark.parametrize("origin", ["mechanical", "verifier", "panel"])
def test_correction_cannot_delete_a_foreign_owned_file(repo, monkeypatch, origin):
    monkeypatch.setattr(orch, "_implementer_cascade", lambda *a, **kw: [
        ("claude", "medium"), ("claude", "high"),
    ])
    rc, row, stages, spawns = _run_retry(repo, monkeypatch, origin=origin, foreign_delete=True)
    assert rc != 0 and row["status"] == "Blocked", row
    assert "scope excursion" in row["blocked_reason"], row
    assert len(spawns) == 2
    assert not (spawns[-1] / "foreign.txt").exists(), "retain the blocked branch for adjudication"


def _events(repo):
    return list(journal.read_events(repo / "_runs/panel-test" / journal.JOURNAL_FILENAME))


def test_restart_journal_identifies_each_candidate(repo, monkeypatch):
    rc, row, stages, spawns = _run_retry(repo, monkeypatch, origin="panel")
    assert rc == 0, row
    events = _events(repo)
    roles = [e.payload for e in events if e.event_type == "role_diff_loop_gate"]
    assert [p["verification_generation"] for p in roles] == [0, 1]
    assert [p["head_sha"] for p in roles] == [sha for stage, sha in stages if stage == "role"]
    assert roles[0]["base_ref"] == roles[1]["base_ref"]
    assert roles[0]["head_sha"] != roles[1]["head_sha"]
    summaries = [e.payload for e in events if e.event_type == "summary_parsed"]
    assert summaries[-1]["after_verification_restart"] is True
    assert summaries[-1]["verification_generation"] == 1


def test_mixed_panel_and_test_fixes_require_one_complete_final_pass(repo, monkeypatch):
    def break_tests(root, count, env):
        if count == 2:
            (root / "correctness.txt").write_text("broken\n", encoding="utf-8")
            _commit(root, "panel fix introduced regression")

    rc, row, stages, spawns = _run_retry(
        repo, monkeypatch, origin="panel", on_spawn=break_tests,
    )
    assert rc == 0 and row["status"] == "Done", row
    assert len(spawns) == 3
    assert row["panel_iterations_used"] == 1
    head = _git(spawns[-1], "rev-parse", "HEAD")
    assert [stage for stage, sha in stages if sha == head] == [
        "role", "holes", "mechanical", "seal", "verifier", "panel",
    ]
    mechanical = [e.payload for e in _events(repo) if e.event_type == "verification_mechanical"]
    assert [p["outcome"] for p in mechanical] == ["passed", "failed", "passed"]
    assert [p["retried"] for p in mechanical] == [False, False, True]


def test_verifier_budget_is_not_renewed_by_a_panel_fix(repo, monkeypatch):
    rc, row, stages, spawns = _run_retry(
        repo, monkeypatch, origin="verifier",
        verify_outcomes=["incomplete", "verified", "incomplete"],
        panel_outputs=[_CHANGES_REQUESTED_OUTPUT, _APPROVE_OUTPUT],
        # Critical work resolves to llm_strict, which adds one retry.
        run_overrides={"max_verify_iterations": 0},
    )
    assert rc != 0 and row["status"] == "Blocked", row
    assert row["blocked_reason"] == "verification_incomplete", row
    assert row["verification_iterations"] == 1
    assert len(spawns) == 3, "the panel restart must not grant another verifier fix"
    assert [stage for stage, _ in stages].count("panel") == 1


def test_panel_budget_is_not_renewed_by_a_verifier_fix(repo, monkeypatch):
    rc, row, stages, spawns = _run_retry(
        repo, monkeypatch, origin="panel",
        verify_outcomes=["verified", "incomplete", "verified"],
        panel_outputs=[_CHANGES_REQUESTED_OUTPUT],
        run_overrides={"max_verify_iterations": 1},
    )
    assert rc != 0 and row["status"] == "Blocked", row
    assert "cross_family_panel" in row["blocked_reason"], row
    assert row["panel_iterations_used"] == 1
    assert len(spawns) == 3, "the verifier restart must not grant another panel fix"
    assert [stage for stage, _ in stages].count("panel") == 2


def test_once_required_panel_cannot_be_dropped_on_reentry(repo, monkeypatch):
    classifications = []

    def classify(**kwargs):
        classifications.append(kwargs)
        if len(classifications) == 1:
            return SimpleNamespace(
                requires_full_panel=True, risk="critical", components=("wallet",),
                financial_paths_touched=True, summary_line=lambda: "wallet change",
            )
        return None

    monkeypatch.setattr(orch, "_panel_should_run", lambda *a: False)
    monkeypatch.setattr(orch, "_panel_gate_classification", classify)
    rc, row, stages, spawns = _run_retry(repo, monkeypatch, origin="panel")
    assert rc == 0 and row["status"] == "Done", row
    assert len(spawns) == 2
    assert [stage for stage, _ in stages].count("panel") == 2
    assert len(classifications) == 1, "the first required-panel decision is retained"


@pytest.mark.parametrize("budget,patience,rounds", [(1, 0, 2), (8, 2, 3)])
def test_panel_budget_and_convergence_history_reset_only_for_a_new_rung(
    repo, monkeypatch, budget, patience, rounds,
):
    monkeypatch.setattr(orch, "_implementer_cascade", lambda *a, **kw: [
        ("claude", "medium"), ("claude", "high"),
    ])
    rc, row, stages, spawns = _run_retry(
        repo, monkeypatch, origin="panel",
        panel_outputs=[_CHANGES_REQUESTED_OUTPUT] * (2 * rounds - 1) + [_APPROVE_OUTPUT],
        run_overrides={"cross_family_panel_iterate": budget, "panel_convergence_patience": patience},
    )
    assert rc == 0 and row["status"] == "Done", row
    assert len(spawns) == 2 * rounds
    assert row["panel_iterations_used"] == rounds - 1
    events = _events(repo)
    assert len([e for e in events if e.event_type == "agent_fallback"]) == 1
    used = [e.payload["iteration"] for e in events if e.event_type == "panel_iterate"]
    assert used == list(range(1, rounds)) * 2
    generations = [e.payload["verification_generation"] for e in events if e.event_type == "role_diff_loop_gate"]
    assert generations == list(range(rounds)) * 2


def test_mechanical_retry_cannot_weaken_its_original_command(repo, monkeypatch):
    def weaken_command(root, count, env):
        if count == 2:
            (root / ".dispatcher.yaml").write_text("test: 'true'\n", encoding="utf-8")
            _commit(root, "attempt to replace the failing command")

    rc, row, stages, spawns = _run_retry(
        repo, monkeypatch, origin="mechanical", regression=True,
        on_spawn=weaken_command,
    )
    assert rc != 0 and row["status"] == "Blocked", row
    assert row["mechanical_verification"] == "failed", row
    assert len(spawns) == 2
    assert [stage for stage, _ in stages].count("mechanical") == 2


@pytest.mark.parametrize("origin", ["verifier", "panel"])
def test_new_seal_failure_stops_downstream_review(repo, monkeypatch, origin):
    rc, row, stages, spawns = _run_retry(
        repo, monkeypatch, origin=origin, seal_outcomes=["passed", "failed"],
    )
    assert rc != 0 and row["status"] == "Blocked", row
    assert row["seal_verification"] == "failed", row
    assert row["blocked_reason"] == "seal_verification_failed", row
    assert row.get("verified") is not True, row
    assert row.get("panel_consensus") != "approve", row
    assert len(spawns) == 2
    head = _git(spawns[-1], "rev-parse", "HEAD")
    assert [stage for stage, sha in stages if sha == head] == ["role", "holes", "mechanical", "seal"]


@pytest.mark.parametrize("origin", ["mechanical", "verifier", "panel"])
def test_corrective_dirty_tree_cannot_reuse_green_checks(repo, monkeypatch, origin):
    def leave_dirty(root, count, env):
        if count == 2:
            (root / "correctness.txt").write_text("uncommitted\n", encoding="utf-8")

    rc, row, stages, spawns = _run_retry(
        repo, monkeypatch, origin=origin, on_spawn=leave_dirty,
    )
    assert rc != 0 and row["status"] == "Blocked", row
    assert row["mechanical_verification"] == "failed", row
    assert "uncommitted changes" in row["mechanical_verification_detail"], row
    assert row.get("verified") is not True, row
    assert row.get("panel_consensus") != "approve", row


@pytest.mark.parametrize("origin", ["mechanical", "verifier", "panel"])
def test_corrective_summary_must_be_read_again(repo, monkeypatch, origin):
    def invalidate_summary(root, count, env):
        if count == 2:
            Path(env["SUMMARY_PATH"]).write_text("not a task summary\n", encoding="utf-8")

    rc, row, stages, spawns = _run_retry(
        repo, monkeypatch, origin=origin, on_spawn=invalidate_summary,
    )
    assert rc != 0 and row["status"] == "Blocked", row
    assert "summary_malformed after corrective spawn" in row["blocked_reason"], row
    assert row.get("mechanical_verification") is None, row
    assert row.get("verified") is not True, row
    assert row.get("panel_consensus") != "approve", row
    assert len(spawns) == 2


@pytest.mark.parametrize("origin", ["verifier", "panel"])
def test_failed_corrective_spawn_drops_previous_green_stamps(repo, monkeypatch, origin):
    rc, row, stages, spawns = _run_retry(
        repo, monkeypatch, origin=origin, retry_exit=1,
    )
    assert rc != 0 and row["status"] == "Blocked", row
    assert len(spawns) == 2
    assert row.get("mechanical_verification") is None, row
    assert row.get("seal_verification") is None, row
    assert row.get("verified") is not True, row
    assert row.get("panel_consensus") != "approve", row


@pytest.mark.parametrize("stage", ["mechanical", "verifier", "panel"])
@pytest.mark.parametrize("committed", [False, True])
def test_unrequested_changes_during_verification_invalidate_approval(
    repo, monkeypatch, stage, committed,
):
    def mutate_verification(current, root):
        if current == stage:
            (root / "correction.txt").write_text("reviewers must not change code\n", encoding="utf-8")
            if committed:
                _commit(root, "unexpected verification mutation")

    rc, row, stages, spawns = _run_retry(
        repo, monkeypatch, origin="none", on_stage=mutate_verification,
    )
    assert rc != 0 and row["status"] == "Blocked", row
    assert "verification_subject_changed" in row["blocked_reason"], row
    assert row.get("mechanical_verification") is None, row
    assert row.get("seal_verification") is None, row
    assert row.get("verified") is not True, row
    assert row.get("panel_consensus") != "approve", row
    assert len(spawns) == 1


@pytest.mark.parametrize("foreign_delete", [False, True])
def test_verifier_cost_is_charged_once_even_if_reentry_blocks(repo, monkeypatch, foreign_delete):
    rc, row, stages, spawns = _run_retry(
        repo, monkeypatch, origin="verifier", foreign_delete=foreign_delete,
        verifier_cost=0.125,
    )
    assert row["status"] == ("Blocked" if foreign_delete else "Done"), row
    expected_calls = 1 if foreign_delete else 2
    assert [stage for stage, _ in stages].count("verifier") == expected_calls
    assert row["cost_usd"] == pytest.approx(0.125 * expected_calls), row


def test_unknown_restart_trigger_does_not_mutate_cycle():
    cycle = orch._VerificationCycle()
    with pytest.raises(ValueError, match="unknown verification restart trigger"):
        cycle.restart("typo")
    assert cycle == orch._VerificationCycle()


def test_retry_cycles_do_not_share_mutable_budgets():
    first = orch._VerificationCycle(verifier_iterations=2, mechanical_retried=True)
    second = orch._VerificationCycle()
    with pytest.raises(orch._VerificationRestart, match="panel"):
        first.restart("panel")
    assert first.verifier_iterations == 2
    assert first.generation == 1 and first.invalidated
    assert first.mechanical_retried is False
    assert second == orch._VerificationCycle()


@pytest.mark.parametrize("mutation", ["none", "dirty", "commit"])
def test_push_recovery_cannot_change_the_accepted_subject(repo, monkeypatch, mutation):
    reads = []
    recoveries = []

    def push_state(**kwargs):
        reads.append(kwargs)
        return orch.pv_mod.PushVerifyResult(
            status="not-pushed" if len(reads) == 1 else "ok",
        )

    def recover(cfg, snap, wt, summary_path, env, log_path, **kwargs):
        recoveries.append(wt.path)
        if mutation != "none":
            (wt.path / "correction.txt").write_text("not a push-only repair\n", encoding="utf-8")
            if mutation == "commit":
                _commit(wt.path, "unexpected push recovery commit")
        return True

    monkeypatch.setattr(orch.pv_mod, "verify", push_state)
    monkeypatch.setattr(orch, "_mechanical_push_recovery", lambda *a, **kw: False)
    monkeypatch.setattr(orch, "_retry_for_push", recover)
    rc, row, stages, spawns = _run_retry(repo, monkeypatch, origin="none")
    assert len(recoveries) == 1 and len(reads) == 2
    if mutation == "none":
        assert rc == 0 and row["status"] == "Done", row
        assert row["verified"] is True
        return
    assert rc != 0 and row["status"] == "Blocked", row
    assert "verification_subject_changed" in row["blocked_reason"], row
    assert "after push recovery" in row["blocked_reason"], row
    assert row.get("mechanical_verification") is None, row
    assert row.get("seal_verification") is None, row
    assert row.get("verified") is not True, row
    assert row.get("panel_consensus") != "approve", row
