# Claude Dispatcher — Claude Context

This file provides guidance for Claude (and dispatched agents) working in this
repository and running dispatched work through it.

---

## EXPERIMENT (2026-06-18): contract-first decomposition with audited deviations

We are trialing a new way to run dispatched work, motivated by two failures:
unreviewable code volume, and long runs thrashing on an implicit/wrong
architecture. Full design: `docs/contract-first-deviation-model.md`.

## NEW: Task Batching
The dispatcher now supports batching multiple tasks into a single LLM session to save time and API costs. If tasks in your `tasks.yaml` share a `batch_id`, they will be executed together. Read `docs/task-batching.md` before planning multi-task workflows to understand how it handles prompts, context, and status synchronization!

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
