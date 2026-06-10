# claude-dispatcher

Orchestrate the Tasker role across many tasks listed in a YAML file. Each task runs in an isolated Claude Code session with fresh context.

The dispatcher owns the boring lifecycle bookkeeping — timestamps, iteration counts, PR URLs, gate decisions — so the Tasker can focus on the actual work. Task YAMLs round-trip with all comments, dividers, and ordering preserved.

---

## Install

```bash
git clone <this-repo> claude-dispatcher
cd claude-dispatcher
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/dispatcher --help
```

Requires Python 3.11+ and `ruamel.yaml`. The dispatcher invokes `claude` (for tasks) and `gh` (for PRs in supervised mode); both must be on `$PATH` or specified via `--claude-bin` / `--gh-bin`.

---

## Quick start

```bash
# Dry-run: print the dispatch plan and exit. No subprocesses, no YAML writes.
dispatcher run path/to/tasks.yaml --mode dry-run

# Unattended: spawn Claude sessions for each runnable task, no human prompts.
# Tasks that hit the Critical/financial-paths PR gate are left Blocked with
# "awaiting human PR approval" so a human can sweep them later.
dispatcher run path/to/tasks.yaml --mode unattended --max-parallel 2

# Supervised: same, but the dispatcher pauses on gate trips for stdin approval.
# On "approve" the dispatcher runs `gh pr create` from the worktree.
dispatcher run path/to/tasks.yaml --mode supervised

# Restrict the set: only certain labels, or only specific keys
dispatcher run path/to/tasks.yaml --filter "size:M,area:schema"
dispatcher run path/to/tasks.yaml --only BSA-0-2,BSA-0-3
```

---

## CLI surface

```
dispatcher run <tasks-yaml> [options]
  --mode {unattended,supervised,dry-run}    default: supervised
  --max-parallel N                          default: 1
  --filter "size:M,area:schema"             include only tasks with these labels
  --only KEY1,KEY2                          dispatch only these task keys
  --skip-design                              short-circuit Design Agent for Critical/High
  --skip-security-linter                    short-circuit Security Linter for Critical
  --reviewer-count {1,2,3}                  override per-tier reviewer count
  --max-iterations N                        default: 2
  --run-id NAME                             default: ISO 8601 timestamp
  --financial-paths "glob1,glob2"            override default financial-paths list
  --runs-dir PATH                           default: docs/runs
  --worktree-base PATH                      default: /worktrees in containers, else ../worktree-<key>
  --claude-bin NAME                         default: claude
  --claude-extra-args "..."                  extra args passed to `claude` after --print
  --gh-bin NAME                             default: gh
  --cross-family-panel {auto,always,never}   default: auto — see Cross-family panel below
  --cross-family-panel-timeout SECONDS      default: 600 — per-reviewer wall-clock budget
  --cross-family-panel-iterate N            default: 0 — on block, re-spawn Tasker with findings up to N times
  --ntfy-topic TOPIC                        push events to https://ntfy.sh/<topic>  (env: DISPATCHER_NTFY_TOPIC)
  --ntfy-server URL                         self-hosted ntfy server                 (env: DISPATCHER_NTFY_SERVER)
  --slack-webhook-url URL                   Slack incoming webhook URL              (env: DISPATCHER_SLACK_WEBHOOK)

dispatcher status <run-id> [--json] [--tasks-yaml PATH] [--runs-dir PATH]
                                            Current state of a run: per-task state,
                                            current wave, totals, cost so far, and run
                                            liveness. Mid-run-safe. --json emits the
                                            structured document. See "Observing a run".
dispatcher resume <run-id> [--strategy {continue,mark-blocked}] [--force] [--runs-dir PATH]
                                            Pick up an interrupted run from its journal —
                                            re-dispatch in-flight tasks, leave terminal
                                            rows untouched. See "Resume".
dispatcher report <run-id>                  Quality dashboard for a run: counts, per-task
                                            gate fields, concerning-tasks highlights, and
                                            the per-reviewer/per-dimension breakdown.

dispatcher forecast-create <tasks-yaml> [--dry-run]
                                            For each row with no `jira_key`, run `forecast jira
                                            create` with mapped flags and write the assigned
                                            Jira key to `row.jira_key`. The dispatcher's local
                                            `key` field is left untouched, so semantic
                                            identifiers like `BSA-E2E-0-1` survive intact.
                                            Soft-skips with exit 0 when forecast is not
                                            installed or not configured.

dispatcher forecast-sync <tasks-yaml> [--dry-run]
                                            For each row in a terminal status (Done/Blocked/Escalated)
                                            whose `jira_key` is set, run `forecast jira transition`
                                            to bring Jira into sync. Soft-skips when forecast
                                            missing or `jira_key` not yet populated.
```

### Run status

`dispatcher status <run-id>` reconstructs the live (or finished) state of a run
from two artifacts the orchestrator already maintains — there is no separate
event-journal subsystem yet:

- the **tasks YAML**, the authoritative per-task state (status, `started_at`/
  `completed_at`, `model`, `cost_usd`, `iteration_count`, `blocked_reason`,
  `pr_url`, …), and
- the run's **`run.log`**, the append-only event log, used for *liveness*: the
  age of the last logged event tells you whether the run is still moving.

It is read-only and mid-run-safe — it never touches the YAML or worktrees, and
tolerates a partially-written final `run.log` line (a live run may be appending
as you read).

```bash
# Human-readable table
dispatcher status 2026-06-10T18-24-47Z-tasks

# Machine-readable JSON (full schema in src/claude_dispatcher/status.py)
dispatcher status 2026-06-10T18-24-47Z-tasks --json
```

The YAML is normally auto-discovered from the run's summary files. For a fresh
run that has no summaries yet, pass `--tasks-yaml PATH` explicitly.

The `--json` document carries `run_id`, `current_wave` / `wave_count`,
`run_complete`, a `liveness` block (`last_event_at`, `last_event_age_seconds`,
`last_event`), a `totals` block (`by_status` counts, `run_cost_usd`,
`tasks_billed`), and a key-sorted `tasks` array with each task's per-run state
and dependency `wave`.

### Forecast bridge (optional)

The dispatcher's tasks YAML is intentionally shaped to mirror `forecast jira create` flags. If your project uses the [forecast](https://github.com/andrewcostello/forecast) Jira tool, you can chain:

```bash
# Materialize Jira tickets from rows with placeholder keys (TBD-1, TBD-2, ...)
dispatcher forecast-create tasks.yaml

# Dispatch as normal
dispatcher run tasks.yaml --mode unattended

# Transition Jira to match dispatcher outcomes (Done/Blocked/Escalated)
dispatcher forecast-sync tasks.yaml
```

Both bridge subcommands smart-detect:
- `forecast` binary on `$PATH`
- `.forecast/config.yaml` in the project root (walks up from the YAML)

If either is missing, the subcommand prints a soft-skip message and exits 0 — safe to chain in CI pipelines on machines without the forecast tool.

The mappable YAML fields (`priority`, `epic`, `parent`, `story_points`, `due_date`, `assignee`, `fix_versions`, `components`) are documented in `claude-workflow/skills/forecast-fields.md`. The dispatcher passively round-trips fields it doesn't recognize, so populating forecast-only fields costs nothing for projects that don't use the bridge.

### Cross-family panel

After a Tasker reports `Done`, the dispatcher can run a panel of three
independent reviewers — one Claude, one Gemini, one Codex — over the diff
and the Tasker's `summary.md`. **All three must `APPROVE`** for the panel
to clear; a single dissenter or any `CRITICAL`/`HIGH` finding flips the
task to `Blocked` and short-circuits `--auto-integrate`. This is an
additional safety net on top of the Tasker's in-cycle review panel — the
in-cycle reviewers are also Claude, so they share Claude's blind spots.
Cross-family review surfaces what same-family review provably misses.

**When the panel fires**

| `--cross-family-panel` | Behaviour |
|------------------------|-----------|
| `auto` (default) | Fires only for risk-gated tickets. A ticket is risk-gated if any of its labels matches `critical`, `security`, `financial`, or `high` (bare or prefixed `risk:`, `tier:`, `severity:`, `priority:`). |
| `always` | Fires for every `Done` ticket. Useful when you want a cross-family audit of an entire epic. |
| `never` | Skips the cross-family panel. The Tasker's in-cycle panel still runs. |

Tickets with `type: docs` or `type: test` always skip the panel — they
don't ship code paths that need this safety net.

**What gets recorded**

When the panel runs, these fields are stamped on the YAML row:

```yaml
- key: BSA-0-2
  status: Blocked                                  # or Done if 3/3 APPROVE
  panel_consensus: block                           # approve | block | incomplete
  panel_summary: "consensus=block | claude=APPROVE | gemini=APPROVE | codex=CHANGES_REQUESTED | blocking=1 (0C/1H)"
  panel_verdict_claude: APPROVE
  panel_verdict_gemini: APPROVE
  panel_verdict_codex: CHANGES_REQUESTED
  panel_blocking_findings: 1
  blocked_reason: "cross_family_panel: consensus=block | ..."
```

The rendered findings are also appended to the per-task `summary.md` so a
human auditor sees the three families' verdicts inline.

**The three CLIs**

The panel shells out to `claude`, `agy` (Antigravity CLI; Google
rebranded `gemini` → `agy` in 2026-05), and `codex` — all three must
be on `$PATH` (or the panel records that family as `UNAVAILABLE` and
treats consensus as `incomplete`, which blocks auto-integrate the same as
a `block` verdict). The Claude invocation reuses the Tasker spawn pattern
(`--print --output-format json --permission-mode bypassPermissions`);
the gemini-family reviewer uses `agy --print "" --print-timeout {N}s`
with the prompt on stdin; Codex uses `exec --sandbox workspace-write
--output-last-message` with the prompt on stdin (closed after the write
so `codex exec` can't hang waiting for EOF). The family identifier stays `gemini` for column
compatibility with historical panel records even though the CLI binary
is `agy`. Per-reviewer timeout defaults to 10 min
(`--cross-family-panel-timeout`).

**Iterate on block (optional)**

`--cross-family-panel-iterate N` (default `0`) makes the dispatcher
re-spawn the Tasker with the panel's blocking findings as a corrective
prompt when the panel returns `block`, then re-run the panel against the
new diff. Up to `N` iterations before giving up and marking the task
`Blocked` for human triage.

Each iteration is one extra Tasker spawn + one extra panel run, so cost
grows linearly with `N`. The iterate path fires on ANY panel block
regardless of severity or vote split — no CRITICAL or single-dissenter
gating. The Tasker is given the findings in the format the in-cycle
reviewer feedback uses, with explicit instructions to address only the
cited issues and not redo the implementation.

If an iterate spawn exits cleanly but produces no new commit (the Tasker
decided nothing needed changing, or got confused), the dispatcher
short-circuits — re-running the panel on the same diff would produce
the same verdict.

YAML row gains `panel_iterations_used: N` so an auditor can see how many
corrective cycles ran before the final verdict landed.

**Retroactive validation**

The `tools/cross_family_panel.py` script runs the panel against an
arbitrary `(repo, base, branch, summary.md)` quadruple — useful for
dry-running the panel against an already-integrated ticket to validate
that the prompts catch real defects:

```bash
python tools/cross_family_panel.py \
    --repo /path/to/repo \
    --base epic/my-epic \
    --branch fix/MY-TICKET-foo \
    --ticket MY-TICKET \
    --summary-md /path/to/summary.md
```

Exit codes: `0` on approve, `1` on block, `2` on incomplete (CI-gateable).
`--family one` runs a single reviewer for prompt iteration.
`--dry-run-with-stub-output FILE` substitutes the canned text for all
three reviewers — exercises the parser without LLM calls.

### Notifications (ntfy.sh / Slack)

The dispatcher can push events to your phone or chat so you know when
the run needs you, without watching the terminal. Four events fire:

| Event | Urgency | When |
|-------|---------|------|
| `task_blocked` | default | Any task lands in `Blocked` (panel block, spawn failure, auto-integrate failure, malformed summary, etc.). One per task. |
| `awaiting_pr_approval` | high | The Tasker parks at the Critical/financial-paths PR gate. Fires in both `supervised` and `unattended` modes — in unattended you also get the gate trip on your phone, then the task is left Blocked for sweep. |
| `run_complete` | high if anything Blocked/Escalated, else default | One rollup at the end of the dispatch loop. Lists the first 10 blocked-task reasons inline. |
| `worker_exception` | high | A worker thread raised something other than a task failure — i.e., the dispatcher itself errored. Should be rare. |

Notifications carry a `click_url` pointing at a `file://` path (typically
the per-task `summary.md` or the tasks YAML) so tapping the notification
opens the relevant artefact.

**ntfy.sh** is the lowest-friction sink — no account, no API key. Install
the ntfy app, subscribe to a topic name only you know, and pass that
topic to the dispatcher:

```bash
# CLI flag
dispatcher run tasks.yaml --ntfy-topic andrew-dispatcher-3a7b

# Or env var (keeps the secret out of shell history)
export DISPATCHER_NTFY_TOPIC=andrew-dispatcher-3a7b
dispatcher run tasks.yaml
```

The topic IS the secret — pick something unguessable.

**Slack incoming webhook** uses Block Kit for rich formatting (header,
section, context block with tags + click URL). The webhook URL is the
secret; prefer the env-var form:

```bash
export DISPATCHER_SLACK_WEBHOOK=https://hooks.slack.com/services/T0/B0/XXXX
dispatcher run tasks.yaml
```

A ready-to-paste Slack app manifest is bundled at
[`docs/slack-app-manifest.json`](docs/slack-app-manifest.json); see
[`docs/slack-app-setup.md`](docs/slack-app-setup.md) for the 4-step
walkthrough.

Both can be configured simultaneously — events fan out to all configured
channels. Failures on one channel don't block the others. Channel
failures are logged to stderr but never raise into the dispatch loop —
the dispatcher's job is to dispatch tasks, not to deliver SMS.

**Back-channel "approve from phone" is NOT supported yet.** Both ntfy and
Slack allow interactive action buttons that POST to a URL, but that
requires the dispatcher to run an HTTP listener with a public HTTPS
endpoint. If your PR-approval gate fires often enough to make that worth
building, file an issue — until then, notifications are one-way push and
you walk back to the laptop for the supervised stdin gate.

### Unattended permission flags

The Tasker uses Bash, Edit, Read, and the Task tool. Under `claude --print` with no extra args, the first tool-use will stall waiting for a permission prompt that no human can answer. For unattended runs, pass:

```bash
dispatcher run tasks.yaml --mode unattended \
  --claude-extra-args "--permission-mode bypassPermissions --allow-dangerously-skip-permissions"
```

Or — preferred for a shared dev machine — configure `~/.claude/settings.json` once with an allowed-tools list scoped to your project, and leave `--claude-extra-args` empty. The dispatcher does not pick a default for you because the right answer is project-specific.

---

## The Tasker contract

The dispatcher invokes `claude` with a prompt that asks the Tasker to:
1. Read `.claude/workflow/roles/tasker.md` (the refactored router).
2. Process the assigned task per Phase 1 → Phase 5 of the role.
3. Write a Markdown summary file to `$SUMMARY_PATH` at session end.

The Tasker **never writes to the YAML directly** — the dispatcher copies fields from the summary into the YAML row.

### Env vars handed to the Tasker session

| Var | Meaning |
|-----|---------|
| `DISPATCHER_RUN_ID` | Present iff under the dispatcher. |
| `TASK_KEY` | The task's YAML key. |
| `SUMMARY_PATH` | Where the Tasker writes its summary. |
| `MAX_ITERATIONS` | Default 2. |
| `SKIP_DESIGN` | Set when `--skip-design`. |
| `SKIP_SECURITY_LINTER` | Set when `--skip-security-linter`. |
| `REVIEWER_COUNT` | Set when `--reviewer-count`. |
| `FINANCIAL_PATHS` | Glob list for the human PR gate. |

### Summary file format

See `.claude/workflow/roles/tasker.md` § "Phase 5: Write Summary File" for the canonical format. The parser is in `src/claude_dispatcher/summary.py` and is resilient: malformed sections mark the task `Blocked` with reason `summary_malformed`, never crash the run.

---

## YAML schema additions

Existing task rows continue to validate. The dispatcher adds these fields as it processes a task:

```yaml
- key: BSA-0-2
  status: Done                                     # default missing = "To Do"
  started_at: "2026-05-18T09:15:00-07:00"          # ISO 8601
  completed_at: "2026-05-18T10:42:00-07:00"
  iteration_count: 1
  linter_cycles: 0                                 # 0 if not run
  pr_url: "https://github.com/.../pull/541"        # OR pr_not_raised_reason
  final_quality_score: 22                          # out of 25, merged
  human_gate_fired: false
  deferred_findings_count: 2
  dispatcher_run_id: "2026-05-18-bay-session"
  branch: "feat/BSA-0-2-schema"                    # branch chosen for the worktree
  summary_path: "docs/runs/.../BSA-0-2/summary.md"

  # Set only on Blocked tasks awaiting human PR approval (Critical/financial):
  prepared_pr_title: "feat(platform): [BSA-0-2] schema ..."
  prepared_pr_branch: "feat/BSA-0-2-schema"
  blocked_reason: "awaiting human PR approval"
```

Tasks with `status: To Do` (or no status) AND all `blockedBy` keys at `status: Done` are dispatched in the next wave.

---

## Comment preservation

The Tasks YAML files in real projects carry load-bearing context in their header comments (design pivot history, "DELETED YYYY-MM-DD" notes, section dividers). The dispatcher uses `ruamel.yaml` in round-trip mode, so:

- Header and section comments survive every write.
- Block-scalar (`|`) descriptions stay block-scalar.
- Field ordering is preserved on the rows the dispatcher touches.
- Atomic write-via-rename means a reader catching a write mid-flight sees the previous version, never a half-written file.

Verified against `bay-session-tasks.yaml` (1375 lines, 55,411 bytes): round-trips byte-identical.

---

## Modes in detail

### `dry-run`

Prints a multi-wave dispatch plan and exits 0. No worktrees, no subprocesses, no YAML writes. Use this to:
- Validate the YAML schema before a run.
- See the dependency graph as waves.
- Estimate parallelism (the first wave's width).
- Audit the env vars that would be handed to each task.

### `unattended`

Spawns tasks; on any gate trip (Critical/financial PR approval, design ambiguity, iteration cap), the task is marked `Blocked` with a reason and the dispatcher moves on. The summary file's `Prepared PR` section (if any) is preserved on the row so a later sweep can pick it up.

Exit code: `0` if all tasks `Done`, `1` if any `Blocked`/`Escalated`.

### `supervised` (default)

Same as unattended, but on PR-gate trips the dispatcher prompts stdin:

```
========================================================================
Human PR gate fired for SMG-1657: add escrow state to prevent silent payout loss
========================================================================
  Title:  feat(wallet): [SMG-1657] add escrow state
  Branch: feat/SMG-1657-escrow-state
  Body preview (first 30 lines):
    ## What
    ...
========================================================================
  Choice [approve/reject/skip]:
```

- `approve` → dispatcher runs `gh pr create` from the worktree, captures URL, marks `Done`.
- `reject` → marks `Blocked`, reason `human rejected PR`.
- `skip` → marks `Blocked`, reason `human skipped PR approval`.

Prompts are serialized across workers — if two tasks gate-fire at once, the human sees them one at a time.

---

## Concurrency

`--max-parallel N` runs up to N tasks in parallel using a thread pool. Each worker:
- Owns its own worktree.
- Mutates the YAML via locked load-mutate-save cycles (`<tasks-yaml>.lock`).
- Writes its own per-task `summary.md` under `<runs-dir>/<run-id>/<task-key>/`.

The YAML lock has a 30-second timeout. If multiple dispatchers are pointed at the same YAML, only one writes at a time; the others wait.

Tasks with `blockedBy` only enter the runnable set after every dependency reaches `Done`. The main thread recomputes the runnable set every time a worker completes, so a dependency unlock surfaces immediately.

---

## Failure modes

| Failure | Outcome |
|---------|---------|
| Claude session exits nonzero | Task `Blocked` with `blocked_reason: session_exit_code_N`. Worktree preserved. |
| Summary file missing at exit | Task `Blocked`, `blocked_reason: summary_missing`. |
| Summary file malformed (invalid Status, missing required field) | Task `Blocked`, `blocked_reason: summary_malformed: <why>`. Run continues. |
| `gh pr create` fails after human approval | Task `Blocked`, `blocked_reason: gh pr create failed: <error>`. Re-run after fixing auth. |
| YAML lock contention timeout (30s) | The waiter raises `LockTimeout`. Typical cause: another dispatcher running against the same YAML. |
| `--max-parallel 4` with only 2 runnable tasks | Workers idle; no error. The next dispatch wave fills as dependencies unblock. |
| Network failure mid-PR-raise | Tasker reports `pr_url: null`; dispatcher marks `Blocked` with reason `pr_raise_failed`. |
| Worker thread exception | Task `Blocked`, `blocked_reason: worker_exception: <repr>`. |
| Cross-family panel dissent (any reviewer non-APPROVE) | Task `Blocked`, `blocked_reason: cross_family_panel: <summary>`. Findings appended to `summary.md`. Auto-integrate short-circuited. |
| Cross-family reviewer CLI missing | That family records `UNAVAILABLE`. Panel `consensus=incomplete`. Treated as block. |
| Cross-family panel framework error (not a reviewer dissent) | Task `Blocked`, `blocked_reason: cross_family_panel_error: <repr>`. Tasker's work preserved. |

Worktrees on `Done` are left for `git worktree remove` (or housekeeping cron) to clean up later — the dispatcher does not auto-remove. Worktrees on `Blocked`/`Escalated` are explicitly preserved for inspection.

---

## Observing a run

A run is observable two ways: **`dispatcher status`** for point-in-time state,
and the per-run **event journal** for the append-only event stream. Both are
read-only and mid-run-safe — they never touch the YAML or the worktrees, and
tolerate a partially-written file on a live run.

### `dispatcher status`

`status <run-id>` reconstructs run state from the tasks YAML (authoritative
per-task state) and the run's `run.log` (for liveness — the age of the last
logged event tells you whether the run is still moving). It prints a
human-readable table by default:

```
$ dispatcher status 2026-06-10T18-24-47Z-tasks
========================================================================================
Dispatcher status — 2026-06-10T18-24-47Z-tasks
  Tasks YAML:   /home/you/project/features/phase0-1/tasks.yaml
  Generated at: 2026-06-10T12:29:17-07:00
  Run complete: no    Current wave: 4 / 4
  Liveness:     last event 2026-06-10T12:24:53-07:00 (265s ago) — DISP-12 worktree at ...
========================================================================================

Tasks (12):  To Do: 0  In Progress: 1  Done: 11  Blocked: 0  Escalated: 0
Run cost:    $48.5504  across 11 billed task(s)

  KEY              STATUS       WAVE      COST ITERS MODEL              NOTE
  --------------------------------------------------------------------------
  DISP-1           Done         1      $2.2895 1     claude-opus-4-8[1m] https://github.com/.../pull/1
  DISP-11          Done         3      $6.5795 1     claude-opus-4-8[1m] https://github.com/.../pull/10
  DISP-12          In Progress  4            — —     —
  DISP-8           Done         1      $9.2351 1     claude-opus-4-8[1m] https://github.com/.../pull/8
  ...
```

`--json` emits a machine-readable document instead — per-task rows plus run
totals, dependency-wave position, and liveness:

```
$ dispatcher status 2026-06-10T18-24-47Z-tasks --json
{
  "run_id": "2026-06-10T18-24-47Z-tasks",
  "tasks_yaml": "/home/you/project/features/phase0-1/tasks.yaml",
  "generated_at": "2026-06-10T12:29:21-07:00",
  "run_complete": false,
  "current_wave": 4,
  "wave_count": 4,
  "liveness": {
    "run_log_present": true,
    "last_event_at": "2026-06-10T12:24:53-07:00",
    "last_event_age_seconds": 268.722,
    "last_event": "DISP-12 worktree at ..."
  },
  "totals": {
    "task_count": 12,
    "by_status": { "To Do": 0, "In Progress": 1, "Done": 11, "Blocked": 0, "Escalated": 0 },
    "run_cost_usd": 48.550377,
    "tasks_billed": 11
  },
  "tasks": [
    {
      "key": "DISP-1",
      "summary": "auto_integrate: discover sqlc/buf via shutil.which + env override",
      "status": "Done",
      "wave": 1,
      "started_at": "2026-06-10T11:24:47-07:00",
      "completed_at": "2026-06-10T11:30:45-07:00",
      "model": "claude-opus-4-8[1m]",
      "cost_usd": 2.2894807,
      "iteration_count": 1,
      "blocked_reason": null,
      "pr_url": "https://github.com/.../pull/1",
      "dispatcher_run_id": "2026-06-10T18-24-47Z-tasks"
    }
    // ... one object per task, key-sorted
  ]
}
```

The full JSON schema is documented in `src/claude_dispatcher/status.py`. The
tasks YAML is auto-discovered from the run's `summary.md` files; pass
`--tasks-yaml PATH` for a fresh run that has no summaries to trace from yet.

### Event journal

Every run also writes an append-only, hash-chained **event journal** at
`<runs-dir>/<run-id>/journal.jsonl` — one JSON object per line, fsync'd per
event, covering all 14 lifecycle event types (`run_started` through
`run_complete`). It is the run's tamper-evident audit trail and the supported
event feed for external tools. The full specification — event types, field
semantics, the hash-chain construction and verification algorithm, the genesis
provenance fields, the single-writer rule, and the location convention — is in
**[`docs/journal-format.md`](docs/journal-format.md)**, written to be complete
enough to implement an independent reader from.

To follow a live run:

```bash
tail -F docs/runs/<run-id>/journal.jsonl | jq -c '{seq, event_type, task_key}'
```

### Note for monitoring agents

`dispatcher status --json` (point-in-time state) and tailing
`journal.jsonl` (the event stream) are the **supported integration surface**
for an external monitoring agent. Build against those two — not against the
tasks YAML, `run.log`, or internal module APIs, which are implementation
details that may change. Both observation paths are read-only, so a monitor
can never perturb a run.

---

## Resume

Every run writes the [event journal](#event-journal) described above; its
`run_started` (genesis) event captures the run's configuration. If a run is
interrupted — `kill -9`, a crashed host, a closed laptop — `dispatcher resume
<run-id>` reconstructs it from that journal plus the current tasks YAML. You do
not re-supply the YAML path; it comes from the genesis provenance.

```bash
# Resume a run by id (looks under --runs-dir, default docs/runs)
dispatcher resume 2026-06-10T18-24-47Z-tasks

# After a hard kill the journal may still look "fresh" — force past the guard
dispatcher resume 2026-06-10T18-24-47Z-tasks --force
```

**Recovery rules:**

| Row state at resume | Action |
|---------------------|--------|
| `In Progress` (interrupted spawn) | **Re-dispatched.** Reset to `To Do` so the loop re-spawns it fresh. The worktree is reused if it still exists (`git worktree add` is idempotent); a missing one is recreated. |
| `Done` / `Blocked` / `Escalated` | **Untouched.** Terminal rows are never re-run. |
| `To Do` not yet reached | Dispatched normally once its `blockedBy` deps are `Done`. |

A resume appends a marker event linking back to the prior genesis, so the
journal records that the run was picked up.

**Liveness guard (`--force`).** Resuming a run that is *still running* would
double-dispatch in-flight tasks. Before resuming, the dispatcher checks the age
of the journal's most recent event; if it is too recent the run may still be
live, and resume refuses (exit code 4) and points you at `--force`. A genuinely
dead run stops emitting events, so its journal ages past the threshold and
resumes without `--force`. Use `--force` only when you are certain the original
process is gone.

**Completed runs are a no-op.** If no rows are `In Progress` and nothing is left
runnable, resume prints `Run <id> is already complete — nothing to resume (...)`
and exits 0 without touching the YAML.

**`--strategy`:**

- `continue` *(default)* — reset interrupted `In Progress` rows to `To Do` and
  re-dispatch them.
- `mark-blocked` — write `Status: Blocked` for interrupted rows instead of
  re-running them, then dispatch any remaining runnable tasks. Use this when you
  want a human to inspect what an interrupted task was doing before it is retried.

---

## Layout

```
src/claude_dispatcher/
├── cli.py                       # argparse, subcommand dispatch
├── run.py                       # `dispatcher run` glue
├── orchestrator.py              # the parallel dispatch loop
├── yaml_io.py                   # round-trip load/dump + FileLock
├── plan.py                      # runnable-set, label filter, wave planner
├── summary.py                   # parser for the Tasker's summary.md
├── spawn.py                     # claude subprocess + env + prompt
├── worktree.py                  # git worktree create/remove, branch naming
├── pr.py                        # gh pr create wrapper
├── auto_integrate.py            # post-Done merge feat → base_branch
├── cross_family_reviewer.py     # three-family review panel
├── reviewer_prompts/            # _shared.md + claude.md / gemini.md / codex.md
├── dispatch_plan.py             # dry-run report renderer
├── journal.py                   # append-only hash-chained event journal (one JSONL/run)
├── status.py                    # `dispatcher status` — run state, table or --json
├── resume.py                    # `dispatcher resume` — recover an interrupted run
└── report.py                    # `dispatcher report` — quality dashboard

tools/
└── cross_family_panel.py        # standalone runner for the review panel

tests/
├── fixtures/
│   ├── three_task.yaml    # 3-task smoke fixture
│   └── fake_claude.py     # stand-in for the claude binary
├── test_yaml_io.py        # round-trip + lock
├── test_plan.py           # validation, runnable-set, filter, waves
├── test_summary.py        # parser, malformed, prepared PR
├── test_dry_run.py        # CLI dry-run path
├── test_orchestrator.py        # live-spawn end-to-end with fake claude
├── test_orchestrator_panel.py  # cross-family panel integration
├── test_cross_family_reviewer.py  # panel parser + adapters + aggregation
├── test_supervised.py          # supervised approve / reject / skip
├── test_concurrency.py         # --max-parallel overlap + YAML serialization
├── test_journal.py             # journal: append / read / genesis / hash-chain verify
├── test_orchestrator_journal.py # orchestrator emits every lifecycle event
├── test_status.py              # status: table + --json, waves, liveness
└── test_resume.py              # resume: no-op, liveness guard + --force, kill-9 recovery
```

Run the suite: `.venv/bin/pytest -q`. The control-surface work (event journal,
`status`, `resume`) added the dedicated suites above on top of the cross-family
panel build.
