# Isolated Git object reads: fifth assurance increment

This continues the [pinned configuration repair](2026-09-04-assurance-policy-increment.md)
at `e721df26d4dad19600b1a1aab4dc5c7a1d82742d`. It is a bounded repair to the
existing object-store reader, not the B5 authority channel or C8 cut-over.

Next increment: [worklist recovery and decision separation](2026-09-05-assurance-worklist-increment.md).

## Reproduced failures

Eleven initial tests failed before the repair, against real disposable Git
repositories. Their outcomes were not all fail-opens:

- Replacing a commit, tree or blob made a captured policy SHA return a different
  test command. A scripted worker installed a blob replacement while leaving
  the committed policy file unchanged; the dispatcher marked a broken candidate
  Done after executing the substituted `true` command.
- An inherited `GIT_DIR` selected a different repository's policy. Inherited
  common/object-directory overrides also interfered with reads; those probes
  raised errors rather than approving weaker policy.
- Inherited global/system configuration paths and injected configuration
  parameters made otherwise valid reads fail on unrelated invalid settings.
- Reading a missing policy blob in a partial-clone fixture fetched it implicitly
  from its local promisor repository. That probe used no external network.

Git documents that [replace refs change ordinary object reads](https://git-scm.com/docs/git-replace).
Its [environment controls](https://git-scm.com/docs/git#_environment_variables)
also permit repository redirection and configuration overrides, and provide
controls for replacement handling and lazy fetching. A SHA supplied to a Git
command is not, by itself, an isolated execution context.

## Repair

`repo_config._run_git` supplies a fresh child environment for each object read:
inherited `GIT_*` entries are removed; global/system configuration loading,
replace refs, lazy fetching, optional locks and interactive credential prompts
are disabled. Non-Git environment entries remain available. The parent
environment and the operator's replace refs are not modified.

Both subprocess execution and the injected runner receive the same controls.
Existing shared-reader consumers inherit the repair, including pinned mechanical
and seal configuration, role policy and signature-source reads. No second
policy parser or authority reader was introduced. Genuine file absence and
existing error/result types retain their meanings.

Required objects must be provisioned before verification. These reads do not
borrow global Git configuration or `safe.directory` exceptions; an unreadable
repository remains a failure. Normal checkouts, linked worktrees and bare
repositories are covered by positive controls.

## Deviation

- **kind:** shared-contract behavior tightening; no public return type or
  signature change. The injectable subprocess runner now receives `env` and
  must honor it, as a real subprocess runner does.
- **original:** object reads inherited the process's Git settings, honored
  replace refs and could lazily fetch missing objects.
- **changed:** the shared reader supplies explicit local-read settings for
  its child processes without mutating the parent environment or Git refs.
- **reason:** real-Git regressions showed substituted policy, unrelated
  configuration failures and an implicit fetch; one orchestration case reached
  Done despite a failing configured test.
- **blast_radius:** all consumers of `repo_config.blob_text_at`, including
  configuration and signature reads, and injected subprocess runners. Checkout
  ownership and pre-provisioned objects matter. No schema, v1 task-state field,
  model/provider routing or `boundary/` production import changed.
- **review status:** manual interactive repair, pending independent adoption
  review. Not formal scaffold/seals/body/adjudication acceptance; no production
  authorization is implied.

## Verification

The 11-case red baseline is `red.xml`; each failure is described above. The
first focused run passed 143 cases; shared-consumer and expanded controls passed
288 cases. Counts overlap and must not be summed as distinct coverage.

The new module has 16 cases. It includes real replace refs at three object
levels, real repository/configuration redirection, a real local promisor fetch
counterexample, the scripted-worker/real-test orchestration case, positive
repository layouts and injected-runner environment-isolation checks. The
runner checks exercise both supported result shapes and child-only mutation.
Agent verdicts are scripted, not live model evaluations.

The full working-tree suite passed **4,092 tests**, with the same two pre-PR2
boundary allowlist warnings (263.27 seconds; `full.xml`). T26 lint and
`git diff --check` passed.

Mutation probes ran only in an owned throwaway clone, each with a 120-second
outer bound. Source/test hashes matched the working-tree inputs before the
control run and after restoration. The 16-case control passed both times.

| Removed protection | Intended assertion failures |
|---|---:|
| Ignore replace refs | 4: commit, tree, blob and dispatcher Done-bypass cases |
| Discard inherited Git overrides | 1: foreign-repository policy selected |
| Disable lazy fetch | 1: missing policy silently fetched |

These are three selected mutations, not a comprehensive mutation score. The
probes changed no bounds, schemas or files in either working repository.
Local reports are retained under `/var/tmp/assurance-git-policy.FmEHxI/`;
post-commit verification is recorded separately there. These are diagnostics,
not protected approval evidence.

## Remaining boundaries

- **Not a complete trusted Git context.** Repository discovery, local Git
  configuration, alternates, symbolic-ref movement, object-store integrity,
  `PATH`/executable identity and non-Git environment variables remain separate
  concerns. A mutable local `.git` directory is not a protected authority.
- **Toolchain assurance remains open.** Git 2.53.0 is the exercised toolchain.
  Version/capability attestation is not added here; older Git is not claimed to
  honor every environment control. The planned authority channel must make
  those capabilities enforceable rather than assumed.
- **Other Git operations are unchanged.** Ref capture, diff/status operations,
  classification and integration were not migrated to this reader's context.
  This patch cannot certify an entire role, review or merge decision.
- **The oracle and final tree still need protection.** Candidate scripts/tests,
  known-red authority, reviewer isolation, evidence reduction and final
  merged-tree verification retain the limitations in the prior handoff.

No repository consolidation, formal boundary-unit adoption, live model trial,
external PR, push or deployment is part of this increment. The workflow repo's
two pre-existing model-matrix YAML edits remain outside this work.
