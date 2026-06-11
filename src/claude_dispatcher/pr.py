"""Raise a GitHub PR from prepared metadata via the `gh` CLI.

The dispatcher invokes this when the human approves a Tasker-prepared PR in
supervised mode. The Tasker writes the title, branch, and body into the
summary file; the dispatcher reads them and runs `gh pr create` from the
task's worktree directory.

The Tasker never invokes gh directly in the gated path — it stops short and
hands the metadata to the dispatcher. This centralizes the actual external
side effect (the PR creation) in the dispatcher, which is the place that
owns the audit log and the YAML write-back.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class PRResult:
    url: str | None
    error: str | None
    # The PR number, parsed from the trailing path segment of the URL (e.g.
    # ``.../pull/42`` → 42). None when the URL has no numeric trailing segment
    # or no URL was returned. The PR-flow lifecycle (PRF-2) stamps this on the
    # YAML row and into the ``pr_opened`` journal event.
    number: int | None = None


def _pr_number_from_url(url: str) -> int | None:
    """Extract the PR number from a ``gh`` PR URL's trailing path segment.

    ``https://github.com/o/r/pull/42`` → 42. Returns None when the last
    segment is not a plain integer (so a non-GitHub or unexpected URL shape
    simply yields no number rather than a wrong one)."""
    tail = url.rstrip("/").rsplit("/", 1)[-1]
    return int(tail) if tail.isdigit() else None


def raise_pr(
    *,
    cwd: Path,
    title: str,
    body: str,
    branch: str,
    base: str = "main",
    gh_bin: str = "gh",
) -> PRResult:
    """Run `gh pr create` from the worktree. Returns the URL on success.

    `gh` reads the body from stdin when --body-file - is used. We never
    write the body to disk — keeps the side effect contained.
    """
    cmd = [
        gh_bin, "pr", "create",
        "--title", title,
        "--body-file", "-",
        "--base", base,
        "--head", branch,
    ]
    try:
        proc = subprocess.run(
            cmd,
            input=body,
            capture_output=True,
            text=True,
            cwd=str(cwd),
            check=False,
            timeout=120,
        )
    except FileNotFoundError:
        return PRResult(url=None, error=f"gh binary not found: {gh_bin}")
    except subprocess.TimeoutExpired:
        return PRResult(url=None, error="gh pr create timed out after 120s")

    if proc.returncode != 0:
        err = proc.stderr.strip() or proc.stdout.strip() or "unknown gh error"
        return PRResult(url=None, error=err)

    # gh prints the URL as the last non-empty line of stdout
    url = ""
    for line in reversed(proc.stdout.splitlines()):
        line = line.strip()
        if line.startswith("http"):
            url = line
            break
    if not url:
        return PRResult(url=None, error="gh returned no URL on stdout")
    return PRResult(url=url, error=None, number=_pr_number_from_url(url))


# --- PRF-4: review state + merge --------------------------------------------
#
# The mechanical merge engine (merge_engine.py) reads a PR's external review
# state and merges it. Both gh side effects live here next to `gh pr create`,
# so the merge engine never shells out directly — it stays pure orchestration
# over these three small, separately-tested adapters.


@dataclass
class ReviewState:
    """The external GitHub review state of a PR (``gh pr view --json reviews``).

    ``approved`` is True iff at least one reviewer's *latest* review is
    ``APPROVED`` and no reviewer's latest review is ``CHANGES_REQUESTED`` — the
    standard "currently approved, nothing outstanding" reading. ``latest`` maps
    each reviewer login to their most recent review state (for the journal).
    ``approver`` is one approving reviewer's login (for the audit trail), or
    None. ``error`` is set when the state could not be read — the caller fails
    closed (treats it as not-approved) so a read failure never auto-merges.
    """

    approved: bool = False
    latest: dict[str, str] = field(default_factory=dict)
    approver: str | None = None
    error: str | None = None


def pr_review_state(
    *,
    cwd: Path,
    number: int,
    gh_bin: str = "gh",
) -> ReviewState:
    """Read PR ``number``'s review state via ``gh pr view <n> --json reviews``.

    Resolves each reviewer's *latest* review (reviews arrive in chronological
    order, so the last entry per author wins) and applies the standard reading:
    approved iff some author's latest state is APPROVED and none is
    CHANGES_REQUESTED. Any failure (gh missing, non-zero exit, unparseable
    JSON) yields ``approved=False`` with ``error`` set — the merge engine fails
    closed, never auto-merging on an unreadable review state.
    """
    cmd = [gh_bin, "pr", "view", str(number), "--json", "reviews"]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, cwd=str(cwd),
            check=False, timeout=60,
        )
    except FileNotFoundError:
        return ReviewState(error=f"gh binary not found: {gh_bin}")
    except subprocess.TimeoutExpired:
        return ReviewState(error="gh pr view timed out after 60s")

    if proc.returncode != 0:
        err = proc.stderr.strip() or proc.stdout.strip() or "unknown gh error"
        return ReviewState(error=err)

    try:
        doc = json.loads(proc.stdout or "{}")
        reviews = doc.get("reviews") or []
    except (json.JSONDecodeError, AttributeError) as e:
        return ReviewState(error=f"could not parse gh review JSON: {e}")

    latest: dict[str, str] = {}
    for r in reviews:
        if not isinstance(r, dict):
            continue
        # An author-less review (e.g. a deleted account) is keyed by "" — still
        # counted, never dropped, so an approval can't silently vanish.
        login = ((r.get("author") or {}).get("login") or "") if isinstance(
            r.get("author"), dict) else ""
        state = str(r.get("state") or "").upper()
        if state:
            latest[login] = state  # later entries overwrite → latest wins

    states = set(latest.values())
    approved = "APPROVED" in states and "CHANGES_REQUESTED" not in states
    approver = None
    if approved:
        approver = next(
            (login for login, st in latest.items() if st == "APPROVED"), None,
        )
    return ReviewState(approved=approved, latest=latest, approver=approver)


@dataclass
class MergeResult:
    """Outcome of ``gh pr merge``.

    ``merged`` True → the PR landed. On failure ``merged`` is False and
    ``conflict`` distinguishes an unmergeable/conflicting PR (the supervising
    agent must rebase — a deliberate non-goal of this phase to auto-fix) from
    any other gh error (``error`` carries the detail either way).
    """

    merged: bool
    conflict: bool = False
    error: str | None = None


# Substrings in gh's stderr that signal the PR cannot be merged as-is and needs
# a rebase — as opposed to a transient/auth/usage error. Matched
# case-insensitively. Deliberately specific to *mergeability* failures: a bare
# "failed to merge" is NOT here because gh prints it for permission /
# branch-protection / failing-check failures too, none of which a rebase fixes.
# Misclassifying those as conflicts would wrongly flag needs_rebase; the
# detail field always carries gh's exact message for the human regardless.
_CONFLICT_MARKERS = (
    "not mergeable",
    "not in a mergeable state",
    "merge conflict",
    "conflict",
    "is dirty",
)


def merge_pr(
    *,
    cwd: Path,
    number: int,
    gh_bin: str = "gh",
    method: str = "merge",
) -> MergeResult:
    """Merge PR ``number`` via ``gh pr merge <n> --<method>`` from ``cwd``.

    ``method`` is the merge strategy flag without the leading dashes
    (``merge`` → ``--merge``, the PRF-4 default; ``squash``/``rebase`` also
    valid). A non-zero exit whose stderr matches a conflict marker returns
    ``conflict=True`` so the caller flags ``needs_rebase`` rather than retrying;
    any other failure returns ``conflict=False`` with the error.
    """
    cmd = [gh_bin, "pr", "merge", str(number), f"--{method}"]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, cwd=str(cwd),
            check=False, timeout=120,
        )
    except FileNotFoundError:
        return MergeResult(merged=False, error=f"gh binary not found: {gh_bin}")
    except subprocess.TimeoutExpired:
        return MergeResult(merged=False, error="gh pr merge timed out after 120s")

    if proc.returncode == 0:
        return MergeResult(merged=True)

    detail = (proc.stderr.strip() or proc.stdout.strip()
              or f"gh pr merge exit {proc.returncode}")
    low = detail.lower()
    is_conflict = any(m in low for m in _CONFLICT_MARKERS)
    return MergeResult(merged=False, conflict=is_conflict, error=detail[:300])
