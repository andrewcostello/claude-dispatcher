"""`dispatcher watch` — stream journal events for a live or finished run."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

# Events that matter to an operator at a glance.
_INTERESTING = frozenset({
    "run_started", "preflight", "task_started", "task_spawn_finished",
    "agent_fallback", "summary_parsed", "verification_mechanical",
    "verification_verdict", "verification_skipped", "panel_verdict",
    "panel_iterate", "task_done", "task_blocked", "budget_exceeded",
    "run_complete", "design_completed", "design_failed",
})

# Stop following if the journal stops growing for this long (run died
# without run_complete).
_NO_GROWTH_TIMEOUT_S = 600.0
_MIN_POLL_S = 0.05


def watch_run(
    run_id: str,
    *,
    runs_dir: Path,
    poll_seconds: float = 1.0,
    follow: bool = True,
) -> int:
    """Print compact journal lines. Exit 0 if run_complete with no blocks,
    1 if any task_blocked seen after start, 2 if journal missing."""
    journal = Path(runs_dir) / run_id / "journal.jsonl"
    if not journal.exists():
        print(f"error: journal not found: {journal}", file=sys.stderr)
        return 2

    poll = max(float(poll_seconds), _MIN_POLL_S)
    offset = 0
    saw_block = False
    finished = False
    last_growth = time.monotonic()
    last_size = 0
    try:
        while True:
            try:
                data = journal.read_bytes()
            except OSError as e:
                print(f"error: reading journal: {e}", file=sys.stderr)
                return 2
            if len(data) != last_size:
                last_size = len(data)
                last_growth = time.monotonic()
            if len(data) > offset:
                chunk = data[offset:]
                # Byte-level put-back BEFORE decode so multi-byte UTF-8 that
                # straddles a poll boundary cannot drift offset via U+FFFD.
                last_nl = chunk.rfind(b"\n")
                if last_nl < 0:
                    # No complete line yet — wait for more bytes when following.
                    if follow:
                        time.sleep(poll)
                        if time.monotonic() - last_growth > _NO_GROWTH_TIMEOUT_S:
                            print(
                                "warning: journal idle without run_complete; "
                                "stopping follow",
                                file=sys.stderr,
                            )
                            break
                        continue
                    # --no-follow: drop torn tail rather than parse garbage.
                    break
                complete = chunk[: last_nl + 1]
                offset += len(complete)
                text = complete.decode("utf-8", errors="replace")
                for line in text.splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        ev = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    et = ev.get("event_type") or ev.get("type")
                    if et not in _INTERESTING:
                        continue
                    key = ev.get("task_key") or ""
                    payload = ev.get("payload") or {}
                    extra = ""
                    if et == "task_blocked":
                        saw_block = True
                        extra = f" reason={payload.get('reason', '')[:80]}"
                    elif et == "agent_fallback":
                        extra = (
                            f" {payload.get('from_agent')}→{payload.get('to_agent')}"
                            f" ({payload.get('reason', '')[:40]})"
                        )
                    elif et == "panel_verdict":
                        extra = f" consensus={payload.get('consensus')}"
                    elif et == "run_complete":
                        finished = True
                    print(f"{et:28} {key:16}{extra}", flush=True)
            if finished or not follow:
                break
            if time.monotonic() - last_growth > _NO_GROWTH_TIMEOUT_S:
                print(
                    "warning: journal idle without run_complete; stopping follow",
                    file=sys.stderr,
                )
                break
            time.sleep(poll)
    except KeyboardInterrupt:
        print("\nwatch interrupted", file=sys.stderr)
        return 1 if saw_block else 0
    return 1 if saw_block else 0
