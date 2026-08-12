r"""D5 — call-site reachability: does production call this?

P4 FLOOR ROUND (2026-08-11, unit D6, ``feat/D6-floor2``) — THE GUARD'S SUBJECT
==============================================================================
**NOT ENROLLED AS OF THIS ROUND.** :data:`ANALYZERS` is ``()``, nothing is
wired, and the pending-state tripwires
(``test_nothing_in_this_commit_enrols_the_go_row``,
``test_analyzers_is_empty_and_no_path_in_any_tree_can_be_analyzed``) are green
before and after. **The count here said "two" and it is THREE — P4,
``feat/D6-enrol2``, ``d8fd825``, 2026-08-11**, measured by enrolling in a clone
rather than by grepping for ``ANALYZERS``; the third is
``test_an_unenrolled_mechanism_abstains_rather_than_passing_everything``, in
this module's own seal file, which names no registry in its title.
What changed in THIS round is ONE production property and it is a fix, not
a feature: :func:`_refuse_enrolment_before_flooring` used to derive
``_floor_relative_path()`` from ``Path(__file__)`` — its own path and nothing
else — so it would have permitted enrolment with the ROW's defining module and
the row's Go helper subtree both writable by the branch under judgement.
Measured at ``feat/D5-relation-body`` @ ``6e18fc0``: ``go_reachability.py`` and
both entry points under ``go_call_reachability/`` were off ``FLOOR_GLOBS``, and
neither this guard nor :func:`validate_analyzers` looked at either. Both globs
land in the same round; the guard's subject is now
:func:`_paths_the_enrolled_registry_is_judged_from`. The None-is-a-skip
conjunct is carried forward for all three kinds of path at once — see there and
see ``test_the_guard_judges_the_rows_own_module_and_its_helper``.

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
The body raised three such places and **all three are now RULED (P4, round 2,
2026-08-11)**; each site carries its ruling and none of them was closed by
weakening the contract that raised it. **Two of the three are IMPLEMENTED on
``feat/D5-body2``, 2026-08-11; the third is deliberately not, and says why:**

  * :func:`_test_id` — **the PROTOCOL grows the method.** ``test_id`` is a
    per-language spelling by the contract's own words, and a per-language fact
    computed centrally is the second answer site this module refuses
    everywhere else. The derivation stays as a recorded INTERIM only until a
    row can supply one. See :attr:`Seal.test_id`. **NOT implemented this
    round, on the P4's own escalation:** requiring ``test_id`` in
    :func:`validate_analyzers` reddens every row that builds the seal file's
    analyzer double, and what a Go row's ``test_id`` RETURNS is a claim about
    Go's spelling that a body may not write on the seal author's behalf. It
    needs one round carrying the production edit and the double together. The
    interim and its written expiry are untouched.
  * the ``roots`` parameter of :func:`check_subject` — **the dispute is upheld
    and the FALLBACK is struck. DONE.** The scaffold's signature really was
    defective; the repair is to require the argument, never to invent the value
    when it is absent. ``roots`` is required with no default, the synthesising
    fallback and its hand-maintained language→entrypoint-kind table are
    deleted, :func:`_witness` raises on a chain whose origin no supplied
    :class:`Root` names, and :func:`_has_no_production_root`'s empty-``roots``
    branch — dead once the default went — is deleted rather than left
    unreachable. See there.
  * :func:`adjudicate` — **the sentence stands and its ADDRESS changes. DONE.**
    The seals were right; the scaffold filed the raise at a layer that reads
    neither field it validates, which is R2's error exactly, so R2's answer
    applies: constructor postcondition plus acting-layer precondition.
    :func:`_validate_finding` is called on every ``return`` in
    :func:`check_subject` and on every finding :func:`check_tree` acts on. No
    seal changed and no verdict moved. See :class:`Finding`.

Two contract sites the composition never named — :attr:`UndecidedReason`'s
``PARSE_FAILED`` and ``UNSUPPORTED_LANGUAGE`` — are placed where the body put
them and the placements are CONFIRMED, with the ordering reason written into
:func:`check_subject` step 1b.

P1 SCAFFOLD (2026-08-11) — THE IMPORT RELATION, SO STEP 3 CAN SCOPE
====================================================================
``feat/D5-import-relation``, base ``f4c7c46`` (``feat/D6-body``, the commit that
landed the Go analyzer's body — so every number below was measured against a
working analyzer, not predicted). CONTRACT AND STUBS ONLY. :data:`ANALYZERS` is
still ``()``, ``role_protocol`` is still untouched, ``FLOOR_GLOBS`` is
unchanged, nothing is wired into :func:`check_subject`, and the suite is
unmoved: **2413 passed, 0 failed, 13 skipped**, before and after.

The defect: :func:`check_subject` step 3 computes its hole set over the ONE
whole-tree ``production_reach`` map :func:`check_tree` builds, so the list is
identical for every (seal, subject) pair and **one hole anywhere abstains every
finding in the tree**. Measured on the acceptance case at this base: 2 holes in
``cmd/gates/main.go`` abstain all 7 findings, 4 of which are in ``cmd/iterate``
and are connected to neither hole by any route.

The operator ruled step 3's hole set is scoped to the SUBJECT; a P4 ruled what
"scoped" must mean and found it not computable from what :class:`CallGraph`
carried. What lands here is what it needs, and nothing else:

  * :class:`ImportRelation` / :class:`PackageImports` — the undirected import
    graph, over package identities spelled as :attr:`Symbol.key` qualifiers.
    **The shape choice and the rejected per-hole candidate-set shape are argued
    on :class:`ImportRelation`.**
  * :class:`ImportsUnavailable` and :data:`IMPORTS_NOT_SUPPLIED` — the absence,
    as a NAMED STATE with a required reason, never ``None`` and never an empty
    relation. An empty relation reads as "no imports", which makes every package
    its own component and silently MAXIMISES the narrowing; the absent relation
    instead means **no narrowing at all**, i.e. exactly today's sealed
    behaviour.
  * :func:`validate_import_relation` — IMPLEMENTED, because "an empty relation
    is refused" is not a sentence prose can make unmistakable.
  * :func:`_union_import_evidence` — IMPLEMENTED, because
    :func:`build_call_graph` is the one production construction site and a field
    the production path never fills reads as coverage and is not.
  * :func:`import_components` and :func:`holes_in_scope` — STUBS. The ruled rule
    and its application, left for a body so that a seal author pins them against
    the RULING rather than against whatever a scaffold happened to write.
  * ``ReachabilityAnalyzer.supplies_import_relation`` — CONTRACTED, not present,
    on ``test_id``'s precedent and for its measured reason.

Measured under ``feat/D5-import-relation``, base ``f4c7c46``, 2026-08-11:

  * the acceptance tree's import graph is **2 packages, 0 in-tree import edges,
    80 external (stdlib) imports (41 + 39), 0 unplaced — TWO components**;
  * findings answered, by hole set and scope, driving the real
    :func:`check_subject`: 2 holes / whole tree **0 of 7**; 2 holes / subject
    **4 of 7**; 7 holes / subject **0 of 7**; 0 holes **7 of 7**. The P4's 4 is
    reproduced, and so is its 0-at-seven-holes;
  * the fail-open is INVISIBLE on this fixture — with 0 in-tree import edges the
    empty relation and the truth both say 2 components and both answer 4 of 7.
    It is visible elsewhere in reach: ``evenplay-mono/apps/website-public-api``
    is 12 packages / 25 edges / **1** true component where an empty relation
    says 12, and ``apps/platform-domain/core`` is 33 packages / 93 edges /
    **6** true components where an empty relation says 33. That gap is the
    entire argument for :class:`ImportsUnavailable` being a type;
  * ``claude-workflow``'s seven ``cmd/`` modules are one package each with
    **zero** in-tree imports and no ``internal/``, so the relation binds nothing
    there — which is also why no seal may be written only against it.

**The relation SUBSUMES D6's ``_import_path_qualifiers``.** See
:class:`ImportRelation`; that heading is shouted there and it is the one thing
in this round a body can get wrong twice in ways that cancel.

P4 ROUND 3 (2026-08-11) — THREE RULINGS THE COVERAGE PASS RAISED
================================================================
The seal pass on ``feat/D5-seals2`` closed seven of the eight disclosed gaps
and asked three questions. All three are answered; each amendment they force is
named in the commit message. Nothing was enrolled: :data:`ANALYZERS` is still
``()`` and ``role_protocol`` is still untouched.

**S1. SUBSTITUTION IS RATIFIED as the sealing device for a contracted layer no
constructible input can reach — with one condition, which all three rows
already meet.** Three rows substitute a module name to exhibit a state:
:func:`subjects_of_seal` (a name in :data:`__all__`), :func:`_unnameable_finding`
and :func:`_validate_finding` (private, and each now says so at its own
definition). Each is stated in its own docstring rather than dressed as a
fixture.

The argument that decides it is not a preference between two workable designs;
it is a comparison of FAILURE MODES, and this module exists for one of them.

  * Substitution's failure mode is a RENAME, and a rename here is a loud red
    that names its own cause. Measured at ``4e66a01`` in a clone with the
    ``.git`` FILE removed: renaming both private names reddens exactly the two
    rows that substitute them, each with an ``AttributeError`` naming the
    attribute that went missing. Two rows, two named attributes, a one-line fix
    each, and the rename becomes a two-file edit.
  * Leaving the layers unpinned has the OTHER failure mode: a layer that is
    contracted, implemented, mutation-verified by a body, and guarded by
    nothing fails SILENTLY and GREEN. This codebase has already measured what
    that costs — "a layer nobody can demonstrate is working is a layer nobody
    can tell has stopped working" — and the whole of this module is one
    instance of it.

A mechanism whose first anti-requirement is that failing to look may never
manufacture a pass does not get to prefer a silent green to a loud red because
the loud red is inconvenient. **The condition**, so the device cannot decay into
the thing it replaces: a substitution row must (a) substitute a name that
EXISTS — never ``monkeypatch.setattr(..., raising=False)``, which would go
silently inert on a rename and leave the row passing vacuously — and (b) judge,
in the same call, a control on the UNSUBSTITUTED path, so the row cannot pass by
the substitution merely existing. Verified at ``4e66a01``: ``raising=False``
appears nowhere in the seal file, and each of the three rows carries such a
control.

The rejected alternative, spelled out because it was the live one: ruling the
three layers UNSEALABLE and saying so in this contract. That trades a coupling
whose failure is loud for a recorded absence whose failure is silent, and it
would have written the module's own defect class into the module's own
contract.

**S2. THE ``Reddens under`` CONVENTION — the defect is UPHELD, the proposed
mechanical row is REJECTED, and a spelling split is adopted instead.**

The defect is real and worse than "unverified". Measured at ``4e66a01``: 43
rows carry such a clause; 12 record a measurement against the shipped body (all
in the seal file's PART 11) and 31 record one only against a reference
implementation that was thrown away. And at least one clause was never true:
:func:`test_discover_roots_refuses_a_tree_it_cannot_sweep` named "swallowing an
:class:`AnalyzerError`" while supplying no analyzer at all, so it could not
detect that mutation under any body — and gap 4 of the eight sat behind that
sentence for a round, reading as coverage. The seal file's header claim that
every injected mutation "reddened the rows that name it" is falsified by it and
is struck there.

**The proposed mechanical row is refused on this module's own first
anti-requirement.** A row over docstrings can check only that a clause is
ACCOMPANIED by a word like "Measured"; it cannot check that anything was
measured. That row is satisfied by typing, and *a mechanism that can be defeated
by a comment is not a mechanism*. Building it would be a claim that reads as
verification and is not — the defect being ruled on, at a third level, shipped
by the ruling against it.

What is adopted instead costs no mechanism and is honest about being a naming
rule rather than a check: **the two kinds of clause get two spellings.** A
clause measured against the body that shipped is spelled ``Measured under:``
and names the run; a clause that is a prediction is spelled ``Predicted
(unmeasured) under:``. One name for two different things is invariant 5's shape,
which this module refuses by name three times, and the whole value of the split
is that a reader can see at a glance which clauses are evidence. **A prediction
is still worth writing** — it tells the next author where to aim a mutation —
but it may not wear a measurement's clothes.

SCOPE, ruled explicitly rather than by silence. Relabelling all 43 clauses to
the two spellings is D5-LOCAL and is an obligation on the SEAL AUTHOR, not on
this round — an adjudicator rewriting 43 docstrings in the file it is ruling on
is the "gate whose decisions can be dissolved by editing it" hazard in
miniature. The 12 in PART 11 are already substantively compliant, since each
names the run it was measured by; the 31 are the real work, and each needs
either a re-measurement against the shipped body or the prediction spelling.
Only the one demonstrably FALSE clause is amended here, and the header sentence
it falsifies. **The MECHANISM question is OUT OF D5's SCOPE** and belongs to task
#27 as a unit of its own: the convention has spread to the G1 and G2 seal files,
a convention living in three files cannot be repaired in one of them, and the
only non-vacuous form of it — a mutation harness with a durable ledger outside
the docstrings — is a unit of work rather than a row.

**S3. GAP 6 (unsorted subject symbols) — the OUTCOME is RATIFIED and the REASON
is OVERTURNED.** Leaving it open is right. The reason given for it was wrong on
both premises, and one of them was dangerous.

The claim was that a row would "have to hand it a graph that violates
:func:`build_call_graph`'s own determinism contract", making it "red only on an
input production cannot construct". :func:`subjects_of_seal` is public and takes
the graph as an ARGUMENT; the determinism contract belongs to
:func:`build_call_graph`, and :class:`CallGraph` contracts its edges as "in no
guaranteed order". A descending-key graph is therefore a LEGAL ``CallGraph`` a
row builds with the helper the seal file already uses — no substitution, no
violation. Measured at ``4e66a01``: handed such a graph,
:func:`subjects_of_seal` returns ``(Alpha, Zulu)`` for edges supplied
``(Zulu, Alpha)``.

That correction is load-bearing beyond this gap: *"a row red only on an input
production cannot construct"* is the argument that would also strike the three
rows S1 ratifies, and here it was aimed at an input that is neither
unconstructible nor illegal. It must not be left standing as precedent.

The outcome survives on the other reason, which is sufficient alone: **nothing
contracts the order and nothing reads it.** A row would legislate a contract
into existence for the row's own benefit rather than guard one that exists,
which is not a P2's standing — R8 refused the same shape. The absence is now
recorded at :attr:`Subject.symbols` instead, so the next reader does not
re-derive it, and the trigger for revisiting is named there.

**Still NOT ENROLLED.** :data:`ANALYZERS` is empty, no call site was added, and
``role_protocol`` was not touched: the ``FLOOR_GLOBS`` round the WIRING section
below raises for P4 is due BEFORE enrolment, because implementing the ruling
grid makes this module a gate whose decisions can be dissolved by editing it.

P3 BODY (2026-08-11) — THE RELATION IS COMPUTED, AND ``root_kind`` READS THE FILE
=================================================================================
``feat/D5-relation-body``, base ``3eedd07`` (``feat/D5-relation-seals``). Three
things land and the two bullets above that call them STUBS are now history
rather than description:

  * :func:`import_components` — IMPLEMENTED. Undirected, transitive, and an
    unplaced import is an edge to every package. One new CHOICE, recorded there
    as **DISPUTE B1**: an ``imports`` entry naming a package the relation does
    not carry is treated as unplaced — an edge to everything — rather than
    raised on or dropped. :func:`validate_import_relation` still refuses that
    shape loudly and still runs first; this is the fail-closed floor under it.
  * :func:`holes_in_scope` — IMPLEMENTED and WIRED, one line in step 3 of
    :func:`check_subject` plus the regime marker on that step's detail string.
    The subject conjunct only; the closure conjunct stays in
    :func:`check_subject`, so its seal keeps pinning it independently.
  * :func:`_validate_root` — REPAIRED. ``root_kind`` now derives from ``kind``
    AND from ``seal_verify.is_test_path`` over the declaring file, which is
    what its own docstring has contracted since the module was written. The
    production-kind-in-a-test-file REFUSAL is struck, and the contradicting
    sentence in :class:`Root`'s ``root_kind`` paragraph is struck with it — a
    body that edited only the derivation would have left this module carrying a
    contract it violates. The MIRROR — a ``TEST_FUNCTION`` outside the tests —
    is not symmetric and remains a refusal.

**Measured under ``feat/D5-relation-body``, base ``3eedd07``, 2026-08-11**,
``PYTHONPATH=src python3 -m pytest -q -o addopts=""``:

  * before: **10 failed, 2420 passed, 13 skipped**, every failure in
    ``tests/test_call_site_reachability.py``;
  * after: **0 failed, 2430 passed, 13 skipped**;
  * on the reach fixture ``evenplay-mono/apps/website-public-api`` @
    ``51a71736c`` — 12 packages, 24 directed in-tree edges — this body returns
    **ONE component of 12**. The three wrong readings return 12 (empty
    relation), 12-with-``internal/snapshot``-a-singleton (directed), and
    8-of-12 for ``cmd/public-api`` (direct-only). It is the truth;
  * the acceptance tree still answers **4 of 7** with the hole set scoped and
    **0 of 7** with the relation absent — and absent is what every tree carries
    at this revision. Neither regime produced a ``FROM_PRODUCTION`` or an
    ``OK``: the narrowing reduces abstention and does not manufacture verdicts;
  * **23 mutations, each applied alone to the shipped body and run over the
    WHOLE suite in a ``cp -a`` clone.** Every row this body closes has at least
    one mutation that reddens it and a recorded blast radius. Three blast radii
    diverge from what the seals record, all reported on the functions
    concerned, and all in the direction of MORE coverage than predicted: the
    absence branch (2 predicted, **4** measured — the difference is the wiring
    line), the representative-keyed mapping (5 predicted, **4** measured), and
    ``_validate_root`` as a no-op (10 predicted, **11** measured). Two changes
    are measured as pinned by NO row and are landed on the contract's authority
    with that fact recorded: **DISPUTE B1** and **DISPUTE B2**.

**NOTHING WAS ENROLLED.** :data:`ANALYZERS` is still ``()``, ``role_protocol``
was not touched, ``FLOOR_GLOBS`` is unchanged, and no analyzer row was added.
The wiring line is inert on every tree this module can build today, because
:func:`_union_import_evidence` returns :data:`IMPORTS_NOT_SUPPLIED` with no row
to ask. **DISPUTE R1 of the seal pass stands unresolved and is not this body's
to close:** :class:`ImportsUnavailable`'s docstring says the reach tree is 25
edges and ``platform-domain/core`` is 33 packages / 93 edges / 6 components;
the seal author re-measured 24, and 31 / 88 / 5. The load-bearing figures — 1
true component against 12 — reproduce under this body exactly.

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
    (``main.go:297``) → ``findConfig`` (``main.go:439``) → ``configCandidates``
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

**P4 EXTENSION (round 2, 2026-08-11): the obligation covers LINE CITATIONS, not
only counts, and it is extended because the same obligation caught its own
author twice in one round.** R6 corrected the ``getattr`` site to ``line 726``;
that was already wrong at ``094fffb``. The body corrected it to ``865``; that
was wrong at ``571e036``, the revision the correction names. It is **890** at
that revision, **961** at ``37f5665``, and **983** on ``feat/D5-body2``
(2026-08-11, this commit) because deleting the fallback and adding
:func:`_validate_finding` moved it again; each is re-measured by AST below,
against the commit it is written at. A line number is a measurement of a
file that changes under every edit including the edit that records it, so a
citation is checked at the revision it is written at or it is not a citation —
which is why this paragraph carries three numbers and not one, and why none of
them is pinned by a row. Every other citation in this docstring was re-checked
against its artifact this round and one had never been right at all:
``resolveConfigPath`` was cited at ``main.go:296``, which is its DOC
COMMENT — the declaration is 297, as ``PROVENANCE.md`` and the seal file both
say. Off by one INTO a doc comment, in the module whose first anti-requirement
is that a doc comment defeated the first scan anyone wrote. Corrected above,
with ``findConfig`` at 439 supplied while the chain was open. The other six
(``contract.go`` 712 and 742, ``contract_seal_test.go`` 852, ``main.go`` 180
and 401, and ``fixture_reachability._resolve_dotted`` at 847) are right.

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

AMENDED on ``feat/D5-contract-module``, 2026-08-11, base ``6e18fc0``
--------------------------------------------------------------------
Two of the three paragraphs above have been overtaken and are kept because the
reasoning in them is still the reasoning:

  * ``FLOOR_GLOBS`` acquired ``**/src/claude_dispatcher/call_site_reachability.py``
    in the D5 P4 round of 2026-08-11, so the first coordination is DONE for this
    module. It is NOT done for ``call_site_contract``, which now holds the
    vocabulary every BREACH is spelled in and is not yet on the floor; the glob
    that is owed, the four spellings that do not work, and the two measured reds
    the landing passes through are all written out in that module's docstring.
  * the delegation closure grew by exactly one member, ``call_site_contract``,
    and by nothing else — that module imports no in-package module at all.
    ``role_protocol`` still does not import this one, so
    ``_DELEGATION_TARGETS`` in ``tests/test_floor_closure.py`` still needs no
    row.

``ANALYZERS`` is still ``()``. This round removed the obstacle to enrolment; it
did not enrol.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Mapping, Protocol, Sequence

from .role_protocol import (
    COMPARATORS,
    FLOOR_GLOBS,
    Language,
    first_matching_glob,
    support_for_path,
)
from .seal_verify import is_test_path

# The shared vocabulary, DEFINED in `call_site_contract` and re-exported
# here. The eighteen names below used to be defined in this file, which made
# `go_reachability`'s module-level import of eleven of them a cycle and made
# enrolment impossible in both available placements — measured, with the
# tracebacks, in that module's docstring. The dependency now runs
# contract <- mechanism and contract <- row, and the row imports its eleven
# from the contract rather than from here.
#
# THE RE-EXPORT IS LOAD-BEARING AND IT IS A SHIM. It is what makes this
# extraction cost zero seal edits: `tests/test_call_site_reachability.py`
# imports 13 of these by name from this module and
# `tests/test_go_reachability.py` imports 9, and a re-export binds the same
# object rather than copying it, so those seals stay TRUE and not merely
# green. Removing it is a P4 round that repoints 22 import sites.
#
# Nothing may be added to `call_site_contract` that DECIDES; the rule and its
# five edges are written out there, and this module is the one that would be
# hollowed out by breaking it.
from .call_site_contract import (
    AnalyzerError,
    AnalyzerFault,
    AnalyzerUnavailable,
    CallGraph,
    Edge,
    EdgeKind,
    EntrypointKind,
    GO_REACHABILITY_PACKAGE_DIR,
    GO_REACHABILITY_SCHEMA,
    IMPORTS_NOT_SUPPLIED,
    ImportEvidence,
    ImportRelation,
    ImportsUnavailable,
    PackageImports,
    ROOT_KIND_BY_ENTRYPOINT,
    Root,
    RootKind,
    Symbol,
)

#: The pre-move spelling of :data:`ROOT_KIND_BY_ENTRYPOINT`, bound to THE SAME
#: OBJECT and not to a copy. A COMPATIBILITY SHIM, owed removal by the P4
#: round that repoints its three seal reads
#: (`tests/test_go_reachability.py:1157`, `:1158`, `:2469` — measured
#: 2026-08-11 at base `6e18fc0`, all subscript reads of
#: `csr._ROOT_KIND_BY_ENTRYPOINT`). It exists so that a P1 scaffold did not
#: have to edit a sibling unit's seals to keep its own suite green.
#:
#: The underscore does NOT cross a module boundary: `go_reachability` imports
#: the public name from the contract. This binding is internal to this module
#: and to the seals that already read it here.
_ROOT_KIND_BY_ENTRYPOINT = ROOT_KIND_BY_ENTRYPOINT

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
    "ImportsUnavailable",
    "PackageImports",
    "ImportRelation",
    "ImportEvidence",
    "IMPORTS_NOT_SUPPLIED",
    "validate_import_relation",
    "import_components",
    "holes_in_scope",
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
    root, a malformed :class:`Subject`, a malformed :class:`Finding` (P4 round
    2; :func:`check_subject` and :func:`check_tree` both raise it, see
    :func:`_validate_finding`), a witness chain that originates at a key no
    supplied :class:`Root` names (P4 round 2, replacing the struck
    synthesising fallback — see :func:`_witness`), or an :class:`AnalyzerError`
    that is not :class:`SourceUnreadable`.

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
    and "when is my silence conclusive". A FOURTH is ruled and not yet written
    (``test_id``, below).

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
        ``094fffb`` either — the ruling's own edits had already moved it.

        **P4 ROUND 2 (2026-08-11): the body's correction was checked rather than
        trusted, and it is wrong at the revision it names.** Fresh AST
        measurement over ``src/`` at ``571e036`` (``feat/D5-body``, the branch
        the body recorded against): **105** ``getattr(`` call sites, **4** with
        a non-literal attribute name, at ``fixture_reachability.py``
        871 / 1118 / 1647 — those three verified, all three right — and
        ``call_site_reachability.py`` at **890**, not 865. The body wrote 865
        and then went on editing the file above the site.

        It was **961** at ``37f5665``, because writing that paragraph moved it
        again. **At this commit (``feat/D5-body2``, 2026-08-11) it is 983**,
        re-measured by AST over ``src/`` on the tree this commit contains,
        because deleting the struck fallback and adding
        :func:`_validate_finding` moved it a fifth time — and the deletion is
        BELOW this docstring while the module-docstring edit that records it is
        ABOVE, which is why a citation written from memory of the last round is
        wrong by construction. Five recordings, three of them wrong the moment
        they were written: 726, 865, 890, 961, 983. The arithmetic — 105 / 4 /
        3 — has now survived four independent AST measurements without moving
        once, this one included.

        That contrast is the whole of R6 in one field. The COUNT is a fact about
        the repository and reproduces; the LINE is a fact about a file that
        every edit invalidates, including the edit that records it. A row on the
        count would never have reddened and would have caught nothing; a row on
        the line would have reddened on all five of these commits and taught
        nobody anything. Neither is pinned, and the obligation is provenance
        instead — extended this round to line citations, in the module docstring
        above.

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

    ``supplies_import_relation`` — **CONTRACTED but NOT YET PRESENT (P1
    scaffold, ``feat/D5-import-relation``, 2026-08-11).**
        The row's claim that its :meth:`graph` populates
        :attr:`CallGraph.package_imports` with a real
        :class:`ImportRelation` rather than an :class:`ImportsUnavailable`.
        A ``bool``, on ``negative_is_conclusive``'s precedent exactly: a claim a
        HUMAN made about a language's row, validated for type in
        :func:`validate_analyzers`, and cross-checked in
        :func:`build_call_graph` — a row declaring ``True`` whose graph carries
        the refusal RAISES, and a row declaring ``False`` whose graph carries a
        relation raises too.

        **Why the belt is worth having when the braces already hold.** The
        VALUE side is enforced today and enforced hard:
        :func:`validate_import_relation` refuses an empty relation, and
        :func:`_union_import_evidence` reads any refusal as a whole-tree
        refusal, so nothing can narrow on evidence nobody collected. What the
        value side cannot see is a row that USED to compute imports and quietly
        stopped: returning :class:`ImportsUnavailable` is legitimate, so the
        regression is invisible in the data and shows up only as a mechanism
        that gradually abstains more. The row bool makes that a raise.

        CHOICE (it could have been DERIVED — "this row supplies a relation iff
        its last graph carried one"): a per-row BOOLEAN. Rejected alternative is
        free and self-maintaining, and it is out for
        ``negative_is_conclusive``'s reason verbatim: a derived claim is a claim
        about the tree the row was last run over, so a row that stopped
        computing imports would read as a row that never claimed to, and the
        cross-check would be vacuous by construction.

        **Written here as a contract and NOT as a member, on ``test_id``'s
        precedent below and for the identical reason — measured, not assumed.**
        Adding the clause to :func:`validate_analyzers` reddens every row that
        builds an analyzer double, and there are three such doubles across two
        seal files on this base (``_Analyzer`` and ``_go``/``_python`` in
        ``tests/test_call_site_reachability.py``, ``_Unimplemented`` in
        ``tests/test_go_reachability.py``), plus the live
        ``GO_REACHABILITY_ANALYZER`` row, which
        ``validate_analyzers((GO_REACHABILITY_ANALYZER,))`` passes through.
        Measured under ``feat/D5-import-relation``, base ``f4c7c46``,
        2026-08-11. Landing it is one round carrying the production edit, the
        Go row's member and the three doubles TOGETHER — a seal amendment, which
        a P1 scaffold does not write on a seal author's behalf. Until then the
        value side stands alone and is sufficient for soundness; what is missing
        is only the regression alarm.

    ``test_id(symbol)`` — **RULED but NOT YET PRESENT (P4 round 2,
    2026-08-11).**
        The row's spelling of the runnable id for one of its test symbols:
        pytest's node id, Go's ``package.TestName``. Ruled onto this protocol
        because :attr:`Seal.test_id` contracts that spelling as per-language and
        not-derived, and until this member exists the only layer that could
        honour it has no channel to. It is written here as a contract and not
        as a member because landing it is four coupled edits, one of which is a
        seal amendment; :func:`_test_id` carries the schedule and the
        escalation.

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
def _the_enrolled_analyzer_rows() -> tuple[ReachabilityAnalyzer, ...]:
    """The rows :data:`ANALYZERS` is bound to. Called once, at import.

    **The import is INSIDE this function and that is not style.**
    ``go_reachability`` imports :mod:`claude_dispatcher.call_site_contract` for
    the eleven contract names it needs and never this module, which is what the
    contract extraction bought and what makes a module-level import here
    acyclic TODAY. It is written function-local anyway, for two reasons that
    outlive today's import graph: it is the shape ``tests/test_d5_floor.py``
    states as fixture input for a row living in its own module
    (``_ENROLMENT_FROM_ROW_MODULE_SOURCE``), where the row module DOES import
    back out of this one; and this call sits above
    :func:`validate_analyzers` and far above
    :func:`_refuse_enrolment_before_flooring`, so binding here is what puts the
    registry in front of both guards rather than behind them — the placement
    ``call_site_contract``'s WIRING section ruled on and measured.

    It does not swallow an :class:`ImportError`. A row that failed to import
    would leave this module reporting an empty registry, which reads as "no
    analyzer has been written" — the one claim :data:`ANALYZERS`' own docstring
    forbids it to make falsely.
    """
    from .go_reachability import GO_REACHABILITY_ANALYZER

    return (GO_REACHABILITY_ANALYZER,)


#: Rejected alternative, spelled out because it is the tempting one: give D5 its
#: own ``extensions`` per row and skip ``role_protocol`` entirely. That buys
#: independence and costs the one property D1 spent a whole unit establishing —
#: exactly one place in this codebase decides what language a file is. A second
#: extension table would drift, and it would drift silently, because the two
#: gates would disagree only on files neither had been pointed at yet.
#:
#: **ENROLLED — the Go row, P4, ``feat/D6-enrol2``, base ``d8fd825``,
#: 2026-08-11.** ``ANALYZERS`` was ``()`` from this module's first commit until
#: this one. What it holds now is
#: :data:`~claude_dispatcher.go_reachability.GO_REACHABILITY_ANALYZER` and
#: nothing else; ``.py`` and ``.ts`` still resolve to a ``COMPARATORS`` row and
#: to no analyzer, which is the state ``analyzer_for_path``'s second bullet
#: describes and it is now instantiated by two real languages rather than by
#: three hypothetical ones.
#:
#: **THE SIGN CHANGE, MEASURED IN BOTH DIRECTIONS ON REAL TREES**, by driving
#: :func:`check_tree` against the SHIPPED registry — no monkeypatch, no
#: hand-built relation — at this revision. A green suite is not evidence and
#: D4's enrolment commit says so in its own words; these are the verdicts::
#:
#:     tests/fixtures/d6_import_scope          ok 0  breach 1  abstain 1
#:       pkg/c.Dark    FROM_TESTS_ONLY  ->  BREACH    genuinely dark, reported
#:       pkg/b.Dark    UNDECIDED/DYNAMIC_EDGE -> ABSTAIN  hole crosses the import
#:
#:     tests/fixtures/d6_g2_preserve   30 seals, 48 findings
#:                                             ok 27 breach 12 abstain 9
#:       cmd/iterate.VerifyPreservation   FROM_TESTS_ONLY -> BREACH   (x4 seals)
#:       cmd/iterate.ApplyRoundRecord     FROM_PRODUCTION/resolved -> OK,
#:         "production reaches ... from cmd/iterate.main over 3 edge(s)"
#:       cmd/gates.VerifyPreservation     UNDECIDED/DYNAMIC_EDGE -> ABSTAIN (x3)
#:
#: A genuinely dark function is reported and a genuinely reached one is clean,
#: on both trees, in the same call. ``pkg/b`` and ``pkg/c`` are the same shape
#: in every respect that could move a verdict and differ only in that
#: ``cmd/app``'s import block names one of them, so the ABSTAIN/BREACH split
#: between them is the narrowing itself and not two separate measurements.
#:
#: **THE 3 THAT STILL ABSTAIN, and the citation defect that is now HALF fixed.**
#: ``cmd/gates.VerifyPreservation`` abstains once per seal, 3 times, and is
#: correct to: both remaining holes are ``context.CancelFunc`` values, at
#: ``cmd/gates/main.go:754`` (in ``runOne``) and ``:1468`` (in ``runCmd``), both
#: in the subject's OWN package and own module — verified by reading
#: ``build_call_graph``'s hole set directly. Before ``_package_imports`` the
#: abstention over a ``cmd/gates`` subject cited ``cmd/deepseek/main.go:46``, a
#: hole in a DIFFERENT MODULE. **That is fixed: no finding on this tree cites
#: any module but the subject's.** What is NOT fixed, and is recorded rather
#: than papered over: all 9 abstentions name the COUNT and the FIRST hole only —
#: *"2 call(s) … first at cmd/gates/main.go:1468"* — and ``:754`` appears in no
#: finding on this tree. The detail is honest about the arithmetic and
#: incomplete about the sites. Naming both is a body change to a floored
#: module's message and is NOT this commit's; it is recorded here so the next
#: reader finds a measured gap rather than a claim of completeness.
#:
#: **WHAT ENROLMENT NEWLY BLOCKS, measured and not claimed harmless** —
#: :func:`check_tree` over a tree holding at least one ``.go`` file, on a host
#: with no usable ``go``, RAISES out of :func:`discover_roots`
#: (:attr:`~claude_dispatcher.call_site_contract.AnalyzerFault.
#: TOOLCHAIN_MISSING`) where before it returned a silent empty report. Measured
#: with ``PATH`` emptied, three trees, both registries::
#:
#:                            ANALYZERS = ()        the Go row enrolled
#:     no .go file at all     report, 0 findings    report, 0 findings
#:     one .go, no seal       report, 0 findings    **RAISES**
#:     the primary target     report, 0 findings    **RAISES**
#:
#: The class is therefore "a Go tree judged on a machine that cannot read Go",
#: and the boundary is real: a tree with no ``.go`` file never selects the row
#: and is untouched in both states. **It is EMPTY on the primary target as
#: things stand** — ``evenplay-mono/apps/website-public-api`` @ ``51a71736c``,
#: this host's go1.24.4 — measured twice over: the toolchain is present so
#: nothing raises, and the module declares ``go 1.25.0``, which
#: :func:`~claude_dispatcher.go_reachability._go_environment`'s
#: ``GOTOOLCHAIN=local`` correctly refuses, so all 13 units come back unreadable
#: and ``package_imports`` is :class:`~claude_dispatcher.call_site_contract.
#: ImportsUnavailable`. That degrades; it does not raise. And the module carries
#: no ``TestSeal_`` function, so ``check_tree`` answers 0 seals and 0 findings
#: and enrolment moves no verdict there at all. **On a CI image with no Go
#: toolchain the class is NOT empty**: that target has 52 ``.go`` files and
#: would raise. Recorded as the price, not as an accident.
#:
#: **THE RULED PRICE, re-measured at this revision** by spying on every
#: ``subprocess.run`` the mechanism makes, three repetitions per tree::
#:
#:     tree                      pkgs   discover_roots   build_call_graph   check_tree
#:     d6_import_scope              3   0.64 s / 3 exec  0.64 s / 3 exec    1.28 s / 6
#:     d6_g2_preserve               2   0.67 s / 2 exec  0.68 s / 2 exec    1.32 s / 4
#:     website-public-api          13         —                —           7.58 s / 26
#:
#: Three corrections to the figure this enrolment was handed ("``go list`` runs
#: twice per ``check_tree``, ~0.83 s per Go module"). The mechanism issues **no
#: ``go list`` from Python at all**; the unit of work is the vendored helper and
#: it is exec'd **once per PACKAGE**, not per module. The DOUBLING is real and
#: is the load-bearing half of that figure: :meth:`GoReachabilityAnalyzer.roots`
#: and :meth:`~GoReachabilityAnalyzer.graph` each sweep every package and share
#: nothing, and the two phases cost the same to within 2% on both fixtures. The
#: helper BINARY is built once per process (0.19 s) and reused across trees.
#: And :func:`check_tree` takes a TREE, never a diff, so the full price is paid
#: whatever the branch size — a one-line branch on the primary target would pay
#: the whole 7.58 s. **Halving it is available and is a body change, not this
#: commit's**: one sweep feeding both phases.
ANALYZERS: tuple[ReachabilityAnalyzer, ...] = _the_enrolled_analyzer_rows()


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


#: The directory a source checkout puts this package in, and the ONE fact that
#: separates a checkout from an install. ``pyproject.toml`` builds a setuptools
#: wheel with ``where = ["src"]``, so the shipped package sits at
#: ``.../site-packages/claude_dispatcher/`` and its parent is NOT this name.
#:
#: It is spelled as a directory name and never as a path, because the AST sweep
#: in ``test_the_module_declares_no_file_extension_and_calls_no_endswith``
#: reads every non-prose string constant in this module and refuses anything
#: extension-shaped: this module's own repo-relative path would match it. The
#: path is derived from ``__file__`` instead, which also cannot drift on a
#: rename.
_CHECKOUT_PACKAGE_ROOT = "src"


def _floor_relative_path(path: Path) -> str | None:
    """``path`` as the floor spells paths, or None if it cannot be spelled.

    ``FLOOR_GLOBS`` is written in repo-relative, git-emitted form, and every
    entry naming something in this package is path-qualified — the leading
    ``**/`` matches zero or more leading segments, so a path spelled relative
    to the directory ABOVE :data:`_CHECKOUT_PACKAGE_ROOT` is exactly what a
    floor glob can be matched against, in a nested checkout as well as at a
    repository root.

    None is returned when this package is NOT sitting in a source checkout, or
    when ``path`` is not inside that checkout, and that return is the whole
    point of this function rather than defensive padding. An installed
    dispatcher derives ``site-packages/claude_dispatcher/<module>``, which NO
    path-qualified floor glob matches and which no repository could make match.
    Reading that "I cannot find myself on the floor" as "I am not on the floor"
    would refuse every installed copy the moment the module is enrolled,
    including copies whose repository floors it correctly. **A None derivation
    is a SKIP, never a refusal, and every caller owes that.**

    **P4, 2026-08-11 (unit D6): it takes a path now, and the derivation is
    anchored rather than counted.** It used to be ``Path(__file__).resolve().
    parts[-3:]`` with ``parts[0] == "src"``, which is right for exactly one
    input — a file sitting directly in the package — and silently wrong for
    every other: measured on this revision, the last three components of
    ``src/claude_dispatcher/go_call_reachability/main.go`` are
    ``claude_dispatcher/go_call_reachability/main.go``, whose first component
    is not ``src``, so the old shape would have returned None for every file in
    the Go helper subtree and the widened guard below would have SKIPPED the
    whole helper while reading as if it had checked it. The anchor — this
    package's own directory, whose parent must be
    :data:`_CHECKOUT_PACKAGE_ROOT` — gives the identical answer for this module
    and the right one for a nested asset.

    Measured 2026-08-11 under ``risk._glob_to_regex`` via
    :func:`role_protocol.first_matching_glob`, against the thirteen-entry
    ``FLOOR_GLOBS``: the checkout spelling of this module returns
    ``**/src/claude_dispatcher/call_site_reachability.py``, the checkout
    spelling of the Go helper's ``main.go`` returns
    ``**/src/claude_dispatcher/go_call_reachability/**``, and the
    ``site-packages`` spelling of either returns None.
    """
    package = Path(__file__).resolve().parent
    if package.parent.name != _CHECKOUT_PACKAGE_ROOT:
        return None
    try:
        relative = path.resolve().relative_to(package.parent.parent)
    except ValueError:
        # Outside the checkout entirely — a row shipped by another
        # distribution. This repository's floor cannot name it, so this
        # repository's guard does not judge it.
        return None
    return "/".join(relative.parts)


def _paths_the_enrolled_registry_is_judged_from() -> tuple[Path, ...]:
    """Every file a branch could rewrite to change what :data:`ANALYZERS` says.

    Three kinds, and the second and third are P4's 2026-08-11 correction to a
    guard that only ever knew the first:

      1. **This module**, the MECHANISM. It was the guard's only subject, and
         checking it alone floors the registry while leaving every row writable
         — the table protected and not the answer.
      2. **Each row's DEFINING MODULE**, derived from ``type(row).__module__``
         and never from a hand-list. A row is a class in a file, and that file
         decides what this tree starts from and what calls what; a branch that
         can rewrite it supplies its own judge just as squarely as one that can
         rewrite this module. Measured 2026-08-11 against ``6e18fc0``:
         ``go_reachability.py`` was off the floor, and the guard as it stood
         would have permitted enrolment.
      3. **Each helper subtree**, resolved as
         ``<the row's package directory>/<a declared helper package dir>`` and
         enumerated FILE BY FILE rather than probed as a directory. Two reasons,
         both measured: a floor glob whose tail is ``**`` matches paths INSIDE
         the directory and not the directory path itself, so a directory probe
         would report the helper unfloored while the floor covers every byte of
         it; and enumerating is what makes a file somebody adds to the helper
         later part of the question rather than outside it.

    A row whose module is not in ``sys.modules``, or has no ``__file__``, or
    whose helper directory is absent from this install, contributes nothing.
    That is the same doctrine :func:`_floor_relative_path` states: an
    underivable path is a SKIP. A guard that refused what it could not locate
    would refuse every wheel, which is the failure that deferred this whole
    check for a round.
    """
    paths: list[Path] = [Path(__file__)]
    for row in ANALYZERS:
        module = sys.modules.get(type(row).__module__)
        source = getattr(module, "__file__", None)
        if source is None:
            continue
        home = Path(source).resolve()
        paths.append(home)
        for name in _HELPER_PACKAGE_DIRS:
            helper = home.parent / name
            if not helper.is_dir():
                continue
            paths.extend(child for child in sorted(helper.rglob("*")) if child.is_file())
    return tuple(paths)


def _refuse_enrolment_before_flooring() -> None:
    """Fail the IMPORT when an enrolled row is judged from off the floor.

    The ordering D5's first P4 escalated, as a property of the ARTIFACT rather
    than of a test run: this module decides, per seal, whether a subject is
    reachable from a production root, and turns that into a ``Disposition`` a
    branch is judged by. A branch that could rewrite it while it is being asked
    the question is the delegation-closure defect, so :data:`ANALYZERS` may not
    acquire a row before ``FLOOR_GLOBS`` acquires the artifacts that row's
    answer is computed from. Enforced here so the failure arrives at the first
    import instead of at the end of a build cycle.

    **P4 RULING, 2026-08-11 (unit D6): the subject is the ROW's artifacts, not
    this file.** As shipped, the check resolved ``_floor_relative_path()`` from
    ``Path(__file__)`` — its own path and nothing else — so it would have
    permitted enrolment with ``go_reachability.py`` and the whole
    ``go_call_reachability/`` helper writable by the branch under judgement.
    Measured on ``feat/D5-relation-body`` @ ``6e18fc0``: both were off the
    floor, and neither this guard nor :func:`validate_analyzers` looked at
    either. :func:`_paths_the_enrolled_registry_is_judged_from` is the widened
    subject; the conjunction below is unchanged in shape.

    THE REFUSAL IS A CONJUNCTION and each conjunct is load-bearing:

      * an EMPTY registry never refuses — that is today's world, and a rule
        that refused it would make the package unimportable as it ships;
      * a FLOORED artifact never refuses — enrolment after flooring is the
        whole point of the ordering, and a rule that refused it too would not
        be a guard but a permanent refusal that the next author deletes;
      * a path that cannot be spelled the way the floor spells paths never
        refuses — see :func:`_floor_relative_path`. This is a fact about the
        FLOOR, not about where the package happens to be sitting, and it is the
        conjunct the widening had to carry forward rather than reinvent: a
        wheel derives ``site-packages/claude_dispatcher/...`` for EVERY path
        this function now collects, so the widened guard skips an installed
        copy exactly as the narrow one did, and skips it for all three kinds at
        once.

    Deliberately NOT written as ``validate_analyzers`` refusing a well-formed
    row: measured 2026-08-11, that reddens a live sibling seal, since
    ``test_validate_analyzers_refuses_a_row_no_path_can_reach`` ends by
    asserting that a Go row IS accepted once its language is enrolled. The
    import-time form leaves that contract untouched.

    Measured 2026-08-11 against this revision, four package copies imported in
    fresh interpreters plus one installed-layout copy: unenrolled-and-unfloored
    imports, enrolled-and-floored imports, enrolled-and-floored under a
    ``site-packages`` parent imports, and enrolled-and-unfloored raises from
    here. Removing the :func:`_floor_relative_path` layout condition turns the
    installed-layout copy into an import failure and nothing else moves.
    """
    if not ANALYZERS:
        return
    unfloored = []
    for candidate in _paths_the_enrolled_registry_is_judged_from():
        path = _floor_relative_path(candidate)
        if path is None:
            continue
        if first_matching_glob(path, FLOOR_GLOBS) is None:
            unfloored.append(path)
    if not unfloored:
        return
    raise ImportError(
        "this module carries an analyzer row while the artifacts that row's "
        "answer is computed from are off the non-overridable floor. They "
        "decide, per seal, whether a subject is reachable from a production "
        "root, and a branch being judged may still rewrite them: four of the "
        "five roles get a clean verdict for editing an unfloored gate. Land "
        "the floor globs covering "
        f"{unfloored} in role_protocol.FLOOR_GLOBS on the protected base — a "
        "reviewed edit, never a line in the branch being judged — and enrol "
        "after that, not before. The floor as imported here is "
        f"{list(FLOOR_GLOBS)}"
    )


# `_refuse_enrolment_before_flooring()` USED TO BE CALLED HERE, immediately
# below its own definition and beside `validate_analyzers(ANALYZERS)`. P4 moved
# the CALL — and only the call — below `_HELPER_PACKAGE_DIRS`, because the
# widened guard reads that constant and a call from here would raise NameError
# before it could read anything. It still runs while this module's body runs,
# which is the whole of what "the failure arrives at the first import" asks for;
# nothing between here and there has a side effect. The NameError is deliberate
# rather than defended against: a future edit that moves the call back up fails
# loudly, where a `globals().get(...)` would have skipped the helper check in
# silence.


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





#: Every helper package directory this gate declares, as DIRECTORY NAMES to be
#: resolved against the package directory of whichever module defines a row —
#: never as paths, and never against a repository root or the CWD.
#:
#: It exists so that :func:`_refuse_enrolment_before_flooring` has ONE place to
#: read "what non-Python source does an enrolled row's answer come out of", and
#: it is spelled from the constants above rather than restating them, so the
#: helper's location is still declared exactly once. A row's helper is a program
#: whose output IS the call graph: leaving it writable by the branch whose call
#: graph it computes is the defect flooring the row module alone would not
#: close.
#:
#: NOT a per-row field on :class:`ReachabilityAnalyzer`, and the reason is
#: measured rather than aesthetic (2026-08-11): adding a member to that Protocol
#: reddens every analyzer double in the suite — ``_Analyzer`` and ``_go`` /
#: ``_python`` in ``tests/test_call_site_reachability.py``, ``_Unimplemented`` in
#: ``tests/test_go_reachability.py`` — which is the coupled seal amendment
#: ``supplies_import_relation`` and ``test_id`` are both already waiting on. The
#: guard must not be held behind that queue, so it reads the gate's own
#: declaration instead. When those four coupled edits land, this tuple is the
#: thing to replace with a row member, and it is two lines.
#:
#: The consequence of being gate-wide rather than per-row, stated because it is
#: a real over-approximation: with a second language enrolled, that row's
#: enrolment would also require the GO helper to be floored. It runs in the safe
#: direction — the check can only refuse enrolment, never permit it — and it
#: cannot bite today, because this round floors the Go helper.
_HELPER_PACKAGE_DIRS: tuple[str, ...] = (GO_REACHABILITY_PACKAGE_DIR,)


# The guard, called here rather than beside its definition: it reads
# `_HELPER_PACKAGE_DIRS`, which is bound one statement up. See the note at the
# definition for why the call moved and why the failure mode of moving it back
# is a NameError rather than a silent skip.
_refuse_enrolment_before_flooring()


# --------------------------------------------------------------------------- #
# Part 2 — the roots: what does this tree START from?
# --------------------------------------------------------------------------- #








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

    **THE DERIVATION WAS REPAIRED ON ``feat/D5-relation-body``, 2026-08-11,
    base ``3eedd07``, and the prose moved with it.** Until this commit the code
    derived ``expected`` from ``_ROOT_KIND_BY_ENTRYPOINT.get(root.kind)``
    ALONE — the ``kind`` half only — and then REFUSED any production kind found
    in a test file. This function's own first paragraph has contracted both
    halves since the module was written, and :class:`Root`'s ``root_kind``
    paragraph contracted the refusal; the two have disagreed from the start and
    the code implemented the second. It now implements the first, and the
    :class:`Root` sentence has been struck rather than left standing.

    What changed, exactly: ``expected`` is ``TEST`` when the declaring file is
    a test file and the table's answer otherwise, and the
    production-kind-in-a-test-file refusal is GONE. A ``func init()`` in a
    ``z_test.go``, and D6's ``<vars:test>`` ``GO_PACKAGE_VAR`` symbol, are
    roots — TEST roots. They RUN, in the test binary, and everything they reach
    is genuinely reached under test. Dropping them made their callees read
    :attr:`Reach.FROM_NEITHER` where the truth is FROM_TEST, and FROM_NEITHER
    RAISES for a seal-derived subject, so the under-approximation converted
    into an exception rather than into a quieter answer. D6 escalated it to
    this layer twice, in ``GoReachabilityAnalyzer.roots``' own docstring, and
    correctly did not try to fix it there.

    **The mirror direction is NOT symmetric and stays a refusal**: a
    ``TEST_FUNCTION`` declared OUTSIDE the tests starts nothing, because ``go
    test`` runs ``TestX`` only out of a ``_test`` file, and accepting it would
    make a production helper named ``TestHelper`` a TEST root and everything
    below it a BREACH manufactured out of a naming convention. The clause above
    is what holds that, and a body repairing the file half by deleting BOTH
    clauses has opened exactly that hole.

    **Measured under ``feat/D5-relation-body``, 2026-08-11, base ``3eedd07``,
    each mutation applied alone to the shipped body and run over the WHOLE
    suite in a clone** (the seven ``FLOOR_GLOBS`` rows cannot run there and are
    excluded; that is expected, not collateral):

      * ``expected = by_kind`` — the pre-fix derivation, ``kind`` alone —
        reddens ``test_root_kind_derives_from_the_kind_and_the_declaring_file_together``
        and ``test_a_root_that_disagrees_with_its_own_file_or_names_no_kind_is_refused``,
        and nothing else;
      * ``expected = root.root_kind if in_test_file else by_kind`` — "accept
        whatever the row says in a test file" — reddens those two AND
        ``test_root_kind_is_derived_from_the_kind_and_never_asserted_by_the_row[test_function]``;
      * deleting the ``TEST_FUNCTION``-outside-the-tests clause reddens
        ``test_a_test_function_outside_the_tests_is_refused_in_both_spellings``
        and the ``…_disagrees_with_its_own_file…`` sibling, and nothing else —
        which is the measurement that says the mirror clause is load-bearing
        and may not be deleted to make the file half easier;
      * making this function a no-op reddens **11** rows. The seal author
        predicted "this row and nine others", i.e. 10; recorded as a
        divergence, in the direction of more coverage rather than less.

    **The sibling row survives the struck refusal, and for a BETTER reason** —
    checked directly rather than inferred from the suite being green: its "``func
    main`` inside ``contract_seal_test.go``" case, ``root_kind=PRODUCTION``,
    now raises "``…derives RootKind.TEST``" because the FILE derives TEST and
    the row asserted PRODUCTION. The same root spelled ``root_kind=TEST`` is
    accepted, which is the whole of the repair.
    """
    if not isinstance(root, Root):
        raise CallSiteReachabilityError(
            f"an analyzer produced {root!r}, which is not a Root"
        )
    by_kind = _ROOT_KIND_BY_ENTRYPOINT.get(root.kind)
    if by_kind is None:
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
    # BOTH halves of the derivation, per this function's own first paragraph.
    # A production kind declared in a test file is a TEST root, not a refusal:
    # `func init()` in a `_test.go`, and D6's `<vars:test>` GO_PACKAGE_VAR
    # symbol, RUN — in the test binary — and everything they reach is genuinely
    # reached under test. The file cannot make a TEST_FUNCTION production: the
    # clause above already refused that spelling, and the table derives TEST
    # for it anyway, so the two halves agree wherever both have an opinion.
    expected = RootKind.TEST if in_test_file else by_kind
    if root.root_kind is not expected:
        raise CallSiteReachabilityError(
            f"root {root.symbol.key!r} declares root_kind "
            f"{root.root_kind!r} while its kind {root.kind.value!r} declared "
            f"in {root.symbol.path!r} (is_test_path: {in_test_file}) derives "
            f"{expected!r}; root_kind is derived from the kind AND from the "
            "declaring file, never asserted by the row"
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




# --------------------------------------------------------------------------- #
# Part 3a — the import relation: which packages can name each other?
#
# Added by the P1 scaffold on ``feat/D5-import-relation``, 2026-08-11, base
# ``f4c7c46``. It exists to make ONE sentence computable — step 3 of
# :func:`check_subject` scoping its hole set to the SUBJECT rather than to the
# tree. Nothing here is wired into :func:`check_subject` yet; see
# :func:`holes_in_scope` for the seam and for what a body must land.
# --------------------------------------------------------------------------- #












def validate_import_relation(
    evidence: ImportEvidence, symbols: Mapping[str, Symbol]
) -> None:
    """Refuse a relation that would narrow on evidence nobody collected. Pure.

    **IMPLEMENTED and not stubbed.** The exception is :func:`validate_analyzers`'
    verbatim and it is the sharpest instance of it in this module: requirement 2
    of this round is that *an analyzer which cannot supply the relation must not
    silently yield an empty one*, and a seal cannot express "an empty relation
    is refused" without calling the function that refuses it. Prose cannot be
    unmistakable; a raise can. Everything else this round adds is a stub.

    Takes ``symbols`` rather than a :class:`CallGraph` because
    :func:`build_call_graph` calls it BEFORE the graph exists, and because a
    seal should be able to exhibit a bad relation without building a graph
    around it.

    :class:`ImportsUnavailable` is always well formed and returns immediately —
    that is the point of it. Raises :class:`CallSiteReachabilityError` on an
    :class:`ImportRelation` when:

      * ``packages`` is EMPTY while ``symbols`` is not. **The requirement-2
        refusal.** An empty relation over a non-empty tree is the fail-open:
        every package is its own component and every hole is scoped away from
        every subject outside it. An analyzer with nothing to say must say
        :class:`ImportsUnavailable`;
      * a map key and its record's ``package`` field disagree. Two spellings of
        one identity is one package wearing two names, and the components would
        depend on which spelling a caller looked up;
      * a symbol in ``symbols`` is in NO package's membership set. An unplaced
        symbol has no component, so every question asked about it fails closed —
        silently, and for a reason no report would show;
      * a symbol is in TWO packages' membership sets. It would be in two
        components, and :func:`ImportRelation.package_of` would answer by
        iteration order;
      * a package's membership set names a key the graph does not declare. A
        relation describing symbols the graph has never heard of is a relation
        built from a different tree;
      * an entry in ``imports`` names a package this relation does not carry. An
        edge to a node that does not exist cannot be traversed, and the
        traversal would either raise deep inside :func:`import_components` or
        silently drop the edge — and a silently dropped import edge is a
        wrongly-split component, which narrows harder;
      * ``external_import_count`` is negative, or is not an ``int``. The
        non-vacuity field, coerced, is no non-vacuity field at all; this is
        ``negative_is_conclusive``'s ``bool`` clause applied to the count that
        tells a reader whether imports were read.

    **It deliberately does NOT raise** when every package reports zero
    ``imports``, zero ``unplaced_imports`` and zero ``external_import_count``.
    CHOICE, and the rejected alternative is tempting: refusing an all-zero
    relation would catch an analyzer that stopped reading import blocks. It is
    out because a single-file package that imports nothing is legal in Go and
    common in Python, so the rule would refuse honest trees; the falsification
    belongs in a SEAL against a tree whose counts are known — 41 and 39 on the
    acceptance tree, measured under ``feat/D5-import-relation``, base
    ``f4c7c46``, 2026-08-11 — which is a row that reddens when the reading stops
    and never fires on an honest empty package.
    """
    if isinstance(evidence, ImportsUnavailable):
        return
    if not isinstance(evidence, ImportRelation):
        raise CallSiteReachabilityError(
            f"{evidence!r} is neither an ImportRelation nor an "
            "ImportsUnavailable; the absence of an import relation is a state "
            "with a name and a reason, never a bare value"
        )
    if symbols and not evidence.packages:
        raise CallSiteReachabilityError(
            f"an import relation with no packages was supplied for a graph "
            f"declaring {len(symbols)} symbol(s). An empty relation reads as "
            "'no package imports anything', which makes every package its own "
            "component and silently maximises the narrowing of step 3's hole "
            "set — the fail-open this mechanism refuses. An analyzer that "
            "cannot supply the relation must return ImportsUnavailable with a "
            "reason, which costs nothing and narrows nothing"
        )
    owner: dict[str, str] = {}
    for identity, package in evidence.packages.items():
        if package.package != identity:
            raise CallSiteReachabilityError(
                f"import relation keys {package.package!r} under {identity!r}; "
                "one package wearing two identities puts it in two components "
                "and makes the answer depend on which spelling was looked up"
            )
        if not isinstance(package.external_import_count, int) or isinstance(
            package.external_import_count, bool
        ):
            raise CallSiteReachabilityError(
                f"package {identity!r} declares external_import_count "
                f"{package.external_import_count!r}, which is not an int; the "
                "field exists so a reader can tell a tree of isolated packages "
                "from an analyzer that is not reading import statements, and a "
                "coerced count tells them neither"
            )
        if package.external_import_count < 0:
            raise CallSiteReachabilityError(
                f"package {identity!r} declares a negative "
                f"external_import_count {package.external_import_count}"
            )
        for key in package.symbols:
            if key not in symbols:
                raise CallSiteReachabilityError(
                    f"package {identity!r} claims symbol {key!r}, which this "
                    "graph does not declare; a relation describing symbols the "
                    "graph has never heard of was built from a different tree"
                )
            if key in owner:
                raise CallSiteReachabilityError(
                    f"symbol {key!r} is claimed by both {owner[key]!r} and "
                    f"{identity!r}; it would sit in two components and "
                    "package_of would answer by iteration order"
                )
            owner[key] = identity
    for identity, package in evidence.packages.items():
        for imported in package.imports:
            if imported not in evidence.packages:
                raise CallSiteReachabilityError(
                    f"package {identity!r} imports {imported!r}, which this "
                    "relation does not carry. An edge to a node that does not "
                    "exist is an edge the traversal must either raise on or "
                    "drop, and a dropped import edge splits a component that "
                    "should be joined — which narrows HARDER, on evidence that "
                    "was collected and then lost"
                )
    unplaced = sorted(key for key in symbols if key not in owner)
    if unplaced:
        raise CallSiteReachabilityError(
            f"{len(unplaced)} symbol(s) belong to no package in the import "
            f"relation, first {unplaced[0]!r}. An unplaced symbol has no "
            "component, so every question asked about it fails closed — "
            "correctly, and silently, and for a reason no report would show. "
            "Membership is data the analyzer already holds: it knows which "
            "unit emitted each symbol"
        )


def import_components(evidence: ImportEvidence) -> Mapping[str, frozenset[str]]:
    """Package identity -> every package in its UNDIRECTED import component.

    **IMPLEMENTED on ``feat/D5-relation-body``, 2026-08-11, base ``3eedd07``.**
    The ruled rule, computed once, here, where one seal can pin it. What the
    body owed, and what it landed:

      * **UNDIRECTED.** ``P`` imports ``Q`` puts ``P`` and ``Q`` in one
        component, both ways. A value crosses that one import in both
        directions: ``P`` can pass ``Q``'s function into ``Q``'s call, and
        ``Q``'s call can return one to ``P``. Reading :attr:`PackageImports.
        imports` directionally would discharge the positive claim in half the
        cases where it is false;
      * **TRANSITIVE.** ``P`` imports ``R``, ``Q`` imports ``R``: ``P`` and
        ``Q`` are in ONE component. ``R`` can hold ``Q``'s function value and
        hand it to ``P`` — ``R`` evaluates ``p.Register(q.S)`` — and this is not
        hypothetical: ``ANALYZERS`` in this very module is that shape, which is
        the measured refutation of same-module scoping that the P4 recorded and
        that a body must not re-open;
      * **AN UNPLACED IMPORT IS AN EDGE TO EVERY PACKAGE.** A package whose
        :attr:`PackageImports.unplaced_imports` is non-empty could import
        anything, including the subject's package, so its component is the
        WHOLE TREE — and because components are an equivalence, one unplaced
        import anywhere collapses the tree to a single component and step 3
        reverts to today's whole-tree behaviour. That is severe and it is
        exactly what "an unresolved import counts as an edge, never as an
        absence" means. A body that finds this too blunt is asking for a ruling,
        not for a heuristic;
      * **RAISES on** :class:`ImportsUnavailable`, rather than returning one
        component or an empty mapping. A caller that has not handled the
        refusal must not be able to slide past it into a component computation
        that answers anyway; :func:`holes_in_scope` branches on the state
        FIRST and this raise is what forces it to.

    CHOICE (the return could have been ``Mapping[str, str]``, package ->
    canonical representative, which is what a union-find naturally produces): the
    full MEMBER SET per package. Rejected alternative is cheaper and is the
    obvious spelling; it is out because a representative is an arbitrary
    identity with no meaning, so a seal pinning it pins the traversal's tie-break
    rather than the partition, and a report printing it names a package the
    reader did not ask about. The member set answers the question a caller
    actually has — "is the hole's package in here" — with no second lookup.

    CHOICE, and it is the ONE policy question the contract left open (the body
    of ``feat/D5-relation-body``, recorded as **DISPUTE B1**): what to do with
    an entry in ``imports`` naming a package the relation does not carry.
    :func:`validate_import_relation` REFUSES that shape, and it runs on every
    relation :func:`_union_import_evidence` returns, so this branch is
    unreachable from production — but this function is public and a seal or a
    later caller can hand it an unvalidated relation. Its own docstring names
    the two bad options, "either raise deep inside :func:`import_components` or
    silently drop the edge", and this body takes NEITHER: a dangling target is
    treated exactly as an :attr:`PackageImports.unplaced_imports` entry — an
    import that could not be placed onto a package of this tree — and therefore
    as an EDGE TO EVERY PACKAGE. Three reasons: it applies the ruled rule
    instead of inventing a fourth policy for the same fact; it can only
    COLLAPSE and never SPLIT, so it cannot narrow on evidence that was
    collected and then lost; and it cannot turn a data drift into an outage in
    a module that is a gate. Defence in depth, not a substitute: the loud
    refusal is still :func:`validate_import_relation`'s and still fires first.

    **Measured under ``feat/D5-relation-body``, 2026-08-11, base ``3eedd07``:**
    on the acceptance tree this returns 2 components, one per package — the
    scaffold's prediction reproduced by running it. On the reach fixture
    ``evenplay-mono/apps/website-public-api`` @ ``51a71736c`` (12 packages, 24
    directed in-tree edges) it returns ONE component of 12, against 12
    singletons for the same node set with the imports removed. Run against all
    four candidate readings the seals separate, on that fixture: **this is the
    TRUTH** — the empty relation gives 12 singletons, a directed reading gives
    ``internal/snapshot`` a member set of 1 though five packages import it, and
    a direct-only reading gives ``cmd/public-api`` 8 of 12. This body matches
    the truth and none of the other three.

    **DISPUTE B1 is measured as UNPINNED and is recorded rather than defended
    by a row**: replacing the collapse with a raise reddens NOTHING in the
    whole suite (2026-08-11, clone, whole suite). The choice above rests on the
    contract's reasoning and not on a seal, and a seal author who disagrees
    with it can overturn it at no cost to any existing row.
    """
    if isinstance(evidence, ImportsUnavailable):
        raise CallSiteReachabilityError(
            f"import_components was asked for the components of "
            f"{evidence!r}; an absent relation has no components, and "
            "answering anyway — with an empty mapping, or with one "
            "all-packages component — would let a caller that never handled "
            "the absence slide into a narrowing computed over evidence "
            "nobody collected. Branch on the state first; see holes_in_scope"
        )
    if not isinstance(evidence, ImportRelation):
        raise CallSiteReachabilityError(
            f"{evidence!r} is neither an ImportRelation nor an "
            "ImportsUnavailable, so it has no components"
        )

    nodes = frozenset(evidence.packages)
    whole_tree = {identity: nodes for identity in nodes}

    # An unplaced import is an edge to EVERY package: a package whose reach
    # cannot be bounded could import anything, including the subject's, so the
    # positive claim cannot be discharged against any subject at all. Because
    # components are an equivalence, one such package anywhere collapses the
    # tree — which is severe, and is exactly what the ruling says.
    for package in evidence.packages.values():
        if package.unplaced_imports:
            return whole_tree

    parent: dict[str, str] = {identity: identity for identity in nodes}

    def _find(node: str) -> str:
        root = node
        while parent[root] != root:
            root = parent[root]
        while parent[node] != root:
            parent[node], node = root, parent[node]
        return root

    for identity, package in evidence.packages.items():
        for imported in package.imports:
            if imported not in parent:
                # DISPUTE B1 above: an edge to a node this relation does not
                # carry is an import that could not be placed on this tree.
                return whole_tree
            # UNDIRECTED: `P imports Q` joins them both ways, because a value
            # crosses that one import in both directions — P can pass Q's
            # function into Q's call, and Q's call can return one to P.
            # TRANSITIVE falls out of the union: P and Q both importing R are
            # one component, and R can evaluate `p.Register(q.S)`.
            left, right = _find(identity), _find(imported)
            if left != right:
                parent[left] = right

    members: dict[str, set[str]] = {}
    for identity in nodes:
        members.setdefault(_find(identity), set()).add(identity)
    return {
        identity: frozenset(members[_find(identity)]) for identity in nodes
    }


def holes_in_scope(
    subject: Symbol,
    holes: Sequence[tuple[Symbol, str, str]],
    evidence: ImportEvidence,
) -> tuple[tuple[Symbol, str, str], ...]:
    """The holes that could be the missing call site FOR THIS SUBJECT.

    **IMPLEMENTED AND WIRED on ``feat/D5-relation-body``, 2026-08-11, base
    ``3eedd07``**, as the one line step 3 of :func:`check_subject` grows. This
    is question 4 of the brief — where the filtering happens — and the answer is
    HERE, in D5, never in an analyzer. Three reasons, the third decisive:

      1. the rule is a ruling about JUDGEMENT and not a fact about a language.
         An analyzer's job is to report what it read; deciding what a hole
         licenses is this module's;
      2. one implementation means one seal. Seven language rows would be seven
         chances to get the undirected half or the unplaced half wrong, and a
         row that got either wrong would narrow HARDER on evidence nobody
         checked;
      3. ``call_site_reachability.py`` is on ``FLOOR_GLOBS`` and
         ``go_reachability.py`` is not. This filter moves an ABSTAIN to a BREACH
         and back. A decision of that weight may not live in a module that four
         of the five roles can rewrite on the branch it is judging.

    ``holes`` is the list step 3 already computed — entries of
    :attr:`CallGraph.unresolved_calls` whose caller is in the production closure.
    **The closure filter stays in :func:`check_subject` and is NOT moved in
    here.** Two conjuncts, two functions, two seals: the closure conjunct is
    already pinned by
    ``test_unresolved_calls_abstain_only_over_the_production_closure`` and a
    body that folded it in here would make that row pass through this stub's
    body, where a defect in either conjunct could be blamed on the other.

    What the body owes:

      * :class:`ImportsUnavailable` -> **return ``holes`` UNCHANGED.** No
        relation, no narrowing, today's behaviour. This branch is the whole of
        requirement 2 in one line and it must be the FIRST thing the function
        does, before any component computation, because
        :func:`import_components` raises on that state;
      * a ``subject.key`` that :func:`ImportRelation.package_of` cannot place ->
        return ``holes`` unchanged. Unknown component, fail closed;
      * a hole whose ``hole[0].key`` cannot be placed -> KEEP that hole. Same
        reason, per hole rather than per call;
      * otherwise keep exactly the holes whose caller's package is in the
        subject's package's component, per :func:`import_components`;
      * **ORDER PRESERVED.** :func:`check_subject`'s abstention detail names
        ``holes[0]``, and a filter that reordered would move which site a human
        is sent to without moving a verdict — the failure this module calls a
        prose-driven flip, in the one register where nothing would be red.

    **Measured under ``feat/D5-import-relation``, base ``f4c7c46``, 2026-08-11,
    by driving the real :func:`check_subject` over the acceptance tree with its
    hole set scoped by hand exactly as this contract specifies — the P4's
    number REPRODUCED and not trusted:**

        hole set                          scope=tree   scope=subject
        2 holes (this base, D6's rule 1)     0 of 7        **4 of 7**
        7 holes (before D6's rule 1)         0 of 7          0 of 7
        0 holes                              7 of 7          7 of 7

    The four that come back are ``cmd/iterate``'s, and they come back
    :attr:`Reach.FROM_TESTS_ONLY` / :attr:`Disposition.BREACH` — which is the
    correct answer, since ``VerifyPreservation`` is dark in ``cmd/iterate`` too.
    ``cmd/gates``' three still abstain, because both holes are in
    ``cmd/gates/main.go``. **The 7-hole row is why this contract is worth
    landing and also why it is not a cure**: five of those seven were in
    ``cmd/iterate`` itself, so subject scoping alone answered nothing until D6's
    body resolved them. Scoping and resolution are independent and this round
    buys neither on its own.

    CHOICE (the signature could have taken ``production_reach`` and done both
    conjuncts, or taken a :class:`CallGraph` and read the evidence off it):
    three explicit arguments, evidence passed in. Rejected alternatives: doing
    both conjuncts is refused above; taking the graph would let this function
    read ``unresolved_calls`` itself and quietly re-derive the closure filter it
    was told not to own, and would make a seal build a whole graph to exhibit a
    two-package question.

    **THE SEAM THAT CANCELS INVISIBLY, and how this body avoids it.** Package
    identity is whatever :meth:`ImportRelation.package_of` ANSWERS, and this
    function derives it nowhere else. There is no ``rpartition('.')`` here and
    there must never be one: a Go method key is
    ``…/cmd/gates.(*Runner).dispatch``, a body splitting on the last dot
    invents the package ``…/cmd/gates.(*Runner)``, finds it in no component,
    fails closed, and KEEPS a hole the truth scopes away. **Measured under
    ``feat/D5-relation-body``, 2026-08-11, base ``3eedd07``:** that mutation
    reddens
    ``test_a_method_key_is_placed_through_package_of_and_never_by_string_surgery``
    and NO other row in the suite.

    **The narrowing can only ever REMOVE holes, by construction and not by
    luck**: the output is built by appending a subset of ``holes`` in input
    order, so it is a subsequence of the input; step 3 abstains iff the hole set
    is non-empty; therefore this can only make the mechanism abstain LESS often
    and can never manufacture a BREACH out of a hole it invented. Step 1 still
    runs first and a found path is still found.

    **Measured under ``feat/D5-relation-body``, 2026-08-11, base ``3eedd07``,
    by driving the real :func:`check_subject` over the acceptance tree with a
    hand-built relation for its two packages — the P4's number and the seal
    author's REPRODUCED and not trusted:**

        hole set                          scope=tree   scope=subject
        2 holes (this base, D6's rule 1)     0 of 7        **4 of 7**

    The four that come back are ``cmd/iterate``'s, :attr:`Reach.FROM_TESTS_ONLY`
    / :attr:`Disposition.BREACH`. ``cmd/gates``' three still abstain, because
    both holes are in ``cmd/gates/main.go``. **With the relation absent — which
    is every tree at this revision, since :data:`ANALYZERS` is ``()`` — the
    answer is 0 of 7, unchanged, because the first branch returns the input.**
    Neither regime produced a single :attr:`Reach.FROM_PRODUCTION` or a single
    :attr:`Disposition.OK`, asserted in the harness rather than eyeballed.

    **THE ABSENCE BRANCH IS WORTH MORE THAN THE SEAL RECORDS, and the
    difference is the wiring line.** ``test_an_absent_relation_leaves_the_hole_
    set_exactly_as_it_found_it`` records that returning ``()`` on the absence
    "reddens this row and ``…_narrowing_only_ever_removes_holes…``, and nothing
    else" — measured by the seal author against a throwaway reference
    implementation in a clone, which had no call site. **Re-measured against
    the SHIPPED body, whole suite, 2026-08-11: that mutation reddens FOUR
    rows** — those two, plus
    ``test_unresolved_calls_abstain_only_over_the_production_closure`` here and
    ``test_the_step_three_abstention_is_measured_and_the_implication_is_total``
    in ``tests/test_go_reachability.py``. Once step 3 actually calls this
    function, two rows that judge REAL TREES become guards on the absence
    branch. The seal author's figure was right for the artifact it was measured
    on; it is not the figure for the wired module.
    """
    if isinstance(evidence, ImportsUnavailable):
        # Requirement 2, and it is FIRST because import_components raises on
        # this state. No relation, no narrowing: the absence degrades to the
        # CURRENT sealed behaviour and never to the maximally-narrowed one.
        return tuple(holes)

    components = import_components(evidence)

    home = evidence.package_of(subject.key)
    if home is None or home not in components:
        # Unknown component, and an unknown component may be any hole's. Fail
        # closed over the whole call.
        return tuple(holes)
    reachable = components[home]

    kept: list[tuple[Symbol, str, str]] = []
    for hole in holes:
        package = evidence.package_of(hole[0].key)
        # Same rule per hole: a key the relation cannot place has an unknown
        # component, and an unknown component may be the subject's.
        if package is None or package not in components or package in reachable:
            kept.append(hole)
    return tuple(kept)




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
      * **The import relation is UNIONED, and the union is fail-closed.** Added
        on ``feat/D5-import-relation``, 2026-08-11. See
        :func:`_union_import_evidence` for the three rules and for why this
        function implements them rather than stubbing them.
    """
    symbols: dict[str, Symbol] = {}
    edges: list[Edge] = []
    unresolved: list[tuple[Symbol, str, str]] = []
    unreadable: list[str] = []
    evidence: list[ImportEvidence] = []
    for analyzer in _analyzers_present(tree)[0]:
        try:
            produced = analyzer.graph(tree)
        except SourceUnreadable as exc:
            # Recorded, never raised past: raising here would lose every other
            # file's edges and turn one bad file into a total outage of the
            # check. It abstains over the whole tree at judgement time instead.
            unreadable.append(exc.path)
            # An analyzer that could not read a file may have missed that
            # file's import block, so it has no relation to contribute and the
            # union must not read its silence as "this language has no imports".
            evidence.append(
                ImportsUnavailable(
                    reason=(
                        f"the {_language_of(analyzer)!r} analyzer could not "
                        f"read {exc.path}, so the imports declared there were "
                        "never seen"
                    )
                )
            )
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
        evidence.append(produced.package_imports)
    ordered = {key: symbols[key] for key in sorted(symbols)}
    return CallGraph(
        symbols=ordered,
        edges=tuple(sorted(edges, key=_edge_order)),
        unresolved_calls=tuple(
            sorted(unresolved, key=lambda hole: (hole[0].key, hole[1], hole[2]))
        ),
        unreadable_paths=tuple(sorted(dict.fromkeys(unreadable))),
        package_imports=_union_import_evidence(evidence, ordered),
    )


def _union_import_evidence(
    parts: Sequence[ImportEvidence], symbols: Mapping[str, Symbol]
) -> ImportEvidence:
    """Every analyzer's import relation, or the named refusal. Pure.

    **IMPLEMENTED and not stubbed, and it is the third exception this module
    makes.** :func:`build_call_graph` is the ONE production construction site of
    a :class:`CallGraph`, so a stub here would either redden every seal that
    calls it or — worse, if it returned the default — make the whole relation
    dead on arrival, present in the type and never populated by the only caller
    that could populate it. A field the production path never fills is a field
    that reads as coverage and is not. It is also the layer that has to enforce
    the union's fail-closed rule, which is a decision and not a body.

    Three rules, and each one fails CLOSED:

      1. **No parts at all -> :data:`IMPORTS_NOT_SUPPLIED`.** Today's world:
         :data:`ANALYZERS` is empty, no analyzer ran, and there is no evidence
         about anything. Not an empty relation.
      2. **Any part is :class:`ImportsUnavailable` -> the whole union is
         :class:`ImportsUnavailable`**, carrying that part's reason. Not a
         partial relation over the languages that did answer: the packages the
         silent analyzer did not describe could be adjacent to any of the ones
         it did, and a relation that omits them would split components that
         should be joined — which narrows HARDER. One language's silence
         suspends the narrowing for the whole tree, which is the same shape as
         :class:`SourceUnreadable`'s whole-tree abstention and is chosen for the
         same reason.
      3. **Otherwise merge the package maps**, and a package identity supplied
         by two analyzers RAISES. Two rows describing one package could disagree
         about its imports and the components would depend on row order — the
         defect :func:`validate_analyzers` refuses at the registry level, met
         again at the value level.

    The merged result is handed to :func:`validate_import_relation` before it is
    returned, so a body that builds an empty or inconsistent relation is refused
    at the construction site rather than at the first narrowing.

    **Measured under ``feat/D5-import-relation``, base ``f4c7c46``,
    2026-08-11**, over the acceptance tree with the live Go row substituted into
    :data:`ANALYZERS`: :attr:`CallGraph.package_imports` comes back
    :class:`ImportsUnavailable`, because the Go row's :meth:`graph` does not
    populate the field yet and its :class:`CallGraph` therefore carries the
    default. That is the correct answer today and it is the one that changes
    nothing: with the relation absent, :func:`holes_in_scope` is contracted to
    return its input unchanged, so step 3 keeps the whole-tree hole set and all
    7 findings still abstain. With no analyzers at all the field is
    :data:`IMPORTS_NOT_SUPPLIED` itself. Rules 2 and 3 and each clause of
    :func:`validate_import_relation` were exercised directly at the same
    revision; none of them is reachable from a tree today, which is what a seal
    author needs to know before writing rows against them.

    CHOICE (the union could have kept one relation per LANGUAGE and had
    :func:`holes_in_scope` pick the subject's): one relation over the whole
    tree. Rejected alternative is more precise per language and is out because
    a cross-language question — a Go hole and a Python subject — would then have
    no relation at all to consult, and "no relation" would have to mean either
    "different components" (fail-open, and wrong: a Python module and a Go
    binary in one repo genuinely cannot share a function value, but a mechanism
    may not assert that from the absence of a table) or "one component"
    (correct, and reachable more simply by rule 2 above).
    """
    if not parts:
        return IMPORTS_NOT_SUPPLIED
    for part in parts:
        if isinstance(part, ImportsUnavailable):
            return part
    merged: dict[str, PackageImports] = {}
    for part in parts:
        if not isinstance(part, ImportRelation):
            raise CallSiteReachabilityError(
                f"{part!r} is neither an ImportRelation nor an "
                "ImportsUnavailable and cannot be unioned; the absence of an "
                "import relation is a state with a name and a reason"
            )
        for identity, package in part.packages.items():
            if identity in merged:
                raise CallSiteReachabilityError(
                    f"two analyzers both describe package {identity!r}; they "
                    "could disagree about its imports and the components would "
                    "then depend on analyzer row order"
                )
            merged[identity] = package
    relation = ImportRelation(packages={key: merged[key] for key in sorted(merged)})
    validate_import_relation(relation, symbols)
    return relation


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
    #:
    #: **P4 RULING (round 2, 2026-08-11).** The body reported that this sentence
    #: is contracted and underivable — :class:`ReachabilityAnalyzer` carries no
    #: method by which a row could supply one — and asked whether the protocol
    #: grows a method or the sentence changes to admit derivation.
    #: **THE PROTOCOL GROWS THE METHOD. The sentence stands, unedited.** Three
    #: reasons, in ascending order of how much they should bind:
    #:
    #:   1. **The sentence names a measured failure, and the derivation commits
    #:      it.** ``_test_id`` yields ``<directory>.<last segment>``. For Go that
    #:      is ``cmd/classify.TestSeal_ResolveConfigDual``, which is right. For
    #:      Python it is ``tests.test_a_seal_covers_production``, which is not a
    #:      pytest node id, is not runnable, and is exactly "a report that
    #:      guessed would send people to nothing" — in the language the
    #:      dispatcher itself is written in. Striking the sentence would ratify
    #:      shipping that.
    #:   2. **The spelling is per-language BY THE SENTENCE'S OWN WORDS, and this
    #:      module answers per-language questions with a ROW.** It holds no file
    #:      extension and calls no ``endswith`` because ``role_protocol`` owns
    #:      that question; it has one matcher for "is this a test file" because
    #:      two would drift. ``_test_id`` is a second, central, language-blind
    #:      answer to a question the registry exists to answer, and it drifts
    #:      the same way: silently, on the language nobody has pointed it at.
    #:   3. **The row already owns the other half of this question.**
    #:      ``test_root_predicate`` decides per language whether a symbol is a
    #:      test entrypoint. The row that knows a symbol is a pytest test is the
    #:      row that knows how to spell its node id, and splitting the two puts
    #:      half of one question in the table and half in a helper.
    #:
    #: What that costs, stated so it is a decision and not an oversight: a
    #: fourth method on a protocol with no rows yet, so it is free today and
    #: binding on the first analyzer written. What it does NOT cost is any
    #: verdict — ``test_id`` is a label on a finding and no dispatch reads it.
    #: :func:`_test_id` names the interim and what deletes it.
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

    DISPUTE RULED (P4 round 2, 2026-08-11): **the protocol grows the method and
    this function is an INTERIM with an expiry.** The argument is at
    :attr:`Seal.test_id`; what it leaves here is a schedule.

    The dispute was correct as raised. :class:`Seal` contracts ``test_id`` as
    "not derived at report time: the spelling differs by language and a report
    that guessed it would send people to nothing", and
    :class:`ReachabilityAnalyzer` carries no method by which a row could supply
    one, so the only layer that could honour the sentence had no channel to it.
    The derivation below — the declaring DIRECTORY, then the symbol's own last
    segment — is the Go ``package.TestName`` spelling the seals pin, and is a
    defensible pytest node id only by accident. It stands ONLY while
    :data:`ANALYZERS` is empty, because with no row there is nothing to ask.

    **P3 owes four coupled edits and they land together or not at all**, because
    three of them are unobservable without the fourth:

      1. ``def test_id(self, symbol: "Symbol") -> str: ...`` on
         :class:`ReachabilityAnalyzer`, beside ``test_root_predicate``.
      2. ``"test_id"`` added to :func:`validate_analyzers`' required-method
         tuple. A protocol member no shape check enforces is the "decorator that
         looks like a shape check and is not one" this protocol's own docstring
         refuses, reintroduced as an omission.
      3. :func:`discover_seals` calls the ROW rather than this helper, resolved
         over ``root.symbol.path`` the way every other per-language dispatch
         here resolves.
      4. This function is deleted. It has no other caller.

    **ESCALATED, and P3 may not resolve it: (2) reddens the seal file.** The
    ``_Analyzer`` double in ``tests/test_call_site_reachability.py`` carries no
    ``test_id``, so the day ``validate_analyzers`` requires one, every row that
    builds a double fails validation. Seals are not a body's to edit and this
    adjudicator deliberately did not pre-amend the double: what a GO row's
    ``test_id`` RETURNS is a claim about Go's spelling, the double is contracted
    as "data in, the same data out", and choosing its return value here would be
    a P4 writing the seal author's assertion for them. The landing needs one
    round that carries the production edit and the double together.
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
    #:
    #: **ORDER IS NOT CONTRACTED (P4 ROUND 3, 2026-08-11), and the absence is
    #: written down rather than left to be re-derived.** The body sorts by key,
    #: and that ``sorted()`` is an uncontracted determinism convenience, not a
    #: promise: :func:`build_call_graph` already sorts its edges by
    #: ``(caller.key, callee.key, …)``, so per caller the callees arrive
    #: ordered and the call idles on every graph the one production path
    #: produces. It does real work for OTHER callers — this function is public
    #: and takes the graph as an argument, and :class:`CallGraph` contracts its
    #: edges as being "in no guaranteed order" — measured at ``4e66a01``:
    #: edges handed in as ``(Zulu, Alpha)`` come back ``(Alpha, Zulu)``.
    #:
    #: No row pins it, deliberately (Part 11's gap 6). Nothing reads the order:
    #: :func:`check_tree` re-sorts findings on ``(test_id, subject key)``,
    #: which is total over them. A row here would legislate a contract into
    #: existence for the row's own benefit rather than guard one that exists.
    #: What would change that: the first consumer whose answer depends on this
    #: order — at which point the contract is written FIRST and the row
    #: follows it, in that order.
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
    #: pins the constructor half.
    #:
    #: **P4 ROUND 3 (2026-08-11): "the :func:`check_tree` half is unpinned by
    #: any row" was true when it was written and is now FALSE, so it is
    #: struck.** ``test_check_tree_refuses_a_subject_record_a_second_constructor_built``
    #: pins it, by SUBSTITUTING :func:`subjects_of_seal` to be the second
    #: constructor R2 hypothesises — the device P4 round 3 ratifies. Left
    #: standing, the sentence would be a coverage claim contradicted by the
    #: file it describes, which is the defect the same round ruled on one level
    #: up.
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
    calls it as a precondition on every record it consumes. The second was
    written while unpinned by any row — the layer that ACTS on a non-judgement
    is the layer where the non-judgement becomes an answer, and a record
    arriving from a second constructor is not constructible today only because
    there is no second constructor today.

    **P4 ROUND 3 (2026-08-11): it is pinned now, so "unpinned" is struck.**
    ``test_check_tree_refuses_a_subject_record_a_second_constructor_built``
    substitutes :func:`subjects_of_seal` — a name in :data:`__all__` — with a
    constructor that returns each contradiction in turn, and requires
    :func:`check_tree` to raise on both. Deleting the ``_validate_subject``
    call in :func:`check_tree` reddens that row and no other.
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
        permanent fact about the gate, not about the machine. **Emitted at
        :func:`check_tree`, per subject symbol** — P4 round 2 confirming the
        body's placement; the site is named here because a member whose
        composition nobody wrote is a member nobody can find.
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
        bad. Abstains over the whole tree; see that class. **Emitted at
        :func:`check_subject` step 1b — after the found-path check and BEFORE
        ``NO_ENTRYPOINT``** (P4 round 2, confirming the body's placement). The
        order is not a detail: it decides which abstention a caller sees when
        both hold, and the reason it must be this one is written at that step.
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

    **SECOND CHOICE, ``feat/D5-import-relation``, 2026-08-11 — the closure is
    the first conjunct and the SUBJECT is the second.** The CHOICE above got the
    direction right and stopped one narrowing short, and the shortfall is
    measured on the acceptance tree at this base: the closure conjunct leaves 2
    holes, both in ``cmd/gates/main.go``, and because ``production_reach`` is
    ONE whole-tree map the list is identical for every (seal, subject) pair —
    so those 2 abstain all 7 findings, including ``cmd/iterate``'s 4, which no
    execution path connects to either hole. **0 of 7 answered.** With the hole
    set also scoped to the subject: **4 of 7**, measured, both numbers under
    ``feat/D5-import-relation``, base ``f4c7c46``, 2026-08-11.

    Two readings of "scoped" were considered and REFUSED, and the reasons are
    recorded so a body does not rediscover them:

      * **same-MODULE scoping is unsound.** ``R`` imports ``P`` and ``Q`` and
        evaluates ``p.Register(q.S)``; a hole in ``P`` then calls a value
        declared in ``Q``. :data:`ANALYZERS` in this module is that shape. A Go
        module bounds NAMING, never value flow;
      * **CALL-GRAPH components are unsound in the permissive direction.** A
        package imported for a name only contributes no call edge, so
        call-graph components under-approximate import components and would
        scope away a hole that can reach the subject.

    What survives is the undirected IMPORT component, with an unresolved import
    counting as an edge; see :class:`PackageImports` and
    :func:`import_components`. Not wired at this commit — the mechanism is
    :func:`holes_in_scope` and it is a stub — so every count above and every
    seal on this member is unmoved today.
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
    :class:`CallSiteReachabilityError` rather than tolerated fields: a finding
    that carries a path AND an undecided reason has two answers, and a report
    showing both would be read as whichever one the reader wanted.

    **P4 RULING (round 2, 2026-08-11): THE SENTENCE STANDS AND ITS ADDRESS
    CHANGES. The raise is owed by :func:`check_subject` as a POSTCONDITION and
    by :func:`check_tree` as a PRECONDITION; "at :func:`adjudicate`" is
    struck.** The body reported the contradiction exactly right — enforcing the
    rule at :func:`adjudicate` empties ``rulings[FROM_PRODUCTION]`` and reddens
    two grid rows — and asked whether the raise moves or the sentence goes. It
    moves, and this is R2 a second time, on a second record, with the same
    answer:

      * **:func:`adjudicate` reads neither field it was told to validate.** It
        is a lookup on ``(reach, quality)``. Filing a consistency check about
        ``reason`` and ``path`` there is the scaffold's R2 error verbatim — it
        located the malformed-:class:`Subject` raise at :func:`check_subject`,
        which has no :class:`Subject` parameter. A validation belongs where the
        record is BUILT and where it is ACTED ON, not at whichever function the
        record happens to pass through.
      * **The seals were RIGHT, and that is why nothing they do changes.** They
        hand-build ``(reach, quality, reason=DYNAMIC_EDGE, path=None)`` to sweep
        a dispatch that reads two fields, which is the correct way to seal a
        two-field dispatch. Under this ruling they keep working unedited, and
        the fact that the body could not make both stand was information about
        the scaffold rather than about the rows.
      * **"Unreachable from inside the module" is not a reason to strike it —
        R2 already refused that argument on the identical shape.**
        :func:`subjects_of_seal` is :class:`Subject`'s only constructor and is
        consistent by construction too, and R2 still put the check at both
        layers, "because a second constructor or a caller-supplied record would
        otherwise reach the judgement loop unchecked". One record may not get a
        different doctrine from its twin.

    What that costs: two checks against a state neither can currently reach.
    What striking it would have cost: the only statement anywhere that a finding
    may not carry two answers, deleted because the layer it was misfiled at
    could not enforce it.

    **IMPLEMENTED (``feat/D5-body2``, 2026-08-11):** :func:`_validate_finding`
    runs on every ``return`` in :func:`check_subject` and on every finding
    :func:`check_tree` acts on. :func:`adjudicate` gained nothing and lost the
    sentence. No seal was edited and no verdict moved, which is what the ruling
    predicted: the two grid sweeps hand-build findings whose ``reason`` and
    ``path`` are arbitrary, and neither of them goes through either layer.

    Each layer is load-bearing without the other, measured rather than argued
    (``feat/D5-body2``, 2026-08-11). The postcondition is the only guard on a
    direct :func:`check_subject` call, which is how every D5 seal reaches this
    module while :data:`ANALYZERS` is empty. The precondition is the only guard
    on the findings :func:`check_tree` builds itself — the
    ``UNSUPPORTED_LANGUAGE`` abstention and :func:`_unnameable_finding` — which
    :func:`check_subject` never sees.

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
    roots: Sequence[Root],
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
      1b. **``graph.unreadable_paths`` is non-empty -> UNDECIDED /
         PARSE_FAILED.** Whole-tree, per :class:`SourceUnreadable`'s CHOICE.

         **P4 CONFIRMS THE BODY'S PLACEMENT (round 2, 2026-08-11), and the
         position relative to step 2 is the substantive half.** The contract
         named ``PARSE_FAILED`` in :class:`UndecidedReason` and in no
         composition, so the body placed it and asked. After step 1 for the
         reason step 1 gives: a found path is not un-found by a file nobody
         could read. **Before step 2 because the two abstentions are not
         equals.** ``NO_ENTRYPOINT`` is a positive claim ABOUT THE TREE — "this
         tree has no production entrypoint of any :class:`EntrypointKind`" —
         and an unparsed file is exactly where an undiscovered ``func main``
         would be, so that claim is computed around the hole and the mechanism
         cannot support it. ``PARSE_FAILED`` is the confession that the tree was
         not fully read. When both hold, a caller must see the confession: the
         other reading has the mechanism asserting a fact it derived around a
         gap, which is anti-requirement 2 in the abstention register — failing
         to look may only make an answer LESS conclusive. Same discriminator as
         R1's: whether the mechanism knew what it was abstaining ABOUT.
      2. **Zero production roots -> UNDECIDED / NO_ENTRYPOINT.** Before the
         tests-only check, because with no production root the tests-only
         answer is arithmetically guaranteed and would be a BREACH against
         every subject in a library.
      3. **``analyzer.negative_is_conclusive`` is False, or the production
         closure holds unresolved calls -> UNDECIDED / DYNAMIC_EDGE.** The
         second half is counted over the production closure only; see the
         CHOICE on :class:`UndecidedReason`.

         **CONTRACT CHANGE, ``feat/D5-import-relation``, 2026-08-11 — SCOPED.
         WIRED on ``feat/D5-relation-body``, base ``3eedd07``.** The operator
         ruled that step 3's hole set is scoped to the SUBJECT. What that means
         is :func:`holes_in_scope`; what fills the evidence it reads is
         :attr:`CallGraph.package_imports`. The line that landed is

             holes = holes_in_scope(subject, holes, graph.package_imports)

         directly after the closure comprehension, plus the regime marker on
         the detail below, and nothing else in this function. **No verdict on
         any tree moves at this revision**: :data:`ANALYZERS` is ``()``, so
         :func:`_union_import_evidence` returns :data:`IMPORTS_NOT_SUPPLIED`
         for every graph this module can build, and the first branch of
         :func:`holes_in_scope` returns its input unchanged. Measured on
         ``feat/D5-relation-body``, 2026-08-11: 0 rows in the suite move on the
         wiring line alone. Spelled out here because "which sentences change"
         is a question the seal author asks first:

           * **STANDS — the two disjuncts and their order.** The
             ``negative_is_conclusive`` half is untouched: it is a fact about a
             LANGUAGE and no import graph bears on it. The row check still runs
             FIRST, so a ``False`` row abstains before any scoping question is
             asked and a repository cannot buy itself a verdict by having tidy
             imports.
           * **STANDS — the closure conjunct.** Holes are still counted over
             the production closure only, and
             ``test_unresolved_calls_abstain_only_over_the_production_closure``
             is untouched. Scoping is a SECOND conjunct applied to what that one
             already returned; it never widens the set.
           * **STANDS — the placement of step 3 in the composition**, and
             therefore anti-requirement 2: step 1 still finds paths before any
             abstention, and this change can only make the mechanism abstain
             LESS, never make it abstain over a found path.
           * **STANDS — DYNAMIC_EDGE may only DOWNGRADE.** Narrowing the hole
             set removes abstentions; it can promote a subject to
             :attr:`Reach.FROM_TESTS_ONLY` and thence to a BREACH, which is
             the whole point, and it can never touch
             :attr:`Reach.FROM_PRODUCTION`.
           * **CHANGES — "the production closure holds unresolved calls".** It
             becomes "the production closure holds an unresolved call THAT
             COULD BE THIS SUBJECT'S MISSING CALL SITE". The old sentence is
             whole-tree and its cost is measured: on the acceptance tree, 2
             holes in ``cmd/gates/main.go`` abstain all 7 findings, 4 of which
             are in ``cmd/iterate`` and cannot be reached from either hole by
             any route.
           * **CHANGED — the abstention DETAIL.** It counts the scoped holes,
             so the number a report shows stops being a whole-tree constant,
             and it now names WHICH regime produced it: with the relation
             absent the string says so, and says the reason the absence
             carried, because "2 holes" under scoping and "2 holes" under no
             evidence are different facts about the mechanism's confidence. See
             :class:`ImportsUnavailable`. **No row in the suite reads this
             string**, measured on ``feat/D5-relation-body``, 2026-08-11, by
             garbling it in a clone and running the whole suite: 0 red. So the
             regime marker is landed on the contract's authority and not on a
             seal's; a seal author who wants it pinned should pin it. Recorded
             as **DISPUTE B2**.
           * **UNCHANGED and worth stating — ``ReachabilityReport.
             unresolved_call_count``.** It stays the whole-tree,
             closure-filtered count, because it is a report-level coverage
             figure about the TREE and not about one subject. A per-subject
             figure would make the report's own blindness metric a function of
             which subject a reader happened to look at.

         **Measured under ``feat/D5-import-relation``, base ``f4c7c46``,
         2026-08-11: 4 of the acceptance tree's 7 findings are answered under
         this contract, against 0 today.** The full table, the controls, and how
         the measurement was taken are on :func:`holes_in_scope`.
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

    **POSTCONDITION (P4 round 2, 2026-08-11): every :class:`Finding` this
    function returns satisfies :class:`Finding`'s reason/path consistency rule,
    and a violation RAISES here.** This function is that record's only
    constructor in this module and it must not be able to RETURN a finding that
    carries two answers, on R2's reasoning for :func:`subjects_of_seal`
    verbatim. The five returns are consistent by construction today, which is
    the argument for the check being cheap and not the argument for its absence
    — R2 refused that argument on the identical shape. See :class:`Finding`.
    **IMPLEMENTED (``feat/D5-body2``, 2026-08-11):** :func:`_validate_finding`
    is called on the record every ``return`` below hands back, at the ``return``
    and not inside :func:`_abstention`. Filing it in the shared abstention
    constructor would have covered three of the returns more cheaply and would
    have made the :func:`check_tree` precondition unfalsifiable — the two layers
    are separable only while each can be shown load-bearing without the other.

    There is deliberately NO ``UNSUPPORTED_LANGUAGE`` step here. ``analyzer`` is
    a required, already-resolved parameter, so this layer cannot meet the state;
    it belongs to the layer that RESOLVES the row. See :func:`check_tree`.

    **``roots`` — DISPUTE UPHELD, FALLBACK STRUCK (P4 round 2, 2026-08-11).**
    The body found a real defect and reported it correctly: :class:`CallPath` is
    contracted to carry the :class:`Root` a chain starts at — "so a reader can
    ask does that program actually ship" — and the scaffold's signature passes
    no root records, so a faithful ``CallPath.root`` is not constructible from
    the arguments it names. **The scaffold's signature was wrong and the repair
    is the parameter. It is NOT the default.**

    Ruled, and **IMPLEMENTED (``feat/D5-body2``, 2026-08-11)**: ``roots`` is
    keyword-only and **REQUIRED — no default** — and the synthesising fallback
    (``_synthetic_root``, with its ``_FALLBACK_PRODUCTION_KIND`` table) is
    deleted. The four reasons are kept in full, because the reasoning is the
    thing a later reader needs and the deleted code is not there to re-derive
    it from; and the last is decisive:

      1. **A missing argument is a signature defect; inventing the value is a
         verdict defect.** A default of ``()`` converts "this layer was not
         handed the evidence" into "this layer made some up", at runtime, where
         no reader is looking.
      2. **The invented record bypasses the module's own validator.** Every
         :class:`Root` an analyzer produces goes through :func:`_validate_root`,
         which exists because ``root_kind`` is "derived from ``kind`` and from
         ``seal_verify.is_test_path``, never asserted". The fallback
         asserted both and was checked by nothing. It could mint what
         ``_validate_root`` refuses outright: hand it a chain whose first caller
         is declared in a test file and it returns a ``GO_MAIN`` root in a
         ``_test.go``, which is "a tree this module does not understand" — the
         one case the validator raises on rather than flipping a coin.
      3. **Its fallback table is the thing anti-requirement 3 names.**
         ``_FALLBACK_PRODUCTION_KIND`` is a hand-maintained map from a language
         to an entrypoint kind. "It must not require a hand-maintained list of
         entrypoints" is not a preference here; it is the anti-requirement whose
         precedent is a hand-list that omitted the safety floor.
      4. **Its entire caller set was the test suite, and that is this module's
         own defect class.** :func:`check_tree` always supplies real records,
         and every witness chain originates at a root key of the matching
         :class:`RootKind`, so the synthesis is unreachable from the one
         production path. What reached it was the seals' ``_judge`` helper,
         which omitted the argument because the default let it. **Measured on
         ``feat/D5-adj2``, 2026-08-11, by making the function raise and running
         the D5 seals: 13 rows reached it before the seal amendment and 0
         after** — so the whole of its liveness was the suite, and once
         ``_judge`` passes the records the reach maps were written from,
         nothing calls it. A branch of production code that only tests execute
         is :attr:`Reach.FROM_TESTS_ONLY`, spelled in Python, inside D5.

    What replaces it: :func:`_witness` RAISES when a chain originates at a key
    no supplied :class:`Root` of that kind names. That is a mechanism bug — the
    traversal returned a chain from something it was not given as a root — and
    it gets the treatment every other mechanism bug here gets.

    Done at this commit: the default is gone, both symbols are deleted, and
    :func:`_witness` raises. **Requiring the argument is not cosmetic, and it
    is not made redundant by that raise.** Measured on ``feat/D5-body2``,
    2026-08-11, by making one call that omits ``roots`` and mutating the module
    under it — three states, three different answers:

      * as shipped, the call is refused at the SIGNATURE:
        ``TypeError: check_subject() missing 1 required keyword-only argument:
        'roots'``. No judgement starts.
      * restore only the default: the call is ACCEPTED, the judgement starts,
        and it dies inside :func:`_witness` with a mechanism-bug message about
        a chain origin. Right refusal, wrong layer, and only because the second
        edit landed — the signature had already let a caller with no evidence
        into the function.
      * restore the default AND the fallback, which is the pre-ruling state:
        the same call RETURNS ``Finding(reach=UNDECIDED)`` whose
        ``test_path.root`` is a ``TEST_FUNCTION`` record reading "derived from
        the witness chain" — a value production never produced, in a report a
        human is meant to check.

    The D5 seal file is 0 red in all three states, which is the P4's own
    measurement reproduced: with ``_judge`` passing real records the suite no
    longer reaches any of this, so no row could have caught the difference and
    the deletion is not row-pinnable. That is a fact about what a seal can see,
    not an argument for leaving the fallback in.

    One further clause reads ``roots``: step 2 decides
    :attr:`UndecidedReason.NO_ENTRYPOINT` from the ROOT SET, which is what R5
    requires — "the map corroborates, it is not the authority". (The body's
    docstring promised "two further clauses" and listed one; with the fallback
    struck there is one, and it is this.) With the argument required, that
    clause reads the root set and nothing else; see
    :func:`_has_no_production_root` for why its corroborating branch was
    deleted rather than left standing.
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
        found = Finding(
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
        # POSTCONDITION, on every return (P4 round 2). See _validate_finding.
        _validate_finding(found)
        return found

    # 1b. An unparsed file is a hole of UNKNOWN SIZE in the edge set, so any
    #     "no path" computed around it is computed around a hole. Whole-tree,
    #     per SourceUnreadable's CHOICE, and after step 1 because a found path
    #     is not un-found by a file nobody could read.
    if graph.unreadable_paths:
        parse_failed = _abstention(
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
        _validate_finding(parse_failed)
        return parse_failed

    # 2. Zero production roots, BEFORE the tests-only check: with no production
    #    root the tests-only answer is arithmetically guaranteed and would be a
    #    BREACH against every subject in a library.
    if _has_no_production_root(roots):
        no_entrypoint = _abstention(
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
        _validate_finding(no_entrypoint)
        return no_entrypoint

    # 3. The negative is not conclusive: either the language says so, or the
    #    production closure itself contains a call nobody could name.
    if not analyzer.negative_is_conclusive:
        inconclusive = _abstention(
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
        _validate_finding(inconclusive)
        return inconclusive
    holes = [
        hole for hole in graph.unresolved_calls if hole[0].key in production_reach
    ]
    # The SECOND conjunct, landed on feat/D5-relation-body: of the holes inside
    # the production closure, the ones that could be THIS subject's missing
    # call site. Never widens the set the comprehension above returned. With
    # the relation absent — which is every tree at this revision, since
    # ANALYZERS is () — this returns its input and step 3 is unchanged.
    holes = list(holes_in_scope(subject, holes, graph.package_imports))
    if holes:
        # The count must say WHICH REGIME produced it. "2 holes" under scoping
        # and "2 holes" with no relation are different facts about the
        # mechanism's confidence, and a reader has no other way to tell them
        # apart. See ImportsUnavailable.
        if isinstance(graph.package_imports, ImportsUnavailable):
            regime = (
                "the hole set is the WHOLE TREE's — no import relation was "
                f"supplied ({graph.package_imports.reason}), so it was not "
                "scoped to this subject"
            )
        else:
            regime = (
                "the hole set is SCOPED to this subject's import component"
            )
        unresolved = _abstention(
            seal,
            subject,
            test_path,
            UndecidedReason.DYNAMIC_EDGE,
            (
                f"{len(holes)} call(s) inside the production closure could not "
                f"be resolved, first at {holes[0][1]} ({holes[0][2]}); one of "
                f"them may be the missing call site. {regime}"
            ),
        )
        _validate_finding(unresolved)
        return unresolved

    # 4. The B1 verdict, reached only once every abstention above is ruled out.
    if subject.key in test_reach:
        tests_only = Finding(
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
        _validate_finding(tests_only)
        return tests_only

    # 5. Impossible for a seal-derived subject, so it is the mechanism's own
    #    bug and is reported as one rather than converted into a finding.
    raise CallSiteReachabilityError(
        f"{subject.key} is reached from no root at all, and {seal.test_id} "
        "has a direct edge to it by the definition of 'subject'; the traversal "
        "lost an edge it was handed, and a lost edge folded into the "
        "tests-only verdict would be an over-call against innocent code"
    )


def _validate_finding(finding: Finding) -> None:
    """``reason`` is non-None exactly when UNDECIDED; ``path`` exactly when
    FROM_PRODUCTION. Both ways.

    Owed at two layers and this is the shared implementation of both, mirroring
    :func:`_validate_subject` exactly (P4 round 2, 2026-08-11):
    :func:`check_subject` calls it as a postcondition on every ``return``,
    :func:`check_tree` calls it as a precondition on every finding it acts on.
    It returns ``None`` rather than the record for the same reason
    :func:`_validate_subject` does — the mirror is in WHERE it is called, and a
    validator that handed the record back would read as a constructor.

    Not filed at :func:`adjudicate`, which is a lookup on ``(reach, quality)``
    and reads neither field named here. That was the scaffold's R2 error on a
    second record: a validation belongs where the record is BUILT and where it
    is ACTED ON, not at whichever function it happens to pass through.

    Neither layer can reach a violation from inside this module today, and that
    is not grounds to skip either — R2 refused that argument on the identical
    shape, where :func:`subjects_of_seal` is :class:`Subject`'s only
    constructor and is consistent by construction too. A second constructor, or
    a caller-supplied record, is not constructible today only because nobody
    has written one yet.

    **Each layer is load-bearing WITHOUT the other, measured on
    ``feat/D5-body2``, 2026-08-11, by mutating the module and probing it —
    two defects, two layers, four runs:**

      * *Defect A*, a two-answer record built by :func:`check_subject` (step
        4's ``FROM_TESTS_ONLY`` return given a ``DYNAMIC_EDGE`` reason). With
        the postcondition: a direct :func:`check_subject` call RAISES. With the
        postcondition alone removed and the precondition left in place: the
        same call RETURNS ``Finding(reach=FROM_TESTS_ONLY,
        reason=DYNAMIC_EDGE)``. The precondition never sees it, because while
        :data:`ANALYZERS` is empty every D5 row reaches this module by calling
        :func:`check_subject` directly and :func:`check_tree` judges nothing.
      * *Defect B*, a two-answer record built inside :func:`check_tree` —
        :func:`_unnameable_finding` rewritten as a second :class:`Finding`
        constructor emitting ``reach=UNDECIDED`` with ``reason=None``, which is
        R2's hypothesised second constructor made real. With the precondition:
        :func:`check_tree` RAISES. With the precondition alone removed and the
        postcondition left in place: :func:`check_tree` RETURNS a report
        carrying the two-answer finding, counted as one ABSTAIN. The
        postcondition never sees it, because :func:`check_subject` never built
        it.

    So neither layer subsumes the other, and that is why the postcondition sits
    at :func:`check_subject`'s ``return`` statements rather than inside
    :func:`_abstention`: filing it in the shared abstention constructor would
    have caught defect B too, and a second layer that cannot be shown to catch
    anything alone is a layer nobody can tell is working.

    **THIS PRIVATE NAME IS PART OF THE SEAL SURFACE (P4 round 3, 2026-08-11).**
    ``test_check_subject_validates_every_finding_it_returns`` substitutes it by
    name, WRAPPING rather than replacing it so the module's own refusals still
    fire, and asserts on object identity that every ``return`` passed through
    it. Renaming it is therefore a TWO-FILE edit. The price is measured, not
    estimated: at ``4e66a01``, renaming this name and
    :func:`_unnameable_finding` reddens exactly those two rows, each with an
    ``AttributeError`` naming the attribute that went missing — a loud,
    correctly-attributed red with a one-line fix, which is why the coupling was
    ratified rather than the layer left unsealed.
    """
    if not isinstance(finding, Finding):
        raise CallSiteReachabilityError(
            f"{finding!r} is not a Finding and cannot be reported"
        )
    if (finding.reason is not None) != (finding.reach is Reach.UNDECIDED):
        raise CallSiteReachabilityError(
            f"finding for {finding.seal.test_id!r} on {finding.subject.key!r} "
            f"carries reach {finding.reach!r} with reason {finding.reason!r}; "
            "an UndecidedReason is what an abstention IS, so one anywhere else "
            "is a finding with two answers and one missing its own"
        )
    if (finding.path is not None) != (finding.reach is Reach.FROM_PRODUCTION):
        raise CallSiteReachabilityError(
            f"finding for {finding.seal.test_id!r} on {finding.subject.key!r} "
            f"carries reach {finding.reach!r} with path {finding.path!r}; a "
            "path is the evidence FROM_PRODUCTION means, so a path without it "
            "is unfalsifiable green and the verdict without one is a claim "
            "nobody can check"
        )
    if finding.reason is not None and not isinstance(
        finding.reason, UndecidedReason
    ):
        raise CallSiteReachabilityError(
            f"finding for {finding.seal.test_id!r} carries {finding.reason!r}, "
            "which is not an UndecidedReason member"
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


def _has_no_production_root(roots: Sequence[Root]) -> bool:
    """R5: the ROOT SET is the authority, and it is now the only witness asked.

    **The empty-``roots`` branch is DELETED, not left unreachable (P4 round 2
    flagged it; ``feat/D5-body2``, 2026-08-11).** It read ``return not
    production_reach`` — the reach map answering when the root set was absent —
    and the only way the root set could be absent was
    :func:`check_subject`'s struck ``roots=()`` default. With the argument
    required, ``()`` no longer means "this layer was not handed the evidence";
    it means "the sweep ran and found no root", which is a first-class fact
    about a library tree and is exactly what :attr:`UndecidedReason.NO_ENTRYPOINT`
    answers. ``not any(...)`` over an empty root set is already ``True``, so the
    empty case now falls out of the rule instead of being special-cased.

    Deleted rather than kept, because the branch is not merely unreachable —
    under R5 it is WRONG. An empty root set beside a non-empty
    ``production_reach`` describes chains starting at roots nobody declared,
    and the branch read ``False`` from it: "there IS a production root", said
    by the corroborator over an authority that named none. That is the one
    thing R5 forbids, and it is the permissive direction.

    Deleted rather than converted into a raise, for two reasons. That state
    already has an answer site — :func:`_witness` raises the moment it is asked
    to build a chain whose origin no supplied :class:`Root` names, which is
    every chain in such a map — and a second layer with its own answer for one
    condition is what the :attr:`Reach.FROM_NEITHER` treatment refuses. And a
    raise HERE would be wrong on its own terms: this predicate is also reached
    with a legitimately empty root set, over a library that has no entrypoint,
    where the contracted answer is :attr:`UndecidedReason.NO_ENTRYPOINT` and
    :func:`check_tree`'s own CHOICE says an empty tree reports rather than
    raises. The module's "an unreachable arm that RAISES is a contract"
    doctrine applies to arms that raise; this one returned a permissive verdict
    computed from the corroborator, which is the coincidence the doctrine is
    contrasted with.

    ``production_reach`` went with it: an argument nothing reads is a second
    input a later reader would assume is consulted.
    """
    return not any(root.root_kind is RootKind.PRODUCTION for root in roots)


def _witness(
    subject: Symbol,
    reach: Mapping[str, tuple[Edge, ...]],
    root_kind: RootKind,
    roots: Sequence[Root],
) -> "CallPath | None":
    """The chain a human follows, or None when this side reached nothing.

    **P4 round 2 (2026-08-11), IMPLEMENTED HERE (``feat/D5-body2``,
    2026-08-11):** the ``declared is None`` branch was the struck fallback's
    last caller and it is now a raise. A chain that originates at a key no
    supplied :class:`Root` of that :class:`RootKind` names is a traversal
    reporting a path from something it was never given as a start, which is a
    mechanism bug rather than a licence to invent the start. It is the one
    answer site for that state: :func:`_has_no_production_root` deliberately
    does not grow a second one, because two layers with their own answer for
    one condition is what the :attr:`Reach.FROM_NEITHER` treatment refuses.
    """
    if subject.key not in reach:
        return None
    chain = tuple(reach[subject.key])
    origin = chain[0].caller if chain else subject
    declared = {
        (root.symbol.key, root.root_kind): root for root in roots
    }.get((origin.key, root_kind))
    if declared is None:
        raise CallSiteReachabilityError(
            f"the {root_kind.value} chain to {subject.key} originates at "
            f"{origin.key!r}, which no supplied Root of that kind names; the "
            "traversal reported a path from something it was never given as a "
            "start, and a start this layer invented would be the only value in "
            "a report that production did not produce"
        )
    return CallPath(root=declared, edges=chain, quality=_chain_quality(chain))


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

    **BODY DISPUTE (``feat/D5-body``) RULED (P4 round 2, 2026-08-11): THE RAISE
    MOVES; THE SENTENCE STANDS; THIS FUNCTION OWES NOTHING.** The body reported
    that it cannot enforce :class:`Finding`'s reason/path consistency rule
    because ``test_the_three_verdict_classes_land_in_three_buckets`` and
    ``test_a_declaration_moves_at_most_one_outcome_and_never_an_abstention``
    both sweep the grid with ``(reach, quality, reason=DYNAMIC_EDGE,
    path=None)`` and require a ruling back for ``(FROM_PRODUCTION, RESOLVED)``,
    so enforcing it here would empty ``rulings[FROM_PRODUCTION]`` and redden
    both rows. That report is accurate and the diagnosis was the right one to
    escalate: it is a contradiction between a contract and two seals, and a body
    may resolve neither.

    **It resolves in the seals' favour, and not because they are seals.** This
    function is a lookup on ``(reach, quality)`` and reads neither ``reason``
    nor ``path``. A consistency check about two fields it never touches was
    filed at the one layer that cannot see them — which is R2's error, on a
    second record, and it gets R2's answer: the raise belongs at
    :func:`check_subject` as a postcondition and at :func:`check_tree` as a
    precondition. Sweeping a two-field dispatch with findings whose other
    fields are arbitrary is the CORRECT way to seal a two-field dispatch, so
    the two rows stand unedited and this docstring loses a sentence it should
    never have carried. The full argument is at :class:`Finding`.
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
      * **Validate every :class:`Finding` before putting it in a report** (P4
        round 2): a finding carrying a ``path`` and an ``UndecidedReason``, or
        neither where its ``reach`` requires one, is a
        :class:`CallSiteReachabilityError` here as well as at
        :func:`check_subject`. Same shape as the :class:`Subject` obligation
        above and the same reason — this is the layer where a non-judgement
        becomes an answer, and it is the layer that hands findings to
        :func:`adjudicate`, which by ruling reads neither field. See
        :class:`Finding`. **Implemented (``feat/D5-body2``, 2026-08-11)**, in
        the disposition loop and BEFORE :func:`adjudicate`, so that the two
        findings this layer builds itself — the ``UNSUPPORTED_LANGUAGE``
        abstention below and :func:`_unnameable_finding`, neither of which
        :func:`check_subject` ever sees — are covered by it and by nothing
        else.
      * **A subject symbol whose language has no analyzer row is UNDECIDED /
        UNSUPPORTED_LANGUAGE, one finding per SUBJECT** — the site the contract
        named the member for and never placed. **P4 CONFIRMS THE BODY'S
        PLACEMENT (round 2, 2026-08-11):** this is the only layer that calls
        :func:`analyzer_for_path` per subject and so the only one that can meet
        a ``None``, and the obligation two bullets up forbids the alternative —
        skipping the symbol would be a subject with no finding, which is "a
        silent pass, the defect one level up". It does NOT duplicate
        ``unanalyzed_paths``: that field counts FILES nobody read and this
        counts SUBJECTS nobody judged, the two populations are different, and a
        seal can name a subject in a file the sweep never had a reason to list.
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
        # R2's shape on a second record, the PRECONDITION half (P4 round 2).
        # Every finding in the report passes here, whichever layer built it,
        # and it runs BEFORE adjudicate because adjudicate is a lookup on
        # (reach, quality) that reads neither field this checks — so a finding
        # with two answers would otherwise be counted as whichever one the
        # dispatch happened to key on. See :func:`_validate_finding`.
        _validate_finding(finding)
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

    **THIS PRIVATE NAME IS PART OF THE SEAL SURFACE (P4 round 3, 2026-08-11).**
    ``test_check_tree_validates_a_finding_check_subject_never_built``
    substitutes it with a second :class:`Finding` constructor emitting
    ``reach=UNDECIDED`` with ``reason=None`` — R2's hypothesised second
    constructor made real — because this is the only seam in :func:`check_tree`
    that can produce a two-answer record from outside: its other self-built
    finding goes through :func:`_abstention`, which fixes ``reach`` and guards
    ``reason``. Renaming this is a TWO-FILE edit; see :func:`_validate_finding`
    for the measured price.
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
