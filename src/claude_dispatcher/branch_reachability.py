"""Unit D7 — the diff-time face of D5/D6 call-site reachability.

**P1 SCAFFOLD. Contract and stubs.** The decision logic in
:func:`check_branch_reachability`, :func:`materialise_base_tree` and
:func:`declarations_at` is a body author's; everything that is *implemented*
here is implemented deliberately and each site says why.

Why this module exists
======================
:func:`~claude_dispatcher.call_site_reachability.check_tree` is built,
adjudicated five times, floored (``FLOOR_GLOBS`` entries five, six, seven and
eight) and enrolled (``ANALYZERS`` holds
:data:`~claude_dispatcher.go_reachability.GO_REACHABILITY_ANALYZER`) — and it
**has no caller outside** ``tests/``. The mechanism commissioned to catch code
that is built and never called is itself built and never called. Closing that
is this unit.

*Measured under* ``2e0dc89`` (``feat/D6-enrol2``), ``grep -rn "check_tree"``
over ``src/`` and ``scripts/``: every hit is inside
``call_site_reachability.py`` itself. The only callers are
``tests/test_call_site_reachability.py``, ``tests/test_go_reachability.py`` and
``tests/test_d5_floor.py``.

THE CONSTRAINT THAT DECIDES WHETHER THIS GATE SURVIVES
======================================================
**:func:`check_tree` judges a TREE. A gate must judge a DIFF.**

If a ``BREACH`` anywhere in the tree failed the branch, then pre-existing dark
code would fail *every* branch from day one, and a permanently red gate trains
everyone to reach for the waiver reflexively. That is not a hypothetical here.

*Measured under* ``2e0dc89``, ``check_tree`` over
``tests/fixtures/d6_g2_preserve`` staged the way its seals stage it
(``go.mod.recorded`` → ``go.mod``), **with no edit of any kind**::

    seals 30   findings 48   roots 34 (production 4)
    ok 27   breach 12   report 0   accepted 0   abstain 9

**Twelve BREACHes on an unmodified vendored tree.** A whole-tree gate is red on
that tree on its first commit, for every branch, forever, with nobody having
done anything wrong. The question this contract has to answer is therefore not
"is there dark code" but **"what did the BRANCH do".**

THE RULING: DELTA. And the two alternatives, priced and refused
---------------------------------------------------------------
All three candidate readings were priced against the primary target,
``evenplay-mono/apps/website-public-api`` @ ``51a71736c`` (13 Go packages, 52
``.go`` files), and against the acceptance fixture.

*Measured under* ``2e0dc89``, this host (go1.24.4), ``subprocess.run`` spied,
three repetitions::

    reading    what it runs                       primary target      acceptance
    delta      base sweep + head sweep            15.4 s / 52 execs   2.81 s / 10
    scoped     head sweep only                     7.6 s / 26 execs   1.30 s /  4
    baseline   head sweep only + a recorded set    7.6 s / 26 execs   1.30 s /  4

    materialising the base tree, primary target, 3 reps:
      git worktree add --detach          0.74 / 0.76 / 0.76 s   (275 MB)
      git archive <subtree> | tar -x     0.01 / 0.01 / 0.01 s   (472 KB)

    the base half of a delta, run on the archived base rather than in place:
      7.83 s / 28 execs, then 7.69 s / 26  — indistinguishable from in-place,
      so materialisation does not make the second sweep more expensive, it
      only adds its own 0.01 s.

**Delta's true price on the primary target is 15.4 s and one 472 KB extraction,
against 7.6 s for the other two.** That is the honest number and it is the one
to argue with. It is also — stated plainly, because the cost argument is the
one that gets this gate switched off — *eight seconds on a PR gate*. What
switches a gate off is not eight seconds; it is twelve red findings on a tree
nobody touched. Delta buys exactly that and costs exactly that.

**SCOPED IS REFUSED, and not on cost — on soundness.** "Fail only on findings
whose subject or seal the diff touched" is blind to the canonical defect, and
this is measured rather than reasoned:

*Measured under* ``2e0dc89``, acceptance fixture, one edit that touches
**only** ``cmd/iterate/main.go`` — the single production call site of
``ApplyRoundRecord`` at line 498 replaced by a local pass-through, so the tree
still compiles::

    BASE  seals 30  findings 48   ok 27  breach 12  abstain 9
    HEAD  seals 30  findings 48   ok 17  breach 22  abstain 9
    INTRODUCED: 10

and **every one of the 10 introduced findings has its subject in
``cmd/iterate/preserve.go``** and its seal in
``cmd/iterate/preserve_seal_test.go`` — two files the diff does not touch. A
scoped gate reports **0 of 10**. This is ``ResolveConfigDual`` exactly:
implemented, sealed green, called by nothing, and made dark by an edit
somewhere else. Scoping by "touched" cannot see it, because the last call site
is by definition in a third file. Any repair — "also scope by what the base run
said reached the subject" — needs the base run, and a scoped gate with a base
run is a delta gate that reports less.

(The one thing scoped gets right and is worth recording: "touched" would in
fact be rename-proof here, because :func:`~claude_dispatcher.role_protocol.
changed_paths_between` runs with rename detection **off** by contract, so a
move shows as delete-old + add-new and the moved path is in the diff either
way. The rename objection is answered; the soundness one is not.)

**BASELINE IS REFUSED.** A recorded BREACH set is the cheapest reading and it
rots, and this codebase has *measured* a recorded expectation going vacuous —
see :class:`~claude_dispatcher.call_site_reachability.StagedDeclaration`'s
stale-declaration reporting and the ``_DELEGATION_TARGETS`` stale-row seal it
cites. A baseline additionally has no natural author: whoever records it is the
party the gate judges, which is the honour system that produced 24 vacuous
seals — the sentence ``scripts/check_body_branch.sh`` opens with.

WHAT DELTA COSTS THAT IS NOT SECONDS, and the guard it forces
-------------------------------------------------------------
Delta has its own evasion and it is worse than the cost. *Measured under*
``2e0dc89``, the same fixture, the same one-file edit, but written so the
package **no longer compiles** (``var data []byte`` with ``data`` unused)::

    BASE  seals 30  findings 48  unanalyzed 2   ok 27  breach 12  abstain 9
    HEAD  seals 12  findings 19  unanalyzed 2   ok 10  breach  0  abstain 9
    INTRODUCED: 0

**Break the build and the delta is empty.** Note which non-vacuity field
catches it: ``seals_examined`` (30 → 12) and ``findings`` (48 → 19).
``unanalyzed_paths`` is 2 in both and sees nothing. So the delta reading is
only honest with a vacuity guard on the pair of reports, which is
:func:`sweep_is_vacuous` and which is implemented here rather than stubbed.

THE RULING, DRIVEN END TO END
-----------------------------
The implemented half of this module — :func:`introduced_findings`,
:func:`sweep_is_vacuous`, :func:`verdict_of` and the tables — driven against
the SHIPPED :func:`check_tree` on real trees, no monkeypatch, no hand-built
report, ``role`` = BODIES. *Measured under* ``2e0dc89``::

    A  acceptance tree, NO edit          introduced 0   VERDICT clean
       (the tree that carries 12 standing BREACHes)
    B  one compiling edit, cmd/iterate/main.go ONLY
                                         introduced 10  VERDICT violation
       every introduced subject in cmd/iterate/preserve.go — a file the
       diff does not touch, which is what a scoped gate cannot see
    C  the same edit written so the tree stops compiling
                                         introduced 0   VERDICT undetermined
       "head examined 12 seal(s) and base examined 30"

A is the permanently-red failure NOT happening. B is the canonical defect being
caught by a gate a scoped reading would have cleared. C is delta's own evasion
being refused rather than passed. Those three lines are the unit.

The appeal and the role table, driven the same way over case B::

    D  all 10 declared, wiring "SMG-9999 wires it next sprint"
                                         introduced 0   VERDICT clean
       all 10 declared, wiring "   "     introduced 10  VERDICT violation
       — R8's ratification condition holding through this layer, because the
         match is `_declaration_answers` and not a local re-spelling of it
    E  the same 10 introduced findings, by role:
         scaffold  not_run   clean      adjudicate  advisory  clean
         seals     not_run   clean      legacy      not_run   clean
         bodies    blocking  VIOLATION

WHOSE GATE IS IT
================
The signature gate is BODIES'. Reachability is not obviously anyone's: the
canonical defect passed P1, P2, P3 and P4 untouched. The rule that decides it
is stated in this unit's own terms and is the one this contract commits to:
**a role that cannot FIX a BREACH must not be BLOCKED by one.**

  * **P1 SCAFFOLD — NOT_RUN.** The scaffold-first protocol *manufactures* this
    state: a P1 scaffold is by construction a set of symbols with seals and no
    call sites (the ratified argument on
    :class:`~claude_dispatcher.call_site_reachability.StagedDeclaration`). P1
    cannot add a call site — wiring is a body edit — so P1 can neither fix nor
    avoid what it would be blocked by. Paying 15 s to print a report that is
    guaranteed noisy is the expensive-gate failure with none of the benefit.
  * **P2 SEALS — NOT_RUN.** D5 judges *the subjects of seals*, so P2 creates
    the findings; but at P2 time the bodies do not exist, and P2 may not touch
    the implementation. Same test, same answer.
  * **P3 BODIES — BLOCKING. This is the gate.** It is the only role that can
    fix a BREACH with an edit it is permitted to make: add the call site, in
    production source. It is also the role whose phase *ends* the manufactured
    dark state — P1 manufactures it and P3 is when it is supposed to stop being
    true. Copying the signature precedent verbatim keeps one sentence for two
    mechanisms: *on the one role whose gate it is, an unchecked X is not a
    pass.*
  * **P4 ADJUDICATE — ADVISORY.** It runs and every finding is reported; it
    cannot move the verdict. P4's writable set is the task's
    ``disputed_paths:``, so P4 usually cannot add a call site either and the
    rule above forbids blocking it. But P4 is the role that RULES on a
    :class:`~claude_dispatcher.call_site_reachability.StagedDeclaration`, and
    a reviewer asked to ratify a debt figure must be shown it. Advisory is what
    "shown, not blocked" spells.
  * **LEGACY — NOT_RUN.** A pre-protocol row has no immutable paths and this
    module must not become a new gate on legacy work — the sentence
    ``role_protocol`` already writes for LEGACY, with the floor as its single
    stated exception. Reachability is not a second exception.

CHOICE (rejected: run it ADVISORY for all five roles, so nothing is invisible).
Refused on the measured price: 15.4 s on every scaffold and seals branch to
print a report that is noisy *by construction* on exactly those branches is how
a gate earns its reputation before it has caught anything. The states are NAMED
instead — :attr:`ReachabilitySweepStatus.NOT_THIS_ROLES_GATE` is on the verdict
line, so "this gate did not ask about your branch" is never mistaken for "this
gate cleared your branch".

CHOICE (rejected: make it P4's gate, on the reasoning that P4 is the last
station before the unit is done). Refused because it inverts the rule: P4 would
be blocked for P3's defect with no edit available to fix it, and the fix P4
*does* have — writing a declaration — is precisely the rubber stamp the appeal
was designed to make expensive. A gate whose only escape is its own annotation
is a gate that produces annotations.

WHAT THIS MODULE DOES NOT DO
============================
It does not weaken :func:`check_tree` by one line. Every question this gate
asks is asked *of the report*, after the fact: the mechanism keeps answering
"what is dark in this tree" and this module answers "what did this branch make
dark", which is a different question asked of the same honest answer.

ESCALATIONS — production changes this design needs that P1 did not make
=======================================================================
Each is left undone on purpose; see the report accompanying this commit.

  1. **``role_protocol.check_branch`` must call
     :func:`check_branch_reachability`** (the step 6 its docstring now names),
     and ``role_protocol.py`` is on ``FLOOR_GLOBS``. Every diff-time surface is:
     the floor holds "the machinery that … computes the verdict" by
     construction, so wiring a new question into the verdict is *necessarily* a
     floored edit. D5's and D6's enrolment commits set the precedent — they are
     P4 rulings on floored files, ratified as plan amendments.
  2. **This module must join ``FLOOR_GLOBS``, and
     ``tests/test_floor_closure.py::_DELEGATION_TARGETS`` must gain a row, in
     the SAME edit as (1).** Not a prediction — *measured under* ``2e0dc89`` by
     inserting one function-local ``from . import blast_radius`` into
     ``check_branch`` in a throwaway copy: ``tests/test_floor_closure.py``
     goes ``2 failed, 82 passed``, on
     ``test_every_module_in_the_derived_closure_is_on_the_floor`` ("floor them,
     or take them off the gate path: blast_radius (imported by
     role_protocol.check_branch())") and
     ``test_the_delegation_closure_is_exactly_the_written_out_table``. The
     closure walk follows function-local imports out of the floor-decision
     roots, so there is no import spelling that avoids this.
     **Consequence: the wiring commit touches both ``FLOOR_GLOBS`` and a SEAL
     file, so it is not a P3 edit — bodies may not touch ``tests/``.** D7's
     wiring is a P4/operator amendment or it is a role violation. This is the
     escalation that matters most.
  3. **:data:`DECLARATION_PATH` must be denied to BODIES** in
     ``role_protocol.DEFAULT_ROLE_RULES``, so that the appeal is written by the
     reviewer and not by the party being judged. That is an edit to a floored
     module's rule table and it is left for the ruling that takes (1).
  4. **``role_protocol._print_report`` must print the reachability block.** A
     verdict a caller cannot read the reason for is the vacuous half of this
     gate. Left with (1), same file, same reason.

Every figure above is stamped. Nothing here is inherited.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable, Mapping, Sequence

from .call_site_contract import RootKind
from .call_site_reachability import (
    Disposition,
    ReachabilityReport,
    StagedDeclaration,
    UndecidedReason,
    _declaration_answers,
    adjudicate,
    analyzer_for_path,
)

# CHOICE (rejected: re-spell the declaration match here, both keys, rather than
# import a private name from a sibling). Refused, and the first draft of
# :func:`dispositions_by_key` made exactly that mistake and lost R8's
# ratification condition in the process — it matched on the two keys and did
# not check that ``wiring`` says something, so a declaration ``check_tree``
# ignores would have been honoured HERE and the two halves of one gate would
# have disagreed about what an appeal is. `_declaration_answers` is the ONE
# place that answers "does this declaration answer this finding"; importing it
# under its private name is a smaller sin than owning a second copy, and it is
# the same call `FLOOR_GLOBS` makes about glob semantics living once in
# `risk.py`. If a body wants it public, that is a rename in a floored module
# and belongs with the wiring escalation, not here.
from .role_protocol import DiffVerdict, Role


class BranchReachabilityError(RuntimeError):
    """A question this module cannot answer without guessing.

    Deliberately distinct from
    :class:`~claude_dispatcher.call_site_reachability.CallSiteReachabilityError`
    (a fact about the MECHANISM or the machine) and from
    :class:`~claude_dispatcher.role_protocol.RoleProtocolError` (a fact about
    the POLICY). This one is a fact about the WIRING: an unmapped
    :class:`~claude_dispatcher.call_site_reachability.Disposition`, an unmapped
    :class:`~claude_dispatcher.role_protocol.Role`, an unmapped
    :class:`ReachabilitySweepStatus`.

    It is raised and never returned as a verdict, on this module's own doctrine
    and on ``role_protocol``'s: an enum member nobody handled must not fall
    through to the permissive branch. :func:`check_branch` catches everything
    and turns it into UNDETERMINED, so raising here costs a caller a refusal
    and never a traceback — see that function's "this function never raises".
    """


# --------------------------------------------------------------------------- #
# Whose gate it is
# --------------------------------------------------------------------------- #


class ReachabilityObligation(Enum):
    """What this gate is to one role. Three states, exhaustively.

    BLOCKING
        The sweep runs and its answer can move the verdict — to VIOLATION for
        an introduced BREACH, to UNDETERMINED for a sweep that could not
        answer. Exactly one role, for the reason the module docstring gives.
    ADVISORY
        The sweep runs, every finding is reported, and the verdict is not
        touched. Not a weaker BLOCKING: it is "shown, not blocked", which is
        what a role that cannot fix a BREACH is owed.
    NOT_RUN
        The sweep does not run at all. **Not a pass**: the status
        :attr:`ReachabilitySweepStatus.NOT_THIS_ROLES_GATE` is on the verdict
        line, in the same place and for the same reason the signature gate
        names its skipped paths there.
    """

    BLOCKING = "blocking"
    ADVISORY = "advisory"
    NOT_RUN = "not_run"


#: **Role → obligation, as DATA.** Five rows and every :class:`Role` member is
#: one, because a role whose obligation has to be inferred is a role somebody
#: will infer wrongly — the sentence ``role_protocol``'s signature dispatch
#: writes about itself, applied to a second gate.
#:
#: A table and not a chain of ``if``\ s for :func:`adjudicate`'s recorded
#: reason: a chain grows a default branch, and a default branch on this
#: dispatch is how the permissive answer gets a new spelling. A new
#: :class:`Role` member lands in :func:`obligation_for_role`'s raise, never in
#: a silent NOT_RUN.
_ROLE_OBLIGATIONS: Mapping[Role, ReachabilityObligation] = {
    Role.BODIES: ReachabilityObligation.BLOCKING,
    Role.ADJUDICATE: ReachabilityObligation.ADVISORY,
    Role.SCAFFOLD: ReachabilityObligation.NOT_RUN,
    Role.SEALS: ReachabilityObligation.NOT_RUN,
    Role.LEGACY: ReachabilityObligation.NOT_RUN,
}


def obligation_for_role(role: Role) -> ReachabilityObligation:
    """This gate's obligation to ``role``. Total over :class:`Role`, raising.

    **IMPLEMENTED, not stubbed**, under the standing exception. This dispatch
    and its raise ARE the property a seal author would otherwise be sealing a
    stub of: "every Role is mapped, and an unmapped one raises" is not
    checkable against a function that raises for everything. D5's precedent —
    ``Diverge`` and the validating dispatches — is the same call.
    """
    try:
        return _ROLE_OBLIGATIONS[role]
    except KeyError:
        raise BranchReachabilityError(
            f"no reachability obligation is defined for role {role!r}; a new "
            "Role member must be handled everywhere it is dispatched, not "
            "fall through to the permissive branch"
        ) from None


# --------------------------------------------------------------------------- #
# When the sweep does not run, or ran and could not answer
# --------------------------------------------------------------------------- #


class ReachabilitySweepStatus(Enum):
    """Whether the two sweeps happened, and what stopped them. Nine states.

    Every one is NAMED and none may read as a pass. That requirement is not
    this unit's invention: it is what ``role_protocol`` bought its two CLEAN
    signature rows with, and a status that confesses nothing is that ruling
    misapplied.

    CHECKED
        Both sweeps ran, both reports are whole, and :attr:`
        BranchReachability.introduced` is authoritative.
    NOT_THIS_ROLES_GATE
        :attr:`ReachabilityObligation.NOT_RUN`. The gate did not ask about this
        branch. It did not clear it either.
    NO_ANALYZABLE_FILE_IN_DIFF
        Not one changed path has an :data:`~claude_dispatcher.
        call_site_reachability.ANALYZERS` row — measured through
        :func:`~claude_dispatcher.call_site_reachability.analyzer_for_path`,
        the one place that answers it, so this module owns no second extension
        table. **This is the cheap exit and it is SOUND**: a branch that
        changed no file any analyzer can read changed no call edge in any
        language this gate can see. It is the direct analogue of
        ``UNCHECKED_NO_SUPPORTED_FILE``, and like it, nothing the branch can
        commit will clear it — which is exactly why it does not refuse.

        *Measured under* ``2e0dc89``: on this repository's own tree
        ``check_tree`` reports ``unanalyzed_paths`` 386 and 3 production roots,
        all from the two vendored Go helper subtrees, so a Python-only branch
        here takes this exit and pays nothing.
    NOT_REACHED_ALREADY_VIOLATION
        The cheap checks already refused the branch. See "the cost's placement"
        on :func:`check_branch_reachability`.
    NO_SEAL_IN_TREE
        Both sweeps ran and ``seals_examined`` is 0 on both. D5 judges the
        subjects of SEALS, so a tree with no seal yields no finding and this
        gate has nothing to say about it. **CLEAN, and loud**: nothing the
        branch commits changes it, which is the discriminator ``role_protocol``
        already ruled with. *Measured under* ``2e0dc89``: the primary target is
        exactly this — 0 seals, 0 findings, 7.6 s spent to learn it.
    UNCHECKED_HEAD_NOT_CHECKED_OUT
        ``repo_root``'s HEAD is not ``branch_ref``, so there is no head TREE to
        sweep. See :func:`check_branch_reachability` — this is the gap between
        a gate that reads blobs and a mechanism that reads a directory.
    UNCHECKED_BASE_UNAVAILABLE
        The base tree could not be materialised. **Never "then everything is
        new"** and never "then nothing is": a delta with one side missing is
        not a delta, and both of the tempting defaults are a verdict about a
        revision nobody read.
    UNCHECKED_ANALYZER_FAULT
        :func:`check_tree` RAISED. Since D6 enrolment it does: a tree holding
        at least one ``.go`` file on a host with no usable ``go`` raises
        ``TOOLCHAIN_MISSING`` out of ``discover_roots``, where before enrolment
        it returned a silent empty report. That change is recorded as the price
        of enrolment and this is the state that pays it.
    UNCHECKED_SWEEP_VACUOUS
        Both sweeps ran and the pair does not support a delta —
        :func:`sweep_is_vacuous` says which. The measured shape is the
        broken-build evasion in the module docstring.
    """

    CHECKED = "checked"
    NOT_THIS_ROLES_GATE = "not_this_roles_gate"
    NO_ANALYZABLE_FILE_IN_DIFF = "no_analyzable_file_in_diff"
    NOT_REACHED_ALREADY_VIOLATION = "not_reached_already_violation"
    NO_SEAL_IN_TREE = "no_seal_in_tree"
    UNCHECKED_HEAD_NOT_CHECKED_OUT = "unchecked_head_not_checked_out"
    UNCHECKED_BASE_UNAVAILABLE = "unchecked_base_unavailable"
    UNCHECKED_ANALYZER_FAULT = "unchecked_analyzer_fault"
    UNCHECKED_SWEEP_VACUOUS = "unchecked_sweep_vacuous"


#: The sweep statuses that REFUSE a branch on the role whose gate this is.
#: Deliberately the same mechanism, the same shape and the same sentence as
#: :data:`~claude_dispatcher.role_protocol._BODIES_BLOCKING_SIGNATURE_STATUSES`
#: — *a check that started and could not finish, on the role whose gate that is,
#: is not a pass* — so a reader who has understood one gate has understood two.
#:
#: The four that are here all name something an author or an operator can act
#: on and that re-running clears: check the branch out, fix the checkout, put a
#: usable ``go`` on the image, fix the tree. Neither is terminal.
#:
#: The five that are NOT here are the specification, and each is here-omitted
#: for the SAME discriminator ``role_protocol`` ruled with on 2026-08-09:
#: **nothing the branch could commit would clear them.** ``CHECKED`` is not a
#: refusal because the findings decide; ``NOT_THIS_ROLES_GATE`` because the
#: role cannot fix what it would be refused for; ``NO_ANALYZABLE_FILE_IN_DIFF``
#: and ``NO_SEAL_IN_TREE`` because they are permanent facts about the tree and
#: the gate rather than about the branch; ``NOT_REACHED_ALREADY_VIOLATION``
#: because the branch is being refused anyway and a second reason changes
#: nothing except the bill.
_BLOCKING_SWEEP_STATUSES: frozenset[ReachabilitySweepStatus] = frozenset(
    {
        ReachabilitySweepStatus.UNCHECKED_HEAD_NOT_CHECKED_OUT,
        ReachabilitySweepStatus.UNCHECKED_BASE_UNAVAILABLE,
        ReachabilitySweepStatus.UNCHECKED_ANALYZER_FAULT,
        ReachabilitySweepStatus.UNCHECKED_SWEEP_VACUOUS,
    }
)


# --------------------------------------------------------------------------- #
# The verdict mapping. Five dispositions, three verdicts, exhaustive
# --------------------------------------------------------------------------- #

#: **Disposition → the verdict an INTRODUCED finding contributes, as DATA.**
#: All five members, and :func:`verdict_for_disposition` raises on a sixth.
#: ``role_protocol`` calls that raise "this module's own doctrine" and records
#: that it has caught real defects twice; ``_RULINGS`` in
#: ``call_site_reachability`` is the same table one level down. This is the
#: third instance and it is written the same way on purpose.
#:
#: Read every row as *"the branch introduced this, on the role whose gate this
#: is"*:
#:
#:   OK        the branch introduced a subject production reaches over a
#:             resolved path. That is the mechanism agreeing with the branch.
#:   REPORT    an over-approximated path. **CLEAN, deliberately.**
#:             :class:`Disposition`'s own words: a human cannot declare an
#:             over-approximated path into a resolved one *because the weakness
#:             is in the analysis and not in the code*. Refusing a branch for
#:             the analyser's limitation is refusing it for something it cannot
#:             fix, which is this unit's whole test. It is COUNTED and PRINTED,
#:             never folded into OK — the distinction is the entire reason
#:             ``PathQuality`` exists as a separate axis.
#:   ACCEPTED  a BREACH with a matching declaration whose ``wiring`` says
#:             something. CLEAN, and counted apart from OK on the verdict line,
#:             because a growing ACCEPTED count is a debt figure and must be
#:             legible as one.
#:   BREACH    **VIOLATION.** The B1 defect, introduced by this branch. The one
#:             cell that refuses.
#:   ABSTAIN   UNDETERMINED — *and then narrowed*, by
#:             :data:`_BLOCKING_UNDECIDED_REASONS`, which is where the real
#:             ruling is. This cell is the pessimistic default; the frozenset
#:             is the evidence. See :func:`verdict_for_abstention`.
#:
#: CHOICE (rejected: map ABSTAIN straight to CLEAN and be done). That is the
#: quietly-wrong trade ``role_protocol``'s 2026-08-09 ruling was careful NOT to
#: make, and :class:`Disposition` forbids it in as many words — *a report that
#: folds abstentions into passes is a coverage number that lies, and this repo
#: has already paid for one of those.*
_DISPOSITION_VERDICTS: Mapping[Disposition, DiffVerdict] = {
    Disposition.OK: DiffVerdict.CLEAN,
    Disposition.REPORT: DiffVerdict.CLEAN,
    Disposition.ACCEPTED: DiffVerdict.CLEAN,
    Disposition.BREACH: DiffVerdict.VIOLATION,
    Disposition.ABSTAIN: DiffVerdict.UNDETERMINED,
}


#: The :class:`UndecidedReason` members that actually refuse a branch, on the
#: role whose gate this is. **This is the answer to "does the signature gate's
#: abstention precedent transfer".** It transfers as a TEST, not as a verdict.
#:
#: The test ``role_protocol`` ruled with on 2026-08-09, in its own words:
#: ``UNCHECKED_COMPARATOR_UNAVAILABLE`` refuses because *"a toolchain that
#: could not run is not a language nobody can read: the first is an environment
#: fault somebody can fix and the second is a permanent fact about this gate"*.
#: Applied here, member by member:
#:
#:   PARSE_FAILED          REFUSES. The gate opened a production file and the
#:                         file is bad. A BODIES branch can fix exactly that,
#:                         with an edit it is permitted to make.
#:   NO_ENTRYPOINT         REFUSES. Zero production roots. This is the
#:                         catastrophic shape ``ReachabilityReport.roots``
#:                         exists to expose — *"an empty production root set
#:                         makes every subject FROM_TESTS_ONLY … or a
#:                         repository-wide silent abstention. Both are
#:                         catastrophic and both are invisible without this
#:                         field."* Caught twice on purpose, here and in
#:                         :func:`sweep_is_vacuous`, because a vacuity guard
#:                         with one reader is a vacuity guard somebody deletes.
#:   UNSUPPORTED_LANGUAGE  does NOT refuse. Its own docstring: *"a permanent
#:                         fact about the gate, not about the machine"*. The
#:                         exact analogue of ``UNCHECKED_UNSUPPORTED_LANGUAGE``,
#:                         which does not refuse either.
#:   DYNAMIC_EDGE          does NOT refuse, and this is the load-bearing one.
#:                         *Measured under* ``2e0dc89`` on the acceptance tree:
#:                         **9 of 48 findings abstain, all DYNAMIC_EDGE, and
#:                         all correct** — both remaining holes are
#:                         ``context.CancelFunc`` values in the subject's own
#:                         package. Refusing it would make that tree
#:                         UNDETERMINED on every branch forever, which is the
#:                         permanently-red failure this unit exists to avoid,
#:                         arriving through the abstention door instead of the
#:                         BREACH door.
#:   SUBJECT_UNIDENTIFIED  does NOT refuse. The seal names something the
#:                         analyzer could not read; the only fix is to rewrite
#:                         the SEAL, and BODIES may not touch ``tests/``.
#:                         Nothing the blocking role can commit clears it.
#:
#: **Abstentions are NOT subject to the delta**, and this is a deliberate
#: asymmetry with BREACH. A BREACH is a claim about the branch's code, so "did
#: the branch introduce it" is the right question. An abstention is a claim
#: about THIS RUN's ability to answer, and a run that cannot answer cannot
#: answer any better for having been unable to answer last time either.
#: Rejected alternative: delta the abstentions too, so a pre-existing
#: PARSE_FAILED stops refusing. That converts "I could not check" into "I
#: checked and it was fine as long as it was already broken", which is the
#: vacuous-seal shape under a new name.
_BLOCKING_UNDECIDED_REASONS: frozenset[UndecidedReason] = frozenset(
    {
        UndecidedReason.PARSE_FAILED,
        UndecidedReason.NO_ENTRYPOINT,
    }
)


def verdict_for_disposition(disposition: Disposition) -> DiffVerdict:
    """One introduced finding's verdict contribution. Total, raising.

    **IMPLEMENTED, not stubbed**, under the standing exception, and for the
    reason D5 implemented its validating dispatches: "exhaustive over
    Disposition, and an unmapped member raises" is the property a seal author
    would otherwise have to seal a stub of, and a stub that raises for
    everything satisfies the raise half vacuously.
    """
    try:
        return _DISPOSITION_VERDICTS[disposition]
    except KeyError:
        raise BranchReachabilityError(
            f"disposition {disposition!r} has no verdict here; a Disposition "
            "member added without updating this table would otherwise be "
            "judged by whichever branch happened to be last, and the "
            "permissive one is always last"
        ) from None


def verdict_for_abstention(reason: UndecidedReason | None) -> DiffVerdict:
    """An abstention's verdict contribution, narrowed by its reason.

    ``None`` is a :class:`BranchReachabilityError`: a finding whose
    ``reach`` is UNDECIDED carries a ``reason`` by ``Finding``'s own
    constructor invariant, so ``None`` here means the record arrived from
    somewhere that does not validate, and guessing which side of
    :data:`_BLOCKING_UNDECIDED_REASONS` it falls on is exactly the guess this
    module refuses.

    **IMPLEMENTED**, same reason as :func:`verdict_for_disposition`: the
    membership test IS the ruling.
    """
    if reason is None:
        raise BranchReachabilityError(
            "an abstention arrived with no UndecidedReason; Finding's own "
            "invariant says a finding whose reach is UNDECIDED carries one, "
            "so this record was not validated and the gate will not pick a "
            "side of the blocking set for it"
        )
    if reason not in UndecidedReason:
        raise BranchReachabilityError(
            f"{reason!r} is not an UndecidedReason; every dispatch over that "
            "enum must be exhaustive and RAISE on an unknown member, which is "
            "that enum's own instruction"
        )
    return (
        DiffVerdict.UNDETERMINED
        if reason in _BLOCKING_UNDECIDED_REASONS
        else DiffVerdict.CLEAN
    )


def verdict_for_status(status: ReachabilitySweepStatus) -> DiffVerdict:
    """A sweep status's verdict contribution, on the BLOCKING role. Total.

    CLEAN here means "this gate does not refuse", never "this gate approves" —
    the distinction the status name on the verdict line carries.

    **IMPLEMENTED**, same reason as the two above.
    """
    if status not in ReachabilitySweepStatus:
        raise BranchReachabilityError(
            f"{status!r} is not a ReachabilitySweepStatus; a new member must "
            "be ruled into or out of _BLOCKING_SWEEP_STATUSES explicitly, "
            "because falling through here is a new spelling of the permissive "
            "answer"
        )
    return (
        DiffVerdict.UNDETERMINED
        if status in _BLOCKING_SWEEP_STATUSES
        else DiffVerdict.CLEAN
    )


#: Verdict precedence when this gate's contribution is unioned with the path
#: and signature verdicts in ``check_branch``. VIOLATION dominates UNDETERMINED
#: dominates CLEAN — the order ``check_branch``'s existing block already
#: applies (violations first, then the BODIES signature arm, then CLEAN),
#: written out here so P3 unions rather than re-decides.
_VERDICT_PRECEDENCE: tuple[DiffVerdict, ...] = (
    DiffVerdict.VIOLATION,
    DiffVerdict.UNDETERMINED,
    DiffVerdict.CLEAN,
)


def worst_verdict(verdicts: Sequence[DiffVerdict]) -> DiffVerdict:
    """The dominant verdict of ``verdicts``; CLEAN for an empty sequence.

    **IMPLEMENTED**, and "worst, not first", for the reason ``check_branch``
    already records about its signature aggregate: first-wins would clear a
    branch whenever the harmless answer happened to sort ahead of the real one.
    """
    for candidate in _VERDICT_PRECEDENCE:
        if candidate in verdicts:
            return candidate
    unknown = [v for v in verdicts if v not in _VERDICT_PRECEDENCE]
    if unknown:
        raise BranchReachabilityError(
            f"verdict(s) {unknown!r} have no place in the precedence order; a "
            "new DiffVerdict member must be ranked, not defaulted"
        )
    return DiffVerdict.CLEAN


# --------------------------------------------------------------------------- #
# The delta, and the vacuity guard it forces
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class IntroducedFinding:
    """One finding the BRANCH introduced, in the shape a report must print.

    A local record rather than
    :class:`~claude_dispatcher.call_site_reachability.Finding` because what a
    verdict line needs is five strings, and because ``RoleDiffResult`` is
    printed by a function in a floored module that must not have to learn D5's
    whole vocabulary to do it. ``subject_path`` and ``subject_line`` are
    carried so the message names a place a human can open — the gap the D6
    enrolment note records ("all 9 abstentions name the COUNT and the FIRST
    hole only") is about the mechanism's detail string and is not repeated
    here.

    ``was`` is the disposition the SAME key had at base, or ``None`` when the
    key is new at head. It is the difference between "this branch made this
    dark" and "this branch removed the declaration that was covering it", and a
    report that cannot tell those apart sends the author to the wrong file.
    """

    test_id: str
    subject_key: str
    subject_path: str
    subject_line: int
    disposition: Disposition
    was: Disposition | None
    reason: UndecidedReason | None
    detail: str


def dispositions_by_key(
    report: ReachabilityReport,
    declarations: Sequence[StagedDeclaration] = (),
) -> Mapping[tuple[str, str], Disposition]:
    """``(seal test_id, subject key)`` → :class:`Disposition`, for one report.

    The identity a delta is taken over, and the one place it is spelled. Both
    halves, because :class:`StagedDeclaration` already requires both to match
    exactly and a delta keyed on one of them would let a seal rename retire a
    finding.

    **IMPLEMENTED**, under the standing exception: this is the key function,
    the delta ruling is meaningless without agreeing what a finding IS, and a
    seal author sealing a stub of it would be sealing the ruling's premise
    rather than the ruling.

    Note what it does NOT do: it does not deduplicate. Two seals over one
    subject are two findings with two keys, which is what the acceptance tree
    measures (30 seals, 48 findings) and what makes an introduced count
    meaningful per-seal.

    The match is :func:`~claude_dispatcher.call_site_reachability.
    _declaration_answers` and not a local re-spelling — see the CHOICE at the
    import. FIRST match wins and later ones are not merged, which is
    :func:`check_tree`'s own behaviour (``if matched is None``), so the two
    agree on a duplicated declaration as well as on a rejected one.
    """
    by_key: dict[tuple[str, str], Disposition] = {}
    for finding in report.findings:
        key = (finding.seal.test_id, finding.subject.key)
        matched: StagedDeclaration | None = None
        for declaration in declarations:
            if _declaration_answers(finding, declaration):
                matched = declaration
                break
        by_key[key] = adjudicate(finding, matched)
    return by_key


def introduced_findings(
    base: ReachabilityReport,
    head: ReachabilityReport,
    *,
    base_declarations: Sequence[StagedDeclaration] = (),
    head_declarations: Sequence[StagedDeclaration] = (),
) -> tuple[IntroducedFinding, ...]:
    """THE DELTA. Findings whose head disposition refuses and whose base one did not.

    The rule, stated so a body cannot narrow it by accident: a head finding is
    *introduced* when :func:`verdict_for_disposition` gives it something other
    than CLEAN **and** the same key at base gave CLEAN or was absent. So:

      * BREACH at head, BREACH at base   → not introduced. Pre-existing dark
        code, which is the entire point of the delta ruling and the reason this
        gate is not red on day one.
      * BREACH at head, ACCEPTED at base → **introduced**, and ``was`` says
        ACCEPTED. The branch deleted the declaration that was covering it, and
        that is a branch action.
      * BREACH at head, key absent at base → **introduced**. New symbol, new
        seal, no call site.
      * ACCEPTED at head, BREACH at base → not introduced, and it is not
        reported as a fix either; the ACCEPTED count in the head report is
        where that debt is legible.

    Abstentions do not appear here at all: they are not deltas, for the reason
    written on :data:`_BLOCKING_UNDECIDED_REASONS`.

    **IMPLEMENTED**, under the standing exception. This is the ruling itself
    rendered as eight lines; a stub of it is a stub of the unit.

    ``base_declarations`` and ``head_declarations`` are separate parameters and
    that is not symmetry for its own sake: the declaration set is read from the
    tree it judges, so a branch that ADDS a declaration must have its head
    findings adjudicated with it and its base findings without it, or the delta
    reports the declaration's arrival as a change in the code.
    """
    at_base = dispositions_by_key(base, base_declarations)
    at_head = dispositions_by_key(head, head_declarations)

    detail_by_key = {
        (f.seal.test_id, f.subject.key): f for f in head.findings
    }

    introduced: list[IntroducedFinding] = []
    for key, disposition in sorted(at_head.items()):
        if verdict_for_disposition(disposition) is DiffVerdict.CLEAN:
            continue
        was = at_base.get(key)
        if was is not None and verdict_for_disposition(was) is not DiffVerdict.CLEAN:
            continue
        finding = detail_by_key[key]
        introduced.append(
            IntroducedFinding(
                test_id=key[0],
                subject_key=key[1],
                subject_path=finding.subject.path,
                subject_line=finding.subject.line,
                disposition=disposition,
                was=was,
                reason=finding.reason,
                detail=finding.detail,
            )
        )
    return tuple(introduced)


def sweep_is_vacuous(
    base: ReachabilityReport, head: ReachabilityReport
) -> str | None:
    """Why this pair of reports cannot support a delta, or ``None``.

    **THE GUARD THE DELTA RULING FORCES**, and it is measured rather than
    imagined. *Measured under* ``2e0dc89`` on ``tests/fixtures/d6_g2_preserve``
    with one non-compiling edit to ``cmd/iterate/main.go`` and nothing else::

        BASE  seals 30  findings 48  unanalyzed 2   breach 12
        HEAD  seals 12  findings 19  unanalyzed 2   breach  0
        INTRODUCED: 0

    Break the build and the delta is empty. Three checks, each pinned to a
    report field that MOVED in that measurement or that
    :class:`ReachabilityReport` names as its own non-vacuity field:

      1. **head ``seals_examined`` below base's.** 30 → 12 above. On the
         BLOCKING role this is unambiguous: BODIES may not touch ``tests/``, so
         a bodies branch cannot legitimately reduce the seal count and any
         reduction is a tree that stopped being readable.
      2. **head production roots zero while head has at least one seal.** The
         catastrophe ``ReachabilityReport.roots`` is documented to expose: an
         empty production root set turns every subject FROM_TESTS_ONLY or
         abstains the whole repository, and both are invisible without this
         field. Guarded on ``head`` and not on the pair, because a base that
         was already broken does not make a broken head acceptable.
      3. **head findings below base's while head seals equal base's.** The
         subtler half of (1): the same seals producing fewer findings means
         subjects stopped being nameable, which is degradation wearing a
         quiet face.

    Deliberately NOT a check on ``unanalyzed_paths``: it was 2 in both halves
    of the measurement above and saw nothing. Naming a field that did not move
    would be a guard that reads as protection — the failure mode ``FLOOR_GLOBS``
    records for the brace-compressed glob.

    **IMPLEMENTED**, under the standing exception, for the plainest form of the
    reason: this predicate is the delta ruling's only defence, a seal author
    handed a stub of it would be sealing that the defence exists rather than
    that it works, and this repository's own taxonomy calls that a vacuous
    seal.
    """
    if head.seals_examined < base.seals_examined:
        return (
            f"head examined {head.seals_examined} seal(s) and base examined "
            f"{base.seals_examined}; a delta over a shrinking seal population "
            "reports 'nothing introduced' for a tree that stopped being "
            "readable, and on the role whose gate this is the seal count "
            "cannot legitimately fall — bodies may not touch tests/"
        )
    head_production = sum(
        1 for root in head.roots if root.root_kind is RootKind.PRODUCTION
    )
    if head.seals_examined > 0 and head_production == 0:
        return (
            f"head found {head.seals_examined} seal(s) and ZERO production "
            "roots; every subject is FROM_TESTS_ONLY or abstains wholesale, "
            "which is a repository-wide verdict manufactured by a broken "
            "sweep rather than by the branch"
        )
    if (
        head.seals_examined == base.seals_examined
        and len(head.findings) < len(base.findings)
    ):
        return (
            f"head produced {len(head.findings)} finding(s) from "
            f"{head.seals_examined} seal(s) where base produced "
            f"{len(base.findings)} from the same number; the same seals "
            "naming fewer subjects is degradation, and a delta over it "
            "silently under-reports"
        )
    return None


def analyzable_paths(changed_paths: Sequence[str]) -> tuple[str, ...]:
    """The changed paths some :data:`ANALYZERS` row can read.

    Delegates to :func:`~claude_dispatcher.call_site_reachability.
    analyzer_for_path` one path at a time, so this module owns no second
    extension table — the property D1 spent a whole unit establishing and that
    ``call_site_reachability`` refuses to re-open ("exactly one place in this
    codebase decides what language a file is").

    *Measured under* ``2e0dc89``: ``analyzer_for_path('a/b.go')`` answers the
    Go row and ``analyzer_for_path('a/b.py')`` answers ``None``, with
    ``ANALYZERS`` holding ``GoReachabilityAnalyzer`` and nothing else.

    ``changed_paths`` must be the list ``changed_paths_between`` produced —
    rename detection OFF — so a file moved out of a Go package appears as a
    deletion of the Go path and still selects the sweep. That is the same
    requirement ``evaluate_changed_paths`` states, for the same reason, and it
    is what makes the cheap exit rename-proof.

    **IMPLEMENTED**: three lines, no decision of its own, and a stub of it
    would make :attr:`ReachabilitySweepStatus.NO_ANALYZABLE_FILE_IN_DIFF` —
    the exit that decides whether most branches pay 15 s — untestable.
    """
    return tuple(path for path in changed_paths if analyzer_for_path(path) is not None)


# --------------------------------------------------------------------------- #
# ACCEPTED: where a StagedDeclaration comes from
# --------------------------------------------------------------------------- #

#: **The one path a :class:`StagedDeclaration` may be written at.** Repo
#: relative, read out of the BRANCH's object store.
#:
#: Read from the branch and not from the base, because a declaration is a
#: statement about code the branch is ADDING and a base-pinned read makes it
#: impossible to declare anything about it. That is the opposite of the
#: ``.dispatcher.yaml`` rule and the difference is real: a policy read from the
#: branch lets a branch widen its own PERMISSIONS (invariant 6), whereas a
#: declaration cannot widen anything at all — it moves exactly one cell of
#: ``_RULINGS``, it cannot touch ABSTAIN or REPORT, and it is counted apart
#: from OK in every report.
#:
#: **WHAT STOPS IT BECOMING A RUBBER STAMP**, five teeth, four of them already
#: mechanical upstream and the fifth an escalation this scaffold does not make:
#:
#:   1. both keys must match exactly (:func:`adjudicate`);
#:   2. a declaration whose ``wiring`` is empty or whitespace **is not a
#:      declaration** — the P4 2026-08-11 ruling, and the only part of "name a
#:      future in which this stops being true" a machine can verify;
#:   3. a declaration matching no finding is reported in
#:      ``stale_declarations`` and is carried onto the verdict line here;
#:   4. ACCEPTED is counted apart from OK, so the debt figure is legible;
#:   5. **ESCALATION (3) in the module docstring: this path must be DENIED to
#:      BODIES** in ``role_protocol.DEFAULT_ROLE_RULES``, so the appeal is
#:      written by the adjudicator and not by the party being judged. Without
#:      it, tooth 2 is the only thing between a BREACH and the word ``"TODO"``,
#:      and P4's own ruling says four teeth were not enough. This is the
#:      "expensive and visible" the ratification demanded, and it is exactly
#:      what makes ADJUDICATE's ADVISORY obligation load-bearing rather than
#:      decorative: P4 must SEE the finding it is being asked to declare.
#:
#: CHOICE (rejected: let the body author write it, and rely on review). That is
#: the honour system ``scripts/check_body_branch.sh`` opens by naming as the
#: thing that produced 24 vacuous seals. A gate whose only annotation is
#: written by the party it judges has one tooth, and it is a sentence nobody
#: reads.
#:
#: CHOICE (rejected: put this path on ``FLOOR_GLOBS``). A floored path is
#: writable by NOBODY, so the appeal would not exist. The floor is for things
#: no role may touch; this is a thing exactly one role may touch.
#:
#: **How much of this actually gets used, and it is less than it looks.** Under
#: the delta ruling the protocol's own manufactured dark state is PRE-EXISTING
#: by the time the blocking role is judged: P1 lands the stub and the seal, so
#: the BREACH is already in P3's base and the delta does not report it.
#: Declarations are therefore for the genuine case only — a body that
#: introduces a new dark symbol, or removes the last call site of an old one —
#: which is what makes an expensive appeal affordable.
DECLARATION_PATH = ".dispatcher.staged.yaml"


def declarations_at(
    repo_root: str | Path, ref: str, *, run: Callable[..., object] | None = None
) -> tuple[StagedDeclaration, ...]:
    """Every :class:`StagedDeclaration` at :data:`DECLARATION_PATH` in ``ref``.

    **STUB.** A body implements it.

    Contract:

      * read out of ``ref``'s OBJECT STORE, never the working tree, through the
        same seam ``role_protocol.file_text_at`` uses — this module must not
        grow a second git seam, and a caller substituting the git seam for one
        gate and not the other is how two reads come to disagree;
      * a file that is ABSENT is zero declarations and is not an error. Most
        branches have none;
      * a file that is PRESENT and unreadable, or that parses to something that
        is not a list of mappings, is a :class:`BranchReachabilityError`.
        **Never zero declarations**: "I could not read the appeals" answered
        with "there were no appeals" is a silent BREACH, and it is the exact
        shape ``load_role_policy_from_base`` refuses for the policy;
      * every row must carry all four fields. A row missing ``wiring``
        entirely is a :class:`BranchReachabilityError` here, and a row whose
        ``wiring`` is empty or whitespace is NOT rejected here — it is passed
        through, because :func:`adjudicate` already ignores it exactly as it
        ignores a key mismatch and ``check_tree`` already reports it in
        ``stale_declarations``. Rejecting it here would move a ruled behaviour
        into a second place and the two would drift.

    CHOICE (rejected: parse it with ``yaml_io`` at import time and cache).
    ``yaml_io`` is in the floor's delegation closure and a cache keyed on a ref
    is a cache that goes stale across a branch that moved mid-check — the
    window ``check_branch`` step 5b already exists to close.
    """
    raise NotImplementedError(
        "D7 P1 scaffold: declarations_at is a stub; see its contract"
    )


# --------------------------------------------------------------------------- #
# Materialising the two trees
# --------------------------------------------------------------------------- #


def materialise_base_tree(
    repo_root: str | Path,
    base_ref: str,
    subtree: str,
    destination: Path,
    *,
    run: Callable[..., object] | None = None,
) -> Path:
    """Extract ``subtree`` at ``base_ref`` into ``destination``; return the tree root.

    **STUB.** A body implements it.

    This function is the delta ruling's whole extra cost and the reason it is
    affordable. *Measured under* ``2e0dc89`` on ``evenplay-mono`` @
    ``51a71736c``, three repetitions each::

        git worktree add --detach <dst> <ref>     0.74 / 0.76 / 0.76 s, 275 MB
        git archive <ref> <subtree> | tar -x      0.01 / 0.01 / 0.01 s, 472 KB

    and a ``check_tree`` sweep over the archived result costs the same as one
    over the tree in place (7.83 s then 7.69 s, against 7.84 / 7.69 / 7.61 s
    in place), so the extraction adds its 0.01 s and nothing else.

    Contract:

      * ``git archive``, not ``git worktree add``. **Measured 75× cheaper and
        580× smaller**, and it needs no cleanup of git's worktree registry —
        which, measured while taking the figure above, is itself a trap: a
        removed directory leaves a registered worktree and the next ``add``
        fails until ``git worktree prune``. A gate that can wedge a repository
        it was only supposed to read is not a gate anyone leaves on;
      * ``destination`` MUST be outside ``repo_root``.
        ``check_tree``'s own obligation — *"never write into ``tree``"*, on
        ``fixture_reachability.construct_witness``'s reasoning that a workspace
        inside the tree under check is picked up by the very thing being
        interrogated — applies to the base tree as much as the head tree, and a
        base extracted under ``repo_root`` would additionally appear in the
        HEAD sweep as new Go packages;
      * it MUST be removed afterwards, including on the failure path. A gate
        that leaks 472 KB per PR is a gate someone turns off in a month;
      * a failure is :attr:`ReachabilitySweepStatus.UNCHECKED_BASE_UNAVAILABLE`
        at the caller, never an empty tree. An empty base tree makes every head
        finding look introduced, which is the permanently-red failure arriving
        by the back door.

    ``subtree`` is the analyzable scope, not the repository: on a monorepo the
    branch's Go work is one app and extracting the other 274 MB buys nothing.
    Deriving it is the caller's job — see
    :func:`check_branch_reachability`.
    """
    raise NotImplementedError(
        "D7 P1 scaffold: materialise_base_tree is a stub; see its contract"
    )


# --------------------------------------------------------------------------- #
# The record, and the entrypoint
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class BranchReachability:
    """What this gate found, in the shape ``RoleDiffResult`` carries and prints.

    ``is_clean`` is deliberately absent, exactly as on
    :class:`ReachabilityReport` and on D3 before it: the caller decides what to
    block on and a single boolean would have to fold the abstentions into one
    side of it. :func:`verdict_of` is the function that decides, and it is
    separate on purpose.

    ``status`` / ``obligation``
        The two named states. Both are printed, always, including on a CLEAN
        verdict — a pass reached without running the sweep says so on the
        verdict's own line, which is what ``role_protocol``'s 2026-08-09
        rulings bought their CLEAN rows with.
    ``introduced``
        :func:`introduced_findings`' answer. Empty on any status but CHECKED.
    ``head_dispositions`` / ``base_dispositions``
        The full :class:`Disposition` counts of both reports, every member a
        key including the zeros, for :class:`ReachabilityReport`'s own reason —
        a count omitted because it was zero is indistinguishable from a count
        nobody took. This is where the ACCEPTED debt figure and the abstention
        coverage figure are legible, and neither is derivable from
        ``introduced``.
    ``head_seals_examined`` / ``base_seals_examined``
        The non-vacuity pair. Printed even when equal: they are what makes the
        broken-build measurement readable off a CI log.
    ``head_production_roots``
        Zero here with a non-zero seal count is the catastrophe
        :func:`sweep_is_vacuous` refuses on, carried so a reader can see it
        without re-running anything.
    ``stale_declarations``
        Declarations that answered nothing, from ``check_tree``. **Reported,
        never blocking.** A declaration goes stale exactly when the wiring
        lands, so refusing the branch that retires it would punish the good
        outcome — but the row must still be deleted, and ADJUDICATE is the role
        that owns the file and sees this.
    ``detail``
        The one line a caller that logs the verdict keeps.
    """

    status: ReachabilitySweepStatus
    obligation: ReachabilityObligation
    introduced: tuple[IntroducedFinding, ...] = ()
    head_dispositions: Mapping[Disposition, int] | None = None
    base_dispositions: Mapping[Disposition, int] | None = None
    head_seals_examined: int = 0
    base_seals_examined: int = 0
    head_production_roots: int = 0
    stale_declarations: tuple[StagedDeclaration, ...] = ()
    abstention_reasons: tuple[UndecidedReason, ...] = ()
    detail: str = ""


def verdict_of(result: BranchReachability) -> DiffVerdict:
    """This gate's contribution to the branch verdict. CLEAN = "does not refuse".

    Total, and the composition is the whole ruling in one place:

      1. under :attr:`ReachabilityObligation.NOT_RUN` or
         :attr:`~ReachabilityObligation.ADVISORY`, CLEAN — always, whatever the
         findings say. A role that cannot fix a BREACH is not blocked by one;
      2. under BLOCKING, the worst of: :func:`verdict_for_status`,
         :func:`verdict_for_disposition` over every introduced finding, and
         :func:`verdict_for_abstention` over every abstention reason in the
         HEAD report (not the delta — see
         :data:`_BLOCKING_UNDECIDED_REASONS`).

    **IMPLEMENTED**, under the standing exception, and it is the single most
    important thing here to implement rather than stub: this is the function
    the whole contract exists to specify, every table above is dead unless
    something composes them, and a seal author handed a stub would be sealing
    the tables in isolation — which is precisely the "the seal proves a
    function behaves, never that it runs" gap this repository has recorded
    twice.
    """
    obligation = result.obligation
    if obligation is ReachabilityObligation.NOT_RUN:
        return DiffVerdict.CLEAN
    if obligation is ReachabilityObligation.ADVISORY:
        return DiffVerdict.CLEAN
    if obligation is not ReachabilityObligation.BLOCKING:
        raise BranchReachabilityError(
            f"obligation {obligation!r} has no verdict rule; a new "
            "ReachabilityObligation member must be ruled on, not defaulted"
        )

    verdicts = [verdict_for_status(result.status)]
    verdicts += [
        verdict_for_disposition(f.disposition) for f in result.introduced
    ]
    verdicts += [
        verdict_for_abstention(reason) for reason in result.abstention_reasons
    ]
    return worst_verdict(verdicts)


def check_branch_reachability(
    repo_root: str | Path,
    base_ref: str,
    branch_ref: str,
    role: Role,
    changed_paths: Sequence[str],
    *,
    already_violation: bool,
    run: Callable[..., object] | None = None,
) -> BranchReachability:
    """THE diff-time reachability check. One entrypoint, as ``check_branch`` is.

    **STUB.** A body implements it. Everything it must compose is above and
    every table it must not re-decide is above.

    THE SEQUENCE, and a body must not reorder it. Each step's exit is a NAMED
    :class:`ReachabilitySweepStatus` and none of them is a pass:

      1. :func:`obligation_for_role`. NOT_RUN ⇒ return immediately with
         :attr:`~ReachabilitySweepStatus.NOT_THIS_ROLES_GATE`. **First**,
         because it is free and it is the answer for three of the five roles.
      2. ``already_violation`` ⇒ return with
         :attr:`~ReachabilitySweepStatus.NOT_REACHED_ALREADY_VIOLATION`. See
         "the cost's placement" below.
      3. :func:`analyzable_paths` over ``changed_paths``. Empty ⇒ return with
         :attr:`~ReachabilitySweepStatus.NO_ANALYZABLE_FILE_IN_DIFF`. **This is
         the exit most branches take and it is what keeps the gate cheap in
         practice**: on this repository a Python-only branch never reaches
         step 5.
      4. confirm ``repo_root``'s HEAD IS ``branch_ref``, else return with
         :attr:`~ReachabilitySweepStatus.UNCHECKED_HEAD_NOT_CHECKED_OUT`.
         **This is the architectural gap and it must not be assumed away.**
         ``check_branch`` reads BLOBS out of the object store and never needs a
         checkout; ``check_tree`` takes a DIRECTORY. ``check_body_branch.sh``
         documents "runs in the checkout to be judged (cwd = repo root), as CI
         does", so the assumption holds at both of today's call sites — and an
         assumption that holds is still an assumption, and this one silently
         judges the wrong revision when it stops holding. Same shape as step
         5b's "the branch moved while it was being checked", same answer.
      5. derive the analyzable SUBTREE from step 3's paths — the shallowest
         directory containing all of them, or the repository root when they
         span more than one — and :func:`materialise_base_tree` it at
         ``base_ref``. A failure is
         :attr:`~ReachabilitySweepStatus.UNCHECKED_BASE_UNAVAILABLE`.
      6. :func:`~claude_dispatcher.call_site_reachability.check_tree` over the
         base tree, then over ``repo_root``. Both, through a module global so
         one seam is substitutable, as ``check_branch`` does for its three git
         functions. A :class:`~claude_dispatcher.call_site_reachability.
         CallSiteReachabilityError` out of either ⇒
         :attr:`~ReachabilitySweepStatus.UNCHECKED_ANALYZER_FAULT`. It will
         happen: since D6 enrolment a tree with a ``.go`` file on a host with
         no usable ``go`` RAISES, and a CI image without a Go toolchain is the
         recorded non-empty case.
      7. :func:`sweep_is_vacuous` over the pair. Non-``None`` ⇒
         :attr:`~ReachabilitySweepStatus.UNCHECKED_SWEEP_VACUOUS`, carrying its
         sentence.
      8. both ``seals_examined`` zero ⇒
         :attr:`~ReachabilitySweepStatus.NO_SEAL_IN_TREE`, with the counts.
      9. :func:`declarations_at` for BOTH refs, :func:`introduced_findings`,
         and assemble. :attr:`~ReachabilitySweepStatus.CHECKED`.

    THE COST'S PLACEMENT — steps 1-3 are the ruling
    -----------------------------------------------
    **After the cheap checks, and a branch that is already VIOLATION does not
    pay.** The verdict cannot get worse than VIOLATION, the branch is being
    refused and the author is coming back; when they come back with the path
    violation fixed, step 2 no longer fires and the sweep runs. What is bought
    by skipping is 15.4 s on the primary target on every already-doomed run;
    what is risked is a reader mistaking a VIOLATION report's silence for a
    reachability pass, and that is what
    :attr:`~ReachabilitySweepStatus.NOT_REACHED_ALREADY_VIOLATION` on the
    verdict line is for.

    CHOICE (rejected: run it first, so the report is complete whatever else
    failed). A complete report is worth real money and this is close — but the
    branch that most needs the report is the one that is otherwise CLEAN, and
    paying on every refused run is how the total bill becomes the argument for
    switching the gate off.

    CHOICE (rejected: skip it when the branch is already UNDETERMINED). It
    never arises: every UNDETERMINED arm in ``check_branch`` returns before the
    verdict block, so there is no such state to test for. Named rather than
    left implicit so a body does not add a test for a condition that cannot
    hold and then trust it.

    WHAT IT MUST NOT DO
    -------------------
      * **never raise.** ``check_branch`` is contracted never to raise, and a
        gate that turns a traceback into a CI mystery has replaced exit 3 with
        nothing. Every failure above is a named status;
      * **never weaken :func:`check_tree`.** No flag, no filter, no "quiet
        mode", no subject list passed down. The mechanism keeps answering "what
        is dark in this tree"; every narrowing this unit does is done to the
        REPORT, afterwards, in :func:`introduced_findings`;
      * **never write into ``repo_root``.**

    P3 NOTE — THE CALL SITE IS NOT YOURS TO ADD ALONE. Wiring this into
    ``check_branch`` puts this module into the floor's derived delegation
    closure (measured; escalation 2 in the module docstring), which requires an
    edit to ``FLOOR_GLOBS`` in a floored file AND a row in
    ``tests/test_floor_closure.py``, a seal file BODIES may not touch. Take it
    to P4.
    """
    raise NotImplementedError(
        "D7 P1 scaffold: check_branch_reachability is a stub; see its contract"
    )
