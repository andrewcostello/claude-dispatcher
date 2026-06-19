# PRD: <feature name>

> **What this is.** The Planner authors this document at GATE 1 and commits it to
> `features/<feature>/PRD.md`, referenced from the tasks.yaml top level as
> `prd: features/<feature>/PRD.md`. It is the **intent oracle** the final feature
> review reads: the cumulative feature diff (`base..feature-branch`) is reviewed
> *against* this PRD, not just for diff-internal quality. Keep it accurate — the
> review's value tracks the PRD's quality.

**Feature:** <feature name / key>
**Author:** <Planner — agent/run id>
**Date:** <ISO 8601>
**tasks.yaml:** `features/<feature>/tasks.yaml`

---

## Problem / intent

<What problem this feature solves and for whom. The motivating intent — why this
is worth building now. State the outcome a reviewer should be able to confirm the
landed code achieves, in plain language and not in terms of any single task.>

## Contracts + data-flow seams

<The pre-established skeleton: the types, interfaces, function signatures, the
state machine, and the data-flow seams that downstream tasks fill the bodies of.
These are authoritative — bodies satisfy them; changing a SHARED contract is a
Deviation (see below). For each seam, name it, give its signature/shape, and say
who produces and who consumes it.>

- **<contract / seam name>** — `<signature or type shape>`
  - Produced by: <task / module>
  - Consumed by: <task / module>
  - Invariant: <what must always hold across the seam>

## Acceptance criteria (feature-level)

<What "feature done" means **beyond per-task tests** — the cross-task, end-to-end
behaviors that no single task's test proves. Each criterion must be checkable by
the final review against the cumulative diff. Number them so dispositions can
reference them.>

1. <criterion — observable, end-to-end>
2. <criterion>
3. <criterion>

## Non-goals

<What this feature explicitly does NOT do. Bounds the review so missing
out-of-scope behavior is not reported as a gap.>

- <non-goal>
- <non-goal>

## Feature asymmetry / degradation decisions

<Known, deliberate asymmetries between backends/platforms/paths, and how the
feature degrades when a dependency is unavailable or a capability is absent.
Recording these here stops the review from flagging an intended asymmetry as a
defect.>

- <decision — what differs, on which path, and why it is acceptable>
- <degradation — behavior when X is unavailable>

## Deviations log

<Appended during the run. Each entry is a deliberate, documented exception to the
skeleton/contract — not a failure. A correct, well-reasoned deviation is the
high-signal review surface. Internal-only changes need no entry; a change to a
SHARED contract (a type/interface others depend on) MUST be logged here and blocks
dependents pending review.>

<!-- One entry per deviation; append, do not rewrite history. -->

### <DEV-1> <short title>
- **Task / commit:** <key / sha>
- **kind:** shared-contract | internal | new-surface
- **original:** <the contract as the skeleton established it>
- **changed:** <what it became>
- **reason:** <why the original was genuinely wrong or insufficient>
- **blast_radius:** <who depends on this — the tasks/modules affected>
