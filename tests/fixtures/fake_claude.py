#!/usr/bin/env python3
"""Stand-in for the `claude` binary used by smoke tests.

Reads the prompt on stdin, extracts TASK_KEY from the environment, writes a
synthetic summary file to SUMMARY_PATH, and exits 0. Simulates a Done outcome
with no PR (since the smoke test doesn't actually want to raise PRs).

Behavior is driven by environment variables passed by the dispatcher's
spawn_claude(), so the test exercises the full env-handoff contract.

Optional: if FAKE_CLAUDE_SCENARIO is set, the fake produces a non-Done summary
to exercise the other branches of the orchestrator.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

SCENARIOS = {
    "done": "Done",
    "done-no-commit": "Done",        # Done but skip the git commit step
    "done-commit-retry": "Done",     # Done; first run skips commit, second commits
    "done-direct-to-base": "Done",   # Done; commits on feat/X AND FF-merges into
                                     # base_branch (BSA-style direct-to-base
                                     # workflow). Leaves feat == base.
    "done-pushed": "Done",           # Done; commits AND pushes the branch to
                                     # origin on the first run (the happy path).
    "done-no-push": "Done",          # Done; commits but NEVER pushes (the DISP-9
                                     # failure mode — surfaces needs_push).
    "done-push-retry": "Done",       # Done; first run commits-but-no-push,
                                     # the push-retry invocation pushes.
    "done-pushed-not-raised": "Done",  # Done; commits + pushes, but the PR
                                     # section honestly says "Not raised: ..."
                                     # (a deliberately PR-less Done).
    "done-tests-green": "Done",      # Done; commits the file the repo's
                                     # .dispatcher.yaml test command checks
                                     # (tests-green.txt) → gate passes first try.
    "done-tests-red-then-fixed": "Done",  # Done; first invocation commits
                                     # WITHOUT the green file; the second
                                     # (the fix retry) commits it. Sentinel-
                                     # file pattern like done-commit-retry.
    "done-tests-red": "Done",        # Done; commits but NEVER creates the
                                     # green file → both gate executions red.
    "blocked-malformed": "Garbage",  # invalid status → parser marks malformed
    "escalated": "Escalated",
    "blocked-iteration-cap": "Blocked",
    "awaiting-human-pr": "Blocked",
}


def main() -> int:
    # --version MUST be handled first, before any stdin read, env reads, or
    # side effects. Both the run-start preflight / `dispatcher doctor` probes
    # (OPS-3) and capture_agent_version() (OPS-4) invoke `<bin> --version`
    # (stdin=DEVNULL); a real `claude --version` is side-effect-free, so the
    # stub must be too — without this guard a probe would run the full Tasker
    # simulation below (reading inherited SUMMARY_PATH/TASK_KEY and
    # `git commit`ing in the developer's real repo).
    if "--version" in sys.argv[1:]:
        print("1.0.0 (fake-claude)")
        return 0

    # Consume stdin so the parent doesn't block on a closed pipe.
    _ = sys.stdin.read()

    task_key = os.environ.get("TASK_KEY", "UNKNOWN")

    # Simulated kill -9 mid-run: if this task is the designated kill target,
    # SIGKILL the parent (the dispatcher process) and exit immediately —
    # before committing or writing a summary. This leaves the task stamped
    # "In Progress" in the YAML (the dispatcher marks that before spawning),
    # exactly as a real crash would, so `dispatcher resume` has something to
    # recover. Only meaningful when fake_claude runs as a direct child of a
    # real dispatcher subprocess (never under the in-process orchestrator,
    # where getppid() would be the test runner).
    kill_key = os.environ.get("FAKE_CLAUDE_KILL_KEY")
    if kill_key and task_key == kill_key:
        import signal
        os.kill(os.getppid(), signal.SIGKILL)
        return 0

    summary_path_raw = os.environ.get("SUMMARY_PATH")
    if not summary_path_raw:
        print("fake_claude: SUMMARY_PATH not set", file=sys.stderr)
        return 2
    summary_path = Path(summary_path_raw)
    scenario = os.environ.get("FAKE_CLAUDE_SCENARIO", "done")
    status = SCENARIOS.get(scenario, "Done")

    # Simulate the Tasker's commit step — real Tasker must `git add` +
    # `git commit` before Done; the dispatcher now verifies this. The fake
    # makes a trivial commit so the dispatcher's `_has_commits_on_branch`
    # check passes. Exceptions:
    #   - `done-no-commit`   — reports Done WITHOUT committing (tests the
    #                           dispatcher's detect-and-retry path).
    #   - `done-commit-retry` — first invocation skips commit; second
    #                           invocation (the retry) DOES commit. Tracked
    #                           via a sentinel file in the worktree.
    def _do_commit():
        """Make a fresh commit on each invocation.

        Uses a per-worktree counter so consecutive spawns (e.g., the
        panel-iterate corrective spawn) produce distinct commits. Without
        this, the second spawn would write the same content and `git
        commit` would no-op, defeating tests that rely on iterate
        actually producing new history.
        """
        import subprocess
        counter_path = Path(f".fake-claude-counter-{task_key}")
        try:
            n = int(counter_path.read_text()) + 1
        except (OSError, ValueError):
            n = 1
        counter_path.write_text(str(n), encoding="utf-8")
        marker = Path(f"smoke-marker-{task_key}.txt")
        marker.write_text(
            f"smoke marker for {task_key} #{n}\n", encoding="utf-8",
        )
        subprocess.run(["git", "add", str(marker)], check=False, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m",
             f"feat(smoke): [{task_key}] simulated work #{n}"],
            check=False, capture_output=True,
        )

    def _do_commit_and_ff_into_base(base_branch: str) -> None:
        """Simulate the BSA direct-to-base workflow: commit on feat/X
        then fast-forward base_branch in the main repo to match feat/X's
        tip. Leaves feat == base, which the standard 'rev-list
        base..HEAD' check misreads as 'no commits made'.
        """
        import subprocess
        _do_commit()
        sha = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=False, capture_output=True, text=True,
        ).stdout.strip()
        # Locate the main repo's .git/ — works whether --git-common-dir
        # returns absolute or worktree-relative.
        cd_proc = subprocess.run(
            ["git", "rev-parse", "--git-common-dir"],
            check=False, capture_output=True, text=True,
        )
        common_dir = Path(cd_proc.stdout.strip())
        if not common_dir.is_absolute():
            common_dir = (Path.cwd() / common_dir).resolve()
        main_repo = common_dir.parent
        subprocess.run(
            ["git", "-C", str(main_repo), "update-ref",
             f"refs/heads/{base_branch}", sha],
            check=False, capture_output=True,
        )

    def _push_current_branch():
        """Push the worktree's current branch to origin, setting upstream.

        The worktree shares the parent repo's remotes, so `origin` resolves
        even though we're inside a `git worktree`. Best-effort: a missing
        remote (the no-remote scenarios) just no-ops under check=False.
        """
        import subprocess
        branch = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            check=False, capture_output=True, text=True,
        ).stdout.strip()
        subprocess.run(
            ["git", "push", "-u", "origin", branch],
            check=False, capture_output=True,
        )

    def _commit_green_file():
        """Create + commit the file the mechanical-verification test command
        checks (`test -f tests-green.txt` in the test fixtures)."""
        import subprocess
        green = Path("tests-green.txt")
        green.write_text(f"green for {task_key}\n", encoding="utf-8")
        subprocess.run(["git", "add", str(green)], check=False, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m",
             f"fix(smoke): [{task_key}] make repo test suite green"],
            check=False, capture_output=True,
        )

    if scenario in ("done", "awaiting-human-pr", "done-tests-red"):
        # done-tests-red commits like `done` but never creates the green
        # file, on the first invocation OR the fix retry — both gate
        # executions stay red.
        _do_commit()
    elif scenario == "done-tests-green":
        _do_commit()
        _commit_green_file()
    elif scenario == "done-tests-red-then-fixed":
        sentinel = Path(f".fake-claude-test-fix-{task_key}")
        if sentinel.exists():
            # Second invocation = the fix-the-tests retry: commit the green
            # file this time so the gate's re-run passes.
            _commit_green_file()
        else:
            sentinel.write_text("first invocation left tests red\n",
                                encoding="utf-8")
            _do_commit()  # commits exist (commit gate passes) but suite is red
    elif scenario in ("done-pushed", "done-pushed-not-raised"):
        _do_commit()
        _push_current_branch()
    elif scenario == "done-no-push":
        # Commit (so the commit-retry gate passes) but never push — even on the
        # push-retry invocation — so the dispatcher must flag needs_push.
        _do_commit()
    elif scenario == "done-push-retry":
        sentinel = Path(f".fake-claude-push-{task_key}")
        if sentinel.exists():
            # Second invocation = the push retry. The commit already exists on
            # the branch from the first run; just push it this time.
            _push_current_branch()
        else:
            sentinel.write_text("first invocation skipped push\n", encoding="utf-8")
            _do_commit()
    elif scenario == "done-commit-retry":
        sentinel = Path(f".fake-claude-retry-{task_key}")
        if sentinel.exists():
            _do_commit()  # second invocation = the retry; commit this time
        else:
            sentinel.write_text("first invocation skipped commit\n", encoding="utf-8")
    elif scenario == "done-direct-to-base":
        # base_branch defaults to "main" in the test fixture; allow
        # override via env for parity with other tests.
        base_branch = os.environ.get("FAKE_CLAUDE_BASE_BRANCH", "main")
        _do_commit_and_ff_into_base(base_branch)
    # `done-no-commit` leaves the worktree uncommitted on every invocation

    summary_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# {task_key}: smoke test outcome",
        "",
        f"**Status:** {status}",
        "**Started:** 2026-05-18T09:15:00-07:00",
        "**Completed:** 2026-05-18T09:17:00-07:00",
        "**Iterations:** 1",
        "**Linter cycles:** 0",
        "**Human gate fired:** " + ("yes" if scenario == "awaiting-human-pr" else "no"),
        "**Final quality score:** 22/25",
        "",
        "## What landed",
        f"Smoke test for {task_key} (scenario: {scenario}).",
        "",
        "## Key decisions",
        "Driven by FAKE_CLAUDE_SCENARIO env var.",
        "",
        "## Deferred findings",
        "",
        "## Review consensus",
        "| Reviewer | Score | Verdict |",
        "|----------|-------|---------|",
        "| A | 22/25 | APPROVE |",
        "| B | 22/25 | APPROVE |",
        "| C | 22/25 | APPROVE |",
        "",
        "## Files changed",
        "- placeholder",
        "",
        "## PR",
    ]
    if scenario == "awaiting-human-pr":
        lines += [
            "Prepared, awaiting human approval",
            "",
            "### Prepared PR",
            f"**Title:** feat(test): [{task_key}] smoke test placeholder",
            f"**Branch:** feat/{task_key}-smoke-test",
            "**Body:**",
            "```",
            "## What",
            f"Smoke test for {task_key}.",
            "",
            "## Ticket",
            task_key,
            "```",
        ]
    elif scenario == "blocked-iteration-cap":
        lines.append("Not raised: iteration cap reached")
        lines += ["", "## Escalation reason (if Blocked or Escalated)",
                  "Iteration cap reached with open CRITICAL findings."]
    elif scenario == "escalated":
        lines.append("Not raised: REJECT verdict")
        lines += ["", "## Escalation reason (if Blocked or Escalated)",
                  "Fundamental design flaw identified by multiple reviewers."]
    elif scenario == "done-pushed-not-raised":
        lines.append("Not raised: docs-only change landed direct; no PR required")
    else:
        lines.append(f"https://github.com/test/repo/pull/smoke-{task_key.lower()}")

    summary_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
