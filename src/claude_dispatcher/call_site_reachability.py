r"""D5 — call-site reachability: does production call this?

CONTRACTS ONLY. Every function in this module raises
:class:`NotImplementedError` except the two named at their definitions
(:func:`validate_analyzers`, :func:`analyzer_for_path`) and the reason each is
an exception is written there. The docstrings are the specification; a body
author who finds one vague should get a ruling rather than guess, because the
last four units each had a seal author derive a ruling from prose and a P4
adjudicate the guess.

The defect class this exists for
================================
The first feature unit built end to end under the scaffold-first protocol
shipped a CRITICAL that the protocol cannot see:

    **A seal proves a function BEHAVES, and nothing proves the function RUNS.**

Measured on ``wt-b1-baseline``, 2026-08-10, in ``cmd/classify`` (Go):

  * ``ResolveConfigDual`` is declared at ``cmd/classify/contract.go:742``. It
    implements the §3.3 dual-config rule: two ``risk-paths.json`` tables whose
    bytes differ is ``INVALID_SCHEMA``, because which one names the project's
    money paths is not something ``classify`` may guess.
  * Six seals in ``contract_seal_test.go`` (``TestSeal_ResolveConfigDual``,
    line 852) and eight more in ``repair_seal_test.go`` certify it. Every one
    passes. The function does exactly what its doc comment says.
  * **Every call to it is from a ``_test.go`` file.** Counted: 27 mentions in
    ``*_test.go``, 0 in non-test source outside its own doc comment and its own
    ``func`` line.
  * Production resolves the config through ``resolveConfigPath``
    (``main.go:296``) → ``findConfig`` → ``configCandidates``
    (``main.go:401``), which takes the FIRST candidate that exists. So two
    differing money-path tables resolve silently to ``.agent`` and the rule
    nobody disputes is enforced nowhere.

The seal author was blameless. Nothing in the protocol requires a seal to prove
its subject is reachable from an entrypoint, so no seal was missing and no seal
was wrong.

**It is the second occurrence, which is why this is a mechanism and not a
wiring fix.** D1's round-1 panel found "the library had no production call
sites"; that was repaired inside D1, and it recurred in the very next unit.
Three of the four vacuous seals that panel found share this shape. A repair
that does not generalise is a repair that will be needed again on a schedule.

THE ANTI-REQUIREMENTS, FIRST, BECAUSE THEY CONSTRAIN EVERY DESIGN BELOW
=======================================================================
**1. It must not be satisfiable by a grep.** The B1 case passes a naive "is the
identifier mentioned anywhere" check, because fourteen seals mention it. It
also passes the *inverse* naive check, and that is the sharper lesson: the
first crude scan written while drafting this module — "an exported func with no
non-test mention" — reported ``ResolveConfigDual`` as CLEAN, because
``contract.go:712`` opens the function's own doc comment with its own name.
A mechanism that can be defeated by a comment is not a mechanism.

The refined crude scan (mentions in non-comment, non-declaration production
lines, within ``cmd/classify`` only) does find it, alongside six others::

    DesugarConfigScaffold  prod=0 test=5     ProjectPanelToV1   prod=0 test=8
    EmitterCovers          prod=0 test=9     ResolveConfigDual  prod=0 test=27
    GenerateReadSet        prod=0 test=22    SemanticEquivalentV1 prod=0 test=19
                                             SidecarSurvives    prod=0 test=13

That scan is recorded here as an ORDER OF MAGNITUDE and explicitly not as a
finding, for a reason that is this module's whole subject: it counts MENTIONS,
so it cannot tell a mention inside live code from a mention inside a function
that is itself dead. ``V2SidecarPath`` scores ``prod=3`` and a grep cannot say
whether any of those three lines runs. Transitive reachability from an
entrypoint is the question, and a grep is a one-hop approximation of it.

**2. It must not report reachable because it failed to look.** Every false
green in this effort has that shape. A parse failure, a missing entrypoint, an
unsupported language, an unresolvable call — each is an ABSTENTION
(:attr:`Reach.UNDECIDED`), never a pass. The rule is stated once, normatively,
and every dispatch below is written to obey it:

    **Failing to look may only make an answer LESS conclusive. It may never
    manufacture** :attr:`Reach.FROM_PRODUCTION`.

**3. It must not require a hand-maintained list of entrypoints.** An earlier
hand-list in this repo omitted ``recheck_min_severity``, the safety floor, and
an emitter built from it would have silently skipped every MEDIUM finding.
:func:`discover_roots` derives from the tree — ``func main()`` swept out of the
sources, ``[project.scripts]`` read out of ``pyproject.toml`` — and a
:class:`Root` this module cannot derive is not a :class:`Root`.

THE RELATIONSHIP TO D3, ITS SIBLING
====================================
``fixture_reachability`` (D3) is the mechanism for the dual problem: *a seal
green on an input production cannot produce.* D5 is its mirror image: *a seal
green on a function production does not call.* The two should feel like
siblings, and the vocabulary below is deliberately parallel: two axes named
separately, an abstention that is a first-class state, a total ruling grid, a
report whose first field is its own non-vacuity.

CARRIED OVER, deliberately
--------------------------
  * **Abstention is a named state and never a pass.** D3's
    :attr:`Reachability.NO_STRATEGY`; here :attr:`Reach.UNDECIDED`, and the
    count of it is this module's own coverage figure.
  * **The reason for an abstention is DATA, not prose.**
    :class:`UndecidedReason` is a straight lift of D3's :class:`WitnessGap`
    and of the P4 ruling that created it: two functions in one module agreeing
    on a prose format is not a protocol, and a reworded error message must not
    be able to flip a verdict toward the permissive side.
  * **The ruling grid is total and RAISES on any pair it does not name**
    (:func:`adjudicate`), so a new enum member cannot fall through to the
    permissive answer.
  * **Deliberately unenrolled.** Built, sealed, and with no call site.
    Enrolment is its own decision with its own evidence; see WIRING.
  * **The report's first field is its own non-vacuity.** D3 has
    ``boundaries_never_observed``; here :attr:`ReachabilityReport.roots` and
    :attr:`ReachabilityReport.seals_examined`, for the same reason — a report
    of zero breaches over zero subjects is what this module exists to stop
    other people shipping, and it must not be able to ship it itself.

DELIBERATELY NOT CARRIED OVER, and this is the load-bearing divergence
-----------------------------------------------------------------------
**D3 discovers by OBSERVING a suite run. D5 cannot, and a body author who
reaches for :func:`fixture_reachability.observe` will build the wrong thing.**

D3's question — "what values arrived at this consumer?" — is a question ABOUT
one run, and one run is the entire population of interest. D5's question — "is
there any path from an entrypoint to this symbol?" — quantifies over every run
the program could have. Observation answers it in one direction only:

  * observing the subject execute under a PRODUCTION root proves
    :attr:`Reach.FROM_PRODUCTION`. Sound, and useful.
  * NOT observing it proves nothing at all — and worse, the observation that is
    cheapest to make is a run of the test suite, under which the B1 subject
    executes 27 times. An observer pointed at ``pytest`` would have certified
    the defect.

So D5 is a STATIC call-graph reachability check, and the D3 discipline it keeps
is not the technique but the principle behind it: *do not ask the artifact to
declare what you can derive.* D3 refuses an annotation on 1811 rows and derives
boundaries by watching; D5 refuses an annotation on 1811 rows and derives roots,
subjects and edges from the tree.

CHOICE (the brief does not say whether observation has any role here):
observation is NOT scaffolded, in either direction. Rejected alternative: a
positive-only corroborator that upgrades :attr:`Reach.UNDECIDED` to
:attr:`Reach.FROM_PRODUCTION` when the subject is seen to execute under a
production root. It is sound and it would genuinely narrow limit 4 below. It is
out because it needs a way to RUN each production entrypoint under
instrumentation — for ``cmd/classify`` that is a compiled Go binary, for which
the Python-side observer of D3 has no equivalent at all — and because a
mechanism that is only ever exercised on the languages it can run would grow a
silent second answer for the ones it cannot. What would bring it back: one
measured case where the static analysis abstains, the runtime answer is
available, and the abstention blocked a real branch.

THE LANGUAGE QUESTION, ANSWERED
================================
The brief's hardest framing question: the failing case is Go, the dispatcher is
Python, and the gate already supports Python, Go and TypeScript through
``role_protocol.COMPARATORS``. Is D5 one language-parametric mechanism, or a
Python mechanism that happens to be needed for Go first?

**Answer: language-parametric, from the first commit, keyed on the EXISTING
registry — and the deciding evidence is not the file counts, it is that the
ABSTENTION RULE IS LANGUAGE-SPECIFIC IN A WAY THAT CHANGES THE VERDICT.**

The evidence, in the order it should be weighed:

  1. **The negative answer is conclusive in Go and usually is not in Python,
     and the difference is a property of the language, not of the analyzer's
     quality.** Go has no way to obtain a package-level function by name at
     runtime: there is no ``reflect`` lookup over a package's declarations, so
     if a symbol's name is referenced nowhere in the production closure, no
     dynamic edge can reach it either, and "no path" is a fact. Python is the
     opposite; ``getattr(module, name)`` with a computed ``name`` is routine.
     Measured in ``src/`` on this worktree, 2026-08-10: 100 ``getattr(`` call
     sites, six of them with a non-literal attribute name, three of those six
     inside ``fixture_reachability`` itself — which resolves ARBITRARY
     fully-qualified names out of a table (``_resolve_dotted``, line 847) and
     is D5's own sibling. A Python-first mechanism would therefore have baked
     in Python's rule, abstained on the Go case it was built for, and been
     switched off; a Go-first mechanism generalised later would have baked in
     Go's rule and reported a confident "no path" for Python code reached by
     ``getattr``, which is a false BREACH — the over-call that gets a check
     removed. The rule has to be a per-language row on day one. It is
     :attr:`ReachabilityAnalyzer.negative_is_conclusive`.
  2. **The registry pattern fits, and the fit is exact where it matters.**
     ``LanguageSupport`` is ``(language, extensions, fingerprinter)``;
     ``support_for_path`` is the ONE site that reads an extension, reading
     ``COMPARATORS`` and nothing else; ``validate_registry`` refuses two rows
     for one language or one extension. The shape D5 needs is the same shape:
     one row per language, one dispatch site, adding a language is adding a
     row. It is adopted verbatim in :data:`ANALYZERS` /
     :func:`validate_analyzers` / :func:`analyzer_for_path`.
  3. **But D5 must NOT be a fourth field on ``LanguageSupport``.** See the
     CHOICE on :data:`ANALYZERS`. Briefly: the two tables have different
     membership (a comparator row is a claim about reading SIGNATURES; an
     analyzer row is a claim about reading CALL EDGES, and the second is
     strictly harder), the rows carry different obligations, and
     ``role_protocol.py`` is on ``FLOOR_GLOBS`` — widening its central
     dataclass to carry an optional analyzer would make a row that has one
     shape-identical to a row that does not, which is a state that reads as
     coverage. What IS shared, and must be, is the KEY: D5 keys on
     ``role_protocol.Language`` and asks ``role_protocol.support_for_path``
     what language a path is, so **this module contains no file-extension
     literal and adds no second ``endswith``.** ``role_protocol`` has exactly
     one ``endswith`` over an extension by design; D5 keeps that count at one.

What the answer costs, stated so it is a decision and not an oversight: a
language D5 could analyze but that has no ``COMPARATORS`` row is invisible to
:func:`analyzer_for_path` and its files come back
:attr:`UndecidedReason.UNSUPPORTED_LANGUAGE`. That binds nothing today —
``COMPARATORS`` holds Python, Go and TypeScript and ``PENDING_COMPARATORS`` is
empty — and it is the right default, because a path whose language nobody has
agreed on is a path this gate should abstain about rather than guess at. The
trigger for revisiting: the first language with a reachability analyzer and no
signature comparator.

WHAT THIS MODULE REFUSES
=========================
Nothing today: it is not enrolled and has no call site (WIRING). The contract
for the day it is enrolled:

  * :attr:`Disposition.BREACH` — the subject is reached only from tests —
    **blocks**. It is the B1 defect exactly and it is not a warning.
  * :attr:`Disposition.REPORT`, :attr:`Disposition.ACCEPTED` and
    :attr:`Disposition.ABSTAIN` do not block. They are counted, printed, and
    an ABSTAIN count that grows is a coverage regression that a reader must be
    able to see without reading findings.

**The precedent that governs how enrolment is announced.** Enrolling the Go
comparator newly blocked a class of branch, and so did TypeScript, and both
were recorded as MEASURED facts rather than claimed harmless. Whoever enrols
D5 owes the same number: how many seals in this repository and in the two
target repositories become BREACH on the enrolling commit, counted by running
this module, not estimated. The crude scan above suggests ``cmd/classify``
alone contributes at least six, and it is a grep, and a grep is what this
module refuses to be — so the number is owed, not inherited.

WHAT THIS CANNOT DETECT
=======================
Stated plainly, because on this effort the honest limits have been worth more
than the claims.

  1. **A root whose kind is not in :class:`EntrypointKind`.** The enum is
     closed and derived-from-the-tree, not hand-listed, but the KINDS are
     written out. A program started by a mechanism nobody enumerated — an
     ``atexit`` hook, a signal handler, a CGo callback, a ``go:generate``
     directive, a systemd unit naming a symbol — has no root, and everything
     only it reaches reads as FROM_TESTS_ONLY. That is an over-call, and
     over-calls are how checks get switched off. :func:`discover_roots` must
     RAISE on a kind it cannot classify rather than skip it.
  2. **A call the extractor cannot resolve.** Interface dispatch, a function
     held in a value, a method on a receiver whose type needs full type
     inference. Followed, but marked (:attr:`PathQuality.OVER_APPROXIMATED`
     when followed, :attr:`UndecidedReason.DYNAMIC_EDGE` when the failure to
     follow could be hiding a path). Never silently dropped.
  3. **Whether the call site is CORRECT.** A subject called from production
     with wrong arguments, or in the wrong branch, or whose result is
     discarded, is :attr:`Reach.FROM_PRODUCTION` here. This module asks
     whether the function runs, never whether it is used right — and the B1
     defect had BOTH halves (nothing called ``ResolveConfigDual`` AND
     ``configCandidates`` puts ``$RISK_PATHS_CONFIG`` ahead of both config
     directories). D5 would have caught the first and is blind to the second.
  4. **Path conditions.** A call behind ``if false``, behind a flag that is
     never set, behind a version check that no deployment satisfies, is
     REACHED. See the CHOICE on :class:`EdgeKind`.
  5. **Cross-repository reach.** The tree under check is the tree under check.
     A library whose only callers are in another repository has no root here
     and lands in :attr:`UndecidedReason.NO_ENTRYPOINT`, which is an
     abstention over the whole tree. It is deliberately NOT "everything
     exported is reachable"; see the CHOICE on :class:`EntrypointKind`.
  6. **Build tags, ``//go:build`` constraints, conditional imports.** A file
     excluded from the build on this platform is still read by the analyzer,
     so an edge that exists only on Windows counts here. Over-approximating
     toward REACHED, which is the permissive direction, and it is a real hole
     rather than a conservative choice.
  7. **Generated code.** A generated file's call sites count. If the generator
     is not run in this tree, they are edges to code nobody ships.
  8. **Its own subject population.** D5 judges the subjects OF SEALS
     (:func:`discover_seals`). A production function nothing calls and no seal
     covers is invisible here — that is dead-code detection, a different and
     much noisier mechanism, and see the CHOICE on :func:`discover_seals`.
  9. **The declaration.** :class:`StagedDeclaration` is the one place this
     module is a policy rather than a measurement, and by D3's limit 10 it is
     the place it will first be abused.

DELIBERATELY NOT SCAFFOLDED
===========================
  * **A TypeScript analyzer, and the TypeScript entrypoint kinds that would go
    with it.** ``TYPESCRIPT_SUPPORT`` is enrolled in ``COMPARATORS``, so
    :func:`analyzer_for_path` will happily resolve a ``.ts`` path's language
    and find no analyzer row — which is
    :attr:`UndecidedReason.UNSUPPORTED_LANGUAGE`, a named abstention, exactly
    as a ``.sql`` path is. No :class:`EntrypointKind` member names a
    TypeScript concept, because a kind with no analyzer emitting it "will
    never fire and will be read as coverage" (D3's :class:`Boundary` contract,
    applied). D2's precedent, verbatim in its commit message: SQL and Java got
    no table entry on purpose. What would bring it back: an analyzer row.
  * **A consequence axis.** D3's second enum answers "does the unreachability
    MATTER", measured by a differential against the producible neighbour. The
    analogous question here — "is there a production path doing this subject's
    job differently, and worse?" — is exactly what made B1 a CRITICAL rather
    than dead weight (``findConfig`` takes the first hit; ``ResolveConfigDual``
    would have refused). It is not scaffolded because no measurement of it is
    within reach: "two functions do the same job" has no mechanical definition
    that is not a similarity heuristic, and a gate whose central discriminator
    is a heuristic is a gate that argues. The second axis here
    (:class:`PathQuality`) answers a different and decidable question instead.
    What would bring a consequence axis back: a mechanical definition of
    "competing implementation" that is not a similarity score.

WIRING
======
Written and NOT enrolled, following D2, D3 and D4. No call site is added by
this commit: not the orchestrator, not ``scripts/``, not CI, not
``role_protocol``. Enrolment is a later decision and needs the seals first,
because a check that reports zero findings because nothing calls it is
indistinguishable from a check that reports zero findings because the repo is
clean — which is this module's own subject matter, one level up, and D3 said
the same sentence about itself.

Two coordinations this scaffold may NOT perform, raised for P4:

  * ``FLOOR_GLOBS``. Once wired, this module is a gate whose decisions can be
    dissolved by editing it, so by the 2026-08-09 delegation-closure ruling it
    belongs on the floor. ``_FLOOR_ROWS`` in
    ``tests/test_role_protocol_floor.py`` is a set difference against
    ``FLOOR_GLOBS``, and a glob P1 invents that P4 has not written there
    reddens a live seal to protect an unwired module. Deferred, deliberately,
    and recorded rather than done — the same deferral D3 made and for the same
    reason.
  * The delegation closure. This module imports ``role_protocol`` (for
    ``Language`` and ``support_for_path``) and will import
    ``seal_verify.is_test_path``; both are already on the floor, so no new
    closure member arrives with it. Wiring D5 into a floor decision would put
    D5 itself into ``_DELEGATION_TARGETS`` and needs the same P4 round.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Mapping, Protocol, Sequence

from .role_protocol import COMPARATORS, Language, support_for_path

__all__ = [
    "CallSiteReachabilityError",
    "AnalyzerFault",
    "AnalyzerError",
    "AnalyzerUnavailable",
    "SourceUnreadable",
    "ReachabilityAnalyzer",
    "ANALYZERS",
    "validate_analyzers",
    "analyzer_for_path",
    "GO_REACHABILITY_SCHEMA",
    "GO_REACHABILITY_PACKAGE_DIR",
    "RootKind",
    "EntrypointKind",
    "Root",
    "discover_roots",
    "Symbol",
    "EdgeKind",
    "Edge",
    "CallGraph",
    "build_call_graph",
    "reachable_from",
    "SubjectGap",
    "Subject",
    "Seal",
    "discover_seals",
    "subjects_of_seal",
    "Reach",
    "UndecidedReason",
    "PathQuality",
    "CallPath",
    "Finding",
    "check_subject",
    "StagedDeclaration",
    "Disposition",
    "adjudicate",
    "ReachabilityReport",
    "check_tree",
]


class CallSiteReachabilityError(RuntimeError):
    """The check could not be carried out, as distinct from a finding.

    Raised for a malformed :data:`ANALYZERS` row, a :class:`Root` whose kind
    this module cannot classify, a :class:`Reach` /:class:`PathQuality` pair
    the ruling grid does not name, a subject that comes back
    :attr:`Reach.FROM_NEITHER` when the seal that named it is itself a test
    root, or a report assembled over zero roots.

    Never used to report a defect in the code under check, and a caller must
    not catch it and continue. An error here means the mechanism has no
    judgement, and a mechanism with no judgement that returns an empty finding
    list is the exact shape this module exists to refuse. The distinction is
    D3's ``FixtureReachabilityError``, kept deliberately identical: "the check
    could not run" and "the check ran and found nothing" must not be the same
    value.
    """


# --------------------------------------------------------------------------- #
# Part 1 — the language registry
# --------------------------------------------------------------------------- #


class AnalyzerFault(Enum):
    """Why an analyzer that EXISTS could not run. A closed, exhaustive set.

    Modelled on ``role_protocol.ComparatorFault`` and for the same stated
    reason: **a fault is not an unsupported language.** A language nobody can
    analyze is a permanent fact about the gate; a missing ``go`` binary is a
    fact about the machine the gate ran on. Conflating them is a live
    fail-open — a Go tree analyzed in a CI image with no toolchain would report
    "nothing to analyze here" for as long as the image stayed broken.

    Every member maps to :attr:`UndecidedReason.ANALYZER_FAULT`, i.e. to an
    ABSTENTION, and none of them maps to a verdict. That is the difference from
    ``ComparatorFault``, which maps to statuses of several kinds: D5 has
    exactly one honest thing to say when its analyzer did not run.

    TOOLCHAIN_MISSING
        The external program the analyzer needs (``go``) is not on PATH.
    TOOLCHAIN_UNUSABLE
        On PATH and did not answer: a failing version probe, a version older
        than the helper's language version, a ``GOCACHE``/``HOME`` the process
        cannot write. On PATH is not the same as working.
    HELPER_MISSING
        The helper program's source is not where this package looked. An
        install that dropped a non-Python asset (``tests/test_packaging.py``
        exists for exactly this; hit live twice on 2026-07-13) must not read as
        "no Go here".
    HELPER_FAILED
        The helper ran and exited non-zero.
    HELPER_TIMEOUT
        The helper exceeded its budget. A gate that hangs enforces nothing, and
        CI reports the hang as infrastructure rather than as an unanalyzed
        tree.
    HELPER_OUTPUT_INVALID
        Exit 0 and stdout is not a well-formed document of the expected schema
        — **including an EMPTY graph where a graph was expected.** "The tree has
        no edges" and "the helper returned nothing" must not be the same
        answer: the first would make every subject FROM_NEITHER, which is the
        loudest state this module has, so the failure direction here is a
        flood rather than a silence. Both are unacceptable; both are faults.
    """

    TOOLCHAIN_MISSING = "toolchain_missing"
    TOOLCHAIN_UNUSABLE = "toolchain_unusable"
    HELPER_MISSING = "helper_missing"
    HELPER_FAILED = "helper_failed"
    HELPER_TIMEOUT = "helper_timeout"
    HELPER_OUTPUT_INVALID = "helper_output_invalid"


class AnalyzerError(Exception):
    """Base for the two things an analyzer may raise.

    Deliberately not a subclass of anything in ``role_protocol``: the four
    handlers there map their own exception types to UNDETERMINED with a message
    about git, and an analyzer failure swept into one of those would lose both
    the fault and the tree. Two different failures with one name is invariant
    5's shape. ``ComparatorError``'s own docstring makes the same argument for
    the same reason, and the two hierarchies are separate for a third: an
    analyzer failure and a fingerprinter failure have different remediations
    and different reportable states.
    """


class AnalyzerUnavailable(AnalyzerError):
    """An analyzer that EXISTS could not run. Carries the named fault.

    A fact about the ENVIRONMENT, never about the file or the language.
    ``role_protocol.ComparatorUnavailable``'s shape, adopted verbatim including
    the constructor, so a reader of one recognises the other.
    """

    def __init__(self, fault: AnalyzerFault, message: str) -> None:
        super().__init__(f"{fault.value}: {message}")
        self.fault = fault
        self.message = message


class SourceUnreadable(AnalyzerError):
    """A file the analyzer opened and could not parse.

    Distinct from every :class:`AnalyzerFault`, on ``ComparatorFault``'s own
    reasoning: the gate opened the file, read it, and the file is bad. The
    remediation differs (fix the source vs fix the environment) and so does the
    party who can act. Maps to :attr:`UndecidedReason.PARSE_FAILED`.

    CHOICE (the design does not say whether one bad file abstains on one
    subject or on the whole tree): **the whole tree.** A call graph is not a
    per-file object — an unparsed file is a hole of unknown size in the edge
    set, and any "no path" answer computed around it is an answer computed
    around a hole. Rejected alternative: abstaining only on subjects declared
    in the unparsed file, which is cheap, is what a per-file mechanism would
    naturally do, and is wrong in precisely the permissive direction, because
    the file that fails to parse is the one most likely to hold the call site
    nobody wrote.

    ``path`` and ``message`` say which file and why, mirroring
    ``role_protocol.SourceUnparseable``. The path is the only thing that makes
    a whole-tree abstention actionable: a body that raised this with a message
    alone would report "this tree cannot be analyzed" and give nobody a file to
    fix.
    """

    def __init__(self, path: str, message: str) -> None:
        super().__init__(f"{path}: {message}")
        self.path = path
        self.message = message


class ReachabilityAnalyzer(Protocol):
    """One language's answer to the three questions this mechanism asks.

    NOT ``@runtime_checkable``, deliberately: ``isinstance`` against a
    runtime-checkable Protocol checks only that the NAMES exist, and it refuses
    outright when the Protocol carries non-method members, which this one does
    (``language``, ``negative_is_conclusive``). A decorator that looks like a
    shape check and is not one is worse than no decorator, so the shape check
    is written out in :func:`validate_analyzers` where a seal can read what it
    actually enforces.

    Three methods, not one, which is the substantive difference from
    ``role_protocol.SignatureFingerprinter`` and the reason D5 cannot ride on
    that protocol. A fingerprinter answers "what does this file declare"; an
    analyzer must answer "what does this tree START from", "what calls what",
    and "when is my silence conclusive".

    ``roots(tree)``
        Every :class:`Root` this language contributes, DERIVED FROM THE TREE.
        See :func:`discover_roots` for the derivation each kind owes and for
        the prohibition on hand-lists.
    ``graph(tree)``
        The :class:`CallGraph`: every :class:`Symbol` this language declares in
        the tree, and every :class:`Edge` between them, each edge carrying the
        :class:`EdgeKind` that says how well it is known.
    ``negative_is_conclusive``
        **The row's most important field and the one that makes this mechanism
        language-parametric rather than Python-with-a-Go-case.** ``True`` when
        the absence of a resolved path, over a closure containing no
        unresolvable in-repo edge, is a FACT about the language and not merely
        a fact about the analyzer. Go: ``True`` — a package-level function
        cannot be obtained by name at runtime, so a symbol referenced nowhere
        is called nowhere. Python: ``False`` — ``getattr(module, computed)``
        and ``importlib.import_module(computed)`` are routine, measured 6 times
        in ``src/`` on 2026-08-10, three of them inside D3.

        A ``False`` row cannot produce :attr:`Reach.FROM_TESTS_ONLY` and
        therefore cannot produce a BREACH by itself; it produces
        :attr:`UndecidedReason.DYNAMIC_EDGE` instead. That is a large cost and
        it is the honest one: a Python-side BREACH would rest on a claim the
        language does not support.

        CHOICE (the design is silent on whether this is a flag or a
        computation): a per-row BOOLEAN, decided once per language and
        readable in the table. Rejected alternative: computing it per tree from
        "does this tree actually contain dynamic dispatch". That is strictly
        more precise, and it is out because it makes the strongest verdict in
        the mechanism depend on a whole-tree property that a single added
        ``getattr`` silently flips — a branch could turn every BREACH in the
        repo into an ABSTAIN by adding one line, with nothing red. A row that
        says ``False`` is a claim a human made; a computed ``False`` is a
        claim a branch can make about its own judge.

    ``test_root_predicate(symbol)``
        Whether a symbol declared in a test FILE is a test ENTRYPOINT. The file
        question is not asked here: it is ``seal_verify.is_test_path``, which
        is this repo's one matcher for "is this one of the tests" and which
        already covers Go's ``_test.`` and Python's ``tests/``. Only the
        symbol-naming half is per-language (Go: ``Test``/``Benchmark``/
        ``Fuzz``/``Example`` prefixes on an exported name; Python: pytest's
        ``test_`` prefix and the classes it collects). Two disagreeing notions
        of "is this a test file" is invariant 5's failure mode and it was live
        once already; D5 does not open a second one.

    A row is validated for SHAPE at import (:func:`validate_analyzers`) and
    never for implementedness: ``NotImplementedError`` is a runtime fact, which
    is what lets a scaffolded row be validated before it works.
    """

    @property
    def language(self) -> Language:
        ...

    @property
    def negative_is_conclusive(self) -> bool:
        ...

    def roots(self, tree: Path) -> tuple["Root", ...]:
        ...

    def graph(self, tree: Path) -> "CallGraph":
        ...

    def test_root_predicate(self, symbol: "Symbol") -> bool:
        ...


#: **THE analyzer registry.** One row per language, keyed on the
#: ``role_protocol.Language`` member. The only input to
#: :func:`analyzer_for_path` beyond ``support_for_path`` itself.
#:
#: EMPTY, and empty is a claim. It does not mean "nobody has thought about the
#: languages"; it means no analyzer has been WRITTEN, so every path in every
#: tree comes back :attr:`UndecidedReason.UNSUPPORTED_LANGUAGE` — an
#: abstention — and no run of :func:`check_tree` can report a verdict until a
#: row lands. That is the correct starting state for a scaffold whose entire
#: thesis is that failing to look is not a pass, and it is the state D4's
#: ``PENDING_COMPARATORS`` note argues for in as many words: "scaffolded but
#: not enrolled" must be a NAMED state with a mechanism rather than a row
#: someone forgot.
#:
#: There is deliberately no ``PENDING_ANALYZERS`` beside it. D1 needed that
#: tuple because a comparator row can be written, validated and left inert
#: while its FLOOR entry lands first; D5 has no such ordering problem while it
#: is unenrolled, and a second table nothing dispatches on would be a second
#: place answering "what can this gate analyze". If enrolment ever needs the
#: staging, the D1 shape is there to copy and the copy is two lines.
#:
#: CHOICE (the brief asks what the registry pattern suggests, and the honest
#: reading is that it suggests a SEPARATE table): D5 gets its own table keyed
#: on the shared ``Language`` enum, rather than a fourth field on
#: ``LanguageSupport``. Three reasons, in ascending order of how much they
#: should bind the next author:
#:
#:   1. **Different obligations.** A ``LanguageSupport`` row promises to
#:      fingerprint one file's declarations from its text. An analyzer row
#:      promises a whole-tree edge set, a root derivation and a claim about the
#:      language's dynamic-dispatch surface. Bolting the second onto the first
#:      makes one row's ``fingerprinter`` and its ``analyzer`` two independently
#:      true-or-false claims wearing one row's name.
#:   2. **Different membership, and the asymmetry runs the wrong way for a
#:      shared row.** Signature comparison is the easier problem: Python, Go
#:      and TypeScript all have comparators today and D5 has no analyzer for
#:      any of them. A shared row would therefore be half-true for every
#:      language in the table on the day D5 lands, and an optional
#:      ``analyzer=None`` field makes a row that cannot answer
#:      shape-identical to one that can — which ``support_for_path`` would then
#:      return, and a caller would then read as coverage. That is the exact
#:      failure ``PENDING_COMPARATORS`` exists to prevent, reintroduced by a
#:      different door.
#:   3. **``role_protocol.py`` is on ``FLOOR_GLOBS``.** Widening its central
#:      registry dataclass is a floor edit, needs a P4 round, and would couple
#:      D5's enrolment schedule to the gate's. D3 refused a smaller floor
#:      coordination than this one for the same reason.
#:
#: Rejected alternative, spelled out because it is the tempting one: give D5 its
#: own ``extensions`` per row and skip ``role_protocol`` entirely. That buys
#: independence and costs the one property D1 spent a whole unit establishing —
#: exactly one place in this codebase decides what language a file is. A second
#: extension table would drift, and it would drift silently, because the two
#: gates would disagree only on files neither had been pointed at yet.
ANALYZERS: tuple[ReachabilityAnalyzer, ...] = ()


def validate_analyzers(analyzers: Sequence[ReachabilityAnalyzer]) -> None:
    """Refuse a registry that could give one language two answers. Pure.

    **The first of the two functions this scaffold implements rather than
    stubs.** The exception is D2's, verbatim: a seal cannot express "the
    registry is well formed" without calling it, and it runs at import over a
    literal, so it either always passes or always fails and a failure is
    visible on the first test collection rather than on the first Go tree.

    Raises :class:`CallSiteReachabilityError` when:

      * a row does not carry a ``role_protocol.Language`` member — a registry
        keyed by anything else has no closed set to be exhaustive over;
      * a :class:`Language` appears in more than one row — two analyzers for
        one language is the drift a registry exists to prevent, and here it is
        worse than in ``COMPARATORS`` because the two rows could disagree about
        ``negative_is_conclusive`` and the verdict would depend on row order;
      * a row's language has no ``COMPARATORS`` row, so
        :func:`analyzer_for_path` could never select it. A row no path can
        reach is coverage that reads as coverage and is not — D1's own words
        about an empty ``extensions``;
      * ``negative_is_conclusive`` is not a ``bool``. Not pedantry: a truthy
        non-bool is the ``bool("false")`` defect from ``skills/explicit-state.md``
        applied to the field that decides whether this module may emit a BREACH;
      * a row does not satisfy :class:`ReachabilityAnalyzer`.

    Never raises for a row being unimplemented. ``NotImplementedError`` is a
    runtime fact and this is a shape check; that is what lets a scaffolded row
    be validated before it works.
    """
    seen: dict[Language, ReachabilityAnalyzer] = {}
    enrolled = {row.language for row in COMPARATORS}
    for row in analyzers:
        language = getattr(row, "language", None)
        if not isinstance(language, Language):
            raise CallSiteReachabilityError(
                f"analyzer row {row!r} does not carry a Language member; a "
                "registry keyed by anything else has no closed set to be "
                "exhaustive over"
            )
        if language in seen:
            raise CallSiteReachabilityError(
                f"language {language.value!r} has two analyzer rows; two "
                "analyzers for one language could disagree about "
                "negative_is_conclusive, and the verdict would then depend on "
                "row order"
            )
        seen[language] = row
        if language not in enrolled:
            raise CallSiteReachabilityError(
                f"analyzer row for {language.value!r} has no COMPARATORS row, "
                "so support_for_path can never select it and no path can reach "
                "this analyzer — coverage that reads as coverage and is not"
            )
        if not isinstance(getattr(row, "negative_is_conclusive", None), bool):
            raise CallSiteReachabilityError(
                f"analyzer row for {language.value!r} must declare "
                "negative_is_conclusive as a real bool; a truthy non-bool is "
                "the coercion defect from skills/explicit-state.md applied to "
                "the one field that decides whether this module may emit a "
                "BREACH"
            )
        for method in ("roots", "graph", "test_root_predicate"):
            if not callable(getattr(row, method, None)):
                raise CallSiteReachabilityError(
                    f"analyzer row for {language.value!r} has no {method!r} "
                    "and cannot satisfy ReachabilityAnalyzer"
                )


validate_analyzers(ANALYZERS)


def analyzer_for_path(path: str) -> ReachabilityAnalyzer | None:
    """The analyzer row that can read ``path``, or None.

    **The second and last function this scaffold implements rather than stubs,
    and the reason is D3's for ``boundary_for`` plus D2's for
    ``support_for_path``:** it is the single answer site for "who reads this",
    a seal that re-spells the lookup can drift from the implementation with
    both of them green, and — the part specific to D5 — *implementing it is how
    this module PROVES it holds no file-extension literal of its own.*

    The two-step is the whole design and both steps matter:

      1. ``role_protocol.support_for_path(path)`` answers "what language is
         this". That function is the ONE place in this codebase where a file
         extension decides anything, and D5 keeps that count at one by asking
         rather than matching. There is no ``endswith`` in this module.
      2. :data:`ANALYZERS` answers "who can analyze that language". Keyed on
         the ``Language`` member, so the two tables cannot disagree about what
         a ``.go`` file is even while they disagree about whether anyone can
         analyze it.

    Returns None in two DIFFERENT situations that a caller must not conflate,
    and this function deliberately does not distinguish them, because the
    caller that needs the distinction is :func:`check_tree` and it has the path
    in hand:

      * no ``COMPARATORS`` row matches the extension (``.sql``, ``.java``);
      * a ``COMPARATORS`` row matches and no analyzer row does (``.ts`` today,
        and ``.py`` and ``.go`` today too, since :data:`ANALYZERS` is empty).

    Both are :attr:`UndecidedReason.UNSUPPORTED_LANGUAGE`, so nothing downstream
    turns on telling them apart TODAY. They are named separately here so that a
    body author who later wants to report them differently finds the seam
    already described rather than inventing a second lookup.

    ``path`` is posix form, as git emits, matching ``support_for_path``'s own
    contract.
    """
    support = support_for_path(path)
    if support is None:
        return None
    for row in ANALYZERS:
        if row.language is support.language:
            return row
    return None


#: The Go helper's protocol version, on every request and every response.
#: Checked rather than assumed, exactly as ``GO_HELPER_SCHEMA`` is: a helper
#: source that a branch, an install or a partial upgrade left at a different
#: version is :attr:`AnalyzerFault.HELPER_OUTPUT_INVALID`, never a best-effort
#: read of whatever came back. Bump it whenever the SYMBOL SPELLING or the edge
#: grammar changes, because a symbol key is compared for equality across the
#: root set and the subject set and a spelling change would otherwise read as
#: every subject being unreachable — the loudest possible false report.
GO_REACHABILITY_SCHEMA = "claude-dispatcher/go-call-reachability/v1"

#: Where the Go helper's source will live, relative to this package. Inside
#: ``src/claude_dispatcher/`` and NOT in ``tools/``, for ``GO_HELPER_PACKAGE_DIR``'s
#: stated reason and it applies with more force here: the gate judges trees in
#: OTHER repositories, so a helper read out of the judged repo would be a
#: CALL-GRAPH ANALYZER supplied by the branch whose call graph it is computing.
#:
#: Nothing is written at this path by this commit. The constant exists so that
#: the floor entry it will need is nameable before the directory exists —
#: D4's precedent, whose commit message is "the floor lands before the 9.1 MB
#: blob does", and whose reasoning was that a floor arriving WITH the asset was
#: absent for the commit that added it.
#:
#: CHOICE (the design does not say how the Go side is read): a stdlib-only Go
#: helper doing NAME-LEVEL resolution over ``go/ast``, in a module of its own
#: with no dependencies — the ``go_signature_fingerprint/go.mod`` pattern,
#: which states the rule as "stdlib only, forever". Rejected alternative:
#: ``golang.org/x/tools/go/ssa`` with ``callgraph/rta``, which is the correct
#: tool for this job and would resolve interface dispatch properly. It is out
#: on that go.mod's own recorded reasoning: "a dependency would need a module
#: cache, and a module cache is a network fetch and a writable HOME on the gate
#: path — two more ways to be TOOLCHAIN_UNUSABLE in CI". Buying precision with
#: two new fail-open surfaces is the trade this effort has refused three times.
#:
#: What the rejection costs, measured against the case that motivated the unit:
#: nothing. ``ResolveConfigDual`` is a package-level function in ``package
#: main``, and every reference to it within that package is a bare identifier
#: an AST walk resolves exactly. The cost lands on method and interface calls,
#: where name-level resolution over-approximates
#: (:attr:`PathQuality.OVER_APPROXIMATED`) rather than guesses.
#:
#: CHOICE (the design does not say what one helper invocation covers): a FILE
#: SET — one whole Go package, or module, per invocation — and NOT one file, so
#: this protocol diverges from ``GoHelperRequest``'s "one revision of one file,
#: not a batch". The divergence is forced: a call graph is not a per-file
#: property, and a per-file protocol would make every cross-file call in a
#: package an unresolved edge, i.e. would abstain on almost everything. What is
#: kept from ``GoHelperRequest``: source travels as TEXT rather than as
#: filenames, so the analysis never depends on the working tree that the branch
#: controls. What is lost, and must be replaced: the per-file timeout that made
#: "which file" answerable. Rejected alternative: keeping per-file requests and
#: stitching the graph on the Python side, which moves Go's name-resolution
#: rules into Python — a second implementation of Go scoping, in the wrong
#: language, maintained by nobody.
GO_REACHABILITY_PACKAGE_DIR = "go_call_reachability"


# --------------------------------------------------------------------------- #
# Part 2 — the roots: what does this tree START from?
# --------------------------------------------------------------------------- #


class RootKind(Enum):
    """Whether a root is production or test. Two states, exhaustively.

    The single most important distinction in this module, because
    :attr:`Reach.FROM_TESTS_ONLY` — the B1 defect — is definable only against
    it. Kept as its own two-valued enum rather than as a ``bool`` on
    :class:`Root` for the reason ``skills/explicit-state.md`` gives about
    policy-bearing booleans: a truthy non-bool, or a field somebody later
    defaults, would silently reclassify a test root as production and turn
    every BREACH into an OK.

    PRODUCTION
        A way the shipped program starts. Reaching a subject from one of these
        is what "production calls it" means.
    TEST
        A way the test suite starts. Reaching a subject from one of these and
        from nothing else is the defect.

    There is no third member and no UNKNOWN. A root whose kind cannot be
    decided is not a root: :func:`discover_roots` RAISES
    :class:`CallSiteReachabilityError` rather than admit one, because the two
    failure directions are both intolerable — classified as PRODUCTION it
    silently certifies everything below it, classified as TEST it floods the
    report with false BREACHes.
    """

    PRODUCTION = "production"
    TEST = "test"


class EntrypointKind(Enum):
    """How a root starts. A CLOSED set, and every dispatch over it must be
    exhaustive and RAISE on an unknown member.

    The brief asks for these exhaustively and the honest answer has two parts:
    the set below is exhaustive over the mechanisms this module can DERIVE from
    a tree, and limit 1 in the module docstring names what that leaves out. A
    kind is here only when some analyzer emits it; a kind with no analyzer
    "will never fire and will be read as coverage".

    Go — PRODUCTION
    ---------------
    GO_MAIN
        ``func main()`` in a file declaring ``package main``. Derived by
        sweeping the tree; seven of them in ``claude-workflow`` today
        (``cmd/{classify,iterate,recheck,repro,deepseek,reviewer,gates}``).
    GO_INIT
        ``func init()`` in any package that a ``GO_MAIN`` package transitively
        imports. Go runs every such function before ``main`` and it is a
        genuine root, not a curiosity: a package whose only job is to register
        itself in a table does it here. Zero instances in ``cmd/classify``
        today, measured 2026-08-10 — so this member is written on the
        LANGUAGE's semantics rather than on an instance, which is the one place
        this module admits a kind with no measured example, because omitting it
        would make everything an ``init`` reaches a false BREACH.
    GO_PACKAGE_VAR
        A package-level ``var x = f()``. Runs before ``init``. Same argument as
        ``GO_INIT`` and the same admission.

    Python — PRODUCTION
    -------------------
    PYTHON_CONSOLE_SCRIPT
        A ``[project.scripts]`` entry in ``pyproject.toml``. Derived by reading
        that file. One today: ``dispatcher = "claude_dispatcher.cli:main"``.
    PYTHON_MODULE_MAIN
        A ``__main__.py`` in a package, making ``python -m pkg`` a start.
        One today: ``src/claude_dispatcher/__main__.py``.
    PYTHON_SCRIPT_MAIN
        The body of an ``if __name__ == "__main__":`` block. Six today, in
        ``cli.py``, ``__main__.py``, ``role_protocol.py``, ``ts_parser_vendor.py``,
        ``tools/retroactive_sweep.py`` and ``tools/cross_family_panel.py``.
    PYTHON_IMPORT_TIME
        Module-level statements of any module another root imports. Not a
        technicality: ``role_protocol.py`` calls
        ``validate_registry(COMPARATORS, PENDING_COMPARATORS)`` at module level,
        and that call is the only thing keeping a malformed registry out of the
        build. A mechanism that did not name this kind would report the repo's
        own registry validator as dead.

    TEST
    ----
    TEST_FUNCTION
        A function in a file ``seal_verify.is_test_path`` calls a test, whose
        name the analyzer's ``test_root_predicate`` accepts. One kind for both
        languages, because the FILE half of the question is answered by one
        shared matcher and only the naming half is per-language.

    THERE IS NO ``PUBLIC_API`` AND THERE MUST NOT BE
    ------------------------------------------------
    CHOICE (the brief asks what an entrypoint is for a library, and this is the
    answer): **a library's exported surface is NOT a root.** A tree with no
    root of any kind above is :attr:`UndecidedReason.NO_ENTRYPOINT` — an
    abstention over the whole tree — and never "everything exported is
    reachable" and never "nothing is reachable".

    Rejected alternative: treat exported symbols (``__all__``, a capitalised Go
    identifier, a package's public API) as roots. It is the obvious answer, it
    is what a linter would do, and it is measurably fatal here:
    ``ResolveConfigDual`` is capitalised, therefore exported, therefore a root
    under that rule — so the mechanism built to catch the B1 defect would
    certify the B1 defect as REACHED on its first run. The same objection
    applies in Python to any module whose ``__all__`` lists a dark function.

    The cost is real and is limit 5: a genuine library, consumed only from
    another repository, gets an abstention rather than an answer. That is the
    correct trade — an abstention says "this mechanism has nothing to tell you
    about this tree", which is true, whereas the exported-surface rule says
    "everything here is fine", which is false and is the exact sentence this
    module exists to stop being said.
    """

    GO_MAIN = "go_main"
    GO_INIT = "go_init"
    GO_PACKAGE_VAR = "go_package_var"
    PYTHON_CONSOLE_SCRIPT = "python_console_script"
    PYTHON_MODULE_MAIN = "python_module_main"
    PYTHON_SCRIPT_MAIN = "python_script_main"
    PYTHON_IMPORT_TIME = "python_import_time"
    TEST_FUNCTION = "test_function"


@dataclass(frozen=True)
class Root:
    """One place execution starts.

    ``symbol``
        The :class:`Symbol` execution enters at. For ``PYTHON_IMPORT_TIME`` and
        ``GO_PACKAGE_VAR`` this is a synthetic module-level symbol rather than
        a declared function, and :class:`Symbol` says how those are spelled —
        synthetic rather than omitted, because a root with no symbol has no
        outgoing edges and would silently contribute nothing.
    ``kind``
        Which mechanism starts it.
    ``root_kind``
        PRODUCTION or TEST. **Derived from ``kind`` and from
        ``seal_verify.is_test_path`` over the declaring file, never asserted by
        the analyzer independently**, so a row cannot mark its own roots
        production. ``TEST_FUNCTION`` is the only kind that yields TEST, and a
        production kind found in a test file is a
        :class:`CallSiteReachabilityError` rather than a coin flip — a
        ``func main()`` inside ``_test.go`` is a tree this module does not
        understand, and saying so is cheaper than being wrong in either
        direction.
    ``evidence``
        What was read to derive this root, in a form a human can check by hand:
        ``"pyproject.toml [project.scripts] dispatcher"``,
        ``"cmd/classify/main.go:180 func main, package main"``. Not decoration.
        A root nobody can verify is a root nobody will believe when it produces
        a BREACH, and the derived-not-hand-listed property is only auditable
        through this field.
    """

    symbol: "Symbol"
    kind: EntrypointKind
    root_kind: RootKind
    evidence: str


def discover_roots(tree: Path) -> tuple[Root, ...]:
    """Every :class:`Root` in ``tree``, DERIVED. Never read from a list.

    The anti-requirement this function exists to satisfy is the third one, and
    the precedent is concrete: an earlier hand-list in this repo omitted
    ``recheck_min_severity``, the safety floor, and an emitter built from it
    would have silently skipped every MEDIUM finding. So there is no
    ``ENTRYPOINTS`` constant here and there must never be one. Each kind names
    the artifact it is derived FROM, in :class:`EntrypointKind`, and a kind
    whose derivation cannot be written is a kind that does not go in the enum.

    Obligations a body must meet, each of which a seal can pin:

      * **Total over :class:`EntrypointKind`, raising on an unknown member.**
        ``skills/explicit-state.md``'s step 3, which is the one that bites:
        naming the states does not give exhaustiveness for free, and a kind
        that falls through to "skip" is a root class that silently stops
        existing.
      * **Every language in the tree contributes.** A tree is swept with
        :func:`analyzer_for_path` per file; a file whose language has no
        analyzer contributes no roots AND is recorded, because "this tree has
        no Go roots" and "nobody looked for Go roots" must not be the same
        answer. :attr:`ReachabilityReport.unanalyzed_paths` is where it goes.
      * **RAISE on an undecidable root_kind**, per :class:`Root`.
      * **An empty result is returned, not swallowed.** Zero production roots
        is a legitimate answer for a library, and it is
        :attr:`UndecidedReason.NO_ENTRYPOINT` at the point of judgement, not a
        silent empty sweep here.

    Raises :class:`CallSiteReachabilityError` if ``tree`` is not a directory,
    or if any analyzer raises :class:`AnalyzerError` — a partial root set is
    worse than none, because the roots that failed to appear are exactly the
    ones whose absence manufactures BREACHes.

    CHOICE (the design does not say whether the tree is the repository or the
    changed set): **the whole repository tree**, always, even when the caller
    is judging one branch's diff. Rejected alternative: deriving roots from the
    changed files only, which is what every other gate in this repo does and is
    much cheaper. It is out because reachability is a whole-program property in
    exactly the way a signature comparison is not: the call site that makes a
    subject live is overwhelmingly likely to be in a file the branch did not
    touch, and a root set computed from the diff would report every unchanged
    entrypoint as absent. The cost is that this check is expensive and cannot
    be made cheap by scoping; that is a reason to run it at a different cadence,
    not a reason to scope it wrongly.
    """
    raise NotImplementedError(
        "discover_roots: no root derivation is written. Deriving roots needs "
        "one ReachabilityAnalyzer row per language present in the tree and "
        "ANALYZERS is empty, so there is nothing to sweep with"
    )


# --------------------------------------------------------------------------- #
# Part 3 — the graph: what calls what?
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Symbol:
    """One callable thing, spelled so two analyzers cannot disagree about it.

    ``key``
        The comparison key, and the ONLY field any decision reads. Fully
        qualified and language-owned: ``claude_dispatcher.risk.evaluate`` for
        Python, ``github.com/yourorg/claude-workflow/classify.ResolveConfigDual``
        for Go, ``…classify.(*Config).Match`` for a Go method. Qualified rather
        than bare so two packages may own same-named functions, which is not
        hypothetical — ``main`` is the package name of all seven ``cmd/``
        binaries.

        A synthetic root (``PYTHON_IMPORT_TIME``, ``GO_PACKAGE_VAR``) is
        spelled with a suffix no declaration can produce, e.g.
        ``claude_dispatcher.role_protocol.<module>``. Synthetic rather than
        omitted: a root with no symbol has no outgoing edges and would
        contribute silently nothing, which is the failure this module is about.
    ``path``
        The file it is declared in, posix, repository-relative. Read for
        exactly two things and nothing else: reporting, and
        ``seal_verify.is_test_path``.
    ``line``
        Where, so a finding names a place a human can open.

    ``path`` and ``line`` are deliberately NOT part of the identity: a symbol
    that moved file is the same symbol, and a graph keyed on location would
    report every refactor as a mass unreachability event. Equality and hashing
    are over ``key`` alone — which a body must implement explicitly, since a
    frozen dataclass hashes all three fields by default. A seal should pin it.
    """

    key: str
    path: str
    line: int


class EdgeKind(Enum):
    """How well an edge is known. Four states, exhaustively.

    This enum is where "what counts as reached" is actually decided, and the
    brief's list maps onto it as follows:

    DIRECT
        A call by name, resolved to exactly one declaration. ``findConfig(wt)``
        inside ``package main``.
    METHOD
        A call on a receiver whose declared type the analyzer knows, resolved
        to exactly one declaration. Distinguished from DIRECT because the
        stdlib-only Go analyzer resolves these less often than a type-checked
        one would, and the report should be able to say which kind of
        resolution it was leaning on.
    INTERFACE
        A call through an interface method, or a Python call on a value whose
        type is not known. Resolved to the SET of in-repo declarations that
        could satisfy it. **Over-approximating**: it may create a path that no
        execution takes. It is followed rather than dropped, because dropping
        it under-approximates and under-approximation manufactures BREACHes,
        which is the over-call direction; and it is MARKED rather than followed
        silently, because an unmarked over-approximation manufactures OKs,
        which is the permissive direction. A path using one is
        :attr:`PathQuality.OVER_APPROXIMATED` and is never spelled the same as
        a resolved one.
    REFERENCE
        The symbol is mentioned as a VALUE and not called: assigned, passed to
        another function, put in a table, registered as a callback,
        ``sort.Slice(xs, less)``. This is a real way production reaches code and
        omitting it would be a large false-BREACH source. It is a weaker fact
        than a call — the value may never be invoked — so a path through one is
        also :attr:`PathQuality.OVER_APPROXIMATED`.

    An edge whose target the analyzer cannot name at all is NOT a member here.
    It is not an edge; it is a hole, counted in
    :attr:`CallGraph.unresolved_calls`, and its consequence is
    :attr:`UndecidedReason.DYNAMIC_EDGE`. Naming it as a fifth EdgeKind was the
    first draft and it was wrong: an "edge to nowhere" is not something a path
    can traverse, and putting it in this enum invites a body to treat the
    absence of a target as a target.

    CHOICE (the brief asks about a call behind a flag): **a flag-guarded call
    is REACHED, at DIRECT strength, and no member here marks it.** A call site
    behind ``if opts.enableX`` is a wiring decision that has been made; the
    flag decides whether it runs today, not whether production knows about the
    function. Rejected alternative: path-sensitive analysis, which would need
    to evaluate conditions, would need to know a deployment's configuration,
    and would turn a reachability check into a symbolic executor. The cost is
    limit 4: a call behind ``if false`` reads as REACHED. Recorded rather than
    narrowed, and the direction of the error is the permissive one, which is
    the one this module is otherwise strict about — so it is the single largest
    concession in the design and a seal author should say so out loud.

    CHOICE (the design is silent on transitive reach): **transitive counts,
    with no depth limit.** A subject called by a helper that main calls is
    reached. Rejected alternative: direct calls from a root only, which is
    trivially cheap and would report essentially every function in the
    repository as unreachable — a check whose first run produces a thousand
    findings is a check that gets deleted, and D3's own note that "an
    over-calling check is one nobody runs twice" applies with full force.
    """

    DIRECT = "direct"
    METHOD = "method"
    INTERFACE = "interface"
    REFERENCE = "reference"


@dataclass(frozen=True)
class Edge:
    """``caller`` reaches ``callee``, this well, from here."""

    caller: Symbol
    callee: Symbol
    kind: EdgeKind
    #: ``file:line`` of the call site itself, which is where a human looks and
    #: — for a BREACH — where the missing call has to be written.
    site: str


@dataclass(frozen=True)
class CallGraph:
    """One tree's symbols and edges, plus an honest account of what is missing.

    ``symbols``
        Every symbol declared in the tree, keyed by ``Symbol.key``. Every
        declaration, including the ones nothing references: a symbol absent
        from this map cannot be a subject, and a subject that cannot be found
        is :attr:`UndecidedReason.SUBJECT_UNIDENTIFIED`, not a pass.
    ``edges``
        Every edge, in no guaranteed order.
    ``unresolved_calls``
        Every call site whose target the analyzer could not name, as
        ``(caller, site, detail)``. **THE non-vacuity field of the graph, and
        the second thing a reader should look at after the root list.** It is
        the exact quantity that decides whether a "no path" answer is
        conclusive (:attr:`UndecidedReason.DYNAMIC_EDGE`), so a graph that
        reports zero of them is either a very well-resolved tree or an analyzer
        that is not counting — and those two must not be the same value. A
        seal should pin a tree with a known dynamic call and require it here.
    ``unreadable_paths``
        Files the analyzer could not parse. Non-empty means the whole tree
        abstains; see :class:`SourceUnreadable`.

    CHOICE (the design does not say what "in-repo" means for the edge set):
    **edges are kept only when BOTH ends are declared in the tree.** A call
    into the standard library or a vendored dependency is dropped, and a
    callback PASSED to one is kept as a ``REFERENCE`` edge from the caller to
    the callback. Rejected alternative: modelling dependency internals, which
    would need their sources, would make the graph size unbounded, and would
    add nothing — a subject in this tree is reached from this tree's roots, and
    a dependency that calls back into it does so through a value this tree
    handed it, which the REFERENCE edge already records.
    """

    symbols: Mapping[str, Symbol]
    edges: tuple[Edge, ...]
    unresolved_calls: tuple[tuple[Symbol, str, str], ...]
    unreadable_paths: tuple[str, ...]


def build_call_graph(tree: Path) -> CallGraph:
    """The union of every enrolled analyzer's graph over ``tree``.

    One graph and not one per language, because a root in one language can
    reach a symbol in another and a per-language graph would report that as
    unreachable. Nothing crosses today — the dispatcher is Python and calls Go
    only as a subprocess — and a subprocess call is exactly the case this
    contract must NOT pretend to see: ``subprocess.run(["go", "run", "."])`` is
    a call to the operating system, the callee is not a :class:`Symbol`, and
    the honest record of it is an entry in
    :attr:`CallGraph.unresolved_calls`, never a synthesised cross-language
    edge.

    Obligations a body must meet:

      * **Every file is offered to :func:`analyzer_for_path`.** A file whose
        language has no analyzer is recorded in
        :attr:`ReachabilityReport.unanalyzed_paths` and contributes nothing —
        recorded, because a file nobody read is not a file with no edges.
      * **A :class:`SourceUnreadable` is recorded, not raised past.** It lands
        in ``unreadable_paths`` and makes the whole tree abstain at judgement
        time; raising here would lose every other file's edges and turn one bad
        file into a total outage of the check.
      * **An :class:`AnalyzerError` that is not :class:`SourceUnreadable`
        PROPAGATES**, wrapped as :class:`CallSiteReachabilityError`. A toolchain
        that is not there is the check not running, and a partial graph
        returned from a partial run is a graph whose missing edges look exactly
        like edges that do not exist.
      * **Determinism.** Two runs over the same tree produce equal graphs, so a
        diff between two reports is a real change. Sort at construction, not at
        print time.
    """
    raise NotImplementedError(
        "build_call_graph: no edge extraction is written. It needs a "
        "ReachabilityAnalyzer per language and ANALYZERS is empty"
    )


def reachable_from(
    graph: CallGraph, roots: Sequence[Root]
) -> Mapping[str, tuple[Edge, ...]]:
    """Transitive closure over ``graph`` from ``roots``, with a witness path.

    Returns ``Symbol.key`` -> the edge chain from some root to it, so a finding
    can SHOW the path rather than assert it. The chain, not merely the fact:
    a mechanism that reports "reachable" with no path is one nobody can check,
    and unverifiable green is the thing this whole effort is about.

    Which chain, when several exist — and this is not a tie-break, it is a
    correctness rule: **the chain with the best :class:`PathQuality`.** A
    subject reached both through a resolved chain and through an interface
    chain is :attr:`PathQuality.RESOLVED`, because the resolved path is a fact
    and the over-approximated one is a possibility. Among chains of equal
    quality, the shortest; among equal-length, the one whose root sorts first
    by ``Symbol.key``, so the answer is deterministic.

    Pure: reads ``graph`` and ``roots`` and touches nothing else. It does not
    consult :class:`RootKind` — the caller runs it twice, once over the
    production roots and once over the test roots, and :func:`check_subject`
    compares. Two calls rather than one labelled traversal so that neither
    result can be contaminated by the other: a single traversal carrying a
    "reached from a production root" flag has to propagate that flag correctly
    through every merge, and a flag that propagates wrongly in the permissive
    direction is a test root laundering itself into a production answer.
    """
    raise NotImplementedError(
        "reachable_from: no traversal is written. It needs a CallGraph and "
        "build_call_graph raises"
    )


# --------------------------------------------------------------------------- #
# Part 4 — the subject: what does a seal claim to cover?
# --------------------------------------------------------------------------- #


class SubjectGap(Enum):
    """Why a seal yielded no subject, as DATA. Three states, exhaustively.

    A straight lift of D3's :class:`WitnessGap` and of the P4 ruling that
    created it, applied to the other end of the mechanism: the discriminator
    between "this seal calls nothing in the repository" and "this seal calls
    something the analyzer could not name" must not be the WORDING of a detail
    string. Two functions in one module agreeing on a prose format is not a
    protocol — the body author writes both, they agree by construction, and the
    pair is green whatever the strings are. Then someone rewords a message and
    the verdict moves. Data, therefore, and no decision reads prose.

    NO_CALLS
        The seal's body calls nothing declared in the tree. It is a pure
        assertion over literals, or over the standard library, or it is a
        table-only row. A legitimate thing for a seal to be, and no finding
        follows from it.
    ALL_TARGETS_IN_TESTS
        Everything it calls is declared in a test file. It exercises helpers,
        not production. Also legitimate, and also no finding — but distinct
        from NO_CALLS, because a seal in this state is one refactor away from
        being the vacuous kind and a report that folded the two together could
        not show that trend.
    UNNAMEABLE
        At least one call target could not be named: a call through a value, a
        ``getattr``, a table of functions. **This is an ABSTENTION and the seal
        is reported**, because the unnameable target may be the very production
        symbol the seal exists to cover, and a seal we could not read is not a
        seal we checked.

    Every dispatch over this enum must be exhaustive and RAISE on an unknown
    member.
    """

    NO_CALLS = "no_calls"
    ALL_TARGETS_IN_TESTS = "all_targets_in_tests"
    UNNAMEABLE = "unnameable"


@dataclass(frozen=True)
class Seal:
    """One test function, and where it lives.

    ``symbol`` is the test function itself, which is also a :class:`Root` of
    kind ``TEST_FUNCTION``. The same object wearing two hats is deliberate: the
    seal is both the thing whose claim is under examination and the test root
    that trivially reaches its own subject, and keeping one identity for it is
    what makes the ``FROM_NEITHER`` self-check in :func:`check_subject` sound.
    """

    symbol: Symbol
    #: The pytest node id or the Go ``package.TestName``, so a finding names a
    #: row a human can run. Not derived at report time: the spelling differs by
    #: language and a report that guessed it would send people to nothing.
    test_id: str


def discover_seals(graph: CallGraph, roots: Sequence[Root]) -> tuple[Seal, ...]:
    """Every test function in the tree, from the roots already derived.

    Derived from ``roots`` rather than re-swept, so there is one answer site
    for "what is a test entrypoint" and it is :func:`discover_roots` calling
    ``seal_verify.is_test_path`` and the analyzer's ``test_root_predicate``.
    A second sweep here would be a second notion of "is this a test", which is
    invariant 5's failure mode and which was live in this repo once already.

    CHOICE (the brief says a seal names a subject, and is silent on whether
    anything else does): **the subject population is seal-derived and nothing
    else.** Every finding in this module is about a function some seal claims
    to cover. Rejected alternative: sweeping every declared symbol in the tree
    and reporting all of them that no root reaches — which is dead-code
    detection, is a strictly larger set, and would bury the B1 shape in it. The
    two are genuinely different findings: dead code is a tidiness problem, and
    *a seal certifying dead code* is a false green in a gate, which is what
    this effort is about. The cost is limit 8, and the trigger for widening is
    a measured case where a dark function nobody sealed caused an incident.
    """
    raise NotImplementedError(
        "discover_seals: no seal derivation is written. It reads the "
        "TEST_FUNCTION roots that discover_roots produces, and that raises"
    )


@dataclass(frozen=True)
class Subject:
    """What one seal claims to cover, and how that was decided."""

    seal: Seal
    #: The symbols the seal calls that are declared in NON-test files. May be
    #: empty, in which case ``gap`` says why.
    symbols: tuple[Symbol, ...]
    #: ``None`` exactly when ``symbols`` is non-empty; a :class:`SubjectGap`
    #: member exactly when it is empty. Both contradictions — a gap alongside
    #: symbols, an empty set with no gap — are
    #: :class:`CallSiteReachabilityError` at :func:`check_subject`, because a
    #: subject record that says two things or says nothing is a non-judgement
    #: and a non-judgement must not read as an answer. D3's :class:`Witness`
    #: contract, unchanged.
    gap: SubjectGap | None
    #: The same reason IN PROSE, FOR A HUMAN, and for nothing else. **No
    #: decision anywhere in this module reads it**, so improving a message can
    #: never move a verdict. A body that discriminates on it should redden.
    detail: str


def subjects_of_seal(seal: Seal, graph: CallGraph) -> Subject:
    """What ``seal`` claims to cover. The answer to the brief's question 1.

    **The subject of a seal is the set of NON-TEST symbols its own body CALLS
    DIRECTLY.** Not what it imports, not what it declares, not what it
    transitively reaches.

    CHOICE (the brief asks precisely this and offers three candidates):

      * **Rejected — by the symbol it IMPORTS.** It fails outright on the case
        that motivated the unit. ``ResolveConfigDual`` and
        ``TestSeal_ResolveConfigDual`` are both in ``package main`` in
        ``cmd/classify``; there is no import, and an import-based reader
        reports ZERO subjects for the exact defect. It also over-reports in
        Python, where ``import claude_dispatcher.risk`` names a module and not
        a claim.
      * **Rejected — by a declaration.** An annotation on 1811 rows is a
        migration nobody finishes and a rubber stamp where they do; D3 refuses
        the same thing for the same reason and records that a mechanism resting
        on one "would record permission rather than protection". It also cannot
        be validated: a seal declaring the wrong subject is green.
      * **Accepted — by what it calls.** Derivable from the same edge
        extraction the traversal already needs, so it is one mechanism and not
        two; it is a fact about the seal rather than a claim by it; and it
        degrades honestly, because a call the analyzer cannot name becomes
        :attr:`SubjectGap.UNNAMEABLE` rather than silence.

    Three boundary rules a body must implement and a seal can pin:

      * **DIRECT calls only, from the seal's own body** — including nested
        closures, table-driven subtest bodies, and ``t.Run`` literals declared
        inside it, since those are the seal's own text. Not transitive:
        transitive would make every helper a subject, and a report where every
        seal has forty subjects is a report nobody reads.
      * **Targets declared in test files are excluded**, by
        ``seal_verify.is_test_path`` over ``Symbol.path``. A seal calling a test
        helper has not made the helper a subject. When that leaves the set
        empty, the gap is :attr:`SubjectGap.ALL_TARGETS_IN_TESTS` — and NOT
        :attr:`SubjectGap.NO_CALLS`, which is the distinction the two members
        exist for.

        The rule is deliberately one hop and does not chase what the helper
        calls. A body author will be tempted to, because a seal that calls
        ``exerciseTheThing(t)`` clearly does have a subject; the answer is that
        chasing it re-opens the transitivity this rule closes and the honest
        middle does not exist. Recorded as a known under-report rather than
        patched: it makes some seals contribute no finding, which is the safe
        direction, and the trigger for revisiting is a measured case where a
        real B1-shaped defect hid behind exactly one test helper.
      * **A seal whose subject cannot be identified is an ABSTENTION, never a
        pass.** :attr:`SubjectGap.UNNAMEABLE` yields
        :attr:`Reach.UNDECIDED` / :attr:`UndecidedReason.SUBJECT_UNIDENTIFIED`
        at :func:`check_subject`, is counted, and is not suppressible. The
        brief names this explicitly and it is the shape of every false green in
        this effort: the checker did not look and the report said fine.
    """
    raise NotImplementedError(
        "subjects_of_seal: no subject extraction is written. It reads the "
        "edges out of a CallGraph and build_call_graph raises"
    )


# --------------------------------------------------------------------------- #
# Part 5 — the two axes and the ruling
# --------------------------------------------------------------------------- #


class Reach(Enum):
    """From what roots is the subject reached? Four states, exhaustively.

    The answer to the brief's question 4. Four, matching D3's
    :class:`Reachability`, and the correspondence is close enough to be worth
    reading across: ``FROM_PRODUCTION`` is ``REACHED``, ``UNDECIDED`` is
    ``NO_STRATEGY``, and ``FROM_TESTS_ONLY`` is the state D3 has no analogue
    for because its defect had no analogue.

    FROM_PRODUCTION
        A path exists from at least one :attr:`RootKind.PRODUCTION` root. How
        good the path is, is the OTHER axis (:class:`PathQuality`) and must be
        read with it: this member alone is not a pass.
    FROM_TESTS_ONLY
        A path exists from a :attr:`RootKind.TEST` root and from no production
        root. **This is the B1 defect and it is spelled like neither of its
        neighbours**, which the brief requires and which is the whole reason
        the enum has four members rather than a boolean. Calling it "reached"
        certifies the defect; calling it "unreachable" is false — the function
        runs, 27 times, under ``go test`` — and would send a human to delete
        code that a seal is depending on.
    FROM_NEITHER
        No path from any root. **Impossible for a seal-derived subject**, since
        the seal that named the subject is itself a TEST root with a direct
        edge to it, so producing this member means the traversal lost an edge
        it was handed. :func:`check_subject` therefore RAISES
        :class:`CallSiteReachabilityError` on it rather than reporting it.

        It is a member anyway, and not merely tolerated: the raise IS the
        exhaustive treatment, and a state that can only arrive through a
        mechanism bug must be nameable so the bug can be reported as a bug.
        Folding it into ``FROM_TESTS_ONLY`` would turn a lost edge into a
        BREACH against innocent code — an over-call, arriving through the
        mechanism's own defect, which is the worst way for a gate to be wrong.
    UNDECIDED
        The mechanism did not judge. An ABSTENTION, carrying an
        :class:`UndecidedReason`. It is not a pass, it may not be declared
        away, and its count is this module's own coverage figure. D3's
        ``NO_STRATEGY`` contract, unchanged, including the sentence that
        matters most: a check that let this resolve to the reached value would
        be a gate reporting a judgement it never made, on the very defect class
        it exists to close.

    Every dispatch over this enum must be exhaustive and RAISE on an unknown
    member. Adding a fifth state without visiting every dispatch is how the
    permissive value gets a new spelling.
    """

    FROM_PRODUCTION = "from_production"
    FROM_TESTS_ONLY = "from_tests_only"
    FROM_NEITHER = "from_neither"
    UNDECIDED = "undecided"


class UndecidedReason(Enum):
    """Why :attr:`Reach.UNDECIDED`, as DATA. Six states, exhaustively.

    D3's :class:`WitnessGap`, widened. Data and not prose for D3's stated
    reason, which is worth repeating because it is the reason this enum is not
    just a string: a reworded error message must not be able to move a verdict,
    and here the flip that matters runs from ``DYNAMIC_EDGE`` (an abstention)
    to ``FROM_TESTS_ONLY`` (a BREACH) and back — in both directions a
    prose-driven flip would be a verdict change with no code change and nothing
    red.

    UNSUPPORTED_LANGUAGE
        :func:`analyzer_for_path` returned None for a file that matters. A
        permanent fact about the gate, not about the machine.
    ANALYZER_FAULT
        An :class:`AnalyzerFault`. A fact about the machine, not about the
        gate. The two are separate members for ``ComparatorFault``'s own
        recorded reason: conflating them is a live fail-open, because a broken
        CI image would otherwise read as "no Go here" for as long as it stayed
        broken.
    PARSE_FAILED
        A :class:`SourceUnreadable`. The gate opened the file and the file is
        bad. Abstains over the whole tree; see that class.
    NO_ENTRYPOINT
        Zero production roots of any :class:`EntrypointKind` in the tree. A
        library, or a tree whose starter this mechanism cannot see (limit 1).
        Never "everything is reachable" and never "nothing is".
    SUBJECT_UNIDENTIFIED
        :attr:`SubjectGap.UNNAMEABLE`. The seal calls something the analyzer
        could not name, and the unnameable target may be the subject.
    DYNAMIC_EDGE
        A "no path" answer that is not conclusive: either the analyzer's
        language row says ``negative_is_conclusive`` is False, or the
        production closure contains at least one entry in
        :attr:`CallGraph.unresolved_calls`. **This member may only ever
        DOWNGRADE a would-be** :attr:`Reach.FROM_TESTS_ONLY` **or**
        :attr:`Reach.FROM_NEITHER`. It may never touch
        :attr:`Reach.FROM_PRODUCTION`: a path that was found is still found,
        and failing to look can only make an answer less conclusive, never
        manufacture the permissive one. That sentence is anti-requirement 2 and
        it is enforced by the order of the dispatch in :func:`check_subject`.

    Every dispatch over this enum must be exhaustive and RAISE on an unknown
    member.

    CHOICE (the design does not say how widely ``DYNAMIC_EDGE`` applies, and
    the naive reading kills the mechanism): the unresolved-call count is taken
    over the **production closure only** — the symbols actually reached from
    production roots — and not over the whole graph. Rejected alternative:
    any unresolved call anywhere abstains, which is defensible, is what a
    soundness purist would write, and would make every real repository abstain
    on every subject forever. A mechanism that always abstains is a mechanism
    that is never consulted, and an unrun check is this repo's most expensive
    recorded failure ("a mutation gate that had never run reported success for
    months"). The residual risk is named and is real: an unresolved call
    OUTSIDE the production closure cannot pull a symbol into it, but an
    unresolved call outside a closure that is itself under-computed can — which
    is why the count is a first-class report field rather than an internal.
    """

    UNSUPPORTED_LANGUAGE = "unsupported_language"
    ANALYZER_FAULT = "analyzer_fault"
    PARSE_FAILED = "parse_failed"
    NO_ENTRYPOINT = "no_entrypoint"
    SUBJECT_UNIDENTIFIED = "subject_unidentified"
    DYNAMIC_EDGE = "dynamic_edge"


class PathQuality(Enum):
    """How good is the path? Three states, exhaustively.

    The second axis, separate from :class:`Reach` on purpose and for D3's exact
    reason: one enum answers whether production reaches the subject, the other
    answers how much the answer is worth. Collapsing them into one
    six-valued status was the first draft and it made every report ambiguous
    about which half was weak — the same mistake as a gate that reports
    ``skipped`` with no reason.

    RESOLVED
        Every edge on the witness path is :attr:`EdgeKind.DIRECT` or
        :attr:`EdgeKind.METHOD`. The strong pass. Production calls this.
    OVER_APPROXIMATED
        At least one edge is :attr:`EdgeKind.INTERFACE` or
        :attr:`EdgeKind.REFERENCE`. The path may not exist at runtime: an
        interface edge was resolved to a set of possible implementations, or a
        symbol was passed as a value that nothing may ever invoke. **This is
        the one place this module can be permissively wrong**, and it must be
        visible rather than folded into RESOLVED — a mechanism that spells its
        strong answer and its weak answer the same way has thrown away the
        distinction it spent an analyzer computing.
    NOT_APPLICABLE
        There is no path, or none was computed: every :attr:`Reach.UNDECIDED`,
        :attr:`Reach.FROM_TESTS_ONLY` and :attr:`Reach.FROM_NEITHER` finding.
        Named rather than left as ``None``, so a report can never show a blank
        where a quality should be and have it read as strength. D3's
        ``NOT_MEASURED``, same argument.
    """

    RESOLVED = "resolved"
    OVER_APPROXIMATED = "over_approximated"
    NOT_APPLICABLE = "not_applicable"


@dataclass(frozen=True)
class CallPath:
    """The evidence behind one :attr:`Reach.FROM_PRODUCTION` answer.

    ``root``
        Which root it starts at, so a reader can ask "does that program
        actually ship".
    ``edges``
        Root to subject, in order. The chain a human follows to check the
        claim. A finding that asserts reachability without one is a finding
        nobody can falsify, and unfalsifiable green is the thing this effort is
        about.
    ``quality``
        The :class:`PathQuality` of THIS chain, which is the minimum over its
        edges: one over-approximated edge makes the whole chain
        over-approximated, because a chain is only as certain as its weakest
        link.
    """

    root: Root
    edges: tuple[Edge, ...]
    quality: PathQuality


@dataclass(frozen=True)
class Finding:
    """One judged (seal, subject symbol) pair: the two axes and the evidence.

    ``reason`` is non-None exactly when ``reach`` is
    :attr:`Reach.UNDECIDED`, and ``path`` is non-None exactly when ``reach`` is
    :attr:`Reach.FROM_PRODUCTION`. Both contradictions are
    :class:`CallSiteReachabilityError` at :func:`adjudicate` rather than
    tolerated fields: a finding that carries a path AND an undecided reason has
    two answers, and a report showing both would be read as whichever one the
    reader wanted.

    ``test_path`` is the chain from the TEST root, present for every finding
    including the passing ones. It is what makes a BREACH actionable — it says
    which seal is resting on the claim — and it is present on OK findings too
    so that the report can answer "which seals cover this" without a second
    traversal.
    """

    seal: Seal
    subject: Symbol
    reach: Reach
    quality: PathQuality
    path: CallPath | None
    test_path: CallPath | None
    reason: UndecidedReason | None
    detail: str


def check_subject(
    seal: Seal,
    subject: Symbol,
    *,
    graph: CallGraph,
    production_reach: Mapping[str, tuple[Edge, ...]],
    test_reach: Mapping[str, tuple[Edge, ...]],
    analyzer: ReachabilityAnalyzer,
) -> Finding:
    """Judge one (seal, subject) pair. The single answer site for one subject.

    The composition, in order, and a body must NOT reorder it — the order is
    what enforces anti-requirement 2, because every abstention check that could
    hide a found path is placed AFTER the found-path check:

      1. **``subject.key in production_reach`` -> FROM_PRODUCTION**, with the
         chain's quality. Checked FIRST, before any abstention. A path that was
         found is found; no amount of unresolved calls elsewhere in the tree can
         un-find it, and putting an abstention check ahead of this would let
         "we could not see everything" suppress a real pass.
      2. **Zero production roots -> UNDECIDED / NO_ENTRYPOINT.** Before the
         tests-only check, because with no production root the tests-only
         answer is arithmetically guaranteed and would be a BREACH against
         every subject in a library.
      3. **``analyzer.negative_is_conclusive`` is False, or the production
         closure holds unresolved calls -> UNDECIDED / DYNAMIC_EDGE.** The
         second half is counted over the production closure only; see the
         CHOICE on :class:`UndecidedReason`.
      4. **``subject.key in test_reach`` -> FROM_TESTS_ONLY.** The B1 verdict,
         reached only when every abstention above has been ruled out.
      5. **Otherwise FROM_NEITHER**, which for a seal-derived subject is
         impossible and RAISES :class:`CallSiteReachabilityError`. The seal has
         a direct edge to its own subject by the definition of "subject", so
         reaching this line means the traversal lost an edge it was handed, and
         a mechanism that lost an edge must say so rather than convert its own
         bug into a finding against the code.

    ``analyzer`` is the row for the SUBJECT's language, resolved by
    :func:`analyzer_for_path` over ``subject.path``. Per-subject and not
    per-tree: a Python seal covering a Go symbol — which nothing does today and
    which the contract must still answer — takes Go's conclusiveness rule,
    because the claim being made is about the Go symbol's callers.

    Any :class:`CallSiteReachabilityError` propagates and is never converted
    into a finding.
    """
    raise NotImplementedError(
        "check_subject: no judgement is written. It reads two traversals and "
        "reachable_from raises"
    )


@dataclass(frozen=True)
class StagedDeclaration:
    """A human's statement that a subject is deliberately not wired YET.

    The only annotation in the mechanism, and it buys exactly one transition:
    :attr:`Disposition.BREACH` becomes :attr:`Disposition.ACCEPTED`. It cannot
    touch an abstention and it cannot weaken a :attr:`PathQuality`.

    ``test_id`` / ``subject_key``
        Which finding it answers. BOTH must match exactly. A declaration that
        matches nothing is itself reported as stale — a stale declaration is
        how an accepted state outlives the reason for it, and this repo has the
        precedent in ``_DELEGATION_TARGETS``'s stale-row seal.
    ``wiring``
        The commit, ticket or task key that WILL add the call site. The one
        part of a declaration that is not an assertion of good faith, and the
        reason the annotation is tolerable at all: a declaration cannot be
        written without naming a future in which it stops being true.
    ``reason``
        Why the subject is staged. Prose, for a human.

    CHOICE (the design is silent on whether FROM_TESTS_ONLY is appealable, and
    this is the hardest judgement in the module): **it is appealable, by this
    declaration only.**

    The case against — which is strong and should be re-argued if this is ever
    reviewed: D3 made its equivalent finding unappealable, on the reasoning
    that "either the fixture becomes the neighbour, or the producer is fixed;
    there is no third resolution and no annotation". The analogue reads
    cleanly: shipped code nothing calls is dead code, and a seal certifying
    dead code certifies nothing.

    The case for, which won: staged code is real in this repository and has a
    recorded commit ("staged/dark code rated by what it gates, not by what
    imports it today"), and the scaffold-first protocol MANUFACTURES this state
    on purpose — a P1 scaffold is by construction a set of symbols with seals
    and no call sites, so an unappealable BREACH would make the protocol's own
    intermediate state a blocking failure and the first thing anyone did would
    be to switch the check off.

    What makes it tolerable rather than a rubber stamp is what the declaration
    demands of its author: to write ``wiring`` you must state, in a sentence,
    what will call this and when. **A B1 author writing that sentence would
    have discovered the bug in the act of writing it**, because there was no
    such future — the wiring was believed to be already done. That is the whole
    value of the annotation and it is not a small one; it is also, by D3's
    limit 10, exactly as good as the person writing it, and it is where this
    module will first be abused.

    Two things a body must do to keep the abuse visible, both sealable:
    ``ACCEPTED`` is counted separately from ``OK`` in every report, and a
    declaration whose keys match nothing is reported. A growing ``ACCEPTED``
    count is a debt figure and must be legible as one.
    """

    test_id: str
    subject_key: str
    wiring: str
    reason: str


class Disposition(Enum):
    """What the mechanism DOES about one finding. Five states, exhaustively.

    Deliberately the same five as D3's :class:`FindingDisposition`, with the
    same names, because a reader of one report should not have to learn a
    second vocabulary for the sibling.

    OK
        FROM_PRODUCTION with a RESOLVED path. Production calls this, and the
        path is a fact.
    BREACH
        FROM_TESTS_ONLY. **The B1 defect.** The resolution is to add the call
        site, or to withdraw the seal's claim to cover production; a
        :class:`StagedDeclaration` postpones it by naming the future call site
        and does not resolve it.
    REPORT
        FROM_PRODUCTION with an OVER_APPROXIMATED path. Not a failure and not
        a pass: the only path found runs through an interface or a function
        value, so production MAY call this. Printed, counted, left for a human,
        and never folded into OK — the distinction is the entire reason
        :class:`PathQuality` exists as a separate axis.
    ACCEPTED
        FROM_TESTS_ONLY with a matching :class:`StagedDeclaration`. The
        declaration's only power, and this module's only policy rather than
        measurement.
    ABSTAIN
        UNDECIDED, for any :class:`UndecidedReason`. The mechanism did not
        judge. Never suppressible, never declarable, and always counted
        separately from OK: a report that folds abstentions into passes is a
        coverage number that lies, and this repo has already paid for one of
        those.
    """

    OK = "ok"
    BREACH = "breach"
    REPORT = "report"
    ACCEPTED = "accepted"
    ABSTAIN = "abstain"


def adjudicate(
    finding: Finding, declaration: StagedDeclaration | None
) -> Disposition:
    """The one answer site for "what does this finding mean".

    Total over :class:`Reach` x :class:`PathQuality`, RAISING
    :class:`CallSiteReachabilityError` on any pair the grid below does not
    name, so a new member of either enum cannot fall through to the permissive
    answer:

        FROM_PRODUCTION,  RESOLVED           -> OK       / OK
        FROM_PRODUCTION,  OVER_APPROXIMATED  -> REPORT   / REPORT
        FROM_TESTS_ONLY,  NOT_APPLICABLE     -> BREACH   / ACCEPTED
        UNDECIDED,        NOT_APPLICABLE     -> ABSTAIN  / ABSTAIN

    (first column: no declaration; second: a declaration whose two keys match.)

    **Four rows, and the omissions are the specification.** Every pair not
    listed raises, and three of them are worth naming because a body author
    will meet each one:

      * ``FROM_PRODUCTION, NOT_APPLICABLE`` — a path was found and its quality
        was not recorded. That is a mechanism bug and it must not read as OK.
      * ``FROM_TESTS_ONLY`` or ``UNDECIDED`` with any quality other than
        ``NOT_APPLICABLE`` — a quality was recorded for a path that does not
        exist. Same argument, other direction.
      * ``FROM_NEITHER, *`` — impossible for a seal-derived subject and already
        raised at :func:`check_subject`. It is omitted here rather than mapped
        to BREACH so that the two layers cannot disagree about it, and the
        raise IS this enum's exhaustive treatment of the member.

    A declaration changes exactly one cell. It cannot touch ABSTAIN, for D3's
    reason stated verbatim: the count of abstentions is this mechanism's own
    coverage figure, and a declaration that could silence one would be buying
    silence on a measurement that was never taken. It cannot touch REPORT
    either — a human cannot declare an over-approximated path into a resolved
    one, because the weakness is in the analysis and not in the code.

    A declaration whose keys do not match ``finding`` is ignored for the ruling
    AND reported as stale by :func:`check_tree`. Silently ignoring it would let
    a typo look like an accepted state.

    The grid itself is deliberately NOT written out as a module-level table in
    this scaffold. D3's P1 left its ruling in the docstring and P3 wrote the
    table; the same split applies here, so that P4 rules on the grid as prose
    before any body pins it as data.
    """
    raise NotImplementedError(
        "adjudicate: the ruling grid is specified in this docstring and not "
        "yet written as data; P4 rules on it before a body pins it"
    )


# --------------------------------------------------------------------------- #
# Part 6 — the run
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ReachabilityReport:
    """The outcome of one whole check, in the shape a caller must act on.

    ``findings``
        Every judged (seal, subject) pair, in a deterministic order: seal
        ``test_id``, then subject ``key``. Two runs over one tree produce
        byte-identical reports so a diff between them is a real change.
    ``dispositions``
        :class:`Disposition` -> count. **Every member is a key, including the
        zeros.** A report that omits ABSTAIN because there were none is
        indistinguishable from one that omits it because nobody counted, and
        the abstention count is this mechanism's own coverage figure.
    ``roots``
        Every derived :class:`Root`, with its evidence. **THE non-vacuity
        field, and the first thing a reader should look at.** An empty
        production root set makes every subject FROM_TESTS_ONLY, so a report
        that did not carry its root list could turn a broken sweep into a
        repository-wide BREACH flood — or, with the NO_ENTRYPOINT guard in
        :func:`check_subject`, into a repository-wide silent abstention. Both
        are catastrophic and both are invisible without this field. D3's
        ``boundaries_never_observed`` at the other end of the mechanism.
    ``seals_examined``
        How many test functions were found. The second non-vacuity field: zero
        breaches over zero seals is exactly what this module exists to stop
        other people shipping, and it must not be able to ship it itself.
    ``subject_gaps``
        :class:`SubjectGap` -> count, over every seal that yielded no subject.
        All three members are keys, zeros included. A repository where
        ``UNNAMEABLE`` dominates is one where this mechanism is not working,
        and that fact must be readable off the summary rather than derived from
        the findings.
    ``unresolved_call_count``
        Entries in :attr:`CallGraph.unresolved_calls` inside the production
        closure. The quantity that decides whether any "no path" answer was
        conclusive, promoted to the report because a reader must be able to see
        the mechanism's own blindness without opening the graph.
    ``unanalyzed_paths``
        Files no analyzer read, each paired with the reason, as DATA: a
        ``Language`` member means ``support_for_path`` recognised the file and
        :data:`ANALYZERS` has no row for that language (``.ts`` today, and
        ``.py`` and ``.go`` too while the table is empty); ``None`` means no
        ``COMPARATORS`` row matched the extension at all (``.sql``, ``.java``).
        Those are the two situations :func:`analyzer_for_path` deliberately
        collapses into one return value, separated again here because the
        remediations differ — write an analyzer row, versus decide whether the
        language belongs in the gate. "This tree has no Go edges" and "nobody
        looked for Go edges" must not be the same answer, and neither must the
        two ways of not looking.
    ``stale_declarations``
        Declarations that matched no finding. Reported, never silent.

    ``is_clean`` is deliberately absent, exactly as in D3. A caller decides
    what to block on, and a single boolean would have to fold ABSTAIN into one
    side of it.
    """

    findings: tuple[Finding, ...]
    dispositions: Mapping[Disposition, int]
    roots: tuple[Root, ...]
    seals_examined: int
    subject_gaps: Mapping[SubjectGap, int]
    unresolved_call_count: int
    unanalyzed_paths: tuple[tuple[str, Language | None], ...]
    stale_declarations: tuple[StagedDeclaration, ...]


def check_tree(
    tree: Path,
    *,
    declarations: Sequence[StagedDeclaration] = (),
) -> ReachabilityReport:
    """Judge a whole tree and assemble the report. The one entry point.

    The composition, and a body must not reorder it:

      1. :func:`discover_roots` over ``tree``.
      2. :func:`build_call_graph` over ``tree``.
      3. :func:`reachable_from` TWICE — once over the production roots, once
         over the test roots. Two calls, never one labelled traversal; see
         that function for why.
      4. :func:`discover_seals`, then :func:`subjects_of_seal` per seal, then
         :func:`check_subject` per subject.
      5. :func:`adjudicate` per finding, matching declarations by both keys.

    Obligations a body must meet, each of which a seal can pin:

      * **Judge every subject of every seal.** A subject with no finding is a
        silent pass, which is the defect one level up.
      * **A seal that yields no subject is COUNTED, in ``subject_gaps``, and
        produces no finding.** Not an error and not a pass: the seal made no
        claim this module can check.
      * **Populate every count, zeros included**, for both mappings.
      * **Let :class:`CallSiteReachabilityError` propagate.** A partial report
        is not a report; a caller that receives one cannot tell a clean run
        from an aborted one.
      * **Never write into ``tree``.** The analyzer reads; a helper that needs
        a scratch directory gets one outside it, on
        ``fixture_reachability.construct_witness``'s reasoning that a workspace
        inside the tree under check is picked up by the very thing being
        interrogated.

    CHOICE (the design does not say what happens with zero seals): **an empty
    tree returns a report with ``seals_examined=0``, and does NOT raise.** Zero
    seals is a true fact about a tree and this function's job is to report
    facts. Rejected alternative: raising, which is tempting because a
    zero-seal report is worthless — but the caller is the right place to decide
    that, the field is there for it to decide with, and a mechanism that raises
    on an empty input cannot be run over a subtree during development. What is
    NOT acceptable is the third option: returning a report that looks clean. It
    does not; ``seals_examined`` is on the face of it.
    """
    raise NotImplementedError(
        "check_tree: no run is written. Every stage it composes raises, "
        "starting with discover_roots"
    )
