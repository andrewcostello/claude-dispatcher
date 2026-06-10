"""Command-line entry point for the dispatcher.

Sub-commands:
  dispatcher run    — load a tasks YAML and dispatch runnable tasks
  dispatcher status — current state of a run (which tasks are mid-flight, blocked, done)
  dispatcher resume — pick up an interrupted run from its checkpoint
  dispatcher report — summary of completed tasks for a run
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import run as run_cmd
from . import status as status_cmd
from . import resume as resume_cmd
from . import report as report_cmd
from . import forecast_bridge


DEFAULT_FINANCIAL_PATHS = ",".join([
    "apps/finance-domain/wallet/**",
    "apps/finance-domain/settlement/**",
    "apps/finance-domain/recovery/**",
    "apps/finance-domain/payout/**",
])


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
        choices=["auto", "always", "never"],
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
    st = sub.add_parser("status", help="Show current state of a run")
    st.add_argument("run_id")
    st.add_argument("--runs-dir", default="docs/runs")
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
    rs.set_defaults(func=resume_cmd.execute)

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
    rp.set_defaults(func=report_cmd.execute)

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
