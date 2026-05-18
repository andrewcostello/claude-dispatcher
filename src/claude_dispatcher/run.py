"""`dispatcher run` — load a tasks YAML, plan, and dispatch.

Modes:
  dry-run    Print the dispatch plan and exit. No worktrees, no subprocesses.
  supervised Run tasks; pause for the human on each gate trip. (Step 6.)
  unattended Run tasks; on any gate trip, mark Blocked and move on. (Step 6.)

This file is the orchestrator. It delegates per-task subprocess spawning to
spawn.py and worktree creation to worktree.py once those land. For now,
only the dry-run path is wired.
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import sys
from pathlib import Path
from typing import Any

from . import plan as plan_mod
from . import yaml_io
from . import dispatch_plan
from . import orchestrator


def execute(args: argparse.Namespace) -> int:
    """Entry point invoked by cli.main()."""
    tasks_path = Path(args.tasks_yaml).resolve()
    if not tasks_path.exists():
        print(f"error: tasks YAML not found: {tasks_path}", file=sys.stderr)
        return 2

    doc = yaml_io.load(tasks_path)
    try:
        tasks = plan_mod.load_tasks(doc)
    except plan_mod.ValidationError as e:
        print(f"error: invalid tasks YAML: {e}", file=sys.stderr)
        return 2

    try:
        label_filter = plan_mod.parse_label_filter(args.filter_spec)
    except plan_mod.ValidationError as e:
        print(f"error: bad --filter: {e}", file=sys.stderr)
        return 2

    only = (
        [k.strip() for k in args.only_keys.split(",") if k.strip()]
        if args.only_keys
        else None
    )

    selected = plan_mod.filter_tasks(tasks, label_filter, only)

    if args.mode == "dry-run":
        return _dry_run(args, tasks, selected, tasks_path)

    return orchestrator.execute(args)


def _dry_run(
    args: argparse.Namespace,
    all_tasks: list[plan_mod.Task],
    selected: list[plan_mod.Task],
    tasks_path: Path,
) -> int:
    """Print a human-readable dispatch plan and exit cleanly.

    The plan respects --filter and --only, but the wave graph reflects the
    full task list (dependencies don't disappear because you filtered) — the
    output flags which selected tasks are runnable now vs. waiting on a
    filtered-out dependency.
    """
    waves = plan_mod.plan_waves(all_tasks)
    runnable_first = plan_mod.runnable_now(all_tasks)

    selected_keys = {t.key for t in selected}
    runnable_keys = {t.key for t in runnable_first}

    print(dispatch_plan.render(
        tasks_path=tasks_path,
        run_id=args.run_id or _default_run_id(tasks_path),
        mode=args.mode,
        max_parallel=args.max_parallel,
        max_iterations=args.max_iterations,
        reviewer_count=args.reviewer_count,
        skip_design=args.skip_design,
        skip_security_linter=args.skip_security_linter,
        financial_paths=args.financial_paths,
        filter_spec=args.filter_spec,
        only_keys=only_or_none(args.only_keys),
        all_tasks=all_tasks,
        selected_keys=selected_keys,
        runnable_keys=runnable_keys,
        waves=waves,
        unreachable=plan_mod.unreachable(all_tasks, waves),
    ))
    return 0


def only_or_none(only_arg: str | None) -> list[str] | None:
    if not only_arg:
        return None
    return [k.strip() for k in only_arg.split(",") if k.strip()]


def _default_run_id(tasks_path: Path) -> str:
    """ISO timestamp prefix + a short identifier from the YAML filename."""
    ts = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    return f"{ts}-{tasks_path.stem}"
