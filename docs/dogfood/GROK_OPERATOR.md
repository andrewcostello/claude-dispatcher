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
  --no-claude \
  --cross-family-panel never \
  --max-parallel 1 \
  --run-id "dogfood-$(date -u +%Y%m%dT%H%M%SZ)" \
  --runs-dir docs/runs
```

`--no-claude` sets implementer=grok, cascade-terminal=grok, skips Claude LLM
verifier/haiku, and preflights the `grok` binary instead of `claude`.

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

## Proven unattended smoke

See [SMOKE_RESULTS.md](./SMOKE_RESULTS.md). One-liner:

```bash
# Block claude on PATH so --no-claude is honest
mkdir -p /tmp/no-claude-bin
printf '#!/bin/sh\necho blocked >&2; exit 127\n' > /tmp/no-claude-bin/claude && chmod +x /tmp/no-claude-bin/claude
export PATH="/tmp/no-claude-bin:$PATH"

.venv/bin/dispatcher run features/grok-dogfood/smoke.yaml \
  --mode unattended --no-claude --cross-family-panel never \
  --base-branch dogfood/grok-first \
  --worktree-base "$(pwd)/worktrees-smoke" \
  --runs-dir docs/runs
```

