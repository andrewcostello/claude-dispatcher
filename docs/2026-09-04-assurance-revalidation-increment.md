# Dispatcher revalidation: third assurance increment

This is an uncommitted implementation record, not release approval or a new
quality rating. It continues the workflow's
[second increment](../../claude-workflow/docs/2026-09-04-assurance-evidence-increment.md)
and repairs the legacy retry paths identified in
[DP-02](2026-09-04-dispatcher-quality-assessment.md#dp-02--panel-corrections-bypass-renewed-mechanical-verification).
The interactive and contract-led workflows remain distinct. The staged
`boundary/` package remains test-only and is not imported by this repair.

## What changed

Mechanical, verifier and panel corrections now return to one acceptance loop:

```text
corrective spawn
  → discard the previous pass's results and parse the summary again
  → role / scope / declared holes
  → mechanical verification → applicable seal verification
  → configured verifier → required panel
  → confirm the revision is unchanged and the worktree is clean
  → existing integration / delivery path
```

Existing role-specific suite expectations, explicit skips and configuration
opt-ins still apply. This is not a claim that every legacy task requires every
gate. A failed or uncommitted repair cannot inherit earlier passing results.
A mechanical correction whose session crashes may still recover, but only if
its committed result passes the restarted checks. Failed verifier/panel
corrective sessions remain blocking and lose earlier green stamps.

Retry state belongs to one cascade rung, not one acceptance pass:

- Verifier corrections retain their configured budget, including the existing
  extra retry for `llm_strict` work.
- Panel corrections retain both their budget and convergence history. Once a
  panel is required on that rung, later corrections cannot silently drop it.
- Mechanical verification permits one corrective retry per segment. A verifier
  or panel correction starts a new segment; a mechanical correction does not.
- A new cascade rung receives fresh budgets and history, preserving the
  existing operator policy. A scope breach blocks without discarding the
  offending branch through a cascade reset.

For effective verifier budget V and panel budget P, this bounds corrections
within one rung to V verifier, P panel, and at most 1+V+P mechanical spawns.
Initial implementation, commit/summary recovery and provider retries are
separate existing mechanisms, not included in that bound.

The mechanical configuration is retained across corrective passes so a retry
cannot replace its failing command with a weaker command on re-entry. Verifier
cost is charged at each invocation, including when a subsequent structural
check blocks before the verifier helper can return again.

Existing role-gate journal events now include the pass's HEAD SHA and local
verification generation. Restarted summary events identify their generation.
These are diagnostic additions, not protected acceptance credentials.

## Delivery safety net

The legacy branch-mode push recovery can invoke an agent after acceptance.
Its prompt now forbids rebasing, merging, amending or changing code. The
dispatcher also checks the revision and worktree after recovery; instructions
alone are not enforcement. A changed revision or dirty tree blocks completion
and clears the current attempt's passing stamps. An unsuccessful push that
leaves the accepted subject unchanged retains the existing advisory
`needs_push` behavior.

This check cannot retract a push an agent already performed. It prevents that
changed subject from being reported Done; it is not an execution sandbox.
Auto-integration does not use this push-recovery path.

## Change record / review boundary

- **kind:** tightened legacy acceptance and recovery behavior; private helper
  changes, no new v1 state fields or boundary contracts.
- **original:** mechanical retries skipped renewed structural checks;
  verifier retries reran mechanical verification only; panel retries reran the
  panel only. The push-retry prompt also permitted an unverified rebase.
- **changed:** one restart path for the three corrective stages, per-rung
  budgets, fresh summary ingestion, revision/cleanliness checks and refusal of
  post-acceptance push-recovery edits.
- **reason:** earlier success described code that no longer existed. Real-Git
  regression tests reproduced this before implementation.
- **blast_radius:** legacy dispatcher orchestration, helper callers and their
  tests. Corrected code incurs the full configured verification cost again.
  Dirty fixes previously accepted by an old test now block; commit the repair
  and revalidate it. Remote divergence can require operator intervention rather
  than an automatic post-acceptance rebase.
- **review status:** pending independent review and adoption. This is not a
  scaffold/seals/body/adjudication acceptance of any planned boundary unit.

## Verification

The initial seven regressions all failed against the pre-repair runtime for
their intended assertions: each correction skipped earlier checks, a panel
regression reached Done, and each correction could delete a foreign-owned file.
They pass after repair.

The new regression module covers stage order and candidate identities, mixed
panel/test fixes, budgets across verifier/panel restarts and cascade rungs,
convergence, required-panel retention, command weakening, dirty fixes, malformed
summaries, failed corrective sessions, seal regressions, verification-time
mutations, exact cost accounting and post-acceptance push-recovery edits.
Configured mechanical commands and Git transitions run for real in disposable
repositories. Implementers, verifier/panel responses and seal outcomes are
scripted; these are orchestration tests, not measurements of live model quality.
The full suite also exercises the existing seal implementation separately.

The final focused run passed **113 tests** on Python 3.14.4. The complete final
suite passed **4,038 tests** in 256.96 seconds, with two existing pre-PR2 boundary
allowlist-degradation warnings about planned modules that remain absent.
T26 lint passed, including peer citations at their pinned revisions.
`git diff --check` passed in both repositories.
An earlier full run identified an obsolete source-expression assertion for
per-rung budgets and the old push test's acceptance of an extra commit. The
updated tests retain those policies and add behavioral positive/negative cases.

Local test outputs are under `/var/tmp/dispatcher-revalidation.sSmAfu/`.
`final-focused.xml` and `final-full-suite.xml` are JUnit reports; these local
files describe an uncommitted worktree, not independently protected evidence.
`verification.json` records the results and source/report hashes. Source
hashes matched across the final verification snapshot and completion check.
No live model calls, commits, external PRs, deployments or repository migration
were performed.

## Still required before stronger autonomy

1. **Protected, complete evidence binding.** Initial mechanical configuration
   still comes from the candidate worktree; retaining it during retries does
   not make it protected policy. Seal and review helpers retain their existing
   configuration sources. Legacy YAML stamps are not proof of a complete gate
   plan, policy identity, invocation identity or durable cross-run authority.
2. **One exact integration subject.** Before/after HEAD and cleanliness checks
   detect persistent changes, not changes made and reverted between checks or
   changes immediately afterward. Existing direct-to-base and integration
   paths still need alignment on a protected exact candidate, atomic handoff
   and verification of the actual merged tree, including code generation.
3. **Execution isolation and panel policy.** Reviewer working-directory and
   write-access findings remain open, as do complete classification/review
   coverage and aggregation-policy findings. Repeating the panel does not
   repair those independent issues.
4. **Adoption and measured evaluation.** Review this increment independently,
   test the exact installed artifact, and extend the evaluation corpus before
   increasing autonomy or migrating the shared machinery to a neutral repo.
   Passing these regressions does not establish production readiness or a
   high-90s quality score.
