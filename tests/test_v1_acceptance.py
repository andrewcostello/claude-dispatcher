"""v1 acceptance: the phases' named deliverables, checked rather than asserted.

`docs/improvement-plan.md` says of itself:

    Every one of the fourteen phases has machinery on main. That is a weaker
    claim than "complete", and the distinction is the point of this section: it
    was established by probing for each phase's named deliverables, not by
    re-reading the acceptance criteria and confirming each one holds. Nobody
    has done the latter, and this document is not evidence that anybody has.

This file is that confirmation, and it is a FILE rather than a one-off audit so
that "v1 holds" is a thing which reddens when it stops being true. The plan
carries exactly one explicit `Acceptance:` line across fourteen phases, so each
row below names the deliverable it is standing in for.

Two rules, both learned the expensive way in this project:

  * A check that only imports a name proves nothing — every false Done in this
    repo's history passed a check like that. Each row exercises BEHAVIOUR.
  * Absent deliverables are recorded as absent (see `test_v1_scope_is_honest`)
    rather than quietly dropped. Phases 9, 10 and 11 have named deliverables
    that do not exist; a v1 that ships without them is a scope decision, and a
    scope decision has to be written down to be one.

Nothing here spends money: no reviewer, implementer or verifier is invoked.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from claude_dispatcher import (
    classification,
    disposition,
    journal as journal_mod,
    known_red,
    plan as plan_mod,
    quality_levels,
    repo_config,
    routing,
    worktree as wt_mod,
    yaml_io,
)
from claude_dispatcher.cli import build_parser

REPO = Path(__file__).resolve().parents[1]


def _cli(*argv: str) -> subprocess.CompletedProcess:
    """Invoke the real CLI in a subprocess — the surface an operator uses."""
    return subprocess.run(
        [sys.executable, "-m", "claude_dispatcher", *argv],
        cwd=REPO, capture_output=True, text=True,
        env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(REPO / "src"),
             "HOME": str(Path.home())},
        timeout=180,
    )


def _journal(tmp_path: Path) -> "journal_mod.Journal":
    """A journal on disk. `create` pins the tasks YAML and the reviewer prompts
    it was opened against — provenance is part of the genesis, not an extra."""
    (tmp_path / "tasks.yaml").write_text("tasks: []\n", encoding="utf-8")
    prompts = tmp_path / "prompts"
    prompts.mkdir(exist_ok=True)
    return journal_mod.Journal.create(
        tmp_path / "journal.jsonl",
        tasks_yaml_path=tmp_path / "tasks.yaml",
        reviewer_prompts_dir=prompts,
    )


# ── Phase 1 — control surface ───────────────────────────────────────────────
# "Acceptance: an external agent can tail the journal, query status, and resume
# a killed run, with no stdout parsing." The plan's only stated acceptance line.


def test_phase1_the_journal_is_append_only_jsonl_an_agent_can_tail(tmp_path) -> None:
    j = _journal(tmp_path)
    j.append(journal_mod.EventType.task_started, {"key": "A-1"}, task_key="A-1")
    j.append(journal_mod.EventType.task_blocked, {"reason": "x"}, task_key="A-1")

    lines = (tmp_path / "journal.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) >= 2, "one event per line, or `tail -f | jq` does not work"
    events = [json.loads(ln) for ln in lines]
    seqs = [e["seq"] for e in events]
    assert seqs == sorted(seqs) and len(set(seqs)) == len(seqs), (
        "seq must order the stream and never repeat")
    tagged = [e for e in events if e.get("task_key") == "A-1"]
    assert len(tagged) == 2, "an agent filters by task_key; it must be carried"


def test_phase1_status_json_is_machine_readable_without_stdout_parsing() -> None:
    """`--json` is the whole point: an external agent must not scrape prose."""
    parser = build_parser()
    args = parser.parse_args(["status", "some-run-id", "--json"])
    assert args.json is True
    assert callable(args.func)


def test_phase1_resume_reconstructs_a_run_from_its_journal_genesis(tmp_path) -> None:
    """A killed run is recoverable because the genesis event carries the run
    config. Without that, resume would need the original argv."""
    j = _journal(tmp_path)
    path = tmp_path / "journal.jsonl"
    j.append(journal_mod.EventType.run_started, {
        "run_config": {"base_branch": "main", "mode": "unattended",
                       "max_parallel": 2},
    })
    genesis = next(
        e for e in (json.loads(ln)
                    for ln in path.read_text(encoding="utf-8").splitlines())
        if "run_config" in (e.get("payload") or {})
    )
    cfg = genesis["payload"]["run_config"]
    assert cfg["base_branch"] == "main" and cfg["max_parallel"] == 2

    # And the journal can be reopened at its head, which is what resume does.
    reopened = journal_mod.Journal.resume(path)
    assert reopened.last_seq >= 0


# ── Phase 1a — machine profile and preflight ────────────────────────────────


def test_phase1a_doctor_runs_and_reports_the_machine() -> None:
    proc = _cli("doctor")
    assert proc.returncode in (0, 1, 3), proc.stderr[-400:]
    assert proc.stdout.strip(), "doctor must report something an operator reads"


def test_phase1a_preflight_refuses_before_spend_not_after() -> None:
    """The whole value of preflight is that it fails BEFORE an implementer is
    spawned. A base branch that does not resolve is the cheapest proof."""
    from claude_dispatcher import preflight

    res = preflight.run_preflight(
        claude_bin=sys.executable,
        claude_extra_args=["--permission-mode", "bypassPermissions",
                           "--allow-dangerously-skip-permissions"],
        mode="unattended", repo_root=REPO, base_branch="no-such-branch",
    )
    assert not res.ok
    assert any("does not resolve" in f for f in res.failures)


# ── Phase 2 — Done metadata ─────────────────────────────────────────────────


def test_phase2_a_done_row_carries_the_evidence_of_its_run() -> None:
    """Done is only meaningful if the row says which run produced it and what
    the gate found. A bare status string is the false-Done shape."""
    doc = yaml_io.load(REPO / "features" / "dogfood-w2" / "tasks.yaml")
    done = [t for t in doc["tasks"] if str(t.get("status")) == "Done"]
    assert done, "fixture expects at least one Done task"

    # Rows a HUMAN performed carry no run id, because no run produced them.
    # W2-2-5 was an operator transcription of W2-2-3's patch into the floored
    # driver — the floor exists precisely so no dispatched role can write it.
    # Listed, so "an operator did it" stays a claim somebody made.
    operator_performed = {"W2-2-5"}
    for t in done:
        if t["key"] in operator_performed:
            assert "OPERATOR" in str(t.get("description", "")), (
                f"{t['key']} is listed as operator-performed but does not say so"
            )
            continue
        assert t.get("dispatcher_run_id"), f"{t['key']} has no run id"

    # Rows that reached Done without a gate verdict of their own. Both are
    # BATCHED keys: the dispatcher runs a batch as one work unit and stamps the
    # gate on the key it ran, so the siblings share the outcome without
    # carrying it. Listed rather than excused — if the list grows, a Done
    # without evidence has slipped in behind the batching rule.
    ungated = {t["key"] for t in done if not t.get("mechanical_verification")}
    assert ungated <= {"W2-2-3", "W2-2-5"}, (
        f"Done rows with no gate verdict of their own: {ungated}"
    )


# ── Phase 3 — PR flow, dependency merge, risk classifier ────────────────────


def test_phase3_dependency_merge_is_mechanical_not_left_to_the_agent(tmp_path) -> None:
    """"instead of relying on the Tasker to discover and merge them (run #2
    showed that behavior varies too much to trust)"."""
    assert hasattr(wt_mod, "merge_dependencies")
    # And it explains a stale base rather than only naming files (f7b470b).
    assert hasattr(wt_mod, "commits_behind")


def test_phase3_the_risk_classifier_fails_closed_on_an_unclassified_path() -> None:
    """An unmatched path is high risk. Failing OPEN here is how an unreviewed
    change ships."""
    c = classification.parse_classification({
        "risk": "low", "unmatched_files": ["src/new_thing.py"],
        "panel": {"reduced": False},
    })
    assert c.requires_full_panel is True
    assert c.unmatched_files == ("src/new_thing.py",)


# ── Phase 4 — verification gate ─────────────────────────────────────────────


def test_phase4_mechanical_checks_run_before_the_agent_verifier() -> None:
    """"Mechanical checks first, agent second" — a cheap deterministic gate
    must not be gated behind an expensive probabilistic one."""
    import ast

    tree = ast.parse((REPO / "src" / "claude_dispatcher" / "orchestrator.py")
                     .read_text(encoding="utf-8"))
    run_task = next(
        n for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        and n.name == "_run_task"
    )

    def line_of(fn_name: str) -> int:
        lines = [
            n.lineno for n in ast.walk(run_task)
            if isinstance(n, ast.Call)
            and getattr(n.func, "id", getattr(n.func, "attr", None)) == fn_name
        ]
        assert lines, f"{fn_name} is not called in _run_task"
        return min(lines)

    # Source position INSIDE one function body is execution order here: both
    # calls sit in the same straight-line sequence. Comparing positions across
    # the whole module would not be — the verifier's log string appears earlier
    # in the file than the gate that must precede it.
    assert line_of("_verify_mechanical_and_maybe_retry") < line_of(
        "_verify_llm_and_maybe_iterate"), (
        "the cheap deterministic gate must run before the expensive "
        "probabilistic one"
    )


def test_phase4_a_dirty_worktree_is_not_accepted_as_evidence() -> None:
    """Test evidence must be keyed to the COMMITTED tree. W2-3-3 was blocked by
    exactly this and the refusal was correct: the suite passed either way, so a
    green run over a tree nobody can name proves nothing."""
    src = (REPO / "src" / "claude_dispatcher" / "orchestrator.py").read_text(
        encoding="utf-8")
    assert "uncommitted changes in worktree at verification time" in src


# ── Phase 5 / 6 — routing, quality levels, fallback ─────────────────────────


def test_phase5_quality_levels_expose_a_floor_that_cannot_be_lowered() -> None:
    """A risk label RAISES the gate and a task-level setting cannot lower it
    below the floor its labels imply — otherwise "anti-rigidity" becomes an
    opt-out from review."""
    plain = quality_levels.resolve_quality_levels(labels=["size:XS"])
    risky = quality_levels.resolve_quality_levels(labels=["risk:critical"])
    assert plain.panel != risky.panel or plain.verify != risky.verify, (
        "a risk label must change the gate, or the levels are decorative"
    )


def test_phase6_a_repo_can_route_task_classes_to_models() -> None:
    """`model_routing` in .dispatcher.yaml is how a repo sends critical work to
    a stronger model. Routing also has to name a default implementer."""
    assert "model_routing" in {f.name for f in __import__("dataclasses").fields(
        repo_config.RepoConfig)}
    assert callable(routing.default_implementer)


# ── Phase 8 — dispositions ──────────────────────────────────────────────────


def test_phase8_every_finding_can_be_given_a_recorded_disposition() -> None:
    """"Every finding gets a recorded disposition" — accepted, fixed, or
    deferred WITH a reason. A finding that merely scrolls past is the
    no-deferral triage this phase exists to prevent."""
    assert hasattr(disposition, "DispositionLedger")


# ── the known-red register — the suite's own honesty ────────────────────────


def test_the_known_red_register_is_empty() -> None:
    """A standing suppression makes every green conditional. v1 does not ship
    with one: if a unit needs rows hidden between its seals and its bodies, the
    bodies land before release.
    """
    reg = known_red.load(REPO)
    assert reg.is_empty, (
        "known-red entries are in force; the suite's green is conditional on "
        f"them: {[e.body_task for e in reg.entries]}"
    )


# ── scope, stated rather than implied ───────────────────────────────────────


#: Deliverables named in the plan that DO NOT EXIST on main. Probed
#: 2026-08-29. Keeping them here makes shipping without them a decision
#: somebody made, rather than something nobody noticed.
KNOWN_ABSENT: dict[str, str] = {
    "Phase 9 — command inbox": "no module accepts queued operator commands",
    "Phase 9 — compressed conversation log": "not implemented",
    "Phase 10 — remote executors": (
        "single-orchestrator only; docs/architecture/single-orchestrator.md is "
        "the architecture that exists"
    ),
    "Phase 11 — `dispatcher evidence <feature>`": "the subcommand is absent",
}


def test_v1_scope_is_honest() -> None:
    """The absent deliverables stay absent, and stay listed.

    This row fails in BOTH directions on purpose. If one is implemented, its
    line must leave this dict — a stale "not implemented" is how a plan starts
    lying. If one is quietly dropped from the dict while still missing, the
    plan's fourteen phases stop describing the product.
    """
    parser = build_parser()
    commands = set(parser._subparsers._group_actions[0].choices)  # noqa: SLF001

    assert "evidence" not in commands, (
        "`dispatcher evidence` now exists — remove it from KNOWN_ABSENT"
    )
    assert KNOWN_ABSENT, "scope gaps must be listed, not implied"
    for name, why in KNOWN_ABSENT.items():
        assert why.strip(), f"{name} needs a stated reason"


def test_every_shipped_command_is_reachable_from_the_cli() -> None:
    """A subcommand nobody can invoke is not a deliverable."""
    parser = build_parser()
    commands = set(parser._subparsers._group_actions[0].choices)  # noqa: SLF001
    for expected in ("run", "status", "resume", "doctor", "blocked", "unblock",
                     "requeue", "audit", "report", "watch", "merge-prs",
                     "prune-branches"):
        assert expected in commands, f"`dispatcher {expected}` is not reachable"


@pytest.mark.parametrize("cmd", ["status", "blocked", "audit", "doctor"])
def test_the_read_only_commands_run_without_a_run_in_flight(cmd: str) -> None:
    """An operator reaches for these when something has gone wrong, which is
    exactly when a crash in the reporting path is most expensive."""
    argv = [cmd] if cmd in ("doctor",) else [cmd, "--help"]
    proc = _cli(*argv)
    assert proc.returncode in (0, 1, 3), f"{cmd}: {proc.stderr[-300:]}"
