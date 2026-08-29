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

  dispatcher requeue tasks.yaml KEY [KEY ...]
      Send a task back to To Do for a FRESH attempt: clear every run-state
      field AND archive-and-delete its branch, so the next run starts from
      the base instead of from work that is weeks old.

The next `dispatcher run` re-dispatches cleared tasks on their existing
branches (prior commits preserved), and every gate re-runs — unblocking
grants a retry, never a waiver.

`unblock` and `requeue` differ in exactly one thing, and it is the thing that
went wrong three times: unblock KEEPS the branch, requeue DESTROYS it.

Unblock is right for a task blocked an hour ago whose commits are worth keeping.
It is wrong for one whose branch is weeks and hundreds of commits stale — that
branch carries an old base, and a stale base drags in old files, an old
.gitignore, and dependencies that no longer merge. EPA-1..4 and GO-1 each failed
that way, and clearing the `branch:` field does NOT avoid it: worktree.branch_name
DERIVES the name from the task row, so the same branch is found again. The branch
itself has to go.

Nothing is lost. Every requeued branch is tagged `archive/<KEY>-<date>` before
deletion, because that branch may be the only record of a completed attempt.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

from . import yaml_io
from .loop_gate import ROW_STAMPS as _LOOP_GATE_STAMPS

BLOCKED = "Blocked"
TODO = "To Do"

# Row keys that describe the PREVIOUS attempt's gate verdicts. Cleared on
# unblock so a To Do row doesn't carry contradictory "failed" stamps into
# its re-run (each gate re-stamps on the next attempt).
#
# The loop role gate's keys (unit D8, §7(c)) come from `loop_gate.ROW_STAMPS`
# rather than being spelled again here: the orchestrator writes them from the
# same constant, and two spellings of one key is the failure where a rename
# clears one and writes the other while both halves stay internally
# consistent.
_STALE_STAMPS = (
    "blocked_reason",
    "mechanical_verification", "mechanical_verification_detail",
    "seal_verification", "seal_verification_detail",
    "verified", "verification_iterations", "verification_detail",
    *_LOOP_GATE_STAMPS,
)

# Detail fields shown in the review queue, in display order.
#
# `_LOOP_GATE_STAMPS[1]` is the loop role gate's detail key, and it is here
# because `list_blocked` prints ONLY the keys in this tuple: without the row,
# the gate would write a detail no reader of the queue ever sees, and
# `ROW_STAMPS`'s own justification for splitting one stamp into a short
# verdict key plus an excerptable detail key would be vacuous. Raised by the
# D8 seal author as dispute P2-6 and NOT sealed there (widening a P3's owed
# list from a seal file is how a seal becomes a specification nobody agreed
# to); landed here by P3, which owns this file, because shipping the write
# without the read is strictly worse than either.
_DETAIL_FIELDS = (
    "mechanical_verification_detail",
    "seal_verification_detail",
    "verification_detail",
    _LOOP_GATE_STAMPS[1],
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


# ── requeue ─────────────────────────────────────────────────────────────────
# Fields written by a dispatch attempt. The task DEFINITION — key, summary,
# description, type, estimate, labels, agent, blockedBy — is the contract and is
# never touched: it was not the thing that failed, and preserving it is what
# makes a fresh attempt cheap rather than a rewrite.
RUN_STATE_FIELDS = (
    "started_at", "completed_at", "dispatcher_run_id", "summary_path", "branch",
    "gate_base_sha", "cost_usd", "effort", "effort_escalated", "iteration_count",
    "linter_cycles", "final_quality_score", "human_gate_fired",
    "deferred_findings_count", "pr_not_raised_reason", "mechanical_verification",
    "verified", "verification_iterations", "input_tokens", "output_tokens",
    "cache_read_input_tokens", "cache_creation_input_tokens", "duration_ms",
    "num_turns", "model", "dispatcher_version", "agent_version",
    "blocked_reason", "blocked_at", "unblocked_at", "needs_push",
    "pr_url", "pr_number", "pr_approved_by", "merged_sha",
)


def _run_git(cmd: list[str], cwd) -> tuple[int, str, str]:
    import subprocess
    try:
        p = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True,
                           timeout=120)
        return p.returncode, p.stdout, p.stderr
    except FileNotFoundError:
        return 127, "", "git not found"
    except Exception as e:  # pragma: no cover - defensive
        return 1, "", str(e)


def archive_and_delete_branch(
    branch: str,
    key: str,
    *,
    cwd,
    date: str,
    run=None,
) -> tuple[bool, str]:
    """Tag a branch as ``archive/<key>-<date>``, then delete it and its worktree.

    Tag FIRST. That branch may be the only record of a completed attempt, and
    deleting it to fix a process problem must never be the thing that loses it.
    A failed tag aborts the deletion.
    """
    r = run or (lambda c: _run_git(c, cwd))
    tag = f"archive/{key}-{date}"

    code, _, _ = r(["git", "rev-parse", "--verify", "--quiet", branch])
    if code != 0:
        return True, f"no local branch {branch!r} — nothing to archive"

    code, _, err = r(["git", "tag", "-f", tag, branch])
    if code != 0:
        return False, f"could not tag {tag}: {err.strip()[:120]}"

    # A branch checked out in a worktree cannot be deleted; remove the worktree.
    code, out, _ = r(["git", "worktree", "list", "--porcelain"])
    if code == 0:
        wt = None
        for block in out.split("\n\n"):
            if f"branch refs/heads/{branch}" in block:
                for line in block.splitlines():
                    if line.startswith("worktree "):
                        wt = line.split(" ", 1)[1]
        if wt:
            r(["git", "worktree", "remove", "--force", wt])

    code, _, err = r(["git", "branch", "-D", branch])
    if code != 0:
        return False, f"could not delete {branch}: {err.strip()[:120]}"

    # The remote copy is best-effort: it may not exist, and its absence is not a
    # failure of the requeue.
    r(["git", "push", "origin", "--delete", branch])
    return True, f"archived as {tag}, branch deleted"


def requeue(args) -> int:
    """`dispatcher requeue` — send tasks back to To Do for a FRESH attempt.

    Clears run state AND destroys the branch, which is the difference from
    `unblock`. Use it when a branch's base is old enough that building on it is
    the problem rather than a head start.
    """
    from datetime import date as _date

    from . import yaml_io

    path = Path(args.tasks_yaml)
    doc = yaml_io.load(str(path))
    tasks = doc.get("tasks") if isinstance(doc, dict) else doc
    wanted = set(args.keys or [])
    if not wanted:
        print("requeue: name at least one task key")
        return 2

    repo = Path(args.repo)
    stamp = _date.today().isoformat()
    seen, failed = set(), 0

    for t in (tasks or []):
        key = str(t.get("key", ""))
        if key not in wanted:
            continue
        seen.add(key)
        branch = t.get("branch")

        if branch and not args.keep_branch:
            ok, detail = archive_and_delete_branch(
                str(branch), key, cwd=repo, date=stamp
            )
            print(f"  {key:12} branch: {detail}")
            if not ok:
                # A branch that could not be archived is a branch that must not
                # be deleted, and a task that must not be requeued yet.
                print(f"  {key:12} NOT requeued — resolve the branch first")
                failed += 1
                continue
        elif branch:
            print(f"  {key:12} branch kept: {branch}")

        cleared = sum(1 for f in RUN_STATE_FIELDS if t.pop(f, None) is not None)
        t["status"] = "To Do"
        print(f"  {key:12} To Do ({cleared} run-state fields cleared)")

    missing = wanted - seen
    for k in sorted(missing):
        print(f"  {k:12} NOT FOUND in {path.name}")

    yaml_io.dump(doc, str(path))
    if failed or missing:
        return 1
    print(f"\n  {len(seen)} task(s) requeued — the next run starts from the base")
    return 0
