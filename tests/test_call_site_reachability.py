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
"""

from __future__ import annotations

import ast
import re
import shutil
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
    Finding,
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
    reachable_from,
    subjects_of_seal,
    validate_analyzers,
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
) -> Finding:
    return check_subject(
        _SEAL,
        subject,
        graph=graph if graph is not None else _graph(),
        production_reach=_production_reach() if production_reach is None else production_reach,
        test_reach=_test_reach() if test_reach is None else test_reach,
        analyzer=analyzer if analyzer is not None else _go(),
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

    RED at HEAD. Reddens under a body on: returning ``()`` for a missing tree;
    swallowing an :class:`AnalyzerError`.
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
