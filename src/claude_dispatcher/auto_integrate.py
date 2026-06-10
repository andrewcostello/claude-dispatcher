"""Auto-integration: after a Tasker completes a Done task, attempt to merge
its feat branch into the base_branch atomically. If the merge is clean and
the affected services build cleanly, advance the base_branch. If not, the
feat branch stays unintegrated and the task is marked Blocked with a clear
reason.

This solves the "fork-from-stale-base" problem: without auto-integration,
each new task forks from the same epic SHA regardless of how many sibling
tasks have completed, so siblings can't see each other's work. With
auto-integration, each completed task's work lands on base_branch before
the next dependent task is dispatched, giving the new worktree a fresh
view of the world.

Safety rails:
  - File-locked YAML during the merge (atomic with other workers' YAML writes).
  - Tasker-committed YAML edits on the feat branch are reverted post-merge
    (the YAML is dispatcher-owned, NOT feat-branch-owned).
  - sqlc/buf regen runs when the merge brings new query / proto sources.
  - go build + go vet run on every Go module touched by the merge.
  - On any failure, the merge is reverted; nothing is left half-applied.
  - Never pushes to remote — that's still the human's call.
  - One integration at a time per repo (the YAML FileLock serialises).
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import yaml_io


# Env vars that override codegen-binary discovery. Set these when the
# toolchain lives somewhere shutil.which() can't find it.
SQLC_BIN_ENV = "DISPATCHER_SQLC_BIN"
BUF_BIN_ENV = "DISPATCHER_BUF_BIN"


def _discover_bin(name: str, env_var: str) -> str:
    """Resolve the path to a codegen binary.

    Resolution order (no silent fallback — a missing binary is a hard error):
      1. The env var override (`env_var`), if set and non-empty.
      2. `shutil.which(name)` — the binary on PATH.
      3. Otherwise raise RuntimeError naming the binary and both mechanisms.
    """
    override = os.environ.get(env_var)
    if override:
        return override
    found = shutil.which(name)
    if found:
        return found
    raise RuntimeError(
        f"codegen binary {name!r} not found: set ${env_var} to its path, "
        f"or make {name!r} available on PATH (looked it up via "
        f"shutil.which({name!r})). No silent fallback — install the "
        f"toolchain or set the override."
    )

# Go-module candidate directories. The auto-integrator only build-checks
# directories that have a go.mod AND have been touched by the merge.
GO_MODULE_CANDIDATES = (
    "apps/finance-domain/wallet",
    "apps/platform-domain/bay-session",
    "apps/platform-domain/core",
    "apps/platform-domain/partner-service",
    "apps/game-domain/engine",
    "apps/game-domain/paylines",
)


@dataclass
class IntegrateResult:
    """Outcome of one auto-integration attempt.

    status semantics:
      - "integrated"          : merge committed; base_branch advanced.
      - "skipped-disabled"    : auto_integrate flag is off; no-op.
      - "skipped-no-commits"  : feat branch has no commits ahead of base.
      - "skipped-already-on"  : base_branch already contains the feat-branch
                                tip (already-merged).
      - "skipped-conflict"    : git merge produced a content conflict.
      - "skipped-build-fail"  : merge applied but a touched Go module failed
                                to build or vet.
      - "skipped-codegen-fail": sqlc generate or buf generate exited non-zero.
      - "skipped-commit-fail" : the merge commit step itself failed (e.g.
                                pre-commit hook rejected).
      - "error"               : unrecoverable shell-level failure (git
                                command itself errored, not the merge).
    """
    status: str
    merge_sha: str | None = None
    detail: str = ""
    services_built: list[str] = field(default_factory=list)
    sqlc_regen: list[str] = field(default_factory=list)
    buf_regen: list[str] = field(default_factory=list)


def integrate(
    *,
    repo_root: Path,
    yaml_path: Path,
    base_branch: str,
    feat_branch: str,
    task_key: str,
    log: Callable[[str], None],
    enabled: bool = True,
    sqlc_bin: str | None = None,
    buf_bin: str | None = None,
) -> IntegrateResult:
    """Attempt to integrate `feat_branch` into `base_branch` in `repo_root`.

    The integration sequence:
      1. Test-merge with `git merge-tree` (no working tree change).
      2. Acquire the YAML FileLock.
      3. Stash the dispatcher's transient YAML edits.
      4. `git merge --no-ff --no-commit feat_branch`.
      5. Revert any YAML changes the feat branch's commit brought in.
      6. If new sqlc queries: `sqlc generate` in each affected service.
      7. If new .proto files: `buf generate` in each affected service.
      8. `go build` + `go vet` on every Go module the merge touched.
      9. Commit the merge.
      10. Pop the stash.

    On any step's failure, all earlier steps are reverted and the function
    returns a skipped-* result.

    `enabled=False` is a fast no-op for callers that want to check the flag
    in one place.

    `sqlc_bin` / `buf_bin` are optional explicit overrides. When None (the
    default), the binary is discovered lazily — only if the merge actually
    brings new query/proto sources — via `_discover_bin` (env override →
    PATH → hard error). Codegen tools are never silently skipped.
    """
    if not enabled:
        return IntegrateResult(status="skipped-disabled")

    log(f"  {task_key} auto-integrate: starting")

    # 1. Are there even any commits to integrate?
    rc, out, _ = _run(["git", "log", "--oneline", f"{base_branch}..{feat_branch}"],
                     cwd=repo_root)
    if rc != 0:
        return IntegrateResult(status="error",
                               detail=f"git log failed checking {feat_branch}: rc={rc}")
    commit_lines = [ln for ln in out.splitlines() if ln.strip()]
    if not commit_lines:
        # Either already-merged (the Tasker's claimed commit is an ancestor
        # of base_branch, e.g. a prior PR landed it) or no work was done.
        # Distinguish via merge-base.
        rc_anc, _, _ = _run(
            ["git", "merge-base", "--is-ancestor", feat_branch, base_branch],
            cwd=repo_root,
        )
        if rc_anc == 0:
            log(f"  {task_key} auto-integrate: branch already on {base_branch}")
            return IntegrateResult(status="skipped-already-on")
        log(f"  {task_key} auto-integrate: no commits to integrate")
        return IntegrateResult(status="skipped-no-commits")

    # 2. Test-merge first (no working tree change). Cheap conflict detection.
    rc, mt_out, _ = _run(
        ["git", "merge-tree", "--write-tree", "--merge-base", base_branch,
         base_branch, feat_branch],
        cwd=repo_root,
    )
    if rc != 0:
        # Conflict detected — surface what files conflict for the human.
        import re
        conflicts = re.findall(r"in (.+)$", mt_out, re.MULTILINE)
        return IntegrateResult(
            status="skipped-conflict",
            detail=("conflict files: " + ", ".join(conflicts[:5])
                    if conflicts else "merge-tree reported conflict"),
        )

    # 3-10. Do the real merge under the YAML FileLock.
    with yaml_io.FileLock(yaml_path):
        # Stash the dispatcher's transient YAML edits so they don't
        # conflict with the merge.
        stashed = False
        rc_dirty, _, _ = _run(["git", "diff", "--quiet", "--", str(yaml_path)],
                             cwd=repo_root)
        if rc_dirty != 0:
            rc_s, _, _ = _run(
                ["git", "stash", "push", "-m",
                 f"auto-integrate-{task_key}-pre", "--", str(yaml_path)],
                cwd=repo_root,
            )
            stashed = (rc_s == 0)

        # Actual merge.
        rc, _, err = _run(
            ["git", "merge", "--no-ff", "--no-commit", feat_branch],
            cwd=repo_root,
        )
        if rc != 0:
            # Late conflict — merge-tree said clean but the actual merge
            # didn't (e.g. local dirty state we didn't anticipate, or a
            # crlf weirdness). Abort and bail.
            _abort_merge(repo_root)
            if stashed:
                _run(["git", "stash", "pop"], cwd=repo_root)
            return IntegrateResult(
                status="skipped-conflict",
                detail=("late conflict: " + err[-300:]).strip(),
            )

        # Safety: feat-branch Taskers sometimes commit the tasks YAML. The
        # YAML is dispatcher-owned, NOT feat-branch-owned. Revert any YAML
        # changes the merge brought along.
        rc_yaml, _, _ = _run(
            ["git", "diff", "--cached", "--quiet", "--", str(yaml_path)],
            cwd=repo_root,
        )
        if rc_yaml != 0:
            # Revert YAML changes to base-branch state.
            _run(["git", "checkout", "ORIG_HEAD", "--", str(yaml_path)],
                cwd=repo_root)
            _run(["git", "checkout-index", "--force", "--", str(yaml_path)],
                cwd=repo_root)

        # Codegen regen — sqlc + buf — for files newly merged in.
        services_diff = _services_touched(repo_root, base_branch, feat_branch)
        try:
            sqlc_regen = _maybe_regen_sqlc(
                repo_root, base_branch, feat_branch, sqlc_bin, log, task_key,
            )
            buf_regen = _maybe_regen_buf(
                repo_root, base_branch, feat_branch, buf_bin, log, task_key,
            )
        except RuntimeError as e:
            # A required codegen binary couldn't be discovered. Don't leave the
            # merge half-applied — revert and surface the clear reason.
            _reset_merge(repo_root)
            if stashed:
                _run(["git", "stash", "pop"], cwd=repo_root)
            return IntegrateResult(
                status="skipped-codegen-fail",
                detail=str(e),
                services_built=sorted(services_diff),
            )

        # Build + vet every Go module the merge touched.
        ok, build_err = _build_check(repo_root, services_diff)
        if not ok:
            _reset_merge(repo_root)
            if stashed:
                _run(["git", "stash", "pop"], cwd=repo_root)
            return IntegrateResult(
                status="skipped-build-fail",
                detail=build_err[-500:],
                services_built=sorted(services_diff),
                sqlc_regen=sqlc_regen,
                buf_regen=buf_regen,
            )

        # Commit the merge.
        rc, _, err = _run(["git", "commit", "--no-edit"], cwd=repo_root)
        if rc != 0:
            _reset_merge(repo_root)
            if stashed:
                _run(["git", "stash", "pop"], cwd=repo_root)
            return IntegrateResult(
                status="skipped-commit-fail",
                detail=(err[-300:]).strip(),
                services_built=sorted(services_diff),
            )

        # Capture the merge SHA.
        rc, sha, _ = _run(["git", "rev-parse", "HEAD"], cwd=repo_root)
        merge_sha = sha.strip()[:8] if rc == 0 else None

        # Restore the dispatcher's transient YAML edits.
        if stashed:
            _run(["git", "stash", "pop"], cwd=repo_root)

    log(f"  {task_key} auto-integrated as {merge_sha}")
    return IntegrateResult(
        status="integrated",
        merge_sha=merge_sha,
        services_built=sorted(services_diff),
        sqlc_regen=sqlc_regen,
        buf_regen=buf_regen,
    )


# --- internal helpers ------------------------------------------------------


def _run(cmd: list[str], *, cwd: Path) -> tuple[int, str, str]:
    """Run a shell command. Returns (exit_code, stdout, stderr)."""
    p = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True)
    return p.returncode, p.stdout, p.stderr


def _abort_merge(repo_root: Path) -> None:
    """Best-effort merge abort. Safe to call even if not in a merge."""
    _run(["git", "merge", "--abort"], cwd=repo_root)


def _reset_merge(repo_root: Path) -> None:
    """Hard-reset the in-progress merge. Used after build-fail when
    `merge --abort` won't work (the merge already produced an unfinalised
    state without conflicts)."""
    _run(["git", "reset", "--merge"], cwd=repo_root)


def _services_touched(repo_root: Path, base: str, feat: str) -> set[str]:
    """Set of Go-module directories the merge touched (have a go.mod)."""
    rc, out, _ = _run(
        ["git", "diff", "--name-only", f"{base}...{feat}"], cwd=repo_root,
    )
    if rc != 0:
        return set()
    touched = set()
    for path in out.splitlines():
        path = path.strip()
        for d in GO_MODULE_CANDIDATES:
            if path.startswith(d + "/"):
                if (repo_root / d / "go.mod").exists():
                    touched.add(d)
                break
    return touched


def _maybe_regen_sqlc(
    repo_root: Path, base: str, feat: str, sqlc_bin: str,
    log: Callable[[str], None], task_key: str,
) -> list[str]:
    """If the merge brought new sqlc queries, regen the gitignored generated
    code. Returns the list of services where regen ran. Safe: sqlc generate
    writes only to gitignored store/sqlc/ directories.

    No regen (empty list) if no store/queries/*.sql files were touched, or no
    touched service has a sqlc.yaml. The sqlc binary is only discovered when
    regen is actually required; if it can't be found `_discover_bin` raises.
    """
    rc, out, _ = _run(
        ["git", "diff", "--name-only", f"{base}...{feat}"], cwd=repo_root,
    )
    if rc != 0:
        return []
    regen_services = set()
    for path in out.splitlines():
        path = path.strip()
        parts = path.split("/")
        if "store" in parts and "queries" in parts and path.endswith(".sql"):
            store_idx = parts.index("store")
            svc = "/".join(parts[:store_idx])
            if svc and (repo_root / svc / "sqlc.yaml").exists():
                regen_services.add(svc)
    if not regen_services:
        return []
    bin_path = sqlc_bin or _discover_bin("sqlc", SQLC_BIN_ENV)
    regenerated = []
    for svc in sorted(regen_services):
        log(f"  {task_key} auto-integrate: sqlc generate in {svc}")
        rc, _, err = _run([bin_path, "generate"], cwd=repo_root / svc)
        if rc == 0:
            regenerated.append(svc)
        else:
            log(f"  {task_key} auto-integrate: sqlc generate FAILED in {svc}: {err[-150:]}")
    return regenerated


def _maybe_regen_buf(
    repo_root: Path, base: str, feat: str, buf_bin: str,
    log: Callable[[str], None], task_key: str,
) -> list[str]:
    """If the merge brought new .proto files, regen the gitignored .pb.go.
    Same pattern as sqlc regen — the buf binary is only discovered when regen
    is actually required, and `_discover_bin` raises if it can't be found."""
    rc, out, _ = _run(
        ["git", "diff", "--name-only", f"{base}...{feat}"], cwd=repo_root,
    )
    if rc != 0:
        return []
    regen_services = set()
    for path in out.splitlines():
        path = path.strip()
        if not path.endswith(".proto"):
            continue
        cur = Path(path).parent
        while str(cur) not in (".", "/"):
            if (repo_root / cur / "buf.gen.yaml").exists():
                regen_services.add(str(cur))
                break
            cur = cur.parent
    if not regen_services:
        return []
    bin_path = buf_bin or _discover_bin("buf", BUF_BIN_ENV)
    regenerated = []
    for svc in sorted(regen_services):
        log(f"  {task_key} auto-integrate: buf generate in {svc}")
        # buf generate needs the protoc-gen plugins on PATH.
        env = os.environ.copy()
        env["PATH"] = f"{Path(bin_path).parent}:{env.get('PATH', '')}"
        proc = subprocess.run(
            [bin_path, "generate"], cwd=str(repo_root / svc),
            capture_output=True, text=True, env=env,
        )
        if proc.returncode == 0:
            regenerated.append(svc)
        else:
            log(f"  {task_key} auto-integrate: buf generate FAILED in {svc}: {proc.stderr[-150:]}")
    return regenerated


def _build_check(repo_root: Path, services: set[str]) -> tuple[bool, str]:
    """Run go build + go vet for each affected service.
    Returns (ok, error_message)."""
    for svc in sorted(services):
        rc, _, err = _run(["go", "build", "./..."], cwd=repo_root / svc)
        if rc != 0:
            return False, f"{svc}: build failed\n{err[-800:]}"
        rc, _, err = _run(["go", "vet", "./..."], cwd=repo_root / svc)
        if rc != 0:
            return False, f"{svc}: vet failed\n{err[-800:]}"
    return True, ""
