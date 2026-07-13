#!/usr/bin/env python3
"""Minimal hermetic stand-in for the `grok` CLI used in dispatcher tests.

Mirrors enough of headless grok to exercise spawn_agent:
  * honors --prompt-file / --cwd / --always-approve / --output-format json
  * writes a Done summary to SUMMARY_PATH
  * creates a trivial file + commit-able dirty tree (dispatcher auto-commits)

Env:
  SUMMARY_PATH, TASK_KEY — from dispatcher
  FAKE_GROK_FAIL=1 — non-zero exit, no changes
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if os.environ.get("FAKE_GROK_FAIL") == "1":
        print("fake_grok: forced fail", file=sys.stderr)
        return 1

    task_key = os.environ.get("TASK_KEY", "TASK")
    summary_path = os.environ.get("SUMMARY_PATH")
    if not summary_path:
        print("fake_grok: SUMMARY_PATH not set", file=sys.stderr)
        return 2

    # Touch a file so auto-commit has work.
    Path("fake_grok_out.txt").write_text(f"ok from {task_key}\n", encoding="utf-8")

    sp = Path(summary_path)
    sp.parent.mkdir(parents=True, exist_ok=True)
    sp.write_text(
        f"# {task_key}: implementation\n"
        f"**Status:** Done\n\n"
        f"## What landed\n- fake_grok_out.txt\n\n"
        f"## Tests\n- not run: hermetic fake\n",
        encoding="utf-8",
    )

    # JSON-ish envelope for parse_grok_usage
    if "--output-format" in argv and "json" in argv:
        print(json.dumps({
            "model": "fake-grok",
            "num_turns": 1,
            "usage": {"input_tokens": 10, "output_tokens": 5},
            "total_cost_usd": 0.0,
        }))
    else:
        print("fake_grok done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
