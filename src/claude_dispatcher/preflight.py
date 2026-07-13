"""Run-start preflight checks for `dispatcher run` (live modes only).

Dogfood run #1 burned a full wave silently: Taskers spawned without a
permission-bypass flag stalled at their first tool-use prompt and exited 0
with nothing committed, and the Tasker role file — at the time a
machine-local symlink — didn't resolve in fresh worktrees. Both failure
modes were knowable *before* any worktree was created or session spawned.
This module is that knowledge, made executable: four checks run by
``orchestrator.execute()`` after base-branch resolution and before the run
directory, journal, or any worktree exists.

Checks and their severity policy
--------------------------------
Failures are reserved for conditions that *provably* waste the whole run
(every Tasker would stall or block); anything merely suspicious is a
warning so a human-attended run is never refused on a guess:

  * **claude binary** — missing binary is a FAILURE (nothing can spawn);
    present-but-version-unreadable is a WARNING (the spawn may still work).
  * **dispatcher staleness** — WARNING only, and only when the repo being
    dispatched IS claude-dispatcher itself: a pipx-installed dispatcher older
    than the repo HEAD it is dispatching is how run #1's fixes silently
    didn't apply. A stale tool still runs; refusing would be overreach.
  * **permission flags** — FAILURE for both live modes (unattended and
    supervised; dry-run never reaches preflight). Without a bypass
    mechanism every Tasker stalls at its first tool-use prompt.
  * **tasker role file resolvable from a fresh worktree** — FAILURE when the
    file is neither git-tracked nor resolvable in a probe worktree; a
    WARNING when the probe *infrastructure* itself fails (the run would
    surface the real problem at the first task worktree anyway).

The role-file probe subtlety
----------------------------
In the dispatcher's own repo, ``.claude/workflow`` is a git-tracked SYMLINK
(mode 120000, target ``../../claude-workflow`` — outside the repo), so
``git ls-files --error-unmatch`` on the role file fails even though the path
resolves fine in fresh sibling worktrees. Hence the two-step check: tracked
regular file passes immediately; otherwise a throwaway detached worktree is
created and ``Path.exists()`` — which follows symlinks — answers the actual
question ("does this path resolve where a task worktree will live?").

The probe worktree is deliberately created at the SAME location real task
worktrees will use — the *configured* worktree base from
``worktree.worktree_base(repo_root, override)`` (``--worktree-base`` when
set, ``/worktrees`` in the container convention, ``repo_root.parent`` only
as the default) — not under a system temp dir and not hardcoded to
``repo_root.parent``: a relative symlink's target resolves relative to the
worktree's own location, so a probe at any other directory depth/location
can diverge from reality in both directions (false pass → the silent burn
this check exists to prevent; false fail → refusing a healthy run). Probing
from ``/tmp`` would falsely fail the exact layout this check exists to
validate.

Journal contract (design judgment calls)
----------------------------------------
The preflight outcome is journaled as a NEW ``preflight`` event type rather
than an extension of the genesis ``run_started`` payload. The genesis schema
is hash-anchored and enforced by ``journal.verify()`` via
``GENESIS_PROVENANCE_KEYS``; extending it would couple a best-effort
diagnostic to the tamper-evidence contract. A separate event keeps the
genesis schema and verifier untouched.

The emitted payload's ``failures`` list is always empty: a *failed*
preflight exits before the run directory — and therefore the journal —
exists, so only passing (or skipped) preflights are ever journaled. The key
is kept anyway so the payload shape is stable for readers. When the run was
started with ``--skip-preflight`` the payload is
``{"skipped": true, "checks": {}, "warnings": [], "failures": []}`` — the
skip itself is thereby journaled (and is also visible in the genesis
``run_config.skip_preflight``).

``orchestrator.resume_run()`` deliberately does NOT re-run preflight: a
resume continues a run whose preflight verdict (or explicit skip) is already
on the chain, and re-checking mid-run could refuse to finish work that is
already half-landed.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tomllib
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import doctor
from . import worktree as wt_mod


DEFAULT_ROLE_FILE = ".claude/workflow/roles/tasker.md"

# Timeout for each git command the preflight issues. Generous — these are
# local-only operations — but bounded so a wedged git can't hang the run
# before it starts.
GIT_TIMEOUT_SECONDS = 60.0

# The exact actionable failure for missing permission flags. The flag pair in
# the suggestion is the combination proven to work in dogfooding (bypass for
# the session, allow-flag so the bypass is accepted in non-interactive mode).
PERMISSION_FLAGS_FAILURE = (
    "unattended/supervised runs require a permission-bypass flag or every "
    "Tasker stalls at its first tool-use prompt (dogfood run #1). Add: "
    "--claude-extra-args '--permission-mode bypassPermissions "
    "--allow-dangerously-skip-permissions'"
)


@dataclass
class PreflightResult:
    """Outcome of one preflight run.

    ``checks`` is a JSON-safe payload describing each check's outcome — it is
    embedded verbatim in the ``preflight`` journal event, so values must stay
    plain (str/int/bool/None/list/dict).
    """

    ok: bool
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    checks: dict[str, Any] = field(default_factory=dict)


def skipped_result() -> PreflightResult:
    """The result recorded when the human passed ``--skip-preflight``."""
    return PreflightResult(ok=True, failures=[], warnings=[], checks={})


def run_preflight(
    *,
    claude_bin: str,
    claude_extra_args: list[str],
    mode: str,
    repo_root: Path,
    base_branch: str,
    role_file: str = DEFAULT_ROLE_FILE,
    worktree_base: Path | None = None,
    no_claude: bool = False,
    implementer: str | None = None,
) -> PreflightResult:
    """Run preflight checks and aggregate their verdicts.

    ``worktree_base`` is the same ``--worktree-base`` override the run will
    hand to task-worktree creation (None → the conventional default); the
    role-file probe must live at that exact base or its verdict can diverge
    from reality (see module docstring).

    ``no_claude``: skip Claude binary + Claude permission-flag requirements;
    require the implementer binary (default grok) instead.

    Pure apart from the subprocess reads (and the throwaway probe worktree,
    removed before returning); creates nothing under the repo or runs dir.
    """
    failures: list[str] = []
    warnings: list[str] = []
    checks: dict[str, Any] = {}

    if no_claude:
        impl = (implementer or "grok").strip().lower()
        # Map gemini → agy binary for PATH probe.
        bin_name = {"gemini": "agy", "claude": "claude", "codex": "codex",
                    "grok": "grok"}.get(impl, impl)
        _check_implementer_binary(bin_name, failures, warnings, checks)
        checks["no_claude"] = True
        # Permission flags are Claude-specific; skip under no_claude.
        checks["permission_flags"] = {
            "ok": True, "mechanism": "skipped-no-claude", "mode": mode,
        }
    else:
        _check_claude_binary(claude_bin, failures, warnings, checks)
        _check_permission_flags(claude_extra_args, mode, failures, checks)
    _check_dispatcher_staleness(repo_root, warnings, checks)
    _check_role_file(
        repo_root, base_branch, role_file, failures, warnings, checks,
        worktree_base=worktree_base,
    )

    return PreflightResult(
        ok=not failures, failures=failures, warnings=warnings, checks=checks,
    )


# --- check 1: claude binary ---------------------------------------------------


def _check_implementer_binary(
    bin_name: str,
    failures: list[str],
    warnings: list[str],
    checks: dict[str, Any],
) -> None:
    """Require the implementer CLI on PATH for no-Claude fleets."""
    info = doctor.probe_binary(bin_name)
    entry = {
        "ok": bool(info.get("present")),
        "bin": bin_name,
        "path": info.get("path"),
        "version": info.get("version"),
    }
    checks["implementer_binary"] = entry
    if not info.get("present"):
        failures.append(
            f"implementer binary {bin_name!r} not found on PATH — install it "
            f"or drop --no-claude / set --implementer to an available agent"
        )
    elif not info.get("version"):
        warnings.append(
            f"implementer binary {bin_name!r} is present but --version failed "
            f"({info.get('version_error') or 'unknown'})"
        )


def _check_claude_binary(
    claude_bin: str,
    failures: list[str],
    warnings: list[str],
    checks: dict[str, Any],
) -> None:
    """Missing binary → failure; present but version unreadable → warning."""
    info = doctor.probe_binary(claude_bin)
    entry: dict[str, Any] = {
        "ok": bool(info["present"]),
        "path": info["path"],
        "version": info["version"],
    }
    if info.get("version_error"):
        entry["version_error"] = info["version_error"]
    checks["claude_binary"] = entry

    if not info["present"]:
        failures.append(
            f"claude binary '{claude_bin}' not found on PATH — install it or "
            f"pass --claude-bin"
        )
    elif info["version"] is None:
        warnings.append(
            f"claude binary '{claude_bin}' is present but its version could "
            f"not be read ({info.get('version_error', 'unknown error')})"
        )


# --- check 2: dispatcher staleness ---------------------------------------------


def _installed_version() -> str | None:
    """The installed claude-dispatcher version, or None when not installed.

    Thin patchable seam over the doctor's lookup so tests never depend on
    this machine's actual pipx/pip state.
    """
    version = doctor._dispatcher_version()
    return None if version == "unknown" else version


def _repo_pyproject_text(repo_root: Path) -> str | None:
    """pyproject.toml content at the repo's HEAD, falling back to the
    working-tree file when git can't show it. None when neither is readable.

    HEAD is preferred because the staleness question is "does the installed
    tool match the *committed* code it is dispatching?" — an uncommitted
    working-tree edit shouldn't change the verdict.
    """
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo_root), "show", "HEAD:pyproject.toml"],
            capture_output=True, text=True, check=False,
            timeout=GIT_TIMEOUT_SECONDS,
        )
        if proc.returncode == 0 and proc.stdout:
            return proc.stdout
    except Exception:
        pass
    try:
        path = repo_root / "pyproject.toml"
        if path.is_file():
            return path.read_text(encoding="utf-8")
    except OSError:
        pass
    return None


# Fallback when tomllib refuses the file: first `name = "..."` / `version =
# "..."` assignments at the start of a line. Tolerant by design — a partially
# broken pyproject shouldn't crash a check that only ever warns.
_NAME_RE = re.compile(r'^name\s*=\s*["\']([^"\']+)["\']', re.MULTILINE)
_VERSION_RE = re.compile(r'^version\s*=\s*["\']([^"\']+)["\']', re.MULTILINE)


def _parse_name_version(text: str) -> tuple[str | None, str | None]:
    """(project name, project version) from pyproject text, best-effort."""
    try:
        project = tomllib.loads(text).get("project", {})
        if isinstance(project, dict):
            name = project.get("name")
            version = project.get("version")
            return (
                name if isinstance(name, str) else None,
                version if isinstance(version, str) else None,
            )
    except Exception:
        pass
    name_m = _NAME_RE.search(text)
    version_m = _VERSION_RE.search(text)
    return (
        name_m.group(1) if name_m else None,
        version_m.group(1) if version_m else None,
    )


def _check_dispatcher_staleness(
    repo_root: Path,
    warnings: list[str],
    checks: dict[str, Any],
) -> None:
    """Warn (never fail) when the installed dispatcher trails the repo HEAD.

    Applicable only when the repo being dispatched IS claude-dispatcher; any
    other repo — or either version being unknown — records the check as
    not-applicable and stays silent.
    """
    entry: dict[str, Any] = {
        "applicable": False,
        "installed_version": None,
        "repo_version": None,
        "stale": False,
    }
    checks["dispatcher_staleness"] = entry

    text = _repo_pyproject_text(repo_root)
    if text is None:
        entry["detail"] = "no pyproject.toml readable at repo root"
        return

    name, repo_version = _parse_name_version(text)
    if name != "claude-dispatcher":
        entry["detail"] = f"repo is {name!r}, not claude-dispatcher"
        return

    installed = _installed_version()
    entry["installed_version"] = installed
    entry["repo_version"] = repo_version
    if installed is None or repo_version is None:
        entry["detail"] = "installed or repo version unknown"
        return

    entry["applicable"] = True
    if installed != repo_version:
        entry["stale"] = True
        warnings.append(
            f"installed claude-dispatcher is {installed} but this repo's HEAD "
            f"pyproject.toml says {repo_version} — the installed dispatcher "
            f"may be a stale pipx snapshot; reinstall, e.g. "
            f"`pipx install --force .`"
        )


# --- check 3: permission flags --------------------------------------------------


def _permission_bypass_mechanism(claude_extra_args: list[str]) -> str | None:
    """The first recognized permission-bypass mechanism in the effective
    claude args, or None when there is none.

    Accepted: ``--dangerously-skip-permissions``, the adjacent pair
    ``--permission-mode bypassPermissions``, or the single-token
    ``--permission-mode=bypassPermissions``. ``--permission-mode`` with any
    other value does not count, and ``--allow-dangerously-skip-permissions``
    alone does not count (it only *permits* a bypass; it doesn't enable one).
    """
    for i, arg in enumerate(claude_extra_args):
        if arg == "--dangerously-skip-permissions":
            return arg
        if arg == "--permission-mode=bypassPermissions":
            return arg
        if (
            arg == "--permission-mode"
            and i + 1 < len(claude_extra_args)
            and claude_extra_args[i + 1] == "bypassPermissions"
        ):
            return "--permission-mode bypassPermissions"
    return None


def _check_permission_flags(
    claude_extra_args: list[str],
    mode: str,
    failures: list[str],
    checks: dict[str, Any],
) -> None:
    """Both live modes require a bypass mechanism (dry-run never gets here)."""
    mechanism = _permission_bypass_mechanism(claude_extra_args)
    checks["permission_flags"] = {
        "ok": mechanism is not None,
        "mechanism": mechanism,
        "mode": mode,
    }
    if mechanism is None:
        failures.append(PERMISSION_FLAGS_FAILURE)


# --- check 4: tasker role file ----------------------------------------------------


def _role_file_tracked(repo_root: Path, role_file: str) -> bool:
    """True iff git tracks `role_file` as a path of its own (a regular file —
    a path *through* a tracked symlinked directory is not itself tracked)."""
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo_root), "ls-files", "--error-unmatch",
             "--", role_file],
            capture_output=True, text=True, check=False,
            timeout=GIT_TIMEOUT_SECONDS,
        )
    except Exception:
        return False
    return proc.returncode == 0


def _probe_ref(repo_root: Path, base_branch: str) -> str:
    """`base_branch` when it resolves, else HEAD — the probe worktree must be
    cut from the same ref task worktrees will fork from, falling back to
    something that always exists."""
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "--verify",
             "--quiet", base_branch],
            capture_output=True, text=True, check=False,
            timeout=GIT_TIMEOUT_SECONDS,
        )
        if proc.returncode == 0:
            return base_branch
    except Exception:
        pass
    return "HEAD"


def _probe_worktree_check(
    repo_root: Path, ref: str, role_file: str, worktree_base: Path | None,
) -> tuple[bool | None, str]:
    """Create a throwaway detached worktree of `ref` and report whether
    `role_file` resolves inside it.

    Returns ``(resolves, detail)``: True/False when the probe ran, or
    ``(None, stderr)`` when the probe infrastructure itself failed. The
    probe lives directly under the run's *configured* worktree base —
    ``worktree.worktree_base(repo_root, override)``, the same directory
    depth/location as ``worktree.worktree_path(base, key)`` — because a
    relative symlink's target resolves relative to the worktree's location
    (see module docstring). The base is created if missing, mirroring real
    task-worktree creation; failure to compute or create it is a probe-
    infrastructure failure (→ warning), not a verdict. Cleanup is
    best-effort in a ``finally``: remove the worktree, prune git's
    bookkeeping, and sweep any leftover directory.
    """
    try:
        base = wt_mod.worktree_base(
            repo_root, str(worktree_base) if worktree_base else None,
        )
        base.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        return None, str(e)
    probe = base / f"preflight-probe-{uuid.uuid4().hex[:12]}"
    try:
        try:
            proc = subprocess.run(
                ["git", "-C", str(repo_root), "worktree", "add", "--detach",
                 str(probe), ref],
                capture_output=True, text=True, check=False,
                timeout=GIT_TIMEOUT_SECONDS,
            )
        except Exception as e:
            return None, str(e)
        if proc.returncode != 0:
            return None, proc.stderr.strip()
        # Path.exists() follows symlinks — exactly the "resolvable from a
        # fresh worktree" semantic the Tasker spawn needs.
        return (probe / role_file).exists(), ""
    finally:
        for cmd in (
            ["git", "-C", str(repo_root), "worktree", "remove", "--force",
             str(probe)],
            ["git", "-C", str(repo_root), "worktree", "prune"],
        ):
            try:
                subprocess.run(
                    cmd, capture_output=True, text=True, check=False,
                    timeout=GIT_TIMEOUT_SECONDS,
                )
            except Exception:
                pass
        shutil.rmtree(probe, ignore_errors=True)


def _check_role_file(
    repo_root: Path,
    base_branch: str,
    role_file: str,
    failures: list[str],
    warnings: list[str],
    checks: dict[str, Any],
    *,
    worktree_base: Path | None = None,
) -> None:
    """Tracked regular file → pass without a probe; otherwise probe a fresh
    worktree at the configured worktree base. Missing in the probe → failure;
    probe infrastructure failing → warning (the run surfaces the real problem
    at the first task worktree)."""
    entry: dict[str, Any] = {"ok": True, "role_file": role_file, "method": None}
    checks["tasker_role_file"] = entry

    if _role_file_tracked(repo_root, role_file):
        entry["method"] = "tracked-regular-file"
        return

    ref = _probe_ref(repo_root, base_branch)
    entry["probe_ref"] = ref
    resolves, detail = _probe_worktree_check(repo_root, ref, role_file, worktree_base)
    if resolves is None:
        entry["method"] = "probe-failed"
        entry["detail"] = detail
        warnings.append(
            f"could not probe whether {role_file} resolves in a fresh "
            f"worktree (worktree add failed: {detail}); proceeding — the run "
            f"will surface any real problem at the first task worktree"
        )
        return

    entry["method"] = "probe-worktree"
    if resolves:
        return
    # Single-orchestrator: dispatched runs use a self-contained implementer
    # prompt and do not require tasker.md. Missing role file is a warning so
    # interactive/Tasker tooling still gets a signal, but dogfood / Grok-only
    # runs are not blocked.
    entry["ok"] = True
    entry["missing"] = True
    warnings.append(
        f"role file {role_file} won't resolve in fresh worktrees (neither "
        f"git-tracked nor resolvable in a probe of {ref}). Dispatched "
        f"implementers no longer require Tasker; this only matters for "
        f"interactive Tasker sessions. To silence: commit "
        f"`.claude/workflow` (or a relative symlink)."
    )
