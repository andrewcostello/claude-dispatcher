"""`dispatcher resume <run-id>` — pick up an interrupted run.

Reconstructs a run from its journal + tasks YAML and re-enters the dispatch
loop. The journal's `run_started` (genesis) event embeds the original run
configuration under `run_config`, so resume needs only the run-id (and
`--runs-dir` to locate the journal) — not the tasks-YAML path again.

Recovery rules:
  - **In Progress** rows whose run was interrupted are re-dispatched: under the
    default `continue` strategy they're reset to To Do so the dispatch loop
    re-spawns them (the worktree is reused if it still exists — `worktree.create`
    is idempotent). Under `--strategy mark-blocked` they're marked Blocked and
    left for a human.
  - **Done / Blocked / Escalated** rows are never touched.
  - A `resume_started` event is appended, linking back to the prior genesis by
    its run-id and its chain hash.

Liveness guard: if the journal's most recent event is recent (younger than
RUN_ACTIVE_THRESHOLD_SECONDS), the original run may still be active — resuming
would double-dispatch. Resume refuses with exit 4 unless `--force`. A run killed
with `kill -9` stops heartbeating, so its journal ages past the threshold and
the guard does not impede genuine recovery; it only catches a still-live run
(the dispatch loop heartbeats every orchestrator.HEARTBEAT_INTERVAL_SECONDS).

This module reads and extends the *canonical* hash-chained journal
(`journal.py`): the genesis is read via `read_events`, and the `resume_started`
event is appended through `Journal.resume`, which first verifies the existing
chain — refusing to extend a journal that is already broken.

Exit codes: 0 (resumed cleanly / nothing to resume), 1 (resumed, some tasks
Blocked/Escalated — propagated from the dispatch loop), 2 (no journal / no
genesis / unusable config / broken chain), 4 (run looks still active; use
--force).
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

from . import journal as journal_mod
from . import orchestrator
from . import plan as plan_mod
from . import yaml_io


# If the journal's last event is younger than this, treat the run as possibly
# still active and refuse to resume without --force. Comfortably above the
# orchestrator's heartbeat interval (a live run pings every
# orchestrator.HEARTBEAT_INTERVAL_SECONDS) so a real running dispatcher always
# trips the guard, while a killed one (no heartbeat) ages past it.
RUN_ACTIVE_THRESHOLD_SECONDS = 90


def execute(args: argparse.Namespace) -> int:
    runs_dir = Path(args.runs_dir).resolve()
    run_dir = runs_dir / args.run_id
    journal_path = run_dir / journal_mod.JOURNAL_FILENAME

    if not journal_path.exists():
        print(
            f"error: no journal at {journal_path} — nothing to resume. "
            f"(Is the run-id correct? Check --runs-dir, default 'docs/runs'.)",
            file=sys.stderr,
        )
        return 2

    # Read the chain (parse only — Journal.resume below does the integrity
    # verify). A parse failure surfaces as a JournalError → treat as unusable.
    try:
        events = list(journal_mod.read_events(journal_path))
    except journal_mod.JournalError as e:
        print(f"error: cannot read journal at {journal_path}: {e}", file=sys.stderr)
        return 2

    genesis = events[0] if events else None
    if genesis is None or genesis.event_type != journal_mod.EventType.run_started.value:
        print(
            f"error: journal at {journal_path} has no run_started genesis event "
            f"— cannot reconstruct the run configuration.",
            file=sys.stderr,
        )
        return 2

    config = genesis.payload.get("run_config")
    if not isinstance(config, dict) or not config.get("tasks_yaml"):
        print(
            f"error: genesis event in {journal_path} is missing its run_config "
            f"— cannot reconstruct the run.",
            file=sys.stderr,
        )
        return 2

    tasks_path = Path(config["tasks_yaml"]).resolve()
    if not tasks_path.exists():
        print(f"error: tasks YAML not found: {tasks_path}", file=sys.stderr)
        return 2

    doc = yaml_io.load(tasks_path)
    try:
        tasks = plan_mod.load_tasks(doc)
    except plan_mod.ValidationError as e:
        print(f"error: invalid tasks YAML: {e}", file=sys.stderr)
        return 2

    in_progress = [t for t in tasks if t.status == plan_mod.IN_PROGRESS]
    # The genesis run_config carries the resolved integration mode; pass it so
    # the "already complete?" check uses pr-mode DISPATCH ordering (a To Do
    # task whose dependency is Awaiting Review IS runnable) — PRF-2. Defaults
    # to branch for pre-PRF journals.
    runnable = plan_mod.runnable_now(
        tasks, integration=str(config.get("integration") or "branch"),
    )

    # Nothing left to do → clean no-op. A completed run has no In Progress
    # rows and no remaining runnable To Do rows. Checked before the liveness
    # guard: a finished run is a no-op even if its last event is recent.
    if not in_progress and not runnable:
        done = sum(1 for t in tasks if t.status == plan_mod.DONE)
        blocked = sum(1 for t in tasks if t.status == plan_mod.BLOCKED)
        escalated = sum(1 for t in tasks if t.status == plan_mod.ESCALATED)
        print(
            f"Run {args.run_id} is already complete — nothing to resume "
            f"({done} done, {blocked} blocked, {escalated} escalated)."
        )
        return 0

    # Liveness guard. A recent last event suggests the original run is still
    # running; resuming would double-dispatch. --force overrides.
    age = _seconds_since_last_event(events)
    if age is not None and age < RUN_ACTIVE_THRESHOLD_SECONDS and not args.force:
        print(
            f"error: run {args.run_id} looks still active — its last journal "
            f"event was {age:.0f}s ago (< {RUN_ACTIVE_THRESHOLD_SECONDS}s). "
            f"Resuming now could double-dispatch in-flight tasks. If you are "
            f"sure the original run is dead, re-run with --force.",
            file=sys.stderr,
        )
        return 4

    # Open the existing chain for append. Journal.resume verifies integrity
    # first and refuses to extend an already-broken chain.
    try:
        journal = journal_mod.Journal.resume(journal_path)
    except journal_mod.JournalError as e:
        print(f"error: cannot resume journal at {journal_path}: {e}", file=sys.stderr)
        return 2

    # Reconcile the current tasks YAML against the content the genesis attested.
    # The YAML may have been legitimately edited between the crash and the
    # resume, so a mismatch is a warning, not a refusal — but it is recorded in
    # the resume_started event so the divergence is itself part of the audit
    # chain (the genesis still attests the original content).
    observed_hash = journal_mod.hash_file(tasks_path)
    genesis_hash_of_yaml = genesis.payload.get("tasks_yaml_hash")
    yaml_matches = observed_hash == genesis_hash_of_yaml
    if not yaml_matches:
        print(
            f"warning: tasks YAML at {tasks_path} has changed since the run "
            f"started (content hash differs from the genesis). Resuming against "
            f"the current file.",
            file=sys.stderr,
        )

    # Link this resume back to the prior genesis — by run-id and by the
    # genesis event's chain hash (a strong, tamper-evident pointer).
    journal.append(
        journal_mod.EventType.resume_started,
        {
            "genesis_run_id": genesis.payload.get("run_id"),
            "genesis_hash": genesis.hash,
            "genesis_ts": genesis.timestamp,
            "strategy": args.strategy,
            "force": bool(args.force),
            "in_progress": [t.key for t in in_progress],
            "tasks_yaml_hash": observed_hash,
            "tasks_yaml_hash_matches_genesis": yaml_matches,
        },
    )

    # Recover interrupted In Progress rows per strategy. The YAML mutation is
    # the durable, load-bearing state change; the per-row journal event is
    # forensic, so it is best-effort (a flaky FS appending the marker must not
    # leave the row un-recovered or abort the resume).
    for t in in_progress:
        if args.strategy == "mark-blocked":
            _mark_blocked(tasks_path, t.key,
                          reason="resume: marked blocked per --strategy mark-blocked")
            _try_append(journal, journal_mod.EventType.task_marked_blocked, t.key)
            print(f"  {t.key}: In Progress → Blocked (--strategy mark-blocked)")
        else:  # continue
            _reset_to_todo(tasks_path, t.key)
            _try_append(journal, journal_mod.EventType.task_reset, t.key)
            print(f"  {t.key}: In Progress → To Do (will re-dispatch)")

    # Rebuild the run args from the genesis config and re-enter the loop.
    resumed_args = _namespace_from_config(config)
    print(f"Resuming run {args.run_id} ...")
    return orchestrator.resume_run(resumed_args, journal)


def _try_append(journal: journal_mod.Journal, event_type, key: str) -> None:
    """Append a per-row resume marker, best-effort. A journal-append failure is
    forensic-only and must never abort a resume whose YAML mutation already
    landed; we warn to stderr and continue (mirrors orchestrator._emit_event)."""
    try:
        journal.append(event_type, {}, task_key=key)
    except Exception as e:  # pragma: no cover - defensive
        et = getattr(event_type, "value", event_type)
        print(f"warning: journal append failed for {et!r} (task {key}): {e}",
              file=sys.stderr)


def _seconds_since_last_event(events: list[journal_mod.JournalEvent]) -> float | None:
    """Age in seconds of the most recent event with a parseable timestamp, or
    None if there are no events / none carry a usable timestamp. This is the
    liveness signal the guard reads."""
    latest: dt.datetime | None = None
    for ev in events:
        ts = ev.timestamp
        if not ts:
            continue
        try:
            parsed = dt.datetime.fromisoformat(ts)
        except (TypeError, ValueError):
            continue
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        if latest is None or parsed > latest:
            latest = parsed
    if latest is None:
        return None
    now = dt.datetime.now(dt.timezone.utc)
    return (now - latest).total_seconds()


def _reset_to_todo(tasks_path: Path, key: str) -> None:
    """Reset an interrupted row to To Do so the dispatch loop re-spawns it.

    Clears the prior in-flight bookkeeping (started_at, completed_at,
    blocked_reason) so the re-dispatch starts clean. The branch is left in
    place — `worktree.create` reuses the existing worktree if present.
    """
    with yaml_io.FileLock(tasks_path):
        doc = yaml_io.load(tasks_path)
        for row in doc.get("tasks", []):
            if str(row.get("key")) == key:
                row["status"] = plan_mod.TODO
                for field in ("started_at", "completed_at", "blocked_reason"):
                    row.pop(field, None)
                yaml_io.dump(doc, tasks_path)
                return


def _mark_blocked(tasks_path: Path, key: str, *, reason: str) -> None:
    with yaml_io.FileLock(tasks_path):
        doc = yaml_io.load(tasks_path)
        for row in doc.get("tasks", []):
            if str(row.get("key")) == key:
                row["status"] = plan_mod.BLOCKED
                row["blocked_reason"] = reason
                yaml_io.dump(doc, tasks_path)
                return


def _namespace_from_config(config: dict) -> argparse.Namespace:
    """Rebuild the `dispatcher run` argparse.Namespace from a genesis config.

    The genesis stored every run argument (with base_branch/run_id/tasks_yaml
    already resolved), so a faithful Namespace lets `orchestrator.resume_run`
    build the same RunConfig the original run used. The `func` callable was
    stripped at write time and isn't needed here.
    """
    return argparse.Namespace(**config)
