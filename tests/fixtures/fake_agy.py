#!/usr/bin/env python3
"""Minimal hermetic stand-in for the `agy` CLI used in dispatcher tests.

Mirrors enough of headless agy to exercise spawn_agent:
  * honors --add-dir / --dangerously-skip-permissions / --print
  * does NOT self-commit (unlike grok); touches a file for dispatcher to auto-commit
  * writes a Done summary to SUMMARY_PATH (actually agy doesn't do this reliably, so we simulate doing nothing or just outputting text and letting the dispatcher synthesize the summary)

Env:
  SUMMARY_PATH, TASK_KEY — from dispatcher
  FAKE_AGY_FAIL=1 — non-zero exit, no changes
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    # Version probes (capture_agent_version, doctor, preflight) must be
    # side-effect free — never run the work simulation for them.
    if "--version" in argv:
        print("fake-agy 0.0.1 (hermetic test stand-in)")
        return 0
    if os.environ.get("FAKE_AGY_FAIL") == "1":
        print("fake_agy: forced fail", file=sys.stderr)
        return 1

    task_key = os.environ.get("TASK_KEY", "TASK")
    
    # Touch a file so auto-commit has work.
    Path("fake_agy_out.txt").write_text(f"ok from {task_key}\n", encoding="utf-8")

    # In headless mode agy just prints to stdout and doesn't write the summary.
    print(f"fake_agy done {task_key}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
