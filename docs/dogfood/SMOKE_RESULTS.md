# Unattended Grok smoke results

## Successful run: `dogfood-smoke-20260713T061016Z`

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
