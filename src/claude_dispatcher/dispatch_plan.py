"""Render the dispatch plan for `dispatcher run --mode dry-run`.

Produces a deterministic text report describing:
  - what would be dispatched and in what wave order
  - which tasks are dependency-blocked (and on what)
  - which tasks would be skipped (filter / only)
  - which tasks are unreachable (depend on Blocked or Escalated work)
  - estimated parallelism

Pure function — no I/O, no side effects. Tests can call render() with
fabricated inputs.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from . import plan as plan_mod


def render(
    *,
    tasks_path: Path,
    run_id: str,
    mode: str,
    max_parallel: int,
    max_iterations: int,
    reviewer_count: int | None,
    skip_design: bool,
    skip_security_linter: bool,
    financial_paths: str,
    filter_spec: str | None,
    only_keys: list[str] | None,
    all_tasks: list[plan_mod.Task],
    selected_keys: set[str],
    runnable_keys: set[str],
    waves: list[plan_mod.Wave],
    unreachable: list[plan_mod.Task],
) -> str:
    """Return the multi-line dispatch plan as a string."""
    lines: list[str] = []
    lines.append("=" * 78)
    lines.append(f"Dispatcher plan — {mode} mode")
    lines.append(f"  Tasks YAML:     {tasks_path}")
    lines.append(f"  Run ID:         {run_id}")
    lines.append(f"  Max parallel:   {max_parallel}")
    lines.append(f"  Max iterations: {max_iterations}")
    if reviewer_count is not None:
        lines.append(f"  Reviewer count: {reviewer_count} (override)")
    if skip_design:
        lines.append("  --skip-design:        on")
    if skip_security_linter:
        lines.append("  --skip-security-linter: on")
    lines.append(f"  Financial paths: {financial_paths}")
    if filter_spec:
        lines.append(f"  --filter:        {filter_spec}")
    if only_keys:
        lines.append(f"  --only:          {','.join(only_keys)}")
    lines.append("=" * 78)
    lines.append("")

    # --- summary table -----------------------------------------------------
    total = len(all_tasks)
    by_status: dict[str, int] = {}
    for t in all_tasks:
        by_status[t.status] = by_status.get(t.status, 0) + 1
    lines.append(f"Total tasks in file: {total}")
    for status in sorted(by_status):
        lines.append(f"  {status}: {by_status[status]}")
    lines.append("")

    # --- selection breakdown ----------------------------------------------
    selected = [t for t in all_tasks if t.key in selected_keys]
    skipped_by_filter = [t for t in all_tasks if t.key not in selected_keys]
    runnable_selected = [t for t in selected if t.key in runnable_keys]
    blocked_selected = [t for t in selected if t.key not in runnable_keys and t.status == plan_mod.TODO]

    lines.append(f"Selected by filter/only: {len(selected)}")
    lines.append(f"  Runnable now:           {len(runnable_selected)}")
    lines.append(f"  Waiting on dependency:  {len(blocked_selected)}")
    if skipped_by_filter:
        lines.append(f"Skipped by filter/only:  {len(skipped_by_filter)}")
    lines.append("")

    # --- waves -------------------------------------------------------------
    if not waves:
        lines.append("No runnable tasks — all selected tasks are either Done or Blocked.")
    else:
        max_width = plan_mod.parallelism_estimate(waves)
        lines.append(f"Dispatch waves (max parallelism: {max_width}):")
        lines.append("")
        for wave in waves:
            wave_selected = [t for t in wave.tasks if t.key in selected_keys]
            if not wave_selected:
                continue
            lines.append(f"  Wave {wave.index} — {len(wave_selected)} task(s):")
            for t in sorted(wave_selected, key=lambda x: x.key):
                size = t.size_label or "?"
                deps = f"  ⟵ {','.join(t.blocked_by)}" if t.blocked_by else ""
                lines.append(f"    {t.key:<12} size:{size:<3} {t.summary[:70]}{deps}")
            lines.append("")

    # --- unreachable -------------------------------------------------------
    unreach_selected = [t for t in unreachable if t.key in selected_keys]
    if unreach_selected:
        lines.append("Unreachable in this run (blocked by non-Done dependency):")
        for t in sorted(unreach_selected, key=lambda x: x.key):
            blockers = ", ".join(t.blocked_by)
            lines.append(f"  {t.key}  ⟵ {blockers}")
        lines.append("")

    # --- env handoff preview ----------------------------------------------
    if runnable_selected:
        lines.append("Per-task env vars handed to Tasker:")
        lines.append(f"  DISPATCHER_RUN_ID={run_id}")
        lines.append(f"  TASK_KEY=<task-key>")
        lines.append(f"  SUMMARY_PATH=<runs-dir>/{run_id}/<task-key>/summary.md")
        lines.append(f"  MAX_ITERATIONS={max_iterations}")
        if reviewer_count is not None:
            lines.append(f"  REVIEWER_COUNT={reviewer_count}")
        if skip_design:
            lines.append("  SKIP_DESIGN=1")
        if skip_security_linter:
            lines.append("  SKIP_SECURITY_LINTER=1")
        lines.append(f"  FINANCIAL_PATHS={financial_paths}")
        lines.append("")

    lines.append("Dry-run only: no worktrees created, no subprocesses spawned, "
                 "no YAML writes.")
    return "\n".join(lines) + "\n"
