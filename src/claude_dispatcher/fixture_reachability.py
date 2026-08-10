r"""D3 — fixture reachability: can production produce this input?

The contracts below are P1's and are unchanged. P2 wrote the seals in
``tests/test_fixture_reachability.py``, P4 ruled on four disputes and amended
both, and P3 wrote the BODIES: the twelve functions that read "CONTRACTS ONLY.
Every function here raises :class:`NotImplementedError`" are implemented as of
this commit, and the statement is corrected here rather than left standing,
because a docstring making a claim about its own module that the next author
would rely on is instance (B) below.

Every docstring in this file is therefore a contract a body has to meet and not
a description of one that will be met later. What has NOT changed: the module
is still not enrolled anywhere (see Wiring), and nothing under ``tests/``,
``schema/`` or ``.dispatcher.yaml`` was touched to make the seals pass.

The defect class this exists for
================================
Two of the three recurring defect classes this effort found now have
mechanisms: *a path rendering defeats a matcher* (closed by unifying on one
decoder, ``role_protocol._unquote_git_path``) and *a gate is writable by what
it gates* (closed by the floor's AST-derived delegation closure in
``tests/test_floor_closure.py``). The third has none, and it has TWO ends:

    **A seal is green on an input production cannot produce —**
    **and the input production DOES produce reached no seal.**

The second clause is not a restatement. It is where the harm lives, and a
design that checks only the first catches neither instance below. The brief
for this unit named only the first clause; the correction was accepted by the
coordinator on 2026-08-09 and this sentence is the unit's definition.

These are not vacuous seals in the usual sense. They fail correctly on their
own inputs; a mutation to the code they cover reddens them. What is wrong is
one level out: **the input never arrives, and the one that does was never
judged.** The gate is therefore unprotected on the input that does arrive, and
every artifact in the repo — the green run, the mutation sweep, the coverage
number — says otherwise.

The two measured instances, and what each one teaches
------------------------------------------------------
**(A) The line feed that production never emitted.** Four rows in
``tests/test_glob_newline.py`` drive ``risk.evaluate`` with a ``FileDiff``
whose path holds a REAL line feed. At the time they were written,
``risk.collect_diff`` — the only production producer of that argument — split
``git diff --numstat`` and passed the path field on undecoded, so what
``evaluate`` actually received for that file was git's *rendering*,
``".github/workflows/ci\nx.yml"`` with a literal backslash-n inside literal
quotes. The rows went green when ``re.DOTALL`` landed in ``risk._compiled``;
the ``.github/**`` bypass stayed open, because the rendering still matched no
glob, and a CI-workflow PR self-approved and merged.

Note what the seal asserted: a **refusal** (``elevated``). So the naive rule
"a hand-made fixture may prove a refusal but may never certify a pass" does
NOT catch this one, and the first draft of this scaffold was wrong for exactly
that reason. What was missing was not the fixture's direction, it was the
NEIGHBOUR: for the state the fixture describes (a workflow file with a line
feed in its name), production emitted a DIFFERENT value, and on that value the
gate went the other way. That observation is this module's engine, and it is
:class:`Consequence`.

**(A) IS ALREADY CLOSED AT HEAD, AND THE SEAL AUTHOR MUST KNOW THAT FIRST.**
``263298d`` put the decoder into ``collect_diff``, so the divergence is gone.
Measured on this worktree, 2026-08-09, over a real repository containing
``.github/workflows/ci<LF>x.yml``::

    git diff --numstat --no-renames main...HEAD
        1\t0\t".github/workflows/ci\nx.yml"
    risk.collect_diff(...)
        [FileDiff(path='.github/workflows/ci\nx.yml', insertions=1, deletions=0)]
    risk.evaluate(...)
        RiskVerdict('elevated', ('forbidden path touched: ... (matches .github/**)',))

So this check reports :attr:`Reachability.REACHED` for instance (A) today, and
that is the CORRECT answer, not a miss. The consequence for whoever writes
D3's seals: **the flagship incident cannot be a live red row.** Reproducing it
needs the pre-``263298d`` collector — a witness repository plus a local
undecoded reimplementation of the numstat split, in the seal file — or the row
proves nothing about this mechanism. Budget for that before starting; it is
the single most likely place these seals go vacuous, on the very defect they
are written against.

**(B) The stub that answered a command it never declared.** Nineteen seals
across ``tests/test_role_protocol_diff.py``, ``test_role_protocol_floor.py``
and ``test_role_protocol_provenance.py`` ran against a ``_run_stub`` whose
docstring said "an unscripted command raises, so a seal cannot pass on a read
it never modelled". False in ONE of the three files (see the corrected count
below), and false there for the first git command of every base-pinned blob
read. ``repo_config.blob_text_at`` issues
``git ls-tree -z <ref>: -- <path>`` before ``git cat-file``; the stub
dispatches on ``":" in arg``, and the tree-ish token ``main:`` satisfies that,
so ``ls-tree`` fell into the blob-spec branch and was answered. Measured on
this worktree (2026-08-09, ``tests/test_role_protocol_diff.py::_run_stub``
with ``changed=["src/app.py"]`` and ``blobs={"main:src/app.py": ...}``)::

    git ls-tree -z main: -- src/app.py  ->  (128, '', "fatal: path '' does not exist in 'main'")
    git cat-file blob main:src/app.py   ->  (0, 'X = 1\n', '')
    git rev-parse HEAD                  ->  AssertionError: unscripted git command

Real git, over a repository in which ``src/app.py`` exists at ``main`` — which
is the very repository the second line asserts — answers the first argv with
rc 0 and a tree entry. The stub's answer is a value **git cannot produce**,
and the empty path in ``fatal: path '' ...`` is the tell: no git anywhere
prints that for that argv. This is (A) again with the producer being git and
the fixture being a *response* rather than a path.

Two corrections to the brief's account of this instance, both measured here
and both accepted by the coordinator on 2026-08-09:

  * **``cat-file`` is unmodelled too.** The second line above is answered by
    the same ``":" in a`` branch. The stub names ``diff`` and ``merge-base``
    and nothing else, so the gap is two subcommands wide, not one, and the
    fix is the branch rather than a missing case.
  * **EXACTLY ONE of the three files is affected.** This scaffold first said
    "only two of the three", and that was itself an over-call. P4 remeasured
    it on 2026-08-10, running each of the three ``_run_stub`` factories against
    the two argvs ``blob_text_at`` really issues::

        _run_stub in     ls-tree -z main: -- p    cat-file blob main:p
        diff.py          ANSWERED rc 128         ANSWERED rc 128
        floor.py         REFUSED  AssertionError REFUSED  AssertionError
        provenance.py    ANSWERED rc 0, an entry ANSWERED rc 0, a blob

    Read through :func:`stub_gaps`' own definition — a gap is unmodelled AND
    answered — that is one gap-bearing file, not two. ``provenance`` NAMES
    ``ls-tree`` and ``cat-file`` and answers them: modelled and answered, a
    stub doing its job. ``floor`` names neither and REFUSES both: unmodelled
    and refused, which is the totality claim HOLDING, not failing — its own
    docstring says in as many words that "a blob read is STILL unscripted
    here", and that property is what several of its rows rest on. Only
    ``test_role_protocol_diff.py`` is unmodelled and answering.

    The earlier count came from grouping ``floor`` with ``diff`` because
    neither NAMES the two subcommands, which is half of the definition applied
    as if it were the whole of it. Recorded rather than quietly fixed, because
    a check that over-calls is one nobody runs twice and this one is *about*
    trustworthy detection: the first draft of the mechanism's own account of
    its own instance was wrong in the permissive-for-the-checker direction.

A THIRD INSTANCE WAS BRIEFED AND DOES NOT EXIST
------------------------------------------------
The brief for this unit named a third: "a seal-inversion row was green on an
outcome the gate could not emit". It was searched for and is not there.
Measured, 2026-08-09: no test constructs a ``SealVerifyResult`` with a fake
outcome, and no test replaces ``run_seal_inversion`` — the only
``SealVerifyResult(`` occurrences under ``tests/`` are inside the AST-reading
helpers of ``test_seal_verify_failopen.py`` itself. The coordinator withdrew
the claim on 2026-08-09: it was a conflation of that file's mutation sweep
finding (six outcome transitions noticed by nothing), which is a different and
true claim about unsealed CODE, not about an unreachable FIXTURE.

Recorded here rather than deleted, because the first draft of this scaffold
built a whole third face on it — see DELIBERATELY NOT SCAFFOLDED below — and
the next author will otherwise re-derive it from the same brief.

What this module is
===================
A check with TWO faces, one per boundary kind. Two because there are two
instances; a face with no measured instance behind it is not scaffolded here
(again: DELIBERATELY NOT SCAFFOLDED). The honest answer to "static or
dynamic?" is *both, and they are not interchangeable*:

  * :attr:`BoundaryKind.COLLECTOR` — **dynamic, witness-based.** Construct a
    repository state FROM the fixture value, run the real collector over it,
    compare. Precise; samples only what ran. Instance (A).
  * :attr:`BoundaryKind.SEAM` — **static, structural.** A stub is a simulated
    producer; the checkable property is not "is this answer right" (nobody
    knows) but "does this stub answer commands its own dispatch never names".
    Total over the stub's source; says nothing about the answers themselves.
    Instance (B).

The unit of analysis: the BOUNDARY, found by observation
---------------------------------------------------------
The brief asked whether the unit is the collector, the stub, or the call site.
It is none of the three on its own; it is the **boundary crossing**, an
ordered pair ``(producer, consumer)`` recorded in :data:`BOUNDARIES`.

The reasoning: "is this fixture producible" is not a well-formed question
about a value. It is only well formed once you name *which producer was
replaced by the fixture*. A seal that calls ``check_branch`` over a real
repository replaces nothing and has nothing to check — except the ``run=``
seam, which replaces git, which is a boundary. A seal that calls
``risk.evaluate`` directly replaces ``risk.collect_diff``. Same repo, same
subject, different question, because a different segment of the path is
missing.

**A seal that cuts more than one boundary is itself a finding.** Its fixture's
reachability is not decidable one hop at a time, and the mechanism must say so
(:attr:`FindingDisposition.ABSTAIN`) rather than answer the easy hop and imply
it answered the question.

Boundaries are found by OBSERVING the suite, not by parsing it. The consumers
in :data:`BOUNDARIES` are wrapped for the duration of a run
(:func:`observe`), and every value that arrives is recorded with the outcome
the consumer returned for it. Three reasons this beats an AST sweep over
``tests/**``:

  1. It needs no annotation on 1811 rows, which is the difference between a
     mechanism that runs and one that is switched off.
  2. It cannot be fooled by indirection — a fixture built by a helper, a
     parametrize table, a fixture-of-a-fixture, or a value that passed through
     three frames all arrive at the same wrapped consumer.
  3. It records the consumer's OUTCOME, which the differential needs and which
     no static reading of the test file can supply.

Its cost is stated under WHAT THIS CANNOT DETECT: a row that did not run
contributes nothing.

The hard question, and the answer that is a measurement and not a policy
=========================================================================
The brief's hardest question: an unreachable fixture is not necessarily wrong.
It may be pinning a defensive branch nobody can reach today, which is
legitimate, and this repo has several on purpose, with reasons recorded. So
the answer cannot be a bare refusal. It must tell *unreachable and that is the
point* from *unreachable and nobody noticed.*

The discriminator is **not an annotation**. An annotation is rubber-stampable
and would be rubber-stamped; the mechanism would then record permission rather
than protection, which is the failure mode ``_DELEGATION_TARGETS`` warns about
in as many words. The discriminator is a **differential on the consumer over
the producible neighbour**:

    Construct a witness state from the fixture value V. Run the real producer.
    It emits V'.

      V' == V                     -> REACHED. Nothing to say.
      V' != V                     -> V is unreachable and V' is its PRODUCIBLE
                                     NEIGHBOUR. Now run the consumer on BOTH.

          disposition(C(V)) != disposition(C(V'))
              -> the seal is green on an input production cannot produce, and
                 the input production DOES produce goes the other way through
                 the gate. This is UNREACHABLE AND NOBODY NOTICED. It is a
                 BREACH and it cannot be declared away.

          disposition(C(V)) == disposition(C(V'))
              -> the fixture is unreachable and nothing hinges on it. The seal
                 is pinning a branch whose reachable neighbour behaves the
                 same way. This is reportable, declarable, and not a failure.

      no witness state constructible
              -> UNREPRESENTABLE: nothing anywhere produces this value, so
                 there is no neighbour to differential against. This is where
                 a genuinely defensive row lands, and it is also the ONLY
                 place a declaration is load-bearing. Stated as a limit below.

      no construction strategy for this value's kind
              -> NO_STRATEGY: the checker abstained. Loudly, and never as a
                 pass. Without this fourth state the mechanism degrades to
                 green on everything it does not understand, which is the
                 defect class it exists to close, one level up
                 (``skills/explicit-state.md``: an unknown must not resolve to
                 the permissive value).

Applied to instance (A): the witness is a repository containing a file named
``.github/workflows/ci<LF>x.yml``; pre-fix ``collect_diff`` emits the quoted
rendering; ``evaluate`` returns ``elevated`` for the fixture and ``low`` for
the neighbour; opposite dispositions; **BREACH**. Applied to a row pinning
"``changed_paths_between`` raises on a blank line": no repository makes git
emit a blank path, so **UNREPRESENTABLE**, declarable, correct.

Two axes, named separately
--------------------------
:class:`Reachability` answers *can the producer emit this value*.
:class:`Consequence` answers *does it matter*. They are separate enums on
purpose. Collapsing them into one five-valued status was the first draft and
it made every report ambiguous about which half had failed, which is the same
mistake as a gate that reports ``skipped`` without a reason.

What FAIL means, exactly
========================
:func:`adjudicate` is the one answer site. Its ruling, normatively:

  * :attr:`Consequence.OPPOSITE_DISPOSITION` at any boundary kind is
    :attr:`FindingDisposition.BREACH`. **No declaration accepts it.** Either
    the fixture becomes the neighbour, or the producer is fixed so it emits
    the fixture. There is no third resolution and no annotation.
  * A :class:`StubGap` — a stub answering a subcommand its own dispatch never
    names — is :attr:`FindingDisposition.BREACH`, regardless of whether the
    answer changed any outcome. The stub's totality claim is either true or it
    is a lie in a docstring that the next author will rely on, as nineteen
    seals did.
  * :attr:`Reachability.UNREPRESENTABLE` with
    :attr:`Consequence.NOT_MEASURED` is :attr:`FindingDisposition.REPORT`
    without a declaration and :attr:`FindingDisposition.ACCEPTED` with one.
  * :attr:`Reachability.NO_STRATEGY` is :attr:`FindingDisposition.ABSTAIN`,
    always, declaration or not. An abstention is not a pass and must not be
    suppressible: the count of abstentions is the mechanism's own coverage
    figure and a run that hides it is reporting a judgement it did not make.
  * :attr:`Reachability.DIVERGED` with :attr:`Consequence.NOT_MEASURED` — a
    value known not to be producible, with a known neighbour, and no
    differential run over it — is :attr:`FindingDisposition.ABSTAIN`, also
    always. P4, 2026-08-10, dispute 2; the reasoning is on :func:`adjudicate`
    and the consequence for an unattended run is limit 12.
  * :attr:`Reachability.REACHED` is :attr:`FindingDisposition.OK`.

So the only thing a declaration can buy is silence on UNREPRESENTABLE. That is
deliberately the smallest possible annotation surface, and it is the only
state where a human genuinely knows something the machine cannot.

WHAT THIS CANNOT DETECT
=======================
Stated plainly, because on this effort the honest limits have been worth more
than the claims.

  1. **A boundary that is not in the table.** :data:`BOUNDARIES` is written
     out. A new collector, or a seal that cuts at a function nobody enrolled,
     is invisible — and invisibly green. The two-way pin required of the seal
     author (see :data:`BOUNDARIES`) keeps the table honest against the
     producers it names; it does nothing about a producer nobody named.
  2. **A row that did not run.** Observation sees executed calls. A skipped
     row, an ``xfail``, a parametrize case behind an ``if``, a branch of the
     test itself — none contribute an observation, and none are reported as
     missing, because the mechanism cannot enumerate the rows that would have
     run under other conditions.
  3. **Combination unreachability.** The witness is built per VALUE. A fixture
     every field of which is individually producible, in a combination that
     never co-occurs, is REACHED. ``risk.evaluate`` is exactly this shape:
     ``verified=True, verification_iterations=0`` alongside a 5,000-line
     effective diff is a state no task row reaches, and every field of it is
     ordinary. This is the largest hole in the mechanism and nothing here
     narrows it.
  4. **Reachability more than one hop out.** ``collect_diff`` can emit a
     10,000-line ``FileDiff``; whether any caller ever puts it in that state
     is a different question and is not asked. One hop, by construction.
  5. **Environment-dependent representability.** UNREPRESENTABLE is a property
     of the machine the check ran on, not of production. A filename that ext4
     accepts and the CI image's filesystem rejects — or the reverse, which is
     worse — flips the verdict with no code change. :class:`Witness` therefore
     records an environment fingerprint, and a declaration that rests on
     UNREPRESENTABLE rests on that fingerprint. It is evidence, not proof.
  6. **Whether the assertion is right.** A perfectly reachable fixture with a
     wrong expectation is invisible here. This module asks whether the input
     can occur, never whether the seal is correct about what should happen.
  7. **Any producer that is not deterministic in the workspace**: the network,
     the clock, another process, an LLM, a git version other than the one
     installed. A producer whose output varies run to run cannot have a
     neighbour and will come out NO_STRATEGY at best.
  8. **A boundary cut by monkeypatching rather than by argument.** A seal that
     patches ``risk.matches_any_glob`` has replaced a producer that is not in
     the table with a value nobody observed. :func:`observe` wraps consumers;
     it does not notice that something under them was replaced.
  9. **Stub ANSWERS.** The seam face checks totality — that nothing undeclared
     is answered — and deliberately not correctness. A stub that declares
     ``ls-tree`` and returns a plausible, wrong entry passes every check here.
     Whether that answer is one git could produce is decidable only against a
     real repository, which is what the collector face does and what a stub
     exists to avoid.
 10. **The residual UNREPRESENTABLE.** With no neighbour there is no
     differential, so the mechanism genuinely cannot tell a deliberate
     defensive row from an oversight, and the declaration that fills the gap
     is exactly as good as the person writing it. This is the one place the
     mechanism is a policy rather than a measurement, and it is the place it
     will first be abused.
 11. **Its own presence.** :func:`observe` wraps production functions for the
     duration of a run. A suite that behaves differently under wrapping has
     been measured with an instrument that changed it, and no seal here can
     notice that.
 12. **The differential does not run itself, so the automated path cannot
     reach OPPOSITE_DISPOSITION.** P4, 2026-08-10, dispute 2. Running it means
     calling the consumer a second time with the neighbour substituted and
     EVERYTHING else identical, and by the time :func:`check_suite` has a
     neighbour, the world the observation was made in no longer exists. So the
     second call is delegated to a ``differential`` a caller supplies, and a
     caller that cannot supply one gets ABSTAIN on every DIVERGED finding. The
     module's headline finding — a fixture that is unreachable AND changes the
     gate — is therefore reachable today only from :func:`stub_gaps`, or by
     hand at a site that holds identical
     (``test_flagship_pre_fix_collector_is_a_breach``). This is the largest gap
     between what this module describes
     and what an unattended run of it can do, and it is recorded rather than
     narrowed. What would close it: a SECOND observed pass over the suite in
     which the wrapper substitutes the precomputed neighbour at the moment of
     the call. That is the only place both values can be run through one
     identical world, and it is a design, not an addition — deferred here, on
     the same terms as the VOCABULARY face.

DELIBERATELY NOT SCAFFOLDED
===========================
**A VOCABULARY face**, and the ``emittable_literals`` /
``vocabulary_findings`` pair that went with it. The first draft of this module
carried both, plus a ``BoundaryKind.VOCABULARY``, a
``ValueKind.OUTCOME_LITERAL``, and a seventh :data:`BOUNDARIES` row for
``run_seal_inversion`` -> ``orchestrator._verify_seal``. All of it rested on
the withdrawn instance (C) and all of it is removed. Three reasons, in
ascending order of how much they should bind the next author:

  1. Its stated provenance was false. The docstring cited a measured incident
     that did not happen — a claim in a docstring that the next author would
     have relied on, which is the exact shape nineteen seals rested on in
     instance (B). Leaving it in while knowing that would have made this
     module an instance of its own defect class.
  2. Its boundary row could never fire. Nothing in the suite substitutes a
     seal outcome, so the row would have been reported forever by
     ``ReachabilityReport.boundaries_never_observed`` — and
     :class:`Boundary`'s own contract says a row whose rationale cannot name a
     real substitution "will never fire and will be read as coverage".
  3. D2's precedent, verbatim in its commit message: SQL (781 files) and Java
     (316) got no table entry on purpose. Mechanism without a measured
     instance is speculative surface, and surface is what gets switched off.

What it would take to bring it back, so this is a deferral and not a veto: one
real row in which a value drawn from a producer's closed literal vocabulary is
SUBSTITUTED across a boundary — a test that fakes a ``seal_outcome``, a
verdict, a status. Then the emittable set is derivable exactly as
``tests/test_seal_verify_failopen.py::_outcomes_seal_verify_can_emit`` already
derives it, membership is decidable, and the finding is a BREACH with no
defensive-branch appeal, because a value your own module has no site
constructing is not a branch anyone is defending.

COLLECTOR ROWS REMOVED BY P4
----------------------------
P4 ruling, 2026-08-10, dispute 1. Two COLLECTOR rows named a producer/consumer
pair at which NOTHING IS EVER SUBSTITUTED, because the consumer calls the
producer itself:

  * ``seal_verify.partition_changed`` -> ``seal_verify.run_seal_inversion``.
    ``run_seal_inversion`` calls ``partition_changed(worktree, base)`` on its
    own line 239 and takes no argument the partition could be handed in.
  * ``blast_radius.changed_files`` -> ``blast_radius.build_blast_radius``.
    ``build_blast_radius`` calls ``changed_files(diff)`` on its own line 186.

Both were therefore permanent members of
``ReachabilityReport.boundaries_never_observed``, and :class:`Boundary`'s own
contract rules out exactly that: a row whose rationale cannot name a real
substitution "will never fire and will be read as coverage". Keeping them
behind a "never observable" marker was considered and refused — it would put
two permanent members into the report's designated NON-VACUITY field, and a
reader who learns to expect two entries there stops reading it, which is the
same failure one level out.

**Why they were not repaired instead.** The two are not alike:

  * ``partition_changed`` is unrepairable. It takes no injectable seam (no
    ``run=``; it calls ``subprocess.run`` directly) and ``run_seal_inversion``
    takes no value, so there is no boundary of any kind here — the suite only
    ever calls ``partition_changed`` itself over a real repository
    (``tests/test_path_gate_bypass.py`` lines 780 and 931), which is the
    producer under test and not a substitution. The removed row's rationale,
    read closely, described a CONTROL-FLOW fact ("the partition decides whether
    the gate runs at all"), which is not the same thing as a substitution site.
  * ``blast_radius`` is repairable, but not at this value kind. A real
    substitution does exist one level out: ``build_blast_radius`` takes
    ``diff``, a DIFF TEXT that production gets from git and that the suite
    hands over by hand (``tests/test_blast_radius.py`` line 86 onward,
    ``tests/test_glob_newline.py`` line 833 at ``changed_files`` directly).
    Enrolling it needs a ``ValueKind.DIFF_TEXT`` and a witness recipe for it
    (build a repository holding those files, run the real ``git diff``, compare
    the text). That is new mechanism, and no measured instance of this defect
    class has landed on it — so it goes where the VOCABULARY face went, for the
    same reason, with the same trigger for bringing it back: **one row in which
    a hand-made diff text is shown to differ from what git emits for the state
    it describes.** Until then the third collector on the one decoder is
    covered by the two collector rows that remain, both of which run through
    ``role_protocol._unquote_git_path``, which is the shared thing at risk.

**An assertion-side reader** — an AST sweep over ``tests/**`` for expected
values, as opposed to observed ones — is likewise not scaffolded. It is the
only thing that would catch a row whose false claim lives in its docstring
while its assertion is weak enough to be green either way (``outcome !=
"passed"``). It is describable and it may well be worth building; there is no
incident behind it, so it is not built here. Explicitly ruled out by the
coordinator on 2026-08-09.

Wiring
======
Written and NOT enrolled, following the D2 precedent. No call site is added by
this commit: not the orchestrator, not ``scripts/``, not CI. Enrolment is P3's
and needs the seals first, because a check that reports zero findings because
nothing calls it is indistinguishable from a check that reports zero findings
because the repo is clean — this module's own subject matter.

Two coordinations this scaffold may NOT perform, raised for P4:

  * ``FLOOR_GLOBS``. This module is a gate, and once wired its decisions can be
    dissolved by editing it, so by the 2026-08-09 delegation-closure ruling it
    belongs on the floor. ``_FLOOR_ROWS`` in
    ``tests/test_role_protocol_floor.py`` is a set difference against
    ``FLOOR_GLOBS`` and a glob P3 invents that P4 has not written there reddens
    that seal, so adding one here would break a live seal to protect an unwired
    module. Deferred, deliberately, and recorded rather than done.
  * The delegation closure. Nothing in ``role_protocol`` imports this module,
    so it is correctly absent from ``_DELEGATION_TARGETS`` today. Wiring it into
    a floor decision would put it there and would need the same P4 round.
"""

from __future__ import annotations

import ast
import functools
import importlib
import inspect
import os
import subprocess
import sys
import tempfile
from collections.abc import Sequence as _AbcSequence
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

__all__ = [
    "FixtureReachabilityError",
    "BoundaryKind",
    "ValueKind",
    "GateDisposition",
    "Reachability",
    "Consequence",
    "FindingDisposition",
    "Boundary",
    "BOUNDARIES",
    "boundary_for",
    "ObservedFixture",
    "observe",
    "WitnessGap",
    "Witness",
    "construct_witness",
    "classify_value",
    "gate_disposition",
    "measure_consequence",
    "Finding",
    "check_observation",
    "ReachabilityDeclaration",
    "adjudicate",
    "StubGap",
    "git_subcommand",
    "modelled_subcommands",
    "stub_gaps",
    "ReachabilityReport",
    "check_suite",
]


class FixtureReachabilityError(RuntimeError):
    """The check could not be carried out, as distinct from a finding.

    Raised for a malformed :data:`BOUNDARIES` row, a consumer outcome the
    boundary's two outcome sets do not between them name, a witness workspace
    that cannot be created, or a source file the analyzers cannot parse.

    Never used to report a defect in the code under check. A caller must not
    catch this and continue: an error here means the mechanism has no
    judgement, and a mechanism with no judgement that returns an empty finding
    list is the exact shape this module exists to refuse.
    """


# --------------------------------------------------------------------------- #
# Part 1 — the boundary table
# --------------------------------------------------------------------------- #


class BoundaryKind(Enum):
    """How a boundary's producer is interrogated. Three kinds, exhaustively.

    COLLECTOR
        The producer is an in-repo function that reads the world and returns
        values. Interrogated DYNAMICALLY: a witness state is constructed from
        the fixture value and the real producer is run over it. Precise, and
        samples only the values that were observed.
    SEAM
        The producer is an external process — git — and the fixture is a
        SUBSTITUTE PRODUCER (an injectable ``run=`` callable) rather than a
        value. Interrogated STRUCTURALLY: the substitute's own source is read
        for the command vocabulary it dispatches on, and any command it answers
        outside that vocabulary is a gap. Total over the substitute's source,
        and silent about whether its answers are right.

    Two kinds, because there are two measured instances. A third —
    VOCABULARY, over a producer whose output is a closed set of literals in its
    own source — was drafted and removed with the incident that justified it;
    see DELIBERATELY NOT SCAFFOLDED in the module docstring for what would
    bring it back.

    Any other kind is a programming error and every dispatch over this enum
    must raise rather than fall through to a default. A third kind resolving
    silently to the cheapest check is how a gate reports a judgement it did not
    make.
    """

    COLLECTOR = "collector"
    SEAM = "seam"


class ValueKind(Enum):
    """What travels across a boundary, and therefore which witness strategy
    applies. The dispatch in :func:`construct_witness` is total over this enum
    and raises on anything else.

    GIT_PATH
        A repository path, as some git command reported it. The witness is a
        fresh repository containing a file at that exact name, committed on a
        branch off a base commit; the producer is then run over
        ``base...HEAD``. UNREPRESENTABLE when the operating system or git
        refuses the name (an embedded NUL, an embedded ``/`` in a component,
        ``.`` or ``..`` as a component, the empty string, a component over
        ``NAME_MAX``, a path over ``PATH_MAX``).
    GIT_RESPONSE
        A ``(returncode, stdout, stderr)`` triple standing in for one git
        invocation. Its witness is a repository consistent with the OTHER
        answers the same substitute gives, which is why this kind is checked
        structurally by default and dynamically only when the boundary row
        supplies a repository recipe.
    """

    GIT_PATH = "git-path"
    GIT_RESPONSE = "git-response"


class GateDisposition(Enum):
    """What a consumer's outcome MEANS for the thing downstream of it.

    PROCEED
        The gate let the change through: ``risk`` said ``low``,
        ``check_branch`` said ``CLEAN``, the seal gate said ``passed`` or
        ``skipped``. The permissive side.
    REFUSE
        The gate stopped or escalated: ``elevated``, ``VIOLATION``,
        ``UNDETERMINED``, ``failed``, ``error``. Note that fail-closed
        non-judgements (``UNDETERMINED``, ``error``) are REFUSE, because that
        is what the caller does with them — this enum describes the effect on
        the run, not the epistemic state of the gate.
    UNKNOWN
        The outcome is in neither of the boundary's two written-out sets. This
        is never returned: :func:`gate_disposition` RAISES
        :class:`FixtureReachabilityError` instead, and the member exists so
        that the state is named rather than implied. A new outcome must be
        classified by a human editing :data:`BOUNDARIES`; defaulting it to
        either side would let a new outcome silently equal an old one and make
        every differential over it vacuous.
    """

    PROCEED = "proceed"
    REFUSE = "refuse"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class Boundary:
    """One producer/consumer pair a fixture can be substituted at.

    ``producer``/``consumer``
        Fully-qualified names, e.g. ``claude_dispatcher.risk.collect_diff``.
        Qualified rather than bare so two modules may own same-named functions
        and so :func:`boundary_for` has one unambiguous key.
    ``kind``
        Which face of the check applies. See :class:`BoundaryKind`.
    ``value_kind``
        What travels, and hence the witness strategy. See :class:`ValueKind`.
    ``proceed_outcomes`` / ``refuse_outcomes``
        The consumer's outcome vocabulary, split, written out as the STRINGS
        the outcome renders to (``RiskVerdict.level``, ``DiffVerdict.value``,
        ``SealVerifyResult.outcome``). Both sets are given because an outcome
        in neither must RAISE: a new outcome defaulting to a side would let two
        different outcomes compare equal and silence the differential that is
        this module's whole engine. They must be disjoint and non-empty; a row
        that violates either is a :class:`FixtureReachabilityError` at load.
    ``extract_outcome``
        The dotted attribute path from the consumer's return value to the
        outcome string, e.g. ``"level"``, ``"verdict.value"``. Recorded here
        rather than hard-coded in the observer so a consumer that changes shape
        changes one table row and not the mechanism. A path that does not
        RESOLVE on the value the consumer actually returned is a
        :class:`FixtureReachabilityError` at observation time — the table has
        gone stale under the code, and an observer that recorded ``""`` or the
        repr instead would put a value into ``proceed_outcomes``/
        ``refuse_outcomes`` comparison that neither set names, which
        :func:`gate_disposition` would then raise on one frame later with no
        way to say why.

        **The empty string is a SENTINEL, and it does not mean "the return
        value IS the string".** P4 correction, 2026-08-10: that claim was false
        on every row that used it. It means *the consumer's return is not
        itself an outcome string, and the observer applies this row's own
        mapping*: ``()`` -> ``"clean"`` and a non-empty violation tuple ->
        ``"violation"`` for ``evaluate_changed_paths``; a string -> ``"text"``
        and ``None`` -> ``"absent"`` for ``blob_text_at``; and, on any row, a
        RAISE -> the row's spelling for the raise.

        So the observer does still hold per-row knowledge, which is the exact
        coupling this field was introduced to remove, and P4 declined to add an
        ``extract_value`` beside it. The reason, recorded so it is a decision
        and not an oversight: the value side is not a dotted path — it is a
        parameter name, a per-element attribute, and a "one observation per
        element" rule — so an honest field would be a small expression language,
        and a parser for it in the mechanism is more surface than the coupling
        it removes, on a table this size. What is NOT accepted is that the
        coupling be silent: a row for which the observer has no mapping must
        raise at :func:`observe`, exactly as an unwrappable consumer does.
    ``rationale``
        Why this pair is a boundary a fixture is actually substituted at, in
        this repo, today. Not decoration: a row whose rationale cannot name a
        real substitution is a row that will never fire and will be read as
        coverage.
    """

    producer: str
    consumer: str
    kind: BoundaryKind
    value_kind: ValueKind
    proceed_outcomes: tuple[str, ...]
    refuse_outcomes: tuple[str, ...]
    extract_outcome: str
    rationale: str


#: Every boundary this check knows about. WRITTEN OUT, one row per pair.
#:
#: Derived from nothing — not from a module scan, not from a comprehension over
#: the package, not from the set of functions that happen to take a
#: ``Sequence``. The lesson recorded on ``_DELEGATION_TARGETS`` in
#: ``tests/test_floor_closure.py`` applies unchanged: a table derived by a
#: comprehension across the thing it pins is vacuous, because deleting an entry
#: deletes the row instead of reddening it.
#:
#: **The two-way pin the seal author owes this table.** A written-out table
#: cannot notice a new boundary, so it needs a witness that is independent of
#: it and of the mechanism. The one available here is the SUITE: a producer
#: whose return value is passed, anywhere in ``tests/**``, as the argument a
#: consumer in this table also takes — or more sharply, any in-package function
#: whose return type annotation equals a parameter type annotation of another
#: in-package function, where the suite is observed calling the second without
#: the first. Deriving that set and requiring it to equal this table is the
#: seal that keeps the table honest, exactly as ``_delegation_closure`` keeps
#: ``_DELEGATION_TARGETS`` honest. It is left to the seal author because it is
#: a measurement, and this scaffold may not pre-empt what it measures.
#:
#: SEAM rows name the SUBSTITUTE's parameter, not a value: the fixture at a
#: seam is a callable, and what is checked is its source. The ``value_kind``
#: is still recorded, because a seam that starts carrying paths rather than
#: responses is a different check and the row must say which it is.
#:
#: **Every COLLECTOR row's consumer must TAKE the producer's value as an
#: argument.** P4 ruling, 2026-08-10, dispute 1. A consumer that calls its own
#: producer inside its own body has no argument a fixture can be substituted
#: at, so no observation can ever cross that row and it sits permanently in
#: ``ReachabilityReport.boundaries_never_observed`` — which
#: :class:`Boundary`'s own contract condemns in as many words ("a row that will
#: never fire and will be read as coverage"). Two rows written that way were
#: removed; see COLLECTOR ROWS REMOVED BY P4 in the module docstring. This is
#: not a style rule and not left to review: it is MEASURED against ``src/`` by
#: an AST sweep in
#: ``tests/test_fixture_reachability.py::test_no_collector_row_calls_its_own_producer``,
#: and a new row that violates it reddens on the commit that adds it.
BOUNDARIES: tuple[Boundary, ...] = (
    Boundary(
        producer="claude_dispatcher.risk.collect_diff",
        consumer="claude_dispatcher.risk.evaluate",
        kind=BoundaryKind.COLLECTOR,
        value_kind=ValueKind.GIT_PATH,
        proceed_outcomes=("low",),
        refuse_outcomes=("elevated",),
        extract_outcome="level",
        rationale=(
            "evaluate is the pure half and collect_diff is the only production "
            "producer of its changed_files argument; the module docstring says "
            "the split exists so the rules are 'unit-testable without a git "
            "repo', which is the substitution this row watches. Instance (A)."
        ),
    ),
    Boundary(
        producer="claude_dispatcher.role_protocol.changed_paths_between",
        consumer="claude_dispatcher.role_protocol.evaluate_changed_paths",
        kind=BoundaryKind.COLLECTOR,
        value_kind=ValueKind.GIT_PATH,
        proceed_outcomes=("clean",),
        refuse_outcomes=("violation", "undetermined"),
        extract_outcome="",
        rationale=(
            "the path gate's pure half. evaluate_changed_paths returns a tuple "
            "of violations rather than a verdict, so extract_outcome is empty "
            "and the observer maps () to 'clean' and a non-empty tuple to "
            "'violation' — the mapping check_branch itself performs."
        ),
    ),
    Boundary(
        producer="git via claude_dispatcher.repo_config._run_git",
        consumer="claude_dispatcher.repo_config.blob_text_at",
        kind=BoundaryKind.SEAM,
        value_kind=ValueKind.GIT_RESPONSE,
        proceed_outcomes=("text", "absent"),
        refuse_outcomes=("raised",),
        extract_outcome="",
        rationale=(
            "the run= seam. Instance (B): ls-tree is the FIRST command of every "
            "base-pinned blob read and three stubs answered it without naming "
            "it. 'absent' is a PROCEED because None means 'the tree does not "
            "contain it', which suppresses every signature change in the file."
        ),
    ),
    Boundary(
        producer="git via claude_dispatcher.role_protocol._run_git_capture",
        consumer="claude_dispatcher.role_protocol.check_branch",
        kind=BoundaryKind.SEAM,
        value_kind=ValueKind.GIT_RESPONSE,
        proceed_outcomes=("clean",),
        refuse_outcomes=("violation", "undetermined"),
        extract_outcome="verdict.value",
        rationale=(
            "the same seam one level out: check_branch takes run= and the three "
            "_run_stub helpers are supplied here. The nineteen rows of instance "
            "(B) cross this boundary, and the stub's totality is what they were "
            "all resting on."
        ),
    ),
)


def boundary_for(producer: str) -> Boundary | None:
    """The :data:`BOUNDARIES` row a producer owns, or None if it owns none.

    **THE ONE IMPLEMENTED FUNCTION IN THIS SCAFFOLD**, and the only exception
    to the contracts-only rule, for the same reason ``support_for_path`` was
    the exception in D2: it is the single answer site for "which row is this",
    and a seal that re-spells the lookup can drift from the implementation
    with both of them green. Keyed on the FULLY-QUALIFIED producer name, so
    a seal cannot get an answer by passing a bare function name and a future
    same-named producer in another module cannot collect the wrong row.

    A producer appearing twice in :data:`BOUNDARIES` is a table error, not a
    lookup outcome, and raises: two rows for one producer means two different
    outcome vocabularies for the same value, and the differential would then
    depend on which one was found first.

    That raise is why a SEAM row's producer is spelled ``git via <injection
    point>`` rather than ``git``. Two consumers share one external process but
    NOT one substitution: ``repo_config.blob_text_at`` and
    ``role_protocol.check_branch`` each take their own ``run=`` and each has
    its own outcome vocabulary, so they are two boundaries. Spelling both
    ``git`` would collapse them into a table error, and "fixing" it by letting
    the lookup return the first match would silently give one consumer the
    other's PROCEED set — a differential comparing two outcomes under the wrong
    vocabulary reports agreement, which is the permissive answer.
    """
    found = [b for b in BOUNDARIES if b.producer == producer]
    if len(found) > 1:
        raise FixtureReachabilityError(
            f"BOUNDARIES names the producer {producer!r} {len(found)} times, "
            "with consumers "
            f"{[b.consumer for b in found]}; one producer means one outcome "
            "vocabulary, or the differential depends on row order"
        )
    return found[0] if found else None


def _resolve_dotted(qualified: str) -> tuple[Any, str, Any]:
    """``(module, attribute, value)`` for a fully-qualified name.

    A SEAM producer is spelled ``git via <injection point>``; the injection
    point is what resolves, exactly as
    ``test_every_named_consumer_and_in_repo_producer_resolves`` reads it.
    Anything that does not resolve to a callable is a
    :class:`FixtureReachabilityError` and never a silently skipped row.
    """
    name = qualified.split(" via ")[-1]
    module_name, _, attribute = name.rpartition(".")
    if not module_name or not attribute:
        raise FixtureReachabilityError(
            f"{qualified!r} is not a fully-qualified name; BOUNDARIES rows are "
            "keyed on module-qualified names so two modules may own same-named "
            "functions"
        )
    try:
        module = importlib.import_module(module_name)
    except ImportError as exc:
        raise FixtureReachabilityError(
            f"{qualified!r}: the module {module_name!r} does not import ({exc})"
        ) from exc
    try:
        value = getattr(module, attribute)
    except AttributeError as exc:
        raise FixtureReachabilityError(
            f"{qualified!r}: {module_name!r} has no attribute {attribute!r} — "
            "the BOUNDARIES table has gone stale under the code"
        ) from exc
    if not callable(value):
        raise FixtureReachabilityError(
            f"{qualified!r} resolves to {type(value).__name__}, which is not "
            "callable"
        )
    return module, attribute, value


def _qualified_callable_name(func: Any) -> str:
    """A substitute producer's own name, for the ``value`` of a SEAM fixture."""
    module = getattr(func, "__module__", None) or "?"
    name = getattr(func, "__qualname__", None) or getattr(func, "__name__", None)
    if name is None:
        return f"{module}.{type(func).__name__}"
    return f"{module}.{name}"


# --------------------------------------------------------------------------- #
# Part 2 — observation: which fixtures actually crossed which boundary
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ObservedFixture:
    """One value that arrived at a boundary's consumer during a suite run.

    ``boundary``
        The row whose consumer received it.
    ``value``
        The value itself, in the consumer's own terms — a path string for
        GIT_PATH, the substitute callable's qualified name for GIT_RESPONSE.
        For a consumer taking a SEQUENCE of
        values (``changed_files``, ``changed_paths``), one ``ObservedFixture``
        is recorded PER ELEMENT: reachability is a property of a value, and a
        list that is half producible would otherwise get one verdict.
    ``outcome``
        The string the consumer returned for the call this value took part in,
        extracted per ``Boundary.extract_outcome``. Recorded at observation
        time because the differential needs it and no later reading can
        recover it.
    ``test_id``
        The pytest node id of the row that produced the call, so a finding
        names a row a human can open. Empty when the call did not happen under
        a test — which must be recorded as empty rather than guessed.
    ``call_site``
        ``file:line`` of the frame that called the consumer, which is where the
        fixture is written and therefore where the fix goes. This is NOT the
        test's own line when the value came through a helper, and that is the
        point: the substitution site is what has to change.
    ``cut_boundaries``
        Every boundary this same call crossed with a substituted value. Length
        one is the ordinary case. Length greater than one is the multi-cut case
        and forces :attr:`FindingDisposition.ABSTAIN` — the reachability of a
        value two substitutions deep is not decidable one hop at a time, and
        answering the near hop would imply the far one was checked.

    **There is NO replay handle here, and there will not be one.** P4 ruling,
    2026-08-10, dispute 2. The seal author was right that these five strings
    cannot replay the original call; the answer is not to add a sixth field
    that can.

    A callable held on this record would be invoked by :func:`check_suite`,
    which by contract runs AFTER the :func:`observe` block has exited. By then
    the world the call was made in is gone: the row's ``tmp_path`` is torn
    down, its monkeypatches are undone, the witness repositories it read no
    longer exist, module state has moved on. The second call would differ from
    the first in every respect EXCEPT the one value the differential is
    supposed to isolate — and :func:`measure_consequence` states the
    consequence of that in as many words: "A second call that differs in two
    ways measures nothing, and a differential that measures nothing reports
    SAME_DISPOSITION, which is the permissive answer." A replay handle would
    not merely fail to meet the obligation; it would manufacture the permissive
    answer while appearing to meet it. That is this module's own defect class,
    committed by the module.

    Replaying at OBSERVATION time, where the world is still live, does not
    rescue it either: the neighbour is not known until a witness has been
    constructed, and observation is contracted to be cheap and to construct
    nothing. And a handle would hold every argument object of every observed
    call alive for the whole run, then re-invoke consumers that are not pure
    (``check_branch`` spawns git, ``blob_text_at`` reads a tree) — an observer
    effect limit 11 already admits nothing here can notice.

    Where the differential IS performable, and by whom, is on
    :func:`check_observation`.
    """

    boundary: Boundary
    value: str
    outcome: str
    test_id: str
    call_site: str
    cut_boundaries: tuple[str, ...]


def observe(
    boundaries: Sequence[Boundary] = BOUNDARIES,
) -> AbstractContextManager[list[ObservedFixture]]:
    """Context manager: wrap each boundary's consumer and record what arrives.

    ``with observe() as seen:`` binds the list that will hold the observations;
    it is appended to as the suite runs and is complete when the block exits.
    Wrapping is undone on exit, including on an exception, or a failing run
    would leave the package patched for everything after it. A context manager
    rather than a pair of ``start``/``stop`` calls precisely so an exception
    cannot leave it on.

    Contract, normatively:

      * **The property: every call to the consumer is observed, including
        calls through a name some other module bound at import time.** That is
        what reason 2 above ("cannot be fooled by indirection") promises, and a
        helper module's ``from claude_dispatcher.risk import evaluate`` is the
        ordinary shape of it.

        The mechanism this contract used to name — "wrapped in the module that
        defines it, so callers that imported it by value are covered" — DOES
        NOT ACHIEVE THAT PROPERTY, and a body author who implements it will
        believe it works. Rebinding one module's attribute cannot reach a name
        another module already bound to the same object; the alias goes on
        pointing at the original function. P4 measured it, 2026-08-10: with
        only ``risk.evaluate`` rebound, a call through an import-time alias
        recorded ZERO observations.

        The achievable mechanism is a sweep: for every module in
        ``sys.modules``, rebind every attribute that **is** (identity, not
        equality) the consumer. Measured in the same probe, that records the
        aliased call. Three obligations come with it and a body must meet all
        three:

          - hold the reference to the consumer somewhere the sweep cannot
            itself rebind (a closure or a local, never a module global of a
            module the sweep will visit) — otherwise the sweep rebinds its own
            target part-way through and silently stops matching. This is a real
            trap; P4's first probe fell into it;
          - record every ``(module, attribute)`` pair rebound, and restore
            exactly those on exit — the unwrap is sealed and a sweep that
            cannot say what it patched cannot undo it;
          - skip nothing for tidiness. A module skipped is a call unobserved,
            and an unobserved call is indistinguishable from a boundary nothing
            crossed, which is this module's own subject matter.

        A consumer that cannot be wrapped, or a row for which the observer has
        no rule for extracting the value or the outcome (see
        :attr:`Boundary.extract_outcome`), is a
        :class:`FixtureReachabilityError` — never a silently unobserved
        boundary.
      * The wrapper is transparent: same return value, same exceptions, same
        arity. A consumer that RAISES still produces an observation, with
        ``outcome`` set to the boundary's spelling for the raise — the
        seam rows above name it ``"raised"`` — because a fixture that makes
        the consumer raise is exactly the defensive shape this module has to
        judge, and dropping it would make every such row invisible.
      * One :class:`ObservedFixture` per VALUE, not per call. A call carrying
        four paths yields four.
      * Values are recorded verbatim. No normalisation, no decoding, no
        stripping. The entire defect class is a value that is nearly the right
        value, and any tidying at this point erases the finding.
      * Observation is CHEAP and never constructs anything. Witnesses are built
        later, from the deduplicated set, by :func:`check_suite`.

    Reentrancy: nesting two :func:`observe` blocks is a
    :class:`FixtureReachabilityError`. Two live wrappers would double-record
    and the second unwrap would restore the first wrapper as if it were the
    original.
    """
    return _observe(tuple(boundaries))


#: The spelling every boundary uses for "the consumer raised". Named once so a
#: row that gains a different spelling changes the table and not the observer.
_RAISED = "raised"

#: True while an :func:`observe` block is live. Module-level rather than
#: per-call because reentrancy is a property of the PACKAGE — two blocks would
#: patch the same module attributes.
_OBSERVE_ACTIVE = False

#: The producers whose boundaries are currently mid-call, innermost last. A
#: value observed while this is non-empty crossed those boundaries on its way
#: in, which is what ``ObservedFixture.cut_boundaries`` records.
_CUT_STACK: list[str] = []


def _observed_values_risk_evaluate(bound: inspect.BoundArguments) -> list[str]:
    """One value per element of ``changed_files``: the path it carries."""
    files = bound.arguments.get("changed_files")
    if not isinstance(files, _AbcSequence) or isinstance(files, (str, bytes)):
        return []
    return [getattr(f, "path", f) for f in files if isinstance(getattr(f, "path", f), str)]


def _observed_values_changed_paths(bound: inspect.BoundArguments) -> list[str]:
    """One value per element of ``changed_paths``: the path itself."""
    paths = bound.arguments.get("changed_paths")
    if not isinstance(paths, _AbcSequence) or isinstance(paths, (str, bytes)):
        return []
    return [p for p in paths if isinstance(p, str)]


def _observed_values_seam(bound: inspect.BoundArguments) -> list[str]:
    """At a SEAM the fixture IS the substitute; ``run=None`` substitutes nothing."""
    run = bound.arguments.get("run")
    return [] if run is None else [_qualified_callable_name(run)]


#: How the observer reads the VALUES out of one consumer's call. Written out per
#: consumer, deliberately: ``Boundary.extract_outcome``'s own contract records
#: P4's refusal to add an ``extract_value`` beside it, and requires instead that
#: the residual coupling be LOUD — a row this table has no rule for raises at
#: :func:`observe` rather than contributing nothing.
_OBSERVER_VALUE_RULES: Mapping[str, Callable[[inspect.BoundArguments], list[str]]] = {
    "claude_dispatcher.risk.evaluate": _observed_values_risk_evaluate,
    "claude_dispatcher.role_protocol.evaluate_changed_paths": (
        _observed_values_changed_paths
    ),
    "claude_dispatcher.repo_config.blob_text_at": _observed_values_seam,
    "claude_dispatcher.role_protocol.check_branch": _observed_values_seam,
}

#: The mapping a row with an EMPTY ``extract_outcome`` asks the observer to
#: apply — the sentinel's real meaning (P4 correction, 2026-08-10). Not "the
#: return value is the string": it is that the return is not an outcome string
#: and this row's own mapping decides.
_OBSERVER_OUTCOME_RULES: Mapping[str, Callable[[Any], str]] = {
    "claude_dispatcher.role_protocol.evaluate_changed_paths": (
        lambda result: "clean" if not result else "violation"
    ),
    "claude_dispatcher.repo_config.blob_text_at": (
        lambda result: "absent" if result is None else "text"
    ),
}


def _extract_outcome(boundary: Boundary, result: Any) -> str:
    """The outcome string for one consumer return, per the row's own field."""
    path = boundary.extract_outcome
    if path:
        current: Any = result
        for part in path.split("."):
            try:
                current = getattr(current, part)
            except AttributeError as exc:
                raise FixtureReachabilityError(
                    f"{boundary.consumer}: extract_outcome {path!r} does not "
                    f"resolve on the {type(result).__name__} it returned "
                    f"({part!r} is missing) — the BOUNDARIES row has gone stale "
                    "under the code, and recording a default here would defer "
                    "the failure to gate_disposition, which cannot say that"
                ) from exc
        if not isinstance(current, str):
            raise FixtureReachabilityError(
                f"{boundary.consumer}: extract_outcome {path!r} resolved to a "
                f"{type(current).__name__}, not the outcome string the row's "
                "two outcome sets are written in"
            )
        return current
    rule = _OBSERVER_OUTCOME_RULES.get(boundary.consumer)
    if rule is None:
        raise FixtureReachabilityError(
            f"{boundary.consumer}: extract_outcome is empty and the observer "
            "holds no mapping for this row; a row it cannot extract from must "
            "raise, never contribute nothing"
        )
    return rule(result)


def _current_test_id() -> str:
    """The pytest node id of the running row, or '' when there is no row.

    Empty is recorded rather than guessed: a finding that names the wrong row
    sends a human to the wrong file.
    """
    raw = os.environ.get("PYTEST_CURRENT_TEST", "")
    if not raw:
        return ""
    return raw.rsplit(" (", 1)[0].strip()


def _make_observer(
    boundary: Boundary, original: Callable[..., Any], seen: list[ObservedFixture]
) -> Callable[..., Any]:
    """The transparent wrapper installed over one boundary's consumer.

    ``original`` is a CLOSURE CELL and never a module global: the sweep in
    :func:`_observe` rebinds every module attribute that is this function, so a
    body holding its target in a module global would have its own target
    rebound part-way through the sweep and would silently stop matching.
    """
    signature = inspect.signature(original)
    values_of = _OBSERVER_VALUE_RULES[boundary.consumer]

    @functools.wraps(original)
    def observer(*args: Any, **kwargs: Any) -> Any:
        try:
            bound = signature.bind(*args, **kwargs)
        except TypeError:
            # Not a call this consumer accepts. Stay transparent and let the
            # real function raise the real TypeError.
            return original(*args, **kwargs)
        values = values_of(bound)
        if not values:
            return original(*args, **kwargs)
        frame = sys._getframe(1)
        call_site = f"{frame.f_code.co_filename}:{frame.f_lineno}"
        test_id = _current_test_id()
        cut = (*_CUT_STACK, boundary.producer)
        _CUT_STACK.append(boundary.producer)
        try:
            result = original(*args, **kwargs)
        except BaseException:
            _CUT_STACK.pop()
            _append_observations(seen, boundary, values, _RAISED, test_id, call_site, cut)
            raise
        _CUT_STACK.pop()
        outcome = _extract_outcome(boundary, result)
        _append_observations(seen, boundary, values, outcome, test_id, call_site, cut)
        return result

    return observer


def _append_observations(
    seen: list[ObservedFixture],
    boundary: Boundary,
    values: Sequence[str],
    outcome: str,
    test_id: str,
    call_site: str,
    cut: tuple[str, ...],
) -> None:
    """One :class:`ObservedFixture` per VALUE. A call carrying four yields four."""
    for value in values:
        seen.append(
            ObservedFixture(
                boundary=boundary,
                value=value,
                outcome=outcome,
                test_id=test_id,
                call_site=call_site,
                cut_boundaries=cut,
            )
        )


@contextmanager
def _observe(boundaries: tuple[Boundary, ...]):
    global _OBSERVE_ACTIVE
    if _OBSERVE_ACTIVE:
        raise FixtureReachabilityError(
            "observe() is already active; two live wrappers double-record and "
            "the second unwrap restores the first wrapper as if it were the "
            "original"
        )

    seen: list[ObservedFixture] = []
    # Validate every row and build every wrapper BEFORE patching anything, so a
    # bad row leaves the package untouched.
    plan: dict[int, tuple[Boundary, Any, Any]] = {}
    for boundary in boundaries:
        if boundary.consumer not in _OBSERVER_VALUE_RULES:
            raise FixtureReachabilityError(
                f"{boundary.consumer}: the observer has no rule for extracting "
                "the values this consumer receives; an unobservable row must "
                "raise rather than be silently unobserved"
            )
        _module, _attribute, original = _resolve_dotted(boundary.consumer)
        plan[id(original)] = (boundary, original, _make_observer(boundary, original, seen))

    patched: list[tuple[dict, str, Any]] = []
    reached: set[int] = set()
    _OBSERVE_ACTIVE = True
    del _CUT_STACK[:]
    try:
        # The sweep. Rebinding one module's attribute cannot reach a name
        # another module already bound to the same object, so every module is
        # visited and every attribute that IS the consumer (identity, not
        # equality) is rebound. Nothing is skipped for tidiness: a module
        # skipped is a call unobserved, and an unobserved call is
        # indistinguishable from a boundary nothing crossed.
        for module in list(sys.modules.values()):
            if module is None:
                continue
            namespace = getattr(module, "__dict__", None)
            if not isinstance(namespace, dict):
                continue
            for name, value in list(namespace.items()):
                entry = plan.get(id(value))
                if entry is None or value is not entry[1]:
                    continue
                namespace[name] = entry[2]
                patched.append((namespace, name, entry[1]))
                reached.add(id(entry[1]))
        missed = [
            entry[0].consumer for key, entry in plan.items() if key not in reached
        ]
        if missed:
            raise FixtureReachabilityError(
                f"{missed}: the sys.modules sweep rebound no name for these "
                "consumers, so their boundaries would be silently unobserved"
            )
        yield seen
    finally:
        _OBSERVE_ACTIVE = False
        del _CUT_STACK[:]
        for namespace, name, original in patched:
            namespace[name] = original


# --------------------------------------------------------------------------- #
# Part 3 — the witness, and the two axes
# --------------------------------------------------------------------------- #


class Reachability(Enum):
    """Can the real producer emit this value? Four states, exhaustively.

    REACHED
        A witness state was constructed, the real producer ran over it, and one
        of the values it emitted is EQUAL to the fixture. The strongest answer
        available, and it carries the state that produced it.
    DIVERGED
        A witness state was constructed, the real producer ran, and it emitted
        something else. The fixture is not producible AND its producible
        neighbour is now known, which is what makes this the useful state
        rather than merely a negative one.
    UNREPRESENTABLE
        No witness state could be constructed: the value describes something
        the environment cannot hold (a path with an embedded NUL, a component
        over NAME_MAX, an empty path). Genuinely unreachable, with evidence —
        but evidence about THIS MACHINE, which is why :class:`Witness` carries
        an environment fingerprint and why limit 5 in the module docstring
        exists.
    NO_STRATEGY
        The checker has no way to construct a state for this value's kind. An
        ABSTENTION. It is not a pass, it may not be declared away, and the
        count of it is reported as the mechanism's own coverage. A check that
        let this resolve to REACHED would be a gate reporting a judgement it
        never made, on the very defect class it exists to close.

    Every dispatch over this enum must be exhaustive and raise on an unknown
    member. Adding a fifth state without visiting every dispatch is how the
    permissive value gets a new spelling.
    """

    REACHED = "reached"
    DIVERGED = "diverged"
    UNREPRESENTABLE = "unrepresentable"
    NO_STRATEGY = "no-strategy"


class Consequence(Enum):
    """Does the unreachability matter? Three states, exhaustively.

    Separate from :class:`Reachability` on purpose. One enum answers whether
    the producer can emit the value; the other answers whether anything hangs
    on the fact that it cannot. A single collapsed status made every report
    ambiguous about which half had failed.

    SAME_DISPOSITION
        The consumer was run on the fixture and on its producible neighbour,
        and both came out on the same side of the gate. The fixture is
        unreachable and nothing hinges on it. **Unreachable and that is the
        point** — or at any rate harmless, which is as far as a measurement
        can go.
    OPPOSITE_DISPOSITION
        The consumer PROCEEDS on one and REFUSES on the other. **Unreachable
        and nobody noticed.** The seal is green on an input production cannot
        produce, and the input production does produce goes the other way. The
        only unappealable finding this module makes.
    NOT_MEASURED
        There was no neighbour to compare against: the value was REACHED (no
        divergence), UNREPRESENTABLE (nothing produced), or NO_STRATEGY
        (nothing attempted). Named rather than left as None, so a report can
        never show a blank where a differential should be and be read as
        agreement.
    """

    SAME_DISPOSITION = "same-disposition"
    OPPOSITE_DISPOSITION = "opposite-disposition"
    NOT_MEASURED = "not-measured"


class WitnessGap(Enum):
    """Why a :class:`Witness` produced nothing. Two states, exhaustively.

    P4 addition, 2026-08-10, on the seal author's second smaller item.
    :func:`classify_value` has to tell an OS/git refusal from a missing
    strategy, and the only thing it had to tell them apart with was the WORDING
    of :attr:`Witness.detail`, which no contract fixed. Two functions in one
    module agreeing on a prose format is not a protocol: the body author writes
    both, they agree by construction, and the pair is green whatever the strings
    are. Then someone rewords an error message and the verdict flips from
    NO_STRATEGY (an abstention, never suppressible) to UNREPRESENTABLE (REPORT,
    and DECLARABLE) with no code change and nothing red. That flip runs toward
    the permissive side, which is why this is data and not prose.

    REFUSED
        A construction strategy exists for this value kind and the state could
        not be built: the OS or git refused the name. Yields UNREPRESENTABLE.
    NO_STRATEGY
        No construction strategy exists for this value kind at all; nothing was
        attempted. Yields NO_STRATEGY — an abstention.

    Every dispatch over this enum must be exhaustive and raise on an unknown
    member, on the same rule as :class:`Reachability`.
    """

    REFUSED = "refused"
    NO_STRATEGY = "no-strategy"


@dataclass(frozen=True)
class Witness:
    """The evidence behind one :class:`Reachability` answer.

    ``recipe``
        What was built, in words a human can reproduce by hand: "a repo on
        ``main`` with one base commit; on ``feat/x``, one added file at
        ``<value>``". A finding whose recipe cannot be followed is a finding
        nobody will act on.
    ``produced``
        Every value the real producer emitted over that state, in order. Plural
        because a producer emits a list and the fixture might match any element,
        and because the neighbour is chosen FROM this and must be visible.
    ``environment``
        Fingerprint of the machine: git version, filesystem type of the
        workspace, ``sys.platform``, and the encoding of the filesystem. An
        UNREPRESENTABLE is only as good as this, and a declaration resting on
        one inherits its dependence on it.
    ``gap``
        Why ``produced`` is empty, as DATA. ``None`` exactly when ``produced``
        is non-empty; a :class:`WitnessGap` member exactly when it is empty.
        The two contradictions — a gap alongside produced values, and an empty
        ``produced`` with no gap — are both
        :class:`FixtureReachabilityError` at :func:`classify_value`, because a
        witness that says two things or says nothing is a non-judgement, and a
        non-judgement must not read as an answer.
    ``detail``
        The same reason IN PROSE, FOR A HUMAN, and for nothing else. For
        REFUSED, the layer that refused and its message (the OS error, or
        git's). For NO_STRATEGY, which value kind had no strategy. Empty
        exactly when ``gap`` is None.

        **No decision anywhere in this module reads ``detail``.** It is
        evidence a person acts on — the declaration author for an
        UNREPRESENTABLE has nothing else to read — and it is deliberately not
        load-bearing, so that improving an error message can never change a
        verdict. A body that discriminates on it reddens; see
        ``test_classify_value_reads_the_gap_and_not_the_prose``.
    """

    recipe: str
    produced: tuple[str, ...]
    environment: Mapping[str, str]
    gap: WitnessGap | None
    detail: str


def construct_witness(
    boundary: Boundary, value: str, *, workspace: Path
) -> Witness:
    """Build a state that would make ``boundary``'s producer emit ``value``,
    run the producer over it, and return what it actually emitted.

    The construction is derived FROM THE VALUE — this is what makes the dynamic
    face affordable. There is no search over a space of repository states: the
    fixture describes the state, so the state is built and the producer is
    asked. A fixture naming ``.github/workflows/ci<LF>x.yml`` yields a repo
    with a file of exactly that name; whatever the producer then prints is the
    answer, and if it is not that string then that string is not producible.

    Total over :class:`ValueKind`, and RAISES on any member it does not handle
    rather than returning a Witness with an empty ``produced`` — an empty
    produced list would classify as DIVERGED against a neighbour that does not
    exist, which is a fabricated finding, and fabricated findings are how a
    mechanism gets switched off.

      GIT_PATH
          A fresh repository under ``workspace``: ``git init -b main``, one
          seed commit, ``git checkout -b feat/x``, create the file at exactly
          ``value``, commit, run the producer over ``main...feat/x``. The file
          is created with ``os.open``/``os.mkdir`` on the RAW BYTES of the
          name, never through a layer that normalises it. If the OS or git
          refuses, the result is ``produced=()`` with
          ``gap=WitnessGap.REFUSED`` and the refusing layer's own message in
          ``detail``.
      GIT_RESPONSE
          Only when the boundary row supplies a repository recipe; otherwise
          ``produced=()`` with ``gap=WitnessGap.NO_STRATEGY``, because a git
          response is a function of a repository state this module cannot infer
          from the response alone. The seam face (:func:`stub_gaps`) is what
          covers these rows by default.

    ``gap`` is set on every returned Witness and is ``None`` exactly when
    ``produced`` is non-empty. It is the ONLY thing that tells the two
    empty-``produced`` states apart; ``detail`` is prose beside it and no
    decision reads it (:class:`WitnessGap`).

    ``workspace`` must be a directory this call may create subdirectories in
    and must NOT be inside the repository under check: a witness repo created
    inside it would be picked up by the very collectors being interrogated.

    Cost: one repository per distinct ``(boundary, value)``. Callers dedupe
    before calling; :func:`check_suite` is required to.
    """
    kind = boundary.value_kind
    environment = _environment_fingerprint(workspace)
    if not isinstance(kind, ValueKind):
        raise FixtureReachabilityError(
            f"{boundary.consumer}: value_kind {kind!r} is not a ValueKind. "
            "construct_witness is total over the enum and raises rather than "
            "returning an empty produced list, which would classify as DIVERGED "
            "against a neighbour that does not exist"
        )
    if kind is ValueKind.GIT_RESPONSE:
        return Witness(
            recipe=(
                "no state was built: a git response is a function of a "
                "repository this module cannot infer from the response alone, "
                "and this boundary row supplies no repository recipe"
            ),
            produced=(),
            environment=environment,
            gap=WitnessGap.NO_STRATEGY,
            detail=(
                f"no dynamic construction strategy for value kind "
                f"{ValueKind.GIT_RESPONSE.value!r} at {boundary.consumer}; the "
                "seam face (stub_gaps) is what covers this row"
            ),
        )
    if kind is ValueKind.GIT_PATH:
        return _git_path_witness(boundary, value, workspace=workspace, environment=environment)
    raise FixtureReachabilityError(
        f"construct_witness has no strategy for ValueKind.{kind.name}; adding a "
        "member without visiting this dispatch is how the permissive value gets "
        "a new spelling"
    )


#: The two refs every GIT_PATH witness is built between, as the contract spells
#: the recipe: a seed commit on ``main``, the file added on ``feat/x``.
_WITNESS_BASE_REF = "main"
_WITNESS_HEAD_REF = "feat/x"

_GIT_VERSION: str | None = None


class _WitnessRefused(Exception):
    """The OS or git refused to hold the state this value describes."""


def _git_version() -> str:
    global _GIT_VERSION
    if _GIT_VERSION is None:
        try:
            proc = subprocess.run(
                ["git", "--version"], capture_output=True, text=True, timeout=30
            )
            _GIT_VERSION = proc.stdout.strip() or "unknown"
        except (OSError, subprocess.SubprocessError):  # pragma: no cover - no git
            _GIT_VERSION = "unavailable"
    return _GIT_VERSION


def _environment_fingerprint(workspace: Path | str | None) -> Mapping[str, str]:
    """The machine an UNREPRESENTABLE is a property OF (module docstring, limit 5)."""
    return {
        "git": _git_version(),
        "platform": sys.platform,
        "filesystem_encoding": sys.getfilesystemencoding(),
        "filesystem_errors": sys.getfilesystemencodeerrors(),
        "filesystem": _filesystem_limits(workspace),
    }


def _filesystem_limits(workspace: Path | str | None) -> str:
    if workspace is None:
        return "unknown"
    probe = Path(workspace)
    for candidate in (probe, *probe.parents):
        try:
            stats = os.statvfs(candidate)
        except OSError:
            continue
        return f"name_max={stats.f_namemax}"
    return "unknown"


def _git(repo: Path, *args: str) -> None:
    """One git command over a witness repository; a refusal is the layer's own."""
    proc = subprocess.run(
        ["git", *args],
        cwd=str(repo),
        capture_output=True,
        text=True,
        env=_GIT_ENV,
        timeout=120,
    )
    if proc.returncode != 0:
        raise _WitnessRefused(
            f"git refused the state: `git {' '.join(args)}` exited "
            f"{proc.returncode}: {(proc.stderr or proc.stdout).strip()}"
        )


_GIT_ENV = {
    **os.environ,
    "GIT_AUTHOR_NAME": "fixture-reachability",
    "GIT_AUTHOR_EMAIL": "witness@invalid",
    "GIT_COMMITTER_NAME": "fixture-reachability",
    "GIT_COMMITTER_EMAIL": "witness@invalid",
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
    "GIT_TERMINAL_PROMPT": "0",
}


def _create_at_raw_bytes(repo: Path, value: str) -> None:
    """Create a file named EXACTLY ``value``, on the raw bytes of the name.

    Never through a layer that normalises it: the whole defect class is a value
    that is nearly the right value, and a normalising create would build the
    state for a DIFFERENT name and then report that name as producible.
    """
    if value == "":
        raise _WitnessRefused(
            "the operating system refused the name: the empty path names no file"
        )
    for component in value.split("/"):
        if component in ("", ".", ".."):
            raise _WitnessRefused(
                "the operating system refused the name: the path component "
                f"{component!r} cannot name a file"
            )
    try:
        raw = os.fsencode(value)
    except (UnicodeEncodeError, ValueError) as exc:
        raise _WitnessRefused(
            f"the filesystem encoding refused the name: {exc}"
        ) from exc
    if b"\0" in raw:
        raise _WitnessRefused(
            "the operating system refused the name: embedded NUL byte, which no "
            "filesystem can hold in a path"
        )
    full = os.path.join(os.fsencode(str(repo)), raw)
    try:
        parent = os.path.dirname(full)
        if parent:
            os.makedirs(parent, exist_ok=True)
        descriptor = os.open(full, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o644)
    except (OSError, ValueError) as exc:
        raise _WitnessRefused(
            f"the operating system refused the name: {exc}"
        ) from exc
    try:
        os.write(descriptor, b"witness\n")
    finally:
        os.close(descriptor)


def _run_producer(boundary: Boundary, repo: Path) -> tuple[str, ...]:
    """Run the row's real producer over the witness state, resolved at CALL time.

    By module ATTRIBUTE and not bound by value at import, so a seal that swaps
    the producer (the flagship's pre-``263298d`` collector) really swaps what
    this interrogates.
    """
    module, attribute, _current = _resolve_dotted(boundary.producer)
    producer = getattr(module, attribute)
    emitted = producer(repo, _WITNESS_BASE_REF, _WITNESS_HEAD_REF)
    produced: list[str] = []
    for item in emitted:
        if isinstance(item, str):
            produced.append(item)
        else:
            path = getattr(item, "path", None)
            if not isinstance(path, str):
                raise FixtureReachabilityError(
                    f"{boundary.producer} emitted a {type(item).__name__} with "
                    "no path; the observer cannot compare it against a fixture"
                )
            produced.append(path)
    return tuple(produced)


def _git_path_witness(
    boundary: Boundary,
    value: str,
    *,
    workspace: Path,
    environment: Mapping[str, str],
) -> Witness:
    recipe = (
        f"a fresh repository: `git init -b {_WITNESS_BASE_REF}`, one seed "
        f"commit, `git checkout -b {_WITNESS_HEAD_REF}`, one file created on "
        f"the raw bytes of {value!r}, committed; then "
        f"{boundary.producer} over {_WITNESS_BASE_REF}...{_WITNESS_HEAD_REF}"
    )
    root = Path(workspace)
    try:
        root.mkdir(parents=True, exist_ok=True)
        repo = Path(tempfile.mkdtemp(prefix="witness-", dir=str(root)))
    except OSError as exc:
        raise FixtureReachabilityError(
            f"the witness workspace {workspace} cannot be created: {exc}"
        ) from exc
    try:
        _git(repo, "init", "-q", "-b", _WITNESS_BASE_REF, ".")
        (repo / "seed.txt").write_text("seed\n", encoding="utf-8")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-q", "-m", "seed")
        _git(repo, "checkout", "-q", "-b", _WITNESS_HEAD_REF)
        _create_at_raw_bytes(repo, value)
        _git(repo, "add", "-A")
        _git(repo, "commit", "-q", "-m", "add")
        produced = _run_producer(boundary, repo)
    except _WitnessRefused as exc:
        return Witness(
            recipe=recipe,
            produced=(),
            environment=environment,
            gap=WitnessGap.REFUSED,
            detail=str(exc),
        )
    except FixtureReachabilityError:
        raise
    except Exception as exc:
        return Witness(
            recipe=recipe,
            produced=(),
            environment=environment,
            gap=WitnessGap.REFUSED,
            detail=(
                f"{boundary.producer} refused the state built for {value!r}: "
                f"{type(exc).__name__}: {exc}"
            ),
        )
    if not produced:
        return Witness(
            recipe=recipe,
            produced=(),
            environment=environment,
            gap=WitnessGap.REFUSED,
            detail=(
                f"{boundary.producer} emitted nothing over a state built for "
                f"{value!r}; the state exists but the producer does not report it"
            ),
        )
    return Witness(
        recipe=recipe,
        produced=produced,
        environment=environment,
        gap=None,
        detail="",
    )


def classify_value(*, value: str, witness: Witness) -> Reachability:
    """The pure decision: which of the four states does this witness support?

    Exactly one rule, and it is a string equality, deliberately:

      * ``value in witness.produced``                    -> REACHED
      * ``witness.produced`` non-empty, value absent     -> DIVERGED
      * ``witness.produced`` empty, ``gap`` is
        :attr:`WitnessGap.REFUSED`                        -> UNREPRESENTABLE
      * ``witness.produced`` empty, ``gap`` is
        :attr:`WitnessGap.NO_STRATEGY`                    -> NO_STRATEGY

    The two empty-``produced`` states are told apart by :attr:`Witness.gap` and
    by NOTHING ELSE. P4 correction, 2026-08-10: this contract used to say they
    were told apart by what ``Witness.detail`` "names", and left the wording
    unspecified — so the discrimination rested on two functions in one module
    happening to agree on a prose format, and a reworded message could move a
    finding from an abstention to a declarable REPORT with nothing red. See
    :class:`WitnessGap`.

    The dispatch over :class:`WitnessGap` is total and raises on any member it
    does not name, on the same rule as every other dispatch here.

    EQUALITY, not a match, not a normalisation, not a comparison modulo
    quoting. Every instance of this defect class is a value that is nearly the
    right value: a decoded path against a rendering, a real line feed against
    two characters, ``rc 128`` against ``rc 0``. Any tolerance here erases
    exactly the findings the module exists to make, and a "helpful" normaliser
    added by a later author is the single most likely way this check is
    silently disabled. A seal should pin that.

    An empty ``produced`` with ``gap`` of ``None`` is a
    :class:`FixtureReachabilityError`: a witness that neither produced nor
    explained is a non-judgement, and the whole point is that a non-judgement
    must not read as an answer. So is the opposite contradiction — a non-empty
    ``produced`` alongside a ``gap`` — for the same reason read the other way:
    a witness that both produced and explained why it could not has been
    assembled by something that did not know which had happened.
    """
    produced = tuple(witness.produced)
    gap = witness.gap
    if produced and gap is not None:
        raise FixtureReachabilityError(
            f"a witness for {value!r} both produced {list(produced)} and carries "
            f"gap {gap!r}: it was assembled by something that did not know which "
            "had happened, and resolving it either way picks one of two answers "
            "to a question the witness cannot be asked"
        )
    if produced:
        # EQUALITY. Not a match, not a normalisation, not a comparison modulo
        # quoting: every instance of this defect class is a value that is nearly
        # the right value.
        return Reachability.REACHED if value in produced else Reachability.DIVERGED
    if gap is None:
        raise FixtureReachabilityError(
            f"a witness for {value!r} neither produced nor explained: a "
            "non-judgement must not read as an answer, and defaulting it to "
            "NO_STRATEGY would report an abstention the checker never made"
        )
    if gap is WitnessGap.REFUSED:
        return Reachability.UNREPRESENTABLE
    if gap is WitnessGap.NO_STRATEGY:
        return Reachability.NO_STRATEGY
    raise FixtureReachabilityError(
        f"classify_value has no rule for WitnessGap member {gap!r}; the dispatch "
        "is total and raises rather than falling through to a state"
    )


def gate_disposition(boundary: Boundary, outcome: str) -> GateDisposition:
    """Which side of the gate an outcome string falls on.

    Reads the boundary's two written-out sets and nothing else. An outcome in
    neither RAISES :class:`FixtureReachabilityError` naming the outcome, the
    boundary, and both sets — it never returns
    :attr:`GateDisposition.UNKNOWN`, which exists to be named, not returned.

    The raise is the load-bearing part. Defaulting an unclassified outcome to
    either side would make it compare EQUAL to some already-classified outcome,
    and :func:`measure_consequence` would then report SAME_DISPOSITION for a
    pair that differs — the differential silently reporting agreement is the
    same shape as the seals this module is written against.
    """
    if outcome in boundary.proceed_outcomes:
        return GateDisposition.PROCEED
    if outcome in boundary.refuse_outcomes:
        return GateDisposition.REFUSE
    raise FixtureReachabilityError(
        f"{boundary.consumer}: the outcome {outcome!r} is named by neither "
        f"proceed_outcomes {list(boundary.proceed_outcomes)} nor "
        f"refuse_outcomes {list(boundary.refuse_outcomes)}. A new outcome must "
        "be classified by a human editing BOUNDARIES; defaulting it to a side "
        "would let it compare equal to an already-classified one and make every "
        "differential over it vacuous"
    )


def measure_consequence(
    boundary: Boundary, *, fixture_outcome: str, neighbour_outcome: str | None
) -> Consequence:
    """Run the differential over the producible neighbour.

    ``fixture_outcome`` is what the consumer returned when the seal handed it
    the fixture — already observed, never re-derived. ``neighbour_outcome`` is
    what the consumer returns when handed the neighbour, which the caller
    obtains by calling the consumer a second time with the neighbour
    substituted and everything else held identical.

    ``None`` means there was no neighbour, and yields
    :attr:`Consequence.NOT_MEASURED`. Otherwise the two are put through
    :func:`gate_disposition` and compared BY DISPOSITION, not by string: two
    different refusals are still both refusals and nothing hinges on which. It
    is the crossing of the gate that matters, and it is the only thing that
    distinguishes the two cases the brief asked to separate.

    "Everything else held identical" is a real obligation on the caller and is
    the reason this function does not run the consumer itself: substituting the
    neighbour must change one value and nothing else — same config, same task
    row, same policy, same sibling paths. A second call that differs in two
    ways measures nothing, and a differential that measures nothing reports
    SAME_DISPOSITION, which is the permissive answer.
    """
    if neighbour_outcome is None:
        return Consequence.NOT_MEASURED
    fixture_side = gate_disposition(boundary, fixture_outcome)
    neighbour_side = gate_disposition(boundary, neighbour_outcome)
    if fixture_side is neighbour_side:
        return Consequence.SAME_DISPOSITION
    return Consequence.OPPOSITE_DISPOSITION


# --------------------------------------------------------------------------- #
# Part 4 — findings and the ruling
# --------------------------------------------------------------------------- #


class FindingDisposition(Enum):
    """What the mechanism does about one finding. Five states, exhaustively.

    OK
        REACHED. The fixture is a value production emits.
    BREACH
        The unappealable finding. Reached by two routes, and by no other:
        :attr:`Consequence.OPPOSITE_DISPOSITION` at any boundary, and a
        :class:`StubGap`. No declaration accepts a BREACH — the resolution is
        to change the fixture to the neighbour or to fix the producer, and an
        annotation is neither.
    REPORT
        UNREPRESENTABLE with no declaration. Not a failure. Printed, counted,
        and left for a human, because with no neighbour there is no
        differential and the mechanism has nothing further to say.
    ACCEPTED
        UNREPRESENTABLE with a declaration that names it. The declaration's
        only power, and the module's only policy rather than measurement.
    ABSTAIN
        NO_STRATEGY; a multi-cut observation
        (``len(ObservedFixture.cut_boundaries) > 1``); or a DIVERGED finding
        for which no ``differential`` was supplied, so the consequence axis was
        never measured (P4, 2026-08-10, dispute 2). The mechanism did not
        judge. Never suppressible and always counted separately from OK: a
        report that folds abstentions into passes is a coverage number that
        lies, and this repo has already paid for one of those ("a mutation gate
        that had never run reported success for months").
    """

    OK = "ok"
    BREACH = "breach"
    REPORT = "report"
    ACCEPTED = "accepted"
    ABSTAIN = "abstain"


@dataclass(frozen=True)
class Finding:
    """One judged observation: the value, the two axes, and the evidence.

    ``neighbour`` is the producible value the fixture should probably have
    been, chosen from ``witness.produced``, and is None exactly when
    ``reachability`` is not DIVERGED. When ``produced`` holds several values
    the neighbour is the one whose consumer disposition differs from the
    fixture's if any does, and the first otherwise — so a BREACH is never
    hidden behind an innocuous sibling in the same call.
    """

    observed: ObservedFixture
    reachability: Reachability
    consequence: Consequence
    neighbour: str | None
    witness: Witness | None
    detail: str


def check_observation(
    observed: ObservedFixture,
    *,
    workspace: Path,
    differential: Callable[[ObservedFixture, str], str] | None = None,
) -> Finding:
    """Judge one observation end to end: witness, classify, differential.

    The composition, in order, and a body must not reorder it:

      1. ``len(observed.cut_boundaries) > 1`` -> NO_STRATEGY /
         NOT_MEASURED, with the detail naming every cut. Judged FIRST, because
         a multi-cut observation's near hop is answerable and answering it
         would imply the far one was checked.
      2. :func:`construct_witness`, then :func:`classify_value`.
      3. DIVERGED only: choose the neighbour, and then run the differential —
         IF, AND ONLY IF, a caller supplied one. Every other reachability
         yields NOT_MEASURED without a second call.

    ``differential``
        P4 ruling, 2026-08-10, dispute 2. Step 3 used to say this function
        should "re-run the consumer with the neighbour substituted and nothing
        else changed". It cannot: :class:`ObservedFixture` records five strings
        and nothing that can replay the original call, and the ruling on the
        record itself says why no sixth field will fix that.

        So the obligation goes where the world is. ``differential`` is supplied
        by a caller that can hold everything else identical; it is handed
        ``(observed, neighbour)`` and returns the outcome string the SAME
        consumer produces for the neighbour, which then goes to
        :func:`measure_consequence`. This is the same placement
        :func:`measure_consequence` already uses and for the same stated reason
        — it "does not run the consumer itself" because "everything else held
        identical is a real obligation on the caller". The only correction is
        that ``check_observation`` was made that caller and is not one.

        ``None`` — the default, and the honest answer for every caller that
        holds only an observation list — means the differential was NOT
        performed. The finding is then DIVERGED with
        :attr:`Consequence.NOT_MEASURED`, ``neighbour`` set, and ``detail``
        saying so, and :func:`adjudicate` rules it ABSTAIN. Not OK, not REPORT,
        not a raise: the reachability axis WAS measured and the consequence
        axis was not, which is precisely the half-measured state the two-enum
        split exists to be able to say.

        The obligation ``differential`` carries is real and unenforceable here:
        a callable that changes two things measures nothing and will report
        SAME_DISPOSITION, the permissive answer. The type makes the obligation
        visible at the call site instead of implied at a call site that does
        not exist. See ``test_flagship_pre_fix_collector_is_a_breach`` for a
        differential that does hold identical, written out.

    Any :class:`FixtureReachabilityError` propagates. It is not converted into
    a finding: "the check could not run" and "the check ran and found nothing"
    must not be the same value, which is the rule this whole effort turns on.
    """
    return _check_observation(
        observed, workspace=workspace, differential=differential
    )


#: "This caller has not built a witness"; distinct from a witness that produced
#: nothing, which is an ANSWER. :func:`check_suite` builds the deduplicated set
#: itself and hands each one in.
_NO_WITNESS = object()


def _check_observation(
    observed: ObservedFixture,
    *,
    workspace: Path,
    differential: Callable[[ObservedFixture, str], str] | None = None,
    witness: Any = _NO_WITNESS,
) -> Finding:
    boundary = observed.boundary
    # The row's own outcome must be classifiable before anything else is said
    # about it: an outcome in neither set means the table is stale, and that is
    # "the check could not run", never a finding.
    fixture_side = gate_disposition(boundary, observed.outcome)

    cuts = tuple(observed.cut_boundaries)
    if len(cuts) > 1:
        # Judged FIRST. The near hop is answerable and answering it would imply
        # the far one was checked.
        return Finding(
            observed=observed,
            reachability=Reachability.NO_STRATEGY,
            consequence=Consequence.NOT_MEASURED,
            neighbour=None,
            witness=None,
            detail=(
                "the value crossed more than one boundary in this call — "
                + ", ".join(cuts)
                + " — so its reachability is not decidable one hop at a time"
            ),
        )

    if witness is _NO_WITNESS:
        witness = construct_witness(boundary, observed.value, workspace=workspace)
    reachability = classify_value(value=observed.value, witness=witness)

    if reachability is Reachability.REACHED:
        return Finding(
            observed=observed,
            reachability=reachability,
            consequence=measure_consequence(
                boundary,
                fixture_outcome=observed.outcome,
                neighbour_outcome=None,
            ),
            neighbour=None,
            witness=witness,
            detail=(
                f"{boundary.producer} emitted {observed.value!r} over the "
                "witness state; the fixture is a value production produces"
            ),
        )
    if reachability in (Reachability.UNREPRESENTABLE, Reachability.NO_STRATEGY):
        return Finding(
            observed=observed,
            reachability=reachability,
            consequence=measure_consequence(
                boundary,
                fixture_outcome=observed.outcome,
                neighbour_outcome=None,
            ),
            neighbour=None,
            witness=witness,
            detail=witness.detail,
        )
    if reachability is not Reachability.DIVERGED:
        raise FixtureReachabilityError(
            f"check_observation has no rule for Reachability.{reachability.name}"
        )

    produced = tuple(witness.produced)
    if differential is None:
        # The honest answer for every caller that holds only an observation
        # list. The reachability axis WAS measured; the consequence axis was
        # not, and adjudicate rules the pair ABSTAIN.
        return Finding(
            observed=observed,
            reachability=reachability,
            consequence=measure_consequence(
                boundary,
                fixture_outcome=observed.outcome,
                neighbour_outcome=None,
            ),
            neighbour=produced[0],
            witness=witness,
            detail=(
                f"{observed.value!r} is not producible; {boundary.producer} "
                f"emits {produced[0]!r} for the state it describes. The "
                "differential was NOT run: no `differential` was supplied, so "
                "whether the two go the same way through the gate is unmeasured"
            ),
        )

    # A neighbour whose disposition DIFFERS is chosen over one that agrees, so a
    # breach is never hidden behind an innocuous sibling in the same call.
    first: tuple[str, str] | None = None
    chosen: tuple[str, str] | None = None
    for candidate in produced:
        candidate_outcome = differential(observed, candidate)
        if first is None:
            first = (candidate, candidate_outcome)
        if gate_disposition(boundary, candidate_outcome) is not fixture_side:
            chosen = (candidate, candidate_outcome)
            break
    neighbour, neighbour_outcome = chosen if chosen is not None else first
    return Finding(
        observed=observed,
        reachability=reachability,
        consequence=measure_consequence(
            boundary,
            fixture_outcome=observed.outcome,
            neighbour_outcome=neighbour_outcome,
        ),
        neighbour=neighbour,
        witness=witness,
        detail=(
            f"{observed.value!r} is not producible; the neighbour "
            f"{neighbour!r} is, and the supplied differential returned "
            f"{neighbour_outcome!r} for it against {observed.outcome!r} for the "
            "fixture"
        ),
    )


@dataclass(frozen=True)
class ReachabilityDeclaration:
    """A human's statement that an UNREPRESENTABLE fixture is deliberate.

    The only annotation in the mechanism, and it can buy exactly one thing:
    :attr:`FindingDisposition.REPORT` becomes
    :attr:`FindingDisposition.ACCEPTED`. It cannot touch a BREACH, a StubGap,
    or an abstention.

    ``test_id`` / ``producer`` / ``value``
        Which finding it answers. All three must match exactly. A declaration
        that matches nothing is itself reported — a stale declaration is how
        an accepted state outlives the reason for it, and this repo has the
        precedent in ``_DELEGATION_TARGETS``'s stale-row seal.
    ``reason``
        Why the value cannot be produced and why the row is worth keeping
        anyway. Prose, for a human.
    ``guard``
        The seal or the code site that proves the state cannot arise — the one
        part of a declaration that is not merely an assertion of good faith.
        A defensive row is defensible precisely when something ELSE proves the
        guard holds; naming that something is the cost of the declaration.
        It is checked for existence and for nothing more, and the module
        docstring's limit 10 says plainly that this is the mechanism's weakest
        point and the place it will first be abused.
    """

    test_id: str
    producer: str
    value: str
    reason: str
    guard: str


def adjudicate(
    finding: Finding, declaration: ReachabilityDeclaration | None
) -> FindingDisposition:
    """The one answer site for "what does this finding mean".

    Total over :class:`Reachability` x :class:`Consequence`, raising on any
    pair the table below does not name, so a new member of either enum cannot
    fall through to the permissive answer:

        REACHED,         NOT_MEASURED            -> OK
        DIVERGED,        OPPOSITE_DISPOSITION    -> BREACH   (declaration ignored)
        DIVERGED,        SAME_DISPOSITION        -> REPORT / ACCEPTED
        DIVERGED,        NOT_MEASURED            -> ABSTAIN  (declaration ignored)
        UNREPRESENTABLE, NOT_MEASURED            -> REPORT / ACCEPTED
        NO_STRATEGY,     NOT_MEASURED            -> ABSTAIN  (declaration ignored)

    ``DIVERGED`` with ``NOT_MEASURED`` is P4's ruling of 2026-08-10 on dispute
    2 and is a NEW row: the pair used to raise, because nothing could produce it.
    It is now the ordinary outcome of a DIVERGED finding whose caller supplied
    no ``differential``, and it is an ABSTENTION — the value is known not to be
    producible, its neighbour is known, and whether that MATTERS was not
    measured. Half-measured is not a pass and is not a failure, and refusing to
    name it (by raising) would abort the whole run on the first divergence and
    leave no report at all, which for a check meant to sweep a suite is the
    same as not having one. It is undeclarable for the same reason NO_STRATEGY
    is: the count of abstentions is this mechanism's own coverage figure, and a
    declaration that could silence one would be buying silence on a
    measurement that was never taken.

    A DIVERGED abstention is nonetheless the LOUDEST abstention this module
    makes, and a report should read it that way: unlike NO_STRATEGY it carries
    a fixture, a producible neighbour and a reproducible recipe, so a human can
    finish the differential by hand in ten lines — which is exactly what
    ``test_flagship_pre_fix_collector_is_a_breach`` does.

    ``DIVERGED`` with ``SAME_DISPOSITION`` is declarable and NOT a breach, and
    that is the ruling the brief's hardest question turns on. It is also where
    instance (B) lands today: ``test_role_protocol_diff.py``'s ``_run_stub``
    answers ``ls-tree`` with a response git cannot produce, and
    ``blob_text_at`` reaches the same text either way, so the outcome is
    unchanged. The structural face
    (:func:`stub_gaps`) is what makes it a BREACH regardless, and the two faces
    disagreeing about the same defect is not an inconsistency — one asks
    whether it mattered this time, the other asks whether the stub's totality
    claim is true, and only the second is a property.

    A declaration whose three keys do not match ``finding`` is ignored for the
    ruling AND reported as stale by :func:`check_suite`. Silently ignoring it
    would let a typo look like an accepted state.
    """
    ruled = _RULING_TABLE.get((finding.reachability, finding.consequence))
    if ruled is None:
        raise FixtureReachabilityError(
            f"adjudicate has no ruling for "
            f"({finding.reachability!r}, {finding.consequence!r}); the grid is "
            "total and raises rather than falling through to the permissive "
            "answer"
        )
    undeclared, declared = ruled
    return declared if _declaration_matches(declaration, finding) else undeclared


#: The ruling grid, written out. Every pair not named here RAISES. The only
#: thing a declaration buys is the second column, and it differs from the first
#: on exactly two rows — the two UNREPRESENTABLE-shaped ones.
_RULING_TABLE: Mapping[
    tuple[Reachability, Consequence],
    tuple[FindingDisposition, FindingDisposition],
] = {
    (Reachability.REACHED, Consequence.NOT_MEASURED): (
        FindingDisposition.OK,
        FindingDisposition.OK,
    ),
    (Reachability.DIVERGED, Consequence.OPPOSITE_DISPOSITION): (
        FindingDisposition.BREACH,
        FindingDisposition.BREACH,
    ),
    (Reachability.DIVERGED, Consequence.SAME_DISPOSITION): (
        FindingDisposition.REPORT,
        FindingDisposition.ACCEPTED,
    ),
    (Reachability.DIVERGED, Consequence.NOT_MEASURED): (
        FindingDisposition.ABSTAIN,
        FindingDisposition.ABSTAIN,
    ),
    (Reachability.UNREPRESENTABLE, Consequence.NOT_MEASURED): (
        FindingDisposition.REPORT,
        FindingDisposition.ACCEPTED,
    ),
    (Reachability.NO_STRATEGY, Consequence.NOT_MEASURED): (
        FindingDisposition.ABSTAIN,
        FindingDisposition.ABSTAIN,
    ),
}


def _declaration_matches(
    declaration: ReachabilityDeclaration | None, finding: Finding
) -> bool:
    """All THREE keys, exactly. Two of three is a typo that looks accepted."""
    if declaration is None:
        return False
    return (
        declaration.test_id == finding.observed.test_id
        and declaration.producer == finding.observed.boundary.producer
        and declaration.value == finding.observed.value
    )


# --------------------------------------------------------------------------- #
# Part 5 — the seam face: stub totality
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class StubGap:
    """A substitute producer answering a command its own dispatch never names.

    Instance (B), as a property rather than as one bug. The claim every
    ``_run_stub`` in this repo makes in its docstring — "an unscripted command
    raises, so a seal cannot pass on a read it never modelled" — is true only
    if the dispatch is by DECLARED COMMAND with an unconditional refusal at the
    end. ``test_role_protocol_diff.py``'s dispatches partly by argv SHAPE
    (``":" in arg``), and a shape predicate is not a command name:
    ``git ls-tree -z main: -- x.py`` satisfies it, so both ``ls-tree`` and
    ``cat-file`` are answered by the blob branch of a stub that names neither.

    **Exactly one of the three ``_run_stub`` files carries a gap.** Measured by
    P4, 2026-08-10, against the argvs ``blob_text_at`` really issues, and the
    two clean files are clean for DIFFERENT reasons — which is why counting
    them together produced this module's own over-call:

      * ``test_role_protocol_diff.py`` — unmodelled AND answered. The gap.
      * ``test_role_protocol_provenance.py`` — MODELLED and answered
        (``"ls-tree" in argv``, ``"cat-file" in argv``). A stub doing its job.
      * ``test_role_protocol_floor.py`` — unmodelled and REFUSED
        (``AssertionError: unscripted git command`` on both argvs). The
        totality claim holding.

    Both halves of the definition are load-bearing and neither on its own
    identifies a gap. A reading that took "does not name it" for the whole
    definition reported two files, and an over-calling check is one nobody runs
    twice.

    ``answered_as`` names the branch that swallowed it, so the fix is local.

    Whose fix it is, which the seal author needs stated: ``tests/**`` is
    immutable to P1 and to P3, so a gap this reports cannot be closed by
    either. Making a stub total is a seal-author or P4 edit. This module
    detects and names; it does not and may not repair.
    """

    stub: str
    argv: tuple[str, ...]
    subcommand: str
    modelled: frozenset[str]
    answered_as: str
    consumer: str


def git_subcommand(argv: Sequence[str]) -> str | None:
    """The subcommand of a git argv, or None if there is none.

    Not ``argv[1]``. Git takes global options before the subcommand and this
    repo uses them: ``role_protocol.changed_paths_between`` runs
    ``git -c core.quotePath=false diff ...``, so ``argv[1]`` there is ``-c``.
    The rule: skip ``argv[0]``, then skip every leading token beginning with
    ``-``, consuming one following token as its value for the options that take
    one (``-c``, ``-C``, ``--git-dir``, ``--work-tree``, ``--namespace``,
    ``--exec-path`` in its separated spelling); the first remaining token is
    the subcommand.

    Returns None for an argv with no subcommand at all (``git``, ``git
    --version``). None is a distinct answer from "a subcommand I do not know",
    and a caller must not treat the two alike: an argv with no subcommand
    cannot be a modelling gap, while an unrecognised one is precisely what a
    gap looks like.

    An option this rule does not know that takes a separated value will make
    that value read as the subcommand. Recorded rather than hidden: the fix is
    to add it to the list, and a seal should pin the current list so a new
    global option in an argv reddens rather than mis-parses.
    """
    tokens = [str(token) for token in argv][1:]
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if not token.startswith("-"):
            return token
        index += 2 if token in _GLOBAL_OPTIONS_TAKING_A_VALUE else 1
    return None


#: The git global options this rule knows take a SEPARATED value. Written out,
#: because an option missing from it makes its value read as the subcommand —
#: recorded on :func:`git_subcommand` and pinned by a seal, so a new global
#: option in an argv reddens rather than mis-parses. Joined spellings
#: (``--git-dir=/x``) need no entry: they are one token.
_GLOBAL_OPTIONS_TAKING_A_VALUE = frozenset(
    {"-c", "-C", "--git-dir", "--work-tree", "--namespace", "--exec-path"}
)


def modelled_subcommands(source: str, function_name: str) -> frozenset[str]:
    """The git subcommands a substitute's source explicitly names.

    Read by AST from the substitute's own text, so the answer is a property of
    the stub and not of anything it was told. What counts as naming a
    subcommand, and nothing else counts:

      * a string constant compared against, or tested for membership in, the
        argv list or a variable derived from it — ``if "diff" in argv``,
        ``argv[1] == "cat-file"``, ``subcmd in ("show", "ls-tree")``;
      * a string constant key of a dict the dispatch indexes with an
        argv-derived value.

    What deliberately does NOT count, because this is the whole finding: a
    predicate over argv SHAPE. ``":" in a``, ``a.startswith("-")``,
    ``len(argv) > 3``, a regex over the joined argv. Those answer commands
    without naming them, and a stub whose last branch before the raise is one
    of them has no totality property at all — which is what the nineteen seals
    were resting on.

    ``function_name`` is the substitute's defining function (the outer
    ``_run_stub``, not the inner ``run``); the analyzer walks the whole nested
    body. A name that is not a function in ``source`` raises
    :class:`FixtureReachabilityError`, because an analyzer that quietly returns
    the empty set would make every stub look maximally under-declared and the
    resulting flood is how a check gets turned off.
    """
    function = _find_function(_parse(source), function_name)
    argv_names = _argv_derived_names(function)
    dict_literals = _dict_literals(function)
    named: set[str] = set()

    def _is_argv_expression(node: ast.AST) -> bool:
        if isinstance(node, ast.Name):
            return node.id in argv_names
        if isinstance(node, ast.Subscript):
            return _is_argv_expression(node.value)
        return False

    for node in ast.walk(function):
        if isinstance(node, ast.Compare):
            lefts = [node.left, *node.comparators[:-1]]
            for left, operator, right in zip(lefts, node.ops, node.comparators):
                if isinstance(operator, (ast.In, ast.NotIn)):
                    # `"diff" in argv`
                    if _string_constant(left) is not None and _is_argv_expression(right):
                        named.add(_string_constant(left))
                    # `subcmd in ("show", "ls-tree")`
                    elif _is_argv_expression(left) and isinstance(
                        right, (ast.Tuple, ast.List, ast.Set)
                    ):
                        named.update(_string_constants(right.elts))
                elif isinstance(operator, (ast.Eq, ast.NotEq)):
                    # `argv[1] == "cat-file"`, either way round.
                    if _string_constant(left) is not None and _is_argv_expression(right):
                        named.add(_string_constant(left))
                    elif _is_argv_expression(left) and _string_constant(right) is not None:
                        named.add(_string_constant(right))
        elif isinstance(node, ast.Subscript):
            # `table[argv[1]]`, where `table` is a dict literal in this source.
            if (
                isinstance(node.value, ast.Name)
                and node.value.id in dict_literals
                and _is_argv_expression(_subscript_index(node))
            ):
                named.update(_string_constants(dict_literals[node.value.id].keys))
    return frozenset(named)


def _parse(source: str) -> ast.Module:
    try:
        return ast.parse(source)
    except SyntaxError as exc:
        raise FixtureReachabilityError(
            f"the substitute's source does not parse: {exc}"
        ) from exc


def _find_function(tree: ast.AST, function_name: str) -> ast.AST:
    for node in ast.walk(tree):
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == function_name
        ):
            return node
    raise FixtureReachabilityError(
        f"{function_name!r} is not a function in this source; returning the "
        "empty set would make every stub look maximally under-declared"
    )


def _subscript_index(node: ast.Subscript) -> ast.AST:
    index = node.slice
    return getattr(index, "value", index) if isinstance(index, ast.Index) else index


def _string_constant(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _string_constants(nodes: Sequence[ast.AST]) -> set[str]:
    found = set()
    for node in nodes:
        value = _string_constant(node)
        if value is not None:
            found.add(value)
    return found


def _argv_derived_names(function: ast.AST) -> frozenset[str]:
    """Names that carry the argv, transitively, inside the substitute.

    Seeded with the parameters of the functions nested INSIDE the factory — the
    seam callable's own ``cmd`` — and not with the factory's own parameters. A
    factory parameter (``raise_on``) compared against a string constant declares
    nothing about git, which is exactly the distinction ``raise_on == "blob"``
    turns on.
    """
    derived: set[str] = set()
    for node in ast.walk(function):
        if node is function:
            continue
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            arguments = node.args
            for parameter in (
                *arguments.posonlyargs,
                *arguments.args,
                *arguments.kwonlyargs,
            ):
                derived.add(parameter.arg)
            if arguments.vararg:
                derived.add(arguments.vararg.arg)
            if arguments.kwarg:
                derived.add(arguments.kwarg.arg)

    assignments = [n for n in ast.walk(function) if isinstance(n, ast.Assign)]
    changed = True
    while changed:
        changed = False
        for assignment in assignments:
            loaded = {
                n.id
                for n in ast.walk(assignment.value)
                if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)
            }
            if not loaded & derived:
                continue
            for target in assignment.targets:
                for name in ast.walk(target):
                    if isinstance(name, ast.Name) and name.id not in derived:
                        derived.add(name.id)
                        changed = True
    return frozenset(derived)


def _dict_literals(function: ast.AST) -> Mapping[str, ast.Dict]:
    """Names bound, in this source, to a dict DISPLAY — the dispatch tables."""
    tables: dict[str, ast.Dict] = {}
    for node in ast.walk(function):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Dict):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    tables[target.id] = node.value
    return tables


def stub_gaps(
    *,
    stub_source: str,
    stub_name: str,
    issued_argv: Sequence[Sequence[str]],
    consumer: str,
) -> tuple[StubGap, ...]:
    """Every command a substitute answers without naming.

    ``issued_argv`` is the set of argvs the CONSUMER actually issues, recorded
    from a real run over a real repository with a recording seam — not guessed,
    not read off the consumer's docstring, which is the artifact that was wrong
    in instance (B). Recording it is a separate obligation of the caller and is
    the reason this function takes it rather than deriving it: an argv list
    derived from the same source the stub was written against would agree with
    the stub by construction.

    A gap is an argv whose :func:`git_subcommand` is not in
    :func:`modelled_subcommands` AND which the substitute nonetheless answers
    (does not raise). Both halves are required:

      * answered and modelled -> fine, that is a stub doing its job;
      * unmodelled and refused -> fine, that is the totality claim holding;
      * unmodelled and ANSWERED -> a gap, whatever the answer was.

    A substitute that raises on every argv in ``issued_argv`` yields no gaps
    and is a different (and louder) problem the seals for those rows will show.

    Note what this cannot say and limit 9 repeats: nothing about whether a
    MODELLED answer is one git could produce. A stub that declares ``ls-tree``
    and returns an entry with a mode git never writes is clean here.
    """
    modelled = modelled_subcommands(stub_source, stub_name)
    gaps: list[StubGap] = []
    seam: Any = None
    for raw in issued_argv:
        argv = tuple(str(token) for token in raw)
        subcommand = git_subcommand(argv)
        if subcommand is None:
            # An argv with no subcommand cannot be a modelling gap. Distinct
            # from "a subcommand I do not know", which is what a gap looks like.
            continue
        if subcommand in modelled:
            continue
        if seam is None:
            seam = _instantiate_substitute(stub_source, stub_name)
        answered, answered_as = _substitute_answers(seam, argv, stub_source)
        if not answered:
            # Unmodelled and refused: the totality claim HOLDING.
            continue
        gaps.append(
            StubGap(
                stub=stub_name,
                argv=argv,
                subcommand=subcommand,
                modelled=modelled,
                answered_as=answered_as,
                consumer=consumer,
            )
        )
    return tuple(gaps)


#: Executed substitute sources, keyed on the source text. A stub file is a whole
#: module and executing one twice buys nothing; the cache is what keeps the seam
#: face off the runtime budget.
_SUBSTITUTE_NAMESPACES: dict[str, dict] = {}
_SUBSTITUTE_FILENAMES: dict[str, str] = {}


def _substitute_filename(source: str) -> str:
    filename = _SUBSTITUTE_FILENAMES.get(source)
    if filename is None:
        filename = f"<fixture-reachability substitute {len(_SUBSTITUTE_FILENAMES)}>"
        _SUBSTITUTE_FILENAMES[source] = filename
    return filename


def _instantiate_substitute(source: str, name: str) -> Any:
    """The seam callable a substitute FACTORY returns.

    Every ``_run_stub`` in this repo is a factory: the fixture at a seam is the
    callable it returns, and that callable is what has to be interrogated. The
    factory's required parameters are filled from their annotations, because a
    factory that cannot be built at all would make every argv look refused —
    the permissive answer for this face.
    """
    namespace = _SUBSTITUTE_NAMESPACES.get(source)
    if namespace is None:
        filename = _substitute_filename(source)
        namespace = {"__name__": "_fixture_reachability_substitute", "__file__": filename}
        try:
            exec(compile(source, filename, "exec"), namespace)  # noqa: S102
        except Exception as exc:
            raise FixtureReachabilityError(
                f"the substitute's source could not be executed: "
                f"{type(exc).__name__}: {exc}"
            ) from exc
        _SUBSTITUTE_NAMESPACES[source] = namespace
    factory = namespace.get(name)
    if not callable(factory):
        raise FixtureReachabilityError(
            f"{name!r} is not a callable in this source, so no seam can be built "
            "from it"
        )
    args, kwargs = _factory_arguments(factory)
    try:
        seam = factory(*args, **kwargs)
    except Exception as exc:
        raise FixtureReachabilityError(
            f"the substitute factory {name!r} could not be called: "
            f"{type(exc).__name__}: {exc}"
        ) from exc
    if not callable(seam):
        raise FixtureReachabilityError(
            f"the substitute factory {name!r} returned {type(seam).__name__}, "
            "not a seam callable; every argv would then 'raise' and every gap "
            "would be missed"
        )
    return seam


_ANNOTATION_PLACEHOLDERS = (
    ("list", list),
    ("sequence", list),
    ("tuple", tuple),
    ("dict", dict),
    ("mapping", dict),
    ("set", set),
    ("str", str),
    ("bool", bool),
    ("int", int),
)


def _factory_arguments(factory: Any) -> tuple[list, dict]:
    args: list = []
    kwargs: dict = {}
    try:
        signature = inspect.signature(factory)
    except (TypeError, ValueError):  # pragma: no cover - builtins
        return args, kwargs
    for parameter in signature.parameters.values():
        if parameter.default is not inspect.Parameter.empty:
            continue
        if parameter.kind in (
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        ):
            continue
        placeholder = _placeholder_for(parameter.annotation)
        if parameter.kind is inspect.Parameter.KEYWORD_ONLY:
            kwargs[parameter.name] = placeholder
        else:
            args.append(placeholder)
    return args, kwargs


def _placeholder_for(annotation: Any) -> Any:
    text = str(annotation).lower()
    for marker, factory in _ANNOTATION_PLACEHOLDERS:
        if marker in text:
            return factory()
    return None


def _substitute_answers(seam: Any, argv: Sequence[str], source: str) -> tuple[bool, str]:
    """Did the seam ANSWER this argv, and which branch swallowed it?

    The call is spelled as ``repo_config._run_git`` spells it, narrowed to what
    the seam's own signature accepts — a seam refused for taking the wrong
    arguments would read as the totality claim holding, which is the permissive
    answer for this face.
    """
    kwargs = {"cwd": ".", "capture_output": True, "text": True, "timeout": 30}
    try:
        parameters = inspect.signature(seam).parameters
    except (TypeError, ValueError):  # pragma: no cover - builtins
        parameters = {}
    if not any(
        p.kind is inspect.Parameter.VAR_KEYWORD for p in parameters.values()
    ):
        kwargs = {k: v for k, v in kwargs.items() if k in parameters}

    filename = _substitute_filename(source)
    executed: list[int] = []
    tracing = sys.gettrace() is None

    def _trace(frame, event, _arg):
        if frame.f_code.co_filename != filename:
            return None

        def _local(inner, inner_event, _inner_arg):
            if inner_event == "line":
                executed.append(inner.f_lineno)
            return _local

        return _local

    try:
        if tracing:
            sys.settrace(_trace)
        try:
            seam(list(argv), **kwargs)
        finally:
            if tracing:
                sys.settrace(None)
    except BaseException:
        return False, ""
    return True, _describe_answering_branch(source, executed, argv)


def _describe_answering_branch(
    source: str, executed: Sequence[int], argv: Sequence[str]
) -> str:
    """Name the branch that swallowed the argv, so the fix is local."""
    if not executed:
        return (
            f"the substitute answered `{' '.join(argv)}` without raising; the "
            "branch could not be traced in this interpreter"
        )
    last = executed[-1]
    enclosing: ast.If | None = None
    try:
        tree = ast.parse(source)
    except SyntaxError:  # pragma: no cover - parsed already by this point
        tree = None
    if tree is not None:
        for node in ast.walk(tree):
            if not isinstance(node, ast.If):
                continue
            covered = {
                inner.lineno
                for statement in node.body
                for inner in ast.walk(statement)
                if hasattr(inner, "lineno")
            }
            if last in covered and (
                enclosing is None or node.test.lineno > enclosing.test.lineno
            ):
                enclosing = node
    if enclosing is not None:
        return (
            f"the branch `{ast.unparse(enclosing.test)}` at line "
            f"{enclosing.test.lineno}"
        )
    lines = source.splitlines()
    text = lines[last - 1].strip() if 0 < last <= len(lines) else ""
    return f"line {last}: {text}" if text else f"line {last}"


# --------------------------------------------------------------------------- #
# Part 6 — the run
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ReachabilityReport:
    """The outcome of one whole check, in the shape a caller must act on.

    ``findings``
        Every judged observation, in observation order.
    ``dispositions``
        ``FindingDisposition`` -> count. Every member of the enum is a key,
        including the zeros: a report that omits ``ABSTAIN`` because there were
        none is indistinguishable from one that omits it because nobody
        counted, and the abstention count is this mechanism's own coverage
        figure.
    ``stale_declarations``
        Declarations that matched no finding. Reported, never silent.
    ``boundaries_never_observed``
        Rows of :data:`BOUNDARIES` whose consumer was never called during the
        run. THE non-vacuity field, and the first thing a reader should look
        at: a report of zero breaches over zero observations is what this
        module exists to stop other people shipping, and it must not be able to
        ship it itself.

    ``is_clean`` is deliberately absent. A caller decides what to block on, and
    a single boolean would have to fold ABSTAIN into one side of it.
    """

    findings: tuple[Finding, ...]
    dispositions: Mapping[FindingDisposition, int]
    stale_declarations: tuple[ReachabilityDeclaration, ...]
    boundaries_never_observed: tuple[Boundary, ...]


def check_suite(
    observations: Sequence[ObservedFixture],
    *,
    workspace: Path,
    declarations: Sequence[ReachabilityDeclaration] = (),
    differential: Callable[[ObservedFixture, str], str] | None = None,
) -> ReachabilityReport:
    """Judge a whole run's observations and assemble the report.

    ``differential`` is passed straight through to :func:`check_observation`
    and nothing here interprets it. It exists on this signature because
    otherwise the parameter would be unreachable from the only entry point a
    caller has, and because the ruling it carries has to be visible to whoever
    wires this module up: with ``None`` — which is what a caller holding only
    an observation list can honestly supply — **every DIVERGED finding in the
    report is an ABSTAIN, and no run of this function can ever produce
    OPPOSITE_DISPOSITION.** BREACH then arrives only from :func:`stub_gaps`.
    That is the state of the module today and it is limit 12.

    Obligations a body must meet, each of which a seal can pin:

      * **Dedupe before constructing.** One witness per distinct
        ``(boundary.producer, value)``, reused across every observation of it.
        Over a suite of this size the distinct set is small and the repeated
        set is not; without this the check costs a repository per row.
      * **Never mutate the repository under check.** Every witness lives under
        ``workspace``, which must be outside it.
      * **Judge every observation**, including those whose boundary kind sends
        them to another face. An observation with no finding is a silent pass.
      * **Count boundaries never observed** and put them in the report even
        when there are no findings at all.
      * **Let :class:`FixtureReachabilityError` propagate.** A partial report is
        not a report; a caller that receives one cannot tell a clean run from
        an aborted one.

    Order is observation order throughout, so two runs over the same suite
    produce byte-identical reports and a diff between them is a real change.
    """
    rows = list(observations)
    root = Path(workspace)
    root.mkdir(parents=True, exist_ok=True)

    # Dedupe before constructing. One witness per distinct
    # (producer, value) — the same value at a DIFFERENT producer is a different
    # pair, because two producers can emit different things for one repository.
    # Built on first need rather than all up front, so a run that aborts on a
    # stale table has not already paid for the witnesses it will never judge.
    witnesses: dict[tuple[str, str], Witness] = {}

    def _witness_for(observed: ObservedFixture) -> Any:
        # The same check check_observation makes first, made here too so a stale
        # table aborts the run before a repository is built for a row whose
        # outcome the mechanism cannot classify.
        gate_disposition(observed.boundary, observed.outcome)
        if len(tuple(observed.cut_boundaries)) > 1:
            return _NO_WITNESS
        key = (observed.boundary.producer, observed.value)
        if key not in witnesses:
            witnesses[key] = construct_witness(
                observed.boundary, observed.value, workspace=root
            )
        return witnesses[key]

    findings = tuple(
        _check_observation(
            observed,
            workspace=root,
            differential=differential,
            witness=_witness_for(observed),
        )
        for observed in rows
    )

    # Every member of FindingDisposition is a key, INCLUDING the zeros: a report
    # that omits ABSTAIN because there were none is indistinguishable from one
    # that omits it because nobody counted.
    dispositions = {disposition: 0 for disposition in FindingDisposition}
    matched: set[int] = set()
    declared = list(declarations)
    for finding in findings:
        declaration = None
        for index, candidate in enumerate(declared):
            if _declaration_matches(candidate, finding):
                declaration = candidate
                matched.add(index)
                break
        dispositions[adjudicate(finding, declaration)] += 1

    observed_boundaries = {observed.boundary for observed in rows}
    return ReachabilityReport(
        findings=findings,
        dispositions=dispositions,
        stale_declarations=tuple(
            declaration
            for index, declaration in enumerate(declared)
            if index not in matched
        ),
        boundaries_never_observed=tuple(
            boundary for boundary in BOUNDARIES if boundary not in observed_boundaries
        ),
    )
