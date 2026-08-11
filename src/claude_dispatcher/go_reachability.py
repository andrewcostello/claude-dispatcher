r"""D6 — the Go reachability analyzer: the first concrete row for D5.

**P1 SCAFFOLD. Contracts and stubs.** Every function below raises
:class:`NotImplementedError` except the seven named at their definitions, and
the reason each is an exception is written there. P2 seals, P3 fills in.

D5 (``call_site_reachability``) is complete as a MECHANISM and is on the floor.
What it does not have is a row: :data:`~claude_dispatcher.call_site_reachability.ANALYZERS`
is ``()``, so every path in every tree comes back
:attr:`UndecidedReason.UNSUPPORTED_LANGUAGE` and no run of ``check_tree`` can
report a verdict. This module is the sibling of ``go_signature_fingerprint``,
which was the same commit one unit earlier: a registry with no rows, and then
one.

**IT IS NOT ENROLLED BY THIS COMMIT.** ``ANALYZERS`` is untouched and still
``()``; ``role_protocol`` is untouched; ``FLOOR_GLOBS`` is untouched; no call
site is added. See WHAT IS OWED BEFORE ENROLMENT. D5's import-time guard
(``_refuse_enrolment_before_flooring``) already refuses a row while the module
is off the floor, so enrolment cannot happen by accident — that is not a reason
to do it deliberately.

Provenance discipline
=====================
Every count and every citation below carries the revision and the date it was
taken at, per D5's R6 extension, and citations prefer SYMBOLS to coordinates
because a recorded line here has been wrong three times out of five and one
recording moved the line it recorded. Prose distinguishes ``Measured under:``
from ``Predicted (unmeasured) under:``, per D5's S2, and a prediction is
written where it tells the next author where to aim a mutation — but it never
wears a measurement's clothes.

Baseline for this unit: ``feat/D6-go-analyzer``, branched from
``feat/D5-floor-body`` at ``0238aa2``. Suite measured 2026-08-11 on that base,
after ``python3 -m claude_dispatcher.ts_parser_vendor``: **2313 passed, 0
failed, 13 skipped.**

THE ACCEPTANCE FIXTURE, AND THE PREMISE THAT DID NOT SURVIVE MEASUREMENT
========================================================================
This unit was handed an acceptance case: ``VerifyPreservation`` in ``cmd/gates``
and in ``cmd/iterate`` — "both contracted, implemented, mutation-verified by
their bodies, covered by green seals, and called from production in neither".
Measured before it was believed, and it is half right in a way that changes
what a correct analyzer must report.

**Measured under:** ``git grep`` / ``git show`` against the bare objects,
2026-08-11.

  * **Neither function is in this worktree at all.** ``feat/D6-go-analyzer``
    tracks no ``cmd/`` directory; the only ``go.mod`` under it is
    ``go_signature_fingerprint``'s. The symbols live on other branches.
  * On ``feat/G2-iterate-preserve`` (``1fe753b``) — the branch whose name
    matches the case — ``cmd/iterate``'s ``VerifyPreservation`` is an
    **unimplemented stub** returning ``errNotImplemented``, and ``cmd/iterate``
    tracks **no ``preserve_seal_test.go`` at all**. Zero seals name it.
  * On ``feat/G2-adj`` (``83b0b97``) both bodies have landed and both are
    sealed. That is the revision this contract is written against, and the one
    a body author should re-measure before believing any number here.

At ``83b0b97``, then, and this is the whole of it:

  * ``cmd/gates/preserve.go`` declares ``func VerifyPreservation(original,
    produced []byte, edits []Edit, level Fidelity) (violations []Divergence,
    err error)``, a package-level func in ``package main``. Nine occurrences of
    the identifier in non-test files: **one is the declaration and eight are
    comments.** Zero call expressions. ``cmd/gates/main.go`` mentions it zero
    times.
  * ``cmd/iterate/preserve.go`` declares the identical signature, also
    package-level, also ``package main``. Nine non-test occurrences: **one
    declaration, eight comments.** Zero call expressions. One of those comments
    reads, in the source, "VerifyPreservation has no non-test caller in this
    package — grep it."
  * Three seals in ``cmd/gates/preserve_seal_test.go``
    (``TestSeal_G1_VerifyPreservation_ReportsEditsOutsideTheLicensedPaths``,
    ``…_TreatsADeletionUnderGatesAsAViolation``, ``…_RefusesWhatItCannotCheck``)
    call it, **eight times, every one lexically inside the test function's own
    body** — some inside plain ``for`` loops, none behind a helper. The three
    occurrences in ``preserve_seal_helpers_test.go`` are all comments, so no
    call is routed through a helper.
  * Five seals in ``cmd/iterate/preserve_seal_test.go``
    (``TestSeal_G2_Licence_GatesIsLicensedForGatesAndForbiddenForIterate``,
    ``TestSeal_G2_VerifyPreservation_CatchesEveryArrayMalformationFromTheLicenceAlone``,
    ``…_DerivesTheLicenceFromTheEditListNotTheOutput``,
    ``…_RefusesWhatItCannotCheckOnItsOwnTerms``, and the licence row) call it,
    **nine times, all in their own bodies.**
  * Neither package has a ``func init()`` or a package-level ``var`` that
    references it.

**It is the B1 shape exactly, twice, and it is a better fixture than B1 in one
respect:** ``ResolveConfigDual``'s doc comment opens with its own name, which is
what defeated the first crude scan anyone wrote. Both ``VerifyPreservation``
doc comments do the same — ``// VerifyPreservation checks a produced document
against the original at the …`` — so **the naive "exported func with no
non-test mention" scan certifies both of them CLEAN**, and the refined
"non-comment, non-declaration production line" scan finds them only because
someone wrote the refinement. This mechanism must not be satisfiable by either.

WHAT A CORRECT ANALYZER MUST REPORT FOR THE TWO CASES
=====================================================
Stated as an obligation on P3 and as a target for P2, at ``83b0b97``, over
``check_tree`` run on a tree containing the whole repository.

**Do the seals qualify under** :func:`~claude_dispatcher.call_site_reachability.discover_seals`\ **? YES, and the
chain is checkable link by link.** ``discover_seals`` takes the roots
``discover_roots`` already derived and keeps those of kind ``TEST_FUNCTION``.
A ``TEST_FUNCTION`` root requires two independent yeses:

  1. ``seal_verify.is_test_path`` over the declaring file. **Measured under:**
     ``_TEST_PATH``'s first alternative is the literal ``_test.``, so
     ``cmd/gates/preserve_seal_test.go`` and
     ``cmd/iterate/preserve_seal_test.go`` both match. This is the shared
     matcher and D5 refuses to open a second one.
  2. the row's ``test_root_predicate`` over the symbol name.
     :func:`go_test_root_predicate` accepts ``TestSeal_G1_…`` and
     ``TestSeal_G2_…`` under Go's own rule.

Then ``discover_seals`` requires the seal's key to be in ``graph.symbols``,
which it is because this row emits a symbol for every declaration including
those in test files. Then ``subjects_of_seal`` takes the NON-TEST symbols the
seal's own body calls DIRECTLY: ``VerifyPreservation`` is declared in
``preserve.go``, which ``is_test_path`` rejects, so it is a subject. **An
import-based subject reader returns zero here** — seal and subject are both
``package main`` in one directory and there is no import between them, which is
the same measurement that killed the import reading for B1.

So the expected report, per module:

  * **``cmd/gates.VerifyPreservation``: three findings, one per seal**, each
    ``Reach.FROM_TESTS_ONLY`` / ``PathQuality.NOT_APPLICABLE`` →
    ``Disposition.BREACH``. Not one finding: ``check_tree`` judges every
    (seal, subject) pair, and a subject with no finding is a silent pass.
  * **``cmd/iterate.VerifyPreservation``: FOUR findings**, same verdict.
    **P4 CORRECTED THIS NUMBER (D6 adjudication, 2026-08-11 — DISPUTE D1
    UPHELD).** It read *five*, and five is unmeasured: the scaffold's own list
    names four distinct seal functions and then adds "and the licence row",
    which is the first of the four. Measured twice, independently — a scan
    attributing each ``VerifyPreservation(`` to its enclosing ``func``, and the
    reference call-graph walk — see the fixture's ``PROVENANCE.md``.
  * **SEVEN BREACHes from these two symbols alone**, plus whatever the rest of
    the repository contributes. Whoever enrols owes that number MEASURED, by
    running this module on the enrolling commit — the crude scan over
    ``cmd/classify`` suggests at least six more and a grep is what this
    mechanism refuses to be.
  * The seven must land over **TWO distinct subject keys and not one**, because
    the two declarations are two symbols. That is only true if the key is
    qualified by the module path — both modules declare ``package main`` and
    both declare ``func VerifyPreservation`` — and under D5's key-only
    ``Symbol`` identity a collision is not a near-miss but one symbol wearing
    two declarations. See :func:`go_symbol_key`, where it is measured. *(P4
    corrected this bullet with the one above: it read "eight distinct findings
    and not four", whose second number followed from nothing.)*

**The honest complication, and it is a real one — no longer a prediction.**
``check_subject`` reaches step 4 (the ``FROM_TESTS_ONLY`` verdict) only after
step 3 has been ruled out, and step 3 abstains when the production closure
contains **any** entry in ``CallGraph.unresolved_calls``.

**Measured under** ``feat/D6-adj2``, 2026-08-11, over the vendored acceptance
tree by a ``go/types`` walk written independently for that adjudication and run
under ``env -u HOME -u GOCACHE -u XDG_CACHE_HOME GOPROXY=off
GOMODCACHE=/nonexistent GOPATH=/nonexistent``. The walk classifies EVERY
``*ast.CallExpr`` by the syntactic form in its ``Fun`` slot — 1,114
``SelectorExpr``, 1,000 ``Ident``, 17 ``ArrayType`` (all conversions), 1
``FuncLit`` (an immediately-invoked literal), and nothing else — because the
two probes that preceded it each reported a rate over a population that
excluded the calls that mattered:

  * the production closure holds **104 symbols** and **SEVEN** unresolved sites
    inside it, every one a call through a FUNCTION VALUE: ``cancel``
    (``context.CancelFunc``, from ``context.WithTimeout``) twice in
    ``cmd/gates/main.go`` at ``runOne`` and ``runCmd``, and a ``setMember``
    closure five times in ``cmd/iterate/preserve.go`` at ``ApplyRoundRecord``;
  * 1,054 call sites name a target that lives OUTSIDE the tree. Those are
    answered questions, not holes — see ``main.go``'s EDGE GRAMMAR — and a walk
    that files them as holes abstains on every real Go tree forever;
  * ``reference`` edges move neither number: 41 in-tree references, closure
    still 104, holes still 7.

**So D6 answers 0 of its 7 findings, and it is not 4.** The scaffold's earlier
adjudication reasoned that a sound single-assignment rule would clear
``cmd/iterate``'s five holes and with them that module's four findings. The
first half is right and is now ruled (see ``main.go``'s SOLE-BINDING FUNC
LITERAL rule). **The second half is refuted by measurement**, and the reason is
a granularity nobody had looked at: ``check_subject`` computes its hole list as
``[h for h in graph.unresolved_calls if h[0].key in production_reach]``, over
the WHOLE-TREE ``production_reach`` that :func:`check_tree` builds once — so
the list is IDENTICAL for every (seal, subject) pair, and a hole in
``cmd/gates`` abstains ``cmd/iterate``'s findings too. Measured by driving
``check_subject`` directly over both modules at four hole-sets:

  ===================  ==========================  ========
  rules applied        holes in production closure  answered
  ===================  ==========================  ========
  neither              7                           0 of 7
  rule 1 only          2 (both ``cancel``)         0 of 7
  rule 2 only          5 (all ``setMember``)       0 of 7
  rules 1 and 2        0                           7 of 7
  ===================  ==========================  ========

The mechanism has no partial answer available on this repository: it is seven
or none. **ESCALATED, not decided here** — making it four would mean scoping
step 3's hole set to the subject rather than to the tree, and
``call_site_reachability.py`` is on ``FLOOR_GLOBS``. It is D5's file and D5's
ruling, and a D6 adjudication may not take it.

The remaining two are ``cancel``, and they are named rather than hand-waved:
the out-of-tree provenance argument for clearing them is REFUSED, with the
counterexample measured, in ``main.go``.

**And a limit the fixture makes concrete.** If ``cmd/iterate`` is analyzed at
``1fe753b`` instead, where no seal names ``VerifyPreservation``, the correct
report is **no finding at all** — not a BREACH, not an abstention. D5 judges
the subjects OF SEALS; a dark function nobody sealed is invisible here (limit
8), and that is dead-code detection rather than this mechanism. A body author
who "fixes" that has widened the subject population without a ruling.

WHAT THIS ROW CLAIMS, AND THE ONE CLAIM THAT MATTERS MOST
==========================================================
``negative_is_conclusive`` is ``True`` for Go, and that single boolean is the
ruling that made D5 language-parametric rather than Python-with-a-Go-case. Go
has no runtime lookup of a package-level function by name — there is no
``reflect`` route to a package's declarations — so a symbol referenced nowhere
in the production closure is called nowhere, and "no path" is a fact about the
LANGUAGE. Python's row is ``False`` for the opposite reason, measured four
times over ``src/``.

It is a per-row boolean and not a computed property, per D5's CHOICE: a
computed ``False`` is a claim a branch can make about its own judge by adding
one line, with nothing red.

WHAT IS OWED BEFORE ENROLMENT — NONE OF IT IS P1'S TO DO
=========================================================
Recorded here rather than performed, following D2's and D4's precedent exactly.

  1. **``FLOOR_GLOBS`` must grow**
     ``**/src/claude_dispatcher/go_call_reachability/**``, a SUBTREE and not a
     file, for the reason the Go fingerprinter's entry records: ``go.mod``
     fixes the language version the parse runs under and pins the module to
     stdlib-only, so it is a parser input as much as ``main.go`` is. That entry
     reddens ``test_the_floor_is_exactly_the_written_out_set_of_globs``, whose
     ``_FLOOR_ROWS`` table P4 has already ruled P3 may not edit — so the glob
     and its literal row are one P4 commit, as the Go and TypeScript subtrees
     each were.
  2. **This module itself must be floored** if it is ever imported by a floored
     module. It is not today: nothing imports it, so it is not in the
     delegation closure, and adding it to ``ANALYZERS`` is what would put it
     there.
  3. **``scripts/check_body_branch.sh``** must read this helper out of the base
     revision's object store in the self-judging case, by the rule it already
     applies to ``role_protocol`` and that ``go_helper_source_dir`` flags for
     the fingerprinter: "when its own ``src/`` lies inside the checkout under
     judgement, the branch supplied the library". A branch could otherwise
     rewrite this helper to emit an empty edge set and walk through a gate it
     had just neutered — which, because an empty graph makes every subject
     ``FROM_NEITHER``, would not even be quiet: it would take the check down
     loudly. Both directions are refused; see :meth:`GoReachabilityAnalyzer.graph`.
  4. **The ``test_id`` protocol edit** (D5's ``_test_id`` schedule, ESCALATED
     there). This row already carries :meth:`GoReachabilityAnalyzer.test_id`
     ahead of the protocol, deliberately — see that method — so the day the four
     coupled edits land, the Go row is not the thing blocking them.
  5. **A measured enrolment count**, taken that day, by enrolling in a clone.
     The Go comparator's count was wrong four times, and the recorded lesson is
     that the only trustworthy count is a measured one.

CHOICE (where this row lives): a module of its own, ``go_reachability.py``, and
not a class inside ``call_site_reachability``. Three reasons. ``role_protocol``
carries ``GoSignatureFingerprinter`` inline and that is the shape a reader would
expect — but ``call_site_reachability`` is on ``FLOOR_GLOBS`` and every edit to
it is a floor edit needing a P4 round, which would couple this unit's schedule
to the gate's; the D5 module is 3,935 lines before a row is added; and a row
that imports the mechanism is the direction the dependency should run, so that
the mechanism cannot come to depend on the row. Rejected alternative: writing it
into ``role_protocol`` beside the fingerprinter, which puts a call-graph
analyzer inside the module whose central registry is about SIGNATURES — the
exact conflation D5's ``ANALYZERS`` CHOICE refuses one level up.

CHOICE (the module's NAME): ``go_reachability.py``, deliberately NOT
``go_call_reachability.py``, which would be the obvious spelling and would sit
beside the helper package directory ``go_call_reachability/``. **Measured
2026-08-11** on CPython 3.11 in a scratch tree: a directory holding an
``__init__.py`` SHADOWS the same-named module and wins the import; a directory
holding no ``__init__.py`` — which is what a directory of ``.go`` files is —
loses, and the module wins. So the collision resolves correctly today and flips
the day anybody drops an ``__init__.py`` into the helper directory. A name whose
correctness depends on the continued absence of a file nobody guards is a name
waiting to be wrong; the two are spelled differently instead.

CHOICE (this module holds no file-extension literal and matches no PATH against
a suffix): adopted voluntarily, since D5's AST sweep
(``test_the_module_declares_no_file_extension_and_calls_no_endswith``) is scoped
to ``call_site_reachability.py`` and does not reach here — **measured
2026-08-11**, the sweep reads exactly that one file. The rule is kept anyway
because the reason for it is not about which file the sweep reads: exactly one
place in this codebase decides what language a file is, and it is
``role_protocol.support_for_path``. This module asks.

**The claim is stated precisely because the loose version of it became false
while this file was being written, and correcting the prose rather than the
code is the honest repair.** An earlier draft of this paragraph said "calls no
``endswith``" flatly. There is exactly ONE ``endswith`` in this module and it is
in :func:`go_symbol_key`, over a Go PACKAGE CLAUSE — ``package_name.endswith("_test")``
— which is not a path, not an extension, and not a language decision about a
judged tree; it is the language's own total discriminator between the two
packages that may share a directory. Naming the site here means a reader who
greps for the word finds the sentence that explains it rather than a
contradiction. The two entry-point filenames in
:data:`GO_REACHABILITY_HELPER_ENTRY_POINTS` are the other apparent exception and
are not one either: they name files inside THIS package, and
``go_helper_source_dir`` names the same two for the same reason.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

from .call_site_reachability import (
    GO_REACHABILITY_PACKAGE_DIR,
    GO_REACHABILITY_SCHEMA,
    AnalyzerFault,
    AnalyzerUnavailable,
    CallGraph,
    Edge,
    EdgeKind,
    EntrypointKind,
    Root,
    Symbol,
    _ROOT_KIND_BY_ENTRYPOINT,
)
from .role_protocol import Language, support_for_path
from .seal_verify import is_test_path

__all__ = [
    "GO_REACHABILITY_HELPER_ENTRY_POINTS",
    "go_reachability_helper_dir",
    "GoUnit",
    "GoSourceFile",
    "GoReachabilityRequest",
    "GoWireSymbol",
    "GoWireRoot",
    "GoWireEdge",
    "GoWireHole",
    "GoWireParseError",
    "GoReachabilityResponse",
    "GO_PACKAGE_VAR_SYMBOL",
    "GO_INIT_SYMBOL_TEMPLATE",
    "encode_go_reachability_request",
    "decode_go_reachability_response",
    "go_symbol_key",
    "go_test_root_predicate",
    "edge_kind_for_wire",
    "entrypoint_kind_for_wire",
    "discover_units",
    "GoReachabilityAnalyzer",
    "GO_REACHABILITY_ANALYZER",
]


# --------------------------------------------------------------------------- #
# Part 1 — where the helper is, and how its path is derived
# --------------------------------------------------------------------------- #

#: The two files that make the helper a program that can be built. Both are
#: checked, on ``go_helper_source_dir``'s ruling for the sibling: ``go.mod``
#: fixes the language version the parse runs under and pins the module to
#: stdlib-only, so an install that dropped it would reach ``go build`` and fail
#: there as HELPER_FAILED with a module error, which names the wrong party.
GO_REACHABILITY_HELPER_ENTRY_POINTS = ("main.go", "go.mod")


def go_reachability_helper_dir() -> Path:
    """Where this build's Go reachability helper source is, or the named fault.

    **The first of the seven functions this scaffold implements rather than
    stubs, and the reason is D4's for** ``ts_parser_home`` **verbatim: this
    function IS this unit's answer to "which program judges the branch", and an
    answer expressed only in prose is a note.**

    THE RULE, and the whole of it: :data:`GO_REACHABILITY_PACKAGE_DIR` resolved
    against ``Path(__file__).parent``. Never against ``repo_root``, never
    against the CWD, never against an environment variable, and never by asking
    anything in the judged tree. D4's ruling stands as the precedent — *the
    parser's location is a pure function of the dispatcher's own installed
    location, and of nothing else* — and it binds here with more force than it
    did there, because this helper computes a CALL GRAPH: a helper read out of
    the judged repository would be a call-graph analyzer supplied by the branch
    whose call graph it is computing.

    Three refusals, all :attr:`AnalyzerFault.HELPER_MISSING`, because all three
    are the same fact — *the helper this build claims to ship is not there*:

      * the directory is absent (an install that dropped a non-``.py`` asset;
        ``tests/test_packaging.py`` exists for exactly this and it has happened
        live twice, 2026-07-13);
      * either entry point in
        :data:`GO_REACHABILITY_HELPER_ENTRY_POINTS` is missing from it;
      * the directory or either entry point resolves, after following symlinks,
        to a path OUTSIDE this package directory. That is D4's containment
        check and it is deliberate belt-and-braces: under the resolution rule
        the escape should be impossible, and a symlink from ``main.go`` into the
        judged tree would satisfy every existence check while restoring the
        exact defect this unit exists to prevent, with a one-byte artifact.

    Absence is a FAULT and never "this build has no Go analysis". The second
    reading is the broken-wheel fail-open :class:`AnalyzerFault` exists to name:
    it would hand every Go branch a clean bill of health for as long as the
    install stayed broken. Note that under D5's R1 ruling the fault does not
    become an abstention — :func:`discover_roots` and :func:`build_call_graph`
    both RAISE on an :class:`AnalyzerError`, and it reaches the caller as a
    :class:`CallSiteReachabilityError` that a caller may not catch and continue.

    CHOICE (D4 checks a digest at use and this function does not, so the
    silence is marked): **there is no digest here, and the omission is the
    ruling rather than an oversight.** Rejected alternative: a
    ``GO_REACHABILITY_SOURCE_SHA256`` constant recomputed before every build,
    copying D4's shape. It is out because the expectation would have to live in
    this module, which is not floored, and a digest a branch can edit alongside
    the bytes is what ``TS_VENDORED_PARSER_SHA256``'s own docstring calls no
    review at all. The full argument: D4 checks
    :data:`~claude_dispatcher.role_protocol.TS_VENDORED_PARSER_SHA256` at USE
    — "a digest computed from the file it pins, pins nothing" — because that
    parser is a separately-versioned artifact FETCHED at install time into a
    mutable path that no floor entry can cover. This helper is the opposite
    artifact: it is tracked in git, it is reviewable source, and the mechanism
    that vouches for it is the ``FLOOR_GLOBS`` subtree entry item 1 of WHAT IS
    OWED names. Adding a digest would mean writing the expectation somewhere,
    and the only place it could live without being editable alongside the bytes
    is a floored module — which is a floor edit this unit may not make. A
    digest constant sitting in THIS module, which is not floored, would be
    exactly "a digest that a branch could edit alongside the bytes", which
    ``TS_VENDORED_PARSER_SHA256``'s own docstring names as no review at all.
    The trigger for revisiting: the first time any part of this helper is
    fetched rather than tracked.
    """
    package = Path(__file__).parent.resolve()
    directory = package / GO_REACHABILITY_PACKAGE_DIR
    if not directory.is_dir():
        raise AnalyzerUnavailable(
            AnalyzerFault.HELPER_MISSING,
            f"the Go reachability helper's source directory is not at "
            f"{directory}. An install that dropped the asset is a broken "
            "install, never 'this build has no Go analysis': the second "
            "reading hands every Go branch a clean bill of health",
        )
    missing = [
        name
        for name in GO_REACHABILITY_HELPER_ENTRY_POINTS
        if not (directory / name).is_file()
    ]
    if missing:
        raise AnalyzerUnavailable(
            AnalyzerFault.HELPER_MISSING,
            f"the Go reachability helper at {directory} is missing "
            f"{', '.join(missing)}; it is a program that cannot be built, "
            "which is a broken install and not a language nobody can read",
        )
    escaped = [
        name
        for name in GO_REACHABILITY_HELPER_ENTRY_POINTS
        if package not in (directory / name).resolve().parents
    ]
    if directory.resolve() != package / GO_REACHABILITY_PACKAGE_DIR or escaped:
        raise AnalyzerUnavailable(
            AnalyzerFault.HELPER_MISSING,
            f"the Go reachability helper at {directory} resolves outside "
            f"{package} ({', '.join(escaped) or 'the directory itself'}). A "
            "symlink into the judged tree satisfies every existence check "
            "while making the branch supply the program that computes its own "
            "call graph",
        )
    return directory


# --------------------------------------------------------------------------- #
# Part 2 — the wire protocol
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class GoUnit:
    """The package one helper invocation covers. See ``main.go``'s ``Unit``.

    ``module_path``
        The ``module`` line of the ``go.mod`` that governs the directory. Read
        by the PYTHON side out of the tree and passed in, because the helper
        does not touch the filesystem — so the analysis cannot depend on a
        working tree the branch controls.
    ``package_dir``
        Tree-relative posix directory. Part of the key, not decoration; see
        :func:`go_symbol_key`.
    ``package_name``
        The ``package`` clause. Distinguishes ``foo`` from ``foo_test`` in one
        directory, which are two packages by the language's own rules and must
        be two invocations.
    """

    module_path: str
    package_dir: str
    package_name: str


@dataclass(frozen=True)
class GoSourceFile:
    """One file of the unit: tree-relative posix path, and text.

    Source travels as TEXT, kept unchanged from ``GoHelperRequest``'s rule and
    for its reason: a helper that took paths would make the answer depend on
    the working tree.
    """

    path: str
    source: str


@dataclass(frozen=True)
class GoReachabilityRequest:
    """What the Python side sends: ONE package's whole file set.

    CHOICE (the design does not say what one invocation covers, and the sibling
    protocol says the opposite): **one PACKAGE per invocation.** This is the
    deliberate divergence from ``GoHelperRequest``, whose
    contract is "one revision of one file, not a batch". That rule is right for
    signatures and fatal here: a call graph is not a per-file property, and a
    per-file protocol would make every cross-file call inside one package an
    unresolved edge — an abstention on almost everything.

    The cost the divergence avoids is measured. The TypeScript comparator kept
    the one-process-per-file rule and pays **169 ms per file on the gate path**
    (``role_protocol``, ``TYPESCRIPT_SUPPORT`` enrolment checklist item 3,
    measured 2026-08-10), about **68 seconds for a 200-file branch**, recorded
    there as a ruled price with no caching route — because the natural fix, a
    persistent process, is refused by the one-file-per-invocation rule itself.
    This protocol costs one process per PACKAGE instead.

    What is LOST with the per-file rule, and must be replaced rather than
    mourned: the per-file timeout that made "which file" answerable. The
    replacement is the unit — a timeout here names a PACKAGE, and the response
    names the first file that would not parse, so "which file" survives for the
    failure that actually needs it.

    Rejected alternative: keep per-file requests and stitch the graph on the
    Python side. That moves Go's name-resolution rules into Python — a second
    implementation of Go scoping, in the wrong language, maintained by nobody.
    """

    schema: str
    unit: GoUnit
    files: tuple[GoSourceFile, ...]


@dataclass(frozen=True)
class GoWireSymbol:
    """One declared callable as the helper reports it. ``main.go``'s ``Symbol``.

    ``kind`` is reportage only — ``"func"``, ``"method"``, ``"package_var"`` —
    and is never part of any comparison. A second comparison surface is a
    second thing to keep in agreement.
    """

    key: str
    path: str
    line: int
    kind: str


@dataclass(frozen=True)
class GoWireRoot:
    """One entrypoint as the helper reports it. ``main.go``'s ``Root``.

    ``kind`` is a wire string, mapped by :func:`entrypoint_kind_for_wire`. The
    helper does NOT report a :class:`RootKind`: that is derived by D5 from the
    entrypoint kind and from ``seal_verify.is_test_path``, and
    ``_validate_root`` refuses any row that asserts it instead.
    """

    symbol: str
    kind: str
    evidence: str


@dataclass(frozen=True)
class GoWireEdge:
    """One call or reference. ``main.go``'s ``Edge`` and its EDGE GRAMMAR."""

    caller: str
    callee: str
    kind: str
    site: str


@dataclass(frozen=True)
class GoWireHole:
    """One call site the helper could not name. ``main.go``'s ``Hole``.

    THE non-vacuity record of a response. It is the exact quantity that decides
    whether a "no path" answer is conclusive (``UndecidedReason.DYNAMIC_EDGE``),
    so a helper that reports zero of them over a real package is either
    extraordinarily good or not counting, and a decoder must not let those be
    the same value. ``detail`` is prose and no decision reads it.
    """

    caller: str
    site: str
    detail: str


@dataclass(frozen=True)
class GoWireParseError:
    """The FIRST file of the unit that go/parser refused, and its message.

    Exit 0: an unparseable file is a successful run of the helper and a fact
    about the file. ``go_signature_fingerprint``'s rule, unchanged.
    """

    path: str
    message: str


@dataclass(frozen=True)
class GoReachabilityResponse:
    """What the helper writes to stdout: exactly one JSON object, always.

    ``parse_error`` and the four arrays are mutually exclusive: a document
    carrying both, or neither, is
    :attr:`AnalyzerFault.HELPER_OUTPUT_INVALID`. When ``parse_error`` is absent
    all four arrays must be PRESENT, possibly empty — ``[]`` is an answer and a
    missing field is not, which is what lets the caller tell "this package
    declares nothing" from "the helper stopped emitting a field".

    ``import_path``
        **The one field that is not a function of the request.** It is the
        import path the GO TOOLCHAIN resolves for the unit's own directory —
        ``go list -e -find -f {{.ImportPath}} .`` — and it replaces the
        directory arithmetic :func:`_import_path_qualifiers` used to do. See
        that function for the three shapes the arithmetic got wrong and which
        of them this closes.

        It is NOT required by this decoder, and the omission is a CHOICE with a
        named alternative. Rejected: requiring it here, which is where the
        other required fields are checked. This function is handed one string
        and has never seen a helper; a document that omits the field is a
        document a TEST wrote, and refusing it here would make the decoder's
        contract about who produced the string rather than about what it says.
        The requirement lives at :func:`_analyzed_units`, which is the only
        layer that knows the string came from the helper — the same R1
        discriminator that puts rule 4's echo check and the whole-tree
        emptiness guard a layer up. Empty means "not stated".
    """

    schema: str
    unit: GoUnit
    import_path: str = ""
    symbols: tuple[GoWireSymbol, ...] = ()
    roots: tuple[GoWireRoot, ...] = ()
    edges: tuple[GoWireEdge, ...] = ()
    unresolved: tuple[GoWireHole, ...] = ()
    parse_error: GoWireParseError | None = None


def encode_go_reachability_request(
    unit: GoUnit, files: Sequence[GoSourceFile]
) -> str:
    """The JSON document for one package, ready for the helper's stdin.

    Contract, and it is ``encode_go_helper_request``'s with the shape changed
    and none of the reasoning: a single JSON object with exactly the fields of
    :class:`GoReachabilityRequest`, ``schema`` set to
    :data:`GO_REACHABILITY_SCHEMA`, UTF-8.

    Two properties a body must not lose, both inherited and both measured
    consequences of real failures:

      * ``ensure_ascii=True``, and it is not a style choice. ``source`` is
        whatever the read accepted, which can include lone surrogates from a
        blob that is not valid UTF-8; ``ensure_ascii=False`` raises on encoding
        those and turns a bad FILE into an environment fault.
      * deterministic separators, so two runs over one package produce one
        request byte for byte.

    ``source`` is passed through verbatim — BOM, CRLF, invalid UTF-8 included —
    because normalising here would make the Python and Go sides disagree about
    what the file says.

    Files are sent in the order the caller supplies them, and the caller sorts
    by path, because ``main.go`` contracts edge order as request order and a
    nondeterministic request makes the witness path a human is asked to check
    nondeterministic too.

    **Measured under** ``feat/D6-body``, 2026-08-11: ``ensure_ascii=True`` turns
    a lone surrogate — which ``discover_units`` produces, by ``surrogateescape``,
    from a source blob that is not valid UTF-8 — into a six-character escape and
    the whole document into ASCII; with ``ensure_ascii=False`` the same input
    raises ``UnicodeEncodeError`` on the way to the helper's stdin, which is a
    bad FILE becoming an environment fault.
    """
    document = {
        "schema": GO_REACHABILITY_SCHEMA,
        "unit": {
            "module_path": unit.module_path,
            "package_dir": unit.package_dir,
            "package_name": unit.package_name,
        },
        # The caller's order, kept: ``main.go`` contracts edge order as REQUEST
        # order, and an encoder that re-sorted would take that decision away
        # from the layer that owns it.
        "files": [{"path": file.path, "source": file.source} for file in files],
    }
    return json.dumps(document, ensure_ascii=True, separators=(",", ":"))


def decode_go_reachability_response(stdout: str) -> GoReachabilityResponse:
    """Parse the helper's stdout, or raise the named fault. STUB.

    **A THIRD DECODER, and the duplication is ruled rather than drifted into.**
    ``role_protocol._decode_helper_response`` is THE shared validator for the
    two signature helpers, extracted under a P4 ruling and forced by
    ``test_one_decoder_serves_both_languages_and_neither_is_a_copy``, because
    "the copy that forgets the duplicate-key check clears branches the original
    refuses — a divergence in the exact place where being wrong fails OPEN".
    That validator is shaped for a ``(symbol, fingerprint, kind)`` triple and a
    single ``symbols`` array; this document has four arrays, a nested unit and a
    structured parse error, so it cannot be served by four arguments. **The
    argument against a copy does not apply, because this is not a copy — no
    line of it is transferable. What DOES transfer is the obligation the
    extraction was protecting**, and it is written out below so it cannot be
    lost the way the extraction ruling says it would be.

    **THE DUPLICATE-KEY GUARD, and a correction to the brief this unit was
    given.** That brief records the sibling's duplicate-key guard as having been
    found UNCOVERED — "removing it left the suite green". **Measured under**
    ``feat/D6-go-analyzer`` @ ``0238aa2``, 2026-08-11, by replacing the
    ``if name in seen`` raise in ``role_protocol._decode_helper_response`` with a
    dead branch and running the whole suite: **2 failed, 2311 passed, 13
    skipped** — both failures are
    ``test_both_decoders_refuse_the_same_malformed_document_with_the_same_fault``
    at its ``a DUPLICATE symbol key`` parameter, once for ``go`` and once for
    ``ts``. The gap was real and D4's shared row closed it. It is written down
    here because the interesting fact is not that it is covered now: it is that
    a guard on this exact question went uncovered once already, in the module
    this one is modelled on.

    Raises :class:`AnalyzerUnavailable` with
    :attr:`AnalyzerFault.HELPER_OUTPUT_INVALID` for every way the document can
    be wrong. The list is EXHAUSTIVE and a seal should be total over it:

      1. stdout is empty or whitespace. "No symbols" and "no output" are not
         the same answer: the first describes one package and the second would
         describe every branch.
      2. stdout is not JSON, or is a JSON value that is not an object.
      3. ``schema`` is absent or is not :data:`GO_REACHABILITY_SCHEMA`.
         Checked before anything else is read.
      4. ``unit`` is absent, is not an object, or does not echo the unit that
         was requested. A response for a package nobody asked about would
         attach one package's edges to another package's symbols.
      5. ``parse_error`` and the arrays are both present, or both absent.
      6. ``parse_error`` is present but is not an object with a non-empty
         ``path`` and ``message``.
      7. any of ``symbols``, ``roots``, ``edges``, ``unresolved`` is absent or
         is not a list, when ``parse_error`` is absent. An empty LIST is the
         answer for a package that declares nothing; a missing one is not an
         answer at all — and requiring all four is what makes rule 12's
         ignore-unknown-fields ruling safe.
      8. any record is not an object, or carries a field of the wrong type, or
         a ``key`` / ``symbol`` / ``caller`` / ``callee`` / ``site`` that is not
         a non-empty string, or a ``line`` that is not a positive integer.
      9. **``symbols`` repeats a ``key``.** Sharper here than in the sibling:
         D5's :class:`Symbol` declares ``path`` and ``line`` as
         ``field(compare=False)``, so identity is over ``key`` alone and two
         records with one key are ONE symbol whose ``path`` is decided by dict
         insertion order — and ``path`` is what ``seal_verify.is_test_path``
         reads to decide whether a symbol is excluded from a subject set and
         whether a root is TEST or PRODUCTION. A duplicate key can turn a
         BREACH into an exclusion.
     10. ``roots`` repeats a ``symbol``, or names a symbol ``symbols`` does not
         declare. A root the graph does not declare has no outgoing edges and
         would contribute silently nothing.
     11. any ``kind`` string is not a member of the wire vocabularies; see
         :func:`edge_kind_for_wire` and :func:`entrypoint_kind_for_wire`, which
         raise rather than defaulting.
     12. an ``edges`` or ``unresolved`` record naming a ``caller`` that
         ``symbols`` does not declare. An edge from nowhere is not an edge.

    **Not on the list. Each omission is a CHOICE and each names what it
    rejected:**

      * CHOICE — **Unknown FIELDS are ignored, at every level.** ``schema`` is checked
        for equality first, so an unknown field can only arrive from a document
        that has already lied about its version, and a second refusal for a
        state the first check owns is a second answer site. Rejected
        alternative: refusing unknown fields, which reads as strictness and
        buys only one thing the version check does not — catching a field
        RENAMED without a schema bump — and rule 7 already catches that as a
        missing required array. Ignoring is also the sibling decoder's live
        behaviour, so the two protocols do not disagree about a document
        neither should ever see.
      * CHOICE — **Duplicate EDGES are DEDUPLICATED, not refused.** Rejected
        alternative: refusing them as rule 9 refuses a duplicate key, which is
        the consistent-looking answer. ``f(f(x))`` is
        ordinary Go and emits two identical ``(caller, callee, kind, site)``
        tuples; refusing them would blame the machine for a legal program,
        which is the lesson ``go_signature_fingerprint``'s ``isBlank`` records
        after ``stringer`` output produced duplicate keys across GOROOT. A
        duplicate edge is the same answer twice, not two answers, and
        reachability is a set property, so the dedup cannot move a verdict.
      * CHOICE — **An EMPTY graph for one unit is an answer, not a fault.**
        Rejected alternative: faulting here on any empty response, which is what
        D5's ``HELPER_OUTPUT_INVALID`` wording reads like in isolation and which
        would fault on a file holding only a package clause and imports. A file
        declaring only a package clause and imports declares nothing. The
        whole-tree guard D5's :attr:`AnalyzerFault.HELPER_OUTPUT_INVALID`
        demands — "including an EMPTY graph where a graph was expected" —
        belongs at :meth:`GoReachabilityAnalyzer.graph`, which is the layer
        that knows how many Go files the sweep found; see there. Placing it
        here would be a claim about a population this function cannot see,
        which is R1's discriminator exactly.

    Does NOT decide anything about the analysis: a document carrying
    ``parse_error`` is returned intact, and it is the analyzer that turns it
    into an entry in :attr:`CallGraph.unreadable_paths`. One place per decision.

    Rule 4's "does not echo the unit that was requested" half is NOT checked
    here and its absence is deliberate: this function is handed one string and
    has never seen the request. :meth:`GoReachabilityAnalyzer.graph` holds the
    two together and checks it there, which is the same R1 discriminator that
    puts the emptiness guard a layer up.
    """
    if not isinstance(stdout, str) or not stdout.strip():
        raise _output_invalid(
            "the helper wrote nothing to stdout. 'No symbols' and 'no output' "
            "are not the same answer: the first describes one package and the "
            "second would describe every branch"
        )
    try:
        document = json.loads(stdout)
    except ValueError as exc:
        raise _output_invalid(
            f"the helper's stdout is not well-formed JSON: {exc}"
        ) from exc
    if not isinstance(document, dict):
        raise _output_invalid(
            f"the helper's stdout is a JSON {type(document).__name__} and not "
            "an object; one response document, always"
        )

    # RULE 3, and it is checked BEFORE anything else is read. The
    # ignore-unknown-fields CHOICE rests on exactly this order: an unknown
    # field can only arrive from a document that has already lied about its
    # version.
    schema = document.get("schema")
    if schema != GO_REACHABILITY_SCHEMA:
        raise _output_invalid(
            f"the response schema is {schema!r} and not "
            f"{GO_REACHABILITY_SCHEMA!r}; a helper and a caller that disagree "
            "about the edge grammar would compute reachability over graphs "
            "that mean different things"
        )

    unit = _decode_unit(document.get("unit"))

    # RULE 5, under D3's reading: ``null`` is ABSENT and ``[]`` is
    # PRESENT-and-empty. Every parse_error document the helper can produce
    # carries the four arrays as ``null`` — Go's encoding/json writes a nil
    # slice that way and ``,omitempty`` is refused because it writes ``{}`` for
    # an empty slice too — so a decoder that read ``null`` as present would
    # refuse every one of them.
    parse_error = document.get("parse_error")
    arrays = {name: document.get(name) for name in _RESPONSE_ARRAYS}
    present = [name for name, value in arrays.items() if value is not None]
    if parse_error is not None and present:
        raise _output_invalid(
            f"the response carries parse_error AND {present}; they are "
            "mutually exclusive, and half of a graph is the silent partial"
        )
    if parse_error is None and not present:
        raise _output_invalid(
            "the response carries neither parse_error nor any of the four "
            f"arrays {list(_RESPONSE_ARRAYS)}; a document that answers nothing "
            "is not an answer"
        )

    if parse_error is not None:
        if not isinstance(parse_error, dict):
            raise _output_invalid(
                f"parse_error is a {type(parse_error).__name__} and not an "
                "object naming the file that would not parse"
            )
        return GoReachabilityResponse(
            schema=schema,
            unit=unit,
            parse_error=GoWireParseError(
                path=_wire_text(parse_error, "path", where="parse_error"),
                message=_wire_text(parse_error, "message", where="parse_error"),
            ),
        )

    # RULE 7. All four, PRESENT and a list. An empty list is the answer for a
    # package that declares nothing; a missing one is not an answer at all —
    # and requiring all four is what makes the ignore-unknown-fields ruling
    # safe, because a field renamed without a schema bump lands here.
    missing = [name for name in _RESPONSE_ARRAYS if arrays[name] is None]
    if missing:
        raise _output_invalid(
            f"the response is missing the required array(s) {missing}; `[]` is "
            "an answer and a missing field is not"
        )
    not_a_list = [
        name for name in _RESPONSE_ARRAYS if not isinstance(arrays[name], list)
    ]
    if not_a_list:
        raise _output_invalid(
            f"the response field(s) {not_a_list} are present and are not lists"
        )

    symbols: list[GoWireSymbol] = []
    declared: set[str] = set()
    for record in arrays["symbols"]:
        _require_object(record, "symbols")
        key = _wire_text(record, "key", where="symbols")
        # RULE 9, and it is sharper here than in the sibling: D5's Symbol
        # declares path and line as field(compare=False), so identity is over
        # key ALONE and two records with one key are ONE symbol whose path is
        # decided by dict insertion order — and path is what is_test_path reads
        # to decide whether a symbol is excluded from a subject set. A
        # duplicate key can turn a BREACH into an exclusion.
        if key in declared:
            raise _output_invalid(
                f"symbols repeats the key {key!r}; two records with one key are "
                "one symbol wearing two declarations, and which path wins is "
                "decided by insertion order"
            )
        declared.add(key)
        symbols.append(
            GoWireSymbol(
                key=key,
                path=_wire_text(record, "path", where="symbols"),
                line=_wire_line(record, where="symbols"),
                kind=_wire_reportage(record, "kind", where="symbols"),
            )
        )

    roots: list[GoWireRoot] = []
    entered: set[str] = set()
    for record in arrays["roots"]:
        _require_object(record, "roots")
        symbol = _wire_text(record, "symbol", where="roots")
        # RULE 11 — the vocabulary raises rather than defaulting.
        entrypoint_kind_for_wire(record.get("kind"))
        if symbol in entered:
            raise _output_invalid(
                f"roots repeats the symbol {symbol!r}"
            )
        # RULE 10. A root the graph does not declare has no outgoing edges and
        # would contribute silently nothing.
        if symbol not in declared:
            raise _output_invalid(
                f"root {symbol!r} names a symbol the response does not declare"
            )
        entered.add(symbol)
        roots.append(
            GoWireRoot(
                symbol=symbol,
                kind=record["kind"],
                evidence=_wire_reportage(record, "evidence", where="roots"),
            )
        )

    edges: list[GoWireEdge] = []
    seen_edges: set[tuple[str, str, str, str]] = set()
    for record in arrays["edges"]:
        _require_object(record, "edges")
        caller = _wire_text(record, "caller", where="edges")
        callee = _wire_text(record, "callee", where="edges")
        edge_kind_for_wire(record.get("kind"))  # RULE 11
        site = _wire_text(record, "site", where="edges")
        _require_declared(caller, declared, "edges")  # RULE 12
        # CHOICE, kept: duplicate EDGES are DEDUPLICATED and never refused.
        # ``f(f(x))`` is ordinary Go and emits two identical tuples; refusing
        # them would blame the machine for a legal program. A duplicate edge is
        # the same answer twice, and reachability is a set property, so the
        # dedup cannot move a verdict.
        signature = (caller, callee, record["kind"], site)
        if signature in seen_edges:
            continue
        seen_edges.add(signature)
        edges.append(
            GoWireEdge(caller=caller, callee=callee, kind=record["kind"], site=site)
        )

    holes: list[GoWireHole] = []
    for record in arrays["unresolved"]:
        _require_object(record, "unresolved")
        caller = _wire_text(record, "caller", where="unresolved")
        _require_declared(caller, declared, "unresolved")  # RULE 12
        holes.append(
            GoWireHole(
                caller=caller,
                site=_wire_text(record, "site", where="unresolved"),
                detail=_wire_reportage(record, "detail", where="unresolved"),
            )
        )

    # Typed but not required, and empty means "not stated" — see the field's
    # note on :class:`GoReachabilityResponse`. A wrongly TYPED field is still a
    # malformed document, which is rule 8's shape.
    import_path = document.get("import_path", "")
    if not isinstance(import_path, str):
        raise _output_invalid(
            f"the response 'import_path' is {import_path!r} and not a string"
        )

    return GoReachabilityResponse(
        schema=schema,
        unit=unit,
        import_path=import_path,
        symbols=tuple(symbols),
        roots=tuple(roots),
        edges=tuple(edges),
        unresolved=tuple(holes),
    )


#: The four arrays a graph document must carry, named once so that rule 5, rule
#: 7 and the ``null``-is-absent reading cannot come to disagree about which four
#: they are.
_RESPONSE_ARRAYS = ("symbols", "roots", "edges", "unresolved")


def _output_invalid(message: str) -> AnalyzerUnavailable:
    """Every way a document can be wrong, under ONE fault.

    Never :attr:`AnalyzerFault.HELPER_FAILED`, which blames the process for a
    document the process delivered successfully.
    """
    return AnalyzerUnavailable(AnalyzerFault.HELPER_OUTPUT_INVALID, message)


def _decode_unit(raw: object) -> GoUnit:
    """RULE 4's decodable half: ``unit`` is an object of three strings."""
    if not isinstance(raw, dict):
        raise _output_invalid(
            f"the response unit is {raw!r} and not an object; a response for a "
            "package nobody asked about would attach one package's edges to "
            "another package's symbols"
        )
    values = {}
    for field in ("module_path", "package_dir", "package_name"):
        value = raw.get(field)
        if not isinstance(value, str):
            raise _output_invalid(
                f"the response unit's {field!r} is {value!r} and not a string"
            )
        values[field] = value
    return GoUnit(**values)


def _require_object(record: object, where: str) -> None:
    if not isinstance(record, dict):
        raise _output_invalid(
            f"{where} carries {record!r}, which is not an object"
        )


def _wire_text(record: Mapping[str, object], field: str, *, where: str) -> str:
    value = record.get(field)
    if not isinstance(value, str) or not value:
        raise _output_invalid(
            f"{where}: {field!r} is {value!r} and not a non-empty string"
        )
    return value


def _wire_reportage(record: Mapping[str, object], field: str, *, where: str) -> str:
    """A string nothing compares: ``kind`` on a symbol, ``evidence``, ``detail``.

    Typed but not required to be non-empty, because a second comparison surface
    is a second thing to keep in agreement and these three are not one.
    """
    value = record.get(field)
    if not isinstance(value, str):
        raise _output_invalid(
            f"{where}: {field!r} is {value!r} and not a string"
        )
    return value


def _wire_line(record: Mapping[str, object], *, where: str) -> int:
    value = record.get("line")
    # ``isinstance(True, int)`` is True in Python, and a bool here would put a
    # finding at line 1 of a file nobody wrote.
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise _output_invalid(
            f"{where}: 'line' is {value!r} and not a positive integer"
        )
    return value


def _require_declared(caller: str, declared: set[str], where: str) -> None:
    if caller not in declared:
        raise _output_invalid(
            f"{where} names the caller {caller!r}, which the response does not "
            "declare; an edge from nowhere is not an edge"
        )


# --------------------------------------------------------------------------- #
# Part 3 — the spellings: keys, kinds and test names
# --------------------------------------------------------------------------- #


#: Spelled as a package-qualifier separator and as a receiver bracket pair,
#: never assembled inline, so that the ONE definition of a key lives in
#: :func:`go_symbol_key` and a body cannot grow a second one three lines away.
_KEY_PACKAGE_SEPARATOR = "."

#: The suffix that spells the synthetic symbol a ``GO_PACKAGE_VAR`` root enters
#: at, on :class:`Symbol`'s own recorded convention for synthetic roots: it is
#: spelled with characters no Go declaration can produce, so it cannot collide
#: with a real symbol.
GO_PACKAGE_VAR_SYMBOL = "<vars>"

#: The SECOND synthetic package-var initialiser: the one whose declarations are
#: compiled into the TEST binary. One per (package, binary) and not one per
#: package, because a single symbol standing for both carries a single ``path``
#: — and ``path`` is what ``seal_verify.is_test_path`` reads to decide whether
#: the root survives at all, so a per-package symbol made the verdict a function
#: of which contributing file sorted first. See ``main.go``'s
#: ``declarePackageVar`` for the two measured trees that flipped.
#:
#: It deliberately does not END in :data:`GO_PACKAGE_VAR_SYMBOL`, so that a
#: reader asking "is this the production initialiser" by suffix is not answered
#: "yes" for the test one.
GO_PACKAGE_VAR_TEST_SYMBOL = "<vars:test>"

#: Likewise for the several ``func init()`` one package may legally declare.
#: The spec permits them explicitly and real code uses them (GOROOT's
#: ``runtime/proc.go`` and ``cmd/go/main.go`` both do, measured by the sibling
#: on GOROOT/src 2026-08-09: 11 files of 4,505), so ``init`` alone is not a
#: key — it is a duplicate key waiting to happen, which is rule 9's fault. The
#: ordinal is the file's index in the request, then the declaration's index in
#: the file, which is deterministic because the request order is.
GO_INIT_SYMBOL_TEMPLATE = "<init:{ordinal}>"


#: The suffix Go's spec fixes for the one package that may share a directory
#: with another. It is the ONLY way two packages can occupy one directory, which
#: is what makes :func:`go_symbol_key`'s disambiguation total rather than a
#: heuristic.
_EXTERNAL_TEST_PACKAGE_SUFFIX = "_test"


def go_symbol_key(
    module_path: str,
    package_dir: str,
    package_name: str,
    receiver: str | None,
    name: str,
) -> str:
    """The one spelling of a Go symbol key. Both sides must agree byte for byte.

    **The second function this scaffold implements rather than stubs, and the
    reason is D4's for** ``ts_symbol_key``: *a seal cannot express the
    key-collision property without calling it.* Here the collision is not
    hypothetical and it is not in a fixture.

    **Measured under** ``feat/G2-adj`` @ ``83b0b97``, 2026-08-11: seven modules
    in the acceptance repository declare ``package main``, and ``cmd/gates`` and
    ``cmd/iterate`` each declare a top-level ``func VerifyPreservation`` with
    an identical signature. A key spelled ``main.VerifyPreservation`` collides
    across them — and under D5's :class:`Symbol`, whose ``path`` and ``line``
    are ``field(compare=False)``, a collision is not a near-miss: it is one
    symbol wearing two declarations, in a mechanism that decides "is this
    reached" by set membership on the key. The eight findings the two subjects
    owe would become four, over a symbol that is in two files at once.

    THE SPELLING::

        <qualifier>.Name          a top-level func
        <qualifier>.(*T).Name     a method, pointer receiver
        <qualifier>.(T).Name      a method, value receiver
        <qualifier>.<vars>        the package-var initialiser, PRODUCTION binary
        <qualifier>.<vars:test>   the same, for the TEST binary
        <qualifier>.<init:N>      the Nth `func init()`

    where ``<qualifier>`` is ``<module_path>/<package_dir>``, plus
    ``[<package_name>]`` when ``package_name`` ends in ``_test``.

    ``package_dir`` keeps any leading directories the module path already
    accounts for — they are NOT stripped. The qualifier is a LABEL that must be
    unique and legible, never an import path to be resolved; stripping would
    require knowing where the module root sits relative to the tree, which is a
    second fact to keep in agreement with the first. It is verbose
    (``github.com/yourorg/claude-workflow/gates/cmd/gates.VerifyPreservation``)
    and verbose is the cheap failure here.

    **``package_name`` is a parameter because a directory can hold TWO
    packages, and without it this function had a collision of its own.** Go's
    spec permits exactly one such pair — ``foo`` and its external test package
    ``foo_test`` — so an ``_test`` suffix on the package clause is a total
    discriminator rather than a heuristic, and it is applied to the QUALIFIER
    rather than to the member so that the two packages' symbol sets can never
    interleave. This scaffold's first draft omitted the parameter; it is
    recorded rather than quietly fixed, because it is the same defect the
    function exists to prevent, one level in: a key that is unique over the
    inputs somebody happened to think of.

    CHOICE (the sibling makes the opposite call and the divergence must not
    read as an accident): **pointer and value receivers get DIFFERENT keys.**
    Rejected alternative: stripping ``*`` as ``receiverBaseName`` does, which
    would keep the two units' keys interchangeable and is wrong here for the
    reason below. It is the opposite of
    ``go_signature_fingerprint``'s ``receiverBaseName``, whose whole job is to
    strip ``*`` so that changing a receiver's pointer-ness reads as one symbol
    changing rather than two swapping. The two units want opposite things and
    the divergence is deliberate: a signature comparison asks "did this contract
    change", for which one key is right; a call graph asks "does execution
    arrive here", for which ``func (T) M`` and ``func (*T) M`` are two bodies —
    and Go forbids declaring both, so the keys cannot collide by accident.

    Pure, total, and it never looks at the filesystem. ``receiver`` is the
    receiver type EXACTLY as written after any parentheses are dropped
    (``*Config``, ``Config``, ``*Set[T]``), and ``None`` for a non-method.
    """
    qualifier = f"{module_path}/{package_dir}" if package_dir else module_path
    if package_name.endswith(_EXTERNAL_TEST_PACKAGE_SUFFIX):
        qualifier = f"{qualifier}[{package_name}]"
    if receiver is None:
        member = name
    else:
        member = f"({receiver}).{name}"
    return f"{qualifier}{_KEY_PACKAGE_SEPARATOR}{member}"


#: The prefixes ``go test`` recognises, exactly. Not a guess: ``testing``'s own
#: documented set, and the ordering is irrelevant because a name has at most one
#: of them.
_GO_TEST_PREFIXES = ("Test", "Benchmark", "Fuzz", "Example")


def go_test_root_predicate(name: str) -> bool:
    """Is this symbol name a Go test entrypoint? Go's own rule, not a guess.

    **The third function this scaffold implements rather than stubs.** It is the
    per-language half of the one question D5 refuses to answer twice — the FILE
    half is ``seal_verify.is_test_path`` and this module does not re-ask it —
    and it decides whether a root is TEST or PRODUCTION. Both wrong answers are
    intolerable in the way D5's :class:`RootKind` describes: a test root read as
    production silently certifies everything below it, and a production root
    read as test floods the report with false BREACHes. A seal author handed a
    stub here would be sealing their own guess at Go's rule.

    THE RULE, which is ``cmd/go``'s ``isTest``: the name begins with one of
    ``Test``, ``Benchmark``, ``Fuzz`` or ``Example``, and the rune immediately
    after the prefix is **not a lower-case letter**. So ``TestFoo`` and a bare
    ``Test`` are test entrypoints and ``Testify`` is not — which is the whole
    reason the rule is a rune check and not ``startswith``.

    ``TestMain`` satisfies it and that is correct rather than a corner: it IS an
    entrypoint, it is the one ``go test`` calls first, and everything it reaches
    is genuinely reached under test.

    ``name`` is the symbol's own last segment, never the key — a key carries a
    module path, and a module whose name began with ``Test`` would otherwise
    make every symbol in it a test root.

    Predicted (unmeasured) under ``feat/G2-adj`` @ ``83b0b97``: this accepts all
    twelve ``TestSeal_G1_…`` names in ``cmd/gates/preserve_seal_test.go`` and
    all of the ``TestSeal_G2_…`` names in ``cmd/iterate``'s, which is what makes
    the acceptance fixture's seals seals. The FILE half is measured above; this
    half is a rule, and a seal can pin it against both.
    """
    for prefix in _GO_TEST_PREFIXES:
        if not name.startswith(prefix):
            continue
        rest = name[len(prefix) :]
        if not rest:
            return True
        return not rest[0].islower()
    return False


#: The wire ``kind`` vocabulary for edges, as a TABLE and not a chain of
#: ``if``\ s, so that a string added to ``main.go``'s grammar without visiting
#: this file is absent from it and :func:`edge_kind_for_wire` raises rather than
#: defaulting. A default on this dispatch decides, silently and for the whole
#: repository, whether an unmarked over-approximation reads as the strong pass —
#: which is D5's own argument for ``_RESOLVED_EDGE_KINDS`` being two tables.
_EDGE_KIND_BY_WIRE: Mapping[str, EdgeKind] = {
    "direct": EdgeKind.DIRECT,
    "method": EdgeKind.METHOD,
    "interface": EdgeKind.INTERFACE,
    "reference": EdgeKind.REFERENCE,
}


def edge_kind_for_wire(value: str) -> EdgeKind:
    """One wire string to one :class:`EdgeKind`, raising on anything else.

    **The fourth function this scaffold implements rather than stubs**, with
    :func:`entrypoint_kind_for_wire`, and for one reason: these two tables ARE
    the Go-side answer to "how does a Go shape map onto D5's vocabulary", which
    is the second question this unit was asked. A mapping left as prose is a
    mapping two authors will spell differently, and a body written against the
    wrong one is wrong everywhere at once.

    THE MAPPING, and which cases force
    :attr:`PathQuality.OVER_APPROXIMATED` — the grammar is stated once, in
    ``main.go``, and this is its Python face:

      ``direct``
        a call by name to exactly one declaration: ``f(x)`` where ``f`` is
        declared in the package, or ``pkg.F(x)`` where ``pkg`` is an import
        alias. Resolved. Does NOT force over-approximation.
      ``method``
        a call on a receiver whose declared type is readable from the text —
        a parameter ``x T``, a ``var x T``, a ``x := T{…}`` — resolved to
        exactly one declaration. Resolved. Does NOT force over-approximation. It
        is a separate kind from ``direct`` anyway, on :class:`EdgeKind`'s own
        reasoning: a stdlib-only walk resolves these less often than a
        type-checked one would, and a report must be able to say which
        resolution it was leaning on.
      ``interface``
        a call through an interface-typed value, or through any receiver the
        name-level walk could not resolve, emitted as ONE EDGE PER in-tree
        method of that name. **FORCES** :attr:`PathQuality.OVER_APPROXIMATED`.
      ``reference``
        the symbol mentioned as a VALUE and not called — assigned, passed
        (``sort.Slice(xs, less)``), stored in a table, a method value ``x.M``,
        a method expression ``T.M``. **FORCES**
        :attr:`PathQuality.OVER_APPROXIMATED`.

    **Interface SATISFACTION is not on this table, and its absence is the
    answer rather than an omission.** Go's satisfaction is implicit and
    structural; a type declaring an interface's methods produces no edge, and
    ``var _ I = (*T)(nil)`` produces none either because it names no method.
    What produces edges is a CALL through an interface-typed value, and the only
    honest name-level resolution of it is the over-approximating one above.
    Method promotion through an embedded field lands in the same place, for the
    same reason: whether an embed promotes is what decides which interfaces a
    type satisfies — the fact ``go_signature_fingerprint``'s v2 grammar moved
    its ``embedded:`` marker to protect — and it is not decidable at name level.

    A call the walk cannot name at all is NOT on this table and must never be
    added to it. It is not an edge; it is a hole, it travels as a
    :class:`GoWireHole`, and its consequence is
    :attr:`UndecidedReason.DYNAMIC_EDGE`. Naming it a fifth kind invites a body
    to treat the absence of a target as a target.
    """
    kind = _EDGE_KIND_BY_WIRE.get(value)
    if kind is None:
        raise AnalyzerUnavailable(
            AnalyzerFault.HELPER_OUTPUT_INVALID,
            f"edge kind {value!r} is not in the wire vocabulary "
            f"{sorted(_EDGE_KIND_BY_WIRE)}; a kind this table does not name "
            "would decide by default whether an over-approximated path is "
            "spelled like a resolved one",
        )
    return kind


#: The wire ``kind`` vocabulary for roots. Four members and no more: the three
#: Go production kinds :class:`EntrypointKind` names, plus the shared
#: ``TEST_FUNCTION``. Every other member of that enum is Python's and a Go row
#: that emitted one would be claiming a start it cannot derive.
_ENTRYPOINT_KIND_BY_WIRE: Mapping[str, EntrypointKind] = {
    "go_main": EntrypointKind.GO_MAIN,
    "go_init": EntrypointKind.GO_INIT,
    "go_package_var": EntrypointKind.GO_PACKAGE_VAR,
    "test_function": EntrypointKind.TEST_FUNCTION,
}


def entrypoint_kind_for_wire(value: str) -> EntrypointKind:
    """One wire string to one :class:`EntrypointKind`, raising on anything else.

    **The fifth function this scaffold implements rather than stubs**; see
    :func:`edge_kind_for_wire` for the shared reason.

    The four, exhaustively, and each names what it is DERIVED from — a kind
    whose derivation cannot be written is a kind that does not go in the enum:

      ``go_main``
        ``func main()`` in a file declaring ``package main``. **Measured
        under** ``feat/G2-adj`` @ ``83b0b97``: seven of them, one per ``cmd/``
        module.
      ``go_init``
        ``func init()`` in any package. Go runs every one before ``main``.
        D5's contract records "zero instances in ``cmd/classify`` today,
        measured 2026-08-10", and says the member is written on the LANGUAGE's
        semantics rather than on an instance. **That is no longer the state of
        the tree: measured under** ``feat/G2-adj`` @ ``83b0b97``,
        ``cmd/classify/capability.go`` declares one. The member now has a live
        example and the reasoning that admitted it without one is unaffected.
      ``go_package_var``
        a package-level ``var x = <expression>``, which runs before ``init``.
        The symbol is synthetic (:data:`GO_PACKAGE_VAR_SYMBOL`).
      ``test_function``
        a func in a file ``seal_verify.is_test_path`` calls a test, whose name
        :func:`go_test_root_predicate` accepts. **The row supplies the naming
        half only**; the file half is the shared matcher and D5 does not open a
        second one.

    There is no ``PUBLIC_API`` member and there must not be one. D5's CHOICE is
    decisive and it is measured against this unit's own fixture: a rule that
    made an exported symbol a root would make ``VerifyPreservation`` — exported,
    in both modules — a root, so the mechanism built to catch this defect would
    certify it as REACHED on its first run.
    """
    kind = _ENTRYPOINT_KIND_BY_WIRE.get(value)
    if kind is None:
        raise AnalyzerUnavailable(
            AnalyzerFault.HELPER_OUTPUT_INVALID,
            f"entrypoint kind {value!r} is not in the wire vocabulary "
            f"{sorted(_ENTRYPOINT_KIND_BY_WIRE)}; a root whose kind this "
            "module cannot classify is not a root, and skipping it would make "
            "everything below it a false BREACH",
        )
    return kind


# --------------------------------------------------------------------------- #
# Part 4 — sweeping the tree into units
# --------------------------------------------------------------------------- #


def discover_units(tree: Path) -> tuple[tuple[GoUnit, tuple[GoSourceFile, ...]], ...]:
    """Every Go package in ``tree``, with its files. STUB.

    The sweep this row owns, and the one place it decides what to send the
    helper. Obligations, each of which a seal can pin:

      * **A file is Go because** ``role_protocol.support_for_path`` **says so**,
        and by no other test. This module holds no file-extension literal and
        matches no path against a suffix; there is exactly one place in this
        codebase that decides what language a file is, and a second extension
        table would drift silently, on files neither gate had been pointed at
        yet. (The module's one ``endswith`` is over a package clause, not a
        path; see the CHOICE in the module docstring.)
      * **One unit per (directory, package clause) pair**, not per directory:
        ``package foo_test`` beside ``package foo`` is two packages by the
        language's rules and merging them would put two unqualified-identifier
        scopes in one resolution pass.
      * **A package's ``_test.go`` files are IN its unit.** The seals whose
        subjects this mechanism judges live there, and a seal the graph does not
        declare makes :func:`discover_seals` raise.
      * **``module_path`` is read from the nearest enclosing ``go.mod``.** Seven
        of them in the acceptance repository, none at the root, so "the nearest
        enclosing" is the rule and "the repository's" is not. A directory with
        no enclosing ``go.mod`` is not a unit and is recorded, never guessed at:
        a synthesised module path is a key nobody can join to anything.
      * **Deterministic order**, files sorted by path within a unit and units
        sorted by ``(package_dir, package_name)``, because ``main.go``
        contracts edge order as request order.
      * **Never write into ``tree``.** The analyzer reads.

    CHOICE (whether the sweep skips vendored or generated trees): **it does
    not.** Rejected alternative: skipping ``vendor/``, ``testdata/`` and
    generated files, which is what every other Go tool does and which is
    tempting because their edges are noise. It is out because a skip is a hole
    of the shape this mechanism exists to refuse — an edge that exists and was
    not looked for is indistinguishable from an edge that does not exist — and
    because the direction of the error is the permissive one: a production call
    site living in a generated file would read as absent, which manufactures a
    BREACH. D5's limit 7 already records generated call sites as counting, and
    this keeps the two consistent. What would change it: a measured case where
    a vendored tree's edges made a real BREACH invisible.

    RECORDED, not silent: a Go file with no enclosing module manifest inside
    ``tree`` is not a unit and is skipped. There is no channel on this signature
    to return it, so it is named here — a synthesised module path is a key
    nobody can join to anything, and every decision in D5 is set membership on
    that key. A file whose package clause cannot be read is NOT skipped: it goes
    to a unit with an empty package name, where ``go/parser`` refuses it and the
    whole tree abstains, which is the direction the CHOICE above rules for.
    """
    root = Path(tree)
    grouped: dict[tuple[str, str, str], list[GoSourceFile]] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        # THE one place in this codebase that decides what language a file is.
        # A second extension table would drift silently, on files neither gate
        # had been pointed at yet.
        support = support_for_path(relative)
        if support is None or support.language is not Language.GO:
            continue
        module_path = _nearest_module_path(root, path.parent)
        if module_path is None:
            continue
        # surrogateescape, deliberately: source travels VERBATIM and a blob that
        # is not valid UTF-8 is a fact about the branch. The encoder's
        # ensure_ascii is what keeps it from becoming an environment fault.
        source = path.read_text(encoding="utf-8", errors="surrogateescape")
        package_dir = path.parent.relative_to(root).as_posix()
        if package_dir == ".":
            package_dir = ""
        key = (module_path, package_dir, _go_package_clause(source))
        grouped.setdefault(key, []).append(
            GoSourceFile(path=relative, source=source)
        )
    units: list[tuple[GoUnit, tuple[GoSourceFile, ...]]] = []
    for module_path, package_dir, package_name in sorted(
        grouped, key=lambda key: (key[1], key[2], key[0])
    ):
        files = grouped[(module_path, package_dir, package_name)]
        units.append(
            (
                GoUnit(
                    module_path=module_path,
                    package_dir=package_dir,
                    package_name=package_name,
                ),
                tuple(sorted(files, key=lambda file: file.path)),
            )
        )
    return tuple(units)


#: The manifest that fixes a directory's module path. It is taken from
#: :data:`GO_REACHABILITY_HELPER_ENTRY_POINTS` rather than written a second
#: time, because this module is permitted exactly the two filename literals that
#: tuple holds and a third would be a second place where a filename is written
#: down — which is what
#: ``test_this_module_asks_role_protocol_what_a_go_file_is_and_never_matches_one``
#: enforces. The tuple is ordered (program, manifest) and a seal pins it
#: verbatim, so the index is exactly as stable as the two names are.
_GO_MODULE_MANIFEST = GO_REACHABILITY_HELPER_ENTRY_POINTS[-1]

#: ``module <path>`` on a line of its own, the manifest's one required directive.
_MODULE_DIRECTIVE = re.compile(r"^\s*module\s+(\S+)\s*$", re.MULTILINE)

#: ``go <major>.<minor>``, read to refuse a toolchain older than the helper.
_GO_DIRECTIVE = re.compile(r"^\s*go\s+(\d+)\.(\d+)", re.MULTILINE)

#: The package clause, matched at a position the scanner has already advanced
#: past every comment to reach.
_PACKAGE_CLAUSE = re.compile(r"package\s+([A-Za-z_][A-Za-z0-9_]*)")


def _nearest_module_dir(root: Path, directory: Path) -> Path | None:
    """The nearest enclosing directory holding a module manifest, or None.

    NEAREST and not outermost. Seven manifests in the acceptance repository,
    none at its root, and the outermost reading would give two directories one
    module — inviting exactly the key collision the qualifier exists to prevent.
    The search stops at ``root``: the tree is the boundary of what is judged.
    """
    current = directory
    while True:
        if (current / _GO_MODULE_MANIFEST).is_file():
            return current
        if current == root:
            return None
        parent = current.parent
        if parent == current:
            return None
        current = parent


def _nearest_module_path(root: Path, directory: Path) -> str | None:
    module_dir = _nearest_module_dir(root, directory)
    if module_dir is None:
        return None
    text = (module_dir / _GO_MODULE_MANIFEST).read_text(
        encoding="utf-8", errors="surrogateescape"
    )
    match = _MODULE_DIRECTIVE.search(_strip_line_comments(text))
    return match.group(1) if match else None


def _strip_line_comments(text: str) -> str:
    return "\n".join(line.split("//", 1)[0] for line in text.splitlines())


def _go_package_clause(source: str) -> str:
    """The ``package`` clause, or ``""`` when the file has none.

    A scanner rather than a regex over the whole text: Go's package clause is
    the first non-comment token, and a doc comment above it may legally carry
    the word ``package`` at the start of a line — which a line-anchored regex
    would read as the clause.
    """
    index = 0
    length = len(source)
    while index < length:
        if source[index].isspace():
            index += 1
            continue
        if source.startswith("//", index):
            end = source.find("\n", index)
            index = length if end < 0 else end + 1
            continue
        if source.startswith("/*", index):
            end = source.find("*/", index + 2)
            index = length if end < 0 else end + 2
            continue
        match = _PACKAGE_CLAUSE.match(source, index)
        return match.group(1) if match else ""
    return ""


def _build_go_reachability_helper() -> Path:
    """Resolve, probe and compile the helper once. Returns the binary. STUB.

    Total: every failure leaves here as an :class:`AnalyzerUnavailable` carrying
    the named fault, in the order :meth:`GoReachabilityAnalyzer.graph`
    documents — HELPER_MISSING (:func:`go_reachability_helper_dir`), then
    TOOLCHAIN_MISSING (no ``go`` on PATH), then TOOLCHAIN_UNUSABLE (on PATH and
    not answering: a failing version probe, a version older than the module's
    language version, a ``GOCACHE``/``HOME`` the process cannot write), then
    HELPER_TIMEOUT or HELPER_FAILED from the build itself.

    **THE BINARY IS NOT TRACKED IN GIT, AND THIS FUNCTION IS THE
    RECOMMENDATION.** It is built into a fresh ``mkdtemp`` workspace, once per
    PROCESS, cached in memory as ``(binary, None)`` or ``(None, fault)``, and
    never on disk between runs. That is ``_build_go_helper``'s design verbatim,
    and the full argument is in WHAT THE TRACKED-BINARY QUESTION ACTUALLY IS,
    below :data:`GO_REACHABILITY_ANALYZER`.
    """
    import atexit
    import shutil
    import subprocess
    import tempfile

    source = go_reachability_helper_dir()

    go = shutil.which("go")
    if go is None:
        raise AnalyzerUnavailable(
            AnalyzerFault.TOOLCHAIN_MISSING,
            "no `go` on PATH, so the Go reachability analyzer could not run. "
            "This is a fact about this machine and not about the branch: a "
            "broken CI image must never clear a Go branch",
        )
    _probe_go_toolchain(go, source)

    workspace = Path(tempfile.mkdtemp(prefix="claude-dispatcher-go-reachability-"))
    atexit.register(shutil.rmtree, workspace, ignore_errors=True)
    binary = workspace / "go-call-reachability"
    try:
        built = subprocess.run(
            [go, "build", "-o", str(binary), "."],
            cwd=str(source),
            capture_output=True,
            timeout=_HELPER_BUILD_TIMEOUT_SECONDS,
            env=_go_environment(),
        )
    except subprocess.TimeoutExpired as exc:
        raise AnalyzerUnavailable(
            AnalyzerFault.HELPER_TIMEOUT,
            f"building the helper in {source} exceeded "
            f"{_HELPER_BUILD_TIMEOUT_SECONDS}s. A gate that hangs is a gate "
            "that is not enforcing anything",
        ) from exc
    except OSError as exc:
        raise AnalyzerUnavailable(
            AnalyzerFault.HELPER_FAILED,
            f"`{go} build` in {source} could not be run: "
            f"{type(exc).__name__}: {exc}",
        ) from exc
    if built.returncode != 0 or not binary.is_file():
        raise AnalyzerUnavailable(
            AnalyzerFault.HELPER_FAILED,
            f"building the helper in {source} exited {built.returncode}: "
            f"{_diagnostic_text(built.stderr)}",
        )
    return binary


#: The build's budget. Generous on purpose: what it bounds is a HUNG toolchain
#: and not a slow one. The sibling measured its own build at 1.9 s cold and
#: 0.04 s warm on the reference machine.
_HELPER_BUILD_TIMEOUT_SECONDS = 120

#: One UNIT's budget, which is the divergence :class:`GoReachabilityRequest`
#: rules on: the sibling's 30 s is per FILE and this one covers a whole package,
#: including the source importer's walk over GOROOT for every import.
#: **Measured under** ``feat/D6-body``, 2026-08-11: the two acceptance modules
#: (10,454 lines over eight files) answer in 1.2 s and 1.4 s.
_HELPER_TIMEOUT_SECONDS = 120

#: Built once per PROCESS and cached in memory as ``(binary, None)`` or
#: ``(None, fault)``, never on disk between runs — ``_GO_HELPER_PREPARED``'s
#: design, for its reason: a binary cached under ``/tmp`` across runs would be a
#: file outside ``FLOOR_GLOBS`` whose bytes decide what a Go CALL GRAPH is, and
#: this module's output is a ``Disposition.BREACH`` that blocks a branch.
_GO_REACHABILITY_PREPARED: tuple[Path | None, AnalyzerUnavailable | None] | None = None


def _go_environment() -> dict[str, str]:
    """The environment ``go`` is invoked under, for the build and for the run.

    ONE environment for both, because the axes that matter are the same ones:
    the target repository is itself a Go module and may carry a ``go.work`` or a
    ``GOFLAGS`` from a shell profile, and inheriting either would let the tree
    under judgement change what the analysis is.

    ``GOCACHE`` and ``HOME`` are INHERITED. The build genuinely needs a writable
    cache and :func:`_probe_go_toolchain` reports an unwritable one as
    :attr:`AnalyzerFault.TOOLCHAIN_UNUSABLE`; the ANALYSIS does not, which is
    the whole reason ``importer.ForCompiler(fset, "source", nil)`` is ruled and
    ``importer.Default()`` is refused.
    """
    import os

    env = dict(os.environ)
    env.update(
        {
            "GOWORK": "off",
            "GOFLAGS": "",
            "GOPROXY": "off",
            "GOTOOLCHAIN": "local",
            "GO111MODULE": "on",
        }
    )
    for cross in ("GOOS", "GOARCH"):
        env.pop(cross, None)
    return env


def _diagnostic_text(raw: bytes | None) -> str:
    """Helper stderr for a fault message. Lossy and bounded on purpose."""
    if not raw:
        return "(nothing on stderr)"
    text = bytes(raw).decode("utf-8", "replace").strip()
    if len(text) > 2000:
        text = text[:2000] + " …(truncated)"
    return text or "(nothing on stderr)"


def _probe_go_toolchain(go: str, source: Path) -> None:
    """Refuse a ``go`` that is on PATH but cannot do the job.

    On PATH is not the same as working, and a gate that assumes it is fails open
    the first time a container drops ``$HOME``. Three refusals, all
    :attr:`AnalyzerFault.TOOLCHAIN_UNUSABLE`: the probe does not answer;
    ``GOCACHE`` is unset or ``off``, which is what ``go env`` reports when there
    is no writable ``HOME``; or the installed version predates the helper's own
    ``go`` directive, which would report a COMPILE error and blame the helper
    for the machine's age.
    """
    import subprocess

    try:
        probe = subprocess.run(
            [go, "env", "GOVERSION", "GOCACHE"],
            capture_output=True,
            timeout=_HELPER_TIMEOUT_SECONDS,
            env=_go_environment(),
        )
    except subprocess.TimeoutExpired as exc:
        raise AnalyzerUnavailable(
            AnalyzerFault.TOOLCHAIN_UNUSABLE,
            f"`{go} env` did not answer within {_HELPER_TIMEOUT_SECONDS}s; a "
            "toolchain that hangs on its own version probe cannot be used to "
            "clear a branch",
        ) from exc
    except OSError as exc:
        raise AnalyzerUnavailable(
            AnalyzerFault.TOOLCHAIN_UNUSABLE,
            f"`{go} env` could not be run: {type(exc).__name__}: {exc}",
        ) from exc
    if probe.returncode != 0:
        raise AnalyzerUnavailable(
            AnalyzerFault.TOOLCHAIN_UNUSABLE,
            f"`{go} env` exited {probe.returncode}: "
            f"{_diagnostic_text(probe.stderr)}",
        )

    lines = probe.stdout.decode("utf-8", "replace").splitlines()
    version_text = lines[0].strip() if lines else ""
    cache = lines[1].strip() if len(lines) > 1 else ""
    if not cache or cache == "off":
        raise AnalyzerUnavailable(
            AnalyzerFault.TOOLCHAIN_UNUSABLE,
            f"`{go} env GOCACHE` is {cache!r}, which is what it reports when "
            "there is no writable HOME; the helper cannot be built",
        )
    required = _GO_DIRECTIVE.search(
        (source / _GO_MODULE_MANIFEST).read_text(encoding="utf-8")
    )
    installed = re.search(r"go(\d+)\.(\d+)", version_text)
    if required and installed:
        if (int(installed.group(1)), int(installed.group(2))) < (
            int(required.group(1)),
            int(required.group(2)),
        ):
            raise AnalyzerUnavailable(
                AnalyzerFault.TOOLCHAIN_UNUSABLE,
                f"the installed toolchain is {version_text!r} and the helper's "
                f"module requires go{required.group(1)}.{required.group(2)}; a "
                "toolchain that predates the syntax the helper is written "
                "against reports a COMPILE error, which blames the helper for "
                "the machine's age",
            )


def _go_reachability_binary() -> Path:
    """The built helper for this process, or re-raise the fault that stopped it."""
    global _GO_REACHABILITY_PREPARED

    if _GO_REACHABILITY_PREPARED is None:
        try:
            _GO_REACHABILITY_PREPARED = (_build_go_reachability_helper(), None)
        except AnalyzerUnavailable as exc:
            _GO_REACHABILITY_PREPARED = (None, exc)
    binary, failure = _GO_REACHABILITY_PREPARED
    if failure is not None:
        raise failure
    assert binary is not None  # the two arms of the tuple are exclusive
    return binary


#: **P4 RULING (D6 adjudication round 3, 2026-08-11): THE PER-PROCESS RESPONSE
#: MEMO DOES NOT STAND, AND IT IS REMOVED HERE RATHER THAN AMENDED.**
#:
#: It was keyed on ``(encoded request, working directory)`` on the stated ground
#: that "the helper is a pure function of those two". **That ground is false,
#: and the ruling that forced the ``cwd`` parameter below is exactly what makes
#: it false**: the helper resolves imports through ``go list``, which reads
#: ``go.mod``, ``go.sum``, ``GOROOT/src`` and the SOURCE OF EVERY IMPORTED
#: PACKAGE — none of which is in the request, because the request carries one
#: unit's files and nothing else.
#:
#: **Measured under** ``feat/D6-body`` @ ``f4c7c46``, 2026-08-11, one process,
#: one tree, ``example.com/app`` at ``sub/`` with ``sub/main.go`` calling
#: ``core.Work()`` in ``sub/internal/core``:
#:
#:   1. ``graph`` — one edge, ``unreadable_paths == ()``;
#:   2. ``core.go`` rewritten to delete ``Work``. ``sub/main.go`` is unchanged
#:      byte for byte and its working directory is unchanged, so the memo hits;
#:   3. ``graph`` again — zero edges, ``unreadable_paths == ()``.
#:
#: A COLD process over the identical tree state answers ``unreadable_paths ==
#: ('sub/main.go',)``, because ``sub/main.go`` does not type-check. So the memo
#: turned a ``PARSE_FAILED`` abstention into a confident graph in which
#: ``core.Other`` has no incoming edge — it reported dark code out of a tree
#: that does not compile. **That is a memo behaving as a fallback in the precise
#: sense the obligation forbids**, and it fails in the manufacturing direction.
#:
#: The two obligations it DID meet are recorded so the next author does not
#: re-derive them: a miss ran the helper, and no fault was ever cached — every
#: raise preceded the store. The defect is the KEY, not the discipline.
#:
#: THE PRICE OF REMOVAL, measured rather than assumed: ``roots`` and ``graph``
#: each run the helper once per unit instead of sharing one run, and the whole
#: suite goes from 74.1 s to 76.4 s — **2.3 seconds**, against a mechanism whose
#: output blocks a branch. A memo may return only if its key covers everything
#: the answer depends on; keying on every unit's encoded document for the whole
#: tree would close the case measured above and is P3's to weigh, not something
#: to reintroduce on the old key.


def _run_go_reachability_helper(
    binary: Path, request: GoReachabilityRequest, cwd: Path
) -> str:
    """One request in, the helper's stdout out, or the named fault.

    Exit status and document are separate channels: a non-zero exit is
    HELPER_FAILED and stdout is **not read at all**, because a document from a
    run that failed is a partial answer, and a partial graph's missing edges
    look exactly like edges that do not exist.

    The timeout budget is per UNIT rather than per file — the divergence
    :class:`GoReachabilityRequest` rules on — and there is no retry and no
    degraded mode: a fallback is how a gate ends up reporting a pass it did not
    earn.

    ``cwd`` is a PARAMETER and its presence is the P4 type-resolution ruling
    made executable: ``importer.ForCompiler(fset, "source", nil)`` resolves
    imports through ``go list``, relative to the process working directory, so
    the helper must run inside the unit's module or every cross-module import
    fails. It is the exposure that ruling quantifies rather than a convenience,
    and it is named here so a reader meets it at the site that opens it.

    **P4 (D6 adjudication round 3, 2026-08-11): THE PARAMETER STANDS, and it is
    load-bearing rather than tidy. Measured under** ``feat/D6-body`` @
    ``f4c7c46``: one unit, ``example.com/app`` at ``sub/``, importing
    ``example.com/app/internal/core``, run twice through this function with
    nothing changed but ``cwd`` —

        cwd = the package directory   1 symbol, 1 edge
        cwd = the tree root           TYPE ERROR, "could not import
                                      example.com/app/internal/core (no
                                      required module provides package …)"

    A type error is a ``parse_error`` document, which becomes
    ``CallGraph.unreadable_paths``, which abstains the WHOLE tree at
    ``check_subject`` step 1b. So without this parameter every repository whose
    modules are not at the tree root — the acceptance fixture included —
    answers PARSE_FAILED and this row decides nothing at all. The exposure the
    type-resolution ruling quantified is the price of the row existing.
    """
    import subprocess

    document = encode_go_reachability_request(request.unit, request.files)
    try:
        finished = subprocess.run(
            [str(binary)],
            input=document.encode("utf-8"),
            capture_output=True,
            cwd=str(cwd),
            timeout=_HELPER_TIMEOUT_SECONDS,
            env=_go_environment(),
        )
    except subprocess.TimeoutExpired as exc:
        raise AnalyzerUnavailable(
            AnalyzerFault.HELPER_TIMEOUT,
            f"the helper took longer than {_HELPER_TIMEOUT_SECONDS}s on the "
            f"package {request.unit.package_dir!r}. There is no retry and no "
            "degraded mode: a fallback is how a gate ends up reporting a pass "
            "it did not earn",
        ) from exc
    except OSError as exc:
        raise AnalyzerUnavailable(
            AnalyzerFault.HELPER_FAILED,
            f"the helper binary at {binary} could not be executed: "
            f"{type(exc).__name__}: {exc}",
        ) from exc

    if finished.returncode != 0:
        raise AnalyzerUnavailable(
            AnalyzerFault.HELPER_FAILED,
            f"the helper exited {finished.returncode} on the package "
            f"{request.unit.package_dir!r}: "
            f"{_diagnostic_text(finished.stderr)}",
        )
    try:
        stdout = finished.stdout.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AnalyzerUnavailable(
            AnalyzerFault.HELPER_OUTPUT_INVALID,
            f"the helper's stdout for the package "
            f"{request.unit.package_dir!r} is not valid UTF-8: {exc}",
        ) from exc
    return stdout


def _analyzed_units(
    tree: Path,
) -> tuple[tuple[GoUnit, tuple[GoSourceFile, ...], GoReachabilityResponse], ...]:
    """Every unit of ``tree``, run through the helper and decoded.

    The one place :meth:`GoReachabilityAnalyzer.roots` and
    :meth:`GoReachabilityAnalyzer.graph` share, so the two methods cannot come
    to disagree about which units exist — which they would have to agree about
    anyway, since ``discover_seals`` raises when a test root is not declared in
    the graph.

    Rule 4's other half is checked here and not in the decoder: the response
    must ECHO the unit that was requested, and this is the only layer holding
    both.

    **AND SO IS THE ``import_path`` REQUIREMENT (P3, D6 body 2, 2026-08-11).**
    A graph document must NAME the import path the toolchain resolved for its
    unit; a document that does not is
    :attr:`AnalyzerFault.HELPER_OUTPUT_INVALID`. This is the layer that knows
    the string came from the helper rather than from a seal, which is why the
    decoder does not check it — the same R1 discriminator that puts rule 4's
    echo check here. The failure it refuses is not hypothetical: without an
    import path the unit is absent from :func:`_import_path_qualifiers`' map,
    every cross-package edge INTO it is dropped by the both-ends rule, and a
    function production calls reads as uncalled. That is a manufactured BREACH
    arriving as silence, so it is refused loudly instead.

    A ``parse_error`` document carries no import path and is not asked for one:
    it declares no symbols, so nothing can be rejoined to it.
    """
    binary = _go_reachability_binary()
    root = Path(tree)
    analyzed = []
    for unit, files in discover_units(root):
        request = GoReachabilityRequest(
            schema=GO_REACHABILITY_SCHEMA, unit=unit, files=files
        )
        directory = root / unit.package_dir if unit.package_dir else root
        response = decode_go_reachability_response(
            _run_go_reachability_helper(binary, request, directory)
        )
        if response.unit != unit:
            raise _output_invalid(
                f"the helper answered for {response.unit} and was asked about "
                f"{unit}; a response for a package nobody asked about would "
                "attach one package's edges to another package's symbols"
            )
        if response.parse_error is None and not response.import_path:
            raise _output_invalid(
                f"the helper's graph document for {unit} names no import path. "
                "The toolchain is the only authority on one, and without it "
                "every cross-package edge into this package is dropped by the "
                "both-ends rule — a function production calls would read as "
                "uncalled, which is a manufactured BREACH arriving as silence"
            )
        analyzed.append((unit, files, response))
    return tuple(analyzed)


def _import_path_qualifiers(
    analyzed: Sequence[tuple[GoUnit, GoReachabilityResponse]],
) -> dict[str, str]:
    """Each unit's IMPORT PATH mapped to the qualifier its keys are spelled with.

    **The two are not the same string and cannot be.** :func:`go_symbol_key`'s
    qualifier keeps the tree-relative ``package_dir`` — it is a LABEL that must
    be unique and legible, never an import path to be resolved — so the
    acceptance fixture's ``cmd/gates`` is keyed
    ``…/gates/cmd/gates.VerifyPreservation`` while its import path is ``…/gates``.
    The helper can only spell a callee in ANOTHER package by that package's
    import path, which is what the file's import block gives it.

    Without this map every cross-package call inside one tree would be an edge
    whose callee no symbol declares, and ``CallGraph``'s both-ends rule would
    drop it — losing a real production edge, which manufactures a BREACH. That
    is the direction anti-requirement 2 forbids, so the join is made here rather
    than left to the drop. It binds nothing in the acceptance fixture, whose
    seven modules are one package each; it binds every repository with an
    ``internal/``.

    **P3 (D6 body 2, 2026-08-11) — THE IMPORT PATH NOW COMES FROM THE GO
    TOOLCHAIN AND NOT FROM DIRECTORY ARITHMETIC, AND THE COLLISION IS LOUD.**

    What this function used to do is written out below and left there, because
    the shapes it got wrong are the reason the field exists. What it does now is
    two lines: read ``GoReachabilityResponse.import_path`` — which the helper
    obtains from ``go list -e -find -f {{.ImportPath}} .`` in the unit's own
    directory — and refuse a second unit that claims one already claimed.

    **WHAT THE FIELD CLOSED, and each was re-measured under** ``feat/D6-body2``,
    **2026-08-11, on the tree the P4 built:**

      * **THE VENDOR SHAPE (was item 1), CLOSED.** ``sub/vendor/example.com/lib``
        under a module at ``sub/``, with ``sub/vendor/modules.txt``: the
        arithmetic answered ``example.com/app/vendor/example.com/lib`` and the
        graph held ZERO edges; the toolchain answers ``example.com/lib``, which
        is what the type-checker resolved, and the edge into ``lib.Do`` lands.
      * **THE DUPLICATE-IMPORT-PATH COLLISION (was item 3), NOW LOUD.** Two units
        claiming one import path raise
        :attr:`AnalyzerFault.HELPER_OUTPUT_INVALID` here, exactly as a duplicate
        symbol key across units does in :meth:`GoReachabilityAnalyzer.graph` and
        for the same reason: one label naming two packages is one symbol wearing
        two declarations, one layer up. **It is NOT closed by construction, and
        the escalation asked whether it would be — the answer is measured and
        it is no.** ``go list`` run in ``a/`` and in ``b/``, both declaring
        ``module example.com/dup``, answers ``example.com/dup`` for both: the
        toolchain reports what each module calls ITSELF, and two directories may
        legally call themselves the same thing. The raise is therefore still
        needed and is still the whole of that repair.

    **WHAT THE FIELD DID NOT CLOSE, AND THIS IS A CORRECTION TO THE ESCALATION
    RATHER THAN A DEFERRAL. A RENAMING** ``replace`` **(was item 2) IS STILL
    OPEN, and no per-unit import-path field can close it.** Measured under
    ``feat/D6-body2``, 2026-08-11, over ``sub/go.mod`` declaring ``module
    example.com/app`` with ``replace example.com/upstream => ./local`` and
    ``sub/local/go.mod`` declaring ``module example.com/localfork``:

      * ``go list`` in ``sub/local`` answers ``example.com/localfork``;
      * the helper for ``sub`` spells the callee ``example.com/upstream.Serve``,
        because that is the path go/types assigned the package it imported.

    Both are the toolchain's own answers and both are right. **A package reached
    through a renaming** ``replace`` **HAS TWO import paths — one per module that
    names it — so "the import path of this directory" is not a function of this
    directory**, and a field carrying one string per unit cannot hold two. The
    edge is DROPPED, which is the same direction as before the field and the
    conservative one; nothing is mis-joined.

    **THE FIX THAT WOULD CLOSE IT, escalated rather than taken, and the reason
    it was not taken is a seal and not a preference.** The toolchain does answer
    the question when it is asked from the IMPORTING side: measured under the
    same revision, ``go list -e -f '{{.ImportPath}} {{.Dir}}' example.com/upstream``
    run in ``sub/`` answers the pair ``example.com/upstream`` →
    ``sub/local``. So a second wire field — per unit, each IMPORT's resolved
    DIRECTORY — would let the join go directory-to-unit and need no import-path
    arithmetic at all, closing the rename shape exactly. It also answers the
    duplicate shape EXACTLY rather than refusing it: the same query in
    ``app/`` resolves ``example.com/dup`` to ``a/``, which is what ``replace``
    says and what this map cannot read. **That is precisely why it was not
    taken here.**
    ``test_two_units_claiming_one_import_path_are_never_silently_joined_to_one``
    requires that shape to raise or to drop, and a correct answer is neither.
    Landing both would mean editing a seal, which this body may not do. See the
    disputes in the commit message.

    **P4 RULING (D6 adjudication round 3, 2026-08-11): THE REPAIR IS CORRECT
    AND IT STAYS HERE. Its limits are below and they are not small.** The
    limits are what the field above closes; the ruling on WHERE the repair
    lives is unchanged.

    THE RULING ON CORRECTNESS was taken by building the shapes that break naive
    prefix rewriting and running them, not by reading this function. **Measured
    under** ``feat/D6-body`` @ ``f4c7c46``, 2026-08-11, each shape a whole tree
    with the module BELOW the tree root — which is the only arrangement in which
    this map is anything but the identity, and it is the acceptance fixture's
    own arrangement:

      * ``internal/`` under a module at ``sub/``: the edge survives WITH the
        map and is DROPPED without it;
      * two package directories where one import path is a strict textual
        prefix of the other's KEY (``example.com/app/b`` and
        ``example.com/app/b.v2``, so ``example.com/app/b.`` genuinely prefixes
        ``example.com/app/b.v2.FromBV2``): both edges land in their own
        package. **This is the one shape in which longest-match is
        load-bearing**; shortest-match rewrites ``b.v2`` into
        ``<qualifier of b>.v2`` and invents a symbol;
      * a nested module (``example.com/inner`` inside ``example.com/outer``'s
        tree, reached by ``replace``): joined correctly;
      * a module path that is a strict prefix of another's
        (``example.com/x`` / ``example.com/xy``): joined correctly, and the
        separator alone is what keeps them apart;
      * a package whose DIRECTORY name differs from its package clause
        (``internal/go-utils`` declaring ``package utils``): joined correctly,
        and it is a non-issue by construction — this map is keyed on the
        directory, which is what an import path names, and never on the clause;
      * pointer and value receiver methods across packages: the prefix rewrite
        moves ``…(*T).Ptr`` and ``…(T).Value`` intact;
      * an external test package beside its package: correctly absent from the
        map, and the two edges into ``core.Work`` — one from ``main``, one from
        ``core_test`` — both join.

    **WHAT THIS DID NOT CLOSE**, as the round-3 adjudication left it. Three
    shapes, measured under the same revision, all ESCALATED TO P3 because each
    needs production code. **Their state under this revision: (1) CLOSED by the
    toolchain field, (2) STILL OPEN and now known to be unclosable by any
    per-unit field, (3) LOUD rather than silent.** They are kept in full
    because the repair above is measured against them:

      1. **A REAL ``go mod vendor`` TREE LOSES THE EDGE.** ``go`` strips
         ``go.mod`` from a vendored module, so ``vendor/example.com/lib`` has
         no manifest of its own and :func:`_nearest_module_dir` walks up to the
         ENCLOSING module. This map then computes its import path as
         ``example.com/app/vendor/example.com/lib`` while the type-checker
         resolves the import as ``example.com/lib``. No prefix matches, the
         edge is dropped, and ``lib.Do`` — which production calls — reads as
         UNCALLED. Measured: a tree with ``sub/vendor/modules.txt`` and
         ``sub/vendor/example.com/lib/lib.go`` produces ZERO edges.
         :func:`discover_units`' CHOICE deliberately does not skip ``vendor/``,
         so this is reachable by this module's own doctrine, and it is the
         second most common shape in Go after ``internal/``.
      2. **A ``replace`` THAT RENAMES LOSES THE EDGE.** ``replace
         example.com/upstream => ./local`` where ``local/go.mod`` declares
         ``module example.com/localfork``: the import block names
         ``example.com/upstream``, this map keys ``example.com/localfork``, and
         the edge into ``Serve`` is dropped. Measured, same direction, rarer.
      3. **TWO UNITS CLAIMING ONE IMPORT PATH ARE SILENTLY MIS-JOINED, AND
         THIS IS THE ONE PLACE THE REPAIR IS WORSE THAN THE DROP IT
         REPLACED.** ``qualifiers`` is a plain ``dict`` with no collision
         check, so the LAST unit written wins and the winner is decided by
         :func:`discover_units`' sort order, which is a fact about directory
         names. Measured over a tree holding ``a/go.mod`` and ``b/go.mod`` both
         declaring ``module example.com/dup``, with ``app`` reaching the first
         through ``replace … => ../a``: the edge lands on ``b/d.go``. The real
         target reads as uncalled (a false BREACH) **and** the decoy reads as
         called (a false certification, which hides dark code). The same
         happens for a vendored copy that does carry a ``go.mod``.
         **The fix is a raise:** a second unit claiming an import path already
         in this map is :attr:`AnalyzerFault.HELPER_OUTPUT_INVALID`, exactly as
         a duplicate symbol key across units is in
         :meth:`GoReachabilityAnalyzer.graph`, and for the same reason — one
         label naming two packages is one symbol wearing two declarations, one
         layer up. ``tests/test_go_reachability.py`` carries the RED row that
         P3 must turn green. **DONE under** ``feat/D6-body2``: the raise is in
         the body of this function and the row is green. It is a RAISE and not
         a construction — see the P3 note above for why the toolchain does not
         tell these two units apart either.

    **WHY THE REPAIR STAYS HERE RATHER THAN BECOMING ONE SPELLING.** See
    :meth:`GoReachabilityAnalyzer.graph`'s ruling on the alternative, which was
    measured rather than argued: making the qualifier the import path costs five
    seal rows and closes only the first four shapes above, because
    ``<module path> + <in-module directory>`` is not a package's import path
    either — it is a second recomputation of the same unknowable, and it gets
    (1) and (2) wrong in exactly the same way this one does. Only the Go
    toolchain knows a package's import path.
    """
    qualifiers: dict[str, str] = {}
    claimed_by: dict[str, GoUnit] = {}
    for unit, response in analyzed:
        if response.parse_error is not None:
            # A unit that did not parse or did not type-check declares no
            # symbol, so nothing can be rejoined to it and it names no
            # import path. It is not a claimant and cannot collide.
            continue
        if _is_external_test_package(unit.package_name):
            # Nothing in any tree can import an external test package, so it
            # has no import path anyone could name and belongs in no map. It
            # is ALSO why this skip must come before the collision check: the
            # helper answers with the DIRECTORY's import path, which for
            # ``package foo_test`` is ``foo``'s — so keeping it would make
            # every external test package a collision with the package beside
            # it, and abstain on an idiomatic Go tree.
            continue
        import_path = response.import_path
        if import_path in claimed_by:
            raise _output_invalid(
                f"the import path {import_path!r} is claimed by two units — "
                f"{claimed_by[import_path]} and {unit}. One label naming two "
                "packages is one symbol wearing two declarations, one layer "
                "up: the edge would land on whichever unit the sweep sorted "
                "last, so the real target would read as uncalled (a false "
                "BREACH) and the other would read as called (a false "
                "certification, which hides dark code). There is no honest "
                "tie-break — `replace` decides which directory an import "
                "resolves to and nothing here reads `replace` — so this "
                "abstains rather than guesses"
            )
        claimed_by[import_path] = unit
        qualifiers[import_path] = _qualifier_of(unit)
    return qualifiers


def _join_callee(
    callee: str, symbols: Mapping[str, Symbol], qualifiers: Mapping[str, str]
) -> str:
    """The callee key as this tree spells it, when the tree spells it at all.

    A callee the helper named by IMPORT PATH — the only way it can name a target
    in another package — is rewritten to the qualifier that package's own unit
    keys its symbols with; see :func:`_import_path_qualifiers` for why the two
    strings differ. Longest prefix wins, so a module and a package inside it
    cannot both claim one key. Anything that does not resolve is left alone and
    the both-ends rule drops it, which is the right answer for the standard
    library.

    **P4 (D6 adjudication round 3, 2026-08-11).** Longest-match is not
    decoration and the shape that needs it was BUILT rather than imagined.
    ``_KEY_PACKAGE_SEPARATOR`` is ``"."`` and an import path may legally contain
    one, so ``example.com/app/b.`` is a genuine textual prefix of
    ``example.com/app/b.v2.FromBV2``. **Measured under** ``feat/D6-body`` @
    ``f4c7c46``: with longest-match both callees land in their own package;
    shortest-match rewrites the second to ``<qualifier of b>.v2.FromBV2``,
    which no unit declares — so the failure mode of getting this backwards is
    a DROPPED production edge, not a visible error.

    THE ``callee in symbols`` SHORT-CIRCUIT IS NOT AN OPTIMISATION and must not
    be removed as one: a key the tree already declares is already this tree's
    spelling, and rewriting it would move a correct key onto a longer prefix.

    RESIDUE, named because leaving it implied is how it becomes a surprise: a
    callee in a package OUTSIDE the tree whose import path is prefixed by an
    in-tree one — ``example.com/x.y.F`` where ``example.com/x`` is in the tree
    and ``example.com/x.y`` is not — is rewritten to ``<qualifier of x>.y.F``.
    That string cannot collide with a real member, because a member is a bare
    name or a ``(recv).name`` form and neither can contain a bare ``.``
    segment, so the rewrite lands on nothing and the both-ends rule drops the
    edge — which is what would have happened anyway. It is recorded rather than
    fixed because the fix would need to know which import paths exist outside
    the tree, and nothing here does.
    """
    if callee in symbols:
        return callee
    for import_path in sorted(qualifiers, key=len, reverse=True):
        prefix = f"{import_path}{_KEY_PACKAGE_SEPARATOR}"
        if callee.startswith(prefix):
            return f"{qualifiers[import_path]}{_KEY_PACKAGE_SEPARATOR}{callee[len(prefix):]}"
    return callee


def _edge_order(edge: Edge) -> tuple[str, str, str, str]:
    """A total, content-only order over edges. Sorted at CONSTRUCTION.

    D5 sorts again in ``build_call_graph``, so this cannot move a VERDICT — but
    :meth:`GoReachabilityAnalyzer.graph` is called directly by seals and by
    ``roots``' sibling, and two runs over one tree must produce EQUAL graphs.
    """
    return (edge.caller.key, edge.callee.key, edge.kind.value, edge.site)


def _qualifier_of(unit: GoUnit) -> str:
    """The qualifier half of a key, taken FROM :func:`go_symbol_key`.

    A key with an empty member is the qualifier plus the separator, so this
    reads the one spelling rather than respelling it — which is the whole point
    of that function existing.
    """
    key = go_symbol_key(
        unit.module_path, unit.package_dir, unit.package_name, None, ""
    )
    return key.rpartition(_KEY_PACKAGE_SEPARATOR)[0]


def _is_external_test_package(package_name: str) -> bool:
    """Go's total discriminator, spelled without a second ``endswith``.

    The module is permitted exactly one ``endswith`` and it is
    :func:`go_symbol_key`'s, over this same clause; a second call would redden
    the sweep that pins it, and a slice comparison says the same thing.
    """
    suffix = _EXTERNAL_TEST_PACKAGE_SUFFIX
    return len(package_name) > len(suffix) and package_name[-len(suffix) :] == suffix


# --------------------------------------------------------------------------- #
# Part 5 — the row
# --------------------------------------------------------------------------- #


class GoReachabilityAnalyzer:
    """Go's answer to the three questions D5's mechanism asks.

    Satisfies ``call_site_reachability.ReachabilityAnalyzer`` structurally; the
    Protocol is deliberately not ``@runtime_checkable`` and the shape check that
    matters is ``validate_analyzers``, which a seal can read.

    **NOT ENROLLED.** :data:`GO_REACHABILITY_ANALYZER` below is an instance and
    nothing else; ``ANALYZERS`` is still ``()``.
    """

    @property
    def language(self) -> Language:
        """``Language.GO``, the key both registries share.

        Implemented, with ``negative_is_conclusive``, because they are fields
        rather than work: a row whose two declarative members raise cannot be
        handed to ``validate_analyzers`` at all, and validating the row's SHAPE
        while its methods are unimplemented is the exact property D5 contracts
        (``a row is validated for SHAPE at import and never for
        implementedness``).
        """
        return Language.GO

    @property
    def negative_is_conclusive(self) -> bool:
        """``True``, and this is the most important claim the row makes.

        Go has no runtime lookup of a package-level function by name: there is
        no ``reflect`` route to a package's declarations, so a symbol whose name
        is referenced nowhere in the production closure is called nowhere and
        "no path" is a FACT about the language rather than a fact about this
        analyzer's quality. That asymmetry — against Python's ``False``, which
        is measured four times over ``src/`` — is the ruling that made D5
        language-parametric on day one rather than Python-with-a-Go-case, and
        it is the reason this row can produce a BREACH at all.

        A real ``bool`` and not a truthy value, which ``validate_analyzers``
        refuses by name: a truthy non-bool is the coercion defect from
        ``skills/explicit-state.md`` applied to the one field that decides
        whether this mechanism may emit a BREACH.

        **What it does NOT buy, because the two guards are independent.** A
        ``True`` row still abstains whenever the production closure contains an
        unresolved call (``check_subject`` step 3), and over a real Go tree it
        will contain some — every ``fns[i](x)``, every call through a struct
        field. The row's boolean and the per-closure count are belt and braces
        by design: a branch cannot turn abstentions into BREACHes by editing the
        row, and cannot turn BREACHes into abstentions by adding one dynamic
        call to a path production already runs.
        """
        return True

    def roots(self, tree: Path) -> tuple[Root, ...]:
        """Every Go :class:`Root` in ``tree``, DERIVED. Never read from a list.

        STUB. The composition: :func:`discover_units`, then one helper
        invocation per unit, then :func:`entrypoint_kind_for_wire` per reported
        root, then a :class:`Root` whose ``root_kind`` is left to
        ``_validate_root`` to derive — a row that asserted its own
        ``root_kind`` is refused outright, and correctly.

        There is no ``ENTRYPOINTS`` constant here and there must never be one.
        The precedent D5 records is concrete: an earlier hand-list in this repo
        omitted ``recheck_min_severity``, the safety floor.

        CHOICE (D5's :func:`discover_roots` says any :class:`AnalyzerError`
        from here raises, and step 1b's ruling says an unparsed tree must reach
        the judgement; the two cannot both be read literally, so the silence is
        marked): **this method must not raise** :class:`SourceUnreadable`.
        Rejected alternative: raising it, which is the literal reading of
        ``discover_roots`` and which makes
        :attr:`UndecidedReason.PARSE_FAILED` unreachable through
        ``check_tree`` for Go — a member no dispatch emits, which is D5's own
        stated failure. **The reason is a composition trace rather than a
        preference.** D5's
        :func:`discover_roots` wraps ANY :class:`AnalyzerError` from here into a
        :class:`CallSiteReachabilityError` and the whole check dies. But P4
        ruled, at ``check_subject`` step 1b, that ``PARSE_FAILED`` outranks
        ``NO_ENTRYPOINT`` precisely because "an unparsed file is exactly where
        an undiscovered ``func main`` would be" — a ruling that can only ever
        take effect if a tree containing an unparsed file REACHES step 1b. So
        the ruling implies this method returns the roots of every unit that
        parsed, and reports the unparsed file through the graph instead.

        The stated harm of a partial root set — "the roots that failed to appear
        are exactly the ones whose absence manufactures BREACHes" — is exactly
        what step 1b neutralises: with ``unreadable_paths`` non-empty, every
        subject abstains at 1b, before step 4 can reach the tests-only verdict.
        A missing root can therefore only cost a ``FROM_PRODUCTION`` at step 1,
        which downgrades to an abstention. Failing to look made the answer less
        conclusive and manufactured nothing, which is anti-requirement 2 satisfied.

        **RAISED FOR P4, not papered over:** ``discover_roots``'s sentence
        ("raises ... if any analyzer raises AnalyzerError") and step 1b's ruling
        cannot both be read literally. This row adopts the reading that makes
        the later ruling non-vacuous, states it here, and edits nothing in D5.
        If P4 prefers the other reading, the consequence must be written down
        rather than left implied: ``UndecidedReason.PARSE_FAILED`` becomes
        unreachable through ``check_tree`` for Go, which would make it "a member
        no dispatch emits" — D5's own stated failure, one level down.

        THE FILE HALF, applied here and nowhere else. The helper emits
        ``test_function`` on a NAMING claim alone, because it must not open a
        second notion of "is this one of the tests". This method asks the shared
        matcher and drops a root whose file disagrees with its kind, in both
        directions:

          * a ``TEST_FUNCTION`` outside a test file is not an entrypoint at all
            — ``go test`` runs ``TestX`` only in a ``_test`` file, so a
            production function that happens to be called ``TestFoo`` starts
            nothing;
          * a production kind INSIDE a test file — an ``init`` or a
            package-level ``var`` in a ``_test`` file — runs in the test binary
            and not in production, so it is not a production root either.

        Both are also exactly what ``_validate_root`` refuses, so the filter is
        what keeps a legal Go tree from taking the whole check down.

        **P4 RULING (D6 adjudication round 3, 2026-08-11) — DROP, IN BOTH
        DIRECTIONS, AND NOT RAISE. The two halves are ruled for DIFFERENT
        reasons and only one of them is semantics.** The rule was not in the
        scaffold and the body was right to flag it rather than let it pass as
        obvious.

        **RAISE IS WRONG HERE, and the module's own doctrine is what says so.**
        "An unreachable arm which raises is the difference between a contract
        and a coincidence" governs arms that are IMPOSSIBLE. Neither of these
        is: ``func init()`` in a ``_test.go`` is idiomatic Go, and a func named
        ``TestFoo`` in ``main.go`` is legal. A raise here leaves as
        :class:`AnalyzerError`, ``discover_roots`` wraps it, and the whole check
        dies on a legal tree — the exact failure this method's CHOICE above was
        written to avoid. There is no unreachable arm to harden: RULE 10 in the
        decoder already refuses a root naming an undeclared symbol, so
        ``symbols[wire.symbol]`` cannot miss, and
        ``_ROOT_KIND_BY_ENTRYPOINT`` is total over :class:`EntrypointKind`
        because ``entrypoint_kind_for_wire`` raises before this line on
        anything else.

        **DIRECTION 1 — a ``TEST_FUNCTION`` in a production file. The drop is
        CORRECT and permanent.** It is not a new rule at all: it is the
        conjunction :func:`go_test_root_predicate` already contracts, whose
        naming half the helper applies and whose FILE half is
        ``seal_verify.is_test_path``. The conjunction is false, so there is no
        root, and no root is lost — the symbol stays in the graph and any real
        edge into it still counts. **Measured under** ``feat/D6-body`` @
        ``f4c7c46``: ``func TestFoo`` in ``main.go`` calling
        ``reachedOnlyFromTestFoo``; the root is dropped and the callee reads
        FROM_NEITHER, which is the TRUE answer, because ``go test`` does not
        run ``TestFoo`` out of ``main.go`` and nothing else calls it.

        **DIRECTION 2 — a production kind in a test file. The drop is FORCED,
        it is an UNDER-APPROXIMATION IN THE MANUFACTURING DIRECTION, and it is
        a LIMIT rather than semantics. The sentence above claiming it "is not a
        production root either" is true and INCOMPLETE, and the completion is
        the point:** it is not "no root", it is a TEST root. ``func init()`` in
        a ``_test.go`` genuinely runs, in the test binary, and everything it
        reaches is genuinely reached under test.

        The row cannot say so. D5 derives ``root_kind`` from ``kind`` ALONE
        (``_ROOT_KIND_BY_ENTRYPOINT``) and ``_validate_root`` then REFUSES the
        disagreement with the file, and that refusal is sealed —
        ``test_root_kind_is_derived_from_the_kind_and_never_asserted_by_the_row``
        pins "``func main`` inside ``contract_seal_test.go``" as a refusal. So
        a Go row's only two moves are drop and die, and dropping is the one
        that leaves the check running.

        **WHAT IT COSTS, measured under** ``feat/D6-body`` @ ``f4c7c46``:

          * ``func init()`` in ``z_test.go`` calling ``registered()`` — the
            root is dropped and ``registered`` reads FROM_NEITHER where the
            true answer is FROM_TEST. FROM_NEITHER is this mechanism's loudest
            state, so an under-approximation here does not merely lose
            information, it accuses;
          * a package whose only initialised package-level ``var`` lives in a
            test file — same, through the synthetic ``<vars>`` symbol.

        **ESCALATED TO THE D5 ADJUDICATOR, and it is D5's contract that is
        already on this side of the argument:** ``_validate_root``'s own
        docstring says ``root_kind`` is "DERIVED from ``kind`` and from
        ``seal_verify.is_test_path`` over the declaring file", while
        ``_ROOT_KIND_BY_ENTRYPOINT`` derives it from ``kind`` alone. The two
        agree only if a production kind in a test file is impossible, and it is
        idiomatic. The fix is one table lookup — ``RootKind.TEST`` whenever
        ``is_test_path`` is true, whatever the ``kind`` — and it belongs to D5,
        not here. Nothing in this module is edited for it.

        **A SEPARATE AND WORSE DEFECT AT THE SAME SEAM, ESCALATED TO P3.** The
        synthetic ``<vars>`` symbol is per PACKAGE and takes its path from the
        first contributing file, so ONE symbol stands for initialisers that run
        in two different binaries. Measured under the same revision, over one
        package holding ``var _ = onlyProd()`` and ``var _ = onlyTest()``:

            main.go + z_test.go   <vars> path is main.go, the root is KEPT as
                                  PRODUCTION, and its edge to `onlyTest` makes
                                  a function only a test file initialises read
                                  as REACHED FROM PRODUCTION — a false
                                  certification, which hides dark code;
            a_test.go + b.go      <vars> path is a_test.go, the whole root is
                                  DROPPED, and `onlyProd` — genuinely
                                  initialised in production — reads
                                  FROM_NEITHER, a false BREACH.

        **The same package, the same code, and the verdict flips on the
        alphabetical position of a test file's name.** Neither answer is
        reachable through the filter in this method, because the filter reads
        one path and the symbol conflates two. The fix is in the helper: emit
        ``<vars>`` once per (package, binary) rather than once per package, each
        taking its path from a file of its own kind.
        """
        roots: list[Root] = []
        for _unit, _files, response in _analyzed_units(tree):
            if response.parse_error is not None:
                # DISPUTE D4's consequence: a unit that did not parse or did not
                # type-check contributes no roots and is NOT raised past. The
                # graph records the file, and step 1b abstains the whole tree
                # before step 4 can reach a tests-only verdict.
                continue
            symbols = {
                record.key: Symbol(
                    key=record.key, path=record.path, line=record.line
                )
                for record in response.symbols
            }
            for wire in response.roots:
                kind = entrypoint_kind_for_wire(wire.kind)
                symbol = symbols[wire.symbol]
                root_kind = _ROOT_KIND_BY_ENTRYPOINT[kind]
                in_test_file = is_test_path(symbol.path)
                if (kind is EntrypointKind.TEST_FUNCTION) != in_test_file:
                    continue
                roots.append(
                    Root(
                        symbol=symbol,
                        kind=kind,
                        root_kind=root_kind,
                        evidence=wire.evidence,
                    )
                )
        return tuple(roots)

    def graph(self, tree: Path) -> CallGraph:
        """The whole tree's Go :class:`CallGraph`. STUB.

        The composition: :func:`discover_units`, one invocation per unit,
        :func:`decode_go_reachability_response` per response, then the union —
        symbols keyed by :func:`go_symbol_key`, edges through
        :func:`edge_kind_for_wire`, holes into ``unresolved_calls``, and a
        ``parse_error`` document into ``unreadable_paths``.

        Obligations a body must meet:

          * **Every declaration becomes a symbol**, including the ones nothing
            references. A symbol absent from the map cannot be a subject, and a
            subject that cannot be found is an abstention, not a pass.
          * **An edge is kept only when BOTH ends are declared in the tree**,
            which is :class:`CallGraph`'s own rule. A call into the standard
            library is dropped; a callback PASSED to it is kept as a
            ``reference`` edge to the callback.
          * **A ``parse_error`` unit is RECORDED, never raised past.** See
            :meth:`roots`: raising from either method takes down the check that
            the ``PARSE_FAILED`` ruling exists to keep running, and the raise
            would land two layers further on — ``build_call_graph`` catches
            :class:`SourceUnreadable` and ``continue``\\ s, discarding this
            row's entire graph, after which ``discover_seals`` raises because
            no test root is declared in an empty symbol map. Measured by
            reading the composition, ``feat/D5-floor-body`` @ ``0238aa2``,
            2026-08-11. ``unreadable_paths`` is the channel that exists for
            this and it is the only one that works.
          * **A duplicate key ACROSS units is HELPER_OUTPUT_INVALID here**, the
            way a duplicate within one unit is at the decoder. It should be
            impossible — the qualifier makes keys unique per package — so if it
            happens the sweep sent one package twice or ``go_symbol_key``
            disagrees with itself, and both are mechanism bugs.
          * **THE WHOLE-TREE EMPTINESS GUARD LIVES HERE.** A unit that declares
            nothing is an answer; a tree in which :func:`discover_units` found
            Go files and the union graph has zero symbols is
            :attr:`AnalyzerFault.HELPER_OUTPUT_INVALID`. D5 demands this
            explicitly — "including an EMPTY graph where a graph was expected"
            — and names the failure direction: an empty graph makes every
            subject ``FROM_NEITHER``, which is the loudest state the mechanism
            has, so the failure is a flood rather than a silence. This is the
            layer that knows how many Go files the sweep found, so it is the
            only layer that can tell the two apart.
          * **Determinism.** Two runs over one tree produce equal graphs.

        The fault ORDER on the first invocation is HELPER_MISSING,
        TOOLCHAIN_MISSING, TOOLCHAIN_UNUSABLE, then the build's own — helper
        first, following the TypeScript comparator rather than the Go
        fingerprinter, because here as there the thing whose provenance is in
        question is the helper, and the first message an operator sees on an
        unconfigured machine should name it.

        **P4 RULING (D6 adjudication round 3, 2026-08-11) — THE CROSS-PACKAGE
        KEY REPAIR BELONGS HERE, FOR NOW, AND THE COST OF MOVING IT WAS
        MEASURED BEFORE THE RULING RATHER THAN ESTIMATED AFTER.**

        A repair that reconciles two spellings is weaker than one spelling, so
        the alternative was built and run rather than reasoned about: make
        ``GoUnit.package_dir`` MODULE-relative instead of tree-relative, so that
        ``qualifierOf(unit)`` in ``main.go`` equals the package's import path
        and the helper's cross-package callee key equals the callee unit's own
        key by construction, with no map and no rewrite.

        **THE COST, measured under** ``feat/D6-body`` @ ``f4c7c46``, 2026-08-11,
        by applying that change to a copy of this tree and running the whole
        suite: **five red rows** —
        ``test_a_directory_holding_two_packages_is_two_units``,
        ``test_the_module_path_is_the_nearest_enclosing_go_mod``,
        ``test_the_sweep_is_deterministic_and_writes_nothing``,
        ``test_interface_satisfaction_produces_no_edge_and_a_call_through_one_produces_many``
        and
        ``test_the_acceptance_case_is_seven_seal_subject_pairs_over_two_keys``.
        The acceptance row's SUBSTANCE survives the move — the two
        ``VerifyPreservation`` keys stay distinct, as
        ``…/gates.VerifyPreservation`` and ``…/iterate.VerifyPreservation`` —
        so the fixture's whole reason for existing is not what the move costs.
        Five rows is a price this effort would pay.

        **THE RULING IS AGAINST THE MOVE ANYWAY, because it does not buy one
        spelling — it buys a cheaper second guess at the same unknowable.**
        Measured under the same change: a real ``go mod vendor`` tree still
        loses its edge, and a renaming ``replace`` still loses its edge, for the
        identical reason both fail today — ``<module path> + <in-module
        directory>`` is not a package's import path in either shape. What the
        move DOES buy is that the duplicate-import-path collision stops being
        silent: the two units merge and go/types answers "Do redeclared in this
        block", which reaches the caller as ``unreadable_paths`` and abstains
        the tree. Loud and conservative, against today's silent mis-join.

        **So the ruling is: keep the repair in this method, make the collision
        loud where it is (see :func:`_import_path_qualifiers`), and ESCALATE THE
        ONE FIX THAT IS ACTUALLY ONE SPELLING to P3 — the import path must come
        from the Go toolchain, which the helper already execs, and not from
        arithmetic on directory names.** Concretely: the helper reports, per
        unit, the import path ``go/build`` resolves for its own directory, and
        the Python side keys symbols by that. That closes all three residual
        shapes at once, it is production code plus a wire field, and it is not
        a contract sentence.

        **P3 (D6 body 2, 2026-08-11) — THE SECOND HOLE IS CLOSED IN THE HELPER
        AND IT COST ONE SEAL ROW.** ``classifySelectorCall`` now emits the one
        target go/types resolved whenever the receiver's base type is not an
        interface, and keeps the fan-out only for genuine interface dispatch.
        Measured over the tree the escalation names: ``core.(*T).Ptr`` and
        ``core.(T).Value`` gain their ``method`` edges and the ``interface``
        edge to the unrelated in-unit ``Decoy.Ptr`` is gone — the false BREACH
        and the false certification close together. Measured over the
        acceptance fixture: 738 edges become 694, all 44 removed are
        ``interface``, none is added, and every removed one is a fan-out from a
        ``String()`` on a CONCRETE STDLIB receiver. The production closure is
        104 either way. **THE COST IS A RED ROW AND IT IS A DISPUTE, NOT A
        REGRESSION:**
        ``test_a_named_out_of_tree_target_is_not_a_hole_and_a_func_value_call_is``
        pins the 45th instance of exactly that shape as REQUIRED. See the note
        at ``main.go``'s ``classifySelectorCall`` and the commit message.

        **THE ESCALATION AS IT STOOD, kept because it is what the repair is
        measured against:** a method call
        on a receiver whose type is declared in another IN-TREE package emits no
        edge at all, because the helper fans out over ITS OWN unit's methods of
        that name. Measured under this revision: ``core.(*T).Ptr``, called from
        ``main``, reads as UNCALLED; and if the calling unit happens to declare
        an unrelated method of the same name, the SAME call site also
        manufactures an ``interface`` edge to it. One false BREACH and one false
        certification, at one site. No amount of key rejoining reaches it — the
        edge is never emitted.
        """
        analyzed = _analyzed_units(tree)
        qualifiers = _import_path_qualifiers(
            [(unit, response) for unit, _, response in analyzed]
        )

        symbols: dict[str, Symbol] = {}
        declaring_unit: dict[str, GoUnit] = {}
        unreadable: list[str] = []
        go_files = 0
        for unit, files, response in analyzed:
            go_files += len(files)
            if response.parse_error is not None:
                # RECORDED, never raised past. Raising from here lands two
                # layers on: build_call_graph catches SourceUnreadable and
                # continues, discarding this row's ENTIRE graph, after which
                # discover_seals raises because no test root is declared in an
                # empty symbol map. unreadable_paths is the channel that exists
                # for this and it is the only one that works.
                unreadable.append(response.parse_error.path)
                continue
            for record in response.symbols:
                if record.key in symbols:
                    raise _output_invalid(
                        f"the key {record.key!r} is declared by two units — "
                        f"{declaring_unit[record.key]} and {unit}. It should be "
                        "impossible, so either the sweep sent one package twice "
                        "or go_symbol_key disagrees with itself, and both are "
                        "mechanism bugs that would put one symbol in two files "
                        "at once"
                    )
                symbols[record.key] = Symbol(
                    key=record.key, path=record.path, line=record.line
                )
                declaring_unit[record.key] = unit

        edges: list[Edge] = []
        holes: list[tuple[Symbol, str, str]] = []
        for _unit, _files, response in analyzed:
            if response.parse_error is not None:
                continue
            for wire in response.edges:
                caller = symbols.get(wire.caller)
                callee = symbols.get(_join_callee(wire.callee, symbols, qualifiers))
                # BOTH ends declared in the tree, which is CallGraph's own rule:
                # a call into the standard library is dropped, and the callback
                # PASSED to one survives as the reference edge to the callback.
                if caller is None or callee is None:
                    continue
                edges.append(
                    Edge(
                        caller=caller,
                        callee=callee,
                        kind=edge_kind_for_wire(wire.kind),
                        site=wire.site,
                    )
                )
            for wire in response.unresolved:
                holes.append((symbols[wire.caller], wire.site, wire.detail))

        # THE WHOLE-TREE EMPTINESS GUARD, at the only layer that can tell the
        # two apart. A unit that declares nothing is an answer; a tree in which
        # the sweep found Go files, every unit answered, and the union graph
        # holds zero symbols is the helper having stopped — and an empty graph
        # makes every subject FROM_NEITHER, so the failure is a flood rather
        # than a silence.
        if go_files and not symbols and not unreadable:
            raise _output_invalid(
                f"the sweep found {go_files} Go file(s) in {tree} and the union "
                "graph declares no symbol at all; 'this tree has no edges' and "
                "'the helper returned nothing' must not be the same answer"
            )

        return CallGraph(
            symbols={key: symbols[key] for key in sorted(symbols)},
            edges=tuple(sorted(edges, key=_edge_order)),
            unresolved_calls=tuple(sorted(holes, key=lambda hole: (hole[0].key, hole[1], hole[2]))),
            unreadable_paths=tuple(sorted(dict.fromkeys(unreadable))),
        )

    def test_root_predicate(self, symbol: Symbol) -> bool:
        """Is this symbol a Go test ENTRYPOINT? The naming half only.

        **The sixth function this scaffold implements rather than stubs**, by
        delegation: the rule is :func:`go_test_root_predicate` and this method
        is the protocol's face on it. The file half of the question is NOT asked
        here — it is ``seal_verify.is_test_path``, this repo's one matcher for
        "is this one of the tests", and two disagreeing notions of that is
        invariant 5's failure mode, which was live in this repo once already.

        The name is taken as the key's last segment after the receiver form is
        stripped, never the whole key: a key carries a module path, and a module
        whose name began with ``Test`` would otherwise make every symbol in it a
        test root.
        """
        member = symbol.key.rpartition(_KEY_PACKAGE_SEPARATOR)[2]
        return go_test_root_predicate(member)

    def test_id(self, symbol: Symbol) -> str:
        """``cmd/gates.TestSeal_G1_…`` — the row a human can run.

        CHOICE (the protocol does not carry this method yet, so writing it is a
        silence either way): **the row supplies it now.** Rejected alternative:
        omitting it until the protocol grows the member, which is the literal
        reading of "do not implement" and which leaves the escalated landing
        blocked on the one edit only a Go row can make. **The seventh function
        this scaffold implements rather than stubs, and it is ahead of the
        protocol on purpose.** D5 ruled (round 2,
        2026-08-11) that :class:`ReachabilityAnalyzer` GROWS this method,
        because :attr:`Seal.test_id` contracts the spelling as per-language and
        not-derived while no row had a channel to supply one — and then
        ESCALATED the landing, because requiring it in ``validate_analyzers``
        reddens every seal-file row that builds an analyzer double, and "what a
        Go row's ``test_id`` RETURNS is a claim about Go's spelling that a body
        may not write on the seal author's behalf".

        This is that claim, written by the row that owns it, where it can be
        argued with. It is Go's ``package.TestName`` — the spelling
        ``go test -run`` takes and the one the existing seals pin — derived from
        the symbol's declaring DIRECTORY rather than from its module path,
        because a human runs ``go test ./cmd/gates -run TestSeal_G1_…`` from a
        directory and not from an import path.

        It changes no verdict: ``test_id`` is a label on a finding and no
        dispatch reads it. Adding it here costs nothing today (the protocol does
        not require it, so nothing calls it) and means that when P3 lands D5's
        four coupled edits, the Go row is not what is blocking them.

        D5's interim ``_test_id`` yields the same string for a Go symbol and a
        useless one for a Python symbol; that is the defect the ruling names,
        and it is not this row's to fix.
        """
        directory = symbol.path.rpartition("/")[0]
        member = symbol.key.rpartition(_KEY_PACKAGE_SEPARATOR)[2]
        return f"{directory}{_KEY_PACKAGE_SEPARATOR}{member}" if directory else member


#: The row, instantiated and **NOT ENROLLED**. It exists so that a seal can hand
#: it to ``validate_analyzers`` and observe that a scaffolded row passes the
#: SHAPE check while its methods raise — which is the property D5 contracts and
#: which cannot be observed against a class nobody instantiated.
#:
#: Adding it to ``ANALYZERS`` is a separate decision with separate evidence, and
#: D5's import-time guard refuses it while this module's own path is off
#: ``FLOOR_GLOBS``. See WHAT IS OWED BEFORE ENROLMENT.
#:
#: WHAT THE TRACKED-BINARY QUESTION ACTUALLY IS
#: --------------------------------------------
#: CHOICE (three binaries in the acceptance repository are tracked at their
#: module's default output path and nothing warns about it, so a scaffold that
#: said nothing would be choosing by silence):
#: **RECOMMENDATION: the helper binary is NOT tracked. It is built once per
#: process into a temporary workspace and never written into the tree.**
#: Rejected alternative: tracking it beside ``main.go`` as ``cmd/*`` do, which
#: removes ``go`` from the gate's dependency list entirely — a real benefit,
#: since ``TOOLCHAIN_MISSING`` is otherwise reachable on any CI image without a
#: Go toolchain — and which is refused on points 1 and 2 below.
#:
#: The question is live because three binaries in the acceptance repository ARE
#: tracked, sitting at their module's default ``go build`` output path, warned
#: about nowhere. **Measured under** ``docs/explicit-state``, 2026-08-11, by
#: ``git ls-files`` plus a MIME probe: **nine** tracked ELF files under
#: ``cmd/``, totalling **44,054,262 bytes** —
#: ``classify/classify`` (3,916,741), ``deepseek/deepseek`` (8,962,883),
#: ``gates/gates`` (4,032,253), ``iterate/iterate`` (3,401,547),
#: ``recheck/recheck`` (3,465,388), ``repro/repro`` (3,863,975),
#: ``reviewer/deepseek`` (8,962,883), ``reviewer/main`` (4,073,497),
#: ``reviewer/reviewer`` (4,375,597). The repository ``.gitignore`` on that
#: branch is three lines and covers **none** of them.
#:
#: Three things follow, and only the first two are arguments against tracking:
#:
#:   1. **A tracked binary goes stale against its source, and this repository
#:      has paid for it.** Commit ``14560c5`` is titled "fix(reviewer): refresh
#:      stale cmd/reviewer/deepseek binary (had no -temperature flag)". And
#:      ``cmd/gates`` carries a whole seal about it —
#:      ``TestSeal_G1_TrackedBinary_IsRebuiltFromTheFixedSource`` — which execs
#:      ``./gates`` and fails when the committed artifact does not match the
#:      fixed source. A tracked artifact needs a seal to tell you it is current;
#:      a built one is current by construction.
#:   2. **The sibling already ruled it, on this gate path, for a reason that
#:      binds harder here.** ``_GO_HELPER_PREPARED`` records that the Go
#:      signature helper is built once per process into ``mkdtemp`` and cached
#:      in memory, "per PROCESS and never on disk between runs", because "a
#:      binary cached under ``/tmp`` across runs would be a file outside
#:      ``FLOOR_GLOBS`` whose bytes decide what a Go signature is". Bytes
#:      outside the floor that decide what a Go CALL GRAPH is are worse: this
#:      module's output is a ``Disposition.BREACH`` that blocks a branch.
#:      ``go_signature_fingerprint/`` accordingly tracks exactly two files,
#:      ``main.go`` and ``go.mod``, and no binary — **measured 2026-08-11.**
#:   3. **The nine tracked binaries are not a precedent for this one, because
#:      they are tracked for a reason this helper does not have.** Production
#:      EXECS them by path: ``roles/tasker.md``, ``README.md`` and
#:      ``skills/critical-review-dispatch.md`` all invoke
#:      ``cmd/reviewer/main`` directly, and ``cmd/gates``'s own seals name
#:      ``./gates`` as "the COMMITTED artifact ... it — not the source tree —
#:      is what production runs". Nothing execs this helper except the
#:      dispatcher, which can build it. Conflating the two populations is how
#:      the second one grows.
#:
#: The cost of the recommendation, so it is a decision: one ``go build`` per
#: gate process. The sibling measured it on the reference machine, 2026-08-09 —
#: **1.9 s with an empty ``GOCACHE``, 0.04 s warm** — against a build timeout
#: deliberately generous at 120 s, because what that bounds is a HUNG toolchain
#: and not a slow one.
#:
#: What is added instead of tracking, and it is one line: the module's default
#: ``go build`` output path is named in ``.gitignore`` — ``go-call-reachability``,
#: the MODULE PATH's last element and not the directory's, measured 2026-08-11
#: under go1.24.4 after a first line naming the directory ignored nothing — so
#: that the accident task #25
#: records — two authors destroying a tracked binary — cannot happen to this
#: directory by a stray ``go build`` in it. That is not machinery and it is not
#: a gate; it is the absence of a trap. ``go_signature_fingerprint/`` has no
#: such line and should get one in the same P4 round as its floor entry.
GO_REACHABILITY_ANALYZER = GoReachabilityAnalyzer()
