# Grok operator runbook — dogfood the dispatcher

Operator = **Grok** (or any session) driving `claude-dispatcher` against
itself. Architecture: [single-orchestrator](../architecture/single-orchestrator.md).

**Status:** Phases 0–8 of the [grok-first plan](../plans/2026-07-12-grok-first-dogfood.md)
are implemented. This branch is **ready to run** dogfood waves.

## Prerequisites

- `git`, `python3`, `grok` on PATH
- Repo checkout on branch `dogfood/grok-first` (or later)
- Install:
  `python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"`

Claude is **optional** unless you pin `agent: claude` or use cascade terminal
claude (default prod closer when not using `--no-claude`).

## Single-orchestrator reminder

The dispatcher owns the loop (worktree → optional design → implement →
mechanical → verifier → panel → integrate). Implementers only write code.
Do **not** expect Tasker in-cycle under `dispatcher run`.

## Authoring a new feature task list

Before a product wave, have a **planner** (human or agent) produce PRD +
`tasks.yaml` using:

- [How to author tasks](../how-to-author-tasks.md) — skeleton → graph → batch → dry-run
- [Planner prompt](../templates/planner-prompt.md) — paste into Claude/Grok/Codex

Then `dispatcher run … --mode dry-run` before spending implementer tokens.

## Ready to run — full dogfood wave (Phases 4–8)

```bash
cd /path/to/claude-dispatcher
# Optional honesty check: block claude binary
mkdir -p /tmp/no-claude-bin
printf '#!/bin/sh\necho blocked >&2; exit 127\n' > /tmp/no-claude-bin/claude
chmod +x /tmp/no-claude-bin/claude
export PATH="/tmp/no-claude-bin:$PATH"

RUN_ID="dogfood-$(date -u +%Y%m%dT%H%M%SZ)"

.venv/bin/dispatcher run features/grok-dogfood/tasks.yaml \
  --mode unattended \
  --no-claude \
  --cross-family-panel never \
  --max-parallel 1 \
  --base-branch dogfood/grok-first \
  --worktree-base "$(pwd)/worktrees-dogfood" \
  --runs-dir docs/runs \
  --run-id "$RUN_ID"
```

What `--no-claude` sets:

| Setting | Value |
|---------|--------|
| implementer | grok |
| cascade terminal | grok |
| verifier_agent | grok |
| design_agent | grok |
| haiku summaries | off |
| preflight | requires `grok`, not `claude` |

Optional knobs (Phases 4–7):

```bash
# LLM verifier via Grok (per-task verify: llm|llm_strict also works)
  --verifier-agent grok

# Design stage for design_required() tasks (Critical/High/L/XL/…)
  --enable-design-stage

# Cheap-first routing for unpinned tasks (HARD→claude if present, else grok)
  --cheap-first

# Panel intensity when seats exist (auto|always|never; task panel: overrides)
  --cross-family-panel auto
```

## Claude regression smoke (thin implementer, not Tasker)

Before merging this branch to `main`, prove the **default Claude path** still
works under the single-orchestrator brief (no Tasker, no `--no-claude`):

```bash
RUN_ID="claude-smoke-$(date -u +%Y%m%dT%H%M%SZ)"

.venv/bin/dispatcher run features/grok-dogfood/claude-smoke.yaml \
  --mode unattended \
  --cross-family-panel never \
  --max-parallel 1 \
  --base-branch dogfood/grok-first \
  --worktree-base "$(pwd)/worktrees-dogfood" \
  --runs-dir docs/runs \
  --run-id "$RUN_ID" \
  --claude-extra-args '--permission-mode bypassPermissions --allow-dangerously-skip-permissions'
```

Expect: task **Done**, `agent: claude` provenance, mechanical gate passed,
`docs/dogfood/CLAUDE_SMOKE.md` on the task branch. Record in
`docs/dogfood/SMOKE_RESULTS.md`.

## Monitor

```bash
.venv/bin/dispatcher status "$RUN_ID" --json   # includes needs_attention[]
.venv/bin/dispatcher watch "$RUN_ID"           # live journal tail
.venv/bin/dispatcher report "$RUN_ID"
```

`needs_attention` lists Blocked tasks and Done tasks that still need push.

## Detect Claude leakage (dogfood honesty)

```bash
pgrep -fl '[c]laude' || true
# Journal / YAML rows should show agent: grok for dogfood tasks
```

## Triage Blocked tasks

1. `docs/runs/<run-id>/<KEY>/summary.md`
2. Journal: `mechanical_verification`, `agent_fallback`, `panel_verdict`,
   `design_*`, `quality_levels_resolved`
3. Worktree under `--worktree-base`
4. Fix description/tests, or add a `FIX-*` task and re-run / resume

## Resume

```bash
.venv/bin/dispatcher resume <run-id>
```

## Tiny smoke (proven)

See [SMOKE_RESULTS.md](./SMOKE_RESULTS.md). One-liner:

```bash
mkdir -p /tmp/no-claude-bin
printf '#!/bin/sh\necho blocked >&2; exit 127\n' > /tmp/no-claude-bin/claude && chmod +x /tmp/no-claude-bin/claude
export PATH="/tmp/no-claude-bin:$PATH"

.venv/bin/dispatcher run features/grok-dogfood/smoke.yaml \
  --mode unattended --no-claude --cross-family-panel never \
  --base-branch dogfood/grok-first \
  --worktree-base "$(pwd)/worktrees-smoke" \
  --runs-dir docs/runs
```

## Success for a dogfood wave

- Tasks Done with real commits
- `pytest` green on the feature branch
- No unexpected `agent: claude` unless pinned
- Operator can triage with `status --json` + `watch` only
