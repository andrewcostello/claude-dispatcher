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

import json
import os
import subprocess
from dataclasses import dataclass, field
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
class SpawnUsage:
    """Per-task resource usage extracted from the Claude CLI's JSON output.

    All fields default to None so the dispatcher can still operate when the
    Claude CLI is invoked without --output-format=json, or when the JSON
    parsing fails (older builds, unexpected schema drift).

    `cost_usd` is the canonical-comparison metric. Token counts are kept for
    drill-down: cache_read is free-ish (no API charge), cache_creation costs
    extra on first write, input/output are the standard rates. The model
    name + duration let downstream tooling compare per-model and per-strategy.
    """
    cost_usd: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cache_read_input_tokens: int | None = None
    cache_creation_input_tokens: int | None = None
    duration_ms: int | None = None
    duration_api_ms: int | None = None
    ttft_ms: int | None = None
    num_turns: int | None = None
    model: str | None = None
    session_id: str | None = None


@dataclass
class SpawnResult:
    exit_code: int
    summary_path: Path
    stdout: str
    stderr: str
    usage: SpawnUsage = field(default_factory=SpawnUsage)


def parse_usage_from_json(stdout: str) -> SpawnUsage:
    """Pull usage data out of a Claude CLI `--output-format=json` blob.

    Returns a SpawnUsage with whatever fields parsed successfully. Empty
    SpawnUsage on any error — the dispatcher's runtime path doesn't care
    about token data, only the reporting layer does. Resilient by design.
    """
    if not stdout or not stdout.strip():
        return SpawnUsage()
    try:
        # The CLI emits one JSON object per `--print --output-format=json` call.
        # `stream-json` is different (line-delimited stream of events); we
        # don't use that mode.
        doc = json.loads(stdout.strip())
    except (json.JSONDecodeError, ValueError):
        return SpawnUsage()
    if not isinstance(doc, dict):
        return SpawnUsage()

    usage_obj = doc.get("usage") or {}
    model_usage = doc.get("modelUsage") or {}
    # modelUsage is keyed by model id; for a single-model run there's one key.
    primary_model = next(iter(model_usage), None) if model_usage else None

    def _int(v):
        try:
            return int(v) if v is not None else None
        except (TypeError, ValueError):
            return None

    def _float(v):
        try:
            return float(v) if v is not None else None
        except (TypeError, ValueError):
            return None

    return SpawnUsage(
        cost_usd=_float(doc.get("total_cost_usd")),
        input_tokens=_int(usage_obj.get("input_tokens")),
        output_tokens=_int(usage_obj.get("output_tokens")),
        cache_read_input_tokens=_int(usage_obj.get("cache_read_input_tokens")),
        cache_creation_input_tokens=_int(usage_obj.get("cache_creation_input_tokens")),
        duration_ms=_int(doc.get("duration_ms")),
        duration_api_ms=_int(doc.get("duration_api_ms")),
        ttft_ms=_int(doc.get("ttft_ms")),
        num_turns=_int(doc.get("num_turns")),
        model=primary_model,
        session_id=doc.get("session_id"),
    )


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
    # --output-format=json gives the dispatcher per-task token/cost usage
    # (total_cost_usd, input/output/cache tokens, duration_ms, num_turns).
    # The Tasker still writes its summary to $SUMMARY_PATH; the JSON output
    # on stdout is the wrapper around the final assistant message + metadata.
    # If a caller's extra_args already specifies --output-format, theirs wins
    # (we don't try to dedupe — `claude` will reject duplicate flags loudly).
    cmd = [claude_bin, "--print", "--output-format", "json",
           *(extra_args or [])]
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
        usage=parse_usage_from_json(proc.stdout),
    )
