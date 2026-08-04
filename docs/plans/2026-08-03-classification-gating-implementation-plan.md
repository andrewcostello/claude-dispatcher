# Classification → Gating Boundary: Implementation Plan (v2.2)

**Input:** design v20 + round-20 dispositions (`docs/plans/2026-08-02-classification-gating-design.md` @ 9c8d517) — §12 PASSED.
**Plan v1 → v2:** revised against the plan-level review (claude 2 BLOCKING + 4 MAJOR, grok 3 BLOCKING + 15 MAJOR/minor; codex quota-dead). Convergent core: v1 assigned the producer half of §8 and NO PR built the dispatcher half — the design's central mechanism would have arrived inside the cut-over PR. v2 gives it PR3. Full disposition table in §5.
**Baselines:** `claude-dispatcher@9c8d517`, `claude-workflow@2dcecfd2`. PR0's first commit re-pins the design's T26 citation baselines to PR0-time HEADs (adjudicated: the build directive superseded this line's original "plan-time SHAs"; pinned `claude-dispatcher@88cec333`, citations verified there).

---

## 0. Standing-item dispositions (the §12 MAJOR-disposition pass)

### 0.1 Observability: targets AND emitters (two tables — grok M7: targets without wiring is documentation theater)

**Targets** (values tunable; obligations not): classifier availability ≥ 99.5%/7d (breach ⇒ page; >1h ⇒ operator LEGACY choice) · classifier p95 < 30s · panel p95 < 20min FULL / 6min SINGLE · append lag p95 < 10s · CAS conflicts < 1% + 10×-spike alarm · `OUTCOME_UNKNOWN` > 15m page · hold age > 24h page / > 5 open ⇒ halt admissions · epoch mismatch/gap/fork ⇒ page + halt base · recovery ceiling 10k events / 30s reduce ⇒ halt admissions · **`OPERATOR_ATTESTED` vs `HUMAN_IDENTITY_ENFORCED` counted separately; any audit row missing `assurance`/`authorization_kind` ⇒ alarm** (grok M6).

**Emitters** (metric → locus → first PR): classifier latency/availability, `classifier_contract` distribution → PR3 · lifecycle/hold/epoch/CAS/`subject_mismatch{stage}`/SEPARATED→SHARED flips → PR4 · verdicts-by-rule, outcomes-by-kind, authorization/assurance counters, LEGACY×financial alarm, `trace_id` spanning classify→effect → PR5 · T25 cost counters → PR6. **PR6's gate includes a metrics smoke: every target above has a live emitter** (claude M4, grok M7).

### 0.2 `BoundaryError` — closed v1 universe (claude M3, grok M8)

`BoundaryError{code, phase, retriability: RETRIABLE|TERMINAL|OPERATOR, operator_action}` · **`phase ∈ {PREFLIGHT, CLASSIFY, PANEL, AUTHORIZE, EFFECT, RECOVER, ROLLBACK}` (closed)** · unknown code at any consumer ⇒ TERMINAL · CLI exit map `0/2/3/4` = ok/TERMINAL/RETRIABLE/OPERATOR · every code carries a metric name (code→metric map generated with the type). Codes:
`CLASSIFY_FAILED(kind)` · `FENCE_MISMATCH` · `EPOCH_GAP` · `EPOCH_FORK` · `CHAIN_BROKEN` · `CAS_CONFLICT` · `ILLEGAL_TRANSITION` · `CARRIER_UNPROTECTED` · `CARRIER_UNREADABLE` · `HOLD_ADMISSION_CEILING` · `WEBHOOK_EVIDENCE_UNAVAILABLE` · `ROSTER_INCOHERENT` · `UNMERGEABLE_CONSENT_ATTEMPT` · `ROLLBACK_UNSUPPORTED_MAJOR` · `BINARY_DIGEST_MISMATCH` · **`SCHEMA_MAJOR_UNKNOWN` · `EVENT_PAYLOAD_DIVERGENT` · `RECOVERY_CEILING` · `UNIT_MEMBERSHIP_MUTATION`**. PR2 seals a T1-style exhaustiveness test binding codes ↔ CLI ↔ metrics.

### 0.3 Conformance/reference kit — deferred post-cut-over (design's standing rationale). PR0's generated artifacts make later extraction mechanical.

### 0.4 Operator items — §0.2(c) + §0.3–0.5 ratifications gate PR6 cut-over. SHARED is the supported launch mode with named residuals.

### 0.5 Round-6 deferred-MAJOR ledger (claude B2)
Design §11's round-6 row deferred 21 MAJORs (claude 4 · grok 8 · codex 9) to this plan. The verbatim texts were not preserved (per-round seat outputs overwrite). Disposition — **absorption by construction, with the evidence being the process itself**: rounds 7–20 re-ran the same seats, same role, same dimensions against every subsequent version fourteen times; §12 obligated seats to re-raise anything unresolved, and the round-6 *themes* the tables record (event attribution, credential modes, wire contradictions, approver sets, policy epochs, registry sealing) each received dedicated BLOCKING-level treatment in later rounds (§11 rounds 6–20 tables). No seat re-raised a round-6 MAJOR as open in fourteen opportunities, including three explicit stragglers probes. Residual risk accepted: any round-6 MAJOR that was both unabsorbed and never re-found survives review-invisible — the same risk class §12 accepts for all unknown unknowns. The design's round-6 row is annotated closed-by-this-ledger.

---

## 1. Rules that bind every PR

- **Review**: 5-seat panel before PR (codex seat optional while quota-dead — bake-off policy), recheck `-min-severity medium`, **zero MEDIUM+** (design §1).
- **Risk tiers**: PR0 includes the `.agent/risk-paths.json` update making `src/claude_dispatcher/boundary/**`, `schema/**`, and `tools/{fsmgen,t26_lint}*` **critical** (grok M9: the catch-all would have tiered them medium).
- **Generated types are the sole source** (grok B2): PR0 artifacts define every FSM/§9/panel/error type; PR2+ may add only (a) the §3.1 `ClassifyOutcome` T15 fixture verbatim, (b) `parse_classification` + equation checks, (c) thin adapters. An import-boundary CI test fails on any redefinition of a generated name.
- **Dark mode** (grok M1): `boundary/` is importable from tests only until PR6; the architecture test (skeleton in PR0, allowlist empty) fails on production imports. PR6 is the sole wiring PR and fills the door-entrypoint allowlist (grok M15).
- **Per-PR seal table**: every PR description carries `{T#, test path, revert-falsify command}` rows; the revert-falsification requirement is per-seal, not a preamble (grok M15).
- **Execution protocol per PR (operator directive, 2026-08-03) — scaffold → failing seals → parallel body-fill → immutable tests:**
  1. **Scaffold phase**: every function lands first as a typed signature — request/response shapes from the PR0 generated types — with a contract docstring and a `raise NotImplementedError` body. (Go PRs: stubs returning typed errors.) The scaffold commit is reviewed for CONTRACT fidelity to the design before any body exists.
  2. **Test phase — by a DIFFERENT agent than the scaffold's author**, both citing design sections independently (a shared misreading must not land in stub and test together and self-confirm). The seal tests for every scaffolded function are written against the stubs and committed FAILING (red), mapped to their T-obligations, before any body work begins. A test that passes against a stub is vacuous by definition and rejected. **Composition seals are first-class phase-B work, not an afterthought**: the T19 crash histories, `reduce(events) == state`, and end-to-end fence equality land as red suite-level tests before bodies, and the reducers get property-based tests, not only examples — a build where every function is green and the composition was never sealed is the failure this project's history warns about.
  3. **Body fan-out — MODULE grain, not function grain** (per-function agents lack the cross-function invariant context; modules are the design's own seams). Bodies route to separate agents in parallel, each scoped to its module. **Body agents may not modify any test, scaffold signature, schema, or generated file** — enforced by `scripts/check_body_branch.sh <base> <branch>` (lands with PR0's CI work; fails on a non-empty `git diff -- tests/ schema/ '**/generated/**'` or any changed signature), run at integration and in CI, never trusted on agent self-report. Until that script exists the rule is operator-enforced by running the diff manually — stated so no claim outruns its mechanism (panel round 3 caught exactly this overclaim in v2.2).
  4. **Dispute escalation — covers tests AND signatures**: a body agent that believes a test or a frozen signature is wrong STOPS on that function and files the dispute (artifact, expected-vs-design citation, proposed fix); contorting an implementation to fit a wrong contract is the mirror-image failure and equally forbidden. A SEPARATE reviewer agent adjudicates against the design doc; a genuinely wrong artifact is fixed in its own commit with the design citation, and that fix passes review before body work resumes. **The adjudication is final for the round; a repeat dispute on the same artifact escalates to the operator** — no agent-to-agent ping-pong. The body agent never touches the disputed artifact either way.
  This is the mechanical form of the vacuous-seal rule: the seal's author and the seal's satisfier are never the same agent, and the seal cannot be weakened by the party it constrains.
- **Cross-repo contract**: `schema/` is a versioned contract package; every schema either repo tests against is digest-cross-checked in both CIs with a single source-commit pin; each repo's CI records the peer SHA (grok M3/M10).

## 2. PR sequence

**PR0 — `claude-dispatcher`: generated truth + CI seals (no runtime behavior).**
`schema/lifecycle_fsm.yaml` (A+B tables incl. r20 rows, event alphabet, disposition algebra, durability partition, projection derivation, epoch-fold params, §9 union variants with per-variant requiredness) · `schema/panel_aggregate.yaml` **generating `required_seats`/`blocking`/`aggregate` code, diff-clean** (claude M-panel: a schema nothing checks against is prose lint one level up) · `schema/classifier_protocol.yaml` + golden/malformed vectors · `schema/ast_allowlists.yaml` + **fail-closed T8/T9 CI that fails while allowlisted modules are absent** (grok B3) · `schema/boundary_errors.yaml` (§0.2, generated) · `tools/fsmgen.py` (types, `apply()`, both reducers, T19 skeletons, diagrams, **and the design doc's §6.0/§9 tables — doc == artifact enforced**) · `tools/t26_lint.py` as CI (citations at re-pinned baselines, T-index, retired names, mutation/field-once, supersession markers, **and this plan's §3 T-map completeness**, claude M2) · architecture-test skeleton · risk-paths update · design-header baseline re-pin.

**PR1 — `claude-workflow`: `cmd/classify` wire (Go).** As v1: `-contract-version 1|2`, framed `-authoritative-stdin`, response wrapper with producer-computed digests, v2 envelope (`config_scaffold` required; no `config_sha256`/`classified_at`), capability probe with contractual exits. Seals: T10 goldens + rollback-mid-run + malformed-frame vectors; T30 split by equation; v1 differential vs pinned binary; sidecar-survival fixture. Contract package consumed at pinned SHA.

**PR2 — `claude-dispatcher`: types + parse (pure).** Generated types imported; adds the T15 fixture, `Classification.__post_init__` equations, `parse_classification` (+ bounds, `UNKNOWN_INTENSITY`, `V1_COMPAT` desugar), preimage functions, constructors with the guarded equalities, `MergePlan` ordered construction list, `BoundaryError` exhaustiveness seal. Seals: T1, T4, T5, T7 (stub via PR1 binary), T8/T9 (bodies under the PR0 gate), T11, T15, T16, T22, T30-consumer; construction-list property tests.

**PR3 — `claude-dispatcher`: `boundary/authority_channels.py` — the §8 channel end-to-end** (plan-review consensus B1): GraphQL ref/tree-entry/blob policy fetch with mode checks · two-request compare protocol with octet preimage · frame assembly against the contract vectors · `O_NOFOLLOW`-open → hash-vs-**release-manifest digest** (compare, never adopt) → `fexecve`/`execveat` · wrapper → `parse_classification` integration · mid-run absence ⇒ `CLASSIFY_FAILED(CONFIGURED_BINARY_MISSING)` · policy-epoch escalation halt · hardened-git offline path. Seals: T13, T21 (both halves), T28 executable-provenance, dispatcher-side T10 vector consumption, corrupted-diff ⇒ `SUBJECT_MISMATCH`, "pathname never valid in REQUIRED" deny row. Emitters: classifier metrics (§0.1).

**PR4 — `claude-dispatcher`: carriers, machines, reducers.** Bootstrap ceremony, append protocol, dual-append shared-`event_id`, reduces, epoch walk, `DurableAuthority`/`FenceSnapshot`/`SharedFence`/`SeparatedFence`/`SharedRestartAuthority`, webhook `VERIFIED_API`, effect lock, ceilings, **rollback preflight reduce-and-refuse + unsupported-major golden** (grok M2). Seals: full T19 suite, T23 component rows, T24, T28 predicates. Emitters: lifecycle/hold/epoch signals.

**PR5 — `claude-dispatcher`: doors, consent, events, panel runner.** **`boundary/panel_runner.py` consuming `PanelPlan` only** (grok M11) · doors 0–3 as pure functions over `MergePlan` · `approve-and-merge` consent-at-read/evidence-at-read **with subject recompute over the §8 module only — T20/T27/T31 assert the channel via mock GraphQL, never local git** (grok M5) · §9 event emission + **audit rows that refuse missing `assurance`** (grok M6) · MergeUnit genesis/confirmation. Seals: T2 component half, T3, T12 door-function matrix, T14, T18, T20, T21-consumer, T27, T29, T31.

**PR6 — cut-over (one PR).** Preflight REQUIRED|LEGACY + genesis; route `merge_engine`/`merge_prs`/`auto_integrate` through doors; delete the `_resolved_quality` re-resolution (orchestrator.py:2049), the `cross_family_panel` re-read, the `_has_commits_on_branch` direct-to-base success branch, and both legacy panel call sites; frozen-reviewer advisory labeling; sidecar writes; fill the door-entrypoint architecture allowlist. **Gate:** §0.4 ratifications recorded · rollback drill (REQUIRED→LEGACY on a scratch repo) · **metrics smoke (§0.1)** · **component-version matrix green** — `{dispatcher, classify, gates, iterate} old/new × authority claim ∈ {mirror-only, advisory, REQUIRED-live}` (grok M4) · T12 inventory/forbidden-mover rows · T2 runner-singularity AST assertion + T23 tamper-vs-live-door row (claude M1) · T25 + T26 green · release manifest pins the classify digest; preflight refuses REQUIRED on mismatch (grok M10).

## 3. Test-obligation map (mechanically linted by PR0's `t26_lint.py` against this doc — claude M2)
T1/T4/T5/T7/T8/T9/T11/**T15**/T16/T22 → PR2 · T10/T30 → PR1 (+consumer halves PR2) · **T13/T21/T28-provenance → PR3** · T19/T23-component/T24/T28-predicates → PR4 · T2-component/T3/T12-doors/T14/T18/T20/T27/T29/T31 → PR5 · T2-singularity/T12-inventory/T23-tamper/T25 → PR6 gates · T6 (deny-row plugin)/T26 → PR0, permanent. Multi-PR obligations name each half above.

## 4. Risks
Cross-repo drift (→ §1 contract package + peer pins) · codex quota (optional seat) · SHARED residuals ship as designed, rendered in reporting · line-number citation brittleness: cite symbols not lines where the design does (`_has_commits_on_branch` branch, not orchestrator.py:3231 — grok m4).

## 5. Plan-review disposition table (v1 → v2)

| Finding (seats) | Disposition |
|---|---|
| §8 dispatcher-side channel in no PR — cut-over unbuildable or written inside PR5 (claude B1, grok B1/M5/M12) | PR3 is that channel; T13/T21/T28 live there; consent asserts the module |
| Round-6 deferred MAJORs never dispositioned (claude B2) | §0.5 ledger: absorption-by-construction + accepted residual; design row annotated |
| PR0 types vs PR2 hand types — dual definitions (grok B2) | generated-types-sole-source rule + import-boundary CI |
| T8/T9 allowlists not PR0 CI (grok B3) | `ast_allowlists.yaml` + fail-closed-while-absent CI |
| T-map incomplete (T15 missing, T13/T30 split unstated) (claude M2, grok M12) | map regenerated; lint enforces it against this doc |
| `BoundaryError` not closed over the halt taxonomy; no phase domain/metric map (claude M3, grok M8) | four codes added; phase closed; code→metric generated; PR2 exhaustiveness seal |
| SLO targets without emitters (claude M4, grok M7) | §0.1 emitters table; PR6 metrics smoke |
| `panel_aggregate.yaml` generated nothing (claude M-panel) | fsmgen generates the aggregate, diff-clean |
| Dark-mode/chokepoint unenforced (grok M1, M15) | architecture test skeleton PR0 → filled PR6; per-PR seal tables |
| Rollback preflight unassigned (grok M2) | PR4 + golden |
| Cross-repo pins beyond one file (grok M3, M10) | contract package + peer SHAs + manifest-pinned classify digest in PR6 preflight |
| Component-version matrix missing (grok M4) | PR6 gate |
| Assurance counters/audit refusal unscheduled (grok M6) | §0.1 + PR5 seals |
| Risk-tier claim false for new paths (grok M9) | risk-paths update in PR0 |
| Panel runner not a deliverable (grok M11) | `boundary/panel_runner.py` in PR5; legacy deletions in PR6 |
| T12/T2/T23 halves mis-placed (claude M1, grok M13) | split across PR5/PR6 as named |
| §12's five CI gates: 3/5 in PR0 (grok M14) | all five now in PR0 |
| Baseline re-pin, citation symbols (grok m1/m4) | PR0 first commit; symbol-cited |

---

The plan-level MAJOR-disposition pass is complete: one adversarial review round + this revision. PR0 begins now; each PR re-enters the standard pipeline.
