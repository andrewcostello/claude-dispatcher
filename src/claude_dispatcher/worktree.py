"""Git worktree creation and lifecycle.

Container vs host path conventions:
  /workspace as repo root → worktrees under /worktrees (tmpfs-mounted in
                            container; ephemeral; cleaned on container exit)
  anything else           → worktrees under ../worktree-<task-key> (sibling
                            of the repo, conventional dev-host layout)

The dispatcher creates the worktree before spawning Claude. On Done it can
remove it; on Blocked/Escalated it preserves it for inspection.

Branch naming follows the .claude/workflow/skills/git-worktree-setup.md convention:
  Fix       → fix/SMG-XXXX-...
  Feature   → feat/SMG-XXXX-...
  Refactor  → refactor/SMG-XXXX-...
  Docs      → docs/SMG-XXXX-...
  Chore     → chore/SMG-XXXX-...
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable


class WorktreeError(RuntimeError):
    """A `git worktree` operation failed.

    Carries the git stderr (if any) so the dispatcher can log a useful reason
    instead of a raw CalledProcessError traceback. Raised by `create`/`remove`
    when git exits non-zero and the situation is not a benign idempotent reuse.
    """

    def __init__(self, message: str, *, stderr: str = "") -> None:
        super().__init__(message)
        self.stderr = stderr


class WorktreeLayout(Enum):
    """Where per-task worktree directories live, relative to the base path.

    CONTAINER: the base is the dedicated `/worktrees` mount, so each task gets
               a flat `<base>/<task-key>` (the mount is ours alone).
    SIBLING:   the base is the repo's parent dir on a dev host, shared with the
               repo and siblings, so each task is namespaced as
               `<base>/worktree-<task-key>`.
    """

    CONTAINER = "container"
    SIBLING = "sibling"


BRANCH_PREFIX_BY_TYPE = {
    "fix": "fix",
    "bug": "fix",
    "feature": "feat",
    "feat": "feat",
    "refactor": "refactor",
    "docs": "docs",
    "chore": "chore",
    "task": "feat",  # default for generic "Task" type
}


@dataclass
class Worktree:
    path: Path
    branch: str


def detect_repo_root(start: Path | None = None) -> Path:
    """Return the git repo root containing `start` (or cwd)."""
    cmd = ["git", "rev-parse", "--show-toplevel"]
    cwd = str(start) if start else None
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd, check=True)
    return Path(result.stdout.strip())


def is_container_env(repo_root: Path) -> bool:
    """True iff the repo root is /workspace (the container convention)."""
    return str(repo_root) == "/workspace"


def worktree_base(repo_root: Path, override: str | None = None) -> Path:
    """Default worktree base path: /worktrees in container, repo_root.parent on host."""
    if override:
        return Path(override)
    if is_container_env(repo_root):
        return Path("/worktrees")
    return repo_root.parent


def branch_name(task_type: str, task_key: str, summary: str) -> str:
    """Build a branch name from task type, ticket key, and summary.

    Type is matched case-insensitively against BRANCH_PREFIX_BY_TYPE; unknown
    types fall back to `feat`. Summary is slugified to <= 5 kebab-cased words.
    """
    prefix = BRANCH_PREFIX_BY_TYPE.get(task_type.lower(), "feat")
    slug = _slugify(summary)
    return f"{prefix}/{task_key}-{slug}" if slug else f"{prefix}/{task_key}"


def _slugify(summary: str) -> str:
    """Lowercase, kebab-case, max 5 words, drop punctuation."""
    text = re.sub(r"[^a-zA-Z0-9 ]+", " ", summary.lower())
    words = [w for w in text.split() if w]
    return "-".join(words[:5])


def layout_for(base: Path) -> WorktreeLayout:
    """Classify the worktree layout from the base path.

    The container convention mounts a dedicated directory named `worktrees`;
    everything else is the sibling-of-repo dev-host layout. Decided on the
    path's final component (`base.name`), not a string prefix, so paths like
    `/worktrees-scratch` or `/var/run/worktrees-old` are not misclassified.
    """
    return WorktreeLayout.CONTAINER if base.name == "worktrees" else WorktreeLayout.SIBLING


def worktree_path(base: Path, task_key: str) -> Path:
    """Resolve the per-task worktree directory under `base` for its layout."""
    if layout_for(base) is WorktreeLayout.CONTAINER:
        return base / task_key
    return base / f"worktree-{task_key}"


def _checked_out_branch(wt_path: Path, fallback: str) -> str:
    """Branch currently checked out at `wt_path`, or `fallback` if undetermined.

    On idempotent reuse the directory may already be on a *different* branch
    than the one requested (e.g. a same-key/different-branch race). Returning
    the real branch keeps the handle honest for downstream SHA/diff tracking;
    a detached HEAD or any git error falls back to the requested branch.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=wt_path,
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, OSError):
        return fallback
    branch = result.stdout.strip()
    return branch if branch and branch != "HEAD" else fallback


def create(
    repo_root: Path,
    task_key: str,
    branch: str,
    base_branch: str = "main",
    base_path: Path | None = None,
) -> Worktree:
    """Create a worktree off `base_branch` at the configured base path.

    Idempotent: if the worktree directory already exists, returns its handle
    without re-creating. (The dispatcher uses this on resume.)
    """
    base = base_path or worktree_base(repo_root)
    wt_path = worktree_path(base, task_key)
    if wt_path.exists() and (wt_path / ".git").exists():
        return Worktree(path=wt_path, branch=_checked_out_branch(wt_path, branch))
    base.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(
            ["git", "worktree", "add", str(wt_path), "-b", branch, base_branch],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        # Concurrent same-key race: another worker won this path (or branch)
        # between our existence check above and `git worktree add`. If the dir
        # is now a valid worktree, reuse it idempotently; otherwise surface a
        # typed error carrying git's stderr rather than a raw traceback.
        if wt_path.exists() and (wt_path / ".git").exists():
            return Worktree(path=wt_path, branch=_checked_out_branch(wt_path, branch))
        raise WorktreeError(
            f"git worktree add failed for {task_key} at {wt_path}",
            stderr=(exc.stderr or "").strip(),
        ) from exc
    return Worktree(path=wt_path, branch=branch)


def remove(repo_root: Path, wt: Worktree, force: bool = False) -> None:
    """Remove a worktree. Use force=True only after a successful run.

    On Blocked/Escalated, preserve the worktree for inspection — do not call
    this. The dispatcher only removes worktrees on Status: Done.
    """
    args = ["git", "worktree", "remove", str(wt.path)]
    if force:
        args.append("--force")
    try:
        subprocess.run(args, cwd=repo_root, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        raise WorktreeError(
            f"git worktree remove failed for {wt.path}",
            stderr=(exc.stderr or "").strip(),
        ) from exc


# --- dispatch-time dependency merge (INT-4) --------------------------------
#
# When a dependent task's worktree is created, its branch is forked from
# base_branch. If a blockedBy dependency has NOT been integrated into base
# (e.g. auto-integrate is off, or the dependency landed only on its own feat
# branch), the fresh worktree can't see that dependency's work. Run #2's
# DISP-9/10/11/12 natural experiment showed Taskers handle this inconsistently
# (merge / narrow scope / fork / read-via-object-store). This provides the
# merge mechanically: bring each unintegrated dependency branch into the new
# task branch before the Tasker is spawned.

# Failure labels for a dependency merge that did not complete. A genuine
# content conflict (unmerged paths present after the failed merge) is labelled
# distinctly from every other merge failure (e.g. committer identity unknown,
# unrelated histories) so triage isn't misled into hunting for conflicting
# edits that don't exist.
DEPENDENCY_MERGE_CONFLICT = "dependency_merge_conflict"
DEPENDENCY_MERGE_FAILURE = "dependency_merge_failure"


@dataclass
class MergedDependency:
    """One blockedBy dependency whose branch was merged into the task branch.

    ``sha`` is the full commit SHA of the dependency branch tip at merge time
    — journaled so an auditor can reconstruct exactly which dependency commits
    the dependent task was built on top of.
    """

    key: str
    branch: str
    sha: str


@dataclass
class DependencyMergeConflict:
    """A blockedBy dependency branch that could not be merged cleanly.

    ``key`` / ``branch`` identify the dependency whose merge failed; ``reason``
    classifies the failure — ``dependency_merge_conflict`` for a genuine
    content conflict (unmerged paths present), ``dependency_merge_failure``
    for every other merge failure (e.g. committer identity unknown).
    ``detail`` carries the conflicting-file list for a conflict, else git's
    stderr/stdout, for the Blocked reason and journal payload. The failed
    merge is aborted before this is returned, so the worktree is left without
    an in-progress merge.
    """

    key: str
    branch: str
    detail: str
    reason: str = DEPENDENCY_MERGE_CONFLICT


@dataclass
class DependencyMergeResult:
    """Outcome of merging a dependent task's blockedBy branches.

    ``merged`` lists the dependencies actually merged (in blockedBy order);
    ``already_on_base`` lists dependency keys whose commits were already
    reachable from base (no merge needed — the no-op case); ``unresolved``
    lists dependency keys whose branch ref could not be found. ``conflict``
    is set iff a merge failed — its ``reason`` distinguishes a genuine
    content conflict (``dependency_merge_conflict``) from any other merge
    failure (``dependency_merge_failure``) — in which case merging stopped at
    that dependency and the caller must NOT dispatch a Tasker into the tree.
    """

    merged: list[MergedDependency] = field(default_factory=list)
    already_on_base: list[str] = field(default_factory=list)
    unresolved: list[str] = field(default_factory=list)
    conflict: DependencyMergeConflict | None = None


def _rev_parse(repo_root: Path, ref: str) -> str | None:
    """Full commit SHA for ``ref`` in ``repo_root``, or None if it can't resolve."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"],
            cwd=repo_root, capture_output=True, text=True, check=False,
        )
    except OSError:
        return None
    sha = (result.stdout or "").strip()
    return sha if (result.returncode == 0 and sha) else None


def _is_ancestor(repo_root: Path, commitish: str, ref: str) -> bool:
    """True iff ``commitish`` is an ancestor of (reachable from) ``ref``."""
    try:
        result = subprocess.run(
            ["git", "merge-base", "--is-ancestor", commitish, ref],
            cwd=repo_root, capture_output=True, text=True, check=False,
        )
    except OSError:
        return False
    return result.returncode == 0


def _merge_branch(wt_path: Path, dep_branch: str) -> tuple[bool, str, str]:
    """``git merge --no-ff --no-edit dep_branch`` in ``wt_path``.

    Returns ``(ok, reason, detail)``. ``(True, "", "")`` on a clean merge.
    Any failure is aborted — leaving the worktree without an in-progress
    merge — and classified by ``reason``: a non-empty unmerged-paths list
    means a genuine content conflict (``dependency_merge_conflict``, detail =
    conflicting-file list); an empty one means the merge failed for some
    other reason, e.g. committer identity unknown
    (``dependency_merge_failure``, detail = git's stderr/stdout).
    """
    proc = subprocess.run(
        ["git", "merge", "--no-ff", "--no-edit", dep_branch],
        cwd=wt_path, capture_output=True, text=True, check=False,
    )
    if proc.returncode == 0:
        return True, "", ""
    # Unmerged paths are the conflict discriminator: present after a genuine
    # content conflict, empty for every other failure mode (which never gets
    # as far as leaving conflicted index entries).
    conflicts = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=U"],
        cwd=wt_path, capture_output=True, text=True, check=False,
    ).stdout.strip()
    # Abort so the worktree is never left mid-merge — a Tasker must never be
    # dispatched into a conflicted tree, and a preserved-for-inspection
    # Blocked worktree should be in a clean state.
    subprocess.run(["git", "merge", "--abort"],
                   cwd=wt_path, capture_output=True, text=True, check=False)
    if conflicts:
        detail = "conflicting files: " + ", ".join(conflicts.splitlines()[:5])
        return False, DEPENDENCY_MERGE_CONFLICT, detail
    detail = ((proc.stderr or proc.stdout) or "merge failed").strip()[:300]
    return False, DEPENDENCY_MERGE_FAILURE, detail


def merge_dependencies(
    repo_root: Path,
    wt: Worktree,
    base_branch: str,
    dependencies: list[tuple[str, str]],
    log: Callable[[str], None] | None = None,
) -> DependencyMergeResult:
    """Merge each blockedBy dependency branch into the task's worktree branch.

    For every ``(key, branch)`` in ``dependencies`` (blockedBy order):
      - resolve the branch tip; an unresolvable ref is recorded in
        ``unresolved`` and skipped (we can't merge what we can't find);
      - if the tip is already reachable from ``base_branch``, skip it — the
        dependency's work is already on base, so the worktree branch (forked
        from base) already contains it. This is the no-op case;
      - otherwise ``git merge --no-ff`` the branch into the worktree. On any
        merge failure — a genuine content conflict or a non-conflict failure
        such as a missing committer identity — the merge is aborted (leaving
        the tree clean) and merging stops: the failure is returned with its
        classifying reason so the caller can Block the task rather than
        dispatch a Tasker into a half-merged tree.

    Merges run in the worktree (``wt.path``) so they land on the checked-out
    task branch. This function never touches ``base_branch``. An empty
    ``dependencies`` list is a no-op returning an empty result.
    """
    result = DependencyMergeResult()
    emit = log or (lambda _m: None)
    for key, dep_branch in dependencies:
        tip = _rev_parse(repo_root, dep_branch)
        if tip is None:
            emit(f"  {key} dependency branch {dep_branch!r} unresolved — skipping merge")
            result.unresolved.append(key)
            continue
        if _is_ancestor(repo_root, tip, base_branch):
            result.already_on_base.append(key)
            continue
        emit(f"  {key} merging dependency branch {dep_branch} ({tip[:8]}) into {wt.branch}")
        ok, reason, detail = _merge_branch(wt.path, dep_branch)
        if not ok:
            kind = ("conflict" if reason == DEPENDENCY_MERGE_CONFLICT
                    else "failure")
            emit(f"  {key} dependency merge {kind} from {dep_branch}: {detail}")
            result.conflict = DependencyMergeConflict(
                key=key, branch=dep_branch, detail=detail, reason=reason,
            )
            return result
        result.merged.append(MergedDependency(key=key, branch=dep_branch, sha=tip))
    return result
