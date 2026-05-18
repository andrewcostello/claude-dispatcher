"""Bridge between the dispatcher's tasks YAML and the `forecast` Jira tool.

The dispatcher and `forecast` share no file but share the Jira issue key.
This module turns each task row in the YAML into the equivalent
`forecast jira create` invocation (YAML → Jira) and, after a dispatcher
run, transitions Jira to match the YAML's terminal status (Jira ← YAML).

Both directions are idempotent and degrade gracefully when `forecast` is
not installed or not configured for the project — the dispatcher should
remain usable without the bridge. The CLI subcommands always exit 0 on
"bridge not applicable here" cases so a CI step or shell pipeline can
chain `dispatcher run && dispatcher forecast-sync` without depending on
the forecast tool being present.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import yaml_io


# A real Jira key looks like SMG-123, FSG-2, FOO-7. Anything not matching
# this AND not the configured placeholder prefix is treated as "needs creation".
_JIRA_KEY_RE = re.compile(r"^[A-Z][A-Z0-9]*-\d+$")

# Default SMG-flavored status mapping per evenplay-mono CLAUDE.md.
# Overrideable per-YAML via top-level forecast.status_mapping.
DEFAULT_STATUS_MAPPING = {
    "Done": ("Done", "Done"),                  # (target_status, resolution_or_None)
    "Blocked": ("Is Blocked", None),
    "Escalated": ("Is Blocked", None),
}

DEFAULT_PLACEHOLDER_PREFIX = "TBD-"


# --- detection -------------------------------------------------------------


@dataclass
class BridgeContext:
    """Resolved bridge inputs. Returned by detect()."""

    forecast_bin: str | None
    config_path: Path | None
    config_dir: Path
    placeholder_prefix: str
    status_mapping: dict[str, tuple[str, str | None]]
    skip_reason: str | None = None

    @property
    def usable(self) -> bool:
        return self.forecast_bin is not None and self.config_path is not None


def detect(yaml_path: Path) -> BridgeContext:
    """Determine whether the bridge can run for this YAML.

    Looks for:
      1. A `forecast` binary on PATH.
      2. A `.forecast/config.yaml` reachable from the YAML's parent dir
         (walks up like git does for repo discovery).
      3. Optional YAML overrides under top-level `forecast:`.
    """
    forecast_bin = shutil.which("forecast")

    config_dir = yaml_path.parent.resolve()
    config_path = _find_forecast_config(config_dir)

    placeholder_prefix = DEFAULT_PLACEHOLDER_PREFIX
    status_mapping = dict(DEFAULT_STATUS_MAPPING)

    # Load YAML-level overrides if present. Don't fail if the YAML can't
    # be parsed here — the regular dispatcher load will surface that.
    try:
        doc = yaml_io.load(yaml_path)
        fc = doc.get("forecast") if isinstance(doc, dict) else None
        if isinstance(fc, dict):
            if "placeholder_prefix" in fc:
                placeholder_prefix = str(fc["placeholder_prefix"])
            if "status_mapping" in fc and isinstance(fc["status_mapping"], dict):
                for k, v in fc["status_mapping"].items():
                    if isinstance(v, str):
                        status_mapping[k] = (v, None)
                    elif isinstance(v, dict):
                        status_mapping[k] = (
                            str(v.get("to", v.get("status"))),
                            v.get("resolution"),
                        )
    except Exception:
        # Don't block detection on YAML parse trouble — caller will surface it.
        pass

    skip = None
    if forecast_bin is None:
        skip = "forecast binary not on PATH"
    elif config_path is None:
        skip = (
            f"no .forecast/config.yaml found at or above {config_dir}; "
            "run `forecast init` in the project root first"
        )

    return BridgeContext(
        forecast_bin=forecast_bin,
        config_path=config_path,
        config_dir=config_dir,
        placeholder_prefix=placeholder_prefix,
        status_mapping=status_mapping,
        skip_reason=skip,
    )


def _find_forecast_config(start: Path) -> Path | None:
    """Walk up from `start` looking for `.forecast/config.yaml`."""
    cur = start
    for _ in range(20):  # bounded walk; never hand-rolled infinite loops
        candidate = cur / ".forecast" / "config.yaml"
        if candidate.is_file():
            return candidate
        if cur.parent == cur:
            return None
        cur = cur.parent
    return None


# --- key classification ----------------------------------------------------


def is_placeholder_key(key: str, placeholder_prefix: str) -> bool:
    """True iff this key is a placeholder waiting for `forecast jira create`."""
    if not key:
        return True
    if key.startswith(placeholder_prefix):
        return True
    if not _JIRA_KEY_RE.match(key):
        return True
    return False


# --- create flow -----------------------------------------------------------


def build_create_argv(forecast_bin: str, row: dict, default_epic: str | None) -> list[str]:
    """Translate one YAML task row into a `forecast jira create` argv.

    Required row fields: summary, type. Description and labels are passed
    when present. Optional forecast-mappable fields (priority, epic, parent,
    story_points, due_date, assignee, fix_versions, components) are added
    when set.
    """
    summary = str(row["summary"]).strip()
    type_ = str(row.get("type", "Task")).strip()
    argv = [forecast_bin, "jira", "create", "--summary", summary, "--type", type_]

    desc = row.get("description")
    if isinstance(desc, str) and desc.strip():
        argv += ["--description", desc.strip()]

    labels = row.get("labels")
    if labels:
        argv += ["--labels", ",".join(str(l) for l in labels)]

    priority = row.get("priority")
    if priority:
        argv += ["--priority", str(priority)]

    # row.epic overrides top-level epic
    epic = row.get("epic") if row.get("epic") else default_epic
    if epic:
        argv += ["--epic", str(epic)]

    parent = row.get("parent")
    if parent:
        argv += ["--parent", str(parent)]

    story_points = row.get("story_points")
    if story_points is not None:
        argv += ["--story-points", str(story_points)]

    due_date = row.get("due_date")
    if due_date:
        argv += ["--due-date", str(due_date)]

    assignee = row.get("assignee")
    if assignee:
        argv += ["--assignee", str(assignee)]

    fix_versions = row.get("fix_versions")
    if fix_versions:
        argv += ["--fix-versions", ",".join(str(v) for v in fix_versions)]

    components = row.get("components")
    if components:
        argv += ["--components", ",".join(str(c) for c in components)]

    return argv


_CREATED_RE = re.compile(r"^Created:\s*([A-Z][A-Z0-9]*-\d+)", re.MULTILINE)


def parse_create_output(stdout: str) -> str | None:
    """Extract the new Jira key from `forecast jira create` stdout."""
    m = _CREATED_RE.search(stdout)
    return m.group(1) if m else None


def create_missing_tickets(
    yaml_path: Path,
    *,
    dry_run: bool = False,
    runner=subprocess.run,
) -> dict[str, Any]:
    """For each task row whose key is a placeholder, run `forecast jira create`
    and write the returned key back to the YAML row.

    Returns a summary dict: {created: [...], skipped: [...], errors: [...]}.
    Does NOT mutate the YAML on dry_run.

    `runner` is an injection seam for tests; pass a mock to bypass real subprocess.
    """
    ctx = detect(yaml_path)
    if not ctx.usable:
        return {"skipped_all": True, "reason": ctx.skip_reason, "created": [], "skipped": [], "errors": []}

    with yaml_io.FileLock(yaml_path):
        doc = yaml_io.load(yaml_path)
        default_epic = doc.get("epic") if isinstance(doc, dict) else None

        created: list[tuple[str, str]] = []  # (old_key, new_key)
        skipped: list[str] = []
        errors: list[tuple[str, str]] = []

        for row in doc.get("tasks", []) or []:
            key = str(row.get("key", "")).strip()
            if not is_placeholder_key(key, ctx.placeholder_prefix):
                skipped.append(key)
                continue
            if "summary" not in row or not row.get("summary"):
                errors.append((key, "row has no summary; cannot create"))
                continue
            argv = build_create_argv(ctx.forecast_bin, row, default_epic)
            if dry_run:
                created.append((key, "(dry-run, not created)"))
                continue
            try:
                proc = runner(argv, capture_output=True, text=True, timeout=60, check=False)
            except FileNotFoundError as e:
                errors.append((key, f"forecast invocation failed: {e}"))
                continue
            if proc.returncode != 0:
                errors.append((key, f"forecast exit={proc.returncode}: {proc.stderr.strip()}"))
                continue
            new_key = parse_create_output(proc.stdout)
            if not new_key:
                errors.append((key, f"could not parse Created: line from output: {proc.stdout!r}"))
                continue
            row["key"] = new_key
            created.append((key, new_key))

        if created and not dry_run:
            yaml_io.dump(doc, yaml_path)

    return {"skipped_all": False, "created": created, "skipped": skipped, "errors": errors}


# --- sync flow -------------------------------------------------------------


def sync_terminal_statuses(
    yaml_path: Path,
    *,
    dry_run: bool = False,
    runner=subprocess.run,
) -> dict[str, Any]:
    """For each task row with a terminal status (Done / Blocked / Escalated),
    transition the corresponding Jira ticket. Idempotent: only transitions
    if the YAML status maps to a known target and the row's key is real.

    Returns a summary dict.
    """
    ctx = detect(yaml_path)
    if not ctx.usable:
        return {"skipped_all": True, "reason": ctx.skip_reason, "transitioned": [], "skipped": [], "errors": []}

    # Sync is read-only on the YAML — no lock needed (we don't write back).
    doc = yaml_io.load(yaml_path)

    transitioned: list[tuple[str, str]] = []  # (key, target_status)
    skipped: list[str] = []
    errors: list[tuple[str, str]] = []

    for row in doc.get("tasks", []) or []:
        key = str(row.get("key", "")).strip()
        status = str(row.get("status", "")).strip()
        if is_placeholder_key(key, ctx.placeholder_prefix):
            skipped.append(f"{key} (not a real Jira key)")
            continue
        if status not in ctx.status_mapping:
            skipped.append(f"{key} (status {status!r} has no Jira mapping)")
            continue
        target, resolution = ctx.status_mapping[status]
        comment = _build_transition_comment(row, status)
        argv = [
            ctx.forecast_bin, "jira", "transition", key, "--to", target,
        ]
        if resolution:
            argv += ["--resolution", resolution]
        if comment:
            argv += ["--comment", comment]
        if dry_run:
            transitioned.append((key, f"{target} (dry-run)"))
            continue
        try:
            proc = runner(argv, capture_output=True, text=True, timeout=60, check=False)
        except FileNotFoundError as e:
            errors.append((key, f"forecast invocation failed: {e}"))
            continue
        if proc.returncode != 0:
            errors.append((key, f"forecast exit={proc.returncode}: {proc.stderr.strip()}"))
            continue
        transitioned.append((key, target))

    return {"skipped_all": False, "transitioned": transitioned, "skipped": skipped, "errors": errors}


def _build_transition_comment(row: dict, status: str) -> str | None:
    """Compose a short comment to attach to the Jira transition.

    Done: PR URL if present, otherwise the iteration count.
    Blocked: blocked_reason.
    Escalated: prefixed escalation note + blocked_reason.
    """
    pr = row.get("pr_url")
    blocked = row.get("blocked_reason")
    iters = row.get("iteration_count")
    score = row.get("final_quality_score")

    if status == "Done":
        parts: list[str] = []
        if pr:
            parts.append(f"PR: {pr}")
        if iters is not None:
            parts.append(f"iterations={iters}")
        if score is not None:
            parts.append(f"quality={score}/25")
        return " | ".join(parts) if parts else None

    if status == "Blocked":
        return f"Blocked by dispatcher: {blocked}" if blocked else "Blocked by dispatcher"

    if status == "Escalated":
        base = "Escalated — needs human review"
        return f"{base}: {blocked}" if blocked else base

    return None
