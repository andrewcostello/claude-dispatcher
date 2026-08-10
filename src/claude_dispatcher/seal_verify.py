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

#: Appended by :func:`is_test_path` to a probe that ends in a newline, so the
#: pattern's one ``$`` cannot treat that newline as the end of the string. NUL
#: is the one byte a POSIX filename cannot contain, so it can never be part of
#: a real path and appears in no alternative of :data:`_TEST_PATH`.
_NOT_A_PATH_CHARACTER = "\0"


class SealPathError(RuntimeError):
    """A changed path git rendered in a form this gate cannot decode.

    Raised by :func:`partition_changed`; :func:`run_seal_inversion` maps it to
    an ``error`` outcome. Distinct from the git failures that fail OPEN
    (``([], [])`` → "nothing claims to seal"): a git failure means we learned
    nothing about the change, while an undecodable path means we learned that
    the change contains a file we cannot put on either side of the partition.
    Guessing puts it on the non-test side, where the inversion would try to
    revert a name that resolves to nothing — or, for an added file, silently
    fail to delete it and then run the suite with the "reverted" fix still in
    place. Both report a judgement that was never made.
    """


def is_test_path(path: str) -> bool:
    r"""Does this repo consider ``path`` one of "the tests"?

    The public face of :data:`_TEST_PATH`, so that every consumer asks the
    question the same way. ``path`` is posix, as git emits.

    **Two normalisations, and the docstring used to be wrong about the first.**

    The leading ``"/"`` is prefixed so that a top-level ``tests/x.py`` exhibits
    the ``/tests?/`` alternative — the same reason ``pkg/tests/x.py`` does. It
    is NOT, as this said until 2026-08-09, what the pattern's ``^``-anchored
    alternatives "need": prefixing a slash puts a ``/`` at position 0, so
    ``^tests?/`` and ``^spec/`` can never match anything at all. They are dead
    alternatives, harmless only because ``/tests?/`` and ``/spec/`` cover
    exactly the paths they were meant to. They are left in place rather than
    deleted because ``tests/test_role_protocol_table.py::_TEST_PATH_PROBES``
    keys its table on the literal text of each alternative and checks those
    keys against the live pattern; removing them is a seal amendment, and the
    prose correction is the part that can land here.

    The trailing sentinel is the fix for a real over-block. ``_TEST_PATH``'s
    one end-anchored alternative is ``conftest\.py$``, and Python's ``$``
    matches at the end of the string OR immediately before a string-final
    newline — the exact ``$``-for-``\Z`` mistake ``risk._compiled``'s docstring
    names and forbids, sitting unsealed in this sibling matcher. So
    ``src/conftest.py<LF>``, a DIFFERENT file that a body agent may
    legitimately add, was judged one of the repo's tests and denied to it.

    The pattern itself is not touched, for the reason above; instead, when the
    probe ends with a newline a character no alternative can match is appended,
    which leaves ``$`` nowhere to land. That is exactly ``\Z`` semantics and
    not an approximation: ``$`` differs from ``\Z`` only on a string ending in
    ``\n``, and on such a string a ``$`` match at the TRUE end is impossible
    (``conftest\.py`` cannot be followed by end-of-string when the string ends
    in a newline), so every ``$`` match there is the spurious one. Appending
    can create no new match either — the sentinel appears in no alternative,
    and no alternative can reach past the end of the old string except through
    ``$``. Unanchored alternatives are unaffected: ``tests/x.py<LF>`` is still
    a test, via ``/tests?/``.

    There is exactly one matcher for this question and it is here: the build
    protocol's role gate (``role_protocol.evaluate_changed_paths``, deciding
    which paths a bodies/scaffold agent may not touch) calls this rather than
    keeping a second list. Two disagreeing notions of "is this a test file"
    is invariant 5's failure mode, and it was live: six of this pattern's
    alternatives were uncovered by the role table's globs, so a body agent
    could add ``web/__tests__/app.js`` — a seal by this module's reckoning —
    and the role gate reported CLEAN (implementation-plan D1 P2 rulings).
    """
    probe = "/" + path
    if probe.endswith("\n"):
        probe += _NOT_A_PATH_CHARACTER
    return bool(_TEST_PATH.search(probe))


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
    r"""The branch's changed files vs ``base`` as (tests, non_tests), each a
    list of ``(git_status_letter, path)``. Empty-both on git failure (the
    caller skips — fail open; the gate is an extra check, not the primary
    verification).

    **Every path is DECODED.** ``--name-status`` prints a path git must quote
    in its C-quoted rendering — ``"tests/t\303\251st_thing.py"`` for
    ``tests/tést_thing.py`` — and a rendering is not a path:
    :func:`is_test_path` is a regex over ``/tests?/`` and friends, so a
    rendering that begins with ``"`` is filed under NON-tests. The consequence
    was the whole false-passing-seal gate switching itself off by a filename:
    with no path recognised as a test, :func:`run_seal_inversion` returned
    ``skipped, "no test files changed — nothing claims to seal"`` and never
    inverted anything. An accent in a new test's filename was enough.

    Decoding goes through :func:`role_protocol._unquote_git_path` — the repo's
    one reverse of ``quote_c_style``, shared with ``changed_paths_between``,
    ``risk.collect_diff`` and ``blast_radius.changed_files``, imported inside
    the function so this module's import graph is unchanged. NOT a
    ``strip('"')``: a directory can really be named ``"tests"``, git renders it
    as ``"\"tests\"/x.py"``, and stripping would start calling an ordinary
    source file one of the repo's seals.

    A path that will not decode raises :class:`SealPathError` rather than being
    filed on a side that was guessed.
    """
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
    from .role_protocol import _unquote_git_path

    tests: list[tuple[str, str]] = []
    non_tests: list[tuple[str, str]] = []
    for line in proc.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        status, rendered = parts[0][:1], parts[-1]
        try:
            path = _unquote_git_path(rendered)
        except ValueError as exc:
            raise SealPathError(
                f"git diff --name-status {base}...HEAD in {worktree} named "
                f"{rendered!r}, which is not a decodable C-quoted path: {exc}; "
                "a path that cannot be decoded cannot be put on either side of "
                "the test/non-test partition"
            ) from exc
        (tests if is_test_path(path) else non_tests).append(
            (status, path))
    return tests, non_tests


@dataclass(frozen=True)
class SealVerifyResult:
    """Outcome of one inversion run.

    ``outcome``: "passed" (suite went red without the fix — the seal is
    real), "failed" (suite stayed GREEN without the fix — the new tests
    prove nothing), "skipped" (gate doesn't apply; reason in detail), or
    "error" (the change could not be safely inverted/restored, or could not be
    partitioned at all; detail says why — treated as a block, because either
    the tree state is now suspect or the judgement was never made).
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
    try:
        tests, non_tests = partition_changed(worktree, base)
    except SealPathError as exc:
        # Fail closed. The tree is untouched, but the change contains a file
        # this gate cannot classify, and "skipped — nothing claims to seal"
        # would be the gate reporting a judgement it never made.
        return SealVerifyResult("error", str(exc))
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
                # Fail closed, for the same reason as SealPathError above: the
                # tree was never inverted and the suite was never run, so
                # "skipped" — whose only two messages are "nothing claims to
                # seal" and "no fix to invert" — would report a judgement about
                # the change that this gate never made.
                #
                # The everyday cause is a RENAME. `--name-status` renders one as
                # `R100<TAB>old<TAB>new` and :func:`partition_changed` keeps
                # ``parts[-1]``, so the pathspec here is the NEW name, which by
                # construction does not exist at ``base``; git exits 1 with
                # "pathspec ... did not match any file(s) known to git". Any fix
                # containing a `git mv` of a non-test file therefore switched the
                # whole gate off, silently and non-blocking.
                #
                # Reverting by the OLD name instead — making the gate actually
                # work on a renaming fix — was measured and does work, but it is
                # NOT what
                # `test_a_renamed_non_test_file_does_not_switch_the_gate_off`
                # accepts: that row also pins `logs == []`, i.e. that no suite is
                # run, and a real verdict necessarily runs one and comes back
                # `passed`. Whether the gate should invert renames rather than
                # block on them is a seal amendment, not a body change.
                #
                # git resolves every pathspec against the tree before writing any
                # of them, so on this path the worktree is untouched and needs no
                # restore.
                return SealVerifyResult(
                    "error",
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
