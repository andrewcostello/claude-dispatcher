"""Unit W2-3 — a durable ledger for mutation-coverage claims.

Run as ``python -m claude_dispatcher.mutation_ledger`` (:func:`main`);
``docs/mutation-ledger/README.md`` is the operator's guide.

A docstring clause is a CITATION here, never evidence. The evidence is a
ledger record, and there are two kinds, because the population this ledger
must cover has two kinds in it:

  * :class:`LedgerEntry` — an OBSERVATION. Admitted only by a pair of runs
    that could have refuted the claim: a control in which the claiming row is
    green, and a mutant in which it goes red. That pair is what a later
    reader RE-RUNS instead of re-reading.
  * :class:`Prediction` — a durable "no such pair exists". A clause naming a
    whole alternative implementation has no :class:`MutationOperator` to
    apply, so it can never yield an observation; recording WHY, at a
    revision, is what stops it being re-examined from scratch forever.

Neither kind reads prose: :attr:`LedgerEntry.note` is the one prose field on
an observation and no fold consults it.

Where the ledger lives
======================
:data:`LEDGER_DIR` — ``docs/mutation-ledger/``, one JSON Lines file per
subject module (:func:`ledger_path_for`). W2-3-3 owns the BODIES role, whose
rule denies ``tests/``, ``test_*.py``, ``*_test.py``, ``*.test.*``,
``testdata/`` and ``conftest.py``; a ledger sited under any of them could not
be created by the task that must create it.
:func:`refuse_unwritable_ledger_path` is that constraint as a check against
the role table itself, and :func:`ledger_path_for` runs it on its own result.

What the ids do and do not prove
================================
Every id here is a content digest, re-derived in ``__post_init__`` so none
can be typed at a call site. They prove a record is INTERNALLY CONSISTENT —
its digests, reddened set and control result are the ones its id names. They
are not attestations: anyone who can edit the file can recompute one, and
:func:`new_entry` hashes whatever it is handed. Only :func:`rederive`
measures, so a record does not count as coverage because its hashes
validate.

The 41 unlabelled clauses in ``tests/test_call_site_reachability.py``
=====================================================================
**None are migrated.** Copying a clause into a ledger does not make it
measured. Each is re-derived or found underivable (W2-3-3), and its TEXT is
then handled in place by SEALS (W2-3-2) under ADJUDICATE's ruling (W2-3-4) —
never by BODIES, which matches that file against its own deny globs and for
which deleting a forbidden file scores as touching it. :func:`proposed_fate`
maps each :class:`Status` to what is proposed; :data:`PREDICTION_FATE` is
the fixed fate of the other kind.
"""

from __future__ import annotations

import argparse
import ast
import datetime
import hashlib
import json
import math
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Sequence

from . import role_protocol, scratch_clone

#: Repo-relative, posix. One directory, checked against the role table by
#: :func:`refuse_unwritable_ledger_path`.
LEDGER_DIR = "docs/mutation-ledger"

#: JSON Lines, not a JSON array: a ledger is appended to and reviewed per
#: line, and an array re-indents every line when one entry changes.
LEDGER_SUFFIX = ".jsonl"

#: Bumped when :func:`canonical_line`'s key set changes. A reader meeting an
#: unknown version REFUSES; defaulting a missing digest to ``""`` would make
#: every observation read as un-drifted.
LEDGER_FORMAT_VERSION = 1

#: Ceiling on one observation's re-derivation, ~33x the measured 1.8 s. An
#: entry that exceeds it folds to :attr:`Status.FAULTED` and is reported; it
#: is never skipped, because a skip that reads as coverage is the defect this
#: unit exists to close.
PER_ENTRY_BUDGET_SECONDS = 60

_SHA40 = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")

#: A pytest node id at FUNCTION level: ``<path>.py::<name>`` with any number
#: of ``::``-separated class segments in front of the function, and no
#: ``[param]`` tail. Parametrisations are folded out by
#: :func:`fold_row_results` — a clause names its rows, and a parametrisation
#: added to a row must not read as the file growing.
_NODE_ID = re.compile(
    r"^(?P<path>[^\s\[\]]+\.py)::"
    r"(?P<qualname>[A-Za-z_][A-Za-z0-9_]*(?:::[A-Za-z_][A-Za-z0-9_]*)*)$")

#: A dotted anchor inside the subject module: ``func`` or ``Class.method``.
#: Not a line number — a line number is a claim about bytes that any edit
#: above it invalidates, and an anchor re-resolves against a changed body.
_ANCHOR = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*$")

#: Prefixed so a citation inside a docstring is greppable and the three id
#: kinds can neither be swapped nor mistaken for a git sha.
CLAIM_ID_PREFIX = "ml-"
OBSERVATION_ID_PREFIX = "mlo-"
PREDICTION_ID_PREFIX = "mlp-"
_CLAIM_ID_HEX = 12
_OBSERVATION_ID_HEX = 16
_PREDICTION_ID_HEX = 12
_CLAIM_ID = re.compile(rf"^{CLAIM_ID_PREFIX}[0-9a-f]{{{_CLAIM_ID_HEX}}}$")
_OBSERVATION_ID = re.compile(
    rf"^{OBSERVATION_ID_PREFIX}[0-9a-f]{{{_OBSERVATION_ID_HEX}}}$")
_PREDICTION_ID = re.compile(
    rf"^{PREDICTION_ID_PREFIX}[0-9a-f]{{{_PREDICTION_ID_HEX}}}$")

#: Any id as it appears cited inside a docstring, for :func:`check_citations`.
CITATION_ID = re.compile(
    rf"\b(?:{CLAIM_ID_PREFIX}[0-9a-f]{{{_CLAIM_ID_HEX}}}"
    rf"|{OBSERVATION_ID_PREFIX}[0-9a-f]{{{_OBSERVATION_ID_HEX}}}"
    rf"|{PREDICTION_ID_PREFIX}[0-9a-f]{{{_PREDICTION_ID_HEX}}})\b")


class MutationLedgerError(RuntimeError):
    """Every refusal this module raises.

    A refusal means the harness or a record is malformed. A claim that failed
    is never an exception — it is a :class:`Rederivation` carrying a
    :class:`Status`.
    """


# --------------------------------------------------------------------------- #
# Shared validators. Every path this module records names a file a later run
# will READ, MUTATE or EXECUTE inside a clone, and every constructor here is
# contracted as the thing the harness may trust — so containment is checked
# once, in one place, rather than per field.
# --------------------------------------------------------------------------- #


def _require_repo_path(value: object, *, name: str, suffix: str | None) -> str:
    """``value`` as a repo-relative posix path, or a refusal.

    Refuses an absolute path, a backslash, a NUL, an empty or ``.``/``..``
    component and a doubled separator, so no recorded path can address
    anything outside the tree it is resolved against. ``suffix`` is required
    when given.
    """
    if not isinstance(value, str) or not value:
        raise MutationLedgerError(f"{name} must be a non-empty string")
    if value.startswith("/") or "\\" in value or "\0" in value:
        raise MutationLedgerError(
            f"{name} must be a relative posix path without NUL: {value!r}")
    for part in value.split("/"):
        if part in ("", ".", ".."):
            raise MutationLedgerError(
                f"{name} {value!r} escapes or does not normalise: a path this "
                "module records is read, mutated and run inside a clone")
    if suffix is not None and not value.endswith(suffix):
        raise MutationLedgerError(f"{name} must end with {suffix!r}: {value!r}")
    return value


def _require_node_id(value: object, *, name: str) -> str:
    """``value`` as a function-level pytest node id whose file part is a
    contained repo-relative path."""
    if not isinstance(value, str) or not _NODE_ID.match(value):
        raise MutationLedgerError(
            f"{name} must be a function-level node id, got {value!r}")
    _require_repo_path(value.split("::", 1)[0], name=f"{name} path",
                       suffix=".py")
    return value


def _require_cost(value: object, *, name: str = "cost_seconds") -> float:
    """A non-negative, FINITE number of seconds.

    ``json`` admits ``NaN`` and ``Infinity`` by default, and ``NaN >
    PER_ENTRY_BUDGET_SECONDS`` is false — a timing failure recorded as NaN
    would round-trip and never fold to :attr:`Status.FAULTED`.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MutationLedgerError(f"{name} must be a number, got {value!r}")
    if not math.isfinite(value):
        raise MutationLedgerError(f"{name} must be finite, got {value!r}")
    if value < 0:
        raise MutationLedgerError(f"{name} must not be negative")
    return float(value)


def _require_day(value: object, *, name: str) -> str:
    """A real ``YYYY-MM-DD`` calendar day.

    Parsed, not shape-matched: the date is inside a derived id, so a nonsense
    day cannot be corrected without superseding the record that carries it.
    """
    if not isinstance(value, str):
        raise MutationLedgerError(f"{name} must be a string")
    try:
        if datetime.date.fromisoformat(value).isoformat() != value:
            raise ValueError
    except ValueError:
        raise MutationLedgerError(
            f"{name} must be a real YYYY-MM-DD date, got {value!r}") from None
    return value


class MutationOperator(Enum):
    """The closed set of mechanically applicable mutations.

    CLOSED is the load-bearing part: a free-prose mutation field would record
    un-runnable mutations, which is the docstring again. Each member is an
    edit to EXISTING bytes, resolved by :mod:`ast` against the subject's own
    source, so it re-applies to a body that has since changed — which is what
    lets an observation be re-derived at a LATER revision.

    A fifth member is a plan amendment and must arrive WITH an observation
    that exercises it: an operator no re-derivation applies will never fire
    and will be read as coverage.

    Deliberately NOT members: whole alternative implementations ("a body that
    maps any abstention onto a pass"). Those are not edits, so a clause
    naming one yields no observation at all — it is recorded as a
    :class:`Prediction` with reason
    :attr:`NonDerivable.NO_APPLICABLE_OPERATOR`, which is how the ledger
    represents a clause it can never measure instead of leaving it out.
    """

    #: Every statement after the docstring replaced by ``return None``.
    BODY_TO_NO_OP = "body_to_no_op"
    #: The ``raise`` inside the anchor's ``except`` handler replaced by
    #: ``continue``; ``argument`` names the caught exception, so a function
    #: with two handlers is unambiguous.
    RAISE_TO_CONTINUE = "raise_to_continue"
    #: Every statement after the docstring replaced by ``return <argument>``,
    #: where ``argument`` is a Python literal.
    RETURN_CONSTANT = "return_constant"
    #: An ``else`` arm appended to the anchor's total dispatch, returning
    #: ``argument``.
    ADD_DEFAULT_BRANCH = "add_default_branch"


class RowResult(Enum):
    """What one row did in one run.

    ABSENT is a member and not an absence: "the mutation stopped reddening
    it" and "the row is gone" are different facts, and reading the second as
    the first is a claim silently downgraded.
    """

    PASSED = "passed"
    FAILED = "failed"
    #: Not collected: renamed, deleted, or a collection error.
    ABSENT = "absent"
    #: Collected, neither passed nor failed — a setup or internal error. The
    #: assertion the claim is about was never reached.
    ERRORED = "errored"


class RederiveMode(Enum):
    """Which tree a re-derivation runs against, and therefore what it asks."""

    #: **Default.** Provision the TARGET revision (HEAD unless a caller names
    #: another) and compare its subject and population digests against the
    #: ones the observation recorded. The only mode in which
    #: :attr:`Drift.SUBJECT_BYTES` and :attr:`Drift.POPULATION` are
    #: expressible, and therefore the only mode that can answer "did the body
    #: change".
    AT_TARGET = "at_target"

    #: **Historical reproduction** — provision the observation's OWN revision
    #: and re-run it, asking "was this true at the revision it names". A
    #: caller may not also name a target: two answers to "which tree" is the
    #: defect this enum prevents. Because git is content-addressed a
    #: well-formed observation cannot show digest drift at its own revision,
    #: so a mismatch here is :attr:`Observation.HARNESS_FAULT`, not drift.
    #: Freshness is ANCHORED whenever the recorded revision can be
    #: provisioned, which makes :attr:`Status.BROKEN` — "never true" —
    #: reachable in this mode and :attr:`Status.EXPIRED` reachable only in
    #: the other. :attr:`Drift.REVISION_ABSENT` is the one drift expressible
    #: here, and it means no tree could be provisioned at all: the
    #: re-derivation reports :attr:`Observation.NOT_ATTEMPTED` with it.
    AT_RECORDED = "at_recorded"


class Drift(Enum):
    """One way the target tree has moved away from what an observation
    recorded.

    A re-derivation reports a SET, because these co-occur and each is worth
    reporting. :func:`freshness_of` folds the set for the total
    :func:`fold`; the set stays on :attr:`Rederivation.drift`, so the fold
    loses nothing.
    """

    #: The observation's own revision is not in this repository — rebased
    #: away, or garbage-collected. A PROVENANCE failure and nothing more:
    #: under :attr:`RederiveMode.AT_TARGET` the comparison still runs at the
    #: target tree, so such an observation can be re-observed and cited
    #: again; it can never fold to :attr:`Status.HELD`, because freshness is
    #: not ANCHORED while the tree it names cannot be audited. Kept OUT of
    #: :data:`HARD_ABSENCE` for exactly that reason.
    REVISION_ABSENT = "revision_absent"
    #: The subject file does not exist in the tree that was run.
    SUBJECT_ABSENT = "subject_absent"
    #: The mutation anchor does not resolve in that tree's source.
    SITE_ABSENT = "site_absent"
    #: The claiming row is not collected from the seal file there.
    ROW_ABSENT = "row_absent"
    #: The subject file's sha256 in the target differs from the recorded one
    #: — "a body that changed".
    SUBJECT_BYTES = "subject_bytes"
    #: The seal file's collected row set differs from the recorded one.
    #: Without this member a scope divergence caused by the FILE GROWING is
    #: indistinguishable from a regression, and reports as one forever.
    POPULATION = "population"


#: The drift members that make a comparison in the tree that was run
#: IMPOSSIBLE — there is nothing to mutate, nothing to anchor to, or no row
#: to watch. A property of the tree, never of the harness, which is why they
#: reach :func:`fold` as ordinary drift and not as
#: :attr:`Observation.HARNESS_FAULT`. :attr:`Drift.REVISION_ABSENT` is not
#: one of them: it blocks only the audit of the provenance, not the
#: comparison. Read by :func:`freshness_of` and named by :func:`fold`.
HARD_ABSENCE: tuple[Drift, ...] = (
    Drift.SUBJECT_ABSENT,
    Drift.SITE_ABSENT,
    Drift.ROW_ABSENT,
)


class Freshness(Enum):
    """:class:`Drift` folded to one value, so :func:`fold` is a table rather
    than a set-cover problem."""

    #: Provenance present, subject bytes and population match the record.
    #: The only member under which :attr:`Status.HELD` is reachable.
    ANCHORED = "anchored"
    #: The subject file's bytes differ from the record's.
    SUBJECT_MOVED = "subject_moved"
    #: The seal file's collected row set differs from the record's.
    POPULATION_MOVED = "population_moved"
    #: The recorded revision is gone, so the record's provenance cannot be
    #: audited. Comparable to the MOVED members and folded with them: the
    #: comparison at the target tree is still a real one.
    PROVENANCE_GONE = "provenance_gone"
    #: No subject file in the tree that was run.
    SUBJECT_GONE = "subject_gone"
    #: No resolvable anchor in it.
    SITE_GONE = "site_gone"
    #: The claiming row is not collected from the seal file.
    ROW_GONE = "row_gone"


class Observation(Enum):
    """What the control/mutant pair actually showed.

    The CONTROL is not a courtesy: a row that is red anyway proves nothing
    under a mutation, and without :attr:`CONTROL_RED` "red under the mutant"
    is satisfied by an unfilled stub.
    """

    #: Control green, claiming row red, reddened set equals the recorded set.
    REDDENED_AS_RECORDED = "reddened_as_recorded"
    #: Control green, claiming row red, reddened set differs.
    REDDENED_SCOPE_DIVERGED = "reddened_scope_diverged"
    #: Control green, claiming row NOT red — the claim is false here.
    SURVIVED = "survived"
    #: The claiming row FAILED in the control run: it was already red without
    #: the mutation.
    CONTROL_RED = "control_red"
    #: The mutation applied, and the claiming row could not be EVALUATED
    #: under it — it ERRORED, or it was collected and then not reported. Kept
    #: apart from :attr:`HARNESS_FAULT` because it is a deterministic
    #: property of (site, operator, tree): a mutation that breaks the row's
    #: setup reproduces on every re-run, so routing it to a state that waits
    #: parks the clause forever. It is also NOT :attr:`SURVIVED` — an error
    #: is not evidence that the mutation failed to bite, because the
    #: assertion was never reached.
    MUTANT_UNEVALUABLE = "mutant_unevaluable"
    #: No comparison was performed. A named state, so that "we did not look"
    #: is not expressible as "we looked and it was fine".
    NOT_ATTEMPTED = "not_attempted"
    #: The RUN failed, so it says nothing about the claim: a refused clone,
    #: an exceeded budget, an unusable pytest, a provisioned tree that is not
    #: the one the observation names, one run that produced no rows while the
    #: other did — or a claiming row that ERRORED or went unreported in the
    #: CONTROL, where the tree cannot execute the row even unmutated.
    #:
    #: Every cause is a fact about the RUN or the tree's health, never about
    #: the clause or the mutation, which is what lets :func:`fold` send this
    #: member and only this member to :attr:`ClauseFate.AWAIT_RERUN`: the
    #: repair is to the run, and until it is made the ledger proposes nothing
    #: about the clause. It is the one fate that does not converge, so
    #: nothing that is a fact about the CLAUSE, the MUTATION or the TREE'S
    #: CONTENT may reach it — a mutation the row cannot be evaluated under is
    #: :attr:`MUTANT_UNEVALUABLE`, and a tree that lacks the subject, the
    #: anchor or the row is :data:`HARD_ABSENCE` drift with
    #: :attr:`NOT_ATTEMPTED`. A control that cannot run the row IS such a
    #: fault: the tree is broken, which is a repo-level condition someone
    #: fixes, and not a disposition of the clause.
    HARNESS_FAULT = "harness_fault"


class Status(Enum):
    """The fold of :class:`Freshness` and :class:`Observation`.

    Seven members, four of them disagreements. Every combination folds to a
    NAMED state; none folds to "kept as it was", which is the outcome this
    unit forbids. The conditions are stated per member and are what
    :func:`fold` must implement.
    """

    #: ANCHORED and REDDENED_AS_RECORDED. The only member of
    #: :data:`READS_AS_COVERAGE`.
    HELD = "held"
    #: Reddened as recorded, but under bytes or a population the observation
    #: did not record. True, and owed a NEW observation before it may be
    #: cited: "still true under different bytes" reported as verified is how
    #: the 41 accumulated.
    REANCHORED = "reanchored"
    #: The row reddened and the SET did not match, at any freshness. Amended,
    #: not struck — half the claim is a real measurement.
    SCOPE_BROKEN = "scope_broken"
    #: ANCHORED and SURVIVED. The loudest state: nothing the observation
    #: names has moved, so the difference has no innocent explanation.
    BROKEN = "broken"
    #: SURVIVED under moved bytes or a moved population.
    EXPIRED = "expired"
    #: No refuting comparison was possible in this tree — NOT_ATTEMPTED,
    #: CONTROL_RED or MUTANT_UNEVALUABLE, at any freshness. Not a pass, not a
    #: failure, and not coverage. This is where a deleted row, a deleted
    #: subject, an unresolvable anchor, a mutation the row cannot be
    #: evaluated under, and a clause nothing can mutate all land, and it
    #: CONVERGES: :attr:`ClauseFate.RELABEL_PREDICTED` disposes of the clause
    #: without pretending a re-run could restore what the tree no longer has.
    UNDERIVABLE = "underivable"
    #: The run broke (HARNESS_FAULT), or the record contradicts itself — a
    #: subject, anchor or row reported ABSENT together with a COMPLETED
    #: comparison, which no honest harness can produce. Both are faults in
    #: the RUN rather than facts about the clause, which is why this and not
    #: UNDERIVABLE is the state that waits; keeping them apart is what stops
    #: a broken clone from relabelling a file.
    FAULTED = "faulted"


#: The one predicate answering "may a clause cite this observation as
#: evidence". A frozenset of ONE. :attr:`Status.REANCHORED` is TRUE and is
#: still not coverage until an observation is written that says so.
READS_AS_COVERAGE: frozenset[Status] = frozenset({Status.HELD})


class ClauseFate(Enum):
    """What happens to the docstring clause behind an observation.

    The EDIT belongs to SEALS (W2-3-2) under ADJUDICATE's ruling (W2-3-4),
    never to BODIES; see the module docstring.
    """

    #: Relabel in place to cite the CLAIM id — not the observation id, so the
    #: citation survives the claim being re-measured.
    CITE_CLAIM = "cite_claim"
    #: Write a new observation at the target tree, then cite the claim.
    REOBSERVE_THEN_CITE = "reobserve_then_cite"
    #: Keep the mutation sentence, replace the SCOPE sentence with the
    #: citation.
    AMEND_SCOPE = "amend_scope"
    #: Relabel in place to ``Predicted (unmeasured) under:``. A prediction is
    #: a legitimate state; a prediction spelled like a measurement is not.
    RELABEL_PREDICTED = "relabel_predicted"
    #: Strike the clause. Safe only because the observation outlives it.
    STRIKE = "strike"
    #: Nothing yet — repair the run, then re-derive. Reachable only from
    #: :attr:`Status.FAULTED`, and it is the one fate that does not dispose
    #: of the clause. That is why no fact about the CLAUSE, the MUTATION or
    #: the tree's CONTENT may reach :attr:`Status.FAULTED`: a clause may wait
    #: only while the repository itself cannot run it — a loud, visible
    #: condition someone repairs — and never on a disposition that waiting
    #: cannot change.
    AWAIT_RERUN = "await_rerun"


class NonDerivable(Enum):
    """Why a clause can never yield an observation, recorded on a
    :class:`Prediction`.

    Closed, and each member is a fact about the CLAUSE or the TREE that a
    later reader can check without running anything — which is what makes a
    prediction re-examinable rather than an opinion.
    """

    #: The clause names a whole alternative body ("a body that maps any
    #: abstention onto a pass"), not an edit to existing bytes, so no
    #: :class:`MutationOperator` applies. The bulk of the 41.
    NO_APPLICABLE_OPERATOR = "no_applicable_operator"
    #: The clause was measured against a reference implementation that has
    #: since been discarded, so its evidence expired with it and there is no
    #: body to re-apply the mutation to.
    REFERENCE_IMPLEMENTATION_DISCARDED = "reference_implementation_discarded"
    #: An operator applies in principle, but the clause names no site that
    #: resolves in the subject at ``revision``.
    ANCHOR_NOT_IN_SUBJECT = "anchor_not_in_subject"


#: The fate of every :class:`Prediction`, fixed rather than folded: a record
#: that no measurement is possible has no :class:`Status` to fold, and the
#: only honest label for the clause behind it is the one this repo already
#: uses — ``Predicted (unmeasured) under:``.
PREDICTION_FATE: ClauseFate = ClauseFate.RELABEL_PREDICTED


@dataclass(frozen=True)
class MutationSite:
    """Where a mutation is applied and what it does."""

    #: Repo-relative posix path of the file mutated.
    subject: str
    #: Dotted anchor inside it, resolved by :mod:`ast`.
    anchor: str
    operator: MutationOperator
    #: The operator's parameter — the exception name for RAISE_TO_CONTINUE,
    #: a Python literal for RETURN_CONSTANT and ADD_DEFAULT_BRANCH, ``""``
    #: for BODY_TO_NO_OP. Empty is only legal for the operator that takes no
    #: parameter; a silently ignored argument would make two different
    #: mutations share one identity.
    argument: str = ""

    def __post_init__(self) -> None:
        _require_repo_path(self.subject, name="subject", suffix=".py")
        if not isinstance(self.anchor, str) or not _ANCHOR.match(self.anchor):
            raise MutationLedgerError(f"anchor is not dotted: {self.anchor!r}")
        if not isinstance(self.operator, MutationOperator):
            raise MutationLedgerError(
                f"operator must be a MutationOperator, got {self.operator!r}")
        if not isinstance(self.argument, str):
            raise MutationLedgerError(
                f"argument must be a string, got {self.argument!r}")
        takes_argument = self.operator is not MutationOperator.BODY_TO_NO_OP
        if takes_argument and not self.argument:
            raise MutationLedgerError(
                f"{self.operator.value} needs an argument")
        if not takes_argument and self.argument:
            raise MutationLedgerError(
                f"{self.operator.value} takes no argument, got "
                f"{self.argument!r}; an ignored argument would give one "
                "mutation two identities")


@dataclass(frozen=True)
class LedgerEntry:
    """One observation: a claim, the tree it was taken on, and what was seen.

    Both ids are DERIVED and re-checked here, so neither can be typed. The
    claim id covers what is asserted; the observation id covers the evidence
    — revision, digests, reddened set, control and date — so a fresh
    observation of the same claim is a DIFFERENT entry that can name the one
    it :attr:`supersedes`.
    """

    claim_id: str
    observation_id: str
    #: Repo-relative posix path of the file holding the claiming clause.
    seal_file: str
    #: Function-level node id of the row that makes the claim; must live in
    #: ``seal_file``.
    claiming_row: str
    site: MutationSite
    #: The 40-char revision the observation was taken on. Abbreviations are
    #: refused: a prefix may resolve differently in a later repository.
    revision: str
    #: sha256 of the subject file at ``revision``, of the mutated bytes, and
    #: of the seal file's collected row set (:func:`population_digest`).
    subject_sha256: str
    mutant_sha256: str
    population_sha256: str
    #: The rows the mutation REDDENED: function-level node ids that were
    #: PASSED in the control and FAILED under the mutant, sorted and unique.
    #: A transition set, not "rows failing under the mutant" — see
    #: :func:`classify_observation`. Empty is legal and means the mutation
    #: was survived.
    reddened: tuple[str, ...]
    #: Whether the claiming row was GREEN in the control run. An observation
    #: with a red control refutes nothing; it is recorded so that the next
    #: run knows why.
    control_green: bool
    observed_on: str
    #: The observation id this one replaces, or None. The superseded entry
    #: stays in the ledger — it is the record of what was believed.
    supersedes: str | None = None
    cost_seconds: float = 0.0
    #: The one prose field. No fold in this module reads it.
    note: str = ""

    def __post_init__(self) -> None:
        for name in ("seal_file", "claiming_row", "revision", "subject_sha256",
                     "mutant_sha256", "population_sha256", "observed_on",
                     "note", "claim_id", "observation_id"):
            if not isinstance(getattr(self, name), str):
                raise MutationLedgerError(f"{name} must be a string")
        if not isinstance(self.site, MutationSite):
            raise MutationLedgerError("site must be a MutationSite")
        _require_repo_path(self.seal_file, name="seal_file", suffix=".py")
        _require_node_id(self.claiming_row, name="claiming_row")
        if not self.claiming_row.startswith(f"{self.seal_file}::"):
            raise MutationLedgerError(
                f"claiming_row {self.claiming_row!r} is not in seal_file "
                f"{self.seal_file!r}")
        if not _SHA40.match(self.revision):
            raise MutationLedgerError(
                f"revision must be a full 40-char lower-hex sha, got "
                f"{self.revision!r}")
        for name in ("subject_sha256", "mutant_sha256", "population_sha256"):
            if not _SHA256.match(getattr(self, name)):
                raise MutationLedgerError(f"{name} is not a sha256 digest")
        if self.subject_sha256 == self.mutant_sha256:
            raise MutationLedgerError(
                "mutant_sha256 equals subject_sha256: the mutation changed "
                "nothing, so the run compared a tree against itself")
        if not isinstance(self.reddened, tuple):
            raise MutationLedgerError("reddened must be a tuple")
        for node in self.reddened:
            _require_node_id(node, name="reddened")
        if list(self.reddened) != sorted(set(self.reddened)):
            raise MutationLedgerError(
                "reddened must be sorted and unique: an unordered set makes "
                "two records of one run compare unequal")
        if not isinstance(self.control_green, bool):
            raise MutationLedgerError(
                f"control_green must be a bool, got {self.control_green!r}")
        _require_day(self.observed_on, name="observed_on")
        if self.supersedes is not None:
            if not isinstance(self.supersedes, str) or not (
                    _OBSERVATION_ID.match(self.supersedes)):
                raise MutationLedgerError(
                    f"supersedes is not an observation id: "
                    f"{self.supersedes!r}")
            if self.supersedes == self.observation_id:
                raise MutationLedgerError(
                    "an entry cannot supersede itself")
        _require_cost(self.cost_seconds)
        want_claim = claim_id(seal_file=self.seal_file,
                              claiming_row=self.claiming_row, site=self.site)
        if self.claim_id != want_claim:
            raise MutationLedgerError(
                f"claim_id {self.claim_id!r} is not the id of this claim "
                f"({want_claim!r}): the id is derived, never assigned")
        want_observation = observation_id(
            claim=want_claim, revision=self.revision,
            subject_sha256=self.subject_sha256,
            mutant_sha256=self.mutant_sha256,
            population_sha256=self.population_sha256,
            reddened=self.reddened, control_green=self.control_green,
            observed_on=self.observed_on, supersedes=self.supersedes)
        if self.observation_id != want_observation:
            raise MutationLedgerError(
                f"observation_id {self.observation_id!r} is not the id of "
                f"this evidence ({want_observation!r})")


@dataclass(frozen=True)
class Rederivation:
    """The result of re-deriving one observation.

    :attr:`freshness` and :attr:`status` are DERIVED PROPERTIES, not stored
    fields: an incoherent triple is unrepresentable here rather than checked
    for, so no later run can emit one and no constructor argument can bypass
    it.
    """

    claim_id: str
    #: The observation compared against.
    observation_id: str
    mode: RederiveMode
    #: The revision actually provisioned and run.
    revision_run: str
    #: Every drift observed, in :class:`Drift` declaration order.
    drift: tuple[Drift, ...]
    observation: Observation
    #: Rows red under the mutant in THIS run, sorted, function-level.
    reddened_observed: tuple[str, ...] = ()
    #: Observed and not recorded — the record understated the blast radius.
    unexpected_rows: tuple[str, ...] = ()
    #: Recorded and not observed — coverage was LOST. Kept apart from
    #: ``unexpected_rows`` because :attr:`Status.SCOPE_BROKEN` does not
    #: distinguish them and the two mean opposite things.
    missing_rows: tuple[str, ...] = ()
    cost_seconds: float = 0.0
    #: Why, for the states that need a why. Prose, and read by nothing.
    detail: str = ""

    def __post_init__(self) -> None:
        if not _CLAIM_ID.match(self.claim_id):
            raise MutationLedgerError(f"not a claim id: {self.claim_id!r}")
        if not _OBSERVATION_ID.match(self.observation_id):
            raise MutationLedgerError(
                f"not an observation id: {self.observation_id!r}")
        if not isinstance(self.mode, RederiveMode):
            raise MutationLedgerError("mode must be a RederiveMode")
        if not isinstance(self.observation, Observation):
            raise MutationLedgerError("observation must be an Observation")
        if not _SHA40.match(self.revision_run):
            raise MutationLedgerError(
                f"revision_run must be a full 40-char sha, got "
                f"{self.revision_run!r}")
        if not isinstance(self.drift, tuple) or any(
                not isinstance(d, Drift) for d in self.drift):
            raise MutationLedgerError("drift must be a tuple of Drift")
        order = list(Drift)
        if list(self.drift) != sorted(set(self.drift), key=order.index):
            raise MutationLedgerError(
                "drift must be unique and in Drift declaration order")
        for name in ("reddened_observed", "unexpected_rows", "missing_rows"):
            rows = getattr(self, name)
            if not isinstance(rows, tuple):
                raise MutationLedgerError(f"{name} must be a tuple")
            for row in rows:
                _require_node_id(row, name=name)
            if list(rows) != sorted(set(rows)):
                raise MutationLedgerError(f"{name} must be sorted and unique")
        _require_cost(self.cost_seconds)

    @property
    def freshness(self) -> Freshness:
        """:attr:`drift` folded, via :func:`freshness_of`."""
        return freshness_of(self.drift)

    @property
    def status(self) -> Status:
        """The verdict, via :func:`fold`. Never stored, so never disagrees."""
        return fold(self.freshness, self.observation)


@dataclass(frozen=True)
class Prediction:
    """One clause that can never yield an observation, and why.

    The other half of the population this ledger must cover. A clause naming
    a whole alternative body has no :class:`MutationOperator` to apply, so
    :class:`LedgerEntry` cannot represent it and :func:`rederive` has nothing
    to run — but "we looked, and here is what makes it unmeasurable, at this
    revision, against these bytes" is a durable fact, and it is what stops
    the clause being re-adjudicated from scratch forever.

    Re-examined in place, not superseded: there is no evidence to preserve.
    ``revision``/``subject_sha256`` are what makes a stale one visible — a
    prediction taken against bytes the subject no longer has is owed another
    look.
    """

    prediction_id: str
    seal_file: str
    claiming_row: str
    #: The module the clause is about, so one ledger still holds one subject.
    subject: str
    #: The clause's mutation sentence, verbatim. Prose, and part of the id
    #: because it is WHAT WAS JUDGED unmeasurable; no fold reads it.
    described: str
    reason: NonDerivable
    #: The revision the judgement was made at, and the subject's bytes there.
    revision: str
    subject_sha256: str
    recorded_on: str
    note: str = ""

    def __post_init__(self) -> None:
        for name in ("prediction_id", "described", "note"):
            if not isinstance(getattr(self, name), str):
                raise MutationLedgerError(f"{name} must be a string")
        _require_repo_path(self.seal_file, name="seal_file", suffix=".py")
        _require_repo_path(self.subject, name="subject", suffix=".py")
        _require_node_id(self.claiming_row, name="claiming_row")
        if not self.claiming_row.startswith(f"{self.seal_file}::"):
            raise MutationLedgerError(
                f"claiming_row {self.claiming_row!r} is not in seal_file "
                f"{self.seal_file!r}")
        if not self.described.strip():
            raise MutationLedgerError(
                "described must quote the clause being judged unmeasurable; "
                "an empty one records a verdict with no subject")
        if not isinstance(self.reason, NonDerivable):
            raise MutationLedgerError("reason must be a NonDerivable")
        if not _SHA40.match(self.revision):
            raise MutationLedgerError(
                f"revision must be a full 40-char lower-hex sha, got "
                f"{self.revision!r}")
        if not _SHA256.match(self.subject_sha256):
            raise MutationLedgerError("subject_sha256 is not a sha256 digest")
        _require_day(self.recorded_on, name="recorded_on")
        want = prediction_id(
            seal_file=self.seal_file, claiming_row=self.claiming_row,
            subject=self.subject, described=self.described)
        if self.prediction_id != want:
            raise MutationLedgerError(
                f"prediction_id {self.prediction_id!r} is not the id of this "
                f"clause ({want!r}): the id is derived, never assigned")


#: Either kind of ledger record. One file holds both, discriminated on the
#: wire by ``kind``, so a reader sees every clause's disposition in one place
#: instead of having to know which of two files to look in.
LedgerRecord = LedgerEntry | Prediction


# --------------------------------------------------------------------------- #
# Identity, paths and records.
#
# Each fails SILENTLY when it is wrong: an id that drifts from what it names,
# a ledger the body role cannot write, a parsed line whose "false" became
# True, a ledger with two current observations for one claim.
# --------------------------------------------------------------------------- #


def _digest(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"),
                   ensure_ascii=False).encode("utf-8")).hexdigest()


def claim_id(*, seal_file: str, claiming_row: str, site: MutationSite) -> str:
    """The stable id of the claim ``(seal_file, claiming_row, site)`` names.

    Covers WHAT IS ASSERTED and nothing else, so it survives re-measurement:
    a docstring citing it stays correct when the evidence is replaced.
    """
    return CLAIM_ID_PREFIX + _digest({
        "seal_file": seal_file,
        "claiming_row": claiming_row,
        "subject": site.subject,
        "anchor": site.anchor,
        "operator": site.operator.value,
        "argument": site.argument,
    })[:_CLAIM_ID_HEX]


def observation_id(*, claim: str, revision: str, subject_sha256: str,
                   mutant_sha256: str, population_sha256: str,
                   reddened: Sequence[str], control_green: bool,
                   observed_on: str, supersedes: str | None) -> str:
    """The id of one piece of EVIDENCE for ``claim``.

    Covers the revision, the three digests, the reddened SET (canonicalised
    here, so a caller cannot mint two ids for one run by reordering), the
    control, the date, and the observation this one REPLACES.

    ``supersedes`` is in the digest because without it two identical re-runs
    of the same claim on the same tree on the same day collide, and the
    second could then neither be added nor supersede the first — the
    append-only history this ledger promises would be unavailable for exactly
    the case it exists for. With it, position in the supersession chain is
    part of identity: each re-observation is a distinct entry, and a re-added
    copy of an existing one is still correctly refused as a duplicate.

    ``cost_seconds`` and ``note`` are excluded: neither is evidence, and both
    vary between identical runs.
    """
    return OBSERVATION_ID_PREFIX + _digest({
        "claim": claim,
        "revision": revision,
        "subject_sha256": subject_sha256,
        "mutant_sha256": mutant_sha256,
        "population_sha256": population_sha256,
        "reddened": sorted(set(reddened)),
        "control_green": control_green,
        "observed_on": observed_on,
        "supersedes": supersedes,
    })[:_OBSERVATION_ID_HEX]


def prediction_id(*, seal_file: str, claiming_row: str, subject: str,
                  described: str) -> str:
    """The stable id of the clause a :class:`Prediction` disposes of.

    Covers what the clause SAYS — where it lives and the mutation sentence it
    names — and not the finding, so re-examining a clause at a later revision
    updates one record instead of accumulating a chain. There is no evidence
    to preserve: a prediction is the record that no measurement was possible.
    """
    return PREDICTION_ID_PREFIX + _digest({
        "seal_file": seal_file,
        "claiming_row": claiming_row,
        "subject": subject,
        "described": described,
    })[:_PREDICTION_ID_HEX]


def new_entry(*, seal_file: str, claiming_row: str, site: MutationSite,
              revision: str, subject_sha256: str, mutant_sha256: str,
              population_sha256: str, reddened: Sequence[str],
              control_green: bool, observed_on: str,
              supersedes: str | None = None, cost_seconds: float = 0.0,
              note: str = "") -> LedgerEntry:
    """A :class:`LedgerEntry` with both ids derived. The only way to make one
    without restating the derivation at the call site.

    It hashes what it is handed and nothing more: the ids that come out prove
    the record is self-consistent, never that any run occurred.
    :func:`rederive` is the only thing in this module that measures.
    """
    claim = claim_id(seal_file=seal_file, claiming_row=claiming_row, site=site)
    rows = tuple(sorted(set(reddened)))
    return LedgerEntry(
        claim_id=claim,
        observation_id=observation_id(
            claim=claim, revision=revision, subject_sha256=subject_sha256,
            mutant_sha256=mutant_sha256, population_sha256=population_sha256,
            reddened=rows, control_green=control_green,
            observed_on=observed_on, supersedes=supersedes),
        seal_file=seal_file, claiming_row=claiming_row, site=site,
        revision=revision, subject_sha256=subject_sha256,
        mutant_sha256=mutant_sha256, population_sha256=population_sha256,
        reddened=rows, control_green=control_green, observed_on=observed_on,
        supersedes=supersedes, cost_seconds=cost_seconds, note=note)


def new_prediction(*, seal_file: str, claiming_row: str, subject: str,
                   described: str, reason: NonDerivable, revision: str,
                   subject_sha256: str, recorded_on: str,
                   note: str = "") -> Prediction:
    """A :class:`Prediction` with its id derived."""
    return Prediction(
        prediction_id=prediction_id(
            seal_file=seal_file, claiming_row=claiming_row, subject=subject,
            described=described),
        seal_file=seal_file, claiming_row=claiming_row, subject=subject,
        described=described, reason=reason, revision=revision,
        subject_sha256=subject_sha256, recorded_on=recorded_on, note=note)


def refuse_unwritable_ledger_path(path: str) -> None:
    """Refuse a ledger path that is not one BODIES could create.

    Two conditions, and both are hard constraints from W2-3's task graph
    rather than preferences:

      * inside :data:`LEDGER_DIR` and carrying :data:`LEDGER_SUFFIX`. Without
        this the check answers "some role may write it", which any file in
        the repository satisfies.
      * off :data:`role_protocol.FLOOR_GLOBS`, and permitted by the BODIES
        rule as :func:`role_protocol.evaluate_changed_paths` evaluates it.

    That evaluator is used rather than a glob scan because it is the one
    thing that is TOTAL over :class:`role_protocol.RuleKind` and that applies
    :data:`role_protocol.SEAL_VERIFY_TEST_PATHS`, which carries no wildcard
    and which a glob match therefore misses. Reading the globs directly and
    treating them as a deny list gives the right answer only while BODIES
    stays DENY_GLOBS: inverted to ALLOW_ONLY_GLOBS the same code silently
    inverts and passes every path outside the allow list.

    It is the STATIC table rule, not :func:`role_protocol.effective_rule`,
    because that one needs a ``TaskRoleSpec`` and this check has no task in
    hand. The difference is one-directional and safe: for DENY_GLOBS a row's
    ``added_immutable_globs`` only ever adds denials. So passing here is
    NECESSARY and not sufficient — a task row may still deny the path, and
    the branch gate is what says so.
    """
    _require_repo_path(path, name="ledger path", suffix=LEDGER_SUFFIX)
    if not path.startswith(f"{LEDGER_DIR}/") or "/" in path[len(LEDGER_DIR)+1:]:
        raise MutationLedgerError(
            f"ledger path {path!r} is not a file directly under "
            f"{LEDGER_DIR}/")
    floored = role_protocol.first_matching_glob(
        path, role_protocol.FLOOR_GLOBS)
    if floored is not None:
        raise MutationLedgerError(
            f"ledger path {path!r} is on the floor ({floored}): no role may "
            "write it, W2-3-3 included")
    rule = role_protocol.built_in_policy().rule_for(role_protocol.Role.BODIES)
    violations = role_protocol.evaluate_changed_paths(rule, (path,))
    if violations:
        raise MutationLedgerError(
            f"ledger path {path!r} is not writable by BODIES "
            f"({violations[0].matched_glob}); W2-3-3 builds the ledger and "
            "could not create it there")


def ledger_path_for(subject: str) -> str:
    """The ledger path for one subject module, refusing an unwritable one.

    ``src/claude_dispatcher/call_site_reachability.py`` →
    ``docs/mutation-ledger/claude_dispatcher.call_site_reachability.jsonl``.
    One ledger per subject, so a re-derivation reads one file rather than
    scanning every claim in the repository.

    The encoding must be INJECTIVE, since a collision would force two
    modules to share a file that :func:`validate_ledger` then refuses for
    holding two subjects. Separators become dots, so a dot inside a path
    segment is refused rather than encoded: ``pkg/a.b.py`` and ``pkg/a/b.py``
    would otherwise be one path.
    """
    _require_repo_path(subject, name="subject", suffix=".py")
    stem = subject[: -len(".py")]
    if stem.startswith("src/"):
        stem = stem[len("src/"):]
    if not stem or any("." in part for part in stem.split("/")):
        raise MutationLedgerError(
            f"subject {subject!r} has a dot inside a path segment, which "
            "would collide with another module's ledger path")
    path = f"{LEDGER_DIR}/{stem.replace('/', '.')}{LEDGER_SUFFIX}"
    refuse_unwritable_ledger_path(path)
    return path


def fold_row_results(results: Mapping[str, RowResult]) -> dict[str, RowResult]:
    """Parametrised node ids folded to the ROWS a clause names.

    ``f.py::t[a]`` and ``f.py::t[b]`` are one row. Precedence ERRORED >
    FAILED > PASSED > ABSENT: a row with one red parametrisation is red, and
    a row is ABSENT only when every parametrisation is.
    """
    precedence = (RowResult.ERRORED, RowResult.FAILED, RowResult.PASSED,
                  RowResult.ABSENT)
    folded: dict[str, RowResult] = {}
    for node, result in results.items():
        if not isinstance(result, RowResult):
            raise MutationLedgerError(
                f"{node!r} maps to {result!r}, not a RowResult")
        row = node.split("[", 1)[0]
        if not _NODE_ID.match(row):
            raise MutationLedgerError(f"not a pytest node id: {node!r}")
        seen = folded.get(row)
        if seen is None or precedence.index(result) < precedence.index(seen):
            folded[row] = result
    return folded


def population_digest(rows: Sequence[str]) -> str:
    """sha256 over a seal file's collected ROW set.

    Sorted and de-duplicated, so collection order cannot move it. This is the
    digest that makes :attr:`Drift.POPULATION` — a file that grew — a
    reportable fact rather than a mystery scope divergence.
    """
    unique = sorted(set(rows))
    for row in unique:
        if not _NODE_ID.match(row):
            raise MutationLedgerError(
                f"population holds a non function-level node id: {row!r}")
    return hashlib.sha256(
        ("\n".join(unique) + "\n").encode("utf-8")).hexdigest()


def source_digest(source: bytes) -> str:
    """sha256 of a subject file's bytes, as recorded on an entry."""
    if not isinstance(source, bytes):
        raise MutationLedgerError("source_digest takes bytes")
    return hashlib.sha256(source).hexdigest()


#: The wire discriminator. One ledger holds both kinds, and a reader that
#: guessed the kind from which keys are present would read a truncated
#: observation as a prediction.
OBSERVATION_KIND = "observation"
PREDICTION_KIND = "prediction"

_OBSERVATION_KEYS: frozenset[str] = frozenset({
    "version", "kind", "claim_id", "observation_id", "seal_file",
    "claiming_row", "subject", "anchor", "operator", "argument", "revision",
    "subject_sha256", "mutant_sha256", "population_sha256", "reddened",
    "control_green", "observed_on", "supersedes", "cost_seconds", "note",
})

_PREDICTION_KEYS: frozenset[str] = frozenset({
    "version", "kind", "prediction_id", "seal_file", "claiming_row",
    "subject", "described", "reason", "revision", "subject_sha256",
    "recorded_on", "note",
})


def canonical_line(record: LedgerRecord) -> str:
    """One record as one JSON line, round-tripping through :func:`parse_line`.

    Sorted keys and no spaces, so a re-written ledger diffs only where a fact
    changed.
    """
    if isinstance(record, LedgerEntry):
        payload: dict[str, Any] = {
            "version": LEDGER_FORMAT_VERSION,
            "kind": OBSERVATION_KIND,
            "claim_id": record.claim_id,
            "observation_id": record.observation_id,
            "seal_file": record.seal_file,
            "claiming_row": record.claiming_row,
            "subject": record.site.subject,
            "anchor": record.site.anchor,
            "operator": record.site.operator.value,
            "argument": record.site.argument,
            "revision": record.revision,
            "subject_sha256": record.subject_sha256,
            "mutant_sha256": record.mutant_sha256,
            "population_sha256": record.population_sha256,
            "reddened": list(record.reddened),
            "control_green": record.control_green,
            "observed_on": record.observed_on,
            "supersedes": record.supersedes,
            "cost_seconds": record.cost_seconds,
            "note": record.note,
        }
    elif isinstance(record, Prediction):
        payload = {
            "version": LEDGER_FORMAT_VERSION,
            "kind": PREDICTION_KIND,
            "prediction_id": record.prediction_id,
            "seal_file": record.seal_file,
            "claiming_row": record.claiming_row,
            "subject": record.subject,
            "described": record.described,
            "reason": record.reason.value,
            "revision": record.revision,
            "subject_sha256": record.subject_sha256,
            "recorded_on": record.recorded_on,
            "note": record.note,
        }
    else:
        raise MutationLedgerError(f"not a ledger record: {record!r}")
    return json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False)


def _typed(obj: Mapping[str, Any], key: str, kind: type) -> Any:
    """One field of a ledger line, at its JSON type or a refusal.

    NO COERCION anywhere in this reader. ``bool("false")`` is True and
    ``float("0")`` is 0.0 — the directions that turn a refuted claim into a
    confirmed one and a blown budget into a free run. A wrong JSON type is a
    corrupt record, so it fails closed.
    """
    if key not in obj:
        raise MutationLedgerError(f"ledger line is missing {key!r}")
    value = obj[key]
    if kind is bool:
        if not isinstance(value, bool):
            raise MutationLedgerError(
                f"{key} must be a JSON boolean, got {value!r}")
        return value
    if kind is float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise MutationLedgerError(
                f"{key} must be a JSON number, got {value!r}")
        return float(value)
    if not isinstance(value, kind) or isinstance(value, bool):
        raise MutationLedgerError(
            f"{key} must be a JSON {kind.__name__}, got {value!r}")
    return value


def parse_line(line: str) -> LedgerRecord:
    """One ledger line back to a record, or a refusal.

    Refuses a missing key, an unknown key, an unknown ``version`` or ``kind``
    and any field at the wrong JSON type. ``allow_nan=False``, so the
    ``NaN``/``Infinity`` tokens CPython's decoder accepts by default cannot
    enter a cost that is compared against
    :data:`PER_ENTRY_BUDGET_SECONDS` — every comparison with NaN is false,
    and a timing failure recorded that way would never fold to
    :attr:`Status.FAULTED`. Field-level validation is the dataclass's, which
    this runs, so a hand-edited digest or a forged id is refused on the way
    in.
    """
    try:
        obj = json.loads(line, parse_constant=_refuse_json_constant)
    except json.JSONDecodeError as exc:
        raise MutationLedgerError(f"not a JSON line: {exc}") from None
    if not isinstance(obj, dict):
        raise MutationLedgerError(
            f"ledger line is not a JSON object: {type(obj).__name__}")
    version = _typed(obj, "version", int)
    if version != LEDGER_FORMAT_VERSION:
        raise MutationLedgerError(
            f"unknown ledger format version {version!r}: this reader knows "
            f"{LEDGER_FORMAT_VERSION}, and reading an older line by "
            "defaulting its missing fields would report drift as absent")
    kind = _typed(obj, "kind", str)
    if kind == OBSERVATION_KIND:
        return _parse_observation(obj)
    if kind == PREDICTION_KIND:
        return _parse_prediction(obj)
    raise MutationLedgerError(f"unknown ledger record kind {kind!r}")


def _refuse_json_constant(name: str) -> float:
    raise MutationLedgerError(
        f"ledger line contains the JSON constant {name}, which no measured "
        "quantity can be")


def _refuse_unknown_keys(obj: Mapping[str, Any],
                         known: frozenset[str]) -> None:
    """An unknown key is refused rather than dropped: a field a reader
    silently ignores is a fact nobody records."""
    unknown = sorted(set(obj) - known)
    if unknown:
        raise MutationLedgerError(f"ledger line has unknown key(s) {unknown}")


def _parse_observation(obj: Mapping[str, Any]) -> LedgerEntry:
    _refuse_unknown_keys(obj, _OBSERVATION_KEYS)
    operator_name = _typed(obj, "operator", str)
    try:
        operator = MutationOperator(operator_name)
    except ValueError:
        raise MutationLedgerError(
            f"unknown operator {operator_name!r}: MutationOperator is closed, "
            "and a mutation nothing can apply is not an observation"
        ) from None
    reddened = _typed(obj, "reddened", list)
    if any(not isinstance(r, str) for r in reddened):
        raise MutationLedgerError("reddened must be a list of strings")
    if "supersedes" not in obj:
        raise MutationLedgerError("ledger line is missing 'supersedes'")
    supersedes = obj["supersedes"]
    if supersedes is not None and not isinstance(supersedes, str):
        raise MutationLedgerError(
            f"supersedes must be a string or null, got {supersedes!r}")
    return LedgerEntry(
        claim_id=_typed(obj, "claim_id", str),
        observation_id=_typed(obj, "observation_id", str),
        seal_file=_typed(obj, "seal_file", str),
        claiming_row=_typed(obj, "claiming_row", str),
        site=MutationSite(
            subject=_typed(obj, "subject", str),
            anchor=_typed(obj, "anchor", str),
            operator=operator,
            argument=_typed(obj, "argument", str)),
        revision=_typed(obj, "revision", str),
        subject_sha256=_typed(obj, "subject_sha256", str),
        mutant_sha256=_typed(obj, "mutant_sha256", str),
        population_sha256=_typed(obj, "population_sha256", str),
        reddened=tuple(reddened),
        control_green=_typed(obj, "control_green", bool),
        observed_on=_typed(obj, "observed_on", str),
        supersedes=supersedes,
        cost_seconds=_typed(obj, "cost_seconds", float),
        note=_typed(obj, "note", str))


def _parse_prediction(obj: Mapping[str, Any]) -> Prediction:
    _refuse_unknown_keys(obj, _PREDICTION_KEYS)
    reason_name = _typed(obj, "reason", str)
    try:
        reason = NonDerivable(reason_name)
    except ValueError:
        raise MutationLedgerError(
            f"unknown non-derivable reason {reason_name!r}: NonDerivable is "
            "closed, and a reason nothing can check is prose") from None
    return Prediction(
        prediction_id=_typed(obj, "prediction_id", str),
        seal_file=_typed(obj, "seal_file", str),
        claiming_row=_typed(obj, "claiming_row", str),
        subject=_typed(obj, "subject", str),
        described=_typed(obj, "described", str),
        reason=reason,
        revision=_typed(obj, "revision", str),
        subject_sha256=_typed(obj, "subject_sha256", str),
        recorded_on=_typed(obj, "recorded_on", str),
        note=_typed(obj, "note", str))


def observations(records: Sequence[LedgerRecord]) -> tuple[LedgerEntry, ...]:
    """Just the observations, in file order."""
    return tuple(r for r in records if isinstance(r, LedgerEntry))


def predictions(records: Sequence[LedgerRecord]) -> tuple[Prediction, ...]:
    """Just the predictions, in file order."""
    return tuple(r for r in records if isinstance(r, Prediction))


def current_observations(
        records: Sequence[LedgerRecord]) -> dict[str, LedgerEntry]:
    """The one live observation per claim: the entry no other supersedes.

    Superseded entries stay in the ledger as the record of what was believed
    and when.

    REFUSES a claim with two live entries rather than projecting one of them.
    This is the reader every consumer of "is this claim covered" goes
    through, and picking the later one by file order is the exact failure
    :func:`validate_ledger` exists to name; a public reader that quietly
    answers anyway makes that validator advisory.
    """
    entries = observations(records)
    replaced = {e.supersedes for e in entries if e.supersedes is not None}
    live: dict[str, LedgerEntry] = {}
    for entry in entries:
        if entry.observation_id in replaced:
            continue
        clash = live.get(entry.claim_id)
        if clash is not None:
            raise MutationLedgerError(
                f"claim {entry.claim_id} has two current observations "
                f"({clash.observation_id}, {entry.observation_id}); there is "
                "no rule by which one of them is the answer")
        live[entry.claim_id] = entry
    return live


def validate_ledger(records: Sequence[LedgerRecord]) -> None:
    """Refuse a ledger whose records cannot all be true at once.

    One subject per ledger; unique ids of both kinds; a ``supersedes`` link
    that resolves, within the same claim, to an entry that appears EARLIER;
    at most one entry superseding any given one; and exactly one current
    observation per claim.

    A CLAIMING ROW MAY CARRY BOTH KINDS, and that is not a contradiction to
    be refused. The rows in the population this ledger is built for name
    several clauses each — ``tests/test_call_site_reachability.py`` writes
    them as semicolon lists, one sentence naming a whole alternative body
    (which no operator can reach) beside one naming an edit to existing bytes
    (which one can). Refusing the pair at ROW granularity makes such a row
    unrecordable, and the way out of a hard refusal is to drop the
    prediction and keep the observation — which leaves the unmeasurable
    clause unrecorded, and an unrecorded clause reading as coverage is the
    defect this unit exists to close.

    Per-CLAUSE exclusivity is the check that would be right, and it is not
    expressible with the fields here: :func:`claim_id` identifies a clause by
    ``(row, site)`` and :func:`prediction_id` by ``(row, described)``, so the
    two kinds share no clause key. Adding one is recorded as owed to
    W2-3-2/3/5, not silently approximated by a rule that refuses true
    records.
    """
    entries = observations(records)
    subjects = {e.site.subject for e in entries}
    subjects |= {p.subject for p in predictions(records)}
    if len(subjects) > 1:
        raise MutationLedgerError(
            f"one ledger per subject module, got {sorted(subjects)}")
    seen_predictions: set[str] = set()
    for prediction in predictions(records):
        if prediction.prediction_id in seen_predictions:
            raise MutationLedgerError(
                f"duplicate prediction {prediction.prediction_id}")
        seen_predictions.add(prediction.prediction_id)
    by_observation: dict[str, LedgerEntry] = {}
    superseders: dict[str, str] = {}
    for entry in entries:
        if entry.observation_id in by_observation:
            raise MutationLedgerError(
                f"duplicate observation {entry.observation_id}")
        if entry.supersedes is not None:
            target = by_observation.get(entry.supersedes)
            if target is None:
                raise MutationLedgerError(
                    f"{entry.observation_id} supersedes "
                    f"{entry.supersedes}, which is not an earlier entry here")
            if target.claim_id != entry.claim_id:
                raise MutationLedgerError(
                    f"{entry.observation_id} supersedes an observation of a "
                    "different claim")
            if entry.supersedes in superseders:
                raise MutationLedgerError(
                    f"{entry.supersedes} is superseded twice, by "
                    f"{superseders[entry.supersedes]} and "
                    f"{entry.observation_id}")
            superseders[entry.supersedes] = entry.observation_id
        by_observation[entry.observation_id] = entry
    # Called for its refusal: two live observations for one claim is the
    # reader's rule, and re-deriving it here would be a second answer.
    current_observations(records)


def counts_as_coverage(status: Status) -> bool:
    """Whether a clause may cite an observation with ``status`` as evidence.

    Reads :data:`READS_AS_COVERAGE`, which is the single definition; a second
    predicate spelling it out again is a second answer waiting to drift.
    """
    if not isinstance(status, Status):
        raise MutationLedgerError(f"not a Status: {status!r}")
    return status in READS_AS_COVERAGE


# --------------------------------------------------------------------------- #
# THE FOUR FOLDS. The behaviour is specified on the enum members; these are
# the tables. Sealed by tests/test_mutation_ledger.py by VALUE, cell by cell.
# --------------------------------------------------------------------------- #


#: :func:`freshness_of`'s precedence, first match wins. NOT :class:`Drift`
#: declaration order: ``REVISION_ABSENT`` is declared first and ranks fourth,
#: because it blocks the audit of the record and not the comparison.
_FRESHNESS_PRECEDENCE: tuple[tuple[Drift, Freshness], ...] = (
    (Drift.SUBJECT_ABSENT, Freshness.SUBJECT_GONE),
    (Drift.SITE_ABSENT, Freshness.SITE_GONE),
    (Drift.ROW_ABSENT, Freshness.ROW_GONE),
    (Drift.REVISION_ABSENT, Freshness.PROVENANCE_GONE),
    (Drift.SUBJECT_BYTES, Freshness.SUBJECT_MOVED),
    (Drift.POPULATION, Freshness.POPULATION_MOVED),
)

_NO_COMPARISON: frozenset[Observation] = frozenset({
    Observation.NOT_ATTEMPTED, Observation.CONTROL_RED,
    Observation.MUTANT_UNEVALUABLE,
})

_GONE: frozenset[Freshness] = frozenset({
    Freshness.SUBJECT_GONE, Freshness.SITE_GONE, Freshness.ROW_GONE,
})

_FATES: dict[Status, ClauseFate] = {
    Status.HELD: ClauseFate.CITE_CLAIM,
    Status.REANCHORED: ClauseFate.REOBSERVE_THEN_CITE,
    Status.SCOPE_BROKEN: ClauseFate.AMEND_SCOPE,
    Status.BROKEN: ClauseFate.STRIKE,
    Status.EXPIRED: ClauseFate.STRIKE,
    Status.UNDERIVABLE: ClauseFate.RELABEL_PREDICTED,
    Status.FAULTED: ClauseFate.AWAIT_RERUN,
}


def freshness_of(drift: Sequence[Drift]) -> Freshness:
    """The observed drift set folded to one :class:`Freshness`.

    Precedence: the :data:`HARD_ABSENCE` members in declaration order, then
    :attr:`Drift.REVISION_ABSENT`, then :attr:`Drift.SUBJECT_BYTES`, then
    :attr:`Drift.POPULATION`; empty is :attr:`Freshness.ANCHORED`. Absence
    of the thing being compared outranks a difference in it, and a missing
    provenance outranks a moved body because it blocks the audit rather than
    the comparison. The full set stays on :attr:`Rederivation.drift`.
    """
    observed: set[Drift] = set()
    for member in drift:
        if not isinstance(member, Drift):
            raise MutationLedgerError(f"not a Drift: {member!r}")
        observed.add(member)
    for member, freshness in _FRESHNESS_PRECEDENCE:
        if member in observed:
            return freshness
    return Freshness.ANCHORED


def transition_set(control: Mapping[str, RowResult],
                   mutant: Mapping[str, RowResult]) -> tuple[str, ...]:
    """The rows PASSED in ``control`` and FAILED in ``mutant``, sorted.

    The one definition of "reddened": a baseline failure is never credited to
    the mutation, and a row the mutant could not evaluate is not a failure.
    """
    return tuple(sorted(
        row for row, after in mutant.items()
        if after is RowResult.FAILED
        and control.get(row) is RowResult.PASSED))


def classify_observation(*, control: Mapping[str, RowResult],
                         mutant: Mapping[str, RowResult], claiming_row: str,
                         recorded_reddened: Sequence[str]) -> Observation:
    """What one control/mutant pair showed, over ROW-level results.

    Both maps are row-level (:func:`fold_row_results` first). The arms are
    reached in this order and the order is the contract: both maps empty is
    NOT_ATTEMPTED; exactly one empty is HARNESS_FAULT; the claiming row
    ERRORED or ABSENT in the control is HARNESS_FAULT (``rederive`` resolves a
    genuinely uncollected row as drift before calling this, so ABSENT here is
    "collected and never reported"); FAILED in the control is CONTROL_RED,
    checked before the mutant so a row that was red anyway never reads as
    reddened; ERRORED or ABSENT under the mutant is MUTANT_UNEVALUABLE, not
    SURVIVED and not a fault; PASSED under the mutant is SURVIVED; otherwise
    the PASSED-to-FAILED :func:`transition_set` is compared with
    ``recorded_reddened`` as sets.

    A ``claiming_row`` missing from a non-empty map is refused: the contract
    does not define it, and answering would invent a disposition.
    """
    for name, results in (("control", control), ("mutant", mutant)):
        for row, result in results.items():
            if not isinstance(result, RowResult):
                raise MutationLedgerError(
                    f"{name}[{row!r}] is {result!r}, not a RowResult")
    if not control and not mutant:
        return Observation.NOT_ATTEMPTED
    if not control or not mutant:
        return Observation.HARNESS_FAULT
    if claiming_row not in control or claiming_row not in mutant:
        raise MutationLedgerError(
            f"claiming row {claiming_row!r} is not in both result maps; "
            "rederive resolves the row against the tree before classifying")
    before = control[claiming_row]
    if before in (RowResult.ERRORED, RowResult.ABSENT):
        return Observation.HARNESS_FAULT
    if before is RowResult.FAILED:
        return Observation.CONTROL_RED
    after = mutant[claiming_row]
    if after in (RowResult.ERRORED, RowResult.ABSENT):
        return Observation.MUTANT_UNEVALUABLE
    if after is RowResult.PASSED:
        return Observation.SURVIVED
    if set(transition_set(control, mutant)) == set(recorded_reddened):
        return Observation.REDDENED_AS_RECORDED
    return Observation.REDDENED_SCOPE_DIVERGED


def fold(freshness: Freshness, observation: Observation) -> Status:
    """:class:`Freshness` and :class:`Observation` folded to one
    :class:`Status`, total over 7 x 7.

    Precedence: HARNESS_FAULT is FAULTED at any freshness; NOT_ATTEMPTED,
    CONTROL_RED and MUTANT_UNEVALUABLE are UNDERIVABLE at any freshness (this
    arm is BEFORE the absence arm: a deleted row arrives as absence drift with
    NOT_ATTEMPTED and must be disposed of, not parked); a completed
    comparison under a GONE freshness is a record contradicting itself,
    FAULTED; REDDENED_SCOPE_DIVERGED is SCOPE_BROKEN; ANCHORED folds
    REDDENED_AS_RECORDED to HELD and SURVIVED to BROKEN; every moved freshness
    folds them to REANCHORED and EXPIRED. A non-member is refused, never
    defaulted.
    """
    if not isinstance(freshness, Freshness):
        raise MutationLedgerError(f"not a Freshness: {freshness!r}")
    if not isinstance(observation, Observation):
        raise MutationLedgerError(f"not an Observation: {observation!r}")
    if observation is Observation.HARNESS_FAULT:
        return Status.FAULTED
    if observation in _NO_COMPARISON:
        return Status.UNDERIVABLE
    if freshness in _GONE:
        return Status.FAULTED
    if observation is Observation.REDDENED_SCOPE_DIVERGED:
        return Status.SCOPE_BROKEN
    reddened = observation is Observation.REDDENED_AS_RECORDED
    if freshness is Freshness.ANCHORED:
        return Status.HELD if reddened else Status.BROKEN
    return Status.REANCHORED if reddened else Status.EXPIRED


def proposed_fate(status: Status) -> ClauseFate:
    """What is PROPOSED for the clause behind an observation with ``status``.

    Proposed, not applied: W2-3-4 rules and SEALS edits. A :class:`Status`
    with no fate is refused, so a new member cannot ship unruled.
    :data:`PREDICTION_FATE` covers the other record kind.
    """
    if not isinstance(status, Status):
        raise MutationLedgerError(f"not a Status: {status!r}")
    fate = _FATES.get(status)
    if fate is None:
        raise MutationLedgerError(f"{status!r} has no ruled fate")
    return fate


# --------------------------------------------------------------------------- #
# The harness. Every subprocess is bounded and killed as a process group; every
# refusal is a raise, never a short or empty result.
# --------------------------------------------------------------------------- #

#: What a re-derivation reports as ``revision_run`` when NOTHING was
#: provisioned. Never the recorded revision — that would be fabricated
#: provenance — and not a real sha, so it cannot be mistaken for one.
NULL_REVISION = "0" * 40

#: Bound on any git child and on a pytest run made outside :func:`rederive`
#: (which bounds its runs by the entry budget instead).
RUN_TIMEOUT_SECONDS = 600

#: How long :func:`_run_bounded` waits for a killed group to be reaped. The
#: handler for an exceeded bound must itself be bounded, or a group that
#: could not be signalled leaves the runner waiting on a pipe forever.
KILL_GRACE_SECONDS = 10

#: Directory names never scanned for citations: tool state, and the ledger
#: itself, whose records name their own ids and are not citations.
_UNSCANNED_DIRS: frozenset[str] = frozenset({
    ".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    ".venv", "venv", "node_modules", ".tox",
})

#: Loaded into every nested pytest run to record the COLLECTED node ids.
#: A row collected and then never reported is what separates ABSENT from
#: PASSED, and neither the summary line nor the junit file carries it.
_COLLECT_PLUGIN = '''import os


def pytest_collection_finish(session):
    with open(os.environ["MUTATION_LEDGER_COLLECTED"], "w",
              encoding="utf-8") as fh:
        for item in session.items:
            fh.write(item.nodeid + "\\n")
'''

#: pytest exit codes under which a RUN completed: all passed, or some failed.
_RAN = frozenset({0, 1})
#: ... and under which a COLLECTION completed: collected, or collected nothing.
_COLLECTED = frozenset({0, 5})


def _git(cwd: Path, *args: str) -> str:
    """``git`` in ``cwd`` under the scrubbed environment; stdout, or a
    refusal carrying stderr."""
    try:
        proc = subprocess.run(
            ("git", *args), cwd=cwd, env=scratch_clone.scrubbed_git_env(),
            capture_output=True, text=True, timeout=RUN_TIMEOUT_SECONDS)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise MutationLedgerError(f"git {' '.join(args)} in {cwd}: {exc}")
    if proc.returncode != 0:
        raise MutationLedgerError(
            f"git {' '.join(args)} in {cwd} exited {proc.returncode}: "
            f"{proc.stderr.strip()}")
    return proc.stdout


def _resolve_commit(repo_root: Path, revision: str) -> str | None:
    """The 40-char sha ``revision`` names in ``repo_root``, or None when the
    repository does not have it. A git that cannot answer is a refusal."""
    proc = subprocess.run(
        ("git", "rev-parse", "--verify", "--quiet", f"{revision}^{{commit}}"),
        cwd=repo_root, env=scratch_clone.scrubbed_git_env(),
        capture_output=True, text=True, timeout=RUN_TIMEOUT_SECONDS)
    if proc.returncode == 0:
        sha = proc.stdout.strip()
        if not _SHA40.match(sha):
            raise MutationLedgerError(
                f"git resolved {revision!r} to {sha!r}, not a sha")
        return sha
    if proc.returncode == 1:
        return None
    raise MutationLedgerError(
        f"git could not answer whether {revision} is in {repo_root} "
        f"(exit {proc.returncode}): {proc.stderr.strip()}")


def _run_bounded(cmd: Sequence[str], *, cwd: Path, env: Mapping[str, str],
                 timeout: float) -> subprocess.CompletedProcess:
    """Run ``cmd`` in its own session and kill the whole group on timeout,
    so a grandchild the run spawned cannot outlive the bound."""
    try:
        proc = subprocess.Popen(
            cmd, cwd=cwd, env=dict(env), stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, start_new_session=True)
    except OSError as exc:
        raise MutationLedgerError(f"could not start {cmd[0]}: {exc}")
    try:
        out, err = proc.communicate(timeout=max(timeout, 0.001))
    except subprocess.TimeoutExpired:
        head = ' '.join(cmd[:4])
        # Any OSError, not only "already gone": a group that refuses the
        # signal (PermissionError) must still reach the bounded reap below.
        for kill in (lambda: os.killpg(proc.pid, signal.SIGKILL), proc.kill):
            try:
                kill()
            except OSError:
                pass
        try:
            proc.communicate(timeout=KILL_GRACE_SECONDS)
        except subprocess.TimeoutExpired:
            # A grandchild holding the pipes is what usually keeps this
            # open; reap the child if it did die, drop the pipes, move on.
            proc.poll()
            for pipe in (proc.stdout, proc.stderr):
                if pipe is not None:
                    pipe.close()
            raise MutationLedgerError(
                f"{head} ... exceeded {timeout:.1f}s, was killed, and was "
                f"still not reaped after {KILL_GRACE_SECONDS}s; abandoned "
                "rather than waited on")
        raise MutationLedgerError(
            f"{head} ... exceeded {timeout:.1f}s and was killed")
    return subprocess.CompletedProcess(list(cmd), proc.returncode, out, err)


def _nested_env(tree: Path, plugins: Path, collected: Path) -> dict[str, str]:
    """The environment for a nested pytest run, scrubbed of the host's.

    Drop-by-prefix: ``PYTEST_ADDOPTS`` with ``-k``/``--lf``/``--maxfail``, a
    ``PYTEST_PLUGINS`` entry, a coverage wrapper, or an inherited
    ``PYTHONPATH`` each change the population a run observes. Plugin
    autoload is off because an installed ``pytest11`` entry point is loaded
    with no variable naming it; the one plugin needed is passed with ``-p``.
    """
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("PYTEST_", "COVERAGE_", "PYTHON", "GIT_",
                                "TOX_", "NOSE_"))}
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    path = [str(plugins)]
    if (tree / "src").is_dir():
        path.insert(0, str(tree / "src"))
    env["PYTHONPATH"] = os.pathsep.join(path)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["MUTATION_LEDGER_COLLECTED"] = str(collected)
    return env


def _unusable(what: str, proc: subprocess.CompletedProcess) -> str:
    return (f"the nested pytest run is unusable ({what}); refused rather "
            f"than parsed around\ncommand: {proc.args}\nstdout:\n"
            f"{proc.stdout}\nstderr:\n{proc.stderr}")


def _require_clone(clone: object) -> scratch_clone.ScratchClone:
    if not isinstance(clone, scratch_clone.ScratchClone):
        raise MutationLedgerError(
            f"expected a ScratchClone, got {type(clone).__name__}: only a "
            "quarantined copy may be run or mutated")
    return clone


def _pytest(clone: object, seal_file: str, *, collect_only: bool,
            timeout: float) -> tuple[subprocess.CompletedProcess,
                                     list[str] | None, bytes | None]:
    """One nested pytest run over ``seal_file`` in ``clone``.

    Returns the process, the collected node ids (None when collection never
    finished) and the junit report bytes (None when the run never finished).
    """
    tree = _require_clone(clone).path
    _require_repo_path(seal_file, name="seal_file", suffix=".py")
    if not (tree / seal_file).is_file():
        raise MutationLedgerError(
            f"{seal_file} is not a file in the provisioned tree {tree}")
    with tempfile.TemporaryDirectory(prefix="mutation-ledger-run-") as work:
        plugins = Path(work) / "plugins"
        plugins.mkdir()
        (plugins / "mutation_ledger_collect.py").write_text(
            _COLLECT_PLUGIN, encoding="utf-8")
        collected = Path(work) / "collected.ids"
        junit = Path(work) / "results.xml"
        cmd = [sys.executable, "-m", "pytest", seal_file, "-q", "--tb=line",
               "-p", "no:cacheprovider", "-p", "mutation_ledger_collect"]
        cmd.append("--collect-only" if collect_only else f"--junitxml={junit}")
        proc = _run_bounded(cmd, cwd=tree,
                            env=_nested_env(tree, plugins, collected),
                            timeout=timeout)
        ids = (collected.read_text(encoding="utf-8").splitlines()
               if collected.exists() else None)
        report = junit.read_bytes() if junit.exists() else None
    return proc, ids, report


def _junit_node_id(seal_file: str, case: ET.Element,
                   proc: subprocess.CompletedProcess) -> str:
    """The node id a junit ``testcase`` reports on: ``classname`` carries
    the dotted module plus any enclosing classes, ``name`` the function."""
    module = seal_file[:-len(".py")].replace("/", ".")
    classname = case.get("classname") or ""
    if classname == module:
        enclosing: tuple[str, ...] = ()
    elif classname.startswith(f"{module}."):
        enclosing = tuple(classname[len(module) + 1:].split("."))
    else:
        raise MutationLedgerError(_unusable(
            f"reported classname {classname!r}, which is not {module!r} nor "
            "a class in it", proc))
    return "::".join((seal_file, *enclosing, case.get("name") or ""))


def _collect_rows(clone: object, seal_file: str, *,
                  timeout: float) -> tuple[str, ...]:
    proc, ids, _ = _pytest(clone, seal_file, collect_only=True,
                           timeout=timeout)
    if proc.returncode not in _COLLECTED or ids is None:
        raise MutationLedgerError(_unusable(
            f"collection exited {proc.returncode}", proc))
    rows: set[str] = set()
    for node in ids:
        if not node:
            continue
        row = node.split("[", 1)[0]
        if not _NODE_ID.match(row):
            raise MutationLedgerError(
                f"collected {node!r}, which is not a pytest node id")
        rows.add(row)
    return tuple(sorted(rows))


def _run_rows(clone: object, seal_file: str, *,
              timeout: float) -> dict[str, RowResult]:
    proc, ids, report = _pytest(clone, seal_file, collect_only=False,
                                timeout=timeout)
    if proc.returncode not in _RAN:
        raise MutationLedgerError(_unusable(f"exit {proc.returncode}", proc))
    if ids is None:
        raise MutationLedgerError(_unusable("collection never finished", proc))
    results = dict.fromkeys((i for i in ids if i), RowResult.ABSENT)
    if not results:
        raise MutationLedgerError(_unusable("collected nothing", proc))
    if report is None:
        raise MutationLedgerError(_unusable(
            "the run never reported: no junit file was written, so the "
            "session ended before its results did", proc))
    try:
        root = ET.fromstring(report)
    except ET.ParseError as exc:
        raise MutationLedgerError(_unusable(f"junit unreadable: {exc}", proc))
    for case in root.iter("testcase"):
        node = _junit_node_id(seal_file, case, proc)
        if node not in results:
            raise MutationLedgerError(_unusable(
                f"reported {node!r}, which it did not collect", proc))
        kinds = {child.tag for child in case}
        if "skipped" in kinds:
            # No SKIPPED member: ABSENT ranks below PASSED, so a skip can
            # neither manufacture a PASSED->FAILED transition nor hide one.
            continue
        if "error" in kinds:
            results[node] = RowResult.ERRORED
        elif "failure" in kinds:
            results[node] = RowResult.FAILED
        else:
            results[node] = RowResult.PASSED
    return results


def _resolve_anchor(module: ast.Module, anchor: str) -> ast.AST:
    node: ast.AST = module
    for part in anchor.split("."):
        body = getattr(node, "body", None)
        if not isinstance(body, list):
            raise MutationLedgerError(
                f"anchor {anchor!r}: {part!r} is looked up inside something "
                "with no body")
        matches = [n for n in body
                   if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef,
                                     ast.ClassDef)) and n.name == part]
        if len(matches) != 1:
            raise MutationLedgerError(
                f"anchor {anchor!r} does not resolve: {part!r} names "
                f"{len(matches)} definitions at that level")
        node = matches[0]
    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        raise MutationLedgerError(f"anchor {anchor!r} is not a function")
    return node


def _leading_whitespace(line: str) -> str:
    return line[:len(line) - len(line.lstrip())]


def _statements_after_docstring(fn: ast.AST) -> list[ast.stmt]:
    body = list(fn.body)
    if body and isinstance(body[0], ast.Expr) and isinstance(
            body[0].value, ast.Constant) and isinstance(
            body[0].value.value, str):
        body = body[1:]
    return body


def _literal(argument: str, operator: MutationOperator) -> str:
    try:
        ast.literal_eval(argument)
    except (ValueError, SyntaxError, TypeError, MemoryError, RecursionError):
        raise MutationLedgerError(
            f"{operator.value} needs a Python literal, got {argument!r}")
    return argument


def _return_chain(fn: ast.AST) -> list[ast.If]:
    """The one if/elif chain among the anchor's direct statements whose
    every arm ends in ``return`` and which has no ``else``; refused when
    there is none or more than one."""
    chains: list[list[ast.If]] = []
    for stmt in fn.body:
        if not isinstance(stmt, ast.If):
            continue
        chain = [stmt]
        while len(chain[-1].orelse) == 1 and isinstance(chain[-1].orelse[0],
                                                        ast.If):
            chain.append(chain[-1].orelse[0])
        if chain[-1].orelse:
            continue
        if all(arm.body and isinstance(arm.body[-1], ast.Return)
               for arm in chain):
            chains.append(chain)
    if len(chains) != 1:
        raise MutationLedgerError(
            f"{fn.name} has {len(chains)} else-less dispatch chains whose "
            "arms all return; add_default_branch needs exactly one")
    return chains[0]


def apply_mutation(source: bytes, site: MutationSite) -> bytes:
    """``source`` with ``site``'s mutation applied.

    The anchor is resolved with :mod:`ast` against ``source`` itself (a
    dotted path of ``def``/``class`` names), never by line number. Refuses —
    never returns a copy — when the anchor does not resolve, the operator
    does not fit what is there, the argument is not what the operator takes,
    the edit changes nothing, or the result does not compile.
    """
    if not isinstance(source, bytes):
        raise MutationLedgerError("apply_mutation takes bytes")
    if not isinstance(site, MutationSite):
        raise MutationLedgerError("site must be a MutationSite")
    try:
        text = source.decode("utf-8")
        module = ast.parse(text)
    except (UnicodeDecodeError, SyntaxError) as exc:
        raise MutationLedgerError(f"subject does not parse: {exc}")
    fn = _resolve_anchor(module, site.anchor)
    lines = text.splitlines(keepends=True)
    op = site.operator

    if op in (MutationOperator.BODY_TO_NO_OP, MutationOperator.RETURN_CONSTANT):
        stmts = _statements_after_docstring(fn)
        if not stmts:
            raise MutationLedgerError(
                f"{site.anchor} has no statement after its docstring")
        first, last = stmts[0], stmts[-1]
        if first.lineno == fn.lineno:
            raise MutationLedgerError(
                f"{site.anchor} is a one-line definition; {op.value} needs "
                "a body on its own lines")
        value = ("None" if op is MutationOperator.BODY_TO_NO_OP
                 else _literal(site.argument, op))
        indent = _leading_whitespace(lines[first.lineno - 1])
        lines[first.lineno - 1:last.end_lineno] = [f"{indent}return {value}\n"]
    elif op is MutationOperator.RAISE_TO_CONTINUE:
        handlers = [h for node in ast.walk(fn) if isinstance(node, ast.Try)
                    for h in node.handlers
                    if h.type is not None
                    and ast.unparse(h.type) == site.argument]
        if len(handlers) != 1:
            raise MutationLedgerError(
                f"{site.anchor} has {len(handlers)} `except {site.argument}` "
                "handlers; raise_to_continue needs exactly one")
        raises = [s for s in handlers[0].body if isinstance(s, ast.Raise)]
        if len(raises) != 1:
            raise MutationLedgerError(
                f"the `except {site.argument}` handler in {site.anchor} has "
                f"{len(raises)} raise statements; raise_to_continue needs one")
        stmt = raises[0]
        indent = _leading_whitespace(lines[stmt.lineno - 1])
        lines[stmt.lineno - 1:stmt.end_lineno] = [f"{indent}continue\n"]
    elif op is MutationOperator.ADD_DEFAULT_BRANCH:
        value = _literal(site.argument, op)
        chain = _return_chain(fn)
        outer = _leading_whitespace(lines[chain[0].lineno - 1])
        inner = _leading_whitespace(lines[chain[-1].body[0].lineno - 1])
        at = chain[-1].body[-1].end_lineno
        lines[at:at] = [f"{outer}else:\n", f"{inner}return {value}\n"]
    else:
        raise MutationLedgerError(f"no applier for {op!r}")

    mutated = "".join(lines).encode("utf-8")
    if mutated == source:
        raise MutationLedgerError(
            f"{op.value} at {site.anchor} changed nothing; a mutation that "
            "is the input would be recorded as one that reddened nothing")
    try:
        compile(mutated, f"<mutant {site.subject}>", "exec")
    except SyntaxError as exc:
        raise MutationLedgerError(
            f"{op.value} at {site.anchor} does not fit what is there: the "
            f"mutant does not compile ({exc.msg}, line {exc.lineno})")
    return mutated


def provision_subject_tree(repo_root: str, revision: str, dest: str) -> object:
    """A quarantined :class:`scratch_clone.ScratchClone` of ``revision``.

    ``git worktree add --detach`` into a sibling staging path, the
    out-of-tree ``.claude/workflow`` symlink removed, then
    :func:`scratch_clone.make_scratch_clone` into ``dest``. The staging
    worktree is removed on every path, so the repository is left as found.
    """
    root = Path(repo_root)
    target = Path(dest)
    if not root.is_dir():
        raise MutationLedgerError(f"repo_root {repo_root!r} is not a directory")
    if os.path.lexists(target):
        raise MutationLedgerError(f"dest {dest!r} already exists")
    staging = target.parent / f"{target.name}.staging"
    if os.path.lexists(staging):
        raise MutationLedgerError(f"staging path {staging} already exists")
    sha = _resolve_commit(root, revision)
    if sha is None:
        raise MutationLedgerError(f"{revision} is not a commit in {repo_root}")
    target.parent.mkdir(parents=True, exist_ok=True)
    _git(root, "worktree", "add", "--detach", "--quiet", str(staging), sha)
    try:
        head = _git(staging, "rev-parse", "HEAD").strip()
        if head != sha:
            raise MutationLedgerError(
                f"the staging worktree is at {head}, not the requested {sha}")
        link = staging / ".claude" / "workflow"
        if link.is_symlink():
            link.unlink()
        return scratch_clone.make_scratch_clone(staging, target)
    finally:
        try:
            _git(root, "worktree", "remove", "--force", str(staging))
        except MutationLedgerError:
            shutil.rmtree(staging, ignore_errors=True)
            try:
                _git(root, "worktree", "prune")
            except MutationLedgerError:
                pass


def collect_rows(clone: object, seal_file: str) -> tuple[str, ...]:
    """The function-level rows ``seal_file`` collects in ``clone``, sorted.

    Collection only. A collection that did not complete RAISES; a file that
    collects nothing is ``()``.
    """
    return _collect_rows(clone, seal_file, timeout=RUN_TIMEOUT_SECONDS)


def run_rows(clone: object, seal_file: str) -> Mapping[str, RowResult]:
    """Run ``seal_file`` in ``clone``; node id to :class:`RowResult`.

    Node-id level, including parametrisations. A row collected and never
    reported is ABSENT. A run that did not complete — a non-{0,1} exit, a
    collection that never finished or collected nothing, a session that
    ended before writing its report — is refused, never returned as a map.
    """
    return _run_rows(clone, seal_file, timeout=RUN_TIMEOUT_SECONDS)


@dataclass(frozen=True)
class Measurement:
    """What one provision-and-run of a claim produced, before any record is
    compared against it. :func:`rederive` and :func:`observe_claim` both
    read one; only the first has a record to disagree with."""

    revision_run: str
    drift: tuple[Drift, ...]
    #: Set only when no comparison happened (NOT_ATTEMPTED, HARNESS_FAULT).
    observation: Observation | None
    control: dict[str, RowResult] | None
    #: None when the control ran and the mutant run was refused.
    mutant: dict[str, RowResult] | None
    subject_sha256: str | None
    mutant_sha256: str | None
    population: tuple[str, ...] | None
    detail: str
    cost_seconds: float

    @property
    def compared(self) -> bool:
        return self.control is not None


def _drift_tuple(drift: set[Drift]) -> tuple[Drift, ...]:
    order = list(Drift)
    return tuple(sorted(drift, key=order.index))


def _measure(*, repo_root: str, revision: str, seal_file: str,
             claiming_row: str, site: MutationSite,
             expected_subject_sha256: str | None,
             expected_population_sha256: str | None, historical: bool,
             budget_seconds: float, drift: set[Drift],
             started: float) -> Measurement:
    """Provision ``revision``, run the control and the mutant, and report.

    ``historical`` (AT_RECORDED) turns a digest mismatch into HARNESS_FAULT:
    git is content-addressed, so the provisioned tree is not the one the
    record names. Otherwise a mismatch is drift.

    A hard absence is applied BEFORE any run: a seal that imports an absent
    subject fails collection, and that is absence, not a harness fault. The
    population is the CONTROL RUN's own collection — the digest names the
    rows that were compared, not a separate collect-only pass — and a
    mutant that collects a different row set is not comparable to it.
    """
    root = Path(repo_root)

    def done(observation: Observation | None, *, control=None, mutant=None,
             subject_sha256=None, mutant_sha256=None, population=None,
             detail="") -> Measurement:
        return Measurement(
            revision_run=revision, drift=_drift_tuple(drift),
            observation=observation, control=control, mutant=mutant,
            subject_sha256=subject_sha256, mutant_sha256=mutant_sha256,
            population=population, detail=detail,
            cost_seconds=time.monotonic() - started)

    def remaining() -> float:
        return budget_seconds - (time.monotonic() - started)

    with tempfile.TemporaryDirectory(prefix="mutation-ledger-") as work:
        try:
            clone = provision_subject_tree(str(root), revision,
                                           str(Path(work) / "tree"))
        except (MutationLedgerError, scratch_clone.ScratchCloneError,
                OSError) as exc:
            return done(Observation.HARNESS_FAULT,
                        detail=f"provisioning refused: {exc}")
        tree = clone.path

        subject_sha256 = mutant_sha256 = None
        mutant_bytes: bytes | None = None
        notes: list[str] = []
        subject_path = tree / site.subject
        if not subject_path.is_file():
            drift.add(Drift.SUBJECT_ABSENT)
            notes.append(f"{site.subject} is not in the tree")
        else:
            source = subject_path.read_bytes()
            subject_sha256 = source_digest(source)
            if (expected_subject_sha256 is not None
                    and subject_sha256 != expected_subject_sha256):
                if historical:
                    return done(Observation.HARNESS_FAULT, detail=(
                        f"the provisioned {site.subject} at {revision} does "
                        "not have the recorded digest, so this is not the "
                        "tree the observation names"))
                drift.add(Drift.SUBJECT_BYTES)
            try:
                mutant_bytes = apply_mutation(source, site)
                mutant_sha256 = source_digest(mutant_bytes)
            except MutationLedgerError as exc:
                drift.add(Drift.SITE_ABSENT)
                notes.append(f"site does not resolve: {exc}")

        if not (tree / seal_file).is_file():
            drift.add(Drift.ROW_ABSENT)
            notes.append(f"{seal_file} is not in the tree")
        if drift & set(HARD_ABSENCE):
            return done(Observation.NOT_ATTEMPTED,
                        subject_sha256=subject_sha256,
                        mutant_sha256=mutant_sha256,
                        detail="; ".join(notes))
        assert mutant_bytes is not None  # SITE_ABSENT is a hard absence

        try:
            control = fold_row_results(
                _run_rows(clone, seal_file, timeout=remaining()))
        except MutationLedgerError as exc:
            return done(Observation.HARNESS_FAULT,
                        subject_sha256=subject_sha256,
                        mutant_sha256=mutant_sha256,
                        detail=f"the control run was refused: {exc}")
        population = tuple(sorted(control))
        if (expected_population_sha256 is not None
                and population_digest(population)
                != expected_population_sha256):
            if historical:
                return done(Observation.HARNESS_FAULT,
                            subject_sha256=subject_sha256,
                            mutant_sha256=mutant_sha256,
                            population=population, detail=(
                                f"the provisioned {seal_file} at {revision} "
                                "does not collect the recorded population, so "
                                "this is not the tree the observation names"))
            drift.add(Drift.POPULATION)
        if claiming_row not in control:
            drift.add(Drift.ROW_ABSENT)
            # No result map is consulted: the row was not collected.
            return done(Observation.NOT_ATTEMPTED,
                        subject_sha256=subject_sha256,
                        mutant_sha256=mutant_sha256, population=population,
                        detail=f"{claiming_row} is not collected")

        mutant: dict[str, RowResult] | None
        token = scratch_clone.swap_in(clone, site.subject, mutant_bytes)
        try:
            mutant = fold_row_results(
                _run_rows(clone, seal_file, timeout=remaining()))
            detail = ""
        except MutationLedgerError as exc:
            mutant = None
            detail = f"the mutant run was refused: {exc}"
        finally:
            scratch_clone.swap_back(clone, token)
        if mutant is not None and set(mutant) != set(control):
            gained = sorted(set(mutant) - set(control))
            lost = sorted(set(control) - set(mutant))
            detail = ("the mutant run collected a different population from "
                      f"the control (gained {gained}, lost {lost}), so the "
                      "two runs are not comparable")
            mutant = None
        if remaining() < 0:
            return done(Observation.HARNESS_FAULT,
                        subject_sha256=subject_sha256,
                        mutant_sha256=mutant_sha256, population=population,
                        detail=f"budget of {budget_seconds}s exceeded")
        return done(None, control=control, mutant=mutant,
                    subject_sha256=subject_sha256, mutant_sha256=mutant_sha256,
                    population=population, detail=detail)


def _mutant_or_unevaluable(m: Measurement) -> dict[str, RowResult]:
    """The mutant map to classify with: the real one, or — when the mutant
    run was refused after the control completed — every row ABSENT, which
    :func:`classify_observation` reads as MUTANT_UNEVALUABLE behind the
    control's own arms."""
    if m.mutant is not None:
        return m.mutant
    assert m.control is not None
    return {row: RowResult.ABSENT for row in m.control}


def _rederive(entry: LedgerEntry, *, repo_root: str, mode: RederiveMode,
              target: str | None, budget_seconds: float,
              ) -> tuple[Rederivation, Measurement | None]:
    """:func:`rederive`, also handing back the one :class:`Measurement` the
    verdict came from (None when nothing was provisioned), so a caller that
    records can record THAT run and not a second one."""
    if not isinstance(entry, LedgerEntry):
        raise MutationLedgerError("rederive takes a LedgerEntry")
    if not isinstance(mode, RederiveMode):
        raise MutationLedgerError(f"not a RederiveMode: {mode!r}")
    budget = _require_cost(budget_seconds, name="budget_seconds")
    if mode is RederiveMode.AT_RECORDED and target is not None:
        raise MutationLedgerError(
            "AT_RECORDED names the tree already; a target is a second answer")
    started = time.monotonic()
    root = Path(repo_root)
    if not root.is_dir():
        raise MutationLedgerError(f"repo_root {repo_root!r} is not a directory")
    drift: set[Drift] = set()

    def report(observation: Observation, *, revision_run: str, reddened=(),
               unexpected=(), missing=(), detail="") -> Rederivation:
        return Rederivation(
            claim_id=entry.claim_id, observation_id=entry.observation_id,
            mode=mode, revision_run=revision_run, drift=_drift_tuple(drift),
            observation=observation, reddened_observed=tuple(reddened),
            unexpected_rows=tuple(unexpected), missing_rows=tuple(missing),
            cost_seconds=time.monotonic() - started, detail=detail)

    recorded = _resolve_commit(root, entry.revision)
    if recorded is None:
        drift.add(Drift.REVISION_ABSENT)
    if mode is RederiveMode.AT_RECORDED:
        if recorded is None:
            return report(Observation.NOT_ATTEMPTED, revision_run=NULL_REVISION,
                          detail=(f"revision {entry.revision} is not in "
                                  f"{repo_root}; nothing was provisioned")
                          ), None
        revision = recorded
    else:
        revision = _resolve_commit(root, target or "HEAD")
        if revision is None:
            if target is not None:
                raise MutationLedgerError(
                    f"target {target!r} is not a commit in {repo_root}")
            return report(Observation.HARNESS_FAULT, revision_run=NULL_REVISION,
                          detail=f"{repo_root} has no HEAD commit to run"
                          ), None

    m = _measure(
        repo_root=repo_root, revision=revision, seal_file=entry.seal_file,
        claiming_row=entry.claiming_row, site=entry.site,
        expected_subject_sha256=entry.subject_sha256,
        expected_population_sha256=entry.population_sha256,
        historical=mode is RederiveMode.AT_RECORDED, budget_seconds=budget,
        drift=drift, started=started)
    if not m.compared:
        assert m.observation is not None
        return report(m.observation, revision_run=m.revision_run,
                      detail=m.detail), m
    assert m.control is not None
    mutant = _mutant_or_unevaluable(m)
    observation = classify_observation(
        control=m.control, mutant=mutant, claiming_row=entry.claiming_row,
        recorded_reddened=entry.reddened)
    observed = transition_set(m.control, mutant)
    return report(
        observation, revision_run=m.revision_run, reddened=observed,
        unexpected=sorted(set(observed) - set(entry.reddened)),
        missing=sorted(set(entry.reddened) - set(observed)),
        detail=m.detail), m


def rederive(entry: LedgerEntry, *, repo_root: str,
             mode: RederiveMode = RederiveMode.AT_TARGET,
             target: str | None = None,
             budget_seconds: float = PER_ENTRY_BUDGET_SECONDS) -> Rederivation:
    """Re-derive one entry: provision, control run, mutant run, compare.

    Never re-reads the docstring. Under :attr:`RederiveMode.AT_RECORDED` a
    ``target`` is refused. A ``target`` that names no commit is refused too:
    both are malformed requests, not run outcomes.

    Returns a :class:`Rederivation` in every other terminating case. A
    BROKEN RUN — a refused clone, an exceeded budget, an unusable pytest, a
    provisioned tree that is not the one the entry names, a control run that
    was refused — is :attr:`Observation.HARNESS_FAULT` with the reason in
    ``detail``. A TREE THAT LACKS WHAT THE ENTRY NAMES is the matching
    :class:`Drift` with :attr:`Observation.NOT_ATTEMPTED`; an absent recorded
    revision under AT_RECORDED reports :data:`NULL_REVISION` as
    ``revision_run``, since nothing was provisioned. A mutant run refused
    after a completed control is the mutation's doing and classifies as
    :attr:`Observation.MUTANT_UNEVALUABLE`.
    """
    return _rederive(entry, repo_root=repo_root, mode=mode, target=target,
                     budget_seconds=budget_seconds)[0]


def _admit(m: Measurement, *, seal_file: str, claiming_row: str,
           site: MutationSite, observed_on: str | None, supersedes: str | None,
           note: str) -> LedgerEntry | None:
    """The entry ONE measurement supports, or None when it compared nothing
    the ledger can hold: both runs must have completed and the control must
    have reported the claiming row PASSED or FAILED. The single admission
    rule, so a record never describes a run other than the one adjudicated.
    """
    if m.control is None or m.mutant is None:
        return None
    before = m.control.get(claiming_row)
    if before not in (RowResult.PASSED, RowResult.FAILED):
        return None
    assert m.subject_sha256 and m.mutant_sha256 and m.population is not None
    return new_entry(
        seal_file=seal_file, claiming_row=claiming_row, site=site,
        revision=m.revision_run, subject_sha256=m.subject_sha256,
        mutant_sha256=m.mutant_sha256,
        population_sha256=population_digest(m.population),
        reddened=transition_set(m.control, m.mutant),
        control_green=before is RowResult.PASSED,
        observed_on=observed_on or datetime.date.today().isoformat(),
        supersedes=supersedes, cost_seconds=m.cost_seconds, note=note)


def observe_claim(*, repo_root: str, seal_file: str, claiming_row: str,
                  site: MutationSite, target: str | None = None,
                  observed_on: str | None = None,
                  supersedes: str | None = None, note: str = "",
                  budget_seconds: float = PER_ENTRY_BUDGET_SECONDS,
                  ) -> tuple[LedgerEntry | None, Measurement]:
    """Measure a claim at ``target`` (HEAD by default) and, when both runs
    completed, the :class:`LedgerEntry` that records what was seen.

    The admission path: an entry made here carries the digests of the tree
    that was run and the transition set that was observed, never a typed
    one. No entry comes back for a run that compared nothing; the
    :class:`Measurement` says why.
    """
    _require_repo_path(seal_file, name="seal_file", suffix=".py")
    _require_node_id(claiming_row, name="claiming_row")
    if not isinstance(site, MutationSite):
        raise MutationLedgerError("site must be a MutationSite")
    budget = _require_cost(budget_seconds, name="budget_seconds")
    root = Path(repo_root)
    if not root.is_dir():
        raise MutationLedgerError(f"repo_root {repo_root!r} is not a directory")
    revision = _resolve_commit(root, target or "HEAD")
    if revision is None:
        raise MutationLedgerError(
            f"{target or 'HEAD'} is not a commit in {repo_root}")
    m = _measure(
        repo_root=repo_root, revision=revision, seal_file=seal_file,
        claiming_row=claiming_row, site=site, expected_subject_sha256=None,
        expected_population_sha256=None, historical=False,
        budget_seconds=budget, drift=set(), started=time.monotonic())
    return _admit(m, seal_file=seal_file, claiming_row=claiming_row,
                  site=site, observed_on=observed_on, supersedes=supersedes,
                  note=note), m


# --------------------------------------------------------------------------- #
# The file, and the check that closes the loop from the docstrings back.
# --------------------------------------------------------------------------- #


def load_ledger(path: str) -> tuple[LedgerRecord, ...]:
    """Every record in one ledger file, validated as a whole.

    Blank lines are skipped; a malformed line refuses the whole file rather
    than being dropped, and :func:`validate_ledger` runs on the result.
    """
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise MutationLedgerError(f"cannot read ledger {path}: {exc}")
    records: list[LedgerRecord] = []
    for number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            records.append(parse_line(line))
        except MutationLedgerError as exc:
            raise MutationLedgerError(f"{path}:{number}: {exc}") from None
    validate_ledger(records)
    return tuple(records)


def _write_records(target: Path, records: Sequence[LedgerRecord]) -> None:
    """Write to a sibling temp file and ``os.replace`` it over ``target``:
    a crash mid-write leaves the previous file, never a torn one."""
    text = "".join(canonical_line(r) + "\n" for r in records)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=target.parent, prefix=f".{target.name}.",
                               suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, target)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def write_ledger(path: str, records: Sequence[LedgerRecord]) -> None:
    """Write a ledger, refusing one that :func:`validate_ledger` rejects and
    a ``path`` that :func:`refuse_unwritable_ledger_path` rejects.

    Consistency only: the ids prove a record is self-consistent, not that a
    run produced it. ``rederive``/:func:`observe_claim` admit evidence.
    """
    refuse_unwritable_ledger_path(path)
    for record in records:
        if not isinstance(record, (LedgerEntry, Prediction)):
            raise MutationLedgerError(f"not a ledger record: {record!r}")
    validate_ledger(records)
    _write_records(Path(path), records)


def _ledger_files(root: Path) -> list[Path]:
    ledger_dir = root / LEDGER_DIR
    if not ledger_dir.is_dir():
        return []
    return sorted(p for p in ledger_dir.iterdir()
                  if p.is_file() and p.name.endswith(LEDGER_SUFFIX))


def check_citations(repo_root: str) -> tuple[str, ...]:
    """Every ledger citation in the tree that does not resolve to a live
    record.

    Loads every ledger under :data:`LEDGER_DIR`, then greps the rest of the
    tree for :data:`CITATION_ID`. One line per problem: an ``ml-`` id with no
    live observation, an ``mlp-`` id with no prediction, or an ``mlo-``
    observation id cited where a claim id belongs (evidence is replaced, so
    such a citation goes stale by design; a superseded one already has).
    The ledger files themselves are not citations and are not scanned.
    Empty when the tree is clean.

    STATIC: reads the ledger and the tree, runs nothing. So it answers
    whether a citation RESOLVES, not whether its live observation still
    :func:`counts_as_coverage` — that is a run outcome, and the ``rederive``
    verb's exit status answers it (deviation D-W2-3-3-citations).
    """
    root = Path(repo_root)
    if not root.is_dir():
        raise MutationLedgerError(f"repo_root {repo_root!r} is not a directory")
    live_claims: set[str] = set()
    observation_ids: set[str] = set()
    superseded: set[str] = set()
    prediction_ids: set[str] = set()
    for ledger in _ledger_files(root):
        records = load_ledger(str(ledger))
        live_claims |= set(current_observations(records))
        for entry in observations(records):
            observation_ids.add(entry.observation_id)
            if entry.supersedes is not None:
                superseded.add(entry.supersedes)
        prediction_ids |= {p.prediction_id for p in predictions(records)}

    problems: list[str] = []
    ledger_dir = (root / LEDGER_DIR).resolve()
    for dirpath, dirnames, filenames in os.walk(root):
        here = Path(dirpath)
        dirnames[:] = sorted(
            d for d in dirnames
            if d not in _UNSCANNED_DIRS and (here / d).resolve() != ledger_dir)
        for name in sorted(filenames):
            file = here / name
            if file.is_symlink():
                continue
            try:
                text = file.read_bytes().decode("utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            if "ml" not in text:
                continue
            rel = file.relative_to(root).as_posix()
            for number, line in enumerate(text.splitlines(), 1):
                for match in CITATION_ID.finditer(line):
                    cited = match.group(0)
                    where = f"{rel}:{number}: {cited}"
                    if cited.startswith(OBSERVATION_ID_PREFIX):
                        state = ("superseded" if cited in superseded
                                 else "live" if cited in observation_ids
                                 else "unresolved")
                        problems.append(
                            f"{where} is an observation id ({state}) cited "
                            "where a claim id belongs; cite the ml- claim")
                    elif cited.startswith(PREDICTION_ID_PREFIX):
                        if cited not in prediction_ids:
                            problems.append(
                                f"{where} resolves to no prediction")
                    elif cited not in live_claims:
                        problems.append(
                            f"{where} resolves to no live observation")
    return tuple(problems)


# --------------------------------------------------------------------------- #
# The CLI face.
# --------------------------------------------------------------------------- #


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m claude_dispatcher.mutation_ledger",
        description="Re-derive, dispose of, and check mutation-coverage "
                    "claims against a ledger.")
    verbs = parser.add_subparsers(dest="verb", required=True)

    def common(sub: argparse.ArgumentParser, *, runs: bool) -> None:
        sub.add_argument("--repo", default=".",
                         help="repository root (default: the current directory)")
        which = sub.add_mutually_exclusive_group(required=True)
        which.add_argument("--subject",
                           help="subject module; the ledger path is derived")
        which.add_argument("--ledger",
                           help=f"ledger path, repo-relative, under {LEDGER_DIR}/")
        if runs:
            sub.add_argument("--mode", choices=[m.value for m in RederiveMode],
                             default=RederiveMode.AT_TARGET.value)
            sub.add_argument("--target",
                             help="commit to run at (AT_TARGET; default HEAD)")
            sub.add_argument("--budget", type=float,
                             default=PER_ENTRY_BUDGET_SECONDS,
                             help="seconds per entry before it faults")

    rederive_ = verbs.add_parser(
        "rederive", help="re-run entries and report each status; "
                         "--record admits what was observed")
    common(rederive_, runs=True)
    rederive_.add_argument("--record", action="store_true",
                           help="write a superseding observation for every "
                                "completed comparison, and record new claims")
    rederive_.add_argument("--observed-on", help="YYYY-MM-DD (default today)")
    rederive_.add_argument("--note", default="", help="prose on new records")
    rederive_.add_argument(
        "--claim", action="append", nargs="+", metavar="ARG", default=[],
        help="a claim not yet in the ledger: SEAL_FILE::ROW ANCHOR OPERATOR "
             "[ARGUMENT]; measured and, with --record, admitted")
    rederive_.add_argument("claim_ids", nargs="*",
                           help="restrict to these ml- claim ids")

    fates = verbs.add_parser("fates", help="proposed_fate over a ledger")
    common(fates, runs=True)

    citations = verbs.add_parser(
        "citations", help="check every ledger citation in the tree")
    citations.add_argument("--repo", default=".")

    predict = verbs.add_parser(
        "predict", help="record a clause no operator can measure")
    common(predict, runs=False)
    predict.add_argument("--row", required=True, metavar="SEAL_FILE::ROW")
    predict.add_argument("--described", required=True,
                         help="the clause's mutation sentence, verbatim")
    predict.add_argument("--reason", required=True,
                         choices=[r.value for r in NonDerivable])
    predict.add_argument("--target", help="commit judged at (default HEAD)")
    predict.add_argument("--recorded-on", help="YYYY-MM-DD (default today)")
    predict.add_argument("--note", default="")
    return parser


def _ledger_for(args: argparse.Namespace) -> tuple[str, Path]:
    """The repo-relative ledger path and its absolute location."""
    rel = args.ledger if args.ledger else ledger_path_for(args.subject)
    refuse_unwritable_ledger_path(rel)
    return rel, Path(args.repo) / rel


def _load_or_empty(location: Path) -> tuple[LedgerRecord, ...]:
    return load_ledger(str(location)) if location.exists() else ()


def _subject_of(records: Sequence[LedgerRecord],
                args: argparse.Namespace) -> str | None:
    subjects = {e.site.subject for e in observations(records)}
    subjects |= {p.subject for p in predictions(records)}
    if args.subject:
        subjects.add(args.subject)
    if len(subjects) > 1:
        raise MutationLedgerError(f"one subject per ledger, got {sorted(subjects)}")
    return next(iter(subjects), None)


def _format(r: Rederivation, row: str) -> str:
    drift = ",".join(d.value for d in r.drift) or "-"
    return (f"{r.claim_id} {r.status.value} freshness={r.freshness.value} "
            f"observation={r.observation.value} at={r.revision_run[:12]} "
            f"drift={drift} reddened={len(r.reddened_observed)} "
            f"+{len(r.unexpected_rows)} -{len(r.missing_rows)} "
            f"{r.cost_seconds:.1f}s {row}"
            + (f"\n    {r.detail}" if r.detail else ""))


def _verb_rederive(args: argparse.Namespace) -> int:
    rel, location = _ledger_for(args)
    records = list(_load_or_empty(location))
    subject = _subject_of(records, args)
    mode = RederiveMode(args.mode)
    if mode is RederiveMode.AT_RECORDED and args.target:
        raise MutationLedgerError("--target is not allowed with at_recorded")
    observed_on = args.observed_on or datetime.date.today().isoformat()
    all_covered = True
    written = 0

    live = current_observations(records)
    wanted = set(args.claim_ids)
    unknown = wanted - set(live)
    if unknown:
        raise MutationLedgerError(f"no live observation for {sorted(unknown)}")
    for claim, entry in live.items():
        if wanted and claim not in wanted:
            continue
        # One measurement: the status printed and the record written are
        # the same run, so the exit status describes the evidence admitted.
        r, m = _rederive(entry, repo_root=args.repo, mode=mode,
                         target=args.target, budget_seconds=args.budget)
        print(_format(r, entry.claiming_row))
        all_covered &= counts_as_coverage(r.status)
        if args.record:
            fresh = None if m is None else _admit(
                m, seal_file=entry.seal_file, claiming_row=entry.claiming_row,
                site=entry.site, observed_on=observed_on,
                supersedes=entry.observation_id, note=args.note)
            if fresh is None:
                print("    not recorded: the comparison did not complete")
            else:
                assert set(fresh.reddened) == set(r.reddened_observed)
                records.append(fresh)
                written += 1
                print(f"    recorded {fresh.observation_id} superseding "
                      f"{entry.observation_id}")

    for spec in args.claim:
        if len(spec) not in (3, 4):
            raise MutationLedgerError(
                f"--claim takes SEAL_FILE::ROW ANCHOR OPERATOR [ARGUMENT], "
                f"got {spec}")
        if subject is None:
            raise MutationLedgerError("--claim needs --subject")
        row, anchor, operator = spec[:3]
        seal_file = row.split("::", 1)[0]
        site = MutationSite(subject=subject, anchor=anchor,
                            operator=MutationOperator(operator),
                            argument=spec[3] if len(spec) == 4 else "")
        claim = claim_id(seal_file=seal_file, claiming_row=row, site=site)
        if claim in live:
            raise MutationLedgerError(
                f"{claim} already has a live observation; rederive it instead")
        fresh, m = observe_claim(
            repo_root=args.repo, seal_file=seal_file, claiming_row=row,
            site=site, target=args.target, observed_on=observed_on,
            note=args.note, budget_seconds=args.budget)
        drift = ",".join(d.value for d in m.drift) or "-"
        if fresh is None:
            print(f"{claim} NOT-RECORDED at={m.revision_run[:12]} "
                  f"drift={drift} {m.cost_seconds:.1f}s {row}\n    "
                  f"{m.detail or 'the comparison did not complete'}")
            all_covered = False
            continue
        assert m.control is not None
        print(f"{claim} OBSERVED at={m.revision_run[:12]} "
              f"control={m.control[row].value} reddened="
              f"{len(fresh.reddened)} {m.cost_seconds:.1f}s {row}")
        for reddened in fresh.reddened:
            print(f"    reddened {reddened}")
        if args.record:
            records.append(fresh)
            written += 1
            print(f"    recorded {fresh.observation_id} as {claim}")

    if written:
        refuse_unwritable_ledger_path(rel)
        validate_ledger(records)
        _write_records(location, records)
        print(f"wrote {written} record(s) to {rel}")
    return 0 if all_covered else 1


def _verb_fates(args: argparse.Namespace) -> int:
    _, location = _ledger_for(args)
    records = _load_or_empty(location)
    mode = RederiveMode(args.mode)
    if mode is RederiveMode.AT_RECORDED and args.target:
        raise MutationLedgerError("--target is not allowed with at_recorded")
    for claim, entry in current_observations(records).items():
        r = rederive(entry, repo_root=args.repo, mode=mode, target=args.target,
                     budget_seconds=args.budget)
        print(f"{claim} {r.status.value} -> {proposed_fate(r.status).value} "
              f"{entry.claiming_row}")
    for p in predictions(records):
        print(f"{p.prediction_id} prediction({p.reason.value}) -> "
              f"{PREDICTION_FATE.value} {p.claiming_row}")
    return 0


def _verb_citations(args: argparse.Namespace) -> int:
    problems = check_citations(args.repo)
    for line in problems:
        print(line)
    return 1 if problems else 0


def _verb_predict(args: argparse.Namespace) -> int:
    rel, location = _ledger_for(args)
    records = list(_load_or_empty(location))
    subject = _subject_of(records, args)
    if subject is None:
        raise MutationLedgerError("predict needs --subject")
    root = Path(args.repo)
    revision = _resolve_commit(root, args.target or "HEAD")
    if revision is None:
        raise MutationLedgerError(f"{args.target or 'HEAD'} is not a commit")
    try:
        source = subprocess.run(
            ("git", "show", f"{revision}:{subject}"), cwd=root,
            env=scratch_clone.scrubbed_git_env(), capture_output=True,
            check=True, timeout=RUN_TIMEOUT_SECONDS).stdout
    except (subprocess.CalledProcessError, OSError,
            subprocess.TimeoutExpired) as exc:
        raise MutationLedgerError(f"{subject} at {revision[:12]}: {exc}")
    prediction = new_prediction(
        seal_file=args.row.split("::", 1)[0], claiming_row=args.row,
        subject=subject, described=args.described,
        reason=NonDerivable(args.reason), revision=revision,
        subject_sha256=source_digest(source),
        recorded_on=args.recorded_on or datetime.date.today().isoformat(),
        note=args.note)
    # Re-examined in place: the same clause replaces its earlier judgement.
    kept = [r for r in records if not (isinstance(r, Prediction)
                                       and r.prediction_id
                                       == prediction.prediction_id)]
    replaced = len(kept) != len(records)
    kept.append(prediction)
    refuse_unwritable_ledger_path(rel)
    validate_ledger(kept)
    _write_records(location, kept)
    print(f"{prediction.prediction_id} {'re-examined' if replaced else 'recorded'} "
          f"({prediction.reason.value}) at={revision[:12]} {args.row}")
    return 0


_VERBS = {
    "rederive": _verb_rederive,
    "fates": _verb_fates,
    "citations": _verb_citations,
    "predict": _verb_predict,
}


def main(argv: Sequence[str]) -> int:
    """The CLI face. ``rederive`` re-runs entries and, with ``--record``,
    admits evidence; ``fates`` proposes each clause's fate; ``citations``
    checks the tree and exits non-zero on any problem; ``predict`` records a
    clause no operator can measure. Usage errors and refusals exit 2."""
    try:
        args = _parser().parse_args(list(argv))
    except SystemExit as exc:
        code = exc.code
        return code if isinstance(code, int) else 2
    try:
        return _VERBS[args.verb](args)
    except (MutationLedgerError, scratch_clone.ScratchCloneError) as exc:
        print(f"mutation_ledger {args.verb}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover - script face
    sys.exit(main(sys.argv[1:]))
