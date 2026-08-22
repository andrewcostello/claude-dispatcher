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
makes `error` a block at all. As first written this file closed every row
above marked NOTHING except the two named under DISPUTES; both of those are
now ruled on and sealed (see RULINGS), so every row is closed.

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

RULINGS (P4, 2026-08-09) — the disputes above, decided
--------------------------------------------------------
The two disputes as raised are preserved in git history at `a5bbcc3`; a
third was raised by the body author of `7569760` and a fourth is the hole
that ruling 2 opens. Rulings 1-3 are each a seal that is RED against this
tree and awaits a SEPARATE body change; ruling 4's seal is green. Nothing in
`src/` was touched by the adjudication except one stale comment, named below.

  1. **A git failure must BLOCK, like an undecodable path.** UPHELD. The
     seal author's argument is correct and decides it: `SealPathError`'s
     docstring blocks because "an undecodable path means we learned that the
     change contains a file we cannot classify" and fails open on a git
     failure because it "means we learned nothing about the change" — and
     learned nothing is the weaker position. There is no reading in which
     knowing less warrants proceeding while knowing more warrants blocking.
     `_OUTCOME_DISPOSITION` below already assigns `error` to "NOT judged",
     and a git failure is definitionally not judged. The counter-argument —
     `partition_changed`'s "the gate is an extra check, not the primary
     verification" — proves too much: it justifies equally the two fail-opens
     this effort has already closed (the undecodable path, the rename), so if
     it were sound none of the three should have been closed. And the harm is
     concrete rather than theoretical: `("skipped", "no test files changed —
     nothing claims to seal")` is a positive claim about the change's
     contents, byte-identical to what a real code-only branch gets, emitted
     when git never said what the contents were. A bad base ref is the worst
     case — it makes every seal check in the run vacuous, silently.
     Sealed by `test_a_git_failure_is_not_a_change_with_no_tests_in_it`, and
     `tests/test_seal_verify.py::test_partition_fails_open_on_bad_base` — the
     live seal that pinned the fail-open as intended — is amended in the same
     commit to pin the block. Neither row names an exception class; the
     mechanism is the body author's choice. `partition_changed`'s docstring
     still documents the fail-open, correctly, because `src/` still does it.

  2. **A renaming fix must be INVERTED AND JUDGED, not blocked.** The
     dispute was raised as "this row is red and any blocking outcome fixes
     it". Measured, that was not what the row said: its FIRST assertion was
     `renamed_logs == []`, so the revert-by-old-name fix its own docstring
     called "the better fix" was rejected on the log line before the outcome
     was ever read. The body author, finding no route the row left open, took
     the blocking one, and `7569760` merged it. So the seal enforced the
     opposite of what it advertised and selected the weaker of the two fixes.
     Ruling: a `git mv` is not an undecidable input. `--name-status` hands
     the gate BOTH names, so the inversion is exact and total — check `old`
     out of base, delete `new` — and a gate that can answer the question it
     exists to ask must answer it. Blocking instead charges a hard stop to
     every fix containing a rename, an ordinary and legitimate shape;
     measured, the previous behaviour switched the gate off for exactly the
     same set of changes, and neither is the gate doing its job. The block is
     kept where it belongs: see ruling 3.
     `test_a_renamed_non_test_file_does_not_switch_the_gate_off` is amended
     to pin the inversion, observed in the tree rather than inferred from the
     outcome.

  3. **The checkout-failure branch must restore.** RAISED BY THE BODY AUTHOR,
     ruled here. That branch is the one exit from `run_seal_inversion` that
     does not call `_restore`, justified in a comment by "git resolves every
     pathspec against the tree before writing any of them". True of pathspec
     RESOLUTION, false of WRITING, and only resolution failures were ever
     exercised because the rename bug produced nothing else. Measured
     2026-08-09: with a read-only directory holding the second of two fixed
     files, git writes the first and then fails, and the gate returns without
     restoring — the fix left reverted on disk, both files reverted in the
     INDEX, and a detail that reads as "nothing was touched". This is why
     ruling 2 does not weaken the gate: the block stays, and it now has a
     seal that reaches it by a route that is a real failure rather than an
     artefact of `parts[-1]`. Sealed by
     `test_a_checkout_that_fails_partway_does_not_leave_the_tree_mongrel`.

  4. **What ruling 2 costs, paid.** Ruling 2 takes the rename away from the
     checkout-failure branch, and the rename was the only BEHAVIOURAL route
     to it — so the flip that started all of this, that branch returning
     `skipped`, goes back to being invisible. Measured in a clone carrying
     rulings 2+3: `error` -> `skipped` there reddened NOTHING in the 1827-row
     suite. Three other routes were tried and none reaches it (they are named
     in the row). Paid structurally instead, by
     `test_the_gate_stands_down_only_on_the_two_applicability_judgements`:
     `skipped` is the gate's only non-blocking outcome, so every construction
     of it is a place the gate can switch itself off, and all of them must be
     judgements about the change rather than reports of a step that failed.
     That is a stronger statement than the row it replaces — it covers the
     `OSError`, restore-failure and `SealPathError` branches too — and it is
     the one row in this file whose input is the source rather than a
     repository, which is a real cost and is why the behavioural routes were
     exhausted first.

  The one `src/` edit: the comment above the checkout-failure branch told a
  future body author that this file's rename row "pins `logs == []`" and so
  forbids inverting renames. After ruling 2 that is exactly backwards, and a
  stale comment pointing the next author at the rejected route is the same
  trap in a different file. Comment text only — no behaviour, no AST change,
  and the totality row below reads the module's AST, not its comments.

NON-VACUITY. Every row that drives the gate judges the awkward input AND its
ordinary twin in the same call, so no row can pass by the gate refusing
everything, and each docstring names the mutation that reddens it. Verified
2026-08-09 by a mutation that makes `run_seal_inversion` return `error`
unconditionally: it reddens all seven of this file's gate-driving rows (ten
across both seal files). The two rows whose input is
`seal_verify`'s own source instead of a repository — the totality row and
ruling 4's — have no twin, and each says in its own docstring why it is
structural.
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


def _skipped_details_in_run_seal_inversion() -> tuple[str, ...]:
    """Every `SealVerifyResult("skipped", <literal>)` in `run_seal_inversion`.

    `skipped` is the one non-blocking outcome the function can emit, so every
    occurrence of it is a place the gate can switch itself off. Returns the
    detail literals, in source order, and refuses a non-literal detail — an
    f-string there would mean the reasons this gate stands down are no longer
    readable from the source.
    """
    tree = ast.parse(_module_source(sv), filename="seal_verify.py")
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef)
              and n.name == "run_seal_inversion")
    out: list[str] = []
    for node in ast.walk(fn):
        if not (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "SealVerifyResult"):
            continue
        first = node.args[0] if node.args else None
        if not (isinstance(first, ast.Constant) and first.value == "skipped"):
            continue
        detail = node.args[1] if len(node.args) > 1 else None
        assert isinstance(detail, ast.Constant) and isinstance(
            detail.value, str), (
            "a `skipped` is constructed with a non-literal reason at line "
            f"{node.lineno}; the reasons this gate stands down must stay "
            "readable from the source"
        )
        out.append(detail.value)
    return tuple(out)


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
    """RED — a renaming fix must be INVERTED AND JUDGED, not blocked.

    AMENDED BY P4, 2026-08-09. What this row used to say, and why it was
    wrong, is recorded under RULINGS in the module docstring. In short: it
    advertised in its own docstring that reverting by the OLD name "also
    satisfies this row, and is the better fix", while its FIRST assertion was
    `renamed_logs == []` — and a gate that reaches a real verdict necessarily
    runs the suite and logs. It therefore rejected the better fix on the log
    line before ever reading the outcome, and the body author took the
    blocking route because this row left no other one open. A seal that
    forbids the correct implementation is not enforcing a policy; it is a
    trap, and amending it is a P4 act.

    The policy this row now pins: `git mv` of a non-test file is not an
    undecidable input. `--name-status` prints `R100\told\tnew` and hands the
    gate BOTH names, so the correct inversion is exact and total — check
    `old` out of base, delete `new` — and the gate can therefore answer the
    question it exists to ask. Declining to (the merged `error`) charges a
    hard block to every fix that contains a rename, which is an ordinary,
    legitimate shape; neither that nor the original `skipped` is the gate
    doing its job. This does NOT delete the block: a checkout that fails for
    a reason that is really a failure still blocks, and
    `test_a_checkout_that_fails_partway_does_not_leave_the_tree_mongrel`
    holds that branch down.

    Producible because: a plain `git mv`. The fixture asserts the exact `R`
    line git printed, and rename detection is git's default for `git diff`.

    THE INVERSION IS OBSERVED, NOT INFERRED. Pinning the outcome alone would
    be satisfiable by a gate that ignored the renamed pair entirely and ran
    the suite over `code.txt` only — the suite would still go red, still
    return `passed`, and the rename half would never have been inverted. So
    the branch's own suite records what the tree looked like DURING the
    inverted run, to an absolute path outside the repository (`_restore`'s
    `clean -fd` would take an in-repo witness). Both halves are checked:
    `mover.txt` back, `moved.txt` gone.

    Red now: `error` — measured 2026-08-09 against `7569760`; nothing is
    inverted, no suite is run, no witness is written.
    Green when: `partition_changed` files a rename as `("R", old)` for the
    checkout plus `("A", new)` for the unlink. Measured in a clone: partition
    `[('M','code.txt'), ('R','mover.txt'), ('A','moved.txt')]`, witness
    `MOVER-RESTORED\\nMOVED-REMOVED`, outcome `passed`, worktree clean. That
    is a SEPARATE body change; this row is the seal for it and is red until
    it lands.
    Falsify: restore `mover.txt` without deleting `moved.txt` (witness says
    MOVED-STILL-PRESENT); delete `moved.txt` without restoring `mover.txt`
    (witness says MOVER-MISSING); make everything block (the un-renamed
    control twin, judged in the same call, reddens).
    """
    witness = tmp_path / "renamed-witness.txt"
    seal = (
        "{ test -f mover.txt && echo MOVER-RESTORED || echo MOVER-MISSING\n"
        "  test -e moved.txt && echo MOVED-STILL-PRESENT || echo MOVED-REMOVED\n"
        f"}} > {witness}\n"
        "grep -q fixed code.txt\n"
    )

    renamed = _seal_repo(tmp_path, "renamed")
    (renamed / "mover.txt").write_text("x" * 400 + "\n", encoding="utf-8")
    _git(renamed, "add", "-A")
    _git(renamed, "commit", "-q", "-m", "a file worth renaming")
    _git(renamed, "branch", "-f", "main", "HEAD")
    _git(renamed, "mv", "mover.txt", "moved.txt")
    (renamed / "code.txt").write_text("fixed\n", encoding="utf-8")
    (renamed / "tests" / "run.sh").write_text(seal, encoding="utf-8")
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
    assert "R100\tmover.txt\tmoved.txt" in status, (
        "the fixture no longer reproduces the input under test: git did not "
        f"report the rename as a rename. It printed {status!r}"
    )

    renamed_result, renamed_logs = _invert(renamed)
    kept_result, _ = _invert(kept)

    assert witness.exists(), (
        "a fix containing a `git mv` never got its seal inverted or judged: "
        f"{renamed_result.outcome!r} / {renamed_result.detail!r}. git named "
        "both the old and the new path, so this change CAN be inverted "
        "exactly; refusing to is a hard block charged to every renaming fix"
    )
    assert witness.read_text(encoding="utf-8") == (
        "MOVER-RESTORED\nMOVED-REMOVED\n"), (
        "the suite ran over a tree the rename was not correctly inverted in "
        f"({witness.read_text(encoding='utf-8')!r}); inverting a rename means "
        "the old name is back AND the new name is gone, and a verdict over "
        "anything else is a verdict about a different tree"
    )
    assert renamed_result.outcome == "passed", (
        "the renamed branch's seal is a real one — its suite greps `code.txt` "
        "for the fix, which the inversion reverts — so the only honest "
        f"verdict is `passed`; got {renamed_result.outcome!r} / "
        f"{renamed_result.detail!r}"
    )
    assert renamed_logs, (
        "the gate reported a verdict without running anything: an outcome of "
        f"{renamed_result.outcome!r} with an empty log"
    )
    assert (renamed / "moved.txt").exists() and not (
        renamed / "mover.txt").exists(), (
        "the rename was inverted and never put back: the branch's own tree "
        "is now the base's, and every later gate reads it"
    )
    assert _git(renamed, "status", "--porcelain").strip() == "", (
        "the worktree was left dirty after a renaming fix was inverted"
    )
    assert kept_result.outcome == "passed", (
        "control: the same branch without the rename must be judged, or the "
        "row above would pass by everything blocking"
    )


def test_a_checkout_that_fails_partway_does_not_leave_the_tree_mongrel(
    tmp_path: Path,
) -> None:
    """RED — the inversion checkout can fail AFTER writing, and that branch
    never restores.

    The checkout-failure branch is the one place in `run_seal_inversion` that
    returns without calling `_restore`, and the comment above it says why:
    "git resolves every pathspec against the tree before writing any of them,
    so on this path the worktree is untouched and needs no restore." That is
    true of pathspec RESOLUTION — does this name exist in `<base>` — and it
    is the only failure mode the rename bug ever exercised. It is not true of
    WRITING. A pathspec that resolves perfectly can still fail to be written,
    and git has by then already written the ones before it.

    MEASURED, 2026-08-09, at `7569760`: a branch that fixes `code.txt` and
    `locked/helper.txt`, with `locked/` at mode 0555 — the same everyday shape
    the restore-failure row above is built on, a directory a test run or a
    docker mount left read-only. `git checkout main -- code.txt
    locked/helper.txt` writes `code.txt`, then fails on the second with
    "unable to unlink old ... Permission denied" and exits 255. The gate
    returns `error`, correctly blocking — and leaves `code.txt` reverted to
    BASE on disk and BOTH files reverted in the INDEX
    (`git status --porcelain` = `M  code.txt` / `MM locked/helper.txt`) while
    reporting only "could not revert to base for inversion", which reads as
    "nothing was touched". The module's own precondition is that the worktree
    is committed-clean; every later gate now reads a tree holding the fix
    half-reverted, and nothing told them.

    Producible because: the row first demonstrates the partial write on a
    throwaway repository of the same shape, by hand, before asking the gate
    anything — so if a future git ever does resolve-and-write atomically,
    this row says the input is no longer producible instead of passing.

    Red now: `code.txt` is left at the base content and the detail does not
    say the tree is suspect.
    Green when: the branch calls `_restore` like its `OSError` sibling and
    reports a failed restore as such. Measured in a clone: `_restore` puts
    `code.txt` back to `fixed` and returns False here (the locked directory
    defeats `reset --hard` too), so the honest answer is the tree-suspect
    error the restore branch below already emits. SEPARATE body change.
    Falsify: the unlocked control twin is judged in the same call, so a gate
    that blocked or dirtied everything reddens on it.
    """
    if os.geteuid() == 0:
        pytest.skip("root ignores directory permissions; the input is "
                    "unproducible here and a green row would be a lie")

    def _two_place_fix(name: str) -> Path:
        repo = _seal_repo(tmp_path, name)
        (repo / "locked").mkdir()
        (repo / "locked" / "helper.txt").write_text(
            "base helper\n", encoding="utf-8")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-q", "-m", "helper lives in its own directory")
        _git(repo, "branch", "-f", "main", "HEAD")
        (repo / "code.txt").write_text("fixed\n", encoding="utf-8")
        (repo / "locked" / "helper.txt").write_text(
            "fixed helper\n", encoding="utf-8")
        (repo / "tests" / "run.sh").write_text(
            "grep -q fixed code.txt\n", encoding="utf-8")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-q", "-m", "fix in two places")
        return repo

    preflight = _two_place_fix("preflight")
    locked = _two_place_fix("locked-dir")
    open_twin = _two_place_fix("open-dir")

    for repo in (preflight, locked):
        (repo / "locked").chmod(0o555)
    try:
        raw = subprocess.run(
            ["git", "checkout", "main", "--", "code.txt", "locked/helper.txt"],
            cwd=str(preflight), capture_output=True, text=True)
        assert raw.returncode != 0 and (
            preflight / "code.txt").read_text(encoding="utf-8") == "broken\n", (
            "the fixture no longer reproduces the input under test: git either "
            "did not fail on the locked path or did not write the earlier "
            f"pathspec first (rc={raw.returncode}, stderr={raw.stderr!r}, "
            f"code.txt={ (preflight / 'code.txt').read_text(encoding='utf-8')!r})"
        )

        locked_result, _ = _invert(locked)
        open_result, _ = _invert(open_twin)

        assert locked_result.outcome in _BLOCKING, (
            "an inversion checkout that failed returned "
            f"{locked_result.outcome!r}: {locked_result.detail!r}"
        )
        assert (locked / "code.txt").read_text(encoding="utf-8") == "fixed\n", (
            "the inversion wrote part of the tree, failed on the rest, and "
            "returned without restoring: the branch's fix is left REVERTED on "
            "disk. The module's precondition is a committed-clean worktree "
            "and every later gate reads this one"
        )
        assert "suspect" in locked_result.detail, (
            "the gate could not put the tree back — `git status --porcelain` "
            f"is {_git(locked, 'status', '--porcelain')!r} — and said only "
            f"{locked_result.detail!r}, which reads as 'nothing was touched'"
        )
        assert open_result.outcome == "passed", (
            "control: the same two-place fix with a writable directory must "
            "be inverted and judged, or the row above would pass by every "
            "multi-file fix blocking"
        )
        assert _git(open_twin, "status", "--porcelain").strip() == "", (
            "control: the writable twin's tree must come back clean"
        )
    finally:
        for repo in (preflight, locked):
            directory = repo / "locked"
            if directory.exists():
                directory.chmod(stat.S_IRWXU)


def test_a_git_failure_is_not_a_change_with_no_tests_in_it(
    tmp_path: Path,
) -> None:
    """RED — "we learned nothing" must not be reported as "we learned the
    change has no tests in it".

    THE ASYMMETRY THIS CLOSES, raised by the seal author and ruled on by P4
    (see RULINGS in the module docstring). `SealPathError` blocks, and its
    docstring justifies blocking by "an undecodable path means we learned
    that the change contains a file we cannot classify", contrasted with "a
    git failure means we learned nothing about the change" — which fails
    OPEN. Learned nothing is the WEAKER position. There is no reading in
    which knowing less warrants proceeding while knowing more warrants
    blocking.

    `partition_changed` returns `([], [])` when git times out, cannot be
    executed, or exits non-zero — a bad base ref, a corrupt repository, an
    index locked by a concurrent process — and `run_seal_inversion` turns
    that into `("skipped", "no test files changed — nothing claims to
    seal")`. That string is a positive claim about the change's contents,
    made when git never said what the contents were, and it is byte-identical
    to the result a genuinely code-only branch produces. A bad base ref is
    the worst case: it makes EVERY seal check in the run vacuous, silently.

    This row is the amendment to `test_seal_verify.py::
    test_partition_fails_open_on_bad_base`, which pinned the fail-open as
    intended and is amended in the same commit.

    Producible because: `base="no-such-ref"` over a real repository is the
    input, and `git diff --name-status no-such-ref...HEAD` really does exit
    non-zero. The control is the same repository at the same commit with a
    base that exists, so the row cannot pass by the gate refusing everything.

    Red now: `("skipped", "no test files changed — nothing claims to seal")`.
    Green when: a git failure reaches the orchestrator as a block, by any
    mechanism the body prefers — this row does not name an exception class,
    only that the gate must not answer a question git refused to inform it
    about. SEPARATE body change.
    Falsify: the good-base control is a real verdict in the same call.
    """
    repo = _seal_repo(tmp_path, "gitfail")
    (repo / "code.txt").write_text("fixed\n", encoding="utf-8")
    (repo / "tests" / "run.sh").write_text(
        "grep -q fixed code.txt\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "an ordinary fix plus its seal")

    probe = subprocess.run(
        ["git", "diff", "--name-status", "no-such-ref...HEAD"],
        cwd=str(repo), capture_output=True, text=True)
    assert probe.returncode != 0, (
        "the fixture no longer reproduces the input under test: git accepted "
        f"`no-such-ref` (rc={probe.returncode}, stdout={probe.stdout!r})"
    )

    logs: list[str] = []
    broken = sv.run_seal_inversion(
        worktree=repo, base="no-such-ref", test_command="sh tests/run.sh",
        timeout_seconds=60, log=logs.append)
    good, _ = _invert(repo)

    assert "nothing claims to seal" not in broken.detail, (
        "git could not say what the change contains and the gate reported "
        f"that the change contains no tests: {broken.detail!r}. The same "
        "sentence is what a real code-only branch gets, so the two are "
        "indistinguishable to the orchestrator and to the journal"
    )
    assert broken.outcome in _BLOCKING, (
        f"the gate returned {broken.outcome!r} without learning anything "
        "about the change; an undecodable path — strictly MORE information "
        "than this — is already a block"
    )
    assert good.outcome == "passed", (
        "control: the same repository with a base that exists must reach a "
        "real verdict, or the row above would pass by the gate blocking "
        "every change"
    )


# --------------------------------------------------------------------------- #
# 3. Totality: no outcome the gate can emit is unclassified.
# --------------------------------------------------------------------------- #


#: The only two things `run_seal_inversion` is allowed to mean by `skipped`.
#: Both are judgements ABOUT THE CHANGE, made from a partition git supplied:
#: the change carries no tests, or it carries nothing but tests. Written out
#: rather than counted, so a third reason must be read and agreed to by a
#: human before it can exist.
_APPLICABILITY_SKIPS: tuple[str, ...] = (
    "no test files changed — nothing claims to seal",
    "test-only change — no fix to invert",
)


def test_the_gate_stands_down_only_on_the_two_applicability_judgements() -> None:
    """`skipped` must never be reachable from a step that FAILED.

    This row is structural, and deliberately so: it is the seal on a branch
    that the P4 rulings made behaviourally unreachable, and dropping it would
    hand back the exact fail-open this file exists to close.

    MEASURED, 2026-08-09. Before ruling 2 the checkout-failure branch was
    reached by a plain `git mv`, so a behavioural row could reach it and
    `test_a_renamed_non_test_file_does_not_switch_the_gate_off` did. After
    ruling 2 a rename is inverted instead, and the only remaining way in is a
    checkout that fails — every one of which, measured, leaves the INDEX
    modified even when the worktree write never lands (git updates the index
    before the write can fail), so it exits through the tree-suspect return
    that ruling 3 requires and not through the plain one. Attempts to reach
    the plain return behaviourally, all failed: a single-file write failure
    (index left `MM`), a parent directory that is a file at HEAD (git removes
    it and succeeds, rc=0), a pathspec absent from base (git resolves every
    pathspec before writing any, which is now only produced by renames).
    So the flip that started all of this — that branch returning `skipped` —
    became invisible again: measured in a clone carrying both rulings' body
    changes, `error` -> `skipped, "nothing claims to seal"` there was noticed
    by NOTHING else in the 1827-row suite — this row is the only one that
    reddens on it.

    The invariant instead: `skipped` is the gate's only non-blocking outcome,
    so every place it is constructed is a place the gate can switch itself
    off, and all of them must be judgements about the change rather than
    reports of a step that did not work. Today there are exactly two, both
    guard clauses on a partition git supplied.

    Producible because: this reads `seal_verify`'s own source, the same seam
    the totality row below uses, and refuses a non-literal reason rather than
    skipping it.

    Green because correct.
    Falsify: return `skipped` from the checkout-failure branch, the inversion
    `OSError` branch, the restore-failure branch, or a `SealPathError` — each
    adds a reason that is not in this tuple. Changing either sentence's
    wording also reddens it, which is intended: the sentence is what the
    orchestrator journals as the reason the fix shipped unsealed.
    """
    reasons = _skipped_details_in_run_seal_inversion()

    assert reasons == _APPLICABILITY_SKIPS, (
        "`run_seal_inversion` stands down for reasons this seal has not "
        f"agreed to: {list(reasons)!r} vs {list(_APPLICABILITY_SKIPS)!r}. "
        "`skipped` is the gate's only non-blocking outcome; it may mean "
        "'this change does not claim to seal anything' and nothing else. A "
        "`skipped` reached from a step that failed is the gate reporting a "
        "judgement about the change that it never made — the whole subject "
        "of this file"
    )


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
