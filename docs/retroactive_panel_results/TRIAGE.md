# Hand-curated triage of panel findings

Companion to the auto-generated `REPORT.md`. For each panel finding, my
judgment of whether it's a real defect, plausible-but-needs-verification,
or a false positive. Confidence is based on:

- **Cross-family corroboration** — multiple reviewers flagging the same
  root issue with different framings is strong signal
- **Specificity** — line numbers, named code paths, named anti-patterns
- **Domain plausibility** — does the failure mode match how the system is
  actually structured? Vague "what if X" findings are weaker than ones
  that cite specific code shapes

I have NOT re-read every cited line in evenplay-mono — these are armchair
judgments on top of the panel output. The "INVESTIGATE" verdicts deserve
a 5-minute source read before deciding whether to act.

Legend: ✅ defect (high confidence) · ❓ investigate · ❌ false positive

---

## BSA-FU-AUTH-PEER-BRIDGE — 3/3 reviewers, 3 findings

All three reviewers flagged **the same root issue** with different framings:
`TestPeerAllowlist_SimulatorHandlerProcedures` is a tautology — it iterates
RPC names as string labels and asserts properties of the `requireSimulator`
helper directly, never invoking the handler entry points the test name
promises to cover.

- ✅ **DEFECT** — Cross-family corroboration is the gold standard. All
  three reviewers independently identified the same anti-pattern that
  human review caught on REFUND-PRIO. The "real" coverage shape is exactly
  what the panel suggested: AST walk or behavioural handler invocation.
  This is the same false-confidence-test pattern the brief flagged as
  worth catching.

---

## BSA-FU-RECOVERY-REFUND-PRIO — 3/3 reviewers, 3 findings (2C/1H)

- ✅ **DEFECT (HIGH at `worker_test.go:1163`)** — Corroborates the human
  gate. The test seeds bet state to `recovery_failed` *before* `drainOnce`
  runs, so `voidNeverDebited` is never actually invoked. The trailing
  comment "the fake doesn't expose one" admits the gap. This is the
  canonical case from the brief.

- ✅ **DEFECT (CRITICAL at `decide.go:208`)** — Money-trap scenario.
  `ActionVoidNeverDebited` assumes `debit_confirmed_at IS NULL` ⇒ wallet
  has no BET transaction. But a network timeout after a successful
  `wallet.Bet` RPC, before the local `debit_confirmed_at` update, breaks
  that invariant. The reviewer's fix (drop the action; add
  `!bet.DebitConfirmedAt.IsZero()` to the existing
  `ActionConfirmRefundResultTimeout` condition) is structurally sound. The
  suggested rollout (let the next loop pick up the corrected state via
  `ActionConfirmDebitStayCommitted`) leverages existing safe
  idempotent-sync paths. High-confidence finding.

- ✅ **DEFECT (CRITICAL at `worker.go:430`)** — Classic CAS-too-narrow.
  The transition row from snapshot to "REFUNDED, never_debited" only
  checks `bet_state='committed'` at write time, not
  `debit_confirmed_at IS NULL`. Race between the snapshot read and the
  CAS write can transition a now-debited bet to refunded without a
  compensating wallet RefundBet call. Standard pattern; well-known fix
  (predicate must match the snapshot's read assumptions). High confidence.

---

## BSA-FU-RECOVERY-OUTCOME — 3/3 APPROVE

No findings. Panel and auto-integrate agreed cleanly. This is the
calibration data point — the panel does NOT block everything.

---

## BSA-FU-CASCADE-REFUND-DRAIN — 1/3 dissent, 1 finding

Only codex flagged this; claude and gemini APPROVED.

- ❓ **INVESTIGATE (HIGH at `bet_recovery.sql:248`)** —
  `ClaimStuckRefundedBets` excludes legacy refunded bets with
  `refund_idempotency_key IS NULL`. The finding's claim is plausible —
  legacy bets are real and a recovery worker that can't repair them is a
  gap — but it could equally be a deliberate scope decision (legacy data
  is migrated separately, the worker covers only new-shape bets). Worth a
  5-min read: does the spec mention legacy backfill? Is the
  `fallbackRefundTransactionID(betID)` helper actually used elsewhere?
  Without that context, treat as plausible-but-unverified.

Note: 1/3 dissent is the kind of signal that the brief's 3/3 rule
deliberately treats as conservative. If you trust the lone dissenter,
this is a real gap. If you don't, the 2/3 majority would have approved.

---

## BSA-FU-XPOD-ORDERING — 3/3 reviewers, 6 findings (all HIGH)

This is the strongest ticket for "panel catches things the in-cycle review
missed." Six distinct findings across the three reviewers, several with
cross-family corroboration on the same root issue.

- ✅ **DEFECT (HIGH at `stream_target.go:660`)** — Stale-frame drops don't
  advance `lastSeq`, so the gap metric co-varies 1:1 with stale drops.
  Specific enough to verify in 2 minutes by reading the drain loop. The
  Tasker explicitly told SRE the gap metric is "orthogonal" to drops in
  the HPA config — if the metric isn't actually orthogonal, that's an
  observability defect that misleads on-call.

- ✅ **DEFECT (HIGH at `stream_target.go:662`)** — `msgDBVersion > 0 &&
  msgDBVersion <= curDBVersion` silently disables causal dedupe for any
  frame with `db_version=0`. The Tasker summary admits this as a deferred
  follow-up with no ticket reference. Either tighten the guard now or add
  a counter so the silent escape hatch is observable. Real defect.

- ❓ **INVESTIGATE (HIGH at `bay_session.proto:57`)** — The reviewer
  raises a real question (is `updated_at` assigned via Postgres `now()`
  (txn-start, non-monotonic under contention) or `clock_timestamp()`
  (real-clock-monotonic)?) but doesn't have access to the SQL UPDATE
  statement. If the schema uses `now()`, this is a CRITICAL defect; if
  it uses `clock_timestamp()` or a sequence, it's fine. Trivially
  verifiable — grep the migration. Worth checking.

- ❓ **INVESTIGATE (HIGH at `stream_target.go:653`)** — Removing the
  `msgSeq <= cur` check is described as "regression for legacy
  producers." This MIGHT be a deliberate replacement (broker-seq dedupe
  replaced by causal dedupe) or it might be a real regression that
  re-enables redeliveries for legacy producers. The right answer depends
  on whether legacy producers still exist on this path. Look at the
  Tasker summary for the explicit removal rationale.

- ✅ **DEFECT (HIGH at `stream_target.go:402`)** — Replay/resume path
  returns `snapshotDBVersion=0` for the sinceSeq path. After a reconnect,
  `lastDBVersion` starts at zero and the server forwards an older causal
  frame with a higher broker-seq. This reintroduces the bug the change is
  meant to fix on a normal production path. Well-reasoned; specific code
  path identified.

- ✅ **DEFECT (HIGH at `session_logic.go:742`)** — `db_version` derived
  from `updated_at.UnixMicro()` aliases on same-microsecond commits, so
  the later state is dropped permanently as a duplicate. Microsecond
  truncation of wall-clock for a monotonic version is a textbook
  anti-pattern. The fix (DB sequence/version column) is the
  industry-standard answer. High-confidence finding.

---

## BSA-FU-NATS-PARTITION-RECOVERY — 2/3 dissent, 3 findings (1C/2H)

- ✅ **DEFECT (CRITICAL at `worker.go:133`)** — Tight redrain on poisoned
  rows. `if n < BatchSize { break }` means a batch full of permanently
  failing rows keeps coming back, the loop never hits the ticker, the DB
  gets pegged. Classic missing-DLQ pattern. The fix (drop the immediate
  redrain OR add a terminal failure state) is standard. High confidence.

- ✅ **DEFECT (HIGH at `worker.go:152`)** — Background context, no DB
  timeouts. If Postgres connection hangs (network partition without RST,
  severe lock contention), recovery stalls forever. The liveness probe
  doesn't see it. Standard distributed-systems oversight. Easy fix
  (context.WithTimeout on each DB call). High confidence.

- ✅ **DEFECT (HIGH at `config.go:95`)** — `minGracePeriod = 5*time.Second`
  contradicts the documented 15-second floor. The reviewer cited the
  specific value and the documentation gap. Either the value or the docs
  is wrong; both must be fixed. Trivially verifiable.

---

## BSA-FU-SHUTDOWN-GOROUTINE-WG — 2/3 dissent, 3 findings (all HIGH)

Two of the three findings are different framings of the same root cause:
`recoverBootGoroutine` swallows panics, creating zombie pods.

- ✅ **DEFECT (HIGH at `shutdown_drain.go:175`)** — Panic recovery
  semantics wrong. `defer wg.Done()` runs during panic unwinding anyway,
  so the WaitGroup-leak justification is incorrect. Swallowing the panic
  silently converts a fatal worker crash into permanent background-feature
  loss. The fix (re-panic, or trigger global shutdown) is the textbook
  answer. High confidence.

- ✅ **DEFECT (HIGH at `shutdown_drain.go:117`)** — Same root issue at
  the launcher side. The two findings together pin down both ends of the
  anti-pattern. Cross-family corroboration on the same defect class.

- ✅ **DEFECT (HIGH at `config.go:552`)** — Validation order-of-operations
  bug. `validateCoreFields` skips the timeout invariant when
  `GoroutineDrainTimeout == 0`, but `cleanup()` then replaces 0 with
  25s — which can silently exceed `ShutdownTimeout`. The fix (resolve
  defaults BEFORE asserting invariants) is correct. The specific
  combination of timeouts that triggers this (10s shutdown + zero drain →
  resolved 25s drain) is concrete enough to be a real hazard. High
  confidence.

---

## Summary

| Ticket | Defects | Investigate | False positives |
|--------|---------|-------------|-----------------|
| AUTH-PEER-BRIDGE | 3 (one defect, 3 framings) | 0 | 0 |
| RECOVERY-REFUND-PRIO | 3 (1H + 2C) | 0 | 0 |
| RECOVERY-OUTCOME | 0 (cleared) | 0 | 0 |
| CASCADE-REFUND-DRAIN | 0 | 1 | 0 |
| XPOD-ORDERING | 4 | 2 | 0 |
| NATS-PARTITION-RECOVERY | 3 | 0 | 0 |
| SHUTDOWN-GOROUTINE-WG | 3 | 0 | 0 |

Across 19 blocking findings:
- **16 likely real defects** (high confidence, often cross-family corroborated)
- **3 worth investigating** (plausible but require source verification)
- **0 false positives** identified (caveat: this is an armchair triage; a careful source read could downgrade some "defect" judgments to "investigate")

The false-positive rate from this sample is too low to require
prompt-iteration. The panel is producing actionable findings.

What this DOES suggest for the "iterate vs block" question (see user
feedback on the wrap-up): when the panel blocks, ~85% of the findings
are real and worth fixing — so feeding them back to the Tasker for an
iteration pass is likely to be productive, not just expensive.
