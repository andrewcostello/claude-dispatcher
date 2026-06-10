"""`dispatcher status <run-id>` — current state of a run, as JSON or a table.

Reconstructs run state from the two artifacts the orchestrator already
maintains; there is no separate event-journal subsystem yet (that is a
distinct Phase 1 deliverable, see docs/improvement-plan.md "Event journal"):

  * **tasks YAML** — authoritative per-task run state. The orchestrator
    stamps `status`, `started_at`, `completed_at`, `dispatcher_run_id`,
    `model`, `cost_usd`, `iteration_count`, `blocked_reason`, `pr_url`,
    etc. onto each row as the run progresses (orchestrator._mark_* /
    _apply). This is the same source `dispatcher report` reads.
  * **run.log** — the append-only event log in the run directory, one
    timestamped line per event (`<iso-8601>  <message>`, written by
    orchestrator._log). Used here for run *liveness*: the age of the last
    event tells an observer whether a run is still moving or has stalled.

Read-only and mid-run-safe: never touches the YAML or worktrees, and
tolerates a partially-written final run.log line (a live run may be
appending to it as we read).

JSON schema (``--json``)
------------------------
A single object::

    {
      "run_id":       str,         # the run being reported on
      "tasks_yaml":   str,         # absolute path to the resolved tasks YAML
      "generated_at": str,         # ISO-8601, when this snapshot was taken
      "run_complete": bool,        # True iff every task is terminal
                                   #   (Done | Blocked | Escalated)
      "current_wave": int | null,  # 1-based index of the lowest dependency
                                   #   wave with a non-Done task still pending
                                   #   (To Do / In Progress); null when complete
      "wave_count":   int,         # number of dependency waves in the graph
      "liveness": {
        "run_log_present":        bool,
        "last_event_at":          str | null,    # ISO-8601 of last parseable line
        "last_event_age_seconds": float | null,  # generated_at - last_event_at
        "last_event":             str | null      # message text of that line
      },
      "totals": {
        "task_count":   int,
        "by_status":    { "<status>": int, ... },  # all five statuses, 0-filled
        "run_cost_usd": float | null,  # sum of per-task cost_usd; null if none
        "tasks_billed": int            # tasks that carry a cost_usd value
      },
      "tasks": [                   # every task in the YAML, key-sorted
        {
          "key":             str,
          "summary":         str,
          "status":          str,
          "wave":            int,          # 1-based dependency depth
          "started_at":      str | null,
          "completed_at":    str | null,
          "model":           str | null,   # agent model, once known
          "cost_usd":        float | null, # cost so far for this task
          "iteration_count": int | null,
          "blocked_reason":  str | null,
          "pr_url":          str | null,
          "dispatcher_run_id": str | null  # which run last touched this row
        },
        ...
      ]
    }

Without ``--json`` the same data is rendered as a human-readable table.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any

from . import plan as plan_mod
from . import report as report_mod
from . import yaml_io


# Ordered for stable rendering; every status is always present in by_status.
_STATUS_ORDER = (
    plan_mod.TODO,
    plan_mod.IN_PROGRESS,
    plan_mod.DONE,
    plan_mod.BLOCKED,
    plan_mod.ESCALATED,
)


def execute(args: argparse.Namespace) -> int:
    runs_dir = Path(args.runs_dir).resolve()
    run_id = str(args.run_id)
    run_dir = runs_dir / run_id
    if not run_dir.is_dir():
        print(f"error: run directory not found: {run_dir}", file=sys.stderr)
        return 2

    # Resolve the tasks YAML: explicit --tasks-yaml wins; otherwise reuse
    # report's walk-up discovery (find a summary.md, read its task_key, hunt
    # for the YAML containing it). A fresh run with no summaries yet can't be
    # auto-discovered — the user must pass --tasks-yaml in that case.
    yaml_arg = getattr(args, "tasks_yaml", None)
    if yaml_arg:
        yaml_path = Path(yaml_arg).resolve()
        if not yaml_path.exists():
            print(f"error: tasks YAML not found: {yaml_path}", file=sys.stderr)
            return 2
    else:
        discovered = report_mod._find_yaml_for_run(run_dir, runs_dir)
        if discovered is None:
            print(
                "error: could not determine which YAML this run is for "
                "(no summary.md to trace from yet). Pass --tasks-yaml.",
                file=sys.stderr,
            )
            return 2
        yaml_path = discovered

    status = build_status(
        run_dir=run_dir,
        run_id=run_id,
        yaml_path=yaml_path,
        now=_now(),
    )

    if getattr(args, "json", False):
        print(json.dumps(status, indent=2))
    else:
        print(render_table(status))
    return 0


def build_status(
    *,
    run_dir: Path,
    run_id: str,
    yaml_path: Path,
    now: dt.datetime,
) -> dict[str, Any]:
    """Pure status assembly — no I/O beyond the two reads below, no clock
    access (``now`` is injected so a snapshot test is deterministic).
    """
    doc = yaml_io.load(yaml_path)
    tasks = plan_mod.load_tasks(doc)

    by_key = {t.key: t for t in tasks}
    wave_memo: dict[str, int] = {}
    waves = {t.key: _wave_index(t, by_key, wave_memo) for t in tasks}

    task_entries: list[dict[str, Any]] = []
    by_status: dict[str, int] = {s: 0 for s in _STATUS_ORDER}
    cost_total = 0.0
    tasks_billed = 0

    for t in sorted(tasks, key=lambda x: x.key):
        row = t.raw
        status = t.status or plan_mod.TODO
        by_status[status] = by_status.get(status, 0) + 1

        cost = _num(row.get("cost_usd"))
        if cost is not None:
            cost_total += cost
            tasks_billed += 1

        task_entries.append({
            "key": t.key,
            "summary": t.summary,
            "status": status,
            "wave": waves[t.key],
            "started_at": _str_or_none(row.get("started_at")),
            "completed_at": _str_or_none(row.get("completed_at")),
            "model": _str_or_none(row.get("model")),
            "cost_usd": cost,
            "iteration_count": _int_or_none(row.get("iteration_count")),
            "blocked_reason": _str_or_none(row.get("blocked_reason")),
            "pr_url": _str_or_none(row.get("pr_url")),
            "dispatcher_run_id": _str_or_none(row.get("dispatcher_run_id")),
        })

    pending_waves = [
        waves[t.key] for t in tasks
        if (t.status or plan_mod.TODO) in (plan_mod.TODO, plan_mod.IN_PROGRESS)
    ]
    current_wave = min(pending_waves) if pending_waves else None
    run_complete = not pending_waves and bool(tasks)

    liveness = _liveness(run_dir / "run.log", now)

    return {
        "run_id": run_id,
        "tasks_yaml": str(yaml_path),
        "generated_at": now.isoformat(timespec="seconds"),
        "run_complete": run_complete,
        "current_wave": current_wave,
        "wave_count": max(waves.values(), default=0),
        "liveness": liveness,
        "totals": {
            "task_count": len(tasks),
            "by_status": by_status,
            "run_cost_usd": round(cost_total, 6) if tasks_billed else None,
            "tasks_billed": tasks_billed,
        },
        "tasks": task_entries,
    }


def _wave_index(
    task: plan_mod.Task,
    by_key: dict[str, plan_mod.Task],
    memo: dict[str, int],
) -> int:
    """1-based dependency depth: a task with no blockers is wave 1; otherwise
    one past the deepest blocker. The graph is already cycle-checked by
    plan_mod.load_tasks, so the recursion terminates.
    """
    if task.key in memo:
        return memo[task.key]
    if not task.blocked_by:
        memo[task.key] = 1
        return 1
    depth = 1 + max(
        _wave_index(by_key[dep], by_key, memo) for dep in task.blocked_by
    )
    memo[task.key] = depth
    return depth


def _liveness(run_log: Path, now: dt.datetime) -> dict[str, Any]:
    """Derive run liveness from the last parseable line of run.log.

    Each line is ``<iso-8601>  <message>``. We scan for the LAST line whose
    leading token parses as an ISO timestamp — this naturally skips a
    half-written final line on a live run (the partial-last-line case) as
    well as any blank lines.
    """
    base: dict[str, Any] = {
        "run_log_present": run_log.exists(),
        "last_event_at": None,
        "last_event_age_seconds": None,
        "last_event": None,
    }
    if not run_log.exists():
        return base

    try:
        text = run_log.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return base

    last_ts: dt.datetime | None = None
    last_msg: str | None = None
    for line in text.splitlines():
        ts_str, sep, msg = line.partition("  ")
        if not sep:
            continue
        try:
            parsed = dt.datetime.fromisoformat(ts_str.strip())
        except ValueError:
            continue
        last_ts = parsed
        last_msg = msg.strip()

    if last_ts is None:
        return base

    age = None
    if now is not None:
        # Both ends should be tz-aware (orchestrator stamps local-tz ISO,
        # _now() is tz-aware). Guard against a naive fixture timestamp.
        ref = now
        if last_ts.tzinfo is None and ref.tzinfo is not None:
            ref = ref.replace(tzinfo=None)
        elif last_ts.tzinfo is not None and ref.tzinfo is None:
            last_ts_cmp = last_ts.replace(tzinfo=None)
            last_ts = last_ts_cmp
        age = round((ref - last_ts).total_seconds(), 3)

    base["last_event_at"] = last_ts.isoformat(timespec="seconds")
    base["last_event_age_seconds"] = age
    base["last_event"] = last_msg
    return base


def render_table(status: dict[str, Any]) -> str:
    """Human-readable rendering of a build_status() result."""
    lines: list[str] = []
    lines.append("=" * 88)
    lines.append(f"Dispatcher status — {status['run_id']}")
    lines.append(f"  Tasks YAML:   {status['tasks_yaml']}")
    lines.append(f"  Generated at: {status['generated_at']}")
    complete = "yes" if status["run_complete"] else "no"
    cw = status["current_wave"]
    lines.append(
        f"  Run complete: {complete}    "
        f"Current wave: {cw if cw is not None else '—'} / {status['wave_count']}"
    )

    live = status["liveness"]
    if not live["run_log_present"]:
        lines.append("  Liveness:     run.log not present")
    elif live["last_event_at"] is None:
        lines.append("  Liveness:     run.log present but no parseable events")
    else:
        age = live["last_event_age_seconds"]
        age_str = f"{age:.0f}s ago" if age is not None else "?"
        lines.append(
            f"  Liveness:     last event {live['last_event_at']} ({age_str}) "
            f"— {live['last_event']}"
        )
    lines.append("=" * 88)
    lines.append("")

    totals = status["totals"]
    counts = "  ".join(
        f"{s}: {totals['by_status'].get(s, 0)}" for s in _STATUS_ORDER
    )
    lines.append(f"Tasks ({totals['task_count']}):  {counts}")
    cost = totals["run_cost_usd"]
    if cost is not None:
        lines.append(
            f"Run cost:    ${cost:.4f}  across {totals['tasks_billed']} billed task(s)"
        )
    lines.append("")

    header = (
        f"  {'KEY':16} {'STATUS':12} {'WAVE':4} {'COST':>9} "
        f"{'ITERS':5} {'MODEL':18} NOTE"
    )
    lines.append(header)
    lines.append("  " + "-" * (len(header) - 2))
    for t in status["tasks"]:
        cost = t["cost_usd"]
        cost_str = f"${cost:.4f}" if cost is not None else "—"
        iters = t["iteration_count"]
        iters_str = str(iters) if iters is not None else "—"
        model = t["model"] or "—"
        note = t["blocked_reason"] or t["pr_url"] or ""
        lines.append(
            f"  {t['key']:16} {t['status']:12} {t['wave']:<4} {cost_str:>9} "
            f"{iters_str:5} {model:18} {note[:40]}"
        )
    return "\n".join(lines)


# --- small coercion helpers -------------------------------------------------


def _str_or_none(value: Any) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    return s or None


def _int_or_none(value: Any) -> int | None:
    if isinstance(value, bool):  # bool is an int subclass — exclude
        return None
    if isinstance(value, int):
        return value
    return None


def _num(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).astimezone()
