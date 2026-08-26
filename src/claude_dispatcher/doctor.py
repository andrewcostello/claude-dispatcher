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

Endpoint agents (endpoint_agents.ENDPOINT_AGENTS) get their own section:
static readiness from the environment always, and behind `--probe-endpoints`
one minimal live messages call per keyed agent that tells auth failure and a
wrong model id apart. Without the flag the doctor never touches the network.

Exit codes: 0 ok, 1 `--check` found a required entry missing or
`--probe-endpoints` found a probed endpoint not ok, 2 environment or file
errors (e.g. an existing machine.yaml that cannot be parsed — the doctor
refuses to overwrite it so the manual section is never destroyed).
"""

from __future__ import annotations

import http.client
import importlib.metadata
import json
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from ruamel.yaml.comments import CommentedMap

from . import endpoint_agents, yaml_io


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

# Wall-clock budget for one endpoint probe. Enforced by a daemon-thread join
# in probe_endpoint, not by the urlopen timeout alone — that one is
# per-socket-operation and cannot bound a trickling body.
ENDPOINT_PROBE_TIMEOUT = 20.0
# Most response-body bytes a probe reads; a large error page is truncated.
ENDPOINT_PROBE_MAX_BODY = 64 * 1024
ANTHROPIC_VERSION_HEADER = "2023-06-01"

# Probe outcomes. "auth" and "model" are the two the ticket needs told apart
# loudly; everything else is a plain failure of the probe.
PROBE_OK = "ok"
PROBE_AUTH = "auth"
PROBE_MODEL = "model"
PROBE_UNREACHABLE = "unreachable"
PROBE_ERROR = "error"
PROBE_LABELS: dict[str, str] = {
    PROBE_OK: "probe ok",
    PROBE_AUTH: "probe AUTH FAILED",
    PROBE_MODEL: "probe MODEL ID NOT FOUND",
    PROBE_UNREACHABLE: "probe unreachable",
    PROBE_ERROR: "probe error",
}

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


# --- endpoint agents --------------------------------------------------------


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Refuse every redirect: a probe is ONE POST to the configured base_url.

    Following would re-send the provider credential to whatever host Location
    names and could turn the POST into a GET; the 3xx surfaces as an HTTPError
    and is classified as a probe error instead.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


PostMessages = Callable[..., tuple[int, str, Mapping[str, str]]]


def _post_messages(
    url: str, key: str, model: str, *, timeout: float, max_body: int,
) -> tuple[int, str, Mapping[str, str]]:
    """One minimal messages call. Returns (status, body_text, headers).

    Auth is `Authorization: Bearer` ONLY — the same header the claude CLI
    sends for ANTHROPIC_AUTH_TOKEN (build_endpoint_env) — so the probe is no
    more permissive than the spawn path it vouches for. HTTP error statuses
    are returned, not raised; transport failures propagate to the caller.
    """
    payload = json.dumps({
        "model": model,
        "max_tokens": 1,
        "messages": [{"role": "user", "content": "hi"}],
    }).encode("utf-8")
    req = urllib.request.Request(
        url, data=payload, method="POST",
        headers={
            "Authorization": f"Bearer {key}",
            "anthropic-version": ANTHROPIC_VERSION_HEADER,
            "content-type": "application/json",
            "accept": "application/json",
        },
    )
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(req, timeout=timeout) as resp:
            body = resp.read(max_body)
            return resp.status, body.decode("utf-8", "replace"), dict(resp.headers)
    except urllib.error.HTTPError as e:
        body = e.read(max_body) if e.fp is not None else b""
        return e.code, body.decode("utf-8", "replace"), dict(e.headers or {})


def _json_object(body: str) -> dict[str, Any] | None:
    try:
        payload = json.loads(body)
    except ValueError:
        return None
    return payload if isinstance(payload, dict) else None


def _snippet(body: str, limit: int = 120) -> str:
    text = " ".join(body.split())
    return text if len(text) <= limit else text[:limit] + "…"


def classify_probe_response(
    status: int, body: str, *, model: str, location: str | None = None,
) -> tuple[str, str]:
    """Map one probe response to (PROBE_* kind, detail). PURE.

    A 2xx is ok only when the body is an Anthropic message (type "message"
    with a content list); a 2xx carrying an error object is classified by
    that error, and any other 2xx body is an error — the probe must never
    vouch for an endpoint on status alone. A not-found is reported as a model
    id problem only when the error message names the model; a bare 404 more
    likely means base_url is wrong, and saying "model" would send the
    operator to the wrong fix.
    """
    payload = _json_object(body)
    err = payload.get("error") if payload else None
    err_type, err_msg = "", ""
    if isinstance(err, dict):
        err_type = str(err.get("type") or "")
        err_msg = str(err.get("message") or "")
    elif isinstance(err, str):
        err_msg = err
    has_error = err is not None or (payload is not None and payload.get("type") == "error")
    if has_error and not err_msg:
        err_msg = _snippet(body)

    names_model = bool(
        err_msg and (
            model.lower() in err_msg.lower()
            or re.search(r"\bmodel\b", err_msg, re.IGNORECASE)
        )
    )

    if status in (401, 403) or err_type in ("authentication_error", "permission_error"):
        return PROBE_AUTH, (
            f"{status} {err_type or 'rejected'}: {err_msg or _snippet(body) or 'no body'}"
            " — check the key in the env var above"
        )
    if (err_type == "not_found_error" or status in (400, 404, 422)) and names_model:
        return PROBE_MODEL, (
            f"model {model!r} rejected ({status} {err_type or 'error'}: {err_msg})"
            " — fix the registry default_model or set model: on the task"
        )
    if has_error:
        hint = " — check base_url" if status == 404 else ""
        return PROBE_ERROR, f"{status} {err_type or 'error'}: {err_msg}{hint}"
    if 300 <= status < 400:
        return PROBE_ERROR, (
            f"redirected ({status}) to {location or '?'}; refusing to follow"
            " — check base_url"
        )
    if 200 <= status < 300:
        if (
            payload is not None
            and payload.get("type") == "message"
            and isinstance(payload.get("content"), list)
        ):
            echoed = payload.get("model")
            suffix = f" (as {echoed!r})" if echoed and echoed != model else ""
            return PROBE_OK, f"model {model} answered{suffix}"
        return PROBE_ERROR, (
            f"{status} but body is not a messages response: "
            f"{_snippet(body) or 'empty'} — check base_url"
        )
    if status == 429:
        return PROBE_ERROR, f"rate limited (429): {_snippet(body) or 'no body'}"
    return PROBE_ERROR, f"{status}: {_snippet(body) or 'no body'}"


def probe_endpoint(
    name: str,
    env: Mapping[str, str],
    *,
    timeout: float = ENDPOINT_PROBE_TIMEOUT,
    post: PostMessages | None = None,
) -> tuple[str, str]:
    """Live-probe one endpoint agent with a 1-token prompt. Never raises.

    Runs the call on a daemon thread and joins for `timeout` so the doctor's
    budget holds even against a server that trickles bytes; a probe that
    outlives it is reported unreachable and abandoned. `post` defaults to the
    module's _post_messages looked up at call time, so tests that patch it
    can never fall through to the network.
    """
    post = post or _post_messages
    try:
        resolution = endpoint_agents.resolve_endpoint_agent(name, env)
    except endpoint_agents.EndpointConfigError as e:
        return PROBE_ERROR, str(e)
    url = resolution.spec.base_url.rstrip("/") + "/v1/messages"

    box: dict[str, Any] = {}

    def run() -> None:
        try:
            box["response"] = post(
                url, resolution.key, resolution.model,
                timeout=timeout, max_body=ENDPOINT_PROBE_MAX_BODY,
            )
        except BaseException as e:  # must reach the caller as data, never escape
            box["exc"] = e

    worker = threading.Thread(target=run, name=f"probe-{name}", daemon=True)
    worker.start()
    worker.join(timeout)
    if worker.is_alive():
        return PROBE_UNREACHABLE, f"no response from {url} within {timeout:g}s"
    if "exc" in box:
        exc = box["exc"]
        if isinstance(exc, (OSError, http.client.HTTPException)):
            return PROBE_UNREACHABLE, f"{url}: {exc}"
        return PROBE_ERROR, f"{url}: probe failed: {exc!r}"
    status, body, headers = box["response"]
    location = next((v for k, v in headers.items() if k.lower() == "location"), None)
    return classify_probe_response(status, body, model=resolution.model, location=location)


def _print_endpoint_section(
    env: Mapping[str, str], *, probe: bool, timeout: float = ENDPOINT_PROBE_TIMEOUT,
) -> list[str]:
    """Render the endpoint-agents rows; return the names whose probe was not ok."""
    print("endpoint agents:")
    failures: list[str] = []
    for name, ok, detail in endpoint_agents.endpoint_doctor_report(env):
        print(f"  {name:<10} {'✓' if ok else '✗'} {detail}")
        if not probe:
            continue
        if not ok:
            print(f"  {name:<10} - probe skipped: key unset")
            continue
        kind, probe_detail = probe_endpoint(name, env, timeout=timeout)
        mark = "✓" if kind == PROBE_OK else "✗"
        print(f"  {name:<10} {mark} {PROBE_LABELS[kind]}: {probe_detail}")
        if kind != PROBE_OK:
            failures.append(f"{name} ({kind})")
    return failures


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
    # The doctor's only environment read for endpoint readiness; the report
    # and probe functions stay pure/injectable.
    probe_failures = _print_endpoint_section(
        os.environ, probe=bool(getattr(args, "probe_endpoints", False)),
    )
    print(f"wrote {path}")

    rc = 0
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
            rc = 1
    if probe_failures:
        print(
            "doctor --probe-endpoints failed; endpoints not ok: "
            + ", ".join(probe_failures),
            file=sys.stderr,
        )
        rc = 1
    return rc
