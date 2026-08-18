# The mutation ledger

One JSON Lines file per subject module, named
`claude_dispatcher.<module>.jsonl` (`mutation_ledger.ledger_path_for`). This
directory holds **no ledger yet** — see *What is owed* below.

## The two kinds of record

A docstring clause is a *citation*. The evidence is a record here, and the
population this ledger must cover has two kinds in it.

**An observation (`LedgerEntry`)** is one measurement of one claim.

* The **claim** is `(seal_file, claiming_row, subject, anchor, operator,
  argument)` — a clause's assertion, restated as something runnable. Its id
  (`ml-…`) digests exactly those fields, so it survives the claim being
  re-measured and a docstring can cite it.
* The **evidence** is the revision, the subject file's digest, the mutant's
  digest, the seal file's population digest, the rows that reddened, whether
  the control run was green, the date, and the observation this one
  `supersedes`. Its id (`mlo-…`) digests all of it.

`supersedes` is inside the observation id deliberately: without it, two
identical re-runs on the same tree on the same day collide, and the second can
neither be added nor supersede the first — the append-only history would be
missing for the one case it exists for. The superseded entry stays in the
file; it is the record of what was believed and when.

**A prediction (`Prediction`)** is a durable *no such measurement is
possible*. A clause naming a whole alternative body ("a body that maps any
abstention onto a pass bucket") has no `MutationOperator` to apply, so it can
never yield an observation. The record carries the clause verbatim, a closed
`NonDerivable` reason, and the revision and subject digest it was judged
against — so a later reader can see it is stale and look again. Its id is
`mlp-…`, and its fate is fixed: `Predicted (unmeasured) under:`.

Predictions are re-examined **in place**, not superseded: there is no evidence
to preserve.

## What the ids prove, and what they do not

Every id is a content digest, re-derived in `__post_init__`, so none can be
typed at a call site. They prove a record is **internally consistent** — its
digests, reddened set and control result are the ones its id names. They are
**not attestations**: anyone who can edit the file can recompute one, and
`new_entry` hashes whatever it is handed. Only `rederive` measures. A record
does not count as coverage because its hashes validate.

## What makes a record stale

Staleness is not a field. It is re-derived, as a `Drift` set folded to one
`Freshness`:

| drift | meaning | folds to |
| --- | --- | --- |
| `subject_absent` / `site_absent` / `row_absent` | the file, the anchor, or the claiming row is gone from the tree that was run | `*_gone` — no comparison is possible |
| `revision_absent` | the observation's own revision is not in this repository (rebased away, collected) | `provenance_gone` |
| `subject_bytes` | the body changed | `subject_moved` |
| `population` | the seal file's collected row set changed — the file grew | `population_moved` |

`revision_absent` is deliberately **not** grouped with the absences. It blocks
the audit of a record's provenance, not the comparison itself: at
`at_target` the run at the target tree is a perfectly good one, so such a
claim is still refutable and is owed a *fresh observation*, not a permanent
wait.

## How a claim is re-derived rather than re-read

`rederive` provisions the tree (`git worktree add --detach`, then
`scratch_clone.make_scratch_clone`, which severs and re-inits the copy), runs
the seal file **twice** — once clean, once with the mutation swapped in — and
compares. Nothing reads the docstring, and the subject module is on
`FLOOR_GLOBS`, so the mutation only ever exists inside the quarantined clone.

The reddened set is the **`PASSED` → `FAILED` transition set**, not "rows
failing under the mutant": crediting the mutation with the file's baseline
failures is how a broken fixture becomes a blast radius. A claiming row that
`ERRORED` in either run is a harness fault, never a failure — the assertion
the claim is about was never reached.

Two modes ask different questions: `at_target` (the default) asks "is this
still true HERE" and is the only mode in which byte and population drift are
expressible; `at_recorded` asks "was it ever true at the revision it names".

## When re-derivation disagrees with the record

It is a named `Status`, always — never a silently kept entry:

| status | when | proposed fate |
| --- | --- | --- |
| `held` | anchored, reddened exactly as recorded | cite the claim id |
| `reanchored` | reddened as recorded, under moved bytes, moved population, or gone provenance | re-observe, then cite |
| `scope_broken` | reddened, wrong set | amend the scope sentence |
| `broken` | anchored and survived — never true | strike |
| `expired` | survived under moved bytes, moved population or gone provenance | strike |
| `underivable` | no refuting comparison was possible: the control was already red, or the tree has no such subject, anchor or row | relabel `Predicted (unmeasured) under:` |
| `faulted` | the run broke, or the record contradicts itself | re-run |

Only `held` counts as coverage. `reanchored` is *true* and still not coverage
until a new observation is written — "still true under different bytes"
reported as verified is how 41 unlabelled clauses accumulated.

**`faulted` is the only fate that waits, and its causes are all retryable** —
a refused clone, an exceeded budget, an unusable pytest, or a record claiming
both that a row was absent and that it reddened. A deleted row, a deleted
subject and an unresolvable anchor are `underivable` instead, and get
relabelled. That precedence is the point: routed the other way, a clause whose
row no longer exists waits on a re-run that can never restore it, and is left
exactly as it was under a different name.

## The 41 clauses in `tests/test_call_site_reachability.py`

**None are migrated.** A clause copied into a ledger is a transcription, not a
measurement. Each is re-derived (→ an observation) or judged unmeasurable (→ a
prediction), and its text is then handled in place: `held` → cite the claim id;
`underivable` or a prediction → relabel `Predicted (unmeasured) under:`;
refuted → struck, safely, because the record outlives the clause.

**Who edits.** W2-3-2 (SEALS) does the relabelling, under W2-3-4's ruling.
W2-3-3 (BODIES) only *reads* that file and reports each disagreement: it
matches BODIES' deny globs, and deleting a forbidden file scores as touching
it.

## Where the ledger may live

`refuse_unwritable_ledger_path` is a hard constraint, not a convention. The
path must be a file directly under `docs/mutation-ledger/` ending `.jsonl`,
off `FLOOR_GLOBS`, and permitted by the BODIES rule *as
`role_protocol.evaluate_changed_paths` evaluates it* — that evaluator rather
than a glob scan, because it is total over `RuleKind` and it applies
`SEAL_VERIFY_TEST_PATHS`, which carries no wildcard and which a glob match
misses. W2-3-3 builds the ledger under BODIES; a path that role cannot create
ships a task that cannot be completed without a protocol breach.

## What is owed, and by whom

Nothing in `mutation_ledger.py` runs today. It is a contract, and this is the
whole of what exists and what does not.

**Implemented (W2-3-1, this scaffold)** — the surfaces whose failure is
*silent*: the enums; `MutationSite`, `LedgerEntry`, `Rederivation` and
`Prediction` with their validation; `claim_id`, `observation_id`,
`prediction_id`, `new_entry`, `new_prediction`; `ledger_path_for` and
`refuse_unwritable_ledger_path`; `fold_row_results`, `population_digest`,
`source_digest`; `canonical_line`, `parse_line`; `observations`,
`predictions`, `current_observations`, `validate_ledger`,
`counts_as_coverage`.

**Owed by W2-3-3 (bodies), sealed first by W2-3-2 (seals):**

* the four folds — `freshness_of`, `classify_observation`, `fold`,
  `proposed_fate`. These are the decision W2-3-2's rows must be able to
  redden, which is why this scaffold specifies them and does not write them.
* the harness — `apply_mutation`, `provision_subject_tree`, `collect_rows`,
  `run_rows`, `rederive`, `load_ledger`, `write_ledger`, `check_citations`.
* the CLI — `main`. There is **no `rederive`, `fates` or `citations` command**
  today, and the module is deliberately not wired to `__main__`: a command
  that half-runs is worse than one that is absent.

`Rederivation.freshness` and `.status` are derived properties, not stored
fields, so no run can emit a triple that disagrees with itself — and no
`Rederivation` can answer either question until `freshness_of` and `fold` are
filled. That is the intended order.
