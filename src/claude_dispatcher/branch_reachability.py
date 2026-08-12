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

import collections.abc
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable, Mapping, Sequence

from . import role_protocol as role_protocol_mod
from . import yaml_io
from .call_site_contract import RootKind
from .call_site_reachability import (
    CallSiteReachabilityError,
    Disposition,
    ReachabilityReport,
    StagedDeclaration,
    UndecidedReason,
    _declaration_answers,
    adjudicate,
    analyzer_for_path,
    check_tree,
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

#: DISPUTE D4's ruling in one name, so that the three sites that use it cannot
#: drift and so that the P4 who adds the tenth member has one line to change.
#: See :func:`check_branch_reachability`'s D4 section for why this member and
#: not one of the other three that refuse. It is asserted below to be one of
#: them, because a D4 ruling that resolved to a CLEARING status would be the
#: permissive answer with a third spelling.
_APPEAL_UNREADABLE_STATUS: ReachabilitySweepStatus = (
    ReachabilitySweepStatus.UNCHECKED_SWEEP_VACUOUS
)

if _APPEAL_UNREADABLE_STATUS not in _BLOCKING_SWEEP_STATUSES:  # pragma: no cover
    # An `if`/`raise` and NOT an `assert`, deliberately: `python -O` strips
    # asserts, and a guard that vanishes under a flag is "a guard that reads as
    # protection" — the failure `FLOOR_GLOBS` records for the brace-compressed
    # glob and the one this module spends a docstring refusing.
    raise BranchReachabilityError(
        "the status DISPUTE D4 is ruled onto must REFUSE on the role whose "
        "gate this is; an appeal file nobody could read is something an author "
        "can fix and re-running clears, and none of the nine may read as a pass"
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
    # DEFECT D5, FIXED (P3 body). Was ``if reason not in UndecidedReason``.
    # See the note on :func:`verdict_for_status` for the measurement and for
    # why this spelling and not the other.
    if not isinstance(reason, UndecidedReason):
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

    DEFECT D5, FIXED (P3 body, ``feat/D7-body``). The shipped guard was ``if
    status not in ReachabilitySweepStatus``, and ``x in SomeEnum`` is a **value**
    lookup on Python 3.12+. *Measured under* ``8948a6e`` on python 3.13.7,
    before the fix::

        "checked" in ReachabilitySweepStatus            -> True
        verdict_for_status("unchecked_analyzer_fault")  -> DiffVerdict.CLEAN
        verdict_for_abstention("parse_failed")          -> DiffVerdict.CLEAN

    The guard admitted the bare string, the string then failed a membership
    test against a frozenset of MEMBERS, and both functions returned the
    CLEARING branch — for exactly the two inputs their own docstrings say must
    refuse. ``isinstance`` is the fix in both.

    **The defect was inside the thing built to prevent the defect.** These three
    tables were implemented at P1 rather than stubbed *precisely* so that a seal
    author would not be sealing a vacuous stub of "an unmapped member raises" —
    and the permissive answer walked in through the one spelling of that raise
    nobody re-derived. A guard is only worth what its author measured, not what
    its docstring claims; this one claimed to forbid "a new spelling of the
    permissive answer" while being one.

    *Measured under* ``8948a6e``, the three dispatches D5 says are unaffected,
    re-derived rather than assumed: ``verdict_for_disposition("breach")``,
    ``obligation_for_role("bodies")`` and ``worst_verdict(["clean"])`` each
    raise :class:`BranchReachabilityError` already — the first two dispatch
    through a ``dict`` lookup (a string is not a member and is not a key) and
    the third tests membership against ``_VERDICT_PRECEDENCE``, a **tuple** of
    members, where ``in`` is ordinary equality and not the enum protocol. All
    three value spellings *are* accepted by ``in <Enum>``
    (``"breach" in Disposition``, ``"bodies" in Role``, ``"clean" in
    DiffVerdict`` are each True), so the three are safe by their dispatch shape
    and not by their inputs — which is why they are worth re-measuring rather
    than reasoning about.
    """
    if not isinstance(status, ReachabilitySweepStatus):
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


#: The four fields a declaration row must carry, and the ONLY four. Checked
#: both ways — a row missing one is a :class:`BranchReachabilityError` by the
#: contract below, and a row carrying a FIFTH is one too, because the fifth is
#: almost always a misspelling of one of these four and a misspelled
#: ``subject_key`` silently answers nothing while looking like an appeal. The
#: cost of the strictness is that a future field is a two-line edit here; the
#: cost of the alternative is an appeal that reads as written and adjudicates
#: as absent, which is the vacuous shape this module exists to refuse.
_DECLARATION_FIELDS: tuple[str, ...] = ("test_id", "subject_key", "wiring", "reason")


def declarations_at(
    repo_root: str | Path, ref: str, *, run: Callable[..., object] | None = None
) -> tuple[StagedDeclaration, ...]:
    """Every :class:`StagedDeclaration` at :data:`DECLARATION_PATH` in ``ref``.

    **IMPLEMENTED (P3 body, ``feat/D7-body``).**

    Delegates the git read to ``role_protocol.file_text_at``, looked up as an
    attribute on the module and never from-imported, so this module grows no
    second git seam: that function already answers symlink, submodule,
    non-UTF-8 and unresolvable-ref for both gates at once (it delegates in turn
    to ``repo_config.blob_text_at``, invariant 5's one reader of a path out of
    a ref's object store). ``None`` from it means "this ref's tree does not
    contain the file" and nothing else — the distinction the whole third bullet
    below rests on.

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
    try:
        text = role_protocol_mod.file_text_at(
            repo_root, ref, DECLARATION_PATH, run=run
        )
    except Exception as exc:  # RoleDiffError, and anything the seam raises
        raise BranchReachabilityError(
            f"cannot read {DECLARATION_PATH} at {ref}: {exc}; 'I could not "
            "read the appeals' is never answered with 'there were no "
            "appeals', which would turn every declared finding back into a "
            "silent BREACH"
        ) from exc

    if text is None:
        return ()

    try:
        rows = yaml_io.loads(text)
    except Exception as exc:
        raise BranchReachabilityError(
            f"{DECLARATION_PATH} at {ref} is not readable YAML: {exc}; a file "
            "that is PRESENT and unparseable is a refusal, never zero "
            "declarations"
        ) from exc

    if rows is None:  # an empty document, which is a file with no rows in it
        return ()
    if not isinstance(rows, list):
        raise BranchReachabilityError(
            f"{DECLARATION_PATH} at {ref} parses to {type(rows).__name__}, not "
            "a list of mappings; the shape load_role_policy_from_base refuses "
            "for the policy, refused here for the appeal"
        )

    declarations: list[StagedDeclaration] = []
    for index, row in enumerate(rows):
        where = f"{DECLARATION_PATH} at {ref}, row {index}"
        if not isinstance(row, collections.abc.Mapping):
            raise BranchReachabilityError(
                f"{where} is {type(row).__name__}, not a mapping; a list of "
                "something else is not a list of declarations"
            )
        missing = [field for field in _DECLARATION_FIELDS if field not in row]
        if missing:
            raise BranchReachabilityError(
                f"{where} is missing {missing!r}; every row must carry all "
                "four fields, and a row with no `wiring` KEY cannot even be "
                "the empty-wiring case adjudicate already rules on"
            )
        unknown = [key for key in row if key not in _DECLARATION_FIELDS]
        if unknown:
            raise BranchReachabilityError(
                f"{where} carries {unknown!r}, which is not one of "
                f"{list(_DECLARATION_FIELDS)}; an unrecognised key is a "
                "misspelling far more often than it is an extension, and a "
                "misspelled subject_key is an appeal that answers nothing "
                "while reading as one"
            )
        values = {}
        for field in _DECLARATION_FIELDS:
            value = row[field]
            if not isinstance(value, str):
                raise BranchReachabilityError(
                    f"{where} has {field}={value!r}, which is "
                    f"{type(value).__name__} and not a string; both keys are "
                    "matched by exact string equality and a non-string "
                    "matches nothing"
                )
            values[field] = value
        # `wiring` that is empty or whitespace is deliberately NOT rejected
        # here — it is passed through, because `adjudicate` already ignores it
        # exactly as it ignores a key mismatch and `check_tree` already reports
        # it in `stale_declarations`. Two places ruling on one behaviour is two
        # places to drift.
        declarations.append(StagedDeclaration(**values))
    return tuple(declarations)


# --------------------------------------------------------------------------- #
# Materialising the two trees
# --------------------------------------------------------------------------- #

#: How long any one subprocess this module starts may take. The same shape
#: ``repo_config`` uses, and here for the same reason: a gate that can hang is
#: a gate CI kills without a verdict, which is the one outcome worse than a
#: named refusal.
_SUBPROCESS_TIMEOUT_SECONDS = 300


def _run_capture(
    command: Sequence[str], run: Callable[..., object] | None
) -> tuple[int, str]:
    """``(returncode, stderr)`` for one command, through the injectable seam.

    ``run``'s convention is ``repo_config._run_git``'s, which is
    ``push_verify``'s: a ``CompletedProcess`` or a ``(rc, out, err)`` triple
    are both accepted, because the seam's shape is the caller's choice.

    Only ``stderr`` is returned because neither of this module's two commands
    has a stdout a caller reads — ``git archive`` writes its bytes to
    ``--output`` and ``tar`` writes files. A helper that returned stdout would
    be a helper that invited someone to hold 270 MB in a string.
    """
    if run is None:
        proc = subprocess.run(
            list(command),
            capture_output=True,
            text=True,
            timeout=_SUBPROCESS_TIMEOUT_SECONDS,
        )
        return proc.returncode, proc.stderr or ""
    result = run(
        list(command),
        capture_output=True,
        text=True,
        timeout=_SUBPROCESS_TIMEOUT_SECONDS,
    )
    if hasattr(result, "returncode"):
        code = int(getattr(result, "returncode"))
        return code, str(getattr(result, "stderr", "") or "")
    if isinstance(result, tuple) and len(result) >= 2:
        return int(result[0]), str(result[2]) if len(result) > 2 and result[2] else ""
    raise BranchReachabilityError(
        f"the injected run seam answered {result!r}, which is neither a "
        "CompletedProcess nor a (rc, out, err) triple; a gate cannot read a "
        "verdict out of a shape it does not recognise"
    )


def _resolved_sha(
    repo_root: Path, ref: str, run: Callable[..., object] | None
) -> str | None:
    """``ref``'s commit sha in ``repo_root``, or ``None`` when it does not resolve.

    ``git rev-parse --verify <ref>^{commit}`` — ``^{commit}`` so that a tag and
    the commit it points at compare equal, and ``--verify`` so that an
    unresolvable ref is a non-zero exit rather than the string ``<ref>`` echoed
    back, which is ``rev-parse``'s default and would compare unequal to
    everything and read as "not checked out" for a reason that is not that.
    """
    if run is None:
        proc = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "--verify", f"{ref}^{{commit}}"],
            capture_output=True,
            text=True,
            timeout=_SUBPROCESS_TIMEOUT_SECONDS,
        )
        return proc.stdout.strip() if proc.returncode == 0 else None
    result = run(
        ["git", "-C", str(repo_root), "rev-parse", "--verify", f"{ref}^{{commit}}"],
        capture_output=True,
        text=True,
        timeout=_SUBPROCESS_TIMEOUT_SECONDS,
    )
    if hasattr(result, "returncode"):
        if int(getattr(result, "returncode")) != 0:
            return None
        return str(getattr(result, "stdout", "") or "").strip()
    if isinstance(result, tuple) and len(result) >= 2:
        return str(result[1] or "").strip() if int(result[0]) == 0 else None
    raise BranchReachabilityError(
        f"the injected run seam answered {result!r} for rev-parse; see "
        "_run_capture"
    )


def materialise_base_tree(
    repo_root: str | Path,
    base_ref: str,
    subtree: str,
    destination: Path,
    *,
    run: Callable[..., object] | None = None,
) -> Path:
    """Extract ``subtree`` at ``base_ref`` into ``destination``; return the tree root.

    **IMPLEMENTED (P3 body, ``feat/D7-body``).** ``subtree`` is a git pathspec;
    ``""`` and ``"."`` mean **the whole repository**, which under the D2 ruling
    below is what the only caller passes.

    This function is the delta ruling's whole extra cost and the reason it is
    affordable. *Measured under* ``2e0dc89`` on ``evenplay-mono`` @
    ``51a71736c``, three repetitions each::

        git worktree add --detach <dst> <ref>     0.74 / 0.76 / 0.76 s, 275 MB
        git archive <ref> <subtree> | tar -x      0.01 / 0.01 / 0.01 s, 472 KB

    and a ``check_tree`` sweep over the archived result costs the same as one
    over the tree in place (7.83 s then 7.69 s, against 7.84 / 7.69 / 7.61 s
    in place), so the extraction adds its 0.01 s and nothing else.

    **THE D2 PRICE, MEASURED. The whole tree, not a subtree.** DISPUTE D2 ruled
    that both halves of the delta must be swept at the REPOSITORY ROOT, because
    a subject key, a subject path and a seal ``test_id`` are all relative to the
    swept root — so a subtree base matches nothing a whole-tree head produced,
    and a *symmetric* subtree reading makes a ``.dispatcher.staged.yaml``
    written from one branch's report stop matching on the next branch, whose
    different changed-file set derives a different scope. An appeal whose
    validity depends on which files the branch happened to edit is not an
    appeal. The scaffold's 472 KB figure is therefore not the figure this gate
    pays, and it is re-measured here rather than inherited.

    *Measured under* ``8948a6e`` on ``evenplay-mono`` @ ``51a71736c``, this
    host, three repetitions, ``git archive --format=tar`` piped through
    ``tar -x``, wall clock covering archive **and** extraction::

        git archive <ref> apps/website-public-api | tar -x
            0.017 / 0.029 / 0.031 s      472 KB extracted (420 KB tar)   58 files
        git archive <ref> | tar -x        (the whole tree, D2's ruling)
            0.856 / 0.845 / 0.859 s   279 824 KB extracted (270 MB tar)  6 285 files

    **So D2 costs 0.85 s and 273 MB where the scaffold budgeted 0.01 s and
    472 KB — 28x the time and 592x the bytes.** Two things about that number
    before anyone argues from it:

      * against the delta's own measured 15.4 s of sweeping on this same
        target, 0.84 s of extra extraction is **+5.5% wall clock**. The
        extraction was never the cost; the second sweep is;
      * it is the same order as ``git worktree add --detach`` (0.74–0.76 s,
        275 MB), which the contract rejected *on cost*. At whole-tree scale
        that argument is gone — the two routes cost the same. What survives,
        and is now the ONLY reason to prefer ``git archive``, is that it
        touches no worktree registry: a removed directory leaves a REGISTERED
        worktree and the next ``add`` fails until ``git worktree prune``, and a
        gate that can wedge a repository it was only supposed to read is not a
        gate anyone leaves on. That reason is sufficient on its own and it is
        the one to keep quoting.

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
    :func:`check_branch_reachability`. **That sentence is the contract's, and
    D2 overruled it**: the only caller passes ``""``, and the 274 MB is bought
    not for the analysis but for the stability of the keys the appeal file is
    written in. The parameter is kept because the containment and cleanup
    obligations are the function's regardless of scope, and because the seal
    exercises it with a real subtree.

    IMPLEMENTATION NOTE — ``--output`` and then ``tar -xf``, not a pipe. Two
    ordinary ``run`` calls through the injectable seam instead of a
    ``Popen``-to-``Popen`` pipe, and neither ever holds the archive in memory:
    at whole-tree scale on the primary target that would be a 270 MB
    ``bytes``. The tarball is created by ``tempfile.mkstemp`` — outside
    ``repo_root`` by the same obligation ``destination`` is — and unlinked in a
    ``finally``.
    """
    repo = Path(repo_root).resolve()
    dest = Path(destination).resolve()

    if dest == repo or repo in dest.parents:
        raise BranchReachabilityError(
            f"refusing to materialise the base tree at {dest}, which is inside "
            f"{repo}: check_tree's own obligation is never to write into the "
            "tree it reads, and a base extracted under repo_root would "
            "additionally appear in the HEAD sweep as new packages — a gate "
            "manufacturing its own findings"
        )

    dest.mkdir(parents=True, exist_ok=True)
    pathspec = [] if subtree in ("", ".") else [subtree]

    handle, tarball_name = tempfile.mkstemp(prefix="d7-base-", suffix=".tar")
    os.close(handle)
    tarball = Path(tarball_name)
    try:
        code, stderr = _run_capture(
            [
                "git",
                "-C",
                str(repo),
                "archive",
                "--format=tar",
                f"--output={tarball}",
                base_ref,
                *pathspec,
            ],
            run,
        )
        if code != 0:
            raise BranchReachabilityError(
                f"git archive {base_ref} {' '.join(pathspec)} in {repo} exited "
                f"{code}: {stderr.strip()}; a base that cannot be materialised "
                "is UNCHECKED_BASE_UNAVAILABLE at the caller and never an "
                "empty tree, which would make every head finding look "
                "introduced"
            )
        code, stderr = _run_capture(["tar", "-xf", str(tarball), "-C", str(dest)], run)
        if code != 0:
            raise BranchReachabilityError(
                f"tar -xf into {dest} exited {code}: {stderr.strip()}; a "
                "partially extracted base tree is the same falsehood as an "
                "empty one"
            )
    finally:
        tarball.unlink(missing_ok=True)

    return dest


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

         **AMENDED FOR DISPUTE D6 (P3 body): the exit is not taken when
         :data:`DECLARATION_PATH` is among the changed paths.** The exit's
         soundness argument is *"a branch that changed no file any analyzer can
         read changed no call edge in any language this gate can see"*. That
         sentence is TRUE and it does not cover the appeal file, because
         withdrawing a declaration changes no edge — it changes the
         ADJUDICATION, and the delta is then ``base=ACCEPTED`` →
         ``head=BREACH`` on every line the appeal was holding.

         *Measured under* ``8948a6e``: a branch whose ENTIRE diff is the
         deletion of an appeal answering all ten findings the compiling edit
         introduced is worth ten VIOLATIONs, and ``analyzable_paths`` over its
         truthful changed-path list — ``('.dispatcher.staged.yaml',)`` — is
         ``()``. Under the exit as written that branch is CLEAN. One line
         fixes it and the line is here; the general shape is a contract
         question and is filed: **the gate's inputs are not only the files an
         analyzer can read**, and any future non-source input to the verdict
         inherits this hole.
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
      5. :func:`materialise_base_tree` at ``base_ref``. A failure is
         :attr:`~ReachabilitySweepStatus.UNCHECKED_BASE_UNAVAILABLE`.

         **AMENDED FOR DISPUTES D2 AND D3 (P3 body): the scope is the
         REPOSITORY ROOT, for both halves, and no subtree is derived from the
         changed paths at all.** The contract said "the shallowest directory
         containing all of them". Both of the readings that sentence permits
         are inadmissible and both were measured:

           * **the mix the contract literally specifies** — base at the derived
             subtree, head at ``repo_root`` (step 6's own words) — reports
             **12 introduced on a ``cmd/gates``-only branch**, every one of them
             ``cmd/iterate``'s pre-existing standing BREACHes, absent from a
             base tree that holds only ``cmd/gates`` and therefore reading as
             new. Sweeping the base one directory deeper instead gives **22**,
             because a subject key is qualified by the package's directory
             RELATIVE TO THE SWEPT ROOT and a base swept deeper matches
             nothing. :func:`sweep_is_vacuous` catches **neither**: head 30
             seals against base 12 trips no check. Through the gate the mix
             reddens THIRTEEN rows;
           * **the symmetric subtree reading** — both halves at the derived
             subtree — is consistent and still inadmissible, and this is the
             finding that decides it. Subject key, subject path and seal
             ``test_id`` are ALL relative to the swept root, so a
             :data:`DECLARATION_PATH` written from one branch's gate report
             stops matching on the NEXT branch, whose different changed-file
             set derives a different scope. **An appeal whose validity depends
             on which files the branch happened to edit is not an appeal.** It
             reddens 2 rows.

         So: the repository root for both halves. Its price is a whole-tree
         archive rather than a subtree one and that price is measured on
         :func:`materialise_base_tree` — 0.85 s and 273 MB against 0.01 s and
         472 KB on the primary target, which is +5.5% on the delta's own
         15.4 s. The contract bought its cheapness by making the appeal file's
         keys a function of the diff, and that was not a trade a seal author
         could hide or a body could take.

         **AND DO NOT REINTRODUCE A COMMON ROOT AS AN OPTIMISATION.** "The
         shallowest directory containing all of them" cuts a module in half:
         *measured under* ``8948a6e`` on ``tests/fixtures/d6_import_scope``,
         one Go module, the whole tree reports **2 seals / 1 BREACH** and
         ``cmd/app`` extracted alone reports **0 seals, 0 findings, 0
         production roots and NO ERROR**. A branch editing only
         ``cmd/app/main.go`` would be swept over a tree with no ``go.mod``,
         take :attr:`~ReachabilitySweepStatus.NO_SEAL_IN_TREE` — *CLEAN, and
         loud* — and state that a tree holding two seals holds none. The cheap
         exit and the honest-status ruling would both be satisfied and the
         answer false. D2's ruling makes this moot; it is written down so that
         the next person to notice the 273 MB does not un-fix it.
      5b. :func:`declarations_at` for BOTH refs. **Ordered here rather than at
         step 9, deliberately and narrowly**: the declarations are an INPUT to
         :func:`~claude_dispatcher.call_site_reachability.check_tree`, and
         passing them down is what makes ``report.dispositions`` and
         ``report.stale_declarations`` the SHIPPED mechanism's own answers
         instead of a tally this module would otherwise have to keep — a second
         implementation of adjudication, in the module contracted to own none.
         Step 9 keeps its remaining job. Nothing else moves: a failure here
         still cannot preempt
         :attr:`~ReachabilitySweepStatus.UNCHECKED_BASE_UNAVAILABLE`, because
         step 5 has already run.
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
      9. :func:`introduced_findings` over the pair and step 5b's two
         declaration sets, and assemble.
         :attr:`~ReachabilitySweepStatus.CHECKED`.

    DISPUTE D4 — WHAT A ``declarations_at`` FAILURE IS CALLED
    ---------------------------------------------------------
    :func:`declarations_at` RAISES on an unreadable or malformed appeal file
    and this function may not raise, and the contract named no status for the
    gap. **Ruled here:
    :attr:`~ReachabilitySweepStatus.UNCHECKED_SWEEP_VACUOUS`**, carrying the
    sentence :func:`declarations_at` raised with. It blocks on the BODIES role,
    which is the property the gap actually needs — an appeal file nobody could
    read is something an author can fix and re-running clears — and it is the
    enum's designated *"both sweeps ran and the pair does not support a delta"*
    state, which is exactly what has happened: the delta is
    ``dispositions(base) → dispositions(head)``, a disposition is a function of
    a report AND its declarations, and one side's declarations are unavailable.
    Its docstring names ``sweep_is_vacuous`` as the thing that usually says
    which; here ``detail`` says which instead, and ``detail`` is printed on the
    verdict line either way.

    CHOICE (rejected, and it is the seal author's own recommendation: a TENTH
    :class:`ReachabilitySweepStatus` member, blocking). It is the right answer
    and **P3 is mechanically barred from giving it.**
    ``tests/test_branch_reachability.py::_STATUS_WITNESSES`` requires every
    member to name a producing row, and
    ``test_every_sweep_status_has_a_witness_and_none_reads_as_a_pass`` asserts
    it over ``for status in ReachabilitySweepStatus`` — so a tenth member
    reddens a seal, in a file BODIES may not touch. That seal says so in as
    many words ("Predicted (unmeasured, and unmeasurable — the enum is closed)
    under: adding a tenth member — claim 1 fails"). The tenth member is
    therefore a P4 amendment shaped exactly like the wiring escalation: one
    edit touching this module AND a seal file. **Filed, not closed.** Reusing
    an existing member is the honest interim and it is honest only because the
    member reused refuses.

    CHOICE (rejected: :attr:`~ReachabilitySweepStatus.UNCHECKED_BASE_UNAVAILABLE`).
    It fits the base-side read and lies about the head-side one, and half a
    status that names the wrong revision is worse on a CI log than one that
    names the right failure in ``detail``. CHOICE (rejected:
    :attr:`~ReachabilitySweepStatus.UNCHECKED_ANALYZER_FAULT`). Nothing about
    the mechanism faulted; the appeal is not a language and ``check_tree`` did
    not raise.

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
    try:
        obligation = obligation_for_role(role)
    except BranchReachabilityError as exc:
        # An unmapped Role. The obligation on the record is BLOCKING and the
        # status refuses: a role this gate has never heard of is the one case
        # where "we did not ask about your branch" would be a guess, and the
        # module's own doctrine is that an unhandled member must not fall
        # through to the permissive branch.
        return BranchReachability(
            status=_APPEAL_UNREADABLE_STATUS,
            obligation=ReachabilityObligation.BLOCKING,
            detail=str(exc),
        )

    # 1. Whose gate it is. First, because it is free and it answers three of
    #    the five roles.
    if obligation is ReachabilityObligation.NOT_RUN:
        return BranchReachability(
            status=ReachabilitySweepStatus.NOT_THIS_ROLES_GATE,
            obligation=obligation,
            detail=(
                f"reachability is not {role.value}'s gate: a role that cannot "
                "FIX a BREACH is not BLOCKED by one, and no sweep ran — this "
                "gate did not ask about your branch and did not clear it"
            ),
        )

    # 2. The branch is already refused. Before step 3, so that the cheapest
    #    exit of all is not what a doomed branch is reported under.
    if already_violation:
        return BranchReachability(
            status=ReachabilitySweepStatus.NOT_REACHED_ALREADY_VIOLATION,
            obligation=obligation,
            detail=(
                "the cheap checks already refused this branch; the verdict "
                "cannot get worse than VIOLATION and a second reason changes "
                "nothing except the bill. The sweep runs on the next push"
            ),
        )

    # 3. The cheap exit, and DISPUTE D6's one line beside it.
    analyzable = analyzable_paths(changed_paths)
    appeal_changed = DECLARATION_PATH in tuple(changed_paths)
    if not analyzable and not appeal_changed:
        return BranchReachability(
            status=ReachabilitySweepStatus.NO_ANALYZABLE_FILE_IN_DIFF,
            obligation=obligation,
            detail=(
                f"none of the {len(tuple(changed_paths))} changed path(s) has "
                "an ANALYZERS row and none is "
                f"{DECLARATION_PATH}: a branch that changed no file any "
                "analyzer can read, and no appeal, changed no call edge this "
                "gate can see. Nothing the branch commits clears this, so it "
                "does not refuse"
            ),
        )

    try:
        return _swept_branch_reachability(
            Path(repo_root), base_ref, branch_ref, obligation, run
        )
    except BranchReachabilityError as exc:
        # DISPUTE D4's ruling, and the "never raise" obligation's last line.
        return BranchReachability(
            status=_APPEAL_UNREADABLE_STATUS,
            obligation=obligation,
            detail=str(exc),
        )
    except Exception as exc:  # noqa: BLE001 - see "never raise" above
        return BranchReachability(
            status=_APPEAL_UNREADABLE_STATUS,
            obligation=obligation,
            detail=(
                f"the reachability gate could not finish: {type(exc).__name__}: "
                f"{exc}. check_branch is contracted never to raise, so a fault "
                "here is a named refusal and never a traceback — but a refusal "
                "reported through this arm is a DEFECT in this module, not a "
                "fact about the branch, and it is meant to be read as one"
            ),
        )


def _abstention_reasons(report: ReachabilityReport) -> tuple[UndecidedReason, ...]:
    """Every abstention's :class:`UndecidedReason` in ``report``, in its order.

    Derived through :func:`~claude_dispatcher.call_site_reachability.adjudicate`
    — the shipped mechanism — rather than by reading ``finding.reason`` for
    truthiness, so that "what counts as an abstention" is answered in the one
    place that answers it. ``None`` is not filtered out: an abstention with no
    reason is a record that was never validated, and
    :func:`verdict_for_abstention` refuses it rather than picking a side.
    """
    return tuple(
        finding.reason
        for finding in report.findings
        if adjudicate(finding, None) is Disposition.ABSTAIN
    )


def _production_roots(report: ReachabilityReport) -> int:
    return sum(1 for root in report.roots if root.root_kind is RootKind.PRODUCTION)


def _swept_branch_reachability(
    repo_root: Path,
    base_ref: str,
    branch_ref: str,
    obligation: ReachabilityObligation,
    run: Callable[..., object] | None,
) -> BranchReachability:
    """Steps 4-9 of :func:`check_branch_reachability`. Never called elsewhere.

    Split out so that the entrypoint's "never raise" guard is one ``try`` around
    everything that can fail, rather than a guard per step that a later edit
    can slip past. Raises :class:`BranchReachabilityError`; the caller names it.
    """
    # 4. The head TREE must BE the checkout. check_branch reads blobs and never
    #    needs one; check_tree takes a directory. The assumption holds at both
    #    of today's call sites and an assumption that holds is still one.
    head_sha = _resolved_sha(repo_root, "HEAD", run)
    branch_sha = _resolved_sha(repo_root, branch_ref, run)
    if head_sha is None or branch_sha is None or head_sha != branch_sha:
        seen = head_sha or "an unresolvable HEAD"
        wanted = branch_sha or "unresolvable"
        return BranchReachability(
            status=ReachabilitySweepStatus.UNCHECKED_HEAD_NOT_CHECKED_OUT,
            obligation=obligation,
            detail=(
                f"{repo_root} is checked out at {seen} and branch_ref "
                f"{branch_ref} is {wanted}; there is no head TREE to sweep, "
                "and sweeping this one would judge the wrong revision and "
                "report CLEAN for it"
            ),
        )

    # 5. The base tree. DISPUTE D2: the REPOSITORY ROOT, both halves — the
    #    empty pathspec is the whole repository. Outside repo_root, and removed
    #    on every path including the failure ones.
    destination = Path(tempfile.mkdtemp(prefix="d7-base-tree-"))
    try:
        try:
            base_root = materialise_base_tree(
                repo_root, base_ref, "", destination, run=run
            )
        except BranchReachabilityError as exc:
            return BranchReachability(
                status=ReachabilitySweepStatus.UNCHECKED_BASE_UNAVAILABLE,
                obligation=obligation,
                detail=(
                    f"{exc}. A delta with one side missing is not a delta: "
                    "'then everything is new' refuses the branch for the whole "
                    "tree's standing set and 'then nothing is' clears it for "
                    "anything, and both are a verdict about a revision nobody "
                    "read"
                ),
            )

        # 5b. The appeals, from each ref's own object store. Read here so that
        #     check_tree computes the dispositions and the stale set.
        base_declarations = declarations_at(repo_root, base_ref, run=run)
        head_declarations = declarations_at(repo_root, branch_ref, run=run)

        # 6. Both sweeps, through the module global `check_tree`.
        try:
            base_report = check_tree(base_root, declarations=base_declarations)
            head_report = check_tree(repo_root, declarations=head_declarations)
        except CallSiteReachabilityError as exc:
            return BranchReachability(
                status=ReachabilitySweepStatus.UNCHECKED_ANALYZER_FAULT,
                obligation=obligation,
                detail=(
                    f"{exc}. Since D6 enrolment a tree holding a .go file on a "
                    "host with no usable `go` RAISES where it used to return a "
                    "silent empty report; a broken image must never clear a Go "
                    "branch"
                ),
            )
    finally:
        # 472 KB on a subtree, 273 MB on a whole tree — a gate that leaks
        # either is a gate someone turns off in a month.
        shutil.rmtree(destination, ignore_errors=True)

    counts = dict(
        head_seals_examined=head_report.seals_examined,
        base_seals_examined=base_report.seals_examined,
        head_production_roots=_production_roots(head_report),
    )

    # 7. Delta's own evasion, refused before the delta is believed.
    vacuous = sweep_is_vacuous(base_report, head_report)
    if vacuous is not None:
        return BranchReachability(
            status=ReachabilitySweepStatus.UNCHECKED_SWEEP_VACUOUS,
            obligation=obligation,
            head_dispositions=head_report.dispositions,
            base_dispositions=base_report.dispositions,
            stale_declarations=head_report.stale_declarations,
            detail=vacuous,
            **counts,
        )

    # 8. Nothing to say, said out loud.
    if head_report.seals_examined == 0 and base_report.seals_examined == 0:
        return BranchReachability(
            status=ReachabilitySweepStatus.NO_SEAL_IN_TREE,
            obligation=obligation,
            head_dispositions=head_report.dispositions,
            base_dispositions=base_report.dispositions,
            stale_declarations=head_report.stale_declarations,
            detail=(
                "both sweeps ran and neither found a seal; D5 judges the "
                "SUBJECTS OF SEALS, so a tree with no seal yields no finding "
                "and this gate has nothing to say about it. Nothing the branch "
                "commits changes that, so it does not refuse — and it is on "
                "the verdict line, because a CLEAN that does not say why is "
                "indistinguishable from a CLEAN that checked something"
            ),
            **counts,
        )

    # 9. The delta.
    introduced = introduced_findings(
        base_report,
        head_report,
        base_declarations=base_declarations,
        head_declarations=head_declarations,
    )
    return BranchReachability(
        status=ReachabilitySweepStatus.CHECKED,
        obligation=obligation,
        introduced=introduced,
        head_dispositions=head_report.dispositions,
        base_dispositions=base_report.dispositions,
        stale_declarations=head_report.stale_declarations,
        abstention_reasons=_abstention_reasons(head_report),
        detail=(
            f"{len(introduced)} finding(s) introduced by this branch, over "
            f"{head_report.seals_examined} seal(s) at head and "
            f"{base_report.seals_examined} at base; "
            f"{head_report.dispositions.get(Disposition.BREACH, 0)} BREACH and "
            f"{head_report.dispositions.get(Disposition.ACCEPTED, 0)} ACCEPTED "
            "stand in the tree, and this gate reports only what the branch "
            "added to them"
        ),
        **counts,
    )
