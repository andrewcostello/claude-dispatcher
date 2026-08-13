"""Unit DF-1 — what a merge record must prove about the SHA it names.

**P1 scaffold. This module is CONTRACT plus the implemented record type and
its stamp fold; the one observation function is a stub. P2 (DF-1-2) writes
the seals — by a different author, per the DF-4 ruling that a scaffold may
not write the seals it will be judged by. P3 (DF-1-3) writes the body and
rewires the one call site in ``merge_engine._consider_one``. P4 (DF-1-4)
rules on the condemned seal (below) and any dispute the body raises.**

Every citation below is ``Measured under:`` ``24e72f0``
(``feat/DF-1-1-scaffold-name-what-a-merge``), git 2.51.0, CPython 3.13.7,
2026-08-13, in throwaway repositories under ``/tmp``, unless a line says
``Predicted (unmeasured)``.

Why this unit exists — the stamp does not track origin
======================================================
MEASURED (task DF-1-1, run journals of this effort): every recorded merge
stamps a ``merged_sha`` that does not track origin. Two DIFFERENT PRs merged
in the same run recorded IDENTICAL post-merge SHAs — impossible if the ref
followed origin. All 7 recorded ``pr_merged`` events are affected. The
audit trail cannot say what was merged.

The mechanism, re-measured for this scaffold rather than carried from the
task text: ``_sync_local_feature_branch`` runs ``git fetch origin fb:fb``
from ``repo_root``. When ``fb`` is checked out there — which is exactly the
pr-mode run configuration, where the run's feature branch IS the working
branch of the repo the engine points at — git refuses the ref update
entirely: measured ``fatal: refusing to fetch into branch 'refs/heads/fb'
checked out at ...``, exit 128, with the local ref left untouched; the same
command with ``fb`` not checked out fast-forwards and exits 0. The sync is
declared best-effort, so the refusal is logged and swallowed, and
``_feature_branch_sha`` then reads the frozen local tip — the same value,
merge after merge. The stamp was never wrong loudly; it was wrong silently,
seven times, under a key (``feature_branch_sha``) whose documented meaning
("the feature-branch tip after the merge") the value never had.

The three questions the contract must answer
============================================

**1. Where the authoritative SHA comes from: origin's record of THIS merge,
never a local ref.** The authoritative value is the merge commit origin
created when the PR landed — GitHub's own record of the merge, read back
per-PR (``gh pr view <n> --json mergeCommit``; Predicted (unmeasured) —
reading it needs a live GitHub PR, which the seals and body measure against
the fake-gh harness and a real run respectively). Two rejected sources,
each a CHOICE stated so the body cannot drift back:

  * *Any local ref* — ``_feature_branch_sha`` and every read derived from
    ``refs/heads/<fb>`` in ``repo_root``. That is the value this unit
    proves wrong; the task forbids it by name, and this contract makes the
    forbidding structural: :class:`ShaSource` has no member for it, so a
    witness carrying a local read cannot even say where it came from.
  * *Origin's branch tip* (``git ls-remote origin refs/heads/<fb>``) — an
    origin read, but of the WRONG question. The tip races: read after a
    sibling merge (or any concurrent push) it names the later state, and
    two records can share a SHA while both telling the truth about the
    tip. The measured defect is many-merges-one-SHA; a source that can
    reproduce that shape honestly is not the fix. The merge commit is
    per-PR and immutable — distinct merges name distinct SHAs by
    construction, which is the property the seals must be able to check.

**2. What a merge record must carry to be checkable afterwards.** A record
is checkable when an auditor holding ONLY the record and network access to
origin can re-ask the question and get yes or no: for row
(``pr_number``, ``target``), does origin's record of that PR's merge name
``sha``? So the witness carries the identifiers of the question
(``pr_number``, ``target``), the answer (``sha``), the named provenance
(``source`` — so a checker knows WHICH question the SHA answers, and a
future source is a new named member, not a silent change of meaning), and
the named ``state`` (observed vs unavailable — so absence is a recorded
fact, not a missing key a reader guesses about). The stamp fold
(:meth:`MergedShaWitness.stamp_fields`) fixes the YAML/journal key names
now, so the seals are written against the real shape:

  * observed:    ``merged_sha``, ``merged_sha_source``,
    ``merged_sha_state: "observed"``
  * unavailable: NO ``merged_sha`` key at all;
    ``merged_sha_state: "unavailable"``, ``merged_sha_detail: <why>``

  The ``pr_merged`` journal payload carries the same keys and RETIRES
  ``feature_branch_sha`` — that key's documented meaning is a claim the
  recorded values never satisfied, and keeping the name while fixing the
  value would leave seven historical events and every future one
  indistinguishable under one key. CHOICE — ``docs/journal-format.md``
  (line ~463) and the ``journal.py`` event-type comment are updated by
  DF-1-3 WITH the body, not by this scaffold: the doc describes what the
  journal actually writes, and until the body lands the journal still
  writes the old shape — a doc ahead of the code is a second silent
  disagreement, which is the defect class this unit exists to end.

**3. What happens when the read fails: a named state, never a silently
stale stamp.** When origin cannot answer — gh missing, network down,
gh's answer missing the field — the witness is
:data:`WitnessState.UNAVAILABLE` with a non-empty ``detail``, the stamp
writes ``merged_sha_state: "unavailable"`` and NO ``merged_sha``, and no
other source is consulted. CHOICE — there is deliberately no labeled
fallback (no ``source: local_ref`` member for a best-effort local read):
a labeled stale value is not silent, but it is still uncheckable — the
local ref moves and the worktree dies, so no auditor can later confirm or
refute it, and an uncheckable value under the ``merged_sha`` key is the
old defect wearing a provenance label. Unavailable is itself checkable:
the auditor re-asks origin, which still has the answer.

The condemned seal — named here, ruled elsewhere
===============================================
``tests/test_merge_engine.py:313`` asserts
``merged[0].payload["feature_branch_sha"]`` — truthiness of a value now
known to be wrong: it passes on the frozen local tip, seven times over.
It is the live instance of "a seal asserting truthiness of a value now
known to be wrong" that DF-1-2's brief names. **Scope: NOT this
scaffold's to amend or strike.** Two reasons, each sufficient: the DF-4
ruling — a scaffold may not write (or rewrite) the seals it will be
judged by — and the unit's own structure, which places
``tests/test_merge_engine.py`` in DF-1-4's ``disputed_paths``: the ruling
on amend-vs-strike is the adjudicator's, made with DF-1-2's replacement
rows and DF-1-3's body in evidence. This contract's obligation is to name
it, which this section does.

Contract surface
================
The record type and its folds are DATA and are implemented; the one
control-flow function is stubbed.

  * :class:`ShaSource` — named provenances. One member; the two rejected
    sources are documented refusals, not members.
  * :class:`WitnessState` — observed / unavailable. No third state.
  * :class:`MergedShaWitness` — the record. Its ``__post_init__`` makes
    the illegal shapes unconstructible (an observed witness without a
    SHA, an unavailable one with a SHA or without a reason), so the
    invariants hold by construction, not by caller discipline.
    Implemented in the scaffold, with :meth:`MergedShaWitness.stamp_fields`
    — CHOICE, mirroring DF-4's ``scrubbed_git_env``: they are pure shapes
    over the record, the seals must be written against the real key names,
    and a seal cannot be written against a stub.
  * :func:`witness_merged_sha` — STUB. DF-1-3 writes the body.

What this unit does NOT do — each a CHOICE, stated so a later reader does
not infer omission. It does not rewire ``merge_engine._consider_one`` —
that is DF-1-3's, with the body: wiring a stub raise into a live merge
pass turns every successful merge into a crash, and this repo's merge
engine promises to never let one bad step abort a pass. It does not
delete ``_sync_local_feature_branch`` — that function's OTHER job
(advancing the local ref so the next worktree forks from merged code) is
real, its measured failure in checked-out repos is a worktree-freshness
defect, not an audit defect, and units DF-2/DF-3 own the ref-vs-action
questions; this unit removes it from the AUDIT path only. And it emits no
migration of the seven wrong historical events — the journal is
append-only and hash-chained; rewriting history to look right is the
opposite of an audit trail.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any


class ShaSource(Enum):
    """Where a witnessed SHA came from. The provenance a checker needs to
    know WHICH question the SHA answers.

    One member. The rejected alternatives are refusals recorded in the
    module docstring (question 1), not members: a local ref is the value
    this unit proves wrong, and origin's branch tip answers a racing
    question two truthful records can collide on. A future source is a new
    named member reviewed as a shared-contract change — never a silent
    change of what ``merged_sha`` means.
    """

    #: GitHub's own record of the PR's merge commit
    #: (``gh pr view <n> --json mergeCommit``). Per-PR and immutable:
    #: distinct merges name distinct SHAs by construction.
    ORIGIN_PR_MERGE_COMMIT = "origin_pr_merge_commit"


class WitnessState(Enum):
    """Whether origin answered. No third state — a partial answer is
    UNAVAILABLE with the partiality in ``detail``, because a stamp a
    checker cannot re-ask origin about is the defect, whatever its key."""

    #: Origin answered; ``sha`` and ``source`` are present.
    OBSERVED = "observed"
    #: Origin could not answer; ``sha`` is None and ``detail`` says why.
    #: Never accompanied by a value from any other source.
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class MergedShaWitness:
    """What one merge records about the SHA origin created for it.

    Frozen because the record is a receipt, not a handle. The constructor
    enforces the shape (see ``__post_init__``): no observed witness
    without a SHA and source, no unavailable witness with a SHA or without
    a reason — so downstream code (the stamp fold, the journal emit, the
    seals) may rely on the invariants without re-checking them.
    """

    #: Which PR this witnesses — half of the question an auditor re-asks.
    pr_number: int
    #: The branch the PR merged into — the other half.
    target: str
    #: Observed or unavailable. The stamp always records which.
    state: WitnessState
    #: The merge commit SHA origin reports, when observed; None when not.
    sha: str | None = None
    #: Provenance of ``sha``. Present exactly when ``sha`` is.
    source: ShaSource | None = None
    #: Why origin could not answer, when unavailable ("gh binary not
    #: found", "no mergeCommit in gh answer", a timeout). Empty when
    #: observed.
    detail: str = ""

    def __post_init__(self) -> None:
        if self.state is WitnessState.OBSERVED:
            if not self.sha or self.source is None:
                raise ValueError(
                    "MergedShaWitness: OBSERVED requires a non-empty sha and "
                    "a named source — an observed witness with neither is a "
                    "stale stamp wearing the success state"
                )
        elif self.state is WitnessState.UNAVAILABLE:
            if self.sha is not None or self.source is not None:
                raise ValueError(
                    "MergedShaWitness: UNAVAILABLE may not carry a sha or "
                    "source — a value smuggled past the named failure state "
                    "is the silently stale stamp this unit exists to end"
                )
            if not self.detail:
                raise ValueError(
                    "MergedShaWitness: UNAVAILABLE requires a non-empty "
                    "detail — an unexplained absence is not checkable"
                )
        else:  # pragma: no cover - enum is closed; guards a fourth member
            raise ValueError(f"MergedShaWitness: unknown state {self.state!r}")

    def stamp_fields(self) -> dict[str, Any]:
        """The audit keys this witness contributes to the task row AND the
        ``pr_merged`` journal payload — the one place the key names live.

        observed:    ``merged_sha``, ``merged_sha_source``,
        ``merged_sha_state``. unavailable: ``merged_sha_state`` and
        ``merged_sha_detail``, and NO ``merged_sha`` key — absence plus a
        named state, rather than a null a reader must interpret, so a
        truthiness check over ``merged_sha`` can never pass on an
        unavailable witness. ``feature_branch_sha`` is deliberately not
        among these keys in either state (module docstring, question 2:
        the key is retired with the body, not renamed-in-place).
        """
        if self.state is WitnessState.OBSERVED:
            # Invariants guaranteed by __post_init__; asserts document them
            # at the use site for the reader, not re-check them for safety.
            assert self.sha is not None and self.source is not None
            return {
                "merged_sha": self.sha,
                "merged_sha_source": self.source.value,
                "merged_sha_state": self.state.value,
            }
        return {
            "merged_sha_state": self.state.value,
            "merged_sha_detail": self.detail,
        }


def witness_merged_sha(
    *,
    cwd: Path,
    pr_number: int,
    target: str,
    gh_bin: str = "gh",
) -> MergedShaWitness:
    """Ask origin which merge commit it created for ``pr_number``.

    Runs after :func:`pr.merge_pr` reports the merge landed; the answer is
    GitHub's own record of the merge (:data:`ShaSource.ORIGIN_PR_MERGE_COMMIT`),
    read from ``cwd`` with ``gh_bin`` in the style of the other ``pr.py``
    seams. TOTAL: this function never raises on its own behalf — the merge
    has already happened on origin when it runs, so an exception here would
    abort the pass AFTER the irreversible step and strand a merged PR's row
    at Awaiting Review; every failure (gh missing, timeout, non-zero exit,
    an answer without the field, an answer that is not a SHA) returns an
    :data:`WitnessState.UNAVAILABLE` witness whose ``detail`` names it.
    CHOICE — failure-as-data over failure-as-exception mirrors
    ``pr.MergeResult``, and it is what makes "never a silently stale stamp"
    mechanical: the caller cannot forget to handle a failure it receives as
    the very record it was going to stamp.

    Consults no local ref in any branch of its body — not as a source, not
    as a fallback, not as a tiebreak. ``_feature_branch_sha`` is the value
    this unit proves wrong.

    P1 STUB — the seals (P2, DF-1-2, a different author) drive this
    signature; P3 (DF-1-3) writes the body and rewires
    ``merge_engine._consider_one`` to stamp ``stamp_fields()`` in place of
    the ``_sync_local_feature_branch`` + ``_feature_branch_sha`` pair. The
    row that matters must FAIL against today's behavior: two PRs merged in
    one run recording the same SHA.
    """
    raise NotImplementedError(
        "DF-1 P1 scaffold: witness_merged_sha is contract only — P3 "
        "(DF-1-3) writes the body. Do NOT fall back to _feature_branch_sha "
        "or any local ref; that value is the defect this unit exists to end."
    )
