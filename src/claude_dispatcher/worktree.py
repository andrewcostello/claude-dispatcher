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
from pathlib import Path


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
    wt_path = base / f"worktree-{task_key}" if not str(base).startswith("/worktrees") \
        else base / task_key
    if wt_path.exists() and (wt_path / ".git").exists():
        return Worktree(path=wt_path, branch=branch)
    base.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "worktree", "add", str(wt_path), "-b", branch, base_branch],
        cwd=repo_root,
        check=True,
        capture_output=True,
    )
    return Worktree(path=wt_path, branch=branch)


def remove(repo_root: Path, wt: Worktree, force: bool = False) -> None:
    """Remove a worktree. Use force=True only after a successful run.

    On Blocked/Escalated, preserve the worktree for inspection — do not call
    this. The dispatcher only removes worktrees on Status: Done.
    """
    args = ["git", "worktree", "remove", str(wt.path)]
    if force:
        args.append("--force")
    subprocess.run(args, cwd=repo_root, check=True, capture_output=True)
