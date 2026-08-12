"""The vocabulary the call-reachability gate and its rows both speak.

**This module NAMES. It does not DECIDE.** That sentence is the whole contract
and the rule the rest of this docstring exists to make enforceable.

``call_site_reachability`` (the MECHANISM) decides whether a subject is
reachable from a production root and turns that into a ``Disposition`` a branch
is judged by. ``go_reachability`` (a ROW) knows how to read Go. Both need the
same eighteen names — the enums a verdict is spelled in, the frozen records an
edge set is made of, the two exception types a row may raise, and the two
constants that pin the helper's wire schema and its directory. Before this
module existed those names lived in the mechanism, which made the row's
module-level import of them a cycle. They live here now, and the dependency
runs::

    call_site_contract  <-  call_site_reachability   (the mechanism)
    call_site_contract  <-  go_reachability          (the row)
    call_site_reachability  <-  go_reachability      (enrolment, now acyclic)

This module imports **nothing from this package**. Its ``import`` block is four
stdlib names, and that is not a coincidence to be preserved by care — it is what
makes the acyclicity structural rather than a property somebody has to keep
re-checking. **Measured under** ``feat/D5-contract-module``, base ``6e18fc0``,
2026-08-11: ``ast`` over this file reports zero relative imports.


WHY THIS MODULE EXISTS — THE CYCLE, MEASURED
============================================
``ANALYZERS`` is the mechanism's registry and it is still ``()``. An attempt to
put ``go_reachability.GO_REACHABILITY_ANALYZER`` in it was refused, in a fresh
interpreter, in both available placements. **Measured under** base ``6e18fc0``,
2026-08-11, each in its own copy of the package:

  * **row at the anchor** (``ANALYZERS`` at ``call_site_reachability.py:1223``,
    with the import beside it) — ``ImportError: cannot import name
    'GO_REACHABILITY_PACKAGE_DIR' from partially initialized module
    'claude_dispatcher.call_site_reachability'``, raised from
    ``go_reachability.py:319``, which imports eleven names from the mechanism at
    module level, all of them defined AFTER line 1223;

  * **row at bottom-of-module** — and this one is worse than "it fails",
    because it fails *conditionally*. ``import
    claude_dispatcher.call_site_reachability`` SUCCEEDS and yields a populated
    registry. ``import claude_dispatcher.go_reachability`` first raises
    ``ImportError: cannot import name 'GO_REACHABILITY_ANALYZER' from partially
    initialized module 'claude_dispatcher.go_reachability'``. A gate whose
    registry depends on which module the process touched first is a gate that
    can be empty on the run that matters.

  * and the bottom-of-module placement additionally **destroys the import-time
    guard, silently**. ``validate_analyzers(ANALYZERS)`` runs at
    ``call_site_reachability.py:1296`` and ``_refuse_enrolment_before_flooring()``
    at ``:1399``; a row assigned after line 5224 is not there when either runs.
    **Measured under** base ``6e18fc0``, 2026-08-11: with the row at the bottom
    AND ``**/src/claude_dispatcher/call_site_reachability.py`` deleted from
    ``FLOOR_GLOBS`` — i.e. enrolled and unfloored, the exact state
    ``_refuse_enrolment_before_flooring`` exists to refuse — the module
    **imports cleanly**. The guard saw ``()``. That is the vacuous-seal shape,
    reintroduced by an import-order workaround.

**LAZY IMPORT WAS REJECTED ON MEASUREMENT AND IS NOT TO BE RELITIGATED.** The
third bullet is the reason, stated as a property rather than as a preference: a
lazily-imported row cannot be in a module-level tuple at the moment the two
import-time guards read that tuple, so it converts both of them into checks over
an empty registry. The mechanism's own ``ANALYZERS`` note argues that "empty is
a claim" and ``_refuse_enrolment_before_flooring``'s docstring makes "an EMPTY
registry never refuses" a load-bearing conjunct. Lazy import makes the registry
permanently empty *to the guards* and populated *to the callers*, which is the
two-different-things-with-one-name failure both were written against.

**COLLAPSING THE ROW INTO THE MECHANISM WAS ALSO REJECTED.** The comparator
precedent (``GO_SUPPORT`` and ``GoSignatureFingerprinter`` both inside
``role_protocol.py``) has no cycle because it has no second module. D5 split on
purpose, and its own scaffold gave the reason: *"a row that imports the
mechanism is the direction the dependency should run, so that the mechanism
cannot come to depend on the row."* Collapsing adds ~3,000 lines to a 5,224-line
floored module and throws that reasoning away to buy an import.


WHAT MAY NEVER BE ADDED HERE
============================
This is the one place two systems agree on what a word means, so the cost of a
wrong entry is paid by both of them and by every BREACH either emits. The rule
is the first sentence of this docstring, and these are its edges:

  1. **Nothing that decides.** No function that maps a state to a verdict, no
     predicate a caller branches on, no table a caller reads to choose between
     two outcomes. ``_validate_root``'s raise, ``adjudicate``'s ruling table,
     ``_edge_is_resolved``, ``_RESOLVED_EDGE_KINDS`` and
     ``_OVER_APPROXIMATING_EDGE_KINDS`` all stayed in the mechanism for exactly
     this reason, and they stayed even though every one of them is *about*
     names defined here. **The test is not "does it mention vocabulary", it is
     "would moving it let a branch change a verdict by editing this file
     instead of the gate".**

  2. **Nothing that reads the tree under judgement.** No ``Path`` argument, no
     ``open``, no ``subprocess``. This module has no ``pathlib`` import today
     and acquiring one is the signal that rule 1 has already been broken.

  3. **No I/O, no environment, no clock, no cache.** A record defined here must
     mean the same thing on every machine that imports it.

  4. **Nothing a single side needs.** A name used by the mechanism alone or by
     one row alone belongs in that module. A contract that accumulates
     one-sided names stops being the agreement and becomes a second home for
     whatever was inconvenient to place, and then "is it in the contract" no
     longer tells a reader anything.

  5. **No dependency on this package.** Rule 5 is rules 1-4 made mechanical: an
     ``import`` from ``claude_dispatcher`` is how a decision gets in here, and
     it is also how the cycle comes back. A future author who needs one has
     found a name that belongs on the other side of the boundary.

Also, and separately: **do not rewrite what the moved definitions mean.** Every
docstring below travelled verbatim from ``call_site_reachability``, including
its measurements, its strike-throughs and its CHOICE notes, because a contract
whose prose was re-derived during the move is a contract nobody measured.
CHOICE: unqualified ``:func:`` / ``:class:`` / ``:data:`` references inside
those docstrings that do not resolve here name members of
``call_site_reachability`` and were LEFT ALONE. Rejected alternative:
re-qualifying every one of them, which is ~100 prose edits inside text this
round is forbidden to change, to buy a cross-reference nothing in this
repository renders.


THE MANIFEST — WHAT MOVED, AND WHY EACH
=======================================
Eighteen names. Eleven are the ones ``go_reachability.py:319`` imports; seven
arrived because a moved definition's own annotation or default names them, which
is a closure and not a judgement call. **Measured under** base ``6e18fc0``,
2026-08-11, by an AST fixed-point over module-level names.

Every one of the eleven was checked against rule 1 rather than assumed. **None
carries analysis logic**: the eleven are four enums, four frozen dataclasses,
two ``str`` constants and one exception type, and the only executable statement
among them is ``AnalyzerUnavailable.__init__``, which formats a message and
stores two attributes.

The eleven the row imports:

    ``GO_REACHABILITY_SCHEMA``     ``str``. The wire-format version the row's
                                   helper stamps and the mechanism checks. One
                                   string, two readers — the definition of a
                                   contract entry.
    ``GO_REACHABILITY_PACKAGE_DIR````str``. The helper subdirectory's name.
                                   Named by ``pyproject.toml``'s package-data
                                   glob and resolved by the row; a second
                                   spelling is a wheel that ships nothing.
    ``AnalyzerFault``              ``Enum``. The named environment failures. No
                                   methods.
    ``AnalyzerUnavailable``        ``Exception``. What a row raises when it
                                   exists and could not run; carries the fault.
    ``EntrypointKind``             ``Enum``. Eight members. No methods.
    ``Root``                       ``@dataclass(frozen=True)``, four fields, no
                                   methods.
    ``Symbol``                     ``@dataclass(frozen=True)``, three fields, no
                                   methods.
    ``EdgeKind``                   ``Enum``. No methods.
    ``Edge``                       ``@dataclass(frozen=True)``, no methods.
    ``CallGraph``                  ``@dataclass(frozen=True)``, five fields, no
                                   methods.
    ``ROOT_KIND_BY_ENTRYPOINT``    ``Mapping``. Renamed from
                                   ``_ROOT_KIND_BY_ENTRYPOINT``; see the ruling
                                   below.

The seven the closure pulled in, each because a moved name would not compile
without it:

    ``AnalyzerError``      base class of ``AnalyzerUnavailable``.
    ``RootKind``           annotates ``Root.root_kind`` and is the value type of
                           ``ROOT_KIND_BY_ENTRYPOINT``.
    ``ImportsUnavailable`` a member of ``ImportEvidence``.
    ``PackageImports``     the value type of ``ImportRelation.packages``.
    ``ImportRelation``     a member of ``ImportEvidence``.
    ``ImportEvidence``     annotates ``CallGraph.package_imports``.
    ``IMPORTS_NOT_SUPPLIED`` the DEFAULT of ``CallGraph.package_imports``.

**So the brief's second question — whether ``ImportRelation`` /
``PackageImports`` / ``ImportsUnavailable`` move too — is not a judgement call
and is answered by the closure: they move, or nothing moves.** ``CallGraph``
gained ``package_imports: ImportEvidence = IMPORTS_NOT_SUPPLIED`` on
``feat/D5-import-relation``; that field's annotation and its default are
evaluated where ``CallGraph`` is defined. Leaving the import vocabulary in the
mechanism and moving ``CallGraph`` here recreates the cycle in the other
direction — the contract would import the mechanism — which is the one shape
this module may not have. Leaving ``CallGraph`` behind instead is worse: it is
one of the eleven, so the row's import stays a cycle and the extraction buys
nothing.

``ImportRelation.package_of`` travels with it and is the single exception to
"no methods". It is a lookup, not a decision: it answers *which package declares
this key* and returns ``None`` when it cannot say, and its own docstring makes
callers fail closed on that ``None``. The decision built on it —
``holes_in_scope`` — stayed.


WHAT STAYED, AND WHAT WOULD BREAK IF IT MOVED
=============================================
Everything that decides. Named explicitly, because "what stayed" is the half of
a contract that is never written down and therefore the half that erodes:

  * ``ANALYZERS``, ``validate_analyzers``, ``analyzer_for_path``,
    ``_refuse_enrolment_before_flooring``, ``_floor_relative_path``. The
    registry and its guards. Moving these moves the enrolment decision off the
    floored module and out from under the guard that reads ``FLOOR_GLOBS``.
  * ``ReachabilityAnalyzer``. The ``Protocol`` a row satisfies. It stayed
    because **the row does not import it** —
    ``go_reachability.GoReachabilityAnalyzer`` satisfies it structurally and
    says so in prose only (**measured** base ``6e18fc0``: zero code references
    in ``go_reachability.py``) — so it is a one-sided name and rule 4 applies.
    CHOICE, and the tempting alternative: move it, on the argument that an
    interface IS a contract. Rejected because it is the mechanism's own
    statement of what it will accept into ``ANALYZERS``, ``validate_analyzers``
    is the only thing that checks it, and a Protocol here would be an interface
    that this module could not enforce and that the row does not consume.
  * ``CallSiteReachabilityError``. The mechanism's refusal type, raised by
    ``_validate_root``, ``validate_analyzers`` and ``adjudicate``. Not part of
    the row's vocabulary — the row raises ``AnalyzerError`` subclasses, which
    moved.
  * ``SourceUnreadable``. A sibling of ``AnalyzerUnavailable`` under the moved
    ``AnalyzerError``, and it stayed even though its base moved — which looks
    like carrying half a hierarchy and is deliberate. **Measured** base
    ``6e18fc0``: ``go_reachability`` names it in four docstrings and imports it
    nowhere, and ``GoReachabilityAnalyzer.roots``'s own CHOICE note is that this
    method **must not raise it**. It is one-sided (rule 4). What this costs, so
    it is a decision and not an oversight: ``except AnalyzerError`` in the
    mechanism now catches one class defined here and one defined there. That is
    legal and it is checked — ``discover_roots``'s handler is exercised by live
    seals — but a future author who moves ``SourceUnreadable`` here should move
    it for the reason that it became two-sided, not for symmetry.
  * ``discover_roots``, ``build_call_graph``, ``reachable_from``,
    ``holes_in_scope``, ``check_subject``, ``adjudicate``, ``check_tree``,
    ``_validate_root``, ``_validate_subject``, ``_validate_finding``,
    ``validate_import_relation``, ``import_components``, ``_edge_is_resolved``,
    ``_RESOLVED_EDGE_KINDS``, ``_OVER_APPROXIMATING_EDGE_KINDS``, ``_RULINGS``
    and the verdict enums ``Reach``, ``UndecidedReason``, ``PathQuality``,
    ``Disposition``, ``SubjectGap`` with their records ``Seal``, ``Subject``,
    ``CallPath``, ``Finding``, ``StagedDeclaration``, ``ReachabilityReport``.

The verdict enums are the interesting case and the one a later round will
reopen, so the reasoning is recorded rather than left implicit. ``Reach``,
``Disposition`` and friends are *shaped* exactly like the vocabulary that moved
— enums with no methods — and they stayed because of rule 4 and not rule 1: the
row produces a graph and roots; the mechanism alone turns those into a verdict,
and **measured** base ``6e18fc0``, ``go_reachability.py`` imports none of them
(its seals do, from the mechanism, which is where the verdict is decided). The
day a row needs to speak about a ``Disposition`` is the day that changes, and
the honest move then is to move the name, not to import the mechanism from here.


WHAT THIS MODULE OWES THE FLOOR — AND THE COORDINATION P4 MUST DO
=================================================================
**This module must be on** ``role_protocol.FLOOR_GLOBS``, **and it is not yet.**
It holds the definition of ``EdgeKind``, ``Root``, ``CallGraph`` and
``ROOT_KIND_BY_ENTRYPOINT`` — every word a BREACH is spelled in. Unfloored, a
branch under judgement can rewrite what ``EdgeKind.INTERFACE`` means, or add a
ninth ``EntrypointKind``, in the very tree the gate is computing a call graph
over. That is the delegation-closure defect the 2026-08-09 ruling closed for
``call_site_reachability`` itself, relocated one import away — and relocated
into a file whose whole purpose is that two systems trust it.

The glob that is owed, spelled out so nobody has to re-derive it::

    "**/src/claude_dispatcher/call_site_contract.py",

**PATH-QUALIFIED, a FILE glob, no ``**`` tail.** Measured 2026-08-11 under this
repository's own matcher (``role_protocol.first_matching_glob``, i.e.
``risk._glob_to_regex``) at base ``6e18fc0``, against six probe paths, because
every one of these spellings has been written by somebody in a previous round:

  * ``**/src/claude_dispatcher/call_site_contract.py`` matches
    ``src/claude_dispatcher/call_site_contract.py`` and its nested-checkout
    spelling ``nested/repo/src/claude_dispatcher/call_site_contract.py``, and
    nothing else. **This is the entry.**
  * ``**/call_site_contract.py`` — basename-only — also matches
    ``vendor/thirdparty/call_site_contract.py`` and
    ``site-packages/claude_dispatcher/call_site_contract.py``. A floor has no
    override, so it cannot buy those back.
  * ``**/src/claude_dispatcher/**`` — the package subtree — also matches
    ``plan.py`` and ``blast_radius.py``, which several seals require to stay
    writable, and a ``**`` tail is exactly what ``_floor_glob_named_by``
    refuses, so it buys no plan-time reach either.
  * ``**/src/claude_dispatcher/{call_site_reachability,call_site_contract}.py``
    matches **none** of the six probes. This engine has no brace expansion; the
    alternation is literal text. A floor written that way is a silent no-op
    that reads as protection.
  * ``**/src/claude_dispatcher/call_site_contract.py/**`` matches none of the
    six. A ``**`` tail on a FILE is not a subtree, it is a path with a
    directory separator this file will never have.

**This file does not write that glob, and the reason is measured rather than
procedural.** The landing is a THREE-part edit and only the first part is a P1
scaffold's to make. **Measured under** ``feat/D5-contract-module``, base
``6e18fc0``, 2026-08-11, whole suite, ``PYTHONPATH=src python3 -m pytest -q -o
addopts=""``, with the TypeScript parser vendored (an unvendored checkout is 87
unrelated failures in ``tests/test_ts_comparator.py`` and is not a baseline):

  * baseline, before this round — **2430 passed, 0 failed, 13 skipped**;
  * **part 1**, this commit: the extraction, both modules rewired, no floor edit
    — **2429 passed, 1 failed**. The one red is
    ``tests/test_d5_floor.py::test_every_module_a_d5_decision_reaches_is_already
    _on_the_floor``, and its message is
    ``call_site_contract (imported by call_site_reachability at module level)``.
    That seal walks the mechanism's module-level in-package imports and requires
    every module it reaches to be on the floor. **It is not collateral damage.
    It is the seal written to detect exactly this, doing exactly that, on the
    first delegation D5 has grown since it was written** — its own docstring
    says "its value is the NEXT delegation: a D5 that grows an import of an
    unfloored module reddens here, naming it";
  * **part 2**, appending the glob to ``FLOOR_GLOBS`` and changing nothing else
    — **2429 passed, 1 failed**, and it is a DIFFERENT row:
    ``tests/test_role_protocol_floor.py::test_the_floor_is_exactly_the_written_
    out_set_of_globs``, because ``_FLOOR_ROWS`` is a set difference against
    ``FLOOR_GLOBS`` and a glob with no written-out row is unsealed;
  * **part 3**, writing the rows into ``_FLOOR_ROWS`` and
    ``_FLOOR_x_ROLE_ROWS`` with a real probe path — green. **Predicted
    (unmeasured) under** base ``6e18fc0``: part 3 is a SEAL edit, seals are
    amended only by P4, and this scaffold did not make it in order to measure
    it.

So parts 2 and 3 are one indivisible P4 edit — either alone is red — and a P1
that performed part 2 would hand P4 a red branch and a seal file it must edit
anyway. The two reds above are recorded so the next author knows which one is
theirs. Landing part 2 here would also collide head-on with the parallel P4
round that is appending two other globs to the same tuple.

**CHOICE, and it is the one that matters, because there was a shape that would
have landed GREEN and it is wrong.** The extraction could have been run the
other way: leave the vocabulary in ``call_site_reachability`` — which is already
on the floor — and move the DECISION out into a new ``call_site_gate.py``
holding ``ANALYZERS``, ``validate_analyzers``, ``check_subject``, ``adjudicate``
and ``check_tree``. The row would then import the (unchanged, floored) vocabulary
module, the cycle would break just as well, ``call_site_reachability``'s
module-level imports would not grow, and
``test_every_module_a_d5_decision_reaches_is_already_on_the_floor`` would stay
green — no floor edit, no P4 coordination, no red.

**Rejected, because green is the wrong thing to optimise here and the seal is
right.** That shape puts the module that decides a ``Disposition.BREACH`` in a
brand-new file that is off the floor, and keeps the floored file for the part
that does not decide — the exact inversion of what ``FLOOR_GLOBS`` is for. It
would satisfy the seal by moving the gate out from under the seal's gaze, which
is the "silent no-op that reads as protection" failure the floor comment three
entries up already names about glob spellings, arriving instead through the
module layout. It would also make false, in one commit, every sentence in
``role_protocol.py``, ``tests/test_d5_floor.py`` and this repository's floor
rationale that identifies ``call_site_reachability`` as "the module that
decides, per seal, whether a subject is reachable from a production root". The
direction this round took costs one red and one P4 round; that one costs the
floor's meaning.

Owed alongside, and NOT done here for the same reason: nothing. **Measured**
base ``6e18fc0`` — this module's delegation closure is empty (it imports no
in-package module), so flooring it adds no further member to D5's closure, and
``role_protocol`` does not import it, so ``_DELEGATION_TARGETS`` in
``tests/test_floor_closure.py`` needs no row.


HOW THIS COMPOSES WITH THE PARALLEL P4 — MEASURED, NOT MERGED
=============================================================
``feat/D6-floor2`` at ``131e044`` is the round landing the other two floor globs
(``**/src/claude_dispatcher/go_reachability.py`` and
``**/src/claude_dispatcher/go_call_reachability/**``) and widening
``_refuse_enrolment_before_flooring`` to check an enrolled row's HELPER
directory as well as its module. It shares this branch's base. Neither branch
was merged into the other; the composition was measured with
``git merge-tree --write-tree`` and the resulting tree materialised in a
throwaway checkout, on 2026-08-11.

**One textual conflict, three lines, in this module's counterpart.** The two
branches both edit ``call_site_reachability``'s import block: that round adds
``import sys``, this one drops ``field`` from ``from dataclasses import
dataclass, field`` because every ``field()`` call went out with ``Symbol``. The
resolution is ``import sys`` plus ``from dataclasses import dataclass``, and it
is checkable — ``= field(`` appears zero times in the composed mechanism.
``go_reachability.py``, ``role_protocol.py`` and all three seal files
auto-merge.

**The two rounds' central edits do not fight, and that is measured rather than
hoped.** That round introduces ``_HELPER_PACKAGE_DIRS = (GO_REACHABILITY_PACKAGE_DIR,)``
and relocates the ``_refuse_enrolment_before_flooring()`` CALL below it. Its
diff anchors that insertion on ``GO_REACHABILITY_PACKAGE_DIR``'s definition —
which this round moved here. In the composed tree the binding survives at its
new place, reads the name through this module's re-export at the top of the
mechanism, and the guard call still follows it. ``_HELPER_PACKAGE_DIRS`` belongs
in the MECHANISM and not here, by rule 1: the guard reads it to decide whether
to refuse an import.

Composed suite, **measured** 2026-08-11 with the TypeScript parser vendored:

  * this branch + ``131e044`` — **2430 passed, 1 failed**, and the failure is
    the same single row, ``test_every_module_a_d5_decision_reaches_is_already_
    on_the_floor``, still naming ``call_site_contract``. Flooring
    ``go_reachability`` did not floor this module and was never going to;
  * the same tree with the owed glob appended after that round's pair —
    **2430 passed, 1 failed**, and it is again ``test_the_floor_is_exactly_the_
    written_out_set_of_globs``. The three-part sequence above is unchanged by
    the composition, so whichever P4 lands last owns parts 2 and 3 for a floor
    tuple that is by then eleven entries, not nine.

The third parallel branch, ``feat/D6-supply-imports`` (making ``graph()``
supply ``package_imports``), is still at the shared base and has no committed
diff to measure against. Predicted (unmeasured): it edits
``GoReachabilityAnalyzer.graph`` in ``go_reachability.py`` and constructs
``ImportRelation`` / ``PackageImports`` — names it already imports and whose
DEFINITIONS moved here without changing. Its import block will conflict with
this round's, textually and once, in the same way the P4's did.


THE RULING ON ``_ROOT_KIND_BY_ENTRYPOINT``
==========================================
It was private and imported across a module boundary — a pre-existing smell this
move surfaces rather than creates. **Ruling: it is PUBLIC here, spelled
``ROOT_KIND_BY_ENTRYPOINT``, and it stays a Mapping.** The underscore does not
cross the boundary: ``go_reachability`` imports the public name.

**A function was considered and rejected, and the reason is rule 1 above rather
than convenience.** ``root_kind_for_entrypoint(kind) -> RootKind`` is the
tidier-looking answer and it would make both call sites total — today
``_validate_root`` reads ``.get(kind)`` and turns ``None`` into a named
``CallSiteReachabilityError``, while ``go_reachability`` reads ``[kind]`` and
would get a bare ``KeyError`` for a ninth member. But:

  1. **The raise is the decision, and it belongs to the mechanism.** A function
     here that refused an unclassifiable kind would need
     ``CallSiteReachabilityError``, which stayed; a contract module that raises
     the gate's refusal type has started deciding, and this file's own rule 1
     forbids it. A table says *which kind is which*. ``_validate_root`` decides
     *what to do when the table has no row* — including the senior half of the
     derivation, ``seal_verify.is_test_path`` over the declaring file, which a
     function taking only a ``kind`` could never express.
  2. **It would change behaviour, which a scaffold may not.** Both call sites
     would change shape and ``go_reachability``'s ``KeyError`` would become
     something else.
  3. **It would force seal edits, which are P4's.** **Measured** base
     ``6e18fc0``: three executable seal references, all
     ``csr._ROOT_KIND_BY_ENTRYPOINT`` and all subscript reads
     (``tests/test_go_reachability.py:1157``, ``:1158``, ``:2469``), plus three
     mutation-probe string literals in ``tests/test_call_site_reachability.py``
     that require it to be a dict with no default.

Those three seal sites are also why ``call_site_reachability`` keeps
``_ROOT_KIND_BY_ENTRYPOINT = ROOT_KIND_BY_ENTRYPOINT`` — the SAME object, not a
copy, so ``csr._ROOT_KIND_BY_ENTRYPOINT[k] is ROOT_KIND_BY_ENTRYPOINT[k]`` and
the seals stay true rather than merely green. CHOICE: the alias is a
compatibility shim and is OWED REMOVAL, by P4, in the round that repoints those
three lines. Rejected alternative: repointing them in this commit, which is a
P1 editing a sibling unit's seals to keep its own suite green — the thing this
process exists to stop, and the thing ``IMPORTS_NOT_SUPPLIED``'s own note
refused one round ago for the same reason.


THE SEAL BLAST RADIUS
=====================
**Zero seal files are edited by this commit, and that is a measured property of
the shape chosen, not an accident.** ``call_site_reachability`` re-exports all
eighteen names, so every existing ``from claude_dispatcher.call_site_reachability
import (...)`` and every ``csr.<Name>`` attribute read keeps resolving — to the
same object, since a re-export binds rather than copies.

**Measured under** base ``6e18fc0``, 2026-08-11, by AST over ``tests/``,
``src/``, ``scripts/`` and ``tools/`` — the files that import a name which moved:

    ``tests/test_call_site_reachability.py``  13 of the 18, plus ``import ... as
                                              csr``; 26 further names that
                                              stayed
    ``tests/test_go_reachability.py``          9 of the 18, plus ``csr``; 6
                                              names that stayed
    ``tests/test_d5_floor.py``                 ``csr`` only, no from-imports
    ``src/claude_dispatcher/go_reachability.py`` the 11 — the only non-test
                                              importer, and the one this round
                                              repoints

Nothing under ``scripts/`` or ``tools/`` imports either module. So the coupling
to name now rather than discover later is exactly one: **if P4 ever removes the
re-export from ``call_site_reachability``, two seal files must be repointed in
the same commit** — 13 names in ``tests/test_call_site_reachability.py`` and 9
in ``tests/test_go_reachability.py``, 22 import sites, plus the three
``csr._ROOT_KIND_BY_ENTRYPOINT`` reads above.

CHOICE (the re-export could have been omitted, forcing the seals to import from
here): **kept.** Rejected alternative costs 22 seal-file import edits by a P1,
buys the property that a reader of a seal sees which module defines the name,
and would have been worth it in a round that owned those files. It does not
belong to this one.


WIRING
======
``ANALYZERS`` is still ``()``. This round unblocks enrolment and does not
perform it: the row is still not in the registry, no call site is added, and the
two pending-state tripwires that pin the empty registry are untouched and green.
Enrolment needs the floor entry above first, which is the ordering
``_refuse_enrolment_before_flooring`` enforces at import and which this module
does not get to shortcut by being new.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping

__all__ = [
    "AnalyzerFault",
    "AnalyzerError",
    "AnalyzerUnavailable",
    "GO_REACHABILITY_SCHEMA",
    "GO_REACHABILITY_PACKAGE_DIR",
    "RootKind",
    "EntrypointKind",
    "Root",
    "ROOT_KIND_BY_ENTRYPOINT",
    "Symbol",
    "EdgeKind",
    "Edge",
    "ImportsUnavailable",
    "PackageImports",
    "ImportRelation",
    "ImportEvidence",
    "IMPORTS_NOT_SUPPLIED",
    "CallGraph",
]


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
        production. The declaring file is the SENIOR half: a kind the table
        calls production, declared in a test file, is a **TEST root**. A ``func
        init()`` in a ``z_test.go`` runs — in the test binary — and everything
        it reaches is genuinely reached under test. See :func:`_validate_root`
        for the derivation and for what refusals remain.

        **STRUCK on ``feat/D5-relation-body``, 2026-08-11, base ``3eedd07``,
        and recorded rather than silently deleted, because the code implemented
        it for as long as it stood:** this paragraph used to end "a production
        kind found in a test file is a :class:`CallSiteReachabilityError`
        rather than a coin flip — a ``func main()`` inside ``_test.go`` is a
        tree this module does not understand, and saying so is cheaper than
        being wrong in either direction." It contradicted
        :func:`_validate_root`'s own docstring, which has contracted the
        two-half derivation from the start, and it was measurably wrong rather
        than merely cautious: it dropped D6's ``<vars:test>`` root and every
        ``init`` in a ``_test.go``, and a dropped root under-approximates into
        :attr:`Reach.FROM_NEITHER`, which RAISES for a seal-derived subject.
        The reading it protected against — a ``GO_MAIN`` inside
        ``contract_seal_test.go`` silently certifying the whole test closure as
        FROM_PRODUCTION — is still refused, and by the derivation itself: such
        a root derives TEST, so a row asserting PRODUCTION for it disagrees
        with the derivation and is refused. The mirror, a ``TEST_FUNCTION``
        outside the tests, remains a refusal for a reason that is not
        symmetric; :func:`_validate_root` gives it.
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


# RENAMED from ``_ROOT_KIND_BY_ENTRYPOINT`` on ``feat/D5-contract-module``,
# 2026-08-11, base ``6e18fc0``. The table was private and imported across a
# module boundary; the ruling on that, and the reason it is a Mapping and not a
# function, are in this module's docstring. Nothing else about it changed — the
# eight rows, the absence of a default and the totality the raise in
# ``call_site_reachability._validate_root`` depends on are all as they were.
# ``call_site_reachability`` binds the old private name to THIS OBJECT so the
# three seal reads of ``csr._ROOT_KIND_BY_ENTRYPOINT`` stay true; that alias is
# a shim and is owed removal.
#: Which :class:`RootKind` each :class:`EntrypointKind` yields. A TABLE and not
#: a chain of ``if``\ s, so that a member added without visiting this file is
#: absent from it and :func:`_validate_root` raises rather than defaulting — the
#: step 3 of ``skills/explicit-state.md`` that actually bites. ``TEST_FUNCTION``
#: is the only kind on the TEST side. That asymmetry used to be offered as the
#: reason the struck fallback's TEST half was a derivation rather than a guess;
#: the ruling was that a constrained guess is still not a derivation, so the
#: table now says only what it is — the derivation of ``root_kind`` from
#: ``kind``.
#:
#: **It is HALF of :func:`_validate_root`'s authority and not the whole of it**
#: (amended on ``feat/D5-relation-body``, 2026-08-11, base ``3eedd07``, where
#: the sentence used to read "which is the whole of ``_validate_root``'s
#: authority"). The other half is ``seal_verify.is_test_path`` over the
#: declaring file, and it is SENIOR to this table: a kind named PRODUCTION
#: here, declared in a test file, derives TEST. This table is what that
#: derivation falls back to for a production file, and it is still the thing a
#: ninth member added without visiting this file falls off — the raise above it
#: is unchanged.

ROOT_KIND_BY_ENTRYPOINT: Mapping[EntrypointKind, RootKind] = {
    EntrypointKind.GO_MAIN: RootKind.PRODUCTION,
    EntrypointKind.GO_INIT: RootKind.PRODUCTION,
    EntrypointKind.GO_PACKAGE_VAR: RootKind.PRODUCTION,
    EntrypointKind.PYTHON_CONSOLE_SCRIPT: RootKind.PRODUCTION,
    EntrypointKind.PYTHON_MODULE_MAIN: RootKind.PRODUCTION,
    EntrypointKind.PYTHON_SCRIPT_MAIN: RootKind.PRODUCTION,
    EntrypointKind.PYTHON_IMPORT_TIME: RootKind.PRODUCTION,
    EntrypointKind.TEST_FUNCTION: RootKind.TEST,
}


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
class ImportsUnavailable:
    """**The named state "this analyzer does not supply the import relation".**

    Requirement 2 of the brief, and the whole reason this is a CLASS and not a
    ``None`` and not an empty :class:`ImportRelation`:

      an empty relation reads as "no package imports anything", which makes
      every package its own component, which silently MAXIMISES the narrowing
      of step 3's hole set. That is fail-open, and it is the one direction this
      mechanism refuses.

    **Measured under ``feat/D5-import-relation``, base ``f4c7c46``, 2026-08-11,
    and this is why the refusal has to be a type rather than a convention:**

      * on the acceptance tree the fail-open and the truth are INDISTINGUISHABLE
        — 2 packages, **0** in-tree import edges, so the true component count
        and the empty-relation component count are both 2 and both answer 4 of
        7. A seal written only against this fixture cannot tell an analyzer that
        computed the relation from one that returned nothing;
      * on ``evenplay-mono/apps/website-public-api`` (12 Go packages, 25
        undirected in-tree import edges) the truth is **1** component and the
        empty relation says **12**. Every hole in that module would be scoped
        away from every subject outside its own package, on evidence nobody
        collected;
      * on ``evenplay-mono/apps/platform-domain/core`` (33 packages, 93 edges)
        the truth is **6** components — one of 28 and five singletons — and the
        empty relation says **33**.

    So: an analyzer that cannot answer says so HERE, by name, with a ``reason``
    it is required to write; and the consequence, contracted at
    :func:`holes_in_scope`, is **no narrowing at all** — step 3 keeps its
    whole-tree hole set and behaves exactly as it does today. The absent
    relation degrades to the CURRENT, SEALED behaviour and never to the
    maximally-narrowed one.

    ``reason``
        Required, no default. Why the relation is absent, in a sentence a report
        can print: "no analyzer ran over this tree", "the Go row does not
        compute imports yet", "the toolchain could not be reached". Required
        because the three are different problems with different remediations,
        and a bare "unavailable" makes them one.

    CHOICE (the design could have spelled the absence as ``None`` on the field,
    or as an ``ImportCoverage`` enum member beside the relation): a distinct
    RECORD carrying a required reason. Rejected alternatives and why:

      * ``None`` — it is what an author writes when they have not thought about
        the field, and it is what a partially-migrated construction site leaves
        behind. The absence must cost a class name and a sentence, so that a
        body cannot arrive at it by omission;
      * a three-state enum ``COMPLETE`` / ``PARTIAL`` / ``UNAVAILABLE`` beside
        an always-present relation — ``PARTIAL`` is derivable from
        :attr:`PackageImports.unplaced_imports` being non-empty, so the enum
        would be a second source of truth for a fact the data already carries,
        and the two could disagree. Two answers to "was this import placed" is
        exactly the drift a registry exists to prevent.
    """

    reason: str


@dataclass(frozen=True)
class PackageImports:
    """One package: what it declares, and what it can NAME.

    A node of the import graph. The rule this serves (operator ruling relayed
    by the P4, restated here so a body does not have to go looking) is that a
    hole stays in scope for subject ``S`` unless this POSITIVE claim can be
    discharged:

        *this hole cannot be the missing call site, because no execution frame
        in the hole's package can hold ``S``'s value and no code in the hole's
        package can name ``S``.*

    A function value crosses a package boundary by exactly three routes — call
    argument, call return, or a package-level variable both packages can see —
    and each of the three requires an IMPORT. So the claim holds exactly when
    the two packages are in different connected components of the tree's
    **undirected** import graph.

    ``package``
        This package's identity, spelled as the qualifier half of the
        :attr:`Symbol.key` its declarations carry — for Go,
        ``github.com/yourorg/claude-workflow/gates/cmd/gates``. **The identity
        is the KEY QUALIFIER and never the import path**, and the two are not
        the same string; see :func:`ImportRelation.package_of` and the note on
        ``go_reachability._import_path_qualifiers``.
    ``symbols``
        Every :attr:`Symbol.key` declared in this package, synthetic root
        symbols included. This is what makes the relation usable from
        :func:`check_subject`, which holds keys and not packages: it has
        ``subject.key`` and ``hole[0].key`` and nothing else, and it must not
        split a key into a package by string surgery. A Go method key is
        ``…/classify.(*Config).Match`` — the package qualifier is not
        "everything before the last dot", and a layer that guessed would place
        methods in a package called ``…/classify.(*Config)``, which is in no
        component and would fail closed on every method in the repository.
        Membership is DATA the analyzer already has (it knows which unit emitted
        each symbol) and is never re-derived here.
    ``imports``
        The identities of the IN-TREE packages this package can name, taken from
        its import statements. Directed as recorded; :func:`import_components`
        reads it undirected, because a value flows both ways across one import
        (an argument goes in, a return value comes out).
    ``unplaced_imports``
        **One entry per import this analyzer could neither place onto a package
        of this tree NOR establish as out-of-tree**, each a detail string a
        human can act on. NON-EMPTY IS AN EDGE TO EVERY PACKAGE, never an
        absence — see :func:`import_components`. An import whose target could be
        anything can be an import of ``S``'s package, so the positive claim
        above cannot be discharged against any ``S`` at all.

        What a body must do when an import cannot be resolved: **record it here
        and stop**. Not drop it (that is the absence the rule forbids), not
        guess a target (a wrong edge is a wrong component in the permissive
        direction if it is missing and merely conservative if it is spurious —
        but a guessed edge that is missing is unrecoverable), and not raise (one
        unplaceable import in one file must not take the whole check down; that
        is :func:`build_call_graph`'s own recorded-not-raised discipline).
    ``external_import_count``
        How many of this package's imports were placed OUT of the tree — the
        standard library, a module dependency. **The non-vacuity field of this
        record**, and it earns its place for :attr:`CallGraph.unresolved_calls`'
        exact reason: a relation reporting zero ``imports`` and zero
        ``unplaced_imports`` for every package is either a tree of genuinely
        isolated packages or an analyzer that is not reading import statements,
        and those two must not be the same value. **Measured on the acceptance
        tree under ``feat/D5-import-relation``, base ``f4c7c46``, 2026-08-11:
        41 for ``cmd/gates`` and 39 for ``cmd/iterate``, against 0 in-tree
        imports and 0 unplaced.** A seal that pins 41/39 falsifies "the analyzer
        is not counting"; a seal that pins only the two zeros does not.

    CHOICE (``external_import_count`` could have been the import PATHS): a
    COUNT. Rejected alternative — the paths — because nothing downstream reads
    them, they are unbounded in a vendored tree, and the count alone falsifies
    the one claim the field exists to falsify. A body that later needs the paths
    for a report should widen this field rather than add a second one.

    CHOICE (an out-of-tree import could have been treated as unplaceable, i.e.
    as an edge to everything): **a placed import to a package outside the tree
    contributes NO edge.** The dependency is not in the tree, so it declares no
    :class:`Symbol` here and cannot be ``S``'s package. Rejected alternative —
    counting every stdlib import as an unknown — because on the acceptance tree
    that is all 80 imports and the relation would collapse to one component on
    every tree ever analysed, which is a mechanism that is never consulted. The
    residual risk is named and is real: a dependency that itself imports THIS
    tree's module and hands a value back is a route this relation does not
    model. It is out of reach for a source-only analyzer, it needs a published
    module and a circular dependency to occur, and the ``REFERENCE`` edge that
    :class:`CallGraph`'s both-ends CHOICE already keeps is what covers the
    common shape of it.
    """

    package: str
    symbols: frozenset[str]
    imports: frozenset[str]
    unplaced_imports: tuple[str, ...]
    external_import_count: int


@dataclass(frozen=True)
class ImportRelation:
    """One tree's packages and the imports between them.

    ``packages``
        Package identity -> :class:`PackageImports`. Every package the analyzers
        read, and — enforced by :func:`validate_import_relation` — every symbol
        in the graph belongs to exactly one of them.

    **THE SHAPE CHOICE, which is question 1 of the brief.** The P4 recorded two
    acceptable shapes and this is the first: an IMPORT/VISIBILITY relation, with
    the component computation living in D5. **Rejected alternative: a per-hole
    CANDIDATE-TARGET SET with an explicit unbounded member** — for each entry in
    :attr:`CallGraph.unresolved_calls`, the set of symbols the missing call
    could be, or a named ``UNBOUNDED``. Four reasons, in ascending order of how
    much they should bind the next author:

      1. **It asks the analyzer for a dataflow answer that D6 measured as
         unavailable.** Every one of the acceptance tree's holes is a call
         through a FUNCTION VALUE — measured on this base, 2 in the production
         closure, both ``cancel`` in ``cmd/gates/main.go``, plus 1 outside it —
         and D6's adjudication measured that ``go/types`` moves the verdict on
         none of them, because a type is not an identity. A candidate set over
         those holes is ``UNBOUNDED`` or it is a guess, so the shape would carry
         an ``UNBOUNDED`` member on every hole this repository actually has and
         would answer 0 of 7. The import shape answers **4 of 7 on the same
         tree, measured** (:func:`holes_in_scope`).
      2. **It puts the RULE in the analyzer instead of in the judge.** The
         ruled rule — undirected, unresolved-import-counts-as-an-edge — is a
         ruling about JUDGEMENT, not a fact about a language. Under the
         candidate-set shape every language row re-derives it, so there would be
         one chance per row to get the undirected half or the unresolved half
         wrong, and a row that got either wrong would silently NARROW harder,
         which is the fail-open direction. Under this shape each row supplies
         FACTS (its import statements) and D5 applies the rule once, where one
         seal can pin it.
      3. **``call_site_reachability.py`` is on ``FLOOR_GLOBS`` and
         ``go_reachability.py`` is not.** The narrowing decision moves an
         ABSTAIN to a BREACH and back; it belongs behind the floor. Putting the
         candidate sets in the analyzer would put the whole of that decision in
         a module four of the five roles may rewrite while being judged by it.
         This reason is decisive on its own.
      4. **The shapes are not equally cheap to be wrong in.** A wrong import
         edge merges two components and abstains MORE. A wrong candidate set
         omits the real target and abstains LESS.

    The candidate-set shape has one property this one had to be given
    deliberately, and the brief is right to flag it: it makes "we cannot bound
    this hole" a NAMED STATE rather than an absence. That property is imported
    wholesale rather than lost — twice, at two different granularities:
    :class:`ImportsUnavailable` names "no relation at all" and
    :attr:`PackageImports.unplaced_imports` names "this package's reach cannot
    be bounded". Neither is spellable as an empty container.

    ================================================================
    THIS RELATION SUBSUMES ``go_reachability._import_path_qualifiers``.
    DO NOT BUILD A SECOND DERIVATION OF IMPORT PATHS.
    ================================================================
    Stated at this volume because two mechanisms deriving import paths
    differently is how this gets wrong twice, in two directions that cancel in
    the reports and not in the truth.

    D6's body found and repaired a live defect: a Go symbol's key is qualified
    ``<module_path>/<tree-relative dir>`` while its real import path is
    ``<module_path>/<dir relative to the nearest go.mod>``, so a cross-package
    in-tree call arrives with a callee key matching no symbol and
    :class:`CallGraph`'s both-ends rule DROPS a real production edge — a false
    BREACH, the direction anti-requirement 2 forbids. ``_import_path_qualifiers``
    computes import path -> key qualifier per unit and ``_join_callee`` rewrites
    the callee through it, longest prefix first.

    That map is exactly this relation's node table. Its VALUES are
    :attr:`PackageImports.package` — the key qualifier, which is the identity
    this relation uses — and its KEYS are the strings an import statement is
    written with, which is precisely what a body must match an import against to
    place it. **Measured under ``feat/D5-import-relation``, base ``f4c7c46``,
    2026-08-11**, on the acceptance tree it returns the two pairs

        …/gates   -> …/gates/cmd/gates
        …/iterate -> …/iterate/cmd/iterate

    and those two values are exactly the two package identities the measured
    2-component partition is over.

    So the obligation on the body is not "write an import-path derivation", it
    is **"build the relation FROM the one that exists"** — hoist
    ``_import_path_qualifiers`` to serve both callers, or call it, but do not
    re-derive. A body that writes a second one gets the cancellation for free:
    ``_join_callee`` would join an edge between two packages while this relation
    reported no import between them, i.e. the call graph would say the packages
    talk and the import graph would say they cannot, and step 3 would scope away
    a hole that a kept edge proves is in reach. Nothing would be red. A seal
    author should pin the two node sets as EQUAL — the values of
    ``_import_path_qualifiers`` and the keys of :attr:`ImportRelation.packages`
    — because that single row is what makes the shared derivation checkable
    rather than merely intended.

    What this relation adds beyond that map, and therefore why it is a
    superset rather than a duplicate: the qualifier map answers "what is this
    package called", and the relation additionally carries which in-tree
    packages each one IMPORTS, which symbols each one declares, which of its
    imports could not be placed, and how many were placed outside the tree.
    """

    packages: Mapping[str, PackageImports]

    def package_of(self, key: str) -> str | None:
        """Which package declares ``key``, or None if this relation cannot say.

        **IMPLEMENTED and not stubbed, on :func:`analyzer_for_path`'s precedent
        verbatim: it is the single answer site for "which package is this
        symbol in", and a seal that re-spelled the lookup could drift from the
        implementation with both of them green.** It is also the one place that
        could be tempted into string surgery on a :attr:`Symbol.key`, and the
        way to prove this module never does that is to write the lookup that
        does not.

        ``None`` is a real answer and a caller must fail CLOSED on it: a key
        this relation cannot place is a key whose component is unknown, and an
        unknown component may be the subject's. See :func:`holes_in_scope`.

        Linear in the number of packages, not in the number of symbols, because
        the membership sets are hashed. A body that finds this hot should build
        the reverse index INSIDE this record at construction; it must not build
        one beside it, for the reason the first paragraph gives.
        """
        for package in self.packages.values():
            if key in package.symbols:
                return package.package
        return None


#: ``ImportRelation`` when an analyzer computed one, ``ImportsUnavailable`` when
#: none did. **A union and never an Optional**, so that the absence has to be
#: constructed by name; see :class:`ImportsUnavailable`.
ImportEvidence = ImportRelation | ImportsUnavailable


#: The value :attr:`CallGraph.package_imports` carries when nobody supplied a
#: relation, and the DEFAULT of that field.
#:
#: CHOICE (the field could have been REQUIRED, with no default): defaulted, to
#: the REFUSAL. This is the one place in this round that has to argue with a
#: standing D5 ruling, so it argues with it directly rather than around it.
#: :func:`check_subject`'s ``roots`` parameter had its default STRUCK in P4
#: round 2, on the sentence "a missing argument is a signature defect; inventing
#: the value is a verdict defect". That ruling stands and it does not reach
#: here, because the two defaults point in opposite directions:
#:
#:   * the struck default INVENTED EVIDENCE — a synthesised :class:`Root` record
#:     that bypassed :func:`_validate_root` and could mint a ``GO_MAIN`` root in
#:     a test file. A caller with no evidence got a judgement built on a fact
#:     nobody established;
#:   * this default invents the CONFESSION. A caller with no evidence gets
#:     "there is no import evidence", which is true, and whose contracted
#:     consequence is no narrowing — i.e. today's sealed behaviour, unchanged.
#:
#: The rejected alternative was measured rather than argued: making the field
#: required breaks **4** construction sites on this base, of which **2 are in
#: seal files** (``tests/test_go_reachability.py`` and
#: ``tests/test_call_site_reachability.py``) — measured under
#: ``feat/D5-import-relation``, base ``f4c7c46``, 2026-08-11. A P1 scaffold that
#: edits a sibling unit's seals to keep its own suite green has done the thing
#: this process exists to stop. The property a required field buys — every
#: construction site must THINK — is bought instead at the layer that matters,
#: by the row-level ``supplies_import_relation`` claim contracted on
#: :class:`ReachabilityAnalyzer` and the cross-check it licenses in
#: :func:`build_call_graph`.
IMPORTS_NOT_SUPPLIED = ImportsUnavailable(
    reason=(
        "no analyzer supplied an import relation for this tree, so no hole can "
        "be scoped away from any subject and step 3 keeps its whole-tree hole "
        "set"
    )
)


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
    ``package_imports``
        The tree's :class:`ImportRelation`, or the named
        :class:`ImportsUnavailable` when no analyzer supplied one. **The field
        that makes step 3's hole set scopable to a subject**, added on
        ``feat/D5-import-relation``, 2026-08-11. It rides on the GRAPH and not
        on a new parameter of :func:`check_subject`, because
        :func:`check_subject` already receives the graph and because the
        relation is a fact about the same tree the edges came from — a second
        channel carrying facts about one tree is two things to keep in step.

        Defaulted to :data:`IMPORTS_NOT_SUPPLIED`, which is the REFUSAL and not
        an empty relation; the argument for defaulting it at all, and the
        measurement behind it, are on that constant. Nothing reads this field
        yet: :func:`holes_in_scope` is the seam and it is a stub.

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
    package_imports: ImportEvidence = IMPORTS_NOT_SUPPLIED
