# Pinned verification configuration: fourth assurance increment

This continues the [revalidation repair](2026-09-04-assurance-revalidation-increment.md).
It pins mechanical and seal configuration; it is not the planned complete
acceptance boundary, production approval or a new quality score.

The [fifth increment](2026-09-04-assurance-git-context-increment.md) addresses
replace refs and inherited Git settings in the shared object-store reader.

## Previously completed work, now committed

| Repository | Commit | Scope |
|---|---|---|
| claude-workflow | `143a6af` | Fail-closed selection, coordinated state updates and fresh review evidence |
| claude-workflow | `c83a0ba` | Offline evaluation pilot, assessments and shared-repository proposal |
| claude-dispatcher | `52cd01e` | Corrective revalidation and preservation during auto-integration |

No commits were pushed. The two existing model-matrix YAML edits were excluded
and their file hashes were unchanged. The earlier increment records describe
the working-tree state at their respective handoffs; they are historical
verification records, not current release authorizations.

Clean throwaway clones of these commits were checked before continuing:
all eight workflow Go modules passed `go test -race -count=1 ./...`, the six
evaluation exporter/result-reader tests passed, and 52 dispatcher revalidation
and integration-preservation cases passed. Both clones remained Git-clean.
The full 4,038-test dispatcher run from the prior increment was against the
same source before commit; it was not repeated in that initial clone.

The evaluation reference fixture is a literal unified Git patch. Its context
prefixes intentionally trigger generic whitespace checks when that patch file
is first added. Its contents were preserved; other staged files passed those
checks, and the recorded offline reference controls remain the behavioral
validation. The Docker controls were not rerun just to commit unchanged inputs.

## The additional repair

The dispatcher captures the configured base commit before design or implementer
execution. Failure to capture it now blocks before a worker is spawned.
Mechanical verification, seal redness and seal inversion obtain their
configuration from that commit, not from the candidate's `.dispatcher.yaml`.
Corrective passes and new cascade rungs retain that policy source even if the
base branch moves during the task.

`repo_config.load_at_base` uses the existing object-store reader and returns
`BaseRepoConfig`: source reference, genuine file presence and parsed config.
The filesystem and Git entry points share one parser. Unreadable, malformed,
non-regular or non-UTF-8 base policy is refused, with no candidate fallback.
Genuine absence and a present file with no command remain distinct, journaled
legacy skips. Verification events include `policy_base_sha` for diagnostics.

Review and commit verification configuration on the intended base before
dispatching production-bound work. A candidate can be checked under the old
policy while proposing a policy edit, but that edit cannot set its own test
command or exclusion style. If the base has no test command, a new one added
by the worker does not retrospectively establish that tests ran.

## Deviation

- **kind:** new-surface (`BaseRepoConfig` and `load_at_base`), with tightened
  legacy consumer behavior. Existing filesystem-loader callers retain their
  return shape and parser rules.
- **original:** the first mechanical pass and every seal-inversion pass loaded
  candidate configuration. Mechanical retries retained the first candidate's
  configuration, which could already have been weakened.
- **changed:** the mechanical/seal family reads the captured base source and
  records it. A missing base is a blocking state rather than an optional
  coordinate with a candidate fallback.
- **reason:** real-Git cases demonstrated that deleting a configured test,
  replacing it with `true`, or removing its key could leave a failing candidate
  marked Done. Seal checks also read a different policy from mechanical checks.
- **blast_radius:** dispatcher mechanical/seal execution, helper callers,
  configuration loading and verification-event consumers. The base must carry
  the intended verification configuration before worker execution. No v1 task
  state fields, schema files or production imports of `boundary/` were added.
- **review status:** manual assurance repair, pending independent adoption
  review. This is not scaffold/seals/body/adjudication acceptance of a formal
  boundary unit, and does not authorize production use by itself.

## Verification

Ten initial behavioral regressions were observed failing for their intended
assertions before the repair. The first fixture draft had setup mistakes;
`policy-red-corrected.xml` is the valid red baseline, not that draft.
The repaired focused suites passed 135 existing/new cases and another 38
configuration/provenance cases. Their inputs include moving base refs, cascade
restarts, candidate deletion/weakening, invalid base configuration, missing
Git, timeout, symlink/directory policy and non-UTF-8 content. Git operations and
configured mechanical tests are real; agents and inversion outcomes in the new
orchestration cases are scripted. Existing real seal tests also run.

The full suite passed **4,076 tests**, with the same two pre-PR2 boundary
allowlist warnings as the previous increment (273.40 seconds;
`policy-final.xml`). T26 lint passed, including pinned peer citations, and
`git diff --check` passed. Final call-site/default-behavior documentation
corrections also passed the 56-case configuration/wiring/orchestration subset
(`policy-doc-claims.xml`).
The first full rerun also found a stale call-site claim after moving validation
into the shared parser, and a pre-existing test that mistook a capital `C` in
the test directory path for a listed Done task. The claim now names the actual
validator; the listing test asserts task headers and deliberately includes `C`
in the path. Neither correction weakens an acceptance rule. All 67 targeted
configuration, orchestration, wiring and unblock cases passed afterward.
Local diagnostics and test reports are retained under
`/var/tmp/assurance-commit.pCH0Ol/`; these are local verification records, not
protected approval evidence. No live model trials, external PRs or deployments
were performed.

## Remaining boundaries

- **Pinned is not independently protected.** This uses local Git objects and
  the configured base; it does not attest forge protections or operator
  approval. Hardened authority fetching, replace-ref/environment defenses and
  durable cross-invocation evidence remain in the planned boundary work.
- **The command is not the complete oracle.** Scripts and tests invoked by it
  still run from the candidate tree. Their integrity, toolchain/dependencies,
  execution isolation and coverage require separate controls. The known-red
  register also retains its existing authority path.
- **Other policy consumers are unchanged.** Classification, panel composition,
  aggregation and review working-directory findings remain open. Existing
  explicit skips and role-specific suite expectations are not tightened here.
- **The final merge still needs its own proof.** A pinned task configuration
  does not verify a later base advance, dependency combination, code generation
  or actual merged tree. No stronger autonomy should rely on this patch as a
  substitute for that integration boundary.
