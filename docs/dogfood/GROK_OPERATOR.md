# Grok operator runbook — dogfood the dispatcher

Operator = **Grok** (or any session) driving `claude-dispatcher` against
itself. Architecture: [single-orchestrator](../architecture/single-orchestrator.md).

## Prerequisites

- `git`, `python3`, `grok` on PATH  
- Repo checkout with this branch (e.g. `dogfood/grok-first`)  
- Install:  
  `python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"`

Claude is **optional** unless you pin `agent: claude` or use cascade terminal
claude.

## Single-orchestrator reminder

The dispatcher owns the loop. Implementers (including Claude) only write code.
Do **not** expect Tasker in-cycle panels under `dispatcher run`.

## Start a dogfood run

```bash
cd /path/to/claude-dispatcher
.venv/bin/dispatcher run features/grok-dogfood/tasks.yaml \
  --mode unattended \
  --implementer grok \
  --cross-family-panel never \
  --skip-verification \
  --max-parallel 1 \
  --run-id "dogfood-$(date -u +%Y%m%dT%H%M%SZ)" \
  --runs-dir docs/runs
```

Until Phase 2 (`--no-claude`) lands, if preflight still requires Claude on your
machine, add `--skip-preflight` only after reading the failure — prefer fixing
preflight over skipping.

## Monitor

```bash
.venv/bin/dispatcher status <run-id> --json
.venv/bin/dispatcher report <run-id>
# Live journal:
tail -f docs/runs/<run-id>/journal.jsonl
```

## Detect Claude leakage (dogfood honesty)

```bash
pgrep -fl '[c]laude' || true
# Journal / YAML rows should show agent: grok for dogfood tasks
```

## Triage Blocked tasks

1. `docs/runs/<run-id>/<KEY>/summary.md`  
2. Journal events: `mechanical_verification`, `agent_fallback`, `panel_verdict`  
3. Worktree (if still present) under the configured worktree base  
4. Either fix the task description/tests, or add a `FIX-*` task and re-run /
   resume

## Resume

```bash
.venv/bin/dispatcher resume <run-id>
```

## Success for a dogfood wave

- Tasks Done with real commits  
- `pytest` green on the feature branch  
- No unexpected `agent: claude` unless pinned  
