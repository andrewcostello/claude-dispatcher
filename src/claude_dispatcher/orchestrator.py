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

from . import auto_integrate as ai_mod
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
    base_branch: str = "main"
    # If True, after each Tasker reports Done with commits on its feat
    # branch, the dispatcher attempts to merge that branch into base_branch
    # before marking the row Done. Prevents the "fork-from-stale-base"
    # problem where sibling tasks fork from the same epic SHA and can't see
    # each other's work. See auto_integrate.py for the integration rules.
    auto_integrate: bool = False


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
    model: str | None = None


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

    # Resolve base_branch: CLI > YAML top-level > "main".
    if cfg.base_branch == "main":  # i.e., user didn't override on CLI
        yaml_base = (doc.get("base_branch") if isinstance(doc, dict) else None)
        if yaml_base:
            cfg.base_branch = str(yaml_base).strip()

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
                    model=t.model,
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
                    try:
                        _mark_blocked(cfg, key, reason=f"worker_exception: {e}")
                    except Exception as mark_err:
                        _log(log_path, f"  worker {key} _mark_blocked itself raised: {mark_err}")

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
    wt = wt_mod.create(repo_root, snap.key, branch,
                       base_branch=cfg.base_branch, base_path=cfg.worktree_base)
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
    # Per-task model override stacks on top of run-level --claude-extra-args.
    # `claude` processes flags left-to-right; appending --model at the END
    # means the per-task value wins if the run-level args also set --model.
    spawn_extra = list(cfg.claude_extra_args)
    if snap.model:
        spawn_extra.extend(["--model", snap.model])
    try:
        result = spawn_mod.spawn_claude(
            claude_bin=cfg.claude_bin,
            cwd=wt.path,
            env=env,
            prompt=prompt,
            extra_args=spawn_extra,
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

    # If the Tasker reported Done (or any terminal-success status) but the
    # branch has no commits beyond base_branch, the work is uncommitted in
    # the worktree. This is recoverable: re-prompt the Tasker to commit
    # (NOT a Block — it's a "forgot to commit" mistake, fixable with one
    # corrective spawn). Max 1 commit-retry; if commits still missing
    # after, only then is this a real failure.
    if (s.status == "Done"
            and not _has_commits_on_branch(wt, cfg.base_branch, log_path, snap.key)):
        _log(log_path, f"  {snap.key} reported Done but no commits on branch — retrying with commit-only prompt")
        retry_status = _retry_for_commit(
            cfg, snap, wt, summary_path, env, log_path,
        )
        if retry_status is None:
            # Retry failed — really no work. Mark Blocked with clear reason.
            _mark_blocked(cfg, snap.key,
                          reason="no commits produced after commit-retry; Tasker spawn 2x failed to commit")
            return plan_mod.BLOCKED
        # Retry succeeded — re-parse summary and continue with Done flow.
        s = summary_mod.parse(result.summary_path)
        if s.malformed:
            _mark_blocked(cfg, snap.key,
                          reason=f"summary_malformed after commit retry: {s.malformed_reason}")
            return plan_mod.BLOCKED

    # Awaiting-human-approval handling — supervised may raise the PR.
    final_status, final_url, final_blocked_reason = _resolve_summary(
        cfg, snap, s, wt, log_path
    )

    # Auto-integrate: if the Tasker landed work and the run config asks for
    # auto-integration, merge feat → base_branch BEFORE we flip the YAML
    # status to Done. The status flip is what makes a task's row visible to
    # the dispatcher's runnable check, so dependents only become eligible
    # AFTER the base_branch advance. Auto-integration only fires for the
    # "Done" terminal; Blocked / Escalated tasks are out of scope (the
    # Tasker hasn't produced work to integrate).
    integrate_result: ai_mod.IntegrateResult | None = None
    if cfg.auto_integrate and final_status == "Done":
        try:
            integrate_result = ai_mod.integrate(
                repo_root=repo_root,
                yaml_path=cfg.tasks_path,
                base_branch=cfg.base_branch,
                feat_branch=branch,
                task_key=snap.key,
                log=lambda m: _log(log_path, m),
                enabled=True,
            )
        except Exception as e:
            _log(log_path, f"  {snap.key} auto-integrate raised: {e}")
            integrate_result = ai_mod.IntegrateResult(
                status="error", detail=f"exception: {e}",
            )
        # If integration failed in a way that means dependents shouldn't
        # proceed, flip status to Blocked so the dispatch loop holds. The
        # Tasker's work isn't lost — its commits are still on the feat
        # branch and the row records the failure reason for human triage.
        if integrate_result.status not in (
            "integrated", "skipped-disabled", "skipped-already-on",
            "skipped-no-commits",
        ):
            _log(log_path,
                 f"  {snap.key} auto-integrate {integrate_result.status}: "
                 f"flipping status from Done → Blocked")
            final_status = plan_mod.BLOCKED
            final_blocked_reason = (
                f"auto_integrate_{integrate_result.status}: "
                f"{integrate_result.detail[:300]}"
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
        # Stamp the auto-integrate outcome for forensic + later sweep.
        if integrate_result is not None:
            row["auto_integrate_status"] = integrate_result.status
            if integrate_result.merge_sha:
                row["auto_integrate_merge_sha"] = integrate_result.merge_sha
            if integrate_result.services_built:
                row["auto_integrate_services"] = list(
                    integrate_result.services_built
                )
            if integrate_result.detail and integrate_result.status not in (
                "integrated", "skipped-disabled", "skipped-already-on",
                "skipped-no-commits",
            ):
                row["auto_integrate_detail"] = integrate_result.detail[:500]
        # Stamp per-task token/cost usage from the Claude CLI's JSON output.
        # All optional — if --output-format=json wasn't honored or parsing
        # failed, the SpawnUsage fields are None and we skip writing them.
        u = result.usage
        if u.cost_usd is not None:
            row["cost_usd"] = u.cost_usd
        if u.input_tokens is not None:
            row["input_tokens"] = u.input_tokens
        if u.output_tokens is not None:
            row["output_tokens"] = u.output_tokens
        if u.cache_read_input_tokens is not None:
            row["cache_read_input_tokens"] = u.cache_read_input_tokens
        if u.cache_creation_input_tokens is not None:
            row["cache_creation_input_tokens"] = u.cache_creation_input_tokens
        if u.duration_ms is not None:
            row["duration_ms"] = u.duration_ms
        if u.num_turns is not None:
            row["num_turns"] = u.num_turns
        if u.model is not None:
            row["model"] = u.model

    _mutate_row(cfg, snap.key, _apply)
    return final_status


def _has_commits_on_branch(wt: wt_mod.Worktree, base_branch: str,
                            log_path: Path, task_key: str) -> bool:
    """True iff the worktree's branch has any commit beyond `base_branch`.

    Used to detect the "Tasker reported Done but forgot to commit" failure
    mode. We don't care HOW many commits — just that at least one exists,
    which proves the Tasker actually did `git commit` instead of leaving
    work uncommitted in the worktree.
    """
    import subprocess
    try:
        proc = subprocess.run(
            ["git", "rev-list", "--count", f"{base_branch}..HEAD"],
            cwd=str(wt.path), capture_output=True, text=True, check=False, timeout=30,
        )
    except Exception as e:
        _log(log_path, f"  {task_key} commit check failed (treating as no-commits): {e}")
        return False
    if proc.returncode != 0:
        _log(log_path, f"  {task_key} `git rev-list` exit={proc.returncode}: {proc.stderr.strip()}")
        return False
    count = (proc.stdout or "").strip()
    try:
        return int(count) > 0
    except ValueError:
        return False


_COMMIT_RETRY_PROMPT_PREFIX = """\
Your previous run on this task reported `Status: Done` in the summary file
but produced ZERO commits on this branch. The work files exist in the
worktree but have not been `git commit`ed.

This is a recoverable mistake — the work is right there, just uncommitted.

Please do ONLY these steps. Do NOT redo the implementation or analysis:

1. Run `git status` to see exactly what's uncommitted in this worktree.
2. Run `git add <files>` for the files that should be tracked (review
   the list — don't blindly `git add -A` if there are stray build
   artifacts you don't want committed).
3. Run `git commit -m "<message>"` with a conventional-commit message
   following the project's CLAUDE.md commit format: `type(scope): summary`.
   For BSA tickets, include `[<TASK_KEY>]` in the subject line. No author
   attribution (no Co-Authored-By, no "Generated with").
4. Verify with `git log --oneline {base_branch}..HEAD` that your commit
   is on the branch.
5. Update the summary file at $SUMMARY_PATH so its "Files changed"
   section reflects the actual committed files (run `git diff --name-only
   {base_branch}..HEAD` to get the list). Status stays `Done`.

The dispatcher will verify commits exist before accepting Done this time.
If you still produce no commits, the task will be Blocked.

Task context (for reference, do NOT redo):
"""


def _retry_for_commit(cfg: RunConfig, snap: TaskSnapshot, wt: wt_mod.Worktree,
                      summary_path: Path, env: dict, log_path: Path) -> str | None:
    """Re-spawn the Tasker with a corrective prompt asking only for the
    missing commit. Returns the spawn result's exit-code-based outcome
    or None if the retry left no commits.
    """
    prompt = _COMMIT_RETRY_PROMPT_PREFIX.format(base_branch=cfg.base_branch)
    prompt += spawn_mod.build_prompt(
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
    retry_extra = list(cfg.claude_extra_args)
    if snap.model:
        retry_extra.extend(["--model", snap.model])
    try:
        result = spawn_mod.spawn_claude(
            claude_bin=cfg.claude_bin, cwd=wt.path, env=env, prompt=prompt,
            extra_args=retry_extra,
        )
    except Exception as e:
        _log(log_path, f"  {snap.key} commit-retry spawn failed: {e}")
        return None
    _log(log_path, f"  {snap.key} commit-retry exited code={result.exit_code}")
    if not _has_commits_on_branch(wt, cfg.base_branch, log_path, snap.key):
        return None
    return "retried_ok"


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


def _mutate_row(cfg: RunConfig, task_key: str, mutator) -> bool:
    """Acquire the FileLock, load the YAML, find the row by key, apply
    `mutator(row)`, save. The mutator is called with the row's ruamel mapping.

    Returns True if the row was found and mutated, False if no row matched
    `task_key`. A missing row is logged to stderr but is NOT fatal -- the
    YAML may have been edited externally between plan-load and write, and
    crashing the dispatcher because a status flip can't land is a worse
    outcome than letting the run continue.
    """
    with yaml_io.FileLock(cfg.tasks_path):
        doc = yaml_io.load(cfg.tasks_path)
        for row in doc.get("tasks", []):
            if str(row.get("key")) == task_key:
                mutator(row)
                yaml_io.dump(doc, cfg.tasks_path)
                return True
        sys.stderr.write(
            f"warning: _mutate_row: task {task_key!r} not in YAML at write time "
            f"(skipping status flip; YAML may have been edited mid-run)\n"
        )
        return False


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
    # CLI base_branch wins if explicitly set; else fall back to "main" here
    # and let execute() check the YAML's top-level before final resolution.
    cli_base = getattr(args, "base_branch", None)
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
        base_branch=cli_base if cli_base else "main",
        auto_integrate=getattr(args, "auto_integrate", False),
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
