# Reviewer bake-off

21 seeded-defect cases, 5 controls, 3 families.

A catch is a HIGH or CRITICAL finding naming the file the defect is in.
A false positive is a blocking finding on a case that has no defect.

| family | detection | caught | missed | false-positive rate | FPs | findings | total s |
|---|---|---|---|---|---|---|---|
| claude | 100% | 21 | 0 | 0% | 0 | 82 | 924.1 |
| codex | 100% | 21 | 0 | 20% | 1 | 44 | 608.4 |
| grok | 100% | 21 | 0 | 0% | 0 | 76 | 2129.4 |

## Per case

| case | kind | claude | codex | grok |
|---|---|---|---|---|
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

## Adjudications

Cases where a human overruled the harness score, with the reason.

* **ctl-pure-refactor / codex** — scored `false-positive`, adjudicated **true-positive**. The control's summary claims "no behaviour change". codex showed that is false for sparse arrays: the original `for...of` visits a hole as `undefined` and throws on `r.currency`, while `filter` skips it. Reproduced independently on both runs. Pedantic, and correct — the claim was wrong, not the reviewer, so codex has no adjudicated false positive.

## Notes

* RUN 2 (2026-08-29). Every family was reachable throughout, so no cell is grafted from another account — the previous run lost claude to a Fable 5 quota limit 7 cases in and had to re-run it separately.
* The corpus gained a HARD tier for this run, built specifically to try to separate the families: lexicographic sort on numeric scores, a timing-unsafe secret comparison, an unanchored validation regex, prototype pollution via for...in merge, negative-modulo ring wrapping, a retry that mints a fresh idempotency key per attempt, and an attention-under-noise case hiding an off-by-one guard change inside a whole-file rename.
* hard-needle-in-rename and ctl-large-rename were re-run after the main pass: their wallet.ts declared `loadAccount` without `async` while using `await`, a compile error on both sides. That made the control invalid and corrupted the attention case, because matching on the FILE credited a finding about the bad `await` as catching the seeded guard. The corpus is now tsc-clean, a seal enforces the bug class, and that case carries `markers` so a finding must name the defect and not merely the file.
* Wall-clock spread across 26 cases: codex 608s, claude 924s, grok 2129s (3.5x).
