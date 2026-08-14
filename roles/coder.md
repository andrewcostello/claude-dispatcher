# Coder (implementer) brief — scratch copies of worktrees

**Status: MANDATORY** (P4 ruling, DF-4-4, 2026-08-14; record in
`docs/rulings/DF-4.md`). This section binds every dispatched implementer
role — scaffold, seals, bodies, adjudicate, legacy — whenever it wants a
scratch copy of a worktree or repository checkout to probe, mutate, or run
anything destructive in.

Why it is mandatory and not advice: the advisory form already ran, and lost.
Every brief in the 2026-08-07..12 effort said "remove the `.git` FILE first",
and three separate agents still made a `cp -a` copy of a linked worktree and
ran git inside it — most recently a `git revert --no-commit` that MOVED THE
REAL INDEX. A sentence prescribing a technique loses to muscle memory; this
brief prescribes a one-line invocation instead.

## The rule

Create every scratch copy with the helper, never by hand:

    SCRATCH=$(python -m claude_dispatcher.scratch_clone <worktree> <dest>)

* **Exit 0** — stdout is the clone path alone: a quarantined copy whose git
  commands cannot reach the real repository (`assert_isolated` has already
  passed when you get it).
* **Exit 2** — a named refusal was printed to stderr. **Stop and report it
  in your summary.** Do NOT fall back to a hand copy: the refusal names a
  state in which the helper cannot guarantee a safe copy, and a hand copy
  made in that state is precisely the incident this helper was built from.
* **Exit 3** — malformed invocation. Exactly two positional arguments, no
  flags; there is deliberately no `--force`.

From Python, the same seams are `make_scratch_clone`, `assert_isolated`,
`swap_in` / `swap_back` in `claude_dispatcher.scratch_clone`. The CLI face is
the recommended entry from an agent shell because it inherits the module's
`GIT_*` scrub by delegation.

## Banned outright

* **A file-level copy of a worktree or repository to probe in** — `cp -a`,
  `rsync`, `shutil.copytree`, tar round-trips, all of it. A linked
  worktree's `.git` is a 54-byte pointer FILE; `cp -a` copies it verbatim
  and every git command inside the copy operates on the real repository.
* **Removing the `.git` file by hand as the "fix".** Measured: discovery
  then walks UP, so a copy parked under any ancestor repository resolves to
  — and mutates — that ancestor. Removal changes which wrong repo gets hit.
* **Pointing `--work-tree`, `--git-dir`, or `GIT_DIR` at a scratch clone
  from outside it** (P4 ruling: banned outright). A command run outside the
  clone never consults the clone's discovery, so no property of the clone
  can intercept it — the quarantine cannot police the keyboard, so the
  brief does. The reason to type it is already a seam: to mutate a file and
  put it back, use `swap_in` / `swap_back`.

## What stays advisory

The helper is required for copies of git repositories and worktrees — the
measured hazard. Copying a plain directory that is not (and is not inside)
a repository checkout carries none of it; the helper is not required there,
though it refuses such a source loudly (`SOURCE_UNUSABLE`) if you point it
at one, which is itself a cheap way to check what you are holding.
