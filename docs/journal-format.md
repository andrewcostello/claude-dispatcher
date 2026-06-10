# Journal format

The dispatcher writes one **append-only, hash-chained event journal** per run.
It is the run's tamper-evident audit trail and the supported machine-readable
feed for external observers (status tools, monitoring agents, evidence
bundling). This document specifies the format completely enough to write an
independent reader, verifier, or tailer from — no need to read the Python.

The reference implementation is `src/claude_dispatcher/journal.py` (writer,
reader, verifier) and `src/claude_dispatcher/orchestrator.py` (the single
writer that emits events across the run lifecycle).

---

## Location convention

One file per run, named `journal.jsonl`, sitting in the run directory next to
`run.log`:

```
<runs-dir>/<run-id>/journal.jsonl
```

`<runs-dir>` defaults to `docs/runs` (overridable with `--runs-dir`); `<run-id>`
is the run identifier (an ISO-8601 timestamp by default, or `--run-id`). The
filename is the module constant `JOURNAL_FILENAME`. A reader given a run-id and
a runs-dir can locate the journal with no other input.

The journal is independent of `run.log`. `run.log` is a free-text, human-facing
log (`<iso-8601>  <message>` lines); the journal is the structured, verifiable
record. They are written side by side but serve different audiences — never
parse one expecting the other's shape.

---

## File format

- **Encoding:** UTF-8.
- **Framing:** [JSON Lines](https://jsonlines.org/) — one JSON object per line,
  terminated by a single `\n`. There is no enclosing array.
- **Order:** lines appear in strictly increasing `seq` order (0, 1, 2, …),
  which is also chronological.
- **Blank lines:** a reader MUST skip empty/whitespace-only lines.
- **Line numbers:** when reporting parse errors, count lines 1-based (to match
  editors and `sed`).
- **Trailing fragment:** a crash mid-append can leave a final line with no
  newline (a *torn tail*). Such a fragment was never durably committed; a reader
  should treat a final unparseable line as absent. See [Durability](#durability).

### Event record

Every line is a JSON object with exactly these seven fields:

| Field        | Type                | Notes |
|--------------|---------------------|-------|
| `seq`        | integer             | 0-based monotonic index. The genesis event is `seq: 0`. |
| `timestamp`  | string              | ISO-8601, seconds precision, local-zone offset (e.g. `2026-06-10T12:24:53-07:00`). |
| `event_type` | string              | One of the [event types](#event-types). Treat as an **open** vocabulary — see the reader guidance below. |
| `task_key`   | string \| null      | The task this event concerns; `null` for run-scoped events (`run_started`, `run_complete`). |
| `payload`    | object              | Event-type-specific fields (tables below). May be `{}`. |
| `prev_hash`  | string (64 hex)     | The previous event's `hash`. The genesis event uses the all-zero sentinel. |
| `hash`       | string (64 hex)     | SHA-256 over the canonical serialization of the other six fields. |

On disk the object's keys are serialized **sorted** (so a file round-trips
byte-stably), but key order is not semantically significant — a reader parses
by key name, not position.

---

## Canonical serialization and hashing

The hash is what makes the journal tamper-evident, so the serialization that
feeds it must be reproduced **exactly** by an independent implementation.

### Covered fields

The `hash` covers every field of the event **except `hash` itself**:

```
covered = { seq, timestamp, event_type, task_key, payload, prev_hash }
```

### Canonical bytes

Serialize `covered` to bytes with these rules (and no others):

1. **Keys sorted** recursively (lexicographic, applied at every object depth).
2. **No insignificant whitespace** — item separator `,`, key/value separator `:`.
3. **Non-ASCII preserved** — do *not* `\u`-escape; emit UTF-8 directly
   (Python: `ensure_ascii=False`).
4. **Reject non-finite floats** — `NaN`, `Infinity`, `-Infinity` are not valid
   JSON and must raise rather than serialize (Python: `allow_nan=False`). This
   keeps the journal parseable by any conformant JSON reader.
5. **Reject non-string object keys** — every mapping key, at every depth, must
   already be a string. (JSON would otherwise coerce `1` and `"1"`, or `true`
   and `1`, to the same key, letting two logically distinct events collide to
   one hash.)
6. Encode the result as UTF-8.

The canonical form is the JSON of `covered` under rules 1–6. In Python this is:

```python
json.dumps(covered, sort_keys=True, separators=(",", ":"),
           ensure_ascii=False, allow_nan=False).encode("utf-8")
```

### Hash

```
hash = SHA-256(canonical_bytes(covered))      # lowercase hex, 64 chars
```

### On-disk line

The stored line is `covered` plus the computed `hash`, serialized with the same
sorting/whitespace rules:

```
line = json_sorted({ **covered, "hash": hash }) + "\n"
```

A verifier recomputes `SHA-256(canonical_bytes(covered))` from the parsed
fields and compares it to the stored `hash`. Because the canonical form is
deterministic, any independent implementation that follows rules 1–6 derives
the identical digest.

---

## Hash-chain construction

Each event's `prev_hash` is the `hash` of the event before it. This links the
log into a chain: editing any byte of any event either changes that event's
recomputed `hash` (caught at that event) or breaks the next event's `prev_hash`
link (caught at the next event). Inserting, deleting, or reordering events
breaks the linkage the same way.

- The genesis event (`seq: 0`) has no predecessor, so its `prev_hash` is the
  fixed sentinel **`GENESIS_PREV_HASH` = 64 ASCII zeros** (`"0000…0000"`, the
  width of a SHA-256 digest). The genesis event is therefore itself covered by
  the chain rather than carrying an empty/`null` `prev_hash`.
- For every subsequent event, `prev_hash == events[seq-1].hash`.

---

## Genesis event and provenance

The first event of every journal is the **genesis** event. It is always:

- `seq: 0`
- `event_type: "run_started"`
- `prev_hash:` the all-zero sentinel
- `task_key: null`

Its `payload` records the run's provenance — the anchor that makes the chain
self-describing. A verifier **enforces** the genesis shape: a journal whose
first event is not a `run_started` carrying every provenance key below fails
verification. Tamper-evidence must live in the verifier, not merely the writer.

### Provenance fields (genesis payload)

| Key                     | Type           | Meaning |
|-------------------------|----------------|---------|
| `dispatcher_version`    | string         | The dispatcher package version that wrote the run. |
| `tasks_yaml_path`       | string         | Path to the tasks YAML the run dispatched. |
| `tasks_yaml_hash`       | string (64 hex)| SHA-256 of the tasks YAML file's bytes at run start. |
| `reviewer_prompts_hash` | string (64 hex)| SHA-256 over the `reviewer_prompts/` directory tree (see below). |
| `hostname`              | string         | The machine that ran the dispatcher. |
| `run_nonce`             | string (32 hex)| Random 128-bit token. **Mandatory.** Makes every chain unique. |
| `run_id`                | string \| null | The run identifier; optional, may be `null`. |

`GENESIS_PROVENANCE_KEYS` is the tuple of the six **mandatory** keys
(`dispatcher_version`, `tasks_yaml_path`, `tasks_yaml_hash`,
`reviewer_prompts_hash`, `hostname`, `run_nonce`). `run_id` is allowed but not
required by the verifier.

**Why `run_nonce`:** two runs with otherwise-identical provenance (same YAML,
same version, same host) would produce identical genesis bytes and thus an
identical genesis `hash` — letting events be spliced from one run's chain into
another's. A fresh random nonce per run makes the genesis hash unique, so chain
prefixes from different runs never match and cross-run splicing is detectable.

**Directory-tree hash** (`reviewer_prompts_hash`): SHA-256 computed over every
regular file under the directory, in sorted relative-path order, hashing each
file's POSIX relative path *and* its bytes (each terminated by a `\0`
separator). This makes the digest deterministic and sensitive to renames as
well as content edits. (Note: symlinks are followed and hashed by target
content without being recorded as symlinks; empty directories do not affect the
digest.)

---

## Event types

The current vocabulary is 14 event types. They are listed below with their
payload fields. `task_key` is non-null for per-task events and `null` for the
two run-scoped events.

> **Readers: treat `event_type` as an open string.** The parser does not reject
> unknown types (only the genesis-shape and chain-integrity rules are enforced).
> New event types may be added in later versions. A correct reader matches the
> types it understands and **ignores** lines whose `event_type` it does not
> recognize, rather than failing.

### Run-scoped

**`run_started`** *(genesis, seq 0, `task_key: null`)* — payload is the
[provenance block](#provenance-fields-genesis-payload).

**`run_complete`** *(terminal, `task_key: null`)* — the last event of a
completed run; an observer that reads it knows the chain is closed.

| Payload key      | Type   | Notes |
|------------------|--------|-------|
| `done`           | int    | Count of `Done` tasks. |
| `blocked`        | int    | Count of `Blocked` tasks. |
| `escalated`      | int    | Count of `Escalated` tasks. |
| `blocked_rollup` | array  | `[{ "key": str, "reason": str }, …]` for each blocked/escalated task. |

### Per-task lifecycle

**`task_started`** — a task has been marked In Progress and submitted.

| Key       | Type        | Notes |
|-----------|-------------|-------|
| `summary` | string      | Task summary line. |
| `type`    | string      | Task type (e.g. `Task`, `Fix`). |
| `labels`  | array\<str> | Task labels. |
| `model`   | string \| null | Agent model, if pinned. |

**`task_spawn_finished`** — the Claude spawn exited (success or failure).
Emitted for every outcome, so cost is recorded even for a failed run. Every
usage field is `null` when the CLI emitted no usage block.

| Key                           | Type           |
|-------------------------------|----------------|
| `exit_code`                   | int            |
| `cost_usd`                    | number \| null |
| `input_tokens`                | int \| null    |
| `output_tokens`               | int \| null    |
| `cache_read_input_tokens`     | int \| null    |
| `cache_creation_input_tokens` | int \| null    |
| `duration_ms`                 | int \| null    |
| `num_turns`                   | int \| null    |
| `model`                       | string \| null |

**`summary_parsed`** — the Tasker's `summary.md` was parsed.

| Key                       | Type        | Notes |
|---------------------------|-------------|-------|
| `status`                  | string      | Parsed status (`Done`/`Blocked`/`Escalated`). |
| `malformed`               | bool        | True if the summary failed structural parsing. |
| `problems`                | array\<str> | Per-problem reasons when malformed (empty otherwise). |
| `iterations`              | int \| null | |
| `linter_cycles`           | int \| null | |
| `final_quality_score`     | int \| null | |
| `awaiting_human_approval` | bool        | True if parked at the PR gate. |
| `after_commit_retry`      | bool        | Present (and `true`) only on the re-parse following a commit retry. |

**`commit_retry`** — the Tasker reported Done with no commits; a commit-only
re-spawn was issued.

| Key       | Type   | Notes |
|-----------|--------|-------|
| `trigger` | string | Why the retry fired. |
| `outcome` | string | `committed` or `still_no_commits`. |

**`push_verify`** — post-Done push/PR verification ran. Emitted once per Done
task on the PR-raising workflow (skipped for auto-integrate runs, which merge
direct-to-base and never push). One event is emitted for *every* outcome,
including the no-remote skip, so the decision is reconstructable from the
journal alone. The `needs_push` outcome corresponds to the row's `needs_push:
true` field — Done landed but the branch is still unpushed (or its PR missing)
after one corrective re-spawn; status stays Done (an advisory signal, not a
block).

| Key                 | Type           | Notes |
|---------------------|----------------|-------|
| `expect_pr`         | bool           | Whether a PR was expected (true unless auto-integrate). |
| `outcome`           | string         | `pushed`, `recovered`, `needs_push`, `skipped-no-remote`, or `error`. |
| `reason`            | string         | Human-readable detail (e.g. `branch absent on origin`). |
| `retry_attempted`   | bool           | Whether the corrective push/PR-only re-spawn fired. |
| `pr_checked`        | bool           | Present when a push was confirmed: whether `gh` was actually consulted (false = PR check inconclusive). |
| `pre_retry_status`  | string         | Present when `retry_attempted`: the pre-retry verdict (`not-pushed` / `no-pr`). |
| `post_retry_status` | string         | Present on `needs_push`: the still-failing post-retry verdict. |

**`panel_started`** — a cross-family review panel run began.

| Key                    | Type | Notes |
|------------------------|------|-------|
| `iteration`            | int  | 0-based panel iteration. |
| `iterations_remaining` | int  | Iterate budget left. |

**`panel_verdict`** — the panel returned. On a framework exception the payload
is instead `{ "error": str }` (truncated).

| Key                  | Type        | Notes |
|----------------------|-------------|-------|
| `consensus`          | string      | `approve` / `block` / `incomplete`. |
| `summary`            | string      | One-line panel summary. |
| `blocking_findings`  | int         | Count of blocking findings. |
| `verdicts`           | object      | `{ "<family>": "<verdict>", … }` (e.g. `claude`, `gemini`, `codex`). |
| `blocking_locations` | array\<str> | `file:line` for blocking findings that carry a location. |

**`panel_iterate`** — a corrective Tasker spawn was issued after a panel block.

| Key                    | Type | Notes |
|------------------------|------|-------|
| `iteration`            | int  | |
| `iterations_remaining` | int  | |
| `corrective_spawn_ok`  | bool | Whether the corrective spawn succeeded. |
| `blocking_findings`    | int  | Findings fed back to the Tasker. |

**`pr_gate`** — a PR-approval gate decision was recorded.

| Key         | Type           | Notes |
|-------------|----------------|-------|
| `decision`  | string         | e.g. `deferred-unattended`, `approve`, `reject`, `skip`. |
| `mode`      | string         | Run mode (`unattended` / `supervised`). |
| `pr_title`  | string \| null | Prepared PR title. |
| `pr_branch` | string \| null | Prepared PR branch. |

Additional decision-specific keys may ride along (e.g. the resulting PR URL on
`approve`).

**`integrate_result`** — auto-integration (merge feat → base) ran.

| Key               | Type           | Notes |
|-------------------|----------------|-------|
| `status`          | string         | e.g. `merged`, `error`. |
| `merge_sha`       | string \| null | Merge commit SHA, if merged. |
| `services_built`  | array\<str>    | Services rebuilt after the merge. |
| `detail`          | string         | Free text (truncated to 500 chars). |

**`notify_sent`** — a notification was attempted (records the outcome, not just
the attempt).

| Key         | Type        | Notes |
|-------------|-------------|-------|
| `title`     | string      | Notification title. |
| `urgency`   | string      | e.g. `default`, `high`. |
| `tags`      | array\<str> | Notification tags. |
| `delivered` | bool        | Whether a channel reported delivery. |

**`task_done`** *(terminal for a task)* — exactly one terminal event fires per
task; this is the success terminal.

| Key                    | Type           |
|------------------------|----------------|
| `pr_url`               | string \| null |
| `iterations`           | int \| null    |
| `final_quality_score`  | int \| null    |
| `panel_consensus`      | string \| null |
| `auto_integrate_status`| string \| null |

**`task_blocked`** *(terminal for a task)* — the non-success terminal.

| Key      | Type   | Notes |
|----------|--------|-------|
| `reason` | string | Why the task was blocked. |

> **Terminal-event invariant:** every task emits **exactly one** of `task_done`
> or `task_blocked`. Early-return blocks (spawn failure, missing/malformed
> summary, commit-retry exhaustion) and in-worker blocks (panel block,
> auto-integrate failure, awaiting-PR-in-unattended) are disjoint code paths, so
> a reader can rely on one-terminal-per-task.

---

## Verification

`verify(path)` walks the file once and returns a result (`ok`, count of events
checked, and on failure the first bad `seq` and a description). It does **not**
raise on a broken chain — a broken chain is the expected outcome of a tamper
check — but it does report a parse failure as `ok: false`.

For each event, in file order, an independent verifier MUST check:

1. **Monotonic seq** — `event.seq` equals the expected index (0, 1, 2, …). A
   gap, repeat, or non-integer fails here.
2. **Genesis shape** (only at `seq == 0`) — `event_type` is `run_started`, the
   payload is an object, and every key in `GENESIS_PROVENANCE_KEYS` is present.
3. **Chain linkage** — `event.prev_hash` equals the expected predecessor hash:
   the all-zero sentinel for the genesis, otherwise the previous event's `hash`.
4. **Hash integrity** — `SHA-256(canonical_bytes(covered_fields))` equals the
   stored `hash`.

If all events pass, the journal is intact. An **empty** journal verifies
vacuously (`ok: true`, 0 events) — there is nothing to attest.

A writer resuming an existing journal verifies it first and refuses to extend a
chain that already fails verification (otherwise a fresh valid tail could mask
earlier tampering).

---

## Single-writer rule

The journal is written by **exactly one logical writer**: the orchestrator
thread. Worker threads never touch the file — they hand events to the
orchestrator, which appends them. To make the contract robust rather than
merely documented, each writer instance also serializes its own `append` calls
behind an internal lock, so concurrent appends through *one* instance stay
correctly chained and never interleave a partial line (important when
`--max-parallel > 1`).

What is **not** supported is two writer instances — or two processes —
appending to the same file concurrently; they would race on `seq`/`prev_hash`
and corrupt the chain. **Funnel all writes for a run through a single
instance.** Readers, verifiers, and tailers are unaffected: they open the file
read-only and never contend with the writer.

---

## Durability

- Each append **flushes and `fsync`s** the file before returning, so a
  committed event survives a crash.
- Creating a journal additionally `fsync`s the parent directory so a
  freshly-created file's directory entry is durable.
- The payload is validated as canonical-serializable *before* any bytes hit
  disk, so a bad payload can never truncate the file mid-line.
- The payload is deep-copied at append time, so the exact bytes hashed are the
  exact bytes written even if the caller mutates its dict afterward.
- **Torn tail:** a crash *during* a write can still leave a final line without
  its newline. That fragment was never durably committed; recovery is to
  truncate the partial last line (a reader treats an unparseable final line as
  absent). Automatic torn-tail repair is out of scope for this module.

---

## Threat model

This is a plain (unkeyed) SHA-256 hash chain. It is tamper-**evident**, not
tamper-**proof**. It reliably detects:

- any **edit** to a committed event (recomputed hash mismatches the stored one),
- **reordering or insertion** of events (`prev_hash` / `seq` linkage breaks),
- **splicing** an event in from a different run (a distinct `run_nonce` in the
  genesis means chain prefixes from different runs never match),
- **truncation measured against a known endpoint** (a recorded head/`run_complete`
  hash no longer matches).

It does **not**, on its own, detect a **full rewrite of the entire chain** by an
actor with write access to the file: such an actor can recompute every hash from
a fresh genesis and produce an internally consistent chain, and can truncate the
tail to erase recent history. Closing that gap requires an external trust anchor
the attacker cannot also rewrite — e.g. HMAC with an off-box key, emitting the
head/`run_complete` hash to an independent sink, or WORM storage. That anchoring
is intentionally out of scope here (it belongs with the Phase 11 evidence-bundle
work). **Do not represent this journal as defending against a write-capable
adversary without that anchor.**

---

## Writing an independent reader

A minimal reader/verifier needs only this loop:

1. Open the file as UTF-8. Iterate lines, 1-based.
2. Skip blank/whitespace-only lines. Treat a final unparseable line as a torn
   tail (absent), not an error.
3. Parse each line as a JSON object. A non-object or invalid JSON line is a
   hard parse error (report the line number).
4. Read the seven fields by name into a record.
5. To **verify**, maintain `expected_seq` (starting 0) and `expected_prev`
   (starting the all-zero sentinel). For each event apply the four checks in
   [Verification](#verification), then set `expected_prev = event.hash` and
   increment `expected_seq`.
6. To **consume** (not verify), dispatch on `event_type`, reading payload fields
   per the [tables above](#event-types), and **ignore** unknown types.

### Illustrative records

Hashes below are abbreviated (`…`) for readability; real values are 64 hex
chars. Keys are shown sorted, as written on disk.

```jsonl
{"event_type":"run_started","hash":"a17f…","payload":{"dispatcher_version":"0.1.0","hostname":"build-01","reviewer_prompts_hash":"9c0b…","run_id":"2026-06-10T18-24-47Z-tasks","run_nonce":"4e9d2c1b…","tasks_yaml_hash":"71aa…","tasks_yaml_path":"features/phase0-1/tasks.yaml"},"prev_hash":"0000000000000000000000000000000000000000000000000000000000000000","seq":0,"task_key":null,"timestamp":"2026-06-10T11:24:47-07:00"}
{"event_type":"task_started","hash":"b93c…","payload":{"labels":["size:S","area:docs"],"model":"claude-opus-4-8[1m]","summary":"Docs: journal format spec","type":"Task"},"prev_hash":"a17f…","seq":1,"task_key":"DISP-12","timestamp":"2026-06-10T11:24:47-07:00"}
{"event_type":"run_complete","hash":"f04e…","payload":{"blocked":0,"blocked_rollup":[],"done":12,"escalated":0},"prev_hash":"…","seq":42,"task_key":null,"timestamp":"2026-06-10T12:40:11-07:00"}
```

---

## Tailing the journal

The journal is the supported feed for live monitoring. Because it is
append-only JSONL with `fsync` per event, a tailer can follow it safely:

```bash
# Follow a live run's events as they land
tail -F docs/runs/<run-id>/journal.jsonl | while read -r line; do
    echo "$line" | jq -c '{seq, event_type, task_key}'
done
```

A consumer should parse each line independently and ignore unknown
`event_type`s (forward compatibility). For point-in-time run state rather than
an event stream, use `dispatcher status --json` (see the README's *Observing a
run* section); the two together — `status --json` for state, journal tailing for
the event feed — are the supported integration surface for external tools.
