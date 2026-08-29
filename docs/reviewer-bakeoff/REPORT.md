# Reviewer bake-off

14 seeded-defect cases, 4 controls, 3 families.

A catch is a HIGH or CRITICAL finding naming the file the defect is in.
A false positive is a blocking finding on a case that has no defect.

| family | detection | caught | missed | false-positive rate | FPs | findings | total s |
|---|---|---|---|---|---|---|---|
| claude | 100% | 14 | 0 | 0% | 0 | 73 | 958.8 |
| codex | 100% | 14 | 0 | 25% | 1 | 31 | 406.6 |
| grok | 100% | 14 | 0 | 0% | 0 | 52 | 1427.4 |

## Per case

| case | kind | claude | codex | grok |
|---|---|---|---|---|
| ctl-correct-feature | CONTROL | clean | clean | clean |
| ctl-docs-only | CONTROL | clean | clean | clean |
| ctl-equivalent-rewrite | CONTROL | clean | clean | clean |
| ctl-pure-refactor | CONTROL | clean | false-positive | clean |
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

* **ctl-pure-refactor / codex** — scored `false-positive`, adjudicated **true-positive**. The control's summary claimed "no behaviour change". codex showed that is false for sparse arrays: `for...of` visits a hole as `undefined` and throws on `r.currency`, while `filter` skips it. Pedantic, and correct — the claim was wrong, not the reviewer. Counted as codex's only false positive in the table above; on adjudication it has none.

## Notes

* claude's seat runs Fable 5 and exhausted that model's quota 7 cases in, returning UNAVAILABLE in ~4.5s for the remaining 11. Those cells were re-run on a pool account via CLAUDE_CONFIG_DIR and grafted in; `claude-rerun.json` holds the raw re-run. That is a quota fact about the run, not a review fact about the family.
* An earlier pass scored a SECOND codex false positive, on ctl-correct-feature. That was a harness defect: every control was handed the summary "a refactor with no behaviour change", which was false of the case that adds a function. All three families flagged the mismatch and only codex rated it HIGH, so the harness scored the strictest reviewer for the author's error. Each case now carries its own summary.
* No case discriminated between the families: all three caught all 14 seeded defects, including the subtle tier (ReDoS, cache-invalidation-before-commit, local-time week bucketing, float money, missing await, unbounded fan-out). This corpus establishes a FLOOR — no seated family is blind to a planted defect — and cannot rank them. Ranking needs defects that at least one family misses.
* Wall-clock is the one axis that separated them, by 3.5x across 18 cases: codex 407s, claude 959s, grok 1427s.
