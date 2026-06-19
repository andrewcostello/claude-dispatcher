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
        }


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
