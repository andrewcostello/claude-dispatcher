r"""Seals: the seal gate's "I could not decide" must never read as "fine".

The class
---------
`run_seal_inversion` answers a gate question with one of four strings, and
the orchestrator blocks on exactly two of them (`orchestrator.py`, twice:
`if seal_outcome in ("failed", "error")`). Every path through the function
that means *the judgement was never made* and returns one of the other two
is a gate reporting a clean answer it did not compute — the shape this
effort keeps finding. `seal_verify.SealPathError`'s own docstring names it:
"Both report a judgement that was never made."

WHAT WAS MEASURED (2026-08-09, worktree at `263298d`, full suite each time)
---------------------------------------------------------------------------
Every outcome-producing site in `run_seal_inversion` mutated one at a time
in a `cp -a` clone, `__pycache__` cleared before each run, 1805-row suite:

    site                                        mutation              noticed by
    SealPathError            -> error           error   -> skipped    NOTHING
    not tests                -> skipped         skipped -> error      1 row
    not non_tests            -> skipped         skipped -> error      1 row
    checkout rc!=0           -> skipped         skipped -> error      NOTHING
    inversion OSError        -> error           error   -> skipped    NOTHING
    restore failed           -> error           error   -> skipped    NOTHING
    suite stayed green       -> failed          failed  -> skipped    3 rows
    suite went red           -> passed          passed  -> skipped    2 rows
    partition rc!=0          -> ([], [])        -> raise              1 row
    partition Timeout/OSError-> ([], [])        -> raise              NOTHING
    orchestrator gate tuple  ("failed","error") drop "error"          NOTHING
    orchestrator row stamp   ("failed","error") drop "error"          NOTHING

So five of the eight outcome sites and BOTH orchestrator classifications
were unsealed, including the disclosed one and including the tuple that
makes `error` a block at all. This file closes every row above marked
NOTHING except the two named under DISPUTES.

THE `unlink` HAZARD, MEASURED RATHER THAN ARGUED
--------------------------------------------------
`run_seal_inversion` deletes each added non-test file with
`(worktree / p).unlink()` under `except FileNotFoundError: pass`. The
disclosure was that a path filed on the non-test side under a name that is
not the name on disk makes that swallow silent, and the suite then runs with
the fix still in place. Measured in a clone whose `partition_changed` files
an undecodable rendering instead of raising (i.e. the pre-fix behaviour),
over real repositories:

  * the unnameable file is the whole fix — the unlink misses, the suite runs
    with the fix in place, goes GREEN, and the gate returns **"failed"**:
    an honest seal accused of being vacuous.
  * one ASCII fix file plus one unnameable one, the seal pinning only the
    unnameable one — the ASCII half reverts, the suite goes red because of
    it, and the gate returns **"passed"**: a seal certified over a tree that
    still contains the half it claimed to pin.

Neither is observable in the outcome (both are ordinary verdicts) and
neither is observable in the logs: the only line emitted is the same
`running suite with the fix reverted` in both, and the swallow logs nothing.
On the fixed tree the run is refused before any of that happens, which is
what `test_the_undecodable_path_is_refused_before_the_suite_can_run` pins —
no suite run, no verdict, no half-inverted tree. The swallow itself is left
alone: it is unreachable by the disclosed route while the decode raises, and
its nearest live sibling — an added file the inversion *cannot* delete — is
sealed as a block by `test_an_added_file_the_inversion_cannot_delete...`.

PRODUCIBILITY
-------------
No row here asserts against a hand-made value. Each builds a real repository
and drives `run_seal_inversion`, and each names in its docstring what git
actually printed. The three awkward inputs and how production reaches them:

  * `A\t"tests/t\377.py"` — a filename containing byte 0xFF. POSIX permits
    every byte but NUL and `/`; git C-quotes high bytes under the default
    `core.quotePath`, which `partition_changed` does not override; the
    decoded bytes are not UTF-8 and `_unquote_git_path` raises. The file is
    created and committed by the fixture, and the rendering is asserted.
  * `R100\tmover.txt\tmoved.txt` — a plain `git mv`. Rename detection is on
    by default for `git diff`, and `--name-status` reports the NEW path,
    which does not exist at base, so `git checkout <base> -- <new>` exits 1
    with "pathspec ... did not match any file(s) known to git".
  * an untracked directory the suite leaves behind with mode 0555 — a test
    run that leaves artifacts it cannot clean up (docker-created files are
    the everyday case). `git clean -fd` exits non-zero and the restore fails.

DISPUTES FOR P4 — raised, not acted on
----------------------------------------
  1. **A git failure and a genuinely test-free change are the same
     `SealVerifyResult`, byte for byte.** `partition_changed` returns
     `([], [])` when git times out, cannot be executed, or exits non-zero
     (bad base ref, corrupt repo, unreadable index), and `run_seal_inversion`
     turns that into `("skipped", "no test files changed — nothing claims to
     seal")` — the identical value it returns for a change that really has no
     test in it. Measured: `run_seal_inversion(base="no-such-ref")` and a
     code-only branch produce equal `SealVerifyResult`s. That is this file's
     whole subject, and it is the ONE instance not sealed here, because
     `tests/test_seal_verify.py::test_partition_fails_open_on_bad_base`
     pins the fail-open as intended and `seal_verify.partition_changed`'s
     docstring documents it ("Empty-both on git failure ... fail open"). A
     row demanding a block would contradict a live seal, so it is P4's call.
     Note the internal contradiction it would have to resolve: `SealPathError`
     is justified in its own docstring by "an undecodable path means we
     learned that the change contains a file we cannot classify" versus "a
     git failure means we learned nothing about the change" — and *learned
     nothing* is the weaker position, not the stronger one.
     The second half of it (`partition` on Timeout/OSError) is likewise
     unsealed and likewise left alone.

  2. **`could not revert to base for inversion` is a fail-open and is
     RED here.** `test_a_renamed_non_test_file_does_not_switch_the_gate_off`
     is the one row in this file that is red-because-broken. It contradicts
     no seal: nothing in the suite touches that branch (measured above), and
     `SealVerifyResult`'s own docstring already assigns "the change could not
     be safely inverted" to `error`. The row asserts only that the outcome is
     one the orchestrator blocks on, so `error`, `failed` or a new blocking
     string are all fixes it accepts. It is left red rather than fixed here
     because this author writes seals only.

NON-VACUITY. Every row judges the awkward input AND its ordinary twin in the
same call, so no row can pass by the gate refusing everything, and each
docstring names the mutation that reddens it.
"""

from __future__ import annotations

import ast
import os
import stat
import subprocess
from pathlib import Path

import pytest

from claude_dispatcher import orchestrator as orch_mod
from claude_dispatcher import seal_verify as sv

# --------------------------------------------------------------------------- #
# What the orchestrator does with each outcome, written out.
# --------------------------------------------------------------------------- #

#: Every outcome the seal gate can hand the orchestrator, and whether the
#: orchestrator treats it as a block. Written out rather than derived, so that
#: adding an outcome to `seal_verify` reddens the totality row instead of
#: quietly enlarging a comprehension (the `FORBIDDEN_DISPUTED_GLOBS` lesson).
_OUTCOME_DISPOSITION: dict[str, bool] = {
    "passed": False,   # judged, and the seal is real
    "failed": True,    # judged, and the seal is vacuous
    "skipped": False,  # judged not to apply
    "error": True,     # NOT judged — the block that makes a non-judgement safe
}

_BLOCKING = frozenset(k for k, v in _OUTCOME_DISPOSITION.items() if v)


def _module_source(module) -> str:
    return Path(module.__file__).read_text(encoding="utf-8")


def _seal_outcome_comparisons() -> tuple[tuple[str, object], ...]:
    """Every comparison the orchestrator makes on a `seal_outcome`.

    Returns `(kind, payload)` pairs: `("in", frozenset)` for the membership
    tests that decide the block, `("is-not-none", None)` for the presence
    check on the journal row, and `("other", ast.dump)` for anything else —
    which is the point. A future `seal_outcome == "error"` or
    `!= "passed"` is a new classification site, and the totality row refuses
    to let one appear without being written down here.
    """
    tree = ast.parse(_module_source(orch_mod), filename="orchestrator.py")
    found: list[tuple[str, object]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Compare):
            continue
        names = [n for n in (node.left, *node.comparators)
                 if isinstance(n, ast.Name) and n.id == "seal_outcome"]
        if not names:
            continue
        op = node.ops[0]
        comparator = node.comparators[0]
        if (isinstance(op, ast.In) and isinstance(node.left, ast.Name)
                and isinstance(comparator, (ast.Tuple, ast.List, ast.Set))
                and all(isinstance(e, ast.Constant) for e in comparator.elts)):
            found.append(("in", frozenset(e.value for e in comparator.elts)))
        elif (isinstance(op, ast.IsNot) and isinstance(comparator, ast.Constant)
                and comparator.value is None):
            found.append(("is-not-none", None))
        else:
            found.append(("other", ast.dump(node)))
    return tuple(found)


def _outcomes_seal_verify_can_emit() -> frozenset[str]:
    """Every literal `SealVerifyResult(<outcome>, ...)` in `seal_verify`."""
    tree = ast.parse(_module_source(sv), filename="seal_verify.py")
    out: set[str] = set()
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "SealVerifyResult"):
            first = node.args[0] if node.args else None
            assert isinstance(first, ast.Constant) and isinstance(
                first.value, str), (
                "a SealVerifyResult is constructed with a non-literal outcome "
                f"at line {node.lineno}; the set of outcomes the orchestrator "
                "must classify is no longer readable from the source, and an "
                "unclassified outcome is a gate that proceeds on a "
                "non-judgement"
            )
            out.add(first.value)
    return frozenset(out)


def _outcomes_verify_seal_can_return() -> frozenset[str]:
    """Literal outcome strings `orchestrator._verify_seal` returns itself.

    The gate's second producer: it answers "skipped" for a repo with no test
    command without ever calling `seal_verify`.
    """
    tree = ast.parse(_module_source(orch_mod), filename="orchestrator.py")
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "_verify_seal")
    out: set[str] = set()
    for node in ast.walk(fn):
        if (isinstance(node, ast.Return) and isinstance(node.value, ast.Tuple)
                and node.value.elts
                and isinstance(node.value.elts[0], ast.Constant)
                and isinstance(node.value.elts[0].value, str)):
            out.add(node.value.elts[0].value)
    return frozenset(out)


# --------------------------------------------------------------------------- #
# Repository fixtures — real git, never a stub.
# --------------------------------------------------------------------------- #


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(["git", *args], cwd=str(repo), capture_output=True,
                          text=True)
    assert proc.returncode == 0, f"git {args!r} failed: {proc.stderr}"
    return proc.stdout


def _seal_repo(root: Path, name: str) -> Path:
    """`main` holds `code.txt` = broken and a trivial green suite.

    The suite command for every row is `sh tests/run.sh`; each row rewrites
    that file on its branch to be the seal under test.
    """
    repo = root / name
    (repo / "tests").mkdir(parents=True)
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "T")
    (repo / "code.txt").write_text("broken\n", encoding="utf-8")
    (repo / "tests" / "run.sh").write_text("exit 0\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "base")
    _git(repo, "checkout", "-q", "-b", "fix/seal")
    return repo


def _invert(repo: Path) -> tuple[sv.SealVerifyResult, list[str]]:
    """Drive the production entry point; return its result and its log."""
    logs: list[str] = []
    result = sv.run_seal_inversion(
        worktree=repo, base="main", test_command="sh tests/run.sh",
        timeout_seconds=60, log=logs.append,
    )
    return result, logs


def _name_status(repo: Path) -> str:
    return _git(repo, "diff", "--name-status", "main...HEAD")


# --------------------------------------------------------------------------- #
# 1. The disclosed direction: an undecodable path is a block, not a skip.
# --------------------------------------------------------------------------- #


def test_an_undecodable_path_is_a_block_and_never_nothing_claims_to_seal(
    tmp_path: Path,
) -> None:
    r"""A path git renders in a form the gate cannot decode must reach the
    orchestrator as a block; `skipped` must not be reachable from it.

    Two repositories of the same shape — a fix in `code.txt` plus one added
    test file — differing only in that test's filename: one carries the raw
    byte 0xFF, the other an ordinary accent. The accented twin is the control
    and is a real judgement, so the row cannot pass by everything blocking.

    Producible because: the fixture creates the 0xFF file with a bytes path
    and commits it, and the row asserts the line git actually printed —
    `A\t"tests/t\377.py"` — before asking the gate anything. That rendering
    reaches `_unquote_git_path` as `\377` under git's default
    `core.quotePath`, which `partition_changed` does not override, and the
    decoded byte string is not UTF-8.

    Green because correct: the landed decode already raises `SealPathError`
    and `run_seal_inversion` already maps it to `error`.
    Falsify: map `SealPathError` to
    `SealVerifyResult("skipped", "no test files changed — nothing claims to
    seal")` — measured, and the whole 1805-row suite stayed green before this
    row existed.
    """
    weird = _seal_repo(tmp_path, "weird")
    with open(bytes(weird) + b"/tests/t\xff.py", "wb") as handle:
        handle.write(b"assert True\n")
    (weird / "code.txt").write_text("fixed\n", encoding="utf-8")
    (weird / "tests" / "run.sh").write_text(
        "grep -q fixed code.txt\n", encoding="utf-8")
    _git(weird, "add", "-A")
    _git(weird, "commit", "-q", "-m", "fix + a seal git must quote")

    plain = _seal_repo(tmp_path, "plain")
    (plain / "tests" / "tést.py").write_text("assert True\n", encoding="utf-8")
    (plain / "code.txt").write_text("fixed\n", encoding="utf-8")
    (plain / "tests" / "run.sh").write_text(
        "grep -q fixed code.txt\n", encoding="utf-8")
    _git(plain, "add", "-A")
    _git(plain, "commit", "-q", "-m", "fix + an accented seal")

    assert 'A\t"tests/t\\377.py"' in _name_status(weird), (
        "the fixture no longer reproduces the input under test: git did not "
        f"C-quote the 0xFF filename. It printed {_name_status(weird)!r}"
    )

    weird_result, _ = _invert(weird)
    plain_result, _ = _invert(plain)

    assert weird_result.outcome in _BLOCKING, (
        "a changed path the gate cannot decode came back as "
        f"{weird_result.outcome!r}, which the orchestrator does not block on; "
        f"the same branch with a decodable filename is {plain_result.outcome!r}"
    )
    assert "nothing claims to seal" not in weird_result.detail, (
        "the gate reported that nothing in the change claims to seal — a "
        "judgement it never made, over a change whose test file it could not "
        f"even name: {weird_result.detail!r}"
    )
    assert plain_result.outcome == "passed", (
        "control: the decodable twin must be a real judgement, or the "
        "assertion above would pass by the gate blocking everything"
    )


def test_the_undecodable_path_is_refused_before_the_suite_can_run(
    tmp_path: Path,
) -> None:
    r"""The refusal happens BEFORE anything is inverted — which is what makes
    the `unlink` swallow unreachable by this route.

    `run_seal_inversion` deletes added non-test files with
    `unlink()` under `except FileNotFoundError: pass`. If an undecodable
    rendering were filed on the non-test side instead of raising, the delete
    would target a name nothing on disk has, miss silently, and the suite
    would run with that half of the fix in place. Measured in a clone with
    exactly that guess in place: the mixed case returns `passed` — a seal
    certified over a tree still holding the file it claimed to pin — and the
    single-file case returns `failed` against an honest seal. Neither is
    visible in the outcome, and the log line is the same one a correct run
    emits, because the swallow logs nothing.

    So the seal is on the refusal's position: no suite is run at all. The
    injected `log` sink is the production seam the orchestrator itself passes.

    Producible because: same fixture and same asserted rendering as the row
    above.

    Green because correct.
    Falsify: replace the `raise SealPathError(...)` with `path = rendered` —
    the pre-fix guess — and this row reddens on the log, because the suite
    then runs over a half-inverted tree.
    """
    weird = _seal_repo(tmp_path, "weird")
    with open(bytes(weird) + b"/mod\xff.py", "wb") as handle:
        handle.write(b"FIXED\n")
    (weird / "code.txt").write_text("fixed\n", encoding="utf-8")
    (weird / "tests" / "run.sh").write_text(
        "grep -q fixed code.txt\n", encoding="utf-8")
    _git(weird, "add", "-A")
    _git(weird, "commit", "-q", "-m", "two fix files, one unnameable")

    control = _seal_repo(tmp_path, "control")
    (control / "mod.py").write_text("FIXED\n", encoding="utf-8")
    (control / "code.txt").write_text("fixed\n", encoding="utf-8")
    (control / "tests" / "run.sh").write_text(
        "grep -q fixed code.txt\n", encoding="utf-8")
    _git(control, "add", "-A")
    _git(control, "commit", "-q", "-m", "two fix files, both nameable")

    assert 'A\t"mod\\377.py"' in _name_status(weird), (
        "the fixture no longer reproduces the input under test: "
        f"{_name_status(weird)!r}"
    )

    weird_result, weird_logs = _invert(weird)
    control_result, control_logs = _invert(control)

    assert weird_logs == [], (
        "the gate ran the suite over a tree it had already failed to invert "
        f"(logged {weird_logs!r}); with one of the change's files unnameable, "
        "whatever the suite says is a verdict about a different tree"
    )
    assert weird_result.outcome in _BLOCKING, (
        f"no suite was run and the outcome was {weird_result.outcome!r}, "
        "which the orchestrator does not block on — a gate that neither "
        "measured nor stopped"
    )
    assert control_logs and control_result.outcome == "passed", (
        "control: the nameable twin must actually run its suite "
        f"({control_logs!r}) and reach a verdict ({control_result.outcome!r}), "
        "or the assertions above would pass by the gate never running anything"
    )


# --------------------------------------------------------------------------- #
# 2. The rest of the outcome mapping, swept.
# --------------------------------------------------------------------------- #


def test_an_added_file_the_inversion_cannot_delete_is_not_a_verdict(
    tmp_path: Path,
) -> None:
    """An added non-test file the inversion cannot remove must block.

    The live sibling of the `unlink` swallow: here the delete does not miss
    silently, it fails loudly, and the question is whether the gate turns
    that into a verdict. Base holds a FILE `helper.txt`; the branch replaces
    it with a DIRECTORY of the same name holding the fix. Inverting checks
    `helper.txt` back out as a file, after which `helper.txt/impl.py` — an
    added non-test path the gate is holding — cannot be unlinked at all
    (ENOTDIR).

    Producible because: the swap is committed with real git and
    `--name-status` prints `D\thelper.txt` beside `A\thelper.txt/impl.py`;
    the failure is the kernel's, raised by `Path.unlink`.

    Green because correct: the OSError is caught, the tree restored, and the
    outcome is `error`.
    Falsify: return `skipped` instead of `error` from the `inversion failed`
    branch — measured, and nothing in the suite noticed before this row.
    """
    swap = _seal_repo(tmp_path, "swap")
    (swap / "helper.txt").write_text("base helper\n", encoding="utf-8")
    _git(swap, "add", "-A")
    _git(swap, "commit", "-q", "-m", "helper is a file at base")
    _git(swap, "branch", "-f", "main", "HEAD")
    (swap / "helper.txt").unlink()
    (swap / "helper.txt").mkdir()
    (swap / "helper.txt" / "impl.py").write_text("FIXED\n", encoding="utf-8")
    (swap / "code.txt").write_text("fixed\n", encoding="utf-8")
    (swap / "tests" / "run.sh").write_text(
        "grep -q fixed code.txt\n", encoding="utf-8")
    _git(swap, "add", "-A")
    _git(swap, "commit", "-q", "-m", "helper becomes a directory")

    ordinary = _seal_repo(tmp_path, "ordinary")
    (ordinary / "helper.txt").write_text("new helper\n", encoding="utf-8")
    (ordinary / "code.txt").write_text("fixed\n", encoding="utf-8")
    (ordinary / "tests" / "run.sh").write_text(
        "grep -q fixed code.txt\n", encoding="utf-8")
    _git(ordinary, "add", "-A")
    _git(ordinary, "commit", "-q", "-m", "fix + an ordinary added helper")

    status = _name_status(swap)
    assert "D\thelper.txt\n" in status and "A\thelper.txt/impl.py" in status, (
        f"the fixture no longer reproduces the file/directory swap: {status!r}"
    )

    swap_result, _ = _invert(swap)
    ordinary_result, _ = _invert(ordinary)

    assert swap_result.outcome in _BLOCKING, (
        "the inversion could not delete a file it was holding and the gate "
        f"returned {swap_result.outcome!r} anyway: {swap_result.detail!r}"
    )
    assert ordinary_result.outcome == "passed", (
        "control: an ordinary added non-test file must still be inverted and "
        "judged, or the row above would pass by every added file blocking"
    )


def test_a_restore_the_gate_could_not_complete_is_not_a_verdict(
    tmp_path: Path,
) -> None:
    """A verdict over a tree the gate could not put back must block.

    `run_seal_inversion` reverts the fix, runs the suite, then restores with
    `reset --hard` + `clean -fd` + a `status --porcelain` check. If the
    restore fails the verdict is worthless twice over: the tree left behind
    is a mongrel, and every later gate reads it.

    Producible because: the branch's own suite leaves an untracked directory
    at mode 0555, so `git clean -fd` exits non-zero — the everyday shape is a
    test run leaving artifacts it does not own (docker-created files). The
    control leaves an ordinary untracked file, which `clean -fd` removes, so
    the row cannot pass by any leftover blocking.

    Green because correct.
    Falsify: return `skipped` from the restore-failure branch — measured, and
    nothing in the suite noticed before this row.
    """
    if os.geteuid() == 0:
        pytest.skip("root ignores directory permissions; the input is "
                    "unproducible here and a green row would be a lie")

    stuck = _seal_repo(tmp_path, "stuck")
    (stuck / "code.txt").write_text("fixed\n", encoding="utf-8")
    (stuck / "tests" / "run.sh").write_text(
        "grep -q fixed code.txt\nrc=$?\n"
        "mkdir -p junk && echo a > junk/a.txt && chmod 555 junk\n"
        "exit $rc\n", encoding="utf-8")
    _git(stuck, "add", "-A")
    _git(stuck, "commit", "-q", "-m", "fix + a suite that leaves a locked dir")

    tidy = _seal_repo(tmp_path, "tidy")
    (tidy / "code.txt").write_text("fixed\n", encoding="utf-8")
    (tidy / "tests" / "run.sh").write_text(
        "grep -q fixed code.txt\nrc=$?\n"
        "mkdir -p junk && echo a > junk/a.txt\n"
        "exit $rc\n", encoding="utf-8")
    _git(tidy, "add", "-A")
    _git(tidy, "commit", "-q", "-m", "fix + a suite that leaves a plain dir")

    try:
        stuck_result, _ = _invert(stuck)
        tidy_result, _ = _invert(tidy)

        assert (stuck / "junk").exists(), (
            "the fixture no longer reproduces the input under test: the "
            "unremovable directory is gone, so the restore did not fail"
        )
        assert stuck_result.outcome in _BLOCKING, (
            "the gate could not restore the worktree and returned "
            f"{stuck_result.outcome!r}: {stuck_result.detail!r}"
        )
        assert tidy_result.outcome == "passed", (
            "control: a suite whose leftovers `clean -fd` can remove must "
            "still reach a verdict, or the row above would pass by any "
            "leftover blocking"
        )
    finally:
        for repo in (stuck, tidy):
            junk = repo / "junk"
            if junk.exists():
                junk.chmod(stat.S_IRWXU)


def test_a_renamed_non_test_file_does_not_switch_the_gate_off(
    tmp_path: Path,
) -> None:
    """RED — the second fail-open, found by sweeping the outcome mapping.

    A fix that RENAMES a non-test file turns the whole seal-inversion gate
    off, non-blocking, and says so in a `skipped`. `--name-status` reports a
    rename as `R100\told\tnew` and the code takes `parts[-1]`, so the path
    handed to `git checkout <base> -- ...` is the NEW name, which does not
    exist at base; git exits 1 with "pathspec ... did not match any file(s)
    known to git"; the gate returns
    `("skipped", "could not revert to base for inversion: ...")`. The tree is
    never inverted and the suite is never run, so this is a non-judgement
    reported as a judgement not to apply — the same shape as the disclosed
    one, in the branch immediately below it.

    Producible because: a plain `git mv`. The fixture asserts the `R` line
    git printed, and rename detection is git's default for `git diff`.

    Red now: `skipped`.
    Green when: the outcome is one the orchestrator blocks on. The row does
    not dictate which — `error` is what `SealVerifyResult`'s own docstring
    assigns to "the change could not be safely inverted", but reverting by
    the OLD name (making the gate work for renames) and returning a real
    verdict also satisfies this row, and is the better fix.
    Falsify: the un-renamed control twin is the second judgement here, so a
    change that made everything block reddens on it.
    """
    renamed = _seal_repo(tmp_path, "renamed")
    (renamed / "mover.txt").write_text("x" * 400 + "\n", encoding="utf-8")
    _git(renamed, "add", "-A")
    _git(renamed, "commit", "-q", "-m", "a file worth renaming")
    _git(renamed, "branch", "-f", "main", "HEAD")
    _git(renamed, "mv", "mover.txt", "moved.txt")
    (renamed / "code.txt").write_text("fixed\n", encoding="utf-8")
    (renamed / "tests" / "run.sh").write_text(
        "grep -q fixed code.txt\n", encoding="utf-8")
    _git(renamed, "add", "-A")
    _git(renamed, "commit", "-q", "-m", "fix + a rename")

    kept = _seal_repo(tmp_path, "kept")
    (kept / "mover.txt").write_text("x" * 400 + "\n", encoding="utf-8")
    _git(kept, "add", "-A")
    _git(kept, "commit", "-q", "-m", "a file worth renaming")
    _git(kept, "branch", "-f", "main", "HEAD")
    (kept / "code.txt").write_text("fixed\n", encoding="utf-8")
    (kept / "tests" / "run.sh").write_text(
        "grep -q fixed code.txt\n", encoding="utf-8")
    _git(kept, "add", "-A")
    _git(kept, "commit", "-q", "-m", "fix, no rename")

    status = _name_status(renamed)
    assert "\nR" in "\n" + status and "moved.txt" in status, (
        "the fixture no longer reproduces the input under test: git did not "
        f"report the rename as a rename. It printed {status!r}"
    )

    renamed_result, renamed_logs = _invert(renamed)
    kept_result, _ = _invert(kept)

    assert renamed_logs == [], (
        "sanity: this row is about a gate that never ran the suite; it "
        f"logged {renamed_logs!r}"
    )
    assert renamed_result.outcome in _BLOCKING, (
        "a fix containing a `git mv` switched the seal-inversion gate off: "
        f"{renamed_result.outcome!r} / {renamed_result.detail!r}. Nothing was "
        "inverted and no suite was run, so the change's new tests were never "
        "asked to fail without the fix — and the orchestrator proceeds"
    )
    assert kept_result.outcome == "passed", (
        "control: the same branch without the rename must be judged, or the "
        "row above would pass by everything blocking"
    )


# --------------------------------------------------------------------------- #
# 3. Totality: no outcome the gate can emit is unclassified.
# --------------------------------------------------------------------------- #


def test_every_outcome_the_seal_gate_can_emit_is_classified_by_the_orchestrator(
    ) -> None:
    """The open-set defect, on the tuple that makes `error` a block.

    `orchestrator` decides the whole gate with `seal_outcome in ("failed",
    "error")`, written twice. Nothing today ties that tuple to the set of
    strings `seal_verify` can actually produce, so a fifth outcome — or a
    fourth removed from the tuple — changes what the gate does and reddens
    nothing. Measured: dropping `"error"` from either occurrence left the
    full 1805-row suite green. This is the same shape already repaired in
    `FORBIDDEN_DISPUTED_GLOBS`, the drift gate's artifact filter and the
    guard dispatch.

    The disposition of every outcome is written out in `_OUTCOME_DISPOSITION`
    rather than derived, so a new one cannot join a comprehension silently:
    it must be classified here, by a human, as judged-or-not.

    Producible because: this reads the two modules' own source. The set of
    emitted outcomes is every literal `SealVerifyResult(...)` in
    `seal_verify` plus every literal `_verify_seal` returns itself — both are
    the values the orchestrator receives at runtime, and the row refuses a
    non-literal outcome rather than skipping it.

    Green because correct (today's tuple matches today's outcomes).
    Falsify: drop `"error"` from either tuple; or add a new outcome string to
    `run_seal_inversion` without adding it here.
    """
    emitted = _outcomes_seal_verify_can_emit() | _outcomes_verify_seal_can_return()

    assert emitted == frozenset(_OUTCOME_DISPOSITION), (
        "the seal gate's outcome vocabulary changed; classify every member "
        "here as blocking or proceeding before the orchestrator sees it: "
        f"{sorted(emitted ^ frozenset(_OUTCOME_DISPOSITION))}"
    )

    comparisons = _seal_outcome_comparisons()
    unexpected = [c for c in comparisons if c[0] == "other"]
    assert not unexpected, (
        "the orchestrator classifies `seal_outcome` in a way this seal does "
        f"not know about: {unexpected!r}. A second, differently-shaped test "
        "is a second policy"
    )

    memberships = [payload for kind, payload in comparisons if kind == "in"]
    assert len(memberships) == 2, (
        "the orchestrator's `seal_outcome in (...)` sites changed in number "
        f"(found {len(memberships)}: {memberships!r}); the gate decision and "
        "the journal row stamp are both classifications and both must be "
        "checked"
    )
    for members in memberships:
        assert members == _BLOCKING, (
            f"an orchestrator gate blocks on {sorted(members)} while the seal "
            f"gate's blocking outcomes are {sorted(_BLOCKING)}; the "
            f"difference {sorted(members ^ _BLOCKING)} either proceeds on a "
            "non-judgement or blocks on a judgement that was fine"
        )
