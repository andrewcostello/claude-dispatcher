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

from . import plan as plan_mod
from . import pr as pr_mod
from . import spawn as spawn_mod
from . import summary as summary_mod
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


# --- entry point -----------------------------------------------------------


def execute(args: argparse.Namespace) -> int:
    """Live-spawn entry point. Returns 0 on clean exit (all done), 1 on partial
    completion (some Blocked/Escalated), 2 on validation error.
    """
    cfg = _build_config(args)
    doc = yaml_io.load(cfg.tasks_path)
    try:
        plan_mod.load_tasks(doc)  # validate
    except plan_mod.ValidationError as e:
        print(f"error: invalid tasks YAML: {e}", file=sys.stderr)
        return 2

    run_dir = cfg.runs_dir / cfg.run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    log_path = run_dir / "run.log"
    _log(log_path, f"start run {cfg.run_id} mode={cfg.mode} max_parallel={cfg.max_parallel}")

    repo_root = wt_mod.detect_repo_root(cfg.tasks_path.parent)

    in_flight: dict[Future[str], str] = {}
    with ThreadPoolExecutor(max_workers=max(cfg.max_parallel, 1)) as exe:
        while True:
            tasks = _load_tasks_snapshot(cfg)
            runnable = plan_mod.runnable_now(tasks)
            runnable = plan_mod.filter_tasks(runnable, cfg.label_filter, cfg.only_keys)
            # Don't re-dispatch tasks already mid-flight.
            in_flight_keys = set(in_flight.values())
            runnable = [t for t in runnable if t.key not in in_flight_keys]

            # Dispatch up to remaining capacity.
            while runnable and len(in_flight) < cfg.max_parallel:
                t = runnable.pop(0)
                snap = TaskSnapshot(
                    key=t.key,
                    summary=t.summary,
                    description=t.description,
                    type=t.type,
                    labels=list(t.labels),
                )
                # Mark In Progress on the YAML BEFORE submit. If we submit
                # first, the main thread could re-load and re-dispatch the
                # same key before the worker has stamped In Progress.
                _mark_in_progress(cfg, snap, run_dir)
                fut = exe.submit(_run_task, snap, cfg, run_dir, log_path, repo_root)
                in_flight[fut] = snap.key
                _log(log_path, f"dispatch {snap.key} submitted")

            if not in_flight:
                break  # nothing running, nothing to start

            done, _pending = wait(list(in_flight), return_when=FIRST_COMPLETED)
            for fut in done:
                key = in_flight.pop(fut)
                try:
                    fut.result()  # propagate exceptions
                except Exception as e:
                    _log(log_path, f"  worker {key} raised: {e}")
                    _mark_blocked(cfg, key, reason=f"worker_exception: {e}")

    tasks = _load_tasks_snapshot(cfg)
    blocked = [t for t in tasks if t.status == plan_mod.BLOCKED]
    escalated = [t for t in tasks if t.status == plan_mod.ESCALATED]
    _log(log_path, f"end run blocked={len(blocked)} escalated={len(escalated)}")
    return 1 if (blocked or escalated) else 0


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
    wt = wt_mod.create(repo_root, snap.key, branch, base_path=cfg.worktree_base)
    _log(log_path, f"  {snap.key} worktree at {wt.path} branch {wt.branch}")

    summary_path = run_dir / snap.key / "summary.md"
    summary_path.parent.mkdir(parents=True, exist_ok=True)

    # Stamp branch + summary_path on the row (started_at already set by main thread).
    _mutate_row(cfg, snap.key, lambda r: r.update({
        "branch": branch,
        "summary_path": str(summary_path),
    }))

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
    try:
        result = spawn_mod.spawn_claude(
            claude_bin=cfg.claude_bin,
            cwd=wt.path,
            env=env,
            prompt=prompt,
            extra_args=cfg.claude_extra_args,
        )
    except Exception as e:
        _log(log_path, f"  {snap.key} spawn failed: {e}")
        _mark_blocked(cfg, snap.key, reason=f"spawn_failed: {e}")
        return plan_mod.BLOCKED

    _log(log_path, f"  {snap.key} spawn exited code={result.exit_code}")
    if result.exit_code != 0:
        _mark_blocked(cfg, snap.key, reason=f"session_exit_code_{result.exit_code}")
        return plan_mod.BLOCKED

    if not result.summary_path.exists():
        _mark_blocked(cfg, snap.key, reason="summary_missing")
        return plan_mod.BLOCKED

    s = summary_mod.parse(result.summary_path)
    if s.malformed:
        _mark_blocked(cfg, snap.key, reason=f"summary_malformed: {s.malformed_reason}")
        return plan_mod.BLOCKED

    # Awaiting-human-approval handling — supervised may raise the PR.
    final_status, final_url, final_blocked_reason = _resolve_summary(
        cfg, snap, s, wt, log_path
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
        if final_blocked_reason:
            row["blocked_reason"] = final_blocked_reason
        if s.prepared_pr_title:
            row["prepared_pr_title"] = s.prepared_pr_title
        if s.prepared_pr_branch:
            row["prepared_pr_branch"] = s.prepared_pr_branch

    _mutate_row(cfg, snap.key, _apply)
    return final_status


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

    # Awaiting human PR approval.
    if cfg.mode == "unattended":
        _log(log_path, f"  {snap.key} awaiting human PR approval — left Blocked")
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
            return plan_mod.DONE, result.url, None
        _log(log_path, f"  {snap.key} gh pr create failed: {result.error}")
        return plan_mod.BLOCKED, None, f"gh pr create failed: {result.error}"
    if decision == "reject":
        _log(log_path, f"  {snap.key} human rejected PR")
        return plan_mod.BLOCKED, None, "human rejected PR"
    _log(log_path, f"  {snap.key} human skipped PR approval")
    return plan_mod.BLOCKED, None, "human skipped PR approval"


# --- YAML mutation helpers -------------------------------------------------


def _mutate_row(cfg: RunConfig, task_key: str, mutator) -> None:
    """Acquire the FileLock, load the YAML, find the row by key, apply
    `mutator(row)`, save. The mutator is called with the row's ruamel mapping.
    """
    with yaml_io.FileLock(cfg.tasks_path):
        doc = yaml_io.load(cfg.tasks_path)
        for row in doc.get("tasks", []):
            if str(row.get("key")) == task_key:
                mutator(row)
                break
        else:
            raise KeyError(f"task {task_key!r} not in YAML at write time")
        yaml_io.dump(doc, cfg.tasks_path)


def _mark_in_progress(cfg: RunConfig, snap: TaskSnapshot, run_dir: Path) -> None:
    summary_path = run_dir / snap.key / "summary.md"

    def _apply(row):
        row["status"] = plan_mod.IN_PROGRESS
        row["started_at"] = _now_iso()
        row["dispatcher_run_id"] = cfg.run_id
        row["summary_path"] = str(summary_path)

    _mutate_row(cfg, snap.key, _apply)


def _mark_blocked(cfg: RunConfig, task_key: str, *, reason: str) -> None:
    def _apply(row):
        row["status"] = plan_mod.BLOCKED
        row["completed_at"] = _now_iso()
        row["blocked_reason"] = reason

    _mutate_row(cfg, task_key, _apply)


# --- misc helpers -----------------------------------------------------------


def _build_config(args: argparse.Namespace) -> RunConfig:
    extra = getattr(args, "claude_extra_args", "") or ""
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


def _load_tasks_snapshot(cfg: RunConfig) -> list[plan_mod.Task]:
    """Acquire the lock, load the YAML, parse into Task list, release.

    The Task objects' .raw fields point at the loaded doc — when the next
    snapshot is taken, the previous doc is garbage-collected. No mutation
    of .raw happens from main-thread code paths.
    """
    with yaml_io.FileLock(cfg.tasks_path):
        doc = yaml_io.load(cfg.tasks_path)
    return plan_mod.load_tasks(doc)


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
