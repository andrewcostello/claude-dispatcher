"""Mechanical verification: run a repo's own test command in a task worktree.

A Tasker that reports Done has only *claimed* the work is complete; the
cheapest independent check is the repo's own test suite. This module runs the
shell command a repo declares in its `.dispatcher.yaml` `test:` key (loaded by
``repo_config``) inside the task worktree and reports the verdict. Mechanical
checks run before any LLM verifier — never spend verifier tokens on a suite
that is provably red.

Mirrors ``push_verify``'s layout: pure subprocess logic with an injectable log
callback, no journal/YAML access. The orchestrator owns the recovery (one
fix-the-tests re-spawn), the journal events, and the YAML write-back; this
module only answers "does the command exit 0 in this worktree, and what did
the end of its output say?".

Output policy: only the LAST :data:`TAIL_CHARS` characters of the combined
stdout+stderr are ever kept or propagated. Test runners print their failure
summary at the end, so the tail is the diagnostic part — and everything
downstream of this result (the corrective prompt, the journal payload, the
YAML detail field) must stay bounded regardless of how chatty the suite is.
"""

from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

# The bound on every output excerpt this module emits. The timeout/launch
# annotation lines are appended AFTER truncation so they can't be pushed out
# by a chatty suite — consumers should treat the effective cap as
# TAIL_CHARS plus a small constant slack.
TAIL_CHARS = 2000


@dataclass(frozen=True)
class MechanicalVerifyResult:
    """The verdict of one test-command execution.

    ``exit_code`` is None when no exit code exists: the command timed out and
    was killed, or it never launched (an OSError from the subprocess machinery,
    e.g. a missing worktree directory). The two are distinguished by the
    annotation line in ``output_tail`` ("timed out after Ns" vs "failed to
    launch"). Either way the execution counts as a failure.
    """

    exit_code: int | None
    duration_seconds: float
    output_tail: str

    @property
    def passed(self) -> bool:
        """True iff the command ran to completion and exited 0."""
        return self.exit_code == 0


def _tail(text: str) -> str:
    """The last TAIL_CHARS characters of ``text`` — the only slice ever kept."""
    return text[-TAIL_CHARS:]


def run_test_command(
    command: str,
    *,
    worktree: Path,
    timeout_seconds: int,
    log: Callable[[str], None] = lambda _m: None,
) -> MechanicalVerifyResult:
    """Run ``command`` through the shell in ``worktree``, bounded by
    ``timeout_seconds``.

    stdout and stderr are merged (test runners interleave them and the tail
    must reflect what a human at the terminal would have seen last). Never
    raises for the expected failure modes — timeout and launch failure come
    back as failed results so the caller's verdict logic stays uniform;
    genuinely unexpected exceptions propagate.
    """
    start = time.monotonic()
    try:
        proc = subprocess.run(
            command,
            shell=True,
            cwd=str(worktree),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        duration = time.monotonic() - start
        # The exception carries whatever output was captured before the kill.
        # Despite text=True it may arrive as bytes (the decode normally
        # happens after a complete read), so normalize defensively.
        partial = exc.output or ""
        if isinstance(partial, bytes):
            partial = partial.decode("utf-8", errors="replace")
        log(f"  mechanical-verify: command timed out after {timeout_seconds}s")
        return MechanicalVerifyResult(
            exit_code=None,
            duration_seconds=duration,
            output_tail=(
                _tail(partial)
                + f"\n[mechanical-verify] timed out after {timeout_seconds}s"
            ),
        )
    except OSError as exc:
        # The command never ran (shell missing, worktree path gone, ...).
        # A failed execution, with the error text standing in for output.
        duration = time.monotonic() - start
        log(f"  mechanical-verify: command failed to launch: {exc}")
        return MechanicalVerifyResult(
            exit_code=None,
            duration_seconds=duration,
            output_tail=_tail(f"[mechanical-verify] failed to launch: {exc}"),
        )

    duration = time.monotonic() - start
    return MechanicalVerifyResult(
        exit_code=proc.returncode,
        duration_seconds=duration,
        output_tail=_tail(proc.stdout or ""),
    )
