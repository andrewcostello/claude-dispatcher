"""`dispatcher status <run-id>` — current state of a run.

Not yet implemented in step 4 (dry-run only). Lands when live-spawn does.
"""

from __future__ import annotations

import argparse
import sys


def execute(args: argparse.Namespace) -> int:
    print(
        "error: `dispatcher status` not yet implemented in this build. "
        "Lands with live-spawn in step 5.",
        file=sys.stderr,
    )
    return 3
