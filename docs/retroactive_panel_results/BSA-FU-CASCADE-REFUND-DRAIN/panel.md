## Cross-family panel

**Verdict:** BLOCK
**Summary:** consensus=block | claude=APPROVE, gemini=APPROVE, codex=CHANGES_REQUESTED | blocking=1 (0C/1H)

### Per-reviewer verdicts

| Family | Verdict | Findings | Dimensions |
|--------|---------|----------|------------|
| claude | APPROVE | 6 (0 blocking) | Corr=4, Secu=4, Comp=4, Resi=4, Idem=5, Obse=5, Perf=4, Main=4 |
| gemini | APPROVE | 0 (0 blocking) | Corr=5, Secu=5, Comp=5, Resi=5, Idem=5, Obse=5, Perf=5, Main=5 |
| codex | CHANGES_REQUESTED | 3 (1 blocking) | Corr=3, Secu=4, Comp=3, Resi=3, Idem=4, Obse=3, Perf=4, Main=3 |

### Blocking findings

- **HIGH** at `apps/platform-domain/bay-session/store/queries/bet_recovery.sql:248` — `ClaimStuckRefundedBets` excludes every refunded bet where `refund_idempotency_key IS NULL`. That means the new recovery worker will never repair shutdown-stranded refunds for legacy bets, even though the hot path already has a deterministic fallback transaction ID (`fallbackRefundTransactionID(betID)`) for exactly that case. In a financial system, leaving a known class of `bet_state='refunded'` rows permanently outside automated repair means some users can still end up with a refunded bet on disk and no wallet credit until manual operator intervention.
  - *Fix:* Recover legacy refunded bets too. Either include `refund_idempotency_key IS NULL` rows in the claim query and derive the same fallback transaction ID the hot path uses, or explicitly migrate/backfill a stable refund idempotency key for legacy rows before enabling the worker. The worker’s replay path must be able to produce the identical wallet transaction ID for both new and legacy bets.
