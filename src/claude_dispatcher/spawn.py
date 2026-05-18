"""Spawn a Claude subprocess for one task.

The dispatcher invokes `claude` with:
  - cwd = the task's worktree
  - env = inherited env + dispatcher-contract vars (TASK_KEY, SUMMARY_PATH, ...)
  - prompt = the initial Tasker prompt naming the task

Returns the subprocess exit code and the SUMMARY_PATH where the Tasker wrote
its result. Mid-flight crashes are detected by missing or unreadable summary
files; the run.py orchestrator marks the task Blocked with reason
`session_exit_code_N` or `summary_missing`.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path


# Default prompt template handed to the Tasker. The Tasker reads .claude/workflow/roles/tasker.md
# from the worktree's checked-out tree (the refactored router) and proceeds from there.
TASKER_PROMPT_TEMPLATE = """\
Read the file `.claude/workflow/roles/tasker.md` and adopt the Tasker role.

You are running under the dispatcher. Environment vars are set:
- TASK_KEY={task_key}
- SUMMARY_PATH={summary_path}
- DISPATCHER_RUN_ID={run_id}
- MAX_ITERATIONS={max_iterations}
- FINANCIAL_PATHS={financial_paths}
{optional_env_lines}

Task to work on:
- Key:     {task_key}
- Summary: {task_summary}
- Type:    {task_type}
- Labels:  {task_labels}
- Branch:  {branch}

Description:
{task_description}

When you finish the session (Done, Blocked, or Escalated) write the summary file
to $SUMMARY_PATH in the format documented in tasker.md Phase 5. Do not print the
summary as a separate message — write it to the file only. After writing the
file the session is complete.
"""


@dataclass
class SpawnResult:
    exit_code: int
    summary_path: Path
    stdout: str
    stderr: str


def build_prompt(
    *,
    task_key: str,
    task_summary: str,
    task_type: str,
    task_labels: list[str],
    task_description: str,
    branch: str,
    summary_path: Path,
    run_id: str,
    max_iterations: int,
    financial_paths: str,
    skip_design: bool,
    skip_security_linter: bool,
    reviewer_count: int | None,
) -> str:
    """Render the prompt template for one task."""
    optional_lines = []
    if skip_design:
        optional_lines.append("- SKIP_DESIGN=1")
    if skip_security_linter:
        optional_lines.append("- SKIP_SECURITY_LINTER=1")
    if reviewer_count is not None:
        optional_lines.append(f"- REVIEWER_COUNT={reviewer_count}")
    return TASKER_PROMPT_TEMPLATE.format(
        task_key=task_key,
        summary_path=str(summary_path),
        run_id=run_id,
        max_iterations=max_iterations,
        financial_paths=financial_paths,
        optional_env_lines="\n".join(optional_lines),
        task_summary=task_summary,
        task_type=task_type,
        task_labels=", ".join(task_labels),
        branch=branch,
        task_description=task_description,
    )


def build_env(
    *,
    base_env: dict[str, str] | None = None,
    task_key: str,
    summary_path: Path,
    run_id: str,
    max_iterations: int,
    financial_paths: str,
    skip_design: bool = False,
    skip_security_linter: bool = False,
    reviewer_count: int | None = None,
) -> dict[str, str]:
    """Construct the env dict the Claude subprocess inherits."""
    env = dict(base_env if base_env is not None else os.environ)
    env["TASK_KEY"] = task_key
    env["SUMMARY_PATH"] = str(summary_path)
    env["DISPATCHER_RUN_ID"] = run_id
    env["MAX_ITERATIONS"] = str(max_iterations)
    env["FINANCIAL_PATHS"] = financial_paths
    if skip_design:
        env["SKIP_DESIGN"] = "1"
    if skip_security_linter:
        env["SKIP_SECURITY_LINTER"] = "1"
    if reviewer_count is not None:
        env["REVIEWER_COUNT"] = str(reviewer_count)
    return env


def spawn_claude(
    *,
    claude_bin: str,
    cwd: Path,
    env: dict[str, str],
    prompt: str,
    extra_args: list[str] | None = None,
    timeout_seconds: int = 60 * 60 * 4,
) -> SpawnResult:
    """Invoke `claude` with the prompt piped on stdin. Block until exit.

    Default invocation: `claude --print`. The Tasker reads its prompt from
    stdin (text format), the summary is written as a side effect to
    $SUMMARY_PATH, and stdout returns the final assistant message.

    For unattended runs, callers will typically want extra_args like
    `--permission-mode bypassPermissions` (or `--dangerously-skip-permissions`)
    plus `--allow-dangerously-skip-permissions` so the Tasker can run Bash,
    Edit, Read, and the Task tool without prompting. The dispatcher exposes
    this via `--claude-extra-args` on the CLI.

    Without those flags, a Tasker running under `claude --print` will stall
    on the first tool-use permission prompt. Confirmed against the local
    Claude Code build (`claude --help` lists --print and --permission-mode).
    """
    summary_path = Path(env["SUMMARY_PATH"])
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [claude_bin, "--print", *(extra_args or [])]
    proc = subprocess.run(
        cmd,
        input=prompt,
        capture_output=True,
        text=True,
        cwd=str(cwd),
        env=env,
        timeout=timeout_seconds,
    )
    return SpawnResult(
        exit_code=proc.returncode,
        summary_path=summary_path,
        stdout=proc.stdout,
        stderr=proc.stderr,
    )
