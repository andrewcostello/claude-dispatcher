## Cross-family panel

**Verdict:** BLOCK
**Summary:** consensus=block | claude=APPROVE, gemini=REJECT, codex=CHANGES_REQUESTED | blocking=3 (1C/2H)

### Per-reviewer verdicts

| Family | Verdict | Findings | Dimensions |
|--------|---------|----------|------------|
| claude | APPROVE | 5 (0 blocking) | Corr=4, Secu=5, Comp=5, Resi=4, Idem=5, Obse=4, Perf=4, Main=4 |
| gemini | REJECT | 3 (2 blocking) | Corr=2, Secu=5, Comp=5, Resi=2, Idem=5, Obse=4, Perf=2, Main=4 |
| codex | CHANGES_REQUESTED | 1 (1 blocking) | Corr=3, Secu=5, Comp=4, Resi=3, Idem=4, Obse=4, Perf=4, Main=4 |

### Blocking findings

- **CRITICAL** at `apps/platform-domain/bay-session/cmd/publish-recovery/worker.go:133` — The `RunWithReadyHook` loop uses immediate-redrain semantics (`if n < w.cfg.BatchSize { break }`) to rapidly clear backlogs. However, if a row permanently fails to publish (e.g., due to a malformed `SnapshotStation` read or a NATS payload rejection), it is never stamped and remains in the stale set indefinitely. If the number of such poisoned rows reaches `BatchSize` (100), `ListStalePublishStations` will continually return these same failing rows. `drainOnce` will repeatedly return `100, nil` (as individual `resync` errors do not bubble up to abort the drain), causing the loop to immediately re-drain without waiting for the `PollInterval` ticker. This creates a tight, unthrottled infinite loop that will DoS the database, peg the CPU, and completely starve the recovery of any newer stale stations (head-of-line blocking).
  - *Fix:* Remove the immediate-redrain bypass so the loop always honors the `PollInterval` backoff, or implement a bounded retry mechanism (such as updating the row to a terminal DLQ state after N failures) so permanently poisoned rows are evicted from the scan.
- **HIGH** at `apps/platform-domain/bay-session/cmd/publish-recovery/worker.go:152` — Database operations (`ListStalePublishStations`, `SnapshotStation`, and `StampSessionLastPublishedAt`) are executed using the background context, which is only cancelled upon pod shutdown. If a Postgres connection hangs—such as from a network partition without a TCP RST, or severe lock contention—the queries will block indefinitely. This will stall the recovery pipeline forever. Because the liveness probe at `/healthz` does not verify loop progress, Kubernetes will not detect the stall and the pod will not be restarted.
  - *Fix:* Wrap the context passed to database operations with explicit timeouts. For example, use `context.WithTimeout(ctx, w.cfg.PollInterval)` for the batch claim, and apply targeted timeouts for the per-row snapshot and stamp operations.
- **HIGH** at `apps/platform-domain/bay-session/cmd/publish-recovery/config.go:95` — The worker does not enforce the documented/spec floor for `GracePeriod`. The file comments state the grace window must not go below 15 seconds, but `minGracePeriod` is set to 5 seconds and `Validate()` accepts any value from 5s to 14s. That creates a real correctness hazard: with a too-small grace period, the recovery worker can classify an in-flight hot-path publish/stamp as stale and emit a false recovery publish. In this system that means unnecessary duplicate session-state traffic, polluted recovery metrics/alerts, and avoidable pressure on broker/storage exactly during degraded conditions.
  - *Fix:* Make the validation match the stated contract. If 15 seconds is the required floor, set `minGracePeriod = 15 * time.Second` and keep the error text/comments consistent. If 5 seconds is actually intended, then the spec comments and ticket summary need to be corrected everywhere, because the current implementation and documentation disagree on a load-bearing safety bound.
