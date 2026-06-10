"""Append-only JSONL event journal, one file per run.

The journal is the run's authoritative timeline. The orchestrator writes a
`run_started` (genesis) event capturing the run's full configuration, then a
stream of lifecycle events (`task_dispatched`, `task_finished`, `heartbeat`,
`run_complete`). `dispatcher resume` reconstructs an interrupted run from this
journal: the genesis event supplies the config (so resume needn't be told the
tasks-YAML path again), and the age of the most recent event is the liveness
signal — a journal whose last event is recent suggests the run is still active,
so resume refuses unless `--force`.

Design notes:
  - One JSON object per line. Each event carries an ISO-8601 UTC `ts` and an
    `event` type; the rest of the payload is event-specific.
  - Appends are serialized with a process-local lock and an open-write-close
    per call, so the heartbeat thread and the main dispatch thread can both
    append without interleaving partial lines.
  - Reads tolerate a torn final line (a crash mid-write): a line that fails to
    parse is skipped, not fatal. The journal is forensic, not transactional.
"""

from __future__ import annotations

import datetime as dt
import json
import threading
from pathlib import Path
from typing import Any


# Event type constants. Kept as plain strings so external tailers can match
# without importing this module.
RUN_STARTED = "run_started"        # genesis — carries the run config
HEARTBEAT = "heartbeat"            # periodic liveness ping while the loop runs
TASK_DISPATCHED = "task_dispatched"
TASK_FINISHED = "task_finished"
TASK_RESET = "task_reset"          # resume reset an In Progress row to To Do
TASK_MARKED_BLOCKED = "task_marked_blocked"  # resume --strategy mark-blocked
RESUME_STARTED = "resume_started"  # a resume picked this run up; links genesis
RUN_COMPLETE = "run_complete"


def _utc_now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


class Journal:
    """Append-only JSONL journal for a single run.

    Construct with the path to the journal file (conventionally
    `<run-dir>/journal.jsonl`). The file is created lazily on first append.
    """

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._lock = threading.Lock()

    # --- writing -----------------------------------------------------------

    def append(self, event: str, **payload: Any) -> dict:
        """Append one event. Returns the written record (including `ts`).

        `ts` is stamped here unless the caller supplied one (resume may want
        to preserve an original timestamp). Serialized across threads.
        """
        record: dict[str, Any] = {"ts": payload.pop("ts", _utc_now_iso()),
                                  "event": event}
        record.update(payload)
        line = json.dumps(record, ensure_ascii=False, sort_keys=False)
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        return record

    # --- reading -----------------------------------------------------------

    def exists(self) -> bool:
        return self.path.exists()

    def read(self) -> list[dict]:
        """Return all parseable events in order. A torn final line (crash
        mid-write) is skipped rather than raising."""
        if not self.path.exists():
            return []
        events: list[dict] = []
        with self.path.open("r", encoding="utf-8") as fh:
            for raw in fh:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    obj = json.loads(raw)
                except (json.JSONDecodeError, ValueError):
                    # Tolerate a partially-written trailing line.
                    continue
                if isinstance(obj, dict):
                    events.append(obj)
        return events

    def genesis(self) -> dict | None:
        """The first `run_started` event, or None if absent."""
        for ev in self.read():
            if ev.get("event") == RUN_STARTED:
                return ev
        return None

    def last_event_time(self) -> dt.datetime | None:
        """Timestamp of the most recent event with a parseable `ts`, or None."""
        latest: dt.datetime | None = None
        for ev in self.read():
            ts = ev.get("ts")
            if not ts:
                continue
            try:
                parsed = dt.datetime.fromisoformat(ts)
            except (TypeError, ValueError):
                continue
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=dt.timezone.utc)
            if latest is None or parsed > latest:
                latest = parsed
        return latest

    def seconds_since_last_event(self, now: dt.datetime | None = None) -> float | None:
        """Age in seconds of the most recent event, or None if the journal is
        empty / has no timestamped events. Used as the liveness signal."""
        last = self.last_event_time()
        if last is None:
            return None
        now = now or dt.datetime.now(dt.timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=dt.timezone.utc)
        return (now - last).total_seconds()
