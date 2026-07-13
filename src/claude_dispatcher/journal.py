"""Hash-chained, append-only event journal — one JSONL file per run.

Each run owns a single ``journal.jsonl`` (by convention next to ``run.log`` at
``<runs_dir>/<run-id>/journal.jsonl``). Every line is one JSON object: an
*event* carrying ``seq``, ``timestamp``, ``event_type``, ``task_key``,
``payload``, ``prev_hash``, and ``hash``. The ``hash`` is the SHA-256 of the
event's canonical serialization *minus the hash field itself*; ``prev_hash`` is
the previous event's ``hash`` (the genesis event uses :data:`GENESIS_PREV_HASH`).
Linking each event to the previous one makes the log tamper-evident: editing any
byte of any event either changes that event's recomputed hash (caught at that
event) or breaks the next event's ``prev_hash`` link (caught at the next event).

The first event of every journal is the *genesis* event (``run_started``,
``seq == 0``). Its payload records the provenance of the run: the dispatcher
version, the tasks.yaml path + content hash, the reviewer-prompts content hash,
the machine hostname, an optional ``run_id``, and a random ``run_nonce`` that
makes every chain unique (so events cannot be spliced between two runs that
happen to share identical genesis inputs). :func:`verify` enforces the genesis
shape — a journal whose first event is not a ``run_started`` carrying every
provenance field fails verification — because tamper-evidence must live in the
*verifier*, not merely in the writer.

Threat model — what the chain does and does NOT protect against
---------------------------------------------------------------
This is a plain (unkeyed) SHA-256 hash chain. It is tamper-*evident*, not
tamper-*proof*. It reliably detects:

  * any edit to a committed event (recomputed hash mismatches the stored hash),
  * reordering or insertion of events (``prev_hash`` / ``seq`` linkage breaks),
  * splicing an event in from a different run (distinct ``run_nonce`` in the
    genesis means prefixes never match).

It does NOT, on its own, detect a *full rewrite of the entire chain* by an actor
who has write access to the file: such an actor can recompute every hash from a
fresh genesis and produce an internally-consistent chain, and can truncate the
tail to erase recent history. Closing that gap requires an external trust anchor
the attacker cannot also rewrite — e.g. HMAC with an off-box key, emitting the
head/`run_complete` hash to an independent sink, or WORM storage. That anchoring
is intentionally out of scope for this module (it belongs with the Phase 11
evidence-bundle work); do not represent this journal as defending against a
write-capable adversary without it.

Durability note: each :meth:`Journal.append` flushes and ``fsync``s the file,
and :meth:`Journal.create` additionally ``fsync``s the parent directory so a
freshly-created journal survives a crash. A crash *mid-write* can still leave a
torn (newline-less) trailing record; recovering from that — discarding an
uncommitted fragment — is left to the operator (truncate the partial last line),
since the fragment was never durably committed.

Concurrency — single-writer assumption
--------------------------------------
The journal is written by exactly one logical writer: the orchestrator thread.
Worker threads do not touch the file; they hand events to the orchestrator,
which calls :meth:`Journal.append`. To make that contract robust rather than
merely documented, every :class:`Journal` instance also serializes its own
``append`` calls behind an internal lock, so concurrent appends through *one*
instance stay correctly chained and never interleave a partial line. What is
*not* supported is two :class:`Journal` instances (or two processes) appending
to the same file concurrently — that would race on ``seq``/``prev_hash``. Funnel
all writes for a run through a single instance.

This module performs no orchestrator wiring; that is DISP-9.
"""

from __future__ import annotations

import copy
import datetime as dt
import hashlib
import json
import os
import secrets
import socket
import threading
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Iterator

from . import __version__ as _DISPATCHER_VERSION

# The provenance keys every genesis (run_started, seq 0) payload must carry.
# verify() enforces their presence so the audit chain's anchor is self-describing
# and cannot be silently stripped by a rewrite.
GENESIS_PROVENANCE_KEYS = (
    "dispatcher_version",
    "tasks_yaml_path",
    "tasks_yaml_hash",
    "reviewer_prompts_hash",
    "hostname",
    "run_nonce",
)

# Genesis events have no predecessor; their prev_hash is this fixed sentinel
# (64 hex zeros — the width of a SHA-256 digest) so that the genesis event is
# itself covered by the chain rather than carrying an empty/None prev_hash.
GENESIS_PREV_HASH = "0" * 64

JOURNAL_FILENAME = "journal.jsonl"


class EventType(str, Enum):
    """The initial set of journal event types.

    Subclassing ``str`` makes members JSON-serializable as their value and lets
    callers pass either the enum member or its string value to
    :meth:`Journal.append`.
    """

    run_started = "run_started"
    # Run-start preflight outcome (OPS-3). Emitted once, right after the
    # journal opens — a separate event type rather than a genesis-payload
    # extension so the genesis schema / GENESIS_PROVENANCE_KEYS / verify()
    # stay untouched. See preflight.py's module docstring.
    preflight = "preflight"
    heartbeat = "heartbeat"
    task_started = "task_started"
    task_spawn_finished = "task_spawn_finished"
    summary_parsed = "summary_parsed"
    commit_retry = "commit_retry"
    # Automatic implementer fallback: a rung of the fallback chain produced no
    # usable result (spawn error / non-zero exit / missing summary — e.g. a
    # cheap cross-family agent hit its spend cap and stopped), so the next
    # agent in the chain is tried. Payload: from_agent, to_agent, reason.
    agent_fallback = "agent_fallback"
    push_verify = "push_verify"
    # Mechanical verification gate (VG-2): one event per test-command
    # execution (first run AND post-fix re-run), plus single events for the
    # skip / malformed-config outcomes. See orchestrator's
    # _verify_mechanical_and_maybe_retry.
    verification_mechanical = "verification_mechanical"
    # Seal-inversion gate (VG-3): for fix-shaped tasks, the new tests must
    # FAIL with the non-test half of the change reverted to base. One event
    # per evaluation (outcome: passed / failed / skipped / error). See
    # orchestrator's _verify_seal and seal_verify.py.
    verification_seal = "verification_seal"
    # LLM verification gate (VG-4): the independent verifier spawned AFTER the
    # mechanical gate passes and BEFORE the cross-family panel. Each verifier
    # spawn is bracketed by verification_started / verification_verdict (the
    # verdict payload carries the verdict, gap count, iteration, and verifier
    # usage/cost). verification_iterate marks one INCOMPLETE → re-spawn-the-Tasker
    # cycle; verification_skipped records the --skip-verification escape hatch.
    # See orchestrator's _verify_llm_and_maybe_iterate.
    verification_started = "verification_started"
    verification_verdict = "verification_verdict"
    verification_iterate = "verification_iterate"
    verification_skipped = "verification_skipped"
    panel_started = "panel_started"
    panel_verdict = "panel_verdict"
    panel_iterate = "panel_iterate"
    # One event per advisory (probationary, non-blocking) reviewer finding —
    # the scorecard raw material for a future promotion decision (VG-5).
    panel_advisory_finding = "panel_advisory_finding"
    # One event per AUTHORITATIVE reviewer finding (any severity), emitted even
    # when the panel approves — so the review-findings backlog captures the
    # HIGH/MEDIUM/LOW items the corroboration gate let through (not just blocks).
    panel_finding = "panel_finding"
    # Feature review loop (docs/feature-review-loop.md). Schema authored now so
    # the loop (steps 3-4, built with a human) and Forecast's `ingest` projection
    # share it. feature_review_* = the final whole-feature review; disposition_*
    # = the no-silent-drop ledger; transcript_logged = the per-task agent log +
    # haiku summary refs.
    feature_review_started = "feature_review_started"
    feature_review_verdict = "feature_review_verdict"
    disposition_recorded = "disposition_recorded"
    transcript_logged = "transcript_logged"
    task_done = "task_done"
    task_blocked = "task_blocked"
    pr_gate = "pr_gate"
    # PR-flow auto-raise (PRF-2): emitted in `pr` mode when the dispatcher
    # pushes a verified task's branch and opens its PR against the run's
    # feature branch. Payload: number, url, target (the PR base branch), and
    # base_sha (the feature branch tip the PR targets).
    pr_opened = "pr_opened"
    # Mechanical merge engine (PRF-4). The merge pass records each step of the
    # ladder-gated, topologically-ordered merge of Awaiting Review PRs into the
    # feature branch:
    #   pr_approved — the approval ladder cleared a PR for merge. Payload:
    #     number, approver (dispatcher-agent for self-approved low-risk, or
    #     external:<login>/external for a GitHub approval), risk_level, and the
    #     classifier reasons.
    #   pr_merged — the PR landed via `gh pr merge --merge`. Payload: number,
    #     merger (dispatcher-agent), approver, target (the feature branch), and
    #     feature_branch_sha (the feature-branch tip after the merge).
    #   pr_merge_failed — the merge did not land. Payload: number, kind
    #     ("conflict" for an unmergeable/conflicting PR, else "error"),
    #     needs_rebase (True only for a conflict), and detail. The row stays
    #     Awaiting Review; the merge is NOT auto-rebased (a deliberate non-goal
    #     — the supervising agent handles rebases).
    pr_approved = "pr_approved"
    pr_merged = "pr_merged"
    pr_merge_failed = "pr_merge_failed"
    integrate_result = "integrate_result"
    notify_sent = "notify_sent"
    budget_exceeded = "budget_exceeded"      # cost ceiling reached → holding the run
    run_complete = "run_complete"
    # Resume lifecycle (DISP-11 / INT-1). These appear only in a journal that
    # `dispatcher resume` has continued; a normal run never emits them.
    resume_started = "resume_started"        # links this resume to the prior genesis
    task_reset = "task_reset"                # In Progress → To Do, will re-dispatch
    task_marked_blocked = "task_marked_blocked"  # In Progress → Blocked (--strategy)


# --- hashing helpers --------------------------------------------------------


def hash_bytes(data: bytes) -> str:
    """SHA-256 hex digest of raw bytes."""
    return hashlib.sha256(data).hexdigest()


def hash_file(path: str | os.PathLike[str]) -> str:
    """SHA-256 hex digest of a single file's contents."""
    return hash_bytes(Path(path).read_bytes())


def hash_tree(root: str | os.PathLike[str]) -> str:
    """SHA-256 hex digest over a directory tree, stable across runs.

    Hashes the relative path *and* contents of every regular file under
    ``root``, in sorted-relative-path order, so the digest is deterministic and
    sensitive to renames as well as content edits. Used for the reviewer-prompts
    provenance field, which is a directory of ``.md`` files.
    """
    root_path = Path(root)
    digest = hashlib.sha256()
    for file_path in sorted(p for p in root_path.rglob("*") if p.is_file()):
        rel = file_path.relative_to(root_path).as_posix()
        digest.update(rel.encode("utf-8"))
        digest.update(b"\0")
        digest.update(file_path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def canonical_bytes(event_fields: dict[str, Any]) -> bytes:
    """Canonical serialization of an event's *hash-covered* fields.

    The mapping must NOT contain the ``hash`` key — the hash is computed over
    everything else. Serialization is deterministic: keys sorted recursively,
    no insignificant whitespace, UTF-8. ``ensure_ascii=False`` keeps non-ASCII
    payloads byte-for-byte stable rather than escaping them.

    Two guards keep the encoding injective and portable — both properties the
    hash relies on:
      * ``allow_nan=False`` — ``NaN``/``Infinity`` are not valid JSON; rejecting
        them keeps the journal parseable by any conformant reader (raises
        ``ValueError``).
      * non-``str`` mapping keys are rejected up front — ``json`` would silently
        coerce ``1`` and ``"1"`` (or ``True`` and ``1``) to the same key, so two
        logically distinct events could otherwise collide to one hash.
    """
    _reject_non_string_keys(event_fields)
    return json.dumps(
        event_fields,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _reject_non_string_keys(value: Any) -> None:
    """Recursively assert every mapping key is a ``str`` (raises TypeError)."""
    if isinstance(value, dict):
        for k, v in value.items():
            if not isinstance(k, str):
                raise TypeError(
                    f"mapping keys must be str for a stable hash, got {type(k).__name__}: {k!r}"
                )
            _reject_non_string_keys(v)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _reject_non_string_keys(item)


def compute_hash(event_fields: dict[str, Any]) -> str:
    """SHA-256 over the canonical serialization of an event minus its hash."""
    return hash_bytes(canonical_bytes(event_fields))


# --- typed records ----------------------------------------------------------


@dataclass(frozen=True)
class JournalEvent:
    """One immutable journal event, as read back from disk or before writing."""

    seq: int
    timestamp: str
    event_type: str
    task_key: str | None
    payload: dict[str, Any]
    prev_hash: str
    hash: str

    def covered_fields(self) -> dict[str, Any]:
        """The fields the ``hash`` is computed over (everything but ``hash``)."""
        return {
            "seq": self.seq,
            "timestamp": self.timestamp,
            "event_type": self.event_type,
            "task_key": self.task_key,
            "payload": self.payload,
            "prev_hash": self.prev_hash,
        }

    def recompute_hash(self) -> str:
        return compute_hash(self.covered_fields())

    def to_json_line(self) -> str:
        """Serialize for storage: covered fields + ``hash``, as one JSONL line.

        The on-disk object is written with sorted keys too, so a file
        round-trips byte-stably, but only :meth:`covered_fields` feeds the hash.
        """
        obj = self.covered_fields()
        obj["hash"] = self.hash
        return json.dumps(
            obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        )

    @classmethod
    def from_dict(cls, obj: dict[str, Any]) -> "JournalEvent":
        try:
            return cls(
                seq=obj["seq"],
                timestamp=obj["timestamp"],
                event_type=obj["event_type"],
                task_key=obj["task_key"],
                payload=obj["payload"],
                prev_hash=obj["prev_hash"],
                hash=obj["hash"],
            )
        except KeyError as e:
            raise JournalError(f"event missing required field: {e}") from e


@dataclass(frozen=True)
class VerifyResult:
    """Outcome of verifying a journal's chain integrity.

    ``ok`` is True iff every event's recomputed hash matched its stored hash,
    every ``prev_hash`` linked to the previous event, and ``seq`` ran 0..N-1.
    On failure, ``error_seq`` is the seq of the first bad event (or the line
    index for a parse/seq error) and ``error`` describes why.
    """

    ok: bool
    events_checked: int
    error: str | None = None
    error_seq: int | None = None


class JournalError(Exception):
    """Raised for unrecoverable journal read/parse problems."""


# --- writer -----------------------------------------------------------------


def _now_iso() -> str:
    """Local-zone ISO 8601 timestamp, seconds precision — matches run.log."""
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")


class Journal:
    """Append-only writer for one run's journal file.

    Construct via :meth:`create` (new run, writes the genesis event) or
    :meth:`resume` (existing run, re-reads the tail to continue the chain).
    Direct construction is internal.
    """

    def __init__(self, path: Path, *, last_seq: int, last_hash: str, clock=_now_iso):
        self._path = path
        self._last_seq = last_seq
        self._last_hash = last_hash
        self._clock = clock
        self._lock = threading.Lock()

    @property
    def path(self) -> Path:
        return self._path

    @property
    def last_seq(self) -> int:
        return self._last_seq

    @property
    def last_hash(self) -> str:
        return self._last_hash

    @classmethod
    def create(
        cls,
        path: str | os.PathLike[str],
        *,
        tasks_yaml_path: str | os.PathLike[str],
        reviewer_prompts_dir: str | os.PathLike[str],
        dispatcher_version: str = _DISPATCHER_VERSION,
        hostname: str | None = None,
        run_id: str | None = None,
        run_nonce: str | None = None,
        run_config: dict[str, Any] | None = None,
        clock=_now_iso,
    ) -> "Journal":
        """Create a new journal and write its genesis (``run_started``) event.

        The genesis payload records the run's provenance fields plus a random
        ``run_nonce`` (overridable for tests) that makes the whole chain unique,
        so events can't be spliced in from another run with identical inputs. The
        parent directory is created (and ``fsync``ed) if missing. Fails if the
        file already exists and is non-empty (use :meth:`resume` to continue an
        existing journal).

        ``run_config``, when given, is stored verbatim under the genesis
        payload's ``run_config`` key. It is the resolved ``dispatcher run``
        configuration that :func:`claude_dispatcher.resume.execute` reads to
        reconstruct an interrupted run without being told the tasks-YAML path
        again. It is an *extra* payload key — :func:`verify` only requires the
        provenance keys, so its presence or absence never affects chain
        validity.
        """
        p = Path(path)
        if p.exists() and p.stat().st_size > 0:
            raise JournalError(
                f"journal already exists and is non-empty: {p} (use resume())"
            )
        p.parent.mkdir(parents=True, exist_ok=True)

        genesis_payload = build_genesis_payload(
            tasks_yaml_path=tasks_yaml_path,
            reviewer_prompts_dir=reviewer_prompts_dir,
            dispatcher_version=dispatcher_version,
            hostname=hostname,
            run_id=run_id,
            run_nonce=run_nonce,
            run_config=run_config,
        )
        journal = cls(p, last_seq=-1, last_hash=GENESIS_PREV_HASH, clock=clock)
        journal.append(EventType.run_started, genesis_payload, task_key=None)
        _fsync_dir(p.parent)
        return journal

    @classmethod
    def resume(cls, path: str | os.PathLike[str], *, clock=_now_iso) -> "Journal":
        """Open an existing journal to append more events.

        Reads the chain to recover the last seq and hash. Verifies integrity
        first — refusing to extend a chain that is already broken would otherwise
        let a new (valid) tail mask earlier tampering.
        """
        p = Path(path)
        result = verify(p)
        if not result.ok:
            raise JournalError(
                f"cannot resume: existing chain fails verification "
                f"at seq {result.error_seq}: {result.error}"
            )
        last_seq = -1
        last_hash = GENESIS_PREV_HASH
        for event in read_events(p):
            last_seq = event.seq
            last_hash = event.hash
        if last_seq < 0:
            # An empty (or absent) journal has no genesis to chain from.
            # Appending here would write a non-genesis event at seq 0, which
            # verify() would reject — fail loudly now instead.
            raise JournalError(f"cannot resume an empty journal: {p} (use create())")
        return cls(p, last_seq=last_seq, last_hash=last_hash, clock=clock)

    def append(
        self,
        event_type: EventType | str,
        payload: dict[str, Any] | None = None,
        *,
        task_key: str | None = None,
    ) -> JournalEvent:
        """Append one event: compute its place in the chain, write, fsync.

        Thread-safe: the whole sequence (read last hash → build → write) runs
        under a lock so concurrent callers can't interleave seqs, hashes, or
        partial lines. The payload must be JSON-serializable; it is validated
        before any bytes hit disk so a bad payload can't truncate the file. The
        payload is deep-copied at entry so the exact bytes hashed are the exact
        bytes written, even if the caller mutates their dict afterward.
        """
        # Accept either an EventType member or its string value; reject unknown
        # event types (ValueError) so typos can't silently enter the chain.
        et = EventType(event_type).value
        # Snapshot the payload so a caller mutating it later cannot make the
        # stored line diverge from the bytes we hashed.
        payload = copy.deepcopy(payload) if payload is not None else {}

        with self._lock:
            seq = self._last_seq + 1
            # The seq-0 slot is the genesis: only a run_started carrying full
            # provenance may occupy it (verify() enforces the same invariant on
            # read). Guard it here so the writer can't produce a chain the
            # verifier would reject.
            if seq == 0 and et != EventType.run_started.value:
                raise JournalError(
                    f"first event must be {EventType.run_started.value!r} (genesis), got {et!r}"
                )
            covered = {
                "seq": seq,
                "timestamp": self._clock(),
                "event_type": et,
                "task_key": task_key,
                "payload": payload,
            }
            # Validate serializability up front, *before* we mutate state or
            # touch the file. TypeError = unserializable value or non-str key;
            # ValueError = non-finite float (allow_nan=False).
            try:
                canonical_bytes({**covered, "prev_hash": self._last_hash})
            except (TypeError, ValueError) as e:
                raise JournalError(f"payload is not serializable to canonical JSON: {e}") from e

            covered["prev_hash"] = self._last_hash
            event_hash = compute_hash(covered)
            event = JournalEvent(
                seq=seq,
                timestamp=covered["timestamp"],
                event_type=et,
                task_key=task_key,
                payload=payload,
                prev_hash=self._last_hash,
                hash=event_hash,
            )

            line = event.to_json_line() + "\n"
            with open(self._path, "a", encoding="utf-8") as fh:
                fh.write(line)
                fh.flush()
                os.fsync(fh.fileno())

            self._last_seq = seq
            self._last_hash = event_hash
            return event


def build_genesis_payload(
    *,
    tasks_yaml_path: str | os.PathLike[str],
    reviewer_prompts_dir: str | os.PathLike[str],
    dispatcher_version: str = _DISPATCHER_VERSION,
    hostname: str | None = None,
    run_id: str | None = None,
    run_nonce: str | None = None,
    run_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the genesis event payload: provenance fields + a uniqueness nonce.

    ``run_nonce`` defaults to a fresh 128-bit random hex token; it is what makes
    two runs with otherwise-identical provenance produce distinct chains, so an
    event cannot be spliced from one run into another. Pass an explicit value
    only in tests that need determinism.

    ``run_config``, when given, is attached under the ``run_config`` key — the
    resolved run arguments ``dispatcher resume`` replays. It is an extra,
    non-provenance key (:data:`GENESIS_PROVENANCE_KEYS` is unchanged), so it
    never affects what :func:`verify` accepts.
    """
    payload: dict[str, Any] = {
        "dispatcher_version": dispatcher_version,
        "tasks_yaml_path": str(tasks_yaml_path),
        "tasks_yaml_hash": hash_file(tasks_yaml_path),
        "reviewer_prompts_hash": hash_tree(reviewer_prompts_dir),
        "hostname": hostname if hostname is not None else socket.gethostname(),
        "run_id": run_id,
        "run_nonce": run_nonce if run_nonce is not None else secrets.token_hex(16),
    }
    if run_config is not None:
        payload["run_config"] = run_config
    return payload


def _fsync_dir(directory: Path) -> None:
    """Best-effort fsync of a directory so a new file's entry is durable.

    Not all platforms permit opening a directory for fsync (notably Windows);
    failures are swallowed because this is a durability hardening, not a
    correctness requirement.
    """
    try:
        fd = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    except (OSError, ValueError):
        pass


# --- reader / verifier ------------------------------------------------------


def read_events(path: str | os.PathLike[str]) -> Iterator[JournalEvent]:
    """Yield each event as a typed :class:`JournalEvent`, in file order.

    This does NOT verify the chain — it only parses. Use :func:`verify` for
    integrity. Blank lines are skipped; a malformed JSON line raises
    :class:`JournalError` identifying the line number.
    """
    p = Path(path)
    with p.open("r", encoding="utf-8") as fh:
        for lineno, raw in enumerate(fh, start=1):  # 1-based to match editors/sed
            stripped = raw.strip()
            if not stripped:
                continue
            try:
                obj = json.loads(stripped)
            except json.JSONDecodeError as e:
                raise JournalError(f"line {lineno}: invalid JSON: {e}") from e
            if not isinstance(obj, dict):
                raise JournalError(f"line {lineno}: event is not a JSON object")
            yield JournalEvent.from_dict(obj)


def _genesis_problem(event: JournalEvent) -> str | None:
    """Return a description if the seq-0 event is not a valid genesis, else None."""
    if event.event_type != EventType.run_started.value:
        return (
            f"genesis must be {EventType.run_started.value!r}, "
            f"got {event.event_type!r}"
        )
    if not isinstance(event.payload, dict):
        return "genesis payload must be an object"
    missing = [k for k in GENESIS_PROVENANCE_KEYS if k not in event.payload]
    if missing:
        return f"genesis payload missing provenance field(s): {', '.join(missing)}"
    return None


def verify(path: str | os.PathLike[str]) -> VerifyResult:
    """Verify a journal's chain integrity end to end.

    Checks, for every event in order:
      * the seq-0 event is a valid *genesis* — ``run_started`` carrying every
        provenance key in :data:`GENESIS_PROVENANCE_KEYS` (the anchor must be
        self-describing; a rewrite can't silently strip provenance)
      * ``seq`` is the expected monotonic index (0, 1, 2, ...)
      * the recomputed hash equals the stored ``hash`` (covered-field integrity)
      * ``prev_hash`` equals the previous event's ``hash`` (genesis links to
        :data:`GENESIS_PREV_HASH`)

    Returns a :class:`VerifyResult` rather than raising on a *broken chain* (the
    common, expected outcome of a tamper check). It still returns ``ok=False``
    with a descriptive error if the file cannot even be parsed. An empty journal
    verifies vacuously (``ok=True``, 0 events) — there is nothing to attest;
    :meth:`Journal.resume` separately refuses to extend an empty file.

    Note the threat model in the module docstring: this detects edits,
    reordering, insertion, truncation-vs-a-known-endpoint, and cross-run
    splicing, but NOT a full-chain re-forge by an actor with file write access.

    This is the ``journal verify`` helper intended for tests and for
    :meth:`Journal.resume`.
    """
    expected_seq = 0
    expected_prev = GENESIS_PREV_HASH
    checked = 0

    # read_events is a lazy generator, so a parse error surfaces here during
    # iteration (not at call time) and is reported as a verification failure.
    try:
        for event in read_events(path):
            if event.seq != expected_seq:
                return VerifyResult(
                    ok=False,
                    events_checked=checked,
                    error=(
                        f"non-monotonic seq: expected {expected_seq!r}, "
                        f"got {event.seq!r} ({type(event.seq).__name__})"
                    ),
                    error_seq=expected_seq,
                )
            if expected_seq == 0:
                genesis_err = _genesis_problem(event)
                if genesis_err is not None:
                    return VerifyResult(
                        ok=False, events_checked=checked, error=genesis_err, error_seq=0
                    )
            if event.prev_hash != expected_prev:
                return VerifyResult(
                    ok=False,
                    events_checked=checked,
                    error=(
                        f"prev_hash mismatch: expected {expected_prev}, "
                        f"got {event.prev_hash}"
                    ),
                    error_seq=event.seq,
                )
            recomputed = event.recompute_hash()
            if recomputed != event.hash:
                return VerifyResult(
                    ok=False,
                    events_checked=checked,
                    error=(
                        f"hash mismatch: stored {event.hash}, recomputed {recomputed}"
                    ),
                    error_seq=event.seq,
                )
            expected_seq += 1
            expected_prev = event.hash
            checked += 1
    except JournalError as e:
        return VerifyResult(
            ok=False, events_checked=checked, error=str(e), error_seq=expected_seq
        )

    return VerifyResult(ok=True, events_checked=checked, error=None, error_seq=None)
