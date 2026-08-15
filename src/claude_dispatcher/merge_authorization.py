"""Unit DF-2 — the authorization and the action must name the same ref.

**P1 scaffold (DF-2-1) wrote this contract plus the record type and the pure
external-approval fold. P2 (DF-2-2) writes the seals — by a different author,
per the DF-4 ruling that a scaffold may not write the seals it will be judged
by. P3 (DF-2-3) writes the body of :func:`authorize_self_approval`, the
``--match-head-commit`` argv leg in :func:`pr.merge_pr`, the
``commit.oid`` parse in :func:`pr.pr_review_state`, and the wiring of both
ladder branches in ``merge_engine._consider_one``. P4 (DF-2-4) rules any
dispute, and in particular the self-approval boundary (question 3 below).**

Every citation below is ``Measured under:`` ``cb9841b``
(``feat/DF-2-1-scaffold-authorization-and-action-must``), gh 2.46.0,
git 2.51.0, CPython 3.13, 2026-08-14, unless a line says
``Predicted (unmeasured)``.

Why this unit exists — two refs, one verdict
============================================
The defect was re-measured on this tree rather than carried from the task
text, and the ORIGINAL FILING DID NOT SURVIVE: it claimed "the merge does not
prove the tree it merges is the tree judged" via an unconsumed panel verdict.
MEASURED: ``grep -cE 'panel_consensus|panel_verdict_'`` over
``merge_engine.py``, ``merge_prs.py``, ``pr.py``, ``plan.py``, ``risk.py`` is
0 for all five — the merge path consumes NO verdict; the only readers are
display code (``report.py``, ``bakeoff.py``, ``cross_family_reviewer.py``,
``orchestrator.py``).

The accurate statement: **authorization and action are computed against
different refs.** ``merge_engine._classify`` hands ``risk.classify`` the
task's BRANCH NAME, and ``risk.collect_diff`` runs ``git diff`` in
``repo_root`` — the local ``refs/heads/<branch>``, with no fetch anywhere on
the authorization path (read on this tree: the only fetch in the engine is
``_sync_local_feature_branch``, which runs AFTER a merge and which DF-1
measured as failing in pr-mode anyway). ``pr.merge_pr`` then runs
``gh pr merge <n> --merge``, which acts on ORIGIN's head of the PR — whatever
that is by the time the request lands. Anything pushed to the branch between
the local diff and origin's merge ships unjudged, under a journal entry that
says it was judged.

Not hypothetical: 7 real ``pr_merged`` events across 25 runs
(EvenPlay/evenplay-mono #809/811/813/815; andrewcostello/claude-dispatcher
#35/36/39). Loss is potential, not historical — both externally-approved
merges had approval-commit == merged head (~21 and ~10 minute windows).

The constraint that shapes the whole contract, re-measured live: five of the
seven merges were low-risk SELF-APPROVALS, and PR #39's ``reviews`` array is
``[]`` — the self-approval path has no external review object AT ALL, so a
fix that pins only from review oids covers two merges in seven. Both ladder
branches must pin, each from its own named source.

The three questions the contract must answer
============================================

**1. Which SHA does an authorization name?** The commit the judged tree
actually was, per ladder branch:

  * *Self-approval (risk ``low``)*: the local ``refs/heads/<branch>`` tip,
    resolved ONCE to a commit SHA and only then judged — the classification
    diff MUST be computed with ``head_ref=<that sha>``, not the branch name,
    so the SHA named is the SHA diffed by construction (pin-then-judge,
    never judge-then-pin). This is :data:`AuthorizedShaSource.LOCAL_CLASSIFIED_TIP`.
    It is NOT the SHA source DF-1 proved stale: DF-1 condemned reading a
    local ref as a *record of what origin did* (the answer); here the local
    tip is the *question* — "this is the tree I judged; origin, merge
    exactly this or refuse."
  * *External approval (risk ``elevated``)*: the ``commit.oid`` of the
    approving reviewer's latest APPROVED review — the tree the reviewer
    actually saw. MEASURED live: ``gh pr view 813 --json reviews`` returns
    ``{"author": {"login": "Pull-Request-Reviewer-Bot"}, "commit":
    {"oid": "4a2e73dfc8b52f6b73781ab7e869fad8f6ea7c86"}, "state":
    "APPROVED"}``, and the GraphQL schema carries
    ``PullRequestReview.commit`` — gh ALREADY returns the value;
    ``pr.pr_review_state`` (pr.py:158-177) iterates those objects keeping
    only ``state`` and ``author.login`` and drops it at the parse. This is
    :data:`AuthorizedShaSource.EXTERNAL_REVIEW_COMMIT`.

  Two rejected sources, each a CHOICE stated so the body cannot drift back
  (structurally: :class:`AuthorizedShaSource` has no member for either):

  * *The branch name* — a moving ref is not a tree. Passing a name to the
    pin re-creates the defect inside the fix: gh would resolve it at merge
    time, which is the "whatever is there by then" read this unit ends.
  * *Origin's branch tip read at merge time* (``git ls-remote`` or a gh
    head query immediately before merging) — an origin read of the WRONG
    question. It names whatever origin holds NOW, so it always "matches"
    and the pin verifies nothing; compare-then-merge in two steps also
    races (TOCTOU) where the one-argv pin is enforced atomically origin-side.

**2. How does the action prove it acts on that SHA?**
``gh pr merge <n> --merge --match-head-commit <sha>``. MEASURED: the flag is
real in the installed gh 2.46.0 (``--match-head-commit SHA   Commit SHA that
the pull request head must match to allow merge``) — the fix is a dispatcher
argv change, not a git operation. Enforcement is origin-side and atomic with
the merge itself: origin compares the PR's head to the pin and refuses the
merge when they differ, so there is no window between check and act. The
argv leg is declared on :func:`pr.merge_pr` (``match_head_commit``); its
body landed with DF-2-3 — the pin travels in the same gh invocation as the
merge, never accepted-and-dropped (see the parameter's docstring).

**3. What happens when the pin does not match — and does the self-approval
path take the same pinning?** Origin refuses, ``merge_pr`` reports the
failure, the row stays Awaiting Review — fail closed, no fallback re-read,
no retry against the moved head (a moved head is a NEW tree that has never
been judged; the only correct next step is a fresh authorization).
Predicted (unmeasured — needs a live moved-head PR, which DF-2-3 measures):
gh's refusal message for a mismatched ``--match-head-commit`` names the head
change ("head branch was modified" in gh's GraphQL error surface) and
matches no entry of ``pr._CONFLICT_MARKERS``, so the engine folds it to
``kind="error"`` — NOT ``needs_rebase`` — which is the correct fold: a
rebase does not re-judge a tree. Whether a mismatch deserves its own named
kind on :class:`pr.MergeResult` is left to DF-2-3's measurement and
DF-2-4's ruling; this scaffold fixes only that it must not wear the
conflict label a rebase is supposed to fix.

On the boundary question DF-2-4 owns: this contract's position is that BOTH
branches pin — the constraint above (five of seven merges were
self-approvals, ``reviews: []``) makes a fix that hardens only the elevated
branch a fix for the minority path. The two branches pin from DIFFERENT
named sources, and that asymmetry is the honest shape: each pins the tree
its own authorizer actually judged. The adjudicator may rule the boundary
differently; the enum keeps each source a named member so a ruling is an
edit to a name, not a silent change of meaning.

Contract surface
================
The record type and the pure fold are DATA and are implemented; the one
git-touching function is :func:`authorize_self_approval`, whose body landed
with DF-2-3.

  * :class:`AuthorizedShaSource` — named provenances, one per ladder
    branch. The two rejected sources are documented refusals, not members.
  * :exc:`AuthorizationUnavailable` — the fail-closed refusal. Raised
    BEFORE the irreversible action, so it is an exception, not
    failure-as-data: ``merge_record.witness_merged_sha`` is total because
    it runs AFTER the merge (an exception there strands a merged row);
    authorization runs BEFORE it, where an ignorable None is the silent
    shape and an exception cannot be ignored. CHOICE — the asymmetry is
    the point, not an inconsistency.
  * :class:`MergeAuthorization` — the record. ``__post_init__`` makes the
    illegal shapes unconstructible (no 40-hex SHA, no named source), so a
    SHA can never travel to the pin without provenance. Implemented in the
    scaffold with :meth:`MergeAuthorization.stamp_fields` — the seals must
    be written against real key names, and a seal cannot be written
    against a stub (the DF-4 precedent).
  * :func:`authorize_external_approval` — the pure fold from a
    :class:`pr.ReviewState` to an authorization. Implemented: it is a pure
    shape over its input (no subprocess), and it is what makes
    ``approved_commit_oid``'s declared meaning checkable now.
  * :func:`authorize_self_approval` — the one observation (a local
    ``git rev-parse``). Body landed with DF-2-3, to the mechanics ruled in
    its docstring.

What this unit does NOT do — each a CHOICE, stated so a later reader does
not infer omission. It does not wire ``merge_engine._consider_one`` — that
is DF-2-3's, with the body: a wired stub breaks every run; an unwired body
is a silent no-op (the DF-3-1 rule). It does not amend the fake-gh harness
in ``tests/test_merge_engine.py`` — tests are denied to this role outright,
and the harness's ``_num()`` first-all-digit-token hazard with digits-only
fixture SHAs is named in DF-2-3's brief for the author allowed to touch it.
It does not add the authorized-SHA keys to the ``pr_merged`` payload — the
pin travels in the ``pr_approved`` event (where the authorization happens);
after the merge, ``merged_sha`` (DF-1's witness) is origin's record and the
merge commit's parents already bind the two for an auditor. And it does not
touch ``_sync_local_feature_branch`` — DF-1 already removed it from the
audit path, and its worktree-freshness job is not this unit's question.
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from claude_dispatcher import pr as pr_mod

#: The one shape origin will compare a pin against: a full 40-char lower-hex
#: object name. Abbreviated, uppercase, or decorated values are refused —
#: ``git rev-parse`` and gh's ``commit.oid`` both emit exactly this shape, so
#: anything else is not a tree either authorizer judged. (Same rule and the
#: same reason as ``merge_record._SHA40``; duplicated one line rather than
#: imported so neither record type's validity can be edited from the other's
#: module.)
_SHA40 = re.compile(r"[0-9a-f]{40}")


class AuthorizedShaSource(Enum):
    """Which authorizer judged the tree a pin names.

    Two members, one per ladder branch. The rejected alternatives are
    refusals recorded in the module docstring (question 1), not members: the
    branch name is a moving ref, and origin's tip read at merge time answers
    the racing "whatever is there now" question this unit exists to end. A
    future source is a new named member reviewed as a shared-contract change
    — never a silent change of what ``authorized_head_sha`` means.
    """

    #: Self-approval: the local ``refs/heads/<branch>`` tip, resolved once
    #: and then diffed — the tree ``risk.classify`` judged, by construction.
    LOCAL_CLASSIFIED_TIP = "local_classified_tip"
    #: External approval: the ``commit.oid`` of the approving reviewer's
    #: latest APPROVED review — the tree the reviewer actually saw.
    EXTERNAL_REVIEW_COMMIT = "external_review_commit"


class AuthorizationUnavailable(RuntimeError):
    """No authorization can name a SHA — so no merge may act.

    Raised BEFORE the irreversible step (contrast
    :func:`merge_record.witness_merged_sha`, which is total because it runs
    after). The caller's only correct fold is HOLD: the row stays Awaiting
    Review with the reason journaled; consulting a fallback source here
    would be the defect wearing the fix's name.
    """


@dataclass(frozen=True)
class MergeAuthorization:
    """What one authorization proves: PR ``pr_number`` was judged at
    ``head_sha``, by the authorizer ``source`` names.

    Frozen because the record is a receipt, not a handle. The constructor
    enforces the shape (see ``__post_init__``), so downstream code — the
    ``--match-head-commit`` argv, the ``pr_approved`` journal fold, the
    seals — may rely on the invariants without re-checking them: a SHA can
    never reach the pin without a named provenance.
    """

    #: Which PR this authorizes — what origin will compare the pin against.
    pr_number: int
    #: The commit the judged tree was. This exact value — no re-resolution —
    #: is what ``pr.merge_pr`` must pass as ``match_head_commit``.
    head_sha: str
    #: Which authorizer judged ``head_sha``. Present always; there is no
    #: unauthorized-but-constructed shape.
    source: AuthorizedShaSource

    def __post_init__(self) -> None:
        if not isinstance(self.source, AuthorizedShaSource):
            raise ValueError(
                "MergeAuthorization: source must be a named "
                f"AuthorizedShaSource member, got {self.source!r} — a SHA "
                "without provenance is a pin nobody can audit"
            )
        if not isinstance(self.head_sha, str) or not _SHA40.fullmatch(self.head_sha):
            raise ValueError(
                "MergeAuthorization: head_sha must be a 40-char lower-hex "
                f"SHA, got {self.head_sha!r} — anything else is not a tree "
                "either authorizer judged, and origin would compare the pin "
                "against a value that never named one"
            )

    def stamp_fields(self) -> dict[str, Any]:
        """The audit keys this authorization contributes to the
        ``pr_approved`` journal payload — the one place the key names live,
        fixed now so the seals are written against the real shape.

        Always both keys: ``authorized_head_sha`` (the pinned commit) and
        ``authorized_head_source`` (its provenance). There is no
        keys-absent state — an authorization that cannot name a SHA is
        :exc:`AuthorizationUnavailable` and never constructs, so unlike
        ``MergedShaWitness.stamp_fields`` this fold has one leg. CHOICE —
        the keys go on ``pr_approved`` (where the authorization happens),
        not ``pr_merged`` (module docstring, "what this unit does NOT do").
        """
        return {
            "authorized_head_sha": self.head_sha,
            "authorized_head_source": self.source.value,
        }


def authorize_external_approval(
    *,
    pr_number: int,
    review: pr_mod.ReviewState,
) -> MergeAuthorization:
    """Fold an approved :class:`pr.ReviewState` into an authorization.

    Pure over its input — no subprocess, IMPLEMENTED in the scaffold for the
    DF-1-1 reason (a pure shape the seals must bind to by real behavior, not
    by stub). The SHA is ``review.approved_commit_oid`` — the commit the
    approving reviewer's latest APPROVED review was submitted against, which
    ``pr.pr_review_state`` owes to DF-2-3 (today its parse drops the oid;
    the field is declared and defaults to None).

    Raises :exc:`AuthorizationUnavailable` — fail closed, never a pin from
    another source — when the state is not approved, carries a read error,
    or names no oid. The no-oid case is REAL today by construction (the
    parse owing above), and stays real after DF-2-3 for a review GitHub
    returns without a commit (deleted branch histories); either way the
    answer is the same: a reviewer whose judged tree cannot be named has
    not authorized any particular tree.
    """
    if review.error:
        raise AuthorizationUnavailable(
            f"review state for PR #{pr_number} could not be read "
            f"({review.error}); an unreadable approval authorizes nothing"
        )
    if not review.approved:
        raise AuthorizationUnavailable(
            f"PR #{pr_number} has no current external approval; "
            "there is no authorization to pin"
        )
    oid = review.approved_commit_oid
    if not isinstance(oid, str) or not _SHA40.fullmatch(oid):
        raise AuthorizationUnavailable(
            f"PR #{pr_number} is approved but the approval names no "
            f"judgeable commit (approved_commit_oid={oid!r}); a reviewer "
            "whose judged tree cannot be named has not authorized any "
            "particular tree"
        )
    return MergeAuthorization(
        pr_number=pr_number,
        head_sha=oid,
        source=AuthorizedShaSource.EXTERNAL_REVIEW_COMMIT,
    )


def authorize_self_approval(
    *,
    cwd: Path,
    pr_number: int,
    branch: str,
) -> MergeAuthorization:
    """Resolve the local branch tip the classification will judge — the one
    observation of this unit. Body landed with DF-2-3, to the mechanics the
    DF-2-1 scaffold ruled:

      * The resolution is ``git rev-parse --verify refs/heads/<branch>^{commit}``
        run in ``cwd`` (the engine's ``repo_root``) — the SAME ref
        ``risk.collect_diff`` diffs there, fully qualified so a tag or
        remote-tracking ref of the same name can never answer for it.
      * PIN-THEN-JUDGE: the caller resolves FIRST and passes the returned
        ``head_sha`` — not the branch name — as ``risk.classify``'s
        ``head_ref``, so the SHA named is the SHA diffed by construction.
        Resolving after (or beside) the diff re-opens the window this unit
        closes, one process-local layer down.
      * Any failure — git missing, exit non-zero, output not a 40-hex SHA —
        raises :exc:`AuthorizationUnavailable` naming the reason. Fail
        closed: no merge may proceed on "the ref was probably fine".
        Timeout bound and subprocess hygiene mirror ``risk.collect_diff``
        (60s, ``GIT_TERMINAL_PROMPT=0``).
      * This is NOT the SHA source DF-1 proved stale (module docstring,
        question 1): DF-1 condemned a local ref read as a *record* of
        origin's action; here the local tip is the *question* the pin puts
        to origin, and a divergence is answered by origin's refusal, not by
        a wrong stamp.
    """
    cmd = ["git", "rev-parse", "--verify", f"refs/heads/{branch}^{{commit}}"]
    try:
        proc = subprocess.run(
            cmd, cwd=str(cwd), capture_output=True, text=True, check=False,
            timeout=60, env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
        )
    except subprocess.TimeoutExpired as exc:
        raise AuthorizationUnavailable(
            f"git rev-parse timed out after 60s resolving refs/heads/{branch} "
            f"in {cwd} (PR #{pr_number}); an unresolvable branch authorizes "
            "nothing"
        ) from exc
    except OSError as exc:
        raise AuthorizationUnavailable(
            f"git rev-parse failed to launch in {cwd} for PR #{pr_number}: "
            f"{exc}"
        ) from exc
    if proc.returncode != 0:
        detail = (proc.stderr or "").strip() or f"exit {proc.returncode}"
        raise AuthorizationUnavailable(
            f"refs/heads/{branch} does not resolve to a commit in {cwd} "
            f"(PR #{pr_number}: {detail}); a branch that names no commit "
            "authorizes nothing"
        )
    sha = proc.stdout.strip()
    if not _SHA40.fullmatch(sha):
        raise AuthorizationUnavailable(
            f"git rev-parse for refs/heads/{branch} in {cwd} returned "
            f"{sha!r}, not a 40-char lower-hex SHA — not a tree anyone judged "
            f"(PR #{pr_number})"
        )
    return MergeAuthorization(
        pr_number=pr_number,
        head_sha=sha,
        source=AuthorizedShaSource.LOCAL_CLASSIFIED_TIP,
    )
