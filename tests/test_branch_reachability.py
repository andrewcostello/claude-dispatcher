"""D7 SEALS — the branch gate that asks what the BRANCH made dark.

**P2. Failing seals for** ``src/claude_dispatcher/branch_reachability.py``.
Every ruling this file pins was argued at P1 and is not relitigated here; what
is added is the measurement that each ruling is *load-bearing*, which is the
only thing a seal can add to a contract.

WHAT THIS FILE SEALS, AND THE ONE THING IT REFUSES TO SEAL VACUOUSLY
====================================================================
The unit's claim is a delta: *a branch is refused for the BREACHes it
introduced, never for the tree's standing set*. A seal for that claim is
worthless unless its fixture **has a standing set**. So every real-tree row in
this file runs over a tree that carries **twelve BREACHes with nothing edited
at all**, and the rows that assert CLEAN assert it against those twelve.

*Measured under* ``4df25e3`` (``feat/D7-gate-wiring``), this host (go1.24.4),
``check_tree`` over ``tests/fixtures/d6_g2_preserve`` staged the way
:func:`_staged` stages it::

    seals 30   findings 48   roots 34 (production 4)   unanalyzed 2
    ok 27   breach 12   report 0   accepted 0   abstain 9   (all DYNAMIC_EDGE)

and the twelve are enumerated in :data:`_STANDING_BREACH_SEALS`. That is the
scaffold's figure, re-measured here rather than inherited.

THE THREE TREE STATES EVERY REAL-TREE ROW IS BUILT FROM
-------------------------------------------------------
*Measured under* ``4df25e3``, on a git repository whose base commit is the
staged fixture:

============================== ===== ======== ====== =======
state                          seals findings breach abstain
============================== ===== ======== ====== =======
base, nothing edited              30       48     12       9
head, ONE COMPILING edit to
``cmd/iterate/main.go``           30       48     22       9
head, THE SAME EDIT written so
``cmd/iterate`` stops compiling   12       19      0       9
============================== ===== ======== ====== =======

The compiling edit introduces **ten** findings; *measured*, **every one of the
ten has its subject in ``cmd/iterate/preserve.go`` and its seal in
``cmd/iterate/preserve_seal_test.go``**, two files the diff does not touch.
The non-compiling edit introduces **zero** — a branch buying CLEAN by breaking
the build — and ``unanalyzed_paths`` is **2 in both halves** and sees nothing.
:func:`test_a_branch_cannot_buy_clean_by_breaking_the_build` and
:func:`test_sweep_is_vacuous_names_the_fields_that_moved_not_the_one_that_did_not`
are those two lines.

THE HAZARD THIS FILE WAS WRITTEN AGAINST
========================================
Four vacuity shapes are measured on this codebase and one of them is live here:
**a mutation invisible because two implementations return the same value.** The
scaffold implemented the three verdict tables *because* a stub that raises for
everything satisfies "raises on an unmapped member" vacuously. The same trap is
one line away in every row below, and the discipline that answers it is applied
per row rather than declared once:

  * every row that asserts an outcome **carries the opposite outcome in the
    same call**, so an implementation that answers one thing for everything
    fails the row rather than half of it;
  * every row states the mutation that reddens it as **Measured under:** (run
    against the reference implementation in a throwaway clone) or **Predicted
    (unmeasured) under:**;
  * no row transcribes a fact that is true only because a table is empty
    today. :func:`test_the_cheap_exit_asks_the_one_extension_table` derives its
    expectation from :func:`analyzer_for_path` rather than writing out
    ``".py" not in``, because "Python is not analyzable" is a fact about
    ``ANALYZERS`` having one row and would pin a transient unimplementedness.

WHICH ROWS A BODY CAN CLOSE ALONE, AND WHICH NEED THE P4 WIRING
===============================================================
**Every row in this file is closable by a body working only in
``src/claude_dispatcher/branch_reachability.py``.** Not one row calls
:func:`~claude_dispatcher.role_protocol.check_branch`, reads
:attr:`~claude_dispatcher.role_protocol.RoleDiffResult.reachability`, or
otherwise depends on the wiring escalation — deliberately, because that wiring
touches ``FLOOR_GLOBS`` and ``tests/test_floor_closure.py`` and is a P4
amendment, and a seal a body cannot turn green is a seal that blocks the body
on somebody else's commit.

The consequence is stated so it is a decision and not an oversight: **this file
does not seal that the gate is REACHED.** That is the recorded protocol gap —
*a seal proves a function behaves, never that it runs* — and it is left open on
purpose, to be closed by the wiring commit's own row in
``tests/test_role_protocol_diff.py`` alongside the ``_DELEGATION_TARGETS``
entry. It is named in this file's report as the one obligation P2 could not
discharge.

DISPUTES
========
Four, all measured, all filed rather than resolved here. See the DISPUTES
section at the foot of this file.

HOW THE ROWS ARE RUN
====================
Repositories are built once per session and the gate's answer is memoised per
distinct call (:func:`_gate`), because two rows asking the identical question
must not be able to get two answers, and because each answer costs two
``check_tree`` sweeps. A memoised call is re-raised, never swallowed: while
:func:`check_branch_reachability` is a stub, every row that reaches it fails
with ``NotImplementedError`` **in the row's own body**, which is a FAILED line
and not a collection error.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import fields as dataclass_fields
from pathlib import Path
from typing import Any

import pytest

from claude_dispatcher import branch_reachability as br
from claude_dispatcher import call_site_reachability as csr
from claude_dispatcher import go_reachability as gor
from claude_dispatcher import yaml_io
from claude_dispatcher.branch_reachability import (
    BranchReachability,
    BranchReachabilityError,
    DECLARATION_PATH,
    IntroducedFinding,
    ReachabilityObligation,
    ReachabilitySweepStatus,
    analyzable_paths,
    check_branch_reachability,
    declarations_at,
    dispositions_by_key,
    introduced_findings,
    materialise_base_tree,
    obligation_for_role,
    sweep_is_vacuous,
    verdict_for_abstention,
    verdict_for_disposition,
    verdict_for_status,
    verdict_of,
    worst_verdict,
)
from claude_dispatcher.call_site_contract import RootKind
from claude_dispatcher.call_site_reachability import (
    Disposition,
    StagedDeclaration,
    UndecidedReason,
    analyzer_for_path,
    check_tree,
)
from claude_dispatcher.role_protocol import DiffVerdict, Role, check_branch

_TESTS_DIR = Path(__file__).resolve().parent
_ACCEPTANCE_FIXTURE = _TESTS_DIR / "fixtures" / "d6_g2_preserve"
_IMPORT_SCOPE_FIXTURE = _TESTS_DIR / "fixtures" / "d6_import_scope"

_RECORDED_GO_MOD = "go.mod.recorded"
_LIVE_GO_MOD = "go.mod"

#: The ONE production call site of ``ApplyRoundRecord`` in the acceptance tree,
#: verbatim. Asserted present by :func:`_compiling_edit` rather than assumed, so
#: a fixture edit reddens a row instead of silently applying no edit at all —
#: which would make every row that uses it a comparison of a tree with itself.
_CALL_SITE_LINE = "\tdata, err := ApplyRoundRecord(raw, edits)\n"

#: The replacement call, and the local pass-through it calls. The package still
#: COMPILES: that is the whole point, because a scoped gate's defence is that
#: "the diff touched nothing relevant" and this edit touches exactly one file
#: whose name appears in none of the ten findings it introduces.
_LOCAL_CALL_LINE = "\tdata, err := localApply(raw, edits)\n"
_COMPILING_TAIL = """

// localApply replaces the ApplyRoundRecord call site with a pass-through. The
// package still compiles; ApplyRoundRecord is now called by nothing outside
// its own seals, which is the B1 defect introduced by an edit in a third file.
func localApply(raw []byte, edits []Edit) ([]byte, error) {
\t_ = edits
\treturn raw, nil
}
"""

#: The same edit written so ``cmd/iterate`` no longer compiles: ``stray`` is
#: declared and never used, which is a Go compile ERROR and not a warning.
#: Delta's own evasion, in four lines.
_BROKEN_TAIL = """

// localApply does not compile: `stray` is declared and never used.
func localApply(raw []byte, edits []Edit) ([]byte, error) {
\tvar stray []byte
\t_ = edits
\treturn raw, nil
}
"""

#: **The standing BREACH set of the acceptance tree, with NOTHING edited.**
#: Twelve, and they are the reason this fixture can tell a delta from a
#: whole-tree sweep at all. Written out as ``(seal test_id suffix, subject
#: name)`` pairs rather than as full keys, because the full key is qualified by
#: the sweep's tree root — see DISPUTE D2 — and a row that wrote out the
#: qualified spelling would pass or fail on the implementation's choice of
#: sweep scope rather than on the delta.
#:
#: *Measured under* ``4df25e3`` by :func:`test_the_acceptance_tree_carries_a_standing_breach_set`,
#: which derives them rather than reading this constant, and compares.
_STANDING_BREACH_SEALS: frozenset[tuple[str, str]] = frozenset(
    {
        ("TestSeal_G2_ApplyRoundRecord_DoesNotTouchTheRoundsItDidNotAppend", "(Licence).Allows"),
        ("TestSeal_G2_ApplyRoundRecord_DoesNotTouchTheRoundsItDidNotAppend", "LicensedPaths"),
        ("TestSeal_G2_ApplyRoundRecord_RefusesASecondAppendInOneList", "(Licence).Allows"),
        ("TestSeal_G2_ApplyRoundRecord_RefusesASecondAppendInOneList", "LicensedPaths"),
        ("TestSeal_G2_Licence_GatesIsLicensedForGatesAndForbiddenForIterate", "(JSONPath).String"),
        ("TestSeal_G2_Licence_GatesIsLicensedForGatesAndForbiddenForIterate", "(Licence).Allows"),
        ("TestSeal_G2_Licence_GatesIsLicensedForGatesAndForbiddenForIterate", "LicensedPaths"),
        ("TestSeal_G2_Licence_GatesIsLicensedForGatesAndForbiddenForIterate", "VerifyPreservation"),
        (
            "TestSeal_G2_VerifyPreservation_CatchesEveryArrayMalformationFromTheLicenceAlone",
            "VerifyPreservation",
        ),
        (
            "TestSeal_G2_VerifyPreservation_DerivesTheLicenceFromTheEditListNotTheOutput",
            "(JSONPath).String",
        ),
        (
            "TestSeal_G2_VerifyPreservation_DerivesTheLicenceFromTheEditListNotTheOutput",
            "VerifyPreservation",
        ),
        (
            "TestSeal_G2_VerifyPreservation_RefusesWhatItCannotCheckOnItsOwnTerms",
            "VerifyPreservation",
        ),
    }
)

#: The ten findings the compiling edit INTRODUCES, in the same tree-root-free
#: spelling. *Measured under* ``4df25e3``. Every subject is in
#: ``cmd/iterate/preserve.go`` and every seal in
#: ``cmd/iterate/preserve_seal_test.go``; the diff touches
#: ``cmd/iterate/main.go`` and nothing else, which is what a scoped gate cannot
#: see and is why scoped was refused on soundness.
_INTRODUCED_BY_THE_COMPILING_EDIT: frozenset[tuple[str, str]] = frozenset(
    {
        ("TestSeal_G2_ApplyRoundRecord_DoesNotTouchTheRoundsItDidNotAppend", "ApplyRoundRecord"),
        ("TestSeal_G2_ApplyRoundRecord_PreservesEveryPathOutsideTheLicensedEdits", "ApplyRoundRecord"),
        ("TestSeal_G2_ApplyRoundRecord_PreservesNumberLiteralsInDeclaredFields", "ApplyRoundRecord"),
        ("TestSeal_G2_ApplyRoundRecord_PreservesTheGateRecordsItDidNotWrite", "ApplyRoundRecord"),
        ("TestSeal_G2_ApplyRoundRecord_PreservesUnknownKeysTopLevelAndNested", "ApplyRoundRecord"),
        ("TestSeal_G2_ApplyRoundRecord_RefusesASecondAppendInOneList", "ApplyRoundRecord"),
        ("TestSeal_G2_ApplyRoundRecord_RefusesAStaleAtIndexAndReturnsNoBytes", "ApplyRoundRecord"),
        ("TestSeal_G2_ApplyRoundRecord_SetRoundZeroWritesTheLiteralAndDoesNotDelete", "ApplyRoundRecord"),
        ("TestSeal_G2_EmptyVerdictIsAppliedAndEmptyStatusIsRefused", "(Edit).Validate"),
        ("TestSeal_G2_EmptyVerdictIsAppliedAndEmptyStatusIsRefused", "ApplyRoundRecord"),
    }
)

#: The one file the compiling edit touches, and the two files every finding it
#: introduces lives in. The gap between them IS the soundness argument against
#: a scoped reading, and :func:`test_the_defect_is_caught_though_the_diff_touches_neither_subject_nor_seal`
#: asserts the gap rather than citing it.
_EDITED_PATH = "cmd/iterate/main.go"
_INTRODUCED_SUBJECT_PATH = "cmd/iterate/preserve.go"
_INTRODUCED_SEAL_PATH = "cmd/iterate/preserve_seal_test.go"


# --------------------------------------------------------------------------- #
# Helpers. None of these implements anything under seal. Where a helper
# computes an expectation it computes it from `check_tree` — the SHIPPED
# mechanism, which this unit is contracted never to weaken — and never from a
# function in `branch_reachability`, so no row can pass because the unit under
# seal and its expectation drifted together.
# --------------------------------------------------------------------------- #


class _NotAMember:
    """A stand-in for the enum member nobody has added yet.

    The dispatches under seal must raise for anything that is not a member of
    the enum they dispatch over. A tenth :class:`ReachabilitySweepStatus` cannot
    be constructed in a row — the enum is closed — so the thing the raise
    actually has to hold against is an object arriving from a caller that did
    not validate, which is what this is. It is deliberately NOT a string: the
    string case is a separate and sharper claim, and it is DEFECT D5.
    """

    def __repr__(self) -> str:  # pragma: no cover - only in a failure message
        return "<not a member of anything>"


def _staged(fixture: Path, dest: Path) -> Path:
    """The vendored fixture, copied to ``dest`` with its ``go.mod`` live.

    Copied and never analysed in place, for the reason
    ``tests/test_go_reachability.py`` records: the mechanism is contracted never
    to write into the tree it reads, and a run that mutated the fixture would
    make the next row's input a function of the previous row's body.
    """
    shutil.copytree(fixture, dest)
    (dest / "PROVENANCE.md").unlink()
    for recorded in dest.rglob(_RECORDED_GO_MOD):
        recorded.rename(recorded.with_name(_LIVE_GO_MOD))
    return dest


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def _init_repo(tree: Path) -> str:
    """Make ``tree`` a git repository with one commit. Returns the base sha."""
    _git(tree, "init", "-q", "-b", "main")
    _git(tree, "config", "user.email", "seals@example.invalid")
    _git(tree, "config", "user.name", "D7 seals")
    _git(tree, "add", "-A")
    _git(tree, "commit", "-q", "-m", "base")
    return _git(tree, "rev-parse", "HEAD").strip()


def _commit_all(repo: Path, message: str) -> str:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", message)
    return _git(repo, "rev-parse", "HEAD").strip()


def _compiling_edit(repo: Path) -> None:
    """Replace the ONE production call site of ``ApplyRoundRecord``, compilably.

    Asserts the line is present rather than trusting ``str.replace`` to be a
    no-op, because a silent no-op would turn every row built on this edit into
    a comparison of a tree with itself — which is the measured vacuity shape
    "a fixture that stated only the world the fix wanted".
    """
    main_go = repo / "cmd" / "iterate" / "main.go"
    source = main_go.read_text()
    assert _CALL_SITE_LINE in source, (
        f"{main_go} no longer contains the ApplyRoundRecord call site this "
        "file's every delta row is built from; the fixture moved and the rows "
        "would silently compare a tree with itself"
    )
    main_go.write_text(source.replace(_CALL_SITE_LINE, _LOCAL_CALL_LINE) + _COMPILING_TAIL)


def _non_compiling_edit(repo: Path) -> None:
    """The same edit, written so ``cmd/iterate`` stops compiling."""
    main_go = repo / "cmd" / "iterate" / "main.go"
    source = main_go.read_text()
    assert _CALL_SITE_LINE in source
    main_go.write_text(source.replace(_CALL_SITE_LINE, _LOCAL_CALL_LINE) + _BROKEN_TAIL)


def _touch_comment(path: Path, marker: str) -> None:
    """Append a Go comment line. Compiles, changes no edge, changes no finding."""
    path.write_text(path.read_text() + f"\n// {marker}\n")


def _short(key: str) -> str:
    """A key with its package qualifier stripped, and NOTHING else stripped.

    The qualifier is the Go module path plus the package's directory RELATIVE TO
    THE SWEPT TREE ROOT, so it is a function of the implementation's choice of
    sweep scope and not of the branch. Every expectation in this file is written
    in this spelling so that the two consistent scopings (DISPUTE D2) both
    satisfy it and the inconsistent one does not.

    Strips the path segments and then the ONE package component, so a method
    key keeps its receiver: ``…/iterate/cmd/iterate.(Licence).Allows`` and
    ``…/iterate.(Licence).Allows`` both become ``(Licence).Allows``. Splitting
    on the last dot instead would collapse ``(Licence).Allows`` and
    ``(JSONPath).Allows`` onto one name, and this fixture exists because keys
    COLLIDE unless they are qualified.
    """
    tail = key.rsplit("/", 1)[-1]
    return tail.split(".", 1)[1] if "." in tail else tail


def _pairs(findings: Any) -> frozenset[tuple[str, str]]:
    """``(seal test_id last segment, subject symbol)`` over introduced findings."""
    return frozenset(
        (_short(f.test_id), _short(f.subject_key)) for f in findings
    )


def _breach_pairs(tree: Path) -> frozenset[tuple[str, str]]:
    """The BREACH set of ``tree``, derived by the SHIPPED mechanism.

    Reads :func:`check_tree` and :func:`~claude_dispatcher.
    call_site_reachability.adjudicate` — the mechanism this unit is contracted
    never to weaken — and never anything in ``branch_reachability``. That is
    what makes it usable as an expectation.
    """
    report = check_tree(tree)
    return frozenset(
        (_short(f.seal.test_id), _short(f.subject.key))
        for f in report.findings
        if csr.adjudicate(f, None) is Disposition.BREACH
    )


# --------------------------------------------------------------------------- #
# The scenario repositories, built ONCE per session, and the memoised gate.
# --------------------------------------------------------------------------- #


class _Scenarios:
    """The repositories every real-tree row is judged over.

    Built once because building them is pure ``git`` and ``shutil`` and cannot
    be affected by anything under seal, and because two rows asking the gate an
    identical question must not be able to receive two answers.

    ``acceptance``
        The staged acceptance fixture at ``base``; ``head_compiling`` and
        ``head_broken`` are the two edits, each on its own branch, and
        ``head_noop`` is a comment-only commit that changes no edge at all.
        Every branch is a real commit so that ``base_ref`` and ``branch_ref``
        are refs a body can read out of an object store.
    ``import_scope``
        The one-module fixture, whose ``cmd/app`` package holds the entrypoint
        and whose ``pkg/b`` holds the dark subject. It exists here for one row
        only: DISPUTE D3, the swept scope must not cut the module.
    """

    def __init__(self, root: Path) -> None:
        self.acceptance = _staged(_ACCEPTANCE_FIXTURE, root / "acceptance")
        self.base = _init_repo(self.acceptance)

        _git(self.acceptance, "checkout", "-q", "-b", "noop", self.base)
        _touch_comment(self.acceptance / "cmd" / "iterate" / "preserve.go", "noop")
        self.head_noop = _commit_all(self.acceptance, "noop")

        _git(self.acceptance, "checkout", "-q", "-b", "gatesonly", self.base)
        _touch_comment(self.acceptance / "cmd" / "gates" / "main.go", "gates only")
        self.head_gates_only = _commit_all(self.acceptance, "gates only")

        _git(self.acceptance, "checkout", "-q", "-b", "broken", self.base)
        _non_compiling_edit(self.acceptance)
        self.head_broken = _commit_all(self.acceptance, "broken")

        # LAST, and left checked out: step 4 of the contract requires the head
        # tree to BE the checkout, and the compiling edit is what most rows use.
        _git(self.acceptance, "checkout", "-q", "-b", "compiling", self.base)
        _compiling_edit(self.acceptance)
        self.head_compiling = _commit_all(self.acceptance, "compiling")

        self.import_scope = _staged(_IMPORT_SCOPE_FIXTURE, root / "importscope")
        self.import_base = _init_repo(self.import_scope)
        _touch_comment(self.import_scope / "cmd" / "app" / "main.go", "app only")
        self.import_head = _commit_all(self.import_scope, "app only")


@pytest.fixture(scope="session")
def scenarios(tmp_path_factory: pytest.TempPathFactory) -> _Scenarios:
    return _Scenarios(tmp_path_factory.mktemp("d7"))


_GATE_MEMO: dict[tuple, tuple[Any, BaseException | None]] = {}


def _gate(
    repo: Path,
    base_ref: str,
    branch_ref: str,
    role: Role,
    changed_paths: tuple[str, ...],
    *,
    already_violation: bool = False,
) -> BranchReachability:
    """:func:`check_branch_reachability`, memoised per distinct call.

    The memo is not a convenience: each answer costs two ``check_tree`` sweeps
    (*measured under* ``4df25e3``: 1.3 s each over the acceptance tree), and two
    rows asking the identical question must not be able to get two answers.

    **A cached exception is RE-RAISED, never swallowed.** While
    :func:`check_branch_reachability` is a stub, every row that reaches this
    helper fails with ``NotImplementedError`` inside the ROW's body, which is a
    FAILED line. A fixture that swallowed it would produce a collection or setup
    ERROR instead, and this module's own instruction is that a collection error
    is not a FAILED line.
    """
    # The CHECKOUT is an input — the contract's step 4 reads it — so it is in
    # the key. Without it the row that checks the repository out at base and
    # then at head would get one answer twice, and the memo would be answering
    # a question nobody asked.
    key = (
        str(repo),
        _git(repo, "rev-parse", "HEAD").strip(),
        base_ref,
        branch_ref,
        role,
        changed_paths,
        already_violation,
    )
    if key not in _GATE_MEMO:
        try:
            _GATE_MEMO[key] = (
                check_branch_reachability(
                    repo,
                    base_ref,
                    branch_ref,
                    role,
                    changed_paths,
                    already_violation=already_violation,
                ),
                None,
            )
        except BaseException as exc:  # noqa: BLE001 - re-raised below, every time
            _GATE_MEMO[key] = (None, exc)
    result, error = _GATE_MEMO[key]
    if error is not None:
        raise error
    return result


def _checkout(repo: Path, ref: str) -> None:
    _git(repo, "checkout", "-q", ref)


# --------------------------------------------------------------------------- #
# 0. The fixture itself. Nothing below is worth anything if these two are red.
# --------------------------------------------------------------------------- #


def test_the_acceptance_tree_carries_a_standing_breach_set(scenarios: _Scenarios) -> None:
    """**THE PREMISE OF EVERY DELTA ROW: the tree is dirty before the branch.**

    A delta gate cannot be told apart from a whole-tree gate by a fixture that
    is clean at base — both answer "nothing introduced" and both answer CLEAN,
    which is the measured vacuity shape *a mutation invisible because two
    implementations return the same value*. This row measures the standing set
    so that every CLEAN below is a CLEAN **over twelve standing BREACHes** and
    not over an empty tree.

    Derived by the SHIPPED :func:`check_tree`, compared against
    :data:`_STANDING_BREACH_SEALS`, which is transcribed. Both directions are
    asserted: a fixture that grew a BREACH and a constant that went stale both
    redden this row rather than quietly widening or narrowing every other one.

    THE CONTROL, in the same call: the head tree with the compiling edit, whose
    BREACH set must be a strict SUPERSET of exactly ten more. A row that only
    measured the base could pass against a mechanism that reported the same set
    for every tree.

    Measured under: ``4df25e3``, this host, go1.24.4 — base 12 BREACH of 48
    findings over 30 seals; head 22 of 48 over 30.
    Predicted (unmeasured) under: deleting ``_COMPILING_TAIL``'s replacement (so the edit is a
    no-op) — the superset assertion fails, 12 != 22.
    """
    _checkout(scenarios.acceptance, scenarios.base)
    standing = _breach_pairs(scenarios.acceptance)
    assert standing == _STANDING_BREACH_SEALS, (
        "the acceptance fixture's standing BREACH set moved; every CLEAN row "
        "in this file is a claim about THESE twelve and cannot be read without "
        f"them. missing={sorted(_STANDING_BREACH_SEALS - standing)} "
        f"unexpected={sorted(standing - _STANDING_BREACH_SEALS)}"
    )

    _checkout(scenarios.acceptance, scenarios.head_compiling)
    after = _breach_pairs(scenarios.acceptance)
    _checkout(scenarios.acceptance, scenarios.head_compiling)

    assert standing < after, "the compiling edit must ADD breaches, not replace them"
    assert after - standing == _INTRODUCED_BY_THE_COMPILING_EDIT
    assert len(after - standing) == 10

    # The gap the soundness argument against a scoped gate is made of, measured
    # rather than cited: the diff touches ONE file, and the ten findings it
    # introduces live in two others.
    report = check_tree(scenarios.acceptance)
    grown = {
        (f.subject.path, f.seal.symbol.path)
        for f in report.findings
        if csr.adjudicate(f, None) is Disposition.BREACH
        and (_short(f.seal.test_id), _short(f.subject.key)) in (after - standing)
    }
    assert {Path(subject).name for subject, _ in grown} == {
        Path(_INTRODUCED_SUBJECT_PATH).name
    }
    assert {Path(seal).name for _, seal in grown} == {
        Path(_INTRODUCED_SEAL_PATH).name
    }
    assert Path(_EDITED_PATH).name not in {Path(s).name for pair in grown for s in pair}


def test_the_broken_edit_is_what_it_claims_and_buys_a_delta_of_nothing(
    scenarios: _Scenarios,
) -> None:
    """**THE PREMISE OF THE VACUITY ROW: the evasion is producible here.**

    ``sweep_is_vacuous`` is only worth sealing against a fixture in which the
    vacuity can actually be produced. It can: the same one-file edit written so
    ``cmd/iterate`` no longer compiles takes the tree from 30 seals to 12 and
    from 12 BREACHes to 0, and the delta over that pair is EMPTY. This row
    measures that emptiness with the shipped mechanism and
    :func:`introduced_findings`, so that
    :func:`test_a_branch_cannot_buy_clean_by_breaking_the_build` is sealing a
    refusal of something real rather than a refusal of nothing.

    THE CONTROL, in the same call: the compiling edit over the same base, whose
    delta is ten. Without it, "the broken delta is empty" is satisfied by a
    delta that is empty for every input.

    Measured under: ``4df25e3`` — base 30 seals / 48 findings / 12 breach;
    broken head 12 / 19 / 0, introduced 0; compiling head 30 / 48 / 22,
    introduced 10. ``unanalyzed_paths`` is 2 in BOTH halves of the broken pair.
    """
    _checkout(scenarios.acceptance, scenarios.base)
    base = check_tree(scenarios.acceptance)

    _checkout(scenarios.acceptance, scenarios.head_broken)
    broken = check_tree(scenarios.acceptance)

    _checkout(scenarios.acceptance, scenarios.head_compiling)
    compiling = check_tree(scenarios.acceptance)

    assert base.seals_examined == 30 and len(base.findings) == 48
    assert broken.seals_examined == 12 and len(broken.findings) == 19
    assert broken.dispositions[Disposition.BREACH] == 0

    assert introduced_findings(base, broken) == (), (
        "the broken-build evasion must produce an EMPTY delta here, or the "
        "vacuity guard below is guarding against nothing"
    )
    assert len(introduced_findings(base, compiling)) == 10

    # The field that must NOT be the guard, measured rather than asserted in
    # prose: it is identical across the pair that the guard has to refuse.
    assert len(broken.unanalyzed_paths) == len(base.unanalyzed_paths)
    assert broken.unanalyzed_paths, (
        "a field that is empty in both halves would be an uninteresting way "
        "for it to be equal; it must be populated and still not move"
    )


# --------------------------------------------------------------------------- #
# 1. Whose gate it is. Target 3.
# --------------------------------------------------------------------------- #


def test_every_role_is_mapped_and_an_unmapped_one_raises() -> None:
    """The obligation table is total over :class:`Role` and refuses a sixth.

    IMPLEMENTED at P1 deliberately, so this row is not sealing a stub of itself:
    a stub that raised for everything would satisfy "raises on an unmapped
    member" vacuously, which is why the table exists.

    THE CONTROL against exactly that: the row asserts the five ANSWERS as well
    as the raise, and asserts that the three NOT_RUN roles and the one BLOCKING
    role differ — a dispatch that returned NOT_RUN for everything passes
    "every Role is mapped" and fails here.

    Measured under: ``_ROLE_OBLIGATIONS = {}`` — five failures at the lookup.
    Measured under: mapping ``Role.ADJUDICATE`` to ``NOT_RUN`` — fails on the
    advisory row.
    Measured under: replacing the raise with ``return NOT_RUN`` — fails on the
    unmapped member.
    """
    assert obligation_for_role(Role.BODIES) is ReachabilityObligation.BLOCKING
    assert obligation_for_role(Role.ADJUDICATE) is ReachabilityObligation.ADVISORY
    for role in (Role.SCAFFOLD, Role.SEALS, Role.LEGACY):
        assert obligation_for_role(role) is ReachabilityObligation.NOT_RUN

    assert {obligation_for_role(r) for r in Role} == set(ReachabilityObligation), (
        "all three obligations must be used; a table that answered one thing "
        "for every role would satisfy totality and say nothing"
    )
    assert sum(
        1 for r in Role if obligation_for_role(r) is ReachabilityObligation.BLOCKING
    ) == 1

    with pytest.raises(BranchReachabilityError):
        obligation_for_role("bodies")  # type: ignore[arg-type]


def test_the_five_roles_are_judged_over_one_introduced_set(
    scenarios: _Scenarios,
) -> None:
    """**Target 3.** One branch, one introduced set, five roles, five answers.

    The same repository, the same two refs, the same ten introduced findings —
    only ``role`` differs. Bodies is refused; the other four are not. That is
    the ruling *a role that cannot FIX a BREACH must not be BLOCKED by one*,
    driven rather than restated.

    **ADVISORY MUST REPORT WHILE NOT BLOCKING, and a row that only checked the
    verdict cannot tell ADVISORY from NOT_RUN** — both are CLEAN. So the row
    asserts what is on the RECORD: ADJUDICATE's status is ``CHECKED`` and its
    ``introduced`` is the same ten BODIES is refused for, while the three
    NOT_RUN roles carry ``NOT_THIS_ROLES_GATE`` and an EMPTY introduced set and
    never ran a sweep at all (``head_seals_examined == 0``).

    Needs only ``branch_reachability``; no wiring.

    Measured under: ``verdict_of`` returning ``CLEAN`` for BLOCKING — bodies row
    fails.
    Measured under: mapping ADJUDICATE to ``NOT_RUN`` — the advisory status and
    introduced-set assertions fail (the verdict assertion does NOT, which is
    the point of asserting the record).
    Predicted (unmeasured) under: returning ``NOT_THIS_ROLES_GATE`` with a populated
    ``introduced`` — the "did not run a sweep" assertion fails.
    """
    repo, base, head = scenarios.acceptance, scenarios.base, scenarios.head_compiling
    _checkout(repo, head)
    changed = (_EDITED_PATH,)

    bodies = _gate(repo, base, head, Role.BODIES, changed)
    assert bodies.obligation is ReachabilityObligation.BLOCKING
    assert bodies.status is ReachabilitySweepStatus.CHECKED
    assert _pairs(bodies.introduced) == _INTRODUCED_BY_THE_COMPILING_EDIT
    assert verdict_of(bodies) is DiffVerdict.VIOLATION

    advisory = _gate(repo, base, head, Role.ADJUDICATE, changed)
    assert advisory.obligation is ReachabilityObligation.ADVISORY
    assert advisory.status is ReachabilitySweepStatus.CHECKED
    assert _pairs(advisory.introduced) == _INTRODUCED_BY_THE_COMPILING_EDIT, (
        "ADJUDICATE rules on the appeal, so it must be SHOWN the debt it is "
        "asked to ratify; an advisory arm that reports nothing is a NOT_RUN "
        "arm wearing a different name"
    )
    assert advisory.head_seals_examined > 0
    assert verdict_of(advisory) is DiffVerdict.CLEAN

    for role in (Role.SCAFFOLD, Role.SEALS, Role.LEGACY):
        quiet = _gate(repo, base, head, role, changed)
        assert quiet.obligation is ReachabilityObligation.NOT_RUN
        assert quiet.status is ReachabilitySweepStatus.NOT_THIS_ROLES_GATE
        assert quiet.introduced == ()
        assert quiet.head_seals_examined == 0 and quiet.base_seals_examined == 0, (
            f"{role} pays 15 s for a report that is noisy by construction on "
            "exactly its branches; NOT_RUN means the sweep did not run"
        )
        assert verdict_of(quiet) is DiffVerdict.CLEAN


# --------------------------------------------------------------------------- #
# 2. The delta is real. Target 1.
# --------------------------------------------------------------------------- #


def test_the_twelve_standing_breaches_are_not_this_branchs(
    scenarios: _Scenarios,
) -> None:
    """**Target 1, the whole of it.** A branch that introduced nothing is CLEAN
    over a tree that carries twelve BREACHes.

    This is the row a whole-tree arm cannot pass and the reason the delta ruling
    exists: on this fixture a whole-tree gate is red on commit one, for every
    branch, forever, with nobody having done anything wrong.

    The branch's diff is a COMMENT in ``cmd/iterate/preserve.go`` — the very
    file the twelve BREACHes' subjects live in — so the row is not passing
    because the branch touched something irrelevant.

    **The non-vacuity is on the record, not in the prose:** the row asserts
    ``head_dispositions[BREACH] == 12`` in the same breath as ``introduced ==
    ()``. A gate that saw nothing at all would satisfy the second and fail the
    first, and that is the failure this assertion exists for.

    THE CONTROL, in the same call: the compiling head over the same base, which
    IS refused. Without it, "introduced is empty" is satisfied by a gate that
    reports nothing for every branch.

    Needs only ``branch_reachability``; no wiring.

    Measured under: reporting the head report's whole BREACH set instead of the
    delta — this row fails with 12 introduced.
    Predicted (unmeasured) under: returning ``introduced=()`` unconditionally —
    the control fails.
    """
    repo, base = scenarios.acceptance, scenarios.base
    _checkout(repo, scenarios.head_noop)
    quiet = _gate(
        repo, base, scenarios.head_noop, Role.BODIES, ("cmd/iterate/preserve.go",)
    )
    assert quiet.status is ReachabilitySweepStatus.CHECKED
    assert quiet.introduced == ()
    assert verdict_of(quiet) is DiffVerdict.CLEAN
    assert quiet.head_dispositions is not None
    assert quiet.head_dispositions[Disposition.BREACH] == 12, (
        "the gate must SEE the twelve and decline to report them; a gate that "
        "saw none of them would pass the assertion above and mean nothing"
    )
    assert quiet.base_dispositions is not None
    assert quiet.base_dispositions[Disposition.BREACH] == 12

    _checkout(repo, scenarios.head_compiling)
    loud = _gate(
        repo, base, scenarios.head_compiling, Role.BODIES, (_EDITED_PATH,)
    )
    assert len(loud.introduced) == 10
    assert verdict_of(loud) is DiffVerdict.VIOLATION


def test_the_defect_is_caught_though_the_diff_touches_neither_subject_nor_seal(
    scenarios: _Scenarios,
) -> None:
    """**The canonical defect, and the measurement that refused a scoped gate.**

    One compiling edit to ``cmd/iterate/main.go`` introduces ten BREACHes whose
    subjects are all in ``cmd/iterate/preserve.go`` and whose seals are all in
    ``cmd/iterate/preserve_seal_test.go``. The diff touches neither file. That
    is ``ResolveConfigDual`` exactly: the last call site is by definition
    somewhere else.

    **THE CONTROL IS THE SCOPED READING ITSELF, computed in this row from the
    gate's own answer**: filter the ten by "the diff touched the subject's file
    or the seal's file" and the filter keeps ZERO. A row that only asserted
    "ten introduced" would be satisfied by a scoped gate that had ten of its own
    from somewhere; this one shows the ten are exactly the ten a scoped gate
    reports none of.

    Needs only ``branch_reachability``; no wiring.

    Measured under: scoping ``introduced_findings`` to findings whose subject
    path is in ``changed_paths`` — this row fails with 0 introduced.
    Measured under: a delta keyed on ``subject_key`` alone rather than on
    ``(test_id, subject_key)`` — fails, 3 introduced rather than 10, because
    eight of the ten share the ``ApplyRoundRecord`` subject across eight seals.
    """
    repo, base, head = scenarios.acceptance, scenarios.base, scenarios.head_compiling
    _checkout(repo, head)
    changed = (_EDITED_PATH,)
    result = _gate(repo, base, head, Role.BODIES, changed)

    assert result.status is ReachabilitySweepStatus.CHECKED
    assert _pairs(result.introduced) == _INTRODUCED_BY_THE_COMPILING_EDIT
    assert len(result.introduced) == 10

    # `subject_path` is relative to the SWEPT ROOT (DISPUTE D2), so the row
    # asserts the file and not the prefix: under either consistent scoping the
    # ten name `preserve.go`, and under neither do they name the edited file.
    assert {Path(f.subject_path).name for f in result.introduced} == {
        Path(_INTRODUCED_SUBJECT_PATH).name
    }
    assert all(f.subject_line > 0 for f in result.introduced), (
        "a report that cannot name a line names a place nobody can open"
    )

    scoped_would_report = [
        f
        for f in result.introduced
        if any(Path(f.subject_path).name == Path(c).name for c in changed)
    ]
    assert scoped_would_report == [], (
        "the scoped reading reports 0 of 10 on this branch, which is the "
        "measurement scoped was refused on; if this list is non-empty the "
        "fixture stopped being the canonical defect"
    )
    assert _INTRODUCED_SUBJECT_PATH not in changed
    assert _INTRODUCED_SEAL_PATH not in changed


def test_a_pre_existing_breach_outside_the_changed_directory_is_not_introduced(
    scenarios: _Scenarios,
) -> None:
    """**DISPUTE D2, sealed as a property.** The two halves of a delta must cover
    the same scope.

    A branch whose only change is a comment in ``cmd/gates/main.go`` has
    introduced nothing. The acceptance tree's twelve standing BREACHes are all
    in ``cmd/iterate`` — *measured under* ``4df25e3``: ``cmd/gates`` swept alone
    reports 12 seals, 19 findings, **0 BREACH**, 9 abstentions.

    The contract's step 5 derives the base subtree from the changed paths
    (``cmd/gates``) and its step 6 sweeps the head at ``repo_root`` (both
    packages). *Measured*, that mix reports **12 introduced** on this branch,
    every one of them pre-existing and none of them the branch's — the
    permanently-red failure the delta ruling exists to prevent, arriving through
    the materialisation door. It reaches ``sweep_is_vacuous`` and passes:
    head 30 seals against base 12 trips neither the shrinking-seal check nor the
    equal-seals check.

    Both CONSISTENT scopings pass this row — sweeping both halves at the derived
    subtree, and sweeping both halves at the repository root — so the row rules
    on symmetry and not on which scope. That is why every expectation in this
    file is written in the tree-root-free spelling ``_short`` produces.

    THE CONTROL, in the same call: the tree really does carry twelve standing
    BREACHes at this branch's head, measured by the shipped mechanism. Without
    it, "introduced is empty" is a claim about a gate that might have seen
    nothing.

    Needs only ``branch_reachability``; no wiring.

    Measured under: base materialised as the ``cmd/gates`` subtree while the
    head is swept at ``repo_root`` — this row fails with 12 introduced.
    Measured under: base materialised at the subtree and swept at
    ``<destination>/cmd/gates`` while the head is swept at ``repo_root`` — fails
    with 22 introduced on the compiling branch, because the subject keys are
    qualified by the swept tree root and NOTHING matches.
    """
    repo, base, head = scenarios.acceptance, scenarios.base, scenarios.head_gates_only
    _checkout(repo, head)

    standing = _breach_pairs(repo)
    assert standing == _STANDING_BREACH_SEALS, (
        "the twelve must still be standing at this branch's head, or 'not "
        "introduced' is a claim about a gate that had nothing to decline"
    )

    result = _gate(repo, base, head, Role.BODIES, ("cmd/gates/main.go",))
    assert result.status is ReachabilitySweepStatus.CHECKED
    assert result.introduced == (), (
        "a branch that edited only cmd/gates is being refused for cmd/iterate's "
        "standing BREACHes; the base half and the head half of the delta are "
        f"not covering the same scope. introduced={_pairs(result.introduced)}"
    )
    assert verdict_of(result) is DiffVerdict.CLEAN


def test_the_swept_scope_never_cuts_the_module_the_change_lives_in(
    scenarios: _Scenarios,
) -> None:
    """**DISPUTE D3.** A scope derived from the changed paths must still contain
    the module's seals.

    ``d6_import_scope`` is ONE Go module: ``go.mod`` at the tree root,
    ``cmd/app`` holding the only production entrypoint, ``pkg/b`` and ``pkg/c``
    holding the seals and the dark subject. *Measured under* ``4df25e3``:

      * the whole tree — **2 seals, 2 findings, 1 BREACH, 1 abstention**;
      * ``cmd/app`` extracted alone — **0 seals, 0 findings, 0 production roots,
        and no error**. A subtree that is not a module analyses to nothing,
        silently.

    So a branch that edits only ``cmd/app/main.go`` under the contract's
    "shallowest directory containing all of them" derivation is swept over a
    tree with no ``go.mod``, reports ``NO_SEAL_IN_TREE`` — *CLEAN, and loud* —
    and states that a tree holding two seals holds none. The cheap exit and the
    honest-status ruling are both satisfied and the answer is false.

    This row rules on the OBSERVABLE consequence and not on the derivation: the
    gate must have examined the module's seals. Every derivation that takes the
    scope up to the nearest enclosing ``go.mod`` satisfies it; the shallowest-
    changed-directory one does not.

    THE CONTROL, in the same call: the mechanism finds two seals in this tree.
    Without it, ``head_seals_examined == 2`` is a claim about a number nobody
    took.

    Needs only ``branch_reachability``; no wiring.

    Measured under: deriving the scope as the shallowest directory containing
    the changed paths — this row fails, ``NO_SEAL_IN_TREE`` and 0 seals against
    a tree the mechanism finds 2 in.
    """
    repo = scenarios.import_scope
    _checkout(repo, scenarios.import_head)

    whole = check_tree(repo)
    assert whole.seals_examined == 2
    assert whole.dispositions[Disposition.BREACH] == 1

    result = _gate(
        repo,
        scenarios.import_base,
        scenarios.import_head,
        Role.BODIES,
        ("cmd/app/main.go",),
    )
    assert result.status is not ReachabilitySweepStatus.NO_SEAL_IN_TREE, (
        "the gate reports NO_SEAL_IN_TREE for a tree the mechanism finds two "
        "seals in; the swept scope cut the module in half"
    )
    assert result.head_seals_examined == whole.seals_examined
    assert result.introduced == ()
    assert verdict_of(result) is DiffVerdict.CLEAN


def test_a_declaration_deleted_at_head_is_introduced_and_names_what_it_was(
    tmp_path: Path,
) -> None:
    """``was`` is the difference between two branch actions that look alike.

    A BREACH at head whose key was ACCEPTED at base is **introduced** — the
    branch deleted the declaration that was covering it — and a BREACH whose key
    was absent at base is introduced too. A report that could not tell them
    apart sends the author to the wrong file: one is "add the call site", the
    other is "put the appeal back or add the call site".

    Built in three commits, each a real branch action:

      * ``base`` — the plain tree;
      * ``declared`` — the compiling edit AND an appeal answering all ten of the
        findings it introduces, so the branch is CLEAN;
      * ``withdrawn`` — the same source, the appeal file deleted and nothing
        else changed.

    Judged as ``declared`` → ``withdrawn``, all ten are introduced with
    ``was=ACCEPTED``, and the diff between the two refs contains no ``.go`` file
    at all. That is the branch action a delta keyed only on code would miss
    entirely.

    THE CONTROLS, in the same call: the same ten judged as ``base`` →
    ``compiling`` carry ``was=OK`` — production reached them at base — so
    ``was`` is shown to distinguish rather than to be a constant, and a
    hard-coded ``was`` passes one of the two and not both.

    Needs only ``branch_reachability``; no wiring.

    Measured under: ``introduced_findings`` reading ONE declaration set for both
    halves — this row fails, 0 introduced, because the base's appeal would clear
    the head too.
    Predicted (unmeasured) under: hard-coding ``was=None`` — fails here and
    passes the control.
    Measured under: reading the appeal from ``branch_ref`` for both halves —
    fails, 0 introduced.
    Measured under: step 3's cheap exit taken on ``analyzable_paths`` alone —
    fails, ``NO_ANALYZABLE_FILE_IN_DIFF`` and CLEAN, because the only changed
    file is ``.dispatcher.staged.yaml``. That is DISPUTE D6 and it is the reason
    this row passes the TRUTHFUL changed-path list rather than a convenient one.
    """
    repo = _staged(_ACCEPTANCE_FIXTURE, tmp_path / "withdrawn")
    base = _init_repo(repo)

    _compiling_edit(repo)
    undeclared = _commit_all(repo, "compiling, no appeal")
    reported = _gate(repo, base, undeclared, Role.BODIES, (_EDITED_PATH,))
    assert len(reported.introduced) == 10
    assert {f.was for f in reported.introduced} == {Disposition.OK}, (
        "the ten were reached from production at base, so `was` must say OK "
        "here and ACCEPTED below; a constant `was` passes one and not both"
    )

    _declaration_file(repo).write_text(
        _declaration_yaml(reported.introduced, wiring="SMG-9999 wires it")
    )
    declared = _commit_all(repo, "the appeal, answering all ten")

    _declaration_file(repo).unlink()
    withdrawn = _commit_all(repo, "the appeal, withdrawn")

    changed_between = tuple(
        _git(repo, "diff", "--name-only", declared, withdrawn).split()
    )
    assert changed_between == (br.DECLARATION_PATH,), (
        "the two refs differ in the appeal file and in nothing else; the ten "
        "findings below are a branch ACTION and not a code change"
    )

    # DISPUTE D6: the TRUTHFUL changed-path list is passed, which contains no
    # file any ANALYZERS row can read. Step 3's cheap exit would clear this
    # branch, and its soundness argument — "a branch that changed no file any
    # analyzer can read changed no call edge" — is true and does not cover the
    # appeal file, which changes the ADJUDICATION and not the edges.
    result = _gate(repo, declared, withdrawn, Role.BODIES, changed_between)
    assert result.status is ReachabilitySweepStatus.CHECKED
    assert len(result.introduced) == 10
    assert {f.was for f in result.introduced} == {Disposition.ACCEPTED}
    assert {f.disposition for f in result.introduced} == {Disposition.BREACH}
    assert verdict_of(result) is DiffVerdict.VIOLATION


# --------------------------------------------------------------------------- #
# 3. Delta's own evasion. Target 2.
# --------------------------------------------------------------------------- #


def test_a_branch_cannot_buy_clean_by_breaking_the_build(
    scenarios: _Scenarios,
) -> None:
    """**Target 2.** Break the build and the delta is empty; the gate refuses.

    *Measured under* ``4df25e3``: the same one-file edit written so
    ``cmd/iterate`` no longer compiles takes the tree from 30 seals to 12,
    48 findings to 19, 12 BREACHes to 0, and the delta to **zero**. A gate that
    trusted its delta would answer CLEAN for a branch that deleted the evidence.

    The row asserts the STATUS and not merely the verdict, because
    ``UNDETERMINED`` is reachable from four statuses and only one of them is
    this: an implementation that refused every broken-looking branch with
    ``UNCHECKED_ANALYZER_FAULT`` would pass a verdict-only assertion.

    THE CONTROL, in the same call: the compiling edit over the same base, which
    is CHECKED and refused for ten real findings. Without it, "the broken branch
    is UNDETERMINED" is satisfied by a gate that answers UNDETERMINED always.

    Needs only ``branch_reachability``; no wiring.

    Measured under: dropping the ``sweep_is_vacuous`` call from step 7 — this
    row fails with ``CHECKED`` / 0 introduced / CLEAN, which is the branch
    buying CLEAN by breaking the build.
    Measured under: ``sweep_is_vacuous`` keyed on ``unanalyzed_paths`` instead —
    same failure, because that field is 2 on both halves.
    """
    repo, base = scenarios.acceptance, scenarios.base

    _checkout(repo, scenarios.head_broken)
    broken = _gate(repo, base, scenarios.head_broken, Role.BODIES, (_EDITED_PATH,))
    assert broken.status is ReachabilitySweepStatus.UNCHECKED_SWEEP_VACUOUS
    assert broken.introduced == (), (
        "on any status but CHECKED the introduced set is empty by contract; "
        "the refusal must come from the guard and not from the delta"
    )
    assert verdict_of(broken) is DiffVerdict.UNDETERMINED
    assert broken.head_seals_examined < broken.base_seals_examined
    assert broken.detail.strip(), (
        "a refusal a reader cannot see the reason for is the vacuous half of "
        "this gate"
    )

    _checkout(repo, scenarios.head_compiling)
    honest = _gate(repo, base, scenarios.head_compiling, Role.BODIES, (_EDITED_PATH,))
    assert honest.status is ReachabilitySweepStatus.CHECKED
    assert verdict_of(honest) is DiffVerdict.VIOLATION
    assert len(honest.introduced) == 10


def test_sweep_is_vacuous_names_the_fields_that_moved_not_the_one_that_did_not(
    scenarios: _Scenarios,
) -> None:
    """The guard is keyed on fields that MOVED in the measurement it exists for.

    IMPLEMENTED at P1. This row is the measurement that makes the choice of
    fields checkable rather than argued: over the broken pair,
    ``seals_examined`` goes 30 → 12 and ``findings`` 48 → 19, while
    ``unanalyzed_paths`` is **2 on both sides**. A guard keyed on
    ``unanalyzed_paths`` returns ``None`` for exactly the pair it exists to
    refuse — "a guard that reads as protection", the failure ``FLOOR_GLOBS``
    records for the brace-compressed glob.

    THE CONTROLS, in the same call: the honest pair (base against the compiling
    head) must return ``None``. A predicate that returned a sentence for every
    pair would refuse every branch and pass a one-sided row.

    Measured under: keying check 1 on ``len(unanalyzed_paths)`` — fails, the
    broken pair returns ``None``.
    Measured under: ``return None`` — fails on the broken pair.
    Measured under: ``return "vacuous"`` — fails on the honest pair.
    Measured under: check 2 guarded on the BASE's production roots rather than
    the head's — the zero-production-roots assertion below fails.
    """
    _checkout(scenarios.acceptance, scenarios.base)
    base = check_tree(scenarios.acceptance)
    _checkout(scenarios.acceptance, scenarios.head_broken)
    broken = check_tree(scenarios.acceptance)
    _checkout(scenarios.acceptance, scenarios.head_compiling)
    compiling = check_tree(scenarios.acceptance)

    reason = sweep_is_vacuous(base, broken)
    assert reason is not None
    assert "12" in reason and "30" in reason, (
        "the sentence must carry the two seal counts, because they are what "
        "makes the evasion readable off a CI log"
    )

    assert sweep_is_vacuous(base, compiling) is None, (
        "the honest pair must support a delta; a guard that refuses every pair "
        "refuses every branch"
    )
    assert sweep_is_vacuous(base, base) is None

    # The field the guard deliberately does NOT read, measured equal across the
    # pair it must refuse.
    assert len(broken.unanalyzed_paths) == len(base.unanalyzed_paths)

    # Check 2, on a head with seals and zero production roots, and with the
    # seal and finding counts held EQUAL to base's so that checks 1 and 3
    # cannot be what answers. Built from the measured report rather than
    # invented, so the shape is real.
    headless = _replace_roots(base, ())
    assert headless.seals_examined == base.seals_examined > 0
    assert len(headless.findings) == len(base.findings)
    reason_two = sweep_is_vacuous(base, headless)
    assert reason_two is not None
    assert "production" in reason_two


# --------------------------------------------------------------------------- #
# 4. The nine sweep statuses. Target 4.
# --------------------------------------------------------------------------- #

#: **Every :class:`ReachabilitySweepStatus` member and the row that PRODUCES
#: it.** Nine rows, and :func:`test_every_sweep_status_has_a_witness_and_none_reads_as_a_pass`
#: refuses a member without one — the shape ``tests/test_floor_closure.py``
#: uses for ``_DELEGATION_TARGETS``, for the same reason: a state nobody
#: produces is a state nobody has checked, and a tenth member added without a
#: witness must redden a row rather than arrive silently.
_STATUS_WITNESSES: dict[ReachabilitySweepStatus, str] = {
    ReachabilitySweepStatus.CHECKED: "test_the_defect_is_caught_though_the_diff_touches_neither_subject_nor_seal",
    ReachabilitySweepStatus.NOT_THIS_ROLES_GATE: "test_the_five_roles_are_judged_over_one_introduced_set",
    ReachabilitySweepStatus.NO_ANALYZABLE_FILE_IN_DIFF: "test_a_diff_with_no_analyzable_file_takes_the_cheap_exit_without_sweeping",
    ReachabilitySweepStatus.NOT_REACHED_ALREADY_VIOLATION: "test_an_already_violation_branch_does_not_pay_and_says_so",
    ReachabilitySweepStatus.NO_SEAL_IN_TREE: "test_a_tree_with_no_seal_is_clean_and_loud",
    ReachabilitySweepStatus.UNCHECKED_HEAD_NOT_CHECKED_OUT: "test_a_head_that_is_not_checked_out_is_refused_not_assumed",
    ReachabilitySweepStatus.UNCHECKED_BASE_UNAVAILABLE: "test_a_base_that_cannot_be_materialised_is_refused_not_emptied",
    ReachabilitySweepStatus.UNCHECKED_ANALYZER_FAULT: "test_an_analyzer_fault_is_refused_on_the_role_whose_gate_it_is",
    ReachabilitySweepStatus.UNCHECKED_SWEEP_VACUOUS: "test_a_branch_cannot_buy_clean_by_breaking_the_build",
    # P4, 2026-08-12 — DISPUTE D4 closed. The tenth member and the eleventh it
    # forced, each with the row that PRODUCES it through the shipped code path
    # rather than by building a record. This dict going from nine rows to
    # eleven in the same commit as the enum is the whole mechanism the D4
    # ruling was blocked on: P3 could not add a member without reddening this
    # file, and P4 adds both halves at once.
    ReachabilitySweepStatus.UNCHECKED_APPEAL_UNREADABLE: "test_an_unreadable_appeal_is_its_own_status_and_not_a_vacuous_sweep",
    ReachabilitySweepStatus.UNCHECKED_GATE_DEFECT: "test_a_role_this_gate_cannot_map_is_a_defect_and_says_so",
}


def test_every_sweep_status_has_a_witness_and_none_reads_as_a_pass() -> None:
    """ELEVEN states, eleven producing rows, and no CLEAN state that is silent.

    **NINE until D7 P4, 2026-08-12.** The tenth
    (``UNCHECKED_APPEAL_UNREADABLE``) closes dispute D4 and the eleventh
    (``UNCHECKED_GATE_DEFECT``) is forced by it — see both members' docstrings.
    The line below that read "A tenth member reddens this rather than arriving
    unchecked" is no longer a prediction: it is what happened, and the
    prediction at the bottom of this docstring is upgraded from *Predicted
    (unmeasured, and unmeasurable — the enum is closed)* to a measurement.

    Three claims, and the third is the one the ruling is about:

      1. every member of :class:`ReachabilitySweepStatus` is named in
         :data:`_STATUS_WITNESSES` and every witness is a real row in this
         module. A tenth member reddens this rather than arriving unchecked;
      2. :func:`verdict_for_status` is total and RAISES on a non-member —
         asserted alongside its five CLEAN and four UNDETERMINED answers, so a
         dispatch that returned CLEAN for everything fails here rather than
         passing "it is total";
      3. **no status reads as a pass**, mechanically: the record has no default
         for ``status``, so a body cannot assemble a
         :class:`BranchReachability` that is silently ``CHECKED``. That is the
         difference between "this gate cleared your branch" and "this gate did
         not ask about your branch", and it is the sentence ``role_protocol``
         bought its two CLEAN signature rows with.

    **DEFECT D5, and it is RED today.** The shipped guard is ``if status not in
    ReachabilitySweepStatus``, and on Python 3.12+ ``in`` on an enum class does
    a **value** lookup. *Measured under* ``4df25e3`` on python 3.13.7:
    ``verdict_for_status("unchecked_analyzer_fault")`` returns
    ``DiffVerdict.CLEAN`` — the permissive answer, for a blocking status, on the
    one dispatch whose own docstring says falling through here "is a new
    spelling of the permissive answer". How production reaches it: ``status`` is
    a field on a record that ``role_protocol._print_report`` must print and that
    ``RoleDiffResult`` carries, and every serialisation this repository has —
    ``yaml_io``, the journal — round-trips an enum to its VALUE. A record
    rebuilt from a log carries strings. ``isinstance`` is the fix and it is a
    body edit in this module.

    Measured under: deleting the ``UNCHECKED_SWEEP_VACUOUS`` row from
    ``_BLOCKING_SWEEP_STATUSES`` — claim 2 fails.
    Measured under: giving ``BranchReachability.status`` a default of
    ``CHECKED`` — claim 3 fails.
    Measured under (2026-08-12, and it was `Predicted (unmeasured, and
    unmeasurable — the enum is closed)` until the enum was opened): the tenth
    and eleventh members added and their `_STATUS_WITNESSES` rows withheld —
    claim 1 fails, naming `UNCHECKED_APPEAL_UNREADABLE` first. That is the
    mechanism P3 was blocked by, doing exactly what it is for.
    Measured under: the shipped ``not in`` guard — the string case fails, which
    is the state today.
    Measured under: ``isinstance(status, ReachabilitySweepStatus)`` — every
    claim passes.
    """
    module = globals()
    for status in ReachabilitySweepStatus:
        assert status in _STATUS_WITNESSES, (
            f"{status} is produced by no row in this file; a state nobody "
            "produces is a state nobody has checked"
        )
        witness = _STATUS_WITNESSES[status]
        assert callable(module.get(witness)), (
            f"{status}'s witness {witness!r} is not a row in this module"
        )

    blocking = {
        ReachabilitySweepStatus.UNCHECKED_HEAD_NOT_CHECKED_OUT,
        ReachabilitySweepStatus.UNCHECKED_BASE_UNAVAILABLE,
        ReachabilitySweepStatus.UNCHECKED_ANALYZER_FAULT,
        ReachabilitySweepStatus.UNCHECKED_SWEEP_VACUOUS,
        ReachabilitySweepStatus.UNCHECKED_APPEAL_UNREADABLE,
        ReachabilitySweepStatus.UNCHECKED_GATE_DEFECT,
    }
    for status in ReachabilitySweepStatus:
        expected = (
            DiffVerdict.UNDETERMINED if status in blocking else DiffVerdict.CLEAN
        )
        assert verdict_for_status(status) is expected, status
    assert len({verdict_for_status(s) for s in ReachabilitySweepStatus}) == 2

    with pytest.raises(BranchReachabilityError):
        verdict_for_status(_NotAMember())  # type: ignore[arg-type]
    with pytest.raises(BranchReachabilityError):
        # DEFECT D5: `x in SomeEnum` does a VALUE lookup on Python 3.12+, so the
        # shipped `if status not in ReachabilitySweepStatus` guard admits the
        # bare string spelling of a member and answers CLEAN for it. Measured
        # under 4df25e3 on python 3.13.7:
        # verdict_for_status("unchecked_analyzer_fault") -> DiffVerdict.CLEAN.
        # That is the permissive answer with a new spelling, on the one dispatch
        # whose docstring forbids exactly it.
        verdict_for_status("unchecked_analyzer_fault")  # type: ignore[arg-type]

    status_field = next(
        f for f in dataclass_fields(BranchReachability) if f.name == "status"
    )
    import dataclasses

    assert status_field.default is dataclasses.MISSING, (
        "BranchReachability.status must have no default: a record that can be "
        "built without naming why the sweep did or did not run is a record "
        "whose CLEAN reads as a pass"
    )


def test_a_diff_with_no_analyzable_file_takes_the_cheap_exit_without_sweeping(
    scenarios: _Scenarios,
) -> None:
    """**The exit most branches take, and the reason the gate is affordable.**

    A branch that changed no file any :data:`ANALYZERS` row can read changed no
    call edge in any language this gate can see. It is the direct analogue of
    ``UNCHECKED_NO_SUPPORTED_FILE`` and, like it, nothing the branch commits
    clears it — so it does not refuse.

    **The claim is not "CLEAN"; the claim is "without sweeping".** A gate that
    ran both sweeps and then answered CLEAN would satisfy a verdict-only row and
    cost 15 s on every Python-only branch — which on this repository is nearly
    all of them (*measured under* ``4df25e3``, this worktree: ``check_tree``
    over this repository's own tree reports **0 seals, 0 findings, 391
    unanalyzed paths and 3 production roots**, all three from the vendored Go
    helper subtrees, in 1.4 s). So the row asserts the seal counts are zero: no
    sweep ran.

    THE CONTROL, in the same call: the same repository, the same refs, one
    ``.go`` path in ``changed_paths`` — which does NOT take the exit.

    Needs only ``branch_reachability``; no wiring.

    Predicted (unmeasured) under: taking the exit whenever ``changed_paths`` is
    empty rather than when ``analyzable_paths`` is empty — this row fails, the
    gate sweeps.
    Measured under: ``analyzable_paths`` returning every path, so the exit is
    never taken — this row fails. The other direction (``analyzable_paths``
    returning ``()``, so the exit is always taken) reddens
    :func:`test_the_cheap_exit_asks_the_one_extension_table`.
    """
    repo, base, head = scenarios.acceptance, scenarios.base, scenarios.head_compiling
    _checkout(repo, head)

    quiet = _gate(
        repo,
        base,
        head,
        Role.BODIES,
        ("README.md", "src/claude_dispatcher/cli.py", "docs/x.ts"),
    )
    assert quiet.status is ReachabilitySweepStatus.NO_ANALYZABLE_FILE_IN_DIFF
    assert verdict_of(quiet) is DiffVerdict.CLEAN
    assert quiet.head_seals_examined == 0 and quiet.base_seals_examined == 0, (
        "the cheap exit must be CHEAP; a gate that swept and then took it pays "
        "the whole price on every branch in a language it cannot read"
    )
    assert quiet.introduced == ()

    loud = _gate(repo, base, head, Role.BODIES, (_EDITED_PATH,))
    assert loud.status is not ReachabilitySweepStatus.NO_ANALYZABLE_FILE_IN_DIFF


def test_a_tree_with_no_seal_is_clean_and_loud(tmp_path: Path) -> None:
    """**The primary target is exactly this shape.** Zero seals, CLEAN, and said.

    *Measured under* ``4df25e3``, re-measured here rather than inherited: the
    primary target ``evenplay-mono/apps/website-public-api`` @ ``51a71736c``
    reports **0 seals, 0 findings, 0 roots, 6 unanalyzed paths, in 7.75 s** —
    the whole price of one sweep, paid to learn that this gate has nothing to
    say about the tree it was commissioned for. D5 judges the SUBJECTS OF SEALS, so a tree
    with no seal yields no finding and this gate has nothing to say — but
    "nothing to say" must be on the verdict line, because a CLEAN that does not
    say why is indistinguishable from a CLEAN that checked something.

    Built as a real Go module with a ``main`` and one production-only helper and
    no ``_test.go`` at all. *Measured under* ``4df25e3``: ``check_tree`` over it
    reports 0 seals, 0 findings and **1 production root** — so the tree is
    readable and the zero is a fact about seals rather than a broken sweep.

    THE CONTROLS, in the same call: the mechanism itself finds one production
    root here (so this is not a tree nothing could read), and the status is NOT
    ``CHECKED`` (so the CLEAN is named).

    Needs only ``branch_reachability``; no wiring.

    Predicted (unmeasured) under: returning ``CHECKED`` when both seal counts are
    zero — this
    row fails on the status assertion while the verdict assertion still passes,
    which is why the status is asserted.
    Measured under: mapping ``NO_SEAL_IN_TREE`` into ``_BLOCKING_SWEEP_STATUSES``
    — fails, UNDETERMINED for a tree nothing the branch commits can change.
    """
    tree = tmp_path / "noseal"
    (tree / "app").mkdir(parents=True)
    (tree / "app" / "go.mod").write_text("module example.com/noseal\n\ngo 1.21\n")
    (tree / "app" / "main.go").write_text(
        "package main\n\nimport \"fmt\"\n\n"
        "func main() { fmt.Println(Helper()) }\n\n"
        "// Helper is reached from main and from nothing else.\n"
        "func Helper() string { return \"h\" }\n"
    )
    base = _init_repo(tree)
    _touch_comment(tree / "app" / "main.go", "a change with no seal anywhere")
    head = _commit_all(tree, "head")

    report = check_tree(tree)
    assert report.seals_examined == 0
    assert sum(1 for r in report.roots if r.root_kind is RootKind.PRODUCTION) == 1, (
        "the tree must be READABLE, or 'no seal' is a broken sweep wearing the "
        "cheap exit's name"
    )

    result = _gate(tree, base, head, Role.BODIES, ("app/main.go",))
    assert result.status is ReachabilitySweepStatus.NO_SEAL_IN_TREE
    assert result.status is not ReachabilitySweepStatus.CHECKED
    assert verdict_of(result) is DiffVerdict.CLEAN
    assert result.head_seals_examined == 0 and result.base_seals_examined == 0


def test_a_head_that_is_not_checked_out_is_refused_not_assumed(tmp_path: Path) -> None:
    """**The architectural gap, refused rather than assumed away.**

    ``check_branch`` reads BLOBS out of the object store and never needs a
    checkout; ``check_tree`` takes a DIRECTORY. ``check_body_branch.sh``
    documents that it runs in the checkout to be judged, so the assumption holds
    at both of today's call sites — and an assumption that holds is still an
    assumption, and this one silently judges the WRONG REVISION when it stops
    holding.

    The row makes it stop holding: the repository is checked out at ``base``
    while ``branch_ref`` names the compiling head, which really does introduce
    ten. A gate that assumed the checkout answers CLEAN — it sweeps the base
    against the base — and that is the failure, not the refusal.

    THE CONTROL, in the same call: the identical arguments with the head checked
    out, which is CHECKED and finds the ten. The pair is what shows the refusal
    is about the checkout and not about the refs.

    Needs only ``branch_reachability``; no wiring.

    Measured under: sweeping ``repo_root`` without comparing HEAD to
    ``branch_ref`` — this row fails CLEAN with 0 introduced, having judged the
    base twice.
    Predicted (unmeasured) under: refusing whenever HEAD is not a branch name —
    the control fails, because the control's checkout is a detached sha.
    """
    repo = _staged(_ACCEPTANCE_FIXTURE, tmp_path / "notcheckedout")
    base = _init_repo(repo)
    _compiling_edit(repo)
    head = _commit_all(repo, "compiling")

    _checkout(repo, base)
    wrong = _gate(repo, base, head, Role.BODIES, (_EDITED_PATH,))
    assert wrong.status is ReachabilitySweepStatus.UNCHECKED_HEAD_NOT_CHECKED_OUT
    assert verdict_of(wrong) is DiffVerdict.UNDETERMINED
    assert wrong.introduced == ()

    _checkout(repo, head)
    right = _gate(repo, base, head, Role.BODIES, (_EDITED_PATH,))
    assert right.status is ReachabilitySweepStatus.CHECKED
    assert len(right.introduced) == 10


def test_a_base_that_cannot_be_materialised_is_refused_not_emptied(
    scenarios: _Scenarios,
) -> None:
    """A delta with one side missing is not a delta.

    **Never "then everything is new" and never "then nothing is".** Both
    tempting defaults are a verdict about a revision nobody read: the first
    refuses the branch for the whole tree's standing set — twelve here — and the
    second clears it for anything.

    The row asks for a base ref that does not exist, on a head that really does
    introduce ten. Both wrong answers are excluded explicitly and by number.

    THE CONTROL, in the same call: the same head against the real base, which is
    CHECKED with exactly ten. Without it, "UNDETERMINED" is satisfied by a gate
    that never resolves any base.

    Needs only ``branch_reachability``; no wiring.

    Measured under: an unresolvable ``base_ref`` swallowed into an empty report
    — this row fails, 22 introduced (the head's whole BREACH set).
    Predicted (unmeasured) under: an unresolvable ``base_ref`` swallowed into a
    CLEAN — fails on the verdict.
    """
    repo, head = scenarios.acceptance, scenarios.head_compiling
    _checkout(repo, head)

    missing = _gate(repo, "0" * 40, head, Role.BODIES, (_EDITED_PATH,))
    assert missing.status is ReachabilitySweepStatus.UNCHECKED_BASE_UNAVAILABLE
    assert verdict_of(missing) is DiffVerdict.UNDETERMINED
    assert missing.introduced == ()

    present = _gate(repo, scenarios.base, head, Role.BODIES, (_EDITED_PATH,))
    assert present.status is ReachabilitySweepStatus.CHECKED
    assert len(present.introduced) == 10


def test_an_analyzer_fault_is_refused_on_the_role_whose_gate_it_is(
    scenarios: _Scenarios, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """**The raise D6's enrolment introduced, and the state that pays for it.**

    Before enrolment a tree with ``.go`` files on a host with no usable ``go``
    returned a silent empty report; since enrolment it RAISES
    ``TOOLCHAIN_MISSING`` out of ``discover_roots``. A CI image without a Go
    toolchain is the recorded non-empty case, and a broken image must never
    clear a Go branch.

    The fault is produced for REAL and not by substituting a seam: a ``go``
    that answers nothing is put at the front of ``PATH`` and the module's
    once-per-process helper cache is reset, which is what a broken CI image
    looks like from inside this process. *Measured under* ``4df25e3``, both
    shapes raise out of ``discover_roots``: in a fresh interpreter with no
    ``go`` on ``PATH`` at all, ``check_tree`` raises
    ``CallSiteReachabilityError`` reading ``…could not derive roots…
    toolchain_missing: no `go` on PATH…``; with the shim it is the
    ``TOOLCHAIN_UNUSABLE`` probe failure. The shim is what this row uses,
    because emptying ``PATH`` removes ``git`` and ``tar`` as well and the row
    would then be measuring the wrong absence.

    THE CONTROL, in the same call: the identical arguments with ``PATH``
    restored, which is CHECKED and finds the ten. It is what shows the refusal
    is about the toolchain and not about the branch — and it is judged after the
    fault, so a body that cached the fault into the record fails here.

    Needs only ``branch_reachability``; no wiring.

    Measured under: the fault reported as ``NO_SEAL_IN_TREE`` instead — this row
    fails CLEAN with 0 introduced, a broken image clearing a Go branch.
    Predicted (unmeasured) under: letting the raise escape — this row fails with
    ``CallSiteReachabilityError``, and ``check_branch_reachability`` is
    contracted never to raise.
    """
    repo, base, head = scenarios.acceptance, scenarios.base, scenarios.head_compiling
    _checkout(repo, head)

    # A REAL broken toolchain: a `go` that answers nothing, shadowing the real
    # one at the front of PATH. Emptying PATH outright would remove `git` and
    # `tar` too and the row would be measuring the wrong absence — which is a
    # fault this row hit and is why the shim is a shim and not a deletion.
    bin_dir = tmp_path / "bin-with-a-broken-go"
    bin_dir.mkdir()
    shim = bin_dir / "go"
    shim.write_text("#!/bin/sh\nexit 1\n")
    shim.chmod(0o755)

    with monkeypatch.context() as patched:
        patched.setattr(gor, "_GO_REACHABILITY_PREPARED", None)
        patched.setenv("PATH", f"{bin_dir}:{os.environ['PATH']}")
        faulted = check_branch_reachability(
            repo, base, head, Role.BODIES, (_EDITED_PATH,), already_violation=False
        )
    assert faulted.status is ReachabilitySweepStatus.UNCHECKED_ANALYZER_FAULT
    assert verdict_of(faulted) is DiffVerdict.UNDETERMINED
    assert faulted.introduced == ()

    healthy = _gate(repo, base, head, Role.BODIES, (_EDITED_PATH,))
    assert healthy.status is ReachabilitySweepStatus.CHECKED
    assert len(healthy.introduced) == 10


# --------------------------------------------------------------------------- #
# 5. ACCEPTED, through `.dispatcher.staged.yaml`. Target 5.
# --------------------------------------------------------------------------- #


def _declaration_file(repo: Path) -> Path:
    return repo / br.DECLARATION_PATH


def _declaration_yaml(introduced: Any, *, wiring: str) -> str:
    """A ``.dispatcher.staged.yaml`` answering the findings the GATE reported.

    Written from the gate's OWN report and never from a second sweep, and that
    is the load-bearing choice in this helper. ``test_id``, ``subject_key`` and
    ``subject_path`` are every one of them relative to the SWEPT ROOT (DISPUTE
    D2), so a declaration keyed from a sweep at a different root matches
    nothing. Deriving them from :attr:`BranchReachability.introduced` also seals
    the property no other row can: **the keys the gate PRINTS are the keys a
    declaration MATCHES ON**, without which no human could write a working
    appeal from a gate report.
    """
    rows = [
        {
            "test_id": finding.test_id,
            "subject_key": finding.subject_key,
            "wiring": wiring,
            "reason": f"staged: {finding.subject_key} is wired by the above",
        }
        for finding in introduced
    ]
    assert rows, "an appeal answering nothing seals nothing"
    return yaml_io.dumps(rows)


def _replace_roots(report: Any, roots: tuple) -> Any:
    """``report`` with its ``roots`` replaced. Frozen dataclass, so a copy."""
    import dataclasses

    return dataclasses.replace(report, roots=roots)


def test_ten_declarations_clear_the_branch_and_the_same_ten_with_whitespace_do_not(
    tmp_path: Path,
) -> None:
    """**Target 5, both directions, through this layer.**

    Ten declarations with real ``wiring`` answering the ten findings the
    compiling edit introduces take the branch to **0 introduced / CLEAN**. The
    same ten rows with ``wiring: "   "`` take it to **10 introduced /
    VIOLATION**. That is R8's ratification condition — *a declaration with no
    wiring is not a declaration* — holding through the diff-time layer and not
    only inside ``adjudicate``.

    **The two directions are the row.** A layer that honoured every declaration
    passes the first half; a layer that honoured none passes the second; only a
    layer that asks ``_declaration_answers`` passes both, and the scaffold
    records that its own first draft re-spelled the match locally and dropped
    the ``wiring`` condition exactly here.

    The declaration file is read out of the BRANCH's object store, so both
    variants are real commits.

    Needs only ``branch_reachability``; no wiring.

    The appeal is written from the GATE's own report of the undeclared branch,
    which is how a human writes one and is the only spelling that is guaranteed
    to match (DISPUTE D2). That makes this row also the seal on **the keys the
    gate prints being the keys a declaration matches on**.

    Measured under: matching on the two keys without the ``wiring`` condition —
    the whitespace half fails, 0 introduced where 10 are owed.
    Measured under: ignoring ``DECLARATION_PATH`` entirely — the first half
    fails, 10 introduced where 0 are owed.
    Measured under: reading the declarations from ``base_ref`` instead of
    ``branch_ref`` — the first half fails; a declaration is a statement about
    code the branch is ADDING and a base-pinned read cannot express it.
    Predicted (unmeasured) under: printing an ``IntroducedFinding.subject_key``
    that is not the key ``adjudicate`` matches on — both halves fail, and
    nothing else in this file would have caught it.
    """
    repo = _staged(_ACCEPTANCE_FIXTURE, tmp_path / "declared")
    base = _init_repo(repo)

    _compiling_edit(repo)
    undeclared = _commit_all(repo, "compiling, no appeal")
    reported = _gate(repo, base, undeclared, Role.BODIES, (_EDITED_PATH,))
    assert len(reported.introduced) == 10

    _declaration_file(repo).write_text(
        _declaration_yaml(reported.introduced, wiring="SMG-9999 wires it")
    )
    honoured = _commit_all(repo, "declared, with a wiring sentence")

    cleared = _gate(repo, base, honoured, Role.BODIES, (_EDITED_PATH,))
    assert cleared.status is ReachabilitySweepStatus.CHECKED
    assert cleared.introduced == (), (
        f"ten real declarations must clear the ten; {_pairs(cleared.introduced)}"
    )
    assert verdict_of(cleared) is DiffVerdict.CLEAN
    assert cleared.head_dispositions is not None
    assert cleared.head_dispositions[Disposition.ACCEPTED] == 10, (
        "ACCEPTED is counted apart from OK because a growing ACCEPTED count is "
        "a debt figure and must be legible as one"
    )

    _declaration_file(repo).write_text(
        _declaration_yaml(reported.introduced, wiring="   ")
    )
    hollow = _commit_all(repo, "declared, with whitespace where the sentence goes")

    refused = _gate(repo, base, hollow, Role.BODIES, (_EDITED_PATH,))
    assert refused.status is ReachabilitySweepStatus.CHECKED
    assert _pairs(refused.introduced) == _INTRODUCED_BY_THE_COMPILING_EDIT
    assert verdict_of(refused) is DiffVerdict.VIOLATION


def test_the_declaration_match_is_the_shared_one_and_not_a_local_respelling(
    scenarios: _Scenarios,
) -> None:
    """One place answers "does this declaration answer this finding".

    The scaffold records the defect this row exists for: its first draft of
    :func:`dispositions_by_key` re-spelled the match locally, matched on the two
    keys, and **silently dropped the ``wiring`` condition** — so a declaration
    ``check_tree`` ignores would have been honoured here and the two halves of
    one gate would have disagreed about what an appeal is.

    Two claims, and both are needed:

      1. **identity** — the name ``branch_reachability`` dispatches on IS
         ``call_site_reachability._declaration_answers``. A local copy reddens
         this immediately, before it has a chance to drift;
      2. **behaviour**, over a REAL finding from the shipped mechanism: a
         matching declaration with a sentence gives ACCEPTED; the same
         declaration with whitespace wiring gives BREACH; a one-character typo
         in either key gives BREACH. Three answers from one call site, so a
         dispatch that answered one thing for everything fails.

    Identity alone would pass a body that imported the name and then never
    called it; behaviour alone would pass a body that re-implemented it
    correctly today and drifted tomorrow. Together they are the ruling.

    Measured under: the call to ``_declaration_answers`` inside
    :func:`dispositions_by_key` replaced by an inline two-key comparison — the
    whole file stays GREEN except for the ordering case below, because
    ``adjudicate`` re-applies the wiring condition downstream and answers BREACH
    anyway. **That measurement is why the ordering case is in this row**: it is
    the only observable consequence of the defect the scaffold records, and a
    row without it would have been a row that could not fail for the reason it
    names. With the ordering case, the same mutation is RED.
    Measured under: ``def _declaration_answers`` defined locally in this module
    — claim 1 fails immediately on the identity.
    Predicted (unmeasured) under: passing ``None`` for every declaration — the
    ACCEPTED case fails.
    """
    assert br._declaration_answers is csr._declaration_answers, (
        "`_declaration_answers` is the ONE place that answers whether a "
        "declaration answers a finding; a second copy here is how the two "
        "halves of one gate come to disagree about what an appeal is"
    )

    _checkout(scenarios.acceptance, scenarios.base)
    report = check_tree(scenarios.acceptance)
    breach = next(
        f for f in report.findings if csr.adjudicate(f, None) is Disposition.BREACH
    )
    key = (breach.seal.test_id, breach.subject.key)

    def _decl(*, test_id: str, subject_key: str, wiring: str) -> StagedDeclaration:
        return StagedDeclaration(
            test_id=test_id,
            subject_key=subject_key,
            wiring=wiring,
            reason="a seal row",
        )

    real = _decl(test_id=key[0], subject_key=key[1], wiring="SMG-9999")
    hollow = _decl(test_id=key[0], subject_key=key[1], wiring="   ")
    typo_seal = _decl(test_id=key[0] + "x", subject_key=key[1], wiring="SMG-9999")
    typo_subject = _decl(test_id=key[0], subject_key=key[1] + "x", wiring="SMG-9999")

    assert dispositions_by_key(report, (real,))[key] is Disposition.ACCEPTED
    assert dispositions_by_key(report, (hollow,))[key] is Disposition.BREACH
    assert dispositions_by_key(report, (typo_seal,))[key] is Disposition.BREACH
    assert dispositions_by_key(report, (typo_subject,))[key] is Disposition.BREACH
    assert dispositions_by_key(report, ())[key] is Disposition.BREACH

    # THE ORDERING CASE, and it is the only one a local re-spelling actually
    # changes. Measured: a key-only match inside this function is invisible in
    # every row above, because `adjudicate` re-applies the wiring condition
    # downstream and answers BREACH anyway. It becomes visible here: a hollow
    # declaration followed by a real one for the SAME key. `check_tree`'s own
    # loop is first-match-wins over `_declaration_answers` (`if matched is
    # None`), so it skips the hollow one — it is not a declaration — and
    # honours the real one. A local key-only match stops at the hollow one and
    # hands `adjudicate` a declaration that answers nothing.
    assert dispositions_by_key(report, (hollow, real))[key] is Disposition.ACCEPTED, (
        "first match wins over `_declaration_answers`, which a whitespace "
        "wiring is not; a local re-spelling that matched on the two keys "
        "alone would stop at the hollow row and the two halves of one gate "
        "would disagree about which appeal answered this finding"
    )
    assert dispositions_by_key(report, (real, hollow))[key] is Disposition.ACCEPTED


def test_declarations_at_refuses_an_unreadable_appeal_instead_of_reading_zero(
    tmp_path: Path,
) -> None:
    """"I could not read the appeals" answered with "there were no appeals" is a
    silent BREACH.

    Three contracted behaviours, in one call so that no two of them can be
    satisfied by the same constant:

      * **absent** is zero declarations and no error — most branches have none;
      * **present and well-formed** is the declarations, read out of the REF's
        object store and not the working tree, so a ref whose file differs from
        the checkout answers the ref;
      * **present and not a list of mappings** is a
        :class:`BranchReachabilityError`, never ``()``. That is the shape
        ``load_role_policy_from_base`` refuses for the policy.

    The object-store half is the one a working-tree read passes by accident, so
    the row commits one file and then overwrites the checkout with a DIFFERENT
    one before asking.

    Needs only ``branch_reachability``; no wiring.

    Measured under: ``return ()`` on any parse failure — the malformed case
    fails.
    Measured under: reading ``repo_root / DECLARATION_PATH`` from disk instead
    of out of the ref — the object-store case fails, 2 declarations where 1 is
    owed.
    Predicted (unmeasured) under: raising on an absent file — the absent case
    fails.
    """
    repo = _staged(_ACCEPTANCE_FIXTURE, tmp_path / "appeals")
    empty = _init_repo(repo)
    assert declarations_at(repo, empty) == ()

    _declaration_file(repo).write_text(
        yaml_io.dumps(
            [
                {
                    "test_id": "cmd/iterate.TestSeal_G2_Whatever",
                    "subject_key": "example.com/m.Symbol",
                    "wiring": "SMG-9999 wires it next sprint",
                    "reason": "staged deliberately",
                }
            ]
        )
    )
    one = _commit_all(repo, "one declaration")

    # A DIFFERENT working tree than the ref carries: a working-tree read answers
    # two here and the object store answers one.
    _declaration_file(repo).write_text(
        yaml_io.dumps(
            [
                {
                    "test_id": "a",
                    "subject_key": "b",
                    "wiring": "w",
                    "reason": "r",
                },
                {
                    "test_id": "c",
                    "subject_key": "d",
                    "wiring": "w",
                    "reason": "r",
                },
            ]
        )
    )
    read = declarations_at(repo, one)
    assert len(read) == 1, (
        "the appeal is read out of the ref's object store, never the working "
        "tree; a caller substituting the git seam for one gate and not the "
        "other is how two reads come to disagree"
    )
    assert read[0].wiring == "SMG-9999 wires it next sprint"
    assert isinstance(read[0], StagedDeclaration)

    _declaration_file(repo).write_text("- 3\n- 4\n")
    malformed = _commit_all(repo, "an appeal file that is not a list of mappings")
    with pytest.raises(BranchReachabilityError):
        declarations_at(repo, malformed)

    assert declarations_at(repo, empty) == ()


# --------------------------------------------------------------------------- #
# 6. Where the cost sits. Target 6.
# --------------------------------------------------------------------------- #


def test_an_already_violation_branch_does_not_pay_and_says_so(
    scenarios: _Scenarios,
) -> None:
    """**Target 6.** The skip is a named state, not a silence.

    A branch the cheap checks already refused is coming back anyway, and paying
    15 s to add a second reason to a verdict that cannot get worse buys nothing.
    What it RISKS is a reader mistaking a VIOLATION report's silence for a
    reachability pass, and
    :attr:`ReachabilitySweepStatus.NOT_REACHED_ALREADY_VIOLATION` on the verdict
    line is the whole of the answer.

    The row asks the question on a branch that really would be refused —
    ten introduced findings are there to be found — so "nothing reported" is a
    fact about the skip and not about the branch.

    THE CONTROL, in the same call: the identical arguments with
    ``already_violation=False``, which is CHECKED and finds the ten. It is what
    makes "did not pay" mean something; without it, a gate that reported nothing
    for anything would pass.

    Needs only ``branch_reachability``; no wiring.

    Measured under: ignoring ``already_violation`` — this row fails, the seal
    counts are non-zero and the status is CHECKED.
    Predicted (unmeasured) under: returning ``CHECKED`` with an empty introduced
    set when ``already_violation`` — fails on the status while the verdict
    assertion still passes, which is why the status is asserted.
    """
    repo, base, head = scenarios.acceptance, scenarios.base, scenarios.head_compiling
    _checkout(repo, head)

    skipped = _gate(
        repo, base, head, Role.BODIES, (_EDITED_PATH,), already_violation=True
    )
    assert skipped.status is ReachabilitySweepStatus.NOT_REACHED_ALREADY_VIOLATION
    assert skipped.introduced == ()
    assert skipped.head_seals_examined == 0 and skipped.base_seals_examined == 0, (
        "the branch is being refused anyway; a second reason changes nothing "
        "except the bill"
    )
    assert verdict_of(skipped) is DiffVerdict.CLEAN, (
        "CLEAN here means 'this gate does not refuse', never 'this gate "
        "approves' — which is what the status on the verdict line carries"
    )

    paid = _gate(repo, base, head, Role.BODIES, (_EDITED_PATH,))
    assert paid.status is ReachabilitySweepStatus.CHECKED
    assert len(paid.introduced) == 10


def test_the_skip_is_ordered_after_the_role_and_before_the_sweep(
    scenarios: _Scenarios,
) -> None:
    """Steps 1-3 are the ruling, and their ORDER is observable.

    Step 1 (the role) is free and answers three of the five roles, so it comes
    first: a SCAFFOLD branch that is already VIOLATION must report
    ``NOT_THIS_ROLES_GATE`` and not ``NOT_REACHED_ALREADY_VIOLATION``, because
    the gate never asked about it at all. Step 2 (already-violation) precedes
    step 3 (the cheap exit) for the same reason in the other direction.

    Both are asserted in one call, over inputs that satisfy TWO exit conditions
    at once — which is the only way an ordering is checkable at all.

    Needs only ``branch_reachability``; no wiring.

    Measured under: testing ``already_violation`` before ``obligation_for_role``
    — the first assertion fails.
    Predicted (unmeasured) under: testing ``analyzable_paths`` before
    ``already_violation`` — the second fails.
    """
    repo, base, head = scenarios.acceptance, scenarios.base, scenarios.head_compiling
    _checkout(repo, head)

    both = _gate(
        repo, base, head, Role.SCAFFOLD, (_EDITED_PATH,), already_violation=True
    )
    assert both.status is ReachabilitySweepStatus.NOT_THIS_ROLES_GATE

    cheap = _gate(
        repo, base, head, Role.BODIES, ("README.md",), already_violation=True
    )
    assert cheap.status is ReachabilitySweepStatus.NOT_REACHED_ALREADY_VIOLATION


# --------------------------------------------------------------------------- #
# 7. The verdict composition and the abstention ruling.
# --------------------------------------------------------------------------- #


def test_the_five_dispositions_map_to_three_verdicts_and_a_sixth_raises() -> None:
    """One cell refuses; three clear; one is undetermined. Exhaustive, raising.

    IMPLEMENTED at P1 for the reason that makes this row worth writing: a stub
    that raised for everything satisfies "raises on an unmapped member"
    vacuously, so the raise is asserted **alongside all five answers** and
    alongside the count of refusing cells. A table that mapped everything to
    VIOLATION passes the raise and fails here.

    ``REPORT`` clears deliberately — a human cannot declare an
    over-approximated path into a resolved one, so refusing a branch for it is
    refusing it for something it cannot fix. ``ACCEPTED`` clears and is counted
    apart from OK. ``ABSTAIN`` is UNDETERMINED here and then narrowed by
    :data:`_BLOCKING_UNDECIDED_REASONS`, which is the row below.

    Measured under: ``_DISPOSITION_VERDICTS = {}`` — five failures.
    Measured under: mapping ``REPORT`` to VIOLATION — fails, and the
    "exactly one refuses" assertion fails with it.
    Measured under: ``return CLEAN`` for an unmapped member — the raise fails.
    """
    assert verdict_for_disposition(Disposition.OK) is DiffVerdict.CLEAN
    assert verdict_for_disposition(Disposition.REPORT) is DiffVerdict.CLEAN
    assert verdict_for_disposition(Disposition.ACCEPTED) is DiffVerdict.CLEAN
    assert verdict_for_disposition(Disposition.BREACH) is DiffVerdict.VIOLATION
    assert verdict_for_disposition(Disposition.ABSTAIN) is DiffVerdict.UNDETERMINED

    refusing = [
        d for d in Disposition
        if verdict_for_disposition(d) is DiffVerdict.VIOLATION
    ]
    assert refusing == [Disposition.BREACH]
    assert len({verdict_for_disposition(d) for d in Disposition}) == 3

    with pytest.raises(BranchReachabilityError):
        verdict_for_disposition("breach")  # type: ignore[arg-type]


def test_only_two_undecided_reasons_refuse_and_a_reasonless_abstention_raises() -> None:
    """The signature gate's abstention precedent transfers as a TEST, not a verdict.

    ``PARSE_FAILED`` and ``NO_ENTRYPOINT`` refuse because a BODIES branch can
    fix exactly those with an edit it is permitted to make. ``DYNAMIC_EDGE``,
    ``UNSUPPORTED_LANGUAGE`` and ``SUBJECT_UNIDENTIFIED`` do not, because
    nothing the blocking role could commit clears them — the discriminator
    ``role_protocol`` ruled with on 2026-08-09.

    ``DYNAMIC_EDGE`` is the load-bearing one and it is measured, not reasoned:
    the acceptance tree abstains **9 times of 48 findings, all DYNAMIC_EDGE**
    (:func:`test_the_nine_dynamic_edge_abstentions_do_not_refuse_the_branch`
    drives it through the gate). Refusing it would make that tree UNDETERMINED
    on every branch forever — the permanently-red failure arriving through the
    abstention door instead of the BREACH door.

    ``None`` raises: ``Finding``'s own constructor invariant says an UNDECIDED
    finding carries a reason, so ``None`` means the record arrived from
    somewhere that does not validate, and picking a side of the blocking set for
    it is the guess this module refuses.

    **DEFECT D5, in its dangerous direction, and it is RED today.** ``if reason
    not in UndecidedReason`` admits the bare string ``"parse_failed"`` on Python
    3.12+ (``in`` is a VALUE lookup there), which then fails the membership test
    against ``_BLOCKING_UNDECIDED_REASONS`` — a frozenset of MEMBERS — and the
    function answers CLEAN for the reason that must refuse. *Measured under*
    ``4df25e3`` on python 3.13.7. Reachable in production for the reason given
    on :func:`test_every_sweep_status_has_a_witness_and_none_reads_as_a_pass`:
    ``abstention_reasons`` is a printed, carried, serialisable field.

    Measured under: ``_BLOCKING_UNDECIDED_REASONS = frozenset(UndecidedReason)``
    — the three clearing rows fail.
    Measured under: ``_BLOCKING_UNDECIDED_REASONS = frozenset()`` — the two
    refusing rows fail.
    Measured under: returning CLEAN for ``None`` — the raise fails.
    Measured under: the shipped ``not in`` guard — the string case fails, which
    is the state today.
    Measured under: ``isinstance(reason, UndecidedReason)`` — every claim
    passes.
    """
    assert verdict_for_abstention(UndecidedReason.PARSE_FAILED) is DiffVerdict.UNDETERMINED
    assert verdict_for_abstention(UndecidedReason.NO_ENTRYPOINT) is DiffVerdict.UNDETERMINED
    assert verdict_for_abstention(UndecidedReason.DYNAMIC_EDGE) is DiffVerdict.CLEAN
    assert verdict_for_abstention(UndecidedReason.UNSUPPORTED_LANGUAGE) is DiffVerdict.CLEAN
    assert (
        verdict_for_abstention(UndecidedReason.SUBJECT_UNIDENTIFIED) is DiffVerdict.CLEAN
    )
    assert len({verdict_for_abstention(r) for r in UndecidedReason}) == 2

    with pytest.raises(BranchReachabilityError):
        verdict_for_abstention(None)
    with pytest.raises(BranchReachabilityError):
        verdict_for_abstention(_NotAMember())  # type: ignore[arg-type]
    with pytest.raises(BranchReachabilityError):
        # DEFECT D5 again, and here it is the dangerous direction: on Python
        # 3.12+ `"parse_failed" in UndecidedReason` is True by VALUE, so the
        # shipped guard passes the bare string through to a membership test
        # against a frozenset of MEMBERS, which it fails, and the function
        # answers CLEAN for the reason that must refuse. Measured under
        # 4df25e3 on python 3.13.7.
        verdict_for_abstention("parse_failed")  # type: ignore[arg-type]


def test_the_nine_dynamic_edge_abstentions_do_not_refuse_the_branch(
    scenarios: _Scenarios,
) -> None:
    """The abstention door, held shut on a real tree.

    *Measured under* ``4df25e3``: the acceptance tree's ``cmd/gates`` package
    abstains **nine** times, every one ``DYNAMIC_EDGE``, and every one correct —
    the two remaining holes are ``context.CancelFunc`` values in the subject's
    own package. A gate that refused ``DYNAMIC_EDGE`` would answer UNDETERMINED
    for this tree on every branch forever.

    The branch is the ``cmd/gates`` comment change, so the nine are in scope
    under either consistent sweep scoping (DISPUTE D2).

    **Abstentions are deliberately not subject to the delta** and this row shows
    why that is safe here rather than merely stated: the nine are pre-existing
    AND they do not refuse, so neither half of the asymmetry is doing the work.

    THE CONTROL, in the same call: a record carrying the same nine reasons plus
    one ``PARSE_FAILED`` IS undetermined. Without it, "nine abstentions clear"
    is satisfied by a gate that never reads ``abstention_reasons`` at all.

    Needs only ``branch_reachability``; no wiring.

    Measured under: adding ``DYNAMIC_EDGE`` to ``_BLOCKING_UNDECIDED_REASONS`` —
    this row fails UNDETERMINED.
    Measured under: dropping ``abstention_reasons`` from ``verdict_of`` — the
    control fails.
    """
    repo, base, head = scenarios.acceptance, scenarios.base, scenarios.head_gates_only
    _checkout(repo, head)

    result = _gate(repo, base, head, Role.BODIES, ("cmd/gates/main.go",))
    assert result.status is ReachabilitySweepStatus.CHECKED
    assert len(result.abstention_reasons) == 9
    assert set(result.abstention_reasons) == {UndecidedReason.DYNAMIC_EDGE}
    assert verdict_of(result) is DiffVerdict.CLEAN

    import dataclasses

    poisoned = dataclasses.replace(
        result,
        abstention_reasons=result.abstention_reasons + (UndecidedReason.PARSE_FAILED,),
    )
    assert verdict_of(poisoned) is DiffVerdict.UNDETERMINED


def test_verdict_of_blocks_only_the_blocking_role_and_takes_the_worst() -> None:
    """The composition, in one place, over hand-built records.

    Two claims that must be made together or neither means anything:

      1. **the obligation gates the verdict** — the SAME record carrying an
         introduced BREACH is VIOLATION under BLOCKING and CLEAN under ADVISORY
         and NOT_RUN. One record, three answers, so an implementation that
         ignored ``obligation`` fails and one that ignored ``introduced``
         fails too;
      2. **worst, not first** — a record carrying a CLEAN-contributing finding
         *before* a refusing one is still refused, in both orders, because
         first-wins clears a branch whenever the harmless answer sorts ahead of
         the real one.

    :func:`worst_verdict` is asserted directly on the empty sequence too: CLEAN,
    and an unrankable member raises.

    Measured under: ``verdict_of`` returning ``worst_verdict`` without consulting
    the obligation — claim 1's advisory and not-run rows fail.
    Measured under: ``verdict_of`` returning ``verdicts[0]`` — claim 2 fails in
    one of the two orders, which is why both are here.
    Measured under: returning CLEAN under BLOCKING — claim 1's first row fails.
    """
    breach = IntroducedFinding(
        test_id="p.TestSeal_X",
        subject_key="example.com/m.Dark",
        subject_path="p/dark.go",
        subject_line=10,
        disposition=Disposition.BREACH,
        was=None,
        reason=None,
        detail="dark",
    )
    accepted = IntroducedFinding(
        test_id="p.TestSeal_Y",
        subject_key="example.com/m.Staged",
        subject_path="p/staged.go",
        subject_line=20,
        disposition=Disposition.ACCEPTED,
        was=None,
        reason=None,
        detail="staged",
    )

    def _record(obligation, introduced, status=ReachabilitySweepStatus.CHECKED):
        return BranchReachability(
            status=status, obligation=obligation, introduced=introduced
        )

    assert verdict_of(_record(ReachabilityObligation.BLOCKING, (breach,))) is (
        DiffVerdict.VIOLATION
    )
    assert verdict_of(_record(ReachabilityObligation.ADVISORY, (breach,))) is (
        DiffVerdict.CLEAN
    )
    assert verdict_of(_record(ReachabilityObligation.NOT_RUN, (breach,))) is (
        DiffVerdict.CLEAN
    )

    assert verdict_of(
        _record(ReachabilityObligation.BLOCKING, (accepted, breach))
    ) is DiffVerdict.VIOLATION
    assert verdict_of(
        _record(ReachabilityObligation.BLOCKING, (breach, accepted))
    ) is DiffVerdict.VIOLATION
    assert verdict_of(
        _record(ReachabilityObligation.BLOCKING, (accepted,))
    ) is DiffVerdict.CLEAN

    # A blocking STATUS refuses even with nothing introduced, and only on the
    # blocking role.
    faulted = _record(
        ReachabilityObligation.BLOCKING,
        (),
        status=ReachabilitySweepStatus.UNCHECKED_ANALYZER_FAULT,
    )
    assert verdict_of(faulted) is DiffVerdict.UNDETERMINED
    assert verdict_of(
        _record(
            ReachabilityObligation.ADVISORY,
            (),
            status=ReachabilitySweepStatus.UNCHECKED_ANALYZER_FAULT,
        )
    ) is DiffVerdict.CLEAN

    assert worst_verdict(()) is DiffVerdict.CLEAN
    assert worst_verdict(
        [DiffVerdict.CLEAN, DiffVerdict.UNDETERMINED, DiffVerdict.VIOLATION]
    ) is DiffVerdict.VIOLATION
    assert worst_verdict(
        [DiffVerdict.CLEAN, DiffVerdict.UNDETERMINED]
    ) is DiffVerdict.UNDETERMINED
    with pytest.raises(BranchReachabilityError):
        worst_verdict(["clean"])  # type: ignore[list-item]


# --------------------------------------------------------------------------- #
# 8. The delta's identity, and the one extension table.
# --------------------------------------------------------------------------- #


def test_the_delta_is_keyed_on_the_seal_and_the_subject_and_does_not_deduplicate(
    scenarios: _Scenarios,
) -> None:
    """Both halves of the key, and two seals over one subject are two findings.

    :class:`StagedDeclaration` requires both keys to match exactly, so a delta
    keyed on one of them would let a seal RENAME retire a finding. And the delta
    must not deduplicate: the acceptance tree measures 30 seals producing 48
    findings, and eight of the ten findings the compiling edit introduces share
    the single subject ``ApplyRoundRecord`` across eight distinct seals.

    *Measured under* ``4df25e3``: keyed on ``subject_key`` alone the ten become
    three; keyed on ``test_id`` alone they become nine.

    THE CONTROL, in the same call: the number of DISTINCT subjects among the ten
    is two, so "ten" cannot be arrived at by counting subjects, and the number
    of distinct seals is nine, so it cannot be arrived at by counting seals
    either. Only the pair gives ten.

    Measured under: keying ``dispositions_by_key`` on ``finding.subject.key``
    alone — this row fails, ten collapse to three.
    Measured under: deduplicating by subject — same failure.
    """
    _checkout(scenarios.acceptance, scenarios.base)
    base = check_tree(scenarios.acceptance)
    _checkout(scenarios.acceptance, scenarios.head_compiling)
    head = check_tree(scenarios.acceptance)

    keys = dispositions_by_key(head)
    assert len(keys) == len(head.findings) == 48, (
        "one disposition per finding; a keying that collapsed two seals over "
        "one subject would lose a claim nobody withdrew"
    )

    ten = introduced_findings(base, head)
    assert len(ten) == 10
    assert len({f.subject_key for f in ten}) == 2
    assert len({f.test_id for f in ten}) == 9
    assert len({(f.test_id, f.subject_key) for f in ten}) == 10


def test_the_cheap_exit_asks_the_one_extension_table() -> None:
    """:func:`analyzable_paths` owns no second answer to "what language is this".

    The expectation is DERIVED from :func:`analyzer_for_path` and never written
    out, deliberately: "``.py`` is not analyzable" is true only because
    :data:`ANALYZERS` holds one row today, and a row that transcribed it would
    pin a transient unimplementedness — a measured vacuity shape on this
    codebase. When a Python row is enrolled this test keeps meaning the same
    thing.

    THE CONTROL, in the same call, and it is what stops the derivation being
    circular: over this input at least one path IS selected and at least one is
    NOT, so a function returning ``()`` or returning its argument fails. Both
    facts are asserted against the shipped table rather than against a literal.

    Measured under: ``return tuple(changed_paths)`` — the "not everything"
    assertion fails.
    Measured under: ``return ()`` — the "at least one" assertion fails.
    Measured under: ``path.endswith(".go")`` spelled locally — passes today and
    is not what this row can catch; DISPUTE D4 records why the identity claim
    is left to the module's own import discipline.
    """
    paths = (
        "cmd/iterate/main.go",
        "cmd/gates/preserve.go",
        "src/claude_dispatcher/cli.py",
        "README.md",
        "web/app.ts",
        "db/schema.sql",
    )
    selected = analyzable_paths(paths)

    assert selected == tuple(p for p in paths if analyzer_for_path(p) is not None)
    assert set(selected) < set(paths), "not every path can be read by an analyzer"
    assert selected, "at least one path must be readable, or the row proves nothing"
    assert list(selected) == sorted(selected, key=paths.index), (
        "order is preserved; the caller derives a subtree from these"
    )


# --------------------------------------------------------------------------- #
# 9. What the gate must not do to the repository.
# --------------------------------------------------------------------------- #


def test_the_gate_never_writes_into_the_repository_and_leaves_nothing_behind(
    tmp_path: Path,
) -> None:
    """Three obligations that are one obligation: read the repository, own nothing.

      * **never write into ``repo_root``.** ``check_tree``'s own obligation, on
        ``fixture_reachability.construct_witness``'s reasoning: a workspace
        inside the tree under check is picked up by the very thing being
        interrogated. A base tree extracted under ``repo_root`` would
        additionally appear in the HEAD sweep as new Go packages, which is a
        gate manufacturing its own findings;
      * **remove the base tree afterwards.** A gate that leaks 472 KB per PR is
        a gate someone turns off in a month. Asserted on the SUCCESS path here
        and on the failure path by the ``UNCHECKED_BASE_UNAVAILABLE`` row's own
        repository being byte-identical after;
      * **leave git's worktree registry alone.** ``git archive`` and not
        ``git worktree add``, measured 75x cheaper and 580x smaller — and a
        removed directory leaves a REGISTERED worktree, so the next ``add``
        fails until ``git worktree prune``. A gate that can wedge a repository
        it was only supposed to read is not a gate anyone leaves on.

    A fresh repository, not the shared one, so a body that writes into it cannot
    contaminate another row's input.

    THE CONTROL, in the same call: the gate really did work — CHECKED, ten
    introduced. Without it, "the tree is unchanged" is satisfied by a gate that
    did nothing at all.

    Needs only ``branch_reachability``; no wiring.

    Measured under: extracting the base into ``repo_root / ".d7-base-workspace"``
    — this row fails on the snapshot, and fifteen other rows fail with it,
    because the base tree then appears in the HEAD sweep as new Go packages.
    Measured under: leaving the extraction directory behind under ``tmp_path``
    — not caught here and not claimed; the removal obligation is asserted for
    ``repo_root`` only, because ``destination`` is the caller's to choose.
    Predicted (unmeasured) under: ``git worktree add --detach`` for the base —
    the registry assertion fails with one extra registered worktree.
    """
    repo = _staged(_ACCEPTANCE_FIXTURE, tmp_path / "untouched")
    base = _init_repo(repo)
    _compiling_edit(repo)
    head = _commit_all(repo, "compiling")

    def _snapshot() -> dict[str, bytes]:
        return {
            str(p.relative_to(repo)): p.read_bytes()
            for p in sorted(repo.rglob("*"))
            if p.is_file() and ".git" not in p.parts
        }

    before = _snapshot()
    worktrees_before = _git(repo, "worktree", "list")

    result = _gate(repo, base, head, Role.BODIES, (_EDITED_PATH,))
    assert result.status is ReachabilitySweepStatus.CHECKED
    assert len(result.introduced) == 10

    assert _snapshot() == before, (
        "the gate wrote into the repository it was asked to read; a workspace "
        "inside the tree under check is picked up by the thing being "
        "interrogated"
    )
    assert _git(repo, "worktree", "list") == worktrees_before, (
        "a gate that can wedge git's worktree registry is not a gate anyone "
        "leaves on; the measured route is `git archive <subtree> | tar -x`"
    )
    assert _git(repo, "status", "--porcelain") == "", (
        "the gate left the working tree dirty"
    )


def test_materialise_base_tree_refuses_a_destination_inside_the_repository(
    tmp_path: Path,
) -> None:
    """``destination`` MUST be outside ``repo_root``, and the refusal is here.

    The obligation is on :func:`materialise_base_tree` itself and not only on
    its caller, because the caller is the function that would be tempted: a
    destination under ``repo_root`` is the cheapest thing to write and the
    hardest failure to see, since the base tree then appears in the HEAD sweep
    as new Go packages and the gate manufactures its own findings.

    THE CONTROL, in the same call: a destination OUTSIDE the repository
    succeeds and yields a tree the shipped mechanism can read — the same 18
    seals ``cmd/iterate`` reports on its own. Without it, "raises inside" is
    satisfied by a function that raises everywhere.

    Needs only ``branch_reachability``; no wiring.

    Measured under: no containment check — the first half fails.
    Predicted (unmeasured) under: raising unconditionally — the control fails.
    Measured under: returning ``destination / subtree`` rather than
    ``destination`` — the control's seal count is unchanged (18 either way) but
    the SUBJECT KEYS lose their ``cmd/iterate`` qualifier, which is DISPUTE D2
    and is why this row asserts the keys and not only the count.
    """
    repo = _staged(_ACCEPTANCE_FIXTURE, tmp_path / "materialise")
    base = _init_repo(repo)

    with pytest.raises(BranchReachabilityError):
        materialise_base_tree(repo, base, "cmd/iterate", repo / "inside")

    outside = tmp_path / "outside"
    outside.mkdir()
    root = materialise_base_tree(repo, base, "cmd/iterate", outside)
    report = check_tree(root)
    assert report.seals_examined == 18
    assert report.dispositions[Disposition.BREACH] == 12

    assert (outside / "cmd" / "iterate" / "go.mod").is_file(), (
        "`git archive <ref> <subtree> | tar -x` reproduces the subtree's PATH "
        "under the destination, and the returned root must be the destination "
        "itself: the subject key is qualified by the package's directory "
        "relative to the swept root, so a root of `<destination>/cmd/iterate` "
        "produces keys that match NOTHING the head sweep produced"
    )
    assert {f.subject.key for f in report.findings}, "the base tree must be readable"
    assert all(
        "/cmd/iterate." in f.subject.key for f in report.findings
    ), (
        "the base tree's subject keys must carry the same qualifier the head "
        "sweep produces, or every head finding reads as introduced"
    )


# --------------------------------------------------------------------------- #
# DISPUTE D4, CLOSED — the tenth status, and the eleventh it forced
# --------------------------------------------------------------------------- #


def test_an_unreadable_appeal_is_its_own_status_and_not_a_vacuous_sweep(
    scenarios: _Scenarios,
) -> None:
    """DISPUTE D4's TENTH MEMBER, produced (P4, 2026-08-12). **The witness row.**

    P3 ruled a :func:`declarations_at` failure onto
    :attr:`ReachabilitySweepStatus.UNCHECKED_SWEEP_VACUOUS` and said in the
    same breath that a tenth member was the right answer and that P3 was
    mechanically barred from giving it — ``_STATUS_WITNESSES`` requires a
    producing row per member and lives in this file, which BODIES may not
    touch. This is that row, landing in the same commit as the member.

    **WHAT IT PRODUCES IT WITH.** A real branch carrying a real
    ``.dispatcher.staged.yaml`` that is present and is not a list of mappings —
    the shape ``load_role_policy_from_base`` refuses for the policy, refused
    here for the appeal. The appeal path is in the changed set, so DISPUTE D6's
    clause keeps the branch out of step 3's cheap exit and it reaches step 5b
    for real. Nothing is monkeypatched and no record is hand-built.

    **THE CONTROL, in the same call, and it is the whole point of the row:** the
    SAME repository and the SAME refs with a WELL-FORMED appeal reaches a
    different status. Without it, "a malformed appeal is
    UNCHECKED_APPEAL_UNREADABLE" is satisfied by a gate that answers that for
    every branch it is handed.

    **THE SECOND CONTROL: the status is not the vacuity one.** That is the
    ruling, stated as an assertion rather than as prose — the interim answer
    blocks exactly as this one does, so a verdict-only row cannot tell the two
    apart, and telling them apart is the entire content of the amendment.

    Measured under: the tenth member reverted, ``_APPEAL_UNREADABLE_STATUS``
    pointed back at ``UNCHECKED_SWEEP_VACUOUS`` — this row fails on the status,
    and ``test_every_sweep_status_has_a_witness_and_none_reads_as_a_pass``
    fails on the missing member.
    Measured under: ``declarations_at`` returning ``()`` instead of raising for
    a present-and-unparseable file — this row fails, because the branch then
    reaches step 6 and answers with a real sweep.
    """
    repo, base = scenarios.acceptance, scenarios.base

    _git(repo, "checkout", "-q", "-b", "appeal-broken", scenarios.head_compiling)
    (repo / DECLARATION_PATH).write_text(
        "this is a string, not a list of mappings\n", encoding="utf-8"
    )
    broken_ref = _commit_all(repo, "an appeal file nobody can read")
    _checkout(repo, broken_ref)

    broken = _gate(
        repo, base, broken_ref, Role.BODIES, (_EDITED_PATH, DECLARATION_PATH)
    )
    assert (
        broken.status is ReachabilitySweepStatus.UNCHECKED_APPEAL_UNREADABLE
    ), broken.status
    assert broken.status is not ReachabilitySweepStatus.UNCHECKED_SWEEP_VACUOUS, (
        "the interim answer is back. It blocks exactly as the tenth member "
        "does, so no verdict-only assertion can see this — and a CI log that "
        "says the two sweeps disagree sends a reader to the tree when the "
        "fault is in one YAML file"
    )
    assert verdict_of(broken) is DiffVerdict.UNDETERMINED
    assert DECLARATION_PATH in broken.detail, (
        "the refusal does not name the file that caused it, so a reader has "
        f"the status and nothing to act on: {broken.detail!r}"
    )
    assert broken.introduced == ()

    # The control: same repository, same base, a well-formed appeal.
    _git(repo, "checkout", "-q", "-b", "appeal-ok", scenarios.head_compiling)
    (repo / DECLARATION_PATH).write_text("[]\n", encoding="utf-8")
    ok_ref = _commit_all(repo, "an appeal file that reads")
    _checkout(repo, ok_ref)

    ok = _gate(repo, base, ok_ref, Role.BODIES, (_EDITED_PATH, DECLARATION_PATH))
    assert ok.status is not ReachabilitySweepStatus.UNCHECKED_APPEAL_UNREADABLE, (
        "a readable appeal was reported as unreadable, so the row above "
        "measures nothing about the appeal"
    )
    assert ok.status is ReachabilitySweepStatus.CHECKED, ok.status


def test_a_role_this_gate_cannot_map_is_a_defect_and_says_so(
    scenarios: _Scenarios,
) -> None:
    """The ELEVENTH member, produced (P4, 2026-08-12). **The witness row.**

    The tenth member forced this one. `_APPEAL_UNREADABLE_STATUS` had THREE
    users before the amendment and only one of them was about an appeal; the
    other two are an unmapped :class:`Role` and
    :func:`check_branch_reachability`'s last-resort arm, and both already said
    in their own code comments that they are a DEFECT in that module rather
    than a fact about the branch. Labelling them "appeal unreadable" would have
    been a manufactured lie where the interim ruling only had an inherited one.

    **WHAT IT PRODUCES IT WITH.** :data:`_ROLE_OBLIGATIONS` maps all five
    :class:`Role` members, so the arm is unreachable through the enum — and it
    is NOT unreachable in production, which is why it must not be raised
    through. A caller that did not validate is the shape it holds against, and
    :class:`_NotAMember` is that caller's argument. **This is not a
    hypothetical**: the D7 wiring commit measured a live one — ``python -m
    claude_dispatcher.role_protocol`` loads ``role_protocol`` twice, so
    ``__main__.Role.BODIES`` is not ``claude_dispatcher.role_protocol.
    Role.BODIES``, and every run through the CI entrypoint hit exactly this arm
    until the ``__main__`` guard was fixed.

    **THE CONTROL, in the same call:** the same repository and refs with a real
    :class:`Role` do NOT get this status. Without it, "an unmappable role is a
    gate defect" is satisfied by a gate that answers it for everything.

    Measured under: the eleventh member reverted, both sites pointed at the
    appeal status — this row fails on the status, and
    ``test_every_sweep_status_has_a_witness_and_none_reads_as_a_pass`` fails on
    the missing member.
    Measured under: the ``obligation_for_role`` guard removed so an unmapped
    role falls through — the ``KeyError`` reaches the last-resort arm, which is
    the SAME status, so this row stays green and the module's own
    ``obligation_for_role`` seal is the one that reddens. Named because a
    reader must not take this row for a seal on that dispatch.
    """
    repo, base = scenarios.acceptance, scenarios.base
    _checkout(repo, scenarios.head_compiling)

    defect = check_branch_reachability(
        repo,
        base,
        scenarios.head_compiling,
        _NotAMember(),  # type: ignore[arg-type]
        (_EDITED_PATH,),
        already_violation=False,
    )
    assert defect.status is ReachabilitySweepStatus.UNCHECKED_GATE_DEFECT, (
        defect.status
    )
    assert defect.obligation is ReachabilityObligation.BLOCKING, (
        "a role this gate has never heard of must not be recorded as NOT_RUN; "
        "'we did not ask about your branch' would be a guess"
    )
    assert verdict_of(defect) is DiffVerdict.UNDETERMINED
    assert defect.detail.strip(), (
        "a defect a reader cannot see the reason for is worse than a crash"
    )

    # The control: a real Role over the same repository does not take this arm.
    real = _gate(
        repo, base, scenarios.head_compiling, Role.BODIES, (_EDITED_PATH,)
    )
    assert real.status is not ReachabilitySweepStatus.UNCHECKED_GATE_DEFECT, (
        "a mapped role was reported as a gate defect, so the row above says "
        "nothing about the unmapped one"
    )


# --------------------------------------------------------------------------- #
# DISPUTE D1, CLOSED — the gate, sealed as REACHED, end to end
# --------------------------------------------------------------------------- #


def test_the_wired_gate_refuses_a_bodies_branch_through_check_branch(
    tmp_path: Path,
) -> None:
    """DISPUTE D1's behavioural half (P4, 2026-08-12). **No monkeypatch.**

    The static half —
    ``tests/test_floor_closure.py::test_check_branch_actually_calls_the_
    reachability_gate`` — proves the call is WRITTEN. This one proves the
    answer MOVES A VERDICT, through the real :func:`check_branch`, over a real
    repository, with nothing substituted: no ``run`` seam, no patched module
    global, no hand-built :class:`BranchReachability`. A row that patched
    ``branch_reachability.check_branch_reachability`` and watched the verdict
    change would prove the call site exists and would prove nothing about which
    answers reach it.

    **THE SHAPE, and why it needs no Go toolchain.** ``repo_root``'s HEAD is
    left at ``main`` while ``branch_ref`` is ``feat/x``, which is step 4's
    :attr:`ReachabilitySweepStatus.UNCHECKED_HEAD_NOT_CHECKED_OUT` — a BLOCKING
    status on BODIES, reached before step 5 materialises anything and before
    step 6 sweeps anything. So the row costs one ``git rev-parse`` and is
    deterministic on a host with no ``go``, and it still traverses every line
    of the wiring: the call, the obligation table, the status table,
    :func:`verdict_of`, and the union at ``_VERDICT_PRECEDENCE``.

    **THREE CONTROLS, all judged in this same call, because a bare "BODIES is
    UNDETERMINED" is satisfied by half a dozen unrelated defects:**

      1. the SAME repository, the SAME refs, role SCAFFOLD — CLEAN. Scaffold's
         obligation is NOT_RUN, so this separates "the reachability arm refused
         it" from "this repository is broken in some way that refuses
         everybody";
      2. the SAME repository, role BODIES, with the changed path a ``.py``
         file instead of a ``.go`` file — CLEAN, through step 3's cheap exit.
         This separates "the arm ran and refused" from "the arm refuses any
         branch it is asked about", and it is the control that would catch a
         wiring that ignored :func:`analyzable_paths`;
      3. the verdict's own ``detail`` names the reachability arm. A verdict
         that moved for a reason the report does not state is the vacuous half
         of this gate, and ``detail`` is the only line a caller that logs the
         verdict keeps.

    Measured under: the step-6 call deleted from ``check_branch`` — the BODIES
    row reads CLEAN and this reddens; the two controls stay green, which is
    what makes them controls.
    Measured under: the ``worst_verdict`` union replaced by ``unioned =
    verdict``, the call left in place — the BODIES row reads CLEAN and this
    reddens. **Before the static row grew its fourth claim, this was the ONLY
    red in the whole suite under that mutation** — one row standing between a
    gate that runs and a gate that is consulted. It is now two, in two files,
    failing for two different reasons.
    Measured under: ``_ROLE_OBLIGATIONS[Role.BODIES]`` set to ``NOT_RUN`` —
    the BODIES row reads CLEAN and this reddens.
    """
    repo = tmp_path / "wired"
    (repo / "cmd").mkdir(parents=True)
    (repo / "cmd" / "main.go").write_text(
        "package main\n\nfunc main() {}\n", encoding="utf-8"
    )
    (repo / "note.py").write_text("VALUE = 1\n", encoding="utf-8")
    _init_repo(repo)

    _git(repo, "checkout", "-q", "-b", "feat/x")
    (repo / "cmd" / "main.go").write_text(
        "package main\n\nfunc main() { _ = 1 }\n", encoding="utf-8"
    )
    _commit_all(repo, "a bodies edit to a go file")

    _git(repo, "checkout", "-q", "-b", "feat/py", "main")
    (repo / "note.py").write_text("VALUE = 2\n", encoding="utf-8")
    _commit_all(repo, "a bodies edit to a python file")

    # HEAD is `feat/py`, so neither `feat/x` nor `main` is checked out. That is
    # step 4's refusal for the Go branch and is invisible to the Python one,
    # which never reaches step 4.
    head = _git(repo, "rev-parse", "--abbrev-ref", "HEAD").strip()
    assert head == "feat/py", head

    go_branch = check_branch(repo, "main", "feat/x", Role.BODIES)

    assert go_branch.reachability is not None, (
        "check_branch produced no BranchReachability at all, so unit D7's gate "
        "did not run. `reachability=None` is the state the P1 scaffold left "
        "and it is NOT a pass"
    )
    assert (
        go_branch.reachability.status
        is ReachabilitySweepStatus.UNCHECKED_HEAD_NOT_CHECKED_OUT
    ), go_branch.reachability.status
    assert go_branch.reachability.obligation is ReachabilityObligation.BLOCKING
    assert go_branch.verdict is DiffVerdict.UNDETERMINED, (
        "a bodies branch whose reachability could not be checked was not "
        f"refused: {go_branch.verdict} — {go_branch.detail}"
    )
    assert not go_branch.violations, (
        "the refusal came from the path gate, not from the reachability arm, "
        "so this row measures the wrong thing"
    )

    # Control 3: the verdict says why, on the line a caller keeps.
    assert "reachability" in go_branch.detail, go_branch.detail
    assert (
        ReachabilitySweepStatus.UNCHECKED_HEAD_NOT_CHECKED_OUT.value
        in go_branch.detail
    ), go_branch.detail

    # Control 1: the same branch, a role whose gate this is not.
    scaffold = check_branch(repo, "main", "feat/x", Role.SCAFFOLD)
    assert scaffold.verdict is DiffVerdict.CLEAN, (
        "role scaffold was refused by a gate whose obligation to it is "
        f"NOT_RUN: {scaffold.verdict} — {scaffold.detail}"
    )
    assert scaffold.reachability is not None
    assert (
        scaffold.reachability.status
        is ReachabilitySweepStatus.NOT_THIS_ROLES_GATE
    ), scaffold.reachability.status

    # Control 2: bodies again, on a diff no analyzer can read.
    python_branch = check_branch(repo, "main", "feat/py", Role.BODIES)
    assert python_branch.verdict is DiffVerdict.CLEAN, (
        "a bodies branch whose whole diff is unanalyzable was refused, so the "
        "arm refuses every branch it is asked about rather than the ones it "
        f"could not check: {python_branch.verdict} — {python_branch.detail}"
    )
    assert python_branch.reachability is not None
    assert (
        python_branch.reachability.status
        is ReachabilitySweepStatus.NO_ANALYZABLE_FILE_IN_DIFF
    ), python_branch.reachability.status


# --------------------------------------------------------------------------- #
# DISPUTES — every one measured under `4df25e3`, none resolved here.
# --------------------------------------------------------------------------- #

_DISPUTES = """
D1  THE GATE IS NOT SEALED AS REACHED, AND THIS FILE CANNOT SEAL IT.
    `check_branch_reachability` has no production caller, which is the exact
    defect the unit exists to close, one level up. Wiring it into
    `role_protocol.check_branch` requires an edit to `FLOOR_GLOBS` (a floored
    module) and a row in `tests/test_floor_closure.py::_DELEGATION_TARGETS` (a
    seal file), so it is a P4 amendment and not a P3 edit — measured by the
    scaffold and re-stated in `check_branch`'s step 6. Every row in this file is
    therefore turnable-green by a body working only in `branch_reachability.py`,
    and NOT ONE of them proves the gate runs. That is the recorded protocol gap
    ("a seal proves a function behaves, never that it runs") accepted knowingly.
    The obligation transfers to the wiring commit: a row in
    `tests/test_role_protocol_diff.py` asserting that `check_branch` populates
    `RoleDiffResult.reachability` and unions `verdict_of` into its verdict, in
    the same commit as the `_DELEGATION_TARGETS` entry.

D2  STEP 5 AND STEP 6 SPECIFY DIFFERENT SCOPES, AND THE MIX IS PERMANENTLY RED.
    Step 5 derives a base SUBTREE from the changed paths; step 6 sweeps the head
    at `repo_root`. Measured on the acceptance repository:

      changed = cmd/iterate/main.go   base@<dst> (cmd/iterate under it)  vs
                                      head@repo_root      -> introduced 10  OK
      changed = cmd/gates/main.go     base@<dst> (cmd/gates under it)    vs
                                      head@repo_root      -> introduced 12  WRONG
      changed = cmd/iterate/main.go   base@<dst>/cmd/iterate vs
                                      head@repo_root      -> introduced 22  WRONG

    The 12 are cmd/iterate's standing BREACHes, absent from a base tree that
    holds only cmd/gates, and every one of them reads as introduced. The 22 are
    every head BREACH: a subject key is qualified by the package's directory
    RELATIVE TO THE SWEPT ROOT, so a base swept one directory deeper matches
    nothing. `sweep_is_vacuous` catches neither (head 30 seals against base 12
    trips no check).

    MEASURED THROUGH THE GATE against a reference implementation in a clone:
    the asymmetric mix reddens THIRTEEN rows, including
    `test_a_pre_existing_breach_outside_the_changed_directory_is_not_introduced`.

    AND THE SYMMETRIC SUBTREE READING IS NOT ADMISSIBLE EITHER, which this file
    did not expect and had to measure. Sweeping BOTH halves at the derived
    subtree reddens two rows, and the second is the finding: a subject key, a
    subject path and a seal test_id are ALL relative to the swept root, so a
    `.dispatcher.staged.yaml` written from one branch's gate report stops
    matching on the next branch — because the next branch touches different
    files and derives a different scope. An appeal whose validity depends on
    which files the branch happened to edit is not an appeal. Measured: the
    withdrawal row goes red at 0 introduced where 10 are owed. **So the sound
    reading is the repository root for BOTH halves**, and its price — a whole-
    tree `git archive` rather than a subtree one — is the honest cost of a
    stable key. That price is a P4's to accept, not a seal author's to hide:
    the contract's step 5 buys its cheapness by making the appeal file's keys
    a function of the diff.

D3  "THE SHALLOWEST DIRECTORY CONTAINING ALL OF THEM" CAN CUT A MODULE IN HALF.
    Measured on `tests/fixtures/d6_import_scope`, one Go module: the whole tree
    reports 2 seals / 1 BREACH / 1 abstention, and `cmd/app` extracted alone
    reports 0 seals, 0 findings, 0 production roots and NO error. A branch
    editing only `cmd/app/main.go` is therefore swept over a tree with no
    `go.mod`, takes `NO_SEAL_IN_TREE` — CLEAN, and loud — and states that a tree
    holding two seals holds none. The cheap exit and the honest-status rulings
    are both satisfied and the answer is false. This is the same soundness
    objection that refused the scoped reading, one layer down: the last call
    site is by definition somewhere else, and a scope derived from the changed
    paths cannot contain it. `test_the_swept_scope_never_cuts_the_module_the_
    change_lives_in` rules on the consequence — the gate must have examined the
    module's seals — and leaves the derivation to the body. Every derivation
    that walks up to the nearest enclosing `go.mod` satisfies it.

D4  STEP 9 HAS NO NAMED STATUS FOR A `declarations_at` FAILURE.
    `declarations_at` is contracted to RAISE `BranchReachabilityError` on an
    unreadable or malformed appeal file, and `check_branch_reachability` is
    contracted NEVER TO RAISE. Step 9 names no status for the gap, and none of
    the nine members fits: it is neither a vacuous sweep nor an analyzer fault
    nor an unavailable base. Left unruled rather than invented here, because
    naming a tenth state is a contract edit and a seal author may not make one.
    `test_declarations_at_refuses_an_unreadable_appeal_instead_of_reading_zero`
    seals the raise at the unit and asserts nothing about the gate's status, so
    a body is free to satisfy it under either ruling. The recommendation, for
    the P4 that takes it: a tenth member, blocking on the BODIES role, because
    an appeal file nobody could read is something an author can fix and
    re-running clears.

D5  `x in SomeEnum` IS A VALUE LOOKUP ON PYTHON 3.12+, AND TWO SHIPPED GUARDS
    ANSWER PERMISSIVELY BECAUSE OF IT. `verdict_for_status` and
    `verdict_for_abstention` both guard with `if x not in <Enum>`. Measured
    under 4df25e3 on python 3.13.7 (this repository requires >=3.11, so both
    behaviours are in scope):

      "checked" in ReachabilitySweepStatus            -> True
      verdict_for_status("unchecked_analyzer_fault")  -> DiffVerdict.CLEAN
      verdict_for_abstention("parse_failed")          -> DiffVerdict.CLEAN

    In both cases the guard passes the string through, the string then fails a
    membership test against a frozenset of MEMBERS, and the function returns the
    clearing branch — for the two inputs that must refuse. This is the failure
    those functions' own docstrings name ("falling through here is a new
    spelling of the permissive answer") arriving by the one route the author did
    not check. `verdict_for_disposition`, `obligation_for_role` and
    `worst_verdict` are NOT affected: they dispatch through a dict lookup or a
    membership test against a tuple of members, both of which reject a string.
    Sealed rather than filed only, because the fix — `isinstance` — is a body
    edit in this module and needs no ruling. Filed as well, because a P4 may
    want the same sweep run over every `in <Enum>` guard in the package.

D6  THE CHEAP EXIT CLEARS A BRANCH THAT WITHDRAWS AN APPEAL.
    `.dispatcher.staged.yaml` has no `ANALYZERS` row — it is not a language —
    so `analyzable_paths` returns () for a diff that touches only it, and step
    3 returns `NO_ANALYZABLE_FILE_IN_DIFF`, CLEAN. The exit's soundness
    argument is "a branch that changed no file any analyzer can read changed no
    call edge in any language this gate can see", which is TRUE and does not
    cover this file: deleting a declaration changes no edge, it changes the
    ADJUDICATION, and the delta is then base=ACCEPTED -> head=BREACH on every
    line the appeal was holding. Measured on the acceptance repository: a
    branch whose entire diff is the deletion of an appeal answering all ten
    findings the compiling edit introduced is worth ten VIOLATIONs and takes
    the cheap exit. `test_a_declaration_deleted_at_head_is_introduced_and_names_
    what_it_was` passes the truthful changed-path list and therefore fails
    under the exit as written. The fix is one line in step 3 and lives in this
    module — do not take the exit when `DECLARATION_PATH` is among the changed
    paths — so the row is sealable without a ruling. Filed because the general
    shape is a contract question a P4 should answer once: the gate's inputs are
    not only the files an analyzer can read, and any future non-source input to
    the verdict inherits this hole.
"""
