"""Shared lenient readers for a run's ``journal.jsonl``.

Extracted from ``status.py`` so the report rollup and the status command share
one journal-reading implementation instead of duplicating the parsing logic.

These readers are for *observability* consumers (``dispatcher status``,
``dispatcher report``): they parse best-effort and never raise on a damaged
file. Blank lines, torn (flush-mid-write) trailing fragments, and non-object
lines are skipped, never errors. Chain integrity is deliberately out of scope —
use ``journal.verify`` for that.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any


def read_journal_events(journal_path: Path) -> list[dict[str, Any]]:
    """Parse ``journal.jsonl`` leniently into raw event dicts, in file order.

    Observability is best-effort, not chain verification: we skip blank lines
    and any line that fails to parse as a JSON object — including a torn final
    line on a live run (a flush-mid-write fragment). An unreadable file yields
    an empty list. Use ``journal.verify`` for integrity.
    """
    events: list[dict[str, Any]] = []
    try:
        text = journal_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return events
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            obj = json.loads(stripped)
        except ValueError:
            continue
        if isinstance(obj, dict):
            events.append(obj)
    return events


def journal_task_index(
    events: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Index per-task enrichment from journal events: for each task_key, the
    LAST ``task_spawn_finished`` usage block and the LAST non-error
    ``panel_verdict``. Iterating to the last event of each kind means a task
    that re-spawned (commit retry, panel iterate) shows its most recent state.

    Tasks with no relevant events do not appear, so callers render
    ``journal: null`` for them (and for every task on a pre-journal run).
    """
    spawn: dict[str, dict[str, Any]] = {}
    panel: dict[str, dict[str, Any]] = {}
    for ev in events:
        tk = ev.get("task_key")
        payload = ev.get("payload")
        if not isinstance(tk, str) or not isinstance(payload, dict):
            continue
        etype = ev.get("event_type")
        if etype == "task_spawn_finished":
            spawn[tk] = {
                "input_tokens": payload.get("input_tokens"),
                "output_tokens": payload.get("output_tokens"),
                "cache_read_input_tokens": payload.get("cache_read_input_tokens"),
                "cache_creation_input_tokens": payload.get("cache_creation_input_tokens"),
                "duration_ms": payload.get("duration_ms"),
                "num_turns": payload.get("num_turns"),
            }
        elif etype == "panel_verdict" and isinstance(payload.get("consensus"), str):
            # The error-form payload ({"error": ...}) carries no consensus —
            # skip it so a transient panel exception doesn't erase a prior
            # real verdict from the enrichment. Requiring a *string* consensus
            # (not merely the key's presence) keeps the emitted `consensus`
            # matching its schema even for a pathological null-valued payload.
            verdicts = payload.get("verdicts")
            panel[tk] = {
                "consensus": payload.get("consensus"),
                "blocking_findings": payload.get("blocking_findings"),
                "verdicts": verdicts if isinstance(verdicts, dict) else {},
            }
    index: dict[str, dict[str, Any]] = {}
    for tk in spawn.keys() | panel.keys():
        index[tk] = {"spawn": spawn.get(tk), "panel": panel.get(tk)}
    return index


def genesis_run_config(events: list[dict[str, Any]]) -> dict[str, Any]:
    """The genesis (``run_started``) event's ``run_config`` mapping, or ``{}``.

    The genesis payload stores the resolved ``dispatcher run`` arguments under
    ``run_config`` (see orchestrator._genesis_config). Returns ``{}`` when there
    is no genesis event, it carries no ``run_config``, or the journal is empty —
    so a caller can read a key with a plain ``.get`` and a safe default.
    """
    for ev in events:
        if ev.get("event_type") == "run_started":
            payload = ev.get("payload")
            if isinstance(payload, dict):
                rc = payload.get("run_config")
                return rc if isinstance(rc, dict) else {}
            return {}
    return {}


def integration_mode(events: list[dict[str, Any]]) -> str:
    """The run's integration mode (``"pr"`` | ``"branch"``) from the genesis
    ``run_config``.

    Defaults to ``"branch"`` when unknown — a pre-journal run, no genesis event,
    or a genesis that predates the PRF-1 ``integration`` key. This is the gate
    the observability commands use to decide whether to surface the pr-flow
    fields (statuses, pr_number, risk level, approver, needs_rebase): a
    branch-mode or legacy run never trips it, so its output is unchanged.
    """
    mode = genesis_run_config(events).get("integration")
    return mode if mode in ("pr", "branch") else "branch"


def parse_iso(value: Any) -> dt.datetime | None:
    """Parse an ISO-8601 string to a datetime, or None if it isn't one."""
    if not isinstance(value, str):
        return None
    try:
        return dt.datetime.fromisoformat(value.strip())
    except ValueError:
        return None
