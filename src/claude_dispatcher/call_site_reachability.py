r"""D5 — call-site reachability: does production call this?

The scaffold that wrote these contracts left every function raising
:class:`NotImplementedError` except the two named at their definitions
(:func:`validate_analyzers`, :func:`analyzer_for_path`) and the reason each was
an exception is written there. **The bodies landed on ``feat/D5-body``,
2026-08-11: nothing here raises :class:`NotImplementedError` any more.** The
docstrings remain the specification and the P4 rulings inside them remain
binding; a body author who finds one vague should get a ruling rather than
guess, because the last four units each had a seal author derive a ruling from
prose and a P4 adjudicate the guess. Where a body could not obey a contract as
literally written, it says so at the site and does not quietly re-scope it.
There are three such places and each names what it could not do and what would
close it: :func:`_test_id` (the protocol carries no channel for a spelling the
contract forbids deriving), the ``roots`` parameter of :func:`check_subject`
(the signature cannot build a faithful :attr:`CallPath.root`), and
:func:`adjudicate`, where :class:`Finding`'s consistency rule and two seals are
incompatible and the seals win. **All three are escalations, not rulings.**

**Still NOT ENROLLED.** :data:`ANALYZERS` is empty, no call site was added, and
``role_protocol`` was not touched: the ``FLOOR_GLOBS`` round the WIRING section
below raises for P4 is due BEFORE enrolment, because implementing the ruling
grid makes this module a gate whose decisions can be dissolved by editing it.

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
  * **Every call to it is from a ``_test.go`` file.** Counted at ``929d362``,
    re-measured by P4 2026-08-11: **31** occurrences of the identifier across
    ``*_test.go`` (11 in ``contract_seal_test.go``, 20 in
    ``repair_seal_test.go``), of which **12** are call expressions; **0** in
    non-test source outside its own doc comment and its own ``func`` line.
    The scaffold first recorded ``27``, which is neither figure; see the P4
    RULING on measurements below.
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
lines, within ``cmd/classify`` only) does find it, alongside six others.
Re-measured by P4 at ``929d362``, 2026-08-11 — the ``test=`` column of the
scaffold's first draft was understated in **every one of the seven rows** and
is corrected here::

    DesugarConfigScaffold  prod=0 test=7     ProjectPanelToV1   prod=0 test=9
    EmitterCovers          prod=0 test=10    ResolveConfigDual  prod=0 test=31
    GenerateReadSet        prod=0 test=28    SemanticEquivalentV1 prod=0 test=22
                                             SidecarSurvives    prod=0 test=15

``test=`` counts occurrences of the identifier in every ``*_test.go`` under
``cmd/classify``; ``prod=`` is the refined scan above. Both are reproducible
from the recorded revision, which is the property the first draft's numbers
lacked and the reason a P4 rather than a body corrected them.

That scan is recorded here as an ORDER OF MAGNITUDE and explicitly not as a
finding, for a reason that is this module's whole subject: it counts MENTIONS,
so it cannot tell a mention inside live code from a mention inside a function
that is itself dead. ``V2SidecarPath`` scores ``prod=3`` and a grep cannot say
whether any of those three lines runs. Transitive reachability from an
entrypoint is the question, and a grep is a one-hop approximation of it.

P4 RULING on the two measurements in this module (2026-08-11), because the
question "should a row pin this?" was raised and the answer is not the same for
both. **Neither is pinned by a row, and the reasons differ.**

  * The ``cmd/classify`` figures above are over a VENDORED, FROZEN artifact
    (``tests/fixtures/d5_b1_classify/``). A row asserting a count over frozen
    text can never redden, which is "a recording that measures a frozen
    artifact" — one of the five non-vacuity hazards the seal file enumerates
    against itself. What a row must pin about that fixture is what makes it the
    right FIXTURE (the doc-comment shortcut, the absent import, the two
    production occurrences), and
    ``test_the_canonical_fixture_is_the_measured_artifact`` already does.
  * The ``getattr`` figure below is over the LIVE ``src/`` tree, where an exact
    count reddens on every unrelated commit that adds a ``getattr``. That is a
    row that cries wolf and is deleted, taking the real claim with it. What a
    row must pin there is the PREMISE of the Python language row — that this
    repository really does resolve names dynamically — and
    ``test_the_python_row_is_false_because_this_repo_resolves_names_dynamically``
    already does, as an invariant with the counts recorded beside it.

The obligation the ruling puts on a body instead: every count in this docstring
carries the revision and the date it was taken at, so that a number without a
provenance is visibly a number nobody can check.

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
     Measured by AST over ``src/`` on this worktree, re-measured by P4
     2026-08-11: **105** ``getattr(`` call sites, **four** of them with a
     non-literal attribute name, **three** of those four
     inside ``fixture_reachability`` itself — which resolves ARBITRARY
     fully-qualified names out of a table (``_resolve_dotted``, line 847) and
     is D5's own sibling. The scaffold first recorded 100 / six / three; the
     claim's shape survived and its arithmetic did not. **The fourth
     non-literal site is inside THIS module**, and it carries a ruling of its
     own — see :attr:`ReachabilityAnalyzer.negative_is_conclusive`.
     A Python-first mechanism would therefore have baked
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

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Mapping, Protocol, Sequence

from .role_protocol import COMPARATORS, Language, support_for_path
from .seal_verify import is_test_path

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
    root, a malformed :class:`Subject`, or an :class:`AnalyzerError` that is
    not :class:`SourceUnreadable`.

    **P4 RULING (2026-08-11), on R4: "a report assembled over zero roots" is
    struck from that list.** It contradicted the CHOICE on :func:`check_tree`
    ("an empty tree returns a report with ``seals_examined=0``, and does NOT
    raise"), and an empty tree has zero roots, so the two could not both stand.
    The CHOICE wins, for two reasons that are the module's own:

      * **Zero roots already has a first-class answer.** Zero PRODUCTION roots
        is :attr:`UndecidedReason.NO_ENTRYPOINT`, a named abstention over the
        whole tree. A raise for the same condition would be a second layer with
        its own answer for one state, which is precisely what the
        :attr:`Reach.FROM_NEITHER` treatment refuses ("omitted here rather than
        mapped ... so that the two layers cannot disagree about it").
      * **The raise would make the non-vacuity field unreachable.**
        :attr:`ReachabilityReport.roots` is contracted as THE field a reader
        looks at first, existing so that an empty root set is VISIBLE. A
        mechanism that raises rather than shipping an empty root list can never
        show one, and the field's stated purpose is dead.

    A report over zero roots is therefore returned, and it is legible as
    vacuous on its face: ``roots=()``, ``seals_examined=0``, ``findings=()``,
    every :class:`Disposition` present as a key and summing to zero.

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

    **P4 RULING (2026-08-11), on the contradiction the seal author raised as
    R1.** The scaffold said every member here maps to an
    ``UndecidedReason.ANALYZER_FAULT`` abstention, while the only two functions
    that run an analyzer — :func:`discover_roots` and :func:`build_call_graph`
    — both RAISE on :class:`AnalyzerError`. Both could not be true.

    **The raises are right and the abstention is UNBUILDABLE, so
    ``UndecidedReason.ANALYZER_FAULT`` is struck.** A fault is carried on the
    raised :class:`AnalyzerUnavailable` and reaches the caller as a
    :class:`CallSiteReachabilityError`; no member here maps to a finding.

    The reason is not a preference between two workable designs. An abstention
    is a statement ABOUT A SUBJECT, and both faulting sites are upstream of the
    subject population: a fault in :func:`discover_roots` leaves no roots,
    therefore no seals, therefore no subjects to abstain over, and a report
    that abstains over zero subjects is a report of zero findings — which is
    the exact artifact this module exists to stop anyone shipping. **An
    abstention you cannot enumerate is not an abstention; it is silence with a
    label on it.** The raise is the honest form of the same refusal: it is not
    a pass, it is not a silent skip, and :class:`CallSiteReachabilityError`
    already contracts that a caller may not catch it and continue.

    What the ruling costs, stated so it is a decision: in a tree with two
    analyzer rows, one faulting toolchain takes down the judgement of the
    healthy language too. That binds nothing today (:data:`ANALYZERS` is empty,
    and the first row will be Go alone) and it is recorded rather than
    engineered around. The trigger for revisiting: the first tree with two
    analyzer rows in which one language's toolchain is routinely absent — at
    which point the member comes back, but it comes back attached to a layer
    that KNOWS the subject population, which neither of these two is.

    That is also the difference from ``ComparatorFault``, which maps to
    statuses of several kinds: D5 has exactly one honest thing to say when its
    analyzer did not run, and it says it by refusing to answer.

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
        and ``importlib.import_module(computed)`` are routine, measured **4**
        times in ``src/`` on 2026-08-11, three of them inside D3.

        **P4 RULING (2026-08-11): the fourth is in this module, inside
        :func:`validate_analyzers`, and it is not merely consistent with
        Python's ``False`` — the mechanism owes a statement about judging
        itself, so here it is.**

        BODY CORRECTION (``feat/D5-body``, 2026-08-11), under R6's obligation
        that every count here carry the revision and date it was taken at: the
        ruling records that site as ``line 726`` and it is not, and was not at
        ``094fffb`` either — the ruling's own edits had already moved it. Fresh
        AST measurement over ``src/`` on this branch, 2026-08-11: **105**
        ``getattr(`` call sites, **4** with a non-literal attribute name, at
        ``fixture_reachability.py`` 871 / 1118 / 1647 and
        ``call_site_reachability.py`` **865**. The arithmetic P4 corrected
        survives unchanged; only the line number moved, which is exactly why R6
        refuses to pin either figure with a row and asks for provenance instead.

        ``validate_analyzers`` resolves its three required method names out of
        a loop variable (``getattr(row, method, None)``). That is an
        unresolvable call, it is in this package, and this package's production
        closure contains it: ``role_protocol.py`` calls ``validate_registry``
        at module level and this module calls ``validate_analyzers(ANALYZERS)``
        at module level, both of which are
        :attr:`EntrypointKind.PYTHON_IMPORT_TIME` roots. So if a Python
        analyzer row is ever written and D5 is run over ``claude-workflow``,
        its own ``getattr`` lands in :attr:`CallGraph.unresolved_calls` INSIDE
        the production closure, and step 3 of :func:`check_subject` downgrades
        every Python subject in the repository to
        :attr:`UndecidedReason.DYNAMIC_EDGE` — by the closure rule, quite
        independently of what this row's boolean says.

        Three consequences a body must not lose:

          1. **D5 cannot emit a BREACH against Python code in THIS repository,
             and flipping this row to ``True`` would not buy one.** The belt
             (the per-language row) and the braces (the per-closure unresolved
             count) are independent, which is exactly the property the CHOICE
             below was reaching for when it refused a computed row: a branch
             cannot turn abstentions into BREACHes by editing the row alone,
             any more than it can turn BREACHes into abstentions by adding one
             ``getattr``.
          2. **D5 run over itself must ABSTAIN over its own Python subjects,
             and that is the correct answer, not a defect to be engineered
             around.** A mechanism whose thesis is that failing to look is not
             a pass does not get to make an exception for its own reflection.
             A body that special-cases this module's own ``getattr`` to buy
             itself a verdict has written the fail-open this module exists to
             refuse, one level up.
          3. **The measurement is load-bearing and is sealed as an invariant**,
             not as a count: the row
             ``test_the_python_row_is_false_because_this_repo_resolves_names_dynamically``
             asserts that ``call_site_reachability.py`` is still among the
             dynamic resolvers. If that stops being true the premise above has
             moved and both this paragraph and Python's ``False`` need
             re-arguing — which is the point of pinning it.

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
    roots: list[Root] = []
    for analyzer in _analyzers_present(tree)[0]:
        try:
            produced = analyzer.roots(tree)
        except AnalyzerError as exc:
            raise CallSiteReachabilityError(
                f"the {_language_of(analyzer)!r} analyzer could not derive "
                f"roots for {tree}; a partial root set is worse than none, "
                "because the roots that failed to appear are exactly the ones "
                f"whose absence manufactures BREACHes: {exc}"
            ) from exc
        for root in produced:
            _validate_root(root)
            roots.append(root)
    return tuple(roots)


#: Which :class:`RootKind` each :class:`EntrypointKind` yields. A TABLE and not
#: a chain of ``if``\ s, so that a member added without visiting this file is
#: absent from it and :func:`_validate_root` raises rather than defaulting — the
#: step 3 of ``skills/explicit-state.md`` that actually bites. ``TEST_FUNCTION``
#: is the only kind on the TEST side, which is what makes the test half of
#: :func:`_synthetic_root` a derivation rather than a guess.
_ROOT_KIND_BY_ENTRYPOINT: Mapping[EntrypointKind, RootKind] = {
    EntrypointKind.GO_MAIN: RootKind.PRODUCTION,
    EntrypointKind.GO_INIT: RootKind.PRODUCTION,
    EntrypointKind.GO_PACKAGE_VAR: RootKind.PRODUCTION,
    EntrypointKind.PYTHON_CONSOLE_SCRIPT: RootKind.PRODUCTION,
    EntrypointKind.PYTHON_MODULE_MAIN: RootKind.PRODUCTION,
    EntrypointKind.PYTHON_SCRIPT_MAIN: RootKind.PRODUCTION,
    EntrypointKind.PYTHON_IMPORT_TIME: RootKind.PRODUCTION,
    EntrypointKind.TEST_FUNCTION: RootKind.TEST,
}


def _language_of(analyzer: ReachabilityAnalyzer) -> str:
    language = analyzer.language
    return language.value if isinstance(language, Language) else repr(language)


def _validate_root(root: Root) -> None:
    """Refuse a root whose ``root_kind`` the analyzer asserted rather than earned.

    :class:`Root` contracts ``root_kind`` as DERIVED from ``kind`` and from
    ``seal_verify.is_test_path`` over the declaring file, so a row cannot mark
    its own roots production. Three refusals, and each is a raise rather than a
    coin flip because both wrong answers are intolerable: a test root read as
    production silently certifies everything below it, and a production root
    read as test floods the report with false BREACHes.
    """
    if not isinstance(root, Root):
        raise CallSiteReachabilityError(
            f"an analyzer produced {root!r}, which is not a Root"
        )
    expected = _ROOT_KIND_BY_ENTRYPOINT.get(root.kind)
    if expected is None:
        raise CallSiteReachabilityError(
            f"root {root.symbol.key!r} carries entrypoint kind {root.kind!r}, "
            "which this module cannot classify; a root whose kind cannot be "
            "decided is not a root"
        )
    in_test_file = is_test_path(root.symbol.path)
    if root.kind is EntrypointKind.TEST_FUNCTION and not in_test_file:
        raise CallSiteReachabilityError(
            f"root {root.symbol.key!r} is a TEST_FUNCTION declared in "
            f"{root.symbol.path!r}, which is not one of the tests; two "
            "disagreeing notions of 'is this a test file' is the failure D5 "
            "refuses to open"
        )
    if root.kind is not EntrypointKind.TEST_FUNCTION and in_test_file:
        raise CallSiteReachabilityError(
            f"root {root.symbol.key!r} is a production entrypoint "
            f"({root.kind.value}) declared in the test file "
            f"{root.symbol.path!r}; that is a tree this module does not "
            "understand, and saying so is cheaper than being wrong in either "
            "direction"
        )
    if root.root_kind is not expected:
        raise CallSiteReachabilityError(
            f"root {root.symbol.key!r} declares root_kind "
            f"{root.root_kind!r} while its kind {root.kind.value!r} derives "
            f"{expected!r}; root_kind is derived, never asserted by the row"
        )


def _analyzers_present(
    tree: Path,
) -> tuple[tuple[ReachabilityAnalyzer, ...], tuple[tuple[str, Language | None], ...]]:
    """Sweep ``tree`` once: which analyzers it needs, and what nobody can read.

    The one file sweep in this module, shared by :func:`discover_roots`,
    :func:`build_call_graph` and :func:`check_tree` so that the three cannot
    disagree about which files exist. Every path is offered to
    :func:`analyzer_for_path` — this module never looks at an extension itself —
    and a path no analyzer claims is RECORDED with its reason as DATA, because
    "this tree has no Go edges" and "nobody looked for Go edges" must not be the
    same answer, and neither must the two ways of not looking.

    Paths are repository-relative posix, the spelling :class:`Symbol` uses, so
    a reader can join a report's ``unanalyzed_paths`` to its findings.
    """
    if not tree.is_dir():
        raise CallSiteReachabilityError(
            f"{tree} is not a directory, so there is no tree to sweep; a "
            "mechanism that returned an empty root set here would report every "
            "subject in a missing tree as unreached"
        )
    languages: set[Language] = set()
    unanalyzed: list[tuple[str, Language | None]] = []
    for path in sorted(tree.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(tree).as_posix()
        analyzer = analyzer_for_path(relative)
        if analyzer is None:
            support = support_for_path(relative)
            unanalyzed.append(
                (relative, support.language if support is not None else None)
            )
            continue
        languages.add(analyzer.language)
    selected = tuple(row for row in ANALYZERS if row.language in languages)
    return selected, tuple(unanalyzed)


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
    report every refactor as a mass unreachability event.

    **P4 FIX (2026-08-11), and it is a production change made rather than
    handed on.** The scaffold declared this identity in prose and then left a
    plain ``@dataclass(frozen=True)``, whose generated ``__eq__`` and
    ``__hash__`` compare all three fields — so a symbol that moved file WAS a
    different symbol, and the class contradicted its own docstring. That is a
    defect in the scaffold, not a task for a body: the contract was already
    written, the fix is declarative, and this class is used as a dict key and a
    set member by the seals themselves and by every traversal below, so a body
    written against the wrong semantics would be wrong everywhere at once.
    ``field(compare=False)`` excludes both fields from ``__eq__`` and from the
    generated ``__hash__``, so identity is over ``key`` alone.
    ``test_symbol_equality_and_hashing_are_over_the_key_alone`` was red for this
    defect and is green because the defect is gone — not because the row moved.
    """

    key: str
    path: str = field(compare=False)
    line: int = field(compare=False)


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


#: The two edge kinds that resolve to exactly ONE declaration, and the two that
#: do not. Written as two tables whose UNION must cover the enum rather than as
#: ``kind in (INTERFACE, REFERENCE)``, so that a fifth member added without
#: visiting this file is in neither and :func:`_edge_is_resolved` raises. A
#: default on this predicate would decide, silently and for the whole
#: repository, whether an unmarked over-approximation reads as the strong pass.
_RESOLVED_EDGE_KINDS = frozenset({EdgeKind.DIRECT, EdgeKind.METHOD})
_OVER_APPROXIMATING_EDGE_KINDS = frozenset({EdgeKind.INTERFACE, EdgeKind.REFERENCE})


def _edge_is_resolved(kind: EdgeKind) -> bool:
    """Is this edge a fact about one declaration, or a possibility over a set?"""
    if kind in _RESOLVED_EDGE_KINDS:
        return True
    if kind in _OVER_APPROXIMATING_EDGE_KINDS:
        return False
    raise CallSiteReachabilityError(
        f"edge kind {kind!r} is in neither strength class; a kind added "
        "without visiting this dispatch would decide by default whether an "
        "over-approximated path is spelled like a resolved one"
    )


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
    symbols: dict[str, Symbol] = {}
    edges: list[Edge] = []
    unresolved: list[tuple[Symbol, str, str]] = []
    unreadable: list[str] = []
    for analyzer in _analyzers_present(tree)[0]:
        try:
            produced = analyzer.graph(tree)
        except SourceUnreadable as exc:
            # Recorded, never raised past: raising here would lose every other
            # file's edges and turn one bad file into a total outage of the
            # check. It abstains over the whole tree at judgement time instead.
            unreadable.append(exc.path)
            continue
        except AnalyzerError as exc:
            raise CallSiteReachabilityError(
                f"the {_language_of(analyzer)!r} analyzer could not build a "
                f"call graph for {tree}; a partial graph is a graph whose "
                f"missing edges look exactly like edges that do not exist: "
                f"{exc}"
            ) from exc
        symbols.update(produced.symbols)
        edges.extend(produced.edges)
        unresolved.extend(produced.unresolved_calls)
        unreadable.extend(produced.unreadable_paths)
    return CallGraph(
        symbols={key: symbols[key] for key in sorted(symbols)},
        edges=tuple(sorted(edges, key=_edge_order)),
        unresolved_calls=tuple(
            sorted(unresolved, key=lambda hole: (hole[0].key, hole[1], hole[2]))
        ),
        unreadable_paths=tuple(sorted(dict.fromkeys(unreadable))),
    )


def _edge_order(edge: Edge) -> tuple[str, str, str, str]:
    """A total, content-only order over edges. Sorted at CONSTRUCTION.

    Determinism is a contract of :func:`build_call_graph` and it is load-bearing
    twice over: two runs over one tree must produce equal reports so that a diff
    between them is a real change, and :func:`reachable_from` breaks its
    equal-length ties on this order, so an unsorted edge list would make the
    WITNESS PATH nondeterministic even where the verdict was not.
    """
    return (edge.caller.key, edge.callee.key, edge.kind.value, edge.site)


def reachable_from(
    graph: CallGraph, roots: Sequence[Root]
) -> Mapping[str, tuple[Edge, ...]]:
    """Transitive closure over ``graph`` from ``roots``, with a witness path.

    Returns ``Symbol.key`` -> the edge chain from some root to it, so a finding
    can SHOW the path rather than assert it. The chain, not merely the fact:
    a mechanism that reports "reachable" with no path is one nobody can check,
    and unverifiable green is the thing this whole effort is about.

    **P4 RULING (2026-08-11), on R5 — and the scaffold was silent on it, which
    it could not afford to be.** *Every root's own key is IN the map, mapped to
    the empty chain* ``()``. Three consequences, all forced:

      1. **A root is reachable from itself.** Excluding roots would make
         ``func main`` unreachable, and a subject that IS a root — a
         ``GO_INIT``, a ``GO_PACKAGE_VAR``, a ``PYTHON_IMPORT_TIME`` module
         body, a console-script ``main`` — would come back
         :attr:`Reach.FROM_TESTS_ONLY` or :attr:`Reach.FROM_NEITHER`. That is a
         false BREACH against the entrypoint itself, which is the loudest
         possible way to be wrong about the one symbol whose liveness is not in
         question.
      2. **It is what makes "no entrypoint" distinguishable from "the
         entrypoint calls nothing", and that distinction is not a detail** —
         it decides whether an empty production reach map is an abstention over
         EVERY subject in the tree. With roots included, a tree whose lonely
         ``main`` calls nothing yields ``{main: ()}``, which is not empty, so
         ``production_reach == {}`` means exactly one thing: **there are no
         production roots.** With roots excluded the two states are the same
         value and a body would have to guess.
      3. **A zero-edge chain is** :attr:`PathQuality.RESOLVED`, **never**
         :attr:`PathQuality.NOT_APPLICABLE`. The quality of a chain is the
         minimum over its edges and the minimum over no edges is the strong
         value — there is no weak link in a chain with no links. A body that
         spelled it ``NOT_APPLICABLE`` would hand :func:`adjudicate` the pair
         ``(FROM_PRODUCTION, NOT_APPLICABLE)``, which the grid RAISES on as a
         mechanism bug, and would take down the check on every tree whose seal
         covers an entrypoint.

    **The inclusion does not move where NO_ENTRYPOINT is decided.** It is still
    derived from the ROOT SET — "zero production roots of any
    :class:`EntrypointKind`" — and never from the shape of this map, so there
    stays one answer site. The map corroborates that answer; it is not the
    authority for it. ``test_no_entrypoint_is_a_fact_about_the_root_set`` pins
    that half and this ruling supplies the convention that lets a body satisfy
    it without inspecting the roots twice.

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
    out_edges: dict[str, list[Edge]] = {}
    for edge in graph.edges:
        out_edges.setdefault(edge.caller.key, []).append(edge)
    for chain in out_edges.values():
        chain.sort(key=_edge_order)

    # Sorted and de-duplicated, which is the "root sorts first by Symbol.key"
    # half of the tie-break: a level-order sweep that starts its frontier in
    # this order reaches an equal-length target from the first-sorting root.
    root_keys = sorted({root.symbol.key for root in roots})

    # Two sweeps, not one scored traversal. The first is over the RESOLVED
    # subgraph alone, so anything it reaches has a chain with no weak link; the
    # second is over everything. Preferring the first is R5's correctness rule
    # — "the chain with the best PathQuality", never the shortest — and it is
    # why the shorter INTERFACE shortcut must lose to the longer DIRECT chain.
    resolved = _sweep_chains(out_edges, root_keys, resolved_only=True)
    everything = _sweep_chains(out_edges, root_keys, resolved_only=False)
    reach = dict(everything)
    reach.update(resolved)
    return reach


def _sweep_chains(
    out_edges: Mapping[str, Sequence[Edge]],
    root_keys: Sequence[str],
    *,
    resolved_only: bool,
) -> dict[str, tuple[Edge, ...]]:
    """Level-order reach from ``root_keys``, shortest chain per key.

    **Every root's own key is in the result, mapped to** ``()`` (R5). Three
    things ride on that and all three are in :func:`reachable_from`'s docstring;
    the one a body can get silently wrong is the third — a zero-edge chain is
    :attr:`PathQuality.RESOLVED`, which :func:`_chain_quality` delivers by
    taking the minimum over no edges to be the strong value.
    """
    chains: dict[str, tuple[Edge, ...]] = {key: () for key in root_keys}
    frontier = list(root_keys)
    while frontier:
        following: list[str] = []
        for key in frontier:
            chain = chains[key]
            for edge in out_edges.get(key, ()):
                if resolved_only and not _edge_is_resolved(edge.kind):
                    continue
                target = edge.callee.key
                if target in chains:
                    continue
                chains[target] = chain + (edge,)
                following.append(target)
        frontier = following
    return chains


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

    **P4 RULING (2026-08-11), on R3.** ``UNNAMEABLE`` was contracted twice and
    incompatibly: :func:`subjects_of_seal` said it yields a finding
    (:attr:`Reach.UNDECIDED` / :attr:`UndecidedReason.SUBJECT_UNIDENTIFIED`),
    :func:`check_tree` said a gap-bearing seal produces none.
    **:func:`subjects_of_seal` was the intent and it stands; the
    :func:`check_tree` sentence was over-general and is amended there.**

    The enum itself settles it, and it always did. ``NO_CALLS`` and
    ``ALL_TARGETS_IN_TESTS`` each say in as many words that they are legitimate
    and that no finding follows; ``UNNAMEABLE`` says the opposite in as many
    words. :func:`check_tree` wrote one rule over three members that do not
    share one. **Two of the three gaps are facts about a seal that made no
    claim. The third is a fact about a claim this mechanism could not read**,
    and a mechanism whose thesis is that failing to look is never a pass may
    not discharge the one gap that means "I failed to look" as a bare count.

    ``UndecidedReason.SUBJECT_UNIDENTIFIED`` is therefore NOT dead — it is the
    reason on that finding, and it is the only member of that enum reachable
    without a graph.

    **The finding needs a subject and there is none, so it gets a synthetic
    one**, on :class:`Symbol`'s own recorded convention for synthetic roots: a
    key spelled with a suffix no declaration can produce,
    ``<the seal's key>.<unnameable>``, carrying the seal's ``path`` and the
    line of the unresolved call site. Synthetic rather than reusing the seal's
    own symbol, because a finding whose subject IS its seal reads as a seal
    covering itself; synthetic rather than ``None``, because
    :class:`Finding` has no optional subject and a report must never show a
    finding with a blank where a subject belongs.
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
    seals: list[Seal] = []
    for root in roots:
        if root.kind is not EntrypointKind.TEST_FUNCTION:
            continue
        if root.symbol.key not in graph.symbols:
            raise CallSiteReachabilityError(
                f"test root {root.symbol.key!r} is not declared in the call "
                "graph, so its body was never read; a seal the graph does not "
                "declare would silently contribute no subject, which is the "
                "defect this module exists to refuse"
            )
        seals.append(Seal(symbol=root.symbol, test_id=_test_id(root.symbol)))
    # Root order, not sorted order. The report sorts its FINDINGS
    # (:func:`check_tree`); sorting here as well would hide a body that only
    # ever emits in discovery order behind a fixture whose two orders agree.
    return tuple(seals)


def _test_id(symbol: Symbol) -> str:
    """``cmd/classify.TestSeal_ResolveConfigDual`` — the row a human can run.

    DISPUTE, recorded rather than resolved. :class:`Seal` contracts ``test_id``
    as "not derived at report time: the spelling differs by language and a
    report that guessed it would send people to nothing", but
    :class:`ReachabilityAnalyzer` carries no method by which a row could supply
    one, so the only layer that could honour that sentence has no channel to.
    It is derived here — the declaring DIRECTORY, then the symbol's own last
    segment — which is exactly the Go ``package.TestName`` spelling the seals
    pin, and which is a defensible pytest node id only by accident. The seam to
    widen when a Python analyzer lands is a ``test_id`` method on the protocol;
    this function is then its one caller and disappears.
    """
    directory = symbol.path.rpartition("/")[0]
    name = symbol.key.rpartition(".")[2]
    return f"{directory}.{name}" if directory else name


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
    #: :class:`CallSiteReachabilityError`, because a subject record that says
    #: two things or says nothing is a non-judgement and a non-judgement must
    #: not read as an answer. D3's :class:`Witness` contract, unchanged.
    #:
    #: **P4 RULING (2026-08-11), on R2.** The scaffold located that raise "at
    #: :func:`check_subject`", which takes a :class:`Symbol` and has no
    #: :class:`Subject` parameter, so as written it was owed by a layer that
    #: cannot see one. It is owed by TWO layers and they owe different things:
    #:
    #:   * :func:`subjects_of_seal` owes it as a POSTCONDITION. It is the one
    #:     constructor of this record and it must raise rather than RETURN a
    #:     contradictory one — a malformed record that escapes its constructor
    #:     is a malformed record every later layer has to re-check.
    #:   * :func:`check_tree` owes it as a PRECONDITION on every
    #:     :class:`Subject` it consumes, because a second constructor or a
    #:     caller-supplied record would otherwise reach the judgement loop
    #:     unchecked, and the layer that ACTS on a non-judgement is the layer
    #:     where the non-judgement becomes an answer.
    #:
    #: :func:`check_subject` owes nothing here; the original sentence naming it
    #: is struck. ``test_a_subject_record_never_says_two_things_or_nothing``
    #: pins the constructor half. The :func:`check_tree` half is unpinned by
    #: any row and is recorded as such.
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
    called: dict[str, Symbol] = {}
    for edge in graph.edges:
        # Keyed on the CALLER's key, never on containment. The fixture's decoy
        # (`…ResolveConfigDualDocComment`) exists to redden a body that reaches
        # for a substring here.
        if edge.caller.key == seal.symbol.key:
            called.setdefault(edge.callee.key, edge.callee)
    in_production = {
        key: symbol
        for key, symbol in called.items()
        if not is_test_path(symbol.path)
    }
    unnameable = [
        hole for hole in graph.unresolved_calls if hole[0].key == seal.symbol.key
    ]

    if in_production:
        subject = Subject(
            seal=seal,
            symbols=tuple(in_production[key] for key in sorted(in_production)),
            gap=None,
            detail=(
                f"{seal.test_id} calls "
                f"{len(in_production)} symbol(s) declared outside the tests"
            ),
        )
    elif unnameable:
        # UNNAMEABLE outranks the other two even when the seal also calls test
        # helpers: the target nobody could name may be the very production
        # symbol the seal exists to cover, and the other two members each say
        # in as many words that the seal made no claim.
        subject = Subject(
            seal=seal,
            symbols=(),
            gap=SubjectGap.UNNAMEABLE,
            detail=(
                f"{seal.test_id} calls {len(unnameable)} target(s) the "
                f"analyzer could not name, first at {unnameable[0][1]}"
            ),
        )
    elif called:
        subject = Subject(
            seal=seal,
            symbols=(),
            gap=SubjectGap.ALL_TARGETS_IN_TESTS,
            detail=(
                f"{seal.test_id} calls only symbols declared in test files; it "
                "exercises helpers, not production"
            ),
        )
    else:
        subject = Subject(
            seal=seal,
            symbols=(),
            gap=SubjectGap.NO_CALLS,
            detail=f"{seal.test_id} calls nothing declared in this tree",
        )
    # R2, the POSTCONDITION half: this is the one constructor of the record and
    # it must raise rather than RETURN a contradictory one, because a malformed
    # record that escapes its constructor is one every later layer re-checks.
    _validate_subject(subject)
    return subject


def _validate_subject(subject: Subject) -> None:
    """``gap`` is None exactly when ``symbols`` is non-empty. Both ways.

    Owed at two layers and this is the shared implementation of both (R2):
    :func:`subjects_of_seal` calls it as a postcondition, :func:`check_tree`
    calls it as a precondition on every record it consumes. The second is
    unpinned by any row and is written anyway — the layer that ACTS on a
    non-judgement is the layer where the non-judgement becomes an answer, and a
    record arriving from a second constructor is not constructible today only
    because there is no second constructor today.
    """
    if not isinstance(subject, Subject):
        raise CallSiteReachabilityError(
            f"{subject!r} is not a Subject and cannot be judged"
        )
    if subject.symbols and subject.gap is not None:
        raise CallSiteReachabilityError(
            f"subject record for {subject.seal.test_id!r} carries gap "
            f"{subject.gap!r} alongside "
            f"{len(subject.symbols)} symbol(s); a record that says two things "
            "is a non-judgement and a non-judgement must not read as an answer"
        )
    if not subject.symbols and subject.gap is None:
        raise CallSiteReachabilityError(
            f"subject record for {subject.seal.test_id!r} names no symbol and "
            "no gap; a record that says nothing is a non-judgement and a "
            "non-judgement must not read as an answer"
        )
    if subject.gap is not None and not isinstance(subject.gap, SubjectGap):
        raise CallSiteReachabilityError(
            f"subject record for {subject.seal.test_id!r} carries "
            f"{subject.gap!r}, which is not a SubjectGap member"
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
    """Why :attr:`Reach.UNDECIDED`, as DATA. Five states, exhaustively.

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
    **There is deliberately no ``ANALYZER_FAULT`` member**, and its absence is
    a P4 ruling rather than an oversight; see :class:`AnalyzerFault`. A fault is
    a fact about the MACHINE and it arrives at the caller as a raised
    :class:`CallSiteReachabilityError`, because both sites that can meet one are
    upstream of the subject population and an abstention over no subjects is
    silence with a label. Every member below is a fact about a SUBJECT that the
    mechanism did enumerate and then declined to judge. A body author who wants
    to fold a fault into this enum is re-opening a decided question and needs a
    new P4 round, not a new member.

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


def _chain_quality(chain: Sequence[Edge]) -> PathQuality:
    """The MINIMUM over a chain's edges. Never the last one, never the majority.

    A chain is only as certain as its weakest link, so one
    :attr:`EdgeKind.INTERFACE` or :attr:`EdgeKind.REFERENCE` anywhere makes the
    whole chain :attr:`PathQuality.OVER_APPROXIMATED`.

    **A ZERO-EDGE chain is** :attr:`PathQuality.RESOLVED` (R5), because the
    minimum over no edges is the strong value — there is no weak link in a chain
    with no links. Spelling it :attr:`PathQuality.NOT_APPLICABLE` would hand
    :func:`adjudicate` the pair ``(FROM_PRODUCTION, NOT_APPLICABLE)``, which the
    grid raises on as a mechanism bug, and would take the check down on every
    tree whose seal covers an entrypoint.
    """
    if all(_edge_is_resolved(edge.kind) for edge in chain):
        return PathQuality.RESOLVED
    return PathQuality.OVER_APPROXIMATED


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
    roots: Sequence[Root] = (),
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

    **``roots`` is a body-added, keyword-only, defaulted parameter and it is a
    recorded DISPUTE, not a widening of the contract.** :class:`CallPath` is
    contracted to carry the :class:`Root` a chain starts at — "so a reader can
    ask does that program actually ship" — and the scaffold's signature passes
    no root records, so a faithful ``CallPath.root`` is not constructible from
    the arguments it names. :func:`check_tree` supplies the real records and
    every report this module produces therefore carries true ones. When they are
    absent (a caller judging one pair in isolation, which is how the seals use
    this function) the root is SYNTHESISED by :func:`_synthetic_root`, whose
    ``evidence`` says so in the report rather than quietly claiming a mechanism
    nobody derived. Two further clauses read ``roots`` when it is supplied:

      * step 2 decides :attr:`UndecidedReason.NO_ENTRYPOINT` from the ROOT SET,
        which is what R5 requires — "the map corroborates, it is not the
        authority". With no root records the map is all there is, and R5's
        inclusion convention is exactly what makes it usable: with roots mapped
        to ``()``, ``production_reach == {}`` means one thing only.
    """
    if not isinstance(subject, Symbol):
        raise CallSiteReachabilityError(
            f"{subject!r} is not a Symbol and cannot be judged"
        )
    test_path = _witness(subject, test_reach, RootKind.TEST, roots)

    # 1. A path that was found is FOUND. First, before every abstention, so
    #    that "we could not see everything" can never suppress a real pass.
    if subject.key in production_reach:
        path = _witness(subject, production_reach, RootKind.PRODUCTION, roots)
        return Finding(
            seal=seal,
            subject=subject,
            reach=Reach.FROM_PRODUCTION,
            quality=path.quality,
            path=path,
            test_path=test_path,
            reason=None,
            detail=(
                f"production reaches {subject.key} from "
                f"{path.root.symbol.key} over {len(path.edges)} edge(s), "
                f"quality {path.quality.value}"
            ),
        )

    # 1b. An unparsed file is a hole of UNKNOWN SIZE in the edge set, so any
    #     "no path" computed around it is computed around a hole. Whole-tree,
    #     per SourceUnreadable's CHOICE, and after step 1 because a found path
    #     is not un-found by a file nobody could read.
    if graph.unreadable_paths:
        return _abstention(
            seal,
            subject,
            test_path,
            UndecidedReason.PARSE_FAILED,
            (
                f"{len(graph.unreadable_paths)} file(s) could not be parsed, "
                f"first {graph.unreadable_paths[0]}; every no-path answer over "
                "this tree would be computed around a hole of unknown size"
            ),
        )

    # 2. Zero production roots, BEFORE the tests-only check: with no production
    #    root the tests-only answer is arithmetically guaranteed and would be a
    #    BREACH against every subject in a library.
    if _has_no_production_root(roots, production_reach):
        return _abstention(
            seal,
            subject,
            test_path,
            UndecidedReason.NO_ENTRYPOINT,
            (
                "this tree has no production entrypoint of any EntrypointKind, "
                "so nothing here is 'everything exported is reachable' and "
                "nothing here is 'nothing is reachable'"
            ),
        )

    # 3. The negative is not conclusive: either the language says so, or the
    #    production closure itself contains a call nobody could name.
    if not analyzer.negative_is_conclusive:
        return _abstention(
            seal,
            subject,
            test_path,
            UndecidedReason.DYNAMIC_EDGE,
            (
                f"the {_language_of(analyzer)} row declares its negative "
                "inconclusive, so 'no path' would be a fact about the analyzer "
                "rather than about the language"
            ),
        )
    holes = [
        hole for hole in graph.unresolved_calls if hole[0].key in production_reach
    ]
    if holes:
        return _abstention(
            seal,
            subject,
            test_path,
            UndecidedReason.DYNAMIC_EDGE,
            (
                f"{len(holes)} call(s) inside the production closure could not "
                f"be resolved, first at {holes[0][1]} ({holes[0][2]}); one of "
                "them may be the missing call site"
            ),
        )

    # 4. The B1 verdict, reached only once every abstention above is ruled out.
    if subject.key in test_reach:
        return Finding(
            seal=seal,
            subject=subject,
            reach=Reach.FROM_TESTS_ONLY,
            quality=PathQuality.NOT_APPLICABLE,
            path=None,
            test_path=test_path,
            reason=None,
            detail=(
                f"{subject.key} is reached from {seal.test_id} and from no "
                "production root; the seal proves it behaves and nothing "
                "proves it runs"
            ),
        )

    # 5. Impossible for a seal-derived subject, so it is the mechanism's own
    #    bug and is reported as one rather than converted into a finding.
    raise CallSiteReachabilityError(
        f"{subject.key} is reached from no root at all, and {seal.test_id} "
        "has a direct edge to it by the definition of 'subject'; the traversal "
        "lost an edge it was handed, and a lost edge folded into the "
        "tests-only verdict would be an over-call against innocent code"
    )


def _abstention(
    seal: Seal,
    subject: Symbol,
    test_path: "CallPath | None",
    reason: UndecidedReason,
    detail: str,
) -> Finding:
    """One shape for every abstention, so none of them can drift into a pass."""
    if not isinstance(reason, UndecidedReason):
        raise CallSiteReachabilityError(
            f"{reason!r} is not an UndecidedReason; an abstention whose reason "
            "is prose is one a reworded message can flip"
        )
    return Finding(
        seal=seal,
        subject=subject,
        reach=Reach.UNDECIDED,
        quality=PathQuality.NOT_APPLICABLE,
        path=None,
        test_path=test_path,
        reason=reason,
        detail=detail,
    )


def _has_no_production_root(
    roots: Sequence[Root], production_reach: Mapping[str, tuple[Edge, ...]]
) -> bool:
    """R5: the ROOT SET is the authority; the reach map only corroborates."""
    if roots:
        return not any(root.root_kind is RootKind.PRODUCTION for root in roots)
    return not production_reach


def _witness(
    subject: Symbol,
    reach: Mapping[str, tuple[Edge, ...]],
    root_kind: RootKind,
    roots: Sequence[Root],
) -> "CallPath | None":
    """The chain a human follows, or None when this side reached nothing."""
    if subject.key not in reach:
        return None
    chain = tuple(reach[subject.key])
    origin = chain[0].caller if chain else subject
    declared = {
        (root.symbol.key, root.root_kind): root for root in roots
    }.get((origin.key, root_kind))
    root = declared if declared is not None else _synthetic_root(origin, root_kind)
    return CallPath(root=root, edges=chain, quality=_chain_quality(chain))


def _synthetic_root(symbol: Symbol, root_kind: RootKind) -> Root:
    """A :class:`Root` for a chain whose real record this layer was not handed.

    Only reachable when a caller judges one pair without supplying ``roots``;
    :func:`check_tree` always supplies them. The ``evidence`` says exactly that,
    because a root nobody can verify is a root nobody will believe.

    The TEST side is a derivation and not a guess: ``TEST_FUNCTION`` is the only
    member of :class:`EntrypointKind` on the test side, so there is nothing to
    choose. **The PRODUCTION side is the dispute** — the production side of
    :data:`_ROOT_KIND_BY_ENTRYPOINT` holds SEVEN kinds (counted over
    :class:`EntrypointKind` in this file at ``feat/D5-body``, 2026-08-11) and a
    chain's first caller does not say which one started it — so the
    kind is narrowed by the LANGUAGE of the declaring file and the narrowing is
    written into ``evidence``. A language with no production entrypoint kind
    (TypeScript, deliberately: "a kind with no analyzer emitting it will never
    fire and will be read as coverage") RAISES rather than borrows another
    language's.
    """
    if root_kind is RootKind.TEST:
        return Root(
            symbol=symbol,
            kind=EntrypointKind.TEST_FUNCTION,
            root_kind=RootKind.TEST,
            evidence=(
                f"{symbol.path}:{symbol.line} — derived from the witness chain; "
                "TEST_FUNCTION is the only test entrypoint kind, so no kind was "
                "chosen"
            ),
        )
    if root_kind is not RootKind.PRODUCTION:
        raise CallSiteReachabilityError(
            f"{root_kind!r} is neither production nor test; RootKind has two "
            "members and no UNKNOWN"
        )
    support = support_for_path(symbol.path)
    language = support.language if support is not None else None
    kind = _FALLBACK_PRODUCTION_KIND.get(language)
    if kind is None:
        raise CallSiteReachabilityError(
            f"no production EntrypointKind can be named for {symbol.key!r} in "
            f"{symbol.path!r} (language {language!r}) and no Root record was "
            "supplied; naming a kind this module cannot derive would put a "
            "mechanism nobody checked into a report a human is meant to check"
        )
    return Root(
        symbol=symbol,
        kind=kind,
        root_kind=RootKind.PRODUCTION,
        evidence=(
            f"{symbol.path}:{symbol.line} — derived from the witness chain; no "
            f"Root record was supplied to check_subject, so the kind is "
            f"NARROWED to {kind.value} by the file's language and is not a "
            "sweep result"
        ),
    )


#: The narrowest production :class:`EntrypointKind` each language has, used only
#: by :func:`_synthetic_root`. TypeScript is deliberately absent: no member of
#: the enum names a TypeScript concept, and borrowing another language's kind
#: would put a mechanism nobody derived into a report.
_FALLBACK_PRODUCTION_KIND: Mapping[Language, EntrypointKind] = {
    Language.GO: EntrypointKind.GO_MAIN,
    Language.PYTHON: EntrypointKind.PYTHON_SCRIPT_MAIN,
}


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

    **P4 RULING (2026-08-11), on R8: RATIFIED, with one condition that is new.**

    The seal author recorded the appealability without ratifying it and was
    right not to: an appealable BREACH is one someone can talk their way out
    of, and a policy claim is not a seal author's to settle. Ratified, on the
    scaffold's argument, which survives scrutiny: the scaffold-first protocol
    MANUFACTURES this state by construction — a P1 scaffold is a set of symbols
    with seals and no call sites — so an unappealable BREACH makes the
    protocol's own intermediate state a blocking failure, and the recorded
    consequence of a check that over-calls is that it gets switched off. A
    check nobody runs is this repository's most expensive measured failure. D3
    could make its finding unappealable because nothing in the protocol
    manufactures D3's state; something in the protocol manufactures this one.

    **What stops ``wiring`` becoming a rubber stamp, and the honest answer is
    that the scaffold's argument does NOT, on its own.** "A B1 author writing
    that sentence would have discovered the bug in the act of writing it" is
    true and is unenforceable: nothing reads the sentence, so nothing stops it
    being ``"TODO"``. What actually holds the line is that the appeal is
    EXPENSIVE and VISIBLE, and four of those five properties were already
    sealed by P2 — both keys exact, staleness reported, ``ACCEPTED`` counted
    apart from ``OK``, abstentions and path qualities untouchable, exactly one
    cell moved. Ratification adds the fifth, because four were not enough:

      * **A declaration whose ``wiring`` is empty or whitespace is NOT a
        declaration.** :func:`adjudicate` ignores it exactly as it ignores a
        key mismatch — the finding rules as though no declaration were passed —
        and :func:`check_tree` reports it in ``stale_declarations``. This is
        the minimum mechanical check that a sentence was written at all, it is
        the only part of "name a future in which this stops being true" a
        machine can verify, and it converts the scaffold's argument from an
        appeal to good faith into a precondition. It is deliberately NOT a
        check that the ticket exists or is open: this module has no issue
        tracker and inventing a dependency on one would put the gate's verdict
        behind a network call.

    What is NOT ruled, and is left for the first body that has evidence: an
    EXPIRY on a declaration. It is the obvious next tooth and it needs a clock
    and a policy, neither of which this module has. The named trigger for
    adding one: the first ``ACCEPTED`` count that survives two releases
    unchanged — at which point the debt figure has demonstrated that visibility
    alone does not retire it.
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


#: **THE ruling grid, as DATA.** Four rows; every pair absent from it raises.
#: A table and not branching prose, per the P4 ruling on :func:`adjudicate`: a
#: chain of ``if``\ s grows a default branch, and a default branch on this
#: dispatch is how the permissive answer gets a new spelling.
#:
#: Each value is ``(no declaration, a declaration whose two keys match and whose
#: wiring says something)``. The two differ in exactly ONE row, which is the
#: whole power of the annotation: it cannot touch ``ABSTAIN`` (the abstention
#: count is this mechanism's own coverage figure and buying silence on it would
#: be buying silence on a measurement nobody took) and it cannot touch
#: ``REPORT`` (a human cannot declare an over-approximated path into a resolved
#: one, because the weakness is in the analysis and not in the code).
#:
#: The eight pairs that are NOT here are the specification, and each omitted
#: class is a MECHANISM bug rather than a policy choice: ``FROM_PRODUCTION`` with
#: ``NOT_APPLICABLE`` is a path found whose quality nobody recorded;
#: ``FROM_TESTS_ONLY`` or ``UNDECIDED`` with any quality other than
#: ``NOT_APPLICABLE`` is a quality recorded for a path that does not exist; and
#: ``FROM_NEITHER`` is omitted rather than mapped so that this layer and
#: :func:`check_subject` cannot disagree about it — the raise IS that member's
#: exhaustive treatment.
_RULINGS: Mapping[tuple[Reach, PathQuality], tuple[Disposition, Disposition]] = {
    (Reach.FROM_PRODUCTION, PathQuality.RESOLVED): (
        Disposition.OK,
        Disposition.OK,
    ),
    (Reach.FROM_PRODUCTION, PathQuality.OVER_APPROXIMATED): (
        Disposition.REPORT,
        Disposition.REPORT,
    ),
    (Reach.FROM_TESTS_ONLY, PathQuality.NOT_APPLICABLE): (
        Disposition.BREACH,
        Disposition.ACCEPTED,
    ),
    (Reach.UNDECIDED, PathQuality.NOT_APPLICABLE): (
        Disposition.ABSTAIN,
        Disposition.ABSTAIN,
    ),
}


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

    A declaration is honoured only when it carries a non-empty ``wiring``; an
    empty or whitespace one is ignored for the ruling exactly as a key mismatch
    is, and is reported stale. See the P4 ruling on :class:`StagedDeclaration`.

    **P4 RULING (2026-08-11): THE GRID ABOVE IS RULED, AS WRITTEN.** The
    scaffold left it as prose following D3's P1 precisely so that a P4 would
    rule before a body pinned it as data. It is ruled: the four rows stand
    unchanged, every other pair raises, and **a body must now implement it as a
    module-level table** rather than treating it as a proposal.

    The four cells were re-derived against this round's other rulings and none
    of them adds a cell:

      * A subject that is itself a production root has a zero-edge chain, whose
        quality is :attr:`PathQuality.RESOLVED` (R5) — cell 1, not a new one.
      * An :attr:`SubjectGap.UNNAMEABLE` seal's finding is
        ``(UNDECIDED, NOT_APPLICABLE)`` (R3) — cell 4, not a new one.
      * An analyzer fault produces no finding at all (R1), so it needs no cell;
        that is what striking :attr:`UndecidedReason.ANALYZER_FAULT` bought.

    **No row is added pinning a cell, and that is also the ruling.** P2 sealed
    the PROPERTIES instead — totality, the raise on an unknown member, the
    raise on ``FROM_NEITHER`` at both layers, three-bucket separation, and the
    exactly-one-cell bound on a declaration — and those are strictly stronger
    than four cell assertions against the failures that actually happen here: a
    default branch, a collapsed vocabulary, a declaration that reaches further
    than it should. Four cell rows would be four rows a body satisfies by
    transcribing the table and nothing else, and they would say nothing about
    the eight pairs that must refuse. The cells are now settled by RULING and
    the properties are settled by SEAL, which is the correct division: a body
    that transcribes this table wrongly is caught by the properties, and a body
    that transcribes it differently on purpose is overturning a P4.

    **BODY DISPUTE (``feat/D5-body``, 2026-08-11), and it is escalated rather
    than resolved here: this function does NOT enforce the ``Finding``
    consistency rule its own class docstring assigns to it, because the seals
    forbid it to.** :class:`Finding` says "``reason`` is non-None exactly when
    ``reach`` is UNDECIDED, and ``path`` is non-None exactly when ``reach`` is
    FROM_PRODUCTION. Both contradictions are :class:`CallSiteReachabilityError`
    at :func:`adjudicate`". But
    ``test_the_three_verdict_classes_land_in_three_buckets`` and
    ``test_a_declaration_moves_at_most_one_outcome_and_never_an_abstention``
    both sweep the whole grid with findings built as
    ``(reach, quality, reason=DYNAMIC_EDGE, path=None)`` and REQUIRE a ruling
    back for ``(FROM_PRODUCTION, RESOLVED)`` — which carries a reason it may not
    carry and lacks a path it must have. A body that enforced the rule would
    raise there, ``rulings[FROM_PRODUCTION]`` would be empty, and both rows
    would redden. The two cannot both stand, the seals are not a body's to
    edit, and so the grid is enforced and the consistency rule is not.

    What that costs, stated so it is a decision: a finding carrying two answers
    is ruled on rather than refused. What it does NOT cost is any answer this
    module produces — :func:`check_subject` is the only constructor of a
    :class:`Finding` here and it is total over the five outcomes, each of which
    sets ``reason`` and ``path`` consistently by construction. The contradiction
    is therefore unreachable from within the module and only a caller
    hand-building a :class:`Finding` can reach it, which is exactly what the two
    rows do. **The question for P4: does the raise move to
    :func:`check_subject`'s postcondition, or is the sentence in
    :class:`Finding` struck?** A body may not choose.
    """
    try:
        cell = _RULINGS.get((finding.reach, finding.quality))
    except TypeError as exc:  # an unhashable stand-in for a member nobody ruled on
        raise CallSiteReachabilityError(
            f"({finding.reach!r}, {finding.quality!r}) cannot even be looked up "
            f"in the ruling grid: {exc}"
        ) from exc
    if cell is None:
        raise CallSiteReachabilityError(
            f"the ruling grid does not name ({finding.reach!r}, "
            f"{finding.quality!r}). Every pair it does not name is a mechanism "
            "bug — a path found with no quality recorded, a quality recorded "
            "for a path that does not exist, or a member added without "
            "visiting this dispatch — and a mechanism bug must not fall "
            "through to the permissive answer"
        )
    undeclared, declared = cell
    return declared if _declaration_answers(finding, declaration) else undeclared


def _declaration_answers(
    finding: Finding, declaration: StagedDeclaration | None
) -> bool:
    """Does this declaration actually answer this finding?

    BOTH keys, exactly — a typo is not an accepted state, and a suffix or a bare
    name would let one declaration cover a family. Plus R8's ratification
    condition: **a declaration with no ``wiring`` is not a declaration.** Empty
    and whitespace-only both count as absent, and such a declaration is ignored
    for the ruling exactly as a key mismatch is, then reported stale by
    :func:`check_tree`. It is deliberately NOT a check that the named ticket
    exists: a verdict behind a network call is a worse gate.
    """
    if declaration is None:
        return False
    if declaration.test_id != finding.seal.test_id:
        return False
    if declaration.subject_key != finding.subject.key:
        return False
    return bool(declaration.wiring and declaration.wiring.strip())


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
      * **A seal that yields no subject is COUNTED, in ``subject_gaps``.**
        Whether it also produces a finding depends on WHICH gap, and the P4
        ruling on :class:`SubjectGap` (R3) makes that split normative:

          - :attr:`SubjectGap.NO_CALLS` and
            :attr:`SubjectGap.ALL_TARGETS_IN_TESTS` produce NO finding. Not an
            error and not a pass: the seal made no claim this module can check.
          - :attr:`SubjectGap.UNNAMEABLE` produces exactly ONE finding, an
            abstention — :attr:`Reach.UNDECIDED`,
            :attr:`UndecidedReason.SUBJECT_UNIDENTIFIED`,
            :attr:`PathQuality.NOT_APPLICABLE`, over the synthetic subject
            symbol :class:`SubjectGap` specifies. The seal made a claim and the
            mechanism could not read it, which is a fact about the MECHANISM
            and belongs in the findings where an abstention is counted, not in
            a gap tally where it reads as a seal that had nothing to say.

        This is the sentence the scaffold wrote over all three members at once;
        it is amended rather than deleted because two thirds of it were right.
      * **Validate every :class:`Subject` before acting on it** (R2): a record
        carrying a gap alongside symbols, or an empty symbol set with no gap,
        is a :class:`CallSiteReachabilityError` here as well as at its
        constructor. See :class:`Subject`.
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
    unanalyzed = _analyzers_present(tree)[1]
    roots = discover_roots(tree)
    graph = build_call_graph(tree)

    production_roots = tuple(r for r in roots if r.root_kind is RootKind.PRODUCTION)
    test_roots = tuple(r for r in roots if r.root_kind is RootKind.TEST)
    # Twice, never one labelled traversal: a flag that propagates wrongly in the
    # permissive direction is a test root laundering itself into a production
    # answer.
    production_reach = reachable_from(graph, production_roots)
    test_reach = reachable_from(graph, test_roots)

    seals = discover_seals(graph, roots)
    gaps: dict[SubjectGap, int] = {gap: 0 for gap in SubjectGap}
    findings: list[Finding] = []
    for seal in seals:
        subject = subjects_of_seal(seal, graph)
        # R2, the PRECONDITION half. See :func:`_validate_subject`.
        _validate_subject(subject)
        if subject.gap is not None:
            gaps[subject.gap] += 1
            if subject.gap is SubjectGap.UNNAMEABLE:
                # R3: exactly ONE finding, an abstention, over a synthetic
                # subject. A seal the mechanism could not READ is a fact about
                # the mechanism and belongs where abstentions are counted, not
                # in a gap tally where it reads as a seal that had nothing to
                # say.
                findings.append(_unnameable_finding(seal, graph, subject.detail))
            elif subject.gap in (SubjectGap.NO_CALLS, SubjectGap.ALL_TARGETS_IN_TESTS):
                # A seal that made no claim this module can check. Counted, and
                # no finding follows — the two members say so in as many words.
                pass
            else:
                raise CallSiteReachabilityError(
                    f"subject gap {subject.gap!r} has no treatment here; a gap "
                    "that falls through would discharge an unread claim as a "
                    "bare count"
                )
            continue
        for symbol in subject.symbols:
            analyzer = analyzer_for_path(symbol.path)
            if analyzer is None:
                findings.append(
                    _abstention(
                        seal,
                        symbol,
                        _witness(symbol, test_reach, RootKind.TEST, roots),
                        UndecidedReason.UNSUPPORTED_LANGUAGE,
                        (
                            f"no analyzer row can read {symbol.path}; this is a "
                            "permanent fact about the gate, not about the "
                            "machine it ran on"
                        ),
                    )
                )
                continue
            findings.append(
                check_subject(
                    seal,
                    symbol,
                    graph=graph,
                    production_reach=production_reach,
                    test_reach=test_reach,
                    analyzer=analyzer,
                    roots=roots,
                )
            )

    findings.sort(key=lambda f: (f.seal.test_id, f.subject.key))

    dispositions: dict[Disposition, int] = {d: 0 for d in Disposition}
    answered: set[int] = set()
    for finding in findings:
        matched: StagedDeclaration | None = None
        for index, declaration in enumerate(declarations):
            if _declaration_answers(finding, declaration):
                answered.add(index)
                if matched is None:
                    matched = declaration
        dispositions[adjudicate(finding, matched)] += 1

    return ReachabilityReport(
        findings=tuple(findings),
        dispositions=dispositions,
        roots=roots,
        seals_examined=len(seals),
        subject_gaps=gaps,
        unresolved_call_count=sum(
            1 for hole in graph.unresolved_calls if hole[0].key in production_reach
        ),
        unanalyzed_paths=unanalyzed,
        stale_declarations=tuple(
            declaration
            for index, declaration in enumerate(declarations)
            if index not in answered
        ),
    )


#: The suffix that spells a synthetic subject, on :class:`Symbol`'s own recorded
#: convention for synthetic roots: no declaration can produce it, so it cannot
#: collide with a real symbol.
_UNNAMEABLE_SUFFIX = "<unnameable>"


def _unnameable_finding(seal: Seal, graph: CallGraph, detail: str) -> Finding:
    """The one abstention an :attr:`SubjectGap.UNNAMEABLE` seal produces (R3).

    The subject is SYNTHETIC — ``<seal key>.<unnameable>`` — rather than the
    seal's own symbol, which would read as a seal covering itself, and rather
    than ``None``, because :class:`Finding` has no optional subject and a report
    must never show a blank where a subject belongs.
    """
    sites = sorted(
        (hole for hole in graph.unresolved_calls if hole[0].key == seal.symbol.key),
        key=lambda hole: (hole[1], hole[2]),
    )
    if not sites:
        raise CallSiteReachabilityError(
            f"{seal.test_id} was classified UNNAMEABLE with no unresolved call "
            "site to point at; the finding would name no place a human can open"
        )
    return _abstention(
        seal,
        Symbol(
            key=f"{seal.symbol.key}.{_UNNAMEABLE_SUFFIX}",
            path=seal.symbol.path,
            line=_line_of(sites[0][1], seal.symbol.line),
        ),
        None,
        UndecidedReason.SUBJECT_UNIDENTIFIED,
        detail,
    )


def _line_of(site: str, fallback: int) -> int:
    """The line out of a ``file:line`` call site, or ``fallback``.

    A best effort over a string an analyzer wrote, and it is deliberately a
    fallback rather than a raise: the site's SPELLING is not a protocol this
    module owns, and a mechanism that refused to report an abstention because it
    could not parse a line number would have converted "I could not read this
    claim" into "I could not run", which is a different and louder answer.
    """
    tail = site.rpartition(":")[2]
    try:
        return int(tail)
    except ValueError:
        return fallback
