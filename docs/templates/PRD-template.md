# PRD — <feature name>

> Authored by the Planner at GATE 1, committed at `features/<feature>/PRD.md`,
> referenced from the tasks.yaml top-level (`prd: features/<feature>/PRD.md`).
> The **final feature review** reads this as the intent oracle — it reviews the
> cumulative diff *against* this file, not just for internal quality. Keep it
> current; the run appends to the Deviations log.

## Problem / intent
<What this feature must accomplish and why. The outcome a human cares about —
not the implementation.>

## Contracts + data-flow seams
<The load-bearing interfaces/types/state-machine from the skeleton, and who
produces/consumes which shape across each seam. Name the canonical shapes. This
is what the final review checks the implementation honors.>

## Acceptance criteria (feature-level)
<Observable, checkable statements of "the feature is done" that go BEYOND the
per-task contract tests — end-to-end behaviors, cross-task coherence, the cases
that only matter once all tasks are integrated. The final review verifies these.>
- [ ] ...

## Non-goals
<Explicitly out of scope, so the final review doesn't flag their absence as a gap.>

## Feature asymmetry / degradation decisions
<Where one path can't do what another can (e.g. a backend that lacks a field),
the deliberate degradation + why. Pre-empts "this path is missing X" findings.>

## Deviations log (appended during the run)
<Each agent deviation from a contract: kind (shared-contract | internal |
new-surface) / original / changed / reason / blast_radius / disposition. The
highest-signal review surface — every entry is where design met reality.>
