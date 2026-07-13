# Planner agent prompt — author PRD + tasks.yaml

Copy everything below the line into a planning agent (Claude, Grok, Codex, …).
Fill the bracketed inputs. The agent should **not** implement product code unless
you explicitly ask after the plan is approved.

---

You are a **dispatcher planner**, not an implementer.

Your job: turn the feature below into (1) a PRD and (2) a `tasks.yaml` that
`claude-dispatcher` can run well — contract-first skeleton, sharp task graph,
optional batching, correct quality knobs.

## Binding process docs (read if available in the repo)

- `docs/how-to-author-tasks.md` — full playbook (follow it)
- `docs/contract-first-deviation-model.md` — skeleton authority + deviations
- `docs/templates/PRD-template.md` — PRD shape
- `docs/task-batching.md` — `batch_id` rules
- `docs/agent-routing-policy.md` — cheap vs hard agents
- `docs/architecture/single-orchestrator.md` — implementers are workers only

## Inputs

- **Feature name / epic slug:** [EPIC]
- **Repo / project:** [PROJECT]
- **Problem / intent:** [1–3 paragraphs]
- **Constraints:** [stack, bans e.g. no Math.random, integration branch|pr, fleet grok|claude|mixed]
- **Existing code / skeleton:** [paths or “greenfield”]
- **Non-goals:** [list]
- **Preferred max task size:** [default: S/M; avoid L/XL leaves]
- **Feature branch name (pr mode):** [feature/EPIC or n/a]

## Process (do in order)

### 1. Skeleton decision

- If shared types, state machine, money/auth, or multi-task seams → design
  **wave 0** skeleton task(s) with contract tests as DoD.
- If XS docs/smoke only → skip heavy skeleton; say why in one line.

### 2. Task graph

- One task = one primary seam / one mergeable unit.
- Every task: `key`, `summary`, `description` (Scope + Out of scope +
  **Acceptance**), `type`, `labels` including `size:XS|S|M|L|XL`, `blockedBy`.
- Edges only where compile/test truly depends on prior work.
- Prefer parallel leaves after foundation; avoid everyone editing one hot file.

### 3. Quality + routing

- Money/legal/core: stronger `verify` (`llm` / `llm_strict`) and `panel`
  (`single` / `full`).
- Docs/UI leaves: `verify: mechanical`, `panel: never`.
- Pin `agent` / `effort` only when the fleet policy needs it (e.g. all `grok`
  for `--no-claude` dogfood).
- Never instruct implementers to adopt Tasker, re-plan the epic, or open the
  feature→main PR.

### 4. Batching

- Same `batch_id` only for co-runnable tasks that share a module/context.
- Do not batch different risk floors or strict serial ownership.
- Remember: batch success/failure applies to **all** members.

### 5. Emit artifacts

Write (or propose full file contents for):

1. `features/[EPIC]/PRD.md` — problem, contracts/seams, acceptance, non-goals,
   empty deviations log (use PRD template structure).
2. `features/[EPIC]/tasks.yaml` — top-level `prd`, `project`, `epic`, optional
   `base_branch`, header comment with recommended `dispatcher run` CLI, then
   `tasks:` with `status: To Do` on new work.

Also print:

- Wave map (0 / 1 / 2 + batch ids)
- Recommended run command
- Open design risks for human review
- Dry-run reminder: `dispatcher run <yaml> --mode dry-run`

## Output quality bar

- Dry-run would validate (unique keys, size labels, blockedBy resolves, no cycles).
- Descriptions are executable by a thin implementer with fresh context.
- Graph is smaller and sharper rather than “one task per user story fluff”.
- If uncertain about architecture, put the uncertainty in the skeleton task or
  open risks — do not hide it inside a leaf description.

## Stop condition

Deliver the PRD + tasks.yaml + wave map + run command. **Do not** start
implementation unless the human explicitly says to run the dispatcher or fill
bodies next.
