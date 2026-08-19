"""Unit W2-3 — a durable ledger for mutation-coverage claims.

**SCAFFOLD (W2-3-1): contract only.** Four folds — :func:`freshness_of`,
:func:`classify_observation`, :func:`fold`, :func:`proposed_fate` — are this
row's declared holes and raise :class:`NotImplementedError` on purpose;
W2-3-2 seals them, W2-3-3 fills them. Nothing imports this module yet.

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

import datetime
import hashlib
import json
import math
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Sequence

from . import role_protocol

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
    it. The cost is that a :class:`Rederivation` cannot answer either
    question until W2-3-3 fills :func:`freshness_of` and :func:`fold`, which
    is the correct order.
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
# Implemented here because each fails SILENTLY when it is wrong: an id that
# drifts from what it names, a ledger the body role cannot write, a parsed
# line whose "false" became True, a ledger with two current observations for
# one claim. The IO and the folds are left to W2-3-3 — a missing subprocess
# is loud, and a fold is the decision W2-3-2's rows must be able to redden.
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
# THE FOUR FOLDS — declared holes, owed by W2-3-3 (bodies), sealed by W2-3-2.
#
# These are the decision this unit is about, so a scaffold that implemented
# them would hand W2-3-2 rows written against existing code. The BEHAVIOUR is
# specified here and on the enum members; only the table is the body's.
# --------------------------------------------------------------------------- #


def freshness_of(drift: Sequence[Drift]) -> Freshness:
    """The observed drift set folded to one :class:`Freshness`.

    Total, and single-valued so :func:`fold` is a table. Precedence, and it
    is load-bearing rather than cosmetic — report the strongest fact, and
    absence of the thing being compared outranks a difference in it:

      1. :data:`HARD_ABSENCE` in declaration order — SUBJECT_ABSENT,
         SITE_ABSENT, ROW_ABSENT — to SUBJECT_GONE, SITE_GONE, ROW_GONE.
      2. :attr:`Drift.REVISION_ABSENT` to
         :attr:`Freshness.PROVENANCE_GONE`. Below hard absence and above the
         MOVED members, because it blocks the audit of the record's
         provenance and not the comparison itself.
      3. :attr:`Drift.SUBJECT_BYTES` to :attr:`Freshness.SUBJECT_MOVED`.
      4. :attr:`Drift.POPULATION` to :attr:`Freshness.POPULATION_MOVED`.
      5. Empty to :attr:`Freshness.ANCHORED`.

    Nothing is lost by the fold: the full set stays on
    :attr:`Rederivation.drift`.
    """
    raise NotImplementedError("W2-3-3 owes this fold; W2-3-2 seals it")


def classify_observation(*, control: Mapping[str, RowResult],
                         mutant: Mapping[str, RowResult], claiming_row: str,
                         recorded_reddened: Sequence[str]) -> Observation:
    """What one control/mutant pair showed, over ROW-level results.

    Both maps are row-level — pass them through :func:`fold_row_results`
    first. Total over :class:`Observation`; the members are reached in this
    order, and the order is the contract:

      * BOTH maps empty — neither run reported anything —
        :attr:`Observation.NOT_ATTEMPTED`.
      * exactly ONE map empty — :attr:`Observation.HARNESS_FAULT`. The other
        run collected and reported rows, so the tree is runnable and this one
        broke. "Empty" is not how a crashed pytest is reported to this
        function; :func:`rederive` may not reach here on a run it could not
        complete.
      * ``claiming_row`` ERRORED or ABSENT in the CONTROL —
        :attr:`Observation.HARNESS_FAULT`. ABSENT here is "collected and then
        not reported": :func:`rederive` resolves the row against the tree
        first and reports a genuinely uncollected row as
        :attr:`Drift.ROW_ABSENT` with NOT_ATTEMPTED, so by this point a
        control that cannot execute the row is a broken run and not a fact
        about the claim. Reading either as CONTROL_RED would turn a broken
        environment into a durable relabelling of the clause.
      * ``control[claiming_row]`` FAILED — :attr:`Observation.CONTROL_RED`.
        Checked before the mutant, so a row that is red anyway can never read
        as reddened.
      * ``claiming_row`` ERRORED or ABSENT under the MUTANT —
        :attr:`Observation.MUTANT_UNEVALUABLE`. The assertion the claim is
        about was never reached, so this is not SURVIVED; and it reproduces
        on every re-run, so it is not HARNESS_FAULT. Reading an error as a
        failure is how a broken import becomes coverage.
      * ``mutant[claiming_row]`` PASSED — :attr:`Observation.SURVIVED`.
      * otherwise (FAILED under the mutant), compare the REDDENED SET against
        ``recorded_reddened``: equal is
        :attr:`Observation.REDDENED_AS_RECORDED`, different is
        :attr:`Observation.REDDENED_SCOPE_DIVERGED`. As sets — order is not
        a fact about a run.

    **The reddened set is the PASSED-to-FAILED transition set**: rows that
    were PASSED in the control and are FAILED under the mutant. Not "rows
    failing under the mutant", which credits the mutation with every
    baseline failure in the file and is how a broken fixture turns into a
    blast radius. This is also why one ``control_green`` boolean is enough on
    the wire: a transition set cannot contain a row that was already red, so
    the full control map is not needed to re-compare one.
    """
    raise NotImplementedError("W2-3-3 owes this fold; W2-3-2 seals it")


def fold(freshness: Freshness, observation: Observation) -> Status:
    """:class:`Freshness` and :class:`Observation` folded to one
    :class:`Status`.

    TOTAL over all 7 x 7 combinations, and no combination may fold to "kept
    as it was". Precedence, in order:

      1. ``observation is HARNESS_FAULT`` — :attr:`Status.FAULTED`. A broken
         RUN says nothing about the claim, at any freshness.
      2. ``observation`` in {NOT_ATTEMPTED, CONTROL_RED, MUTANT_UNEVALUABLE}
         — :attr:`Status.UNDERIVABLE`, at any freshness. No refuting
         comparison was possible: nothing to look at, a control that was
         already red, or a mutation this site cannot be evaluated under.
         This arm comes BEFORE the absence arm on purpose: a deleted row, a
         deleted subject and an unresolvable anchor are the cases UNDERIVABLE
         names, and they arrive here as absence drift carrying NOT_ATTEMPTED.
         Ranked the other way they fold to FAULTED, whose fate is
         :attr:`ClauseFate.AWAIT_RERUN` — and no number of re-runs restores a
         row that was deleted, so the clause is stranded un-relabelled and
         un-struck forever, which is "kept as it was" under another name.
         MUTANT_UNEVALUABLE is in this arm for the same reason from the other
         side: it reproduces identically on every re-run.
      3. ``freshness`` in {SUBJECT_GONE, SITE_GONE, ROW_GONE} —
         :attr:`Status.FAULTED`. Only reachable now with a COMPLETED
         comparison, which is a record contradicting itself: nothing can
         report both that the row was absent and that it reddened.
      4. ``observation is REDDENED_SCOPE_DIVERGED`` —
         :attr:`Status.SCOPE_BROKEN`, at any remaining freshness.
      5. ``freshness is ANCHORED`` — REDDENED_AS_RECORDED to
         :attr:`Status.HELD`, SURVIVED to :attr:`Status.BROKEN`.
      6. otherwise (SUBJECT_MOVED, POPULATION_MOVED, PROVENANCE_GONE) —
         REDDENED_AS_RECORDED to :attr:`Status.REANCHORED`, SURVIVED to
         :attr:`Status.EXPIRED`. PROVENANCE_GONE is here and not with the
         absences because the comparison at the target tree was a real one:
         a claim whose recorded revision was rebased away is still refutable,
         and is owed a fresh observation rather than a permanent wait.

    Refuse an argument that is not a member rather than answering: an unknown
    input reaching a default arm is how a fold silently keeps an entry.
    """
    raise NotImplementedError("W2-3-3 owes this fold; W2-3-2 seals it")


def proposed_fate(status: Status) -> ClauseFate:
    """What is PROPOSED for the clause behind an observation with ``status``.

    Proposed, not applied: W2-3-4 rules and W2-3-2 edits. Total over
    :class:`Status`, and it must refuse a member it has no fate for, so that
    a new :class:`Status` cannot ship unruled:

      HELD to CITE_CLAIM; REANCHORED to REOBSERVE_THEN_CITE; SCOPE_BROKEN to
      AMEND_SCOPE; BROKEN and EXPIRED to STRIKE; UNDERIVABLE to
      RELABEL_PREDICTED; FAULTED to AWAIT_RERUN.

    Every fate but AWAIT_RERUN disposes of the clause, and AWAIT_RERUN is
    reachable only from :attr:`Status.FAULTED`, whose causes are all faults
    in the RUN — so a clause waits only while the repository cannot run it,
    and every fact about the mutation or the tree reaches a fate that
    disposes of it. :data:`PREDICTION_FATE` covers the other record kind.
    """
    raise NotImplementedError("W2-3-3 owes this table; W2-3-2 seals it")


# --------------------------------------------------------------------------- #
# The harness — owed by W2-3-3. Every one is IO or a subprocess, where a
# missing implementation is loud rather than silent.
# --------------------------------------------------------------------------- #


def apply_mutation(source: bytes, site: MutationSite) -> bytes:
    """``source`` with ``site``'s mutation applied.

    Resolve ``site.anchor`` with :mod:`ast` against ``source`` itself, never
    by line number, so the same recorded mutation re-applies to a body that
    has changed. Refuse (do not no-op) when the anchor does not resolve or
    the operator does not fit what is there — a returned copy of the input
    would be recorded as a mutation that reddened nothing.
    """
    raise NotImplementedError("W2-3-3 owes the applier")


def provision_subject_tree(repo_root: str, revision: str, dest: str) -> object:
    """A quarantined :class:`scratch_clone.ScratchClone` of ``revision``.

    ``git worktree add --detach`` then
    :func:`scratch_clone.make_scratch_clone`, which severs and re-inits the
    copy. The subject module is on :data:`role_protocol.FLOOR_GLOBS`, so the
    mutation goes into the CLONE through
    :func:`scratch_clone.swap_in`/``swap_back`` and the real tree is never
    edited. Remove ``.claude/workflow`` from the staging worktree first: it
    is a symlink out of the tree and the clone refuses one.
    """
    raise NotImplementedError("W2-3-3 owes the provisioner")


def collect_rows(clone: object, seal_file: str) -> tuple[str, ...]:
    """The function-level rows ``seal_file`` collects in ``clone``, sorted.

    Collection only. This is the input to :func:`population_digest`, so a
    collection error must RAISE rather than return a short list: a truncated
    population reads as a file that shrank.
    """
    raise NotImplementedError("W2-3-3 owes the collector")


def run_rows(clone: object, seal_file: str) -> Mapping[str, RowResult]:
    """Run ``seal_file`` in ``clone``; node id to :class:`RowResult`.

    Node-id level, including parametrisations — :func:`fold_row_results` is
    the caller's step. A row that was collected but not reported is ABSENT,
    never PASSED.
    """
    raise NotImplementedError("W2-3-3 owes the runner")


def rederive(entry: LedgerEntry, *, repo_root: str,
             mode: RederiveMode = RederiveMode.AT_TARGET,
             target: str | None = None,
             budget_seconds: float = PER_ENTRY_BUDGET_SECONDS) -> Rederivation:
    """Re-derive one entry: provision, control run, mutant run, compare.

    Never re-reads the docstring, and never trusts the entry beyond its
    inputs. Under :attr:`RederiveMode.AT_RECORDED` a ``target`` is refused —
    two answers to "which tree" is the defect :class:`RederiveMode` prevents.

    Returns a :class:`Rederivation` in every terminating case, including
    failure. The split between the two failure shapes is the contract:

      * A BROKEN RUN — clone refused, ``budget_seconds`` exceeded, pytest
        unusable, a provisioned tree that is not the one the entry names —
        is :attr:`Observation.HARNESS_FAULT`, with the reason in ``detail``.
        Every one of those is worth retrying.
      * A TREE THAT LACKS WHAT THE ENTRY NAMES — no subject file, no
        resolvable anchor, no claiming row, or (in AT_RECORDED) no such
        revision to provision — is DRIFT: the matching :class:`Drift` member
        on ``drift``, with :attr:`Observation.NOT_ATTEMPTED`. It is a fact
        about the tree, not a fault, and re-running cannot change it.

    That split is what :func:`classify_observation` is entitled to assume:
    the claiming row was COLLECTED in both runs before it is called, so an
    ABSENT there means "collected and then not reported", which is a broken
    run rather than a missing row. Do not call it on a run that did not
    complete.

    Nothing here raises to mean "the claim failed" — that is a
    :class:`Status`.
    """
    raise NotImplementedError("W2-3-3 owes the harness")


def load_ledger(path: str) -> tuple[LedgerRecord, ...]:
    """Every record in one ledger file, validated as a whole.

    Blank lines are skipped; a malformed line refuses the whole file rather
    than being dropped, and :func:`validate_ledger` runs on the result.
    """
    raise NotImplementedError("W2-3-3 owes the reader")


def write_ledger(path: str, records: Sequence[LedgerRecord]) -> None:
    """Write a ledger, refusing one that :func:`validate_ledger` rejects and
    a ``path`` that :func:`refuse_unwritable_ledger_path` rejects.

    Admission is a separate question from consistency, and this function
    answers only the second: the ids on a record prove it is self-consistent,
    not that a run produced it. A caller adding an observation it did not
    measure is writing a well-formed lie, which is why the CLI's ``rederive``
    verb — not this function — is what admits evidence.
    """
    raise NotImplementedError("W2-3-3 owes the writer")


def check_citations(repo_root: str) -> tuple[str, ...]:
    """Every ledger citation in the tree that no longer holds up.

    The check that closes the loop the other direction: a clause relabelled
    to cite ``ml-…`` is only as good as the record behind it, and nothing
    else here answers "does every id in this repository still resolve to a
    live record whose status reads as coverage".

    Greps for :data:`CITATION_ID`, resolves each against its subject's ledger
    through :func:`current_observations` and the prediction set, and returns
    one line per problem — unresolved, superseded, cited as a claim whose
    live observation does not :func:`counts_as_coverage`, or an ``mlo-``
    observation id cited where a claim id belongs (an observation id is
    evidence and is replaced; a citation to one goes stale by design).
    Empty when the tree is clean, so the CLI verb can exit on its length.
    """
    raise NotImplementedError("W2-3-3 owes the citation check")


def main(argv: Sequence[str]) -> int:
    """The CLI face, owed by W2-3-3. Three verbs:

      * ``rederive`` — re-run entries and report each :class:`Status`.
      * ``fates`` — :func:`proposed_fate` over a ledger, for W2-3-4 to rule.
      * ``citations`` — :func:`check_citations` over the tree, non-zero exit
        on any problem.

    It does not exist yet, and the module is deliberately not wired to
    ``__main__`` until it does: a command that half-runs is worse than one
    that is absent.
    """
    raise NotImplementedError("W2-3-3 owes the CLI")
