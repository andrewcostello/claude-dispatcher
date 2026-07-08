"""Seal-inversion gate: a change's new tests must FAIL without the change.

The 2026-07 escape audit's highest-frequency test defect (13 substantive
findings) was the *false-passing seal*: a regression test that passes with
or without the fix — `undefined === undefined` baselines, property tests
whose fixed keys make the defect unreachable, mocks encoding a contract
production doesn't have. Reading a test cannot prove it pins anything;
inverting the change can. This module does the mechanical RED-check:

  1. partition the branch's changed files into test vs non-test;
  2. revert the NON-test files to their base-branch state (delete files the
     branch added, restore files it deleted);
  3. run the repo's test command — it must go RED. A green suite over the
     reverted change means the new tests prove nothing;
  4. restore the worktree (`git reset --hard` + targeted clean), which is
     safe because the committed-tree gate has already proven the tree clean.

Scope policy lives in :func:`applies` — the gate runs only for tasks that
claim to seal a fix (FIX-* keys, `type:fix` / `seal-check` labels) and only
when the diff contains BOTH test and non-test changes. Everything else
skips with a journaled reason.

Mirrors ``mechanical_verify``'s shape: subprocess logic with an injectable
log sink, bounded output, no journal/YAML access. The orchestrator owns
events and row stamps.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from . import mechanical_verify as mv_mod

# Which changed paths count as "the tests" (kept when inverting).
_TEST_PATH = re.compile(
    r"(_test\.|\.test\.|\.spec\.|^tests?/|/tests?/|/__tests__/|^spec/|/spec/"
    r"|/testdata/|/fixtures/|conftest\.py$)"
)

# Labels that opt a task into the gate.
_SEAL_LABELS = frozenset({"type:fix", "seal-check", "kind:fix"})


def applies(task_key: str, labels: list[str] | None) -> bool:
    """Should the seal-inversion gate run for this task at all?

    Fix work only: synthesized FIX-* tasks (the disposition loop's output)
    and tasks explicitly labeled as fixes/seals. Feature tasks are excluded
    on purpose — inverting a feature also reddens its tests, but features
    routinely carry config/docs side-files whose reversion proves nothing,
    and the audit's false-seal escapes were all fix-shaped.
    """
    if task_key.upper().startswith("FIX-"):
        return True
    return bool(_SEAL_LABELS.intersection(labels or []))


def partition_changed(
    worktree: Path, base: str, *, timeout_seconds: int = 30,
) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """The branch's changed files vs ``base`` as (tests, non_tests), each a
    list of ``(git_status_letter, path)``. Empty-both on git failure (the
    caller skips — fail open; the gate is an extra check, not the primary
    verification)."""
    try:
        proc = subprocess.run(
            ["git", "diff", "--name-status", f"{base}...HEAD"],
            cwd=str(worktree), capture_output=True, text=True,
            timeout=timeout_seconds,
        )
    except (subprocess.TimeoutExpired, OSError):
        return [], []
    if proc.returncode != 0:
        return [], []
    tests: list[tuple[str, str]] = []
    non_tests: list[tuple[str, str]] = []
    for line in proc.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        status, path = parts[0][:1], parts[-1]
        (tests if _TEST_PATH.search("/" + path) else non_tests).append(
            (status, path))
    return tests, non_tests


@dataclass(frozen=True)
class SealVerifyResult:
    """Outcome of one inversion run.

    ``outcome``: "passed" (suite went red without the fix — the seal is
    real), "failed" (suite stayed GREEN without the fix — the new tests
    prove nothing), "skipped" (gate doesn't apply; reason in detail), or
    "error" (the worktree could not be safely inverted/restored; detail
    says why — treated as a block because the tree state is now suspect).
    """
    outcome: str
    detail: str


def _git(worktree: Path, *args: str, timeout: int = 60) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=str(worktree), capture_output=True, text=True,
        timeout=timeout,
    )


def run_seal_inversion(
    *,
    worktree: Path,
    base: str,
    test_command: str,
    timeout_seconds: int,
    log: Callable[[str], None] = lambda _m: None,
) -> SealVerifyResult:
    """Invert the non-test half of the change, run the suite, restore.

    Precondition: the worktree is committed-clean (the committed-tree gate
    runs first). Restoration is ``git reset --hard HEAD`` plus deletion of
    any files the inversion resurrected that HEAD doesn't know; if restore
    fails the result is "error" so the caller blocks rather than trusting a
    possibly-mongrel tree.
    """
    tests, non_tests = partition_changed(worktree, base)
    if not tests:
        return SealVerifyResult(
            "skipped", "no test files changed — nothing claims to seal")
    if not non_tests:
        return SealVerifyResult(
            "skipped", "test-only change — no fix to invert")

    # --- invert: put every non-test file back to its base state ----------
    added = [p for st, p in non_tests if st == "A"]
    existing_at_base = [p for st, p in non_tests if st != "A"]
    try:
        if existing_at_base:
            proc = _git(worktree, "checkout", base, "--", *existing_at_base)
            if proc.returncode != 0:
                return SealVerifyResult(
                    "skipped",
                    f"could not revert to base for inversion: "
                    f"{proc.stderr.strip()[:300]}")
        for p in added:
            try:
                (worktree / p).unlink()
            except FileNotFoundError:
                pass
    except (subprocess.TimeoutExpired, OSError) as exc:
        _restore(worktree)
        return SealVerifyResult("error", f"inversion failed: {exc}")

    # --- run the suite over the inverted tree ----------------------------
    log("  seal-verify: running suite with the fix reverted (must go RED)")
    result = mv_mod.run_test_command(
        test_command, worktree=worktree, timeout_seconds=timeout_seconds,
        log=log,
    )

    # --- restore ----------------------------------------------------------
    if not _restore(worktree):
        return SealVerifyResult(
            "error",
            "worktree restore after inversion failed — tree state suspect")

    if result.passed:
        return SealVerifyResult(
            "failed",
            "suite stayed GREEN with the fix reverted — the new tests do "
            "not pin the change (false-passing seal). Tail of the green "
            "run:\n" + result.output_tail[-500:])
    return SealVerifyResult(
        "passed",
        f"suite went red without the fix (exit={result.exit_code})")


def _restore(worktree: Path) -> bool:
    """Bring the worktree back to HEAD exactly; True on success."""
    try:
        reset = _git(worktree, "reset", "--hard", "HEAD")
        if reset.returncode != 0:
            return False
        # Files resurrected from base that HEAD deleted are now untracked.
        clean = _git(worktree, "clean", "-fd")
        if clean.returncode != 0:
            return False
        status = _git(worktree, "status", "--porcelain")
        return status.returncode == 0 and not status.stdout.strip()
    except (subprocess.TimeoutExpired, OSError):
        return False
