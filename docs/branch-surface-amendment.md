# The floored amendment: wiring `branch_surface` into the signature gate

`branch_surface.py` decides whether a branch widened a sealed declaration space
from a file the per-file gate never compares. It decides nothing until the gate
calls it, and the only place that call belongs is
`role_protocol._compare_branch_signatures` — **floor glob 3 of 20**, which no
role may edit. This document is the whole of what an operator (task W2-2-5)
applies. It is a transcription: if anything here requires a decision, it is not
ready, and the correct move is to send it back to W2-2-3 rather than decide it
here. An operator deciding is an unreviewed design act.

## Preconditions — check all four before touching the file

1. `branch_surface`'s two holes are filled (W2-2-3). The check is an exit code,
   not a judgement:

   ```
   python -m claude_dispatcher.scaffold_shape holes --bodies \
     src/claude_dispatcher/branch_surface.py::build_surface \
     src/claude_dispatcher/branch_surface.py::compare_surfaces
   ```

   These two are W2-2-1's `declares.holes` in full, so the bodies gate checks
   them on its own and this command only makes it visible. **The module has no
   other stub**: `_fold` is implemented, because a stub outside the declared
   pair is a hole no gate checks — the bodies gate would pass with both
   declared holes filled and the module still answering UNDETERMINED. What
   `_fold` contains is the read order, the fault precedence and the error
   contract; every judgement it routes through is inside one of the two holes,
   so it decides nothing before the seals do.

   Transcribing this patch before W2-2-3 lands is still wrong, but it fails
   CLOSED rather than aborting the gate: `fold_branch_signatures` converts the
   holes' `NotImplementedError` into `RoleDiffError`, so every BODIES branch
   with TypeScript in it reads UNDETERMINED.
2. W2-2-2's rows are registered in `config/known-red.yaml` against
   `body_task: W2-2-5`, so they retire when this row is marked Done.
3. The suite is green at the commit being amended.
4. Both edits below land in ONE commit. Edit 2 without edit 1 floors a module
   nothing calls; edit 1 without edit 2 puts a gate decision in a file every
   BODIES branch may rewrite.

## Edit 1 — the call

In `src/claude_dispatcher/role_protocol.py`, in `_compare_branch_signatures`,
**after the `for path in changed_paths:` loop and BEFORE the `if not examined and
unsupported_paths:` block**, insert:

```python
    # The branch-wide half (W2-2). Everything this could decide is decided in
    # `branch_surface`; nothing but `RoleDiffError` crosses back.
    from . import branch_surface as _branch_surface

    fold = _branch_surface.fold_branch_signatures(
        repo_root, merge_base, branch_ref, changed_paths, run=run,
    )
    status = _worst_signature_status(status, fold.status)
    changes.extend(fold.changes)
    if fold.detail:
        details.append(fold.detail)
```

Four things about the placement, each of which is a defect if changed:

* **Before the promotion block, not after.** The promotion sets
  `UNCHECKED_NO_SUPPORTED_FILE`, which is deliberately absent from
  `_SIGNATURE_STATUS_PRECEDENCE`; `_worst_signature_status` raises on an
  unranked status. Placed after, a Go-only or docs-only diff raises instead of
  clearing. Placed before, the promotion still fires and still wins, and the
  fold contributed nothing to it — with nothing in the diff whose language
  merges declarations across files, `fold_branch_signatures` returns
  `CLEAN_FOLD` before any read.
* **After the loop, not inside it.** The loop `continue`s on `if base_text is
  None`, which is exactly the new-file case this unit exists to catch; a block
  spliced beside the `compare_signatures` call is never reached by the attack.
* **`merge_base`, not `base_ref`.** The path list is a three-dot diff measured
  from the merge-base, so the baseline blobs are read there. Passing `base_ref`
  reintroduces the D1-inputs I4 defect the function's own docstring names.
  `merge_base` is `str | None` here and the fold takes both — but **`None` is
  only a clean answer when the diff holds no merging-language path**. With one
  present the fold raises `RoleDiffError` rather than clearing, because "there
  was TypeScript and no baseline" is not a pass. Through this call site that
  case is unreachable: TypeScript is enrolled in `COMPARATORS`, so a `.ts` path
  is examined by the loop and the lazy merge-base is resolved before the fold
  sees it. The refusal is the module's own fail-closed contract, not a case an
  operator has to arrange.
* **The import is function-local.** `branch_surface` imports `role_protocol` at
  module scope; a module-scope import back would be a cycle.

`fold.changes` are `SignatureChange` values, so no printer, caller or report
format changes. `fold.status` is CHECKED or a ranked blocking `UNCHECKED_*`.
Every other outcome — an unread global, script, unresolved or over-budget
space — arrives as a `RoleDiffError` raised out of the fold, which
`check_branch` already maps to UNDETERMINED at its `except (RoleDiffError,
RoleProtocolError)` guard. No new exception type reaches this function, and no
new status needs a rank.

## What this costs, per branch

Zero on any diff with no TypeScript path in it — `_merging_paths` filters
before the first read, and this repository has no TypeScript in it today.

On a diff that does, the bound is stated in `_fold` and is
**`2 × (changed TypeScript paths) + MAX_CLOSURE_READS`** blob reads, where
`MAX_CLOSURE_READS` is 256: two per changed path (merge-base and branch head),
plus the baseline read of every candidate path a relative `declare module`
specifier could name, six per specifier, deduplicated. A closure larger than
the cap is reported as an unread space (`BUDGET_EXCEEDED`) and therefore
UNDETERMINED — it is never silently truncated, because a bound that drops
candidates quietly is a bypass anyone can buy with a large diff.

## Edit 2 — the floor

In the same file, append to `FLOOR_GLOBS`:

```python
    # The branch-wide half of the signature gate (W2-2, 2026-08-18). It is on
    # the gate path from the commit that adds the call above, and a check a
    # branch can edit is not a check.
    "**/src/claude_dispatcher/branch_surface.py",
```

## After applying

1. Run W2-2-2's registered rows targeted; they must now pass. The CONTROL rows
   matter as much as the rest: an in-place widening must still be exactly one
   change, and a member added to a container in its own file must still be no
   change. A fix that reddens a control has broken the gate it was extending.
2. Run the whole suite. `tests/test_floor_closure.py` reads `FLOOR_GLOBS`.
3. Mark W2-2-5 Done, which retires the known-red entry. If the row is marked
   Done without this patch applied, those rows become required-green, fail, and
   the gate goes red — it fails toward red by construction.

## What this patch deliberately does not do

* It does not thread the loop's already-read blobs into the fold. The fold
  re-reads what it needs, which costs the bound above and nothing at all on any
  other diff. Threading them would mean restructuring the loop body, which is a
  floored edit with judgement in it.
* It does not filter `changes`. The fold may only ADD findings and worsen
  status. A legitimate move of a sealed symbol therefore stays refused, exactly
  as it is refused today; relaxing that is W2-2-4's ruling, not an operator's.
* It does not make TypeScript module-ness available, and this is the patch's
  real cost. Until a comparator reports `is_module`, a changed `.ts` file whose
  keys carry no `export =`/`export {}` surface, no anonymous default export and
  no relative `declare module` is routed to the global space and read as
  UNDETERMINED. **Measured on this tree:** the fingerprinter puts the `export`
  modifier in the fingerprint value, not the key — `export interface Bet {…}`
  keys as `i:Bet` — so an ordinary exported declaration is NOT proof, and a
  branch touching one `.ts` file reads UNDETERMINED rather than clean.

  That is the fail-closed half of the script bypass: routing an unknown file's
  declarations to its own space instead is the bypass this unit exists to
  close. Closing it properly needs `ts.isExternalModule` reported by the helper
  or the export modifier keyed, and both live on the floor (`role_protocol.py`
  and `ts_signature_fingerprint/` are floor globs 3 and 12) — a separate unit,
  not an operator edit. **If that cost is not acceptable before it lands, the
  ruling belongs to W2-2-4 and the routing default is `build_surface`'s to
  change; do not soften it here.**
