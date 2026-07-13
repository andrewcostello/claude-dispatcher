# Unattended smoke results

## Successful Claude run: `claude-smoke-20260713T203444Z`

Regression for **thin Claude implementer** (no Tasker, no `--no-claude`) before
merging `dogfood/grok-first` → `main`.

| Field | Value |
|-------|--------|
| Command | `dispatcher run features/grok-dogfood/claude-smoke.yaml --mode unattended --cross-family-panel never --base-branch dogfood/grok-first` + permission bypass extra-args |
| Claude on PATH | **Present** (`claude` 2.1.207) |
| Implementer | **claude** (model `claude-fable-5`) |
| Status | **Done** |
| Mechanical gate | **passed** (~141s full pytest) |
| LLM verifier | skipped (`verify: mechanical`) |
| Panel | never |
| Wall clock | ~5.2 min |
| Cost (YAML) | ~$2.30 |
| Artifact | `docs/dogfood/CLAUDE_SMOKE.md` |
| Feature branch | `feat/DOG-CLAUDE-SMOKE-1-write-docs-dogfood-claude-smoke` |
| PR | https://github.com/andrewcostello/claude-dispatcher/pull/55 |

### Provenance (YAML row after run)

- `agent: claude`
- `model: claude-fable-5`
- `agent_version: 2.1.207 (Claude Code)`
- `mechanical_verification: passed`
- `verified: true` (mechanical stamp for risk ladder)

### Preflight

- `no_claude: false` (default Claude path)
- `permission_flags: --permission-mode bypassPermissions` ok
- Tasker role file missing → **warning only** (expected; single-orchestrator)

### Notes

1. First spawn reported Done with no commits → **commit-retry** recovered (same pattern as Grok smoke).
2. Push-retry recovered after branch absent on origin; PR #55 opened against `dogfood/grok-first`.
3. Summary shows worker brief only — no Tasker phases. Artifact contains "not Tasker".

---

## Successful Grok run: `dogfood-smoke-20260713T061016Z`

| Field | Value |
|-------|--------|
| Command | `dispatcher run features/grok-dogfood/smoke.yaml --mode unattended --no-claude --cross-family-panel never --base-branch dogfood/grok-first` |
| Claude on PATH | **Blocked** (`/tmp/no-claude-bin/claude` → exit 127 first) |
| Implementer | **grok** (CLI 0.2.99) |
| Status | **Done** |
| Mechanical gate | **passed** (~200s full pytest) |
| LLM verifier | skipped (`verify: mechanical`) |
| Panel | never |
| Wall clock | ~397s |
| Tokens (journal) | ~80k in / ~15k out (3 spawns: implement + commit-retry + push-retry) |
| Artifact | `docs/dogfood/SMOKE.md` |
| Feature branch | `feat/DOG-SMOKE-1-write-docs-dogfood-smoke-md` |
| PR | https://github.com/andrewcostello/claude-dispatcher/pull/54 |

### Provenance (YAML row after run)

- `agent: grok`
- `model: grok`
- `agent_version: grok 0.2.99 (b1b49ccb71a7) [stable]`
- `mechanical_verification: passed`

### Preflight

- `no_claude: true`
- `implementer_binary: grok` ok
- Tasker role file missing → **warning only** (expected)

### Notes / follow-ups

1. First spawn sometimes exits without commits → dispatcher **commit-retry** recovered (Grok may leave dirty tree inconsistently; auto-commit path helps).
2. Push/PR recovery fired once (stale remote tip from prior smoke) then recovered.
3. Genesis still serializes some resolved flags oddly (`implementer: null` while task pins grok); runtime behavior was correct. Optional cleanup later.

## Prior run: `dogfood-smoke-20260713T060608Z`

Also **Done** with model `grok`, but incorrectly stamped `agent: claude` (hard-coded provenance). Fixed in later commits before the second smoke.

## Rerun smokes at the reconciled head (2026-07-13, post PR #56 reviews)

Both unattended smokes re-run against the merged tree (grok-first + 20
main-line commits + two review rounds of fixes) before merging PR #56.

| Field | Grok rerun | Claude rerun |
|-------|------------|--------------|
| Run ID | `grok-smoke-rerun-20260713a` | `claude-smoke-rerun-20260713a` |
| Flags | `--no-claude --cross-family-panel never` | default path, panel never |
| Status | **Done** | **Done** |
| Mechanical gate | passed (full pytest) | passed (full pytest) |
| Provenance | `agent: grok`, `agent_version: grok 0.2.93` | `agent: claude`, `claude-fable-5` |
| Commit-retry | none | **none** (pre-fix run needed one) |
| Cost | — | ~$1.60 (pre-fix run: ~$2.30) |
| Marker PR | #57 | #58 |

Key deltas proven live vs the 2026-07-13 morning smokes:
1. The commit-your-work brief eliminates the guaranteed commit-retry detour
   on the Claude path (one spawn instead of two; ~30% cheaper).
2. `--no-claude`/`--implementer` provenance stamps the implementer's own CLI
   version (was: Claude's version on grok rows via the resume/version-capture
   divergence).

## Batch + design smokes (2026-07-13, post PR #56/#59, pipx binary)

| Field | Batch smoke | Design smoke |
|-------|-------------|--------------|
| Run ID | `batch-smoke-20260713a` | `design-smoke-20260713a` |
| Feature | `_take_batch_group` (2 tasks, one `batch_id`) | `--enable-design-stage` + `design: true` |
| Status | **Both rows Done** (one session/branch/PR #60) | **Done** (PR #61) |
| Mechanical gate | passed | passed |
| Cost | $1.41 (billed to primary row only) | $3.06 ($1.46 design + $0.76 impl + $0.85 push-retry) |
| Notes | both markers in one commit; combined prompt executed both | design spawn journaled `spawn_kind=design`; recommendation parse empty (format follow-up) |

Follow-ups surfaced: design-worker Recommendation block format compliance
(parser got verify/panel/selected = None); one push-retry on the design run.
