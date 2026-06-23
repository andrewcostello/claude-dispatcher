# Contract-first decomposition with audited deviations

Status: proposal for experiment (2026-06-18)
Origin: designed with Andrew after the tournament-BSA + live-e2e runs, which
exposed the current model's failure modes (unreviewable code volume; long
unattended runs thrashing on implicit/wrong architecture; fuzzy LLM-judge
verification; the supervisor hand-resuming on every transient).

## The core idea

Flip what the human authors and what agents author.

- **The human authors the *skeleton*** — types, interfaces, the state machine,
  mutation points, data-flow edges, and the contracts (ideally as tests). This
  is the small, high-leverage, judgment-bearing part.
- **Agents fill *function bodies* against fixed contracts** — bounded,
  parallelizable, mechanically checkable work.
- **The skeleton generates the dispatcher plan.** The call graph and data-flow
  edges *are* the task graph and `blockedBy` edges. Decomposition stops being
  hand-guessed.

### Why this fixes the failure modes we hit

1. **Review burden → the right surface.** You review the skeleton (a fraction
   of the volume, ~all the design) and skim conforming bodies. The
   tournament-BSA pain was reviewing thousands of lines + comments; here you
   never read a conforming body.
2. **Verification → mechanical.** If the skeleton ships contracts-as-tests,
   each task is "make this test pass" — objective. This retires the LLM-verifier
   truncation false-positives that cost hours (7 adjudications in one run).
3. **Architecture → enforced, not prose.** The live-e2e disaster was an implicit
   architecture I reverse-engineered wrong (legacy vs BSA, free-shots). A
   skeleton where the only injected dependency is `bay-session` and there is no
   `smg-core GetGameState` in the contract makes that wandering a *type error*,
   not a 6-hour spiral. CORRECTED-MODEL.md was prose that got under-read; a
   skeleton is a guardrail the compiler enforces.
4. **Cheap models for the bulk.** A function with a fixed signature + a passing
   test as its definition-of-done is bounded work a fast model (Grok Build) can
   do, with the test as the net. Reserve strong models (and your review) for the
   skeleton and the complex stateful core.

## Deviations: the part that keeps it from being too rigid

Pure contract-first is too rigid — the human's architecture is often wrong, and
the agent hitting reality is exactly who discovers it (TRN-8's spike refuted a
design bet; TRN-3's panel caught a wrong overlay model). So:

**An agent MAY alter the structure/contract — if it records a deviation.**
Conformance is the default; deviation is a deliberate, logged, reviewed
exception. The deviation log becomes the **single highest-signal review
surface**: every entry is a point where the design and reality diverged.

### Double feedback loop

Each deviation resolves to one of three dispositions (the no-deferral
disposition queue we already built for findings):

- **design was wrong** → update the skeleton,
- **contract was needlessly tight** → loosen the *process*,
- **agent was wrong** → reject, revert, reinforce the contract.

This tunes both the architecture and the methodology over time.

### Deviation record (proposed fields)

```yaml
deviation:
  task: TLE-3
  kind: shared-contract | internal | new-surface   # see typing below
  original: "checkInAndJoin returns CheckInResult{evenplayToken}"
  changed:  "...also mints + returns legacySmgToken; join uses legacySmgToken"
  reason:   "JoinTournament is a legacy smg RPC needing a legacy userSession;
             the bay-session token returns 'User session not found'."
  blast_radius: ["TLE-4 specs call checkInAndJoin"]   # who depends on this
  disposition: pending | accept-update-skeleton | reject-revert | loosen-process
```

### Three rules that keep it from drifting into mush

1. **Type deviations by blast radius.** Changing a function's *internal*
   implementation isn't worth logging. Changing a *shared contract* (a type /
   interface others depend on) **blocks dependents and demands review now** —
   that's where the load-bearing forks live. Private = free; shared = gated.
2. **Deviation costs an escalation.** A cheap model fills a conforming function
   silently; the moment it wants to deviate, it escalates to a stronger
   model/human. Otherwise a fast model deviates sloppily to dodge a hard
   contract and you're back to reviewing everything.
3. **Deviation *rate* is an alarm.** Many deviations ⇒ the skeleton was
   under-designed ⇒ redesign, don't keep patching. The rate is a metric.

## How it maps onto the existing dispatcher

- **Plan generation**: the skeleton/contract graph yields tasks + `blockedBy`
  (sharpens the Phase 5 Planner role — the plan is *derived*, not guessed).
- **Gate**: "contract test passes" replaces/augments the LLM verifier for
  conforming tasks (objective; no truncation problem). The verifier's job
  shrinks to judging *deviations*.
- **Deviations** flow into the no-deferral disposition queue (Phase 8 machinery)
  — every one gets a recorded disposition; conforming tasks merge unread.
- **Tiering**: `agent: grok` for contracted leaf fills; `agent: opus` for the
  skeleton, the complex core, and deviation review.

## Honest limits (what this does NOT solve)

- **Emergent/integration behavior still needs real seam tests.** Correctly-
  contracted functions can be wrong together — exactly the e2e problem. The
  skeleton must include integration contracts at the seams; those are the
  genuinely valuable, harder-to-mechanize checks.
- **Contract quality is load-bearing.** A weak test lets a fast model produce
  subtly-wrong-but-green code — argues for the mutation-check (a planted bug must
  fail the contract test).
- **Stubbing the architecture well is expert work** — but it's the right place
  to spend human effort, and far less volume than reviewing all the code.

## First experiment

The dual-backend FullSwing mobile feature
(`evenplay-mono/docs/plans/2026-06-18-mobile-dual-backend-fullswing.md`):
architecture + seams already established (the canonical `UserSessionUpdateData`
shape; the login fork; the stream facade), well-bounded work items (§6), risk
pre-classified (§8). Run it contract-first: human-owned skeleton (the facade +
backend enum + login fork contract), Grok for the leaf hooks, deviations logged
and reviewed. Measure: review burden, deviation rate, and whether the thrash
drops vs. the live-e2e run.
