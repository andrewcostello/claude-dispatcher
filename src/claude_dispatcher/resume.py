"""`dispatcher resume <run-id>` — pick up an interrupted run.

Reconstructs a run from its journal + tasks YAML and re-enters the dispatch
loop. The journal's `run_started` (genesis) event supplies the original run
configuration, so resume needs only the run-id (and `--runs-dir` to locate the
journal) — not the tasks-YAML path again.

Recovery rules:
  - **In Progress** rows whose run was interrupted are re-dispatched: under the
    default `continue` strategy they're reset to To Do so the dispatch loop
    re-spawns them (the worktree is reused if it still exists — `worktree.create`
    is idempotent). Under `--strategy mark-blocked` they're marked Blocked and
    left for a human.
  - **Done / Blocked / Escalated** rows are never touched.
  - A `resume_started` event is appended, linking back to the prior genesis.

Liveness guard: if the journal's most recent event is recent (younger than
RUN_ACTIVE_THRESHOLD_SECONDS), the original run may still be active — resuming
would double-dispatch. Resume refuses with exit 4 unless `--force` is given.
A run killed with `kill -9` leaves a stale journal (no further events), so the
guard does not impede genuine recovery; it only catches a still-live run.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import journal as journal_mod
from . import orchestrator
from . import plan as plan_mod
from . import yaml_io


# If the journal's last event is younger than this, treat the run as possibly
# still active and refuse to resume without --force. Comfortably above the
# orchestrator's heartbeat interval (a live run pings every 30s) so a real
# running dispatcher always trips the guard, while a killed one (no heartbeat)
# ages past it.
RUN_ACTIVE_THRESHOLD_SECONDS = 90


def execute(args: argparse.Namespace) -> int:
    runs_dir = Path(args.runs_dir).resolve()
    run_dir = runs_dir / args.run_id
    journal = journal_mod.Journal(run_dir / "journal.jsonl")

    if not journal.exists():
        print(
            f"error: no journal at {journal.path} — nothing to resume. "
            f"(Is the run-id correct? Check --runs-dir, default 'docs/runs'.)",
            file=sys.stderr,
        )
        return 2

    genesis = journal.genesis()
    if genesis is None:
        print(
            f"error: journal at {journal.path} has no run_started event — "
            f"cannot reconstruct the run configuration.",
            file=sys.stderr,
        )
        return 2

    config = genesis.get("config")
    if not isinstance(config, dict) or not config.get("tasks_yaml"):
        print(
            f"error: genesis event in {journal.path} is missing its config — "
            f"cannot reconstruct the run.",
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
    runnable = plan_mod.runnable_now(tasks)

    # Nothing left to do → clean no-op. A completed run has no In Progress
    # rows and no remaining runnable To Do rows.
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
    age = journal.seconds_since_last_event()
    if age is not None and age < RUN_ACTIVE_THRESHOLD_SECONDS and not args.force:
        print(
            f"error: run {args.run_id} looks still active — its last journal "
            f"event was {age:.0f}s ago (< {RUN_ACTIVE_THRESHOLD_SECONDS}s). "
            f"Resuming now could double-dispatch in-flight tasks. If you are "
            f"sure the original run is dead, re-run with --force.",
            file=sys.stderr,
        )
        return 4

    # Link this resume back to the prior genesis.
    journal.append(
        journal_mod.RESUME_STARTED,
        genesis_run_id=genesis.get("run_id"),
        genesis_ts=genesis.get("ts"),
        strategy=args.strategy,
        force=bool(args.force),
        in_progress=[t.key for t in in_progress],
    )

    # Recover interrupted In Progress rows per strategy.
    for t in in_progress:
        if args.strategy == "mark-blocked":
            _mark_blocked(tasks_path, t.key,
                          reason="resume: marked blocked per --strategy mark-blocked")
            journal.append(journal_mod.TASK_MARKED_BLOCKED, key=t.key)
            print(f"  {t.key}: In Progress → Blocked (--strategy mark-blocked)")
        else:  # continue
            _reset_to_todo(tasks_path, t.key)
            journal.append(journal_mod.TASK_RESET, key=t.key)
            print(f"  {t.key}: In Progress → To Do (will re-dispatch)")

    # Rebuild the run args from the genesis config and re-enter the loop.
    resumed_args = _namespace_from_config(config)
    print(f"Resuming run {args.run_id} ...")
    return orchestrator.resume_run(resumed_args, journal)


def _reset_to_todo(tasks_path: Path, key: str) -> None:
    """Reset an interrupted row to To Do so the dispatch loop re-spawns it.

    Clears the prior in-flight bookkeeping (started_at, summary_path,
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

    The genesis stored every run argument (with base_branch/run_id already
    resolved), so a faithful Namespace lets `orchestrator.resume_run` build the
    same RunConfig the original run used. The `func` callable was stripped at
    write time and isn't needed here.
    """
    return argparse.Namespace(**config)
