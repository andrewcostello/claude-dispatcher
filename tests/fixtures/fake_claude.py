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
        import subprocess
        marker = Path(f"smoke-marker-{task_key}.txt")
        marker.write_text(f"smoke marker for {task_key}\n", encoding="utf-8")
        subprocess.run(["git", "add", str(marker)], check=False, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", f"feat(smoke): [{task_key}] simulated work"],
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
