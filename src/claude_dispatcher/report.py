"""`dispatcher report <run-id>` — quality dashboard + cost rollup for a
completed (or in-flight) run.

Mid-run-safe: reads files only, never touches the YAML or worktrees.

Two output modes: a human-readable dashboard (default) and ``--json`` (one
machine-readable document mirroring it; schema documented field-by-field in
``docs/report-json.md``).

The per-run cost/usage rollup prefers the journal (``journal.jsonl``, see
docs/journal-format.md) over the YAML rows: a task can spawn multiple times
(commit retry, push retry, panel iterate) and the YAML row records only the
LAST spawn's usage, so real spend is the SUM over all of the task's
``task_spawn_finished`` events — journal-sourced totals can legitimately
exceed the YAML totals. Runs that predate the journal fall back to a
YAML-only rollup, clearly labeled (``source: yaml``). Spawns whose usage
fields are null (the agent CLI emitted no usage block) are excluded from the
sums and surfaced as an *unmeasured* count — null is never silently treated
as zero.

The dashboard keeps the original quality sections: status counts, per-task
quality table, "concerning tasks" highlights, per-reviewer breakdown from
each task's summary.md, PRs raised, and the parked / blocked lists.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from . import journal as journal_mod
from . import journal_read
from . import summary as summary_mod
from . import yaml_io


_STATUS_ORDER = ("To Do", "In Progress", "Done", "Blocked", "Escalated")

# Usage fields summed across spawns. duration_ms is summed too but does not
# participate in the "unmeasured" determination (a spawn with cost+tokens but
# no duration is still measured spend).
_MEASURED_FIELDS = (
    "cost_usd",
    "input_tokens",
    "output_tokens",
    "cache_read_input_tokens",
    "cache_creation_input_tokens",
)
_SUM_FIELDS = _MEASURED_FIELDS + ("duration_ms",)

_SOURCE_JOURNAL = "journal"
_SOURCE_YAML_PRE_JOURNAL = (
    "yaml (pre-journal run — per-task usage reflects last spawn only)"
)
_SOURCE_YAML_UNREADABLE = (
    "yaml (journal unreadable — per-task usage reflects last spawn only)"
)


def execute(args: argparse.Namespace) -> int:
    runs_dir = Path(args.runs_dir).resolve()
    run_id = _resolve_run_id(runs_dir, getattr(args, "run_id", None))
    if run_id is None:
        print(f"error: no runs found under {runs_dir}", file=sys.stderr)
        return 2
    run_dir = runs_dir / run_id
    if not run_dir.is_dir():
        print(f"error: run directory not found: {run_dir}", file=sys.stderr)
        return 2

    # Resolve the tasks YAML, highest precedence first: explicit --tasks-yaml
    # flag, then the journal genesis (run_started) payload's tasks_yaml_path,
    # then walk-up discovery (the only option for pre-journal runs).
    yaml_arg = getattr(args, "tasks_yaml", None)
    if yaml_arg:
        yaml_path = Path(yaml_arg).resolve()
        if not yaml_path.is_file():
            print(f"error: tasks YAML not found: {yaml_path}", file=sys.stderr)
            return 2
    else:
        yaml_path = (_yaml_from_journal_genesis(run_dir)
                     or _find_yaml_for_run(run_dir, runs_dir))
        if yaml_path is None:
            print("error: could not determine which YAML this run is for. "
                  "Pass --tasks-yaml <path>.", file=sys.stderr)
            return 2

    data = build_report(run_dir=run_dir, run_id=run_id, yaml_path=yaml_path)
    if getattr(args, "json", False):
        print(json.dumps(data, indent=2))
    else:
        print(render_report(data))
    return 0


def _resolve_run_id(runs_dir: Path, requested: str | None) -> str | None:
    """If user passed a run_id, use it. Otherwise pick the newest dir."""
    if requested and requested != "latest":
        return requested
    if not runs_dir.is_dir():
        return None
    candidates = [p for p in runs_dir.iterdir() if p.is_dir()]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime).name


def _yaml_from_journal_genesis(run_dir: Path) -> Path | None:
    """Resolve the tasks YAML from the journal's genesis (``run_started``)
    event, whose payload records the authoritative absolute ``tasks_yaml_path``
    at dispatch time.

    Real tasks YAMLs typically live in a sibling subtree of the runs dir
    (``features/<phase>/tasks.yaml``), which walk-up discovery can never find —
    the genesis path is the reliable source for journal-era runs. Returns None
    (so callers fall back to walk-up discovery) when there is no journal, no
    genesis event, or the recorded path no longer exists on disk (the repo may
    have moved since the run).
    """
    journal_path = run_dir / journal_mod.JOURNAL_FILENAME
    if not journal_path.is_file():
        return None
    for ev in journal_read.read_journal_events(journal_path):
        if ev.get("event_type") != "run_started":
            continue
        payload = ev.get("payload")
        raw = payload.get("tasks_yaml_path") if isinstance(payload, dict) else None
        if isinstance(raw, str) and raw.strip():
            candidate = Path(raw.strip())
            if candidate.is_file():
                return candidate.resolve()
        # Genesis found but its path is stale/unusable — fall back to walk-up.
        return None
    return None


def _find_yaml_for_run(run_dir: Path, runs_dir: Path) -> Path | None:
    """Find the tasks YAML this run was against.

    Strategy: pick any task_dir with a summary.md, extract its task_key,
    then walk UP from runs_dir looking for a directory containing a *.yaml
    that has that task. Handles both `runs/` and `docs/runs/` layouts.
    """
    # Find a usable task_key by scanning all task_dirs (some might be
    # mid-flight with no summary yet).
    target_key: str | None = None
    for task_dir in run_dir.iterdir():
        if not task_dir.is_dir():
            continue
        summary_path = task_dir / "summary.md"
        if summary_path.exists():
            s = summary_mod.parse(summary_path)
            if s.task_key:
                target_key = s.task_key
                break
    if target_key is None:
        return None

    # Walk up from runs_dir looking for the YAML. Bounded — stop at FS root.
    cur = runs_dir.parent
    for _ in range(10):
        for yaml_path in cur.glob("*.yaml"):
            try:
                doc = yaml_io.load(yaml_path)
                if isinstance(doc, dict) and "tasks" in doc:
                    for t in doc["tasks"] or []:
                        if str(t.get("key")) == target_key:
                            return yaml_path
            except Exception:
                continue
        if cur.parent == cur:
            return None
        cur = cur.parent
    return None


# --- data assembly ------------------------------------------------------------


def build_report(
    *, run_dir: Path, run_id: str, yaml_path: Path
) -> dict[str, Any]:
    """Assemble the full report as one JSON-serializable document.

    Pure data — rendering lives in :func:`render_report`. Schema documented
    in docs/report-json.md.
    """
    doc = yaml_io.load(yaml_path)
    tasks = doc.get("tasks", []) or []
    run_summaries = _load_run_summaries(run_dir)

    journal_path = run_dir / journal_mod.JOURNAL_FILENAME
    journal_present = journal_path.is_file()
    events = journal_read.read_journal_events(journal_path) if journal_present else []

    if events:
        source, source_label = "journal", _SOURCE_JOURNAL
    elif journal_present:
        # The file exists but yielded zero parseable events: fall back to the
        # YAML rollup, but label the failure distinctly from a pre-journal run.
        source, source_label = "yaml", _SOURCE_YAML_UNREADABLE
    else:
        source, source_label = "yaml", _SOURCE_YAML_PRE_JOURNAL

    run_rows = [t for t in tasks if t.get("dispatcher_run_id") == run_id
                or str(t.get("key")) in run_summaries]

    if source == "journal":
        rollup = _journal_rollup(events, run_rows)
    else:
        rollup = _yaml_rollup(run_rows)

    # pr mode (PRF-5) gets the pr-flow rollup + the two lifecycle statuses in
    # the status counts; branch mode (and any pre-journal/legacy run) is
    # unchanged. The mode comes from the genesis run_config.
    pr_mode = journal_read.integration_mode(events) == "pr"
    status_order = _STATUS_ORDER + (
        ("Awaiting Review", "Merged") if pr_mode else ())
    status_counts = Counter((t.get("status") or "To Do").strip() for t in tasks)
    result = {
        "run_id": run_id,
        "run_dir": str(run_dir),
        "tasks_yaml": str(yaml_path),
        "source": source,
        "source_label": source_label,
        "summary_file_count": len(run_summaries),
        "status_counts": {s: status_counts.get(s, 0) for s in status_order},
        "rollup": rollup,
        "quality": _quality(run_rows, run_summaries),
    }
    if pr_mode:
        result["pr_flow"] = _pr_flow(run_rows, events)
    return result


def _pr_flow(run_rows: list[dict], events: list[dict[str, Any]]) -> dict[str, Any]:
    """The pr-mode merge rollup (PRF-5): merged / awaiting / needs-rebase
    tallies, a self-vs-external approver breakdown, and the list of PRs still
    unmerged at run end.

    Counts are over this run's rows. The approver split reads the row's
    ``pr_approved_by`` (stamped at merge) and the risk level for the unmerged
    list comes from the journal pr_approved/pr_merged events (the merge engine
    records the level there, not on the row)."""
    pr_index = _journal_pr_index(events)
    merged = [r for r in run_rows if (r.get("status") or "").strip() == "Merged"]
    awaiting = [r for r in run_rows
                if (r.get("status") or "").strip() == "Awaiting Review"]
    needs_rebase = [r for r in run_rows if r.get("needs_rebase")]

    self_count = external_count = 0
    for r in merged:
        approver = (_str_or_none(r.get("pr_approved_by"))
                    or pr_index.get(str(r.get("key")), {}).get("approver") or "")
        if approver == "dispatcher-agent":
            self_count += 1
        elif approver.startswith("external"):
            external_count += 1

    unmerged_prs = [{
        "key": str(r.get("key")),
        "jira_key": _str_or_none(r.get("jira_key")),
        "status": (_str_or_none(r.get("status")) or "—"),
        "pr_number": _int_or_none(r.get("pr_number")),
        "pr_url": _str_or_none(r.get("pr_url")),
        "risk_level": pr_index.get(str(r.get("key")), {}).get("risk_level"),
        "needs_rebase": bool(r.get("needs_rebase")),
    } for r in sorted(awaiting, key=lambda r: str(r.get("key")))]

    return {
        "merged": len(merged),
        "awaiting_review": len(awaiting),
        "needs_rebase": len(needs_rebase),
        "approver_breakdown": {"self": self_count, "external": external_count},
        "unmerged_prs": unmerged_prs,
    }


def _journal_pr_index(events: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Per-task risk_level / approver from the LAST pr_approved / pr_merged
    journal event (the merge engine records these there, not on the row)."""
    index: dict[str, dict[str, Any]] = {}
    for ev in events:
        if ev.get("event_type") not in ("pr_approved", "pr_merged"):
            continue
        tk = ev.get("task_key")
        payload = ev.get("payload")
        if not isinstance(tk, str) or not isinstance(payload, dict):
            continue
        cur = index.setdefault(tk, {"risk_level": None, "approver": None})
        risk = _str_or_none(payload.get("risk_level"))
        if risk is not None:
            cur["risk_level"] = risk
        approver = _str_or_none(payload.get("approver"))
        if approver is not None:
            cur["approver"] = approver
    return index


def _journal_rollup(
    events: list[dict[str, Any]], run_rows: list[dict]
) -> dict[str, Any]:
    """Rollup sourced from the journal: per-task usage summed over ALL spawns,
    wall clock from run_started → run_complete (or last event, in flight),
    and the per-model aggregate. Cross-checked with the YAML for tasks that
    never reached a terminal journal event."""
    acc = _accumulate_tasks(events)
    rows_by_key = {str(r.get("key")): r for r in run_rows}

    task_entries: list[dict[str, Any]] = []
    for key in sorted(acc.keys() | rows_by_key.keys()):
        a = acc.get(key, _new_task_acc())
        row = rows_by_key.get(key)
        status = a["terminal_status"] or (
            _str_or_none(row.get("status")) if row else None) or "In Progress"
        task_entries.append({
            "key": key,
            "status": status,
            "model": a["model"],
            "agent": a["agent"],
            **{f: a["sums"][f] for f in _SUM_FIELDS},
            "cost_usd": _round_cost(a["sums"]["cost_usd"]),
            "spawn_count": a["spawns"],
            "unmeasured_spawns": a["unmeasured"],
            "iterations": a["iterations"],
            "panel_verdict": a["panel_verdict"],
            "needs_push": a["needs_push"],
            "in_yaml": row is not None,
        })

    totals = _sum_task_entries(task_entries)
    totals["spawn_count"] = sum(t["spawn_count"] or 0 for t in task_entries)
    totals["unmeasured_spawns"] = sum(
        t["unmeasured_spawns"] or 0 for t in task_entries)
    return {
        "wall_clock": _wall_clock(events),
        "totals": totals,
        "tasks": task_entries,
        "by_model": _by_model(events),
    }


def _new_task_acc() -> dict[str, Any]:
    return {
        "sums": {f: None for f in _SUM_FIELDS},
        "spawns": 0,
        "unmeasured": 0,
        "model": None,
        "agent": None,
        "needs_push": None,
        "iterations": None,
        "summary_iterations": None,
        "panel_verdict": None,
        "done_panel_consensus": None,
        "terminal_status": None,
    }


def _accumulate_tasks(events: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Walk the journal once and fold every task-keyed event into a per-task
    accumulator (spawn sums, last model, terminal metadata, panel verdicts)."""
    acc: dict[str, dict[str, Any]] = {}
    for ev in events:
        tk = ev.get("task_key")
        payload = ev.get("payload")
        if not isinstance(tk, str) or not isinstance(payload, dict):
            continue
        a = acc.setdefault(tk, _new_task_acc())
        etype = ev.get("event_type")
        if etype == "task_spawn_finished":
            _fold_spawn(a, payload)
        elif etype == "summary_parsed":
            a["summary_iterations"] = _int_or_none(payload.get("iterations"))
        elif etype == "panel_verdict" and isinstance(payload.get("consensus"), str):
            # Error-form payloads ({"error": ...}) carry no consensus and are
            # skipped, so a transient panel exception never erases a verdict.
            a["panel_verdict"] = payload["consensus"]
        elif etype == "task_done":
            a["terminal_status"] = "Done"
            _fold_terminal(a, payload)
        elif etype == "task_blocked":
            a["terminal_status"] = "Blocked"
            _fold_terminal(a, payload)
    for a in acc.values():
        if a["iterations"] is None:
            a["iterations"] = a["summary_iterations"]
        if a["panel_verdict"] is None:
            a["panel_verdict"] = a["done_panel_consensus"]
        del a["summary_iterations"], a["done_panel_consensus"]
    return acc


def _fold_spawn(a: dict[str, Any], payload: dict[str, Any]) -> None:
    """Fold one task_spawn_finished payload into a task accumulator: non-null
    usage adds to the sums; a spawn with any null measured field counts as
    unmeasured (never coerced to 0); model tracks the LAST spawn."""
    a["spawns"] += 1
    for f in _SUM_FIELDS:
        v = payload.get(f)
        if _num(v) is not None:
            a["sums"][f] = (a["sums"][f] or 0) + v
    if any(_num(payload.get(f)) is None for f in _MEASURED_FIELDS):
        a["unmeasured"] += 1
    model = _str_or_none(payload.get("model"))
    if model:
        a["model"] = model


def _fold_terminal(a: dict[str, Any], payload: dict[str, Any]) -> None:
    """Fold a terminal (task_done / task_blocked) payload: agent metadata and
    needs_push exist only since they were added to the orchestrator — older
    journals simply lack the keys, which stays null (no KeyError)."""
    a["agent"] = _str_or_none(payload.get("agent"))
    if "needs_push" in payload:
        a["needs_push"] = bool(payload.get("needs_push"))
    if _int_or_none(payload.get("iterations")) is not None:
        a["iterations"] = _int_or_none(payload.get("iterations"))
    a["done_panel_consensus"] = _str_or_none(payload.get("panel_consensus"))


def _wall_clock(events: list[dict[str, Any]]) -> dict[str, Any] | None:
    """run_started timestamp → run_complete timestamp; if the run never
    completed, measure to the last event and flag the rollup in-flight."""
    started = ended = last = None
    in_flight = False
    for ev in events:
        ts = ev.get("timestamp")
        if isinstance(ts, str):
            last = ts
        etype = ev.get("event_type")
        if etype == "run_started" and started is None:
            started = ts if isinstance(ts, str) else None
        elif etype == "run_complete" and isinstance(ts, str):
            ended = ts
    if ended is None and last is not None:
        ended = last
        in_flight = True
    return {
        "started_at": started,
        "ended_at": ended,
        "seconds": _seconds_between(started, ended),
        "in_flight": in_flight,
    }


def _seconds_between(start: str | None, end: str | None) -> float | None:
    a = journal_read.parse_iso(start)
    b = journal_read.parse_iso(end)
    if a is None or b is None:
        return None
    # Normalize tz-awareness so a naive fixture timestamp can't raise.
    if a.tzinfo is None and b.tzinfo is not None:
        b = b.replace(tzinfo=None)
    elif a.tzinfo is not None and b.tzinfo is None:
        a = a.replace(tzinfo=None)
    return round((b - a).total_seconds(), 3)


def _by_model(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Per-model aggregate over all task_spawn_finished events. Spawns with a
    null model group under "unknown"."""
    groups: dict[str, dict[str, Any]] = {}
    for ev in events:
        if ev.get("event_type") != "task_spawn_finished":
            continue
        payload = ev.get("payload")
        if not isinstance(payload, dict):
            continue
        model = _str_or_none(payload.get("model")) or "unknown"
        g = groups.setdefault(model, {
            "model": model, "spawns": 0, "task_keys": set(),
            "sums": {f: None for f in _MEASURED_FIELDS}, "unmeasured": 0,
        })
        g["spawns"] += 1
        tk = ev.get("task_key")
        if isinstance(tk, str):
            g["task_keys"].add(tk)
        for f in _MEASURED_FIELDS:
            v = payload.get(f)
            if _num(v) is not None:
                g["sums"][f] = (g["sums"][f] or 0) + v
        if any(_num(payload.get(f)) is None for f in _MEASURED_FIELDS):
            g["unmeasured"] += 1
    out = []
    for model in sorted(groups):
        g = groups[model]
        sums = g["sums"]
        out.append({
            "model": model,
            "spawns": g["spawns"],
            "tasks": len(g["task_keys"]),
            "cost_usd": _round_cost(sums["cost_usd"]),
            **{f: sums[f] for f in _MEASURED_FIELDS if f != "cost_usd"},
            "unmeasured_spawns": g["unmeasured"],
        })
    return out


def _yaml_rollup(run_rows: list[dict]) -> dict[str, Any]:
    """Fallback rollup for pre-journal runs, built from the YAML rows stamped
    with this run's id. Per-task usage reflects the LAST spawn only (all the
    YAML records); journal-only fields (wall clock, spawn counts) are null."""
    task_entries: list[dict[str, Any]] = []
    for row in sorted(run_rows, key=lambda r: str(r.get("key"))):
        task_entries.append({
            "key": str(row.get("key")),
            "status": (_str_or_none(row.get("status")) or "To Do"),
            "model": _str_or_none(row.get("model")),
            "agent": _str_or_none(row.get("agent")),
            "cost_usd": _num(row.get("cost_usd")),
            "input_tokens": _int_or_none(row.get("input_tokens")),
            "output_tokens": _int_or_none(row.get("output_tokens")),
            "cache_read_input_tokens": _int_or_none(row.get("cache_read_input_tokens")),
            "cache_creation_input_tokens": _int_or_none(row.get("cache_creation_input_tokens")),
            "duration_ms": _int_or_none(row.get("duration_ms")),
            "spawn_count": None,
            "unmeasured_spawns": None,
            "iterations": _int_or_none(row.get("iteration_count")),
            "panel_verdict": _str_or_none(row.get("panel_consensus")),
            "needs_push": bool(row.get("needs_push")) if "needs_push" in row else None,
            "in_yaml": True,
        })

    totals = _sum_task_entries(task_entries)
    totals["spawn_count"] = None
    totals["unmeasured_spawns"] = None
    return {
        "wall_clock": None,
        "totals": totals,
        "tasks": task_entries,
        "by_model": _by_model_from_rows(task_entries),
    }


def _by_model_from_rows(task_entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """YAML-mode per-model aggregate: group per-task rows by their model."""
    groups: dict[str, list[dict[str, Any]]] = {}
    for t in task_entries:
        groups.setdefault(t["model"] or "unknown", []).append(t)
    out = []
    for model in sorted(groups):
        rows = groups[model]
        sums = {f: _sum_or_none(r[f] for r in rows) for f in _MEASURED_FIELDS}
        out.append({
            "model": model,
            "spawns": None,
            "tasks": len(rows),
            "cost_usd": _round_cost(sums["cost_usd"]),
            **{f: sums[f] for f in _MEASURED_FIELDS if f != "cost_usd"},
            "unmeasured_spawns": None,
        })
    return out


def _sum_task_entries(task_entries: list[dict[str, Any]]) -> dict[str, Any]:
    """Run totals over per-task entries: each usage field sums its non-null
    values, staying null when NOTHING was measured (null is never zero)."""
    totals: dict[str, Any] = {
        "tasks_by_status": dict(Counter(t["status"] for t in task_entries)),
    }
    for f in _SUM_FIELDS:
        totals[f] = _sum_or_none(t[f] for t in task_entries)
    totals["cost_usd"] = _round_cost(totals["cost_usd"])
    totals["tasks_billed"] = sum(1 for t in task_entries if t["cost_usd"] is not None)
    return totals


def _sum_or_none(values) -> Any:
    present = [v for v in values if v is not None]
    return sum(present) if present else None


def _round_cost(value: float | None) -> float | None:
    return round(value, 6) if value is not None else None


def _quality(
    run_rows: list[dict], run_summaries: dict[str, summary_mod.Summary]
) -> dict[str, Any]:
    """The original quality dashboard data, as JSON-serializable structures."""
    rows = sorted(run_rows, key=lambda r: str(r.get("key")))
    return {
        "tasks": [{
            "key": str(t.get("key")),
            "jira_key": _str_or_none(t.get("jira_key")),
            "status": (_str_or_none(t.get("status")) or "To Do"),
            "final_quality_score": _int_or_none(t.get("final_quality_score")),
            "iteration_count": _int_or_none(t.get("iteration_count")),
            "linter_cycles": _int_or_none(t.get("linter_cycles")),
            "deferred_findings_count": _int_or_none(t.get("deferred_findings_count")),
            "human_gate_fired": bool(t.get("human_gate_fired")),
            "pr_url": _str_or_none(t.get("pr_url")),
        } for t in rows],
        "concerning": [
            {"key": str(t.get("key")), "reasons": reasons}
            for t, reasons in _identify_concerning(rows)
        ],
        "reviews": _quality_reviews(rows, run_summaries),
        "prs": [
            {"key": str(t.get("key")), "jira_key": _str_or_none(t.get("jira_key")),
             "pr_url": str(t.get("pr_url"))}
            for t in rows if t.get("pr_url")
        ],
        "parked": [
            {"key": str(t.get("key")), "jira_key": _str_or_none(t.get("jira_key")),
             "branch": _str_or_none(t.get("prepared_pr_branch"))}
            for t in rows
            if (t.get("status") or "").strip() == "Blocked"
            and t.get("prepared_pr_title")
        ],
        "blocked": [
            {"key": str(t.get("key")),
             "reason": _str_or_none(t.get("blocked_reason")) or "—"}
            for t in rows
            if (t.get("status") or "").strip() == "Blocked"
            and not t.get("prepared_pr_title")
        ],
    }


def _quality_reviews(
    rows: list[dict], run_summaries: dict[str, summary_mod.Summary]
) -> list[dict[str, Any]]:
    """Per-task review-consensus blocks from each task's summary.md."""
    reviews: list[dict[str, Any]] = []
    for t in rows:
        key = str(t.get("key"))
        s = run_summaries.get(key)
        if not s or not s.review_consensus:
            continue
        reviews.append({
            "key": key,
            "status": s.status,
            "consensus": [{
                "reviewer": r.get("reviewer", "?"),
                "score": r.get("score", "—"),
                "verdict": r.get("verdict", "—"),
            } for r in s.review_consensus],
            "per_dimension": _extract_per_dimension(s),
            "deferred_findings": list(s.deferred_findings),
        })
    return reviews


# --- rendering ------------------------------------------------------------------


def render_report(data: dict[str, Any]) -> str:
    """Human-readable rendering of a build_report() result. Pure string."""
    lines: list[str] = []
    lines.append("=" * 88)
    lines.append(f"Dispatcher report — {data['run_id']}")
    lines.append(f"  Tasks YAML:    {data['tasks_yaml']}")
    lines.append(f"  Run dir:       {data['run_dir']}")
    lines.append(f"  Summary files: {data['summary_file_count']}")
    lines.append(f"  Source:        {data['source_label']}")
    lines.append("=" * 88)
    lines.append("")

    lines.append("Status counts:")
    for status in ("Done", "In Progress", "To Do", "Blocked", "Escalated"):
        n = data["status_counts"].get(status, 0)
        if n or status in ("Done", "In Progress", "To Do"):
            lines.append(f"  {status:13}  {n}")
    # pr mode (PRF-5) adds Awaiting Review / Merged to status_counts; show them
    # when present. Branch mode has neither key, so this loop is a no-op there.
    for status in ("Awaiting Review", "Merged"):
        if status in data["status_counts"]:
            lines.append(f"  {status:13}  {data['status_counts'][status]}")
    lines.append("")

    lines.extend(_render_rollup(data))
    lines.extend(_render_pr_flow(data.get("pr_flow")))

    quality = data["quality"]
    if not quality["tasks"] and not data["rollup"]["tasks"]:
        lines.append("(no tasks from this run found in the YAML — "
                     "is the run still very fresh?)")
        return "\n".join(lines)
    lines.extend(_render_quality(quality))
    return "\n".join(lines)


def _render_rollup(data: dict[str, Any]) -> list[str]:
    rollup = data["rollup"]
    totals = rollup["totals"]
    lines: list[str] = []
    lines.append(f"Run rollup [source: {data['source_label']}]:")
    counts = "  ".join(f"{s}: {n}" for s, n in
                       sorted(totals["tasks_by_status"].items()))
    lines.append(f"  Tasks by status          {counts or '—'}")
    wc = rollup["wall_clock"]
    if wc is not None and wc["started_at"]:
        secs = f"{wc['seconds']:.1f} s" if wc["seconds"] is not None else "?"
        flight = " so far — run in flight, no run_complete" if wc["in_flight"] else ""
        lines.append(f"  Wall clock               {wc['started_at']} → "
                     f"{wc['ended_at']}  ({secs}{flight})")
    lines.append(f"  Total cost (USD)         {_fmt_cost(totals['cost_usd'], 8)}")
    if totals["tasks_billed"]:
        avg = (totals["cost_usd"] or 0) / totals["tasks_billed"]
        lines.append(f"  Tasks billed             {totals['tasks_billed']}")
        lines.append(f"  Avg cost per task        ${avg:>8.4f}")
    lines.append(f"  Total input tokens       {_fmt_tok(totals['input_tokens'])}")
    lines.append(f"  Total output tokens      {_fmt_tok(totals['output_tokens'])}")
    lines.append(f"  Cache-read tokens        {_fmt_tok(totals['cache_read_input_tokens'])}")
    lines.append(f"  Cache-creation tokens    {_fmt_tok(totals['cache_creation_input_tokens'])}")
    if totals["duration_ms"] is not None:
        lines.append(f"  Sum of spawn durations   {totals['duration_ms'] / 1000:>8.1f} s")
    if totals["spawn_count"] is not None:
        unmeasured = totals["unmeasured_spawns"] or 0
        note = f"  ({unmeasured} with unmeasured usage)" if unmeasured else ""
        lines.append(f"  Spawns                   {totals['spawn_count']}{note}")
    lines.append("")

    lines.extend(_render_usage_table(rollup["tasks"]))
    lines.extend(_render_model_table(data, rollup["by_model"]))
    return lines


def _render_pr_flow(pr_flow: dict[str, Any] | None) -> list[str]:
    """The pr-mode merge section (PRF-5). Empty list in branch mode (pr_flow is
    absent), so the branch dashboard is unchanged."""
    if not pr_flow:
        return []
    ab = pr_flow["approver_breakdown"]
    lines = [
        "PR flow:",
        f"  Merged                   {pr_flow['merged']}  "
        f"(self-approved {ab['self']}, external {ab['external']})",
        f"  Awaiting merge           {pr_flow['awaiting_review']}",
    ]
    if pr_flow["needs_rebase"]:
        lines.append(f"  Needs rebase             {pr_flow['needs_rebase']}")
    unmerged = pr_flow["unmerged_prs"]
    if unmerged:
        lines.append("")
        lines.append(f"  Unmerged PRs at run end ({len(unmerged)}):")
        for p in unmerged:
            num = f"#{p['pr_number']}" if p["pr_number"] is not None else "—"
            risk = p["risk_level"] or "?"
            flag = "  ⚠ needs rebase" if p["needs_rebase"] else ""
            url = p["pr_url"] or "—"
            lines.append(f"    {p['key']:14} {num:6} risk={risk:9} {url}{flag}")
    lines.append("")
    return lines


def _render_usage_table(task_entries: list[dict[str, Any]]) -> list[str]:
    if not task_entries:
        return []
    lines = ["Per-task usage:"]
    header = (f"  {'KEY':14} {'STATUS':12} {'MODEL':20} {'AGENT':8} "
              f"{'COST':>9} {'IN':>9} {'OUT':>9} {'CACHE-R':>9} {'CACHE-C':>9} "
              f"{'SPWN':>4} {'ITERS':>5} {'PANEL':10} PUSH")
    lines.append(header)
    lines.append("  " + "-" * (len(header) - 2))
    for t in task_entries:
        flag = "" if t["in_yaml"] else "  (not in YAML)"
        lines.append(
            f"  {t['key']:14} {t['status']:12} {t['model'] or '—':20} "
            f"{t['agent'] or '—':8} {_fmt_cost(t['cost_usd'], 9):>9} "
            f"{_fmt_tok(t['input_tokens'])} {_fmt_tok(t['output_tokens'])} "
            f"{_fmt_tok(t['cache_read_input_tokens'])} "
            f"{_fmt_tok(t['cache_creation_input_tokens'])} "
            f"{_fmt_n(t['spawn_count'], 4)} {_fmt_n(t['iterations'], 5)} "
            f"{t['panel_verdict'] or '—':10} {_fmt_bool(t['needs_push'])}{flag}"
        )
    lines.append("")
    return lines


def _render_model_table(data: dict[str, Any], by_model: list[dict[str, Any]]) -> list[str]:
    if not by_model:
        return []
    lines = [f"Per-model usage [source: {data['source_label']}]:"]
    header = (f"  {'MODEL':20} {'SPAWNS':>6} {'TASKS':>5} {'COST':>9} "
              f"{'IN':>9} {'OUT':>9} {'CACHE-R':>9} {'CACHE-C':>9}")
    lines.append(header)
    lines.append("  " + "-" * (len(header) - 2))
    for m in by_model:
        lines.append(
            f"  {m['model']:20} {_fmt_n(m['spawns'], 6)} {m['tasks']:>5} "
            f"{_fmt_cost(m['cost_usd'], 9):>9} {_fmt_tok(m['input_tokens'])} "
            f"{_fmt_tok(m['output_tokens'])} {_fmt_tok(m['cache_read_input_tokens'])} "
            f"{_fmt_tok(m['cache_creation_input_tokens'])}"
        )
    lines.append("")
    return lines


def _render_quality(quality: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    tasks = quality["tasks"]
    if tasks:
        lines.append(f"Tasks in this run ({len(tasks)}):")
        lines.append("")
        header = (f"  {'KEY':14} {'JIRA':10} {'STATUS':12} {'SCORE':8} "
                  f"{'ITERS':5} {'LINT':4} {'DEFRRD':6} {'GATE':4}")
        lines.append(header)
        lines.append("  " + "-" * (len(header) - 2))
        for t in tasks:
            score = t["final_quality_score"]
            score_str = f"{score}/25" if score is not None else "—"
            lines.append(
                f"  {t['key']:14} {t['jira_key'] or '—':10} {t['status']:12} "
                f"{score_str:8} {t['iteration_count'] or 0:<5} "
                f"{t['linter_cycles'] or 0:<4} "
                f"{t['deferred_findings_count'] or 0:<6} "
                f"{'yes' if t['human_gate_fired'] else 'no'}"
            )
        lines.append("")

    if quality["concerning"]:
        lines.append(f"Concerning tasks to spot-check ({len(quality['concerning'])}):")
        for c in quality["concerning"]:
            lines.append(f"  {c['key']:14} → {'; '.join(c['reasons'])}")
        lines.append("")

    lines.extend(_render_reviews(quality["reviews"]))
    lines.extend(_render_pr_lists(quality))
    return lines


def _render_reviews(reviews: list[dict[str, Any]]) -> list[str]:
    lines = ["Per-reviewer breakdown (from summary files):", ""]
    if not reviews:
        lines.append("  (no review consensus tables found — Low-risk self-review tasks "
                     "won't have one)")
        lines.append("")
        return lines
    for r in reviews:
        lines.append(f"  {r['key']} ({r['status'] or '—'}):")
        for rev in r["consensus"]:
            lines.append(f"    {rev['reviewer']:10}  {rev['score']:10}  {rev['verdict']}")
        for dim, scores in r["per_dimension"].items():
            lines.append(f"      {dim:18} " + "  ".join(scores))
        if r["deferred_findings"]:
            lines.append(f"    Deferred ({len(r['deferred_findings'])}): " +
                         "; ".join(f[:60] for f in r["deferred_findings"][:3]))
        lines.append("")
    return lines


def _render_pr_lists(quality: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    if quality["prs"]:
        lines.append(f"PRs raised ({len(quality['prs'])}):")
        for p in quality["prs"]:
            lines.append(f"  {p['key']} ({p['jira_key'] or '—'}): {p['pr_url']}")
        lines.append("")

    if quality["parked"]:
        lines.append(f"Parked at human PR gate, awaiting approval ({len(quality['parked'])}):")
        for p in quality["parked"]:
            lines.append(f"  {p['key']:14}  {p['jira_key'] or '—':10}  {p['branch']}")
        lines.append("    -> sweep with: dispatcher run <yaml> --mode supervised --only <key,key,...>")
        lines.append("")

    if quality["blocked"]:
        lines.append(f"Blocked for other reasons ({len(quality['blocked'])}):")
        for b in quality["blocked"]:
            lines.append(f"  {b['key']:14}  {b['reason']}")
        lines.append("")

    return lines


# --- formatting helpers ---------------------------------------------------------


def _fmt_cost(value: float | None, width: int) -> str:
    if value is None:
        return f"{'—':>{width}}"
    return f"${value:>{width - 1}.4f}"


def _fmt_tok(value: int | None) -> str:
    return f"{value:>9,}" if value is not None else f"{'—':>9}"


def _fmt_n(value: int | None, width: int) -> str:
    return f"{value:>{width}}" if value is not None else f"{'—':>{width}}"


def _fmt_bool(value: bool | None) -> str:
    if value is None:
        return "—"
    return "yes" if value else "no"


def _identify_concerning(tasks: list[dict]) -> list[tuple[dict, list[str]]]:
    """Tasks worth spot-checking. Returns (task, reasons[]) pairs."""
    out: list[tuple[dict, list[str]]] = []
    for t in tasks:
        if (t.get("status") or "").strip() != "Done":
            continue
        reasons: list[str] = []
        score = t.get("final_quality_score")
        if isinstance(score, int) and score < 22:
            reasons.append(f"score {score}/25 (low end of APPROVE band)")
        iters = t.get("iteration_count", 0)
        if isinstance(iters, int) and iters > 0:
            reasons.append(f"iterated {iters}x before APPROVE")
        deferred = t.get("deferred_findings_count", 0)
        if isinstance(deferred, int) and deferred >= 3:
            reasons.append(f"{deferred} deferred findings")
        if t.get("human_gate_fired") and t.get("pr_url"):
            reasons.append("human gate fired (financial/Critical) — PR has been approved")
        if reasons:
            out.append((t, reasons))
    return out


def _load_run_summaries(run_dir: Path) -> dict[str, summary_mod.Summary]:
    """Map task_key → parsed Summary for every summary.md in this run."""
    summaries: dict[str, summary_mod.Summary] = {}
    for task_dir in run_dir.iterdir():
        if not task_dir.is_dir():
            continue
        summary_path = task_dir / "summary.md"
        if summary_path.exists():
            s = summary_mod.parse(summary_path)
            if s.task_key:
                summaries[s.task_key] = s
    return summaries


_DIM_RE = re.compile(
    r"^\|\s*(Correctness|Security|Compliance|Resilience|Idempotency|"
    r"Observability|Performance|Maintainability)\s*\|(.*?)\|$",
    re.IGNORECASE,
)


def _extract_per_dimension(s: summary_mod.Summary) -> dict[str, list[str]]:
    """If the summary's "What landed" / "Key decisions" contains a per-
    dimension review table, extract it. Best-effort — many tasks won't
    have this in a structured form.
    """
    text = (s.what_landed or "") + "\n" + (s.key_decisions or "")
    out: dict[str, list[str]] = {}
    for line in text.splitlines():
        m = _DIM_RE.match(line.strip())
        if m:
            dim = m.group(1).title()
            scores = [c.strip() for c in m.group(2).split("|") if c.strip()]
            out[dim] = scores
    return out


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
        return int(value)
    return None


def _num(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None
