# Reviewer bake-off

27 seeded-defect cases, 6 controls, 3 families.

A catch is a HIGH or CRITICAL finding naming the file the defect is in.
A false positive is a blocking finding on a case that has no defect.

| family | detection | caught | missed | false-positive rate | FPs | findings | total s |
|---|---|---|---|---|---|---|---|
| claude | 100% | 27 | 0 | 0% | 0 | 103 | 1165.0 |
| codex | 96% | 26 | 1 | 17% | 1 | 52 | 763.4 |
| grok | 100% | 27 | 0 | 0% | 0 | 97 | 2838.2 |

## Per case

| case | kind | claude | codex | grok |
|---|---|---|---|---|
| ctl-consistent-multifile-rename | CONTROL | clean | clean | clean |
| ctl-correct-feature | CONTROL | clean | clean | clean |
| ctl-docs-only | CONTROL | clean | clean | clean |
| ctl-equivalent-rewrite | CONTROL | clean | clean | clean |
| ctl-large-rename | CONTROL | clean | clean | clean |
| ctl-pure-refactor | CONTROL | clean | false-positive | clean |
| hard-lexicographic-sort | sort-order | caught | caught | caught |
| hard-needle-in-rename | attention-under-noise | caught | caught | caught |
| hard-negative-modulo | off-by-one | caught | caught | caught |
| hard-prototype-pollution | prototype-pollution | caught | caught | caught |
| hard-retry-double-charge | idempotency | caught | caught | caught |
| hard-timing-unsafe | timing-attack | caught | caught | caught |
| hard-unanchored-regex | input-validation | caught | caught | caught |
| ts-auth-bypass | authorization | caught | caught | caught |
| ts-cache-before-commit | cache-coherence | caught | caught | caught |
| ts-connection-leak | resource-leak | caught | caught | caught |
| ts-float-money | float-money | caught | caught | caught |
| ts-idempotency | idempotency | caught | caught | caught |
| ts-local-time-bucket | timezone | caught | caught | caught |
| ts-missing-await | async-ordering | caught | caught | caught |
| ts-off-by-one | off-by-one | caught | caught | caught |
| ts-redos | redos | caught | caught | caught |
| ts-sql-injection | injection | caught | caught | caught |
| ts-swallowed-write | silent-failure | caught | caught | caught |
| ts-toctou-debit | race-condition | caught | caught | caught |
| ts-unbounded-fanout | resource-exhaustion | caught | caught | caught |
| ts-value-loss | money-conservation | caught | caught | caught |
| xf-dropped-dedupe-key | cross-file-idempotency | caught | caught | caught |
| xf-epoch-units | cross-file-units | caught | caught | caught |
| xf-lock-ordering | cross-file-deadlock | caught | caught | caught |
| xf-migration-drift | cross-file-schema | caught | missed | caught |
| xf-unit-boundary | cross-file-units | caught | caught | caught |
| xf-widened-union | cross-file-exhaustiveness | caught | caught | caught |

## Adjudications

Cases where a human overruled the harness score, with the reason.

* **ctl-pure-refactor / codex** — scored `false-positive`, adjudicated **true-positive**. The control's summary claims "no behaviour change". codex showed that is false for sparse arrays: the original `for...of` visits a hole as `undefined` and throws on `r.currency`, while `filter` skips it. Reached independently on both runs. Pedantic, and correct — so codex has no adjudicated false positive.

## Notes

* THREE TIERS, built in escalating difficulty because each previous one failed to separate the families. (1) plain defects — value loss, auth bypass, TOCTOU, injection, swallowed write, off-by-one, idempotency, connection leak. (2) subtle — ReDoS, cache-invalidated-before-commit, local-time week bucketing, float money, missing await, unbounded fan-out, lexicographic sort, timing-unsafe compare, unanchored regex, prototype pollution, negative modulo, retry minting a fresh idempotency key, and an off-by-one guard hidden inside a whole-file rename. (3) CROSS-FILE, where every hunk is individually plausible and only the interaction is wrong: a units boundary, opposite lock orders, a widened union whose `default` arm hides the missing case from the compiler, a second-vs-millisecond epoch, a column rename with one query missed, and a producer dropping the field its consumer dedupes on.
* THE ONE DISCRIMINATING CASE. `xf-migration-drift` renames a column and updates one of the two queries in the same file. claude and grok raise it as blocking; codex does not, in 4 of 4 repetitions, each time producing the same substitute finding about missing migration tests. Consensus needs TWO families to block, so a 2-seat panel of {claude, codex} APPROVES the change and a {claude, grok} panel blocks it. That is why the seat trim keeps claude and grok. Raw repetitions in migration-drift-reps.json.
* Still no separation: cases missed by at least one family: xf-migration-drift.
* Both scored false positives across all runs were adjudicated TRUE positives — the corpus author's claim was wrong, not the reviewer's finding. See Adjudications.
* Wall-clock across 33 cases: codex 763s, claude 1165s, grok 2838s (3.7x). It remains the only axis that discriminates, and it is what the seat-trim order is based on.
