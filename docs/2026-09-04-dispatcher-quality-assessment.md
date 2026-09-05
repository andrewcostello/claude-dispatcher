# Dispatcher quality assessment

Assessment date: 2026-09-04.

Implementation follow-up: [first assurance increment](../../claude-workflow/docs/2026-09-04-assurance-first-increment.md).
Retry follow-up: [third assurance increment](2026-09-04-assurance-revalidation-increment.md).
The findings below describe the audited revision; the follow-up tracks subsequent repairs.

## Conclusion and operating context

Keep the dispatcher as a distinct, contract-led construction workflow. Its
dependency graph, worker isolation, deterministic checks, review, recovery,
and supervision fit large services and products. Do not replace it with an
interactive Tasker running inside every dispatched task.

The operator clarified the actual lifecycle:

1. Define the product and develop a thorough PRD.
2. Investigate unknowns; design, exercise, and load-test the data model.
3. Review the model and scaffold; establish the contracts.
4. Dispatch a large task graph, with critical components and logic/state-flow
   documentation receiving deliberate attention.
5. Have an agent supervise and escalate decisions to the operator.
6. Integrate on a development branch, then perform operator testing before
   entering the subsequent testing cycle.

Consequently, an intermediate integration is **not production approval**.
Findings below distinguish unsafe intermediate behavior from missing final
acceptance guarantees. The review does not claim that the current dispatcher
directly deploys untested code to production.

Recommendation: put both workflows in one modular, agent-neutral repository,
sharing quality machinery but retaining their different purposes. See
[the architecture recommendation](../../claude-workflow/docs/2026-09-04-agent-neutral-architecture.md)
and [the workflow assessment](../../claude-workflow/docs/2026-09-04-workflow-quality-assessment.md).

The operator further clarified that Tasker also builds real systems needing a
healthy engineering process. Both workflows should therefore have strong
assurance by default. Any lighter experimental profile must be explicitly
invoked; uncertain requirements or vibe coding must not automatically lower
the quality bar.

## Scope and verification

The audit began at `1068521417d3cbab2b02fc00c19f84ec60a3be2e` with existing
changes to `src/claude_dispatcher/run.py` and an untracked
`tests/test_dry_run_integration_mode.py`. Those were left untouched. Concurrent
work committed them as `a008608`; a subsequent documentation commit advanced
HEAD to `c291a400ed3a93e18807cb96c872e15af5fbbfcc`. The runtime files cited in
the findings did not change between those revisions.

Read-only inspection covered onboarding, orchestration ownership, the main
execution/review/integration paths, classification, PR authorization, testing,
CI, and relevant existing redesign plans. This is not an exhaustive audit of
every module, product service, provider CLI, or deployed repository protection.

Verification in the existing workspace:

- Python 3.14.4; all 3,984 collected repository tests passed.
- `tools/t26_lint.py` passed, including peer citations at their pinned revisions.
- Two expected boundary-test warnings identify planned implementation modules
  that are still absent. Passing preliminary boundary tests does not establish
  that the proposed boundary is wired into production paths.
- Nine additional characterization probes confirmed the behaviors below.
  Their passing assertions describe the current defects, not repaired behavior.
- Two probes used real merges in disposable repositories; another drove the
  real dispatch loop with the repository's fake implementer and stub reviewers.
  No paid models, external PRs, deployments, or real-repository merges ran.

Commands:

```sh
TMPDIR=/var/tmp/dispatcher-quality-audit.KpW6IT PYTHONPATH=src .venv/bin/python -m pytest tests/ -q --tb=line --basetemp=/var/tmp/dispatcher-quality-audit.KpW6IT/pytest
.venv/bin/python tools/t26_lint.py
TMPDIR=/var/tmp/dispatcher-quality-audit.KpW6IT PYTHONPATH=src .venv/bin/python -m pytest /var/tmp/dispatcher-quality-audit.KpW6IT/test_quality_audit.py -q -o addopts='' --tb=short --basetemp=/var/tmp/dispatcher-quality-audit.KpW6IT/probes
```

Probe artifacts are temporary, not a durable replacement for project regression
tests. No production source or existing tests were edited during this audit.

## What to preserve

- Single-orchestrator ownership: dispatcher schedules, gates, integrates, and
  records; implementer agents implement. See `docs/architecture/single-orchestrator.md`.
- Contract-first planning, scaffold/seal/body role separation, and explicit
  adjudication of shared-contract deviations.
- Real worktree and merge tests, behavioral negative cases, independently
  authored boundary goldens, and tests for crashes and retries.
- Append-only, hash-chained journaling with explicit outcomes and reasons.
- Mechanical verification and seal inversion; prose assertions are not the
  only evidence the system gathers.
- Pin-then-judge PR authorization: `merge_engine.py:228` names a commit before
  classification and carries the authorized SHA to the merge operation.
  The external-approval path also requires the approving review's commit.
- Stalled review loops escalate rather than converting exhaustion to approval.

These are substantial assets. Fixing the acceptance boundaries is more valuable
than rewriting the dispatcher from scratch or merely increasing reviewer count.

## Confirmed findings

P1 means repair before relying on the affected automated assurance. P2 means a
policy/integration improvement whose urgency depends on the stage's declared
guarantees. Neither label claims a demonstrated production incident.

### DP-01 — Panel approval can coexist with rejection and HIGH findings

Priority: P1 for production-bound critical work; part policy conflict, part bug.

`src/claude_dispatcher/cross_family_reviewer.py:1625` aggregates using a
corroboration rule: any CRITICAL blocks, but otherwise two dissenting families
are needed. One HIGH dissenter and two approvals therefore produce `approve`.
That is intentional in this implementation, but conflicts with the workflow's
blocking-HIGH policy and with `reviewer_prompts/_shared.md:3`, which promises
unanimity. The aggregation function has no risk-tier parameter.

More directly, the minimum valid-seat count becomes one for a one-seat panel,
while the dissent threshold remains two. A sole reviewer returning `REJECT`
with a HIGH finding still produces `approve`. Both cases were reproduced.

Change: make panel composition and acceptance explicit, shared policy. Resolve
each blocking finding with a fix or recorded evidence-based adjudication; a
different reviewer failing to mention it is not evidence that it is false.
Enforce required seat availability, severity thresholds, and any retained
dimension floors mechanically. Single-seat rejection must never approve.

Acceptance: exercise every panel size with approval, rejection, missing seats,
parse errors, and all severities, including critical-domain policy. Assert
consistency between the verdict, open findings, and required evidence.

### DP-02 — Panel corrections bypass renewed mechanical verification

Priority: P1. Reproduced through the dispatch loop.

The mechanical, role/scope, and seal checks occur before the panel. The panel
loop at `orchestrator.py:2208` can call `_spawn_panel_iterate` at line 3416,
which requires only a clean agent exit and an advanced branch/base commit.
The loop then reruns the panel, not the earlier mechanical/role/scope/seal
checks. Integration follows after panel approval.

An isolated critical-task probe first passed a real configured test. Its fake
panel-correction worker then committed a regression. Stub reviewers approved
that new revision. The dispatcher exited zero with `status: Done`,
`mechanical_verification: passed`, and `panel_consensus: approve`; running the
configured test against the final worker tree failed.

Change: any code-changing corrective step invalidates evidence affected by the
change. Route all mutation paths back through a shared verification boundary,
including role/scope enforcement. Bind results to exact source and base SHAs,
configuration/policy versions, and invocation identity. Do not merely add an
instruction telling the corrective agent to rerun tests.

Acceptance: have the corrective worker break a test, violate ownership, change
a contract, or leave uncommitted files. Each must prevent a stale passing state.
Also test the analogous paths after verifier fixes and integration codegen.

### DP-03 — Classification accepts malformed policy data and can degrade open

Priority: P1 for required classification.

`classification.py:157` defaults missing policy fields and coerces values.
The strict subprocess wrapper accepts exit-zero `{}` as a low-risk result with
no financial/human-approval flags. A string `"false"` for `panel.reduced`
becomes boolean true and suppresses `requires_full_panel`. Both were reproduced.
The empty object alone defaults to a full panel; it is not itself proof of a
panel skip or automatic financial merge.

Separately, `_panel_gate_classification` at `orchestrator.py:2667` uses the
lenient wrapper. Classifier failure leaves the metadata-based skip intact.
A nonexistent explicitly configured classifier also looks like absence.

Qualification: the PR risk path in `risk.py:612` uses complete SHA-pinned
diffs and fails elevated on a present classifier's execution error. It also
retains independent risk rules. The weaker panel fallback must not be confused
with that stronger path, nor described as proof of universal auto-merge bypass.

Change: validate a versioned closed contract, including actual booleans,
required fields, allowed values, and cross-field consistency. Required mode
must distinguish unavailable, failed, malformed, empty, and successfully
classified. Make optional/legacy behavior an explicit operator-selected mode.

Acceptance: missing fields, wrong types, unknown enum values, inconsistent
fields, invalid explicit paths, tool failure, and unavailable tools cannot
silently reduce required assurance.

### DP-04 — Review-sized diffs are reused for safety classification

Priority: P1 when path-derived review is required; otherwise P2 review coverage.

`cross_family_reviewer.py:707` truncates diffs to a default 24,000 lines and
excludes selected generated/dependency files. Both the panel's classification
context and the metadata-skip safety net consume this representation.
A probe placed a wallet change after the default line budget; the returned
diff omitted that path. The omission is announced in text, but is not a typed
incomplete-review result that blocks acceptance.

Change: derive risk from a complete immutable changed-file/dependency manifest
and the complete required semantic inputs. Budgeted review chunks are a separate
representation. Track which files and affected consumers were reviewed; do not
approve an unreviewed remainder. Treat generated files, lockfiles, migrations,
and schemas according to their impact, not solely their suitability for prompts.

Acceptance: late-sorting critical paths, oversized files, generated changes,
renames, and diff failures must retain classification and review completeness.

### DP-05 — Review processes are not bound to the reviewed worktree

Priority: P1 for review provenance; confirmed invocation-level gap.

`_run_cross_family_panel` knows the task worktree, but passes a diff and branch
labels rather than a pinned review worktree to `run_panel`. `Reviewer` has no
worktree argument. `CodexReviewer._invoke_cli` at line 1058 invokes the CLI
without `cwd` or a directory argument and requests `workspace-write`.

A mocked process invocation confirmed those arguments. This demonstrates lack
of isolation/binding, not that a real reviewer actually edited or read the
wrong file during this audit. Depending on launch location, supplemental file
reads can refer to the dispatcher's checkout rather than the reviewed commit.

Change: review a pinned snapshot with an explicit working directory. Keep the
authoritative snapshot read-only; provide isolated writable scratch space for
tests if necessary. Record model, effort, provider/CLI identity, prompt digest,
and reviewed subject. Verify that review did not change the subject.

Acceptance: deliberately different base/feature files, alternate process CWD,
branch movement, and attempted source writes must not change what is reviewed.

### DP-06 — Direct integration deletes unrelated untracked files

Priority: P1. Reproduced in a disposable Git repository.

`auto_integrate.py:206` runs `git clean -fd` in `repo_root`, assuming every
non-ignored untracked file is integration residue. A deliberately unrelated
notes file was deleted by a successful integration. This is unsafe even on a
development branch and independent of production release policy.

Change: integrate in a dispatcher-owned temporary worktree. Refuse or surface
unexpected files rather than clearing a developer's checkout. Cleanup must be
restricted to artifacts the dispatcher created and can identify.

Acceptance: untracked files/directories survive both successful and failed
integration. Test dirty tracked state and concurrent activity too. The audit
deleted no files in either actual project repository.

### DP-07 — Integrated-tree verification is narrower than task verification

Priority: P2 for the operator's intermediate branch; P1 if treated as acceptance.

`auto_integrate.py:66` hardcodes six project-specific Go module locations.
`_build_check` at line 478 runs build/vet, not the repository test command;
unrecognized modules and Python/TypeScript changes get no equivalent check.

A real two-branch fixture passed its configured invariant test independently
on each branch. Their conflict-free merge violated the invariant. Integration
still returned `integrated`, committed the merge, and reported no services
built. This illustrates semantic cross-task interaction, not a production bug
in the user's product.

Change: discover affected modules and consumers through language adapters.
Run stage-appropriate checks against the assembled tree, including codegen.
Do not require deliberately unfinished scaffold/seal stages to masquerade as
fully green: give them explicit readiness states and planned-red allowances.
Require complete integrated acceptance at critical milestones and before the
branch is promoted into the operator's testing cycle.

Acceptance: individually green but incompatible tasks must fail the appropriate
integration checkpoint. Planned-red stages must remain distinguishable from
accepted implementation, and downstream work must consume the promised state.

## Additional policy recommendations

### Do not equate all Done states with the same assurance

`orchestrator.py:5262` intentionally skips mechanical verification when no
test command is configured, preserving backward compatibility. That may be
reasonable for explicitly experimental work or selected scaffold roles, but
production-bound implementation should require a configured test policy. Record stage outcomes
such as scaffold-ready, seal-ready, implementation-verified, integrated, and
ready-for-product-testing without implying final release approval.

### Keep the supervisor within explicit authority

Let it observe progress, identify stalls, retry approved transient failures,
pause affected subgraphs, and request human decisions. It should not silently
relax acceptance criteria, rewrite locked contracts, discard independent tests,
or turn failed evidence into a waiver to keep the run moving. Questions should
include the decision, relevant evidence, affected tasks, and consequences.

### Carry design evidence through construction

Preserve the reviewed data model, load-test workload/results, contract version,
state/logic flows, failure semantics, acceptance requirements, and unresolved
assumptions as a versioned handoff. Tie critical invariants to independent
acceptance tests against real storage/services. If a contract changes, record
the decision and invalidate affected evidence before resuming dependents.

### Finish existing convergence work rather than competing with it

`docs/plans/2026-08-02-classification-gating-design.md` already identifies
duplicated decisions, permissive states, subject-bound evidence, and incomplete
subjects. Reconcile these findings with that plan and test the live paths;
the proposed design must not be credited as an already-enforced guarantee.

Phase 14 in `docs/improvement-plan.md:764` is also well aligned: keep authored
task definitions separate from runtime state, distinguish requested model from
model used, reconstruct state from the journal, provide operator commands, and
key state by repository and epic. Adopt that direction in the shared design;
do not add a second competing state store with separate authority.

## Suggested repair order

1. Preserve user files and invalidate verification after every mutation.
2. Reconcile panel policy and implement strict classification/completeness.
3. Bind reviewers and evidence to immutable subjects.
4. Complete definition/state separation and shared quality-tool contracts.
5. Add language-aware assembled-tree checkpoints and explicit stage readiness.
6. Migrate both entry points to the shared machinery, retaining their different
   interaction and supervision models.
