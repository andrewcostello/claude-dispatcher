"""Tests for the hash-chained event journal.

Covers the four acceptance criteria from DISP-8:
  * round-trip: write N events, read back, chain verifies
  * tamper: editing any byte breaks verification at that event
  * genesis: contains all four provenance fields
  * (module is standalone; no orchestrator wiring is exercised here)

Plus the chain mechanics the acceptance leans on: monotonic seq, prev_hash
linkage, canonical-serialization stability, concurrency safety, and resume.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

from claude_dispatcher import journal as J
from claude_dispatcher.journal import EventType, Journal, JournalError


# --- helpers ----------------------------------------------------------------


def _make_journal(
    tmp_path: Path,
    *,
    hostname: str = "test-host",
    subdir: str = "run",
    run_id: str | None = None,
    run_nonce: str | None = None,
) -> Journal:
    """Create a journal with a tasks.yaml and reviewer-prompts dir to hash."""
    tasks_yaml = tmp_path / "tasks.yaml"
    tasks_yaml.write_text("base_branch: main\ntasks: []\n", encoding="utf-8")

    prompts = tmp_path / "reviewer_prompts"
    if not prompts.exists():
        prompts.mkdir()
        (prompts / "claude.md").write_text("claude reviewer\n", encoding="utf-8")
        (prompts / "codex.md").write_text("codex reviewer\n", encoding="utf-8")

    return Journal.create(
        tmp_path / subdir / J.JOURNAL_FILENAME,
        tasks_yaml_path=tasks_yaml,
        reviewer_prompts_dir=prompts,
        dispatcher_version="9.9.9",
        hostname=hostname,
        run_id=run_id,
        run_nonce=run_nonce,
    )


# --- round-trip -------------------------------------------------------------


def test_round_trip_chain_verifies(tmp_path: Path):
    jr = _make_journal(tmp_path)
    jr.append(EventType.task_started, {"n": 1}, task_key="DISP-1")
    jr.append(EventType.summary_parsed, {"status": "Done"}, task_key="DISP-1")
    jr.append(EventType.run_complete, {"blocked": 0})

    events = list(J.read_events(jr.path))
    assert len(events) == 4  # genesis + 3
    assert [e.seq for e in events] == [0, 1, 2, 3]
    assert events[0].event_type == EventType.run_started.value
    assert events[1].task_key == "DISP-1"
    assert events[1].payload == {"n": 1}

    result = J.verify(jr.path)
    assert result.ok is True
    assert result.events_checked == 4
    assert result.error is None


def test_genesis_prev_hash_is_sentinel_and_links_forward(tmp_path: Path):
    jr = _make_journal(tmp_path)
    jr.append(EventType.task_started, task_key="DISP-1")
    events = list(J.read_events(jr.path))

    assert events[0].prev_hash == J.GENESIS_PREV_HASH
    # Each event's prev_hash chains to the prior event's hash.
    assert events[1].prev_hash == events[0].hash


def test_append_returns_event_with_consistent_state(tmp_path: Path):
    jr = _make_journal(tmp_path)
    ev = jr.append(EventType.notify_sent, {"channel": "slack"})
    assert ev.seq == 1
    assert jr.last_seq == 1
    assert jr.last_hash == ev.hash


def test_append_accepts_string_event_type(tmp_path: Path):
    jr = _make_journal(tmp_path)
    ev = jr.append("pr_gate", {"fired": True})
    assert ev.event_type == "pr_gate"


def test_append_rejects_unknown_event_type(tmp_path: Path):
    jr = _make_journal(tmp_path)
    with pytest.raises(ValueError):
        jr.append("not_a_real_event", {})


def test_append_rejects_non_serializable_payload(tmp_path: Path):
    jr = _make_journal(tmp_path)
    with pytest.raises(JournalError):
        jr.append(EventType.task_started, {"bad": object()})
    # The bad write must not have corrupted the chain.
    assert J.verify(jr.path).ok is True


# --- genesis provenance -----------------------------------------------------


def test_genesis_contains_all_four_provenance_fields(tmp_path: Path):
    jr = _make_journal(tmp_path, hostname="prov-host")
    genesis = next(iter(J.read_events(jr.path)))

    assert genesis.event_type == EventType.run_started.value
    assert genesis.seq == 0
    p = genesis.payload
    # 1) dispatcher version
    assert p["dispatcher_version"] == "9.9.9"
    # 2) tasks.yaml path + content hash
    assert p["tasks_yaml_path"].endswith("tasks.yaml")
    assert len(p["tasks_yaml_hash"]) == 64
    # 3) reviewer-prompts content hash
    assert len(p["reviewer_prompts_hash"]) == 64
    # 4) machine hostname
    assert p["hostname"] == "prov-host"
    # plus a uniqueness nonce so chains from identical inputs can't be spliced
    assert len(p["run_nonce"]) == 32  # secrets.token_hex(16)


def test_genesis_records_run_id_when_provided(tmp_path: Path):
    jr = _make_journal(tmp_path, run_id="2026-06-10T18-24-47Z-tasks")
    genesis = next(iter(J.read_events(jr.path)))
    assert genesis.payload["run_id"] == "2026-06-10T18-24-47Z-tasks"


def test_verify_rejects_genesis_with_wrong_event_type(tmp_path: Path):
    jr = _make_journal(tmp_path)
    obj = _read_raw(jr.path, 0)
    obj["event_type"] = "task_started"
    obj["hash"] = J.compute_hash(  # re-hash so ONLY the genesis-shape check can fail
        {k: obj[k] for k in obj if k != "hash"}
    )
    _rewrite_line(jr.path, 0, obj)
    result = J.verify(jr.path)
    assert result.ok is False
    assert result.error_seq == 0
    assert "genesis" in result.error


def test_verify_rejects_genesis_with_non_object_payload(tmp_path: Path):
    jr = _make_journal(tmp_path)
    obj = _read_raw(jr.path, 0)
    obj["payload"] = "not-an-object"
    obj["hash"] = J.compute_hash({k: obj[k] for k in obj if k != "hash"})
    _rewrite_line(jr.path, 0, obj)
    result = J.verify(jr.path)
    assert result.ok is False
    assert result.error_seq == 0


def test_verify_rejects_genesis_missing_provenance_field(tmp_path: Path):
    jr = _make_journal(tmp_path)
    obj = _read_raw(jr.path, 0)
    del obj["payload"]["reviewer_prompts_hash"]
    obj["hash"] = J.compute_hash({k: obj[k] for k in obj if k != "hash"})
    _rewrite_line(jr.path, 0, obj)
    result = J.verify(jr.path)
    assert result.ok is False
    assert result.error_seq == 0
    assert "reviewer_prompts_hash" in result.error


def test_tasks_yaml_hash_tracks_content(tmp_path: Path):
    tasks_yaml = tmp_path / "tasks.yaml"
    tasks_yaml.write_text("a: 1\n", encoding="utf-8")
    h1 = J.hash_file(tasks_yaml)
    tasks_yaml.write_text("a: 2\n", encoding="utf-8")
    h2 = J.hash_file(tasks_yaml)
    assert h1 != h2


def test_reviewer_prompts_hash_tracks_rename(tmp_path: Path):
    d = tmp_path / "prompts"
    d.mkdir()
    (d / "a.md").write_text("x", encoding="utf-8")
    h1 = J.hash_tree(d)
    (d / "a.md").rename(d / "b.md")
    h2 = J.hash_tree(d)
    assert h1 != h2  # path is part of the digest, not just content


# --- tamper detection -------------------------------------------------------


def _rewrite_line(path: Path, idx: int, new_obj: dict) -> None:
    lines = path.read_text(encoding="utf-8").splitlines()
    lines[idx] = json.dumps(new_obj, sort_keys=True, separators=(",", ":"))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _read_raw(path: Path, idx: int) -> dict:
    return json.loads(path.read_text(encoding="utf-8").splitlines()[idx])


def test_tamper_payload_breaks_verification_at_that_event(tmp_path: Path):
    jr = _make_journal(tmp_path)
    jr.append(EventType.task_started, {"amount": 100}, task_key="DISP-1")
    jr.append(EventType.task_done, {"ok": True}, task_key="DISP-1")

    obj = _read_raw(jr.path, 1)
    obj["payload"] = {"amount": 999}  # edit a covered field, leave hash as-is
    _rewrite_line(jr.path, 1, obj)

    result = J.verify(jr.path)
    assert result.ok is False
    assert result.error_seq == 1
    assert "hash mismatch" in result.error


def test_tamper_stored_hash_breaks_verification_at_that_event(tmp_path: Path):
    jr = _make_journal(tmp_path)
    jr.append(EventType.task_started, task_key="DISP-1")

    obj = _read_raw(jr.path, 1)
    bad = "f" * 64
    obj["hash"] = bad
    _rewrite_line(jr.path, 1, obj)

    result = J.verify(jr.path)
    assert result.ok is False
    # Editing the stored hash is caught at that very event (recompute mismatch).
    assert result.error_seq == 1
    assert "hash mismatch" in result.error


def test_tamper_genesis_provenance_is_detected(tmp_path: Path):
    jr = _make_journal(tmp_path)
    jr.append(EventType.task_started, task_key="DISP-1")

    obj = _read_raw(jr.path, 0)
    obj["payload"]["hostname"] = "attacker-host"
    _rewrite_line(jr.path, 0, obj)

    result = J.verify(jr.path)
    assert result.ok is False
    assert result.error_seq == 0


def test_tamper_every_byte_position_is_detected(tmp_path: Path):
    """Flip one byte at each position of a covered region — always caught."""
    jr = _make_journal(tmp_path)
    jr.append(EventType.task_started, {"k": "value"}, task_key="DISP-1")

    raw = jr.path.read_bytes()
    # Walk the whole file; any byte change that produces still-parseable JSONL
    # must fail verification. (Changes that break JSON parsing fail too, via
    # JournalError -> ok=False.)
    detected = 0
    tested = 0
    for i in range(len(raw)):
        if raw[i : i + 1] in (b"\n",):
            continue
        mutated = bytearray(raw)
        mutated[i] = mutated[i] ^ 0x01
        scratch = tmp_path / "scratch.jsonl"
        scratch.write_bytes(bytes(mutated))
        if bytes(mutated) == raw:
            continue
        tested += 1
        assert J.verify(scratch).ok is False, f"byte {i} flip went undetected"
        detected += 1
    assert tested > 0
    assert detected == tested


def test_reordering_events_breaks_chain(tmp_path: Path):
    jr = _make_journal(tmp_path)
    jr.append(EventType.task_started, {"i": 1}, task_key="A")
    jr.append(EventType.task_done, {"i": 2}, task_key="A")

    lines = jr.path.read_text(encoding="utf-8").splitlines()
    lines[1], lines[2] = lines[2], lines[1]  # swap two non-genesis events
    jr.path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    assert J.verify(jr.path).ok is False


def test_resume_continues_from_existing_tail(tmp_path: Path):
    # A truncated journal (lost tail) still verifies as a shorter valid chain —
    # that's a documented limitation, not detected here. What resume MUST do is
    # continue from the real tail with the correct next seq and prev_hash.
    jr = _make_journal(tmp_path)
    jr.append(EventType.task_started, task_key="A")
    resumed = Journal.resume(jr.path)
    assert resumed.last_seq == 1
    ev = resumed.append(EventType.run_complete, {})
    assert ev.seq == 2
    assert J.verify(jr.path).ok is True


def test_resume_refuses_empty_journal(tmp_path: Path):
    empty = tmp_path / "empty.jsonl"
    empty.write_text("", encoding="utf-8")
    with pytest.raises(JournalError):
        Journal.resume(empty)


def test_direct_append_refuses_non_genesis_first_event(tmp_path: Path):
    # Bypassing create(): the seq-0 slot must still reject a non-run_started
    # event, so the writer can never produce a chain verify() would reject.
    path = tmp_path / "j.jsonl"
    jr = Journal(path, last_seq=-1, last_hash=J.GENESIS_PREV_HASH)
    with pytest.raises(JournalError):
        jr.append(EventType.task_started, {})


def test_append_rejects_non_finite_float(tmp_path: Path):
    jr = _make_journal(tmp_path)
    for bad in (float("nan"), float("inf"), float("-inf")):
        with pytest.raises(JournalError):
            jr.append(EventType.task_started, {"x": bad})
    # Rejected before any bytes hit disk — chain stays intact.
    assert J.verify(jr.path).ok is True


def test_append_rejects_non_string_payload_keys(tmp_path: Path):
    jr = _make_journal(tmp_path)
    with pytest.raises(JournalError):
        jr.append(EventType.task_started, {1: "coerced"})
    with pytest.raises(JournalError):
        jr.append(EventType.task_started, {"nested": {2: "deep"}})
    assert J.verify(jr.path).ok is True


def test_append_deepcopies_payload_so_caller_mutation_cannot_diverge(tmp_path: Path):
    jr = _make_journal(tmp_path)
    payload = {"items": [1, 2]}
    jr.append(EventType.task_started, payload, task_key="A")
    # Mutate the caller's dict after the write — the stored event and hash must
    # reflect the value at append time, not the later mutation.
    payload["items"].append(999)
    payload["sneaky"] = True
    events = list(J.read_events(jr.path))
    assert events[1].payload == {"items": [1, 2]}
    assert J.verify(jr.path).ok is True


def test_run_nonce_prevents_cross_journal_splice(tmp_path: Path):
    # Two runs with byte-identical provenance inputs still get distinct genesis
    # hashes (random nonce), so an event from B cannot be spliced into A.
    a = _make_journal(tmp_path, subdir="A", run_nonce=None)
    b = _make_journal(tmp_path, subdir="B", run_nonce=None)
    a.append(EventType.task_started, {"i": 1}, task_key="X")
    b.append(EventType.task_started, {"i": 1}, task_key="X")

    a_genesis = next(iter(J.read_events(a.path)))
    b_genesis = next(iter(J.read_events(b.path)))
    assert a_genesis.hash != b_genesis.hash  # nonce diverges the chains

    # Splice B's seq-1 line into A in place of A's seq-1 line.
    b_line = b.path.read_text(encoding="utf-8").splitlines()[1]
    a_lines = a.path.read_text(encoding="utf-8").splitlines()
    a_lines[1] = b_line
    a.path.write_text("\n".join(a_lines) + "\n", encoding="utf-8")

    result = J.verify(a.path)
    assert result.ok is False
    assert result.error_seq == 1
    assert "prev_hash mismatch" in result.error


# --- canonical serialization ------------------------------------------------


def test_canonical_serialization_is_key_order_independent(tmp_path: Path):
    # Two payloads that differ only in insertion order hash identically.
    a = {"seq": 1, "timestamp": "t", "event_type": "x", "task_key": None,
         "payload": {"b": 2, "a": 1}, "prev_hash": "0"}
    b = {"payload": {"a": 1, "b": 2}, "prev_hash": "0", "task_key": None,
         "event_type": "x", "timestamp": "t", "seq": 1}
    assert J.compute_hash(a) == J.compute_hash(b)


def test_hash_is_stable_known_vector():
    fields = {
        "seq": 0,
        "timestamp": "2026-06-10T00:00:00+00:00",
        "event_type": "run_started",
        "task_key": None,
        "payload": {"x": 1},
        "prev_hash": J.GENESIS_PREV_HASH,
    }
    # Pin the canonical form; if serialization rules ever change this trips.
    expected = J.hash_bytes(
        (
            '{"event_type":"run_started","payload":{"x":1},"prev_hash":"'
            + J.GENESIS_PREV_HASH
            + '","seq":0,"task_key":null,"timestamp":"2026-06-10T00:00:00+00:00"}'
        ).encode("utf-8")
    )
    assert J.compute_hash(fields) == expected


# --- empty / degenerate -----------------------------------------------------


def test_empty_journal_verifies_vacuously(tmp_path: Path):
    empty = tmp_path / "empty.jsonl"
    empty.write_text("", encoding="utf-8")
    result = J.verify(empty)
    assert result.ok is True
    assert result.events_checked == 0


def test_blank_lines_are_skipped(tmp_path: Path):
    jr = _make_journal(tmp_path)
    jr.append(EventType.task_started, task_key="A")
    content = jr.path.read_text(encoding="utf-8")
    jr.path.write_text(content + "\n\n", encoding="utf-8")
    assert J.verify(jr.path).ok is True


def test_garbage_line_reports_not_ok(tmp_path: Path):
    bad = tmp_path / "bad.jsonl"
    bad.write_text("this is not json\n", encoding="utf-8")
    result = J.verify(bad)
    assert result.ok is False
    assert "invalid JSON" in result.error


def test_non_object_line_reports_not_ok(tmp_path: Path):
    bad = tmp_path / "bad.jsonl"
    bad.write_text("[1, 2, 3]\n", encoding="utf-8")  # valid JSON, not an object
    result = J.verify(bad)
    assert result.ok is False
    assert "not a JSON object" in result.error


def test_create_refuses_existing_nonempty_file(tmp_path: Path):
    jr = _make_journal(tmp_path)
    jr.append(EventType.task_started, task_key="A")
    with pytest.raises(JournalError):
        Journal.create(
            jr.path,
            tasks_yaml_path=tmp_path / "tasks.yaml",
            reviewer_prompts_dir=tmp_path / "reviewer_prompts",
        )


def test_resume_refuses_broken_chain(tmp_path: Path):
    jr = _make_journal(tmp_path)
    jr.append(EventType.task_started, task_key="A")
    obj = _read_raw(jr.path, 1)
    obj["payload"] = {"tampered": True}
    _rewrite_line(jr.path, 1, obj)
    with pytest.raises(JournalError):
        Journal.resume(jr.path)


# --- concurrency ------------------------------------------------------------


def test_concurrent_appends_stay_chained(tmp_path: Path):
    """Many threads appending through one instance produce a valid chain.

    The single-writer contract funnels through the orchestrator thread; the
    internal lock makes even this stress pattern correct rather than merely
    documented.
    """
    jr = _make_journal(tmp_path)
    n_threads = 8
    per_thread = 25
    barrier = threading.Barrier(n_threads)

    def worker(tid: int):
        barrier.wait()
        for i in range(per_thread):
            jr.append(EventType.task_started, {"tid": tid, "i": i}, task_key=f"T{tid}")

    threads = [threading.Thread(target=worker, args=(t,)) for t in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    events = list(J.read_events(jr.path))
    expected_total = 1 + n_threads * per_thread  # genesis + appends
    assert len(events) == expected_total
    assert [e.seq for e in events] == list(range(expected_total))
    assert J.verify(jr.path).ok is True
