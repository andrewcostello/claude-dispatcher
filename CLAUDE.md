# Claude Dispatcher — Claude Context

This file provides guidance for Claude (and dispatched agents) working in this
repository and running dispatched work through it.

Humans (and agents) onboarding the *system*: start at
`docs/onboarding/README.md`. Map of the rest: `docs/README.md`.

---

## EXPERIMENT (2026-06-18): contract-first decomposition with audited deviations

We are trialing a new way to run dispatched work, motivated by two failures:
unreviewable code volume, and long runs thrashing on an implicit/wrong
architecture. Full design: `docs/contract-first-deviation-model.md`.

## Task Batching
If tasks in your `tasks.yaml` share a non-empty `batch_id` **and** are
co-runnable in the same wave, the dispatcher runs them as one work unit
(one worktree, one implementer session, combined prompt; all keys get the
same Done/Blocked outcome). See `docs/task-batching.md` and
`docs/how-to-author-tasks.md` Phase C.

## Authoring tasks.yaml (planners)
If you are asked to **build or rewrite a task list / PRD** for dispatcher runs,
follow `docs/how-to-author-tasks.md` and use `docs/templates/planner-prompt.md`.
Skeleton/contracts first, then the task graph, then optional `batch_id`s.
Do not invent mega-tasks; dry-run before dispatch.

First subject: the dual-backend FullSwing mobile feature (its plan doc lives in
the evenplay-mono repo at `docs/plans/2026-06-18-mobile-dual-backend-fullswing.md`).

Rules for agents working under this experiment:

1. **The skeleton is authoritative.** Types, interfaces, function signatures,
   the state machine, and the data-flow seams are pre-established. Fill the
   body to satisfy the contract (the test). Do NOT redesign silently.
2. **To change a contract, record a DEVIATION — do not force-fit or hack
   around it.** A deviation is a deliberate, documented exception, not a
   failure. Put it in your summary under a `## Deviation` heading with:
   `kind` (shared-contract | internal | new-surface), `original`, `changed`,
   `reason`, `blast_radius` (who depends on this). Internal-only changes need
   no deviation; changing a SHARED contract (a type/interface others use) is a
   deviation and must be flagged loudly — it blocks dependents pending review.
3. **Deviation is the high-signal review surface.** A correct, well-reasoned
   deviation is *more* valuable than silent conformance to a wrong contract —
   it's how we learn the design (or this process) needs to change. But it costs
   an escalation: prefer conforming; deviate only when the contract is genuinely
   wrong or insufficient, and say exactly why.
4. **Do not import the wrong architecture.** Stay within the seams the
   plan/skeleton establishes. The per-feature architecture lives in that
   feature's plan doc — read it before filling bodies, and don't reshape the
   established seams to fit a body you find easier to write.

## Attribution: none, in commits or in names

No `Co-Authored-By`, no author names in file headers or docs, and no class or
function named after whoever wrote it — human or model. Code belongs to the
team; attribution creates silos and a false sense of ownership.

Naming a symbol after what it INTEGRATES WITH is not attribution and stays:
`ClaudeReviewer` names the CLI it drives, as `PostgresStore` would name a
database.

**Keep the provenance, drop the credit.** What the trailer was buying is the
ability to ask later *how* a change was produced — dispatched under a panel, or
hand-edited — an audit question, not a credit one. Record the process instead:

```
type(scope): short description [TASK-KEY]

Dispatched-Task: TASK-KEY
Dispatcher-Run: <run id>
```

The bracketed key is load-bearing, not decoration: `dispatcher audit`'s
`landed-by-message` route greps for the bracketed form (`--fixed-strings`) to
distinguish a landed-and-pruned branch from work that went missing. Bare
mentions are noise — `W2-1-1` appears in 16 commit messages on main and
`[W2-1-1]` in 3 — so keep the brackets.

Commits before 2026-08-30 carry a `Co-Authored-By` trailer. They are left
alone: rewriting published history to remove a line costs more than the line.

## Comments: purpose and constraints, not rationale

Measured 2026-08-17 across this package: the established modules run about
**0.5:1** prose-to-code (`orchestrator.py` 0.4, `plan.py` 0.5,
`mechanical_verify.py` 0.7, by docstring+comment lines over executable lines).
Three scaffolds written the same week ran 1.9:1, 2.2:1 and **4.3:1**, and
`role_protocol.py` is 1.7:1 over 10,050 lines. Every later agent that reads
those files pays for the excess in context, and long prose is also what goes
stale — a docstring stating a world that does not exist yet has now caused
three separate blocks (D-56, D-65, D-72).

So:

* Comments state **purpose, intent, and non-obvious constraints** — the facts
  whose absence would let someone break the code.
* **Rationale, measurements, rejected alternatives and rulings go in the commit
  message** and `DECISIONS.md`, referenced by ID. Written there they are read
  once by a reviewer; written inline they are re-read by every agent forever.
* The test: *would a future agent break this code without this comment?* If it
  is justification aimed at a reviewer, it belongs in the commit message.
* Do not restate the commit log in a module docstring. If the two say the same
  thing, delete the docstring copy.

`python -m claude_dispatcher.scaffold_shape measure <file.py>` prints the
ratio. It is advisory — a contract-heavy scaffold legitimately runs higher —
but a file well above 1:1 should have a reason you can say out loud.
