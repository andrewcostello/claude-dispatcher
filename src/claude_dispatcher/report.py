"""`dispatcher report <run-id>` — quality dashboard for a completed (or
in-flight) run.

Mid-run-safe: reads files only, never touches the YAML or worktrees.

Output: a single-pane summary with overall counts, a per-task table
showing the gate-relevant quality fields, a "concerning tasks" highlight
section (gate fired, high deferred count, had to iterate), and the
per-reviewer / per-dimension breakdown from each task's summary.md
where available.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from . import plan as plan_mod
from . import summary as summary_mod
from . import yaml_io


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

    yaml_path = _find_yaml_for_run(run_dir, runs_dir)
    if yaml_path is None:
        print(f"error: could not determine which YAML this run is for. "
              f"Pass --tasks-yaml.", file=sys.stderr)
        return 2

    print(_render(run_dir, run_id, yaml_path))
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


def _render(run_dir: Path, run_id: str, yaml_path: Path) -> str:
    """Build the dashboard text. Pure-string output — testable."""
    doc = yaml_io.load(yaml_path)
    tasks = doc.get("tasks", []) or []
    run_summaries = _load_run_summaries(run_dir)

    lines: list[str] = []
    lines.append("=" * 88)
    lines.append(f"Dispatcher report — {run_id}")
    lines.append(f"  Tasks YAML:    {yaml_path}")
    lines.append(f"  Run dir:       {run_dir}")
    lines.append(f"  Summary files: {len(run_summaries)}")
    lines.append("=" * 88)
    lines.append("")

    # --- overall status counts -------------------------------------------
    status_counts = Counter((t.get("status") or "To Do").strip() for t in tasks)
    lines.append("Status counts:")
    for status in ("Done", "In Progress", "To Do", "Blocked", "Escalated"):
        n = status_counts.get(status, 0)
        if n or status in ("Done", "In Progress", "To Do"):
            lines.append(f"  {status:13}  {n}")
    lines.append("")

    # --- run-level cost + token totals -----------------------------------
    # Tasks that participated in this run record cost_usd / token counts on
    # their row. Sum across tasks with completion timestamps in this run for
    # the run's total spend; show per-task average for cross-strategy compare.
    cost_total = 0.0
    cost_tasks = 0
    input_total = 0
    output_total = 0
    cache_read_total = 0
    cache_creation_total = 0
    duration_total_ms = 0
    for t in tasks:
        if t.get("dispatcher_run_id") != run_id:
            continue
        c = t.get("cost_usd")
        if isinstance(c, (int, float)):
            cost_total += float(c)
            cost_tasks += 1
        if isinstance(t.get("input_tokens"), int):
            input_total += t["input_tokens"]
        if isinstance(t.get("output_tokens"), int):
            output_total += t["output_tokens"]
        if isinstance(t.get("cache_read_input_tokens"), int):
            cache_read_total += t["cache_read_input_tokens"]
        if isinstance(t.get("cache_creation_input_tokens"), int):
            cache_creation_total += t["cache_creation_input_tokens"]
        if isinstance(t.get("duration_ms"), int):
            duration_total_ms += t["duration_ms"]
    if cost_tasks > 0:
        lines.append("Run cost / token usage:")
        lines.append(f"  Total cost (USD)         ${cost_total:>8.4f}")
        lines.append(f"  Tasks billed             {cost_tasks}")
        if cost_tasks:
            lines.append(f"  Avg cost per task        ${cost_total / cost_tasks:>8.4f}")
        lines.append(f"  Total input tokens       {input_total:>10,}")
        lines.append(f"  Total output tokens      {output_total:>10,}")
        lines.append(f"  Cache-read tokens        {cache_read_total:>10,}")
        lines.append(f"  Cache-creation tokens    {cache_creation_total:>10,}")
        if duration_total_ms:
            lines.append(f"  Sum of task durations    {duration_total_ms / 1000:>8.1f} s")
        lines.append("")

    # --- per-task table for this run only --------------------------------
    run_tasks = [t for t in tasks if t.get("dispatcher_run_id") == run_id
                 or t.get("key") in run_summaries]
    if not run_tasks:
        lines.append("(no tasks from this run found in the YAML — "
                     "is the run still very fresh?)")
        return "\n".join(lines)

    lines.append(f"Tasks in this run ({len(run_tasks)}):")
    lines.append("")
    header = f"  {'KEY':14} {'JIRA':10} {'STATUS':12} {'SCORE':8} {'ITERS':5} {'LINT':4} {'DEFRRD':6} {'GATE':4}"
    lines.append(header)
    lines.append("  " + "-" * (len(header) - 2))
    for t in sorted(run_tasks, key=lambda x: str(x.get("key"))):
        lines.append(_row(t))
    lines.append("")

    # --- concerning tasks ---------------------------------------------
    concerning = _identify_concerning(run_tasks)
    if concerning:
        lines.append(f"Concerning tasks to spot-check ({len(concerning)}):")
        for t, reasons in concerning:
            reasons_str = "; ".join(reasons)
            lines.append(f"  {t['key']:14} → {reasons_str}")
        lines.append("")

    # --- per-task review consensus from summary.md ---------------------
    lines.append("Per-reviewer breakdown (from summary files):")
    lines.append("")
    has_any_review = False
    for t in sorted(run_tasks, key=lambda x: str(x.get("key"))):
        key = str(t.get("key"))
        s = run_summaries.get(key)
        if not s or not s.review_consensus:
            continue
        has_any_review = True
        lines.append(f"  {key} ({s.status or '—'}):")
        for rev in s.review_consensus:
            lines.append(f"    {rev.get('reviewer', '?'):10}  {rev.get('score', '—'):10}  {rev.get('verdict', '—')}")
        # Per-dimension scores if extractable from "What landed" / decisions text
        per_dim = _extract_per_dimension(s)
        if per_dim:
            for dim, scores in per_dim.items():
                lines.append(f"      {dim:18} " + "  ".join(scores))
        if s.deferred_findings:
            lines.append(f"    Deferred ({len(s.deferred_findings)}): " +
                         "; ".join(f[:60] for f in s.deferred_findings[:3]))
        lines.append("")
    if not has_any_review:
        lines.append("  (no review consensus tables found — Low-risk self-review tasks "
                     "won't have one)")
        lines.append("")

    # --- PRs raised ----------------------------------------------------
    prs = [(t["key"], t.get("pr_url"), t.get("jira_key"))
           for t in run_tasks
           if t.get("pr_url")]
    if prs:
        lines.append(f"PRs raised ({len(prs)}):")
        for key, url, jk in prs:
            lines.append(f"  {key} ({jk}): {url}")
        lines.append("")

    parked = [t for t in run_tasks
              if (t.get("status") or "").strip() == "Blocked"
              and t.get("prepared_pr_title")]
    if parked:
        lines.append(f"Parked at human PR gate, awaiting approval ({len(parked)}):")
        for t in parked:
            lines.append(f"  {t['key']:14}  {t.get('jira_key', '—'):10}  {t.get('prepared_pr_branch')}")
        lines.append("    -> sweep with: dispatcher run <yaml> --mode supervised --only <key,key,...>")
        lines.append("")

    other_blocked = [t for t in run_tasks
                     if (t.get("status") or "").strip() == "Blocked"
                     and not t.get("prepared_pr_title")]
    if other_blocked:
        lines.append(f"Blocked for other reasons ({len(other_blocked)}):")
        for t in other_blocked:
            reason = t.get("blocked_reason", "—")
            lines.append(f"  {t['key']:14}  {reason}")
        lines.append("")

    return "\n".join(lines)


def _row(t: dict) -> str:
    """One table row per task."""
    key = str(t.get("key", "?"))
    jira = str(t.get("jira_key", "—"))
    status = (t.get("status") or "To Do").strip()
    score = t.get("final_quality_score")
    score_str = f"{score}/25" if score is not None else "—"
    iters = t.get("iteration_count", 0)
    linter = t.get("linter_cycles", 0)
    deferred = t.get("deferred_findings_count", 0)
    gate = "yes" if t.get("human_gate_fired") else "no"
    return f"  {key:14} {jira:10} {status:12} {score_str:8} {iters:<5} {linter:<4} {deferred:<6} {gate}"


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
