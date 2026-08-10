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


class SealPartitionError(RuntimeError):
    """:func:`partition_changed` could not produce a partition at all.

    The base of the two failures below, and the reason they share one: the
    caller's only honest response to either is the same. ``([], [])`` — the
    value this class replaced on the git-failure path — is byte-identical to
    the answer a real code-only branch produces, and
    :func:`run_seal_inversion` reads it as one, reporting ``skipped, "no test
    files changed — nothing claims to seal"``. That sentence is a positive
    claim about the change's contents, and a function that cannot say "git
    would not tell me" has no way to keep it from being made.

    :func:`run_seal_inversion` maps every subclass to an ``error`` outcome,
    which the orchestrator blocks on.
    """


class SealDiffError(SealPartitionError):
    """git would not say what the change contains.

    A bad base ref, a corrupt repository, an index another process holds, a
    diff that timed out, a git that could not be executed. Until 2026-08-09
    this failed OPEN, on the argument that "a git failure means we learned
    nothing about the change" while an undecodable path (below) blocks because
    "we learned that the change contains a file we cannot classify". P4 ruled
    the asymmetry runs the wrong way: **there is no reading in which knowing
    less warrants proceeding while knowing more warrants blocking.** A bad base
    ref is the worst case — it makes every seal check in the run vacuous,
    silently, and each one reports that the fix carried no tests.

    The message names the base ref, so a refusal cannot be mistaken for an
    incidental bug in the caller's own arguments.
    """


class SealPathError(SealPartitionError):
    """A changed path git rendered in a form this gate cannot decode.

    We learned that the change contains a file we cannot put on either side of
    the partition. Guessing puts it on the non-test side, where the inversion
    would try to revert a name that resolves to nothing — or, for an added
    file, silently fail to delete it and then run the suite with the
    "reverted" fix still in place. Both report a judgement that was never made.
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
    list of ``(git_status_letter, path)``. Raises :class:`SealPartitionError`
    rather than answering when it has no answer.

    **``--no-renames``, so each side of a move is its own path.** This matches
    ``risk.collect_diff`` and ``role_protocol.changed_paths_between``, the
    repo's two other diff collectors, both of which pass it for the same
    reason: a rename is a delete plus an add with full paths, and a collector
    that has to decode git's two-path rename rendering is a collector with a
    special case in it. This one did not pass it, and the special case was live
    twice over, because ``--name-status`` renders a rename as
    ``R100<TAB>old<TAB>new`` and the loop below keeps ``parts[-1]`` — the NEW
    name, alone:

      * ``git mv`` of a non-test file put the new name on the non-test side,
        where :func:`run_seal_inversion` checked it out of ``base``. It does not
        exist at ``base`` by construction, so git exited 1, and until 2026-08-09
        that switched the whole gate off (``skipped``); the fix for THAT made it
        a hard block charged to every fix containing a rename. Neither is the
        gate doing its job. P4 ruled it must be inverted and judged: git names
        both paths, so the inversion is exact.
      * Worse and quieter: ``git mv impl.py tests/impl_test.py``. The new name
        is the only one the gate sees, :func:`is_test_path` calls it a test,
        ``non_tests`` comes back EMPTY, and the gate returns ``skipped,
        "test-only change — no fix to invert"`` — non-blocking — about a change
        that moved an implementation file. Measured 2026-08-09.

    Both are the same root cause and ``--no-renames`` removes it: the same tree
    arrives as ``D impl.py`` + ``A tests/impl_test.py``, each side classified on
    its own name, and :func:`run_seal_inversion` inverts it with no
    rename-specific code at all — check the deleted name out of ``base``, unlink
    the added one. A path-swap (``a``→``b`` and ``b``→``a`` in one change) comes
    through as two ``M`` lines rather than as two renames whose restore and
    delete sets collide, which is the other special case not written here.

    ``core.quotePath`` is deliberately NOT overridden, unlike
    ``changed_paths_between``: the decode below is the seal, and turning the
    quoting off would leave it untested.

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

    **A git failure raises too** (:class:`SealDiffError`), and does not return
    ``([], [])`` as it did until 2026-08-09 — see that class for the ruling.
    ``changed_paths_between``'s docstring already states the rule this now
    follows: "It must never return an empty tuple to mean failure."
    """
    argv = ["git", "diff", "--name-status", "--no-renames", f"{base}...HEAD"]
    try:
        proc = subprocess.run(
            argv, cwd=str(worktree), capture_output=True, text=True,
            timeout=timeout_seconds,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        raise SealDiffError(
            f"{' '.join(argv)} in {worktree} could not be run to completion: "
            f"{exc!r}; an empty partition from a command that did not run is "
            "indistinguishable from a change that really carries no test "
            "files, and the caller would report it as one"
        ) from exc
    if proc.returncode != 0:
        raise SealDiffError(
            f"{' '.join(argv)} in {worktree} exited {proc.returncode}: "
            f"{proc.stderr.strip()[:300] or '(no stderr)'}; git did not say "
            "what the change contains, and an empty partition is "
            "indistinguishable from a change that really carries no test "
            "files, and the caller would report it as one"
        )
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
    "error" (the change could not be safely inverted/restored, could not be
    partitioned at all, **or the inverted suite never finished** — it was
    killed at the timeout bound or never launched, so no verdict about the
    change exists to report; detail says why — treated as a block, because
    either the tree state is now suspect or the judgement was never made).

    That fourth case is the one a reader is most likely to file under
    "failed": a run that did not finish is not a run that went RED. It says
    nothing about whether the new tests pin the change, so it is a
    non-judgement and not an accusation. A run that DID finish is a verdict
    on whatever exit code it produced, including one the kernel chose — a
    signal death and an ordinary non-zero exit are the same evidence here,
    and deliberately so: a fix for a crash, inverted, legitimately kills the
    runner.
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
    except SealPartitionError as exc:
        # Fail closed, both ways. The tree is untouched, but there is no
        # partition, and "skipped — nothing claims to seal" would be the gate
        # reporting a judgement it never made: either the change contains a
        # file this gate cannot classify (`SealPathError`) or git never said
        # what the change contains at all (`SealDiffError`).
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
                # Fail closed, for the same reason as SealPartitionError above:
                # the tree was never fully inverted and the suite was never run,
                # so "skipped" — whose only two messages are "nothing claims to
                # seal" and "no fix to invert" — would report a judgement about
                # the change that this gate never made.
                #
                # AND RESTORE, like the ``OSError`` sibling below. The comment
                # that used to stand here said no restore was needed because
                # "git resolves every pathspec against the tree before writing
                # any of them". That is true of pathspec RESOLUTION and false of
                # WRITING, and resolution failures were the only kind this
                # branch ever saw, because the rename bug `partition_changed`
                # used to carry produced nothing else — and that bug is now
                # gone, so a write failure is the only way in.
                # Measured 2026-08-09: two fixed files with the second in
                # a mode-0555 directory — git writes the first, fails on the
                # second, exits 255, and the fix is left REVERTED on disk with
                # BOTH files reverted in the INDEX (`M  code.txt` /
                # `MM locked/helper.txt`). Even a single-file write failure
                # dirties the index, because git updates the index before the
                # worktree write can fail. The module's precondition is a
                # committed-clean worktree and every later gate reads this one,
                # so a bare "could not revert to base" — which reads as "nothing
                # was touched" — is the wrong report to leave behind.
                #
                # Sealed by `test_a_checkout_that_fails_partway_does_not_leave_
                # the_tree_mongrel` (P4 ruling 3, 2026-08-09).
                detail = (f"could not revert to base for inversion: "
                          f"{proc.stderr.strip()[:300]}")
                if not _restore(worktree):
                    return SealVerifyResult(
                        "error",
                        "worktree restore after inversion failed — tree state "
                        f"suspect. {detail}")
                return SealVerifyResult("error", detail)
        for p in added:
            try:
                (worktree / p).unlink()
            except FileNotFoundError:
                # STILL UNREACHABLE after `--no-renames`, re-checked 2026-08-09
                # and left alone. Every added path exists at HEAD and the
                # worktree is committed-clean, so the only thing that can have
                # removed one before this line is the checkout above — and it
                # removes an added path ONLY by writing a file over one of that
                # path's ancestor directories, which makes the unlink raise
                # NotADirectoryError (ENOTDIR), not ENOENT. Measured on the one
                # shape `--no-renames` newly routes here: base holds FILE `d`,
                # the branch holds `d/x` with identical content (git called that
                # `R100 d d/x` and it used to hit the checkout-failure branch);
                # now it is `D d` + `A d/x`, the checkout writes file `d`, and
                # the unlink raises `[Errno 20] Not a directory`, caught below
                # as an OSError and blocked with a restore. The live sibling —
                # an added file the inversion cannot delete — is sealed by
                # `test_an_added_file_the_inversion_cannot_delete_is_not_a_
                # verdict`, which is exactly that ENOTDIR path.
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

    if result.exit_code is None:
        # A run that did not finish is not a run that went RED. `run_test_command`
        # returns no exit code in exactly two cases, named in its result's own
        # docstring: the command was killed at the bound, or it never launched
        # (an OSError out of the subprocess machinery — E2BIG on a repo-supplied
        # `test:` string, a fork that could not be had, a missing worktree).
        # Neither produced evidence about the change, and both used to fall
        # through to the `passed` return below — the gate's certificate that the
        # seal is real — because `MechanicalVerifyResult.passed` is
        # `exit_code == 0`, so *not green* was read as *red*. A repo whose test
        # command cannot be launched then gets EVERY seal certified, silently,
        # for as long as the command stays that way.
        #
        # `failed` is not the answer either: that is the accusation that the new
        # tests are vacuous, and a suite that never ran is evidence for nothing.
        # `error` is already the outcome for "the judgement was never made" and
        # the orchestrator already blocks on it, so no new vocabulary is needed.
        #
        # WHICH of the two it was lives only in the annotation `run_test_command`
        # appends to `output_tail`, so the tail is carried into the detail: the
        # detail is what the orchestrator journals and what the panel's evidence
        # lens reads, and "it hung" and "it could not be started" want different
        # answers from a human.
        return SealVerifyResult(
            "error",
            "the inverted suite never reached a verdict: it was killed at the "
            f"{timeout_seconds}s bound or never launched (no exit code), so it "
            "said nothing about whether the new tests fail without the fix. "
            "Tail of the run:\n" + result.output_tail[-500:])

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
