## Cross-family panel

**Verdict:** BLOCK
**Summary:** consensus=block | claude=APPROVE, gemini=CHANGES_REQUESTED, codex=CHANGES_REQUESTED | blocking=3 (0C/3H)

### Per-reviewer verdicts

| Family | Verdict | Findings | Dimensions |
|--------|---------|----------|------------|
| claude | APPROVE | 4 (0 blocking) | Corr=4, Secu=5, Comp=5, Resi=4, Idem=4, Obse=4, Perf=5, Main=4 |
| gemini | CHANGES_REQUESTED | 2 (2 blocking) | Corr=3, Secu=5, Comp=5, Resi=3, Idem=4, Obse=4, Perf=4, Main=4 |
| codex | CHANGES_REQUESTED | 2 (1 blocking) | Corr=3, Secu=4, Comp=4, Resi=3, Idem=4, Obse=4, Perf=4, Main=3 |

### Blocking findings

- **HIGH** at `apps/platform-domain/bay-session/cmd/bay-session/config.go:552` — `validateCoreFields` skips the validation check `c.GoroutineDrainTimeout >= c.ShutdownTimeout` when `c.GoroutineDrainTimeout == 0` (to support ergonomic test fixtures). However, in `buildDeps`'s `cleanup()`, a zero value is replaced with `defaultGoroutineDrainTimeout` (25s) before being used. If `Config{}` is instantiated directly with a zero `GoroutineDrainTimeout` and a short `ShutdownTimeout` (e.g., 10s), the fallback causes the drain budget to silently exceed the overall shutdown timeout. This causes a timeout inversion where the orchestrator forcefully kills the process before the graceful drain can complete.
  - *Fix:* Resolve the default fallback value *before* asserting the timeout invariant in `validateCoreFields`. For example: `effDrain := c.GoroutineDrainTimeout; if effDrain <= 0 { effDrain = defaultGoroutineDrainTimeout }; if effDrain >= c.ShutdownTimeout { return fmt.Errorf(...) }`.
- **HIGH** at `apps/platform-domain/bay-session/cmd/bay-session/shutdown_drain.go:175` — `recoverBootGoroutine` catches and swallows panics from boot workers, allowing the goroutine to exit cleanly. The comment claims this prevents a drain deadlock, but standard `defer` statements (like `wg.Done()`) execute during panic unwinding regardless, so the `WaitGroup` would not leak. By swallowing the panic without signaling the application to shut down, the pod becomes a "zombie" — it continues to pass HTTP liveness probes indefinitely while critical background loops (like `frs_idle_sweeper`) are permanently dead.
  - *Fix:* Do not silently swallow panics. Either re-panic at the end of `recoverBootGoroutine` (e.g., `panic(r)`) to crash the process, or trigger a graceful process shutdown by invoking a global context cancellation when a critical boot worker crashes.
- **HIGH** at `apps/platform-domain/bay-session/cmd/bay-session/shutdown_drain.go:117` — `launchBootGoroutine` now wraps every boot worker in `recoverBootGoroutine`, and `recoverBootGoroutine` swallows the panic after logging it. In Go, an unhandled panic in any goroutine normally crashes the process; this change silently converts fatal worker crashes into permanent background-feature loss. If `runFrsIdleSweeper`, `runWelcomeEmailConsumer`, or the stream-stats scraper panic once, the pod stays up but that worker is dead forever until an external restart. In this system that can mean idle-session cleanup stops, welcome-email messages stop draining, or observability quietly degrades without the self-healing restart behavior the service previously had.
  - *Fix:* Do not swallow boot-worker panics just to preserve `WaitGroup` bookkeeping. Either remove the recovery entirely, or recover only long enough to emit the log and then terminate the process explicitly so the orchestrator restarts the pod. If you need both clean `wg.Done()` behavior and crash semantics, recover in the wrapper, log, call `wg.Done()`/`registry.done()`, then re-panic or `os.Exit(1)` from a fatal path.
