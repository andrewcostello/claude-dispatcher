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
import shutil
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

    def __str__(self) -> str:
        # The reason reaches the operator as `str(e)` — through the run log and
        # through `blocked_reason` in tasks.yaml. Without git's stderr it names
        # the worktree path and not the cause, which is the same for a missing
        # base ref, an occupied directory and a locked worktree.
        message = super().__str__()
        return f"{message}: {self.stderr}" if self.stderr else message


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


def branch_name(
    task_type: str, task_key: str, summary: str, jira_key: str | None = None,
) -> str:
    """Build a branch name from task type, ticket key, and summary.

    Type is matched case-insensitively against BRANCH_PREFIX_BY_TYPE; unknown
    types fall back to `feat`. Summary is slugified to <= 5 kebab-cased words.

    ``jira_key`` LEADS when the row carries one that differs from its task key,
    giving ``feat/SMG-1234-WAL-LEDGER-3-...`` — the shape this docstring always
    described, for repos whose task keys are their own rather than the
    tracker's. Some CI gates require the branch to name the ticket
    (evenplay-mono's does), and 26 of 26 dispatched PRs failed that check.

    The task key is KEPT, not replaced: `dispatcher audit`'s landed-by-message
    route greps for the bracketed key, and dependency merges regenerate branch
    names through this same function, so both must stay derivable. Omitted when
    it would duplicate the task key.
    """
    prefix = BRANCH_PREFIX_BY_TYPE.get(task_type.lower(), "feat")
    slug = _slugify(summary)
    stem = task_key
    if jira_key and jira_key.strip() and jira_key.strip() != task_key:
        stem = f"{jira_key.strip()}-{task_key}"
    return f"{prefix}/{stem}-{slug}" if slug else f"{prefix}/{stem}"


def _slugify(summary: str) -> str:
    """Lowercase, kebab-case, max 5 words, drop punctuation."""
    text = re.sub(r"[^a-zA-Z0-9 ]+", " ", summary.lower())
    words = [w for w in text.split() if w]
    return "-".join(words[:5])


def sanitize_branch_segment(text: str) -> str:
    """Sanitize an arbitrary string into a single git-branch-safe segment.

    Lowercases, replaces every run of characters outside ``[a-z0-9._-]`` with a
    single ``-``, then strips leading/trailing separators. Unlike
    :func:`_slugify` this keeps the full text (no 5-word cap) and preserves
    ``.``/``_`` — it's for deriving a stable feature-branch name from an epic
    key like ``PHASE-3-PRF`` → ``phase-3-prf``. Returns ``""`` when nothing
    branch-safe survives (caller decides how to handle that).
    """
    cleaned = re.sub(r"[^a-z0-9._-]+", "-", text.strip().lower())
    return cleaned.strip("-._/")


def default_feature_branch(epic: str | None) -> str | None:
    """The default run-level feature branch for an epic: ``feature/<epic>``.

    The epic is sanitized into a branch-safe segment (see
    :func:`sanitize_branch_segment`). Returns None when ``epic`` is absent or
    sanitizes to nothing — the caller then knows it must require an explicit
    ``--feature-branch`` instead of inventing a name.
    """
    if not epic:
        return None
    seg = sanitize_branch_segment(str(epic))
    return f"feature/{seg}" if seg else None


@dataclass
class FeatureBranchResult:
    """Outcome of :func:`ensure_feature_branch`.

    ``status`` is ``"created"`` when the branch was freshly forked from the
    base branch this call, or ``"existing"`` when it was already present (and
    left untouched). ``sha`` is the branch tip's full commit SHA either way —
    recorded in the genesis so an auditor can pin the exact fork point.
    """

    branch: str
    sha: str
    status: str  # "created" | "existing"


def ensure_feature_branch(
    repo_root: Path, feature_branch: str, base_branch: str,
) -> FeatureBranchResult:
    """Ensure the run-level feature branch exists, creating it from base if not.

    PR-flow mode (PRF-1) runs all task worktrees off a shared feature branch.
    At run start the dispatcher calls this once: if ``feature_branch`` already
    resolves it is reused as-is (``status="existing"``); otherwise it is forked
    from ``base_branch`` via ``git branch`` (``status="created"``). This never
    checks out or modifies the branch's content — it only ensures the ref
    exists and reports its tip SHA. Idempotent: a second call on an existing
    branch is a no-op returning ``status="existing"``.

    Raises :class:`WorktreeError` if ``base_branch`` does not resolve (cannot
    fork from a non-existent ref) or ``git branch`` fails.
    """
    existing = _rev_parse(repo_root, feature_branch)
    if existing is not None:
        return FeatureBranchResult(branch=feature_branch, sha=existing, status="existing")
    base_sha = _rev_parse(repo_root, base_branch)
    if base_sha is None:
        raise WorktreeError(
            f"cannot create feature branch {feature_branch!r}: "
            f"base branch {base_branch!r} does not resolve"
        )
    try:
        subprocess.run(
            ["git", "branch", feature_branch, base_branch],
            cwd=repo_root, check=True, capture_output=True, text=True,
        )
    except subprocess.CalledProcessError as exc:
        raise WorktreeError(
            f"git branch failed creating {feature_branch!r} from {base_branch!r}",
            stderr=(exc.stderr or "").strip(),
        ) from exc
    sha = _rev_parse(repo_root, feature_branch) or base_sha
    return FeatureBranchResult(branch=feature_branch, sha=sha, status="created")


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


def commits_behind(repo_root: Path, branch: str, base_branch: str) -> int | None:
    """How many commits on ``base_branch`` are not on ``branch``.

    None when either ref does not resolve. Used to explain a dependency-merge
    conflict: `create` deliberately REUSES an existing branch rather than
    resetting it to the base (that is what has recovered real work four times),
    so a task re-dispatched months later merges its dependencies into a tree
    that predates them, and the conflict names files neither side deliberately
    touched.
    """
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo_root), "rev-list", "--count",
             f"{branch}..{base_branch}"],
            capture_output=True, text=True, check=False, timeout=30,
        )
        if proc.returncode != 0:
            return None
        return int(proc.stdout.strip())
    except (ValueError, OSError, subprocess.SubprocessError):
        return None


def owning_repo(wt_path: Path) -> Path | None:
    """The repository a worktree directory belongs to, or None.

    A linked worktree's ``.git`` is a FILE reading
    ``gitdir: <repo>/.git/worktrees/<name>``, so the owner is recoverable
    without asking git anything.
    """
    dot_git = wt_path / ".git"
    try:
        if not dot_git.is_file():
            return None
        text = dot_git.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    # `partition`, not `startswith`: this module carries an acceptance row
    # forbidding string-prefix checks (Phase 0), and a blunt rule is worth more
    # than an exception for a case that happens not to be a path.
    head, sep, gitdir = text.partition("gitdir:")
    if not sep or head.strip():
        return None
    gitdir = gitdir.strip()
    marker = "/.git/worktrees/"
    if marker not in gitdir:
        return None
    return Path(gitdir.split(marker, 1)[0])


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

    # A worktree path is `<repo_root.parent>/worktree-<KEY>` on a host, so TWO
    # REPOSITORIES THAT SHARE A PARENT DIRECTORY COLLIDE on it — and every repo
    # in ~/Project does. Measured 2026-08-30: a killed run against
    # claude-dispatcher left `worktree-GO-4-1` behind, and the next run, against
    # claude-workflow, reused it. The task then looked for its branch in a
    # checkout of the wrong repository and escalated ("the dispatcher reused
    # the stale claude-dispatcher worktree ... worktree creation should refuse,
    # not reuse, a path that belongs to another repository"). It is right: the
    # reuse path below exists to preserve THIS repo's work, and a directory
    # owned by another repo holds none of it.
    owner = owning_repo(wt_path)
    if owner is not None and owner.resolve() != repo_root.resolve():
        raise WorktreeError(
            f"worktree path {wt_path} belongs to a DIFFERENT repository "
            f"({owner}), not {repo_root}. Two repos sharing a parent directory "
            f"collide here. Remove it (`git -C {owner} worktree remove "
            f"{wt_path}`) or pass --worktree-base to separate them."
        )

    if wt_path.exists() and (wt_path / ".git").exists():
        # Provision on REUSE too (D-61, corrected). A re-dispatched task —
        # after an unblock, a resume, or a run stopped mid-flight — takes this
        # path, and it is the common case, not the rare one. Measured: with the
        # provisioning only on the create path, `worktree-DF-5-3` was reused
        # after a quota stop carrying `main.cjs` alone, and would have paid the
        # whole wasted fix-the-tests round D-61 exists to remove.
        provision_untracked_deps(wt_path, repo_root=repo_root)
        return Worktree(path=wt_path, branch=_checked_out_branch(wt_path, branch))
    base.mkdir(parents=True, exist_ok=True)
    # `-b` CREATES the branch, so it fails when the branch already exists. That
    # is the normal state for a re-dispatched task whose worktree is gone: the
    # branch survives a `git worktree remove`, and the reuse path above only
    # triggers when the DIRECTORY is still there. Measured 2026-08-17 — after
    # tidying preserved worktrees, all three Blocked tasks became undispatchable
    # with "git worktree add failed", and the branch that held their work was
    # the thing making it fail.
    #
    # So: create the branch only when it is not already there, and otherwise
    # check the existing one out. Checking out an existing branch deliberately
    # does NOT reset it to `base_branch` — a re-dispatch must not silently
    # discard commits an unblocked task already made, which is the property
    # that has recovered real work four times (D-54, D-59, D-63, D-66).
    exists = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}"],
        cwd=repo_root, capture_output=True, text=True,
    ).returncode == 0
    add_args = (
        ["git", "worktree", "add", str(wt_path), branch] if exists
        else ["git", "worktree", "add", str(wt_path), "-b", branch, base_branch]
    )
    try:
        subprocess.run(
            add_args,
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
            provision_untracked_deps(wt_path, repo_root=repo_root)
            return Worktree(path=wt_path, branch=_checked_out_branch(wt_path, branch))
        raise WorktreeError(
            f"git worktree add failed for {task_key} at {wt_path}",
            stderr=(exc.stderr or "").strip(),
        ) from exc
    provision_untracked_deps(wt_path, repo_root=repo_root)
    return Worktree(path=wt_path, branch=branch)


#: Files a task worktree needs that git will never bring: deliberately
#: untracked, install-time artifacts. Paths are relative to the repository root
#: and are copied from the RUNNING INSTALL's tree, never fetched.
_UNTRACKED_DEPS: tuple[str, ...] = (
    "src/claude_dispatcher/ts_signature_fingerprint/typescript.js",
    "src/claude_dispatcher/ts_signature_fingerprint/LICENSE.typescript.txt",
)


def provision_untracked_deps(
    wt_path: Path,
    source_root: Path | None = None,
    *,
    repo_root: Path | None = None,
) -> list[str]:
    """Copy install-time, gitignored dependencies into a fresh worktree (D-61).

    Returns the relative paths actually copied, for logging.

    **Why this exists.** `ts_parser_vendor`'s docstring is explicit that
    fetching the TypeScript parser is "an INSTALL-TIME step, and never a
    judgement-time one. Run it once per install." That is right for a checkout
    and false for this dispatcher, because **every task runs in a fresh
    worktree and a fresh worktree is a new install**. `typescript.js` (8.7 MB)
    and its licence are gitignored by the operator ruling of 2026-08-10 — a
    9.1 MB blob does not belong in git history — so `git worktree add` never
    brings them.

    Measured on a fresh worktree of this repository before this function
    existed::

        ls src/claude_dispatcher/ts_signature_fingerprint/
          main.cjs                    <- and nothing else
        pytest tests/test_ts_comparator.py
          87 failed, 100 passed, 3 errors

    so the mechanical gate went red on the FIRST run of EVERY TASK, the
    dispatcher spawned a fix-the-tests agent whose real job was a file copy,
    that agent committed NOTHING (the file is ignored), and the second suite
    run passed. One wasted agent spawn plus a second full suite run per task,
    on every wave.

    **COPIED, not re-fetched.** Re-running the network vendor step per worktree
    would mean one 8.7 MB download per task and a judgement-time network
    dependency that `ts_parser_vendor`'s own design forbids. **And not
    symlinked**: a worktree is meant to be self-contained, and a link pointing
    out of the tree is precisely the escape channel `scratch_clone`'s isolation
    contract (DF-4) exists to refuse.

    **A bad copy cannot pass silently.** `role_protocol._ts_prepared_parser`
    re-checks `TS_VENDORED_PARSER_SHA256` in every process that renders a
    TypeScript signature, so a truncated or wrong file is refused at use rather
    than trusted here.

    **Absence is not an error.** An install that never ran the vendor step has
    nothing to copy, and this must not turn that into a worktree-creation
    failure — the TypeScript comparator is one enrolled language among several,
    and the suite's own rows report its absence far better than a crash during
    `git worktree add` would.
    """
    root = source_root or Path(__file__).resolve().parents[2]

    # ONLY the dispatcher's OWN repository (D-61, corrected twice).
    #
    # Measured, before this guard: `create` provisioned EVERY worktree it made,
    # including one for a repository that has nothing to do with the
    # dispatcher. A bare probe repo containing one README came back carrying
    # 9,112,572 bytes of `typescript.js` and `git status --porcelain` reporting
    # `?? src/`. The committed-tree gate treats ANY uncommitted worktree file
    # as a verification failure, so this would have failed EVERY task on every
    # target repo that is not this one — evenplay-mono included — while
    # dumping 9 MB of unrelated content into each worktree. Six rows of
    # `tests/test_mechanical_verify.py` caught it.
    #
    # The guard is also the honest scope. `role_protocol.ts_parser_home`
    # resolves the parser out of the RUNNING PACKAGE and out of nowhere else,
    # so a target repo's worktree never needs a copy. The only reason a
    # worktree needs one is DOGFOODING: when the repository under test IS the
    # dispatcher, the task's `pytest` imports the package from its own
    # worktree, and that worktree is a new install.
    if repo_root is not None:
        try:
            same = repo_root.resolve() == root.resolve()
        except OSError:
            same = False
        if not same:
            return []

    copied: list[str] = []
    for rel in _UNTRACKED_DEPS:
        src = root / rel
        dst = wt_path / rel
        if not src.is_file() or dst.exists():
            continue
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dst)
            shutil.copymode(src, dst)
            copied.append(rel)
        except OSError:
            # Best effort by design: see "Absence is not an error" above. The
            # same reasoning covers a copy that fails — the parser's digest
            # check refuses it at use, and the suite reports it.
            continue
    return copied


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
