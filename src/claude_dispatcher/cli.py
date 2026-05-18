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
            "continue: try to resume in-flight worktrees; "
            "mark-blocked: write Status: Blocked for in-flight tasks and re-run"
        ),
    )
    rs.set_defaults(func=resume_cmd.execute)

    # --- report ------------------------------------------------------------
    rp = sub.add_parser("report", help="Summarize completed tasks for a run")
    rp.add_argument("run_id")
    rp.add_argument("--runs-dir", default="docs/runs")
    rp.set_defaults(func=report_cmd.execute)

    return parser


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
