"""Agent bake-off: run every implementer agent on every task, score each
solution with the cross-family panel, and recommend an outcome-first routing.

This is the experiment harness for "which agent should implement which task".
For each (task, agent) cell it:
  1. forks an isolated worktree from the task's base ref,
  2. spawns that agent as the implementer (spawn.spawn_agent),
  3. runs the repo's mechanical gate (.dispatcher.yaml `test:`),
  4. scores the diff with the cross-family panel (the authoring family is
     excluded from its own jury to cut self-bias),
  5. records gate outcome, panel consensus, blocking findings, cost, duration.

Scoring is OUTCOME-FIRST, cost as a tiebreaker (the chosen policy): a cell's
quality rank is (gate_passed, panel_rank, -blocking_findings); ties break on
lower cost_usd, then lower duration. Per task we recommend the top-ranked
agent; the matrix + per-task winners are written as JSON + a markdown table.

Cost note: Claude/Codex report cost via their JSON usage; Grok (flat-rate
SuperGrok) and Gemini/agy report none here, so their cost is treated as 0.0 —
which fits the outcome-first/cost-tiebreak policy (a free agent only wins a
tie). The harness records `cost_known` so the report never implies false
precision.
"""

from __future__ import annotations

import json
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import cross_family_reviewer as cfr
from . import mechanical_verify as mv
from . import plan as plan_mod
from . import repo_config as repo_config_mod
from . import spawn as spawn_mod

ALL_AGENTS = ("claude", "codex", "grok", "gemini")
# Reviewers in the panel (v2: grok promoted from advisory). Author excluded per cell.
ALL_REVIEWERS = ("claude", "codex", "gemini", "grok")
EFFORT_LEVELS = ("low", "medium", "high")  # gemini has no effort flag -> "default"
HARNESS_VERSION = "2"

# Panel consensus -> rank (higher is better). Used in the outcome-first sort.
_CONSENSUS_RANK = {"approve": 2, "incomplete": 1, "block": 0}


@dataclass
class CellResult:
    """One (task, agent) bake-off cell."""
    task_key: str
    agent: str
    spawned: bool = False
    gate_passed: bool = False
    panel_consensus: str = "n/a"  # approve|block|incomplete|n/a
    blocking_findings: int = 0
    diff_lines: int = 0
    cost_usd: float = 0.0
    cost_known: bool = False
    duration_s: float = 0.0
    error: str | None = None
    # --- v2 (eval-harness) fields ---
    effort: str = "default"        # low|medium|high|default
    trial: int = 0                 # repeat index for variance
    stack: str = "unknown"         # react|go|unknown (per-language routing)
    model_id: str | None = None    # provenance: resolved model
    cli_version: str | None = None # provenance: agent CLI version
    input_tokens: int = 0
    output_tokens: int = 0
    relaxed_pass: bool = False     # gate_passed AND 0 CRITICAL/HIGH findings
    findings: list[dict] = field(default_factory=list)   # full persisted findings
    reviewers: list[dict] = field(default_factory=list)  # per-reviewer verdict+findings
    repair_attempted: bool = False
    repair_helped: bool = False    # repair turned a fail into a (relaxed) pass
    pre_repair: dict | None = None # {gate_passed, blocking_findings, panel_consensus}

    @property
    def quality_key(self) -> tuple:
        """Outcome-first sort key (higher tuple = better). Cost/duration are
        negated so that, among equal-quality cells, cheaper+faster ranks higher
        — cost is purely a tiebreaker per the chosen policy."""
        return (
            1 if self.gate_passed else 0,
            _CONSENSUS_RANK.get(self.panel_consensus, -1),
            -self.blocking_findings,
            -self.cost_usd,
            -self.duration_s,
        )

    def to_dict(self) -> dict:
        return {
            "task_key": self.task_key, "agent": self.agent,
            "spawned": self.spawned, "gate_passed": self.gate_passed,
            "panel_consensus": self.panel_consensus,
            "blocking_findings": self.blocking_findings,
            "diff_lines": self.diff_lines,
            "cost_usd": round(self.cost_usd, 4), "cost_known": self.cost_known,
            "duration_s": round(self.duration_s, 1), "error": self.error,
            "effort": self.effort, "trial": self.trial, "stack": self.stack,
            "model_id": self.model_id, "cli_version": self.cli_version,
            "input_tokens": self.input_tokens, "output_tokens": self.output_tokens,
            "relaxed_pass": self.relaxed_pass, "findings": self.findings,
            "reviewers": self.reviewers, "repair_attempted": self.repair_attempted,
            "repair_helped": self.repair_helped, "pre_repair": self.pre_repair,
        }


# ===========================================================================
# Pure-logic body-fills (dogfood: each implemented by a dispatched agent task
# against the contract below + its skipped contract test in tests/test_bakeoff.py).
# Stubs raise until filled; the live-integration spine (run_cell/run_bakeoff)
# wires them in. Keep these PURE (no subprocess / network / fs) so they're
# unit-testable and the pytest gate gives objective done-criteria.
# ===========================================================================

def infer_stack(task: plan_mod.Task) -> str:
    """Classify a task's stack for per-language routing.

    Returns "go" if the task targets Go services (label `area:bay-session`,
    `area:go`, or `lang:go`, or a description/path under apps/platform-domain or
    *.go), "react" for mobile/TS/React work (label `area:mobile`, `area:react`,
    `lang:react`, or apps/skillstrike-mobile / *.tsx), else "unknown". Label
    match takes precedence over path heuristics. Pure function of `task`.
    """
    labels = task.labels or []
    if any(l in ("area:bay-session", "area:go", "lang:go") for l in labels):
        return "go"
    if any(l in ("area:mobile", "area:react", "lang:react") for l in labels):
        return "react"

    # Path heuristics (labels win). Search description (and summary for robustness).
    text = f"{task.description or ''} {task.summary or ''}"
    if "apps/platform-domain" in text or ".go" in text:
        return "go"
    if "apps/skillstrike-mobile" in text or ".tsx" in text:
        return "react"
    return "unknown"


def compute_relaxed_pass(gate_passed: bool, panel: "cfr.PanelVerdict | None") -> bool:
    """The relaxed acceptance bar: True iff the gate passed AND the panel has
    zero CRITICAL/HIGH (blocking) findings. MEDIUM/LOW nits do NOT block. A
    None panel (not run) counts as no blocking findings. Pure function.
    """
    if not gate_passed:
        return False
    if panel is None:
        return True
    findings = getattr(panel, "blocking_findings", None)
    return len(findings) == 0 if findings is not None else True


def evaluate_reviewers(cells: list["CellResult"]) -> dict:
    """Objective reviewer meta-evaluation over all cells' persisted per-reviewer
    data (`cell.reviewers` = [{family, verdict, findings:[{severity,...}]}]).

    For each reviewer family return a dict with:
      - reviews: int (cells judged)
      - approvals: int; approvals_of_gate_failing: int (objective false-negatives
        — approving a solution whose cell.gate_passed is False)
      - findings_total, blocking_findings_total (CRITICAL/HIGH)
      - approve_rate (approvals / reviews)
      - unique_blocking: blocking findings at a (task,agent,effort,trial,location)
        no OTHER reviewer flagged (candidate signal; needs adjudication for truth)
    Pure function of `cells`. Precision/recall vs ground truth come later from
    the planted-bug set + adjudication; this computes the gate-grounded +
    descriptive stats.
    """
    _BLOCKING = {"CRITICAL", "HIGH"}
    stats: dict[str, dict] = {}

    def _fam(family: str) -> dict:
        if family not in stats:
            stats[family] = {
                "reviews": 0,
                "approvals": 0,
                "approvals_of_gate_failing": 0,
                "findings_total": 0,
                "blocking_findings_total": 0,
                "approve_rate": 0.0,
                "unique_blocking": 0,
            }
        return stats[family]

    for cell in cells:
        reviewers = cell.reviewers or []
        # Per cell: which families flagged each location (any severity). Used to
        # decide whether a blocking finding is unique to one reviewer.
        flagged_by: dict[object, set] = {}
        for rv in reviewers:
            fam = rv.get("family")
            for f in rv.get("findings") or []:
                flagged_by.setdefault(f.get("location"), set()).add(fam)

        for rv in reviewers:
            fam = rv.get("family")
            s = _fam(fam)
            s["reviews"] += 1
            if rv.get("verdict") == "approve":
                s["approvals"] += 1
                if not cell.gate_passed:
                    s["approvals_of_gate_failing"] += 1
            for f in rv.get("findings") or []:
                s["findings_total"] += 1
                if (f.get("severity") or "").upper() in _BLOCKING:
                    s["blocking_findings_total"] += 1
                    others = flagged_by.get(f.get("location"), set()) - {fam}
                    if not others:
                        s["unique_blocking"] += 1

    for s in stats.values():
        s["approve_rate"] = (s["approvals"] / s["reviews"]) if s["reviews"] else 0.0
    return stats


def render_report(cells: list["CellResult"]) -> str:
    """Render the full markdown report from the matrix. Sections:
      1. Per (agent × effort) aggregate over the whole project: total wall-clock
         (sum duration), total cost_usd, total tokens, cells, relaxed-pass count.
      2. Per-stack (react / go) routing tables: per-task best agent×effort by
         (relaxed_pass, fewest blocking, then cost, then duration).
      3. Reviewer evaluation (from evaluate_reviewers): per-reviewer approve_rate,
         gate-failing approvals, findings, unique-blocking.
      4. Provenance footer: harness version + per-agent model_id/cli_version seen.
    Pure function of `cells` (may call evaluate_reviewers). Returns markdown.
    """
    out: list[str] = ["# Bake-off report", ""]
    if not cells:
        out.append("_No cells._")
        return "\n".join(out)

    # 1. Per (agent × effort) aggregate over the whole project.
    out += ["## Aggregate by agent × effort", "",
            "| agent | effort | cells | relaxed-pass | cost_usd | tokens | duration_s |",
            "|---|---|--:|--:|--:|--:|--:|"]
    agg: dict[tuple[str, str], dict] = {}
    for c in cells:
        a = agg.setdefault((c.agent, c.effort), {
            "cells": 0, "relaxed": 0, "cost": 0.0, "tokens": 0, "dur": 0.0})
        a["cells"] += 1
        a["relaxed"] += 1 if c.relaxed_pass else 0
        a["cost"] += c.cost_usd
        a["tokens"] += c.input_tokens + c.output_tokens
        a["dur"] += c.duration_s
    for (agent, effort), a in sorted(agg.items()):
        out.append(f"| {agent} | {effort} | {a['cells']} | {a['relaxed']} | "
                   f"${a['cost']:.3f} | {a['tokens']} | {a['dur']:.0f} |")
    out.append("")

    # 2. Per-stack routing tables: per task, the best agent×effort cell by
    #    (relaxed_pass, fewest blocking, then cheaper, then faster).
    def _route_key(c: "CellResult") -> tuple:
        return (1 if c.relaxed_pass else 0, -c.blocking_findings,
                -c.cost_usd, -c.duration_s)
    by_stack: dict[str, dict[str, list["CellResult"]]] = {}
    for c in cells:
        by_stack.setdefault(c.stack, {}).setdefault(c.task_key, []).append(c)
    out += ["## Per-stack routing (recommended agent × effort per task)", ""]
    for stack in sorted(by_stack):
        out += [f"### stack: {stack}", "",
                "| task | best agent | effort | relaxed-pass | blocking | cost_usd | duration_s |",
                "|---|---|---|:--:|--:|--:|--:|"]
        for task_key in sorted(by_stack[stack]):
            best = max(by_stack[stack][task_key], key=_route_key)
            out.append(f"| {task_key} | {best.agent} | {best.effort} | "
                       f"{'yes' if best.relaxed_pass else 'no'} | "
                       f"{best.blocking_findings} | ${best.cost_usd:.3f} | "
                       f"{best.duration_s:.0f} |")
        out.append("")

    # 3. Reviewer evaluation (objective stats from evaluate_reviewers).
    out += ["## Reviewer evaluation", ""]
    rstats = evaluate_reviewers(cells)
    if rstats:
        out += ["| reviewer | reviews | approve_rate | gate-failing approvals | "
                "findings | blocking | unique-blocking |",
                "|---|--:|--:|--:|--:|--:|--:|"]
        for fam in sorted(rstats):
            s = rstats[fam]
            out.append(
                f"| {fam} | {s['reviews']} | {s['approve_rate']:.0%} | "
                f"{s['approvals_of_gate_failing']} | {s['findings_total']} | "
                f"{s['blocking_findings_total']} | {s['unique_blocking']} |")
    else:
        out.append("_No per-reviewer data persisted._")
    out.append("")

    # 4. Provenance footer.
    out += ["## Provenance", "", f"- harness version: {HARNESS_VERSION}"]
    seen: dict[str, set] = {}
    for c in cells:
        seen.setdefault(c.agent, set()).add((c.model_id or "?", c.cli_version or "?"))
    for agent in sorted(seen):
        combos = ", ".join(f"{m} / {v}" for m, v in sorted(seen[agent]))
        out.append(f"- {agent}: {combos}")
    return "\n".join(out)


def _git(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=str(cwd),
                          capture_output=True, text=True)


def _diff_against(base: str, wt: Path) -> str:
    return _git(["diff", f"{base}...HEAD"], wt).stdout


def _authoritative_panel_excluding(author: str,
                                   timeout_seconds: int) -> list[cfr.Reviewer]:
    """Default authoritative reviewers minus the authoring family (cut
    self-review bias). Grok is advisory-only so it's never in this set."""
    return [r for r in cfr.default_reviewers(timeout_seconds)
            if getattr(r, "family", None) != author]


def run_cell(
    *, task: plan_mod.Task, agent: str, base_ref: str, repo_root: Path,
    worktree_base: Path, test_command: str | None,
    run_id: str, financial_paths: str,
    claude_extra_args: list[str], claude_bin: str,
    task_timeout: int, gate_timeout: int, panel_timeout: int,
    log: Callable[[str], None],
) -> CellResult:
    """Run one (task, agent) cell end to end and return its scored result."""
    cell = CellResult(task_key=task.key, agent=agent)
    wt = worktree_base / f"bakeoff-{task.key}-{agent}"
    branch = f"bakeoff/{task.key}-{agent}"
    # Fresh worktree forked from the task's base ref.
    _git(["worktree", "remove", "--force", str(wt)], repo_root)
    _git(["branch", "-D", branch], repo_root)
    add = _git(["worktree", "add", "-b", branch, str(wt), base_ref], repo_root)
    if add.returncode != 0:
        cell.error = f"worktree add failed: {add.stderr.strip()[:200]}"
        return cell

    start = time.monotonic()
    try:
        summary_path = wt / ".bakeoff-summary.md"
        env = spawn_mod.build_env(
            task_key=task.key, summary_path=summary_path, run_id=run_id,
            max_iterations=1, financial_paths=financial_paths,
        )
        prompt = spawn_mod.build_prompt(
            task_key=task.key, task_summary=task.summary, task_type=task.type,
            task_labels=task.labels, task_description=task.description,
            branch=branch, summary_path=summary_path, run_id=run_id,
            max_iterations=1, financial_paths=financial_paths,
            skip_design=False, skip_security_linter=False, reviewer_count=None,
            agent=agent,
        )
        log(f"  [{task.key}/{agent}] spawning…")
        res = spawn_mod.spawn_agent(
            agent=agent, claude_bin=claude_bin, cwd=wt, env=env, prompt=prompt,
            model=None, extra_args=list(claude_extra_args),
            timeout_seconds=task_timeout,
        )
        cell.spawned = res.exit_code == 0
        if res.usage and res.usage.cost_usd is not None:
            cell.cost_usd = res.usage.cost_usd
            cell.cost_known = True
    except Exception as e:  # noqa: BLE001 — one bad cell must not sink the run
        cell.error = f"spawn raised: {e}"
        cell.duration_s = time.monotonic() - start
        return cell

    diff = _diff_against(base_ref, wt)
    cell.diff_lines = diff.count("\n")

    # Mechanical gate.
    if test_command:
        gate = mv.run_test_command(
            test_command, worktree=wt, timeout_seconds=gate_timeout, log=log)
        cell.gate_passed = gate.passed
    else:
        cell.gate_passed = True  # no gate configured → don't penalize

    # Cross-family panel (author excluded from its own jury).
    if diff.strip():
        try:
            summary_md = (summary_path.read_text() if summary_path.exists()
                          else f"# {task.key}\n**Status:** Done\n")
            panel = cfr.run_panel(
                ticket_key=task.key, ticket_summary=task.summary,
                summary_md=summary_md, diff=diff, branch=branch,
                base_branch=base_ref,
                reviewers=_authoritative_panel_excluding(agent, panel_timeout),
                log=log,
            )
            cell.panel_consensus = panel.consensus
            cell.blocking_findings = len(panel.blocking_findings)
        except Exception as e:  # noqa: BLE001
            cell.error = (cell.error or "") + f" panel raised: {e}"
    cell.duration_s = time.monotonic() - start
    log(f"  [{task.key}/{agent}] gate={'P' if cell.gate_passed else 'F'} "
        f"panel={cell.panel_consensus} blocking={cell.blocking_findings} "
        f"cost=${cell.cost_usd:.3f} {cell.duration_s:.0f}s")
    # Results (diff_lines, panel verdict, cost) are fully captured above; the
    # worktree is no longer needed. Remove it so a 28-cell run doesn't accumulate
    # 28 full monorepo checkouts. Best-effort — a leftover worktree is harmless.
    _git(["worktree", "remove", "--force", str(wt)], repo_root)
    _git(["branch", "-D", branch], repo_root)
    return cell


def recommend(cells: list[CellResult]) -> dict[str, str]:
    """Per task, the outcome-first winner (cost only breaks ties)."""
    by_task: dict[str, list[CellResult]] = {}
    for c in cells:
        by_task.setdefault(c.task_key, []).append(c)
    winners: dict[str, str] = {}
    for tk, cs in by_task.items():
        best = max(cs, key=lambda c: c.quality_key)
        winners[tk] = best.agent
    return winners


def render_markdown(cells: list[CellResult], winners: dict[str, str]) -> str:
    lines = ["# Agent bake-off results", "",
             "| Task | Agent | Gate | Panel | Blocking | Cost | Dur(s) | Winner |",
             "|------|-------|------|-------|----------|------|--------|--------|"]
    for c in sorted(cells, key=lambda x: (x.task_key, x.agent)):
        win = "✅" if winners.get(c.task_key) == c.agent else ""
        cost = f"${c.cost_usd:.3f}" + ("" if c.cost_known else "?")
        lines.append(
            f"| {c.task_key} | {c.agent} | {'pass' if c.gate_passed else 'FAIL'} "
            f"| {c.panel_consensus} | {c.blocking_findings} | {cost} "
            f"| {c.duration_s:.0f} | {win} |")
    lines += ["", "## Recommended routing (outcome-first, cost tiebreak)", ""]
    for tk, ag in sorted(winners.items()):
        lines.append(f"- `{tk}` → **{ag}**")
    return "\n".join(lines) + "\n"


def run_bakeoff(
    *, tasks_path: Path, base_ref: str, agents: tuple[str, ...] = ALL_AGENTS,
    only_keys: list[str] | None = None,
    base_overrides: dict[str, str] | None = None,
    test_command_override: str | None = None,
    repo_root: Path | None = None,
    worktree_base: Path | None = None, out_dir: Path | None = None,
    claude_extra_args: list[str] | None = None, claude_bin: str = "claude",
    task_timeout: int = 60 * 60, gate_timeout: int = 900,
    panel_timeout: int = 600, log: Callable[[str], None] = print,
) -> dict:
    """Run the matrix and write results incrementally. Returns the summary dict.

    base_ref is the default fork point; base_overrides maps task_key -> ref for
    tasks that need a different base (e.g. the skeleton task forks from main
    while body-fills fork from the skeleton+gate commit). Results are persisted
    to matrix.json after EVERY cell so a multi-hour run survives interruption.
    """
    from . import yaml_io
    tasks_path = Path(tasks_path)
    repo_root = repo_root or tasks_path.parent
    worktree_base = worktree_base or (repo_root.parent)
    out_dir = out_dir or (repo_root / "docs" / "runs" / "bakeoff")
    out_dir.mkdir(parents=True, exist_ok=True)
    base_overrides = base_overrides or {}
    doc = yaml_io.load(tasks_path)
    tasks = plan_mod.load_tasks(doc)
    if only_keys:
        tasks = [t for t in tasks if t.key in set(only_keys)]
    repo_test = repo_config_mod.load(repo_root).test
    fin = "apps/finance-domain/**"

    def _persist(cells: list[CellResult]) -> dict[str, str]:
        winners = recommend(cells)
        (out_dir / "matrix.json").write_text(json.dumps(
            {"cells": [c.to_dict() for c in cells], "winners": winners}, indent=2))
        (out_dir / "results.md").write_text(render_markdown(cells, winners))
        return winners

    cells: list[CellResult] = []
    total = len(tasks) * len(agents)
    for task in tasks:
        task_base = base_overrides.get(task.key, base_ref)
        for agent in agents:
            log(f"=== cell {len(cells)+1}/{total}: {task.key}/{agent} "
                f"(base {task_base[:12]}) ===")
            cells.append(run_cell(
                task=task, agent=agent, base_ref=task_base, repo_root=repo_root,
                worktree_base=worktree_base,
                test_command=test_command_override or repo_test,
                run_id="bakeoff", financial_paths=fin,
                claude_extra_args=claude_extra_args or [], claude_bin=claude_bin,
                task_timeout=task_timeout, gate_timeout=gate_timeout,
                panel_timeout=panel_timeout, log=log))
            _persist(cells)  # incremental: survive interruption

    winners = _persist(cells)
    log(f"bake-off complete: {len(cells)} cells -> {out_dir}/results.md")
    return {"cells": [c.to_dict() for c in cells], "winners": winners,
            "out_dir": str(out_dir)}
