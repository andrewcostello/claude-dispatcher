"""`dispatcher doctor` — probe the machine and write a profile to machine.yaml.

Machine knowledge (which agent CLIs exist, their versions, how the dispatcher
itself is installed) was previously discovered lazily mid-run. This module
makes it explicit: it probes once, up front, and writes a plain, predictable
YAML profile that later phases (preflight, provider registry, done-metadata)
can read without re-probing.

The profile lives at $XDG_CONFIG_HOME/claude-dispatcher/machine.yaml
(default ~/.config/claude-dispatcher/machine.yaml). The file is shared with
the user: everything under the top-level `manual:` key is user-owned and
never touched by the doctor, and re-probes mutate the loaded ruamel document
in place so file comments survive — the same comment-preserving contract
yaml_io gives the tasks YAML.

Exit codes: 0 ok, 1 `--check` found a required entry missing, 2 environment
or file errors (e.g. an existing machine.yaml that cannot be parsed — the
doctor refuses to overwrite it so the manual section is never destroyed).
"""

from __future__ import annotations

import importlib.metadata
import json
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ruamel.yaml.comments import CommentedMap

from . import yaml_io


SCHEMA_VERSION = 1

# How long a `<bin> --version` probe may run before being killed. A constant
# (passed down as an argument) so tests can shrink it instead of waiting 10s
# on a deliberately-hanging stub.
VERSION_PROBE_TIMEOUT = 10.0

# Static capability table: which stats/usage probe is known for each agent
# CLI. This is a stop-gap pending the Phase 6 provider registry, which will
# own per-provider capabilities properly. Labels:
#   "json-output"   — usage/cost can be parsed from the CLI's --print JSON
#                     output (how spawn.py reads Claude usage today).
#   "stats-command" — the CLI exposes a dedicated stats/usage subcommand.
#   None            — no stats probe known for this CLI yet.
# In the written profile, stats_probe is only emitted for CLIs that are
# actually present; absent CLIs get null like every other probed field.
AGENT_STATS_PROBES: dict[str, str | None] = {
    "claude": "json-output",
    "agy": "unmeasurable",  # agy emits no machine-readable usage/cost metadata in headless mode
    "codex": "stats-command",
    "grok": "json-output",  # spawn.parse_grok_usage from --output-format json
    "opencode": None,
    "qwen": None,
}

AGENT_BINS: tuple[str, ...] = tuple(AGENT_STATS_PROBES)
TOOL_BINS: tuple[str, ...] = ("git", "gh", "docker", "sqlc", "buf")

# (section, name) pairs that `--check` requires. Everything else is soft:
# reported in the table, never affecting the exit code.
REQUIRED: tuple[tuple[str, str], ...] = (("agents", "claude"), ("tools", "git"))

# Top-level keys the doctor owns and replaces on every probe. `manual:` and
# any other unrecognized top-level key are deliberately NOT in this list.
PROBED_KEYS: tuple[str, ...] = (
    "schema_version", "probed_at", "host", "dispatcher", "agents", "tools",
)

# First semver-ish token in a version line: "2.43.0", "0.1", "1.2.3-rc1".
# Tail is limited to semver-ish characters (not \S*) so adjacent punctuation
# isn't swallowed — e.g. "Docker version 29.1.3, build ..." must yield
# "29.1.3", not "29.1.3,".
_VERSION_RE = re.compile(r"\d+\.\d+(?:\.\d+)?[0-9A-Za-z.\-+]*")


# --- probing ----------------------------------------------------------------


def probe_binary(name: str, *, timeout: float = VERSION_PROBE_TIMEOUT) -> dict[str, Any]:
    """Probe one binary: presence, path, and `--version` output.

    Never raises on a misbehaving binary — a missing, crashing, hanging, or
    gibberish-printing tool degrades to version=None with a `version_error`
    note, because the doctor must always produce a complete profile.
    """
    path = shutil.which(name)
    info: dict[str, Any] = {
        "present": path is not None,
        "path": path,
        "version": None,
        "version_raw": None,
    }
    if path is None:
        return info

    try:
        proc = subprocess.run(
            [path, "--version"],
            capture_output=True, text=True, timeout=timeout, check=False,
        )
    except subprocess.TimeoutExpired:
        info["version_error"] = f"--version timed out after {timeout:g}s"
        return info
    except OSError as e:
        info["version_error"] = f"--version could not run: {e}"
        return info

    # Some CLIs print their version to stderr — check stdout first, then stderr.
    out = proc.stdout.strip() or proc.stderr.strip()
    first_line = out.splitlines()[0].strip() if out else None
    info["version_raw"] = first_line
    if proc.returncode != 0:
        info["version_error"] = f"--version exited {proc.returncode}"
        return info
    m = _VERSION_RE.search(first_line or "")
    if m:
        info["version"] = m.group(0)
    else:
        info["version_error"] = "no version token in --version output"
    return info


def _install_mode() -> str:
    """Heuristic for how the dispatcher itself is installed.

    In order: "pipx" if "pipx" is a path component of sys.prefix; else
    "editable" if the installed distribution's direct_url.json says
    dir_info.editable (PEP 660 / pip install -e); else "venv" if running
    inside a virtualenv (sys.prefix != sys.base_prefix); else "system".
    Each step is wrapped defensively — any unexpected failure yields
    "unknown" rather than crashing the probe.
    """
    try:
        if "pipx" in Path(sys.prefix).parts:
            return "pipx"
    except Exception:
        return "unknown"
    try:
        dist = importlib.metadata.distribution("claude-dispatcher")
        direct_url = dist.read_text("direct_url.json")
        if direct_url:
            dir_info = json.loads(direct_url).get("dir_info", {})
            if dir_info.get("editable"):
                return "editable"
    except importlib.metadata.PackageNotFoundError:
        pass  # not installed at all (e.g. PYTHONPATH run) — fall through
    except Exception:
        return "unknown"
    try:
        return "venv" if sys.prefix != sys.base_prefix else "system"
    except Exception:
        return "unknown"


def _dispatcher_version() -> str:
    try:
        return importlib.metadata.version("claude-dispatcher")
    except importlib.metadata.PackageNotFoundError:
        return "unknown"


def build_profile(*, timeout: float = VERSION_PROBE_TIMEOUT) -> dict[str, Any]:
    """Run all probes and return the profile's probed keys as plain data."""
    agents: dict[str, Any] = {}
    for name in AGENT_BINS:
        entry = probe_binary(name, timeout=timeout)
        entry["stats_probe"] = AGENT_STATS_PROBES[name] if entry["present"] else None
        agents[name] = entry

    tools = {name: probe_binary(name, timeout=timeout) for name in TOOL_BINS}

    return {
        "schema_version": SCHEMA_VERSION,
        "probed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "host": {
            "hostname": socket.gethostname(),
            "platform": platform.platform(),
        },
        "dispatcher": {
            "version": _dispatcher_version(),
            "install_mode": _install_mode(),
            "python_version": platform.python_version(),
        },
        "agents": agents,
        "tools": tools,
    }


# --- file I/O ---------------------------------------------------------------


def default_config_dir() -> Path:
    """$XDG_CONFIG_HOME/claude-dispatcher, defaulting to ~/.config."""
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / "claude-dispatcher"


def _fresh_document(profile: dict[str, Any]) -> CommentedMap:
    """Build a brand-new machine.yaml document with explanatory comments."""
    doc = CommentedMap()
    for key in PROBED_KEYS:
        doc[key] = profile[key]
    doc["manual"] = None
    doc.yaml_set_start_comment(
        "Machine profile written by `dispatcher doctor`.\n"
        "All keys except `manual:` are regenerated on every probe.\n"
        "Comments and anything under `manual:` are preserved across re-probes.\n"
    )
    doc.yaml_set_comment_before_after_key(
        "manual",
        before="user-owned; doctor never touches anything under this key",
    )
    return doc


def write_profile(path: Path, profile: dict[str, Any]) -> int:
    """Write (or refresh) machine.yaml at `path`. Returns an exit code.

    If the file exists, the loaded ruamel document is mutated in place —
    only the probed top-level keys are replaced, so `manual:`, any other
    unrecognized top-level keys, and all file comments survive. Building a
    fresh dict instead would silently drop the comments.
    """
    if path.exists():
        try:
            doc = yaml_io.load(path)
        except Exception as e:
            print(
                f"error: existing {path} could not be parsed ({e}); "
                "refusing to overwrite it. Fix or delete the file and re-run.",
                file=sys.stderr,
            )
            return 2
        if not isinstance(doc, dict):
            print(
                f"error: existing {path} is not a YAML mapping; "
                "refusing to overwrite it. Fix or delete the file and re-run.",
                file=sys.stderr,
            )
            return 2
        for key in PROBED_KEYS:
            doc[key] = profile[key]
    else:
        doc = _fresh_document(profile)

    path.parent.mkdir(parents=True, exist_ok=True)
    yaml_io.dump(doc, path)
    return 0


# --- CLI --------------------------------------------------------------------


def _print_table(profile: dict[str, Any]) -> None:
    for section in ("agents", "tools"):
        print(f"{section}:")
        for name, entry in profile[section].items():
            if entry["present"]:
                version = entry["version"] or entry.get("version_error", "version unknown")
                print(f"  {name:<10} ✓ {version}")
            else:
                print(f"  {name:<10} ✗ not found")


def _missing_required(profile: dict[str, Any]) -> list[str]:
    return [
        name
        for section, name in REQUIRED
        if not profile[section][name]["present"]
    ]


def execute(args) -> int:
    """Entry point for `dispatcher doctor`."""
    config_dir = (
        Path(args.config_dir) if getattr(args, "config_dir", None)
        else default_config_dir()
    )
    path = config_dir / "machine.yaml"

    profile = build_profile(timeout=VERSION_PROBE_TIMEOUT)
    rc = write_profile(path, profile)
    if rc != 0:
        return rc

    _print_table(profile)
    print(f"wrote {path}")

    if getattr(args, "check", False):
        missing = _missing_required(profile)
        if missing:
            print(
                "doctor --check failed; required entries missing: "
                + ", ".join(missing),
                file=sys.stderr,
            )
            print(
                "(all other entries are soft and never affect the exit code)",
                file=sys.stderr,
            )
            return 1
    return 0
