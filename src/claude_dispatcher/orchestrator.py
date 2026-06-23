"""Core orchestrator: pick runnable tasks, spawn, parse, write back.

This is the live-spawn loop. dry-run does not invoke this module.

Concurrency model (step 7):
  - The main thread maintains the set of in-flight task keys.
  - Each task's full lifecycle (mark In Progress → spawn → parse → write final)
    runs on a worker thread.
  - YAML mutations happen via load-mutate-save cycles under the FileLock —
    each cycle re-reads fresh state and writes back atomically. Workers never
    share an in-memory doc.
  - The main thread waits on as_completed() for any worker to finish, then
    recomputes the runnable set (which may include newly-unblocked tasks).
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import sys
import threading
from concurrent.futures import (
    FIRST_COMPLETED,
    Future,
    ThreadPoolExecutor,
    wait,
)
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import __version__
from . import auto_integrate as ai_mod
from . import cross_family_reviewer as cfr_mod
from . import disposition as disposition_mod
from . import journal as journal_mod
from . import mechanical_verify as mv_mod
from . import merge_engine as merge_mod
from . import notify as notify_mod
from . import plan as plan_mod
from . import pr as pr_mod
from . import preflight as preflight_mod
from . import push_verify as pv_mod
from . import repo_config as repo_config_mod
from . import spawn as spawn_mod
from . import summary as summary_mod
from . import verifier as verifier_mod
from . import worktree as wt_mod
from . import yaml_io


# Injectable I/O for supervised mode. Tests replace `_prompt_human` with a
# scripted responder so they don't need a real stdin.
_prompt_human_impl = None  # type: ignore[var-annotated]
_prompt_human_lock = threading.Lock()


def set_prompt_responder(fn) -> None:
    """Override how supervised mode prompts the human. Used by tests."""
    global _prompt_human_impl
    _prompt_human_impl = fn


def _ask_human(prompt_text: str, choices: list[str]) -> str:
    """Print `prompt_text`, accept one of `choices` from stdin (or the
    injected responder). Serialized across workers so supervised prompts
    don't interleave when multiple workers gate-fire concurrently.
    """
    with _prompt_human_lock:
        if _prompt_human_impl is not None:
            return _prompt_human_impl(prompt_text, choices)
        print(prompt_text)
        while True:
            raw = input(f"  Choice [{'/'.join(choices)}]: ").strip().lower()
            if raw in choices:
                return raw
            print(f"  invalid response — must be one of {choices}")


_log_lock = threading.Lock()


# How often the dispatch loop appends a `heartbeat` event to the journal while
# running. The journal's most-recent-event age is the liveness signal
# `dispatcher resume` reads to decide whether a run is still active; a periodic
# heartbeat keeps that signal fresh even during a long single-task spawn that
# emits no other events for hours. Must stay comfortably below
# resume.RUN_ACTIVE_THRESHOLD_SECONDS so a live run always trips the guard.
HEARTBEAT_INTERVAL_SECONDS = 30


@dataclass
class RunConfig:
    tasks_path: Path
    runs_dir: Path
    run_id: str
    mode: str
    max_parallel: int
    max_iterations: int
    reviewer_count: int | None
    skip_design: bool
    skip_security_linter: bool
    financial_paths: str
    claude_bin: str
    worktree_base: Path | None
    label_filter: list[tuple[str, str]]
    only_keys: list[str] | None
    gh_bin: str = "gh"
    claude_extra_args: list[str] = field(default_factory=list)
    base_branch: str = "main"
    # Integration mode (PRF-1). "branch" (default) forks each task worktree
    # directly from base_branch, as today. "pr" runs the whole run off a
    # shared run-level feature branch: at run start it is created from
    # base_branch if absent, and base_branch is then REPOINTED to the feature
    # branch so it becomes the effective base for worktree creation,
    # dependency-merge reachability checks, and diff baselines (every site
    # that already reads base_branch). The resolution (CLI > .dispatcher.yaml
    # > "branch") and the feature-branch creation happen in execute(); resume
    # rebuilds from the genesis, where base_branch is already the feature
    # branch, so it forks correctly without re-creating anything.
    integration: str = "branch"
    # In pr mode: the resolved feature branch name, its tip SHA at run start,
    # and whether it was "created" this run or "existing". All None in branch
    # mode. Recorded in the genesis run_config (PRF-1 acceptance).
    feature_branch: str | None = None
    feature_branch_sha: str | None = None
    feature_branch_status: str | None = None
    # How long to wait for the tasks-YAML FileLock before raising LockTimeout
    # (seconds). Threaded into every FileLock acquisition in the run path.
    lock_timeout_seconds: float = 30.0
    # Per-task wall-clock budget for each spawned Claude session (seconds).
    # Threaded into every spawn_claude() call.
    task_timeout_seconds: int = 60 * 60 * 4
    # Wall-clock bound for EACH execution of the repo's `.dispatcher.yaml`
    # `test:` command in the mechanical verification gate (the first run and
    # the post-fix re-run are bounded independently). A timed-out execution
    # is a failure like any non-zero exit.
    verify_test_timeout_seconds: int = 600
    # LLM verification gate (VG-4). After the mechanical gate passes and
    # before the cross-family panel, an independent verifier (verifier.py) is
    # spawned over the task + summary + committed diff to answer "does this
    # diff actually do what the task asked — nothing stubbed/deferred/quietly
    # narrowed?". INCOMPLETE re-spawns the Tasker with the gap list, re-runs
    # the mechanical gate, and re-verifies up to `max_verify_iterations` times
    # (distinct from the panel's own iterate budget) before Blocking with
    # reason verification_incomplete. `skip_verification` is the --skip-
    # verification escape hatch (journaled). `verifier_timeout_seconds` bounds
    # EACH verifier spawn.
    max_verify_iterations: int = 2
    skip_verification: bool = False
    verifier_timeout_seconds: int = verifier_mod.DEFAULT_VERIFIER_TIMEOUT_SECONDS
    # If True, after each Tasker reports Done with commits on its feat
    # branch, the dispatcher attempts to merge that branch into base_branch
    # before marking the row Done. Prevents the "fork-from-stale-base"
    # problem where sibling tasks fork from the same epic SHA and can't see
    # each other's work. See auto_integrate.py for the integration rules.
    auto_integrate: bool = False
    # Cross-family reviewer panel: after a Tasker reports Done, run three
    # independent reviewers (one Claude, one Gemini, one Codex) over the
    # diff + summary. ALL THREE must APPROVE for auto-integrate to fire;
    # any dissenter or critical/high finding blocks. Values:
    #   "auto"   — run only for risk-gated tickets (critical/security/
    #              financial/high labels). Default.
    #   "always" — run for every Done ticket regardless of labels.
    #   "never"  — disable. The Tasker's in-cycle panel still runs; only
    #              the cross-family checkpoint is skipped.
    # See cross_family_reviewer.panel_required() for the gating rules.
    cross_family_panel: str = "auto"
    # Per-reviewer wall-clock budget (seconds). Each reviewer runs in its
    # own thread; the panel wall-clock is the slowest reviewer.
    cross_family_panel_timeout: int = cfr_mod.DEFAULT_REVIEWER_TIMEOUT_SECONDS
    # When the cross-family panel returns block, optionally re-spawn the
    # Tasker with the panel's blocking findings as a corrective prompt,
    # then re-run the panel against the new diff. Default 0 = no iterate
    # (current behavior; panel block → Blocked status). Each iteration is
    # one extra Tasker spawn + one extra panel run. The panel verdict
    # stamped on the YAML row is from the FINAL run (which may be approve
    # if the Tasker successfully addressed the findings).
    cross_family_panel_iterate: int = 0
    # Step 6: when True, persist each task's transcript + a cheap haiku summary
    # and reference them from the YAML row (audit log; Forecast projects them).
    # Opt-in (off by default) because it shells claude-haiku per task — cost +
    # latency, and not correctness-critical.
    haiku_summary: bool = False
    # Feature review loop (steps 3-4, docs/feature-review-loop.md). When on
    # (pr-mode only), after the per-task drain the dispatcher reviews the
    # cumulative feature diff vs the PRD, dispositions findings, and loops fix
    # tasks until clean / held / alarmed. Opt-in (off = identical prior behavior).
    feature_review: bool = False
    feature_review_rounds: int = 3
    # Budget ceiling (BUDGET-1). When set, the dispatch loop stops STARTING new
    # tasks once the run's cumulative per-task cost_usd reaches this many US
    # dollars — it does NOT kill in-flight tasks (that would orphan a worktree /
    # PR), it lets them drain and then holds the run for a human (a
    # budget_exceeded journal event + notification fire once; the run exits
    # non-zero with un-dispatched tasks left To Do, so raising the ceiling and
    # `dispatcher resume` continues). The cost basis is the row's accumulated
    # cost_usd — every per-task Claude spawn (implementer + verifier + all
    # corrective/retry spawns) is accounted via _account_spawn, so it's the
    # task's full bill even when the task blocks. NOT counted: cross-family
    # panel reviewer spend (non-Claude adapters emit no usage JSON; the Claude
    # reviewer's cost isn't surfaced). None (default) disables the ceiling — the
    # loop is byte-identical to before.
    max_cost_usd: float | None = None
    # Run-start cost baseline (BUDGET-1). cost_usd persists on task rows across
    # runs of the same YAML, so a FRESH run over an already-partly-completed
    # YAML would otherwise count prior runs' spend against this run's ceiling.
    # execute() captures the sum of pre-existing cost_usd here at run start and
    # persists it in the genesis run_config; the ceiling caps cumulative cost
    # MINUS this baseline, i.e. only what this run (and its resumes — which
    # reuse the genesis baseline) actually adds.
    cost_baseline_usd: float = 0.0
    # Notification channels for human-attention events. Built once at
    # execute() time from CLI flags + env vars; injected into _run_task
    # via this slot so tests can substitute a recording stub.
    notifier: notify_mod.Notifier = field(default_factory=notify_mod.NullNotifier)
    # The agent CLI's `--version` line, captured exactly once per run at run
    # setup (execute()/resume_run()), never per task. None when capture
    # failed — _agent_meta() then omits the field entirely (OPS-4).
    agent_version: str | None = None
    # Append-only event journal for this run (one JSONL file under run_dir).
    # Created in execute() once run_dir exists; left None if creation fails
    # (an unwritable runs dir must NOT abort the run — journaling is
    # best-effort, mirroring the notifier policy). Every emit goes through
    # _emit_event(), which is a no-op when this is None. See journal.py.
    journal: journal_mod.Journal | None = None


@dataclass
class TaskSnapshot:
    """A frozen copy of one task's data captured at dispatch time.

    Workers receive this so they don't have to re-load the YAML to build
    their prompt. The YAML can still be modified by other workers in the
    meantime — the snapshot stays valid because it's a copy.
    """
    key: str
    summary: str
    description: str
    type: str
    labels: list[str]
    model: str | None = None
    # Per-task implementer agent (claude/codex/grok/gemini); None -> claude.
    agent: str | None = None
    # blockedBy dependency keys, in declaration order. Used at worker start to
    # merge each dependency's branch into this task's fresh worktree branch
    # when the dependency's commits are not yet on base (INT-4).
    blocked_by: list[str] = field(default_factory=list)


# --- entry point -----------------------------------------------------------


def execute(args: argparse.Namespace) -> int:
    """Live-spawn entry point. Returns 0 on clean exit (all done), 1 on partial
    completion (some Blocked/Escalated), 2 on validation error.
    """
    cfg = _build_config(args)
    # Capture the agent CLI version exactly once per run (OPS-4). Failure
    # degrades to None (capture_agent_version never raises) and the
    # provenance field is simply omitted from terminal rows/events.
    cfg.agent_version = spawn_mod.capture_agent_version(cfg.claude_bin)
    doc = yaml_io.load(cfg.tasks_path)
    try:
        plan_mod.load_tasks(doc)  # validate
    except plan_mod.ValidationError as e:
        print(f"error: invalid tasks YAML: {e}", file=sys.stderr)
        return 2

    # Resolve base_branch: CLI > YAML top-level > "main".
    if cfg.base_branch == "main":  # i.e., user didn't override on CLI
        yaml_base = (doc.get("base_branch") if isinstance(doc, dict) else None)
        if yaml_base:
            cfg.base_branch = str(yaml_base).strip()

    # Pure read; needed by the preflight before any run artifact exists.
    repo_root = wt_mod.detect_repo_root(cfg.tasks_path.parent)

    # Run-start preflight (live modes only — dry-run returns in run.py and
    # never reaches this function). Failures exit 2 HERE, before the run
    # directory, journal, or any worktree exists, so a doomed run leaves no
    # half-created artifacts behind. Warnings print now (no run.log yet) and
    # are replayed into run.log once it exists. The outcome — including an
    # explicit --skip-preflight — is journaled right after the journal opens.
    if getattr(args, "skip_preflight", False):
        pf = preflight_mod.skipped_result()
        pf_skipped = True
    else:
        pf = preflight_mod.run_preflight(
            claude_bin=cfg.claude_bin,
            claude_extra_args=cfg.claude_extra_args,
            mode=cfg.mode,
            repo_root=repo_root,
            base_branch=cfg.base_branch,
            worktree_base=cfg.worktree_base,
        )
        pf_skipped = False
        if not pf.ok:
            for failure in pf.failures:
                print(f"error: preflight: {failure}", file=sys.stderr)
            return 2
        for warning in pf.warnings:
            print(f"warning: preflight: {warning}", file=sys.stderr)

    run_dir = cfg.runs_dir / cfg.run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    log_path = run_dir / "run.log"
    _log(log_path, f"start run {cfg.run_id} mode={cfg.mode} max_parallel={cfg.max_parallel}")
    for warning in pf.warnings:
        _log(log_path, f"preflight warning: {warning}")

    # Resolve the integration mode and, in pr mode, create the run-level
    # feature branch and repoint base_branch to it (PRF-1). Done AFTER
    # preflight (so a doomed run isn't given a feature branch) and BEFORE the
    # journal opens (so the genesis run_config records the resolved mode +
    # feature branch + SHA). A config error here — pr mode with no derivable
    # feature branch — exits 2 like a preflight failure.
    integ_err = _setup_integration(cfg, doc, repo_root, args, log_path)
    if integ_err is not None:
        print(f"error: {integ_err}", file=sys.stderr)
        return 2

    # Budget baseline (BUDGET-1): cost_usd already on the rows from PRIOR runs of
    # this YAML is not this run's spend. Capture it now (before any task runs) so
    # the ceiling caps only what THIS run adds. Persisted in the genesis below so
    # resumes reuse the same baseline (capping total spend across original +
    # resumes), rather than recomputing it from rows this run has since written.
    cfg.cost_baseline_usd = _cumulative_cost_usd(_load_tasks_snapshot(cfg))

    # Open the event journal. Its genesis (run_started, seq 0) event records
    # the run's provenance — dispatcher version, tasks.yaml + reviewer-prompts
    # content hashes, host — plus the resolved run config under `run_config`
    # so `dispatcher resume` can replay this run from the journal alone. If
    # creation fails (e.g. an unwritable runs dir), we warn and run
    # journal-less: a control-surface convenience must never be load-bearing
    # for the run completing.
    cfg.journal = _open_journal(
        cfg, run_dir, repo_root, log_path, run_config=_genesis_config(args, cfg),
    )

    # Journal the preflight outcome (or the explicit skip). `failures` is
    # always empty on this path — a failed preflight returned 2 above, before
    # the journal existed (see preflight.py's module docstring). Run-level
    # event: task_key stays None, like run_started/run_complete.
    _emit_event(cfg, journal_mod.EventType.preflight, {
        "skipped": pf_skipped,
        "checks": pf.checks,
        "warnings": list(pf.warnings),
        "failures": [],
    })

    return _run_loop(cfg, run_dir, log_path, repo_root)


def resume_run(args: argparse.Namespace, journal: journal_mod.Journal) -> int:
    """Re-enter the dispatch loop for an already-genesis'd run.

    Called by :func:`claude_dispatcher.resume.execute` after it has appended a
    ``resume_started`` event and reset (or blocked) the interrupted In Progress
    rows. ``args`` is reconstructed from the genesis ``run_config``, so its
    ``base_branch`` / ``run_id`` are already resolved (no YAML re-resolution).
    ``journal`` is the EXISTING run's journal, opened for append via
    :meth:`Journal.resume` — this continues the original chain rather than
    starting a new genesis.

    Deliberately does NOT re-run the run-start preflight: the original run's
    preflight verdict (or its explicit ``--skip-preflight``) is already on
    the chain as the ``preflight`` event, and re-checking mid-run could
    refuse to finish work that is already half-landed.
    """
    cfg = _build_config(args)
    # Same once-per-run agent version capture as execute() (OPS-4).
    cfg.agent_version = spawn_mod.capture_agent_version(cfg.claude_bin)
    cfg.journal = journal
    run_dir = cfg.runs_dir / cfg.run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    log_path = run_dir / "run.log"
    _log(log_path, f"resume run {cfg.run_id} mode={cfg.mode} max_parallel={cfg.max_parallel}")
    repo_root = wt_mod.detect_repo_root(cfg.tasks_path.parent)
    return _run_loop(cfg, run_dir, log_path, repo_root)


def _cumulative_cost_usd(tasks) -> float:
    """Sum the per-task ``cost_usd`` across the run (implementer + verifier
    spawns — the same basis report.py aggregates). A task that hasn't reported
    cost yet, or whose adapter didn't emit usage JSON, contributes 0. Pure."""
    total = 0.0
    for t in tasks:
        c = t.raw.get("cost_usd")
        if isinstance(c, (int, float)) and not isinstance(c, bool):
            total += float(c)
    return total


def _run_spend_usd(tasks, baseline: float = 0.0) -> float:
    """This run's spend = cumulative per-task cost MINUS the run-start baseline
    (cost_usd left on rows by prior runs of the same YAML). Pure."""
    return _cumulative_cost_usd(tasks) - baseline


def _budget_exceeded(tasks, ceiling: float | None, baseline: float = 0.0) -> bool:
    """True when a positive ceiling is set and THIS RUN's spend (cumulative cost
    minus the run-start baseline) has reached it. A None/zero/negative ceiling
    disables the gate (returns False) — the CLI rejects non-positive ceilings,
    so this guard is defense-in-depth for a resume whose genesis carried one.
    Pure."""
    return bool(ceiling and ceiling > 0) and _run_spend_usd(tasks, baseline) >= ceiling


def _add_task_cost(cfg: RunConfig, task_key: str, delta: float | None) -> None:
    """ADD ``delta`` dollars to a task row's running ``cost_usd`` (creating it at
    that value if absent). Accumulating — not overwriting — lets every spawn in
    a task's lifecycle (implementer, verifier, corrective/retry, panel/verifier
    iterations) contribute, so the row's cost_usd is the task's true bill even
    when the task blocks before any success-path writeback. A None/0 delta is a
    no-op."""
    if not delta:
        return

    def _apply(row):
        cur = row.get("cost_usd")
        base = float(cur) if isinstance(cur, (int, float)) and not isinstance(cur, bool) else 0.0
        row["cost_usd"] = base + float(delta)

    _mutate_row(cfg, task_key, _apply)


def _account_spawn(cfg: RunConfig, task_key: str, result, *, kind: str) -> None:
    """Single accounting point for one ``spawn_claude`` result: emit a
    ``task_spawn_finished`` event (tagged with ``spawn_kind``) AND add its cost
    to the task row's running ``cost_usd``. Routing EVERY spawn through here —
    implementer, corrective/retry (commit/push/test-fix), and panel/verifier
    iterations — keeps both report.py's journal rollup and the budget ceiling
    complete and consistent. (BUDGET-1 / spawn-complete cost accounting.)"""
    payload = _spawn_usage_payload(result)
    payload["spawn_kind"] = kind
    _emit_event(cfg, journal_mod.EventType.task_spawn_finished,
                payload, task_key=task_key)
    _add_task_cost(cfg, task_key, result.usage.cost_usd)


def _run_loop(
    cfg: RunConfig, run_dir: Path, log_path: Path, repo_root: Path,
) -> int:
    """The core dispatch loop, shared by :func:`execute` and :func:`resume_run`.

    Picks runnable tasks, marks them In Progress, spawns workers, collects
    results, and recomputes the runnable set until nothing is left. A daemon
    heartbeat thread appends periodic ``heartbeat`` events so the journal's
    liveness signal — which `dispatcher resume` reads to decide whether a run
    is still active — stays fresh even during a long single-task spawn that
    emits no other events for hours. The heartbeat is stopped (and joined)
    before the terminal ``run_complete`` event so that event stays the last
    record in the chain.
    """
    stop_heartbeat = threading.Event()
    heartbeat = threading.Thread(
        target=_heartbeat_loop, args=(cfg, stop_heartbeat), daemon=True,
    )
    heartbeat.start()

    # Mechanical merge engine (PRF-4): in pr mode the dispatcher merges
    # Awaiting Review PRs into the feature branch as they become eligible. One
    # MergePassState lives for the whole run so the once-per-task notifications
    # (elevated PR awaiting external approval, conflict needing rebase) fire
    # exactly once across the many passes a run triggers.
    merge_state = merge_mod.MergePassState()

    # Budget ceiling (BUDGET-1): set once the cost ceiling is reached so the
    # post-loop rollup can report the hold and exit non-zero. The trip is
    # idempotent — the event + notification fire only on the transition.
    budget_tripped = False

    try:
        # OUTER feature-review loop (steps 3-4). With cfg.feature_review off (the
        # default) it runs the dispatch-drain + merge exactly ONCE then breaks —
        # behaviorally identical to the prior single-drain code. When on (pr-mode
        # only), each round runs the final whole-feature review, dispositions the
        # findings, and appends accepted findings as FIX-* tasks; the next round
        # re-drains to run them, then re-reviews — until clean, held, or alarmed.
        ledger = disposition_mod.DispositionLedger(
            max_fix_rounds=cfg.feature_review_rounds)
        review_round = 0
        while True:
            # _dispatch_drain runs the inner dispatch loop incl. the budget
            # ceiling (BUDGET-1); it returns True if the ceiling tripped this
            # drain. A budget hold stops the outer review loop too — we don't
            # spend more on review rounds / fix tasks once the human gate fired.
            if _dispatch_drain(cfg, run_dir, log_path, repo_root, merge_state):
                budget_tripped = True
            # End-of-round merge: the last task(s) to reach Awaiting Review — and
            # any PR eligible only once the final dependency merged — get a pass.
            _maybe_merge_pass(cfg, repo_root, log_path, merge_state)
            if budget_tripped:
                break
            if not (cfg.feature_review and cfg.integration == "pr"):
                break
            if not _feature_review_round(
                cfg, repo_root, log_path, ledger, review_round):
                break  # clean / held / alarm / no diff -> done
            review_round += 1
    finally:
        # Stop the heartbeat and wait for it to fully exit before emitting
        # run_complete, so that event is guaranteed to be the terminal record
        # of the chain. The join is untimed deliberately: once `stop` is set the
        # thread returns from `stop.wait()` immediately and can only be inside at
        # most one bounded `append` (a single fsync), so this cannot hang any
        # longer than the orchestrator's own appends already can.
        stop_heartbeat.set()
        heartbeat.join()

    tasks = _load_tasks_snapshot(cfg)
    # "Done" for the rollup counts every terminal-success status: plain Done
    # (branch mode) plus the pr-mode lifecycle states Awaiting Review / Merged
    # (PRF-2), so a pr-mode run that auto-raised every PR isn't reported as
    # "0 done". Neither pr status occurs in branch mode, so the count is
    # unchanged there.
    done_tasks = [
        t for t in tasks
        if t.status in (plan_mod.DONE, plan_mod.AWAITING_REVIEW, plan_mod.MERGED)
    ]
    blocked = [t for t in tasks if t.status == plan_mod.BLOCKED]
    escalated = [t for t in tasks if t.status == plan_mod.ESCALATED]
    # pr-mode merge tallies (PRF-5). Merged is terminal; Awaiting Review means
    # the PR was raised but hasn't landed (run finished with merges pending);
    # needs_rebase flags a PR held back by a merge conflict. These feed both the
    # run_complete event payload and the rollup notification — but only in pr
    # mode, so the branch-mode payload/notification are unchanged.
    pr_mode = cfg.integration == "pr"
    merged = [t for t in tasks if t.status == plan_mod.MERGED]
    awaiting = [t for t in tasks if t.status == plan_mod.AWAITING_REVIEW]
    needs_rebase = [t for t in tasks if t.raw.get("needs_rebase")]
    _log(log_path, f"end run blocked={len(blocked)} escalated={len(escalated)}"
         + (f" merged={len(merged)} awaiting={len(awaiting)} "
            f"needs_rebase={len(needs_rebase)}" if pr_mode else "")
         + (" BUDGET-HELD" if budget_tripped else ""))
    # Run-complete rollup notification. Always fires (including on clean
    # runs — knowing the run finished is signal). Best-effort. Sent BEFORE
    # the run_complete journal event so that event stays the terminal record
    # of the chain.
    blocked_rollup = []
    try:
        blocked_rollup = [
            (t.key, str(t.raw.get("blocked_reason") or "unknown"))
            for t in blocked + escalated
        ]
        _send_notification(cfg, notify_mod.run_complete_notification(
            run_id=cfg.run_id,
            done=len(done_tasks),
            blocked=len(blocked),
            escalated=len(escalated),
            blocked_rollup=blocked_rollup,
            tasks_yaml=str(cfg.tasks_path),
            # pr mode: surface the pending-merge picture in the same glanceable
            # message. None in branch mode → message unchanged.
            merged=len(merged) if pr_mode else None,
            awaiting_review=len(awaiting) if pr_mode else None,
            needs_rebase=len(needs_rebase) if pr_mode else None,
        ))
    except Exception:
        pass
    # Terminal journal event: closes the chain with the run's tallies. An
    # external observer that reads run_complete knows no more events follow.
    run_complete_payload: dict[str, Any] = {
        "done": len(done_tasks),
        "blocked": len(blocked),
        "escalated": len(escalated),
        "blocked_rollup": [{"key": k, "reason": r} for k, r in blocked_rollup],
    }
    # pr-mode merge tallies (PRF-5): added only in pr mode so the branch-mode
    # payload shape is unchanged. `done` already counts Merged/Awaiting Review
    # (its umbrella meaning is preserved); these break that down.
    if pr_mode:
        run_complete_payload["merged"] = len(merged)
        run_complete_payload["awaiting_review"] = len(awaiting)
        run_complete_payload["needs_rebase"] = len(needs_rebase)
    # Budget hold (BUDGET-1): added only when the ceiling tripped, so the
    # default payload shape is unchanged.
    if budget_tripped:
        run_complete_payload["budget_held"] = True
        run_complete_payload["cost_usd"] = round(
            _run_spend_usd(tasks, cfg.cost_baseline_usd), 4)
    _emit_event(cfg, journal_mod.EventType.run_complete, run_complete_payload)
    # A budget hold is an incomplete run needing a human — exit non-zero even
    # when nothing is formally Blocked/Escalated (tasks are parked To Do).
    return 1 if (blocked or escalated or budget_tripped) else 0


def _maybe_merge_pass(
    cfg: RunConfig,
    repo_root: Path,
    log_path: Path,
    state: merge_mod.MergePassState,
) -> None:
    """Run one mechanical merge pass in pr mode (PRF-4); a no-op otherwise.

    A thin adapter from the orchestrator's RunConfig to the merge engine's
    own config, reusing the run's journal + notifier + log so merge events and
    notifications land on the same audit trail / channels as everything else.
    Never raises — the merge engine contains every git/gh/journal failure, and
    a guard here means even an unexpected one can't abort the dispatch loop.
    """
    if cfg.integration != "pr":
        return
    feature_branch = cfg.feature_branch or cfg.base_branch
    if not feature_branch:
        return
    me_cfg = merge_mod.MergeEngineConfig(
        tasks_path=cfg.tasks_path,
        repo_root=repo_root,
        feature_branch=feature_branch,
        gh_bin=cfg.gh_bin,
        lock_timeout_seconds=cfg.lock_timeout_seconds,
        run_id=cfg.run_id,
    )
    try:
        merge_mod.merge_pass(
            me_cfg,
            journal=cfg.journal,
            notifier=cfg.notifier,
            log=lambda m: _log(log_path, m),
            state=state,
        )
    except Exception as e:  # pragma: no cover - defensive
        _log(log_path, f"  merge pass raised (continuing): {e}")


# --- per-worker -------------------------------------------------------------


def _run_task(
    snap: TaskSnapshot,
    cfg: RunConfig,
    run_dir: Path,
    log_path: Path,
    repo_root: Path,
) -> str:
    """Run one task end-to-end. Returns the final status string.

    YAML mutations happen via _mutate_row() which acquires the FileLock,
    re-loads the YAML, modifies one row, writes it back, and releases.
    """
    _log(log_path, f"  {snap.key} starting")

    branch = wt_mod.branch_name(snap.type, snap.key, snap.summary)
    try:
        wt = wt_mod.create(repo_root, snap.key, branch,
                           base_branch=cfg.base_branch, base_path=cfg.worktree_base)
    except wt_mod.WorktreeError as e:
        # Worktree creation failed before we could attempt the dependency
        # merge. Emit task_started so the lifecycle still has a start record,
        # then Block (_mark_blocked emits the terminal task_blocked event +
        # notification). This keeps task_started the first per-task event.
        _emit_event(cfg, journal_mod.EventType.task_started,
                    _task_started_payload(snap), task_key=snap.key)
        _log(log_path, f"  {snap.key} worktree creation failed: {e}")
        _mark_blocked(cfg, snap.key, reason=f"worktree_create_failed: {e}")
        return plan_mod.BLOCKED
    _log(log_path, f"  {snap.key} worktree at {wt.path} branch {wt.branch}")

    summary_path = run_dir / snap.key / "summary.md"
    summary_path.parent.mkdir(parents=True, exist_ok=True)

    # Stamp branch + summary_path on the row (started_at already set by main thread).
    _mutate_row(cfg, snap.key, lambda r: r.update({
        "branch": branch,
        "summary_path": str(summary_path),
    }))

    # Dispatch-time dependency rule (INT-4): merge each blockedBy dependency's
    # branch into this task's fresh worktree branch when the dependency's
    # commits are not yet reachable from base_branch. This gives the Tasker a
    # tree that already contains its dependencies' work, mechanically —
    # instead of relying on the Tasker to discover and merge them (run #2
    # showed that behavior varies too much to trust). A no-op when the task
    # has no dependencies, or when they are already on base (auto-integrate).
    dep_branches = _resolve_dependency_branches(cfg, snap.blocked_by)
    merge_result = wt_mod.merge_dependencies(
        repo_root, wt, cfg.base_branch, dep_branches,
        log=lambda m: _log(log_path, m),
    )
    # task_started carries the merge outcome (merged dependency SHAs).
    _emit_event(cfg, journal_mod.EventType.task_started,
                _task_started_payload(snap, merge_result), task_key=snap.key)
    if merge_result.conflict is not None:
        # Failed dependency merge: do NOT dispatch a Tasker into the tree.
        # Block with the precise label — dependency_merge_conflict for a
        # genuine content conflict, dependency_merge_failure for any other
        # merge failure (e.g. missing committer identity); the task_started
        # event above already journaled the detail.
        c = merge_result.conflict
        _mark_blocked(
            cfg, snap.key,
            reason=f"{c.reason}: {c.key} ({c.branch}): {c.detail}",
        )
        return plan_mod.BLOCKED

    # When dependency branches were merged, the task branch already has commits
    # beyond base before the Tasker runs — so "did the Tasker commit its own
    # work?" must be measured against the post-merge tip, not base. Capture it
    # here; None when nothing was merged (preserving the base-relative check
    # exactly for the common no-dependency path).
    feat_baseline_sha = (
        _branch_sha(repo_root, wt.branch, log_path, snap.key)
        if merge_result.merged else None
    )

    env = spawn_mod.build_env(
        task_key=snap.key,
        summary_path=summary_path,
        run_id=cfg.run_id,
        max_iterations=cfg.max_iterations,
        financial_paths=cfg.financial_paths,
        skip_design=cfg.skip_design,
        skip_security_linter=cfg.skip_security_linter,
        reviewer_count=cfg.reviewer_count,
    )
    prompt = spawn_mod.build_prompt(
        task_key=snap.key,
        task_summary=snap.summary,
        task_type=snap.type,
        task_labels=snap.labels,
        task_description=snap.description,
        branch=wt.branch,
        summary_path=summary_path,
        run_id=cfg.run_id,
        max_iterations=cfg.max_iterations,
        financial_paths=cfg.financial_paths,
        skip_design=cfg.skip_design,
        skip_security_linter=cfg.skip_security_linter,
        reviewer_count=cfg.reviewer_count,
    )
    # Per-task agent + model routing is handled inside spawn_agent: for the
    # default "claude" agent it appends --model (stacking after run-level
    # --claude-extra-args so the per-task value wins); for cross-family agents
    # (codex/grok/gemini) it dispatches to that CLI's headless agentic mode and
    # normalizes the result (auto-commit + summary). See spawn.spawn_agent.
    if snap.agent and snap.agent != "claude":
        _log(log_path, f"  {snap.key} implementer agent = {snap.agent}"
                       + (f" (model={snap.model})" if snap.model else ""))

    # Snapshot base_branch's tip SHA BEFORE the spawn. This is the
    # discriminator for the direct-to-base workflow: a Tasker that
    # fast-forwards feat/X into base_branch leaves feat/X equal to
    # base_branch, so the standard "rev-list base..feat" check returns 0
    # even though the work landed. Comparing base_branch's tip before vs
    # after the spawn detects the FF advance. See
    # _has_commits_on_branch() for the two-condition success check.
    base_sha_before = _branch_sha(repo_root, cfg.base_branch, log_path, snap.key)

    try:
        result = spawn_mod.spawn_agent(
            agent=snap.agent,
            claude_bin=cfg.claude_bin,
            cwd=wt.path,
            env=env,
            prompt=prompt,
            model=snap.model,
            extra_args=list(cfg.claude_extra_args),
            timeout_seconds=cfg.task_timeout_seconds,
        )
    except Exception as e:
        _log(log_path, f"  {snap.key} spawn failed: {e}")
        _mark_blocked(cfg, snap.key, reason=f"spawn_failed: {e}")
        return plan_mod.BLOCKED

    _log(log_path, f"  {snap.key} spawn exited code={result.exit_code}")
    # Spawn-completion event: carries the per-task usage/cost payload parsed
    # from the Claude CLI's JSON output (all fields optional — None when the
    # CLI didn't emit usage). Emitted for every spawn outcome, success or
    # non-zero exit, so the journal records the cost even of a failed run.
    # Account the implementer spawn (emits task_spawn_finished + accumulates its
    # cost onto the row). Done here, before any block branch, so a task that
    # spawns and THEN blocks still counts toward the cost ceiling. (BUDGET-1 /
    # spawn-complete cost.)
    _account_spawn(cfg, snap.key, result, kind="implementer")
    # Step 6 (opt-in via --haiku-summary): persist the agent's captured output as
    # the transcript log + a cheap haiku summary, referenced from the YAML row
    # (review/audit; what Forecast `ingest` later projects). Best-effort — never
    # blocks the task; runs for every outcome so a blocked run is auditable too.
    if cfg.haiku_summary:
        _log_transcript_and_haiku(cfg, snap, result, summary_path.parent, log_path)
    if result.exit_code != 0:
        _mark_blocked(cfg, snap.key, reason=f"session_exit_code_{result.exit_code}")
        return plan_mod.BLOCKED

    if not result.summary_path.exists():
        _mark_blocked(cfg, snap.key, reason="summary_missing")
        return plan_mod.BLOCKED

    s = summary_mod.parse(result.summary_path)
    _emit_event(cfg, journal_mod.EventType.summary_parsed,
                _summary_parsed_payload(s), task_key=snap.key)
    if s.malformed:
        _log_summary_problems(log_path, snap.key, s)
        _mark_blocked(cfg, snap.key,
                      reason=f"summary_malformed: {_summary_problem_detail(s)}")
        return plan_mod.BLOCKED

    # If the Tasker reported Done (or any terminal-success status) but the
    # branch has no commits beyond base_branch, the work is uncommitted in
    # the worktree. This is recoverable: re-prompt the Tasker to commit
    # (NOT a Block — it's a "forgot to commit" mistake, fixable with one
    # corrective spawn). Max 1 commit-retry; if commits still missing
    # after, only then is this a real failure.
    if (s.status == "Done"
            and not _has_commits_on_branch(
                wt, cfg.base_branch, repo_root,
                base_sha_before, log_path, snap.key,
                feat_baseline_sha=feat_baseline_sha)):
        _log(log_path, f"  {snap.key} reported Done but no commits on branch — retrying with commit-only prompt")
        retry_status = _retry_for_commit(
            cfg, snap, wt, repo_root, summary_path, env, log_path,
            feat_baseline_sha=feat_baseline_sha,
        )
        _emit_event(cfg, journal_mod.EventType.commit_retry, {
            "trigger": "reported Done with no commits on branch",
            "outcome": "committed" if retry_status is not None else "still_no_commits",
        }, task_key=snap.key)
        if retry_status is None:
            # Retry failed — really no work. Mark Blocked with clear reason.
            _mark_blocked(cfg, snap.key,
                          reason="no commits produced after commit-retry; Tasker spawn 2x failed to commit")
            return plan_mod.BLOCKED
        # Retry succeeded — re-parse summary and continue with Done flow.
        s = summary_mod.parse(result.summary_path)
        _emit_event(cfg, journal_mod.EventType.summary_parsed,
                    {**_summary_parsed_payload(s), "after_commit_retry": True},
                    task_key=snap.key)
        if s.malformed:
            _log_summary_problems(log_path, snap.key, s)
            _mark_blocked(
                cfg, snap.key,
                reason=f"summary_malformed after commit retry: {_summary_problem_detail(s)}")
            return plan_mod.BLOCKED

    # Awaiting-human-approval handling — supervised may raise the PR.
    final_status, final_url, final_blocked_reason = _resolve_summary(
        cfg, snap, s, wt, log_path
    )

    # Mechanical verification gate (VG-2): run the repo's own test command
    # (.dispatcher.yaml `test:`, loaded from the WORKTREE so the branch under
    # test governs its own gate) before any LLM checkpoint spends tokens on
    # the work. Positioned deliberately BEFORE the cross-family panel and
    # auto-integrate blocks: a failed gate flips final_status to BLOCKED
    # here, and the panel / auto-integrate / push-verify blocks below are
    # all gated on final_status == DONE, so a red suite can never be
    # panel-reviewed, integrated, or push-flagged. Outcomes:
    #   passed  — green (possibly after one fix-the-tests re-spawn); proceed.
    #   skipped — no config / no test command; behavior unchanged from
    #             pre-gate runs (Done stays Done).
    #   failed  — still red after the retry, or the config is malformed;
    #             Blocked with the failing output tail on the row.
    mech_outcome: str | None = None
    mech_detail: str | None = None
    if final_status == plan_mod.DONE:
        mech_outcome, mech_detail = _verify_mechanical_and_maybe_retry(
            cfg, snap, wt, summary_path, env, log_path,
        )
        if mech_outcome == "failed":
            final_status = plan_mod.BLOCKED
            final_blocked_reason = "mechanical_verification_failed"

    # LLM verification gate (VG-4). Spawned ONLY for a still-Done task, AFTER
    # the mechanical gate above (ordering rule: never spend verifier tokens on
    # a red suite) and BEFORE the cross-family panel below. The verifier asks
    # one question — does the committed diff actually do what the task asked,
    # nothing stubbed/deferred/quietly narrowed? VERIFIED proceeds as today;
    # INCOMPLETE re-spawns the Tasker with the gap list, re-runs the mechanical
    # gate, and re-verifies up to --max-verify-iterations times before Blocking
    # with reason verification_incomplete (gaps in the YAML detail). The whole
    # gate is skippable via --skip-verification (journaled). Because a block
    # flips final_status to BLOCKED here, the panel / auto-integrate / push
    # blocks below — all gated on final_status == DONE — never run on an
    # unverified change.
    verified: bool | None = None
    verification_iterations = 0
    verification_detail: str | None = None
    verifier_cost_total = 0.0
    if final_status == plan_mod.DONE:
        if cfg.skip_verification:
            _emit_event(cfg, journal_mod.EventType.verification_skipped,
                        {"reason": "--skip-verification"}, task_key=snap.key)
            _log(log_path,
                 f"  {snap.key} LLM verification skipped (--skip-verification)")
        else:
            vout = _verify_llm_and_maybe_iterate(
                cfg=cfg, snap=snap, wt=wt, repo_root=repo_root,
                summary_path=summary_path, env=env, log_path=log_path,
                base_sha_before=base_sha_before,
            )
            verified = vout.verified
            verification_iterations = vout.iterations
            verification_detail = vout.detail
            verifier_cost_total = vout.cost_usd_total
            # Add the verifier's verdict-spawn cost to the row so it lands on the
            # bill whether the task ends Done or BLOCKED (the old success-path
            # fold missed the BLOCKED case). NO event is emitted here — each
            # verifier verdict spawn already emits its own task_spawn_finished
            # (spawn_kind=verifier) that report.py sums, so emitting an aggregate
            # too would double-count in the journal rollup. The Tasker re-spawns
            # inside iterate are accounted separately in _spawn_verifier_iterate.
            _add_task_cost(cfg, snap.key, verifier_cost_total)
            # A mechanical re-run during an iterate may have re-decided the
            # mechanical outcome — carry it through to the row stamp.
            if vout.mech_outcome is not None:
                mech_outcome, mech_detail = vout.mech_outcome, vout.mech_detail
            if vout.blocked_reason is not None:
                final_status = plan_mod.BLOCKED
                final_blocked_reason = vout.blocked_reason

    # Cross-family reviewer panel. Runs ONLY for Done tasks that match
    # the configured gating mode (always | auto via labels | never).
    # Diff bounds: prefer base_sha_before..feat-tip so the direct-to-base
    # workflow is covered (where feat == base_branch by the time we get
    # here). Falls back to base_branch..feat for plain feat-branch work.
    #
    # When `cross_family_panel_iterate > 0` and the panel blocks, the
    # dispatcher re-spawns the Tasker with the blocking findings as a
    # corrective prompt and re-runs the panel up to N times before giving
    # up. Each iteration is one extra Tasker spawn + one extra panel run.
    panel_verdict: cfr_mod.PanelVerdict | None = None
    panel_iterations_used = 0
    if final_status == plan_mod.DONE and _panel_should_run(cfg, snap):
        iterations_remaining = max(0, cfg.cross_family_panel_iterate)
        while True:
            _emit_event(cfg, journal_mod.EventType.panel_started, {
                "iteration": panel_iterations_used,
                "iterations_remaining": iterations_remaining,
            }, task_key=snap.key)
            try:
                panel_verdict = _run_cross_family_panel(
                    cfg=cfg, snap=snap, wt=wt,
                    summary_path=result.summary_path,
                    repo_root=repo_root,
                    base_sha_before=base_sha_before,
                    log_path=log_path,
                )
            except Exception as e:
                _log(log_path, f"  {snap.key} cross-family panel raised: {e}")
                _emit_event(cfg, journal_mod.EventType.panel_verdict,
                            {"error": str(e)[:300]}, task_key=snap.key)
                panel_verdict = None
                final_status = plan_mod.BLOCKED
                final_blocked_reason = f"cross_family_panel_error: {e}"
                break

            _emit_event(cfg, journal_mod.EventType.panel_verdict,
                        _panel_verdict_payload(panel_verdict), task_key=snap.key)
            # Scorecard groundwork (VG-5): one event per advisory finding.
            # Advisory verdicts never gate anything — these events (plus
            # the advisory_verdicts map in panel_verdict) are the raw
            # material for a future promotion decision.
            _emit_advisory_finding_events(cfg, panel_verdict, snap.key)
            if panel_verdict.is_approve or iterations_remaining <= 0:
                break

            _log(log_path,
                 f"  {snap.key} cross-family panel block — iterating "
                 f"({iterations_remaining} attempt(s) left)")
            corrective_ok = _spawn_panel_iterate(
                cfg=cfg, snap=snap, wt=wt, repo_root=repo_root,
                summary_path=result.summary_path,
                env=env, log_path=log_path,
                panel=panel_verdict,
                iterations_left=iterations_remaining,
            )
            panel_iterations_used += 1
            iterations_remaining -= 1
            _emit_event(cfg, journal_mod.EventType.panel_iterate, {
                "iteration": panel_iterations_used,
                "iterations_remaining": iterations_remaining,
                "corrective_spawn_ok": bool(corrective_ok),
                "blocking_findings": len(panel_verdict.blocking_findings),
            }, task_key=snap.key)
            if not corrective_ok:
                _log(log_path,
                     f"  {snap.key} panel-iterate spawn failed — leaving "
                     f"last panel verdict in place")
                break
            # Loop: re-run the panel against the now-updated diff.

        if panel_verdict is not None and not panel_verdict.is_approve:
            final_status = plan_mod.BLOCKED
            final_blocked_reason = (
                f"cross_family_panel: {panel_verdict.summary}"
                + (f" (after {panel_iterations_used} iterate attempt(s))"
                   if panel_iterations_used else "")
            )
            _append_panel_findings_to_summary(
                result.summary_path, panel_verdict, log_path, snap.key,
            )
        elif panel_verdict is not None:
            _append_panel_findings_to_summary(
                result.summary_path, panel_verdict, log_path, snap.key,
            )

    # Auto-integrate: if the Tasker landed work and the run config asks for
    # auto-integration, merge feat → base_branch BEFORE we flip the YAML
    # status to Done. The status flip is what makes a task's row visible to
    # the dispatcher's runnable check, so dependents only become eligible
    # AFTER the base_branch advance. Auto-integration only fires for the
    # "Done" terminal; Blocked / Escalated tasks are out of scope (the
    # Tasker hasn't produced work to integrate).
    integrate_result: ai_mod.IntegrateResult | None = None
    if cfg.auto_integrate and final_status == "Done":
        try:
            integrate_result = ai_mod.integrate(
                repo_root=repo_root,
                yaml_path=cfg.tasks_path,
                base_branch=cfg.base_branch,
                feat_branch=branch,
                task_key=snap.key,
                log=lambda m: _log(log_path, m),
                enabled=True,
                lock_timeout_seconds=cfg.lock_timeout_seconds,
            )
        except Exception as e:
            _log(log_path, f"  {snap.key} auto-integrate raised: {e}")
            integrate_result = ai_mod.IntegrateResult(
                status="error", detail=f"exception: {e}",
            )
        _emit_event(cfg, journal_mod.EventType.integrate_result, {
            "status": integrate_result.status,
            "merge_sha": integrate_result.merge_sha,
            "services_built": list(integrate_result.services_built)
                if integrate_result.services_built else [],
            "detail": (integrate_result.detail or "")[:500],
        }, task_key=snap.key)
        # If integration failed in a way that means dependents shouldn't
        # proceed, flip status to Blocked so the dispatch loop holds. The
        # Tasker's work isn't lost — its commits are still on the feat
        # branch and the row records the failure reason for human triage.
        if integrate_result.status not in (
            "integrated", "skipped-disabled", "skipped-already-on",
            "skipped-no-commits",
        ):
            _log(log_path,
                 f"  {snap.key} auto-integrate {integrate_result.status}: "
                 f"flipping status from Done → Blocked")
            final_status = plan_mod.BLOCKED
            final_blocked_reason = (
                f"auto_integrate_{integrate_result.status}: "
                f"{integrate_result.detail[:300]}"
            )

    # Post-Done push/PR verification (INT-3). The standard PR-raising workflow
    # expects the Tasker to push its feat branch and (when PRs are configured)
    # open a PR BEFORE reporting Done. DISP-9 reported Done with commits but
    # never pushed — no PR was raised and integration found it by accident.
    # Mirror the commit-retry safety net: verify push/PR state, retry once with
    # a push/PR-only prompt, and if the branch is STILL unpushed (or the PR
    # still missing) flag needs_push on the row + journal it so the supervisor
    # sees it rather than discovering it by accident. Out of scope:
    #   - auto-integrate runs merge direct-to-base and intentionally never push
    #     (auto_integrate.py), so expect_pr == not auto_integrate.
    #   - supervised mode that just raised the PR this session (final_url set):
    #     we already hold the URL, so there is nothing to verify.
    # The branch push is always verified; the PR half is required only when the
    # Tasker did NOT honestly declare "Not raised: <reason>" — a deliberately
    # PR-less Done (e.g. docs landed direct) must still push, but must not be
    # flagged for a missing PR. A SILENT omission (no PR, no reason) is exactly
    # the DISP-9 failure mode and still trips the PR check.
    needs_push = False
    final_pr_number: int | None = None
    if cfg.integration == "pr" and final_status == plan_mod.DONE:
        # PR-flow auto-raise (PRF-2). The task passed every gate above; the
        # dispatcher now pushes its branch and opens the PR against the run's
        # feature branch — automatically, no size-based parking for *raising*
        # (gating moves to the merge step, PRF-4). On success the row moves to
        # Awaiting Review with pr_url + pr_number; a push or gh failure Blocks.
        # This is the pr-mode counterpart to the branch-mode push-verify net
        # below — mutually exclusive, so a pr-mode Done never push-verifies.
        outcome = _pr_mode_open_pr(cfg, snap, s, wt, repo_root, log_path)
        if outcome.url is not None:
            final_status = plan_mod.AWAITING_REVIEW
            final_url = outcome.url
            final_pr_number = outcome.number
        else:
            final_status = plan_mod.BLOCKED
            final_blocked_reason = outcome.blocked_reason
    elif (final_status == plan_mod.DONE
            and not cfg.auto_integrate
            and final_url is None):
        expect_pr = not s.pr_not_raised_reason
        needs_push = _verify_push_and_maybe_retry(
            cfg, snap, wt, summary_path, env, log_path, expect_pr=expect_pr,
        )

    def _apply(row):
        row["status"] = final_status
        row["completed_at"] = _now_iso()
        row["iteration_count"] = s.iterations
        row["linter_cycles"] = s.linter_cycles
        if s.final_quality_score is not None:
            row["final_quality_score"] = s.final_quality_score
        row["human_gate_fired"] = bool(s.human_gate_fired)
        row["deferred_findings_count"] = s.deferred_findings_count
        if final_url:
            row["pr_url"] = final_url
        elif s.pr_url:
            row["pr_url"] = s.pr_url
        elif s.pr_not_raised_reason:
            row["pr_not_raised_reason"] = s.pr_not_raised_reason
        # pr-mode auto-raise stamps the PR number alongside pr_url (PRF-2).
        if final_pr_number is not None:
            row["pr_number"] = final_pr_number
        if final_blocked_reason:
            row["blocked_reason"] = final_blocked_reason
        # Mechanical verification outcome. The key is absent entirely when
        # the gate never ran (non-Done outcomes) — absence means "not
        # evaluated", never "evaluated and skipped". On failure the output
        # tail (already capped by mechanical_verify.TAIL_CHARS) lands in the
        # detail field so a human can triage from the YAML alone;
        # blocked_reason stays the short label.
        if mech_outcome is not None:
            row["mechanical_verification"] = mech_outcome
            if mech_outcome == "failed" and mech_detail:
                row["mechanical_verification_detail"] = mech_detail
        # LLM verification outcome (VG-4). Absent entirely when the gate never
        # ran (non-Done, or --skip-verification) — absence means "not
        # evaluated". verification_iterations is the count of INCOMPLETE →
        # re-spawn cycles performed (0 when VERIFIED first try). On a block the
        # rendered gaps land in verification_detail so a human can triage from
        # the YAML alone; blocked_reason stays the short label.
        if verified is not None:
            row["verified"] = verified
            row["verification_iterations"] = verification_iterations
            if not verified and verification_detail:
                row["verification_detail"] = verification_detail
        # Advisory flag: Done landed but the branch is still unpushed (or its PR
        # is missing) after one corrective re-spawn. Status stays Done — this is
        # a surfacing signal for the supervisor/integrator, not a block.
        if needs_push:
            row["needs_push"] = True
        if s.prepared_pr_title:
            row["prepared_pr_title"] = s.prepared_pr_title
        if s.prepared_pr_branch:
            row["prepared_pr_branch"] = s.prepared_pr_branch
        # Stamp the cross-family panel outcome for forensics + later
        # sweep. Per-reviewer verdicts let an auditor see whether the
        # block was 2/3 or 1/3, and what each family flagged.
        if panel_verdict is not None:
            row["panel_consensus"] = panel_verdict.consensus
            row["panel_summary"] = panel_verdict.summary
            row["panel_blocking_findings"] = len(panel_verdict.blocking_findings)
            if panel_iterations_used:
                row["panel_iterations_used"] = panel_iterations_used
            for r in panel_verdict.reviewers:
                row[f"panel_verdict_{r.family}"] = r.verdict.value
                if r.error:
                    row[f"panel_error_{r.family}"] = r.error[:300]
        # Stamp the auto-integrate outcome for forensic + later sweep.
        if integrate_result is not None:
            row["auto_integrate_status"] = integrate_result.status
            if integrate_result.merge_sha:
                row["auto_integrate_merge_sha"] = integrate_result.merge_sha
            if integrate_result.services_built:
                row["auto_integrate_services"] = list(
                    integrate_result.services_built
                )
            if integrate_result.detail and integrate_result.status not in (
                "integrated", "skipped-disabled", "skipped-already-on",
                "skipped-no-commits",
            ):
                row["auto_integrate_detail"] = integrate_result.detail[:500]
        # Stamp per-task token usage from the Claude CLI's JSON output. All
        # optional — if --output-format=json wasn't honored or parsing failed,
        # the SpawnUsage fields are None and we skip writing them.
        #
        # NOTE: cost_usd is deliberately NOT written here. It is ACCUMULATED at
        # each spawn via _account_spawn / _add_task_cost (implementer + verifier
        # + any corrective/retry + panel/verifier iterations), so the row's
        # running total is already the task's full bill. Overwriting it here
        # would drop every spawn except the implementer's. (BUDGET-1.)
        u = result.usage
        if u.input_tokens is not None:
            row["input_tokens"] = u.input_tokens
        if u.output_tokens is not None:
            row["output_tokens"] = u.output_tokens
        if u.cache_read_input_tokens is not None:
            row["cache_read_input_tokens"] = u.cache_read_input_tokens
        if u.cache_creation_input_tokens is not None:
            row["cache_creation_input_tokens"] = u.cache_creation_input_tokens
        if u.duration_ms is not None:
            row["duration_ms"] = u.duration_ms
        if u.num_turns is not None:
            row["num_turns"] = u.num_turns
        if u.model is not None:
            row["model"] = u.model
        # Agent/version provenance (OPS-4): agent, dispatcher_version, and —
        # when the once-per-run capture succeeded — agent_version.
        row.update(_agent_meta(cfg))

    _mutate_row(cfg, snap.key, _apply)

    # Terminal per-task journal event. A terminal-success status (Done, or the
    # pr-mode Awaiting Review after a successful auto-raise) → task_done;
    # anything else (the in-worker Blocked paths: panel block, auto-integrate
    # fail, pr-mode push/raise failure, awaiting-PR-in-unattended-mode) →
    # task_blocked. Early-return paths (spawn failure, summary
    # missing/malformed, commit-retry exhaustion) journal their own task_blocked
    # via _mark_blocked — disjoint from this one, so exactly one terminal event
    # fires per task.
    if final_status in (plan_mod.DONE, plan_mod.AWAITING_REVIEW):
        _emit_event(cfg, journal_mod.EventType.task_done, {
            "status": final_status,
            "pr_url": final_url or s.pr_url,
            "pr_number": final_pr_number,
            "iterations": s.iterations,
            "verified": verified,
            "verification_iterations": verification_iterations,
            "final_quality_score": s.final_quality_score,
            "panel_consensus": panel_verdict.consensus if panel_verdict else None,
            "auto_integrate_status": integrate_result.status
                if integrate_result else None,
            "needs_push": needs_push,
            **_agent_meta(cfg),
        }, task_key=snap.key)
    else:
        _emit_event(cfg, journal_mod.EventType.task_blocked, {
            "reason": final_blocked_reason or "blocked",
            **_agent_meta(cfg),
        }, task_key=snap.key)

    # If the final status is Blocked (panel block, auto-integrate fail,
    # awaiting-PR-in-unattended-mode), fire the task-blocked notification
    # here. Early-return Blocked paths (spawn failures, summary missing)
    # notify via _mark_blocked instead — the two paths are disjoint, so
    # exactly one notification fires per Blocked outcome.
    if final_status == plan_mod.BLOCKED:
        _send_notification(cfg, notify_mod.task_blocked_notification(
            task_key=snap.key,
            summary=snap.summary,
            reason=final_blocked_reason or "blocked",
            run_id=cfg.run_id,
            summary_path=str(result.summary_path)
                if result.summary_path.exists() else None,
            tasks_yaml=str(cfg.tasks_path),
        ), task_key=snap.key)

    return final_status


def _panel_should_run(cfg: RunConfig, snap: TaskSnapshot) -> bool:
    """Decide whether to fire the cross-family panel for this Done task.

    Reads `cfg.cross_family_panel`:
      - "never"  → no
      - "always" → yes (regardless of labels)
      - "auto"   → yes iff the labels indicate critical/security/financial/high

    "auto" is the default. docs/test-type tickets always skip the panel,
    even with high-risk labels, because they don't ship code paths that
    need the safety net.
    """
    mode = (cfg.cross_family_panel or "auto").lower()
    if mode == "never":
        return False
    if mode == "always":
        # docs/tests still skip — same rule as auto.
        if snap.type and snap.type.lower() in cfr_mod._PANEL_SKIP_TYPES:
            return False
        return True
    # "auto" — risk-tier gating
    return cfr_mod.panel_required(snap.labels, task_type=snap.type)


def _run_cross_family_panel(
    *,
    cfg: RunConfig,
    snap: TaskSnapshot,
    wt: wt_mod.Worktree,
    summary_path: Path,
    repo_root: Path,
    base_sha_before: str | None,
    log_path: Path,
) -> cfr_mod.PanelVerdict:
    """Invoke the three-family panel against the Tasker's committed work.

    Computes the diff using `base_sha_before..HEAD` when available — this
    covers the direct-to-base workflow where feat == base_branch by the
    time the panel runs. Falls back to `base_branch..feat_branch` for
    standard feat-branch work.
    """
    # Resolve the diff bounds (shared with the LLM verifier).
    diff_base, diff_branch = _resolve_diff_bounds(
        cfg, snap, wt, repo_root, base_sha_before, log_path,
    )

    _log(log_path,
         f"  {snap.key} cross-family panel: diff {diff_base[:8] if len(diff_base) >= 8 else diff_base}"
         f"...{diff_branch[:8] if len(diff_branch) >= 8 else diff_branch}")

    diff = cfr_mod.collect_diff(
        repo_root=repo_root,
        base_branch=diff_base,
        branch=diff_branch,
    )

    summary_md = ""
    try:
        summary_md = summary_path.read_text(encoding="utf-8")
    except (OSError, FileNotFoundError) as e:
        _log(log_path, f"  {snap.key} panel: summary.md read failed: {e}")

    return cfr_mod.run_panel(
        ticket_key=snap.key,
        ticket_summary=snap.summary,
        summary_md=summary_md,
        diff=diff,
        branch=diff_branch,
        base_branch=diff_base,
        reviewers=_panel_reviewer_factory(cfg),
        advisory_reviewers=_panel_advisory_reviewer_factory(
            cfg, repo_root, log_path, snap.key,
        ),
        log=lambda m: _log(log_path, m),
    )


def run_feature_review(
    cfg: RunConfig, repo_root: Path, doc: Any, log_path: Path,
) -> cfr_mod.PanelVerdict | None:
    """Step 3 (feature-review loop): the final whole-feature review. Runs the
    cross-family panel over the CUMULATIVE diff (base...feature) reviewed AGAINST
    the PRD — does it satisfy intent + acceptance + cross-task coherence, what is
    missing/regressed — not just diff-internal quality. pr-mode only. Returns the
    PanelVerdict, or None when there is no diff to review. Emits
    feature_review_started / feature_review_verdict."""
    # The cumulative-diff base is the feature branch's RUN-START sha (its fork
    # point), NOT cfg.base_branch — pr-mode repoints base_branch to the feature
    # branch, so using it would diff the branch against itself (empty). For a
    # feature-branch created this run that sha is the true fork point (whole
    # feature); for an existing branch it's this run's start (the run's delta).
    base = cfg.feature_branch_sha or cfg.base_branch
    branch = cfg.feature_branch or cfg.base_branch
    # pr-mode merges land on origin; the LOCAL feature ref lags. Fetch + diff the
    # origin tip so the review sees the merged feature work (best-effort — falls
    # back to the local ref if there's no origin / the fetch fails).
    if cfg.feature_branch:
        import subprocess
        try:
            fetch = subprocess.run(
                ["git", "fetch", "origin", cfg.feature_branch], cwd=str(repo_root),
                capture_output=True, text=True, timeout=120)
            if fetch.returncode == 0:
                branch = f"origin/{cfg.feature_branch}"
        except Exception:  # noqa: BLE001 — fall back to the local ref
            pass
    diff = cfr_mod.collect_diff(repo_root=repo_root, base_branch=base, branch=branch)
    if not diff.strip():
        _log(log_path, "feature-review: no cumulative diff — skipping")
        return None
    prd_path = plan_mod.feature_prd(doc)
    prd_md = ""
    if prd_path:
        try:
            prd_md = (repo_root / prd_path).read_text(encoding="utf-8")
        except OSError:
            prd_md = f"(PRD at {prd_path} not readable)"
    summary_md = (
        "# Final feature review\n\nReview the CUMULATIVE feature diff against the "
        "PRD below: does it satisfy the intent + acceptance criteria, is it "
        "coherent across tasks, what is missing or regressed? Judge the feature "
        "as a whole, not each hunk.\n\n## PRD\n" + (prd_md or "(no PRD provided)")
    )
    epic = (str(doc.get("epic") or doc.get("project") or "feature")
            if isinstance(doc, dict) else "feature")
    _emit_event(cfg, journal_mod.EventType.feature_review_started, {
        "base": base, "branch": branch, "prd": prd_path,
        "diff_lines": diff.count("\n"),
    })
    verdict = cfr_mod.run_panel(
        ticket_key="FEATURE-REVIEW",
        ticket_summary=f"final review of feature {epic}",
        summary_md=summary_md, diff=diff, branch=branch, base_branch=base,
        reviewers=_panel_reviewer_factory(cfg),
        advisory_reviewers=_panel_advisory_reviewer_factory(
            cfg, repo_root, log_path, "FEATURE-REVIEW"),
        log=lambda m: _log(log_path, m),
    )
    _emit_event(cfg, journal_mod.EventType.feature_review_verdict, {
        "consensus": verdict.consensus,
        "blocking": len(verdict.blocking_findings),
    })
    _log(log_path, f"feature-review: consensus={verdict.consensus} "
                   f"blocking={len(verdict.blocking_findings)}")
    return verdict


_SEV_RANK = {"CRITICAL": 3, "HIGH": 2, "MEDIUM": 1, "LOW": 0}


def _distinct_findings(verdict) -> list[dict]:
    """Dedupe findings across reviewers by `disposition.finding_key` (file-level
    for blocking severities, file:line for nits), keeping the MAX severity and a
    representative location/description. So one defect flagged by N reviewers at
    slightly different lines is a SINGLE record — its corroboration is counted
    the same way by `disposition.corroboration`, so the count matches the
    record."""
    by_key: dict[str, dict] = {}
    for rv in getattr(verdict, "reviewers", []) or []:
        for f in getattr(rv, "findings", []) or []:
            sv = getattr(f.severity, "value", str(f.severity))
            key = disposition_mod.finding_key(f.location, sv)
            cur = by_key.get(key)
            if cur is None:
                by_key[key] = {"location": f.location, "severity": sv,
                               "description": getattr(f, "description", "")}
            elif _SEV_RANK.get(sv, 0) > _SEV_RANK.get(cur["severity"], 0):
                cur["severity"] = sv
                cur["description"] = getattr(f, "description", "") or cur["description"]
    return list(by_key.values())


def apply_dispositions(
    cfg: RunConfig, verdict, *, mode: str,
    ledger: disposition_mod.DispositionLedger, log_path: Path,
) -> tuple[list[dict], list[dict]]:
    """Step 4a: classify EVERY distinct finding (no silent drops), record it in
    the ledger, journal a disposition_recorded event, and return
    (accepted, held). accepted -> become FIX tasks; held -> block + notify.
    gate_grounded/refutable are False at the feature level (decisions #3/#6)."""
    corr = disposition_mod.corroboration(verdict)
    accepted: list[dict] = []
    held: list[dict] = []
    for fnd in _distinct_findings(verdict):
        key = disposition_mod.finding_key(fnd["location"], fnd["severity"])
        c = corr.get(key, 1)
        disp, reason = disposition_mod.classify_disposition(
            severity=fnd["severity"], corroboration=c, gate_grounded=False,
            refutable=False, mode=mode,
        )
        rec = disposition_mod.DispositionRecord(
            finding_id=f"{key}:{fnd['severity']}",
            severity=fnd["severity"], corroboration=c, gate_grounded=False,
            disposition=disp, reason=reason,
        )
        ledger.record(rec)
        _emit_event(cfg, journal_mod.EventType.disposition_recorded, {
            "finding_id": rec.finding_id, "location": fnd["location"],
            "severity": fnd["severity"], "corroboration": c,
            "disposition": disp.value, "reason": reason,
            "description": (fnd["description"] or "")[:300],
        }, task_key="FEATURE-REVIEW")
        if disp is disposition_mod.Disposition.ACCEPT:
            accepted.append({**fnd, "corroboration": c})
        elif disp is disposition_mod.Disposition.HOLD:
            held.append({**fnd, "corroboration": c})
    _log(log_path, f"feature-review dispositions: {ledger.tally()} "
                   f"(accepted={len(accepted)} held={len(held)})")
    return accepted, held


def _dispatch_drain(
    cfg: RunConfig, run_dir: Path, log_path: Path, repo_root: Path,
    merge_state: merge_mod.MergePassState,
) -> bool:
    """One dispatch-drain pass: spawn runnable tasks (up to max_parallel) until
    nothing is runnable or in-flight, merging eligible PRs after each batch.
    Re-run by the feature-review loop each round (to run the FIX-* tasks it
    appends). Returns True iff the cost ceiling (BUDGET-1) tripped during this
    drain — the caller then holds the run (and stops further review rounds)."""
    budget_tripped = False
    in_flight: dict[Future[str], str] = {}
    with ThreadPoolExecutor(max_workers=max(cfg.max_parallel, 1)) as exe:
        while True:
            tasks = _load_tasks_snapshot(cfg)
            runnable = plan_mod.runnable_now(tasks, integration=cfg.integration)
            runnable = plan_mod.filter_tasks(runnable, cfg.label_filter, cfg.only_keys)
            in_flight_keys = set(in_flight.values())
            runnable = [t for t in runnable if t.key not in in_flight_keys]

            # Budget ceiling (BUDGET-1): once this run's spend reaches the
            # ceiling, stop STARTING new tasks — but let in-flight ones drain
            # (killing a task mid-spawn orphans its worktree/PR). Fires ONLY when
            # there is runnable work to suppress, so a run that merely finished
            # its last task over budget is COMPLETE, not falsely held.
            if runnable and _budget_exceeded(
                    tasks, cfg.max_cost_usd, cfg.cost_baseline_usd):
                if not budget_tripped:
                    budget_tripped = True
                    spent = _run_spend_usd(tasks, cfg.cost_baseline_usd)
                    in_flight_now = sorted(in_flight.values())
                    parked = sorted(t.key for t in runnable)
                    _log(log_path,
                         f"BUDGET: run spend ${spent:.2f} >= ceiling "
                         f"${cfg.max_cost_usd:.2f} — holding; parking "
                         f"{len(parked)} task(s), no new ones will start "
                         f"(in-flight: {in_flight_now or 'none'})")
                    _emit_event(cfg, journal_mod.EventType.budget_exceeded, {
                        "cost_usd": round(spent, 4),
                        "ceiling_usd": cfg.max_cost_usd,
                        "in_flight": in_flight_now,
                        "parked": parked,
                    })
                    _send_notification(cfg, notify_mod.budget_exceeded_notification(
                        run_id=cfg.run_id, cost_usd=spent,
                        ceiling_usd=cfg.max_cost_usd, in_flight=in_flight_now,
                        parked_count=len(parked), tasks_yaml=str(cfg.tasks_path),
                    ))
                runnable = []  # stop starting new work; drain in-flight
            while runnable and len(in_flight) < cfg.max_parallel:
                t = runnable.pop(0)
                snap = TaskSnapshot(
                    key=t.key, summary=t.summary, description=t.description,
                    type=t.type, labels=list(t.labels), model=t.model,
                    agent=t.agent, blocked_by=list(t.blocked_by),
                )
                _mark_in_progress(cfg, snap, run_dir)
                fut = exe.submit(_run_task, snap, cfg, run_dir, log_path, repo_root)
                in_flight[fut] = snap.key
                _log(log_path, f"dispatch {snap.key} submitted")
            if not in_flight:
                break
            done, _pending = wait(list(in_flight), return_when=FIRST_COMPLETED)
            for fut in done:
                key = in_flight.pop(fut)
                try:
                    fut.result()
                except Exception as e:
                    _log(log_path, f"  worker {key} raised: {e}")
                    _send_notification(cfg, notify_mod.worker_exception_notification(
                        task_key=key, run_id=cfg.run_id, exception_repr=repr(e),
                        tasks_yaml=str(cfg.tasks_path),
                    ), task_key=key)
                    try:
                        _mark_blocked(cfg, key, reason=f"worker_exception: {e}")
                    except Exception as mark_err:
                        _log(log_path, f"  worker {key} _mark_blocked itself raised: {mark_err}")
            _maybe_merge_pass(cfg, repo_root, log_path, merge_state)
    return budget_tripped


def _feature_review_round(
    cfg: RunConfig, repo_root: Path, log_path: Path,
    ledger: disposition_mod.DispositionLedger, review_round: int,
) -> bool:
    """One feature-review round: review the cumulative diff vs the PRD ->
    disposition every finding -> append accepted ones as FIX tasks. Returns True
    iff another dispatch round should run (FIX tasks were appended); False to
    stop (no diff / alarm tripped / findings held for a human / clean)."""
    doc = yaml_io.load(cfg.tasks_path)
    verdict = run_feature_review(cfg, repo_root, doc, log_path)
    if verdict is None:
        return False
    accepted, held = apply_dispositions(
        cfg, verdict, mode=cfg.mode, ledger=ledger, log_path=log_path)
    tripped, why = ledger.alarm_tripped(review_round)
    if tripped:
        _log(log_path, f"feature-review: HOLD (alarm) — {why}")
        return False
    if held:
        _log(log_path, f"feature-review: {len(held)} finding(s) need a human "
                       f"(lone CRITICAL / conflict) — holding the feature")
        return False
    if not accepted:
        _log(log_path, "feature-review: clean — no accept-worthy findings")
        return False
    n = _append_fix_tasks(cfg, accepted, review_round)
    _log(log_path, f"feature-review round {review_round}: appended {n} FIX task(s)")
    return n > 0


def _append_fix_tasks(cfg: RunConfig, accepted: list[dict], review_round: int) -> int:
    """Append accepted findings as FIX-* task rows to the tasks.yaml so the next
    dispatch-drain runs them (gated + per-task-paneled like any task). FIX keys
    are unique across rounds (max existing index + 1). Returns the count added."""
    with yaml_io.FileLock(cfg.tasks_path, timeout_seconds=cfg.lock_timeout_seconds):
        doc = yaml_io.load(cfg.tasks_path)
        rows = doc.get("tasks") or []
        existing = [int(str(r.get("key"))[4:]) for r in rows
                    if str(r.get("key", "")).startswith("FIX-")
                    and str(r.get("key"))[4:].isdigit()]
        n = max(existing, default=0)
        added = 0
        for f in accepted:
            n += 1
            loc = f.get("location", "?")
            rows.append({
                "key": f"FIX-{n}",
                "summary": f"fix: {(f.get('description') or loc)[:70]}",
                "description": (
                    f"Address this finding from the final feature review "
                    f"(round {review_round}):\n\n"
                    f"- location: {loc}\n"
                    f"- severity: {f.get('severity')}\n"
                    f"- corroboration: {f.get('corroboration')} reviewer(s)\n\n"
                    f"{f.get('description', '')}\n\n"
                    f"Make the change and add/adjust a test proving it. "
                    f"Commit only — the dispatcher integrates."
                ),
                "type": "Task",
                "labels": ["size:S", "area:fix"],
                "agent": "claude",
            })
            added += 1
        doc["tasks"] = rows
        yaml_io.dump(doc, cfg.tasks_path)
    return added


def _spawn_panel_iterate(
    *,
    cfg: RunConfig,
    snap: TaskSnapshot,
    wt: wt_mod.Worktree,
    repo_root: Path,
    summary_path: Path,
    env: dict,
    log_path: Path,
    panel: cfr_mod.PanelVerdict,
    iterations_left: int,
) -> bool:
    """Re-spawn the Tasker with the panel's blocking findings as a
    corrective prompt. Returns True iff the spawn exited cleanly with at
    least one new commit (or new direct-to-base advance) — i.e., the
    Tasker actually addressed something.

    Errors are logged and propagated as False (the caller decides what to
    do with a failed iterate; today: stop iterating and keep the last
    panel verdict).
    """
    if not panel.blocking_findings:
        # Defensive: caller should only invoke when panel.is_approve is
        # False, but a panel can block on PARSE_FAILED / CHANGES_REQUESTED
        # without blocking_findings. In that case there's nothing concrete
        # to ask the Tasker to fix; skip iterating.
        _log(log_path,
             f"  {snap.key} panel block without blocking findings — "
             f"skipping iterate (no concrete fixes to propose)")
        return False

    findings_block = _render_findings_for_iterate_prompt(panel)
    iter_prompt = _PANEL_ITERATE_PROMPT_PREFIX.format(
        n_findings=len(panel.blocking_findings),
        panel_summary=panel.summary,
        findings_block=findings_block,
        task_key=snap.key,
        iteration_n=cfg.cross_family_panel_iterate - iterations_left + 1,
        iterations_left=iterations_left - 1,
    )
    iter_prompt += spawn_mod.build_prompt(
        task_key=snap.key,
        task_summary=snap.summary,
        task_type=snap.type,
        task_labels=snap.labels,
        task_description=snap.description,
        branch=wt.branch,
        summary_path=summary_path,
        run_id=cfg.run_id,
        max_iterations=cfg.max_iterations,
        financial_paths=cfg.financial_paths,
        skip_design=cfg.skip_design,
        skip_security_linter=cfg.skip_security_linter,
        reviewer_count=cfg.reviewer_count,
    )
    extra = list(cfg.claude_extra_args)
    if snap.model:
        extra.extend(["--model", snap.model])

    # Snapshot feat HEAD AND base_branch tip BEFORE the iterate spawn.
    # The "did the iterate actually produce a commit?" check needs to
    # compare against feat-before-iterate, NOT base — the initial spawn
    # already produced commits on feat, so `base..HEAD > 0` is true
    # regardless of whether this iteration added anything.
    feat_sha_before_iter = _branch_sha(repo_root, wt.branch, log_path, snap.key)
    base_sha_before_iter = _branch_sha(repo_root, cfg.base_branch, log_path, snap.key)

    try:
        result = spawn_mod.spawn_claude(
            claude_bin=cfg.claude_bin, cwd=wt.path, env=env, prompt=iter_prompt,
            extra_args=extra,
            timeout_seconds=cfg.task_timeout_seconds,
        )
    except Exception as e:
        _log(log_path, f"  {snap.key} panel-iterate spawn failed: {e}")
        return False

    _log(log_path,
         f"  {snap.key} panel-iterate spawn exit={result.exit_code}")
    _account_spawn(cfg, snap.key, result, kind="panel-iterate")
    if result.exit_code != 0:
        return False

    # Did this iterate produce a new commit on feat OR advance base
    # (direct-to-base workflow)? Either counts as "Tasker did something".
    # If neither — no-op iterate; re-running the panel on the same diff
    # will produce the same verdict, so short-circuit.
    feat_sha_after = _branch_sha(repo_root, wt.branch, log_path, snap.key)
    base_sha_after = _branch_sha(repo_root, cfg.base_branch, log_path, snap.key)
    feat_advanced = (
        feat_sha_before_iter and feat_sha_after
        and feat_sha_before_iter != feat_sha_after
    )
    base_advanced = (
        base_sha_before_iter and base_sha_after
        and base_sha_before_iter != base_sha_after
    )
    if not (feat_advanced or base_advanced):
        _log(log_path,
             f"  {snap.key} panel-iterate produced no new commits; "
             f"treating as no-op iteration")
        return False
    return True


def _render_findings_for_iterate_prompt(panel: cfr_mod.PanelVerdict) -> str:
    """Format blocking findings as a numbered, scannable block for the
    Tasker's corrective prompt. Distinct from
    `cfr_mod.render_findings_markdown` (which is human-readable for
    summary.md); this format is instruction-shaped for an LLM.
    """
    lines: list[str] = []
    for i, f in enumerate(panel.blocking_findings, 1):
        lines.append(
            f"{i}. **{f.severity.value}** at `{f.location}`"
        )
        if f.description:
            # Indent description so the Tasker reads it as part of the
            # bullet, not a new section.
            for ln in f.description.splitlines():
                lines.append(f"   {ln}")
        if f.fix:
            lines.append(f"   *Fix:* {f.fix}")
        lines.append("")  # blank line between findings
    return "\n".join(lines).rstrip()


def _resolve_diff_bounds(
    cfg: RunConfig,
    snap: TaskSnapshot,
    wt: wt_mod.Worktree,
    repo_root: Path,
    base_sha_before: str | None,
    log_path: Path,
) -> tuple[str, str]:
    """Resolve the ``(base, branch)`` git refs to diff for a Done task.

    Prefers ``base_sha_before..feat-tip`` so the direct-to-base workflow is
    covered (where feat == base_branch by the time we get here). Falls back to
    ``base_branch..feat_branch`` for standard feat-branch work. Shared by the
    cross-family panel and the LLM verifier so both review the same change set.
    """
    feat_tip = _branch_sha(repo_root, wt.branch, log_path, snap.key)
    if base_sha_before and feat_tip and base_sha_before != feat_tip:
        return base_sha_before, feat_tip
    return cfg.base_branch, wt.branch


# --- LLM verification gate (VG-4) -------------------------------------------


@dataclass
class _LlmVerifyOutcome:
    """Result of the LLM verification gate for one Done task.

    ``verified`` is True/False once the gate ran (None only when skipped, but
    the skip path never builds this object — it short-circuits in _run_task).
    ``iterations`` counts the INCOMPLETE → re-spawn-the-Tasker cycles
    performed (0 when VERIFIED on the first try). ``detail`` is the rendered
    gap list (or the verifier's reason/error when no gaps parsed) for the YAML
    row on a block, else None. ``blocked_reason`` is the short label that
    flips the task to Blocked (``verification_incomplete``, or
    ``mechanical_verification_failed`` when an iterate's re-run went red), or
    None when the gate passed. ``mech_outcome`` / ``mech_detail`` are non-None
    only when an iterate re-ran the mechanical gate, so the caller can refresh
    the row's mechanical_verification stamp.
    """

    verified: bool | None
    iterations: int
    cost_usd_total: float
    detail: str | None = None
    blocked_reason: str | None = None
    mech_outcome: str | None = None
    mech_detail: str | None = None


# Diff-detail bound for the rendered gap list stamped on a Blocked row. Keeps
# the YAML readable; the full verdict (incl. raw output) is never persisted.
_VERIFICATION_DETAIL_CHARS = 2000


# Hook for tests to inject a stub verifier without subclassing or
# monkeypatching subprocess.run. When set, it is called in place of
# verifier.run_verifier with the same keyword arguments and must return a
# verifier.VerifierResult. Production code never sets this.
_verifier_run_override = None  # type: ignore[var-annotated]


def set_verifier(fn) -> None:
    """Test-only: override how the LLM verifier is invoked. None restores the
    real verifier.run_verifier. The callable receives the same keyword args
    (task, diff, summary_text, claude_bin, timeout_seconds) and returns a
    verifier.VerifierResult."""
    global _verifier_run_override
    _verifier_run_override = fn


def _verify_llm_and_maybe_iterate(
    *,
    cfg: RunConfig,
    snap: TaskSnapshot,
    wt: wt_mod.Worktree,
    repo_root: Path,
    summary_path: Path,
    env: dict,
    log_path: Path,
    base_sha_before: str | None,
) -> _LlmVerifyOutcome:
    """Run the LLM verifier; iterate on INCOMPLETE up to the budget.

    Each iteration: re-spawn the Tasker with the verifier's gap list, re-run
    the mechanical gate (ordering rule — never re-verify a red suite), then
    re-verify. Returns once VERIFIED, the iterate budget is exhausted, an
    iterate produced no new commit, or an iterate's mechanical re-run went red.
    Never raises — the verifier is conservative (a spawn/parse failure is
    INCOMPLETE, never VERIFIED).
    """
    cost_total = 0.0
    iterations = 0
    while True:
        result = _run_llm_verifier(
            cfg=cfg, snap=snap, wt=wt, repo_root=repo_root,
            summary_path=summary_path, base_sha_before=base_sha_before,
            log_path=log_path, iteration=iterations,
        )
        if result.usage.cost_usd is not None:
            cost_total += result.usage.cost_usd

        if result.verdict.verdict == verifier_mod.VerdictKind.VERIFIED:
            return _LlmVerifyOutcome(
                verified=True, iterations=iterations, cost_usd_total=cost_total,
            )

        # INCOMPLETE. Out of budget → Blocked with the gaps as the detail.
        detail = _render_gaps_detail(result.verdict)
        if iterations >= cfg.max_verify_iterations:
            _log(log_path,
                 f"  {snap.key} verifier INCOMPLETE and iterate budget "
                 f"exhausted ({iterations}/{cfg.max_verify_iterations}) — "
                 f"blocking verification_incomplete")
            return _LlmVerifyOutcome(
                verified=False, iterations=iterations, cost_usd_total=cost_total,
                detail=detail, blocked_reason="verification_incomplete",
            )

        # Iterate: re-spawn the Tasker with the gap list.
        _log(log_path,
             f"  {snap.key} verifier INCOMPLETE — iterating "
             f"({cfg.max_verify_iterations - iterations} attempt(s) left)")
        corrective_ok = _spawn_verifier_iterate(
            cfg=cfg, snap=snap, wt=wt, repo_root=repo_root,
            summary_path=summary_path, env=env, log_path=log_path,
            verdict=result.verdict, iteration_n=iterations + 1,
        )
        iterations += 1
        _emit_event(cfg, journal_mod.EventType.verification_iterate, {
            "iteration": iterations,
            "iterations_remaining": cfg.max_verify_iterations - iterations,
            "corrective_spawn_ok": bool(corrective_ok),
            "gaps": len(result.verdict.gaps),
        }, task_key=snap.key)
        if not corrective_ok:
            _log(log_path,
                 f"  {snap.key} verifier-iterate spawn produced no new "
                 f"commit — blocking with the last gaps")
            return _LlmVerifyOutcome(
                verified=False, iterations=iterations, cost_usd_total=cost_total,
                detail=detail, blocked_reason="verification_incomplete",
            )

        # Ordering rule: re-run the mechanical gate before re-verifying, so the
        # verifier never burns tokens on a suite the iterate may have reddened.
        mech_outcome, mech_detail = _verify_mechanical_and_maybe_retry(
            cfg, snap, wt, summary_path, env, log_path,
        )
        if mech_outcome == "failed":
            _log(log_path,
                 f"  {snap.key} mechanical gate red after verifier-iterate — "
                 f"blocking mechanical_verification_failed")
            return _LlmVerifyOutcome(
                verified=False, iterations=iterations, cost_usd_total=cost_total,
                detail=detail, blocked_reason="mechanical_verification_failed",
                mech_outcome=mech_outcome, mech_detail=mech_detail,
            )
        # Loop: re-run the verifier against the updated diff.


def _run_llm_verifier(
    *,
    cfg: RunConfig,
    snap: TaskSnapshot,
    wt: wt_mod.Worktree,
    repo_root: Path,
    summary_path: Path,
    base_sha_before: str | None,
    log_path: Path,
    iteration: int,
) -> verifier_mod.VerifierResult:
    """Spawn the verifier once over the task + summary + committed diff.

    Emits ``verification_started`` before the spawn, a ``task_spawn_finished``
    after it (so the report rollup folds the verifier's cost into this task's
    totals — acceptance: verifier cost visible in the rollup), and
    ``verification_verdict`` carrying the verdict, gap count, iteration, and
    usage/cost. The test seam ``_verifier_run_override`` stands in for
    verifier.run_verifier so e2e tests need no real claude subprocess.
    """
    _emit_event(cfg, journal_mod.EventType.verification_started,
                {"iteration": iteration}, task_key=snap.key)

    diff_base, diff_branch = _resolve_diff_bounds(
        cfg, snap, wt, repo_root, base_sha_before, log_path,
    )
    diff = cfr_mod.collect_diff(
        repo_root=repo_root, base_branch=diff_base, branch=diff_branch,
    )
    summary_text = ""
    try:
        summary_text = summary_path.read_text(encoding="utf-8")
    except (OSError, FileNotFoundError) as e:
        _log(log_path, f"  {snap.key} verifier: summary.md read failed: {e}")

    task_row = {
        "key": snap.key,
        "summary": snap.summary,
        "type": snap.type,
        "labels": list(snap.labels),
        "description": snap.description,
    }
    runner = _verifier_run_override or verifier_mod.run_verifier
    result = runner(
        task=task_row,
        diff=diff,
        summary_text=summary_text,
        claude_bin=cfg.claude_bin,
        timeout_seconds=cfg.verifier_timeout_seconds,
    )

    # Cost folding for the per-spawn journal rollup. The verifier IS a claude
    # spawn, so it emits the same event the report already sums; spawn_kind
    # tags it for any consumer that wants to separate verifier from Tasker.
    _emit_event(cfg, journal_mod.EventType.task_spawn_finished,
                _verifier_spawn_usage_payload(result), task_key=snap.key)
    _emit_event(cfg, journal_mod.EventType.verification_verdict, {
        "verdict": result.verdict.verdict.value,
        "gaps": len(result.verdict.gaps),
        "iteration": iteration,
        "reason": result.verdict.reason,
        "error": result.error,
        "cost_usd": result.usage.cost_usd,
        "input_tokens": result.usage.input_tokens,
        "output_tokens": result.usage.output_tokens,
        "duration_seconds": result.duration_seconds,
    }, task_key=snap.key)
    _log(log_path,
         f"  {snap.key} verifier verdict={result.verdict.verdict.value} "
         f"gaps={len(result.verdict.gaps)} (iteration {iteration})")
    return result


def _spawn_verifier_iterate(
    *,
    cfg: RunConfig,
    snap: TaskSnapshot,
    wt: wt_mod.Worktree,
    repo_root: Path,
    summary_path: Path,
    env: dict,
    log_path: Path,
    verdict: verifier_mod.VerifierVerdict,
    iteration_n: int,
) -> bool:
    """Re-spawn the Tasker with the verifier's gap list as a corrective prompt.

    Returns True iff the spawn exited cleanly AND produced a new commit (on the
    feat branch or direct-to-base) — i.e., the Tasker actually changed
    something to re-verify. A gapless INCOMPLETE (malformed/unparsed/spawn-
    failed verdict) has nothing concrete to fix, so we skip the re-spawn and
    return False (the caller blocks). Mirrors _spawn_panel_iterate.
    """
    if not verdict.gaps:
        _log(log_path,
             f"  {snap.key} verifier INCOMPLETE without parsed gaps — "
             f"skipping iterate (nothing concrete to fix)")
        return False

    gaps_block = _render_gaps_for_iterate_prompt(verdict)
    iter_prompt = _VERIFIER_ITERATE_PROMPT_PREFIX.format(
        n_gaps=len(verdict.gaps),
        gaps_block=gaps_block,
        task_key=snap.key,
        iteration_n=iteration_n,
        iterations_left=cfg.max_verify_iterations - iteration_n,
    )
    iter_prompt += spawn_mod.build_prompt(
        task_key=snap.key,
        task_summary=snap.summary,
        task_type=snap.type,
        task_labels=snap.labels,
        task_description=snap.description,
        branch=wt.branch,
        summary_path=summary_path,
        run_id=cfg.run_id,
        max_iterations=cfg.max_iterations,
        financial_paths=cfg.financial_paths,
        skip_design=cfg.skip_design,
        skip_security_linter=cfg.skip_security_linter,
        reviewer_count=cfg.reviewer_count,
    )
    extra = list(cfg.claude_extra_args)
    if snap.model:
        extra.extend(["--model", snap.model])

    feat_sha_before_iter = _branch_sha(repo_root, wt.branch, log_path, snap.key)
    base_sha_before_iter = _branch_sha(repo_root, cfg.base_branch, log_path, snap.key)

    try:
        result = spawn_mod.spawn_claude(
            claude_bin=cfg.claude_bin, cwd=wt.path, env=env, prompt=iter_prompt,
            extra_args=extra,
            timeout_seconds=cfg.task_timeout_seconds,
        )
    except Exception as e:
        _log(log_path, f"  {snap.key} verifier-iterate spawn failed: {e}")
        return False
    _log(log_path,
         f"  {snap.key} verifier-iterate spawn exit={result.exit_code}")
    _account_spawn(cfg, snap.key, result, kind="verifier-iterate")
    if result.exit_code != 0:
        return False

    feat_sha_after = _branch_sha(repo_root, wt.branch, log_path, snap.key)
    base_sha_after = _branch_sha(repo_root, cfg.base_branch, log_path, snap.key)
    feat_advanced = (
        feat_sha_before_iter and feat_sha_after
        and feat_sha_before_iter != feat_sha_after
    )
    base_advanced = (
        base_sha_before_iter and base_sha_after
        and base_sha_before_iter != base_sha_after
    )
    if not (feat_advanced or base_advanced):
        _log(log_path,
             f"  {snap.key} verifier-iterate produced no new commits; "
             f"treating as no-op iteration")
        return False
    return True


def _render_gaps_for_iterate_prompt(verdict: verifier_mod.VerifierVerdict) -> str:
    """Format the verifier's gaps as a numbered, scannable block for the
    Tasker's corrective prompt (instruction-shaped, like
    _render_findings_for_iterate_prompt for the panel)."""
    lines: list[str] = []
    for g in verdict.gaps:
        loc = f" at `{g.location}`" if g.location else ""
        lines.append(f"{g.index}.{loc} {g.description}".rstrip())
    return "\n".join(lines)


def _render_gaps_detail(verdict: verifier_mod.VerifierVerdict) -> str:
    """Render the verdict's gaps (or its reason/error fallback) as the YAML
    ``verification_detail`` for a Blocked row — bounded for readability."""
    if verdict.gaps:
        lines = []
        for g in verdict.gaps:
            loc = f"{g.location}: " if g.location else ""
            lines.append(f"{g.index}. {loc}{g.description}")
        text = "\n".join(lines)
    else:
        text = (verdict.reason or
                "verifier returned INCOMPLETE with no parsed gaps")
    return text[:_VERIFICATION_DETAIL_CHARS]


def _verifier_spawn_usage_payload(
    result: verifier_mod.VerifierResult,
) -> dict[str, Any]:
    """Build a task_spawn_finished payload for one verifier spawn so the report
    rollup folds its cost into the task's totals. exit_code is synthesised
    (0 = ran, 1 = spawn failure) because the VerifierResult carries usage, not
    a raw exit code. spawn_kind tags it as a verifier spawn for any consumer
    that wants to separate it from the Tasker spawn."""
    u = result.usage
    return {
        "exit_code": 0 if result.error is None else 1,
        "cost_usd": u.cost_usd,
        "input_tokens": u.input_tokens,
        "output_tokens": u.output_tokens,
        "cache_read_input_tokens": u.cache_read_input_tokens,
        "cache_creation_input_tokens": u.cache_creation_input_tokens,
        "duration_ms": u.duration_ms,
        "num_turns": u.num_turns,
        "model": u.model,
        "spawn_kind": "verifier",
    }


# Hook for tests to inject stub reviewers without subclassing or
# monkeypatching subprocess.run. Production code never sets this.
_panel_reviewers_override: list[cfr_mod.Reviewer] | None = None


def set_panel_reviewers(reviewers: list[cfr_mod.Reviewer] | None) -> None:
    """Test-only: override the reviewer set the panel uses. None restores defaults."""
    global _panel_reviewers_override
    _panel_reviewers_override = reviewers


def _panel_reviewer_factory(cfg: RunConfig) -> list[cfr_mod.Reviewer]:
    if _panel_reviewers_override is not None:
        return _panel_reviewers_override
    return cfr_mod.default_reviewers(timeout_seconds=cfg.cross_family_panel_timeout)


# Test hook for ADVISORY (probationary, non-blocking) reviewers, mirroring
# `set_panel_reviewers`. None means "derive from the target repo's
# .dispatcher.yaml"; an explicit EMPTY LIST forces no advisory reviewers —
# the two are deliberately distinct. Production code never sets this.
_panel_advisory_override: list[cfr_mod.Reviewer] | None = None


def set_panel_advisory_reviewers(reviewers: list[cfr_mod.Reviewer] | None) -> None:
    """Test-only: override the advisory reviewer set the panel uses.

    None restores config-derived behaviour; [] forces no advisory seats.
    """
    global _panel_advisory_override
    _panel_advisory_override = reviewers


def _panel_advisory_reviewer_factory(
    cfg: RunConfig, repo_root: Path, log_path: Path, task_key: str,
) -> list[cfr_mod.Reviewer]:
    """Resolve the advisory (probationary) reviewer seats for one panel run.

    Source of truth is the target repo's `.dispatcher.yaml` `panel.advisory`
    list. This path must NEVER break the authoritative panel: a malformed
    config is logged and yields no advisory reviewers; unknown names are
    skipped and logged.
    """
    if _panel_advisory_override is not None:
        return _panel_advisory_override
    try:
        repo_cfg = repo_config_mod.load(repo_root)
    except repo_config_mod.RepoConfigError as e:
        _log(log_path,
             f"  {task_key} panel: invalid .dispatcher.yaml — running "
             f"without advisory reviewers: {e}")
        return []
    if not repo_cfg.panel_advisory:
        return []
    reviewers, unknown = cfr_mod.advisory_reviewers_from_names(
        repo_cfg.panel_advisory,
        timeout_seconds=cfg.cross_family_panel_timeout,
    )
    for name in unknown:
        _log(log_path,
             f"  {task_key} panel: unknown advisory reviewer {name!r} in "
             f".dispatcher.yaml — skipped")
    return reviewers


def _emit_advisory_finding_events(
    cfg: RunConfig, panel: cfr_mod.PanelVerdict, task_key: str,
) -> None:
    """Emit one `panel_advisory_finding` event per advisory finding.

    The scorecard raw material: family + severity + location + the
    advisory reviewer's overall verdict, truncated like other journal
    payloads. No advisory reviewers (or none with findings) → no events.
    """
    for adv in panel.advisory:
        for f in adv.findings:
            _emit_event(cfg, journal_mod.EventType.panel_advisory_finding, {
                "family": adv.family,
                "severity": f.severity.value,
                "location": f.location,
                "description": (f.description or "")[:500],
                "fix": (f.fix or "")[:500],
                "advisory_verdict": adv.verdict.value,
            }, task_key=task_key)


def _append_panel_findings_to_summary(
    summary_path: Path, panel: cfr_mod.PanelVerdict,
    log_path: Path, task_key: str,
) -> None:
    """Append the rendered panel verdict to the Tasker's summary.md.

    The summary.md is the artefact the human reads when triaging a Blocked
    task. Appending the panel findings here means the auditor sees the
    three families' verdicts inline, not buried in the YAML row.

    Best-effort — a write failure is logged but not fatal.
    """
    try:
        existing = summary_path.read_text(encoding="utf-8") if summary_path.exists() else ""
        block = cfr_mod.render_findings_markdown(panel)
        # Avoid double-appending on re-run.
        if "## Cross-family panel" in existing:
            _log(log_path,
                 f"  {task_key} panel findings already in summary.md; not re-appending")
            return
        sep = "\n\n" if existing and not existing.endswith("\n\n") else ""
        summary_path.write_text(existing + sep + block, encoding="utf-8")
    except OSError as e:
        _log(log_path, f"  {task_key} append-panel-to-summary failed: {e}")


def _branch_sha(repo_root: Path, branch: str,
                log_path: Path, task_key: str) -> str | None:
    """Return the tip SHA of `branch` in `repo_root`, or None on error.

    Used to snapshot base_branch's tip before a spawn so we can later
    detect a fast-forward advance into base (the direct-to-base workflow
    pattern). On any git failure returns None — callers treat that as
    "no snapshot available, fall back to the feat-branch check only."
    """
    import subprocess
    try:
        proc = subprocess.run(
            ["git", "rev-parse", branch],
            cwd=str(repo_root), capture_output=True, text=True,
            check=False, timeout=30,
        )
    except Exception as e:
        _log(log_path, f"  {task_key} base-sha snapshot failed: {e}")
        return None
    if proc.returncode != 0:
        _log(log_path,
             f"  {task_key} `git rev-parse {branch}` exit={proc.returncode}: "
             f"{proc.stderr.strip()}")
        return None
    sha = (proc.stdout or "").strip()
    return sha or None


def _has_commits_on_branch(wt: wt_mod.Worktree, base_branch: str,
                            repo_root: Path,
                            base_sha_before: str | None,
                            log_path: Path, task_key: str,
                            feat_baseline_sha: str | None = None) -> bool:
    """True iff the spawn produced new commits, on the feat branch OR on
    `base_branch` directly (the direct-to-base workflow).

    Two success modes:
    1. **Feature-branch mode (standard)**: the worktree's feat branch has
       at least one commit beyond its baseline. The baseline is
       `base_branch` normally; but when dispatch-time dependency merges
       (INT-4) put dependency commits on the feat branch BEFORE the spawn,
       `feat_baseline_sha` (the post-merge tip) is the baseline instead — so
       the merged dependency commits don't get miscounted as the Tasker's own
       work. This is the original check — Tasker ran `git commit` on feat/X.
    2. **Direct-to-base mode (BSA-style)**: `base_branch`'s tip has
       advanced past `base_sha_before` (the SHA snapshot taken before
       the spawn). This catches the Tasker that fast-forwarded feat/X
       into `base_branch`, leaving the feat-branch check returning 0 —
       which mis-fires as "no commits" when in fact the work landed
       directly on base.

    Either condition is sufficient. If `base_sha_before` is None (the
    pre-spawn snapshot failed for any reason), only mode 1 is checked.

    Used to detect the "Tasker reported Done but forgot to commit"
    failure mode while NOT false-firing on a successful direct-to-base
    merge.
    """
    import subprocess
    # Mode 1: feat branch has commits past its baseline (post-dependency-merge
    # tip when deps were merged in, else base_branch).
    feat_baseline = feat_baseline_sha or base_branch
    try:
        proc = subprocess.run(
            ["git", "rev-list", "--count", f"{feat_baseline}..HEAD"],
            cwd=str(wt.path), capture_output=True, text=True, check=False, timeout=30,
        )
    except Exception as e:
        _log(log_path, f"  {task_key} commit check failed (treating as no-commits): {e}")
        return False
    if proc.returncode != 0:
        _log(log_path, f"  {task_key} `git rev-list` exit={proc.returncode}: {proc.stderr.strip()}")
        return False
    count = (proc.stdout or "").strip()
    try:
        feat_count = int(count)
    except ValueError:
        feat_count = 0
    if feat_count > 0:
        return True

    # Mode 2: base_branch tip advanced since the spawn started. Detects
    # the direct-to-base workflow where the Tasker FF-merged feat/X into
    # base_branch, leaving feat/X == base_branch (so mode 1 returns 0
    # despite the work landing).
    if base_sha_before is None:
        return False
    base_sha_after = _branch_sha(repo_root, base_branch, log_path, task_key)
    if base_sha_after is None:
        return False
    if base_sha_after == base_sha_before:
        return False
    # Confirm base actually moved FORWARD (not a force-reset or rewind) — and,
    # when dependency branches were merged into the feat branch (INT-4), that
    # base advanced by the Tasker's OWN commits and not merely by the merged
    # dependency commits. Excluding `^feat_baseline_sha` drops everything
    # reachable from the post-merge tip (the deps + their merge commits), so a
    # dependent that only fast-forwarded its dep-containing branch into base
    # without committing its own work is correctly seen as no-commits.
    rev_list_args = ["git", "rev-list", "--count",
                     f"{base_sha_before}..{base_sha_after}"]
    if feat_baseline_sha:
        rev_list_args.append(f"^{feat_baseline_sha}")
    try:
        proc = subprocess.run(
            rev_list_args,
            cwd=str(repo_root), capture_output=True, text=True,
            check=False, timeout=30,
        )
    except Exception as e:
        _log(log_path,
             f"  {task_key} direct-to-base check failed: {e}")
        return False
    if proc.returncode != 0:
        _log(log_path,
             f"  {task_key} `git rev-list {base_sha_before}..{base_sha_after}` "
             f"exit={proc.returncode}: {proc.stderr.strip()}")
        return False
    try:
        advance_count = int((proc.stdout or "").strip())
    except ValueError:
        advance_count = 0
    if advance_count > 0:
        _log(log_path,
             f"  {task_key} direct-to-base advance detected: "
             f"{base_branch} moved {base_sha_before[:8]}..{base_sha_after[:8]} "
             f"({advance_count} commit(s))")
        return True
    return False


_PANEL_ITERATE_PROMPT_PREFIX = """\
A cross-family review panel (three independent reviewers, one each from
Claude, Gemini, and Codex) found {n_findings} blocking finding(s) on the
work you already committed on this branch. Your job is to address ONLY
the findings below. DO NOT redo the implementation. DO NOT re-investigate
the requirements.

Panel verdict: {panel_summary}

Blocking findings (CRITICAL and HIGH only — MEDIUM/LOW are informational):

{findings_block}

Steps:
1. For each finding, locate the cited `file:line` and apply the suggested
   Fix. If you disagree with the Fix, apply the spirit of the finding
   (the underlying defect the reviewer identified) and add a short
   "Panel iteration note" subsection to $SUMMARY_PATH explaining your
   decision. DO NOT silently skip a finding.
2. Run / update tests for any code path you change. If a finding is
   specifically about test quality (a vacuous test, a tautology, a
   missing edge case), the fix is the test itself — write a test that
   would fail under the defect the reviewer described.
3. `git add` the modified files. Commit:
   `git commit -m "fix(<scope>): [{task_key}] address cross-family panel findings"`.
   (Conventional-commit format per CLAUDE.md. No author attribution.)
4. Append a "Panel iteration {iteration_n}" section to $SUMMARY_PATH
   summarising what changed for each finding. Status stays Done.

The dispatcher will re-run the panel against your updated diff. If the
panel still raises blocking findings, this corrective cycle may repeat
up to {iterations_left} more time(s) before the task is marked Blocked
for human triage.

Task context for reference (DO NOT redo):
"""


_VERIFIER_ITERATE_PROMPT_PREFIX = """\
An independent verifier checked whether the work you committed on this branch
actually does what the task asked — and found {n_gaps} gap(s): things that
were stubbed, deferred, quietly narrowed, or claimed-but-untested versus the
task's description and acceptance criteria. Your job is to CLOSE these gaps on
the existing work. DO NOT redo the implementation from scratch.

Gaps (close ALL of them):

{gaps_block}

Steps:
1. For each gap, locate the cited code (a `file:line` when given) and make the
   work genuinely satisfy what the task asked — implement the stubbed/deferred
   piece, restore the narrowed scope, or add the missing test that proves the
   claim. If you believe a gap is a false positive, do NOT silently skip it:
   add a short "Verifier iteration note" subsection to $SUMMARY_PATH explaining
   why, with the evidence.
2. Run / update tests for any code path you change.
3. `git add` the modified files. Commit:
   `git commit -m "fix(<scope>): [{task_key}] close verifier gaps"`.
   (Conventional-commit format per CLAUDE.md. No author attribution.)
4. Update $SUMMARY_PATH so its "Files changed" section reflects reality.
   Status stays Done.

The dispatcher will re-run the repo test suite and then re-verify your updated
diff. If gaps remain, this corrective cycle may repeat up to {iterations_left}
more time(s) before the task is marked Blocked (verification_incomplete) for
human triage.

Task context for reference (DO NOT redo):
"""


_COMMIT_RETRY_PROMPT_PREFIX = """\
Your previous run on this task reported `Status: Done` in the summary file
but produced ZERO commits on this branch. The work files exist in the
worktree but have not been `git commit`ed.

This is a recoverable mistake — the work is right there, just uncommitted.

Please do ONLY these steps. Do NOT redo the implementation or analysis:

1. Run `git status` to see exactly what's uncommitted in this worktree.
2. Run `git add <files>` for the files that should be tracked (review
   the list — don't blindly `git add -A` if there are stray build
   artifacts you don't want committed).
3. Run `git commit -m "<message>"` with a conventional-commit message
   following the project's CLAUDE.md commit format: `type(scope): summary`.
   For BSA tickets, include `[<TASK_KEY>]` in the subject line. No author
   attribution (no Co-Authored-By, no "Generated with").
4. Verify with `git log --oneline {base_branch}..HEAD` that your commit
   is on the branch.
5. Update the summary file at $SUMMARY_PATH so its "Files changed"
   section reflects the actual committed files (run `git diff --name-only
   {base_branch}..HEAD` to get the list). Status stays `Done`.

The dispatcher will verify commits exist before accepting Done this time.
If you still produce no commits, the task will be Blocked.

Task context (for reference, do NOT redo):
"""


_PUSH_RETRY_PROMPT_PREFIX = """\
Your previous run on this task reported `Status: Done` and committed work on
this branch, but the dispatcher could not confirm the work reached the remote:

  {detail}

This is a recoverable mistake — the commits are right there, they just need to
be pushed (and a PR opened, if this run raises PRs). Do ONLY these steps. Do
NOT redo the implementation, the review, or the analysis:

1. Confirm your commits are present:
   `git log --oneline {base_branch}..HEAD`.
2. Push the branch to the remote, setting upstream:
   `git push -u origin {branch}`.
   (If the push is rejected because the remote moved, rebase onto the latest
   `origin/{base_branch}` first, then push — do NOT force-push over others' work.)
{pr_step}{final_step}. Update the `## PR` section of the summary file at $SUMMARY_PATH so it
   reflects reality (the PR URL if one exists, otherwise an honest
   `Not raised: <reason>`). Status stays `Done`.

The dispatcher will re-check the push/PR state after this run. If the branch is
still unpushed, the task stays Done but its row is flagged `needs_push: true`
for a human to finish the push.

Task context (for reference, do NOT redo):
"""


_PUSH_RETRY_PR_STEP = """\
3. Ensure a pull request exists for this branch. Check first with
   `gh pr list --head {branch} --state open`; if none exists, open one with
   `gh pr create --base {base_branch} --head {branch}` (fill in a title/body
   consistent with the summary file).
"""


def _retry_for_commit(cfg: RunConfig, snap: TaskSnapshot, wt: wt_mod.Worktree,
                      repo_root: Path, summary_path: Path, env: dict,
                      log_path: Path,
                      feat_baseline_sha: str | None = None) -> str | None:
    """Re-spawn the Tasker with a corrective prompt asking only for the
    missing commit. Returns the spawn result's exit-code-based outcome
    or None if the retry left no commits.

    `repo_root` is needed so the post-spawn commit check can also detect
    a direct-to-base fast-forward (the retry Tasker may FF into
    base_branch instead of leaving commits on the feat branch).

    `feat_baseline_sha` (INT-4) is the post-dependency-merge tip, so the
    retry's commit check measures the Tasker's own work, not the merged
    dependency commits. None for tasks with no merged dependencies.
    """
    prompt = _COMMIT_RETRY_PROMPT_PREFIX.format(base_branch=cfg.base_branch)
    prompt += spawn_mod.build_prompt(
        task_key=snap.key,
        task_summary=snap.summary,
        task_type=snap.type,
        task_labels=snap.labels,
        task_description=snap.description,
        branch=wt.branch,
        summary_path=summary_path,
        run_id=cfg.run_id,
        max_iterations=cfg.max_iterations,
        financial_paths=cfg.financial_paths,
        skip_design=cfg.skip_design,
        skip_security_linter=cfg.skip_security_linter,
        reviewer_count=cfg.reviewer_count,
    )
    retry_extra = list(cfg.claude_extra_args)
    if snap.model:
        retry_extra.extend(["--model", snap.model])
    # Snapshot base_branch tip BEFORE the retry spawn so we can detect a
    # direct-to-base advance the retry may produce (parallel to the
    # check performed on the first-spawn path).
    retry_base_sha_before = _branch_sha(
        repo_root, cfg.base_branch, log_path, snap.key)
    try:
        result = spawn_mod.spawn_claude(
            claude_bin=cfg.claude_bin, cwd=wt.path, env=env, prompt=prompt,
            extra_args=retry_extra,
            timeout_seconds=cfg.task_timeout_seconds,
        )
    except Exception as e:
        _log(log_path, f"  {snap.key} commit-retry spawn failed: {e}")
        return None
    _log(log_path, f"  {snap.key} commit-retry exited code={result.exit_code}")
    _account_spawn(cfg, snap.key, result, kind="commit-retry")
    if not _has_commits_on_branch(
            wt, cfg.base_branch, repo_root,
            retry_base_sha_before, log_path, snap.key,
            feat_baseline_sha=feat_baseline_sha):
        return None
    return "retried_ok"


@dataclass
class _PrOpenOutcome:
    """Result of the pr-mode auto-raise (PRF-2).

    On success ``url`` (and usually ``number`` + ``base_sha``) are set and
    ``blocked_reason`` is None. On failure ``url`` is None and
    ``blocked_reason`` carries the short label the caller stamps as
    ``blocked_reason`` on the row.
    """

    url: str | None = None
    number: int | None = None
    base_sha: str | None = None
    blocked_reason: str | None = None


def _push_branch(
    cwd: Path, branch: str, log_path: Path, task_key: str,
) -> tuple[bool, str]:
    """Push ``branch`` to ``origin`` from ``cwd`` (the task's worktree).

    Returns ``(ok, detail)``. ``GIT_TERMINAL_PROMPT=0`` makes an
    auth-requiring remote fail fast rather than hang the worker thread. A
    git worktree shares its parent repo's remotes, so ``origin`` resolves
    from inside the worktree.
    """
    import subprocess
    try:
        proc = subprocess.run(
            ["git", "push", "-u", "origin", branch],
            cwd=str(cwd), capture_output=True, text=True, check=False,
            timeout=120, env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
        )
    except FileNotFoundError as e:
        return False, f"git not found: {e}"
    except subprocess.TimeoutExpired:
        return False, "git push timed out after 120s"
    except Exception as e:  # pragma: no cover - defensive
        return False, f"git push raised: {e}"
    if proc.returncode != 0:
        detail = (proc.stderr.strip() or proc.stdout.strip()
                  or f"git push exit {proc.returncode}")
        _log(log_path, f"  {task_key} git push failed: {detail[:200]}")
        return False, detail[:300]
    return True, "pushed"


def _generated_pr_title(snap: TaskSnapshot) -> str:
    """Generate a PR title from task metadata when no prepared title exists.

    ``<type-prefix>: [KEY] <summary>`` — the scope is omitted because the
    dispatcher can't infer it; the conventional-commit type comes from the
    task type via the same map :func:`worktree.branch_name` uses.
    """
    prefix = wt_mod.BRANCH_PREFIX_BY_TYPE.get((snap.type or "").lower(), "feat")
    return f"{prefix}: [{snap.key}] {snap.summary}"


def _generated_pr_body(snap: TaskSnapshot, s: summary_mod.Summary) -> str:
    """Generate a PR body from the parsed summary when no prepared body exists.

    Self-contained per the PR-body rules: What (from the summary's "What
    landed", falling back to the task summary), optional Key decisions, and
    the ticket key. No attribution.
    """
    parts = ["## What", (s.what_landed.strip() or snap.summary), ""]
    if s.key_decisions.strip():
        parts += ["## Key decisions", s.key_decisions.strip(), ""]
    parts += ["## Ticket", snap.key]
    return "\n".join(parts)


def _pr_mode_open_pr(
    cfg: RunConfig,
    snap: TaskSnapshot,
    s: summary_mod.Summary,
    wt: wt_mod.Worktree,
    repo_root: Path,
    log_path: Path,
) -> _PrOpenOutcome:
    """pr-mode auto-raise (PRF-2): push the branch + open the PR against the
    run's feature branch.

    The PR base is the run's feature branch (``cfg.feature_branch``, which is
    also the repointed ``cfg.base_branch`` in pr mode). The body comes from the
    Tasker's prepared PR section when present, else is generated from the
    summary; same for the title. On success emits a ``pr_opened`` journal event
    (number, url, target, base sha) and returns the URL/number. A push failure
    or a ``gh pr create`` failure returns a blocked_reason instead — no PR was
    opened, so the task Blocks rather than silently advancing.
    """
    base = cfg.feature_branch or cfg.base_branch

    pushed, push_detail = _push_branch(wt.path, wt.branch, log_path, snap.key)
    if not pushed:
        return _PrOpenOutcome(blocked_reason=f"pr_push_failed: {push_detail}")

    title = s.prepared_pr_title or _generated_pr_title(snap)
    body = s.prepared_pr_body or _generated_pr_body(snap, s)
    body_source = "prepared" if s.prepared_pr_body else "generated"

    result = pr_mod.raise_pr(
        cwd=wt.path,
        title=title,
        body=body,
        branch=wt.branch,
        base=base,
        gh_bin=cfg.gh_bin,
    )
    if result.url is None:
        _log(log_path, f"  {snap.key} pr-mode gh pr create failed: {result.error}")
        return _PrOpenOutcome(
            blocked_reason=f"pr_open_failed: {result.error}"[:300],
        )

    base_sha = _branch_sha(repo_root, base, log_path, snap.key)
    _log(log_path,
         f"  {snap.key} pr-mode PR opened against {base}: {result.url} "
         f"(#{result.number}, body={body_source})")
    _emit_event(cfg, journal_mod.EventType.pr_opened, {
        "number": result.number,
        "url": result.url,
        "target": base,
        "base_sha": base_sha,
        "body_source": body_source,
    }, task_key=snap.key)
    return _PrOpenOutcome(
        url=result.url, number=result.number, base_sha=base_sha,
    )


def _verify_push_and_maybe_retry(
    cfg: RunConfig,
    snap: TaskSnapshot,
    wt: wt_mod.Worktree,
    summary_path: Path,
    env: dict,
    log_path: Path,
    *,
    expect_pr: bool,
) -> bool:
    """Verify the Done task's branch is pushed (and a PR exists when expected).

    Mirrors the commit-retry safety net: a clean push (and PR) is a no-op; a
    missing push/PR triggers ONE corrective push/PR-only re-spawn, after which
    the state is re-checked. Returns True iff the work is STILL unpushed (or the
    PR still missing) after the retry — the caller flags ``needs_push`` on the
    row. Returns False for a clean/recovered push, for a skipped check (no
    remote), and for an inconclusive check (a git read error): an inability to
    confirm must never be reported as a confirmed-unpushed branch.

    ``expect_pr`` controls only the PR half — the branch push is always
    verified. The caller passes False for a Done that honestly declared its PR
    was not raised, so a deliberately PR-less Done isn't flagged for a missing
    PR (it must still push, though).

    Every outcome emits one ``push_verify`` journal event so the decision is
    reconstructable from the journal alone — including the no-remote skip.
    """
    res = pv_mod.verify(
        repo_root=wt.path,
        branch=wt.branch,
        expect_pr=expect_pr,
        gh_bin=cfg.gh_bin,
        log=lambda m: _log(log_path, m),
    )

    if res.status == "skipped-no-remote":
        _log(log_path, f"  {snap.key} push-verify skipped: {res.detail}")
        _emit_event(cfg, journal_mod.EventType.push_verify, {
            "expect_pr": expect_pr, "outcome": "skipped-no-remote",
            "reason": res.detail, "retry_attempted": False,
        }, task_key=snap.key)
        return False
    if res.status == "error":
        _log(log_path, f"  {snap.key} push-verify inconclusive: {res.detail}")
        _emit_event(cfg, journal_mod.EventType.push_verify, {
            "expect_pr": expect_pr, "outcome": "error",
            "reason": res.detail, "retry_attempted": False,
        }, task_key=snap.key)
        return False
    if not res.needs_attention:
        _emit_event(cfg, journal_mod.EventType.push_verify, {
            "expect_pr": expect_pr, "outcome": "pushed",
            "reason": res.detail, "pr_checked": res.pr_checked,
            "retry_attempted": False,
        }, task_key=snap.key)
        return False

    # not-pushed / no-pr → one corrective push/PR-only re-spawn, then re-check.
    _log(log_path,
         f"  {snap.key} reported Done but {res.status} ({res.detail}) — "
         f"retrying with push/PR-only prompt")
    _retry_for_push(cfg, snap, wt, summary_path, env, log_path,
                    initial=res, expect_pr=expect_pr)
    res2 = pv_mod.verify(
        repo_root=wt.path,
        branch=wt.branch,
        expect_pr=expect_pr,
        gh_bin=cfg.gh_bin,
        log=lambda m: _log(log_path, m),
    )
    if not res2.needs_attention:
        # Recovered (status "ok") or a now-inconclusive read — either way we do
        # not flag. "recovered" is the common, intended outcome.
        outcome = "recovered" if res2.status == "ok" else res2.status
        _log(log_path, f"  {snap.key} push-verify after retry: {outcome}")
        _emit_event(cfg, journal_mod.EventType.push_verify, {
            "expect_pr": expect_pr, "outcome": outcome,
            "reason": res2.detail, "pr_checked": res2.pr_checked,
            "retry_attempted": True, "pre_retry_status": res.status,
        }, task_key=snap.key)
        return False

    _log(log_path,
         f"  {snap.key} push-verify still {res2.status} after retry — "
         f"flagging needs_push")
    _emit_event(cfg, journal_mod.EventType.push_verify, {
        "expect_pr": expect_pr, "outcome": "needs_push",
        "reason": res2.detail, "pr_checked": res2.pr_checked,
        "retry_attempted": True, "pre_retry_status": res.status,
        "post_retry_status": res2.status,
    }, task_key=snap.key)
    return True


def _retry_for_push(
    cfg: RunConfig,
    snap: TaskSnapshot,
    wt: wt_mod.Worktree,
    summary_path: Path,
    env: dict,
    log_path: Path,
    *,
    initial: pv_mod.PushVerifyResult,
    expect_pr: bool,
) -> bool:
    """Re-spawn the Tasker with a push/PR-only corrective prompt.

    Returns whether the spawn exited cleanly (exit code 0). The caller re-checks
    the push state regardless of this return — a clean exit does not guarantee
    the Tasker actually pushed, and a non-zero exit does not guarantee it
    didn't.
    """
    pr_step = ""
    final_step = 3
    if expect_pr:
        pr_step = _PUSH_RETRY_PR_STEP.format(
            branch=wt.branch, base_branch=cfg.base_branch,
        )
        final_step = 4
    prompt = _PUSH_RETRY_PROMPT_PREFIX.format(
        detail=initial.detail,
        branch=wt.branch,
        base_branch=cfg.base_branch,
        pr_step=pr_step,
        final_step=final_step,
    )
    prompt += spawn_mod.build_prompt(
        task_key=snap.key,
        task_summary=snap.summary,
        task_type=snap.type,
        task_labels=snap.labels,
        task_description=snap.description,
        branch=wt.branch,
        summary_path=summary_path,
        run_id=cfg.run_id,
        max_iterations=cfg.max_iterations,
        financial_paths=cfg.financial_paths,
        skip_design=cfg.skip_design,
        skip_security_linter=cfg.skip_security_linter,
        reviewer_count=cfg.reviewer_count,
    )
    retry_extra = list(cfg.claude_extra_args)
    if snap.model:
        retry_extra.extend(["--model", snap.model])
    try:
        result = spawn_mod.spawn_claude(
            claude_bin=cfg.claude_bin, cwd=wt.path, env=env, prompt=prompt,
            extra_args=retry_extra,
            timeout_seconds=cfg.task_timeout_seconds,
        )
    except Exception as e:
        _log(log_path, f"  {snap.key} push-retry spawn failed: {e}")
        return False
    _log(log_path, f"  {snap.key} push-retry exited code={result.exit_code}")
    _account_spawn(cfg, snap.key, result, kind="push-retry")
    return result.exit_code == 0


_TEST_FIX_RETRY_PROMPT_PREFIX = """\
Your previous run on this task reported `Status: Done` and committed work on
this branch, but the repo's own test suite is RED in this worktree. The
dispatcher ran the repo's configured verification command and it failed:

  Command:   {command}
  Exit code: {exit_code}

Output tail (the last part of the combined output):

```
{output_tail}
```

Do ONLY these steps. Do NOT redo the implementation or analysis:

1. Run the command above in this worktree and reproduce the failure.
2. Fix ONLY what is needed to make it pass. The minimal change wins — a
   broken test of yours, a missed import, a stale fixture. Do NOT redo or
   rework the implementation beyond what the failure demands.
3. Re-run the command and confirm it exits 0.
4. `git add` the modified files and commit:
   `git commit -m "fix(<scope>): [{task_key}] make repo test suite green"`.
   (Conventional-commit format per CLAUDE.md, task key in the subject, no
   author attribution.)
5. Update the summary file at $SUMMARY_PATH if its "Files changed" section
   shifted. Status stays `Done`.

The dispatcher will re-run the command after this session. If the suite is
still red, the task will be Blocked with reason
mechanical_verification_failed.

Task context (for reference, do NOT redo):
"""


def _verify_mechanical_and_maybe_retry(
    cfg: RunConfig,
    snap: TaskSnapshot,
    wt: wt_mod.Worktree,
    summary_path: Path,
    env: dict,
    log_path: Path,
) -> tuple[str, str | None]:
    """Run the worktree's `.dispatcher.yaml` `test:` command; retry once on red.

    Mirrors the commit/push safety nets: a green run is a no-op; a red run
    triggers ONE corrective fix-the-tests re-spawn, after which the command is
    re-run REGARDLESS of the spawn's outcome (a clean exit doesn't guarantee a
    fix, a dirty exit doesn't guarantee no fix — only the re-run's verdict
    counts). Returns ``(outcome, detail)``:

      ("passed", None)    — green, first try or after the retry.
      ("skipped", None)   — no `.dispatcher.yaml` or no `test:` key; the gate
                            does not apply (preserves pre-gate behavior for
                            unconfigured repos — Done stays Done).
      ("failed", detail)  — still red after the retry (detail = the failing
                            output tail) or the config is malformed (detail =
                            the parse error; no retry, because a fix-the-tests
                            prompt can't fix a config the dispatcher can't
                            parse). The caller flips the task to Blocked.

    Every test execution emits one ``verification_mechanical`` journal event;
    the skip and malformed-config outcomes emit one each, so the gate's
    decision is reconstructable from the journal alone. RepoConfigError is
    consumed here, never propagated; unexpected exceptions propagate to the
    worker's handler as usual.
    """
    try:
        repo_cfg = repo_config_mod.load(wt.path)
    except repo_config_mod.RepoConfigError as exc:
        err = str(exc)[:500]
        _log(log_path,
             f"  {snap.key} mechanical-verify: invalid .dispatcher.yaml: {err}")
        _emit_event(cfg, journal_mod.EventType.verification_mechanical, {
            "outcome": "failed",
            "error": err,
            "exit_code": None,
            "retried": False,
        }, task_key=snap.key)
        return "failed", err

    if repo_cfg.test is None:
        # Distinguish "the repo never opted in" from "the file exists but
        # declares no test command" — same skip, different journaled reason.
        reason = (
            "no test command"
            if (wt.path / repo_config_mod.CONFIG_FILENAME).exists()
            else "no .dispatcher.yaml"
        )
        _log(log_path, f"  {snap.key} mechanical-verify skipped: {reason}")
        _emit_event(cfg, journal_mod.EventType.verification_mechanical, {
            "outcome": "skipped",
            "reason": reason,
        }, task_key=snap.key)
        return "skipped", None

    first = _run_mechanical_test(cfg, snap, wt, repo_cfg,
                                 retried=False, log_path=log_path)
    if first.passed:
        return "passed", None

    _log(log_path,
         f"  {snap.key} reported Done but the repo test command is red "
         f"(exit={first.exit_code}) — retrying with fix-the-tests prompt")
    _retry_for_test_fix(cfg, snap, wt, summary_path, env, log_path,
                        command=repo_cfg.test, first=first)
    second = _run_mechanical_test(cfg, snap, wt, repo_cfg,
                                  retried=True, log_path=log_path)
    if second.passed:
        _log(log_path, f"  {snap.key} mechanical-verify recovered after retry")
        return "passed", None
    return "failed", second.output_tail


def _run_mechanical_test(
    cfg: RunConfig,
    snap: TaskSnapshot,
    wt: wt_mod.Worktree,
    repo_cfg: repo_config_mod.RepoConfig,
    *,
    retried: bool,
    log_path: Path,
) -> mv_mod.MechanicalVerifyResult:
    """Execute the repo test command once and journal the execution.

    One ``verification_mechanical`` event per execution — the first run and
    the post-fix re-run each get their own, distinguished by ``retried``.
    ``unknown_keys`` from the config loader ride along when non-empty (the
    journaled note the loader's forward-compat contract promises).
    """
    res = mv_mod.run_test_command(
        repo_cfg.test,
        worktree=wt.path,
        timeout_seconds=cfg.verify_test_timeout_seconds,
        log=lambda m: _log(log_path, m),
    )
    outcome = "passed" if res.passed else "failed"
    _log(log_path,
         f"  {snap.key} mechanical-verify {outcome} "
         f"(exit={res.exit_code}, {res.duration_seconds:.1f}s"
         f"{', retried' if retried else ''})")
    payload: dict[str, Any] = {
        "command": repo_cfg.test,
        "exit_code": res.exit_code,
        "duration_seconds": round(res.duration_seconds, 3),
        "retried": retried,
        "outcome": outcome,
        "output_tail": res.output_tail,
    }
    if repo_cfg.unknown_keys:
        payload["unknown_keys"] = list(repo_cfg.unknown_keys)
    _emit_event(cfg, journal_mod.EventType.verification_mechanical,
                payload, task_key=snap.key)
    return res


def _retry_for_test_fix(
    cfg: RunConfig,
    snap: TaskSnapshot,
    wt: wt_mod.Worktree,
    summary_path: Path,
    env: dict,
    log_path: Path,
    *,
    command: str,
    first: mv_mod.MechanicalVerifyResult,
) -> bool:
    """Re-spawn the Tasker with a fix-the-tests-only corrective prompt.

    Returns whether the spawn exited cleanly (exit code 0). The caller
    re-runs the test command regardless of this return — same philosophy as
    the push retry: the re-run's verdict is the only thing that counts.
    """
    prompt = _TEST_FIX_RETRY_PROMPT_PREFIX.format(
        command=command,
        exit_code=(first.exit_code if first.exit_code is not None
                   else "none (timed out / never ran)"),
        output_tail=first.output_tail,
        task_key=snap.key,
    )
    prompt += spawn_mod.build_prompt(
        task_key=snap.key,
        task_summary=snap.summary,
        task_type=snap.type,
        task_labels=snap.labels,
        task_description=snap.description,
        branch=wt.branch,
        summary_path=summary_path,
        run_id=cfg.run_id,
        max_iterations=cfg.max_iterations,
        financial_paths=cfg.financial_paths,
        skip_design=cfg.skip_design,
        skip_security_linter=cfg.skip_security_linter,
        reviewer_count=cfg.reviewer_count,
    )
    retry_extra = list(cfg.claude_extra_args)
    if snap.model:
        retry_extra.extend(["--model", snap.model])
    try:
        result = spawn_mod.spawn_claude(
            claude_bin=cfg.claude_bin, cwd=wt.path, env=env, prompt=prompt,
            extra_args=retry_extra,
            timeout_seconds=cfg.task_timeout_seconds,
        )
    except Exception as e:
        _log(log_path, f"  {snap.key} test-fix retry spawn failed: {e}")
        return False
    _log(log_path, f"  {snap.key} test-fix retry exited code={result.exit_code}")
    _account_spawn(cfg, snap.key, result, kind="test-fix-retry")
    return result.exit_code == 0


def _resolve_summary(
    cfg: RunConfig,
    snap: TaskSnapshot,
    s: summary_mod.Summary,
    wt: wt_mod.Worktree,
    log_path: Path,
) -> tuple[str, str | None, str | None]:
    """Decide the final (status, pr_url, blocked_reason) for one task.

    Handles the awaiting-human-approval branches per mode.
    """
    if not s.awaiting_human_approval:
        return s.status or plan_mod.BLOCKED, None, None

    # PR-flow mode (PRF-2): the raise-time human gate is removed — gating moves
    # to the merge step (PRF-4). A Tasker that parked at its own
    # Critical/financial gate with a prepared PR is treated as ready-to-raise:
    # the dispatcher pushes + opens the PR against the feature branch downstream
    # (after the verification gate + panel), reusing the prepared body. Return
    # DONE so those gates run; the auto-raise block consumes the prepared
    # metadata. No human prompt, no awaiting-approval notification.
    if cfg.integration == "pr":
        _log(log_path,
             f"  {snap.key} pr mode — raise-time human gate skipped "
             f"(gating moves to merge, PRF-4)")
        _emit_event(cfg, journal_mod.EventType.pr_gate, {
            "decision": "auto-pr-mode",
            "mode": cfg.mode,
            "pr_title": s.prepared_pr_title,
            "pr_branch": s.prepared_pr_branch,
        }, task_key=snap.key)
        return plan_mod.DONE, None, None

    # PR-gate event: notify here so the human sees the gate trip on
    # their phone whether the dispatcher proceeds to stdin (supervised)
    # or parks the task Blocked (unattended). Best-effort.
    _send_notification(cfg, notify_mod.awaiting_pr_approval_notification(
        task_key=snap.key,
        summary=snap.summary,
        pr_title=s.prepared_pr_title,
        pr_branch=s.prepared_pr_branch,
        run_id=cfg.run_id,
        summary_path=None,  # _resolve_summary doesn't have summary_path
    ), task_key=snap.key)

    def _gate(decision: str, **extra) -> None:
        """Journal one pr_gate decision. Records who decided and the outcome
        so an auditor can reconstruct every gate trip from the journal."""
        _emit_event(cfg, journal_mod.EventType.pr_gate, {
            "decision": decision,
            "mode": cfg.mode,
            "pr_title": s.prepared_pr_title,
            "pr_branch": s.prepared_pr_branch,
            **extra,
        }, task_key=snap.key)

    # Awaiting human PR approval.
    if cfg.mode == "unattended":
        _log(log_path, f"  {snap.key} awaiting human PR approval — left Blocked")
        _gate("deferred-unattended")
        return plan_mod.BLOCKED, None, "awaiting human PR approval"

    # supervised: ask
    decision = _ask_human(
        _format_pr_gate_prompt(snap, s),
        choices=["approve", "reject", "skip"],
    )
    if decision == "approve":
        result = pr_mod.raise_pr(
            cwd=wt.path,
            title=s.prepared_pr_title or "",
            body=s.prepared_pr_body or "",
            branch=s.prepared_pr_branch or "",
            gh_bin=cfg.gh_bin,
        )
        if result.url:
            _log(log_path, f"  {snap.key} PR raised after human approval: {result.url}")
            _gate("approve", pr_url=result.url)
            return plan_mod.DONE, result.url, None
        _log(log_path, f"  {snap.key} gh pr create failed: {result.error}")
        _gate("approve", pr_url=None, error=f"gh pr create failed: {result.error}"[:300])
        return plan_mod.BLOCKED, None, f"gh pr create failed: {result.error}"
    if decision == "reject":
        _log(log_path, f"  {snap.key} human rejected PR")
        _gate("reject")
        return plan_mod.BLOCKED, None, "human rejected PR"
    _log(log_path, f"  {snap.key} human skipped PR approval")
    _gate("skip")
    return plan_mod.BLOCKED, None, "human skipped PR approval"


# --- YAML mutation helpers -------------------------------------------------


def _mutate_row(cfg: RunConfig, task_key: str, mutator) -> bool:
    """Acquire the FileLock, load the YAML, find the row by key, apply
    `mutator(row)`, save. The mutator is called with the row's ruamel mapping.

    Returns True if the row was found and mutated, False if no row matched
    `task_key`. A missing row is logged to stderr but is NOT fatal -- the
    YAML may have been edited externally between plan-load and write, and
    crashing the dispatcher because a status flip can't land is a worse
    outcome than letting the run continue.
    """
    with yaml_io.FileLock(cfg.tasks_path, timeout_seconds=cfg.lock_timeout_seconds):
        doc = yaml_io.load(cfg.tasks_path)
        for row in doc.get("tasks", []):
            if str(row.get("key")) == task_key:
                mutator(row)
                yaml_io.dump(doc, cfg.tasks_path)
                return True
        sys.stderr.write(
            f"warning: _mutate_row: task {task_key!r} not in YAML at write time "
            f"(skipping status flip; YAML may have been edited mid-run)\n"
        )
        return False


def _mark_in_progress(cfg: RunConfig, snap: TaskSnapshot, run_dir: Path) -> None:
    summary_path = run_dir / snap.key / "summary.md"

    def _apply(row):
        row["status"] = plan_mod.IN_PROGRESS
        row["started_at"] = _now_iso()
        row["dispatcher_run_id"] = cfg.run_id
        row["summary_path"] = str(summary_path)

    _mutate_row(cfg, snap.key, _apply)


def _mark_blocked(cfg: RunConfig, task_key: str, *, reason: str) -> None:
    summary_for_notify = {"summary": "", "summary_path": None}

    def _apply(row):
        row["status"] = plan_mod.BLOCKED
        row["completed_at"] = _now_iso()
        row["blocked_reason"] = reason
        # Agent/version provenance (OPS-4) — same stamp as _run_task's
        # terminal row, so every terminal row carries it.
        row.update(_agent_meta(cfg))
        # Capture for the post-write notification.
        summary_for_notify["summary"] = str(row.get("summary") or "")
        sp = row.get("summary_path")
        if sp:
            summary_for_notify["summary_path"] = str(sp)

    _mutate_row(cfg, task_key, _apply)
    # Terminal journal event for the early-return Blocked paths (spawn
    # failure, summary missing/malformed, commit-retry exhaustion,
    # worker exception). Disjoint from the in-worker Blocked task_blocked
    # in _run_task, so exactly one terminal event fires per task.
    _emit_event(cfg, journal_mod.EventType.task_blocked,
                {"reason": reason, **_agent_meta(cfg)}, task_key=task_key)
    # Best-effort notification + notify_sent journal event. Failures are
    # swallowed — never let a flaky webhook (or a journal write) break the
    # dispatch loop.
    _send_notification(cfg, notify_mod.task_blocked_notification(
        task_key=task_key,
        summary=summary_for_notify["summary"],
        reason=reason,
        run_id=cfg.run_id,
        summary_path=summary_for_notify["summary_path"],
        tasks_yaml=str(cfg.tasks_path),
    ), task_key=task_key)


# --- misc helpers -----------------------------------------------------------


def _agent_meta(cfg: RunConfig) -> dict[str, Any]:
    """Agent/version provenance stamped on every terminal row + terminal
    journal event (OPS-4). `agent_version` is OMITTED (not None) when the
    once-per-run capture failed — degrade-to-absent, never write null."""
    meta: dict[str, Any] = {
        "agent": spawn_mod.AGENT_NAME,
        "dispatcher_version": __version__,
    }
    if cfg.agent_version:
        meta["agent_version"] = cfg.agent_version
    return meta


def _build_config(args: argparse.Namespace) -> RunConfig:
    extra = getattr(args, "claude_extra_args", "") or ""
    # CLI base_branch wins if explicitly set; else fall back to "main" here
    # and let execute() check the YAML's top-level before final resolution.
    cli_base = getattr(args, "base_branch", None)
    return RunConfig(
        tasks_path=Path(args.tasks_yaml).resolve(),
        runs_dir=Path(args.runs_dir).resolve(),
        run_id=args.run_id or _default_run_id(Path(args.tasks_yaml)),
        mode=args.mode,
        max_parallel=args.max_parallel,
        max_iterations=args.max_iterations,
        reviewer_count=args.reviewer_count,
        skip_design=args.skip_design,
        skip_security_linter=args.skip_security_linter,
        financial_paths=args.financial_paths,
        claude_bin=args.claude_bin,
        worktree_base=Path(args.worktree_base) if args.worktree_base else None,
        label_filter=plan_mod.parse_label_filter(args.filter_spec),
        only_keys=_split_keys(args.only_keys),
        gh_bin=getattr(args, "gh_bin", "gh"),
        claude_extra_args=extra.split() if extra else [],
        base_branch=cli_base if cli_base else "main",
        # Integration mode (PRF-1). A fresh CLI run carries the raw --integration
        # (None when unset); execute() re-resolves it against .dispatcher.yaml
        # and stamps the final value here. A resumed run's namespace comes from
        # the genesis, where these are already the resolved values (and
        # base_branch is already the feature branch), so resume needs no
        # re-resolution — hence the plain getattr with the production defaults.
        integration=getattr(args, "integration", None) or "branch",
        feature_branch=getattr(args, "feature_branch", None),
        feature_branch_sha=getattr(args, "feature_branch_sha", None),
        feature_branch_status=getattr(args, "feature_branch_status", None),
        lock_timeout_seconds=getattr(args, "lock_timeout_seconds", 30.0),
        task_timeout_seconds=getattr(args, "task_timeout_seconds", 60 * 60 * 4),
        # getattr default keeps `dispatcher resume` of pre-gate journals
        # working — their genesis run_config lacks the key.
        verify_test_timeout_seconds=getattr(args, "verify_test_timeout", 600),
        # getattr defaults keep `dispatcher resume` of pre-VG-4 journals
        # working — their genesis run_config lacks these keys.
        max_verify_iterations=getattr(args, "max_verify_iterations", 2),
        skip_verification=getattr(args, "skip_verification", False),
        auto_integrate=getattr(args, "auto_integrate", False),
        cross_family_panel=getattr(args, "cross_family_panel", "auto"),
        cross_family_panel_timeout=getattr(
            args, "cross_family_panel_timeout",
            cfr_mod.DEFAULT_REVIEWER_TIMEOUT_SECONDS,
        ),
        cross_family_panel_iterate=getattr(
            args, "cross_family_panel_iterate", 0,
        ),
        haiku_summary=getattr(args, "haiku_summary", False),
        feature_review=getattr(args, "feature_review", False),
        feature_review_rounds=getattr(args, "feature_review_rounds", 3),
        # getattr default keeps `dispatcher resume` of pre-BUDGET journals
        # working — their genesis run_config lacks the key. cost_baseline_usd is
        # set by execute() for a fresh run; on resume it comes from the genesis.
        max_cost_usd=getattr(args, "max_cost_usd", None),
        cost_baseline_usd=getattr(args, "cost_baseline_usd", 0.0),
        notifier=notify_mod.build_notifier_from_env(
            cli_ntfy_topic=getattr(args, "ntfy_topic", None),
            cli_ntfy_server=getattr(args, "ntfy_server", None),
            cli_slack_webhook=getattr(args, "slack_webhook_url", None),
        ),
    )


def _split_keys(only_arg: str | None) -> list[str] | None:
    if not only_arg:
        return None
    return [k.strip() for k in only_arg.split(",") if k.strip()]


def _default_run_id(tasks_path: Path) -> str:
    ts = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    return f"{ts}-{tasks_path.stem}"


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")


def _log(log_path: Path, message: str) -> None:
    """Thread-safe append to run.log. POSIX append-atomicity covers single
    syscalls under PIPE_BUF, but a per-process lock guards multi-write lines."""
    ts = _now_iso()
    with _log_lock:
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(f"{ts}  {message}\n")


# --- event journal helpers --------------------------------------------------


def _open_journal(
    cfg: RunConfig, run_dir: Path, repo_root: Path, log_path: Path,
    *, run_config: dict[str, Any] | None = None,
) -> journal_mod.Journal | None:
    """Create this run's event journal, or return None on failure.

    Journaling is a control-surface convenience, NOT a precondition for the
    run: if the genesis write fails for any reason (unwritable runs dir,
    hashing error, …) we warn to stderr + run.log and return None so the
    dispatch loop proceeds journal-less. Every later emit is a no-op when
    the journal is None. Mirrors the notifier's best-effort policy.

    ``run_config`` is the resolved run arguments embedded in the genesis so
    `dispatcher resume` can replay this run from the journal alone.
    """
    journal_path = run_dir / journal_mod.JOURNAL_FILENAME
    reviewer_prompts_dir = getattr(
        cfr_mod, "_PROMPTS_DIR",
        Path(journal_mod.__file__).parent / "reviewer_prompts",
    )
    try:
        j = journal_mod.Journal.create(
            journal_path,
            tasks_yaml_path=cfg.tasks_path,
            reviewer_prompts_dir=reviewer_prompts_dir,
            run_id=cfg.run_id,
            run_config=run_config,
        )
        _log(log_path, f"event journal at {journal_path}")
        return j
    except Exception as e:
        msg = f"journal creation failed ({journal_path}): {e} — running journal-less"
        _log(log_path, msg)
        sys.stderr.write(f"warning: {msg}\n")
        return None


def _heartbeat_loop(cfg: RunConfig, stop: threading.Event) -> None:
    """Append a ``heartbeat`` event every HEARTBEAT_INTERVAL_SECONDS until
    ``stop`` is set. Runs on a daemon thread; goes through ``_emit_event`` so
    a journal-less run (cfg.journal is None) is a no-op and an append failure
    is swallowed — a flaky filesystem must never take down the run."""
    while not stop.wait(HEARTBEAT_INTERVAL_SECONDS):
        _emit_event(cfg, journal_mod.EventType.heartbeat)


# Run arguments that must NOT be persisted into the genesis. The journal is a
# long-lived, hash-covered on-disk artifact; once an event is chained its bytes
# cannot be redacted without breaking verification. The notifier credentials are
# secrets (the webhook URL / ntfy topic IS the secret — see the CLI help), so
# embedding them in run_config would leak them at rest. They are intentionally
# omitted: a resumed run rebuilds its notifier from the environment via
# build_notifier_from_env(), so the only behavioral difference is that a secret
# passed on argv (which the CLI help already discourages) is not replayed.
_GENESIS_CONFIG_SECRET_KEYS = frozenset(
    {"slack_webhook_url", "ntfy_topic", "ntfy_server"}
)


def _genesis_config(args: argparse.Namespace, cfg: RunConfig) -> dict[str, Any]:
    """Serialize the run's arguments for the genesis ``run_config`` payload.

    Captures every ``dispatcher run`` argument verbatim (all JSON-safe:
    str/int/bool/None) minus the non-serializable ``func`` callable and the
    notifier secrets in :data:`_GENESIS_CONFIG_SECRET_KEYS` (never persist a
    secret into the hash-covered journal), then overrides ``base_branch`` /
    ``run_id`` with the values resolved at run time (the YAML's top-level
    base_branch and the default run-id are resolved after argument parsing) so
    a resume forks from the same branch and reuses the same run directory.
    ``tasks_yaml`` is normalised to the resolved absolute path so resume
    locates it regardless of its own working directory.
    """
    d = {
        k: v for k, v in vars(args).items()
        if k != "func" and k not in _GENESIS_CONFIG_SECRET_KEYS
    }
    d["base_branch"] = cfg.base_branch
    d["run_id"] = cfg.run_id
    d["tasks_yaml"] = str(cfg.tasks_path)
    # Integration mode + feature branch (PRF-1). base_branch above is already
    # the EFFECTIVE base — repointed to the feature branch in pr mode — so a
    # resume forks from the feature branch with no re-resolution. These extra
    # keys carry the mode, the feature branch name, its run-start tip SHA, and
    # whether it was created or reused this run.
    d["integration"] = cfg.integration
    d["feature_branch"] = cfg.feature_branch
    d["feature_branch_sha"] = cfg.feature_branch_sha
    d["feature_branch_status"] = cfg.feature_branch_status
    # Budget baseline (BUDGET-1), resolved at run start — persisted so a resume
    # reuses it instead of recomputing from rows this run has since written.
    d["cost_baseline_usd"] = cfg.cost_baseline_usd
    return d


def _setup_integration(
    cfg: RunConfig,
    doc: Any,
    repo_root: Path,
    args: argparse.Namespace,
    log_path: Path,
) -> str | None:
    """Resolve the integration mode and, in pr mode, stand up the feature branch.

    Precedence for the mode: the ``--integration`` CLI flag wins; else the
    repo's ``.dispatcher.yaml`` ``integration:`` key; else ``"branch"``. A
    malformed ``.dispatcher.yaml`` is NOT fatal here — the mechanical gate
    surfaces it per-worktree later — so a load error is logged and treated as
    "no repo default".

    In pr mode the feature branch name is ``--feature-branch`` when given,
    else ``feature/<epic>`` derived from the tasks YAML's top-level ``epic:``.
    The branch is created from ``cfg.base_branch`` if absent (else reused), and
    ``cfg.base_branch`` is then repointed to it so every downstream site that
    forks worktrees / checks dependency reachability / computes diff baselines
    uses the feature branch as its base.

    Mutates ``cfg`` in place. Returns None on success, or an error string when
    pr mode is requested but no feature branch can be derived (no
    ``--feature-branch`` and no epic) or the branch cannot be created.
    """
    cli_mode = getattr(args, "integration", None)
    repo_mode: str | None = None
    try:
        repo_mode = repo_config_mod.load(repo_root).integration
    except repo_config_mod.RepoConfigError as e:
        # A malformed .dispatcher.yaml is surfaced per-worktree by the
        # mechanical gate later, so it is not fatal at run start — but if the
        # repo was relying on its `integration:` default, suppressing it
        # silently downgrades the run to branch mode. Warn to stderr (not just
        # run.log) so an operator notices the downgrade now, and only when no
        # CLI flag is overriding the repo default anyway.
        msg = (f"integration: could not read .dispatcher.yaml for the mode "
               f"default ({e}); proceeding in {cli_mode or 'branch'} mode")
        _log(log_path, msg)
        if cli_mode is None:
            sys.stderr.write(f"warning: {msg}\n")
        repo_mode = None
    cfg.integration = cli_mode or repo_mode or "branch"

    if cfg.integration != "pr":
        cfg.feature_branch = None
        cfg.feature_branch_sha = None
        cfg.feature_branch_status = None
        return None

    feature_branch = (getattr(args, "feature_branch", None) or "").strip()
    if not feature_branch:
        epic = doc.get("epic") if isinstance(doc, dict) else None
        feature_branch = wt_mod.default_feature_branch(epic)
        if not feature_branch:
            return (
                "integration: pr mode needs a feature branch, but the tasks "
                "YAML has no top-level `epic:` and no --feature-branch was "
                "given"
            )

    try:
        result = wt_mod.ensure_feature_branch(
            repo_root, feature_branch, cfg.base_branch,
        )
    except wt_mod.WorktreeError as e:
        detail = f"{e}" + (f": {e.stderr}" if e.stderr else "")
        return f"integration: could not ensure feature branch: {detail}"

    cfg.feature_branch = result.branch
    cfg.feature_branch_sha = result.sha
    cfg.feature_branch_status = result.status
    _log(log_path,
         f"integration=pr feature_branch={result.branch} ({result.status}) "
         f"sha={result.sha[:8]} forked_from={cfg.base_branch}")
    # The feature branch is every task PR's `--base`, so it MUST exist on the
    # remote before the first PR is raised. ensure_feature_branch only creates
    # the LOCAL ref; without pushing it here `gh pr create --base <feature>`
    # fails with "Base ref must be a branch" and EVERY task false-blocks with
    # pr_open_failed even though its work and branch are fine (dogfood
    # 2026-06-15). Push covers both the freshly-forked ("created") branch and an
    # "existing" local-only branch; it is a no-op when the branch is already in
    # sync on origin. A local-only repo (no remote — e.g. tests) skips. A real
    # push failure aborts setup (return != None → exit 2) rather than letting
    # the run proceed to false-block every task on an unreachable base.
    pv = pv_mod.verify(
        repo_root=repo_root, branch=result.branch, expect_pr=False,
        gh_bin=cfg.gh_bin, log=lambda m: _log(log_path, m),
    )
    if pv.status == "skipped-no-remote":
        _log(log_path,
             "integration: no remote configured; skipping feature-branch push")
    else:
        pushed, detail = _push_branch(
            repo_root, result.branch, log_path, "integration")
        if not pushed:
            return (
                f"integration: could not push feature branch {result.branch!r} "
                f"to origin; PR creation would false-block every task: {detail}"
            )
        _log(log_path, f"integration: pushed {result.branch} to origin")
    # Repoint the effective base. Every worktree-create, dependency-merge
    # reachability check, and diff baseline reads cfg.base_branch, so this one
    # assignment makes the whole run fork from the feature branch.
    cfg.base_branch = result.branch
    return None


def _emit_event(
    cfg: RunConfig,
    event_type: journal_mod.EventType,
    payload: dict[str, Any] | None = None,
    *,
    task_key: str | None = None,
) -> None:
    """Append one event to the run journal, best-effort.

    A journal write must NEVER crash a run — on any failure we warn to
    stderr and continue (mirroring the notifier policy). A no-op when
    journaling is disabled (cfg.journal is None). Thread-safe: Journal.append
    serializes concurrent worker appends behind its own lock.
    """
    j = cfg.journal
    if j is None:
        return
    try:
        j.append(event_type, payload or {}, task_key=task_key)
    except Exception as e:
        et = getattr(event_type, "value", event_type)
        sys.stderr.write(
            f"warning: journal append failed for {et!r}"
            + (f" (task {task_key})" if task_key else "")
            + f": {e}\n"
        )


def _send_notification(
    cfg: RunConfig, notification: notify_mod.Notification, *, task_key: str | None = None,
) -> bool:
    """Send a notification and journal a notify_sent event — both best-effort.

    Neither a flaky webhook nor a journal write may break the dispatch loop,
    so both calls are guarded. Returns whether the channel reported delivery.
    The notify_sent event records the delivery outcome so the journal shows
    not just that we tried to notify, but whether it landed.
    """
    delivered = False
    try:
        delivered = bool(cfg.notifier.send(notification))
    except Exception:
        # Defensive: Notifier.send is contractually non-raising, but a buggy
        # channel must not convert a notification into a dispatcher crash.
        pass
    _emit_event(cfg, journal_mod.EventType.notify_sent, {
        "title": notification.title,
        "urgency": notification.urgency,
        "tags": list(notification.tags),
        "delivered": delivered,
    }, task_key=task_key)
    return delivered


def _task_started_payload(
    snap: TaskSnapshot,
    merge_result: "wt_mod.DependencyMergeResult | None" = None,
) -> dict[str, Any]:
    """Build the task_started payload: task metadata + the dispatch-time
    dependency-merge outcome (INT-4).

    ``merged_dependencies`` carries each merged dependency's branch + tip SHA
    so an auditor can reconstruct exactly which dependency commits this task
    was built on. ``dependencies_already_on_base`` / ``dependencies_unresolved``
    record the no-op and unresolved deps. On a failed merge, a key named
    after the failure label — ``dependency_merge_conflict`` for a genuine
    content conflict (so existing journal readers are unaffected),
    ``dependency_merge_failure`` for any other merge failure — carries the
    offending dependency + detail. Fields beyond the base metadata are
    omitted when empty/absent (e.g. a worktree-create failure passes
    ``merge_result=None``).
    """
    payload: dict[str, Any] = {
        "summary": snap.summary,
        "type": snap.type,
        "labels": list(snap.labels),
        "model": snap.model,
    }
    if merge_result is not None:
        payload["merged_dependencies"] = [
            {"key": m.key, "branch": m.branch, "sha": m.sha}
            for m in merge_result.merged
        ]
        if merge_result.already_on_base:
            payload["dependencies_already_on_base"] = list(merge_result.already_on_base)
        if merge_result.unresolved:
            payload["dependencies_unresolved"] = list(merge_result.unresolved)
        if merge_result.conflict is not None:
            c = merge_result.conflict
            payload[c.reason] = {
                "key": c.key, "branch": c.branch, "detail": c.detail[:300],
            }
    return payload


def _log_transcript_and_haiku(
    cfg: RunConfig, snap: TaskSnapshot, result: spawn_mod.SpawnResult,
    out_dir: Path, log_path: Path,
) -> None:
    """Step 6: persist the agent's captured output as a transcript log + a cheap
    haiku summary, reference both from the YAML row, and journal it. Best-effort:
    any failure is logged and swallowed — this is an audit nicety and must never
    block or fail a task. (The captured output is the agent's stdout — the JSON
    envelope for claude, fuller stdout for cross-family agents; a richer
    turn-by-turn transcript is a future enhancement.)"""
    try:
        transcript = out_dir / "transcript.json"
        transcript.write_text(result.stdout or "", encoding="utf-8")
        haiku = spawn_mod.summarize_transcript_haiku(
            result.stdout or "", claude_bin=cfg.claude_bin)
        haiku_path = out_dir / "summary-haiku.md"
        if haiku:
            haiku_path.write_text(haiku, encoding="utf-8")
        refs = {"transcript_log": str(transcript)}
        if haiku:
            refs["haiku_summary"] = str(haiku_path)
        _mutate_row(cfg, snap.key, lambda r: r.update(refs))
        _emit_event(cfg, journal_mod.EventType.transcript_logged, {
            "transcript_log": str(transcript),
            "haiku_summary": str(haiku_path) if haiku else None,
            "haiku_chars": len(haiku) if haiku else 0,
        }, task_key=snap.key)
    except Exception as e:  # noqa: BLE001 — audit nicety, never fatal
        _log(log_path, f"  {snap.key} transcript/haiku log failed (non-fatal): {e}")


def _spawn_usage_payload(result: spawn_mod.SpawnResult) -> dict[str, Any]:
    """Build the task_spawn_finished payload: exit code + per-task usage/cost.

    Every usage field is optional — None when the Claude CLI didn't emit a
    JSON usage block — and is carried through as-is (the journal records the
    absence as faithfully as a value)."""
    u = result.usage
    return {
        "exit_code": result.exit_code,
        "cost_usd": u.cost_usd,
        "input_tokens": u.input_tokens,
        "output_tokens": u.output_tokens,
        "cache_read_input_tokens": u.cache_read_input_tokens,
        "cache_creation_input_tokens": u.cache_creation_input_tokens,
        "duration_ms": u.duration_ms,
        "num_turns": u.num_turns,
        "model": u.model,
    }


def _summary_parsed_payload(s: summary_mod.Summary) -> dict[str, Any]:
    """Build the summary_parsed payload. On a malformed parse the discovered
    reasons ride along in `problems` (DISP-3) so a journal reader sees *why*
    the summary was rejected, not merely that it was."""
    return {
        "status": s.status,
        "malformed": bool(s.malformed),
        "problems": list(s.problems),
        "iterations": s.iterations,
        "linter_cycles": s.linter_cycles,
        "final_quality_score": s.final_quality_score,
        "awaiting_human_approval": bool(s.awaiting_human_approval),
    }


def _panel_verdict_payload(panel: cfr_mod.PanelVerdict) -> dict[str, Any]:
    """Build the panel_verdict payload: the consensus gate, its summary, and
    each family's verdict. On a block the blocking findings' locations ride
    along so the reason is reconstructable from the journal alone.

    `advisory_verdicts` is always present ({} when no advisory reviewer
    ran) — the scorecard groundwork for the probationary tier (VG-5). It
    never feeds the consensus."""
    return {
        "consensus": panel.consensus,
        "summary": panel.summary,
        "blocking_findings": len(panel.blocking_findings),
        "verdicts": {r.family: r.verdict.value for r in panel.reviewers},
        "blocking_locations": [
            f.location for f in panel.blocking_findings if f.location
        ],
        "advisory_verdicts": {
            r.family: r.verdict.value for r in panel.advisory
        },
    }


def _log_summary_problems(log_path: Path, task_key: str, s: summary_mod.Summary) -> None:
    """Write each parse problem the summary recorded to the run log, one per line."""
    for problem in s.problems:
        _log(log_path, f"  {task_key} summary problem: {problem}")


def _summary_problem_detail(s: summary_mod.Summary) -> str:
    """The human-readable detail appended to a summary_malformed Blocked reason.

    Prefers the explicit per-problem list; falls back to malformed_reason for
    any legacy path that flagged malformed without recording a problem.
    """
    if s.problems:
        return "; ".join(s.problems)
    return s.malformed_reason or "no reason recorded"


def _load_tasks_snapshot(cfg: RunConfig) -> list[plan_mod.Task]:
    """Acquire the lock, load the YAML, parse into Task list, release.

    The Task objects' .raw fields point at the loaded doc — when the next
    snapshot is taken, the previous doc is garbage-collected. No mutation
    of .raw happens from main-thread code paths.
    """
    with yaml_io.FileLock(cfg.tasks_path, timeout_seconds=cfg.lock_timeout_seconds):
        doc = yaml_io.load(cfg.tasks_path)
    return plan_mod.load_tasks(doc)


def _resolve_dependency_branches(
    cfg: RunConfig, blocked_by: list[str],
) -> list[tuple[str, str]]:
    """Resolve each blockedBy key to a ``(key, branch)`` pair, in blockedBy
    order (INT-4).

    The branch is read from the dependency's YAML row ``branch`` field
    (stamped when that task was dispatched); if absent, it is recomputed
    deterministically from the dependency's type + summary via
    ``branch_name()`` — the same function that produced it. Keys with no
    matching row are dropped (a validated YAML can't reference unknown keys,
    but the snapshot is taken under lock and may differ from validation time).
    """
    if not blocked_by:
        return []
    tasks = _load_tasks_snapshot(cfg)
    by_key = {t.key: t for t in tasks}
    out: list[tuple[str, str]] = []
    for dep_key in blocked_by:
        dep = by_key.get(dep_key)
        if dep is None:
            continue
        branch = None
        raw = getattr(dep, "raw", None)
        if isinstance(raw, dict):
            raw_branch = raw.get("branch")
            if raw_branch:
                branch = str(raw_branch)
        if not branch:
            branch = wt_mod.branch_name(dep.type, dep.key, dep.summary)
        out.append((dep_key, branch))
    return out


def _format_pr_gate_prompt(snap: TaskSnapshot, s: summary_mod.Summary) -> str:
    """Render the human-readable gate prompt with the prepared PR metadata."""
    lines = [
        "",
        "=" * 72,
        f"Human PR gate fired for {snap.key}: {snap.summary}",
        "=" * 72,
        f"  Title:  {s.prepared_pr_title}",
        f"  Branch: {s.prepared_pr_branch}",
        "",
        "  Body preview (first 30 lines):",
    ]
    for line in (s.prepared_pr_body or "").splitlines()[:30]:
        lines.append(f"    {line}")
    lines.append("=" * 72)
    return "\n".join(lines)
