# Grok-first dogfood + single-orchestrator restructure — Implementation Plan

> **Operator:** Grok Build (this session / future Grok sessions) *or* any
> supervising agent/human.  
> **Subject system:** `claude-dispatcher` dogfooding itself.  
> **Architectural rule:** The **dispatcher is the only orchestrator** for
> `dispatcher run`. Agents are **workers** (implement / design / verify /
> review). **No Tasker role under dispatch** — including when Claude is the
> implementer.  
> **Hard constraint (dogfood):** Once the Grok-only runtime lands, a full
> dogfood loop must run with **zero Claude CLI invocations** unless a task
> explicitly pins `agent: claude`.

**Goal:** (1) Restructure dispatched execution so orchestration lives only in
the dispatcher and every family (Claude, Grok, …) is a thin worker; (2) make
Grok a first-class implementer *and* operator so we dogfood the dispatcher
without Claude on the path; (3) progressively enhance quality, metering, and
UX.

**Architecture:**

```text
tasks.yaml + PRD/skeleton
        │
        ▼
┌───────────────────────────────────────┐
│           DISPATCHER (only loop)      │
│  worktree · [design?] · implement     │
│  mechanical gate · verifier · panel   │
│  cascade · PR/merge · journal         │
└───────────────┬───────────────────────┘
                │ spawn workers only
     design-agent   implementer   verifier   reviewers
     (optional)    (grok|claude|…)  (any)    (multi-family)
```

- **Claude remains first-class** as an *implementer* (and optional verifier /
  panel seat / cascade terminal). It does **not** re-run Tasker orchestration
  inside the spawn.
- **`tasker.md` stays** for **interactive** Claude Code / future Grok TUI
  sessions **without** the dispatcher (`/work-ticket`, standalone).

**Tech stack:** Python 3.11+ dispatcher, Grok CLI, optional Claude CLI, git
worktrees, pytest, `claude-workflow` roles as *worker* prompts.

**Non-goals:**
- Deleting Claude support or forcing all product repos to Grok-only.
- Porting full `tasker.md` prose into Python (stages + thin prompts only).
- Interactive Tasker replacement in Grok TUI (optional later track).
- Renaming the package (`claude-dispatcher` → …) — optional later.

---

## Why this restructure (even when Claude implements)

| Old path | Problem |
|----------|---------|
| Dispatcher → Claude “adopt Tasker” → Tasker re-orchestrates | Two orchestrators, double panel risk, wasted tokens |
| Grok thin implementer / Claude thick Tasker | Unequal contracts; Grok unfairly compared |
| Quality owned partly by in-session Tasker | Non-deterministic; hard to journal |

**Rule:** If a job is “decide what happens next,” it belongs in the dispatcher.
If a job is “produce code / a design / a verdict,” it belongs in a worker spawn.

---

## Success criteria

### A. Single-orchestrator (all implementers)

1. `build_prompt(agent="claude")` does **not** instruct reading `tasker.md`.
2. Claude and Grok implementer prompts share the same job shape (implementer
   brief; optional design attached by dispatcher).
3. Preflight does **not** require Tasker role file unless interactive tooling
   is involved (dispatched runs: optional).
4. Existing suite green; Claude implementer path still works end-to-end.

### B. Grok-only dogfood

```bash
dispatcher run features/grok-dogfood/tasks.yaml \
  --mode unattended --no-claude --max-parallel 2
dispatcher status <run-id> --json
dispatcher report <run-id>
```

1. Zero `claude` process activity unless pinned.
2. Tasks Done or Blocked with real reasons.
3. ≥1 dogfood improvement lands via the loop.

---

## Current baseline (honest)

| Capability | State |
|------------|--------|
| Grok implementer prompt | Agent-native (no `tasker.md`) ✅ |
| Claude implementer prompt | **Still Tasker** ❌ |
| `effort` + quality cascade | Present; cascade terminal still Claude by default |
| Mechanical gate / panel / PR / journal | Dispatcher-owned ✅ |
| Design agent stage | **Missing** (was Tasker-only) ❌ |
| LLM verifier | Always Claude CLI |
| Preflight | Claude + Tasker-centric |
| Summary | Agent-written; synthetic for cross-family |

---

## Phase map

```
Phase 0   Operator loop + dogfood YAML scaffolding
Phase 1   ★ Single-orchestrator restructure (all agents)   ← core restructure
Phase 2   Grok-only runtime (--no-claude, preflight, usage)
Phase 3   Dogfood wave: improve dispatcher via dispatcher
Phase 4   Quality: pluggable verifier + panel without requiring Claude
Phase 5   Optional design stage (Critical/High)
Phase 6   Operator UX (watch, needs_attention)
Phase 7   Fleet defaults (routing as code) + policy refresh
Phase 8   claude-workflow dual-runtime docs/roles
```

Each phase has an **exit gate**. Do not start the next until green.

---

## Phase 0 — Operator loop + scaffolding

**Goal:** Supervise runs and hold dogfood task definitions.

### Task 0.1 — Operator runbook

**Files:** Create `docs/dogfood/GROK_OPERATOR.md`

**Contents:** prerequisites, install, start/status/resume/report, Claude-leak
detection (`pgrep`, journal `agent`), triage, pointer to single-orchestrator
rule (“dispatcher is Tasker; workers only implement”).

**Exit gate:** Grok or human can dry-run without inventing flags.

### Task 0.2 — Dogfood feature skeleton

**Files:**
- Create: `features/grok-dogfood/tasks.yaml`
- Create: `features/grok-dogfood/PRD.md`

**Initial rows (XS/S, `agent: grok`):**
- `DOG-0-1` — `docs/dogfood/README.md` → runbook
- `DOG-0-2` — pytest: **both** `agent=grok` and `agent=claude` prompts omit
  `tasker.md` (locks restructure invariant; may fail until Phase 1)

**Exit gate:** `dispatcher run … --mode dry-run` plans successfully.

---

## Phase 1 — Single-orchestrator restructure ★

**Goal:** Under `dispatcher run`, **no agent adopts Tasker**. Claude is an
implementer worker like Grok. Missing Tasker *orchestration* is either already
in the dispatcher or deferred to explicit stages (Phase 5 design).

### Task 1.1 — Unified implementer prompt for all families

**Files:**
- Modify: `src/claude_dispatcher/spawn.py` (`build_prompt`, remove
  Claude→Tasker branch)
- Prefer load from workflow file if present:
  `.claude/workflow/roles/implementer.md` (or `coder.md` with a thin wrapper)
- Fallback: embed `IMPLEMENTER_PROMPT` (today’s cross-family brief), including
  Claude
- Test: `tests/test_implementer_prompts_effort_panel.py` — assert **no**
  `tasker.md` for claude/grok/codex/gemini
- Test: update any test that expected Tasker wording for Claude

**Behavior:**
- Same job: implement task in CWD, tests if feasible, summary path, no PR/push.
- Optional prefix blocks injected by dispatcher only:
  - prior cascade failure context (exists)
  - approved design spec (Phase 5)
  - panel/verifier fix lists (exists on iterate)

**Exit gate:** Unit tests green; Claude spawn prompt has no Tasker adoption.

### Task 1.2 — Dispatcher owns summary contract

**Files:**
- Modify: `spawn.py` synthetic summary + orchestrator Done path
- Modify: `summary.py` if needed
- Docs: note in runbook

**Behavior:**
- Prefer agent-written summary when present and parseable.
- If missing/malformed but commits + mechanical gate green: dispatcher writes a
  **canonical** summary from journal facts (status, files from diff, gate
  outcome) — not only cross-family.
- Agents never write tasks YAML.

**Exit gate:** Deliberate “no summary file” Grok/Claude implementer still can
reach Done when gate green (or Blocked with clear reason).

### Task 1.3 — Preflight: Tasker file not required for dispatch

**Files:**
- Modify: `src/claude_dispatcher/preflight.py`
- Test: `tests/test_preflight.py`

**Behavior:**
- Tasker role file check: **warning** or skip for dispatched runs (implementer
  prompt is self-contained / implementer.md).
- Claude permission flags: only if any cascade rung uses Claude.
- Keep git / dispatcher install checks.

**Exit gate:** Preflight PASS without `.claude/workflow/roles/tasker.md` when
using implementer-only prompts.

### Task 1.4 — Kill dual-orchestration docs in-repo

**Files:**
- Modify: `README.md` (dispatcher) — dispatched agents are implementers
- Modify: `Claude.md` / experiment notes if they imply Tasker-under-dispatch
- Create: `docs/architecture/single-orchestrator.md` (1–2 pages: diagram + rules)

**Exit gate:** New contributor reads one doc and understands Tasker ≠ dispatch.

### Task 1.5 — Regression smoke (Claude implementer, no Tasker)

**Manual / scripted:**
```bash
dispatcher run features/grok-dogfood/tasks.yaml \
  --only DOG-0-2 --implementer claude --mode unattended \
  --claude-extra-args '…permissions…'
```
(or a hermetic fake_claude test that asserts prompt content)

**Exit gate:** Claude implementer completes a tiny task without Tasker phases;
mechanical gate still enforces quality.

### Phase 1 exit gate (all of)

- [ ] No `tasker.md` in any implementer prompt
- [ ] Claude + Grok share implementer job shape
- [ ] Full pytest suite green
- [ ] Architecture doc landed

---

## Phase 2 — Grok-only runtime

**Goal:** Complete runs with Claude off PATH (dogfood honesty).

### Task 2.1 — `--no-claude` / cascade terminal config

**Files:** `repo_config.py`, `cli.py`, `orchestrator.py` `RunConfig`,
`.dispatcher.yaml`, tests

```yaml
implementer: grok
cascade:
  terminal: grok    # dogfood; production may use claude
```

`--no-claude`:
- default implementer grok if unset
- `cascade.terminal = grok`
- force `haiku_summary=False`
- verifier: skip or non-Claude (Phase 4)
- preflight: do not require Claude binary

### Task 2.2 — Cascade never appends Claude when terminal=grok

**Files:** `orchestrator.py` `_implementer_cascade`, `tests/test_agent_fallback.py`

### Task 2.3 — Doctor/preflight Grok binary + version capture

**Files:** `doctor.py`, `preflight.py`, `spawn.capture_agent_version` per family

### Task 2.4 — Grok usage parse (`--output-format json`)

**Files:** `spawn.py`, `tests/test_spawn_usage.py`, fixture from one real capture

### Task 2.5 — Hermetic `fake_grok` for CI

**Files:** `tests/fixtures/fake_grok.py`, wire into no-Claude integration tests

### Task 2.6 — Manual PATH-sans-claude smoke

**Exit gate:** Unattended dogfood smoke Done with no `claude` binary.

---

## Phase 3 — Dogfood wave (dispatcher improves itself)

**Goal:** ≥3 real improvements via `dispatcher run --no-claude`.

### Task 3.1 — Expand `features/grok-dogfood/tasks.yaml`

Contract-first S/M tasks, e.g.:
- finish any Phase 2 gaps not hand-landed
- report cheatsheet for grok implementer
- cascade/unit locks
- docs polish

Rules: `agent: grok`, no HARD labels until Phase 4 panel is Claude-free;
tests as acceptance.

### Task 3.2 — Operator loop protocol (in runbook)

plan YAML → run → status/watch → fix/resume → review diffs → pytest → next

### Task 3.3 — Integration: feature branch `dogfood/grok-first`

Not main until suite green.

**Exit gate:** ≥3 tasks landed through dispatch; human/Grok merges feature branch.

---

## Phase 4 — Quality workers (still no second orchestrator)

**Goal:** Verifier + panel as pluggable workers; Claude optional.

### Task 4.1 — Pluggable verifier

- `verifier_agent: claude|grok|none` in config
- Same VERIFIED/INCOMPLETE contract
- `--no-claude` ⇒ `grok` or `none` (mechanical-only)

### Task 4.2 — Panel seats without requiring Claude

- no-Claude / config: authoritative `grok` + `codex` + `gemini` (available only)
- keep corroboration consensus
- Claude seat remains default when Claude is in the fleet

### Task 4.3 — Done requires evidence

Cross-family auto-commit OK; Done requires mechanical green (else cascade/Block).

**Exit gate:** Risk-labeled dogfood task can panel+verify without Claude binary.

---

## Phase 5 — Optional design stage (extract last Tasker gap)

**Goal:** Critical/High design without Tasker-in-session.

### Task 5.1 — Dispatcher stage `design` (config-gated)

**When:** label risk critical/high or `design: true` on task, and not
`SKIP_DESIGN`.

**Flow:**
1. Spawn worker with `.claude/workflow/roles/design-agent.md` (any agent family
   configurable; default claude if available else grok).
2. Parse 2–3 designs or raw markdown.
3. Selection: supervised → human; unattended → heuristic or first design +
   journal `design_selected`.
4. Attach `### Approved Design Spec` to implementer prompt.
5. Journal design artifact under `run_dir/<key>/design.md`.

**Not in scope:** Full financial sub-agents inside design — keep design-agent
role as the worker.

**Exit gate:** One Critical-labeled fixture task shows design.md + implementer
prompt contains approved spec.

---

## Phase 6 — Operator UX

### Task 6.1 — `dispatcher watch <run-id>`

Tail journal; compact events; exit non-zero on Blocked when run ends.

### Task 6.2 — `status --json` → `needs_attention[]`

### Task 6.3 — Document ntfy/Slack for Blocked-only

**Exit gate:** Operator loop uses watch + needs_attention only.

---

## Phase 7 — Fleet defaults

### Task 7.1 — `routing.py` from `docs/agent-routing-policy.md`

EASY/MEDIUM → grok cascade; HARD → claude if available else grok@high + flag.

### Task 7.2 — Refresh routing policy from dogfood evidence

### Task 7.3 — `.dispatcher.yaml` production-shaped defaults

```yaml
implementer: grok          # volume
cascade:
  terminal: claude         # quality closer when Claude installed
# dogfood: --no-claude forces terminal grok
```

**Exit gate:** Defaults documented; dogfood override still one flag.

---

## Phase 8 — claude-workflow dual-runtime

**Upstream:** `~/Project/claude-workflow` (submodule consumers).

### Task 8.1 — Add `roles/implementer.md`

Canonical worker brief; dispatcher loads it when present.

### Task 8.2 — `tasker.md` header: “Interactive only — not used under dispatcher”

### Task 8.3 — `prd-to-task-yaml` / `task-yaml-review`: `agent` + `effort` + routing

### Task 8.4 — README: Dispatched mode vs Interactive mode

**Exit gate:** Workflow README matches single-orchestrator architecture.

---

## What we explicitly will *not* put back into agents

- In-session multi-agent dispatch (Task tool as orchestrator)
- In-session cross-family panel (dispatcher panel only under dispatch)
- PR create / merge / worktree lifecycle
- Runnable-set / blockedBy planning mid-implementer

Those stay dispatcher (or pre-dispatch Planner → YAML).

---

## Testing strategy

| Layer | What |
|-------|------|
| Unit | Prompt invariants (all agents), cascade terminal, preflight, usage parse |
| Hermetic | `fake_claude` + `fake_grok` implementer-only prompts |
| Integration | no-Claude PATH smoke; Claude implementer without Tasker |
| Dogfood | Real Grok on feature branch |

---

## Risk register

| Risk | Mitigation |
|------|------------|
| Claude quality drops without Tasker ceremony | Mechanical gate + verifier + panel already own quality; design stage for Critical |
| Missing design on hard tasks | Phase 5; until then pin human PRD/skeleton in description |
| Scope creep rewriting all of tasker.md | Only implementer prompt + optional design stage |
| Claude users surprised | Docs + Claude still default cascade terminal in prod config |
| Dogfood fights WIP | Branch `dogfood/grok-first` |

---

## Execution protocol

1. **Phase 1 first (or in parallel with 0)** — restructure unlocks fair Grok *and*
   cleaner Claude; do this even if Claude remains the human’s interactive tool.
2. **Phase 2** — unlock honest Grok-only dogfood.
3. **Phase 3+** — prefer implementing via dispatcher, not hand-editing main.
4. **Chicken-and-egg:** Phase 0–2 may be interactive Grok/human; Phase 3+
   dispatched.

### Suggested sessions

```
Session A — Phase 0 + Phase 1 (restructure) + Phase 2 bootstrap
  Interactive Grok/human, TDD, branch dogfood/grok-first

Session B — Phase 3 dogfood loop
  dispatcher run --no-claude; watch; merge task branches

Session C — Phase 4–5 quality + design stage
  Still dogfood where possible
```

---

## Progress checklist

- [ ] Phase 0: runbook + dogfood YAML
- [ ] Phase 1: ★ no Tasker under dispatch; unified implementer; docs
- [ ] Phase 2: --no-claude smoke green
- [ ] Phase 3: ≥3 dispatched improvements
- [ ] Phase 4: verifier/panel without requiring Claude
- [ ] Phase 5: optional design stage
- [ ] Phase 6: watch + needs_attention
- [ ] Phase 7: routing defaults
- [ ] Phase 8: workflow package dual-runtime

---

## Open decisions (defaults)

| Decision | Recommendation |
|----------|----------------|
| Panel in early dogfood | `never` until Phase 4 |
| Cascade terminal (dogfood) | `grok` via `--no-claude` |
| Cascade terminal (prod config) | `claude` when installed |
| Verifier under no-Claude | mechanical-only first; Grok verifier next |
| Design stage agent | claude if present else grok |
| Integration | feature branch `dogfood/grok-first` |

---

## Handoff

**Plan updated:** `docs/plans/2026-07-12-grok-first-dogfood.md`

**Includes:**
1. **Single-orchestrator restructure** (Phase 1) — applies even when Claude
   implements.
2. **Grok-first dogfood** (Phases 2–3+) — no Claude on the path when
   `--no-claude`.
3. **Claude remains** implementer / cascade terminal / panel seat outside
   no-Claude mode.
4. **Tasker** reserved for interactive non-dispatch sessions only.

**Ready to execute Phase 0 + Phase 1** in this session when you say go.
