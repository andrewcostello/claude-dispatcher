"""`dispatcher merge-prs <run-id>` — run the mechanical merge pass standalone.

The merge engine (``merge_engine.py``) runs inside the dispatch loop after each
task reaches Awaiting Review. This command exposes the SAME pass for a post-run
/ next-morning catch-up: when a run finished with PRs still Awaiting Review
(elevated PRs waiting on a human approval, or low-risk PRs whose dependencies
hadn't merged yet), point this at the finished run and it merges everything now
eligible.

It reconstructs the run from its journal genesis exactly as ``dispatcher
resume`` does — the ``run_config`` payload carries the tasks-YAML path, the
integration mode, and the feature branch — so you need only the run-id (and
``--runs-dir`` to locate the journal). Only ``pr``-mode runs have PRs to merge;
a ``branch``-mode run is a clean no-op.

The merge events (``pr_approved`` / ``pr_merged`` / ``pr_merge_failed``) are
appended to the run's EXISTING journal chain, so the audit trail stays in one
hash-linked log. A catch-up pass legitimately extends the chain past
``run_complete``; the chain stays verifiable (``verify`` enforces genesis shape
+ linkage, not that ``run_complete`` is last).

Liveness guard: if the journal's last event is recent the original run may still
be merging, and a second merger could double-merge — so this refuses with exit 4
unless ``--force`` (mirrors ``dispatcher resume``).

Exit codes: 0 (pass ran — including a clean no-op), 2 (no journal / no genesis /
unusable config / not pr mode), 4 (run looks still active; use --force).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import journal as journal_mod
from . import merge_engine as me_mod
from . import notify as notify_mod
from . import resume as resume_mod
from . import worktree as wt_mod
from . import yaml_io


def execute(args: argparse.Namespace) -> int:
    runs_dir = Path(args.runs_dir).resolve()
    run_dir = runs_dir / args.run_id
    journal_path = run_dir / journal_mod.JOURNAL_FILENAME

    if not journal_path.exists():
        print(
            f"error: no journal at {journal_path} — nothing to merge. "
            f"(Is the run-id correct? Check --runs-dir, default 'docs/runs'.)",
            file=sys.stderr,
        )
        return 2

    try:
        events = list(journal_mod.read_events(journal_path))
    except journal_mod.JournalError as e:
        print(f"error: cannot read journal at {journal_path}: {e}", file=sys.stderr)
        return 2

    genesis = events[0] if events else None
    if genesis is None or genesis.event_type != journal_mod.EventType.run_started.value:
        print(
            f"error: journal at {journal_path} has no run_started genesis event "
            f"— cannot reconstruct the run configuration.",
            file=sys.stderr,
        )
        return 2

    config = genesis.payload.get("run_config")
    if not isinstance(config, dict) or not config.get("tasks_yaml"):
        print(
            f"error: genesis event in {journal_path} is missing its run_config "
            f"— cannot reconstruct the run.",
            file=sys.stderr,
        )
        return 2

    if str(config.get("integration") or "branch") != "pr":
        print(
            f"Run {args.run_id} is not a pr-mode run (integration="
            f"{config.get('integration')!r}) — no PRs to merge."
        )
        return 0

    tasks_path = Path(config["tasks_yaml"]).resolve()
    if not tasks_path.exists():
        print(f"error: tasks YAML not found: {tasks_path}", file=sys.stderr)
        return 2

    # The PR base. base_branch was repointed to the feature branch at run start
    # (PRF-1), so either carries it; prefer the explicit feature_branch.
    feature_branch = (config.get("feature_branch")
                      or config.get("base_branch"))
    if not feature_branch:
        print(
            f"error: genesis run_config for {args.run_id} has no feature branch "
            f"— cannot determine the PR merge target.",
            file=sys.stderr,
        )
        return 2

    # Liveness guard — a recent last event suggests the original run is still
    # merging; a second merger could double-merge. --force overrides.
    age = resume_mod._seconds_since_last_event(events)
    if (age is not None
            and age < resume_mod.RUN_ACTIVE_THRESHOLD_SECONDS
            and not args.force):
        print(
            f"error: run {args.run_id} looks still active — its last journal "
            f"event was {age:.0f}s ago (< {resume_mod.RUN_ACTIVE_THRESHOLD_SECONDS}s). "
            f"A concurrent merge pass could double-merge. If you are sure the "
            f"original run is done, re-run with --force.",
            file=sys.stderr,
        )
        return 4

    # Open the existing chain for append (verifies integrity first, refusing a
    # broken chain). The merge events extend this run's audit trail.
    try:
        journal = journal_mod.Journal.resume(journal_path)
    except journal_mod.JournalError as e:
        print(f"error: cannot open journal at {journal_path}: {e}", file=sys.stderr)
        return 2

    repo_root = wt_mod.detect_repo_root(tasks_path.parent)
    notifier = notify_mod.build_notifier_from_env(
        cli_ntfy_topic=getattr(args, "ntfy_topic", None),
        cli_ntfy_server=getattr(args, "ntfy_server", None),
        cli_slack_webhook=getattr(args, "slack_webhook_url", None),
    )

    cfg = me_mod.MergeEngineConfig(
        tasks_path=tasks_path,
        repo_root=repo_root,
        feature_branch=str(feature_branch),
        gh_bin=str(config.get("gh_bin") or "gh"),
        lock_timeout_seconds=float(config.get("lock_timeout_seconds") or 30.0),
        run_id=str(config.get("run_id") or args.run_id),
    )

    print(f"Merge pass for run {args.run_id} (feature branch {feature_branch}) ...")
    result = me_mod.merge_pass(
        cfg, journal=journal, notifier=notifier, log=lambda m: print(m),
    )

    _print_result(result)
    return 0


def _print_result(result: me_mod.MergePassResult) -> None:
    print(
        f"  merged: {len(result.merged)}  |  "
        f"awaiting approval: {len(result.awaiting_approval)}  |  "
        f"needs rebase: {len(result.needs_rebase)}  |  "
        f"unactionable: {len(result.unactionable)}"
    )
    for key in result.merged:
        print(f"    merged             {key}")
    for key in result.awaiting_approval:
        print(f"    awaiting approval  {key}")
    for key in result.needs_rebase:
        print(f"    needs rebase       {key}")
    for key in result.unactionable:
        print(f"    unactionable       {key}")
