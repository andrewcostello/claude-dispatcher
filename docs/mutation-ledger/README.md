# The mutation ledger

One JSON Lines file per subject module, named
`claude_dispatcher.<module>.jsonl` (`mutation_ledger.ledger_path_for`).
`claude_dispatcher.call_site_reachability.jsonl` is the first ledger, built
by W2-3-3 on 2026-08-28 — see *What the ledger holds so far* below for its
five records and the handover to W2-3-5.

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
`ERRORED` is never read as a failure — the assertion the claim is about was
never reached — but which side it errored on decides the disposition:

* in the **control**, the tree cannot run the row even unmutated. That is a
  `harness_fault`: fix the run and re-derive.
* under the **mutant**, the mutation broke the row's setup or collection.
  That is `mutant_unevaluable`, and it is a deterministic property of
  (site, operator, tree) — it reproduces on every re-run, so it must not be
  routed to a state that waits. It folds to `underivable`.

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
| `underivable` | no refuting comparison was possible: the control was already red, the tree has no such subject, anchor or row, or the row cannot be evaluated under the mutation | relabel `Predicted (unmeasured) under:` |
| `faulted` | the run broke, or the record contradicts itself | repair the run, then re-derive |

Only `held` counts as coverage. `reanchored` is *true* and still not coverage
until a new observation is written — "still true under different bytes"
reported as verified is how 41 unlabelled clauses accumulated.

**`faulted` is the only fate that waits, and every one of its causes is a
fault in the RUN** — a refused clone, an exceeded budget, an unusable pytest,
one run that reported nothing while the other reported rows, a control that
cannot execute the claiming row, or a record claiming both that a row was
absent and that it reddened. A clause therefore waits only while the
repository itself cannot run it, which is loud and visible.

Nothing that is a fact about the *clause*, the *mutation* or the tree's
*content* may reach it. A deleted row, a deleted subject, an unresolvable
anchor and a mutation the row cannot be evaluated under are `underivable`
instead, and get relabelled. That precedence is the point: routed the other
way, a clause whose row no longer exists — or whose mutation deterministically
errors — waits on a re-run that can never change the answer, and is left
exactly as it was under a different name.

## Can this ledger hold all 41 clauses? Yes, and none are struck by it

The question this contract has to answer before anything is sealed against
it. The clause spelling is `Reddens under a body on: …` — a *body*, not an
edit — so most of the population names a whole alternative implementation
that no `MutationOperator` reaches and no `rederive` call can ever run; the
round-3 panel put it at 29 of the 41. If a ledger row required a re-runnable
`MutationSite`, those would be unrecordable and the only honest option left
would be to strike them.

They are **recorded, not struck**. `Prediction` is a ledger row with no
`MutationSite` and no re-run: it carries the clause verbatim, a closed
`NonDerivable` reason, and the revision and subject digest it was judged
against. A recorded non-derivable claim is a legitimate ledger row — it is
the original point of writing a ledger rather than a test. `rederive` takes a
`LedgerEntry` and predictions are not fed to it; their fate is fixed
(`PREDICTION_FATE`) rather than folded, because there is no `Status` to fold.

Nor is the choice per-ROW. A row may carry live observations *and*
predictions: the seal file writes clauses as semicolon lists, and a single
test function routinely names one alternative-body sentence (a prediction)
beside one edit-to-existing-bytes sentence (an observation). Measured on this
branch on 2026-08-18: **41 clause headers, 72 sentences, and 21 headers
carrying more than one** — so a rule that let a row hold only one kind would
be wrong for at least half of the population. `validate_ledger`
refuses only a duplicate id or two live observations of one claim. Per-clause
exclusivity — refusing an observation and a prediction *of the same sentence*
— needs a clause key the two kinds do not yet share, and is recorded as owed
below rather than approximated by a row-level rule that would refuse true
records.

## What it costs to run

A ledger nobody runs is the docstring again with a different extension, so
the cost is part of the contract:

* one run of `tests/test_call_site_reachability.py` (110 rows): **0.80 s**,
  measured on this branch on 2026-08-18.
* one re-derivation is **two** such runs plus one `git worktree add --detach`
  and one scratch clone — the dominant term for a seal file this size is the
  provisioning, not the pytest.
* `PER_ENTRY_BUDGET_SECONDS` is **60 s**, ~33× the two-run figure. An entry
  that exceeds it folds to `faulted` and is reported. It is never skipped: a
  skip that reads as coverage is the defect this unit exists to close.
* the cost scales per *claim*, not per clause-word, and claims sharing one
  seal file share nothing — each re-derivation provisions its own tree.
  Whether W2-3-3 batches them is a body decision this contract does not fix,
  but a batching that reuses a control run across mutations must still record
  one control result per observation.

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

It reads the STATIC table rule, since `effective_rule` needs a `TaskRoleSpec`
and this check has no task in hand. That difference runs one way only — a
row's `added_immutable_globs` can only add denials to a `DENY_GLOBS` rule — so
passing here is necessary, not sufficient, and the branch gate remains the
thing that judges a diff.

## What is implemented, and how to run it

Everything in `mutation_ledger.py` runs. W2-3-1 wrote the contract and the
silent-failure surfaces (ids, records, path rule, wire); W2-3-2 sealed the
rest; W2-3-3 filled it on 2026-08-28 against those seals — all 23 rows of
`tests/test_mutation_ledger.py` are green, and the module measures 0.5:1
prose-to-code (`scaffold_shape measure`).

```
python -m claude_dispatcher.mutation_ledger rederive  --subject SRC [--mode at_target|at_recorded] [--target REV] [--record] [--claim 'SEAL::ROW' ANCHOR OPERATOR [ARGUMENT]]... [CLAIM_ID...]
python -m claude_dispatcher.mutation_ledger predict   --subject SRC --row 'SEAL::ROW' --described 'verbatim sentence' --reason REASON [--note ...]
python -m claude_dispatcher.mutation_ledger fates     --subject SRC [--mode ...] [--target REV]
python -m claude_dispatcher.mutation_ledger citations [--repo ROOT]
```

* **`rederive`** re-runs every live observation in the ledger and prints one
  line per claim: status, freshness, observation, the revision run, the drift
  set, the size of the observed transition set and the `+unexpected`/
  `-missing` counts. Exit 0 only when every status counts as coverage.
  `--record` is the **admission path**: a completed comparison is written back
  as a new observation superseding the old one, and each `--claim` not yet in
  the ledger is measured at the target and recorded with the digests of the
  tree that was run and the transition set that was observed — never a typed
  one (`observe_claim`). A comparison that did not complete records nothing
  and says why.
* **`predict`** records a clause no operator can measure: the sentence
  verbatim, a closed reason, and the subject's digest at the judged
  revision. Re-examining the same sentence replaces the record in place.
* **`fates`** is `rederive` plus `proposed_fate`, and `PREDICTION_FATE` for
  each prediction — the input W2-3-4 rules on.
* **`citations`** greps the tree (not the ledger directory) for `ml-`/`mlo-`/
  `mlp-` ids and exits non-zero on one that resolves to no live record, or on
  an `mlo-` observation id cited where a claim id belongs.

How a run is made, and what it costs here: `provision_subject_tree` adds a
detached worktree in a sibling staging path, removes the out-of-tree
`.claude/workflow` symlink, scratch-clones it, and removes the staging
worktree on every path (the repository under measurement is left as found —
`git status` clean, HEAD unmoved). Each nested pytest runs under an
environment scrubbed by prefix (`PYTEST_*`, `COVERAGE_*`, `PYTHON*`,
`GIT_*`, `TOX_*`, `NOSE_*`) with `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` and only
the collection plugin named with `-p`, in its own process group, killed
whole on timeout. One claim against `tests/test_call_site_reachability.py`
costs **2.0 s** measured on this branch (provision + control + mutant).

Choices the contract left to the body, stated so a later reader does not
infer omission:

* `revision_run` is the null sha `000…0` when NOTHING was provisioned (a
  recorded revision absent under `at_recorded`). The seal refuses only the
  echo of the absent revision; W2-3-4 may rule a different spelling.
* A mutant run refused after a completed control (the mutation broke
  import or collection) classifies as `mutant_unevaluable`, not as a harness
  fault: the same tree just ran the control.
* `apply_mutation` refuses a mutant that does not compile (a `continue`
  outside a loop) and validates `return_constant`/`add_default_branch`
  arguments as Python literals, closing the contract's "argument not
  validated by operator" gap at the applier. `add_default_branch` extends
  exactly one else-less if/elif chain, a direct statement of the anchor,
  whose every arm returns; anything else is refused.
* `write_ledger` writes a sibling temp file and `os.replace`s it, so a crash
  mid-write leaves the previous ledger rather than a torn one.
* A skipped row stays `absent` (no SKIPPED member; ranks below PASSED).

**Still open, carried to W2-3-4/W2-3-5:** no shared clause key between the
two record kinds (a format-version bump); `Prediction` carries no structured
reason data and nothing checks prediction freshness against the tree; the
`fold_row_results` ABSENT-below-PASSED ranking; the operator set itself (see
the handover below).

## The measurement W2-3-2 seals

`tests/test_mutation_ledger.py` is the seal file, and its flagship row runs a
real mutation rather than asserting over a fixture. Re-derived 2026-08-18 at
`4e66a01da37c5ea4d480cc2aa3bca84728a2a4da` (`feat/D5-seals2`), not carried
from the P4 report:

* subject `src/claude_dispatcher/call_site_reachability.py`, anchor
  `discover_roots`, operator `raise_to_continue` on `AnalyzerError`.
* control: 95 node ids, 53 rows after folding, **all green**.
* mutant: exactly one row transitions —
  `test_discover_roots_raises_on_a_fault_without_help_from_the_graph_builder`
  (six parametrisations). Nothing else in the file moves.
* the row whose own clause names that mutation,
  `test_discover_roots_refuses_a_tree_it_cannot_sweep`, **passes under the
  mutant**. The clause was never true, which is why it was struck.

Both facts are recorded as `LedgerEntry`s over the same site and revision and
judged from the same pair of runs, so the expired claim folds to `broken` /
`strike` while the control folds to `held` / `cite_claim`. A fold that answers
either one constantly fails the other.

## Why the folds are pinned by VALUE and not by invariant

The first round of seals pinned `fold` with constraints — 7x7 totality,
`await_rerun`'s exact preimage, surjectivity over `Status` and `ClauseFate`,
and `citable == {cite_claim}`. A panel showed every one of them is satisfied
by an **inverted** table, and demonstrated two independent inversions that
kept all nine rows green:

* `fold(subject_moved | population_moved | provenance_gone,
  reddened_as_recorded) → expired` with `(…, survived) → reanchored`; and
* `proposed_fate(reanchored) = strike` with
  `proposed_fate(expired) = reobserve_then_cite`.

Under either, a clause whose mutation *still reddens exactly as recorded* is
proposed for `strike`, and a clause that **survived** — an entry that no
longer reproduces, which is this task's whole subject — folds to
`reobserve_then_cite` and stays citable pending a re-run. That is the failure
this unit exists to prevent, passing its own seal.

So all 49 cells are now written out as a literal table, `proposed_fate` is
pinned per member, and `freshness_of` is swept over all 64 drift subsets
against its numbered precedence list. The last of those closes a third
demonstrated hole: scanning `Drift` in **declaration order** and taking the
first match — which is also the order `Rederivation.__post_init__` forces the
tuple into, so it is the natural misreading — passed the old table of named
pairs while answering `provenance_gone` for `(revision_absent,
subject_absent)`, where the contract says `subject_gone`.

Arm 6 is not an edge case. It is the **common** path for W2-3-3 and W2-3-5,
which re-derive 41 clauses against subjects whose bytes have moved since the
clause was written; the flagship reaches only `anchored`.

## The harness holes, and why a seals task had to close them

Eight of the module's declared holes had no row anywhere in the repository:
`apply_mutation`, `provision_subject_tree`, `collect_rows`, `run_rows`,
`write_ledger`, `load_ledger`, `check_citations` and `main`. W2-3-2 is the
only seals task in this unit — W2-3-3 and W2-3-5 fill bodies, W2-3-4
adjudicates — so nothing later would have closed them.

Three of the eight are **fail-open by shape**, which is why they could not be
left:

| hole | a body that does nothing | reads as |
|---|---|---|
| `check_citations` | `return ()` | every tree is clean, `citations` exits 0 |
| `collect_rows` | swallow the collection error | the seal file shrank, so every entry against it reports population drift |
| `run_rows` | omit an unreported row | the row is `absent`, not "collected and never reported" |

The tiny repository these run against carries a **parametrised** row, because
that is the only place `collect_rows` (function-level, sorted) and `run_rows`
(node-id level, pre-fold) are allowed to differ — and a runner that folded
would hide a parametrisation that never ran behind one that passed.

The rows added for them assert **whole sets** rather than membership, and the
applier is checked against `_swallow` — the independent `ast` mutation this
file already carries and took the flagship measurement through. If the two
disagree, every re-derivation runs a different mutation from the one the
ledger records. That comparison is over **parsed trees**, not bytes: the
contract says "resolve the anchor with `ast`, refuse rather than no-op" and
says nothing about the emitted text, `mutant_sha256` is provenance that no
`Drift` member compares, and pinning bytes would make the harness answerable
to a private helper's indentation. What is pinned instead is that the parsed
trees agree and that the **only** function whose body moved is the anchor.

Two more shapes are refused rather than returned, and neither is visible in
an exception check alone:

* `run_rows` is given three runs that produce a well-formed result and no
  measurement — a seal file that stops importing, a file that collects
  nothing, and a row that calls `os._exit(0)` mid-run. Each refusal is
  asserted as the raise (`pytest.raises`), never as "no map came back": a
  body that returns `None` for a degraded run is the fail-open, not a
  refusal. The last shape is the one that defeats an exit-code check
  specifically: pytest never reaches its reporting hook, so there are no
  results, and the process exits **0** — and it is the one the seal cannot
  observe from its own interpreter, because a `run_rows` that runs pytest
  in-process is ended by the nested `os._exit(0)` with nothing raised and
  the session reporting green. So that case is driven from a **child
  interpreter** that prints a completion sentinel after the control run and
  the refusal; the parent judges the child's report, never its exit code
  (an in-process body exits 0 without the sentinel). The healthy tree is run
  first in the same call — in the same child for the `os._exit` case — so a
  `run_rows` that refuses everything fails rather than passing refusals.
* the provisioner row distinguishes the **requested revision** on a row
  rather than a marker file: the entry is recorded at a revision whose seal
  file carries a row that a later commit deletes, so a provisioner that
  stands up HEAD collects one row fewer and reddens the whole-set
  assertions. Its **isolation** is shown by swapping the recorded mutant
  into the clone through `scratch_clone.swap_in` and observing it redden
  there while the repository's bytes, status and HEAD are unchanged — plus
  `scratch_clone.assert_isolated`, because a linked worktree of the
  repository handed back as the clone passes every content check while its
  git commands operate on the real object database.
* `write_ledger`'s refusals are asserted on the **file**, not only on the
  exception. "It raised" is satisfied by a writer that truncates the ledger,
  writes the rival records, validates last and then raises — the previously
  valid ledger is destroyed and the caller is told the write was refused. So
  the committed bytes are compared before and after each refusal, and the
  refused path is checked for not having been created.

Two things are deliberately **not** sealed there, and both are named in the
rows: `check_citations`'s "a claim whose live observation does not
`counts_as_coverage`", because a W2-3-1 finding is that no stored record
carries a `Status` and the predicate is not computable from a ledger file;
and `rederive`'s `revision_run` beyond the one value that would be a lie.

## Which rows say `Measured under:`, and which do not

`Measured under:` is a claim about a run. In `tests/test_mutation_ledger.py`
only the five rows green over implemented seams can make it. Each named
mutation was applied to `mutation_ledger.py` and the row observed to go
`PASSED` → `FAILED` (2026-08-18):

| row | mutation |
| --- | --- |
| `…_is_predicted_and_never_cited` | drop `Prediction.subject_sha256` |
| `…_is_predicted_and_never_cited` | put the judgement's `reason` into `prediction_id` |
| `…_is_predicted_and_never_cited` | drop `described` from `prediction_id` |
| `…_is_predicted_and_never_cited` | let `observations` return every record |
| `…_reddens_the_row_and_a_missing_one_does_not` | rank `FAILED` below `PASSED` |
| `…_reddens_the_row_and_a_missing_one_does_not` | drop the `[param]` split |
| `…_no_role_could_create_is_refused_before_it_is_used` | drop the `first_matching_glob` floor check |
| `…_no_role_could_create_is_refused_before_it_is_used` | scan `rule.globs` instead of calling `evaluate_changed_paths` |
| `…_no_role_could_create_is_refused_before_it_is_used` | drop the dot-in-segment refusal in `ledger_path_for` |
| `…_round_trips_and_a_damaged_one_is_refused_not_guessed` | guess the record kind from which keys are present |
| `…_round_trips_and_a_damaged_one_is_refused_not_guessed` | coerce a string to a bool in `_typed` |
| `…_round_trips_and_a_damaged_one_is_refused_not_guessed` | drop BOTH id re-derivations from `LedgerEntry.__post_init__` |
| `…_round_trips_and_a_damaged_one_is_refused_not_guessed` | drop `_refuse_unknown_keys` from `_parse_observation` |
| `…_round_trips_and_a_damaged_one_is_refused_not_guessed` | drop `parse_constant=` from `json.loads` |
| `…_two_live_observations_has_no_answer_and_is_refused` | pick the later entry by file order in `current_observations` |
| `…_two_live_observations_has_no_answer_and_is_refused` | drop the `target.claim_id` check |
| `…_two_live_observations_has_no_answer_and_is_refused` | drop the `superseders` check |
| `…_two_live_observations_has_no_answer_and_is_refused` | resolve `supersedes` against later entries too |

The other eighteen rows are red against `freshness_of`, `classify_observation`,
`fold`, `proposed_fate`, `rederive`, `apply_mutation`,
`provision_subject_tree`, `collect_rows`, `run_rows`, `write_ledger`,
`load_ledger`, `check_citations` or `main` under the **control** as well as
the mutant, so no `PASSED` → `FAILED` transition exists to observe. They carry
`Predicted (unmeasured) under:`, which is what the ledger's own vocabulary
requires of a claim with no comparison behind it — the same rule this unit
applies to the 31 expired clauses. W2-3-3 filled the holes and every one of
the eighteen is green over a real body now, so each has become measurable;
the promotion to `Measured under:` is an edit to `tests/`, which BODIES may
not make, and stays with SEALS under W2-3-4's ruling.

## What running the seal file costs, and what it must not touch

The flagship's measurement is a real pair of pytest runs, so the file is
explicit about its own footprint:

* it takes the subject tree with `git archive`, never `git worktree add`, so
  no repository metadata is written to take a measurement;
* `rederive` *is* specified to add a worktree and delete `.claude/workflow`
  inside it, so the rows that call it are handed a throwaway
  `git clone --shared --no-checkout` of this repository, never the developer's
  checkout;
* the nested runs get an environment scrubbed by prefix (`PYTEST_*`,
  `COVERAGE_*`, `PYTHON*`, `GIT_*`), because `PYTEST_ADDOPTS` carrying `-k`,
  `--lf` or `--maxfail` silently changes the population the flagship calls a
  whole file — **and** `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`, because a
  `pytest11` entry point installed in the interpreter (`cov`, `timeout`,
  `xdist`, `rerunfailures`, `testmon`) is loaded with no environment variable
  naming it, which is the same "a clean shell is not CI" escape the scrub
  exists to close. The one plugin the measurement needs is named with `-p`;
* every subprocess is bounded (`TIMEOUT_SECONDS`), the nested pytest's exit
  code is checked against `{0, 1}`, and its output is reported on anything
  else — a junit file from an interrupted run is well-formed and can hold the
  two rows the flagship asserts on while the rest never ran;
* the collected population comes from a plugin loaded into the measurement run
  itself, so a row that was collected and then not reported is `ABSENT` rather
  than missing from the map.

`4e66a01…` and `2e0dc89…` are object-database dependencies, and their absence
**fails**. Every row that takes a measurement needs them — the flagship, the
rederive oracle, the applier, and the one green prediction-staleness row — so
a clone without them does not lose a row, it loses the file's entire subject
and still exits 0. That is "a green suite that compared nothing", which is the
reading this whole unit exists to make impossible; the file must not produce
one about itself. Nothing in this repository sets an opt-in variable, there is
no CI workflow, and `actions/checkout` defaults to `fetch-depth: 1`, so a gate
that skipped unless told otherwise would be fail-open in every environment
that exists today.

`MLSEAL_ALLOW_MISSING_HISTORY=1` restores the skip for a clone that genuinely
cannot fetch. It is a named act: whoever sets it is saying "this run does not
measure", and the skip message says so.

The gate is narrow in the other direction too, because a skip is also how a
green run comes to mean nothing:

* only the **absence itself** is skippable. `git cat-file -e <sha>` —
  unpeeled — exits 1 with an empty stderr for an object this clone does not
  have, and 128 with a message for no repository, an unreadable object
  database, or a git that will not start. The rest are raised. (Peeled,
  `<sha>^{commit}` reports the absence as 128 too, and the two become
  indistinguishable, which is what the previous gate did.)
* it names **every** revision a row will reach, so a clone carrying
  `4e66a01…` but not `2e0dc89…` is answered here rather than raising
  `CalledProcessError` out of `git show`.

## What the seals could not fix

**Three** defects the rows pin the *correct* side of, and which the seal
author cannot correct in `mutation_ledger.py`:
* **`Rederivation.revision_run` has no truthful value** when nothing was
  provisioned, while `rederive` must still return a `Rederivation` for an
  absent revision. The seal asserts the disposition (`underivable`) and the
  one answer that would be a *lie* — `revision_run` may not echo back the
  revision that is absent, which is the cheapest value for a body to reach
  for. The null sha and the revision of whatever tree was in fact stood up
  both stay open; W2-3-4 owns the ruling that closes them.
* **`fold_row_results` ranks `ABSENT` below `PASSED`**, so a row whose `[b]`
  was collected and never reported folds to `PASSED`. The seal pins the
  current ranking so that changing it is a visible diff, and names it as
  unruled rather than answering it.
* **The two record kinds share no clause key**, so `validate_ledger` cannot
  tell one *row* carrying two clauses — which is legitimate and common in
  this population, and which it argues at length it must keep accepting —
  from one *clause* recorded twice, where a citation could pick whichever
  disposition supports it. `claim_id` keys on `(row, site)` and
  `prediction_id` on `(row, described)`.
  `test_a_claim_with_two_live_observations_has_no_answer_and_is_refused`
  pins the **missing key** rather than the acceptance: it asserts that the
  pair it uses names two different clauses, and that the two kinds share
  exactly the five field names `seal_file`, `claiming_row`, `revision`,
  `subject_sha256`, `note` — of which the first two name the *row*, the next
  two are provenance equal at one commit, and the last is prose. Any added
  shared clause key reddens that line **whatever it is named**, which a
  comparison of `claim_id` against `prediction_id` could not do: their
  `ml-`/`mlp-` prefixes make them unequal under every possible
  implementation, so such a comparison asserts nothing about this module.
  Written this way round, a W2-3-4 ruling that adds the key and refuses the
  duplicate does not have to redden a row demanding that the pair stay
  accepted.

## What the ledger holds so far (W2-3-3, 2026-08-28)

Five records at `efd05ca0f795bb223a3e9482f622d8dfcfa54817`, every one made by
the CLI above and none transcribed from a clause. The population is 40 rows
carrying the `Reddens under a body on:` header (41 grep hits: line 2968 of
the seal file is a mention of another row's clause, inside row
`test_discover_roots_raises_on_a_fault_without_help_from_the_graph_builder`).

| record | row | what was observed / judged | clause text vs. record |
| --- | --- | --- | --- |
| `ml-bf1a80e6438d` | `test_discover_roots_raises_on_a_fault_without_help_from_the_graph_builder` | `raise_to_continue` on `discover_roots`/`AnalyzerError`: control green, reddens exactly this row | **agrees** ("this row and no other in the file"); re-derives `held` at target and at recorded |
| `ml-c3420ec3a18c` | `test_root_kind_is_derived_from_the_kind_and_never_asserted_by_the_row` | `body_to_no_op` on `_validate_root`: control green, reddens **4** rows — this one, `…_disagrees_with_its_own_file…`, `test_a_test_function_outside_the_tests_is_refused_in_both_spellings`, `test_root_kind_derives_from_the_kind_and_the_declaring_file_together` | **disagrees**: the clause says "this row and its sibling, and no other row in the file". The two extra rows were added by `seals(D5)` `3eedd07` after the clause was written at `4e66a01` — the file grew. Proposed for W2-3-4: `amend_scope` (keep the mutation sentence, cite the claim) |
| `ml-02d29bf4548e` | `test_a_root_that_disagrees_with_its_own_file_or_names_no_kind_is_refused` | same mutation, same 4 rows | **disagrees** the same way ("the first reddens this row and the sweep above"). Proposed: `amend_scope`. Its other two sentences (a default on `_ROOT_KIND_BY_ENTRYPOINT`; dropping the `is_test_path` cross-check) are edits outside the operator set and are W2-3-5's to record as predictions |
| `mlp-e51598c10e9f` | `test_adjudicate_is_total_over_the_grid` | "a default branch of any kind" — `reference_implementation_discarded` | the clause predates the shipped body; `adjudicate` dispatches through the `_RULINGS` table, so `add_default_branch` finds no else-less return chain and is refused |
| `mlp-bb680f38bd5f` | `test_an_edge_kind_in_neither_strength_class_is_a_refusal_not_a_default` | "``return False`` or ``return True`` in place of ``_edge_is_resolved``'s raise" — `no_applicable_operator` | measured against the shipped body at `4e66a01`, but "replace one raise with a return" is not `return_constant`, which replaces the whole body |

`fates` proposes `cite_claim` for the three observations (each is `held`)
and `relabel_predicted` for the two predictions. The scope disagreements on
the two `_validate_root` clauses are **reported here, not corrected**: the
clause text is in `tests/`, and the ruling is W2-3-4's.

**Which reason a prediction takes**, the rule applied above and offered to
W2-3-5: a clause on a row that was `RED at HEAD` when written (rows 1–29 of
the population, `seals(D5)` `094fffb`..`4e66a01`, before the shipped body)
is `reference_implementation_discarded` — whatever it was measured against
is gone; a clause on a `GREEN at HEAD, mutation-verified` row whose edit is
outside the closed operator set is `no_applicable_operator`;
`anchor_not_in_subject` is for an operator that fits but an anchor that no
longer resolves (none found yet).

**The shape of the remaining 35 rows, measured rather than guessed.** Read
against the four operators, none of them names an edit the closed set can
apply:

* 28 rows (`RED at HEAD` when written) name whole alternative bodies —
  "any discrimination on `detail`", "any write into `tree`", "swapping the
  two behaviours" — expected: 28 predictions, `reference_implementation_discarded`.
* 7 rows (`GREEN at HEAD, mutation-verified`) name edits the set does not
  express: deleting one call (`_validate_subject` in `check_tree`;
  `_validate_finding` at either layer), restoring a default argument or a
  fallback, moving one check after another, sorting a result, a specific
  return value for one branch (`_chain_quality` on the empty chain) —
  expected: 7 predictions, `no_applicable_operator`, plus the two extra
  sentences on `ml-02d29bf4548e`'s row.
* Expected observations among the 35: **0**. The three recorded are the
  whole reach of the operator set over this file.

So the ceiling on this ledger is the operator set, not the harness. A fifth
operator — *delete one call statement in the anchor* — would reach three
more rows (four sentences) with real runs; the contract says such an
amendment must arrive **with an observation that exercises it**, which makes
it W2-3-5's to propose with a measurement, or W2-3-4's to rule out.
