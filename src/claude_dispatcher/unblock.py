"""`dispatcher blocked` / `dispatcher unblock` — the human review-and-clear
loop for Blocked tasks.

Blocked is the dispatcher's only stop state: gates (mechanical, seal,
committed-tree, LLM verifier, panel) flip a task to Blocked and nothing
re-dispatches it automatically — `resume` never touches Blocked rows and
`runnable_now` only sees To Do. Before this module the sole unblock path
was hand-editing the YAML. These commands make the human loop first-class:

  dispatcher blocked tasks.yaml
      Review queue: every Blocked task with its reason and the gate detail
      that explains it (which files were dirty, why the seal failed, what
      the panel flagged).

  dispatcher unblock tasks.yaml KEY [KEY ...] [--note "..."]
  dispatcher unblock tasks.yaml --all [--note "..."]
      Clear: flip Blocked -> To Do, drop blocked_reason and the stale gate
      stamps (so the re-run re-evaluates from scratch), and stamp
      unblocked_at. --note appends a "## Unblock note (human)" section to
      the task description — the re-spawned Tasker reads the description,
      so this is how the human's adjudication reaches the agent (e.g.
      "commit helper.go, delete debug.log" or "the seal must fail with the
      fix reverted — strengthen it, do not weaken the fix").

The next `dispatcher run` re-dispatches cleared tasks on their existing
branches (prior commits preserved), and every gate re-runs — unblocking
grants a retry, never a waiver.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys

from . import yaml_io

BLOCKED = "Blocked"
TODO = "To Do"

# Row keys that describe the PREVIOUS attempt's gate verdicts. Cleared on
# unblock so a To Do row doesn't carry contradictory "failed" stamps into
# its re-run (each gate re-stamps on the next attempt).
_STALE_STAMPS = (
    "blocked_reason",
    "mechanical_verification", "mechanical_verification_detail",
    "seal_verification", "seal_verification_detail",
    "verified", "verification_iterations", "verification_detail",
)

# Detail fields shown in the review queue, in display order.
_DETAIL_FIELDS = (
    "mechanical_verification_detail",
    "seal_verification_detail",
    "verification_detail",
    "panel_summary",
)

_DETAIL_EXCERPT = 400


def _blocked_rows(doc) -> list[dict]:
    rows = (doc.get("tasks") or []) if isinstance(doc, dict) else []
    return [r for r in rows if r.get("status") == BLOCKED]


def list_blocked(args: argparse.Namespace) -> int:
    """`dispatcher blocked` — print the review queue. Exit 0 when nothing
    is blocked, 3 when at least one task is (scriptable: cron/CI can alert
    on the exit code without parsing output)."""
    doc = yaml_io.load(args.tasks_yaml)
    blocked = _blocked_rows(doc)
    if not blocked:
        print("no blocked tasks")
        return 0
    for r in blocked:
        print(f"{r.get('key')}  [{r.get('blocked_reason', 'no reason recorded')}]")
        print(f"  summary: {r.get('summary', '')}")
        for f in _DETAIL_FIELDS:
            v = r.get(f)
            if v:
                text = str(v).strip().replace("\n", "\n    ")
                if len(text) > _DETAIL_EXCERPT:
                    text = text[:_DETAIL_EXCERPT] + " ..."
                print(f"  {f}:\n    {text}")
        print(f"  clear with: dispatcher unblock {args.tasks_yaml} "
              f"{r.get('key')} [--note \"...\"]")
        print()
    print(f"{len(blocked)} blocked task(s)")
    return 3


def unblock(args: argparse.Namespace) -> int:
    """`dispatcher unblock` — flip the named Blocked tasks back to To Do.

    Refuses keys that aren't Blocked (unknown, already To Do, Done — each
    reported individually; exit 1 if ANY named key could not be cleared,
    exit 0 when everything asked for was cleared). Mutates under the same
    FileLock the orchestrator uses, so clearing mid-run is safe.
    """
    if not args.keys and not getattr(args, "all", False):
        print("error: name at least one task key, or pass --all",
              file=sys.stderr)
        return 2

    cleared: list[str] = []
    failed: list[str] = []
    with yaml_io.FileLock(args.tasks_yaml, timeout_seconds=30):
        doc = yaml_io.load(args.tasks_yaml)
        rows = (doc.get("tasks") or []) if isinstance(doc, dict) else []
        by_key = {str(r.get("key")): r for r in rows if r.get("key")}
        targets = ([str(r.get("key")) for r in _blocked_rows(doc)]
                   if getattr(args, "all", False) else list(args.keys))
        if not targets:
            print("no blocked tasks to clear")
            return 0
        for key in targets:
            row = by_key.get(key)
            if row is None:
                print(f"error: {key}: no such task", file=sys.stderr)
                failed.append(key)
                continue
            if row.get("status") != BLOCKED:
                print(f"error: {key}: status is {row.get('status')!r}, "
                      f"not Blocked — nothing to clear", file=sys.stderr)
                failed.append(key)
                continue
            prior_reason = row.get("blocked_reason", "")
            for stamp in _STALE_STAMPS:
                row.pop(stamp, None)
            row["status"] = TODO
            row["unblocked_at"] = (
                dt.datetime.now(dt.timezone.utc)
                .isoformat(timespec="seconds")
            )
            if getattr(args, "note", None):
                row["description"] = (
                    str(row.get("description", "")).rstrip()
                    + "\n\n## Unblock note (human)\n"
                    + f"(cleared from Blocked: {prior_reason})\n"
                    + args.note + "\n"
                )
            cleared.append(key)
        if cleared:
            yaml_io.dump(doc, args.tasks_yaml)

    for key in cleared:
        print(f"{key}: Blocked -> To Do")
    if cleared:
        print(f"\n{len(cleared)} task(s) cleared — re-run the dispatcher to "
              f"re-dispatch them on their existing branches. All gates "
              f"re-run: unblocking grants a retry, not a waiver.")
    return 1 if failed else 0
