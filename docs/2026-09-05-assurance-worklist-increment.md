# Worklist recovery: sixth assurance increment

This follows the [Git-context repair](2026-09-04-assurance-git-context-increment.md).
The baseline is `9f2754f681b9275d40713277bd450e47df750c0d`, which includes the
earlier assurance work and the defective-row recovery change from PR #112.
This is a bounded legacy repair, not Phase 14 state separation, boundary C8
adoption, independent adjudication, or production approval.

## Reproduced failures

The new baseline passed **4,099 tests** in a separate clean clone. Additional
probes using the real YAML reader, validator, file locks and dispatch executor
showed failures not covered by that suite:

- A scripted worker completed a task and damaged its agent/model pairing. The
  dispatcher then launched a second task from the surviving partial list.
- An invalid final worklist with an individually readable Done row returned
  exit zero. The next invocation's startup refusal did not make that earlier
  run unsuccessful.
- Dependency resolution accepted surviving rows from a worklist that failed
  whole-document validation. The same shared loader also fed verification,
  declared-hole expectations and known-red retirement.
- Scalar/list YAML roots and a numeric `tasks` collection crashed the salvage
  path despite its recovery promise.
- Empty mappings and strings as `tasks` were accepted as empty successful
  worklists. Other non-sequence inputs produced inconsistent exceptions.

The scheduling regression is a composition failure: prior drain tests replaced
the loader with a stub that raised, while PR #112 made the real loader swallow
that failure. Both groups passed independently. Tests must exercise the actual
producer/consumer connection as well as each component.

## Repair

The shared decision reader again returns a fully validated snapshot or raises.
Scheduling, dependency resolution and verification do not receive salvaged
rows. The reporting-only reader may recover individual rows after failure;
these are diagnostic counts, not an authoritative task graph.

A thread-safe, invocation-local hold is set when a decision read fails. It is
independent of journal/notification availability, persists across later valid
reads, and stops further admissions, post-hold PR merge passes and feature
review rounds. Already running workers are not cancelled; their normal gates
and status/error handling remain in effect. Repair followed by explicit resume
creates a new invocation; no automatic retry releases the hold.

The final rollup still runs. A held invocation returns exit 1, writes
`worklist_invalid: true` in `run_complete`, logs that counts may be partial,
and sends a warning instead of a green completion notification. The journal's
terminal event means the invocation ended, not that all work was accepted.

Malformed salvage shapes now yield no diagnostic rows. Lock timeouts propagate
on both the first read and the salvage reread. The task parser rejects
non-list/non-tuple collections with `ValidationError`; the existing explicit
null/empty-list behavior and tuple inputs remain supported.

## Deviation

- **kind:** shared-contract behavior tightening, with an additive journal
  payload field; private reporting/hold helpers, no boundary schema changes.
- **original:** all mid-run consumers could receive partial rows; corrupted
  worklists could suppress failure and still authorize new work.
- **changed:** recovery is reporting-only; observed failure holds the invocation
  and cannot produce a successful completion code. Invalid collection shapes
  are refused by the shared parser.
- **reason:** real-loader regressions demonstrated continued dispatch,
  successful termination, incomplete decision input, and recovery crashes.
- **blast_radius:** orchestrator scheduling, verification/dependency consumers,
  terminal reporting, and callers of the task parser. Consumers of
  `run_complete` should honor `worklist_invalid`. The hold is not a new durable
  task-state store or a replacement for the planned definition/state split.
- **test-contract adjustment:** three existing recovery assertions now call the
  reporting-only reader. Their expected surviving rows/empty diagnostic result
  are unchanged. Startup, valid-input and lock-timeout checks are retained;
  the existing drain tests are unchanged. New end-to-end composition checks
  prevent routing those partial rows back into decision-making.
- **review status:** manual interactive repair, pending independent adoption
  review; not formal scaffold/seals/body/adjudication acceptance.

## Verification record

Reports are local diagnostics under `/var/tmp/assurance-resume.3TLdtm/`, not
protected evidence or a live-model evaluation. All agents/workers in these
tests are scripted; no external service, paid review panel or deployment runs.

- `baseline.xml`: 4,099 passed, two known pre-PR2 boundary warnings.
- `red-corrected.xml`: six intended failures against the unchanged runtime.
  The first draft (`red.xml`) included a worker-fixture error and is not the
  scheduling counterexample; the corrected run uses the actual YAML writer.
- `first.xml`: the six new regressions and existing drain checks passed; three
  legacy assertions identified the reporting/decision contract adjustment.
- `focused.xml`: 134 passed before the collection-shape cases were added.
- `shape-red.xml`: seven intended failures, four passes; distinguishes false
  success from wrong exception types.
- `mutation-control.xml`: 45 passed; cloned source/test hashes match the
  working inputs before any probe.
- `full.xml`: **4,131 passed**, two known pre-PR2 boundary warnings
  (323.53 seconds), with the initial 32-case regression module.
- `mutation-restored.xml`: 45 passed after all mutations were restored;
  source/test hashes still match the working inputs.
- `final-focused.xml`: 48 passed after adding three cases for a failure first
  observed during rollup and the declared-hole gate's corruption/valid controls.
  The final regression module contains **35 cases**; runtime source is unchanged
  from `full.xml`.
- `mutation-final-control.xml` and `mutation-final-restored.xml`: 48 passed
  before/after repeating all six probes against the final test inputs. The
  table below describes `final-mutation-*.xml`; final source/test hashes agree.
- `concurrency-1.xml` through `concurrency-10.xml`: ten additional passes of
  the two-worker failure/repair/drain scenario.

Each mutation ran in the owned throwaway clone with a 120-second outer bound.
No probe changed the real worktree or increased a safety ceiling.

| Weakened safeguard | Intended failures |
|---|---:|
| Give decision consumers partial rows | 3: continued dispatch, dependency acceptance, omitted declared-hole check |
| Forget the observed failure | 2: false success, repaired file resumes admissions |
| Ignore the hold in the exit status | 2: false success for mid-run and rollup-only failure |
| Swallow the salvage reread's lock timeout | 1: timeout becomes diagnostic absence |
| Remove collection-shape validation | 7: false success or wrong failure types |
| Continue feature review after the hold | 1: review runs on the damaged worklist |

These are selected mutation checks, not a comprehensive mutation score.
T26 lint, including pinned peer citations, and `git diff --check` passed.
Clean committed-tree verification is recorded separately in the final local
verification record after it completes.

## Remaining limits

- This does not prevent the dispatcher from writing an invalid authored row.
  Phase 14's definition/state separation remains the structural repair.
- Diagnostic salvage is incomplete: rows needing their graph context can be
  omitted, and whole-document constraints are not certified by row counts.
  No task file or missing row is reconstructed or rewritten by recovery.
- The hold is an observed-error checkpoint, not an atomic file/effect fence or
  a sandbox. It does not cancel an effect already in flight or prove that an
  unobserved, transient mutation never occurred.
- Locks, journals and notifications retain their existing operational limits.
  Lock contention can still terminate an invocation through its exception path;
  it is never treated as an empty successful worklist. Third-party journal
  readers must not treat `run_complete` alone as approval.
- Parser hardening here concerns the collection shape; it is not a new closed
  task schema. Classification, panel-policy, reviewer-isolation and integrated-
  tree findings in the original assessment remain separate work.

No push, PR, deployment, repository consolidation, model-policy change, or edit
to the workflow repository's two pre-existing YAML changes is part of this
increment.
