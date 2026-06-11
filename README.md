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
  --verify-test-timeout SECONDS             default: 600 — wall-clock bound per execution of the .dispatcher.yaml `test:` command (mechanical gate)
  --max-verify-iterations N                 default: 2 — on LLM-verifier INCOMPLETE, re-spawn Tasker with the gap list, re-run the mechanical gate, re-verify, up to N times
  --skip-verification                        escape hatch — skip the post-Done LLM verifier entirely (mechanical gate still runs); the skip is journaled
  --lock-timeout-seconds SECONDS            default: 30 — tasks-YAML FileLock wait
  --task-timeout-seconds SECONDS            default: 14400 (4h) — per-task wall-clock budget
  --run-id NAME                             default: ISO 8601 timestamp
  --financial-paths "glob1,glob2"            override default financial-paths list
  --runs-dir PATH                           default: docs/runs
  --worktree-base PATH                      default: /worktrees in containers, else ../worktree-<key>
  --base-branch NAME                        fork worktrees from this branch (flag > YAML `base_branch` > main)
  --claude-bin NAME                         default: claude
  --claude-extra-args "..."                  extra args passed to `claude` after --print
  --skip-preflight                          skip the run-start preflight checks — see Run-start preflight
  --gh-bin NAME                             default: gh
  --auto-integrate                          merge each Done task's branch into --base-branch atomically
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
dispatcher report [<run-id>] [--json] [--tasks-yaml PATH] [--runs-dir PATH]
                                            Quality dashboard + per-run cost rollup:
                                            wall clock, cost/token totals summed over
                                            every spawn (journal-sourced), per-task and
                                            per-model usage tables, plus the quality data
                                            (gate fields, concerning-tasks highlights,
                                            per-reviewer breakdown). <run-id> defaults to
                                            the latest run. See "dispatcher report".

dispatcher doctor [--check] [--config-dir PATH]
                                            Probe the machine (agent CLIs, tools, dispatcher
                                            install) and write the profile to
                                            ~/.config/claude-dispatcher/machine.yaml.
                                            --check exits 1 if claude or git is missing.
                                            See "Machine profile (dispatcher doctor)".

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
from the artifacts the orchestrator maintains:

- the **tasks YAML**, the authoritative per-task state (status, `started_at`/
  `completed_at`, `model`, `cost_usd`, `iteration_count`, `blocked_reason`,
  `pr_url`, …),
- the run's **`journal.jsonl`** (the hash-chained [event journal](docs/journal-format.md)),
  the *preferred* liveness source — the age of its last event tells you whether
  the run is still moving — and the source of each task's `journal` enrichment
  block (spawn token usage, panel verdicts), and
- the run's legacy **`run.log`**, used as a *fallback* liveness source for
  pre-journal runs whose directory predates the journal. When liveness comes
  from `run.log`, `liveness.source` is `"run.log"` so the reading is labeled as
  the fallback.

It is read-only and mid-run-safe — it never touches the YAML or worktrees, and
parses the journal leniently (a torn/partial final line on a live run is skipped,
never an error; for chain integrity use `journal.verify`), as well as tolerating
a partially-written final `run.log` line.

```bash
# Human-readable table
dispatcher status 2026-06-10T18-24-47Z-tasks

# Machine-readable JSON (full schema in src/claude_dispatcher/status.py)
dispatcher status 2026-06-10T18-24-47Z-tasks --json
```

The YAML is normally auto-discovered from the run's summary files. For a fresh
run that has no summaries yet, pass `--tasks-yaml PATH` explicitly.

The `--json` document carries `run_id`, `current_wave` / `wave_count`,
`run_complete`, a `liveness` block (`source` — `"journal"`/`"run.log"`/`null` —
`journal_present`, `run_log_present`, `last_event_at`, `last_event_age_seconds`,
`last_event`, plus `last_event_type`/`last_event_seq` when sourced from the
journal), a `totals` block (`by_status` counts, `run_cost_usd`, `tasks_billed`),
and a key-sorted `tasks` array with each task's per-run state, dependency `wave`,
and a `journal` enrichment block (spawn token usage + last panel verdict, or
`null` on pre-journal runs / tasks with no events yet).

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

### Verification gate

After a Tasker reports `Done` — and *before* the cross-family panel — the
dispatcher runs a two-stage verification gate that asks a question the Tasker's
own self-review cannot answer impartially: *does the committed diff actually do
what the task asked, with the repo still green?* Both stages run only for a
still-`Done` task; a non-Done outcome (Blocked/Escalated) skips them entirely.

**Mechanical-first ordering.** The two stages run in a fixed order, cheapest
first:

1. **Mechanical gate (VG-2)** — runs the repo's `.dispatcher.yaml` `test:`
   command inside the task worktree. Green (exit 0) proceeds; red triggers one
   "fix-the-tests" re-spawn of the Tasker and a single re-run. Still red →
   `Blocked` with reason `mechanical_verification_failed` (the failing output
   tail lands in `mechanical_verification_detail` on the row). No `test:`
   command (or no `.dispatcher.yaml`) → the gate is **skipped**, behaviour
   unchanged from pre-gate runs. Each execution is bounded by
   `--verify-test-timeout` (default 600s) — a timeout counts as a failure.
2. **LLM verifier (VG-4)** — spawned only after the mechanical gate passes, so
   verifier tokens are never spent on a red suite. An independent Claude session
   reads the task, the Tasker's `summary.md`, and the committed diff, and
   returns `VERIFIED` or `INCOMPLETE` (with a gap list). `VERIFIED` proceeds to
   the panel.

**The iterate loop.** On `INCOMPLETE`, the dispatcher re-spawns the Tasker with
the verifier's gap list as a corrective prompt, **re-runs the mechanical gate**
(an iterate may have reddened the suite), then re-verifies — up to
`--max-verify-iterations` times (default 2). This is distinct from
`--cross-family-panel-iterate`; the verifier runs first, and each iteration is
one Tasker re-spawn + one mechanical re-run + one verifier re-spawn. If an
iterate spawn produces no new commit (the Tasker changed nothing), the loop
short-circuits — re-verifying the same diff would return the same verdict.

**Blocked reasons** the gate can stamp on a row:

| `blocked_reason` | Meaning |
|------------------|---------|
| `mechanical_verification_failed` | The `test:` command was still red after the fix-the-tests retry, or `.dispatcher.yaml` was malformed (no retry — a prompt can't fix an unparseable config). Can also fire *during* an LLM-verifier iterate, if the re-run reddens the suite. |
| `verification_incomplete` | The LLM verifier still returned `INCOMPLETE` after exhausting `--max-verify-iterations` (or an iterate produced no new commit). The rendered gaps land in `verification_detail` on the row. |

**Skipping.** `--skip-verification` is an emergency escape hatch that skips the
LLM verifier entirely (the mechanical gate still runs). The skip is journaled (a
`verification_skipped` event, plus `run_config.skip_verification` in the genesis
provenance) so an auditor can see the gate was bypassed. The verifier exists to
catch stubbed/deferred/quietly-narrowed work that a passing mechanical suite
can hide, so skip it only when you must.

The gate stamps `verified`, `verification_iterations`, and
`mechanical_verification` on the YAML row (see [YAML schema
additions](#yaml-schema-additions)), and emits `verification_*` journal events
documented in [docs/journal-format.md](docs/journal-format.md).

### Per-repo config: `.dispatcher.yaml`

A repo opts into the verification gate and advisory reviewers through a
`.dispatcher.yaml` at the repo root (schema introduced in VG-1). All keys are
optional; an absent file means "no mechanical test command, no advisory seats"
and is not an error.

```yaml
# The shell command run inside a task worktree for the mechanical gate.
# Exit 0 = green. Run verbatim (never stripped). Absent → mechanical gate skipped.
test: "pytest -q"

# Cross-family panel options. Today the only known key is `advisory:`.
panel:
  # Probationary, non-blocking reviewer families seated next to the
  # authoritative three. See "Advisory (probationary) reviewers" below.
  advisory: [grok]
```

| Key | Type | Meaning |
|-----|------|---------|
| `test` | string | Mechanical-gate command, run verbatim in the worktree (exit 0 = green). Must be a non-blank string; absent → gate skipped. |
| `panel.advisory` | list\<string> | Advisory reviewer family names. Empty/absent → no advisory seats. |

**Forward-compatibility.** The loader does **not** reject keys it doesn't
recognise. Unknown top-level keys, and unknown keys nested under `panel:`
(reported as `panel.<key>`), are collected into `RepoConfig.unknown_keys` and
journaled as a `unknown_keys` note on the `verification_mechanical` event rather
than failing the run. This lets a newer config schema be dropped into a repo an
older dispatcher reads without breaking it. What *is* rejected (raising
`RepoConfigError`, which Blocks the task with `mechanical_verification_failed`):
a non-mapping root, unparseable YAML, a `test:` that isn't a non-blank string, a
`panel:` that isn't a mapping, or a `panel.advisory` that isn't a list of
strings.

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

**Advisory (probationary) reviewers**

A repo can seat additional *advisory* reviewers next to the authoritative
three by adding a `panel:` section to its `.dispatcher.yaml`:

```yaml
panel:
  advisory: [grok]
```

Advisory semantics:

- Advisory reviewers run **in parallel** with the authoritative three (same
  executor pass, same prompt shape with a family-specific preamble).
- They **never count toward consensus**: an advisory `CHANGES_REQUESTED` or
  `CRITICAL` finding cannot block the task or trigger
  `--cross-family-panel-iterate`, and an advisory `APPROVE` cannot rescue a
  panel that is `incomplete` because an authoritative seat was
  `UNAVAILABLE`.
- An advisory failure (CLI missing, timeout, empty output) is journaled as
  `UNAVAILABLE` with zero effect on the panel outcome.
- Unknown names in `advisory:` are skipped and logged; a malformed
  `.dispatcher.yaml` is logged and the authoritative panel runs without
  advisory seats.

What gets recorded: every `panel_verdict` journal event carries an
`advisory_verdicts` map (`{}` when no advisory reviewer ran), and each
advisory finding is journaled as its own `panel_advisory_finding` event
(family, severity, location, description, fix, advisory verdict). The
rendered `summary.md` block gains a clearly-labelled
"Advisory reviewers (non-blocking, probationary)" appendix in both the
approve and block render paths. Advisory verdicts are NOT stamped as
`panel_verdict_<family>` YAML columns — those stay authoritative-only.

The first advisory occupant is **Grok Build** (xAI's `grok` CLI,
contract verified against 0.2.39): the panel invokes
`grok --prompt-file <tempfile> --output-format plain --always-approve`
with stdin closed (`DEVNULL`), reads the verdict from stdout, and ignores
grok's noisy stderr. Nonzero exit or empty stdout → `UNAVAILABLE`.

The advisory tier exists to build a scorecard: once enough journaled
verdicts exist to compare an advisory family against the authoritative
three, promoting it to a voting seat is a future **explicit human
decision** — never automatic.

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

### Run-start preflight

Both live modes (`unattended` and `supervised`) run four checks **before the
run directory, journal, or any worktree exists** — `dry-run` never reaches
them. Each check encodes a failure mode that silently burned a real dogfood
run. A failed preflight prints every failure and exits 2, leaving **no
half-created artifacts**; warnings print to stderr, are replayed into
`run.log`, and the run proceeds.

| Check | Severity | What it catches |
|-------|----------|-----------------|
| `claude` binary on `$PATH` | **Failure** when missing (nothing can spawn). Present-but-version-unreadable is only a warning. | Typo'd `--claude-bin`, bare machine. |
| Permission-bypass flag in `--claude-extra-args` | **Failure** for both live modes. Accepted mechanisms: `--dangerously-skip-permissions`, or `--permission-mode bypassPermissions` (adjacent pair or `=` form). `--allow-dangerously-skip-permissions` alone does NOT count — it permits a bypass without enabling one. | Every Tasker stalling at its first tool-use prompt and exiting 0 with nothing committed (dogfood run #1). |
| Tasker role file resolvable from a fresh worktree | **Failure** when the file is neither git-tracked nor resolvable in a throwaway probe worktree cut at the configured `--worktree-base`. Probe *infrastructure* failing is only a warning. | A machine-local symlink convention that doesn't reach fresh worktrees (dogfood run #1). |
| Dispatcher staleness | **Warning only**, and only when the repo being dispatched IS claude-dispatcher itself: warns when the installed version differs from the repo HEAD's `pyproject.toml` version. | A stale pipx snapshot silently dispatching with old code (dogfood run #2). See [docs/machine-profile.md](docs/machine-profile.md). |

The outcome is journaled as a run-level `preflight` event (checks, warnings)
right after the journal opens. Because a *failed* preflight exits before the
journal exists, only passing or skipped preflights ever appear on the chain.
`dispatcher resume` deliberately does **not** re-run preflight — the original
verdict (or skip) is already on the chain, and re-checking mid-run could
refuse to finish half-landed work.

To bypass the checks when one is wrong for your setup:

```bash
dispatcher run tasks.yaml --mode unattended --skip-preflight
```

The skip itself is journaled (the `preflight` event carries `skipped: true`,
and the genesis `run_config.skip_preflight` records the flag), so an auditor
can always see that the checks were waived rather than passed.

### Machine profile (`dispatcher doctor`)

`dispatcher doctor` probes the machine — agent CLIs (`claude`, `agy`,
`codex`, `grok`, `opencode`, `qwen`), tools (`git`, `gh`, `docker`, `sqlc`,
`buf`), and how the dispatcher itself is installed — and writes the profile
to `$XDG_CONFIG_HOME/claude-dispatcher/machine.yaml` (default
`~/.config/claude-dispatcher/machine.yaml`):

```
$ dispatcher doctor
agents:
  claude     ✓ 2.1.34
  agy        ✓ 0.121.0
  codex      ✗ not found
  grok       ✗ not found
  opencode   ✗ not found
  qwen       ✗ not found
tools:
  git        ✓ 2.43.0
  gh         ✓ 2.45.0
  docker     ✗ not found
  sqlc       ✗ not found
  buf        ✗ not found
wrote /home/you/.config/claude-dispatcher/machine.yaml
```

`--check` makes it a setup gate: exit 1 if a **required** entry (`claude`,
`git`) is missing — every other entry is soft, reported but never affecting
the exit code:

```bash
dispatcher doctor --check && dispatcher run tasks.yaml --mode unattended ...
```

`--config-dir PATH` overrides where `machine.yaml` is written. The file is
shared with you: everything under the top-level `manual:` key is user-owned
and never touched by re-probes, and file comments survive (the same
comment-preserving contract the tasks YAML gets). Re-run `doctor` after
installing anything it covers.

The full profile format — every field, the probe semantics, exit codes, and
the staleness warning — is specified in
**[docs/machine-profile.md](docs/machine-profile.md)**, complete enough to
hand-write a profile.

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

  # Usage/cost from the agent CLI's JSON output (last spawn only — the
  # journal records every spawn; see `dispatcher report`). Each field is
  # written only when the CLI actually reported it — never null-filled:
  model: "claude-opus-4-8[1m]"
  cost_usd: 2.2894807
  input_tokens: 81000
  output_tokens: 12400
  cache_read_input_tokens: 600000
  cache_creation_input_tokens: 9000
  duration_ms: 358000
  num_turns: 24

  # Agent/version provenance, stamped on every terminal row:
  agent: claude                                    # which agent CLI ran the task
  dispatcher_version: "0.1.0"
  agent_version: "2.1.34"                          # omitted if the once-per-run capture failed

  # Verification gate outcome (VG-2 mechanical + VG-4 LLM verifier). All absent
  # when the gate never ran (non-Done outcome, or --skip-verification for the
  # LLM half) — absence means "not evaluated", never "evaluated and skipped":
  mechanical_verification: passed                  # passed | skipped | failed
  mechanical_verification_detail: "…tail…"         # only on mechanical failure
  verified: true                                   # LLM verifier: true | false
  verification_iterations: 0                       # INCOMPLETE → re-spawn cycles run
  verification_detail: "…rendered gaps…"           # only when verified: false

  # Set only when the Done summary shows commits that did not reach the
  # remote (signal for the supervisor/integrator, not a block):
  needs_push: true

  # Set only on Blocked tasks awaiting human PR approval (Critical/financial):
  prepared_pr_title: "feat(platform): [BSA-0-2] schema ..."
  prepared_pr_branch: "feat/BSA-0-2-schema"
  blocked_reason: "awaiting human PR approval"
```

Runs with the cross-family panel enabled stamp additional `panel_*` fields,
documented in the [Cross-family panel](#cross-family-panel) section. Runs
with `--auto-integrate` stamp the merge outcome: `auto_integrate_status`
(e.g. `integrated`, or a failure label), plus `auto_integrate_merge_sha` /
`auto_integrate_services` / `auto_integrate_detail` when applicable.

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

A run is observable three ways: **`dispatcher status`** for point-in-time
state, **`dispatcher report`** for the quality dashboard + cost rollup, and
the per-run **event journal** for the append-only event stream. All three are
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
    "source": "journal",
    "journal_present": true,
    "run_log_present": true,
    "last_event_at": "2026-06-10T12:24:53-07:00",
    "last_event_age_seconds": 268.722,
    "last_event": "task_spawn_finished (DISP-12)",
    "last_event_type": "task_spawn_finished",
    "last_event_seq": 37
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
      "dispatcher_run_id": "2026-06-10T18-24-47Z-tasks",
      "journal": {
        "spawn": { "input_tokens": 81000, "output_tokens": 12400,
                   "cache_read_input_tokens": 600000, "cache_creation_input_tokens": 9000,
                   "duration_ms": 358000, "num_turns": 24 },
        "panel": { "consensus": "approve", "blocking_findings": 0,
                   "verdicts": { "claude": "approve", "codex": "approve", "gemini": "approve" } }
      }
    }
    // ... one object per task, key-sorted; "journal" is null on pre-journal runs
  ]
}
```

The full JSON schema is documented in `src/claude_dispatcher/status.py`. The
tasks YAML is auto-discovered from the run's `summary.md` files; pass
`--tasks-yaml PATH` for a fresh run that has no summaries to trace from yet.

### `dispatcher report`

`report [<run-id>]` is the post-run (but mid-run-safe) dashboard: the per-run
**cost/usage rollup** plus the original **quality data**. `<run-id>` defaults
to the most recent run under `--runs-dir`:

```
$ dispatcher report
========================================================================================
Dispatcher report — 2026-06-10T18-24-47Z-tasks
  Tasks YAML:    /home/you/project/features/phase0-1/tasks.yaml
  Run dir:       /home/you/project/docs/runs/2026-06-10T18-24-47Z-tasks
  Summary files: 12
  Source:        journal
========================================================================================

Status counts:
  Done           12
  In Progress    0
  To Do          0

Run rollup [source: journal]:
  Tasks by status          Done: 12
  Wall clock               2026-06-10T11:24:47-07:00 → 2026-06-10T14:02:10-07:00  (9443.0 s)
  Total cost (USD)         $48.5504
  Tasks billed             12
  Avg cost per task        $  4.0459
  Total input tokens         972,000
  Total output tokens        148,800
  Cache-read tokens        7,200,000
  Cache-creation tokens      108,000
  Sum of spawn durations     4296.0 s
  Spawns                   14  (1 with unmeasured usage)

Per-task usage:
  KEY            STATUS       MODEL                AGENT         COST        IN ...
  ...

Per-model usage [source: journal]:
  MODEL                SPAWNS TASKS      COST        IN       OUT   CACHE-R   CACHE-C
  ...

Tasks in this run (12):
  KEY            JIRA       STATUS       SCORE    ITERS LINT DEFRRD GATE
  ...
```

**Where the numbers come from.** The rollup prefers the run's
[journal](#event-journal) over the YAML rows: a task can spawn multiple times
(commit retry, push retry, panel iterate) and the YAML row records only the
*last* spawn's usage, so real spend is the **sum over all of the task's
`task_spawn_finished` events** — journal-sourced totals can legitimately
exceed the YAML totals. Pre-journal runs (and a journal that yields no
parseable events) fall back to a YAML-only rollup, clearly labeled in the
`Source:` line. Wall clock and spawn counts are journal-only and shown as `—`
in YAML mode.

**Null is never zero.** A spawn whose usage fields are missing (the agent CLI
emitted no usage block) is excluded from the sums and surfaced as an
*unmeasured* count instead of being silently treated as $0.

The quality sections below the rollup are unchanged: per-task gate fields
(score, iterations, linter cycles, deferred findings, human gate), the
concerning-tasks highlights, the per-reviewer/per-dimension breakdown parsed
from each task's `summary.md`, PRs raised, and the parked/blocked lists.

`--json` emits one machine-readable document mirroring the dashboard — the
schema is specified field-by-field in
**[docs/report-json.md](docs/report-json.md)**. The tasks YAML is resolved
with this precedence: explicit `--tasks-yaml` flag → the journal genesis
event's `tasks_yaml_path` → walk-up discovery from the run's summary files
(the only option for pre-journal runs).

### Event journal

Every run also writes an append-only, hash-chained **event journal** at
`<runs-dir>/<run-id>/journal.jsonl` — one JSON object per line, fsync'd per
event, covering the full lifecycle from `run_started` (genesis) through
`run_complete` — including the run-start `preflight` outcome, per-task spawn
usage, panel verdicts, and resume markers. It is the run's tamper-evident audit trail and the supported
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

`dispatcher status --json` (point-in-time state), `dispatcher report --json`
(post-run rollup + quality, schema in [docs/report-json.md](docs/report-json.md)),
and tailing `journal.jsonl` (the event stream) are the **supported integration
surface** for an external monitoring agent. Build against those — not against the
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
├── preflight.py                 # run-start preflight checks (live modes only)
├── yaml_io.py                   # round-trip load/dump + FileLock
├── plan.py                      # runnable-set, label filter, wave planner
├── summary.py                   # parser for the Tasker's summary.md
├── spawn.py                     # claude subprocess + env + prompt + usage parsing
├── worktree.py                  # git worktree create/remove, branch naming
├── pr.py                        # gh pr create wrapper
├── push_verify.py               # post-Done push/PR verification
├── auto_integrate.py            # post-Done merge feat → base_branch
├── cross_family_reviewer.py     # three-family review panel
├── reviewer_prompts/            # _shared.md + claude.md / gemini.md / codex.md
├── dispatch_plan.py             # dry-run report renderer
├── journal.py                   # append-only hash-chained event journal (one JSONL/run)
├── journal_read.py              # lenient journal reader shared by status/report
├── notify.py                    # ntfy.sh / Slack push notifications
├── status.py                    # `dispatcher status` — run state, table or --json
├── resume.py                    # `dispatcher resume` — recover an interrupted run
├── report.py                    # `dispatcher report` — quality dashboard + cost rollup
├── doctor.py                    # `dispatcher doctor` — machine profile (machine.yaml)
└── forecast_bridge.py           # optional forecast-create / forecast-sync Jira bridge

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
├── test_resume.py              # resume: no-op, liveness guard + --force, kill-9 recovery
├── test_preflight.py           # the four run-start checks + orchestrator wiring
├── test_doctor.py              # probe, machine.yaml write/refresh, --check
├── test_report.py              # rollup: journal vs YAML source, null-vs-zero, render
├── test_agent_metadata.py      # agent/version provenance on rows + events
├── test_spawn_usage.py         # usage/cost parsing from the CLI JSON output
├── test_per_task_model.py      # per-task `model:` override stacking
├── test_commit_retry.py        # Done-with-no-commits corrective respawn
├── test_push_verify.py         # post-Done push verification + needs_push
├── test_dependency_merge.py    # dispatch-time dependency branch merging
├── test_auto_integrate.py      # post-Done merge into base branch
├── test_notify.py              # ntfy/Slack channels + event fan-out
├── test_worktree.py            # worktree base resolution + creation
└── test_forecast_bridge.py     # forecast-create / forecast-sync soft-skip + mapping
```

Run the suite: `.venv/bin/pytest -q`.
