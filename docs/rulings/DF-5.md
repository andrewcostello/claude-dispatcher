# DF-5 rulings — the money net (recorded by the DF-5-4 adjudicate role)

Documentation records. No gate reads this file (the D-66 boundary).

## A consumer that cannot see the target repository ships no list — it ships the universal glob, with the reason named

The task put the dispute plainly: should a fallback that cannot see the
target repository ship a list at all, or refuse? Ruled: **neither a list nor
a run-abort.** When the net cannot be derived, the state is ABSENT with a
mandatory detail, and the env fold is exactly `**` — everything is money
until the repo says otherwise. DF-5-1 ruled this; DF-5-3 implemented it
exactly; this adjudication upholds it.

* **Decided against a recited list** (the shipped `DEFAULT_FINANCIAL_PATHS`,
  or any successor): a list recited from memory is a claim about a
  repository the reciter cannot see. Measured on this tree: the hand-list
  was 49 globs stale against the tracked table's 74 (evenplay-mono
  `164d3a828`, blob `7b4fd16fffdb`), one day after its last sync commit
  promised otherwise (`0a457ff`), and it was injected verbatim into
  claude-dispatcher runs it never described — noise presented as a safety
  net. A hand-list plus drift test was the shipped status quo and failed the
  same day: the detector's truth source was an untracked mirror.
* **Decided against refusing to run**: the classification contract is
  ADD-only — `FINANCIAL_PATHS` can only widen scrutiny, never exempt a path
  from it. For an ADD-only net the honest fail-closed shape is "gate
  everything", not "run nothing"; over-gating costs review attention,
  under-gating costs money, and an abort costs the whole run to protect
  against a risk `**` already covers. `**` also makes the ignorant and the
  informed reading agree: a consumer that has never heard of ABSENT
  over-gates, never under-gates (an empty string or a sentinel word would
  silently under-gate — GO-0 wearing a uniform).
* **Measured:** live derivation against evenplay-mono yields 74 globs at the
  authoritative commit; `main` (no tracked table) folds to ABSENT/`**` with
  the ref named — both exactly as DF-5-1 measured. `tests/test_money_net.py`
  17/17 green on this branch.
* **What would change the ruling:** if `FINANCIAL_PATHS` ever gains a
  SUBTRACTIVE consumer — anything that treats a *non*-matching path as
  exempt from a check it would otherwise get — `**` stops being fail-closed
  (it would exempt nothing, but a *derived* list would, making absence the
  safer state) and the whole fold must be re-adjudicated before that
  consumer ships. Short of that, a measured over-gate storm (runs unusable
  because `**` drowns reviewers) would justify revisiting *refusal*; nothing
  re-justifies a list.

## Refusal's one rightful place: the contradicted operator

The one branch where the run does refuse outright is ruled correct: a
malformed `--financial-paths` override exits 2 before any run artifact
exists, while an *empty* override folds to ABSENT/`**` with the reason
named. The asymmetry is the point. Absence of knowledge is a state the
fail-closed fold covers; a present-but-malformed operator statement cannot
be folded away without either honoring a corrupt net or silently replacing
what the operator explicitly said — and D-65 already teaches what silent
substitution costs. Loud refusal of an explicit statement; quiet widening
for a missing one. Reversal trigger: none foreseen — folding a malformed
override to `**` would mean an operator typo widens the net without the
operator learning their flag was discarded.

## The disputed path stays deleted

`tests/test_default_financial_paths.py` — this row's `disputed_paths` entry,
deleted by DF-5-3 — is ruled retired, not restored. Its parity row compared
the condemned constant against `~/Project/evenplay-mono/.agent/risk-paths.json`,
an untracked file frozen at the pre-#1387 table, so it was green across a
49-glob drift; its structural row (`test_entries_are_normalised_globs`)
would have rejected 14 of the authoritative table's own exact-file rows.
The relationship it pretended to seal is now sealed for real by
`tests/test_money_net.py` (drift row through the production fold, two
retirement rows, one-commit coupling row). A restored file would first have
to defeat the retirement seals, which pin `CONDEMNED_SURFACES` by name —
that is the intended cost. Reversal trigger: none; a future hand list is
the defect this unit exists to make unrepresentable.

## Advisory findings on this surface, ruled

DF-5-3 disclosed **no deviation**, and its summary claims transcribe the
ruled contract faithfully (checked against `money_net.py` as merged). The
open items on this surface are the advisory panel findings from DF-5-1,
ruled here so they stop being ambient:

* **grok MEDIUM (bare `financial_globs_from_table` is fail-open):** ruled to
  STAND as shipped, with a named tripwire. The helper is documented as the
  pure half — the caller folds `()` and `ValueError` to ABSENT — and today
  it has exactly one production caller, `derive_money_net`, which does so;
  glob validation fires in the `MoneyNet` constructor, and an illegal table
  glob folds to ABSENT ("carries an illegal glob"), sealed green. The
  finding's real content is that this safety is a call-site convention, not
  a property of the helper (the D-65 lesson). Revisit trigger: the moment a
  second call site consumes the helper's raw return — that call site is the
  bug, and validation moves into the helper (raise on bad glob; never return
  a joinable `()`) in the same change. Recommended as a follow-on seals row,
  not written here: `tests/test_money_net.py` is DF-5-2's surface, outside
  this row's writable set.
* **grok LOW (40-hex `_SHA_RE` refuses sha256-object-format repos):** ruled
  to STAND. On a sha256 checkout the derivation folds to ABSENT with the
  detail naming the non-40-hex token — the degradation direction is a loud
  named over-gate, never a silent accept, which is this unit's stated
  failure direction. Revisit trigger: a real sha256-format target repo in
  dispatcher use; the fix is accepting 40- or 64-hex as the freshness
  witness, a seals+bodies row.
