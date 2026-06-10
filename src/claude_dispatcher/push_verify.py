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
