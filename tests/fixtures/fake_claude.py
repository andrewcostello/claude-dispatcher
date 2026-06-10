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
    "blocked-malformed": "Garbage",  # invalid status → parser marks malformed
    "escalated": "Escalated",
    "blocked-iteration-cap": "Blocked",
    "awaiting-human-pr": "Blocked",
}


def main() -> int:
    # Consume stdin so the parent doesn't block on a closed pipe.
    _ = sys.stdin.read()

    task_key = os.environ.get("TASK_KEY", "UNKNOWN")
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

    if scenario in ("done", "awaiting-human-pr"):
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
    else:
        lines.append(f"https://github.com/test/repo/pull/smoke-{task_key.lower()}")

    summary_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
