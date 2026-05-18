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

dispatcher status <run-id>                  current state of a run            (not yet implemented)
dispatcher resume <run-id>                  pick up an interrupted run        (not yet implemented)
dispatcher report <run-id>                  summary of completed tasks         (not yet implemented)
```

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

Worktrees on `Done` are left for `git worktree remove` (or housekeeping cron) to clean up later — the dispatcher does not auto-remove. Worktrees on `Blocked`/`Escalated` are explicitly preserved for inspection.

---

## Layout

```
src/claude_dispatcher/
├── cli.py             # argparse, subcommand dispatch
├── run.py             # `dispatcher run` glue
├── orchestrator.py    # the parallel dispatch loop
├── yaml_io.py         # round-trip load/dump + FileLock
├── plan.py            # runnable-set, label filter, wave planner
├── summary.py         # parser for the Tasker's summary.md
├── spawn.py           # claude subprocess + env + prompt
├── worktree.py        # git worktree create/remove, branch naming
├── pr.py              # gh pr create wrapper
├── dispatch_plan.py   # dry-run report renderer
├── status.py          # `dispatcher status` (stubbed)
├── resume.py          # `dispatcher resume` (stubbed)
└── report.py          # `dispatcher report` (stubbed)

tests/
├── fixtures/
│   ├── three_task.yaml    # 3-task smoke fixture
│   └── fake_claude.py     # stand-in for the claude binary
├── test_yaml_io.py        # round-trip + lock
├── test_plan.py           # validation, runnable-set, filter, waves
├── test_summary.py        # parser, malformed, prepared PR
├── test_dry_run.py        # CLI dry-run path
├── test_orchestrator.py   # live-spawn end-to-end with fake claude
├── test_supervised.py     # supervised approve / reject / skip
└── test_concurrency.py    # --max-parallel overlap + YAML serialization
```

Run the suite: `.venv/bin/pytest -q`. As of the v0.1.0 build: 49 tests, all green.
