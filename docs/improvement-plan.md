# Dispatcher Improvement Plan

Status: draft for review
Date: 2026-06-10

## Goal

Evolve the dispatcher from a batch task-runner into a supervised feature-delivery
pipeline: an agent starts and monitors runs, tasks flow as PRs into a feature
branch with dependency-ordered merges, no work is ever silently deferred or
falsely marked Done, model/agent capacity is managed automatically, and every
feature ends with a real-environment e2e gate and a fully-triaged adversarial
review.

## Design principles

1. **Deterministic logic lives in the dispatcher; judgment lives in the agent.**
   Merge ordering, quota circuit-breakers, risk classification, and gates are
   dispatcher code that works unattended. The supervising agent handles
   conflict resolution, triage, and refinement — things that need a brain.
2. **Execution evidence over artifacts.** A test file, a Done status, or a
   summary section proves nothing by itself. Gates consume run output, diffs,
   and recorded verdicts.
3. **No silent disposal paths.** Every review finding gets a recorded
   disposition: a fix task, or an explicit human acceptance with rationale.
   Severity-threshold auto-deferral is removed entirely.
4. **Executable config over prose.** Anything an agent must "follow" (env
   setup, gate criteria) is a command the dispatcher runs, so rot fails loudly.
5. **Record planned vs. actual.** Fallbacks, approvals, and overrides are
   journaled so the report shows what really happened, not what was intended.

---

## Phase 0 — Hygiene fixes (from code review)

Small, independent fixes; can land alongside Phase 1.

- Replace hardcoded `/home/andrew/go/bin/{sqlc,buf}` in `auto_integrate.py:37-38`
  with `shutil.which()` + env-var override + clear error.
- Replace the string-prefix worktree path check (`worktree.py:99`) with proper
  path comparison; catch and gracefully report `git worktree add` failures,
  including the concurrent same-key race.
- Summary parser logs *why* a parse failed (missing section, bad status line,
  regex miss) to the run log instead of only setting `malformed=True`.
- Make YAML lock timeout and spawn timeout configurable.
- End-to-end test for the panel-iterate loop (`orchestrator.py:396-441`),
  including iteration-exhaustion.
- Hide or mark `status`/`resume` as experimental until Phase 1 implements them.

## Phase 1 — Control surface (foundation for everything)

The supervising agent needs to observe and steer runs without scraping stdout.

- **Event journal**: append-only JSONL per run. Events include
  `task_started`, `summary_parsed`, `verification_failed`, `panel_blocked`,
  `pr_opened`, `pr_approved` (with approver identity), `pr_merged`,
  `quota_exhausted`, `fallback_used`, `finding_disposed`, `run_complete`.
  Every later phase both writes to and is reconstructable from this journal.
- **`dispatcher status --json`** (implements the stub): per-task state, current
  wave, open PRs, provider availability, cost so far, blocked-and-why.
- **`dispatcher resume`** (implements the stub): recover an interrupted run
  from the journal + YAML state.

Acceptance: an external agent can tail the journal, query status, and resume a
killed run, with no stdout parsing.

## Phase 1a — Machine profile (`dispatcher doctor`)

Machine knowledge is currently scattered and discovered lazily mid-run (panel
reviewers found `UNAVAILABLE` at spawn time, hardcoded tool paths, forecast
soft-skip). Replace with an explicit per-machine profile.

- **`dispatcher doctor`**: probes the machine and writes
  `~/.config/claude-dispatcher/machine.yaml`. Probe-derived with manual
  overrides; re-run after installing anything. Discovers:
  - Agent CLIs (`claude`, `agy`, `codex`): path, version, auth state, whether
    a stats/quota command is supported.
  - Tools: `git`, `gh`, `docker`, `sqlc`, `buf` — path + version via
    `shutil.which()`.
  - Capabilities: can this machine run the e2e gate (docker present, etc.).
  - **Dispatcher install mode + staleness** (lesson from dogfood run #2):
    the running `dispatcher` may be a pipx snapshot while fixes land in the
    repo. `doctor` records install method and version; preflight warns when
    the installed version is older than the repo HEAD it's dispatching.
- **Run-start preflight**: at plan time, intersect the run's requirements
  (every preferred agent + fallback across tasks, panel reviewer families,
  e2e tooling) with the profile. Missing pinned agent → fail before anything
  spawns. Missing fallback → warning with affected task count.
- **Preflight checks proven necessary by dogfood run #1 (2026-06-10)**, where
  both failures burned a full silent wave: (a) unattended/supervised live
  runs without permission-bypass args in the spawn command → fail fast
  (Taskers stall at the first tool-use prompt and exit with nothing);
  (b) the Tasker role file must resolve *in a freshly created worktree*, not
  just the main checkout (machine-local symlink conventions don't reach
  worktrees unless git-tracked) → verify by creating a probe worktree or
  checking the file is tracked.
- **Single consumer**: the provider registry (Phase 6) reads invocation
  details from the profile; Phase 2 agent-version metadata comes from the
  probe; `auto_integrate` tool paths come from the profile (supersedes the
  Phase 0 hardcoded-path fix as the durable solution).

Scope split: machine profile = *what this box can do*; repo config = *what
this project needs*; feature definition = *what this work changes*.

## Phase 2 — Done metadata + report rollup

- On every terminal status, write to YAML (and later sync to Jira): tokens
  (in/out/cached), cost, model, agent, agent CLI version (captured at spawn),
  planned vs. actual agent, iteration counts.
- Claude usage comes from existing JSON parsing. Gemini/Codex usage comes from
  the stats-delta mechanism in Phase 6 (snapshot provider stats before/after a
  task); until then, mark as `unmeasured` — never silently zero.
- Extend `dispatcher report` to a per-run rollup: per task and per agent —
  model, tokens, cost, iterations, verification outcomes, panel verdicts,
  approver, fallbacks used.

## Phase 3 — PR-into-feature-branch flow

New integration mode alongside direct merge: `integration: pr`.

- Each task's worktree branch raises a PR (existing `pr.py` machinery)
  targeting the **feature branch**, not main.
- New task states: `Awaiting Review` → `Merged`. Done is no longer terminal in
  this mode.
- **Mechanical merge ordering**: the dispatcher merges a PR only when it is
  approved AND all `blockedBy` dependencies are merged. Topological constraint,
  enforced in code, never eyeballed.
- **Dispatch-time dependency code** (lesson from dogfood run #2, DISP-9):
  when a dependent task dispatches before its dependencies' branches are
  integrated, its worktree must start from a merge of those branches — not
  bare base. Today this only works if the Tasker improvises the merge itself
  (DISP-9's did; relying on that is luck). The dispatcher should create the
  dependent's branch from base + merged `blockedBy` branches and record the
  merged SHAs in the journal.
- **Approval ladder** (deterministic risk classifier in the dispatcher):
  1. Supervising agent may approve **low-risk** PRs.
  2. pr-reviewer bot approves per its rule set.
  3. Everything else falls to Andrew.
- **Low-risk classifier — proposed defaults** (config-driven per repo; ALL
  conditions must hold):
  ```yaml
  low_risk:
    max_size: S                       # XS or S only
    forbidden_labels: [security, critical, financial]
    forbidden_paths:                  # any touched path disqualifies
      - "**/migrations/**"
      - "**/*.proto"
      - "**/auth/**"
      - ".github/**"                  # CI config
      - "go.mod"                      # dependency manifests
      - "go.sum"
      - "Dockerfile*"
      - "compose*.y*ml"
    max_diff_lines: 200               # EFFECTIVE lines — see counting rule
    require_first_pass_verification: true   # verifier passed with no iterations
    forbid_new_dependencies: true
  docs_only: always low-risk           # *.md-only diffs, any size
  # NOTE: test-only diffs are NOT auto-low-risk — a test change can weaken
  # assertions; they go through the normal ladder.
  ```
- **Effective-diff counting rule** (shared by this threshold and the Phase 7b
  mutation escalation): diff-line thresholds count only hand-written
  production code. Excluded from the count, via per-repo globs:
  - *Test code* — `*_test.go`, `**/testdata/**`, e2e suites — thorough tests
    on a small change shouldn't push it out of low-risk.
  - *Generated code* — `*.pb.go`, sqlc output dirs, etc. — mechanical output
    is reviewed via its source (`.proto`, `queries.sql`), which the path
    denylist already guards.
  Exclusion is for **counting only** — excluded files still ship through the
  PR, review, and gates like everything else.
  Journal records who approved every merge. The agent never approves work it
  authored or iterated on.
- Agent responsibilities (judgment): watch PR review state, nudge on stalls
  (existing notify channels), resolve rebase conflicts when an earlier merge
  invalidates a later branch.

## Phase 4 — Verification gate ("no false Done")

Distinct from code review: the panel asks *is this code good*; the verifier
asks *does this diff actually do what the task said*.

- **Mechanical checks first, agent second** (lesson from dogfood run #2,
  where the supervisor verified by hand): before spending an agent, run the
  deterministic checks — commits exist on the branch, repo test suite green
  *inside the task worktree* (repo config gains a `test:` command, sibling
  of the Phase 7a `e2e:` block; worktrees have no venv of their own, so the
  command must be self-contained). Only a mechanically-clean task earns an
  LLM verifier pass.
- After Tasker reports Done, before the panel: spawn an independent verifier
  with task description + acceptance criteria + diff + summary.
- Looks for: TODO/stub implementations, "deferred to follow-up" language,
  silent scope narrowing, untested claims.
- Verdict `verified` | `incomplete` (with specifics). Incomplete → re-spawn
  Tasker with the gaps, reusing the panel-iterate machinery; exhausted
  iterations → Blocked with the verifier's findings attached.

## Phase 5 — Refinement workflow + per-task routing

- `plan.py` rule: XL tasks are never runnable; they sit in `Needs Refinement`.
  ("No XL" is a proxy for the real invariant: every dispatched task fits one
  focused agent session.)
- New `dispatcher refine` subcommand: agent loop that decomposes XL tasks into
  S/M tasks with `blockedBy` edges, validates the graph (existing cycle
  detection), iterates with the human until no XLs remain.
- **Anti-rigidity valves** (the gate stays hard; these keep it from being
  brittle):
  - *Spike tasks*: when the seams aren't knowable up front, the refiner emits
    a time-boxed exploration task whose deliverable is the proposed
    decomposition + findings, not merged code. The gate redirects work to
    learning instead of blocking it — no premature decomposition under
    maximum ignorance.
  - *Sizing calibration*: compare actuals (tokens, duration, diff size,
    iterations) against the size label; journal `size_mismatch` events and
    surface calibration in the report. Detects label gaming and honest drift
    without blocking anything.
  - *Override = relabel, journaled*: no bypass flag. Dispatching something
    big means changing its label, and label changes are journaled events
    with actor and prior value — visible in the evidence bundle.
- Refinement also assigns **per-task routing**:
  ```yaml
  agent: claude
  model: opus
  fallbacks: [gemini, codex]   # empty list = pinned
  ```
- Standing refinement checklist question: *"does this feature change what's
  needed to run the system?"* If yes, generate a concrete env-update task
  (see Phase 7) that blocks the e2e gate.

## Phase 6 — Quota management + fallback routing

**Provider registry** with per-provider adapters exposing:

- `usage_stats()` — runs the CLI's stats command (Gemini: input/output/cached
  tokens; Codex: TBD). Called before each dispatch wave (cached a few minutes)
  and after each task. Before/after deltas give per-task usage for providers
  whose output lacks it. Concurrent tasks on one provider commingle deltas →
  mark those numbers `approximate` rather than serializing and losing
  parallelism.
- `quota_state()` — interprets limit signals ("hit your limit for the day" →
  breaker open until daily reset; Claude → rolling 5h window; Codex → *fully
  structured, researched 2026-06-10*: rolling 5h + weekly windows exposed as
  `used_percent` with `resets_at` Unix timestamps in the session rollout file
  (`~/.codex/sessions/.../rollout-*.jsonl`, keyed by `thread_id` from the
  `thread.started` event — never use `--ephemeral`, it disables this).
  Per-turn token usage (input/cached/output) is in `codex exec --json`
  stdout. Limit hit = `usage_limit_exceeded` error with reset time, exit 1.
  The Codex breaker can be *predictive* — open it when `used_percent` nears
  100 instead of waiting for a failed spawn — and supports **API-key
  overflow**: re-spawn with `CODEX_API_KEY` (pay-per-token, no windows) when
  subscription quota is exhausted, as an explicit config opt-in.

**Scheduler behavior**: skip providers with open breakers; route to the task's
fallback list if allowed; otherwise the task *waits* (not Blocked) with the
known reset time surfaced in `status`. (Phase 10 inserts a tier ahead of
family fallback: same preferred agent on another host with capacity.)

**Fallback policy (role-dependent):**

| Role | Fallback? |
|---|---|
| Tasker, ordinary S/M work | Yes, per task's `fallbacks` list |
| Tasker, panel-trigger labels (security/critical/financial) | Pinned, no substitution |
| Tasker continuing another task's work | Pinned (context/style continuity) |
| Panel reviewer | Never — and never into the author's family. Wait for reset or escalate. |

Rationale: implementation fallback is safe because the verification gate and
panel sit behind it; reviewer substitution silently collapses cross-family
independence, which is the panel's entire value.

**Probationary (advisory) reviewer tier** — how new agents enter the fleet:

- An advisory reviewer runs in every panel but its verdict **never counts
  toward consensus**, and its findings **do not enter no-deferral triage**
  (no back-door authority) — they ride along as a journaled appendix a human
  can manually promote.
- Adapter failure of an advisory reviewer = journaled, run unaffected —
  which makes beta-quality CLIs safe to adopt early.
- Every run feeds a **per-reviewer scorecard**: agreement with final
  consensus, agreement with ground truth (findings that became real fix
  tasks; approvals that later failed mutation checks), availability. The
  scorecard also measures the authoritative reviewers retroactively.
- **Promotion is an explicit, journaled human decision** once earned
  (guideline: ~30 panel runs, high consensus agreement, low false-block
  rate, ≥95% availability). Demotion is symmetric. All future fleet
  candidates enter through probation; nobody starts authoritative.
- **First probationer: Grok Build (xAI)** — adds a fourth model family.
  SuperGrok subscription already in place (2026-06-10). Sole remaining
  prerequisite: spike to confirm the headless contract (`-p`,
  `--always-approve`, stream-json — partly UNCONFIRMED secondary sources).

## Phase 7 — E2E gate (real, no-mock) + test quality review

Runs after all PRs merge to the feature branch, **before** the final
adversarial review (the panel should review a feature already proven to run).

**7a. Environment config — two layers:**

- *Repo-level baseline* (executable, lives in dispatcher config):
  ```yaml
  e2e:
    up: docker compose -f compose.e2e.yaml up -d
    ready: ./scripts/wait-healthy.sh
    seed: make seed-e2e
    down: docker compose -f compose.e2e.yaml down -v
    frameworks:
      "type:api": karate
      "type:ui": playwright
  ```
- *Feature-level deltas*: optional `environment:` section in the feature
  definition declaring new services/env vars/seed data; the refine step turns
  deltas into a dispatched env-update task. The e2e gate is the enforcement —
  missing env work means the suite can't go green, and no-false-Done means the
  feature can't close.

**7b. The gate itself:**

1. **Authoring**: a test-author task is generated (or verified to exist) per
   feature; framework selected by work-type labels; both for full-stack.
2. **No-mock enforcement**: static scan for mocking frameworks / stub servers
   in test code, plus the suite must run green against the actually-provisioned
   environment. *Run output* is the gate evidence in the journal — file
   existence counts for nothing.
3. **Test quality review**: a reviewer agent checks assertion quality, plus a
   **mutation check**: an agent in a throwaway worktree plants one deliberate,
   plausible bug; the suite must go red. A suite that stays green with a
   planted bug is decorative.
   - **Budget**: 1 mutation per feature by default. Escalate to 3 when ANY of:
     panel-trigger labels on the feature; feature diff > ~1,500 **effective**
     lines (Phase 3 counting rule — test and generated code excluded); any
     per-task panel block occurred during the run; or this feature introduces
     the repo's e2e suite (first suite = least trusted).
   - **Survived mutation = blocking finding**: generate fix tasks for the test
     gaps, then re-run with a *fresh* mutation (never the same one — the goal
     is a suite that catches bugs, not that bug) until one is caught.

Test-review findings feed the same no-deferral triage as Phase 8.

## Phase 8 — Final adversarial review + no-deferral triage

- After the e2e gate passes: cross-family panel over the **whole feature diff**
  (feature branch vs. base) with a more adversarial prompt and larger budget
  than per-task review.
- **Every finding gets a recorded disposition** — either a generated fix task
  appended to the run (flowing through normal dispatch → verify → review → PR),
  or an explicit acceptance by a named human with a one-line rationale, written
  to the journal and Jira. "Medium and below auto-defer" is removed.
- Loop until the panel is clean or all remaining findings carry explicit
  acceptances.

## Phase 9 — Jira integration extensions

> **Decision — state layer (2026-06-10).** Considered moving the system of
> record from YAML+journal to Jira or a custom web tool. Rejected: Jira as
> store couples dispatch to network/availability and loses git-reviewable,
> commit-pinned task breakdowns plus local-file testability; a custom tool is
> a second product with its own bus factor. Instead: YAML+journal stays
> authoritative; Jira gets two narrow channels — (1) one-way authoritative
> sync dispatcher→Jira (this phase), and (2) a **command inbox** Jira→
> dispatcher: a small verb set (approve, accept-finding-with-rationale,
> re-refine) read from transitions/labeled comments, executed against
> dispatcher state, journaled with Jira provenance. If a richer UI is ever
> wanted, build a *read-only* dashboard rendering the journal — it owns no
> state, so it cannot drift.

- Sync Phase 2 metadata (tokens, cost, model, agent version) to the Jira issue
  on Done via the forecast bridge.
- **Compressed conversation log**: capture the Tasker session transcript
  (stream-json or session file), compress with a cheap model (Haiku) into a
  decision-focused digest — decisions and deviations, not narration — posted
  as a Jira comment.
- Finding dispositions from Phase 8 recorded on the Jira issue.
- **Command inbox** (per the decision above): dispatcher polls watched issues
  for the verb set (approve / accept-finding / re-refine), validates the
  actor, executes against local state, journals with Jira provenance.

## Phase 10 — Multi-machine dispatch

Distribute tasks across machines with different agents and capabilities,
building directly on the machine profile.

- **Architecture: single orchestrator, remote executors.** One machine runs
  the orchestrator and owns all state (YAML, journal, FileLock — which only
  works single-machine anyway); other machines only execute tasks. No
  distributed state, no consensus problems.
- **Fleet registry**: `machines.yaml` listing hosts; each runs
  `dispatcher doctor` and registers its profile. The scheduler routes a task
  to a machine where its preferred (or fallback) agent is available and
  capable — e.g., e2e gate tasks only go to docker-capable boxes.
- **Quota breakers key by account; each host has its own accounts.**
  `dispatcher doctor` records which account each CLI is authenticated as, so
  breaker state follows the profile (and still degrades correctly if two
  hosts ever share an account). Per-host accounts mean fleet quota scales
  with machines — and they add a routing tier: before falling back to a
  different model family, retry the *same preferred agent on another host*
  with remaining capacity. Routing order: preferred agent on any capable
  host → fallback family → wait for reset.
- **Work travels via git, not file copying.** The PR flow (Phase 3) is the
  enabler: a remote executor clones/fetches the repo, works in a local
  worktree, pushes its branch, and raises the PR — integration happens
  through the git remote, so results never need to be shipped back as files.
- **Transport**: SSH spawn for execution; journal events written locally on
  the executor and streamed/pulled back to the orchestrator's journal with a
  `machine` field on every event. `status --json` and the report gain
  per-machine breakdowns.

## Phase 11 — Evidence & traceability (compliance)

Target: ISO 27001 change-control evidence and regulatory-submission
traceability fall out of normal operation instead of being assembled by hand
at audit time. Explicitly out of scope: RBAC, HA, secrets management.

- **`dispatcher evidence <feature>`**: emits one bundle per feature —
  requirement (Jira) → tasks → prompts used (reviewer-prompt git SHA) →
  agent/model/version/account per task → commits and diffs → verification
  verdicts → panel findings with **all dispositions** (fix tasks and named
  acceptances with rationale) → approvals with identity → e2e + mutation-check
  run output → merges. Single archive with a human-readable index; doubles as
  a requirement→implementation→test traceability matrix for regulatory
  submission.
- **Evidence-grade journal**: hash-chained JSONL (each event embeds the hash
  of the previous) for tamper-evidence; configurable retention; journal +
  YAML backed up to a durable location per run.
- **Versions of the controls themselves**: every run records the dispatcher
  version and the git SHA of reviewer prompts / gate config, so the bundle
  proves *which* controls were in force, not just that something ran.
- **Controls-mapping doc**: one page mapping dispatcher gates to ISO 27001
  Annex A controls (8.25 secure SDLC, 8.28 secure coding, 8.29 testing,
  8.30 outsourced development — the closest analog for AI-authored code,
  8.32 change management, 8.15 logging) so the ISMS can cite the dispatcher
  and auditors get a ready answer to "how do you control AI-generated code?"

## Phase 12 — Operational hardening & knowledge

The dispatcher must notice its own death, and its cleverness must survive its
author's absence.

- **Heartbeat + watchdog**: orchestrator writes a periodic heartbeat event;
  a minimal independent watchdog (systemd timer or cron) alerts via the
  existing notify channels when a run's heartbeat goes stale — catching both
  a dead dispatcher and a dead monitoring agent.
- **Crash-recovery drill**: `resume` tested under kill -9 at every lifecycle
  stage (mid-spawn, mid-merge, mid-panel); documented recovery runbook for
  the states that can't self-heal.
- **Architecture doc**: the load-bearing invisible logic written down —
  direct-to-base fast-forward detection, panel consensus semantics, YAML
  mutation protocol, breaker/reset semantics — so a second maintainer can
  operate and extend the system without reverse-engineering orchestrator.py.

## Phase 13 — Roles & workflow integration

> **Decision — repo boundary (2026-06-10).** Considered merging
> claude-dispatcher and claude-workflow. Rejected: claude-workflow is a
> layered library (generic + evenplay overlay) that also serves
> human-interactive roles; merging welds prompt edits to Python releases and
> breaks the overlay. Instead: **dispatcher owns role contracts** (inputs
> provided, output schema expected); **claude-workflow owns role content**;
> each run pins a workflow-repo SHA recorded in the journal (feeds Phase 11
> evidence: "which controls were in force"). Role edits are reviewable PRs
> in claude-workflow, picked up explicitly, never accidentally.

- **Roles audit**: contract sheet per role/skill across claude-workflow
  (16 roles, 10 skills) — inputs, output schema, invoked-by (dispatcher
  pipeline vs. human), owning phase; flag dead or overlapping roles.
- **Existing coverage**: tasker (core), verification-agent (Phase 4),
  pr-reviewer family (Phase 3 ladder), regression-test-author (Phase 7
  adjacent), security-linter (panel adjunct).
- **New roles required by this plan**: Feature Planner (below), Refiner +
  Spike (Phase 5), Test-quality reviewer + Mutator (Phase 7b),
  Triage/disposition assistant (Phase 8), **Supervisor** (the run-monitoring
  agent — currently undocumented tribal knowledge; its playbook becomes a
  role file).
- **Feature Planner role** (upgrades the prd-to-task-yaml skill): brief →
  tasks.yaml with sizes, blockedBy graph, routing fields, environment
  deltas — then **self-validates via `dispatcher run --dry-run`** and
  iterates until schema, cycle detection, and the no-XL gate pass. Output is
  dispatchable by construction. task-yaml-review runs as a second,
  independent reviewer of the plan before dispatch.
- Skills needing updates for new vocabulary: prd-to-task-yaml,
  task-yaml-review (routing fields, environment deltas, no-XL gate,
  effective-diff rule).

---

## Sequencing & dependencies

```
Phase 0 (hygiene)          — anytime, small PRs
Phase 1 (control surface)  — first; everything depends on the journal
Phase 1a (machine profile) — alongside 1; preflight gates all later phases
Phase 2 (metadata/report)  — after 1/1a; Gemini/Codex numbers complete after 6
Phase 3 (PR flow)          — after 1
Phase 4 (verification)     — after 1; reuses panel-iterate machinery
Phase 5 (refine + routing) — after 1; routing fields consumed by 6
Phase 6 (quota/fallback)   — after 5 (needs routing fields)
Phase 7 (e2e gate)         — after 3 (needs feature-branch merge flow)
Phase 8 (final review)     — after 7 (review a feature that provably runs)
Phase 9 (Jira)             — after 2; logs/dispositions after 4/8
Phase 10 (multi-machine)   — after 1a, 3, 6 (profiles, PR flow, registry)
Phase 11 (evidence)        — bundle after 8/9; hash-chain journal can land with 1
Phase 12 (ops/knowledge)   — heartbeat with 1; drills after 3/6; doc anytime
Phase 13 (roles/workflow)  — SHA pinning with 1/11; Planner with 5; audit anytime
```

## Dogfood log

Lessons from running the dispatcher on itself; each entry either changed a
phase above (cross-referenced) or records an operational fact.

**Run #1 (2026-06-10T18-16-11Z, failed — full wave silently produced
nothing):**
- Missing `--claude-extra-args` permission flags → Taskers stalled at first
  tool-use prompt, exited 0 with no work. → Phase 1a preflight check (a).
- Tasker role file absent in fresh worktrees (machine-local symlink, never
  git-tracked) → fixed by committing a relative symlink (`6923d0a`).
  → Phase 1a preflight check (b).
- Diagnosis required manual archaeology (worktree status, YAML greps,
  reading spawn.py) — exactly the gap Phase 1's journal + `status --json`
  closes.

**Run #2 final: 12/12 Done, blocked=0, escalated=0, ~70 min wall clock,
$52.27 total (~$4.36/task), 11 PRs auto-raised (DISP-9's missing — investigate
why at integration). All Phase 0 hygiene + Phase 1 control surface delivered;
integration debt: DISP-11 journal fork, DISP-10 journal wiring, DISP-12 docs
written without sight of the final implementation.**

**Run #2 integration (2026-06-10, supervisor-executed):**
- 11 of 12 branches merged to main, full suite green throughout; PR #10
  (resume) held with disposition recorded on the PR per no-deferral policy.
- One trivial conflict (PR #2 vs PR #1: parameter-list union) and one README
  conflict (DISP-12's accurate docs vs DISP-10's, resolved by marking resume
  "pending PR #10").
- DISP-9 never *pushed* its branch — Done-detection checks local commits but
  not push/PR state. → run #3 task: post-Done push/PR verification.
- **Fourth dependency-gap behavior (DISP-12)**: its Tasker read the unmerged
  journal implementation from the shared git object store (`git show` across
  worktree branches) and produced docs that matched the real module exactly.
  Cleverest of the four — and still luck, not mechanism.
- `pipx reinstall` deployed; the new `dispatcher status` command's first real
  invocation reported on the run that built it.

**Run #2 (2026-06-10T18-24-47Z, in progress):**
- Wave 1 (DISP-1..4): 4/4 Done, all suites green in-worktree, ~6-9 min/task,
  single iteration each. Permission flags + role file were the only thing
  wrong with run #1's setup.
- Supervisor verification was manual (run tests in each worktree) →
  Phase 4 gains mechanical-checks-first; repo config gains a `test:`
  command.
- Running dispatcher is a pipx snapshot, distinct from the repo it's
  improving — merged fixes don't take effect until reinstall. → Phase 1a
  doctor records install mode; remember `pipx reinstall` before run #3.
- DISP-1's Tasker improved on spec (lazy discovery, merge-revert on missing
  binary) — evidence that task descriptions stating *intent and acceptance*
  rather than implementation detail get better-than-specced results.
- DISP-5: panel-iterate loop passed all four end-to-end scenarios with **no
  production bug found** — retires the top untested-code risk from the
  original code review.
- DISP-7: live agy 1.0.7 smoke PASS — the June-18 migration risk is verified
  closed (see open question 2). A dispatched task *performed the
  verification itself*, including running the CLI from its worktree —
  dispatchable ops checks work.
- DISP-9: dependent task's worktree branched from bare main without its
  dependencies' code; the Tasker noticed and merged feat/DISP-8 + feat/DISP-3
  into its branch unprompted. Right outcome, wrong mechanism — dependency
  branches must be provided mechanically at dispatch time. → Phase 3
  dispatch-time dependency rule.
- **DISP-9/10/11 controlled experiment**: the identical dependency gap
  produced three behaviors — merge the dependency branches (DISP-9, correct),
  narrow scope and document it (DISP-10: shipped `status` with no journal
  integration despite acceptance naming it — exactly what the Phase 4
  verifier catches), and **fork the dependency** (DISP-11: divergent copy of
  journal.py, guaranteeing merge conflict + writer/reader format mismatch).
  All locally rational, collectively an integration mess. Empirical close on
  the design question: Tasker improvisation has high variance; the
  dispatch-time dependency rule is mandatory, not nice-to-have. Integration
  debt from this run: reconcile DISP-11's journal fork onto DISP-8/9's
  module; wire DISP-10's status to the real journal.

**Run #3 (2026-06-10T20-26-55Z) + integration: 4/4 Done, blocked=0, $37.77,
~100 min. All integration debt cleared; journal chain cryptographically
verified (ok=True, 19 events) using the module the run was built to deploy.**
- INT-1 superseded held PR #10 (closed with disposition); INT-2/INT-3/INT-4
  landed `status`-from-journal, push verification, and the dispatch-time
  dependency rule. All four Taskers pushed + raised PRs unprompted.
- INT-4 exceeded spec: found and fixed a subtle interaction (merged
  dependency commits masking forgot-to-commit; `feat_baseline_sha`), and
  spawned its own adversarial review subagent — 1 MEDIUM found and fixed
  in-task. Self-arranged review prefigures the Phase 4/8 gates.
- Integration conflicts were all INT-1's `_run_loop` refactor vs siblings:
  field unions in status (needs_push + journal enrichment) and one real port
  (worker-side task_started into the refactored loop; `blocked_by` snapshot
  field initially lost in resolution — caught by INT-4's own test, the
  fixture suite doing exactly its job).
- **Dispositions — INT-4's review LOWs:**
  (1) non-conflict merge failures mislabeled `dependency_merge_conflict` —
  **DISPOSED 2026-06-10: fix task in next run (Andrew)**. Carry into run #4's
  tasks.yaml.
  (2) `--no-ff` dependency merges create merge commits the Tasker didn't
  author — rationale: the merge commit is the in-graph boundary between
  dispatcher-injected dependency code and Tasker-authored work (provenance
  in the git graph itself, not just the journal; clean anchor for
  feat_baseline_sha). **DISPOSED 2026-06-10: accepted with rationale
  (Andrew).**
- `resume` declines pre-run_config runs by design (genesis lacks
  `run_config` before INT-1); all future runs are resumable.

**Run #4 (2026-06-10T21-21-27Z) + integration: 6/6 Done, ~$98 total.
Phases 1a and 2 complete — doctor, machine profile, preflight, Done-metadata,
journal-sourced report rollup, docs.**
- **Dependency rule proved live both ways**: OPS-3/OPS-5 got dependency code
  mechanically (merged SHAs journaled in task_started), and OPS-6's first
  dispatch was correctly REFUSED with dependency_merge_conflict when its two
  dependency branches conflicted (fake_claude.py) — no tokens wasted on a
  conflicted tree. Repair: integrate deps to main, re-dispatch clean.
- **Human size-gate fired twice** (OPS-3, OPS-5, both >500-line role
  threshold): unattended mode parked them Blocked; Andrew approved both;
  supervisor raised the prepared PRs and recorded pr_approved_by. The
  approval ladder worked end-to-end manually — Phase 3 automates it.
- Integration conflicts were semantic this run: both tasks independently
  invented the same fake_claude --version guard (union trivial), and two
  pre-preflight tests collided with preflight's new refusals — one aligned
  to run WITH preflight, one (whose premise preflight outlaws) uses the
  journaled --skip-preflight escape hatch. Lesson: parallel siblings touching
  shared test harnesses is the main conflict source; harness changes might
  deserve their own task.
- Metadata + report verified on themselves: OPS-6's row carries
  agent_version/dispatcher_version; `dispatcher report` rolled up its own
  birth run from the journal ($87.51 in-run + $10.75 OPS-6 redispatch).
- Claude CLI silently moved 2.1.170→2.1.172 mid-day and switched the spawn
  default model (Opus 4.8 → Fable 5 for OPS-5) — caught only because per-row
  model metadata exists. Doctor's profile now records agent versions; drift
  is visible.

**Run #5 (2026-06-10T23-06-04Z + 5b) + integration: 6/6 Done, $95.55.
Phase 4 complete (mechanical gate + LLM verifier + iterate-on-incomplete)
and the Grok advisory seat is live — the dispatcher now verifies its own
Taskers' work.**
- **Grok live smoke: APPROVE in 24.4s**, all 8 dimensions parsed, through the
  real adapter (--prompt-file to dodge E2BIG; empty-stdout→UNAVAILABLE
  mirroring agy#76; closed reviewer registry; advisory status not disclosed
  to the reviewer, keeping the scorecard honest). Consensus proven
  byte-identical under advisory approve/block/unavailable.
- **INT-3's push verification fired in production**: VG-4's Tasker forgot to
  push (the DISP-9 class); detected, push-retry recovered in 26s, run
  continued. A failure mode discovered by human accident in run #2 is now
  self-healing.
- **No-false-Done self-applied before the gate shipped**: VG-6 (docs task)
  found a pre-existing red test in its tree, proved it pre-existing via git
  stash, and Blocked itself rather than report Done. The verification gate's
  culture preceded its code.
- **First true cross-branch semantic conflict**: VG-5's panel-robustness test
  asserted rc==0 on malformed .dispatcher.yaml; VG-2's gate (correctly)
  blocks loudly on the same config. Both productions right per spec; the
  test's assertion was stale. Fixed at integration: gate-blocks-first
  ordering is now the encoded truth; the malformed-config-reaches-panel
  path is unreachable by design.
- **Size-gate variance, instances #1-#3** (park / auto-raise-with-rationale /
  skip-citing-future-machinery across VG-2, VG-5, VG-4): Andrew's
  disposition — the threshold is arbitrary and that's fine; variance is an
  observation, not an offense. Phase 3's deterministic classifier still
  makes it consistent; consistency, not the number, is the point.
- Day-one totals across runs #2-#5: ~$435, phases 0/1/1a/2/4 complete plus
  the Phase 3 dependency rule and Phase 6 advisory tier.

**Run #6 (2026-06-11T02-35-52Z + 6b) + integration: 6/6 Done, $58.22.
Phase 3 complete — PR-flow mode, deterministic risk classifier, mechanical
merge engine with ladder gating, merge-prs command, status/report surface.
First run protected by the Phase 4 verification gate.**
- **Verification gate, first production campaign: 5/5 VERIFIED, gaps=0,
  ~$0.31 and ~22s per verdict** (PRF-3 parked pre-verification — see below).
  Mechanical gate averaged ~20s per task. Zero human verification performed
  this run; the supervisor's checks from runs #2-#5 are now machinery.
- **Forgot-to-push tally: 3 of 8 verified tasks today** (PRF-4, PRF-5 +
  VG-4) — all self-healed by INT-3's retry in <60s. Upstream fix queued:
  tasker.md should emphasize push-before-summary; retry remains the net.
- **Ordering nuance (fixed by this run's own design)**: PRF-3 parked at the
  Tasker's PR gate BEFORE verification could run — parked ≠ Done, so no
  verdict. In pr mode (PRF-2), raising happens AFTER verification, which
  retires both this nuance and the push_verify expect_pr gaps observed
  (PRF-4/5 pushed without PRs).
- Integration: 2 of 6 PRs showed GitHub conflicts that evaporated on real
  merges (conservative mergeability on dependency-merge history); PRF-5's
  remote tip had grown PRF-6's history — reconciled by merging the remote
  tip back. Suite green at every step.
- **Phase 3 + 4 are the last manually-integrated phases**: the merge engine
  shipped tonight does this job from the next pr-mode run onward.

## Open questions — resolutions (2026-06-10)

1. **Per-repo e2e provisioning** — RESOLVED: per repo. Each repo owns its
   `e2e:` block (Phase 7a); the dispatcher requires it before running the e2e
   gate and fails the gate loudly if absent or broken. No global defaults.
2. **Codex quota semantics + agent fleet candidates** — RESOLVED (research
   2026-06-10). Codex semantics now concrete in Phase 6 (structured
   `used_percent`/`resets_at` via session rollout files; per-turn usage in
   `--json` stdout; predictive breaker + optional API-key overflow).
   **Adapter action items**: (a) `--full-auto` is deprecated → migrate to
   `--sandbox workspace-write`; (b) close/redirect stdin (`</dev/null`) when
   spawning `codex exec` — non-TTY stdin left open hangs the process
   (openai/codex#20919); (c) version-gate the usage parser
   (`reasoning_output_tokens` added somewhere in 0.122–0.139; local install
   is 0.121.0 and lacks it — `doctor` records the version).
   - ~~URGENT~~ **Verified 2026-06-10 (DISP-7)**: Gemini CLI shuts off for
     individual plans 2026-06-18; `agy` (already in use) is the replacement.
     antigravity-cli#76 (silent stdout drop on non-TTY pipes) does **not**
     reproduce on agy 1.0.7 — live smoke PASS via `tools/verify_agy_pipe.sh`
     (re-run after any agy update). Adapter additionally hardened: empty
     stdout + exit 0 → reviewer UNAVAILABLE, never a parse attempt.
   - **Fleet additions recommended**: Qwen Code (Gemini-CLI fork — near
     drop-in adapter; JSON output with token usage; new Qwen family; API
     pay-per-token since the free tier ended 2026-04), OpenCode (one adapter
     → DeepSeek/Kimi/GLM/local via 75+ providers; JSON is an event stream,
     cost via `opencode stats`), optionally Mistral Vibe (clean headless
     contract, Devstral economics). Panel goes from 3 model families to 5–6.
   - **Grok Build (xAI)**: adopt now as the first *probationary* advisory
     reviewer (mechanism in Phase 6) rather than waiting for GA. **Skip**:
     Copilot CLI (no JSON, burns premium requests, broke programmatic
     interface without deprecation), Cursor CLI (headless hang bugs), Amp
     (no model pinning, no new family), Kiro, Aider (wrong shape for
     autonomous dispatch).
3. **Low-risk classifier rules** — RESOLVED: proposed defaults recorded in
   Phase 3 (size ≤ S, no panel-trigger labels, path denylist incl. migrations/
   proto/auth/CI/dependency manifests, ≤ 200 *effective* diff lines — test and
   generated code excluded from counting, first-pass verification, no new
   dependencies; docs-only always low-risk, test-only never auto-low-risk).
   Andrew tunes per repo.
4. **Mutation-check budget** — RESOLVED: 1 per feature default; escalate to 3
   on panel-trigger labels, > ~1,500 *effective*-line feature diff (same
   counting rule), any per-task panel block, or a newly introduced e2e suite.
   Survived mutation = blocking finding → fix tasks → re-run with a fresh
   mutation until caught. Recorded in Phase 7b.
