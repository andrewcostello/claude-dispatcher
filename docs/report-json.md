# `dispatcher report --json` schema

`dispatcher report <run-id> --json` emits **one JSON document** to stdout (no
trailing prose), mirroring the human-readable dashboard. It is the
machine-readable superset of the report: the per-run cost rollup plus the
original quality data. All values are JSON-serializable; timestamps are
ISO-8601 strings.

## Source selection

The rollup prefers the run's journal (`<run-dir>/journal.jsonl`, see
[journal-format.md](journal-format.md)) because a task can spawn multiple
times (commit retry, push retry, panel iterate) and the YAML row records only
the **last** spawn's usage. Real spend is the **sum over all of a task's
`task_spawn_finished` events**, so journal-sourced totals can legitimately
exceed the YAML totals — that is the point of the journal source.

| Condition | `source` | `source_label` |
|-----------|----------|----------------|
| `journal.jsonl` exists and yields parseable events | `"journal"` | `"journal"` |
| No `journal.jsonl` (pre-journal run) | `"yaml"` | `"yaml (pre-journal run — per-task usage reflects last spawn only)"` |
| `journal.jsonl` exists but yields zero parseable events | `"yaml"` | `"yaml (journal unreadable — per-task usage reflects last spawn only)"` |

The label appears in both the JSON (`source_label`) and the table rendering
(the `Source:` header line and the rollup section headings).

The journal is parsed **leniently** (shared reader in
`claude_dispatcher.journal_read`): blank lines and torn/unparseable lines —
including a flush-mid-write fragment at the tail of a live run — are skipped,
never errors. Chain verification is `journal verify`'s job, not the report's.

## Null vs. zero

A spawn whose usage fields are null (the agent CLI emitted no usage block) is
**excluded from the sums and counted as unmeasured** — null is never silently
treated as 0. A usage total is `null` (not `0`) when *nothing* contributed to
it.

## Top level

| Field | Type | Meaning |
|-------|------|---------|
| `run_id` | string | The run being reported on. |
| `run_dir` | string | Absolute path to the run directory. |
| `tasks_yaml` | string | Absolute path to the resolved tasks YAML. |
| `source` | string | `"journal"` or `"yaml"` (see Source selection). |
| `source_label` | string | The full human-facing label, including the fallback annotation. |
| `summary_file_count` | int | Number of `summary.md` files found under the run dir. |
| `status_counts` | object | `{<status>: int}` over **every** task in the YAML (not just this run), 0-filled for all five statuses (`To Do`, `In Progress`, `Done`, `Blocked`, `Escalated`). |
| `rollup` | object | The per-run cost/usage rollup (below). |
| `quality` | object | The original quality-dashboard data (below). |

## `rollup`

| Field | Type | Meaning |
|-------|------|---------|
| `wall_clock` | object \| null | **Null in YAML mode** (wall clock is journal-only). |
| `wall_clock.started_at` | string \| null | Timestamp of the `run_started` (genesis) event. |
| `wall_clock.ended_at` | string \| null | Timestamp of `run_complete`; for a run with no `run_complete` (in flight), the **last event's** timestamp. |
| `wall_clock.seconds` | number \| null | `ended_at − started_at`, 3 dp. |
| `wall_clock.in_flight` | bool | True when `ended_at` came from the last event rather than `run_complete`. |
| `totals` | object | Run-level totals (below). |
| `tasks` | array | Per-task rollup rows (below), key-sorted. |
| `by_model` | array | Per-model aggregate (below), model-sorted. |

### `rollup.totals`

| Field | Type | Meaning |
|-------|------|---------|
| `tasks_by_status` | object | `{<status>: int}` over the rollup's task rows: terminal status from `task_done`/`task_blocked` events, cross-checked with the YAML for tasks with no terminal event. Only observed statuses appear. |
| `cost_usd` | number \| null | Journal mode: sum over **all** `task_spawn_finished` events. YAML mode: sum of row `cost_usd` (last spawn only). Null when nothing was measured. |
| `input_tokens` | int \| null | Same summing rules. |
| `output_tokens` | int \| null | Same summing rules. |
| `cache_read_input_tokens` | int \| null | Same summing rules. |
| `cache_creation_input_tokens` | int \| null | Same summing rules. |
| `duration_ms` | int \| null | Sum of spawn durations (journal) / row durations (YAML). |
| `tasks_billed` | int | Tasks whose rollup row carries a non-null cost. |
| `spawn_count` | int \| null | Total `task_spawn_finished` events. **Null in YAML mode** (spawn counts are journal-only). |
| `unmeasured_spawns` | int \| null | Spawns where any of `cost_usd` / `input_tokens` / `output_tokens` / `cache_read_input_tokens` / `cache_creation_input_tokens` was null (a null `duration_ms` alone does not make a spawn unmeasured). **Null in YAML mode.** |

### `rollup.tasks[]`

One row per task: in journal mode, the union of tasks with journal events and
YAML rows stamped with this run's id (so a task present in the journal but
missing from the YAML is still rendered); in YAML mode, the run's YAML rows.

| Field | Type | Journal mode | YAML mode |
|-------|------|--------------|-----------|
| `key` | string | Task key. | Task key. |
| `status` | string | `task_done` → `Done`, `task_blocked` → `Blocked`; otherwise the YAML row's status; otherwise `In Progress`. | YAML row status. |
| `model` | string \| null | Model of the **last** spawn. | Row `model`. |
| `agent` | string \| null | `agent` key of the terminal event payload; null when absent (pre-agent-metadata journals). | Row `agent`, if stamped. |
| `cost_usd` | number \| null | **Sum across all of the task's spawns.** | Row value (last spawn only). |
| `input_tokens` / `output_tokens` / `cache_read_input_tokens` / `cache_creation_input_tokens` / `duration_ms` | int \| null | Sums across spawns (null fields excluded). | Row values. |
| `spawn_count` | int \| null | Number of `task_spawn_finished` events (retries included). | **Null** (journal-only). |
| `unmeasured_spawns` | int \| null | Spawns with null usage (see totals). | **Null** (journal-only). |
| `iterations` | int \| null | `task_done.iterations`, falling back to the last `summary_parsed.iterations`. | Row `iteration_count`. |
| `panel_verdict` | string \| null | Last **non-error** `panel_verdict.consensus` (error-form `{"error": ...}` payloads are ignored), falling back to `task_done.panel_consensus`. | Row `panel_consensus`. |
| `needs_push` | bool \| null | `task_done.needs_push`; **null when the key is absent** (pre-agent-metadata journals) — absence is not false. | Row `needs_push` when present, else null. |
| `in_yaml` | bool | False for a task seen in the journal but missing from the YAML. | Always true. |

In the table rendering, every null above is shown as `—`.

### `rollup.by_model[]`

Journal mode: `task_spawn_finished` events grouped by their `model` payload
field; spawns with a null model group under `"unknown"`. YAML mode: per-task
rows grouped by row model.

| Field | Type | Meaning |
|-------|------|---------|
| `model` | string | Model name, or `"unknown"`. |
| `spawns` | int \| null | Spawn count in the group. **Null in YAML mode.** |
| `tasks` | int | Distinct tasks in the group. |
| `cost_usd` | number \| null | Group cost sum (null-excluded). |
| `input_tokens` / `output_tokens` / `cache_read_input_tokens` / `cache_creation_input_tokens` | int \| null | Group token sums. |
| `unmeasured_spawns` | int \| null | Unmeasured spawns in the group. **Null in YAML mode.** |

## `quality`

The original dashboard data, sourced from the YAML rows of this run plus each
task's `summary.md`. Identical in both source modes.

| Field | Type | Meaning |
|-------|------|---------|
| `tasks` | array | Key-sorted rows: `{key, jira_key, status, final_quality_score, iteration_count, linter_cycles, deferred_findings_count, human_gate_fired, pr_url}` — string/int fields null when the YAML row lacks them. |
| `concerning` | array | `{key, reasons: [string]}` — Done tasks worth spot-checking (low score, iterated before approve, many deferred findings, human gate fired). |
| `reviews` | array | `{key, status, consensus: [{reviewer, score, verdict}], per_dimension: {<dimension>: [scores]}, deferred_findings: [string]}` from each summary.md's review-consensus table. |
| `prs` | array | `{key, jira_key, pr_url}` for tasks with a PR. |
| `parked` | array | `{key, jira_key, branch}` — Blocked tasks parked at the human PR gate. |
| `blocked` | array | `{key, reason}` — Blocked tasks not parked at the gate. |

## Exit codes

Unchanged from the table mode: `0` on success, `2` when the run directory is
missing, no runs exist under `--runs-dir`, or the tasks YAML cannot be
discovered from the run's summary files.
