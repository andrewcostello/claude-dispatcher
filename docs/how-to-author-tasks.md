# How to author a dispatcher task list

**Audience:** humans and planning agents that turn a feature idea into a
runnable `tasks.yaml` (+ PRD) for `claude-dispatcher`.

**Not for:** implementers filling bodies under `dispatcher run`. They already
get a thin worker brief — see
[architecture/single-orchestrator.md](./architecture/single-orchestrator.md).

**Companion docs:**

| Doc | Role |
|-----|------|
| [contract-first-deviation-model.md](./contract-first-deviation-model.md) | Why skeleton first; deviations |
| [templates/PRD-template.md](./templates/PRD-template.md) | Feature intent oracle |
| [templates/planner-prompt.md](./templates/planner-prompt.md) | Paste-this prompt for a planning agent |
| [task-batching.md](./task-batching.md) | `batch_id` mechanics |
| [agent-routing-policy.md](./agent-routing-policy.md) | Cheap vs hard agents |
| [feature-review-loop.md](./feature-review-loop.md) | Feature → main adversarial review |

---

## Goal

Produce a plan the dispatcher can execute without re-architecting mid-run:

1. **Skeleton** — contracts, seams, tests-as-DoD (human or strong planner).
2. **Task graph** — one mergeable unit per task; `blockedBy` from real deps.
3. **Batching** — shared context only; never hide serial ownership.
4. **Quality knobs** — `verify` / `panel` / `effort` / `agent` match risk.
5. **Sanity** — dry-run plan waves look right before spending tokens.

Bad YAMLs waste more money than missing CLI flags. Prefer a smaller, sharper
graph over a long wish-list of 6h mega-tasks.

---

## Phase A — Skeleton (before the leaf tasks)

### When you need a real skeleton

Ship a skeleton (types + state machine + data-flow + contract tests) when any of:

- Shared interfaces multiple tasks will implement against
- Money / auth / settlement / irreversible side effects
- A state machine or multi-screen flow with real invariants
- Size L/XL work that would otherwise become one unreviewable blob
- You have already thrash-failed once on implicit architecture

### When you can skip or thin the skeleton

- XS/S docs, glue, pure UI polish on stable APIs
- One-shot smoke tasks (`DOG-SMOKE-*`)
- Bugfix with an already-correct contract in-tree

### Skeleton task shape

Put foundation in **wave 0**, often one task:

```yaml
  - key: FEAT-0-1
    summary: "Skeleton: types, seams, contract tests (bodies stubbed)"
    description: |
      Author (or extend) the load-bearing contracts:
        - types/interfaces for X, Y
        - state machine transitions for Z
        - contract tests that FAIL on empty/stub bodies where bodies are out of scope
      Bodies may be `notImplemented` / minimal stubs so dependents compile.

      Out of scope: full product UI, production polish, feature-complete paths.

      Acceptance:
        - contract tests exist and name the invariants
        - dependents can typecheck against exported seams
        - no Math.random / unseeded I/O if repo forbids it
    type: Task
    estimate: 2h
    labels: [size:M, area:skeleton, area:core]
    blockedBy: []
    effort: high
    verify: mechanical   # or llm if contracts are subtle
    panel: single        # or full for money/auth skeletons
```

**Rule:** the skeleton generates the plan. Call-graph edges and data-flow
seams *are* your `blockedBy` edges. Do not invent a parallel “story points”
DAG that disagrees with the code seams.

Human reviews the skeleton hard; leaf bodies are skim-able when they conform.
See contract-first for **deviations** when a leaf must change a shared type.

---

## Phase B — Task graph

### One task = one primary seam

Each task should own **one** of:

- A module/file cluster with a clear contract test, or
- A vertical slice that can merge without rewriting siblings, or
- A pure docs/certification artifact

**Split** when a row would take >~2h, touch money + UI polish, or own two
independent seams (ASCENT rewrote one 6h task into 1-1…1-5 for this reason).

**Merge** only when splitting would force thrashing on the same 20 lines with
no independent DoD (then prefer `batch_id` — Phase C).

### Required YAML fields

Validated by `plan.load_tasks`:

| Field | Required | Notes |
|-------|----------|--------|
| `key` | yes | Unique; stable (`EPIC-wave-n` style) |
| `summary` | yes | One line; shows in status/PRs |
| `description` | yes | Scope, out-of-scope, **Acceptance** |
| `type` | yes | Often `Task` / `feature` (string; free-form today) |
| `labels` | yes | **Must** include `size:XS\|S\|M\|L\|XL` |
| `blockedBy` | no | List of keys; unknown key → validation error |
| `status` | no | Default `To Do` |
| `agent` | no | `claude` \| `codex` \| `grok` \| `gemini` |
| `effort` | no | `low` \| `medium` \| `high` |
| `batch_id` | no | Reserved: accepted-but-inert today (no grouping yet — see task-batching.md banner) |
| `verify` | no | `none` \| `mechanical` \| `llm` \| `llm_strict` |
| `panel` | no | `never` \| `auto` \| `single` \| `full` \| `always` |
| `design` | no | `true`/`false` force design stage; else heuristics |
| `model` | no | Claude model pin only; ignored for non-Claude agents |

Top-level (recommended):

```yaml
prd: features/<feature>/PRD.md
project: <repo-or-product>
epic: <feature-slug>          # also names default feature/ branch in pr mode
base_branch: main             # optional; CLI can override
```

### Description template (every non-trivial task)

```text
LAW / contract first: <paths to binding docs or skeleton files>

Scope:
  1. …
  2. …

Out of scope:
  - …

Acceptance:
  - <command> green (e.g. npm test / pytest)
  - <named test or observable behavior>
  - <negative: what must NOT appear>
```

Implementers under the dispatcher are **workers**. Do not tell them to adopt
Tasker, open the feature PR, or re-plan the epic.

### Dependencies (`blockedBy`)

- Edge exists only if the dependent **needs code or contracts** from the
  dependency to compile/test.
- In **branch** mode, dependents run when deps are `Done`.
- In **pr** mode, `Done` / `Awaiting Review` / `Merged` all satisfy dispatch
  ordering (commits reach dependents via dependency merge) — but **serial
  merge** of PRs into the feature branch still matters for shared files;
  prefer non-overlapping file ownership in parallel waves.
- No cycles (dispatcher rejects).
- Prefer shallow graphs: wave 0 foundation → wave 1 parallel surfaces →
  wave 2 polish/cert.

### Labels (beyond size)

Useful conventions (not all enforced):

| Label | Use |
|-------|-----|
| `size:XS…XL` | Required; drives design/quality heuristics |
| `area:core` / `area:skeleton` / `area:docs` / `area:game` | Routing + design |
| `risk:high` / class markers | Operator signal; pair with verify/panel |
| `security` / `auth` / `financial` / `critical` | HARD routing triggers |
| `dogfood` / `smoke` | Operator filtering |

Quality **floors** (when task does not pin `verify`/`panel`) rise with risk
tier — see `quality_levels.py`. Explicit task fields always win.

### Verify / panel defaults (practical)

| Kind of work | `verify` | `panel` |
|--------------|----------|---------|
| Docs, glue, pure polish | `mechanical` | `never` |
| Leaf with good unit tests | `mechanical` | `never` or `auto` |
| Money / legal / Class R core | `llm` or `llm_strict` | `full` or `single` |
| Skeleton / new shared API | `mechanical` or `llm` | `single`+ |
| Smoke / dogfood | `mechanical` | `never` |

`panel: single` under multi-family fleets prefers a reliable seat (e.g. codex);
reduced panels can approve with one valid seat. Still pin `never` for pure
mechanical leaves to save cost.

### Agent / effort

- Default implementer is **claude** unless run uses `--no-claude`,
  `--implementer`, `--cheap-first`, or per-task `agent:`.
- Bounded leaves → `grok` + `effort: medium` is a proven cheap default.
- Shared skeleton / hard state → `claude` or `effort: high` (see routing policy).
- Do **not** put Claude model pins on Grok-only fleets; non-Claude agents ignore them.

---

## Phase C — Batching

> **Batching is NOT YET IMPLEMENTED** — `batch_id` is accepted and
> validated but has no runtime effect today; every task runs alone.
> Author batches for forward-compatibility only, and do not rely on
> shared-session cost savings or all-or-nothing batch status.

Full mechanics (design): [task-batching.md](./task-batching.md).

### Batch when

- Tasks touch the **same module** and share exploration tax
- Second task only makes sense in the same session as the first’s dirty tree
- Combined scope still fits one focused session (~same as one M task)

```yaml
  - key: FEAT-2-1
    batch_id: feat-hud-polish
    …
  - key: FEAT-2-2
    batch_id: feat-hud-polish
    …
```

### Do **not** batch when

- Strict serial contract ownership (A must merge and be reviewed before B)
- Different risk floors (money core + random CSS) — gate/panel apply to **all**
  members of the batch; one failure blocks the whole batch
- Tasks would exceed a sane context (split waves instead)
- You need independent PR/review surfaces for each row in pr mode

### Batch + blockedBy

Members of a batch should be co-runnable (same wave). Do not put
`blockedBy: [sibling-in-same-batch]` for ordering you expect the agent to
respect inside one session — write ordered Scope steps in the descriptions
instead, or unbatch.

---

## Phase D — PRD + integration mode

### PRD

Copy [templates/PRD-template.md](./templates/PRD-template.md) →
`features/<feature>/PRD.md` (or repo-local path). Point YAML at it:

```yaml
prd: features/<feature>/PRD.md
```

Feature review (when enabled) judges the **cumulative** feature branch against
this file. Keep contracts, acceptance, non-goals current.

### Branch vs PR-flow

| Mode | Use |
|------|-----|
| `branch` (default) | Classic; task branches from base; optional auto-integrate |
| `integration: pr` | Task PRs → shared `feature/<epic>`; human only on feature→main after review |

For product demos (ASCENT-style), prefer **pr** + `--feature-review` and state
that in the YAML header comments so operators copy the right CLI.

Header comment block (recommended):

```yaml
# Recommended run:
#   dispatcher run path/to/tasks.yaml \
#     --mode unattended --max-parallel 2 \
#     --integration pr --feature-branch feature/<epic> \
#     --base-branch main --feature-review \
#     --cross-family-panel auto
```

---

## Phase E — Sanity checks before spend

```bash
# Schema + waves only (no agents)
dispatcher run path/to/tasks.yaml --mode dry-run

# Optional: only first wave
dispatcher run path/to/tasks.yaml --mode dry-run --only KEY1,KEY2
```

Checklist:

- [ ] Every task has `size:` and Acceptance
- [ ] `blockedBy` keys resolve; no cycles
- [ ] Wave 0 is skeleton/foundation only if needed
- [ ] Parallel wave tasks do not all edit the same hot files
- [ ] High-risk rows pin stronger `verify`/`panel`
- [ ] Batches share `batch_id` for the right reason
- [ ] `prd:` exists for feature-review runs
- [ ] No Tasker / “open the epic PR yourself” language in descriptions
- [ ] Grok fleets: `agent: grok` or `--no-claude`, no Claude-only assumptions

---

## Annotated mini example

Contract-first + one high-risk core + two parallel leaves + optional batch on polish.

```yaml
prd: features/demo-pad/PRD.md
project: demo-pad
epic: demo-pad
base_branch: main

tasks:
  # Wave 0 — skeleton
  - key: PAD-0-1
    summary: "Skeleton: PadState machine + contract tests"
    description: |
      Author src/pad/types.ts + state transitions + tests/pad-contract.test.ts.
      Bodies for UI may stub. Acceptance: contract tests fail on empty machine.
    type: Task
    estimate: 90m
    labels: [size:M, area:skeleton, area:core]
    blockedBy: []
    effort: high
    verify: mechanical
    panel: single

  # Wave 1 — high-risk core (serial after skeleton)
  - key: PAD-1-1
    summary: "Ledger seals stake × settle; no synthetic credits"
    description: |
      Implement vault math against PAD-0-1 contracts.
      Acceptance: vault_total === sum(settlements) test; no Math.random.
      Out of scope: Pixi polish.
    type: Task
    estimate: 90m
    labels: [size:S, area:core, risk:high]
    blockedBy: [PAD-0-1]
    effort: high
    verify: llm
    panel: full

  # Wave 1b — parallel UI leaves after money core
  - key: PAD-1-2
    summary: "Altitude curve from fixture marks"
    description: |
      Wire mark path to view model. Acceptance: samples match fixture tape.
    type: Task
    estimate: 60m
    labels: [size:S, area:game]
    blockedBy: [PAD-1-1]
    verify: mechanical
    panel: never

  - key: PAD-1-3
    summary: "Purchase ticket fee line verbatim"
    description: |
      Fee string pinned by test. Acceptance: "$A+$B" form matches constants.
    type: Task
    estimate: 45m
    labels: [size:S, area:game]
    blockedBy: [PAD-1-1]
    verify: mechanical
    panel: never

  # Wave 2 — batch polish (same HUD module)
  - key: PAD-2-1
    summary: "HUD spacing + type scale"
    description: |
      CSS/tokens only. Acceptance: build green; no game-logic changes.
    type: Task
    estimate: 30m
    labels: [size:XS, area:ui]
    blockedBy: [PAD-1-2, PAD-1-3]
    batch_id: pad-hud-polish
    verify: mechanical
    panel: never

  - key: PAD-2-2
    summary: "Help control + first-run copy hook"
    description: |
      DOM control only; no new state machine. Acceptance: control present in DOM test.
    type: Task
    estimate: 30m
    labels: [size:XS, area:ui]
    blockedBy: [PAD-1-2, PAD-1-3]
    batch_id: pad-hud-polish
    verify: mechanical
    panel: never
```

Real-world reference (richer, production-shaped):
`awevoke/game-ascent/ascent-tasks.yaml` — foundation Merged, Class R core with
`verify: llm` + `panel: full`, parallel S leaves mechanical, PR-flow header.

Dogfood micro-tasks (thin, mechanical):
`features/grok-dogfood/tasks.yaml` and `features/grok-dogfood/claude-smoke.yaml`.

---

## Anti-patterns

| Anti-pattern | Why it hurts | Do instead |
|--------------|--------------|------------|
| One task: “implement the feature” | Unreviewable; wrong architecture thrash | Skeleton + graph |
| Description without Acceptance | LLM verifier + humans guess | Named tests/commands |
| Fake `blockedBy` for storytelling | Deadlocks / false serial | Edges from compile/test need |
| Batch money + CSS | One panel failure sinks polish | Separate risk floors |
| Parallel tasks on same hot file | Merge hell in pr mode | Serial or single owner |
| “Adopt Tasker / open epic PR” | Two orchestrators | Thin worker scope only |
| `size:L` leaf with `panel: never` | Underruns quality floor | Match risk or explicit override + know why |
| Silent shared-type change in a leaf | Breaks dependents | Deviation record + maybe unblock |

---

## Planner agent output contract

When an agent authors the plan, deliver:

1. `features/<feature>/PRD.md` (from template)
2. `features/<feature>/tasks.yaml` (or repo-local path)
3. Short **wave map** in the PR/summary (wave 0 / 1 / 2 + batch ids)
4. Recommended `dispatcher run …` command (mode, integration, panel, agent fleet)
5. Explicit list of **open design risks** the human should review before run

Then stop. Do not start implementer work unless asked — planning is a different
job from filling bodies.

Paste-ready instructions: [templates/planner-prompt.md](./templates/planner-prompt.md).
