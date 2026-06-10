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
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


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
