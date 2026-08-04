# Classification → Gating Boundary: Implementation Plan (v3)

**Input:** design v20 + its round-20 dispositions (`docs/plans/2026-08-02-classification-gating-design.md`) — §12 PASSED.
**Baselines:** design T26 citations are pinned in the design's own header; this plan's units re-pin at merge time.
**v2.4 → v3:** restructured after building the A-stream and reviewing it five times at full scout coverage. Two things were wrong with v2, both structural rather than clerical: (1) each "PR" carried six to ten deliverables in one paragraph, so the first grew to 20,700 diff lines and could not be reviewed in a single panel; (2) it let a mechanism ship without its consumer, so operational policy (credential-mode threading, admission ceilings, operator attribution, dedup, fence provenance) arrived as dark code reviewed against hypothetical callers — an unbounded surface. v3 replaces 7 PRs with **18 units**, each sized to one panel, each pairing a mechanism with the caller that pins it. §5 records what the A-stream taught; the measurements that justify these rules are in §5 too.

---

## 0. Standing dispositions (the §12 MAJOR-disposition pass)

### 0.1 Observability: targets AND emitters
**Targets** (values tunable; obligations not): classifier availability ≥ 99.5%/7d (breach ⇒ page; >1h ⇒ operator LEGACY choice) · classifier p95 < 30s · panel p95 < 20min FULL / 6min SINGLE · append lag p95 < 10s · CAS conflicts < 1% + 10×-spike alarm · `OUTCOME_UNKNOWN` > 15m page · hold age > 24h page / > 5 open ⇒ halt admissions · epoch mismatch/gap/fork ⇒ page + halt base · recovery ceiling 10k events / 30s reduce ⇒ halt admissions · `OPERATOR_ATTESTED` vs `HUMAN_IDENTITY_ENFORCED` counted separately; any audit row missing `assurance`/`authorization_kind` ⇒ alarm.

**Emitters** (metric → first unit): classifier latency/availability + `classifier_contract` → B5 · lifecycle/hold/epoch/CAS/`subject_mismatch{stage}`/SEPARATED→SHARED flips → C2–C4 · verdicts-by-rule, outcomes-by-kind, authorization/assurance counters, LEGACY×financial, `trace_id` spanning classify→effect → C7 · T25 cost counters → C8. **C8's gate includes a metrics smoke: every target above has a live emitter.**

### 0.2 `BoundaryError` — closed v1 universe
`BoundaryError{code, phase ∈ {PREFLIGHT, CLASSIFY, PANEL, AUTHORIZE, EFFECT, RECOVER, ROLLBACK}, retriability ∈ {RETRIABLE, TERMINAL, OPERATOR}, operator_action}` · unknown code at any consumer ⇒ TERMINAL · CLI exit `0/2/3/4` = ok/TERMINAL/RETRIABLE/OPERATOR · every code carries a metric name, generated with the type. Codes: `CLASSIFY_FAILED(kind)` · `FENCE_MISMATCH` · `EPOCH_GAP` · `EPOCH_FORK` · `CHAIN_BROKEN` · `CAS_CONFLICT` · `ILLEGAL_TRANSITION` · `CARRIER_UNPROTECTED` · `CARRIER_UNREADABLE` · `HOLD_ADMISSION_CEILING` · `WEBHOOK_EVIDENCE_UNAVAILABLE` · `ROSTER_INCOHERENT` · `UNMERGEABLE_CONSENT_ATTEMPT` · `ROLLBACK_UNSUPPORTED_MAJOR` · `BINARY_DIGEST_MISMATCH` · `SCHEMA_MAJOR_UNKNOWN` · `EVENT_PAYLOAD_DIVERGENT` · `RECOVERY_CEILING` · `UNIT_MEMBERSHIP_MUTATION`. Widening the set is a plan amendment, never an in-flight addition.

### 0.3 Conformance/reference kit — deferred post-cut-over (the design's standing rationale).

### 0.4 Operator items — gate **C8**, nothing earlier
- §0.2(c) channel-level attestation ratification; §0.3–0.5 amendment ratifications.
- `STANDING × REJECT_RESTORE_HOLD`: the safer reading is implemented (`auto_release_after_reject_restore: false`) because `HELD_FOREIGN` is the only state auto-release can fire from, so demoting there re-opens non-operator release on a hold an operator just refused. Needs ratifying as a design amendment.
- Auto-release webhook provenance: requires a design §9 amendment (the doc==artifact gate correctly refuses unilateral field additions); recorded `blocks_pr6_cutover`.
- SHARED is the supported launch mode with its named residuals.

### 0.5 Round-6 deferred-MAJOR ledger — closed by absorption-by-construction across design rounds 7–20, with the residual accepted (unchanged from v2).

---

## 1. Invariants every unit inherits

Stated once because each was learned by shipping its violation. A unit that breaks one is not mergeable regardless of its findings count.

1. **One public entrypoint per decision.** If two callables must agree about the same state, they are one callable plus pure accessors over its result. Patched divergence recurred four times (fold vs reducers: algebra, identity replay, dedup, then credential mode); unification ended each. Corollary: run-scoped context (credential mode, protocol epoch, roster) is a **required argument of the single entrypoint**, never a per-function parameter some caller can omit.
2. **Validate before apply.** No transition, append or mutation is recorded until every check on that input passes. A halt leaves state unmutated, and the seal asserts *that*, not merely the halt code.
3. **Total dispatch over closed unions.** Every consumer dispatches exhaustively with `else: raise`. Fixing the reachable instance is not fixing the property — `aggregate` discarded a *blocking* verdict, was fixed, and still discarded an *unparseable* one.
4. **Absence is a named state.** No field defaults to the permissive value; missing input at a gate ⇒ typed halt (`skills/explicit-state.md`).
5. **One fact, one place — including protections.** Redundant guards weaken seals: two globs covering one fact let a mutation delete half while the suite stayed green.
6. **Policy comes from the protected base.** Nothing on the gating path reads its parameters from the branch under review or from a working tree (design §8). Done for Python in `fix/authority-doc-carveout`; open on the Go side (§4a).
7. **No claim without its mechanism** — in code, comments, docs and this plan. A comment asserting a safety property the code lacks is a finding at the severity of that property.

## 2. Rules that bind every unit

- **Size**: a unit's diff must be reviewable in ONE critical-tier panel. Measured ceiling ≈ **3k lines**; above ~6k the panel demonstrably loses scouts (§5). Slicing a review is a recovery tool, not a plan.
- **Coverage is part of the verdict**: every panel run records scout completion and seat count. A run with unverified scouts **is not a verdict**.
- **Merge gate**: zero **gate-affecting** findings (changes a gate decision: fence value, authorization, panel/merge verdict, halt behaviour, or a seal's validity) + a **written disposition** for every remaining finding (fixed / accepted-with-rationale / booked to a named unit). Severity orders the work; it no longer decides the gate alone.
- **A mechanism ships with its consumer.** Operational policy with no caller is reviewed against hypothesis and never converges. If a unit would introduce policy whose caller lands later, the policy moves to that later unit and this one ships types/data only.
- **Generated types are the sole source**; hand-written redefinition of a generated name fails an import-boundary test.
- **Dark mode**: `boundary/` is test-only until C8; the architecture test fails on production imports, and C8 is the sole wiring unit.
- **Execution protocol per unit** (operator directive): scaffold (typed signatures, `NotImplementedError`) → **seal author ≠ scaffold author**, failing seals committed red, composition seals first-class (crash histories, `reduce == state`, property-based) → module-grain body fan-out → **body agents may not touch tests, scaffolds, schemas or generated files** (enforced by `scripts/check_body_branch.sh`, never self-report) → disputes over a test *or* a frozen signature stop and escalate to a separate adjudicator; adjudication is final for the round, a repeat dispute escalates to the operator.
- **Cross-repo**: `schema/` is a versioned contract package; every schema either repo tests against is digest-cross-checked in both CIs at one pinned source commit.
- **Agent hygiene** (learned the hard way): commit whenever green and never batch — a session limit or dropped connection then costs one chunk, not a session; every agent uses a **private scratch directory** (a shared one was overwritten mid-run by a concurrent agent); never run an agent in a checkout another agent is writing.

## 2a. Phases inside a unit, and who drives

Every unit decomposes into **three mandatory phases plus one conditional**, because the protocol's value comes from different parties owning them. This is the granularity a task runner needs, and the granularity a human handoff needs:

| Phase | Owner constraint | Artifact | Done when |
|---|---|---|---|
| **P1 scaffold** | any author | typed signatures from the generated types + contract docstrings + `NotImplementedError` bodies | reviewed for contract fidelity to the design, before any body exists |
| **P2 seals** | **must differ from P1's author** | failing seal tests mapped to their T-obligations, incl. composition seals (crash histories, `reduce == state`, property-based) and state-unmutated assertions | committed RED; a seal that passes against a stub is vacuous and rejected |
| **P3 bodies** | module grain, parallel, **must differ from P2's author** | implementations only | suite green; `scripts/check_body_branch.sh` shows no diff under `tests/ schema/ **/generated/**` and no changed signature |
| **P4 adjudicate** | **must differ from P1–P3** | ruling on a disputed test or frozen signature, with its design citation | fix lands in its own reviewed commit; repeat dispute on the same artifact escalates to the operator |

**Who drives, and in what order.** The dispatcher is not yet a safe or capable driver for these units, on two grounds that are both fixable and are themselves scheduled below:

1. **Self-gating.** Most units repair the gate path the dispatcher would be gating them with. Two live fail-opens remain in that path (§4a), and a third is fixed but unmerged. A dispatcher must not be the authority over its own repair — so hand-driven agents run until the gate path is trustworthy: close the A-stream → merge the base-pinning fix → land **B1/B2** (which closes §4a.1) → from **C1** onward the dispatcher drives.
2. **The protocol is not expressible.** Verified against the current task schema: `depends_on`/`blocked_by` exists (so unit ordering is fine) and `agent:` selects a model — but there is **no role and no immutable-paths concept**, so "seal author ≠ scaffold author" and "body agents may not touch tests" would be honour-system. Honour-system is precisely what produced 24 vacuous seals. **D1 supplies it.**

The panel/recheck/merge machinery is already good and stays the dispatcher's job throughout; what is missing is the build-side role protocol, not review.

## 3. Units

Dependencies are strict: a unit may not begin before its predecessors merge. Sizes are diff targets.

### Stream A — drift-proofing (`claude-dispatcher`; no runtime behaviour)
| Unit | Deliverable | Seals | ~size |
|---|---|---|---|
| **A1** | `tools/t26_lint.py` + CI workflow + pre-push hook + `.agent/risk-paths.json` tiers + design baseline re-pin | lint self-passes; 10 planted violations each asserting their own message; peer-present/peer-absent matrix | 1.0k |
| **A2** | the five `schema/*.yaml` as validated data + `doc == artifact` table generation | schema well-formedness; doc-table equality with two planted drifts | 1.5k |
| **A3** | `fsmgen` → generated **types only** (enums, frozen dataclasses, wire validation, `BoundaryError`) | T1, T4, T5, T15, enum exhaustiveness, error-map element-wise | 2.0k |
| **A4** | `fsmgen` → `apply()` transition relation for both machines + T19 **artifact-fidelity** goldens against the hand-written oracle | T19 transition rows, oracle-independence, T6, T8/T9 fail-closed, dark-mode gate | 2.5k |

**A-stream status:** built as one 20.7k unit on `feat/PR0-generated-truth` before this restructuring and reviewed in five slices at near-full coverage. It ships as A1–A4 combined **once** its 5 CRITICALs, its vacuous seals and its CI findings are closed; its operational semantics are booked to Stream C (§4b). No future unit ships at that size.

### Stream D — make the units machine-drivable (`claude-dispatcher`)
| Unit | Deliverable | Seals | ~size |
|---|---|---|---|
| **D1** | task-schema support for the §2a protocol: `role: scaffold\|seals\|bodies\|adjudicate`; `immutable_paths:` per role; a preflight refusal when a unit's seals-phase agent equals its scaffold-phase agent; `scripts/check_body_branch.sh` wired at PR time and in CI | role/immutability rejection rows (a bodies task touching `tests/**` fails preflight AND at PR time); same-author refusal; a unit whose phases are out of order fails to plan | 1.5k |

Ordering: D1 lands before the dispatcher drives any unit. It does not block hand-driven work, so A-stream, the base-pinning merge and B1/B2 may proceed in parallel with it.

### Stream B — the classifier boundary (mechanism + caller in the same unit)
| Unit | Deliverable | Seals | ~size |
|---|---|---|---|
| **B1** | `cmd/classify`: `-contract-version 1\|2`, v2 envelope (`config_scaffold` required; no `config_sha256`/`classified_at`), capability probe with contractual exits | T10 goldens both contracts; v1 differential vs the pinned binary (semantic equivalence, volatile fields excluded) | 1.5k |
| **B2** | `cmd/classify`: framed `-authoritative-stdin` + response wrapper with **producer-computed** digests | octet-level frame goldens; malformed-length / truncation / trailing-data / corrupted-diff vectors | 1.5k |
| **B3** | dispatcher parse: sealed `ClassifyOutcome`, `__post_init__` producer equations, `parse_classification`, bounds, `UNKNOWN_INTENSITY`, `V1_COMPAT` desugar | T7 (stub from the B1 binary), T11, T16, T22, T30 consumer half | 2.0k |
| **B4** | `MergeSubject` / `AttemptSubject` / `ClassifierAuthority` / `AuthorityFingerprint` + canonical preimages | independent preimage oracles incl. the retarget property; guarded-constructor rows | 1.5k |
| **B5** | §8 authority channels **with B3 as the caller**: GraphQL ref/tree-entry/blob, two-request compare + octet preimage, `O_NOFOLLOW` → hash-vs-manifest → `fexecve`, hardened-git offline | T13, T21 both halves, T28 provenance, "pathname never valid in REQUIRED" deny row | 2.5k |

### Stream C — effects (each mechanism with its carrier)
| Unit | Deliverable | Seals | ~size |
|---|---|---|---|
| **C1** | protected carriers: bootstrap ceremony (orphan commit → `createRef` → protection), `createCommitOnBranch` append protocol, CAS retry, `updateRefs` for non-append moves | carrier absent/mutable ⇒ halt; CAS conflict; duplicate `event_id` byte-identity | 2.0k |
| **C2** | the reduce runtime over C1's carriers — **one public entrypoint taking the run context**; projection machine; epoch in reduced state; dedup; per-base halt isolation | full T19 crash/race/fork/gap/cycle histories; state-unmutated on every halt; property-based reducer tests | 2.5k |
| **C3** | fences: `DurableAuthority` / `FenceSnapshot` / `SeparatedFence` / `SharedFence` (typed to refuse branch heads) / `SharedRestartAuthority`; protocol-epoch fencing | pre-effect equality set; forged terminal under SHARED; mode-boundary type test | 2.0k |
| **C4** | section B: holds, `hold_lifecycle`, webhook `VERIFIED_API` (GUID → numeric resolution), `occurrence_seq`, admission ceiling, operator attribution | every section-B disposition row; ceiling backpressure **and its release path**; attribution required | 2.0k |
| **C5** | `boundary/panel_runner.py` consuming `PanelPlan` only; `RosterSnapshot`; `aggregate`/`required_seats` generated from schema | T2 strategy × intensity × outcome; roster provenance; **total** outcome dispatch (blocking, unparseable, unknown) | 1.5k |
| **C6** | doors 0–3 as pure functions over `MergePlan`; the ordered construction list; effect inventory | T12 door matrix (bot/self/stale/out-of-set/renamed/base-advanced/Unmergeable-consent); T14 | 2.0k |
| **C7** | consent-at-read + evidence-at-read; `authorization_granted`; §9 event emission with envelope + fingerprints; audit rows refusing missing `assurance` | T3, T18, T20, T27, T29, T31 | 2.0k |
| **C8** | **cut-over** (sole wiring unit): preflight REQUIRED\|LEGACY + genesis; route `merge_engine`/`merge_prs`/`auto_integrate` through the doors; delete `orchestrator.py:2049`'s re-resolution, the `cross_family_panel` re-read, the `_has_commits_on_branch` direct-to-base branch and both legacy panel call sites; sidecar writes; fill the door-entrypoint allowlist | **Gate:** §0.4 ratifications · rollback drill · metrics smoke · component-version matrix · T2 singularity AST · T12 inventory · T23 tamper-vs-live-door · T25 · T26 · manifest-pinned classify digest refused on mismatch | 1.5k |

## 4. Live holes and forward dispositions

### 4a. Found while building the A-stream (tracked, not closed)
1. **The Go classifier reads its rule table from a working tree** — `orchestrator.py:1905,1993` pass `-worktree <repo_root>`, so an uncommitted `.agent/risk-paths.json` edit changes the table for every classification. **B2/B5 close it** (framed stdin + the §8 fetch). Interim mitigation landed: `**/.agent/**` sits in the authority floor, so touching it elevates.
2. **The merge verdict is computed on a local ref and enforced on origin's PR head with no SHA pin** — a commit pushed in between is never gated. Needs `gh pr view --json headRefOid` + `--match-head-commit`. Its own unit, unscheduled.

### 4b. A-stream operational findings booked forward
Credential-mode threading and spurious mode halts → **C2/C3** (they need the run context a real caller supplies) · admission-ceiling backpressure and its release path → **C4** · operator attribution on section-A reconciles → **C4** · §9 singles bypassing dedup, and the derived-id core omitting fence/evidence → **C2** · `ACCEPT_OURS` fence provenance and `new_oid_source` → **C3** · auto-release from-states, the parked-subject conjunct, per-delivery vs per-hold key → **C4**. Each is recorded with its finding text in the A-stream merge PR body; **C2–C4 may not close review without addressing their inherited list.**

## 5. What the A-stream taught (so it is not re-learned)
- A 20.7k-line review completed **1 of 6 scouts and reported 7 findings**; the same tree in five slices completed 6/6 on four of five slices and reported **5 CRITICAL / 68 HIGH / 107 MEDIUM**. A too-large review returns a *clean-looking* number, which is more dangerous than a bad one.
- Severity was assigned by current blast radius: a swallowed CRITICAL blocking verdict came back MEDIUM beside a 7-parameter style nit. `roles/reviewer.md` now rates staged/dark code by what it gates, and notes that a dark-code review returning only MEDIUMs is a signal to re-check that rule.
- **24 seals were vacuous** when an independent author mutation-tested them — including every deny row for the fail-closed gates. Seals require mutation proof, not authorship.
- One author writing both a fix and its check produced a circular oracle (T19 expectations generated by the reducer under test). Separating the roles caught it — and caught three operator/orchestrator instructions that were themselves wrong.
- Instance-level fixes regenerate the defect at the next seam: four rounds of fold-vs-reducer divergence, two of `aggregate` discarding an outcome. Invariants 1 and 3 exist to end that.

## 6. Test-obligation map (linted by A1 against this document)
T1/T4/T5/T15 → A3 · T6/T8/T9/T19-transitions/oracle-independence → A4 · T26 → A1, permanent · T10/T30 → B1/B2 (+ consumer halves in B3) · T7/T11/T16/T22 → B3 · T24 → B4 · T13/T21/T28-provenance → B5 · T19-full/T23-component → C2 · T28-predicates → C3 · T2 → C5 · T12-doors/T14 → C6 · T3/T18/T20/T27/T29/T31 → C7 · T2-singularity/T12-inventory/T23-tamper/T25 → C8 gates. Multi-unit obligations name each half; every non-retired T appears at least once and A1's lint enforces that against this section.

## 7. Risks
Cross-repo schema drift (→ the contract package + peer SHA pins) · codex seat quota (optional; 4/5 is the working panel) · SHARED residuals ship as designed and are rendered in run reporting · citation brittleness: cite symbols, not line numbers.
