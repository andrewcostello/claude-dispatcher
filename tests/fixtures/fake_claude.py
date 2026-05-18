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
