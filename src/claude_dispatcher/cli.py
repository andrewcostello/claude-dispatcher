"""Command-line entry point for the dispatcher.

Sub-commands:
  dispatcher run    — load a tasks YAML and dispatch runnable tasks
  dispatcher status — current state of a run (which tasks are mid-flight, blocked, done)
  dispatcher resume — pick up an interrupted run from its checkpoint
  dispatcher report — summary of completed tasks for a run
  dispatcher doctor — probe the machine (agent CLIs, tools) and write machine.yaml
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

from . import run as run_cmd
from . import status as status_cmd
from . import resume as resume_cmd
from . import report as report_cmd
from . import merge_prs as merge_prs_cmd
from . import forecast_bridge
from . import doctor as doctor_cmd
from . import watch as watch_cmd


DEFAULT_FINANCIAL_PATHS = ",".join([
    "apps/finance-domain/wallet/**",
    "apps/finance-domain/settlement/**",
    "apps/finance-domain/recovery/**",
    "apps/finance-domain/payout/**",
])


def _positive_dollars(s: str) -> float:
    """argparse type for --max-cost-usd: a budget ceiling must be a finite,
    positive dollar amount. Rejecting 0/negative (rather than silently
    disabling) keeps the spend-control contract unambiguous — omit the flag to
    disable. `nan`/`inf` are rejected too: `float()` parses them but they would
    silently neuter the gate (`cost >= inf` is never true; `nan` comparisons are
    always false), turning a typo into an uncapped run."""
    try:
        v = float(s)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{s!r} is not a number")
    if not math.isfinite(v):
        raise argparse.ArgumentTypeError(
            "--max-cost-usd must be a finite number (not nan/inf)")
    if v <= 0:
        raise argparse.ArgumentTypeError(
            "--max-cost-usd must be a positive dollar amount (omit the flag to "
            "disable the ceiling)")
    return v


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dispatcher",
        description=(
            "Orchestrate the Tasker role across many tasks in a YAML file. "
            "Each task runs in an isolated Claude Code session with fresh context."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")

    # --- run ---------------------------------------------------------------
    run = sub.add_parser("run", help="Dispatch runnable tasks from a YAML file")
    run.add_argument("tasks_yaml", help="Path to the tasks YAML")
    run.add_argument(
        "--mode",
        choices=["unattended", "supervised", "dry-run"],
        default="supervised",
        help="Default: supervised. dry-run prints the dispatch plan and exits.",
    )
    run.add_argument("--max-parallel", type=int, default=1, metavar="N")
    run.add_argument(
        "--filter",
        dest="filter_spec",
        default=None,
        help='Comma-separated labels, e.g. "size:M,area:schema"',
    )
    run.add_argument(
        "--only",
        dest="only_keys",
        default=None,
        help="Comma-separated task keys to dispatch (others skipped)",
    )
    run.add_argument("--skip-design", action="store_true")
    run.add_argument("--haiku-summary", action="store_true",
                     help="persist each task's transcript + a haiku summary and "
                          "reference them from the YAML row (audit log; opt-in "
                          "because it shells claude-haiku per task)")
    run.add_argument("--feature-review", action="store_true",
                     help="after the per-task drain (pr mode), review the "
                          "cumulative feature diff vs the PRD, disposition "
                          "findings, and loop fix tasks until clean/held/alarmed")
    run.add_argument("--feature-review-rounds", type=int, default=3,
                     help="max feature-review fix rounds before holding (default 3)")
    run.add_argument("--skip-security-linter", action="store_true")
    run.add_argument(
        "--reviewer-count",
        type=int,
        choices=[1, 2, 3],
        default=None,
        help="Override per-tier default reviewer count",
    )
    run.add_argument("--max-iterations", type=int, default=2)
    run.add_argument(
        "--lock-timeout-seconds",
        type=float,
        default=30.0,
        metavar="SECONDS",
        help=(
            "How long to wait for the tasks-YAML FileLock before giving up "
            "(default: 30). Raise it if many parallel workers contend on the "
            "lock; lower it to fail fast in tests."
        ),
    )
    run.add_argument(
        "--task-timeout-seconds",
        type=int,
        default=60 * 60 * 4,
        metavar="SECONDS",
        help=(
            "Per-task wall-clock budget for each spawned Claude session "
            "(default: 14400, i.e. 4h). The session is killed if it exceeds "
            "this and the task is marked Blocked."
        ),
    )
    run.add_argument(
        "--max-cost-usd",
        type=_positive_dollars,
        default=None,
        metavar="DOLLARS",
        help=(
            "Cost ceiling for the run, in US dollars (must be > 0; omit to "
            "disable, the default). Once cumulative per-task cost (implementer "
            "+ verifier spawns) reaches this AND runnable work remains, the "
            "dispatcher stops STARTING new tasks, lets in-flight tasks finish, "
            "then holds the run for a human (a budget_exceeded event + high-"
            "urgency notification fire; the run exits non-zero with remaining "
            "tasks parked To Do — raise this and `dispatcher resume` to "
            "continue). The ceiling is checked BETWEEN dispatches, so with "
            "--max-parallel > 1 actual spend can overshoot by up to the cost of "
            "the tasks already in flight. Cost basis counts every per-task "
            "Claude spawn — implementer, verifier, and all corrective/retry "
            "spawns (commit/push/test-fix retries, verifier/panel iterations), "
            "stamped even if the task later blocks. NOT counted: cross-family "
            "panel REVIEWER spend (the non-Claude adapters emit no usage JSON, "
            "and the Claude reviewer's cost isn't surfaced), so a panel-heavy "
            "run can still exceed the ceiling somewhat. Treat it as a strong "
            "guardrail, not an exact cap."
        ),
    )
    run.add_argument(
        "--verify-test-timeout",
        type=int,
        default=600,
        metavar="SECONDS",
        help=(
            "Wall-clock bound for the repo's .dispatcher.yaml `test:` "
            "command in the post-Done mechanical verification gate "
            "(default: 600). Bounds EACH execution independently — the "
            "first run and the post-fix re-run. A timed-out execution is "
            "treated as a failure, like any non-zero exit."
        ),
    )
    run.add_argument(
        "--max-verify-iterations",
        type=int,
        default=2,
        metavar="N",
        help=(
            "When the post-Done LLM verifier returns INCOMPLETE, re-spawn the "
            "Tasker with the verifier's gap list, re-run the mechanical gate, "
            "and re-verify — up to N times before marking the task Blocked "
            "with reason verification_incomplete (default: 2). Distinct from "
            "--cross-family-panel-iterate; the verifier runs first. Each "
        ),
    )
    run.add_argument(
        "--verifier-model",
        help="Model to use for the LLM verification gate",
    )
    run.add_argument(
        "--skip-verification",
        action="store_true",
        default=False,
        help=(
            "Escape hatch: skip the post-Done LLM verifier entirely (the "
            "mechanical gate still runs). The skip is journaled (a "
            "verification_skipped event, plus run_config.skip_verification in "
            "the genesis). For emergencies only — the verifier exists to catch "
            "stubbed/deferred/quietly-narrowed work that the mechanical suite "
            "can pass."
        ),
    )
    run.add_argument(
        "--run-id",
        default=None,
        help="Default: ISO 8601 timestamp",
    )
    run.add_argument(
        "--financial-paths",
        default=DEFAULT_FINANCIAL_PATHS,
        help=f"Comma-separated globs (default: {DEFAULT_FINANCIAL_PATHS})",
    )
    run.add_argument(
        "--runs-dir",
        default="docs/runs",
        help="Where to write per-run artifacts (run.log, summaries). Default: docs/runs",
    )
    run.add_argument(
        "--worktree-base",
        default=None,
        help=(
            "Override worktree base path. Default: /worktrees if /workspace is repo root, "
            "else ../worktree-<task-key>"
        ),
    )
    run.add_argument(
        "--base-branch",
        default=None,
        help=(
            "Branch to fork each task's worktree from. Precedence: this flag > "
            "the YAML's top-level `base_branch` > `main` (default). Use this when "
            "your work lives on an epic branch (e.g., epic/bay-session-architecture) "
            "and forking from main would produce empty/stale worktrees."
        ),
    )
    run.add_argument(
        "--implementer",
        choices=["claude", "codex", "grok", "gemini"],
        default=None,
        help=(
            "Run-level default implementer agent (worker, not Tasker). A per-task "
            "`agent:` in the YAML still wins; otherwise every task is built by this "
            "family's headless CLI. Default: claude (or grok under --no-claude)."
        ),
    )
    run.add_argument(
        "--cascade-terminal",
        choices=["claude", "grok"],
        default=None,
        help=(
            "Final agent in the quality cascade after effort bumps. Default: claude. "
            "Use grok for dogfood fleets that must not call Claude. Implied by "
            "--no-claude."
        ),
    )
    run.add_argument(
        "--no-claude",
        action="store_true",
        default=False,
        help=(
            "Grok-only fleet mode: default implementer=grok, cascade-terminal=grok, "
            "skip LLM verification (Claude-only today), disable haiku summaries, "
            "and preflight without requiring the claude binary. Per-task "
            "`agent: claude` still allowed if you explicitly pin it."
        ),
    )
    run.add_argument(
        "--integration",
        choices=["branch", "pr"],
        default=None,
        help=(
            "Integration mode. 'branch' (the default behavior) forks each "
            "task worktree directly from --base-branch, as today. 'pr' runs "
            "the whole run off a shared run-level FEATURE branch: it is "
            "created from --base-branch at run start (if absent), task "
            "worktrees fork from IT, and the genesis records the mode + "
            "feature branch + its SHA. Precedence: this flag > .dispatcher.yaml "
            "`integration:` > 'branch'."
        ),
    )
    run.add_argument(
        "--feature-branch",
        default=None,
        metavar="NAME",
        help=(
            "PR-flow mode only: the run-level feature branch name. Default: "
            "feature/<epic from the tasks YAML>, sanitized. Ignored in branch "
            "mode."
        ),
    )
    run.add_argument(
        "--claude-bin",
        default="claude",
        help="claude CLI binary name (default: claude)",
    )
    run.add_argument(
        "--claude-extra-args",
        default="",
        help=(
            "Extra args to pass to `claude` after --print, space-separated. "
            "Typical for unattended runs: "
            "'--permission-mode bypassPermissions --allow-dangerously-skip-permissions'. "
            "Without these, the Tasker will stall on the first tool-use permission prompt."
        ),
    )
    run.add_argument(
        "--skip-preflight",
        action="store_true",
        default=False,
        help=(
            "Skip the run-start preflight checks (claude binary present, "
            "permission-bypass flag in --claude-extra-args, Tasker role file "
            "resolvable from a fresh worktree, dispatcher-staleness warning). "
            "The skip itself is journaled (a `preflight` event with "
            "skipped=true, plus run_config.skip_preflight in the genesis). "
            "Use only when a check is wrong for your setup — these checks "
            "exist because each failure mode silently burned a real run."
        ),
    )
    run.add_argument(
        "--gh-bin",
        default="gh",
        help="gh CLI binary name (default: gh, used for `gh pr create` in supervised mode)",
    )
    run.add_argument(
        "--auto-integrate",
        action="store_true",
        default=False,
        help=(
            "After each Tasker reports Done with commits, attempt to merge "
            "its feat branch into --base-branch atomically (git merge --no-ff "
            "+ sqlc/buf regen + go build + go vet). On clean integration, "
            "the base branch advances so the next dispatched task forks "
            "from the updated SHA. On conflict or build-fail, the task is "
            "flipped to Blocked (work preserved on feat branch). Prevents "
            "the 'fork-from-stale-base' problem where sibling tasks can't "
            "see each other's work. Off by default; opt-in per run."
        ),
    )
    run.add_argument(
        "--cross-family-panel",
        choices=["auto", "always", "never", "progressive"],
        default="auto",
        help=(
            "Cross-family reviewer panel: after each Tasker reports Done, "
            "fire three independent reviewers (Claude, Gemini, Codex) over "
            "the diff + summary. ALL THREE must APPROVE for auto-integrate "
            "to proceed; any dissenter or CRITICAL/HIGH finding blocks. "
            "Values: 'auto' (default) runs the panel only for risk-gated "
            "tickets (labels: critical/security/financial/high); 'always' "
            "runs for every Done ticket; 'never' disables the cross-family "
            "checkpoint. The Tasker's in-cycle panel still runs in all "
            "modes — this is an additional safety net for cross-family "
            "blind spots."
        ),
    )
    run.add_argument(
        "--cross-family-panel-timeout",
        type=int,
        default=600,
        help=(
            "Per-reviewer wall-clock budget for the cross-family panel "
            "(seconds; default: 600). Reviewers run in parallel, so the "
            "panel wall-clock is bounded by the slowest one. UNAVAILABLE "
            "on timeout (treated as 'incomplete' panel — does not approve)."
        ),
    )
    run.add_argument(
        "--cross-family-panel-iterate",
        type=int,
        default=0,
        metavar="N",
        help=(
            "When the cross-family panel returns block, re-spawn the Tasker "
            "with the blocking findings as a corrective prompt and re-run "
            "the panel against the new diff. Up to N iterations before "
            "giving up and marking Blocked for human triage. Default: 0 "
            "(no iterate — block goes straight to Blocked status). Each "
            "iteration is one extra Tasker spawn + one extra panel run. "
            "Always fires on any block regardless of severity or vote "
            "split; no CRITICAL or single-dissenter gating."
        ),
    )
    run.add_argument(
        "--ntfy-topic",
        default=None,
        metavar="TOPIC",
        help=(
            "ntfy.sh topic to push notifications to. Install the ntfy "
            "phone app and subscribe to the same topic to get pushed "
            "events: per-task Blocked, awaiting-human-approval gate, "
            "run-complete rollup, dispatcher worker exception. The topic "
            "IS the secret — pick something unguessable. Env var "
            "fallback: DISPATCHER_NTFY_TOPIC."
        ),
    )
    run.add_argument(
        "--ntfy-server",
        default=None,
        metavar="URL",
        help=(
            "Self-hosted ntfy server base URL. Defaults to "
            "https://ntfy.sh. Env var fallback: DISPATCHER_NTFY_SERVER."
        ),
    )
    run.add_argument(
        "--slack-webhook-url",
        default=None,
        metavar="URL",
        help=(
            "Slack incoming-webhook URL. The URL IS the secret — prefer "
            "the env-var form to keep it out of argv / shell history. "
            "Env var fallback: DISPATCHER_SLACK_WEBHOOK."
        ),
    )
    run.set_defaults(func=run_cmd.execute)

    # --- status ------------------------------------------------------------
    st = sub.add_parser(
        "status",
        help=("Current state of a run: per-task state, current wave, totals, "
              "cost so far, and run liveness. Mid-run-safe; --json for "
              "machine-readable output."),
    )
    st.add_argument("run_id")
    st.add_argument("--runs-dir", default="docs/runs")
    st.add_argument(
        "--json",
        action="store_true",
        help="Emit the structured JSON document (schema in status.py docstring)",
    )
    st.add_argument(
        "--tasks-yaml",
        dest="tasks_yaml",
        default=None,
        help=("Path to the tasks YAML this run is for. Optional — by default "
              "it is discovered from the run's summary files; pass it "
              "explicitly for a fresh run that has no summaries yet."),
    )
    st.set_defaults(func=status_cmd.execute)

    # --- resume ------------------------------------------------------------
    rs = sub.add_parser("resume", help="Resume an interrupted run from checkpoint")
    rs.add_argument("run_id")
    rs.add_argument("--runs-dir", default="docs/runs")
    rs.add_argument(
        "--strategy",
        choices=["continue", "mark-blocked"],
        default="continue",
        help=(
            "continue (default): reset interrupted In Progress tasks to To Do "
            "and re-dispatch them (worktree reused if present); "
            "mark-blocked: write Status: Blocked for In Progress tasks instead "
            "of re-dispatching, then run any remaining runnable tasks."
        ),
    )
    rs.add_argument(
        "--force",
        action="store_true",
        default=False,
        help=(
            "Resume even if the journal's last event is recent (which normally "
            "signals the original run may still be live, and resuming could "
            "double-dispatch). Use only when you are sure the original run is "
            "dead — e.g. after a kill -9 or a crashed host."
        ),
    )
    rs.add_argument(
        "--max-cost-usd",
        type=_positive_dollars,
        default=None,
        metavar="DOLLARS",
        help=(
            "Override the cost ceiling for this resume, in US dollars (> 0). "
            "Without it the resumed run keeps the original ceiling from the "
            "genesis — which, for a run that was budget-held, would immediately "
            "re-hold without progress. Raise it here to give the resumed run "
            "room to continue."
        ),
    )
    rs.set_defaults(func=resume_cmd.execute)

    # --- merge-prs ---------------------------------------------------------
    mp = sub.add_parser(
        "merge-prs",
        help=("PR-flow mode: run the mechanical merge pass over a run's "
              "Awaiting Review PRs — merge each (in blockedBy order) whose "
              "approval ladder is satisfied AND whose dependencies are all "
              "Merged. Use for a post-run / next-morning catch-up; the "
              "dispatch loop runs the same pass live."),
    )
    mp.add_argument("run_id")
    mp.add_argument("--runs-dir", default="docs/runs")
    mp.add_argument(
        "--force",
        action="store_true",
        default=False,
        help=(
            "Merge even if the journal's last event is recent (which normally "
            "signals the original run may still be merging, risking a "
            "double-merge). Use only when you are sure the run is done."
        ),
    )
    mp.add_argument("--ntfy-topic", default=None, metavar="TOPIC",
                    help="ntfy.sh topic for merge notifications (env fallback: "
                         "DISPATCHER_NTFY_TOPIC).")
    mp.add_argument("--ntfy-server", default=None, metavar="URL",
                    help="Self-hosted ntfy server (env fallback: "
                         "DISPATCHER_NTFY_SERVER).")
    mp.add_argument("--slack-webhook-url", default=None, metavar="URL",
                    help="Slack incoming-webhook URL (env fallback: "
                         "DISPATCHER_SLACK_WEBHOOK).")
    mp.set_defaults(func=merge_prs_cmd.execute)

    # --- report ------------------------------------------------------------
    rp = sub.add_parser(
        "report",
        help=("Quality dashboard for a run: per-task scores, iterations, "
              "deferred findings, gate trips, parked-for-approval list, "
              "PRs raised, concerning-tasks highlight. Mid-run-safe."),
    )
    rp.add_argument(
        "run_id",
        nargs="?",
        default="latest",
        help="Run ID to report on. Defaults to the latest run in --runs-dir.",
    )
    rp.add_argument("--runs-dir", default="docs/runs")
    rp.add_argument(
        "--json",
        action="store_true",
        help=("Emit the structured JSON document instead of the table "
              "(schema in docs/report-json.md)"),
    )
    rp.add_argument(
        "--tasks-yaml",
        dest="tasks_yaml",
        default=None,
        help=("Path to the tasks YAML this run is for. Optional — by default "
              "it is resolved from the journal's run_started event, falling "
              "back to discovery from the run's summary files; pass it "
              "explicitly to override, or for a pre-journal run whose YAML "
              "is not an ancestor of --runs-dir."),
    )
    rp.set_defaults(func=report_cmd.execute)

    # --- watch ---------------------------------------------------------------
    wh = sub.add_parser(
        "watch",
        help=("Stream compact journal events for a run (task_started, "
              "spawn, panel, blocked, done). Exit 1 if any task_blocked."),
    )
    wh.add_argument("run_id", help="Run ID under --runs-dir")
    wh.add_argument("--runs-dir", default="docs/runs")
    wh.add_argument(
        "--no-follow",
        action="store_true",
        help="Print existing events once and exit (do not tail).",
    )
    wh.add_argument(
        "--poll",
        type=float,
        default=1.0,
        metavar="SECONDS",
        help="Poll interval when following (default 1.0).",
    )
    wh.set_defaults(func=_watch_entry)

    # --- doctor --------------------------------------------------------------
    dr = sub.add_parser(
        "doctor",
        help=("Probe the machine (agent CLIs, tools, dispatcher install) and "
              "write the profile to $XDG_CONFIG_HOME/claude-dispatcher/"
              "machine.yaml. The `manual:` section and file comments are "
              "preserved across re-probes."),
    )
    dr.add_argument(
        "--check",
        action="store_true",
        help=("Exit 1 if a required entry (claude, git) is missing. All other "
              "entries are soft: reported but never affect the exit code."),
    )
    dr.add_argument(
        "--config-dir",
        default=None,
        help=("Override the config directory machine.yaml is written to "
              "(default: $XDG_CONFIG_HOME/claude-dispatcher, falling back to "
              "~/.config/claude-dispatcher)."),
    )
    dr.set_defaults(func=doctor_cmd.execute)

    # --- forecast-create ---------------------------------------------------
    fc = sub.add_parser(
        "forecast-create",
        help="For each task row with a placeholder key, run `forecast jira create` "
             "and write the new Jira key back to the YAML. No-op if forecast is "
             "not installed or not configured.",
    )
    fc.add_argument("tasks_yaml", help="Path to the tasks YAML")
    fc.add_argument("--dry-run", action="store_true",
                    help="Print what would be created without invoking forecast")
    fc.set_defaults(func=_forecast_create)

    # --- forecast-sync -----------------------------------------------------
    fs = sub.add_parser(
        "forecast-sync",
        help="For each task row in a terminal status (Done/Blocked/Escalated), "
             "run `forecast jira transition` to bring Jira into sync. No-op if "
             "forecast is not installed or not configured.",
    )
    fs.add_argument("tasks_yaml", help="Path to the tasks YAML")
    fs.add_argument("--dry-run", action="store_true",
                    help="Print what would be transitioned without invoking forecast")
    fs.set_defaults(func=_forecast_sync)

    return parser


def _forecast_create(args) -> int:
    """Run the create-missing-tickets bridge. Always exits 0 if forecast is
    just not present — that's a "bridge not applicable" case, not an error.
    """
    from pathlib import Path
    yaml_path = Path(args.tasks_yaml).resolve()
    if not yaml_path.exists():
        print(f"error: tasks YAML not found: {yaml_path}", file=sys.stderr)
        return 2
    result = forecast_bridge.create_missing_tickets(yaml_path, dry_run=args.dry_run)
    return _print_bridge_result(result, action="create")


def _forecast_sync(args) -> int:
    from pathlib import Path
    yaml_path = Path(args.tasks_yaml).resolve()
    if not yaml_path.exists():
        print(f"error: tasks YAML not found: {yaml_path}", file=sys.stderr)
        return 2
    result = forecast_bridge.sync_terminal_statuses(yaml_path, dry_run=args.dry_run)
    return _print_bridge_result(result, action="sync")


def _print_bridge_result(result: dict, *, action: str) -> int:
    """Render the bridge result to stdout/stderr. Returns 0 for graceful skip
    and for full success, 1 if any errors occurred (so callers can detect).
    """
    if result.get("skipped_all"):
        print(f"forecast bridge skipped: {result['reason']}")
        print("(this is a soft skip; chain `&& dispatcher {action}` safely)".format(action=action))
        return 0

    if action == "create":
        for old, new in result["created"]:
            print(f"  created  {old} -> {new}")
        for k in result["skipped"]:
            print(f"  skipped  {k}")
    else:  # sync
        for k, target in result["transitioned"]:
            print(f"  -> {target:<20}  {k}")
        for k in result["skipped"]:
            print(f"  skipped  {k}")

    if result["errors"]:
        print("Errors:", file=sys.stderr)
        for k, msg in result["errors"]:
            print(f"  {k}: {msg}", file=sys.stderr)
        return 1
    return 0


def _watch_entry(args: argparse.Namespace) -> int:
    return watch_cmd.watch_run(
        args.run_id,
        runs_dir=Path(args.runs_dir),
        poll_seconds=float(args.poll),
        follow=not args.no_follow,
    )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("\nInterrupted. Run `dispatcher resume <run-id>` to continue.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
