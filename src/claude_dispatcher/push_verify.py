"""Post-Done push/PR verification.

A Tasker that finishes a task on the standard PR-raising workflow is expected
to (a) push its feature branch to the remote and (b), when the run raises PRs,
open a pull request — *before* it writes ``Status: Done``. DISP-9 reported Done
with commits but never pushed; no PR was raised, and integration only found it
by accident. This module is the deterministic check the dispatcher runs after a
Done task to catch that failure mode early, mirroring the commit-retry safety
net (``orchestrator._has_commits_on_branch``).

The check is pure and side-effect-free apart from the git/gh reads it issues, so
it is unit-testable with an injected ``run`` callable. The orchestrator owns the
*recovery* (a single corrective push/PR-only re-spawn) and the YAML/journal
write-back; this module only answers "is the branch pushed, and does a PR exist
when one is expected?".

Out of scope: the auto-integrate (direct-to-base) workflow never pushes — that
is the human's call (see ``auto_integrate.py``) — so the orchestrator does not
invoke this module for auto-integrate runs.

``verify_landed`` is the rung above. Pushing is not landing: a task can push a
branch, open a PR, be marked Done, and never merge. That is exactly what happened
to features/endpoint-agents — EPA-1 through EPA-4 sat ``status: Done`` for seven
weeks while main still raised ``NotImplementedError``, because every gate proved
the work was WRITTEN and none compared it to what was on main. "Done" and "on
main" were allowed to be different things.
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

# Outcome of a push/PR check. The orchestrator maps these to journal outcomes
# and to whether the row is flagged ``needs_push``:
#   - "ok"                : branch pushed AND (PR present OR not expected OR the
#                           PR check was inconclusive). Nothing to flag.
#   - "skipped-no-remote" : no such remote is configured — the check does not
#                           apply (a local-only repo). Skip, journal the reason.
#   - "not-pushed"        : the branch is absent on the remote, or the remote
#                           tip is behind the local tip (a stale/partial push).
#   - "no-pr"             : branch is pushed but no open PR exists, and a PR was
#                           expected and the PR check was conclusive.
#   - "error"             : a git read failed (network/auth/etc.) so the push
#                           state could not be determined. The orchestrator does
#                           NOT flag on this — an inability to check must not be
#                           reported as a confirmed unpushed branch.
_NEEDS_ATTENTION = ("not-pushed", "no-pr")


@dataclass
class PushVerifyResult:
    """The verdict of one push/PR check."""

    status: str
    detail: str = ""
    local_sha: str | None = None
    remote_sha: str | None = None
    # True iff `gh` was actually consulted and returned a parseable answer.
    # False when a PR was not expected, or the PR check was skipped/inconclusive
    # (gh missing, not authenticated, repo not on a forge). Lets the journal
    # distinguish "no PR" from "couldn't look for a PR".
    pr_checked: bool = False

    @property
    def needs_attention(self) -> bool:
        """True iff this verdict warrants a corrective push/PR re-spawn."""
        return self.status in _NEEDS_ATTENTION


def _run(cmd: list[str], *, cwd: Path) -> tuple[int, str, str]:
    """Run a command, returning (exit_code, stdout, stderr).

    A missing binary (e.g. ``gh`` not installed) is reported as exit code 127
    rather than raised, so callers handle "tool absent" uniformly with "tool
    errored" — both mean "could not determine", never "confirmed bad".

    ``GIT_TERMINAL_PROMPT=0`` makes an auth-requiring remote fail fast (the
    verification reads are read-only and unattended; a credential prompt would
    otherwise hang the worker thread until the timeout).
    """
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    try:
        p = subprocess.run(
            cmd, cwd=str(cwd), capture_output=True, text=True, timeout=120,
            env=env,
        )
    except FileNotFoundError as e:
        return 127, "", f"binary not found: {e}"
    except subprocess.TimeoutExpired:
        return 124, "", f"timed out: {' '.join(cmd)}"
    return p.returncode, p.stdout, p.stderr


def verify(
    *,
    repo_root: Path,
    branch: str,
    expect_pr: bool,
    remote: str = "origin",
    gh_bin: str = "gh",
    run: Callable[..., tuple[int, str, str]] = _run,
    log: Callable[[str], None] = lambda _m: None,
) -> PushVerifyResult:
    """Determine whether ``branch``'s local tip is pushed to ``remote`` and,
    when ``expect_pr`` is set, whether an open PR exists for it.

    ``repo_root`` is the directory the git/gh commands run in — the task's
    worktree is fine (git worktrees share the parent repo's remotes). ``run`` is
    injectable so the check is unit-testable without a real remote or ``gh``.
    """
    # 1. Is the remote even configured? A local-only repo can't be "unpushed".
    rc, out, _ = run(["git", "remote"], cwd=repo_root)
    remotes = {ln.strip() for ln in out.splitlines() if ln.strip()}
    if rc != 0 or remote not in remotes:
        return PushVerifyResult(
            status="skipped-no-remote",
            detail=f"no {remote!r} remote configured",
        )

    # 2. Local tip we expect to find on the remote.
    rc, out, err = run(["git", "rev-parse", "HEAD"], cwd=repo_root)
    if rc != 0:
        return PushVerifyResult(
            status="error", detail=f"git rev-parse HEAD failed: {err.strip()[-200:]}"
        )
    local_sha = out.strip()

    # 3. The remote's tip for this branch (empty stdout = branch absent).
    rc, out, err = run(["git", "ls-remote", "--heads", remote, branch], cwd=repo_root)
    if rc != 0:
        # Network/auth/etc. — we genuinely cannot tell. Do not claim unpushed.
        return PushVerifyResult(
            status="error",
            detail=f"git ls-remote {remote} {branch} failed: {err.strip()[-200:]}",
            local_sha=local_sha,
        )
    first = out.split() if out.strip() else []
    remote_sha = first[0].strip() if first else None
    if remote_sha is None:
        return PushVerifyResult(
            status="not-pushed",
            detail=f"branch {branch!r} absent on {remote}",
            local_sha=local_sha,
        )
    if remote_sha != local_sha:
        return PushVerifyResult(
            status="not-pushed",
            detail=(
                f"remote tip {remote_sha[:8]} behind local {local_sha[:8]} "
                f"(stale/partial push)"
            ),
            local_sha=local_sha,
            remote_sha=remote_sha,
        )

    # The branch is fully pushed. If no PR is expected, we're done.
    if not expect_pr:
        return PushVerifyResult(
            status="ok", detail="pushed; PR not expected",
            local_sha=local_sha, remote_sha=remote_sha,
        )

    # 4. Is there an open PR for this branch?
    pr_open = _pr_open(repo_root, branch, gh_bin, run, log)
    if pr_open is None:
        # gh missing / not authed / repo not on a forge — inconclusive. Treat as
        # ok so we never flag needs_push on the basis of a check we couldn't run.
        return PushVerifyResult(
            status="ok", detail="pushed; PR check inconclusive (gh unavailable)",
            local_sha=local_sha, remote_sha=remote_sha, pr_checked=False,
        )
    if pr_open:
        return PushVerifyResult(
            status="ok", detail="pushed; open PR found",
            local_sha=local_sha, remote_sha=remote_sha, pr_checked=True,
        )
    return PushVerifyResult(
        status="no-pr", detail="pushed but no open PR found",
        local_sha=local_sha, remote_sha=remote_sha, pr_checked=True,
    )


def _pr_open(
    repo_root: Path,
    branch: str,
    gh_bin: str,
    run: Callable[..., tuple[int, str, str]],
    log: Callable[[str], None],
) -> bool | None:
    """Return True/False if an open PR for ``branch`` definitely exists/doesn't,
    or None if the question is unanswerable (gh absent, unauthenticated, repo
    not on a forge, unparseable output). None is deliberately distinct from
    False so callers don't conflate "no PR" with "couldn't check".
    """
    rc, out, err = run(
        [gh_bin, "pr", "list", "--head", branch, "--state", "open", "--json", "url"],
        cwd=repo_root,
    )
    if rc != 0:
        log(f"  push-verify: PR check inconclusive (gh exit {rc}): {err.strip()[-150:]}")
        return None
    try:
        data = json.loads(out.strip() or "[]")
    except json.JSONDecodeError:
        log("  push-verify: PR check inconclusive (gh returned non-JSON)")
        return None
    if not isinstance(data, list):
        return None
    return len(data) > 0


# ── landed verification ──────────────────────────────────────────────────────
# Outcomes:
#   - "landed"        : the branch tip is an ancestor of the base. Definitive.
#   - "landed-via-pr" : the tip is not an ancestor but a MERGED pull request
#                       exists for the branch — a squash or rebase merge, whose
#                       result is a different sha carrying the same work.
#   - "unlanded"      : neither. Needs review; see the caveat below.
#   - "no-branch"     : no ref exists locally or on the remote, and nothing on
#                       the base claims the key either.
#   - "landed-by-message" : the ref is gone, but commits on the base carry the
#                       task key in the project's `[KEY]` form. WEAKER than
#                       `landed`: a message is a claim somebody wrote, not an
#                       ancestry proof, and the detail says so. It exists
#                       because `prune-branches` DELETES a branch once its work
#                       is on the base — so the tidier an operator is, the more
#                       false REVIEW rows this check produced. Measured
#                       2026-08-29 on dogfood-w2: 4 of 16 Done tasks flagged,
#                       every one of them landed-and-pruned.
#   - "skipped"       : no branch to check (never dispatched, or an
#                       auto-integrate run committing straight to the base).
#   - "error"         : a git read failed. NEVER treated as a problem — an
#                       inability to check is not evidence of absence.
#
# WHAT "unlanded" DOES AND DOES NOT MEAN. It means this BRANCH's tip is not on
# the base. It does not prove the work is missing: DISP-11 is `unlanded` by this
# check, its PR was closed unmerged, and `resume.py` is on main anyway because
# the work was landed by another route. So this is EVIDENCE FOR REVIEW, not a
# verdict, and it is deliberately not called a "false done" — a gate that
# announces false failures gets switched off, and then it catches nothing.
#
# Where it is decisive is the opposite case: EPA-1 through EPA-4 are `unlanded`,
# have no pull request at all, and main raises NotImplementedError for three of
# them. That is the shape worth surfacing.
_NEEDS_REVIEW = ("unlanded", "no-branch")


@dataclass
class LandedResult:
    """The verdict of one landed check."""

    status: str
    detail: str = ""
    branch: str | None = None
    base: str | None = None

    @property
    def needs_review(self) -> bool:
        """True iff this branch's work could not be found on the base."""
        return self.status in _NEEDS_REVIEW


def _commits_claiming_key(task_key: str, base_ref: str, *, cwd: Path, r) -> list[str]:
    """Commits on ``base_ref`` whose message carries ``[task_key]``.

    The BRACKETED form only. Bare mentions are noise — measured on this repo,
    `W2-1-1` appears in 16 commit messages and `[W2-1-1]` in 3, because
    operator commits discuss keys in prose all the time. Matching the loose
    form would report every task as landed the moment somebody wrote about it.
    """
    if not task_key:
        return []
    code, out, _ = r(
        ["git", "log", base_ref, "--format=%H", f"--grep=[{task_key}]",
         "--fixed-strings"],
        cwd,
    )
    if code != 0:
        return []
    return [ln.strip() for ln in out.splitlines() if ln.strip()]


def _merged_pr_exists(branch: str, *, cwd: Path, r) -> bool:
    """Did a pull request for ``branch`` merge?

    Consulted only when reachability already said no, because a squash or rebase
    merge lands the work under a sha the branch tip is not an ancestor of. A
    missing or unauthenticated ``gh`` returns False, which keeps the caller in
    "needs review" rather than inventing a merge.
    """
    code, out, _ = r(
        ["gh", "pr", "list", "--head", branch, "--state", "merged",
         "--json", "number", "--limit", "1"],
        cwd,
    )
    if code != 0 or not out.strip():
        return False
    try:
        return bool(json.loads(out))
    except (ValueError, TypeError):
        return False


def verify_landed(
    branch: str | None,
    *,
    cwd: Path,
    base: str = "main",
    task_key: str | None = None,
    run: Callable[[list[str], Path], tuple[int, str, str]] | None = None,
) -> LandedResult:
    """Is ``branch``'s work on ``base``?

    The one check that asks a question of the BASE. Everything else the
    dispatcher verifies happens on the branch, which is how a task can be Done,
    gated, verified and reviewed while its work sits unmerged.

    Resolution order matters. The LOCAL branch is preferred over the remote,
    because a run that merged locally and has not pushed the base yet is landed
    and must not be reported otherwise.
    """
    r = run or (lambda cmd, wd: _run(cmd, cwd=wd))

    if not branch:
        return LandedResult("skipped", "task has no branch")

    tip = None
    for ref in (branch, f"refs/remotes/origin/{branch}"):
        code, out, _ = r(["git", "rev-parse", "--verify", "--quiet", ref], cwd)
        if code == 0 and out.strip():
            tip = out.strip()
            break
    if tip is None:
        # The branch is gone. Before calling this a problem, ask the base
        # whether anything there claims the key — `prune-branches` exists to
        # delete branches whose work has landed, so a missing ref is the
        # EXPECTED end state of a tidy repo, not evidence of loss.
        base_for_grep = None
        for ref in (base, f"refs/remotes/origin/{base}"):
            code, out, _ = r(["git", "rev-parse", "--verify", "--quiet", ref], cwd)
            if code == 0 and out.strip():
                base_for_grep = ref
                break
        claims = (
            _commits_claiming_key(task_key or "", base_for_grep, cwd=cwd, r=r)
            if base_for_grep else []
        )
        if claims:
            return LandedResult(
                "landed-by-message",
                f"no ref for {branch!r}, but {len(claims)} commit(s) on {base} "
                f"carry [{task_key}], first {claims[0][:9]} — a message is "
                "corroboration, not ancestry",
                branch, base,
            )
        return LandedResult(
            "no-branch", f"no local or remote ref for {branch!r}", branch, base
        )

    base_ref = None
    for ref in (base, f"refs/remotes/origin/{base}"):
        code, out, _ = r(["git", "rev-parse", "--verify", "--quiet", ref], cwd)
        if code == 0 and out.strip():
            base_ref = ref
            break
    if base_ref is None:
        return LandedResult("error", f"base {base!r} not found", branch, base)

    code, _, err = r(["git", "merge-base", "--is-ancestor", tip, base_ref], cwd)
    if code == 0:
        return LandedResult("landed", f"{tip[:9]} is on {base}", branch, base)
    if code != 1:
        return LandedResult("error", err.strip()[:200] or "git read failed", branch, base)

    # Not an ancestor. A squash or rebase merge looks exactly like this, so ask
    # the forge before concluding anything.
    if _merged_pr_exists(branch, cwd=cwd, r=r):
        return LandedResult(
            "landed-via-pr", "merged by pull request (squash or rebase)", branch, base
        )
    return LandedResult(
        "unlanded", f"{tip[:9]} is not on {base} and no merged PR", branch, base
    )


# Statuses that CLAIM the work is finished. "Awaiting Review" is here because a
# stalled approval ladder is indistinguishable from a finished task otherwise:
# the row reads like progress and the work sits in an open PR indefinitely.
#
# That is not hypothetical. The ladder self-approves a low-risk PR, but an
# ELEVATED one needs an external GitHub approval — and in a single-maintainer
# repository GitHub forbids approving your own pull request, so the condition can
# never be met. A ladder that cannot be satisfied is a deadlock, not a gate, and
# the least this can do is make the deadlock visible instead of leaving a row
# that looks like it is still moving.
_CLAIMS_FINISHED = ("done", "awaiting review", "merged")


def audit_done_tasks(
    tasks: list[dict],
    *,
    cwd: Path,
    base: str = "main",
    run: Callable[[list[str], Path], tuple[int, str, str]] | None = None,
) -> list[tuple[str, LandedResult]]:
    """Check every task that CLAIMS to be finished against ``base``.

    Returns one row per such task, the ones needing review first, so a caller
    printing only the head of the list still prints the problems. Tasks in any
    other status are not checked: an unfinished task is not claiming to have
    landed.
    """
    rows: list[tuple[str, LandedResult]] = []
    for t in tasks:
        if str(t.get("status", "")).strip().lower() not in _CLAIMS_FINISHED:
            continue
        key = str(t.get("key", "?"))
        rows.append((key, verify_landed(
            t.get("branch"), cwd=cwd, base=base, run=run, task_key=key)))
    rows.sort(key=lambda kv: (not kv[1].needs_review, kv[0]))
    return rows


# ── pruning landed branches ──────────────────────────────────────────────────
# 126 feature branches, 111 of them already merged into main, is not clutter —
# it is wrong input. The dispatcher finds a task's branch by DERIVED name and
# merges dependency branches into each worktree, so every landed-but-undeleted
# branch is a future conflict waiting for whichever task depends on it. GO-1
# failed exactly that way: GO-0 had landed by squash-merge weeks earlier, its
# branch was still present, and the dependency merge conflicted against it.
#
# So a landed branch is deleted, and only a landed one. `verify_landed` already
# knows the difference, including the squash-merge case that reachability alone
# gets wrong.


def landed_branches(
    *,
    cwd: Path,
    base: str = "main",
    pattern: str = "feat/",
    run: Callable[[list[str], Path], tuple[int, str, str]] | None = None,
) -> tuple[list[tuple[str, LandedResult]], list[tuple[str, LandedResult]]]:
    """Split local branches into (landed, not-landed).

    Only the first list is safe to delete. The second is the review queue: work
    that is not on the base and has no merged PR, which may be unfinished, may
    have landed by another route, or may be the next EPA.
    """
    r = run or (lambda cmd, wd: _run(cmd, cwd=wd))
    code, out, _ = r(["git", "for-each-ref", "--format=%(refname:short)",
                      "refs/heads/"], cwd)
    if code != 0:
        return [], []

    landed: list[tuple[str, LandedResult]] = []
    held: list[tuple[str, LandedResult]] = []
    for name in (b.strip() for b in out.splitlines()):
        if not name or not name.startswith(pattern) or name == base:
            continue
        res = verify_landed(name, cwd=cwd, base=base, run=r)
        (landed if res.status in ("landed", "landed-via-pr") else held).append(
            (name, res)
        )
    return landed, held
