# DF-2 rulings — the merge pin

Documentation records. No gate reads this file. All sections recorded by the
DF-2-4 adjudicate role.

## Adjudication (DF-2-4): both ladder branches take the SAME pinning; the source asymmetry is ratified

The boundary question this row owns (merge_authorization.py, question 3):
does the self-approval path take the same pinning as the externally-approved
one?

**Decided:** yes — the same pinning, ratified as DF-2-3 landed it. Both
branches construct the same record type (`MergeAuthorization`, whose
`__post_init__` makes an unpinnable authorization unconstructible), travel
through the one `merge_pr` call that carries
`match_head_commit=authorization.head_sha` unconditionally
(merge_engine.py:312-315 — there is no unpinned merge path left in the
engine), are enforced by the same origin-side refusal atomic with the merge,
stamp the same two audit keys into `pr_approved`, and fold the same way on
failure (fail-closed hold, reason journaled, never `needs_rebase`). What
differs is only the SOURCE, by named enum member: `LOCAL_CLASSIFIED_TIP`
(the local tip, resolved once, then diffed — pin-then-judge, so the SHA
named is the SHA judged by construction) versus `EXTERNAL_REVIEW_COMMIT`
(the approving review's `commit.oid` — the tree the reviewer actually saw).
That asymmetry is the honest shape the scaffold argued: each branch pins the
tree its OWN authorizer judged, and there is no single source that names
both.

**Decided against:** both available symmetries.

* *Source symmetry via origin* — pinning self-approvals to origin's branch
  tip read at merge time. Rejected in the scaffold (question 1) and upheld:
  a pin read from the thing it is compared against always matches, so it
  verifies nothing, and the two-step compare-then-merge shape races where
  the one-argv pin is atomic.
* *Source symmetry via review* — requiring an external review object so
  both branches pin from a `commit.oid`. The measured constraint kills it:
  five of the seven recorded merges were self-approvals and PR #39's
  `reviews` array is `[]` — the majority path has no review object AT ALL,
  so this symmetry hardens only the minority path.

**Measured:** re-ran this session at 2549a83 —
`pytest tests/test_merge_authorization.py tests/test_merge_engine.py
tests/test_merge_record.py tests/test_path_gate_bypass.py tests/test_pr.py
tests/test_rulings_channel.py` → 90 passed, 0 failed, 0 xfailed, 2.13s. The
24 DF-2-2 seal rows run plain green (the three self-retiring probes flipped,
`strict=True` held); the engine rows pin the self-approved merges by
equality to same-call rev-parses of the judged tips and the elevated merge
to the reviewed oid, with both `pr_approved` stamp keys asserted — both
branches' pins are sealed, not just claimed. Wiring read on this tree:
`_classify` receives `authorization.head_sha` (merge_engine.py:247), so the
judged tree is the pinned tree by construction on the self-approval branch.

**What would change the ruling:** a third authorizer — which is a new named
`AuthorizedShaSource` member reviewed as a shared-contract change (the
members-are-fixed seal makes a silent addition loud), never a re-sourcing of
an existing member; or a measured break of pin-then-judge (classification
observing state other than the pinned SHA), which would be a defect in the
self-approval branch's construction, not a reason to abandon its pin.

## Adjudication (DF-2-4): a mismatch keeps the plain error fold — no named `MergeResult` kind while the refusal is unmeasured

DF-2-3 posed this exactly (summary, "Notes for DF-2-4"): whether a
mismatched `--match-head-commit` deserves its own named kind on
`pr.MergeResult`, or stays the plain fold it landed
(`merged=False, conflict=False`, engine journal `kind="error"`,
`needs_rebase=False`).

**Decided:** the plain fold stands; no new named kind now. The fold already
produces every consequence that matters: the moved head never wears the
conflict label a rebase is supposed to fix (a rebase does not re-judge a
tree), there is no retry and no unpinned re-invocation, the row holds
fail-closed, and origin's detail is journaled. A named kind would add no
correct behavior today — it could only route somewhere, and every correct
route already happens.

**Decided against:** adding a `head_moved` (or similar) kind now. Naming the
case requires classifying gh's refusal stderr, and that message remains
**Predicted (unmeasured)** — DF-2-3 could not reach a live moved-head PR
from its environment. A kind keyed on a predicted string is the exact
marker-drift class the seals' in-call control exists to catch
(`_PREDICTED_MISMATCH_STDERR` vs `pr._CONFLICT_MARKERS`,
tests/test_merge_authorization.py); a misnamed kind is worse than an
unnamed one, because a later reader routes on the name.

**What would change the ruling:** a live measurement of gh's mismatch
refusal. With a measured string in hand, a named kind becomes an ordinary
shared-contract change: add the marker, update the one harness constant the
seals name for exactly this event, and let the in-call control prove the
new marker collides with nothing. Recommendation to the operator: a
follow-on measurement row — a disposable moved-head PR on a scratch repo,
deliverable being the measured string and that one-constant update.

## Adjudication (DF-2-4): DF-2-3 recorded no Deviation; the D-72 split is ratified

DF-2-3's summary carries no `## Deviation` heading — the body conformed to
the scaffold's contract on every seam it filled. Its two role-gate
violations (the fake-gh harness amendment in `tests/test_merge_engine.py`;
the `_classify(cfg, row, branch)` → `_classify(cfg, row, head_sha)`
signature) were adjudicated by the operator as D-72: both were assigned to
the body by its own brief, neither was its to commit, and both were split
into operator commits (bf2644a, c98bc44). Nothing is left for this row to
re-rule; the split is ratified as recorded, and the harness amendment it
moved — now on this row's own `disputed_paths` surface — is accepted as
written: the 40-hex token skip in `_num()`/`_merge_order` closes the
scaffold-named first-all-digit-token hazard, and the argv equality
assertions are the cheap seal the brief predicted. No amendment to
`tests/test_merge_engine.py` or `tests/test_pr.py` is forced by any ruling
above; per the D-65 lesson, ruling prose lands here and only here.
