r"""D5 seals (P2) — call-site reachability.

Written against ``src/claude_dispatcher/call_site_reachability.py`` at
``685003b`` by an author who did not write the scaffold and does not write the
bodies. Every row below is either RED at HEAD — ten of the twelve contracts
raise :class:`NotImplementedError` — or, for the rows that pin the parts the
scaffold implemented on purpose (:data:`ANALYZERS`, :func:`validate_analyzers`,
:func:`analyzer_for_path`) and the rows that pin a STRUCTURAL property of the
module's own text, mutation-verified in a clone and named as such in its own
docstring.

THE DEFECT AND THE FIXTURE
==========================
*A seal proves a function BEHAVES, and nothing proves the function RUNS.*

The canonical instance is vendored, verbatim, under
``tests/fixtures/d5_b1_classify/`` — the real ``cmd/classify`` of
``claude-workflow`` at ``929d362``, in which ``ResolveConfigDual`` is
implemented at ``contract.go:742``, sealed by ``TestSeal_ResolveConfigDual``
(``contract_seal_test.go:852``) and its five siblings, and called from no
production path. Production goes ``main`` (``main.go:180``) →
``resolveConfigPath`` (``main.go:297``) → ``findConfig`` (``main.go:439``) →
``configCandidates`` (``main.go:401``), which takes the first candidate that
exists, so two differing money-path tables resolve silently to ``.agent``.

It is vendored rather than reconstructed because the two properties that make
it the right fixture are properties of the REAL text and a reconstruction would
be a shape this author chose:

  1. **The naive check certifies it.** ``contract.go:712`` opens the function's
     own doc comment with its own name, so "an exported func with no non-test
     mention" reports the defect CLEAN.
     :func:`test_the_naive_scan_certifies_the_canonical_defect` runs that scan
     over the vendored production set and asserts it does exactly that.
  2. **There is no import between the seal and its subject.** Both are
     ``package main`` in one directory. An import-based subject reader returns
     ZERO subjects for the exact defect it was built for, which is
     :func:`test_the_subject_reader_cannot_be_import_based`.

WHAT THESE SEALS DELIBERATELY DO NOT PIN
=========================================
**The ruling grid's cells.** The scaffold left :func:`adjudicate`'s
dispositions as prose in its docstring, following D3's P1, precisely so that a
P4 rules before a body pins them. No row below asserts that a given
``(Reach, PathQuality)`` pair maps to a named :class:`Disposition`. What IS
asserted, because the scaffold states it as a settled obligation rather than a
proposal, is that the dispatch is TOTAL, that it RAISES on an unknown member
and on every pair the grid does not name, that the three verdicts land in three
DIFFERENT buckets, and that a declaration moves at most one outcome.

**The declaration policy.** :class:`StagedDeclaration` makes
:attr:`Reach.FROM_TESTS_ONLY` appealable, diverging from D3's unappealable
precedent. That is a real ruling with a real cost and it is raised for P4 in
``RULING REQUESTS`` below; the rows here seal the MECHANISM's shape — matching
on both keys, staleness reported, abstentions untouchable, the accepted count
carried separately — and not the policy.

RULING REQUESTS FOR P4 — ALL EIGHT RULED, 2026-08-11
=====================================================
Each was raised at the row that met it and each is now answered. The requests
are kept verbatim below because a ruling is only readable against the question
it answered; the answer is appended to each. The rulings themselves live in
``call_site_reachability.py``, where a body author will meet them.

  R1  **STRUCK.** ``UndecidedReason.ANALYZER_FAULT`` is gone; the raises stand.
  R2  **BOTH LAYERS.** ``subjects_of_seal`` as a postcondition, ``check_tree``
      as a precondition; ``check_subject`` owes nothing and its mention struck.
  R3  **``subjects_of_seal`` WAS THE INTENT.** ``UNNAMEABLE`` yields a finding;
      ``SUBJECT_UNIDENTIFIED`` is live; ``check_tree``'s sentence was
      over-general and now splits by member.
  R4  **THE EMPTY TREE RETURNS.** The zero-roots raise is struck.
  R5  **ROOTS ARE INCLUDED**, mapped to ``()``, and a zero-edge chain is
      ``RESOLVED``. ``NO_ENTRYPOINT`` is still decided from the root set.
  R6  **BOTH FIGURES CORRECTED, NEITHER PINNED BY A ROW**, for different
      reasons — one is over frozen text, the other over the live tree.
  R7  **THE MECHANISM OWES A STATEMENT AND NOW MAKES ONE**: D5 must abstain
      over its own Python subjects, and the row's boolean and the closure rule
      are independent in both directions.
  R8  **RATIFIED WITH A CONDITION**: a declaration with no ``wiring`` is not a
      declaration.

THE ORIGINAL EIGHT
------------------
Each raised at the row that met it.

  R1. **``UndecidedReason.ANALYZER_FAULT`` has no production site.**
      :class:`AnalyzerFault` says "every member maps to
      :attr:`UndecidedReason.ANALYZER_FAULT`, i.e. to an ABSTENTION", but the
      only two functions that run an analyzer both RAISE on
      :class:`AnalyzerError`: :func:`discover_roots` ("if any analyzer raises
      AnalyzerError") and :func:`build_call_graph` ("an AnalyzerError that is
      not SourceUnreadable PROPAGATES, wrapped as
      :class:`CallSiteReachabilityError`"). So no run can produce that member,
      and a member no dispatch emits is the module's own stated failure — "a
      kind with no analyzer emitting it will never fire and will be read as
      coverage". Either the raise is right and the member is dead, or the
      member is right and one of the two contracts must abstain instead.
      :func:`test_an_analyzer_fault_never_reads_as_a_clean_tree` seals only
      what both readings agree on.

  R2. **A malformed :class:`Subject` is contracted to raise "at
      :func:`check_subject`", which cannot see one.** :class:`Subject`'s
      ``gap`` field says both contradictions "are
      :class:`CallSiteReachabilityError` at :func:`check_subject`", but
      :func:`check_subject` takes a :class:`Symbol` and has no ``Subject``
      parameter. Sealed at the only site that has one
      (:func:`subjects_of_seal` must never CONSTRUCT one) plus at
      :func:`check_tree`; the layer that owes the raise needs naming.

  R3. **``SubjectGap.UNNAMEABLE`` is contracted twice, incompatibly.**
      :func:`subjects_of_seal` says it "yields :attr:`Reach.UNDECIDED` /
      :attr:`UndecidedReason.SUBJECT_UNIDENTIFIED` at :func:`check_subject`,
      is counted, and is not suppressible"; :func:`check_tree` says "a seal
      that yields no subject is COUNTED, in ``subject_gaps``, and produces no
      finding". An UNNAMEABLE seal has no subject symbol, so there is nothing
      to pass to :func:`check_subject` and no finding can exist — which makes
      ``SUBJECT_UNIDENTIFIED`` a second member with no production site (see
      R1). The rows here seal the intersection: it is counted, it is visible,
      and it never lands in a passing bucket.

  R4. **"A report assembled over zero roots" raises, and an empty tree does
      not.** :class:`CallSiteReachabilityError` lists the first; the CHOICE on
      :func:`check_tree` rules the second explicitly ("an empty tree returns a
      report with ``seals_examined=0``, and does NOT raise"). An empty tree has
      zero roots. :func:`test_an_empty_run_is_distinguishable_from_a_clean_one`
      accepts either and pins the property both share.

  R5. **Does :func:`reachable_from` include the roots themselves?** It decides
      whether ``production_reach == {}`` means "no production root" or "the
      production roots call nothing", and :func:`check_subject` step 2 turns
      the first into NO_ENTRYPOINT — an abstention over every subject in the
      tree. :func:`test_no_entrypoint_is_a_fact_about_the_root_set` seals that
      the two must not be the same answer; which convention delivers it is P4's.

  R6. **The scaffold's ``27 mentions`` does not reproduce.** At ``929d362``
      the identifier occurs **31** times across ``*_test.go`` (11 in
      ``contract_seal_test.go``, 20 in ``repair_seal_test.go``) and **12** of
      those are call expressions. 27 is neither. The number is narrative in the
      scaffold and nothing turns on it, so no row pins it; the reproducible
      facts are pinned instead, at
      :func:`test_the_canonical_fixture_is_the_measured_artifact`.

  R7. **The ``getattr`` measurement does not reproduce either, and the miss is
      in the interesting direction.** The scaffold records "100 ``getattr(``
      call sites, six of them with a non-literal attribute name, three of those
      six inside ``fixture_reachability``". Measured by AST on this worktree:
      **105** call sites, **4** non-literal, **3** of them in
      ``fixture_reachability`` — and the fourth is
      ``call_site_reachability.validate_analyzers`` itself, line 726. The
      claim's shape survives; its arithmetic does not. Sealed as the invariant
      at :func:`test_the_python_row_is_false_because_this_repo_resolves_names_dynamically`.

  R8. **``StagedDeclaration`` makes a BREACH appealable.** Recorded, not
      sealed. An appealable BREACH is a BREACH someone can talk their way out
      of, and the scaffold's own argument for it — that scaffold-first
      MANUFACTURES this state, and that a B1 author writing the ``wiring``
      sentence would have found the bug in the act of writing it — is a policy
      claim this file has no standing to ratify. What is sealed is that the
      appeal is expensive and visible: both keys must match, staleness is
      reported, ``ACCEPTED`` is counted apart from ``OK``, and no declaration
      can touch an abstention or a quality.

NON-VACUITY
===========
Five shapes are measured on this codebase and every row below is written
against them:

  * *green on an unproducible input* — every fixture here is the vendored real
    tree or a graph whose symbols, paths and lines are pinned against it by
    :func:`test_the_canonical_fixture_is_the_measured_artifact`;
  * *a pass condition satisfiable by executing nothing* — no row skips, no row
    is conditional on the environment, and every red row names the specific
    defect that reddens it rather than resting on
    :class:`NotImplementedError`;
  * *green on an incidental substring* — the live hazard for a mechanism whose
    whole job is name resolution. Every fixture graph carries a decoy symbol
    whose ``key`` CONTAINS the subject's key
    (``…classify.ResolveConfigDualDocComment``), reached from production; an
    implementation that matched by substring answers FROM_PRODUCTION for the
    canonical defect and reddens;
  * *a collapsed input space* — every verdict row carries its opposite as an
    in-test control judged in the same call, so neither a
    constantly-BREACH nor a constantly-OK mechanism passes;
  * *a recording that measures a frozen artifact* — the vendored fixture is an
    INPUT, never the thing measured; the measurement rows
    (:func:`test_the_module_declares_no_file_extension_and_calls_no_endswith`,
    :func:`test_the_python_row_is_false_because_this_repo_resolves_names_dynamically`)
    run over the LIVE ``src/`` tree and each carries a positive control proving
    the sweep can still find what it is looking for.

Two more shapes have since been measured on this codebase and PART 11 is
written against all seven: *a test reading through the same struct shape that
caused the loss*, and *a seal asserting truthiness of a value now known to be
wrong*. Part 11's rows read through no shared helper the module under seal also
reads — the reach maps, root records and graphs they hand in are written out in
this file — and none of them asserts that a value is merely truthy.

PART 11 — THE SECOND PASS
=========================
Everything above was written before a body existed. Part 11 was written after
one did, against the eight mutations ``feat/D5-body2`` ran that reddened NOTHING
and disclosed against its own interest, plus the properties the round-2 rulings
made pinnable for the first time. Its rows are GREEN at HEAD — the body is
implemented — so each of them is verified by the mutation it names rather than
by an unimplemented stub, and each names that mutation and what it measured.

JOINT SATISFIABILITY, AND THE EVIDENCE THAT EACH ROW IS RED FOR ITS OWN REASON
==============================================================================
At HEAD every row that touches a contract is red with
:class:`NotImplementedError`, and *"red because the function raises"* is not
evidence that the row would catch the defect it names. So both claims were
measured in a throwaway clone (``.git`` removed first; ``__pycache__`` cleared
between every run, because CPython keys bytecode on ``(mtime_seconds, size)``
and a same-size mutation restored inside one second is reported as covered when
it is not):

  * **Jointly satisfiable.** A reference implementation of the ten stubs and of
    ``Symbol``'s identity — about 300 lines, thrown away — turns all 70 rows
    green together. No row contradicts another and none is unsatisfiable.
  * **Each red row is red for the defect it names.** Forty mutations were then
    injected one at a time into that green baseline, one per "Reddens under a
    body on:" clause below, and every one of them reddened the rows that name
    it and no others. Four of the first thirty-eight did NOT, and each was a
    real weakness in a row rather than in the mutation — a fixture with one
    finding cannot detect a mis-sorted report, and a fixture with one seal
    cannot detect an import-based reader that happens to be right about it.
    Those rows were strengthened (a second seal whose discovery order and
    sorted order disagree; a decoy the containment reader must not pull in)
    rather than the mutations weakened.

    **P4 ROUND 3 (2026-08-11) — "every one of them" IS FALSE, and it is struck.
    Measured, not argued.** Swallowing the :class:`AnalyzerError` in
    :func:`discover_roots` — a mutation named verbatim by
    :func:`test_discover_roots_refuses_a_tree_it_cannot_sweep`'s clause — was
    injected into ``feat/D5-seals2`` @ ``4e66a01`` in a clone with the ``.git``
    FILE removed and ``__pycache__`` cleared. It reddens the six
    parametrisations of
    :func:`test_discover_roots_raises_on_a_fault_without_help_from_the_graph_builder`
    and **nothing else in this file** — not the row whose clause names it,
    which never hands :func:`discover_roots` a raising analyzer and therefore
    could not have detected that mutation under the reference implementation
    either. So the sentence was wrong when it was written, not merely stale.

    The second half of the claim expired independently: the reference
    implementation those forty mutations ran against **was thrown away**, and
    the body that shipped on ``feat/D5-body2`` is not it. Counted at
    ``4e66a01``: **43** rows carry a ``Reddens under`` clause, **12** of them
    (all in PART 11) record a measurement against the shipped body, and **31**
    record one only against the discarded reference. See the P4 round-3 ruling
    on the clause convention in ``call_site_reachability.py``.
"""

from __future__ import annotations

import ast
import re
import shutil
from collections.abc import Mapping
from pathlib import Path

import pytest

from claude_dispatcher import call_site_reachability as csr
from claude_dispatcher.call_site_reachability import (
    ANALYZERS,
    AnalyzerFault,
    AnalyzerUnavailable,
    CallGraph,
    CallSiteReachabilityError,
    Disposition,
    Edge,
    EdgeKind,
    EntrypointKind,
    IMPORTS_NOT_SUPPLIED,
    Finding,
    ImportRelation,
    ImportsUnavailable,
    PackageImports,
    PathQuality,
    Reach,
    ReachabilityReport,
    Root,
    RootKind,
    Seal,
    SourceUnreadable,
    StagedDeclaration,
    Subject,
    SubjectGap,
    Symbol,
    UndecidedReason,
    adjudicate,
    analyzer_for_path,
    build_call_graph,
    check_subject,
    check_tree,
    discover_roots,
    discover_seals,
    holes_in_scope,
    import_components,
    reachable_from,
    subjects_of_seal,
    validate_analyzers,
    validate_import_relation,
)
from claude_dispatcher.role_protocol import COMPARATORS, Language, support_for_path

_TESTS_DIR = Path(__file__).resolve().parent
_REPO = _TESTS_DIR.parent
_SRC = _REPO / "src" / "claude_dispatcher"

#: The vendored canonical fixture. See its ``PROVENANCE.md``.
_FIXTURE = _TESTS_DIR / "fixtures" / "d5_b1_classify"

#: ``cmd/classify``'s module path, read off the recorded ``go.mod``. Every
#: ``Symbol.key`` below is spelled from it, because the scaffold requires keys
#: to be fully qualified — ``main`` is the package name of all seven ``cmd/``
#: binaries and a bare key would collide across them.
_MOD = "github.com/yourorg/claude-workflow/classify"

#: The five production files of ``cmd/classify`` and the one test file that
#: carries the subject's own seals, as vendored. The other six files at
#: ``929d362`` are recorded in ``PROVENANCE.md``; only ``repair_seal_test.go``
#: among them mentions the subject at all.
_PRODUCTION_FILES = (
    "capability.go",
    "contract.go",
    "init.go",
    "main.go",
    "readset.go",
)
_TEST_FILES = ("contract_seal_test.go",)

_SUBJECT_NAME = "ResolveConfigDual"


# --------------------------------------------------------------------------- #
# Helpers — test doubles and fixture builders.
#
# None of these is an implementation of anything in the module under seal. The
# analyzer doubles answer with data this file wrote down; the graph builders
# assemble that data into the dataclasses the contracts name. The one place
# real text is read is the two sweeps, which read it to MEASURE, never to
# decide.
# --------------------------------------------------------------------------- #


def _sym(name: str, path: str, line: int) -> Symbol:
    return Symbol(key=f"{_MOD}.{name}", path=f"cmd/classify/{path}", line=line)


#: Every symbol below carries the file and line it really has at ``929d362``;
#: :func:`test_the_canonical_fixture_is_the_measured_artifact` pins each one
#: against the vendored text, so this block cannot drift into fiction.
_SUBJECT = _sym(_SUBJECT_NAME, "contract.go", 742)
_SEAL_FN = _sym("TestSeal_ResolveConfigDual", "contract_seal_test.go", 852)
_MAIN = _sym("main", "main.go", 180)
_RESOLVE_CONFIG_PATH = _sym("resolveConfigPath", "main.go", 297)
_FIND_CONFIG = _sym("findConfig", "main.go", 439)
_CONFIG_CANDIDATES = _sym("configCandidates", "main.go", 401)
_LOAD_CONFIG = _sym("loadConfig", "main.go", 486)

#: **The substring decoy, and it is the sharpest control in this file.** Its
#: key CONTAINS the subject's key in full, it is declared in production, and
#: production reaches it. A mechanism that decides reachability by asking
#: whether the subject's name occurs among the reached keys — the shape that
#: made an authorisation seal pass because an error message happened to contain
#: ``ProtocolGenesis`` — answers FROM_PRODUCTION for the canonical defect and
#: reddens every verdict row below.
#:
#: It is synthetic, and it is the one synthetic symbol here. The real tree has
#: no such pair; the hazard it controls for is a property of the CHECKER, not
#: of the tree, so a fixture that cannot express it cannot control for it.
_DECOY = _sym(_SUBJECT_NAME + "DocComment", "main.go", 512)

#: A test-declared symbol whose key also contains the subject's, so the same
#: substring hazard is controlled for on the SUBJECT-READING side as well as on
#: the traversal side.
_TEST_HELPER = _sym(
    _SUBJECT_NAME + "Fixture", "contract_seal_test.go", 880
)


def _edge(caller: Symbol, callee: Symbol, kind: EdgeKind = EdgeKind.DIRECT) -> Edge:
    return Edge(caller=caller, callee=callee, kind=kind, site=f"{caller.path}:{caller.line}")


#: The production chain as it really runs, and the whole point of it is what it
#: does NOT contain: no edge anywhere reaches ``_SUBJECT``.
_PRODUCTION_EDGES = (
    _edge(_MAIN, _RESOLVE_CONFIG_PATH),
    _edge(_RESOLVE_CONFIG_PATH, _FIND_CONFIG),
    _edge(_FIND_CONFIG, _CONFIG_CANDIDATES),
    _edge(_FIND_CONFIG, _LOAD_CONFIG),
    _edge(_MAIN, _DECOY),
)

#: The seal's own edge to its subject. This is the edge whose EXISTENCE makes
#: the subject a subject and whose EXCLUSIVITY makes it the defect.
_SEAL_EDGES = (
    _edge(_SEAL_FN, _SUBJECT),
    _edge(_SEAL_FN, _TEST_HELPER),
)

_ALL_SYMBOLS = (
    _SUBJECT,
    _SEAL_FN,
    _MAIN,
    _RESOLVE_CONFIG_PATH,
    _FIND_CONFIG,
    _CONFIG_CANDIDATES,
    _LOAD_CONFIG,
    _DECOY,
    _TEST_HELPER,
)

_SEAL = Seal(symbol=_SEAL_FN, test_id="cmd/classify.TestSeal_ResolveConfigDual")

_GO_MAIN_ROOT = Root(
    symbol=_MAIN,
    kind=EntrypointKind.GO_MAIN,
    root_kind=RootKind.PRODUCTION,
    evidence="cmd/classify/main.go:180 func main, package main",
)
_TEST_ROOT = Root(
    symbol=_SEAL_FN,
    kind=EntrypointKind.TEST_FUNCTION,
    root_kind=RootKind.TEST,
    evidence="cmd/classify/contract_seal_test.go:852 func TestSeal_ResolveConfigDual",
)


def _graph(
    *,
    symbols=_ALL_SYMBOLS,
    edges=_PRODUCTION_EDGES + _SEAL_EDGES,
    unresolved=(),
    unreadable=(),
) -> CallGraph:
    return CallGraph(
        symbols={s.key: s for s in symbols},
        edges=tuple(edges),
        unresolved_calls=tuple(unresolved),
        unreadable_paths=tuple(unreadable),
    )


def _chain(*edges: Edge) -> tuple[Edge, ...]:
    return tuple(edges)


def _production_reach(**extra) -> dict[str, tuple[Edge, ...]]:
    """What a traversal from ``_GO_MAIN_ROOT`` really yields over ``_graph()``.

    Written out rather than computed, because :func:`reachable_from` is one of
    the contracts under seal and a row that fed :func:`check_subject` the
    output of a function this file is also sealing would be green whenever the
    two agreed with each other and wrong together.
    """
    reach = {
        _MAIN.key: (),
        _RESOLVE_CONFIG_PATH.key: _chain(_PRODUCTION_EDGES[0]),
        _FIND_CONFIG.key: _chain(*_PRODUCTION_EDGES[:2]),
        _CONFIG_CANDIDATES.key: _chain(*_PRODUCTION_EDGES[:3]),
        _LOAD_CONFIG.key: _chain(_PRODUCTION_EDGES[0], _PRODUCTION_EDGES[1], _PRODUCTION_EDGES[3]),
        _DECOY.key: _chain(_PRODUCTION_EDGES[4]),
    }
    reach.update(extra)
    return reach


def _test_reach(**extra) -> dict[str, tuple[Edge, ...]]:
    reach = {
        _SEAL_FN.key: (),
        _SUBJECT.key: _chain(_SEAL_EDGES[0]),
        _TEST_HELPER.key: _chain(_SEAL_EDGES[1]),
    }
    reach.update(extra)
    return reach


class _Analyzer:
    """A :class:`ReachabilityAnalyzer` double: data in, the same data out.

    It is a double and not a stub-that-happens-to-work: ``roots`` and ``graph``
    return exactly what the row was constructed with. The module's dispatch is
    what is under seal, never the analysis.
    """

    def __init__(
        self,
        language: Language,
        negative_is_conclusive: bool,
        *,
        roots: tuple[Root, ...] = (_GO_MAIN_ROOT, _TEST_ROOT),
        graph: CallGraph | None = None,
        raises: Exception | None = None,
        test_prefixes: tuple[str, ...] = ("Test", "Benchmark", "Fuzz", "Example"),
    ) -> None:
        self._language = language
        self._negative = negative_is_conclusive
        self._roots = roots
        self._graph = graph if graph is not None else _graph()
        self._raises = raises
        self._test_prefixes = test_prefixes

    @property
    def language(self) -> Language:
        return self._language

    @property
    def negative_is_conclusive(self) -> bool:
        return self._negative

    def roots(self, tree: Path) -> tuple[Root, ...]:
        if self._raises is not None:
            raise self._raises
        return self._roots

    def graph(self, tree: Path) -> CallGraph:
        if self._raises is not None:
            raise self._raises
        return self._graph

    def test_root_predicate(self, symbol: Symbol) -> bool:
        name = symbol.key.rpartition(".")[2]
        return any(name.startswith(p) for p in self._test_prefixes)


def _go(**kwargs) -> _Analyzer:
    """Go's row: ``negative_is_conclusive`` is True, per the language."""
    return _Analyzer(Language.GO, True, **kwargs)


def _python(**kwargs) -> _Analyzer:
    """Python's row: ``negative_is_conclusive`` is False, per the language."""
    return _Analyzer(Language.PYTHON, False, **kwargs)


def _finding(
    reach: Reach,
    quality: PathQuality,
    *,
    reason: UndecidedReason | None = None,
    path=None,
    detail: str = "",
    subject: Symbol = _SUBJECT,
    seal: Seal = _SEAL,
) -> Finding:
    return Finding(
        seal=seal,
        subject=subject,
        reach=reach,
        quality=quality,
        path=path,
        test_path=None,
        reason=reason,
        detail=detail,
    )


def _declaration(
    *,
    test_id: str = _SEAL.test_id,
    subject_key: str = _SUBJECT.key,
    wiring: str = "SMG-0000 will call it from resolveConfigPath",
) -> StagedDeclaration:
    return StagedDeclaration(
        test_id=test_id,
        subject_key=subject_key,
        wiring=wiring,
        reason="staged behind the config-path repair",
    )


def _judge(
    subject: Symbol,
    *,
    analyzer: _Analyzer | None = None,
    graph: CallGraph | None = None,
    production_reach=None,
    test_reach=None,
    roots: tuple[Root, ...] = (_GO_MAIN_ROOT, _TEST_ROOT),
) -> Finding:
    """One pair judged, against the SAME two root records the reach maps use.

    AMENDED by P4 round 2 (2026-08-11), under the ruling that struck
    ``_synthetic_root``. This helper used to omit ``roots`` and take
    :func:`check_subject`'s default, which made the module SYNTHESISE the
    :class:`Root` on every ``CallPath`` these rows produce — so
    ``dark.test_path.root`` below was an assertion about a record the module
    invented for this helper's benefit, and the production side of that
    synthesis had no caller outside this file. Passing the records the reach
    maps were written from is not a widening: ``_production_reach`` originates
    every chain at ``_MAIN`` and ``_test_reach`` at ``_SEAL_FN``, which are
    exactly ``_GO_MAIN_ROOT.symbol`` and ``_TEST_ROOT.symbol``, so every row
    below now checks a real record and none of their verdicts move.
    """
    return check_subject(
        _SEAL,
        subject,
        graph=graph if graph is not None else _graph(),
        production_reach=_production_reach() if production_reach is None else production_reach,
        test_reach=_test_reach() if test_reach is None else test_reach,
        analyzer=analyzer if analyzer is not None else _go(),
        roots=roots,
    )


def _tree(tmp_path: Path) -> Path:
    """A working copy of the vendored fixture, outside the repository.

    A copy rather than the fixture itself, so that
    :func:`test_check_tree_never_writes_into_the_tree_under_check` can be a
    real row without a buggy body being able to damage the fixture every other
    row rests on.
    """
    dest = tmp_path / "cmd" / "classify"
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(_FIXTURE, dest)
    return tmp_path


def _snapshot(tree: Path) -> dict[str, bytes]:
    return {
        str(p.relative_to(tree)): p.read_bytes()
        for p in sorted(tree.rglob("*"))
        if p.is_file()
    }


# --------------------------------------------------------------------------- #
# The two sweeps. Both read text to MEASURE. Neither is consulted by any
# assertion about a verdict, and neither is a parser of anything the module
# under seal parses.
# --------------------------------------------------------------------------- #

#: A string constant is EXTENSION-SHAPED when it carries no whitespace and ends
#: in a dot followed by one to five ASCII alphanumerics: ``".py"``, ``".tsx"``,
#: ``"_test.go"``. Prose that happens to name a file — the module's own
#: ``"…from skills/explicit-state.md applied to…"`` — carries spaces and is not
#: matched, which is the distinction that makes this sweep about CODE.
_EXTENSION_SHAPED = re.compile(r"^\S*\.[A-Za-z0-9]{1,5}$")


def _docstring_constants(tree: ast.AST) -> set[int]:
    """``id()`` of every string constant that is a docstring or a bare literal.

    A docstring is an :class:`ast.Expr` whose value is a string constant, which
    is also exactly the shape of a bare string used as a comment. Both are
    prose. Excluding them by SHAPE rather than by position is what lets the
    sweep say "a comment must neither satisfy nor trip it" and mean it — a
    ``#`` comment is not in the AST at all, and a ``#:`` doc-comment even less
    so, and this covers the third form.
    """
    out: set[int] = set()
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            if (
                isinstance(child, ast.Expr)
                and isinstance(child.value, ast.Constant)
                and isinstance(child.value.value, str)
            ):
                out.add(id(child.value))
    return out


def _extension_literals(source: str) -> list[tuple[int, str]]:
    """Every extension-shaped string constant in ``source`` that is not prose."""
    tree = ast.parse(source)
    prose = _docstring_constants(tree)
    found = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in prose
            and _EXTENSION_SHAPED.match(node.value)
        ):
            found.append((node.lineno, node.value))
    return sorted(found)


def _endswith_sites(source: str) -> list[int]:
    """Every ``<expr>.endswith(...)`` CALL in ``source``. Lines, sorted."""
    tree = ast.parse(source)
    return sorted(
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "endswith"
    )


def _dynamic_getattr_sites(source: str) -> list[int]:
    """``getattr(obj, <not a literal>)`` call sites. Lines, sorted.

    The construct that makes Python's ``negative_is_conclusive`` False: a
    symbol referenced nowhere statically can still be reached, so "no path" is
    not a fact about the language.
    """
    tree = ast.parse(source)
    return sorted(
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "getattr"
        and len(node.args) >= 2
        and not isinstance(node.args[1], ast.Constant)
    )


def _naive_exported_scan(production: dict[str, str]) -> set[str]:
    r"""The scaffold's own first crude scan, reconstructed exactly.

    *"An exported func with no non-test mention."* Written out here so the row
    that uses it demonstrates the shortcut rather than asserting it, and kept
    deliberately dumb: it is the check this module must not be reducible to,
    not a check anybody should improve.

    Returns the set of exported function names it reports as CLEAN — i.e. as
    having a non-test mention and therefore needing no attention.
    """
    declared = set()
    for text in production.values():
        declared.update(re.findall(r"^func ([A-Z]\w*)\(", text, flags=re.M))
    clean = set()
    for name in declared:
        mentions = sum(text.count(name) for text in production.values())
        declaring = sum(
            len(re.findall(rf"^func {name}\(", text, flags=re.M))
            for text in production.values()
        )
        if mentions - declaring > 0:
            clean.add(name)
    return clean


def _refined_scan(production: dict[str, str], name: str) -> int:
    """Mentions in non-comment, non-declaration production lines. The scan the
    scaffold records as an ORDER OF MAGNITUDE and explicitly not as a finding.
    """
    count = 0
    for text in production.values():
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("//") or stripped.startswith(f"func {name}("):
                continue
            count += line.count(name)
    return count


def _read(names, *, where: Path = _FIXTURE) -> dict[str, str]:
    return {n: (where / n).read_text(encoding="utf-8") for n in names}


# --------------------------------------------------------------------------- #
# Part 0 — the fixture is the measured artifact, and the naive check certifies
# it. GREEN at HEAD: these rows pin the INPUT, not the mechanism.
# --------------------------------------------------------------------------- #


def test_the_canonical_fixture_is_the_measured_artifact():
    """Every symbol this file hand-writes is where the real tree puts it.

    The hand-built graph above is the stand-in for what a Go analyzer would
    emit, and a stand-in nobody pins is fiction. This is the two-way pin: each
    ``Symbol``'s ``path`` and ``line`` is checked against the vendored text,
    and the two facts that make the fixture canonical are checked with it —
    ``ResolveConfigDual`` occurs exactly twice in the whole production set, and
    both occurrences are in ``contract.go``.

    R6: the scaffold's ``27 mentions in *_test.go`` does NOT reproduce. It is
    31 by identifier and 12 by call expression at ``929d362``. Nothing turns on
    the number and no row pins it; this row pins what does reproduce.

    Reddens on: editing any vendored file; moving a declaration; a production
    call site being added to ``ResolveConfigDual`` (which would be the fix, and
    which must redden this row so the fixture is retired rather than silently
    becoming a different fixture).
    """
    production = _read(_PRODUCTION_FILES)
    tests = _read(_TEST_FILES)

    for symbol in (
        _SUBJECT,
        _MAIN,
        _RESOLVE_CONFIG_PATH,
        _FIND_CONFIG,
        _CONFIG_CANDIDATES,
        _LOAD_CONFIG,
    ):
        name = symbol.key.rpartition(".")[2]
        filename = symbol.path.rpartition("/")[2]
        lines = production[filename].splitlines()
        assert lines[symbol.line - 1].startswith(
            f"func {name}("
        ), f"{symbol.path}:{symbol.line} is not the declaration of {name}"

    seal_lines = tests["contract_seal_test.go"].splitlines()
    assert seal_lines[_SEAL_FN.line - 1].startswith("func TestSeal_ResolveConfigDual(")

    # The subject is exported, which is what makes the rejected
    # "exported surface is a root" rule certify the defect.
    assert _SUBJECT_NAME[0].isupper()

    occurrences = {n: t.count(_SUBJECT_NAME) for n, t in production.items()}
    assert occurrences == {
        "capability.go": 0,
        "contract.go": 2,
        "init.go": 0,
        "main.go": 0,
        "readset.go": 0,
    }, f"the production side of the fixture moved: {occurrences}"

    # Both production occurrences are the shortcut: one opens the doc comment,
    # one is the declaration. Neither is a call.
    contract_lines = production["contract.go"].splitlines()
    hits = [i + 1 for i, l in enumerate(contract_lines) if _SUBJECT_NAME in l]
    assert hits == [712, 742], hits
    assert contract_lines[711].startswith(f"// {_SUBJECT_NAME} "), contract_lines[711]
    assert contract_lines[741].startswith(f"func {_SUBJECT_NAME}(")
    assert production["contract.go"].count(f"{_SUBJECT_NAME}(") == 1

    # And the test side really does exercise it, repeatedly.
    assert tests["contract_seal_test.go"].count(f"{_SUBJECT_NAME}(") >= 6

    # The seal and its subject share a package and there is no import between
    # them. This is the trap that defeats an import-based subject reader.
    assert "package main" in tests["contract_seal_test.go"]
    assert "package main" in production["contract.go"]


def test_the_naive_scan_certifies_the_canonical_defect():
    """*"An exported func with no non-test mention"* reports the defect CLEAN.

    The sharpest available proof of anti-requirement 1, run rather than
    asserted: ``contract.go:712`` opens the function's own doc comment with its
    own name, so the scan counts a non-test mention and moves on. A mechanism
    that can be defeated by a comment is not a mechanism, and every verdict row
    below is written so that no such shortcut satisfies it.

    The refined scan — non-comment, non-declaration production lines — is the
    control, and it must find ZERO, because the two mentions are precisely a
    comment and a declaration. That pair is the whole finding: the naive scan
    says clean, the refined scan says nothing at all, and only a call graph
    can tell either of them apart from a function production really calls.

    Measured here, and it is worse than the scaffold claims: the scan certifies
    **all fourteen** exported functions in the production set, seven of which
    the refined scan scores ``prod=0``. Go's doc-comment convention starts a
    comment with the name of the thing it documents, so on idiomatic Go this
    check has no discriminating power AT ALL — it is not a check with a blind
    spot, it is a check that always says yes.

    Two controls, because "everything came back clean" is also what a broken
    scan returns:

      * a synthetic exported function with no doc comment and no other mention
        must NOT come back clean, so the scan can still say no;
      * the refined scan must separate the subject from a live neighbour —
        ``ResolveConfigDual`` scores 0 and ``V2SidecarPath`` scores 3 — which
        is the scaffold's recorded order-of-magnitude, reproduced. And it is
        still not a finding: a grep cannot say whether any of those three lines
        runs, which is the whole reason this module is a call graph.

    Reddens on: a production call site landing on ``ResolveConfigDual``; the
    doc comment being reworded so it no longer opens with the name (which
    would make the naive scan CORRECT here and retire this fixture).
    """
    production = _read(_PRODUCTION_FILES)

    clean = _naive_exported_scan(production)
    assert _SUBJECT_NAME in clean, (
        "the naive scan no longer certifies the canonical defect, so this "
        "fixture no longer demonstrates anti-requirement 1"
    )
    declared = set()
    for text in production.values():
        declared.update(re.findall(r"^func ([A-Z]\w*)\(", text, flags=re.M))
    assert clean == declared and len(declared) == 14, (
        f"the naive scan certified {len(clean)} of {len(declared)} exported "
        "functions; the measured fact is that it certifies every one of them"
    )

    orphan = dict(production)
    orphan["orphan.go"] = "package main\n\nfunc Orphan(x int) int {\n\treturn x\n}\n"
    assert "Orphan" not in _naive_exported_scan(orphan), (
        "the positive control failed: the naive scan cannot say no to anything, "
        "so its verdict on the subject above proves nothing"
    )

    assert _refined_scan(production, _SUBJECT_NAME) == 0
    assert _refined_scan(production, "V2SidecarPath") == 3, (
        "the refined scan no longer separates the subject from a live "
        "neighbour, so 0 above is not a measurement"
    )


# --------------------------------------------------------------------------- #
# Part 1 — ANALYZERS is empty and empty is a claim.
#
# The four rows over validate_analyzers and analyzer_for_path are GREEN at
# HEAD; the scaffold implements both on purpose and says why. Each names the
# mutation that reddens it, measured in a clone.
# --------------------------------------------------------------------------- #


def test_analyzers_is_empty_and_no_path_in_any_tree_can_be_analyzed():
    """The table is empty, so every path — including the enrolled ones — has
    no analyzer, and ``analyzer_for_path`` says so by returning None.

    Empty is a claim: not "nobody thought about the languages" but "no analyzer
    has been WRITTEN". The claim is only worth something if the lookup really
    is keyed on the table, which is the second half of this row: a ``.go`` path
    resolves to a ``COMPARATORS`` row and STILL gets no analyzer, and that is a
    different fact from ``.sql``, which resolves to nothing at all.

    Reddens on: enrolling any row (which is what makes this a live tripwire on
    an unenrolled mechanism rather than a tautology).
    """
    assert ANALYZERS == ()
    assert csr.ANALYZERS == ()

    for path in ("src/claude_dispatcher/risk.py", "cmd/classify/main.go", "web/app.ts"):
        assert support_for_path(path) is not None, f"{path} lost its COMPARATORS row"
        assert analyzer_for_path(path) is None, f"{path} acquired an analyzer"

    for path in ("store/queries/x.sql", "Main.java", "README"):
        assert support_for_path(path) is None
        assert analyzer_for_path(path) is None


def test_analyzer_for_path_holds_no_second_extension_table(monkeypatch):
    """The lookup asks ``support_for_path`` and reads ``ANALYZERS``; nothing else.

    With a row enrolled for each enrolled language, ``analyzer_for_path`` must
    agree with ``support_for_path`` on EVERY extension in ``COMPARATORS`` and
    on nothing outside it. That is the property that keeps exactly one place in
    this codebase deciding what language a file is, and it is why this function
    is implemented in the scaffold rather than stubbed.

    Reddens on: keying the loop on anything but ``support.language``; adding an
    extension test of D5's own (measured in a clone by giving the lookup a
    ``path.endswith('.go')`` fast path, which then disagrees with
    ``support_for_path`` on ``x.cgo``-shaped near misses).
    """
    rows = tuple(_Analyzer(row.language, True) for row in COMPARATORS)
    monkeypatch.setattr(csr, "ANALYZERS", rows)
    by_language = {row.language: row for row in rows}

    for support in COMPARATORS:
        for extension in support.extensions:
            path = f"pkg/thing{extension}"
            assert analyzer_for_path(path) is by_language[support.language]
            # And the two lookups cannot disagree about what the file IS.
            assert support_for_path(path).language is support.language

    for path in ("pkg/thing.sql", "pkg/thing.PY", "pkg/thing"):
        assert support_for_path(path) is None
        assert analyzer_for_path(path) is None


@pytest.mark.parametrize(
    ("rows", "expected_in_message"),
    [
        pytest.param(
            (_Analyzer("go", True),),
            "does not carry a Language member",
            id="not-a-Language",
        ),
        pytest.param(
            (_Analyzer(Language.GO, True), _Analyzer(Language.GO, False)),
            "two analyzer rows",
            id="two-rows-one-language",
        ),
        pytest.param(
            (_Analyzer(Language.GO, "false"),),
            "negative_is_conclusive",
            id="truthy-non-bool",
        ),
        pytest.param(
            (_Analyzer(Language.GO, 1),),
            "negative_is_conclusive",
            id="int-for-bool",
        ),
    ],
)
def test_validate_analyzers_refuses_a_registry_that_could_answer_twice(
    rows, expected_in_message
):
    """A malformed row is a mechanism error at import, never a runtime surprise.

    The ``"false"`` and ``1`` cases are not pedantry and the scaffold says so:
    ``negative_is_conclusive`` is the ONE field that decides whether this module
    may emit a BREACH, and ``bool("false")`` is this repo's recorded coercion
    defect. A truthy non-bool on a Python row would let Python code be
    BREACHed on a claim the language does not support.

    Reddens on: dropping any of the four checks; replacing
    ``isinstance(..., bool)`` with a truthiness test (measured in a clone —
    the ``"false"`` and ``1`` rows both go green).
    """
    with pytest.raises(CallSiteReachabilityError) as exc:
        validate_analyzers(rows)
    assert expected_in_message in str(exc.value)


def test_validate_analyzers_refuses_a_row_no_path_can_reach():
    """A row for a language with no ``COMPARATORS`` entry is refused.

    ``analyzer_for_path`` goes through ``support_for_path``, so a language
    absent from ``COMPARATORS`` can never select its analyzer. The row would be
    coverage that reads as coverage and is not — D1's own sentence about an
    empty ``extensions``.

    Rather than invent a ``Language`` member that does not exist, this row
    removes the comparator: with ``COMPARATORS`` holding only Python, a Go
    analyzer row is unreachable and must be refused.

    Reddens on: dropping the enrolment check; reading
    ``PENDING_COMPARATORS`` as well (measured in a clone — a pending row is not
    coverage, and a lookup that consulted it would report a language readable
    while its reader raises).
    """
    python_only = tuple(r for r in COMPARATORS if r.language is Language.PYTHON)
    assert python_only, "COMPARATORS lost its Python row"

    original = csr.COMPARATORS
    try:
        csr.COMPARATORS = python_only  # the name validate_analyzers reads
        with pytest.raises(CallSiteReachabilityError) as exc:
            validate_analyzers((_Analyzer(Language.GO, True),))
        assert "no COMPARATORS row" in str(exc.value)
        # And the same row is accepted once its language is enrolled.
        csr.COMPARATORS = original
        validate_analyzers((_Analyzer(Language.GO, True),))
    finally:
        csr.COMPARATORS = original


def test_an_unenrolled_mechanism_abstains_rather_than_passing_everything():
    """``check_tree`` over a real tree with an empty registry must not read clean.

    The discipline ``PENDING_COMPARATORS`` exists for, applied to D5's own
    table: a mechanism that has been WRITTEN and has no analyzer must say "I
    did not look" over every file, not "there is nothing wrong here". With
    ``ANALYZERS`` empty every path is
    :attr:`UndecidedReason.UNSUPPORTED_LANGUAGE`, so the report must carry
    every file in ``unanalyzed_paths``, must show ``seals_examined == 0``, and
    must not report a single OK.

    The ``.go`` files here resolve to a ``COMPARATORS`` row and still have no
    analyzer, so their reason is a ``Language`` member and not ``None`` —
    "write an analyzer row" is a different remediation from "decide whether the
    language belongs in the gate", and the report separates the two situations
    ``analyzer_for_path`` deliberately collapses.

    RED at HEAD: ``check_tree`` raises :class:`NotImplementedError`.
    Reddens under a body on: returning an empty report with no
    ``unanalyzed_paths``; folding the two unanalyzed reasons together;
    reporting ``dispositions[OK] > 0`` for a tree nobody read.
    """
    report = check_tree(_FIXTURE)

    assert isinstance(report, ReachabilityReport)
    assert report.seals_examined == 0
    assert report.findings == ()
    assert report.dispositions[Disposition.OK] == 0
    assert set(report.dispositions) == set(Disposition)

    unanalyzed = dict(report.unanalyzed_paths)
    assert unanalyzed, "a tree nobody read reported no unanalyzed paths"
    go_files = {p for p in unanalyzed if p.endswith(".go")}
    assert go_files, "the vendored Go files were not reported as unanalyzed"
    assert all(unanalyzed[p] is Language.GO for p in go_files), (
        "a .go path has a COMPARATORS row and no analyzer row; its reason is "
        "the Language, not None"
    )
    assert unanalyzed.get("PROVENANCE.md", "missing") is None, (
        "a path with no COMPARATORS row at all must be reported with None, "
        "which is a different remediation from a language with no analyzer"
    )


def test_the_report_carries_no_single_boolean_verdict():
    """``ReachabilityReport`` has no ``is_clean`` and must not grow one.

    Deliberately absent, exactly as in D3: a single boolean would have to fold
    ABSTAIN onto one side of itself, and the abstention count is this
    mechanism's own coverage figure. The caller decides what to block on.

    GREEN at HEAD. Reddens on: adding ``is_clean`` (or any bool field) to the
    report; measured in a clone.
    """
    annotations = ReachabilityReport.__annotations__
    assert "is_clean" not in annotations
    assert not [n for n, t in annotations.items() if t is bool or t == "bool"], (
        f"a boolean verdict field appeared on the report: {annotations}"
    )
    for required in (
        "roots",
        "seals_examined",
        "subject_gaps",
        "unresolved_call_count",
        "unanalyzed_paths",
        "stale_declarations",
    ):
        assert required in annotations, f"the report lost its {required} field"


# --------------------------------------------------------------------------- #
# Part 2 — the module holds no file-extension literal. Structural, and GREEN.
# --------------------------------------------------------------------------- #


def test_the_module_declares_no_file_extension_and_calls_no_endswith():
    """D5 asks ``support_for_path`` what language a file is; it never matches.

    ``role_protocol.py:6920`` is the ONE site in this codebase where a path is
    matched against an extension, and D5 keeps that count at one by asking
    rather than matching. A second extension table would drift, and it would
    drift silently, because the two gates would disagree only on files neither
    had been pointed at yet.

    Sealed by AST and not by grep, deliberately, and the difference is
    load-bearing in both directions: the module's own docstring names ``.ts``,
    ``.py``, ``.go``, ``.sql`` and ``.java`` in prose, so a grep is red on a
    clean module; and a body author could hide ``x.endswith(".go")`` behind a
    line a grep pattern misses. The sweep therefore reads the syntax tree,
    excludes prose by SHAPE (a docstring is an ``Expr`` wrapping a string
    constant, which is also exactly how a bare-string comment is spelled), and
    a ``#`` comment is not in the tree at all.

    Three controls, because an empty-set assertion is passed by a sweep that
    has stopped working:

      * ``role_protocol.py`` must still yield extension literals AND an
        ``endswith`` call — the live positive control;
      * a synthetic source carrying the tokens ONLY in comments and docstrings
        must yield nothing — a comment does not trip it;
      * the same synthetic source with the tokens in code must yield them — a
        comment does not satisfy it either.

    GREEN at HEAD. Reddens on: adding any extension-shaped literal or any
    ``.endswith(`` call to ``call_site_reachability.py``; both measured in a
    clone.
    """
    d5 = (_SRC / "call_site_reachability.py").read_text(encoding="utf-8")

    assert _extension_literals(d5) == [], (
        "call_site_reachability.py grew a file-extension literal; the module "
        "keeps that count at zero and role_protocol keeps it at one"
    )
    assert _endswith_sites(d5) == [], (
        "call_site_reachability.py grew an endswith call; ask "
        "support_for_path what language a file is"
    )
    # Prose naming extensions is fine and is present, which is what makes the
    # grep version of this row a false positive.
    assert ".ts" in d5 and ".sql" in d5

    registry = (_SRC / "role_protocol.py").read_text(encoding="utf-8")
    control_literals = [v for _, v in _extension_literals(registry)]
    assert ".py" in control_literals and ".go" in control_literals, (
        "the positive control failed: role_protocol declares no extension "
        "literal, so the empty result above proves nothing"
    )
    assert _endswith_sites(registry), (
        "the positive control failed: role_protocol calls no endswith"
    )

    prose_only = '''\
"""A docstring naming ".py" and x.endswith(".go")."""
# A comment naming ".ts" and y.endswith(".tsx").
#: A doc-comment naming ".sql".
VALUE = "not an extension"
"A bare string comment naming .java and z.endswith(\\".py\\")."
'''
    assert _extension_literals(prose_only) == []
    assert _endswith_sites(prose_only) == []

    in_code = 'EXT = ".py"\nif path.endswith(".go"):\n    pass\n'
    assert [v for _, v in _extension_literals(in_code)] == [".py", ".go"]
    assert _endswith_sites(in_code) == [2]


# --------------------------------------------------------------------------- #
# Part 3 — FROM_TESTS_ONLY is spelled like neither neighbour. THE flagship.
# --------------------------------------------------------------------------- #


def test_from_tests_only_is_spelled_like_neither_neighbour():
    """The B1 verdict, its two neighbours, and the substring decoy, in one call.

    "Reached" certifies the defect. "Unreachable" is false — the function runs
    under ``go test`` — and would send a human to delete code a seal depends
    on. The seal is therefore not that ``Reach`` has four members, which is
    free, but that the three verdicts differ **in the output a caller acts
    on**: three distinct ``Disposition`` values, three distinct payload shapes,
    and the tests-only finding carrying the chain from the seal so the human is
    handed the seal rather than a delete instruction.

    Four subjects, judged against ONE graph:

      * ``ResolveConfigDual`` — reached from the seal and from nothing else;
      * ``findConfig`` — reached from ``main``. The control that a mechanism
        answering the defect's verdict unconditionally cannot pass;
      * ``ResolveConfigDualDocComment`` — the substring decoy, reached from
        ``main``. A mechanism that resolves by substring answers the SAME thing
        for it and for the subject, and this row is the one that catches it;
      * the same subject under Python's row — an abstention, so the third
        verdict is present in the same call too.

    Which disposition each verdict gets is NOT pinned; the grid is P4's.

    RED at HEAD: ``check_subject`` raises :class:`NotImplementedError`.
    Reddens under a body on: mapping FROM_TESTS_ONLY to the same disposition as
    FROM_PRODUCTION or as UNDECIDED; deciding reach by substring over the
    reached keys (the decoy then makes the subject FROM_PRODUCTION); dropping
    ``test_path`` from a tests-only finding.
    """
    dark = _judge(_SUBJECT)
    live = _judge(_FIND_CONFIG)
    decoy = _judge(_DECOY)
    undecided = _judge(_SUBJECT, analyzer=_python())

    assert dark.reach is Reach.FROM_TESTS_ONLY
    assert live.reach is Reach.FROM_PRODUCTION
    assert decoy.reach is Reach.FROM_PRODUCTION, (
        "the decoy is reached from main; if it is not FROM_PRODUCTION the "
        "fixture is broken and the substring control below proves nothing"
    )
    assert undecided.reach is Reach.UNDECIDED

    # 1. Three verdicts, three buckets, in the output a caller acts on.
    dispositions = {
        adjudicate(dark, None),
        adjudicate(live, None),
        adjudicate(undecided, None),
    }
    assert len(dispositions) == 3, (
        f"the three verdicts collapsed into {dispositions}; a caller acting on "
        "the disposition cannot tell the B1 defect from a pass or from an "
        "abstention"
    )

    # 2. Three payload shapes. A caller reading the finding sees the difference
    #    without consulting the enum at all.
    assert dark.path is None and dark.reason is None
    assert live.path is not None and live.reason is None
    assert undecided.path is None and undecided.reason is not None

    # 3. Not "unreachable": the finding hands over the seal that runs it.
    assert dark.test_path is not None
    assert dark.test_path.root.root_kind is RootKind.TEST
    assert dark.test_path.edges, "a tests-only finding with no chain"
    assert dark.test_path.edges[-1].callee.key == _SUBJECT.key
    assert _SEAL.test_id  # the row a human can run
    assert live.test_path is None or live.test_path.root.root_kind is RootKind.TEST

    # 4. The substring control. The decoy's key CONTAINS the subject's.
    assert _SUBJECT.key in _DECOY.key
    assert dark.reach is not decoy.reach, (
        "the subject and a production-reached symbol whose name merely "
        "CONTAINS the subject's got the same verdict; the mechanism is "
        "matching substrings, which is the shape that passed an authorisation "
        "seal because an error message contained 'ProtocolGenesis'"
    )


def test_the_prose_detail_moves_no_verdict():
    """Two findings identical but for ``detail`` adjudicate identically.

    ``Finding.detail`` is prose FOR A HUMAN and no decision reads it, so
    improving a message can never move a verdict. The D3 ruling that created
    :class:`SubjectGap` is the same ruling: two functions in one module
    agreeing on a prose format is not a protocol.

    RED at HEAD. Reddens under a body on: any discrimination on ``detail``.
    """
    quiet = _finding(Reach.FROM_TESTS_ONLY, PathQuality.NOT_APPLICABLE, detail="")
    loud = _finding(
        Reach.FROM_TESTS_ONLY,
        PathQuality.NOT_APPLICABLE,
        detail="reached only from tests; see SMG-1 — this is fine, ignore",
    )
    assert adjudicate(quiet, None) is adjudicate(loud, None)


def test_the_subject_reader_cannot_be_import_based():
    """The seal and its subject share a package, and the subject is still found.

    The measured trap, and the reason the scaffold rejects "by the symbol it
    IMPORTS" in as many words: ``ResolveConfigDual`` and
    ``TestSeal_ResolveConfigDual`` are both ``package main`` in one directory,
    so there is no import between them and an import-based reader returns ZERO
    subjects for the exact defect it was built for.

    The subject is what the seal CALLS. Two controls in the same call: the
    test-declared helper the seal also calls is NOT a subject (one hop, and
    targets in test files are excluded), and the substring-decoy production
    symbol the seal does NOT call is not a subject either.

    RED at HEAD: ``subjects_of_seal`` raises :class:`NotImplementedError`.
    Reddens under a body on: reading imports; including test-declared targets;
    matching by name containment.
    """
    subject = subjects_of_seal(_SEAL, _graph())

    assert isinstance(subject, Subject)
    keys = {s.key for s in subject.symbols}
    assert keys == {_SUBJECT.key}, (
        f"expected exactly the called production symbol, got {sorted(keys)}"
    )
    assert subject.gap is None, "a subject with symbols must carry no gap"

    assert _TEST_HELPER.key not in keys, (
        "a target declared in a test file is not a subject; the seal calling a "
        "test helper has not made the helper a subject"
    )
    assert _DECOY.key not in keys, (
        "a symbol the seal does not call became a subject; its key merely "
        "contains the subject's"
    )


def test_a_subject_record_never_says_two_things_or_nothing():
    """``gap`` is None exactly when ``symbols`` is non-empty. Both ways.

    A subject record that says two things or says nothing is a non-judgement,
    and a non-judgement must not read as an answer. R2: the scaffold contracts
    the raise "at :func:`check_subject`", which has no ``Subject`` parameter;
    this row seals it where it can be — the constructing function must never
    produce one.

    Three seals in one call: the canonical one (symbols, no gap), a seal that
    calls nothing (gap, no symbols), and a seal that calls only test helpers
    (gap, no symbols, and a DIFFERENT gap — the distinction the two members
    exist for, because a seal in the second state is one refactor away from
    being the vacuous kind).

    RED at HEAD. Reddens under a body on: returning a gap alongside symbols;
    returning an empty symbol set with ``gap=None``; collapsing
    ``ALL_TARGETS_IN_TESTS`` into ``NO_CALLS``.
    """
    silent = Seal(
        symbol=_sym("TestSeal_Nothing", "contract_seal_test.go", 40),
        test_id="cmd/classify.TestSeal_Nothing",
    )
    helpers_only = Seal(
        symbol=_sym("TestSeal_HelpersOnly", "contract_seal_test.go", 60),
        test_id="cmd/classify.TestSeal_HelpersOnly",
    )
    graph = _graph(
        symbols=_ALL_SYMBOLS + (silent.symbol, helpers_only.symbol),
        edges=_PRODUCTION_EDGES
        + _SEAL_EDGES
        + (_edge(helpers_only.symbol, _TEST_HELPER),),
    )

    for seal, expected_gap in (
        (_SEAL, None),
        (silent, SubjectGap.NO_CALLS),
        (helpers_only, SubjectGap.ALL_TARGETS_IN_TESTS),
    ):
        subject = subjects_of_seal(seal, graph)
        assert (subject.gap is None) is bool(subject.symbols), (
            f"{seal.test_id}: gap={subject.gap!r} symbols={subject.symbols!r} — "
            "a record that says two things or says nothing"
        )
        assert subject.gap is expected_gap, seal.test_id


# --------------------------------------------------------------------------- #
# Part 4 — abstention is never a pass.
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("reason", list(UndecidedReason), ids=lambda r: r.value)
def test_no_undecided_reason_is_actionable_as_a_pass(reason):
    """Every abstention lands apart from every pass, and none is declarable.

    **Five** members, each judged in the same call as the two things it must
    not be confused with: a resolved production pass and an over-approximated
    one. And a matching declaration must not move it — the abstention count is
    this mechanism's own coverage figure and a declaration that could silence
    one would be buying silence on a measurement nobody took.

    R1 and R3 were the two dead-member questions and P4 ruled them opposite
    ways, which is why this row's parameter count moved from six to five with
    no assertion changed: ``ANALYZER_FAULT`` was STRUCK (a fault raises; both
    faulting sites are upstream of the subject population) and
    ``SUBJECT_UNIDENTIFIED`` was CONFIRMED LIVE (an ``UNNAMEABLE`` seal does
    produce an abstention finding). This row is over the ENUM and needed no
    amendment for either; the rows that exercise the two production sites are
    :func:`test_an_analyzer_fault_never_reads_as_a_clean_tree` and
    :func:`test_an_unnameable_target_is_counted_and_never_passes`.

    RED at HEAD. Reddens under a body on: mapping any abstention onto a pass
    bucket; letting a declaration touch an abstention.
    """
    abstention = _finding(Reach.UNDECIDED, PathQuality.NOT_APPLICABLE, reason=reason)
    resolved_pass = _judge(_FIND_CONFIG)
    over_approximated = _judge(
        _FIND_CONFIG,
        graph=_graph(
            edges=(
                _edge(_MAIN, _RESOLVE_CONFIG_PATH),
                _edge(_RESOLVE_CONFIG_PATH, _FIND_CONFIG, EdgeKind.INTERFACE),
            )
            + _SEAL_EDGES
        ),
        production_reach={
            _MAIN.key: (),
            _RESOLVE_CONFIG_PATH.key: _chain(_edge(_MAIN, _RESOLVE_CONFIG_PATH)),
            _FIND_CONFIG.key: _chain(
                _edge(_MAIN, _RESOLVE_CONFIG_PATH),
                _edge(_RESOLVE_CONFIG_PATH, _FIND_CONFIG, EdgeKind.INTERFACE),
            ),
        },
    )

    abstained = adjudicate(abstention, None)
    assert abstained != adjudicate(resolved_pass, None)
    assert abstained != adjudicate(over_approximated, None)
    assert adjudicate(abstention, _declaration()) is abstained, (
        "a declaration silenced an abstention; the abstention count is this "
        "mechanism's own coverage figure"
    )


def test_no_entrypoint_over_a_library_tree_abstains(tmp_path, monkeypatch):
    """Zero production roots abstains over the whole tree, and certifies nothing.

    The named case, and both wrong answers are refused in one call. "Everything
    exported is reachable" is the linter's answer and it is measurably fatal —
    ``ResolveConfigDual`` is exported, so under that rule the mechanism built
    to catch the defect certifies the defect on its first run. "Nothing is
    reachable" is a BREACH flood against a library whose callers are in another
    repository.

    The control is judged in the same call: the same tree plus one ``GO_MAIN``
    root produces real verdicts, so a mechanism that abstains unconditionally
    does not pass.

    RED at HEAD. Reddens under a body on: treating an exported symbol as a
    root; checking tests-only before checking the root set (which is
    arithmetically guaranteed to fire when there are no production roots).
    """
    tree = _tree(tmp_path)

    library = _go(roots=(_TEST_ROOT,))
    monkeypatch.setattr(csr, "ANALYZERS", (library,))
    report = check_tree(tree)

    assert report.findings, "a library tree produced no findings at all"
    for finding in report.findings:
        assert finding.reach is Reach.UNDECIDED, (
            f"{finding.subject.key}: a tree with no production root produced "
            f"{finding.reach}; over an exported symbol that is either "
            "'everything exported is reachable' or a BREACH flood"
        )
        assert finding.reason is UndecidedReason.NO_ENTRYPOINT
        assert finding.quality is PathQuality.NOT_APPLICABLE
        assert finding.path is None
    assert not any(r.root_kind is RootKind.PRODUCTION for r in report.roots)

    monkeypatch.setattr(csr, "ANALYZERS", (_go(),))
    with_entrypoint = check_tree(tree)
    reaches = {f.subject.key: f.reach for f in with_entrypoint.findings}
    assert reaches.get(_SUBJECT.key) is Reach.FROM_TESTS_ONLY, (
        "the control failed: with a production root the canonical subject is "
        "the B1 verdict, so the abstention above was not about the root set"
    )


def test_no_entrypoint_is_a_fact_about_the_root_set(tmp_path, monkeypatch):
    """A production root that reaches nothing is not the same as no root.

    R5. ``NO_ENTRYPOINT`` is "zero production roots of any
    :class:`EntrypointKind` in the tree" — a statement about the ROOT SET.
    A tree that HAS a ``func main()`` which happens to call nothing has an
    entrypoint, and the honest answer about a subject it does not reach is the
    tests-only verdict or a dynamic-edge abstention, never "this tree has no
    starter". Whether :func:`reachable_from` includes its own roots is what
    decides whether a body can tell the two apart from the reach map alone;
    that convention is P4's, and this row pins the property it has to deliver.

    RED at HEAD. Reddens under a body on: deriving "no entrypoint" from an
    empty production reach map instead of from the root set.
    """
    tree = _tree(tmp_path)
    lonely = Root(
        symbol=_MAIN,
        kind=EntrypointKind.GO_MAIN,
        root_kind=RootKind.PRODUCTION,
        evidence="cmd/classify/main.go:180 func main, package main",
    )
    analyzer = _go(
        roots=(lonely, _TEST_ROOT),
        graph=_graph(edges=_SEAL_EDGES),
    )
    monkeypatch.setattr(csr, "ANALYZERS", (analyzer,))

    report = check_tree(tree)
    assert any(r.root_kind is RootKind.PRODUCTION for r in report.roots)
    for finding in report.findings:
        assert finding.reason is not UndecidedReason.NO_ENTRYPOINT, (
            f"{finding.subject.key}: this tree has a production entrypoint that "
            "calls nothing; reporting NO_ENTRYPOINT confuses a fact about the "
            "root set with a fact about the reach map"
        )


@pytest.mark.parametrize("fault", list(AnalyzerFault), ids=lambda f: f.value)
def test_an_analyzer_fault_never_reads_as_a_clean_tree(tmp_path, monkeypatch, fault):
    """A broken toolchain is not "no Go here". It is a refusal to answer.

    R1, RULED by P4 2026-08-11: the raises in :func:`discover_roots` and
    :func:`build_call_graph` stand and ``UndecidedReason.ANALYZER_FAULT`` is
    STRUCK, because both faulting sites are upstream of the subject population
    — a fault leaves no roots, therefore no seals, therefore no subjects to
    abstain over, and an abstention you cannot enumerate is silence with a
    label. So this row no longer accepts either answer: every
    :class:`AnalyzerFault` must reach the caller as a
    :class:`CallSiteReachabilityError`, which is not a pass and not a silent
    skip. A Go tree analyzed in a CI image with no toolchain reporting
    "nothing to analyze here" is a live fail-open for as long as the image
    stays broken, and so is one reporting nothing at all without raising.

    The control is judged in the same call: the same analyzer, not faulting,
    returns a report with real findings — so a body that raises on everything
    does not pass.

    RED at HEAD. Reddens under a body on: catching
    :class:`AnalyzerUnavailable` and returning a report of any kind; raising
    any type other than the mechanism's own.
    """
    tree = _tree(tmp_path)
    monkeypatch.setattr(
        csr,
        "ANALYZERS",
        (_go(raises=AnalyzerUnavailable(fault, "measured by a seal")),),
    )

    with pytest.raises(CallSiteReachabilityError):
        check_tree(tree)

    monkeypatch.setattr(csr, "ANALYZERS", (_go(),))
    healthy = check_tree(tree)
    assert healthy.findings, (
        "the control failed: the non-faulting analyzer produced no findings, "
        "so the outcome above says nothing about the fault"
    )


def test_a_source_unreadable_abstains_over_the_whole_tree(tmp_path, monkeypatch):
    """One unparsed file holes the edge set, so every subject abstains.

    The scaffold's CHOICE, and the rejected alternative is wrong in precisely
    the permissive direction: abstaining only on subjects declared in the
    unparsed file is what a per-file mechanism would naturally do, and the file
    that fails to parse is the one most likely to hold the call site nobody
    wrote. The canonical subject is declared in ``contract.go``; the unreadable
    file here is ``main.go``, so a per-file body answers BREACH for it and a
    correct body abstains.

    The control is judged in the same call: the same tree with nothing
    unreadable produces a verdict.

    RED at HEAD. Reddens under a body on: scoping the abstention to the
    unparsed file; raising instead of recording, which would lose every other
    file's edges and turn one bad file into a total outage.
    """
    tree = _tree(tmp_path)
    holed = _graph(unreadable=("cmd/classify/main.go",))
    monkeypatch.setattr(csr, "ANALYZERS", (_go(graph=holed),))

    report = check_tree(tree)
    assert report.findings
    for finding in report.findings:
        assert finding.reach is Reach.UNDECIDED, (
            f"{finding.subject.key} was judged around a hole of unknown size"
        )
        assert finding.reason is UndecidedReason.PARSE_FAILED

    monkeypatch.setattr(csr, "ANALYZERS", (_go(),))
    clean = check_tree(tree)
    assert any(f.reach is not Reach.UNDECIDED for f in clean.findings), (
        "the control failed: the readable tree also abstained on everything"
    )


def test_an_unnameable_target_is_counted_and_never_passes(tmp_path, monkeypatch):
    """A seal whose target could not be named is visible, and is not a pass.

    R3, RULED by P4 2026-08-11 in favour of :func:`subjects_of_seal`:
    ``UNNAMEABLE`` DOES produce a finding, an abstention carrying
    ``SUBJECT_UNIDENTIFIED`` over a synthetic subject symbol, and
    :func:`check_tree`'s "produces no finding" was over-general — it holds for
    ``NO_CALLS`` and ``ALL_TARGETS_IN_TESTS``, which are seals that made no
    claim, and not for the one gap that means the mechanism could not READ a
    claim. ``SUBJECT_UNIDENTIFIED`` is therefore not a dead member.

    The row is amended accordingly, and the amendment is a strengthening: as
    written the per-finding loop below was VACUOUSLY satisfied by a report with
    no finding for the mystery seal at all, which is precisely the reading the
    ruling rejects. A finding must now exist.

    An unresolved call from the seal is how the state arises: the seal calls
    something through a value, and the unnameable target may be the very
    production symbol the seal exists to cover.

    RED at HEAD. Reddens under a body on: dropping the gap counts; folding
    UNNAMEABLE into NO_CALLS; reporting the seal as OK; discharging the
    unnameable seal as a count with no finding.
    """
    tree = _tree(tmp_path)
    mystery = Seal(
        symbol=_sym("TestSeal_ViaValue", "contract_seal_test.go", 300),
        test_id="cmd/classify.TestSeal_ViaValue",
    )
    mystery_root = Root(
        symbol=mystery.symbol,
        kind=EntrypointKind.TEST_FUNCTION,
        root_kind=RootKind.TEST,
        evidence="cmd/classify/contract_seal_test.go:300 func TestSeal_ViaValue",
    )
    graph = _graph(
        symbols=_ALL_SYMBOLS + (mystery.symbol,),
        unresolved=((mystery.symbol, "cmd/classify/contract_seal_test.go:310", "call through a func value"),),
    )
    monkeypatch.setattr(
        csr,
        "ANALYZERS",
        (_go(roots=(_GO_MAIN_ROOT, _TEST_ROOT, mystery_root), graph=graph),),
    )

    report = check_tree(tree)

    assert set(report.subject_gaps) == set(SubjectGap), (
        "every SubjectGap member is a key, zeros included; a report that omits "
        "one because there were none is indistinguishable from one that never "
        "counted"
    )
    assert report.subject_gaps[SubjectGap.UNNAMEABLE] >= 1, (
        "a seal whose call target could not be named vanished from the report"
    )
    mystery_findings = [
        f for f in report.findings if f.seal.test_id == mystery.test_id
    ]
    assert len(mystery_findings) == 1, (
        "an UNNAMEABLE seal produces exactly one finding, an abstention; a "
        "count with no finding discharges 'the mechanism could not read this "
        "claim' as though the seal had made none"
    )
    for finding in mystery_findings:
        assert finding.reach is Reach.UNDECIDED
        assert finding.reason is UndecidedReason.SUBJECT_UNIDENTIFIED
        assert finding.quality is PathQuality.NOT_APPLICABLE
        assert finding.path is None
        assert finding.subject.key not in graph.symbols, (
            "the synthetic subject must carry a key no declaration can "
            "produce, or it collides with a real symbol"
        )


# --------------------------------------------------------------------------- #
# Part 5 — negative_is_conclusive is per-language and it changes the verdict.
# --------------------------------------------------------------------------- #


def test_a_python_subject_with_no_static_reference_does_not_get_gos_answer():
    """One graph, two rows, two verdicts. The reason D5 is language-parametric.

    Go has no runtime lookup of a package-level function by name, so a symbol
    referenced nowhere in the production closure is called nowhere and "no
    path" is a FACT. Python is the opposite. A Go-first mechanism generalised
    later would report a confident "no path" for Python code reached by
    ``getattr`` — a false BREACH, which is the over-call that gets a check
    removed.

    So: identical graph, identical reach maps, identical subject. The Go row
    yields the B1 verdict; the Python row yields an abstention with
    ``DYNAMIC_EDGE``. A ``False`` row cannot produce a BREACH by itself, and
    that is a large cost paid on purpose.

    RED at HEAD. Reddens under a body on: reading
    ``negative_is_conclusive`` from anywhere but the row; a row-independent
    verdict (both halves then agree and the row goes red on one of them).
    """
    go = _judge(_SUBJECT, analyzer=_go())
    python = _judge(_SUBJECT, analyzer=_python())

    assert go.reach is Reach.FROM_TESTS_ONLY
    assert go.reason is None

    assert python.reach is Reach.UNDECIDED
    assert python.reason is UndecidedReason.DYNAMIC_EDGE
    assert python.reach is not go.reach, (
        "a Python subject with no static reference got Go's answer; that is a "
        "BREACH resting on a claim the language does not support"
    )
    assert adjudicate(python, None) != adjudicate(go, None)


def test_a_false_row_still_reports_a_path_it_found():
    """``DYNAMIC_EDGE`` may only DOWNGRADE. It may never touch FROM_PRODUCTION.

    Anti-requirement 2, at the one place it is enforced by the ORDER of the
    dispatch: the found-path check runs first, before every abstention check,
    so "we could not see everything" can never suppress a real pass. Failing to
    look may only make an answer LESS conclusive; it may never manufacture the
    permissive one, and it may never destroy the conclusive one either.

    Judged in one call for the Python row: a subject WITH a production path
    stays FROM_PRODUCTION, and a subject without one abstains.

    RED at HEAD. Reddens under a body on: putting the
    ``negative_is_conclusive`` test ahead of the ``production_reach`` lookup.
    """
    python = _python()
    reached = _judge(_FIND_CONFIG, analyzer=python)
    dark = _judge(_SUBJECT, analyzer=python)

    assert reached.reach is Reach.FROM_PRODUCTION
    assert reached.reason is None
    assert reached.path is not None
    assert dark.reach is Reach.UNDECIDED


def test_unresolved_calls_abstain_only_over_the_production_closure():
    """An unresolvable call outside the production closure does not abstain.

    The scaffold's CHOICE, and the naive reading kills the mechanism: any
    unresolved call anywhere is what a soundness purist would write and would
    make every real repository abstain on every subject forever. A mechanism
    that always abstains is never consulted, and an unrun check is this repo's
    most expensive recorded failure.

    Two graphs, judged in one call. In the first the unresolved call is made by
    a TEST symbol, outside the production closure — the Go verdict stands. In
    the second it is made by ``findConfig``, which ``main`` reaches — the
    answer downgrades to ``DYNAMIC_EDGE``.

    RED at HEAD. Reddens under a body on: counting unresolved calls over the
    whole graph; ignoring them entirely (the second half then keeps the
    tests-only verdict and the row goes red there).
    """
    outside = _graph(
        unresolved=((_SEAL_FN, "cmd/classify/contract_seal_test.go:900", "t.Run literal"),)
    )
    inside = _graph(
        unresolved=((_FIND_CONFIG, "cmd/classify/main.go:450", "call through a value"),)
    )

    assert _judge(_SUBJECT, graph=outside).reach is Reach.FROM_TESTS_ONLY
    downgraded = _judge(_SUBJECT, graph=inside)
    assert downgraded.reach is Reach.UNDECIDED
    assert downgraded.reason is UndecidedReason.DYNAMIC_EDGE


def test_the_python_row_is_false_because_this_repo_resolves_names_dynamically():
    """The measurement behind the rule, run live over ``src/``.

    A per-language row that says ``False`` is a claim a human made, and this
    row keeps the premise of that claim from silently stopping being true.
    Measured by AST on this worktree, 2026-08-10: ``getattr(`` appears at
    **105** call sites in ``src/``, **4** of them with a non-literal attribute
    name, **3** of those inside ``fixture_reachability`` — which resolves
    ARBITRARY fully-qualified names out of a table and is D5's own sibling.

    R7: the scaffold records 100 / six / three. The shape survives, the
    arithmetic does not, and the fourth non-literal site is the one worth
    naming: it is in ``call_site_reachability.validate_analyzers`` itself. The
    module that would judge Python reachability contains, in its one
    implemented function, exactly the construct that makes Python's negative
    inconclusive. So the invariant is sealed and the counts are recorded here
    rather than pinned.

    Controls: a synthetic source with a LITERAL attribute name must not be
    counted (or the sweep proves nothing about dynamism), and one with a
    computed name must be.

    GREEN at HEAD. Reddens on: ``fixture_reachability`` losing every dynamic
    resolution — at which point Python's ``False`` row is no longer supported
    by this repository and needs re-arguing, which is the point.
    """
    dynamic: dict[str, list[int]] = {}
    for path in sorted(_SRC.rglob("*.py")):
        sites = _dynamic_getattr_sites(path.read_text(encoding="utf-8"))
        if sites:
            dynamic[path.name] = sites

    assert dynamic, (
        "no dynamic getattr anywhere in src/; Python's negative_is_conclusive "
        "= False is no longer supported by a measurement on this repository"
    )
    assert "fixture_reachability.py" in dynamic, (
        "D5's own sibling no longer resolves names dynamically; the deciding "
        "evidence for the per-language row has moved"
    )
    assert "call_site_reachability.py" in dynamic, (
        "R7: validate_analyzers' getattr over a loop variable was the fourth "
        "measured site; if it is gone the recorded measurement needs redoing"
    )

    assert _dynamic_getattr_sites("getattr(m, 'name')\n") == []
    assert _dynamic_getattr_sites("getattr(m, n)\n") == [1]


# --------------------------------------------------------------------------- #
# Part 6 — FROM_NEITHER raises, and the raise IS its exhaustive treatment.
# --------------------------------------------------------------------------- #


def test_from_neither_raises_for_a_seal_derived_subject():
    """A lost edge is a mechanism bug, reported as one. Both directions.

    The seal has a direct edge to its own subject by the definition of
    "subject", so a subject reached from no root at all means the traversal
    lost an edge it was handed. Folding that into the tests-only verdict would
    turn a lost edge into a BREACH against innocent code — an over-call
    arriving through the mechanism's own defect, which is the worst way for a
    gate to be wrong.

    The control is judged in the same call: restore the edge to the test reach
    map and the same subject gets a clean verdict, so a body that raises
    unconditionally does not pass.

    RED at HEAD. Reddens under a body on: returning a ``Finding`` with
    ``Reach.FROM_NEITHER``; mapping it to the tests-only verdict; raising a
    bare ``KeyError`` instead of the mechanism's own error type.
    """
    with pytest.raises(CallSiteReachabilityError) as exc:
        _judge(_SUBJECT, test_reach={_SEAL_FN.key: ()})
    message = str(exc.value)
    assert _SUBJECT.key in message or _SUBJECT_NAME in message, (
        "the raise must name the subject whose edge went missing"
    )

    restored = _judge(_SUBJECT)
    assert restored.reach is Reach.FROM_TESTS_ONLY, (
        "the control failed: the raise above was not about the missing edge"
    )


@pytest.mark.parametrize("quality", list(PathQuality), ids=lambda q: q.value)
def test_adjudicate_raises_on_from_neither_rather_than_ruling_on_it(quality):
    """The grid does not name ``FROM_NEITHER``, so the two layers cannot disagree.

    Omitted from the grid rather than mapped to a disposition, deliberately:
    ``check_subject`` already raises on it, and a second layer with its own
    answer is two answers. The raise IS this enum member's exhaustive
    treatment.

    RED at HEAD. Reddens under a body on: adding any ``FROM_NEITHER`` row to
    the grid, including one that maps to the BREACH bucket.
    """
    finding = _finding(Reach.FROM_NEITHER, quality)
    with pytest.raises(CallSiteReachabilityError):
        adjudicate(finding, None)
    with pytest.raises(CallSiteReachabilityError):
        adjudicate(finding, _declaration())


# --------------------------------------------------------------------------- #
# Part 7 — PathQuality is never spelled like RESOLVED when it is not.
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "weak_kind", [EdgeKind.INTERFACE, EdgeKind.REFERENCE], ids=lambda k: k.value
)
def test_an_over_approximated_path_is_never_spelled_resolved(weak_kind):
    """The one axis where D5 may be permissively wrong, so it must be loud.

    An interface edge was resolved to a SET of possible implementations; a
    reference edge is a symbol passed as a value that nothing may ever invoke.
    Either may create a path no execution takes. Followed rather than dropped,
    because dropping under-approximates and under-approximation manufactures
    BREACHes; marked rather than followed silently, because an unmarked
    over-approximation manufactures OKs.

    The control is judged in the same call: the same subject reached by a
    ``DIRECT`` chain is ``RESOLVED`` and lands in a DIFFERENT bucket. Which
    bucket each gets is not pinned; that they differ is.

    RED at HEAD. Reddens under a body on: folding OVER_APPROXIMATED into
    RESOLVED; giving both the same disposition.
    """
    weak = _edge(_RESOLVE_CONFIG_PATH, _FIND_CONFIG, weak_kind)
    strong = _edge(_RESOLVE_CONFIG_PATH, _FIND_CONFIG, EdgeKind.DIRECT)
    first = _edge(_MAIN, _RESOLVE_CONFIG_PATH)

    def judged(edge):
        return _judge(
            _FIND_CONFIG,
            graph=_graph(edges=(first, edge) + _SEAL_EDGES),
            production_reach={
                _MAIN.key: (),
                _RESOLVE_CONFIG_PATH.key: _chain(first),
                _FIND_CONFIG.key: _chain(first, edge),
            },
        )

    over = judged(weak)
    resolved = judged(strong)

    assert over.reach is Reach.FROM_PRODUCTION
    assert resolved.reach is Reach.FROM_PRODUCTION
    assert over.quality is PathQuality.OVER_APPROXIMATED
    assert resolved.quality is PathQuality.RESOLVED
    assert over.path is not None and over.path.quality is PathQuality.OVER_APPROXIMATED
    assert adjudicate(over, None) != adjudicate(resolved, None), (
        "a mechanism that spells its strong answer and its weak answer the "
        "same way has thrown away the distinction it spent an analyzer "
        "computing"
    )


def test_a_chain_is_only_as_certain_as_its_weakest_link():
    """One over-approximated edge makes the whole chain over-approximated.

    ``CallPath.quality`` is the MINIMUM over its edges, not the majority and
    not the last one. Judged against a three-edge chain in which only the
    middle edge is weak, with an all-``DIRECT`` control in the same call.

    ``METHOD`` is on the strong side with ``DIRECT``: it is a resolution to
    exactly one declaration, distinguished only so the report can say which
    kind of resolution it leaned on.

    RED at HEAD. Reddens under a body on: taking the quality of the last edge;
    treating METHOD as weak.
    """
    a = _edge(_MAIN, _RESOLVE_CONFIG_PATH, EdgeKind.DIRECT)
    b_weak = _edge(_RESOLVE_CONFIG_PATH, _FIND_CONFIG, EdgeKind.INTERFACE)
    b_method = _edge(_RESOLVE_CONFIG_PATH, _FIND_CONFIG, EdgeKind.METHOD)
    c = _edge(_FIND_CONFIG, _LOAD_CONFIG, EdgeKind.DIRECT)

    def judged(middle):
        return _judge(
            _LOAD_CONFIG,
            graph=_graph(edges=(a, middle, c) + _SEAL_EDGES),
            production_reach={
                _MAIN.key: (),
                _RESOLVE_CONFIG_PATH.key: _chain(a),
                _FIND_CONFIG.key: _chain(a, middle),
                _LOAD_CONFIG.key: _chain(a, middle, c),
            },
        )

    assert judged(b_weak).quality is PathQuality.OVER_APPROXIMATED
    assert judged(b_method).quality is PathQuality.RESOLVED


def test_reachable_from_prefers_the_resolved_chain_over_the_possible_one():
    """Two chains to one subject: the resolved one wins. Not a tie-break.

    A subject reached both through a resolved chain and through an interface
    chain is ``RESOLVED``, because the resolved path is a fact and the
    over-approximated one is a possibility. The control is in the same call:
    remove the resolved chain and the same subject comes back
    over-approximated, so a body that reports RESOLVED unconditionally does not
    pass.

    RED at HEAD: ``reachable_from`` raises :class:`NotImplementedError`.
    Reddens under a body on: taking the shortest chain before the best one
    (the interface chain here is SHORTER, which is what makes this row
    discriminating).
    """
    direct_a = _edge(_MAIN, _RESOLVE_CONFIG_PATH, EdgeKind.DIRECT)
    direct_b = _edge(_RESOLVE_CONFIG_PATH, _LOAD_CONFIG, EdgeKind.DIRECT)
    shortcut = _edge(_MAIN, _LOAD_CONFIG, EdgeKind.INTERFACE)

    both = _graph(edges=(direct_a, direct_b, shortcut))
    reach = reachable_from(both, (_GO_MAIN_ROOT,))
    chain = reach[_LOAD_CONFIG.key]
    assert all(e.kind is EdgeKind.DIRECT for e in chain), (
        f"the shorter INTERFACE chain was preferred: {[e.kind for e in chain]}"
    )

    only_weak = _graph(edges=(shortcut,))
    weak_chain = reachable_from(only_weak, (_GO_MAIN_ROOT,))[_LOAD_CONFIG.key]
    assert any(e.kind is EdgeKind.INTERFACE for e in weak_chain), (
        "the control failed: with only the interface chain available the "
        "traversal still reported a resolved one"
    )


# --------------------------------------------------------------------------- #
# Part 8 — the ruling grid: total, raising, and NOT pinned cell by cell.
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("reach", list(Reach), ids=lambda r: r.value)
@pytest.mark.parametrize("quality", list(PathQuality), ids=lambda q: q.value)
def test_adjudicate_is_total_over_the_grid(reach, quality):
    """Every pair either rules or RAISES. Nothing falls through.

    Twelve pairs. The scaffold names four; the omissions are the specification
    and it names each omitted class as a MECHANISM BUG rather than a policy
    choice — a path found with no quality recorded, a quality recorded for a
    path that does not exist. So the obligation sealed here is totality and the
    error type, never which of the four named pairs gets which disposition.

    A body that returns ``None`` for an unnamed pair, or lets a ``KeyError``
    out of a dict lookup, fails this row: the caller cannot tell a
    non-judgement from a permissive one.

    RED at HEAD. Reddens under a body on: a default branch of any kind.
    """
    finding = _finding(reach, quality, reason=UndecidedReason.DYNAMIC_EDGE)
    try:
        ruling = adjudicate(finding, None)
    except CallSiteReachabilityError:
        return
    assert isinstance(ruling, Disposition), (
        f"({reach.value}, {quality.value}) returned {ruling!r}, which is "
        "neither a Disposition nor a refusal"
    )


def test_adjudicate_raises_on_a_member_the_grid_has_never_seen():
    """A new enum member cannot fall through to the permissive answer.

    ``skills/explicit-state.md``'s step 3, which is the one that bites: naming
    the states does not give exhaustiveness for free. The sentinel below stands
    for the fifth ``Reach`` member somebody adds without visiting every
    dispatch — which is how the permissive value gets a new spelling.

    RED at HEAD. Reddens under a body on: an ``else`` that returns anything.
    """

    class _Unnamed:
        value = "a state nobody has ruled on"

    for unnamed in (
        _finding(_Unnamed(), PathQuality.NOT_APPLICABLE),
        _finding(Reach.FROM_TESTS_ONLY, _Unnamed()),
    ):
        with pytest.raises(CallSiteReachabilityError):
            adjudicate(unnamed, None)


def test_the_three_verdict_classes_land_in_three_buckets():
    """Distinguishable in the ruling, without naming a single cell.

    The complement of :func:`test_adjudicate_is_total_over_the_grid`: totality
    is worthless if everything rules the same way. Every pair the grid can rule
    on is collected and the three verdict classes must occupy three different
    dispositions. Which three is P4's.

    RED at HEAD. Reddens under a body on: any two of the three sharing a
    disposition.
    """
    rulings: dict[Reach, set[Disposition]] = {}
    for reach in Reach:
        for quality in PathQuality:
            finding = _finding(reach, quality, reason=UndecidedReason.DYNAMIC_EDGE)
            try:
                rulings.setdefault(reach, set()).add(adjudicate(finding, None))
            except CallSiteReachabilityError:
                continue

    for reach in (Reach.FROM_PRODUCTION, Reach.FROM_TESTS_ONLY, Reach.UNDECIDED):
        assert rulings.get(reach), f"{reach.value} can never be ruled on at all"

    assert (
        rulings[Reach.FROM_TESTS_ONLY]
        & (rulings[Reach.FROM_PRODUCTION] | rulings[Reach.UNDECIDED])
        == set()
    ), (
        "the B1 verdict shares a disposition with a pass or an abstention; a "
        "caller acting on the disposition cannot see the defect"
    )
    assert rulings[Reach.FROM_PRODUCTION] & rulings[Reach.UNDECIDED] == set()


def test_a_declaration_moves_at_most_one_outcome_and_never_an_abstention():
    """The annotation's only power, bounded and swept.

    Over the whole grid: a matching declaration changes at most ONE pair's
    outcome, and it changes none of the pairs whose reach is UNDECIDED (the
    coverage figure) or FROM_PRODUCTION (a human cannot declare an
    over-approximated path into a resolved one, because the weakness is in the
    analysis and not in the code).

    Which cell it moves is not pinned. That it moves one, and only one, is.

    RED at HEAD. Reddens under a body on: a declaration that touches an
    abstention, a REPORT, or more than one cell.
    """
    moved = []
    for reach in Reach:
        for quality in PathQuality:
            finding = _finding(reach, quality, reason=UndecidedReason.DYNAMIC_EDGE)
            try:
                plain = adjudicate(finding, None)
                declared = adjudicate(finding, _declaration())
            except CallSiteReachabilityError:
                continue
            if plain is not declared:
                moved.append((reach, quality, plain, declared))
                assert reach not in (Reach.UNDECIDED, Reach.FROM_PRODUCTION), (
                    f"a declaration moved ({reach.value}, {quality.value}); it "
                    "may touch neither the coverage figure nor a found path"
                )
    assert len(moved) == 1, f"a declaration moved {len(moved)} cells: {moved}"


@pytest.mark.parametrize(
    "declaration",
    [
        pytest.param(_declaration(test_id="cmd/classify.TestOther"), id="wrong-test-id"),
        pytest.param(_declaration(subject_key=f"{_MOD}.findConfig"), id="wrong-subject"),
        pytest.param(
            _declaration(test_id="TestSeal_ResolveConfigDual"), id="unqualified-test-id"
        ),
        pytest.param(_declaration(wiring=""), id="empty-wiring"),
        pytest.param(_declaration(wiring="   \t\n"), id="whitespace-wiring"),
    ],
)
def test_a_declaration_that_misses_a_key_or_names_no_wiring_buys_nothing(declaration):
    """BOTH keys must match exactly, and ``wiring`` must say something.

    A typo is not an accepted state, and neither is an empty promise.

    R8, RATIFIED by P4 2026-08-11 WITH A CONDITION, which is what the last two
    parameters pin. The appeal was ratified on the scaffold's argument — the
    scaffold-first protocol manufactures this state by construction, so an
    unappealable BREACH makes P1's own intermediate state a blocking failure
    and the check gets switched off. But the scaffold's guarantee against a
    rubber stamp ("a B1 author writing the ``wiring`` sentence would have
    discovered the bug in the act of writing it") is unenforceable on its own:
    nothing reads the sentence, so nothing stops it being ``""``. The
    ratification therefore adds the one part a machine can check — **a
    declaration with no ``wiring`` is not a declaration**, is ignored for the
    ruling exactly as a key mismatch is, and is reported stale. It is
    deliberately not a check that the named ticket exists: this module has no
    issue tracker and a verdict behind a network call is a worse gate.

    The two key-mismatch parameters and the two wiring parameters are the same
    assertion because they are the same rule: a declaration that fails any
    precondition buys exactly nothing, and buying nothing must be
    indistinguishable from not declaring.

    RED at HEAD. Reddens under a body on: matching on one key; matching on a
    suffix or a bare name; honouring a declaration whose ``wiring`` is empty or
    whitespace.
    """
    finding = _finding(Reach.FROM_TESTS_ONLY, PathQuality.NOT_APPLICABLE)
    assert adjudicate(finding, declaration) is adjudicate(finding, None)


# --------------------------------------------------------------------------- #
# Part 9 — the run, and the report's own non-vacuity.
# --------------------------------------------------------------------------- #


def test_an_empty_run_is_distinguishable_from_a_clean_one(tmp_path, monkeypatch):
    """Zero breaches over zero seals must not read as a clean tree.

    What this module exists to stop other people shipping, turned on itself.

    R4, RULED by P4 2026-08-11 in favour of the CHOICE on :func:`check_tree`:
    an empty tree RETURNS a report and does not raise, and
    ":class:`CallSiteReachabilityError` ... over zero roots" is struck. Zero
    production roots already has a first-class answer (``NO_ENTRYPOINT``), so a
    raise would be a second layer answering one state — the thing the
    ``FROM_NEITHER`` treatment refuses — and a mechanism that raises rather
    than shipping an empty root list can never SHOW one, which kills the stated
    purpose of ``roots`` as the non-vacuity field. The row is amended
    accordingly and the amendment is a strengthening: it no longer accepts
    either answer.

    The control is judged in the same call: the populated tree reports a
    non-zero ``seals_examined``, so a body that reports zero always does not
    pass.

    RED at HEAD. Reddens under a body on: raising on an empty tree; returning a
    report with no root list; reporting ``seals_examined`` as anything but the
    count of test functions.
    """
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.setattr(csr, "ANALYZERS", (_go(roots=(), graph=_graph(symbols=(), edges=())),))
    report = check_tree(empty)
    assert report.seals_examined == 0
    assert report.roots == ()
    assert report.findings == ()
    assert set(report.dispositions) == set(Disposition)
    assert sum(report.dispositions.values()) == 0

    populated = _tree(tmp_path)
    monkeypatch.setattr(csr, "ANALYZERS", (_go(),))
    real = check_tree(populated)
    assert real.seals_examined >= 1, (
        "the control failed: the populated tree also examined zero seals, so "
        "the emptiness above is not about the tree"
    )
    assert real.roots, "THE non-vacuity field came back empty on a real tree"
    assert any(r.root_kind is RootKind.PRODUCTION for r in real.roots)
    for root in real.roots:
        assert root.evidence.strip(), (
            f"{root.symbol.key}: a root nobody can verify is a root nobody "
            "will believe when it produces a BREACH"
        )


def test_the_report_counts_every_bucket_including_the_zeros(tmp_path, monkeypatch):
    """Every ``Disposition`` and every ``SubjectGap`` is a key, zeros included.

    A report that omits ABSTAIN because there were none is indistinguishable
    from one that omits it because nobody counted, and the abstention count is
    this mechanism's own coverage figure. ``ACCEPTED`` is counted apart from
    ``OK`` because a growing accepted count is a debt figure and must be
    legible as one.

    RED at HEAD. Reddens under a body on: building the counts by iterating the
    findings; folding ACCEPTED into OK.
    """
    tree = _tree(tmp_path)
    monkeypatch.setattr(csr, "ANALYZERS", (_go(),))

    report = check_tree(tree)
    assert set(report.dispositions) == set(Disposition)
    assert set(report.subject_gaps) == set(SubjectGap)
    assert sum(report.dispositions.values()) == len(report.findings)
    assert report.unresolved_call_count == 0

    declared = check_tree(tree, declarations=(_declaration(),))
    assert declared.dispositions[Disposition.OK] == report.dispositions[Disposition.OK], (
        "a declaration changed the OK count; ACCEPTED is counted apart from OK"
    )
    assert (
        declared.dispositions[Disposition.ACCEPTED]
        > report.dispositions[Disposition.ACCEPTED]
    ), "a matching declaration produced no accepted state at all"


def test_a_declaration_that_matched_nothing_is_reported_as_stale(tmp_path, monkeypatch):
    """A stale declaration is how an accepted state outlives its reason.

    Silently ignoring a declaration would let a typo look like an accepted
    state. The control is in the same call: the matching declaration is NOT
    reported stale.

    RED at HEAD. Reddens under a body on: dropping unmatched declarations.
    """
    tree = _tree(tmp_path)
    monkeypatch.setattr(csr, "ANALYZERS", (_go(),))
    stale = _declaration(subject_key=f"{_MOD}.NoSuchFunction")

    report = check_tree(tree, declarations=(_declaration(), stale))
    assert stale in report.stale_declarations
    assert _declaration() not in report.stale_declarations


def test_check_tree_never_writes_into_the_tree_under_check(tmp_path, monkeypatch):
    """A workspace inside the tree under check is picked up by the check.

    ``fixture_reachability.construct_witness``'s reasoning, unchanged: the
    analyzer reads, and a helper that needs scratch space gets it elsewhere. A
    scratch file written into ``cmd/classify`` would be swept by
    :func:`discover_roots` on the next run.

    RED at HEAD. Reddens under a body on: any write into ``tree``.
    """
    tree = _tree(tmp_path)
    monkeypatch.setattr(csr, "ANALYZERS", (_go(),))
    before = _snapshot(tree)

    check_tree(tree)

    assert _snapshot(tree) == before, "check_tree wrote into the tree under check"


def test_check_tree_judges_every_subject_of_every_seal(tmp_path, monkeypatch):
    """A subject with no finding is a silent pass — the defect, one level up.

    Every (seal, subject) pair the mechanism derived must appear in
    ``findings``, in the deterministic order the contract names, and two runs
    over one tree must produce equal reports so a diff between them is a real
    change.

    TWO seals, deliberately. A one-finding report is in sorted order whatever
    the body does, so a single-subject fixture cannot tell a sorted report from
    an accidental one — and the second seal is named so that discovery order
    and sorted order DISAGREE: ``TestSeal_AlsoCovers`` sorts before
    ``TestSeal_ResolveConfigDual`` and is discovered after it.

    RED at HEAD. Reddens under a body on: dropping a subject; a
    nondeterministic or discovery-ordered report.
    """
    tree = _tree(tmp_path)
    second = Seal(
        symbol=_sym("TestSeal_AlsoCovers", "contract_seal_test.go", 990),
        test_id="cmd/classify.TestSeal_AlsoCovers",
    )
    second_root = Root(
        symbol=second.symbol,
        kind=EntrypointKind.TEST_FUNCTION,
        root_kind=RootKind.TEST,
        evidence="cmd/classify/contract_seal_test.go:990 func TestSeal_AlsoCovers",
    )
    graph = _graph(
        symbols=_ALL_SYMBOLS + (second.symbol,),
        edges=_PRODUCTION_EDGES + _SEAL_EDGES + (_edge(second.symbol, _LOAD_CONFIG),),
    )
    roots = (_GO_MAIN_ROOT, _TEST_ROOT, second_root)
    monkeypatch.setattr(csr, "ANALYZERS", (_go(roots=roots, graph=graph),))

    report = check_tree(tree)
    seals = discover_seals(graph, roots)
    expected = {
        (seal.test_id, symbol.key)
        for seal in seals
        for symbol in subjects_of_seal(seal, graph).symbols
    }
    assert len(expected) == 2, f"the fixture stopped having two subjects: {expected}"
    judged = {(f.seal.test_id, f.subject.key) for f in report.findings}
    assert judged == expected, f"unjudged subjects: {sorted(expected - judged)}"

    order = [(f.seal.test_id, f.subject.key) for f in report.findings]
    assert order == sorted(order), f"findings are not in (test_id, subject key) order: {order}"
    assert check_tree(tree).findings == report.findings, "two runs disagreed"


def test_discover_roots_refuses_a_tree_it_cannot_sweep(tmp_path):
    """Not a directory, and an analyzer that raises, are both refusals.

    A partial root set is worse than none: the roots that failed to appear are
    exactly the ones whose absence manufactures BREACHes.

    RED at HEAD. Predicted (unmeasured) under: returning ``()`` for a missing
    tree.

    **P4 ROUND 3 (2026-08-11): the second half of this clause is STRUCK, and it
    is the reason the convention itself was ruled on.** It used to read ";
    swallowing an :class:`AnalyzerError`", and gap 4 of the eight sat behind
    that sentence for a whole round, reading as coverage. This row supplies no
    analyzer and never reaches the ``except`` branch, so it cannot detect that
    mutation under ANY body — including the reference implementation the
    seal-file header measured against. Measured at ``4e66a01``: the swallow
    reddens only
    :func:`test_discover_roots_raises_on_a_fault_without_help_from_the_graph_builder`,
    where the coverage actually lives and where it is measured against the
    shipped body. Nothing about this row's own assertion moves; only the claim
    made on its behalf does.
    """
    with pytest.raises(CallSiteReachabilityError):
        discover_roots(tmp_path / "does-not-exist")


def test_build_call_graph_records_an_unreadable_file_and_propagates_a_fault(
    tmp_path, monkeypatch
):
    """One bad file is recorded; a missing toolchain propagates.

    The asymmetry is the contract and both halves are judged in one call.
    Raising on :class:`SourceUnreadable` would lose every other file's edges
    and turn one bad file into a total outage of the check; returning a partial
    graph after an :class:`AnalyzerUnavailable` would produce a graph whose
    missing edges look exactly like edges that do not exist.

    RED at HEAD. Reddens under a body on: swapping the two behaviours.
    """
    tree = _tree(tmp_path)

    monkeypatch.setattr(
        csr, "ANALYZERS", (_go(raises=SourceUnreadable("cmd/classify/main.go", "bad")),)
    )
    graph = build_call_graph(tree)
    assert "cmd/classify/main.go" in graph.unreadable_paths

    monkeypatch.setattr(
        csr,
        "ANALYZERS",
        (_go(raises=AnalyzerUnavailable(AnalyzerFault.TOOLCHAIN_MISSING, "no go")),),
    )
    with pytest.raises(CallSiteReachabilityError):
        build_call_graph(tree)


# --------------------------------------------------------------------------- #
# Part 10 — Symbol identity.
# --------------------------------------------------------------------------- #


def test_symbol_equality_and_hashing_are_over_the_key_alone():
    """A symbol that moved file is the same symbol.

    A graph keyed on location would report every refactor as a mass
    unreachability event — a repository-wide BREACH flood on a commit that
    changed no behaviour. The scaffold says a body must implement this
    explicitly, since a frozen dataclass hashes all three fields by default,
    and asks a seal to pin it.

    RED at HEAD: ``Symbol`` is a plain ``@dataclass(frozen=True)``, so
    ``dataclasses``' generated ``__eq__`` compares ``path`` and ``line`` too
    and the first assertion fails. That is the specific defect this row names.
    """
    moved = Symbol(key=_SUBJECT.key, path="cmd/classify/config.go", line=1)
    assert moved == _SUBJECT
    assert hash(moved) == hash(_SUBJECT)
    assert len({moved, _SUBJECT}) == 1

    renamed = Symbol(key=f"{_MOD}.ResolveConfig", path=_SUBJECT.path, line=_SUBJECT.line)
    assert renamed != _SUBJECT
    assert len({renamed, _SUBJECT}) == 2


# --------------------------------------------------------------------------- #
# Part 11 — the coverage gaps the P1 body disclosed against its own interest.
#
# ``feat/D5-body2`` ran 33 mutations against this file. Twenty-five reddened the
# rows naming them and no others; EIGHT reddened nothing, and the body reported
# all eight. Every row below closes one of those eight, or pins a property the
# round-2 rulings made pinnable for the first time. Each carries the mutation
# that proves it red, measured in a clone of this worktree with the ``.git``
# FILE removed and ``__pycache__`` cleared between runs — CPython keys bytecode
# on ``(mtime_seconds, size)``, so a same-size mutation restored within a second
# reports as covered when it is not.
#
# Symbols are cited rather than line numbers. A recorded line in this effort has
# been wrong three times out of five and one recording MOVED the line it
# recorded, because the paragraph that records it sits above the site.
#
# THE BODY'S OWN ASSESSMENT OF GAPS 6, 7 AND 8, TESTED RATHER THAN ACCEPTED
# ------------------------------------------------------------------------
# The body judged all three unreachable from the current fixtures and therefore
# in need of richer fixtures rather than more assertions. Measured on
# ``feat/D5-body2`` + this file, one mutation each:
#
#   * **Gap 7 (a default on ``_edge_is_resolved``) — the assessment is WRONG.**
#     "No fifth :class:`EdgeKind` is constructible" is false: ``Edge`` is a
#     frozen dataclass with no runtime type enforcement, and a stand-in member
#     goes into ``kind`` exactly as ``_Unnamed`` goes into ``Finding.reach`` in
#     :func:`test_adjudicate_raises_on_a_member_the_grid_has_never_seen`. It
#     needed a row, and it has one. What it did need from a fixture was the
#     ``.value`` attribute — ``_edge_order`` reads it while sorting, so a bare
#     string stand-in dies in the sort before it reaches the dispatch.
#   * **Gap 8 (sorting inside ``discover_seals``) — the assessment is RIGHT
#     about ``check_tree`` and does not settle the contract.** ``check_tree``
#     does re-sort its findings, so the mutation is invisible there on any
#     fixture. The rule is stated, is public, and gives its own reason, so the
#     row is written at the public function. Closed, at that boundary and only
#     there.
#   * **Gap 6 (unsorted subject symbols) — LEFT OPEN, and P4 round 3 RATIFIES
#     the outcome while OVERTURNING the reason. Both premises were measured and
#     both are wrong.**
#
#     What was written here: that the ``sorted()`` inside ``subjects_of_seal``
#     is a no-op on every graph the one production path can produce, because
#     ``build_call_graph`` sorts edges by ``(caller.key, callee.key, …)`` at
#     construction; and that a row would therefore "have to hand it a graph that
#     violates ``build_call_graph``'s own determinism contract", which would be
#     the mirror of "green on an unproducible input".
#
#     The first premise is true and irrelevant, and the second is false.
#     ``subjects_of_seal`` is PUBLIC, in ``__all__``, and takes the graph as an
#     ARGUMENT; the determinism contract belongs to ``build_call_graph``, and
#     ``CallGraph.edges`` is contracted in as many words as "Every edge, in no
#     guaranteed order". So a graph whose edges descend by callee key is a
#     LEGAL ``CallGraph`` that a row constructs with the ``_graph`` helper this
#     file already uses, needing no substitution and violating nothing.
#     Measured at ``4e66a01``: handed such a graph directly,
#     ``subjects_of_seal`` returns ``(Alpha, Zulu)`` for edges supplied
#     ``(Zulu, Alpha)`` — the ``sorted()`` is doing real work, not idling.
#
#     That correction matters beyond this gap. "A row red only on an input
#     production cannot construct" is the argument that would also strike the
#     three substitution rows P4 round 3 RATIFIES below, and here it was aimed
#     at an input that is neither unconstructible nor illegal.
#
#     The outcome stands on the OTHER reason, which is sufficient on its own:
#     **no sentence contracts ``Subject.symbols`` as ordered, and the order is
#     load-bearing for nothing** — ``check_tree`` re-sorts findings by
#     ``(test_id, subject key)``, a key that is total over them, and
#     :func:`test_check_tree_judges_every_subject_of_every_seal` pins that. A
#     row here would not guard a contract; it would legislate one into
#     existence for the row's own benefit, which is not a P2's standing and is
#     the shape R8 already refused. Measured at ``4e66a01``: deleting the
#     ``sorted()`` reddens nothing in this file, and under this ruling that is
#     the correct reading rather than a hole — the call is an uncontracted
#     determinism convenience for callers other than ``check_tree``, and
#     ``Subject.symbols`` now records that absence rather than leaving a reader
#     to re-derive it.
# --------------------------------------------------------------------------- #


def test_reachable_from_includes_its_own_roots_mapped_to_the_empty_chain():
    """R5's convention, and the two states it exists to keep apart.

    **Gap 1 of the eight.** P4 predicted this one unpinned and it was: excluding
    the roots from the map reddened nothing in this file. Three consequences ride
    on the convention and the row pins all three in one call:

      1. **A root is reachable from itself.** ``func main`` excluded from its own
         reach map comes back :attr:`Reach.FROM_TESTS_ONLY` or
         :attr:`Reach.FROM_NEITHER` — a false BREACH against the one symbol whose
         liveness is not in question.
      2. **"No production root" and "the production roots call nothing" are
         different values.** With roots included, a tree whose lonely ``main``
         calls nothing yields ``{main: ()}``, which is not empty; with them
         excluded it yields ``{}``, the same value as a tree with no roots at
         all, and :func:`check_subject` step 2 turns the second into an
         abstention over EVERY subject in the tree. The row asserts the two maps
         differ, which is the property, rather than either one's contents.
      3. A zero-edge chain is :attr:`PathQuality.RESOLVED`, which is gap 2 and
         has its own row below.

    The control is judged in the same call: a symbol the root really reaches
    carries a NON-empty chain, so a body that returns ``{key: () for every
    symbol}`` does not pass; and the canonical subject is still absent from the
    production map, so the defect the fixture exists for is still the defect.

    GREEN at HEAD, and mutation-verified rather than trusted. Reddens under a
    body on: ``_sweep_chains`` returning ``{k: v for k, v in chains.items() if k
    not in set(root_keys)}`` — the exact exclusion P4 predicted. Measured: that
    mutation reddens this row and
    :func:`test_a_subject_that_is_itself_a_production_root_is_a_resolved_pass`,
    and no other row in the file. The coupling is reported rather than designed
    away: excluding the roots removes the very map entry whose zero-edge chain
    the other row judges.

    **P4 ROUND 3 (2026-08-11): CONFIRMED as honest reporting, and the row is
    NOT split — but the sentence that used to end this paragraph ("the two rows
    cannot be made independent of it without one of them stopping being about
    R5") overstated it and is struck.** Re-measured at ``4e66a01``: the
    exclusion reddens exactly those two rows and no others, and the other row
    decomposes. Its **contract half is already independent** — half 1 judges
    ``_chain_quality`` against ``_production_reach()``, which this file writes
    out by hand precisely so that no row is fed the output of a function it is
    also sealing. Only its **end-to-end half** co-reddens, because that half
    runs :func:`check_tree` and therefore the real traversal. An end-to-end
    half that did not depend on the mechanism's own traversal would not be
    end-to-end, so splitting would delete integration evidence to buy an
    independence the contract half already has. Each row also still has a
    mutation that reddens it alone.
    """
    graph = _graph()

    production = reachable_from(graph, (_GO_MAIN_ROOT,))
    assert _MAIN.key in production, (
        "the production root is missing from its own reach map; a subject that "
        "IS an entrypoint would come back unreached, which is the loudest "
        "possible way to be wrong"
    )
    assert production[_MAIN.key] == (), (
        f"a root maps to {production[_MAIN.key]!r} rather than the empty chain"
    )
    assert production[_FIND_CONFIG.key], (
        "the control failed: a symbol two edges from the root carries no chain, "
        "so the empty chain above says nothing about roots"
    )
    assert _SUBJECT.key not in production, (
        "the control failed: production reaches the canonical defect, so this "
        "fixture is no longer the fixture"
    )

    tests = reachable_from(graph, (_TEST_ROOT,))
    assert tests.get(_SEAL_FN.key) == (), "the test root is missing from its own map"

    # 2. The two states that must not collapse, compared in this call.
    lonely_root = reachable_from(_graph(edges=_SEAL_EDGES), (_GO_MAIN_ROOT,))
    no_root = reachable_from(graph, ())
    assert no_root == {}, f"a traversal from no root produced {no_root!r}"
    assert lonely_root != no_root, (
        "'this tree has a main that calls nothing' and 'this tree has no "
        "production root' are the same map, so NO_ENTRYPOINT cannot be told "
        "from an entrypoint with no callees"
    )


def test_a_subject_that_is_itself_a_production_root_is_a_resolved_pass(
    tmp_path, monkeypatch
):
    """A zero-edge chain is RESOLVED, and NOT_APPLICABLE takes the check down.

    **Gap 2 of the eight, and the one that matters most.** P4 predicted it
    unpinned and it was: no fixture in this file had a subject that is itself a
    production root, so spelling the zero-edge chain
    :attr:`PathQuality.NOT_APPLICABLE` reddened nothing. It is not a cosmetic
    difference — it hands :func:`adjudicate` the pair ``(FROM_PRODUCTION,
    NOT_APPLICABLE)``, which the grid RAISES on as a mechanism bug, so the whole
    check dies on **every** tree whose seal covers an entrypoint.

    That state is ordinary rather than exotic, which is how this row knows
    production can reach the input. :func:`reachable_from` maps every production
    root's own key to ``()`` (R5), and R5 names four kinds of subject that are
    themselves roots: a ``GO_INIT``, a ``GO_PACKAGE_VAR``, a
    ``PYTHON_IMPORT_TIME`` module body and a console-script ``main``. The last
    is the common one — ``pyproject``'s ``[project.scripts]`` entry is a
    ``PRODUCTION`` root and a pytest row calling it is unremarkable — and a Go
    test calling ``main()`` from inside ``package main`` is legal and does
    happen. The end-to-end half below is that case, in Go, over the vendored
    tree.

    Two halves, and the second is the one that would have caught the outage:

      * one pair judged directly, where the quality must be RESOLVED and must
        rule the same way a multi-edge resolved pass rules;
      * a whole :func:`check_tree` run over a tree whose seal covers ``main``,
        which must RETURN a report rather than raise out of the grid.

    Controls judged in the same call: the multi-edge resolved pass, so a body
    that answers RESOLVED for everything is caught by
    :func:`test_an_over_approximated_path_is_never_spelled_resolved`; and the
    canonical subject, which must still be the B1 verdict in the same report, so
    an unconditionally-passing run does not satisfy this row.

    GREEN at HEAD, mutation-verified. Reddens under a body on: ``_chain_quality``
    answering ``NOT_APPLICABLE`` for the empty chain. Measured: that mutation
    reddens this row and no other in the file. It also reddens under gap 1's
    root-exclusion mutation, which is reported at
    :func:`test_reachable_from_includes_its_own_roots_mapped_to_the_empty_chain`
    and is a property of R5 rather than a weakness in either row.
    """
    # Half 1 — one pair, judged directly. ``_production_reach`` maps _MAIN to
    # the empty chain because _MAIN is where it starts.
    entrypoint = _judge(_MAIN)
    assert entrypoint.reach is Reach.FROM_PRODUCTION
    assert entrypoint.path is not None and entrypoint.path.edges == ()
    assert entrypoint.path.root is _GO_MAIN_ROOT, (
        "the zero-edge chain named a root the caller never supplied"
    )
    assert entrypoint.quality is PathQuality.RESOLVED, (
        f"a chain with no links was spelled {entrypoint.quality.value}; the "
        "minimum over no edges is the strong value, and the weak spelling hands "
        "adjudicate a pair the grid raises on"
    )

    multi_edge = _judge(_FIND_CONFIG)
    assert multi_edge.quality is PathQuality.RESOLVED and multi_edge.path.edges, (
        "the control failed: the multi-edge resolved pass is not resolved"
    )
    assert adjudicate(entrypoint, None) is adjudicate(multi_edge, None), (
        "a subject that is its own entrypoint rules differently from a subject "
        "two edges away, though both are resolved production paths"
    )

    # Half 2 — the whole run, over a tree whose seal covers the entrypoint.
    tree = _tree(tmp_path)
    covers_main = _sym("TestSeal_Main", "contract_seal_test.go", 120)
    main_seal_root = Root(
        symbol=covers_main,
        kind=EntrypointKind.TEST_FUNCTION,
        root_kind=RootKind.TEST,
        evidence="cmd/classify/contract_seal_test.go:120 func TestSeal_Main",
    )
    graph = _graph(
        symbols=_ALL_SYMBOLS + (covers_main,),
        edges=_PRODUCTION_EDGES + _SEAL_EDGES + (_edge(covers_main, _MAIN),),
    )
    monkeypatch.setattr(
        csr,
        "ANALYZERS",
        (_go(roots=(_GO_MAIN_ROOT, _TEST_ROOT, main_seal_root), graph=graph),),
    )

    report = check_tree(tree)
    on_main = [f for f in report.findings if f.subject.key == _MAIN.key]
    assert len(on_main) == 1, (
        f"the seal covering the entrypoint produced {len(on_main)} findings"
    )
    assert on_main[0].reach is Reach.FROM_PRODUCTION
    assert on_main[0].quality is PathQuality.RESOLVED
    assert sum(report.dispositions.values()) == len(report.findings), (
        "a finding reached the report without being ruled on, which is what "
        "the grid raising on (FROM_PRODUCTION, NOT_APPLICABLE) prevents"
    )

    canonical = [f for f in report.findings if f.subject.key == _SUBJECT.key]
    assert canonical and canonical[0].reach is Reach.FROM_TESTS_ONLY, (
        "the control failed: the canonical defect is not the B1 verdict in this "
        "report, so the pass above is not evidence of anything"
    )


def test_check_tree_refuses_a_subject_record_a_second_constructor_built(
    tmp_path, monkeypatch
):
    """R2's second layer, which no row reached.

    **Gap 3 of the eight.** P4 predicted it and it was: deleting
    ``_validate_subject``'s call inside :func:`check_tree` reddened nothing,
    because :func:`subjects_of_seal` is the record's only constructor today and
    it validates its own output. R2 ruled the precondition in ANYWAY — "a second
    constructor or a caller-supplied record would otherwise reach the judgement
    loop unchecked, and the layer that ACTS on a non-judgement is the layer
    where the non-judgement becomes an answer" — so the layer is contracted and
    was pinned by nothing.

    The only way a row can exhibit the state is to BE the second constructor R2
    hypothesises, which is what the substitution below is. It is not a fixture
    that production produces and this row does not claim otherwise: the input is
    reachable exactly when someone writes the second constructor, which is the
    event the precondition exists for, and a layer whose only justification is a
    future caller cannot be sealed by any input that exists before that caller
    does. The alternative is not sealing it.

    Both contradictions are swept, because they fail differently and the second
    is the silent one: a gap ALONGSIDE symbols makes :func:`check_tree` count a
    gap and ``continue``, dropping every symbol the record also named — a silent
    pass over real subjects; an empty record with no gap produces no finding and
    no count at all.

    The control is judged in the same call: the real constructor's records run
    through the same tree and produce a report with findings, so a body that
    raises on every subject does not pass.

    GREEN at HEAD, mutation-verified. Reddens under a body on: deleting the
    ``_validate_subject(subject)`` call in :func:`check_tree`. Measured: that
    mutation reddens this row and no other in the file.
    """
    tree = _tree(tmp_path)
    monkeypatch.setattr(csr, "ANALYZERS", (_go(),))

    baseline = check_tree(tree)
    assert baseline.findings, (
        "the control failed: the unsubstituted run produced no findings, so a "
        "refusal below would say nothing"
    )

    two_answers = Subject(
        seal=_SEAL,
        symbols=(_SUBJECT,),
        gap=SubjectGap.NO_CALLS,
        detail="a record that says two things",
    )
    says_nothing = Subject(
        seal=_SEAL, symbols=(), gap=None, detail="a record that says nothing"
    )

    for malformed in (two_answers, says_nothing):
        monkeypatch.setattr(
            csr, "subjects_of_seal", lambda seal, graph, _r=malformed: _r
        )
        with pytest.raises(CallSiteReachabilityError):
            check_tree(tree)


@pytest.mark.parametrize("fault", list(AnalyzerFault), ids=lambda f: f.value)
def test_discover_roots_raises_on_a_fault_without_help_from_the_graph_builder(
    tmp_path, monkeypatch, fault
):
    """The root sweep's own refusal, measured where nothing can mask it.

    **Gap 4 of the eight, and NOT predicted.** Deleting
    :func:`discover_roots`' ``raise`` and swallowing the
    :class:`AnalyzerError` instead reddened nothing — including
    :func:`test_an_analyzer_fault_never_reads_as_a_clean_tree`, whose
    ``Reddens under a body on:`` clause names exactly that mutation. The reason
    is structural rather than an oversight: that row goes through
    :func:`check_tree`, which calls :func:`build_call_graph` immediately after
    :func:`discover_roots`, and ``build_call_graph``'s own raise fires on the
    same faulting analyzer. So the whole-tree row cannot tell which of the two
    refused, and a body that swallowed the fault HERE and returned a partial
    root set would have shipped green.

    That is the failure R1's ruling exists to prevent. R1 STRUCK
    :attr:`UndecidedReason.ANALYZER_FAULT` precisely so that a fault RAISES
    rather than abstains — "a fault leaves no roots, therefore no seals,
    therefore no subjects to abstain over, and an abstention you cannot
    enumerate is silence with a label". A swallowed fault does something worse
    than abstain: it returns a root set missing exactly the roots whose absence
    manufactures BREACHes, and the report carries no mark of it at all.

    :class:`SourceUnreadable` is swept alongside :class:`AnalyzerUnavailable`
    because the asymmetry with :func:`build_call_graph` is the contract:
    ``build_call_graph`` RECORDS an unreadable file and abstains at judgement
    time; ``discover_roots`` raises on "any analyzer raises
    :class:`AnalyzerError`", of which :class:`SourceUnreadable` is one. A body
    that copies the graph builder's handling into the root sweep loses every
    other analyzer's roots to a silent ``continue``.

    The control is judged in the same call: the same analyzer, not faulting,
    returns a non-empty root set — so a body that raises unconditionally does
    not pass.

    GREEN at HEAD, mutation-verified. Reddens under a body on: replacing
    :func:`discover_roots`' ``except AnalyzerError`` raise with ``continue``.
    Measured: that mutation reddens this row and no other in the file.
    """
    tree = _tree(tmp_path)

    for broken in (
        AnalyzerUnavailable(fault, "measured by a seal"),
        SourceUnreadable("cmd/classify/main.go", "measured by a seal"),
    ):
        monkeypatch.setattr(csr, "ANALYZERS", (_go(raises=broken),))
        with pytest.raises(CallSiteReachabilityError):
            discover_roots(tree)

    monkeypatch.setattr(csr, "ANALYZERS", (_go(),))
    assert discover_roots(tree), (
        "the control failed: the healthy analyzer derived no roots at all, so "
        "the refusals above are not about the fault"
    )


@pytest.mark.parametrize("kind", list(EntrypointKind), ids=lambda k: k.value)
def test_root_kind_is_derived_from_the_kind_and_never_asserted_by_the_row(
    tmp_path, monkeypatch, kind
):
    """The invariant ``_synthetic_root`` was struck for bypassing, sealed at last.

    **Gap 5 of the eight, NOT predicted, and the most surprising of them:
    deleting :func:`_validate_root` entirely reddened nothing.** The contract
    "``root_kind`` is DERIVED from ``kind`` and from ``seal_verify.is_test_path``
    over the declaring file, never asserted by the analyzer independently, so a
    row cannot mark its own roots production" had **no row at all** — while the
    P4 that struck ``_synthetic_root`` gave as its second reason that the
    fallback "bypasses the module's own validator" and "could mint what
    ``_validate_root`` refuses outright". An invariant load-bearing enough to
    delete production code over, and nothing measured it.

    Swept over the whole of :class:`EntrypointKind`, both directions per member,
    which is strictly stronger than a few hand-picked rows and is what pins the
    derivation TABLE rather than a body's ``if``: for each member, the root
    whose ``root_kind`` the table derives is ACCEPTED and the root asserting the
    other one is REFUSED. A member added without visiting
    ``_ROOT_KIND_BY_ENTRYPOINT`` is absent from it, and the refusal above the
    table is what this sweep sees.

    Both wrong answers are intolerable and the sweep covers both: a TEST root
    read as production silently certifies everything below it, and a production
    root read as test floods the report with false BREACHes.

    Production reaches this input on the first analyzer written: every
    :class:`Root` an analyzer produces goes through this validator, and the
    values come from a Go helper's JSON, not from a Python literal.

    GREEN at HEAD, mutation-verified. Reddens under a body on: making
    :func:`_validate_root` a no-op. Measured: that mutation reddens this row
    and its sibling
    :func:`test_a_root_that_disagrees_with_its_own_file_or_names_no_kind_is_refused`,
    and no other row in the file. A DEFAULT on ``_ROOT_KIND_BY_ENTRYPOINT``
    does NOT redden this row and is measured as reddening the sibling only —
    recorded here rather than claimed, because the table still names all eight
    members and this sweep cannot see past them. That is the sibling's job.
    """
    in_tests = kind is EntrypointKind.TEST_FUNCTION
    path = "contract_seal_test.go" if in_tests else "main.go"
    symbol = _sym(f"rootOf_{kind.value}", path, 7)
    derived = RootKind.TEST if in_tests else RootKind.PRODUCTION
    asserted = RootKind.PRODUCTION if in_tests else RootKind.TEST

    tree = _tree(tmp_path)

    honest = Root(
        symbol=symbol,
        kind=kind,
        root_kind=derived,
        evidence=f"cmd/classify/{path}:7, derived for {kind.value}",
    )
    monkeypatch.setattr(csr, "ANALYZERS", (_go(roots=(honest,)),))
    assert discover_roots(tree) == (honest,), (
        f"the control failed: a well-formed {kind.value} root was refused, so "
        "the refusal below is not about the asserted root_kind"
    )

    lying = Root(
        symbol=symbol,
        kind=kind,
        root_kind=asserted,
        evidence=f"cmd/classify/{path}:7, asserted by the row",
    )
    monkeypatch.setattr(csr, "ANALYZERS", (_go(roots=(lying,)),))
    with pytest.raises(CallSiteReachabilityError):
        discover_roots(tree)


def test_a_root_that_disagrees_with_its_own_file_or_names_no_kind_is_refused(
    tmp_path, monkeypatch
):
    """The other three refusals ``_validate_root`` owes, none of them pinned.

    **Gap 5 of the eight, continued.** The sweep above pins the derivation
    table; these are the three refusals that do not fall out of it, and the
    third is the one the struck fallback could actually mint.

      * **Not a :class:`Root` at all.** An analyzer returning dicts, or
        ``None``s, or the tuples an earlier protocol used. Refused by name
        rather than by ``AttributeError`` three layers down.
      * **A kind this module cannot classify.** The stand-in below is the ninth
        :class:`EntrypointKind` somebody adds without visiting
        ``_ROOT_KIND_BY_ENTRYPOINT`` — the same device
        :func:`test_adjudicate_raises_on_a_member_the_grid_has_never_seen` uses
        for :class:`Reach`, and for the same reason: naming the states does not
        give exhaustiveness for free.
      * **A production entrypoint declared in a test file.** This is the case
        the P4 named when it struck ``_synthetic_root``: "hand it a chain whose
        first caller is declared in a test file and it returns a ``GO_MAIN``
        root in a ``_test.go``, which is a tree this module does not
        understand". It is also the permissive direction — a ``GO_MAIN`` root
        inside ``contract_seal_test.go`` makes the entire test closure read
        FROM_PRODUCTION, which certifies every B1 defect in the package.
      * **A ``TEST_FUNCTION`` declared outside the tests**, the mirror, which
        would make production symbols read as test-only and flood the report.

    The control is the sweep above, and one is judged here too: the same
    analyzer with the well-formed pair returns both roots.

    GREEN at HEAD, mutation-verified, three mutations. Reddens under a body on:
    making :func:`_validate_root` a no-op; giving ``_ROOT_KIND_BY_ENTRYPOINT``
    a default (``.get(root.kind, root.root_kind)``, the shape that lets a row
    assert its own answer for a kind nobody classified); dropping the
    ``is_test_path`` cross-check and trusting ``kind`` alone. Measured: the
    second and third redden this row and no other in the file; the first
    reddens this row and the sweep above.
    """
    tree = _tree(tmp_path)

    class _NinthKind:
        value = "a kind nobody has classified"

    refusals = (
        {"symbol": _MAIN.key, "kind": "not a Root at all"},
        Root(
            symbol=_MAIN,
            kind=_NinthKind(),
            root_kind=RootKind.PRODUCTION,
            evidence="a member added without visiting the table",
        ),
        Root(
            symbol=_SEAL_FN,
            kind=EntrypointKind.GO_MAIN,
            root_kind=RootKind.PRODUCTION,
            evidence="func main inside contract_seal_test.go",
        ),
        Root(
            symbol=_MAIN,
            kind=EntrypointKind.TEST_FUNCTION,
            root_kind=RootKind.TEST,
            evidence="a TEST_FUNCTION inside main.go",
        ),
    )
    for refused in refusals:
        monkeypatch.setattr(csr, "ANALYZERS", (_go(roots=(refused,)),))
        with pytest.raises(CallSiteReachabilityError):
            discover_roots(tree)

    monkeypatch.setattr(csr, "ANALYZERS", (_go(),))
    assert set(discover_roots(tree)) == {_GO_MAIN_ROOT, _TEST_ROOT}, (
        "the control failed: the well-formed pair was refused too"
    )


def test_check_subject_is_handed_its_roots_and_never_invents_one():
    """The struck fallback's two replacements, neither of which a row measured.

    **Newly pinnable, flagged by P4 for this pass.** The body measured that this
    seal file is **0 red in all three states** — as shipped, with the ``roots``
    default restored, and with the default AND ``_synthetic_root`` restored —
    so nothing distinguished a signature that refuses the call from one that
    accepts it and invents the evidence. Both halves are sealed here, and they
    are separate defects with separate mutations:

      * **The signature.** ``roots`` is keyword-only and REQUIRED. A default of
        ``()`` converts "this layer was not handed the evidence" into "this
        layer made some up", at runtime, where no reader is looking. The
        refusal must happen before any judgement starts, which is what the
        :class:`TypeError` half asserts — it is the interpreter refusing, and
        that is the point: no other layer has to be right for it to hold.
      * **The raise.** :func:`_witness` refuses a chain that originates at a key
        no supplied :class:`Root` of that :class:`RootKind` names. The traversal
        reported a path from something it was never given as a start; that is a
        mechanism bug, not a licence to invent the start.

    Both directions of the second half are swept, because the fallback was
    wrong in both: a TEST chain whose origin the caller did not declare, and a
    PRODUCTION chain likewise. The ``RootKind`` is part of the lookup, so
    supplying the right symbol under the wrong kind must not satisfy it either
    — that is how a test root laundered itself into a production answer.

    Production reaches the input the moment ``check_tree`` is not the only
    caller, and the P4 measured that the suite ITSELF was the whole of the
    fallback's liveness: 13 rows reached it before the seal amendment and 0
    after. A branch of production code only tests execute is
    :attr:`Reach.FROM_TESTS_ONLY` spelled in Python, inside D5.

    The control is judged in the same call: with both records supplied, the same
    arguments return the B1 verdict.

    GREEN at HEAD, mutation-verified. Reddens under a body on: restoring
    ``roots: Sequence[Root] = ()`` (the TypeError half); restoring
    :func:`_witness`'s ``declared is None`` fallback to a synthesised
    :class:`Root` (the raise half). Measured: each mutation reddens this row and
    no other in the file.
    """
    with pytest.raises(TypeError):
        check_subject(
            _SEAL,
            _SUBJECT,
            graph=_graph(),
            production_reach=_production_reach(),
            test_reach=_test_reach(),
            analyzer=_go(),
        )

    # The TEST chain to the canonical subject originates at the seal, which this
    # root set does not name.
    with pytest.raises(CallSiteReachabilityError):
        _judge(_SUBJECT, roots=(_GO_MAIN_ROOT,))

    # The PRODUCTION chain to findConfig originates at main, likewise.
    with pytest.raises(CallSiteReachabilityError):
        _judge(_FIND_CONFIG, roots=(_TEST_ROOT,))

    # The right symbol under the wrong RootKind is not the same record.
    mislabelled = Root(
        symbol=_SEAL_FN,
        kind=EntrypointKind.GO_MAIN,
        root_kind=RootKind.PRODUCTION,
        evidence="the seal, asserted as a production entrypoint",
    )
    with pytest.raises(CallSiteReachabilityError):
        _judge(_SUBJECT, roots=(_GO_MAIN_ROOT, mislabelled))

    dark = _judge(_SUBJECT)
    assert dark.reach is Reach.FROM_TESTS_ONLY, (
        "the control failed: with both records supplied the canonical subject "
        "is not the B1 verdict, so the refusals above are not about the roots"
    )
    assert dark.test_path is not None and dark.test_path.root is _TEST_ROOT


def test_parse_failed_outranks_no_entrypoint_when_both_hold(tmp_path, monkeypatch):
    """The order of the two abstentions, which no fixture made both hold at once.

    **Newly pinnable, flagged by P4 for this pass.** D4 confirmed the body's
    placement of ``PARSE_FAILED`` and ruled that the position relative to step 2
    is the SUBSTANTIVE half, and it was pinned by nothing: the existing rows
    exercise each abstention alone
    (:func:`test_a_source_unreadable_abstains_over_the_whole_tree`,
    :func:`test_no_entrypoint_over_a_library_tree_abstains`) and no tree made
    both hold, so swapping the two steps reddened nothing.

    The two abstentions are not equals. ``NO_ENTRYPOINT`` is a positive claim
    ABOUT THE TREE — "this tree has no production entrypoint of any
    :class:`EntrypointKind`" — and an unparsed file is exactly where an
    undiscovered ``func main`` would be, so under a parse hole that claim is
    computed AROUND the hole and the mechanism cannot support it.
    ``PARSE_FAILED`` is the confession that the tree was not fully read. When
    both hold the caller must see the confession, not the claim: the other
    reading has the mechanism asserting a fact it derived around a gap, which is
    anti-requirement 2 in the abstention register — failing to look may only
    make an answer LESS conclusive.

    Both controls are judged in the same call, and the first is the one that
    stops a body answering ``PARSE_FAILED`` unconditionally: the same library
    tree with nothing unreadable still answers ``NO_ENTRYPOINT``.

    GREEN at HEAD, mutation-verified. Reddens under a body on: moving
    :func:`check_subject`'s ``unreadable_paths`` check after the zero-production-
    roots check. Measured: that mutation reddens this row and no other in the
    file.
    """
    tree = _tree(tmp_path)

    def _reasons(analyzer):
        monkeypatch.setattr(csr, "ANALYZERS", (analyzer,))
        report = check_tree(tree)
        assert report.findings, "a run produced no finding to read a reason off"
        return {f.reason for f in report.findings}

    both_hold = _reasons(
        _go(roots=(_TEST_ROOT,), graph=_graph(unreadable=("cmd/classify/main.go",)))
    )
    assert both_hold == {UndecidedReason.PARSE_FAILED}, (
        f"a tree with no production root AND an unparsed file answered "
        f"{sorted(r.value for r in both_hold)}; NO_ENTRYPOINT is a positive "
        "claim about a tree that was not fully read, and the unparsed file is "
        "exactly where the missing entrypoint would be"
    )

    only_no_entrypoint = _reasons(_go(roots=(_TEST_ROOT,)))
    assert only_no_entrypoint == {UndecidedReason.NO_ENTRYPOINT}, (
        "the control failed: a fully-read library tree no longer answers "
        "NO_ENTRYPOINT, so the answer above is not an ordering"
    )

    only_parse_failed = _reasons(_go(graph=_graph(unreadable=("cmd/classify/main.go",))))
    assert only_parse_failed == {UndecidedReason.PARSE_FAILED}, (
        "the control failed: a rooted tree with an unparsed file no longer "
        "answers PARSE_FAILED"
    )


def test_check_subject_validates_every_finding_it_returns(monkeypatch):
    """The postcondition layer, shown load-bearing on its own.

    **Also worth a row, and this file agrees it is sealable.** The body proved
    by mutation that the two :func:`_validate_finding` layers are separable —
    postcondition alone removed, a direct :func:`check_subject` call returns a
    two-answer :class:`Finding`; precondition alone removed,
    :func:`check_tree` returns a report silently counting it as one ABSTAIN —
    and that separability is a DESIGN PROPERTY, ratified over a wider guard
    inside ``_abstention`` that would have covered more for less code, **because
    the wider guard would have made the second layer unfalsifiable**. A property
    defended that explicitly and pinned by nothing is worth a row.

    A seal cannot mutate the module, so it cannot make :func:`check_subject`
    BUILD a two-answer record — the five returns are consistent by construction
    and every field is computed. What it can do is observe that the validator
    runs on the record actually handed back, at every return, which is the
    obligation. The substitution below wraps the real validator rather than
    replacing it, so the module's own refusals still fire.

    Three of the five returns are swept, chosen to be three different reaches so
    that no single ``if`` covers them, and the assertion is on OBJECT IDENTITY:
    a body that validates some other record, or a copy, does not pass.

    The last assertion is the non-vacuity control and it is the one that makes
    the rest mean anything: a call that raises before constructing anything
    records NOTHING. So the recorder measures calls rather than being satisfied
    by the substitution existing.

    GREEN at HEAD, mutation-verified. Reddens under a body on: dropping any
    ``_validate_finding`` call from :func:`check_subject`; moving the
    postcondition into :func:`_abstention`, which reaches three of the five
    returns and none of the two that are not abstentions. Measured: both
    mutations redden this row and no other in the file.
    """
    seen: list[Finding] = []
    real = csr._validate_finding

    def _recording(finding):
        seen.append(finding)
        return real(finding)

    monkeypatch.setattr(csr, "_validate_finding", _recording)

    returned = [
        _judge(_SUBJECT, analyzer=_go()),          # FROM_TESTS_ONLY
        _judge(_SUBJECT, analyzer=_python()),      # UNDECIDED / DYNAMIC_EDGE
        _judge(_FIND_CONFIG, analyzer=_go()),      # FROM_PRODUCTION
    ]
    assert {f.reach for f in returned} == {
        Reach.FROM_TESTS_ONLY,
        Reach.UNDECIDED,
        Reach.FROM_PRODUCTION,
    }, "the three returns swept here no longer cover three different reaches"

    for finding in returned:
        assert any(finding is candidate for candidate in seen), (
            f"check_subject returned a {finding.reach.value} finding it never "
            "validated; the postcondition is the only guard on a direct call, "
            "which is how every D5 row reaches this module while ANALYZERS is "
            "empty"
        )

    seen.clear()
    with pytest.raises(CallSiteReachabilityError):
        _judge("not a Symbol at all")
    assert seen == [], (
        "the control failed: the recorder logged a validation for a call that "
        "never built a finding, so it is not measuring calls"
    )


def test_check_tree_validates_a_finding_check_subject_never_built(
    tmp_path, monkeypatch
):
    """The precondition layer, shown load-bearing on its own.

    **Also worth a row, second half.** :func:`check_tree` builds two findings
    itself — the ``UNSUPPORTED_LANGUAGE`` abstention and
    :func:`_unnameable_finding` — and :func:`check_subject` never sees either,
    so the precondition is the ONLY guard on them. The body measured this by
    rewriting ``_unnameable_finding`` as a second :class:`Finding` constructor
    emitting ``reach=UNDECIDED`` with ``reason=None``, "which is R2's
    hypothesised second constructor made real", and found that with the
    precondition removed :func:`check_tree` returns a report carrying the
    two-answer finding, counted as one ABSTAIN.

    This row is that measurement, done the way a seal is allowed to do it: the
    second constructor is substituted rather than written into the module. The
    substituted name is private, and that is a deliberate choice with an
    alternative that is worse. ``check_tree``'s other self-built finding goes
    through ``_abstention``, which fixes ``reach`` and guards ``reason``, so it
    cannot be made two-answered from outside; the seam R2 names is the one
    substituted here, and the alternative is not sealing the layer at all.

    The control is judged in the same call, and it is the strong one: the SAME
    tree with the real constructor returns a report that counts exactly one
    ABSTAIN for the unnameable seal. So the refusal below is about the record's
    shape and not about the tree, the seal, or the substitution.

    GREEN at HEAD, mutation-verified. Reddens under a body on: deleting the
    ``_validate_finding(finding)`` call in :func:`check_tree`'s disposition
    loop. Measured: that mutation reddens this row and no other in the file.
    """
    tree = _tree(tmp_path)
    mystery = Seal(
        symbol=_sym("TestSeal_ViaValue", "contract_seal_test.go", 300),
        test_id="cmd/classify.TestSeal_ViaValue",
    )
    mystery_root = Root(
        symbol=mystery.symbol,
        kind=EntrypointKind.TEST_FUNCTION,
        root_kind=RootKind.TEST,
        evidence="cmd/classify/contract_seal_test.go:300 func TestSeal_ViaValue",
    )
    graph = _graph(
        symbols=(_MAIN, _DECOY, mystery.symbol),
        edges=(_edge(_MAIN, _DECOY),),
        unresolved=(
            (
                mystery.symbol,
                "cmd/classify/contract_seal_test.go:310",
                "call through a func value",
            ),
        ),
    )
    monkeypatch.setattr(
        csr,
        "ANALYZERS",
        (_go(roots=(_GO_MAIN_ROOT, mystery_root), graph=graph),),
    )

    real = check_tree(tree)
    assert real.dispositions[Disposition.ABSTAIN] == 1, (
        "the control failed: the unnameable seal did not produce exactly one "
        "abstention, so the refusal below is not about the record"
    )
    assert all(f.reach is Reach.UNDECIDED for f in real.findings)
    assert not any(
        f.seal.test_id == _SEAL.test_id for f in real.findings
    ), "this tree deliberately holds one seal, and it is the unnameable one"

    def _second_constructor(seal, graph, detail):
        return Finding(
            seal=seal,
            subject=Symbol(key=f"{seal.symbol.key}.<unnameable>", path=seal.symbol.path, line=1),
            reach=Reach.UNDECIDED,
            quality=PathQuality.NOT_APPLICABLE,
            path=None,
            test_path=None,
            reason=None,
            detail=detail,
        )

    monkeypatch.setattr(csr, "_unnameable_finding", _second_constructor)
    with pytest.raises(CallSiteReachabilityError):
        check_tree(tree)


def test_an_edge_kind_in_neither_strength_class_is_a_refusal_not_a_default():
    """The fifth ``EdgeKind``, which the body reported unconstructible.

    **Gap 7 of the eight, NOT predicted, and the body's own assessment of it is
    WRONG — measured, not argued.** The body judged that giving
    ``_edge_is_resolved`` a default is unreachable from the fixtures because "no
    fifth :class:`EdgeKind` is constructible". :class:`Edge` is a plain frozen
    dataclass with no runtime type enforcement, so a stand-in member goes into
    ``kind`` exactly as ``_Unnamed`` goes into ``Finding.reach`` in
    :func:`test_adjudicate_raises_on_a_member_the_grid_has_never_seen`, which is
    the device this file already uses and which P4 ratified there. The gap needed
    a row, not a richer fixture.

    **P4 ROUND 3 (2026-08-11): CONFIRMED, and the duck-type surface is recorded
    in full, because half of it was written down and half was not.** A stand-in
    for :attr:`Edge.kind` must be ``(hashable, .value)`` — BOTH, and for two
    different reasons at two different layers. ``_edge_order`` reads
    ``edge.kind.value`` while sorting, so a stand-in without one dies in the
    sort before reaching the dispatch (recorded below already); and
    ``_edge_is_resolved`` tests ``kind in _RESOLVED_EDGE_KINDS``, a set
    membership, so an unhashable stand-in raises ``TypeError`` rather than the
    mechanism's own error and the row would pass for the wrong reason.
    ``_FifthKind`` below satisfies both — a plain class, hashable by identity,
    carrying a ``str`` ``value``. An incomplete record of a duck-type surface is
    how the next stand-in breaks.

    What a default would decide, silently and for the whole repository: whether
    an unmarked over-approximation reads as the strong pass. ``_RESOLVED_EDGE_KINDS``
    and ``_OVER_APPROXIMATING_EDGE_KINDS`` are written as two tables whose union
    must cover the enum for exactly this reason, and a member added without
    visiting that dispatch is in neither.

    Both public paths that classify an edge are swept, because they fail at
    different layers and a body could default one without the other:
    :func:`reachable_from`'s resolved-only sweep, and the chain quality
    :func:`check_subject` puts on a :class:`CallPath`.

    The control is judged in the same call and it is over the WHOLE enum: each
    of the four real members classifies without raising, and the two classes
    produce two different qualities — so a body that raises on everything, or
    one that answers RESOLVED for everything, does not pass.

    GREEN at HEAD, mutation-verified. Reddens under a body on: ``return False``
    or ``return True`` in place of ``_edge_is_resolved``'s raise. Measured: both
    mutations redden this row and no other in the file.
    """

    class _FifthKind:
        value = "a strength nobody has classified"

    unknown = Edge(
        caller=_MAIN,
        callee=_FIND_CONFIG,
        kind=_FifthKind(),
        site="cmd/classify/main.go:180",
    )

    with pytest.raises(CallSiteReachabilityError):
        reachable_from(_graph(edges=(unknown,)), (_GO_MAIN_ROOT,))

    with pytest.raises(CallSiteReachabilityError):
        _judge(
            _FIND_CONFIG,
            graph=_graph(edges=(unknown,) + _SEAL_EDGES),
            production_reach={_MAIN.key: (), _FIND_CONFIG.key: (unknown,)},
        )

    qualities = set()
    for kind in EdgeKind:
        known = Edge(
            caller=_MAIN,
            callee=_FIND_CONFIG,
            kind=kind,
            site="cmd/classify/main.go:180",
        )
        reach = reachable_from(_graph(edges=(known,)), (_GO_MAIN_ROOT,))
        assert reach.get(_FIND_CONFIG.key) == (known,), (
            f"the control failed: a {kind.value} edge was not traversed at all"
        )
        found = _judge(
            _FIND_CONFIG,
            graph=_graph(edges=(known,) + _SEAL_EDGES),
            production_reach={_MAIN.key: (), _FIND_CONFIG.key: (known,)},
        )
        qualities.add(found.quality)
    assert qualities == {PathQuality.RESOLVED, PathQuality.OVER_APPROXIMATED}, (
        "the control failed: the four real members no longer produce two "
        f"different qualities, they produce {sorted(q.value for q in qualities)}"
    )


def test_discover_seals_reports_in_root_order_and_never_sorts():
    """Discovery order, so a body that only ever emits in it cannot hide.

    **Gap 8 of the eight, NOT predicted.** Sorting inside :func:`discover_seals`
    reddened nothing, and the body's reading of why — "``check_tree`` sorts
    findings anyway" — is **correct about the report and beside the point about
    the contract**, which this row measures rather than accepts. The contract is
    explicit and gives its own reason: "Root order, not sorted order. The report
    sorts its FINDINGS; sorting here as well would hide a body that only ever
    emits in discovery order behind a fixture whose two orders agree."

    So the row is written where the property is observable, which is the public
    function, and the fixture is the one the old fixtures could not be: two test
    roots whose DISCOVERY order and SORTED order disagree. A body that sorts
    returns them the other way round.

    Measured, and reported as a limit rather than hidden: this property is NOT
    observable through :func:`check_tree` on any fixture, because
    :func:`check_tree` re-sorts its findings by ``(test_id, subject key)`` and
    the gap counts are order-free. The mutation is caught here and nowhere else,
    which is why the row is at this boundary.

    Two controls are judged in the same call: the production root is not a seal
    (so a body that returns every root passes nothing), and a test root the
    graph does not declare is a refusal rather than a silent omission — a seal
    the graph never read would contribute no subject, which is the defect this
    module exists to refuse.

    GREEN at HEAD, mutation-verified. Reddens under a body on: ``return
    tuple(sorted(seals, key=...))`` in :func:`discover_seals`. Measured: that
    mutation reddens this row and no other in the file.
    """
    first_found = _sym("TestSeal_Zulu", "contract_seal_test.go", 700)
    second_found = _sym("TestSeal_Alpha", "contract_seal_test.go", 900)
    assert second_found.key < first_found.key, (
        "the fixture no longer distinguishes discovery order from sorted order"
    )

    roots = (
        Root(
            symbol=first_found,
            kind=EntrypointKind.TEST_FUNCTION,
            root_kind=RootKind.TEST,
            evidence="cmd/classify/contract_seal_test.go:700 func TestSeal_Zulu",
        ),
        _GO_MAIN_ROOT,
        Root(
            symbol=second_found,
            kind=EntrypointKind.TEST_FUNCTION,
            root_kind=RootKind.TEST,
            evidence="cmd/classify/contract_seal_test.go:900 func TestSeal_Alpha",
        ),
    )
    graph = _graph(symbols=_ALL_SYMBOLS + (first_found, second_found))

    seals = discover_seals(graph, roots)
    assert [s.symbol.key for s in seals] == [first_found.key, second_found.key], (
        "discover_seals re-ordered its roots; the report sorts its findings, and "
        "sorting here as well hides a body that only ever emits in discovery "
        "order behind a fixture whose two orders agree"
    )
    assert _MAIN.key not in {s.symbol.key for s in seals}, (
        "the control failed: a production root became a seal"
    )

    with pytest.raises(CallSiteReachabilityError):
        discover_seals(_graph(symbols=_ALL_SYMBOLS), roots)


# --------------------------------------------------------------------------- #
# Part 12 — the import relation, and the second defect at the root seam.
#
# D5 P2 seals, written on ``feat/D5-relation-seals`` @ ``b2e6fa6`` — the merge
# of the P1 scaffold ``feat/D5-import-relation`` @ ``76c1918`` into
# ``feat/D6-adj4`` @ ``c889ac6``. **The merge is CLEAN — the scaffold touched
# only ``call_site_reachability.py`` and D6's last three rounds touched only
# ``go_reachability.py``, ``go_call_reachability/main.go``,
# ``tests/test_go_reachability.py`` and a PROVENANCE file, so the two histories
# do not overlap in a single file.** Measured with
# ``PYTHONPATH=src python3 -m pytest -q -o addopts=""``: 2417 passed / 0 failed
# / 13 skipped at ``c889ac6``, and the same 2417 / 0 / 13 at the merge commit
# ``b2e6fa6``. ``ANALYZERS`` is ``()`` at both.
#
# THE MEASUREMENT THAT DECIDES WHERE THESE ROWS GET THEIR EVIDENCE, and it is
# the reason not one mechanism row below uses the acceptance tree's shape as
# its only witness:
#
#   The acceptance tree has **0 in-tree import edges** — measured below by
#   :func:`test_the_acceptance_trees_import_counts_are_the_measured_ones`, which
#   reads the vendored fixture. On a tree with no edges the FAIL-OPEN and the
#   TRUTH are the same partition: an empty relation says every package is its
#   own component, and so does the truth, and both answer 4 of 7. A row proved
#   only there cannot tell an analyzer that computed the relation from one that
#   returned nothing, which is vacuity shape "green because the two candidate
#   answers coincide on this input".
#
#   So the mechanism rows are proved on a tree where the two DIFFER, and the
#   tree is real and is named: ``evenplay-mono/apps/website-public-api`` at
#   ``51a71736c``, transcribed into :data:`_REACH_EDGES` /
#   :data:`_REACH_EXTERNAL` below. **Measured by this author 2026-08-11** with
#   ``go list -e -json ./...`` in that module, unioning ``Imports``,
#   ``TestImports`` and ``XTestImports`` and keeping the pairs whose target is
#   in the module:
#
#       packages                     12
#       in-tree undirected edges     24
#       external (out-of-module)    156
#       TRUE components               1   (all 12)
#       EMPTY-relation components    12
#
#   **DISPUTE R1 (figures).** :class:`ImportsUnavailable`'s docstring records
#   this tree as "12 packages, 25 undirected in-tree import edges". Re-measured
#   here it is **24**, by every counting this author could construct — 24
#   production-only (``Imports``), 24 including test imports, 24 distinct
#   undirected pairs. The load-bearing figures, 1 true component against 12
#   under an empty relation, reproduce EXACTLY. The same docstring's second
#   tree, ``apps/platform-domain/core``, is recorded as "33 packages, 93 edges,
#   6 components — one of 28 and five singletons"; re-measured at ``51a71736c``
#   it is **31 packages, 88 edges, 5 components — one of 27 and four
#   singletons** (86 edges production-only, same partition). The shape of the
#   claim survives and the counts do not. No row below rests on either
#   contested number; the reach fixture is transcribed rather than cited, so a
#   reader can re-derive every assertion from the data in this file.
# --------------------------------------------------------------------------- #


def _pkg(
    identity: str,
    *,
    symbols: tuple[str, ...] = (),
    imports: tuple[str, ...] = (),
    unplaced: tuple[str, ...] = (),
    external: int = 0,
) -> PackageImports:
    """One :class:`PackageImports`, spelled positionally-free.

    Not an implementation of anything under seal: it fills a frozen record.
    """
    return PackageImports(
        package=identity,
        symbols=frozenset(symbols),
        imports=frozenset(imports),
        unplaced_imports=tuple(unplaced),
        external_import_count=external,
    )


def _relation(*packages: PackageImports) -> ImportRelation:
    return ImportRelation(packages={p.package: p for p in packages})


#: The acceptance tree's two package IDENTITIES — the qualifier half of the
#: ``Symbol.key`` its declarations carry, which is what the relation is keyed
#: on. NOT the import paths; see :data:`_ACCEPTANCE_IMPORT_PATHS`.
_GATES_PKG = "github.com/yourorg/claude-workflow/gates/cmd/gates"
_ITERATE_PKG = "github.com/yourorg/claude-workflow/iterate/cmd/iterate"

#: The same two packages as an IMPORT STATEMENT spells them. **Disjoint from
#: the identities above**, which is the whole reason a second derivation of
#: import paths cancels invisibly rather than colliding loudly.
_ACCEPTANCE_IMPORT_PATHS = (
    "github.com/yourorg/claude-workflow/gates",
    "github.com/yourorg/claude-workflow/iterate",
)

#: The acceptance tree's measured external import counts, per package. Pinned
#: against the vendored fixture by
#: :func:`test_the_acceptance_trees_import_counts_are_the_measured_ones`.
_ACCEPTANCE_EXTERNAL = {_GATES_PKG: 41, _ITERATE_PKG: 39}


def _g(name: str, path: str = "cmd/gates/main.go", line: int = 1) -> Symbol:
    return Symbol(key=f"{_GATES_PKG}.{name}", path=path, line=line)


def _i(name: str, path: str = "cmd/iterate/preserve.go", line: int = 1) -> Symbol:
    return Symbol(key=f"{_ITERATE_PKG}.{name}", path=path, line=line)


#: The acceptance case's two real holes, both ``cancel`` in ``cmd/gates/main.go``
#: — D6's body resolved the other five. Their CALLER is what scoping reads.
_GATES_RUN = _g("run", line=90)
_GATES_SERVE = _g("serve", line=140)
_HOLE_A = (_GATES_RUN, "cmd/gates/main.go:97", "call through the value `cancel`")
_HOLE_B = (_GATES_SERVE, "cmd/gates/main.go:151", "call through the value `cancel`")

#: The subject the four answerable findings are about, in the OTHER package.
_ITERATE_SUBJECT = _i("VerifyPreservation", line=61)
_ITERATE_HELPER = _i("licenceOf", line=120)


def _acceptance_relation(**overrides) -> ImportRelation:
    """The acceptance tree as the relation records it: two packages, no in-tree
    import, 41 and 39 placed OUT of the tree, nothing unplaced.
    """
    gates = dict(
        symbols=(_GATES_RUN.key, _GATES_SERVE.key),
        external=_ACCEPTANCE_EXTERNAL[_GATES_PKG],
    )
    iterate = dict(
        symbols=(_ITERATE_SUBJECT.key, _ITERATE_HELPER.key),
        external=_ACCEPTANCE_EXTERNAL[_ITERATE_PKG],
    )
    gates.update(overrides.pop("gates", {}))
    iterate.update(overrides.pop("iterate", {}))
    assert not overrides, overrides
    return _relation(_pkg(_GATES_PKG, **gates), _pkg(_ITERATE_PKG, **iterate))


# --------------------------------------------------------------------------- #
# The reach fixture. ``evenplay-mono/apps/website-public-api`` @ ``51a71736c``,
# transcribed from ``go list -e -json ./...`` on 2026-08-11. The module prefix
# is dropped so the data is readable; nothing below depends on the spelling.
#
# It is here because the acceptance tree cannot separate a computed relation
# from an absent one, and because this tree separates FOUR bodies rather than
# two — see :func:`test_the_import_graph_is_read_undirected_and_transitively`.
# --------------------------------------------------------------------------- #

_REACH_MOD = "github.com/EvenPlay/evenplay-mono/apps/website-public-api"

_REACH_EXTERNAL = {
    "cmd/public-api": 46,
    "cmd/snapshot-builder": 19,
    "internal/builder": 10,
    "internal/domain": 15,
    "internal/inquiry": 32,
    "internal/metrics": 15,
    "internal/seams": 3,
    "internal/snapshot": 6,
    "internal/source/postgres": 13,
    "internal/source/redshift": 20,
    "internal/store/cache": 12,
    "internal/store/s3": 21,
}

#: Directed, as the import statements are written. 24 of them.
_REACH_EDGES = (
    ("cmd/public-api", "internal/domain"),
    ("cmd/public-api", "internal/inquiry"),
    ("cmd/public-api", "internal/metrics"),
    ("cmd/public-api", "internal/seams"),
    ("cmd/public-api", "internal/snapshot"),
    ("cmd/public-api", "internal/store/cache"),
    ("cmd/public-api", "internal/store/s3"),
    ("cmd/snapshot-builder", "internal/builder"),
    ("cmd/snapshot-builder", "internal/metrics"),
    ("cmd/snapshot-builder", "internal/source/postgres"),
    ("cmd/snapshot-builder", "internal/source/redshift"),
    ("cmd/snapshot-builder", "internal/store/s3"),
    ("internal/builder", "internal/domain"),
    ("internal/builder", "internal/seams"),
    ("internal/builder", "internal/snapshot"),
    ("internal/inquiry", "internal/seams"),
    ("internal/metrics", "internal/builder"),
    ("internal/seams", "internal/snapshot"),
    ("internal/source/postgres", "internal/builder"),
    ("internal/source/redshift", "internal/builder"),
    ("internal/store/cache", "internal/seams"),
    ("internal/store/cache", "internal/snapshot"),
    ("internal/store/s3", "internal/seams"),
    ("internal/store/s3", "internal/snapshot"),
)


def _reach_id(short: str) -> str:
    return f"{_REACH_MOD}/{short}"


def _reach_relation(**overrides) -> ImportRelation:
    """The 12-package reach tree, keyed on identities, imports as measured."""
    by_source: dict[str, list[str]] = {short: [] for short in _REACH_EXTERNAL}
    for source, target in _REACH_EDGES:
        by_source[source].append(_reach_id(target))
    return _relation(
        *(
            _pkg(
                _reach_id(short),
                # One symbol per package, so every node is witnessed and
                # ``package_of`` can place a hole in any of them.
                symbols=(f"{_reach_id(short)}.Run",),
                imports=tuple(by_source[short]),
                external=_REACH_EXTERNAL[short],
                **overrides.get(short, {}),
            )
            for short in sorted(_REACH_EXTERNAL)
        )
    )


# --------------------------------------------------------------------------- #
# Requirement 1 — absence is not narrowing.
# --------------------------------------------------------------------------- #


def test_an_absent_relation_leaves_the_hole_set_exactly_as_it_found_it():
    """No relation, no narrowing — the CURRENT sealed behaviour, not the
    maximally-narrowed one.

    Requirement 2 of the scaffold's brief and the one direction this mechanism
    refuses. The fail-open is not a hypothetical shape: an empty
    :class:`ImportRelation` reads as "no package imports anything", every
    package becomes its own component, and every hole is scoped away from every
    subject outside it. :class:`ImportsUnavailable` exists so that an analyzer
    with nothing to say lands on TODAY's answer instead.

    Three absences are judged in one call because a body may only handle one of
    them: the module-level :data:`IMPORTS_NOT_SUPPLIED`, a freshly constructed
    :class:`ImportsUnavailable` with a different reason, and the one
    :func:`build_call_graph` mints on a :class:`SourceUnreadable`. Identity is
    asserted as well as equality — the contract says "return ``holes``
    UNCHANGED" and a body that rebuilt an equal tuple has still not been caught
    doing anything wrong, but a body that rebuilt a REORDERED one has, and
    order is load-bearing (``check_subject``'s abstention detail names
    ``holes[0]``).

    The control is judged in the same call and it is the whole point: with a
    real relation in hand and the two packages genuinely disconnected, the same
    subject and the same holes come back EMPTY. Without it this row is green
    against a body that returns its input for every evidence value whatsoever —
    which is a mechanism that never narrows and is never worth landing.

    Production reaches these inputs today and on every tree: :data:`ANALYZERS`
    is ``()`` so :func:`_union_import_evidence` returns
    :data:`IMPORTS_NOT_SUPPLIED` for every graph the module can build, and the
    Go row's :meth:`graph` carries the field's default, so ``ImportsUnavailable``
    is the ONLY value ``CallGraph.package_imports`` takes at this revision.

    RED at HEAD: :func:`holes_in_scope` raises ``NotImplementedError``.

    **Measured under**, each applied to a throwaway reference implementation in
    a clone and each run over the whole suite:

      * returning ``()`` on the absence — the fail-open spelled directly.
        Reddens this row and
        ``test_narrowing_only_ever_removes_holes_and_can_never_un_find_a_path``,
        and nothing else;
      * returning ``holes`` for EVERY evidence value — the control half reddens,
        together with ``…_in_both_directions`` and ``…_never_by_string_surgery``;
      * returning ``tuple(sorted(holes, key=lambda h: h[0].key, reverse=True))``
        on the absence — the order half reddens, same two rows as the first.
    """
    holes = (_HOLE_A, _HOLE_B)
    absences = (
        IMPORTS_NOT_SUPPLIED,
        ImportsUnavailable(reason="the Go row does not compute imports yet"),
        ImportsUnavailable(
            reason="the 'go' analyzer could not read cmd/gates/main.go, so the "
            "imports declared there were never seen"
        ),
    )
    for absent in absences:
        kept = holes_in_scope(_ITERATE_SUBJECT, holes, absent)
        assert kept == holes, (
            f"{absent!r} narrowed the hole set. An analyzer that could not "
            "answer must degrade to today's whole-tree behaviour, never to the "
            "maximally-narrowed one"
        )
        assert [h[0].key for h in kept] == [h[0].key for h in holes], (
            "the absence branch reordered the holes; check_subject's abstention "
            "detail names holes[0], so a reorder moves which site a human is "
            "sent to with no verdict moving and nothing red"
        )

    assert holes_in_scope(_ITERATE_SUBJECT, holes, _acceptance_relation()) == (), (
        "the control failed: with a real relation and the two packages in "
        "different components, both cmd/gates holes are still in scope for a "
        "cmd/iterate subject — so the rows above are green against a body that "
        "never narrows at all"
    )


def test_an_empty_relation_over_a_non_empty_graph_is_refused():
    """The fail-open spelled as data, refused at the type.

    An :class:`ImportRelation` with no packages over a graph that declares
    symbols is the maximal narrowing wearing the costume of a computed answer.
    It is refused, and the refusal is what makes :class:`ImportsUnavailable`
    the only way to say "I could not compute this" — an absence that costs a
    class name and a required reason cannot be arrived at by omission.

    Three controls, all judged in the same call, because the refusal must be
    about the EMPTINESS and not about the shape:

      * the same emptiness over an EMPTY symbol map is accepted — an empty tree
        genuinely has no packages, and a rule that refused it would refuse a
        legal input;
      * :data:`IMPORTS_NOT_SUPPLIED` over the same non-empty symbols is
        accepted — the named absence is always well formed, which is the point
        of it;
      * a well-formed two-package relation over the same symbols is accepted.

    GREEN at HEAD, mutation-verified: :func:`validate_import_relation` is one of
    the three things the scaffold implemented on purpose, on the stated ground
    that "a seal cannot express 'an empty relation is refused' without calling
    the function that refuses it".

    Production reaches this input at :func:`_union_import_evidence`, which hands
    every merged relation to this validator before returning it — so an analyzer
    that answered with an empty relation is refused at the construction site
    rather than at the first narrowing.

    **Measured under: deleting BOTH refusals** — the ``if symbols and not
    evidence.packages`` clause AND the trailing unplaced-symbol clause. Reddens
    this row and no other in the suite. Relaxing the first to ``if not
    evidence.packages`` reddens the empty-tree control, and this row alone.

    **DISPUTE R3, and it is why the mutation above names two clauses rather than
    one. The requirement-2 refusal is OVER-DETERMINED, and its dedicated clause
    is not individually load-bearing.** Measured on ``feat/D5-relation-seals`` @
    ``b2e6fa6``: with ``if symbols and not evidence.packages`` replaced by ``if
    False``, an empty relation over a one-symbol graph is STILL refused — by
    ``unplaced = sorted(key for key in symbols if key not in owner)``, which
    fires on exactly the same inputs, because an empty ``packages`` places no
    symbol. That mutation reddens NO row in the suite. Deleting the
    unplaced-symbol clause alone reddens no row either. Neither clause is
    redundant in general — the second catches partial relations the first cannot
    see — but for THIS requirement they are co-extensive, and the whole value of
    the dedicated clause is its MESSAGE: a body debugging "1 symbol(s) belong to
    no package" is being told about a symbol when the fact is that an analyzer
    returned nothing. Recorded rather than repaired; collapsing them is a
    scaffold decision, not a seal author's.
    """
    symbols = {
        s.key: s
        for s in (_GATES_RUN, _GATES_SERVE, _ITERATE_SUBJECT, _ITERATE_HELPER)
    }
    empty = ImportRelation(packages={})

    with pytest.raises(CallSiteReachabilityError):
        validate_import_relation(empty, symbols)

    assert validate_import_relation(empty, {}) is None, (
        "the control failed: an empty relation over an empty tree was refused, "
        "so the refusal above is about the shape and not about the fail-open"
    )
    assert validate_import_relation(IMPORTS_NOT_SUPPLIED, symbols) is None, (
        "the control failed: the NAMED absence was refused, which would leave "
        "an analyzer with nothing to say no legal way to say it"
    )
    assert validate_import_relation(_acceptance_relation(), symbols) is None, (
        "the control failed: a well-formed two-package relation was refused"
    )


def test_import_components_raises_on_the_absence_rather_than_answering_anyway():
    """A caller that has not handled the refusal may not slide past it.

    The scaffold contracts this raise and gives the reason: the branch order in
    :func:`holes_in_scope` — absence FIRST, components second — is only
    enforceable if the component computation refuses to answer for a state that
    carries no components. The two plausible wrong answers are both silent: an
    empty mapping makes every lookup a ``KeyError`` three frames down, and a
    single all-packages component makes the absence read as "everything is
    connected", which is the RIGHT verdict reached by the WRONG route and would
    make a body that dropped the ``holes_in_scope`` absence branch entirely
    still pass every verdict row in this file.

    The control is judged in the same call: a real relation returns a mapping
    rather than raising, so the raise above is about the state and not about the
    function being unimplemented.

    Production reaches this input the moment a body writes the ``holes_in_scope``
    branch in the wrong order, which is the only thing this row is for.

    RED at HEAD: the stub raises ``NotImplementedError``, which is not
    :class:`CallSiteReachabilityError`, so ``pytest.raises`` does not catch it.
    **Measured under**: returning ``{}`` for :class:`ImportsUnavailable`;
    returning ``{"<all>": frozenset()}``. Each reddens this row and no other in
    the suite.
    """
    with pytest.raises(CallSiteReachabilityError):
        import_components(IMPORTS_NOT_SUPPLIED)
    with pytest.raises(CallSiteReachabilityError):
        import_components(ImportsUnavailable(reason="no analyzer ran"))

    components = import_components(_acceptance_relation())
    assert isinstance(components, Mapping), (
        "the control failed: a real relation did not yield a mapping, so the "
        "raises above are about the function and not about the state"
    )


# --------------------------------------------------------------------------- #
# Requirement 2 — an unplaced import is an edge to every package.
# --------------------------------------------------------------------------- #


def test_an_unplaced_import_is_an_edge_to_every_package():
    """One import nobody could place collapses the tree to one component.

    The ruled rule, in the half that is easiest to soften into a heuristic: *an
    unresolved import counts as an EDGE, never as an ABSENCE*. A package whose
    reach cannot be bounded could import anything, including the subject's
    package, so the positive claim — "no code in the hole's package can name
    ``S``" — cannot be discharged against ANY ``S``. Because components are an
    equivalence, one such package anywhere collapses the whole tree and step 3
    reverts to today's behaviour.

    Proved on the reach tree and not on the acceptance tree, and the choice is
    load-bearing: the acceptance tree has 0 in-tree import edges, so its true
    partition and its empty-relation partition are the SAME 12-of-12 shape —
    there, "unplaced collapses the tree" and "unplaced is dropped" differ by the
    whole answer, but so does every other pair of bodies, and the row would not
    say which rule produced it. Here the surgery is a single package: the tree
    is one component either way, so the row is made to speak by DISCONNECTING
    one package first (``internal/audit``, imported by nobody and importing
    nothing) and then giving it — and only it — an unplaced import.

    Three bodies separated, in one call:

      * **DROP the unplaced import** (the absence reading, and the fail-open):
        ``internal/audit`` stays a singleton;
      * **RAISE on it**: the row errors out;
      * **GUESS a target**: any single guessed edge leaves at least one of the
        twelve outside ``internal/audit``'s component, since a guess names one
        package and the rule names all of them.

    The control is judged in the same call: the identical relation with
    ``unplaced_imports=()`` keeps ``internal/audit`` alone, so the collapse is
    attributable to the unplaced import and to nothing else about the fixture.

    Production reaches this input on the first Go tree with a ``replace``
    directive: ``_import_path_qualifiers``' own docstring records a renaming
    ``replace`` as OPEN and unclosable by any per-unit import-path field, and an
    import the analyzer can neither place in the tree nor establish as
    out-of-tree is exactly this state.

    RED at HEAD: :func:`import_components` raises ``NotImplementedError``.
    **Measured under**: dropping ``unplaced_imports`` from the traversal —
    reddens this row and ``…_a_placed_out_of_tree_import_contributes_no_edge``,
    and nothing else; returning direct neighbours only — reddens this row and
    ``…_undirected_and_transitively``; reading ``external_import_count`` as
    unplaceable — reddens this row and five others, because that body collapses
    every fixture in this part.
    """
    audit = _reach_id("internal/audit")
    detached = _relation(
        *_reach_relation().packages.values(),
        _pkg(audit, symbols=(f"{audit}.Run",), external=4),
    )
    nodes = frozenset(detached.packages)
    assert len(nodes) == 13

    clean = import_components(detached)
    assert clean[audit] == frozenset({audit}), (
        "the control failed: a package importing nothing and imported by "
        "nobody is not a singleton component, so the collapse below is not "
        "attributable to the unplaced import"
    )
    assert clean[_reach_id("cmd/public-api")] == nodes - {audit}, (
        "the control failed: the other twelve are not one component, so this "
        "fixture cannot show a collapse"
    )

    with_unplaced = _relation(
        *_reach_relation().packages.values(),
        _pkg(
            audit,
            symbols=(f"{audit}.Run",),
            external=4,
            unplaced=("replace example.com/upstream => ./local: no unit claims it",),
        ),
    )
    collapsed = import_components(with_unplaced)
    for identity in sorted(nodes):
        assert collapsed[identity] == nodes, (
            f"{identity!r} is not in the whole-tree component. One unplaced "
            "import anywhere makes every package's component the whole tree — "
            "an import whose target could be anything can be an import of the "
            f"subject's package. Got {sorted(collapsed[identity])}"
        )


# --------------------------------------------------------------------------- #
# Requirement 3 — a placed out-of-tree import contributes no edge, and the
# count is the non-vacuity field.
# --------------------------------------------------------------------------- #


def test_a_placed_out_of_tree_import_contributes_no_edge():
    """80 stdlib imports do not make two packages one component.

    The scaffold's CHOICE, and the rejected alternative is the one a cautious
    body writes: treating every import the analyzer did not place IN the tree as
    unplaceable. On the acceptance tree that is all 80 imports, the relation
    collapses to one component on every tree ever analysed, and the mechanism is
    never consulted. A dependency outside the tree declares no :class:`Symbol`
    here and therefore cannot be the subject's package.

    The row is the pair, judged in one call, and the pair is what makes it say
    something: the acceptance relation carries 41 and 39 PLACED-EXTERNAL imports
    and 0 unplaced, and must yield TWO components; the same two packages with a
    single unplaced import — one import, against eighty placed ones — must yield
    ONE. A body that conflated "outside the tree" with "could not be placed"
    passes neither half.

    The counts are not decoration and they are not a literal this file invented:
    :func:`test_the_acceptance_trees_import_counts_are_the_measured_ones` reads
    them off the vendored fixture. They are the non-vacuity field — a relation
    reporting zero imports, zero unplaced and zero external for every package is
    either a tree of genuinely isolated packages or an analyzer that stopped
    reading import blocks, and the third assertion here is what stops those two
    reading the same: the all-zero relation gives the SAME partition as the
    41/39 one, so the partition alone can never distinguish them and the COUNT
    is the only thing that can.

    Production reaches this input on the acceptance tree itself, which is the
    tree D6's analyzer runs over.

    RED at HEAD: :func:`import_components` raises ``NotImplementedError``.
    **Measured under**: treating ``external_import_count > 0`` as unplaceable —
    the two-component half reddens; ignoring ``unplaced_imports`` — the
    one-component half reddens, together with
    ``…_an_unplaced_import_is_an_edge_to_every_package`` and nothing else.
    """
    two = import_components(_acceptance_relation())
    assert two[_GATES_PKG] == frozenset({_GATES_PKG}), (
        f"{_GATES_PKG}'s component is {sorted(two[_GATES_PKG])}; 41 imports "
        "placed OUTSIDE the tree are not edges inside it"
    )
    assert two[_ITERATE_PKG] == frozenset({_ITERATE_PKG})

    one = import_components(
        _acceptance_relation(gates={"unplaced": ("a vendored path no unit claims",)})
    )
    assert one[_GATES_PKG] == frozenset({_GATES_PKG, _ITERATE_PKG}), (
        "one UNPLACED import did not collapse the tree while eighty PLACED "
        "external ones left it split — the two must not be the same value"
    )

    zeros = import_components(
        _acceptance_relation(gates={"external": 0}, iterate={"external": 0})
    )
    assert zeros == two, (
        "the partition moved when the external counts went to zero, which "
        "means the count is being read as structure. It is not structure: it "
        "is the field that tells a reader whether the analyzer read the import "
        "blocks at all, and a relation of all zeros must be distinguishable "
        "from one that counted BY THE COUNT and never by the partition"
    )


def test_the_acceptance_trees_import_counts_are_the_measured_ones():
    """41, 39, 80, and zero in-tree — read off the vendored fixture.

    This row pins the INPUT, not the mechanism, exactly as
    :func:`test_the_canonical_fixture_is_the_measured_artifact` does for
    ``cmd/classify``. It exists for two reasons and both are about the rows
    above rather than about this one:

      1. :data:`_ACCEPTANCE_EXTERNAL` is the number a body must hit, and a
         hand-written number nobody checks is fiction. The scaffold cites 41 and
         39 in three docstrings; if the fixture ever changes, this row is what
         goes red instead of those three going quietly wrong;
      2. **it is the measurement that disqualifies the acceptance tree as
         non-vacuity evidence for every other row in this part.** ZERO in-tree
         imports is what makes the fail-open and the truth agree there, so the
         reach fixture had to be brought in. That claim is asserted here rather
         than asserted in prose.

    The sweep is deliberately crude and is not a parser of anything the module
    under seal parses: it counts the lines of a Go ``import ( … )`` block and
    the single-line ``import "x"`` form, over every ``.go`` file of each
    package, test files included — which is the set an analyzer reading import
    blocks would read.

    GREEN at HEAD, mutation-verified: it reads vendored text.

    **Measured under**: deleting one import line from the first ``import (…)``
    block of ``tests/fixtures/d6_g2_preserve/cmd/gates/main.go``. Reddens this
    row and no other row in THIS file; it also reddens three rows in
    ``tests/test_go_reachability.py`` that read the same fixture
    (``…_seven_seal_subject_pairs_over_two_keys``,
    ``…_step_three_abstention_is_measured…``,
    ``…_subject_reader_cannot_be_import_based_over_this_fixture``), which is the
    correct blast radius for a fixture edit and is recorded so a body does not
    mistake it for collateral from a code change.
    """
    fixture = _TESTS_DIR / "fixtures" / "d6_g2_preserve"
    block = re.compile(r"^import\s*\(([^)]*)\)", re.M | re.S)
    single = re.compile(r'^import\s+(?:\w+\s+)?"[^"]+"\s*$', re.M)

    counted = {}
    for short, identity in (("cmd/gates", _GATES_PKG), ("cmd/iterate", _ITERATE_PKG)):
        total = 0
        in_tree = 0
        for go_file in sorted((fixture / short).glob("*.go")):
            text = go_file.read_text(encoding="utf-8")
            lines = []
            for match in block.finditer(text):
                lines += [
                    line.strip()
                    for line in match.group(1).splitlines()
                    if line.strip() and not line.strip().startswith("//")
                ]
            lines += [m.group(0).partition("import")[2].strip() for m in single.finditer(text)]
            total += len(lines)
            in_tree += sum(1 for line in lines if "yourorg/claude-workflow" in line)
        counted[identity] = total
        assert in_tree == 0, (
            f"{short} now has {in_tree} in-tree import(s). The rows in this "
            "part rest on the acceptance tree having NONE — that is what makes "
            "its true partition and its empty-relation partition the same "
            "answer, and therefore what makes it unusable as non-vacuity "
            "evidence. If this changed, the reach fixture's justification "
            "changed with it"
        )

    assert counted == _ACCEPTANCE_EXTERNAL, (
        f"the fixture's import blocks now count {counted}, not "
        f"{_ACCEPTANCE_EXTERNAL}; the numbers three scaffold docstrings cite "
        "and the numbers the tree carries have drifted apart"
    )
    assert sum(counted.values()) == 80


# --------------------------------------------------------------------------- #
# Requirement 4 — the graph is undirected, and it is transitive.
# --------------------------------------------------------------------------- #


def test_the_import_graph_is_read_undirected_and_transitively():
    """``A imports B`` joins them BOTH ways, and joins reach through a third.

    A function value crosses one import in both directions — ``A`` passes
    ``B``'s function into ``B``'s call, and ``B``'s call returns one to ``A`` —
    so reading :attr:`PackageImports.imports` directionally would discharge the
    positive claim in half the cases where it is false, which is the fail-open
    direction. Transitivity has the same standing: ``P`` imports ``R``, ``Q``
    imports ``R``, and ``R`` can evaluate ``p.Register(q.S)``.

    **This is the row the acceptance tree cannot carry**, and the reach fixture
    is here for it. On a tree with zero in-tree edges every reading — undirected,
    directed, transitive, direct-only, and the empty relation — gives the same
    12-singleton partition. On this tree, measured at ``51a71736c``, the four
    separate cleanly, and the row asserts each separation rather than asserting
    the answer once:

      * **the truth** — one component of 12;
      * **an EMPTY relation** — 12 components. Asserted here as the FAIL-OPEN
        CONTROL, in this same call, because it is the body this whole class
        exists to refuse and on the acceptance tree it is invisible;
      * **DIRECTED** — ``internal/snapshot`` imports nothing, so a directed
        reading gives it a component of ONE while five packages import it;
      * **DIRECT-ONLY (no transitivity)** — ``cmd/public-api`` imports seven of
        the eleven others and imports ``internal/builder`` through none of them,
        so a direct-only reading gives it a component of 8, not 12.

    Production reaches this input on any repository with an ``internal/``
    tree, which is every module in ``evenplay-mono`` and is the shape
    ``_import_path_qualifiers``' docstring says "binds every repository with an
    ``internal/``".

    RED at HEAD: :func:`import_components` raises ``NotImplementedError``.
    **Measured under**: following ``imports`` in the declared direction only —
    reddens this row, ``…_an_unplaced_import_is_an_edge_to_every_package`` and
    ``…_in_both_directions``; returning each package's direct neighbours plus
    itself — reddens this row and the unplaced row; ignoring ``imports``
    altogether — the fail-open control reddens, same three rows as the first.
    """
    relation = _reach_relation()
    nodes = frozenset(relation.packages)
    assert len(nodes) == 12
    assert sum(len(p.imports) for p in relation.packages.values()) == 24

    components = import_components(relation)
    assert set(components) == nodes
    for identity in sorted(nodes):
        assert components[identity] == nodes, (
            f"{identity!r} is not in the one component this tree has. Measured "
            "at evenplay-mono 51a71736c: 12 packages, 24 undirected in-tree "
            f"import edges, ONE component. Got {len(components[identity])} "
            "member(s)"
        )

    # The three wrong readings, each named by the member that exposes it.
    snapshot = _reach_id("internal/snapshot")
    assert relation.packages[snapshot].imports == frozenset(), (
        "the fixture changed: internal/snapshot importing something makes the "
        "directed reading indistinguishable from the undirected one here"
    )
    assert len(relation.packages[_reach_id("cmd/public-api")].imports) == 7, (
        "the fixture changed: cmd/public-api's direct neighbourhood is no "
        "longer a proper subset of the tree, so the direct-only reading is no "
        "longer separated"
    )

    # The fail-open control, judged here: the SAME node set with every import
    # removed is twelve components, and on this tree that is a different answer.
    hollow = _relation(
        *(
            _pkg(p.package, symbols=tuple(p.symbols), external=p.external_import_count)
            for p in relation.packages.values()
        )
    )
    hollow_components = import_components(hollow)
    assert {frozenset(v) for v in hollow_components.values()} == {
        frozenset({n}) for n in nodes
    }, (
        "the control failed: a relation with no imports at all did NOT give "
        "twelve singleton components, so the twelve-into-one result above is "
        "not attributable to the imports being read"
    )


def test_an_import_puts_a_hole_in_scope_in_both_directions():
    """The undirected rule, at the seam that spends it.

    :func:`import_components` is where the rule is computed and
    :func:`holes_in_scope` is where it is spent, and the two are separately
    wrongable: a body can compute an undirected partition and then look the
    subject up in the HOLE's component rather than asking whether the two agree.
    The row is the mirror pair — hole in the importer with the subject in the
    imported, and hole in the imported with the subject in the importer — and a
    body that got the direction wrong passes exactly one half.

    The third package is the control, judged in the same call: ``cmd/iterate``
    imports nothing and nothing imports it, so its hole is scoped AWAY for a
    ``cmd/gates`` subject. Without that assertion the row is green against
    ``return holes``.

    Production reaches this input on the acceptance case as soon as one of the
    two modules imports the other, and on any ``internal/`` tree today.

    RED at HEAD: :func:`holes_in_scope` raises ``NotImplementedError``.
    **Measured under**: keeping a hole only when the HOLE's package imports the
    subject's — reddens this row and no other in the suite; reading the graph in
    the declared direction only — reddens this row and two others; returning
    ``holes`` unchanged — the control reddens.
    """
    third = "github.com/yourorg/claude-workflow/repro/cmd/repro"
    third_caller = Symbol(key=f"{third}.run", path="cmd/repro/main.go", line=12)
    third_hole = (third_caller, "cmd/repro/main.go:20", "call through a value")

    # gates imports iterate. Nothing imports repro and repro imports nothing.
    relation = _relation(
        _pkg(
            _GATES_PKG,
            symbols=(_GATES_RUN.key, _GATES_SERVE.key),
            imports=(_ITERATE_PKG,),
            external=41,
        ),
        _pkg(
            _ITERATE_PKG,
            symbols=(_ITERATE_SUBJECT.key, _ITERATE_HELPER.key),
            external=39,
        ),
        _pkg(third, symbols=(third_caller.key,), external=2),
    )

    holes = (_HOLE_A, third_hole)

    # Direction 1: the hole is in the IMPORTER, the subject in the IMPORTED.
    assert holes_in_scope(_ITERATE_SUBJECT, holes, relation) == (_HOLE_A,), (
        "a hole in cmd/gates was scoped away from a cmd/iterate subject while "
        "cmd/gates imports cmd/iterate. gates can name iterate's function and "
        "pass it to a value it then calls"
    )

    # Direction 2: the hole is in the IMPORTED, the subject in the IMPORTER.
    iterate_caller = _i("licenceOf", line=120)
    iterate_hole = (iterate_caller, "cmd/iterate/preserve.go:133", "call through a value")
    mirrored = (iterate_hole, third_hole)
    assert holes_in_scope(_GATES_RUN, mirrored, relation) == (iterate_hole,), (
        "a hole in cmd/iterate was scoped away from a cmd/gates subject. The "
        "graph is UNDIRECTED for this purpose: gates' call into iterate can "
        "RETURN a gates function, so an iterate frame can hold it"
    )


# --------------------------------------------------------------------------- #
# Requirement 5 — narrowing may only reduce abstention.
# --------------------------------------------------------------------------- #


def test_narrowing_only_ever_removes_holes_and_can_never_un_find_a_path():
    """Anti-requirement 2 in the register this change opens.

    Scoping is allowed to move a subject from :attr:`Reach.UNDECIDED` to
    :attr:`Reach.FROM_TESTS_ONLY` and thence to a BREACH — that is the whole
    point of it. What it may never do is make the mechanism assert MORE than it
    could before, and there are exactly two routes to that and both are sealed
    here:

      * **the output is a SUBSEQUENCE of the input**, over every evidence shape
        this module can produce. Step 3 abstains iff the hole set is non-empty,
        so a subsequence can only make the mechanism abstain LESS often; a body
        that ADDED a hole, or duplicated one, or reordered them, has made the
        abstention set a function of something other than the input;
      * **and the two fail-closed clauses**, which are what stop the narrowing
        being computed around a gap: a subject :meth:`ImportRelation.package_of`
        cannot place keeps ALL holes, and an individual hole it cannot place is
        KEPT. An unplaceable key has an unknown component, and an unknown
        component may be the subject's.

    Five evidence shapes are swept in one call, including the two that a naive
    body handles by accident and the one that a naive body gets exactly
    backwards (the all-singleton relation, where the correct answer is the
    empty tuple and the fail-open answer is also the empty tuple — which is why
    the subsequence property, and not the ANSWER, is what this row asserts).

    The control is judged in the same call and it is the un-find half: a
    subject that is already in ``production_reach`` reads
    :attr:`Reach.FROM_PRODUCTION` while the graph carries a relation that
    scopes every hole away and while the production closure is FULL of holes.
    That is step 1 running before step 3, which the contract says STANDS, and
    it is the row a body must not redden when it lands the one-line wiring.

    Production reaches the unplaceable-key inputs on any tree the analyzer
    partly described: :func:`validate_import_relation` refuses a relation that
    leaves a graph symbol unplaced, but :func:`holes_in_scope` is handed the
    evidence directly and is contracted to fail closed on its own.

    RED at HEAD: :func:`holes_in_scope` raises ``NotImplementedError``.
    **Measured under**, each reddening this row and — for the first three — no
    other row in the suite: reordering the kept holes; dropping a hole whose
    package cannot be placed; scoping to ``()`` when the SUBJECT cannot be
    placed. The fourth is the un-find control: wiring ``holes_in_scope`` into
    ``check_subject`` AHEAD of step 1 reddens this row and two rows in
    ``tests/test_go_reachability.py`` that judge the acceptance tree — which is
    the point, since that wiring moves verdicts on a real tree.
    """
    stranger = Symbol(
        key="example.com/nobody/pkg.helper", path="pkg/helper.go", line=3
    )
    stranger_hole = (stranger, "pkg/helper.go:9", "call through a value")
    holes = (_HOLE_A, stranger_hole, _HOLE_B)

    shapes = (
        IMPORTS_NOT_SUPPLIED,
        ImportsUnavailable(reason="the Go row does not compute imports yet"),
        _acceptance_relation(),
        _acceptance_relation(gates={"imports": (_ITERATE_PKG,)}),
        _acceptance_relation(gates={"unplaced": ("a path no unit claims",)}),
    )
    for evidence in shapes:
        kept = holes_in_scope(_ITERATE_SUBJECT, holes, evidence)
        assert list(kept) == [h for h in holes if h in set(kept)], (
            f"{evidence!r} produced {[h[1] for h in kept]}, which is not a "
            "SUBSEQUENCE of the input. check_subject's abstention detail names "
            "holes[0]; a filter that reorders moves which site a human is sent "
            "to with no verdict moving and nothing red"
        )
        assert len(kept) == len(set(kept)) <= len(holes)
        assert stranger_hole in kept, (
            f"{evidence!r} scoped away a hole whose package the relation "
            "cannot place. An unplaceable key has an unknown component and an "
            "unknown component may be the subject's — this clause is the "
            "difference between narrowing and guessing"
        )

    unplaceable_subject = holes_in_scope(stranger, holes, _acceptance_relation())
    assert unplaceable_subject == holes, (
        "a subject the relation cannot place did not keep the whole hole set. "
        "Unknown component, fail closed — the same rule as the per-hole one, "
        "applied per call"
    )

    # The un-find control. A saturated hole set, a relation that puts the
    # subject alone, and a subject that step 1 already found.
    saturated = _graph(
        unresolved=(
            (_FIND_CONFIG, "cmd/classify/main.go:450", "call through a value"),
        )
    )
    found = _judge(_LOAD_CONFIG, graph=saturated)
    assert found.reach is Reach.FROM_PRODUCTION, (
        "the control failed: a subject already in production_reach did not read "
        "FROM_PRODUCTION with the production closure full of holes. Step 1 runs "
        "before step 3, and the scoping change may not move that — failing to "
        "look may only make an answer LESS conclusive"
    )


# --------------------------------------------------------------------------- #
# Requirement 6 — package identity agrees with the key's qualifier.
# --------------------------------------------------------------------------- #


def test_the_components_are_keyed_on_the_identities_package_of_answers():
    """One node table, or the divergence cancels and nothing is red.

    D6's P4 measured that a Go symbol's KEY QUALIFIER and its IMPORT PATH are
    different strings whenever the module root is not the tree root — the
    acceptance tree's ``cmd/gates`` is keyed ``…/gates/cmd/gates`` and imported
    as ``…/gates`` — and warned that any import relation must be keyed on an
    identity that agrees with the qualifier. :data:`_ACCEPTANCE_IMPORT_PATHS`
    and :data:`_GATES_PKG` are asserted DISJOINT below, which is the fact that
    makes a second derivation cancel invisibly rather than collide loudly.

    What a body can get wrong here is not the arithmetic, it is the KEY SPACE:
    :meth:`ImportRelation.package_of` answers identities, so a component
    mapping keyed on anything else — import paths, a union-find representative,
    a normalised spelling — makes ``components[package_of(k)]`` either a
    ``KeyError`` or a silent miss, and a silent miss on the subject's package is
    the fail-open. So the row pins the two key spaces as ONE, both ways:

      * every key of the mapping is a node of the relation, and every node is a
        key — no phantom nodes, no dropped ones;
      * every MEMBER of every component is a node too;
      * and the round trip closes: for every symbol the relation places,
        ``package_of(key)`` is a key of the mapping.

    The all-unplaced relation is swept in the same call as the ordinary one,
    because the whole-tree collapse is exactly where a body is tempted to
    return a single synthetic component under a made-up name.

    Production reaches this input the moment an analyzer supplies a relation,
    which is what ``ImportRelation``'s docstring means by "**THIS RELATION
    SUBSUMES ``go_reachability._import_path_qualifiers``. DO NOT BUILD A SECOND
    DERIVATION OF IMPORT PATHS.**"

    RED at HEAD: :func:`import_components` raises ``NotImplementedError``.
    **Measured under**: keying the mapping on the union-find representative —
    the spelling the scaffold's own rejected alternative names, and the one a
    body reaches for by accident. It reddens this row and four others in this
    part, because a representative-keyed mapping misses on every package that is
    not its own representative.

    **DISPUTE R2, and it is the limit of this row.** The scaffold asks a seal
    author to "pin the two node sets as EQUAL — the values of
    ``_import_path_qualifiers`` and the keys of ``ImportRelation.packages``".
    That row cannot be written at this revision and cannot be turned green by
    the body these seals are for: no analyzer populates
    ``CallGraph.package_imports``, so the live comparison has no left-hand side,
    and a row asserting one would be red the day it was written and red the day
    the D5 body landed — vacuity shape "pins a transient unimplementedness",
    which this unit has already been burned by once. The narrower property that
    IS D5's and IS reachable is the one above. The full cross-derivation
    equality is owed by whichever round makes the Go row supply a relation, and
    it is recorded here so it is not lost.
    """
    for identity in _ACCEPTANCE_IMPORT_PATHS:
        assert identity not in (_GATES_PKG, _ITERATE_PKG), (
            "an import path and a key qualifier came out equal; the whole "
            "hazard this row guards is that they are DIFFERENT strings for one "
            "package, so a second derivation produces a node set that overlaps "
            "the first nowhere and every component silently splits"
        )

    for relation in (
        _acceptance_relation(),
        _reach_relation(),
        _acceptance_relation(gates={"unplaced": ("a path no unit claims",)}),
    ):
        nodes = frozenset(relation.packages)
        components = import_components(relation)
        assert frozenset(components) == nodes, (
            f"the component mapping is keyed on {sorted(set(components) - nodes)} "
            f"and is missing {sorted(nodes - set(components))}. holes_in_scope "
            "looks a package up by what package_of returned, so a mapping in "
            "any other key space misses silently on the subject's own package"
        )
        for identity, members in components.items():
            assert members <= nodes, (
                f"{identity!r}'s component names {sorted(members - nodes)}, "
                "which the relation does not carry"
            )
            assert identity in members, (
                f"{identity!r} is not in its own component; the relation is an "
                "equivalence and a package can always name itself"
            )
        for package in relation.packages.values():
            for key in sorted(package.symbols):
                assert relation.package_of(key) in components, (
                    f"package_of({key!r}) answered "
                    f"{relation.package_of(key)!r}, which is not a key of the "
                    "component mapping — the two derivations have diverged and "
                    "the lookup fails closed on every symbol in that package"
                )


def test_a_method_key_is_placed_through_package_of_and_never_by_string_surgery():
    """``…/classify.(*Config).Match`` is in ``…/classify``, and no split says so.

    The scaffold names this hazard on :attr:`PackageImports.symbols` and it is
    the concrete shape of the identity-agreement requirement at the spending
    seam: a Go method key is ``…/classify.(*Config).Match``, the qualifier is
    NOT "everything before the last dot", and a layer that guessed would place
    the method in a package called ``…/classify.(*Config)`` — a package in no
    component, on which every question fails closed, for every method in the
    repository.

    The row is built so that the two bodies give OPPOSITE answers rather than
    the same one twice, which is what makes it non-vacuous: the method's package
    and the subject's package are in DIFFERENT components, so the correct answer
    is to scope the hole AWAY, while a surgical body invents an unplaceable
    package, hits the fail-closed clause, and KEEPS it. A row built the other
    way round — same component — would be green under both.

    The control is judged in the same call: a second method hole, in the
    SUBJECT's own package and spelled with the same two dots, is kept. Without
    it the row is green against ``return ()``.

    Production reaches this input on every Go tree with a method: D6's
    ``go_symbol_key`` spells receivers this way and the acceptance tree's own
    ``preserve.go`` declares methods.

    RED at HEAD: :func:`holes_in_scope` raises ``NotImplementedError``.
    **Measured under**: deriving the hole's package as
    ``key.rpartition(".")[0]`` and falling closed when that names no package —
    reddens this row and NO other in the suite, which is the point: the surgery
    is invisible everywhere except on a method key. Returning ``holes``
    unchanged reddens the first half; the control is what covers ``return ()``.
    """
    gates_method = Symbol(
        key=f"{_GATES_PKG}.(*Runner).dispatch",
        path="cmd/gates/main.go",
        line=210,
    )
    iterate_method = Symbol(
        key=f"{_ITERATE_PKG}.(*Licence).allows",
        path="cmd/iterate/preserve.go",
        line=88,
    )
    gates_hole = (gates_method, "cmd/gates/main.go:217", "call through a value")
    iterate_hole = (iterate_method, "cmd/iterate/preserve.go:95", "call through a value")

    relation = _acceptance_relation(
        gates={"symbols": (_GATES_RUN.key, _GATES_SERVE.key, gates_method.key)},
        iterate={
            "symbols": (
                _ITERATE_SUBJECT.key,
                _ITERATE_HELPER.key,
                iterate_method.key,
            )
        },
    )
    assert relation.package_of(gates_method.key) == _GATES_PKG, (
        "the control failed: package_of could not place a method key, so the "
        "assertions below would be about the fixture and not about the caller"
    )

    kept = holes_in_scope(_ITERATE_SUBJECT, (gates_hole, iterate_hole), relation)
    assert kept == (iterate_hole,), (
        "a method-keyed hole was placed by string surgery. `…(*Runner).dispatch` "
        "is declared in cmd/gates, which the relation carries and which is in a "
        "DIFFERENT component from the cmd/iterate subject, so the hole is out "
        "of scope; a body splitting the key on a dot invents the package "
        f"'{_GATES_PKG}.(*Runner)', finds it in no component, and fails closed "
        f"— keeping it. Got {[h[0].key for h in kept]}"
    )


# --------------------------------------------------------------------------- #
# The second, separate defect: ``root_kind`` derives from ``kind`` AND from the
# declaring file, which is what ``_validate_root``'s own docstring already says.
# --------------------------------------------------------------------------- #


def test_root_kind_derives_from_the_kind_and_the_declaring_file_together(
    tmp_path, monkeypatch
):
    """A ``go_package_var`` in a ``_test.go`` is not "no root". It is a TEST root.

    :func:`_validate_root`'s docstring contracts ``root_kind`` as "DERIVED from
    ``kind`` AND from ``seal_verify.is_test_path`` over the declaring file". The
    code derives it from ``kind`` alone — ``_ROOT_KIND_BY_ENTRYPOINT.get(
    root.kind)`` — and then REFUSES any production kind found in a test file.
    The two agree only if a production kind in a test file is impossible, and it
    is idiomatic Go.

    **The consequence is measured and it was escalated to this layer twice by
    D6, in ``GoReachabilityAnalyzer.roots``' own docstring**, under
    ``feat/D6-body`` @ ``f4c7c46`` and again under ``feat/D6-adj4`` @
    ``c889ac6``:

      * ``func init()`` in ``z_test.go`` calling ``registered()`` — the root is
        dropped and ``registered`` reads FROM_NEITHER where the truth is
        FROM_TEST;
      * D6's ``<vars:test>`` symbol — the per-(package, binary) split P3 landed
        to stop a verdict flipping on a filename's sort order — is a
        ``go_package_var`` declared in a ``_test.go``, so it is exactly this
        case and contributes NO root in either fixture tree. The split raised
        the price of this defect rather than changing it.

    **FROM_NEITHER is not merely imprecise: it RAISES for a seal-derived
    subject** (:func:`test_from_neither_raises_for_a_seal_derived_subject`), so
    the under-approximation converts into an exception rather than into a
    quieter answer.

    D6's row cannot fix it and correctly did not try: routing ``<vars:test>``
    past its filter while this module derives PRODUCTION from ``go_package_var``
    alone trips ``_validate_root`` and turns a quiet under-approximation into a
    raise on a legal tree. The fix is one table lookup and it is D5's.

    Swept over every production :class:`EntrypointKind`, both root_kind
    spellings per member, because a body that special-cases ``GO_PACKAGE_VAR``
    has fixed the instance and not the derivation — ``GO_INIT`` in a ``_test.go``
    is the same tree and ``PYTHON_IMPORT_TIME`` in ``tests/conftest.py`` is the
    Python one.

    Two controls judged in the same call: the same kinds in a PRODUCTION file
    still derive PRODUCTION (the fix must not flip the default), and each kind's
    test-file root asserting PRODUCTION is still REFUSED (the fix must not
    become "accept whatever the row says").

    Production reaches this input on the first Go tree with a package-level
    ``var`` or an ``init`` in a test file, which D6 measured as idiomatic and
    built two fixtures around.

    RED at HEAD: ``discover_roots`` raises
    :class:`CallSiteReachabilityError` — "is a production entrypoint
    (go_package_var) declared in the test file …" — on the first assertion.
    **Measured under**: the current HEAD — this row is red, on
    ``_validate_root``'s "is a production entrypoint (go_main) declared in the
    test file" refusal; reverting the file half so ``expected`` comes from
    ``_ROOT_KIND_BY_ENTRYPOINT[kind]`` alone — reddens this row and
    ``test_a_root_that_disagrees_with_its_own_file_or_names_no_kind_is_refused``;
    accepting the row's asserted ``root_kind`` whenever the file is a test file
    — reddens this row, that same sibling, and
    ``test_root_kind_is_derived_from_the_kind_and_never_asserted_by_the_row[test_function]``;
    making :func:`_validate_root` a no-op — reddens this row and nine others.

    **DISPUTE R4 (prose that must move with the code).** :class:`Root`'s own
    ``root_kind`` docstring says "a production kind found in a test file is a
    :class:`CallSiteReachabilityError` rather than a coin flip" — the behaviour
    this row refutes — while :func:`_validate_root`'s docstring already
    contracts the derivation this row seals. The two have disagreed since the
    module was written, and the CODE implements the first. A body landing the
    fix must strike the :class:`Root` sentence; a body that edits only the
    derivation leaves the module carrying a contract it violates.

    **DISPUTE R5 (what the fix does NOT cost, measured).** The
    production-kind-in-a-test-file REFUSAL must go — a ``go_package_var`` in a
    ``_test.go`` becomes a root rather than a raise — and removing it was
    measured NOT to cost the sibling row: its "func main inside
    contract_seal_test.go" case still raises under the fix, because that row
    asserts PRODUCTION while the file now derives TEST. The refusal survives,
    for a different and better reason.
    """
    production_kinds = tuple(
        kind
        for kind in EntrypointKind
        if kind is not EntrypointKind.TEST_FUNCTION
    )
    assert len(production_kinds) == 7, (
        "EntrypointKind grew or shrank; this sweep is over every kind the "
        "table calls PRODUCTION and a member added without visiting it would "
        "go unswept"
    )

    tree = _tree(tmp_path)
    for kind in production_kinds:
        symbol = _sym(f"initOf_{kind.value}", "contract_seal_test.go", 11)
        honest = Root(
            symbol=symbol,
            kind=kind,
            root_kind=RootKind.TEST,
            evidence=f"cmd/classify/contract_seal_test.go:11 {kind.value}",
        )
        monkeypatch.setattr(csr, "ANALYZERS", (_go(roots=(honest,)),))
        assert discover_roots(tree) == (honest,), (
            f"a {kind.value} declared in contract_seal_test.go was not accepted "
            "as a TEST root. It is not 'no root': it runs, in the test binary, "
            "and everything it reaches is genuinely reached under test. "
            "root_kind is derived from the kind AND from is_test_path, which "
            "is what _validate_root's own docstring already says"
        )

        lying = Root(
            symbol=symbol,
            kind=kind,
            root_kind=RootKind.PRODUCTION,
            evidence="asserted by the row",
        )
        monkeypatch.setattr(csr, "ANALYZERS", (_go(roots=(lying,)),))
        with pytest.raises(CallSiteReachabilityError):
            discover_roots(tree)

        in_production = _sym(f"prodOf_{kind.value}", "main.go", 11)
        unchanged = Root(
            symbol=in_production,
            kind=kind,
            root_kind=RootKind.PRODUCTION,
            evidence=f"cmd/classify/main.go:11 {kind.value}",
        )
        monkeypatch.setattr(csr, "ANALYZERS", (_go(roots=(unchanged,)),))
        assert discover_roots(tree) == (unchanged,), (
            f"the control failed: a {kind.value} in a PRODUCTION file stopped "
            "deriving PRODUCTION, so the fix flipped the default rather than "
            "adding the file to the derivation"
        )


def test_a_test_function_outside_the_tests_is_refused_in_both_spellings(
    tmp_path, monkeypatch
):
    """The MIRROR direction stays a refusal, and the drop above it stays a drop.

    D6's P4 ruled the two directions for DIFFERENT reasons and only one of them
    is a defect. This row is the half that is CORRECT AND PERMANENT, sealed
    explicitly so that a body repairing the other half cannot repair it by
    deleting both clauses — which is the cheapest way to make the sibling row
    green and is measurably wrong.

    A ``func TestFoo`` in ``main.go`` starts nothing: ``go test`` runs ``TestX``
    only out of a ``_test`` file, so the conjunction
    :func:`go_test_root_predicate` contracts is false and there is no root. D6
    measured the consequence under ``feat/D6-body`` @ ``f4c7c46`` — ``func
    TestFoo`` in ``main.go`` calling ``reachedOnlyFromTestFoo``, the root
    dropped, the callee reading FROM_NEITHER — and ruled that TRUE, because
    nothing else calls it. Losing this refusal would make a production symbol
    named ``TestFoo`` a TEST root, and everything below it would read
    FROM_TESTS_ONLY: a BREACH manufactured out of a naming convention.

    BOTH root_kind spellings are refused, and the second is the one the naive
    fix opens. A body that rewrites the derivation as "TEST when
    ``is_test_path``, else the table" and DELETES the ``TEST_FUNCTION``-outside-
    the-tests clause accepts ``TEST_FUNCTION`` in ``main.go`` with
    ``root_kind=TEST``, because the table already derives TEST for that kind and
    the row's assertion agrees with it. Nothing would be red without this half.

    The control is judged in the same call: the well-formed pair still returns
    both roots, so the refusals are about the file/kind disagreement and not
    about the validator having been made to refuse everything.

    GREEN at HEAD, mutation-verified. The ``root_kind=TEST`` spelling is also
    covered by
    :func:`test_a_root_that_disagrees_with_its_own_file_or_names_no_kind_is_refused`;
    the ``root_kind=PRODUCTION`` spelling is covered nowhere, and the sweep in
    :func:`test_root_kind_is_derived_from_the_kind_and_never_asserted_by_the_row`
    does not reach it because that sweep puts every ``TEST_FUNCTION`` in a test
    file by construction.

    Production reaches this input on any Go tree with a helper named
    ``TestHelper`` in a production file, and on any Python module with a
    module-level ``test_`` function.

    **Measured under**: deleting the ``TEST_FUNCTION and not in_test_file``
    clause from :func:`_validate_root`, on top of the file-half fix — reddens
    this row and
    ``test_a_root_that_disagrees_with_its_own_file_or_names_no_kind_is_refused``,
    and nothing else in the suite. Making :func:`_validate_root` a no-op reddens
    this row and nine others. **The measurement is the reason this row exists:**
    with the file half added, the sibling's fourth refusal and this row are the
    only two things between a body and a production ``TestHelper`` becoming a
    TEST root, and the sibling covers only the ``root_kind=TEST`` spelling.
    """
    tree = _tree(tmp_path)
    for asserted in (RootKind.TEST, RootKind.PRODUCTION):
        misplaced = Root(
            symbol=_MAIN,
            kind=EntrypointKind.TEST_FUNCTION,
            root_kind=asserted,
            evidence=f"a TEST_FUNCTION inside main.go, root_kind={asserted.value}",
        )
        monkeypatch.setattr(csr, "ANALYZERS", (_go(roots=(misplaced,)),))
        with pytest.raises(CallSiteReachabilityError):
            discover_roots(tree)

    monkeypatch.setattr(csr, "ANALYZERS", (_go(),))
    assert set(discover_roots(tree)) == {_GO_MAIN_ROOT, _TEST_ROOT}, (
        "the control failed: the well-formed pair was refused too, so the "
        "refusals above are not about the file disagreeing with the kind"
    )
