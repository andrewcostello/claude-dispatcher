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
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path

from . import endpoint_agents as endpoint_agents_mod


# Agent identity stamped onto every terminal task row + terminal journal
# event (OPS-4). The dispatcher only spawns the Claude CLI today; if other
# agents are ever supported this becomes per-config.
AGENT_NAME = "claude"


def effective_model_for_agent(
    agent: str | None,
    model: str | None,
    *,
    log=None,
    task_key: str | None = None,
) -> str | None:
    """Return a model pin safe to pass to ``agent``'s CLI.

    Claude-shaped pins (``claude-*``, strings containing ``claude``) are
    dropped for non-Claude families so YAML written for Claude does not break
    grok/codex/agy retries and verifiers.
    """
    if not model:
        return None
    a = (agent or "claude").strip().lower() or "claude"
    if a == "claude":
        return model
    if "claude" in str(model).lower():
        if log:
            key = task_key or "?"
            log(f"  {key} ignoring Claude model pin {model!r} for agent={a}")
        return None
    return model


def capture_agent_version(claude_bin: str, timeout_seconds: int = 30) -> str | None:
    """Run `<claude_bin> --version` once and return its version line.

    Returns the first non-empty line of stdout, stripped, when the binary
    exits 0 with non-empty output. On ANY failure — missing binary, timeout,
    non-zero exit, empty output, unexpected exception — emits a single
    stderr warning and returns None. Contractually non-raising: version
    provenance is nice-to-have metadata and must never block a run.
    """
    try:
        proc = subprocess.run(
            [claude_bin, "--version"],
            # CRITICAL: the claude CLI (and the fake_claude fixture) reads
            # stdin; without DEVNULL this call would hang on an open pipe.
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except Exception as e:  # noqa: BLE001 — degrade-to-absent by contract
        print(
            f"warning: agent version capture failed for {claude_bin!r}: {e}",
            file=sys.stderr,
        )
        return None
    if proc.returncode != 0:
        print(
            f"warning: agent version capture failed for {claude_bin!r}: "
            f"exit code {proc.returncode}",
            file=sys.stderr,
        )
        return None
    for line in (proc.stdout or "").splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    print(
        f"warning: agent version capture failed for {claude_bin!r}: "
        "empty --version output",
        file=sys.stderr,
    )
    return None


# Unified implementer brief for EVERY family under `dispatcher run` (claude,
# codex, grok, gemini). The dispatcher is the sole orchestrator — agents do
# not adopt Tasker, dispatch sub-reviewers, or raise PRs. Interactive
# Tasker (`tasker.md`) remains for non-dispatch Claude/Grok sessions only.
#
# Optional env/context lines (SKIP_*, REVIEWER_COUNT) are informational for
# agents that still honor them; the dispatcher owns verification and panel.
IMPLEMENTER_PROMPT_TEMPLATE = """\
You are an autonomous implementer agent under the dispatcher (agent family:
{agent}). Work only in the CURRENT WORKING DIRECTORY.

You are a WORKER, not an orchestrator. The dispatcher owns worktrees, gates,
review panels, PRs, and merges. Do NOT adopt a Tasker role, spawn reviewer
subagents, or open pull requests.

## Dispatcher context
- TASK_KEY={task_key}
- SUMMARY_PATH={summary_path}
- DISPATCHER_RUN_ID={run_id}
- MAX_ITERATIONS={max_iterations}
- FINANCIAL_PATHS={financial_paths}
{optional_env_lines}

## Task
- Key:     {task_key}
- Summary: {task_summary}
- Type:    {task_type}
- Labels:  {task_labels}
- Branch:  {branch}

## Description
{task_description}

## Instructions
1. Make the minimum code changes that fully satisfy the task description.
2. Prefer existing patterns and public seams in this repo; do not redesign
   architecture unless the task explicitly requires it.
3. Run the most relevant tests you can; fix failures you introduce.
4. Commit your work to the current branch with a conventional-commit message
   (`type(scope): summary`, include [{task_key}] in the subject). Do NOT push
   and do NOT open a PR — the dispatcher integrates. If your environment
   cannot run `git commit`, leave the changes in the working tree and the
   dispatcher will commit them for you.
5. When finished, write a short markdown summary ONLY to this path:
   {summary_path}

## Summary format (required)
```
# {task_key}: implementation
**Status:** Done

## What landed
- concrete bullet list of changes (files + behavior)

## Tests
- what you ran and the result, or "not run: <reason>"
```

SUMMARY CONTRACT (the single most common dispatch failure is skipping this):
BEFORE starting the work, create the summary file above with this skeleton and
`**Status:** Blocked` as a placeholder. Update it as you work and finalize it
(Done or Blocked) as your LAST action. A session that ends without a parseable
summary blocks the whole task and burns a retry — writing the skeleton first
makes that impossible. Do not print the summary as a chat message — write it
to the file only.

Use `**Status:** Blocked` instead of Done if you cannot complete the task, and
add an `## Escalation reason` section explaining why.
"""

# Back-compat aliases (tests / older imports).
CROSS_FAMILY_IMPLEMENTER_PROMPT = IMPLEMENTER_PROMPT_TEMPLATE
TASKER_PROMPT_TEMPLATE = IMPLEMENTER_PROMPT_TEMPLATE


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


def _coerce_int(v) -> int | None:
    try:
        return int(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _coerce_float(v) -> float | None:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


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

    return SpawnUsage(
        cost_usd=_coerce_float(doc.get("total_cost_usd")),
        input_tokens=_coerce_int(usage_obj.get("input_tokens")),
        output_tokens=_coerce_int(usage_obj.get("output_tokens")),
        cache_read_input_tokens=_coerce_int(usage_obj.get("cache_read_input_tokens")),
        cache_creation_input_tokens=_coerce_int(
            usage_obj.get("cache_creation_input_tokens")),
        duration_ms=_coerce_int(doc.get("duration_ms")),
        duration_api_ms=_coerce_int(doc.get("duration_api_ms")),
        ttft_ms=_coerce_int(doc.get("ttft_ms")),
        num_turns=_coerce_int(doc.get("num_turns")),
        model=primary_model,
        session_id=doc.get("session_id"),
    )


def parse_grok_usage(stdout: str) -> SpawnUsage:
    """Best-effort usage extract from `grok --output-format json` stdout.

    Grok's JSON envelope has varied across CLI versions. We accept:
      * a single JSON object (whole stdout)
      * NDJSON / last JSON object on stdout
    and look for usage under common keys (usage, token_usage, tokens,
    total_cost_usd, cost_usd, model, num_turns / turns). Never raises.
    """
    if not stdout or not stdout.strip():
        return SpawnUsage()

    doc: dict | None = None
    text = stdout.strip()
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            doc = parsed
    except (json.JSONDecodeError, ValueError):
        # Try last non-empty line as NDJSON tail.
        for line in reversed(text.splitlines()):
            line = line.strip()
            if not line or not line.startswith("{"):
                continue
            try:
                parsed = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue
            if isinstance(parsed, dict):
                doc = parsed
                break
    if not doc:
        return SpawnUsage()

    usage_obj = {}
    for key in ("usage", "token_usage", "tokens", "tokenUsage"):
        cand = doc.get(key)
        if isinstance(cand, dict):
            usage_obj = cand
            break

    return SpawnUsage(
        cost_usd=_coerce_float(
            doc.get("total_cost_usd", doc.get("cost_usd", usage_obj.get("cost_usd")))
        ),
        input_tokens=_coerce_int(
            usage_obj.get("input_tokens", usage_obj.get("prompt_tokens",
                          usage_obj.get("input")))
        ),
        output_tokens=_coerce_int(
            usage_obj.get("output_tokens", usage_obj.get("completion_tokens",
                          usage_obj.get("output")))
        ),
        cache_read_input_tokens=_coerce_int(
            usage_obj.get("cache_read_input_tokens", usage_obj.get("cached_tokens"))
        ),
        duration_ms=_coerce_int(doc.get("duration_ms", doc.get("durationMs"))),
        num_turns=_coerce_int(doc.get("num_turns", doc.get("turns"))),
        model=doc.get("model") or usage_obj.get("model"),
        session_id=doc.get("session_id") or doc.get("sessionId"),
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
    agent: str | None = None,
) -> str:
    """Render the unified implementer prompt for one task.

    Single-orchestrator rule: every agent family (including Claude) gets the
    same implementer worker brief. No family is asked to adopt tasker.md
    under ``dispatcher run``.
    """
    agent_name = (agent or "claude").strip().lower() or "claude"
    optional_lines = []
    if skip_design:
        optional_lines.append("- SKIP_DESIGN=1")
    if skip_security_linter:
        optional_lines.append("- SKIP_SECURITY_LINTER=1")
    if reviewer_count is not None:
        optional_lines.append(f"- REVIEWER_COUNT={reviewer_count}")
    optional_env = "\n".join(optional_lines)
    if optional_env:
        optional_env = optional_env + "\n"
    return IMPLEMENTER_PROMPT_TEMPLATE.format(
        agent=agent_name,
        task_key=task_key,
        summary_path=str(summary_path),
        run_id=run_id,
        max_iterations=max_iterations,
        financial_paths=financial_paths,
        optional_env_lines=optional_env,
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


def summarize_transcript_haiku(
    text: str, *, claude_bin: str = "claude",
    model: str = "claude-haiku-4-5-20251001", timeout_seconds: int = 120,
) -> str | None:
    """Cheap haiku summary of an agent run's captured output for the audit log
    (step 6). Best-effort: returns the summary text, or None on any failure
    (empty input, timeout, non-zero exit) — never raises, so it cannot block a
    task. Uses the cheapest model; only the last ~12k chars are summarized."""
    if not text or not text.strip():
        return None
    prompt = (
        "Summarize this dispatcher agent run in 3-6 terse bullets: what it "
        "changed, the key decisions it made, and how it ended (Done/Blocked). "
        "No preamble, just the bullets.\n\n" + text[-12000:]
    )
    try:
        proc = subprocess.run(
            [claude_bin, "--print", "--model", model],
            input=prompt, capture_output=True, text=True, timeout=timeout_seconds,
            # subscription, not metered (mirror spawn_claude's cost default)
            env={k: v for k, v in os.environ.items()
                 if k not in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")},
        )
    except Exception:  # noqa: BLE001 — audit nicety must never break a run
        return None
    if proc.returncode != 0:
        return None
    out = proc.stdout.strip()
    return out or None


def spawn_claude(
    *,
    claude_bin: str,
    cwd: Path,
    env: dict[str, str],
    prompt: str,
    extra_args: list[str] | None = None,
    timeout_seconds: int = 60 * 60 * 4,
    metered: bool = False,
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
    # Cost control: default to the Claude Code SUBSCRIPTION (included tokens),
    # not the metered Anthropic API. Strip ANTHROPIC_API_KEY/AUTH_TOKEN so the
    # `claude` CLI falls back to the logged-in subscription. The cost_policy
    # overflow (run.py) passes metered=True to deliberately bill the metered API.
    run_env = dict(env)
    if not metered:
        run_env.pop("ANTHROPIC_API_KEY", None)
        run_env.pop("ANTHROPIC_AUTH_TOKEN", None)
    proc = subprocess.run(
        cmd,
        input=prompt,
        capture_output=True,
        text=True,
        cwd=str(cwd),
        env=run_env,
        timeout=timeout_seconds,
    )
    return SpawnResult(
        exit_code=proc.returncode,
        summary_path=summary_path,
        stdout=proc.stdout,
        stderr=proc.stderr,
        usage=parse_usage_from_json(proc.stdout),
    )


# ---------------------------------------------------------------------------
# Cross-family implementer agents (codex / grok / gemini).
#
# Each runs its CLI's HEADLESS AGENTIC mode in the task worktree to EDIT files.
# Three hard-won invariants from the 2026-06-18 feasibility smoke test:
#   1. stdin MUST be closed (DEVNULL). codex `exec` and `agy --print` both
#      block forever waiting for stdin EOF when the parent leaves it open.
#   2. The agent EDITS but the dispatcher COMMITS. codex's
#      `--sandbox workspace-write` mounts .git read-only, so it cannot commit;
#      grok self-commits; agy doesn't. A uniform post-run auto-commit of the
#      dirty worktree covers every agent identically.
#   3. They will NOT reliably write $SUMMARY_PATH in the parser's format, so
#      the adapter synthesizes a guaranteed-parseable summary when absent.
# The "gemini" agent maps to the `agy` CLI (Antigravity) — the authenticated
# Google coding CLI here; the `gemini` CLI itself fails refreshAuth headless.
# ---------------------------------------------------------------------------

AGENT_BINS: dict[str, str] = {"codex": "codex", "grok": "grok", "gemini": "agy"}


def agent_bin_name(agent: str | None) -> str:
    """Resolve CLI binary name for an implementer/verifier/design family.

    gemini → agy; claude/None → claude; others pass through.
    """
    a = (agent or "claude").strip().lower() or "claude"
    if a == "claude":
        return "claude"
    return AGENT_BINS.get(a, a)


# ---------------------------------------------------------------------------
# agy (Antigravity CLI) model selection.
#
# agy does NOT accept a model at launch — `--model` is silently ignored. It
# reads its active engine from a single global settings.json (`.model` key),
# defaulting to "Gemini 3.5 Flash (Medium)". To run a chosen engine in a
# non-interactive loop we mutate that file BEFORE spawning agy.
#
# Because settings.json is a global singleton, two concurrent agy spawns with
# DIFFERENT models would clobber each other's setting. `_AgyModelGate`
# enforces the invariant "all live agy processes agree on the model": any
# number of SAME-model spawns run concurrently; a DIFFERENT-model spawn waits
# until the current cohort drains before it rewrites the file and proceeds.
#
# The dispatcher's per-task `model` value for a gemini task must be one of the
# exact agy engine strings, e.g. "Gemini 3.1 Pro (High)", "Gemini 3.5 Flash
# (Medium)", "Claude Opus 4.6 (Thinking)". A None model leaves settings.json
# untouched (agy runs whatever is on disk) and forms its own cohort.
# ---------------------------------------------------------------------------

AGY_SETTINGS_PATH = Path.home() / ".gemini" / "antigravity-cli" / "settings.json"


def _write_agy_model(model: str, settings_path: Path) -> None:
    """Set the `.model` key in agy's settings.json, preserving other keys.

    Atomic (temp file + os.replace). A missing or unparseable file is treated
    as an empty object rather than a hard error — agy recreates the rest of
    its state on next launch, but we must not lose an explicitly-chosen model.
    """
    try:
        data = json.loads(settings_path.read_text()) if settings_path.exists() else {}
        if not isinstance(data, dict):
            data = {}
    except (OSError, json.JSONDecodeError):
        data = {}
    data["model"] = model
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = settings_path.with_suffix(settings_path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    os.replace(tmp, settings_path)


class _AgyModelGate:
    """Serialize agy spawns across models; allow same-model spawns in parallel.

    Usage: gate.acquire(model) -> run agy -> gate.release(). acquire() writes
    the model into settings.json only when it opens a new cohort (active count
    0 -> 1), so a burst of same-model spawns writes once and runs together.
    """

    def __init__(self, settings_path: Path = AGY_SETTINGS_PATH) -> None:
        self._cond = threading.Condition()
        self._current_model: str | None = None
        self._active = 0
        self._settings_path = settings_path

    def acquire(self, model: str | None) -> None:
        with self._cond:
            while self._active > 0 and self._current_model != model:
                self._cond.wait()
            if self._active == 0:
                if model is not None:
                    _write_agy_model(model, self._settings_path)
                self._current_model = model
            self._active += 1

    def release(self) -> None:
        with self._cond:
            self._active -= 1
            if self._active == 0:
                self._current_model = None
                self._cond.notify_all()


# Process-wide gate shared by every agy spawn in the run (the dispatch pool is
# a ThreadPoolExecutor in one process, so a threading primitive suffices).
_agy_model_gate = _AgyModelGate()

def _agent_argv(
    agent: str, bin_: str, prompt_file: Path, cwd: Path,
    model: str | None, prompt_text: str, effort: str | None = None,
) -> list[str]:
    """Build the headless-agentic argv for a cross-family implementer CLI.

    effort (low|medium|high) maps to each CLI's reasoning knob: codex via
    `-c model_reasoning_effort=`, grok via `--effort`; gemini/agy has no flag
    (ignored, runs default).
    """
    if agent == "codex":
        # --skip-git-repo-check: a freshly-created git worktree is not in codex's
        # trusted-projects list, so without this codex exits 1 ("Not inside a trusted
        # directory and --skip-git-repo-check was not specified") before doing any work.
        # The reviewer codex already passes it (cross_family_reviewer.py).
        cmd = [bin_, "exec", "--sandbox", "workspace-write", "--skip-git-repo-check"]
        if model:
            cmd += ["--model", model]
        if effort:
            cmd += ["-c", f"model_reasoning_effort={effort}"]
        return cmd + ["-"]  # Read from stdin
    if agent == "grok":
        # --output-format json: usage/cost-ish metadata on stdout when supported.
        cmd = [bin_, "--cwd", str(cwd), "--always-approve",
               "--output-format", "json"]
        if model:
            cmd += ["--model", model]
        if effort:
            cmd += ["--effort", effort]
        return cmd + ["--prompt-file", str(prompt_file)]
    if agent == "gemini":  # -> agy (no effort flag; runs default)
        # CRITICAL: agy writes files to its own ~/.gemini scratch dir, NOT the
        # process cwd, unless the worktree is added to the workspace via
        # --add-dir. And it stalls on tool-permission prompts without
        # --dangerously-skip-permissions. Without BOTH, the implementer
        # produces no commits in the worktree and blocks. (Verified 2026-06-25.)
        # Model: agy ignores launch --model; selection is via settings.json
        # (_AgyModelGate). Never pass --model on argv.
        return [bin_, "--add-dir", str(cwd), "--dangerously-skip-permissions", "--print"]
    raise ValueError(f"no argv builder for agent {agent!r}")


def _autocommit_worktree(cwd: Path, task_key: str, agent: str) -> bool:
    """Stage + commit any dirty changes in the worktree. Returns True if a
    commit was created (or the agent already committed and the tree is clean
    with new work, which we can't distinguish here — so: True iff we committed).
    """
    status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=str(cwd),
        capture_output=True, text=True,
    )
    if not status.stdout.strip():
        return False  # nothing to commit (clean tree — agent self-committed or did nothing)
    subprocess.run(["git", "add", "-A"], cwd=str(cwd),
                   capture_output=True, text=True)
    commit = subprocess.run(
        ["git", "commit", "-m", f"[{task_key}] {agent} implementation"],
        cwd=str(cwd), capture_output=True, text=True,
    )
    return commit.returncode == 0


def _write_synthetic_summary(
    summary_path: Path, task_key: str, agent: str,
    exit_code: int, stdout: str, committed: bool,
) -> None:
    """Write a guaranteed-parseable summary when the agent didn't write one.

    Only three things make summary.parse() flag malformed: a missing Status,
    an invalid Status, or an unbalanced code fence. So: a valid Status plus a
    fence-stripped tail of the agent's stdout.
    """
    status = "Done" if committed else "Blocked"
    # Strip code-fence markers so we never emit an unterminated fence.
    body = "\n".join(
        ln for ln in (stdout or "").splitlines()
        if not ln.lstrip().startswith("```")
    ).strip()[-2000:]
    if not body:
        body = f"(no stdout captured; exit={exit_code})"
    reason = "" if committed else (
        "\n\n## Escalation reason\n"
        f"{agent} produced no committed changes (exit={exit_code})."
    )
    summary_path.write_text(
        f"# {task_key}: {agent} implementation\n"
        f"**Status:** {status}\n\n"
        f"## What landed\n{body}\n{reason}\n"
    )


def spawn_endpoint_agent(
    *,
    agent: str,
    cwd: Path,
    env: dict[str, str],
    prompt: str,
    model: str | None = None,
    effort: str | None = None,
    extra_args: list[str] | None = None,
    claude_bin: str = "claude",
    timeout_seconds: int = 60 * 60 * 4,
) -> SpawnResult:
    """Run one endpoint agent (kimi/glm/deepseek) as a re-pointed claude Tasker.

    Contract (EPA-3, see endpoint_agents module docstring):
      - resolve via endpoint_agents.resolve_endpoint_agent(agent, env, model);
        an EndpointConfigError propagates to the caller (misconfiguration must
        fail the cell loudly, not silently fall back to Anthropic),
      - child env = endpoint_agents.build_endpoint_env(env, resolution),
      - delegate to spawn_claude() with metered=True (module invariant 1: the
        provider token must survive spawn_claude's subscription strip) and
        extra_args extended with ["--model", resolution.model]; a caller
        `effort` maps to ["--effort", effort] exactly as the claude branch of
        spawn_agent does,
      - the returned SpawnResult passes through unchanged EXCEPT
        usage.model, which must carry resolution.model for provenance.
    """
    raise NotImplementedError("EPA-3")


def spawn_agent(
    *,
    agent: str | None,
    cwd: Path,
    env: dict[str, str],
    prompt: str,
    model: str | None = None,
    effort: str | None = None,
    extra_args: list[str] | None = None,
    claude_bin: str = "claude",
    timeout_seconds: int = 60 * 60 * 4,
) -> SpawnResult:
    """Spawn the chosen implementer agent for one task.

    agent in (None, "claude") -> the default `claude --print` worker (with an
    optional --model). Otherwise dispatch to the cross-family CLI's headless
    agentic mode (see module notes), then auto-commit + ensure a summary so
    the downstream gate/verifier/panel flow is identical regardless of agent.
    The claude-shaped-model guard below applies to EVERY non-claude spawn —
    primary, retries, and iterates alike.
    """
    summary_path = Path(env["SUMMARY_PATH"])
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    task_key = env.get("TASK_KEY", "task")
    # Single choke point: a Claude-shaped model pin never reaches a
    # non-Claude CLI, no matter which call site (primary spawn, retries,
    # panel/verifier iterates) forwarded it.
    safe_model = effective_model_for_agent(agent, model)

    if not agent or agent == "claude":
        spawn_extra = list(extra_args or [])
        if safe_model:
            spawn_extra += ["--model", safe_model]
        if effort:
            spawn_extra += ["--effort", effort]
        # No auto-commit here: the brief instructs claude to commit, and the
        # committed-tree gate treats stray uncommitted files as an evidence
        # failure — a blanket `git add -A` would mask exactly that signal
        # (and commit stray artifacts). Cross-family CLIs that cannot commit
        # get the auto-commit normalization below instead.
        return spawn_claude(
            claude_bin=claude_bin, cwd=cwd, env=env, prompt=prompt,
            extra_args=spawn_extra, timeout_seconds=timeout_seconds,
        )

    if agent in endpoint_agents_mod.ENDPOINT_AGENTS:
        return spawn_endpoint_agent(
            agent=agent, cwd=cwd, env=env, prompt=prompt, model=safe_model,
            effort=effort, extra_args=extra_args, claude_bin=claude_bin,
            timeout_seconds=timeout_seconds,
        )

    bin_ = AGENT_BINS[agent]
    # Prompt is already agent-native (see build_prompt); do not wrap with a
    # Claude Tasker suffix — that was the main quality gap for grok/codex/agy.
    prompt_file = summary_path.parent / f"{task_key}-{agent}-prompt.txt"
    prompt_file.write_text(prompt)
    argv = _agent_argv(agent, bin_, prompt_file, cwd, safe_model, prompt, effort)

    try:
        proc = subprocess.run(
            argv, input=prompt, capture_output=True, text=True,
            cwd=str(cwd), env=env, timeout=timeout_seconds,
        )
        rc, out, err = proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired as e:
        rc = 124
        out = (e.stdout.decode() if isinstance(e.stdout, bytes) else (e.stdout or ""))
        err = f"timeout after {timeout_seconds}s"

    committed = _autocommit_worktree(cwd, task_key, agent)
    if not summary_path.exists():
        _write_synthetic_summary(summary_path, task_key, agent, rc, out, committed)

    # Work landed iff we committed something. Treat that as success even if the
    # CLI returned non-zero; conversely a clean exit with no commits falls
    # through to the orchestrator's no-commits handling.
    exit_code = 0 if (rc == 0 or committed) else rc
    usage = SpawnUsage(model=safe_model or agent)
    if agent == "grok":
        gusage = parse_grok_usage(out)
        # Prefer parsed fields; keep model tag if parser left it empty.
        if gusage.model is None:
            gusage.model = safe_model or agent
        usage = gusage
    return SpawnResult(
        exit_code=exit_code, summary_path=summary_path,
        stdout=out, stderr=err, usage=usage,
    )
