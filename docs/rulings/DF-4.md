# DF-4 rulings — scratch clone

Documentation records. No gate reads this file. The round-2 sections were
recorded by the DF-4-3 bodies role, per the round-2 adjudication's
invitation; the adjudication sections by the DF-4-4 adjudicate role.

## Symlink rule narrowed: landing place, not resolvability (round 2)

Round 1 asked that a dangling symlink not be accepted just because its
unresolved text reads in-clone; the fix answered with strict resolution,
which refused EVERY unresolvable link. Round 2 (grok, :765) measured the
overshoot: real worktrees legitimately carry dangling links (relative
targets, editor artifacts, links into build output that does not exist
yet), so a correct clone of a normal repository was refused and the claimed
destination deleted.

Ruling applied: a symlink is judged by its LANDING PLACE — where a write
through it would land — never by whether its target exists.

* Every existing component of the target chain is resolved through the
  filesystem (a chain through an existing out-of-tree link is caught).
* A missing tail is normalized lexically, which is sound because a missing
  directory can hold no symlink to reroute the tail.
* A landing place outside the clone refuses; a landing place that cannot
  be computed at all (a symlink loop) refuses — unprovable keeps the
  unsafe answer.
* Mechanism: `os.path.realpath(strict=os.path.ALLOW_MISSING)` (CPython
  3.13.4+). On an interpreter without `ALLOW_MISSING` there is no
  loop-safe way to compute the landing place of a dangling link, so it
  refuses there — fail closed, per-interpreter, rather than a lexical
  fallback that walks a loop.

## Quarantine identity is an exact-shape allowlist (round 2)

Round 2 (codex, :947) showed emptiness-of-refs was not the quarantine's
identity: an otherwise-empty real repository carrying an index,
pseudorefs, includes, aliases, `core.hooksPath`, or `core.fsmonitor`
satisfied every named check while each is a door.

Ruling applied: `assert_isolated` now establishes the fresh-init shape
itself — exactly the files, directories, and local config keys a scrubbed
`git init --template=` writes (measured, git 2.51.0) — and refuses
everything else BY NAME, including entries and keys the module has never
heard of. Allowlist, not blocklist: a new door is refused before it needs
to be understood, where a blocklist is the enumeration that falls out of
date. The stated LIMIT stands: a repository byte-identical to a fresh
quarantine remains indistinguishable and is accepted; shape, not
provenance, is the establishable property.

Consequence accepted knowingly: a future git version whose `init` writes a
new file or config key will make the probe refuse fresh quarantines until
the allowlist constants are extended. That is the correct failure
direction (loud, named, fail-closed) and the maintenance cost is one
constant per git change.

## Source validation is anchored, not existential (round 2)

Round 2 (codex, :713) showed `lexists(source/".git")` handed a success
receipt to an arbitrary directory. Ruling applied: git's own answer,
anchored — `rev-parse --show-toplevel` run AT the source under the scrub
must answer the source itself. An umbrella repo answers the umbrella root,
garbage answers a nonzero rc; both refuse as `SOURCE_UNUSABLE`. The cheap
`lexists` check stays as a first gate so a plain directory refuses without
spawning git.

## Adjudication (DF-4-4): the helper is MANDATORY in role briefs

**Decided:** mandatory. The brief text lives at `roles/coder.md` (this
row's `disputed_paths` grant) and binds every implementer role: a scratch
copy of a worktree or repository checkout is made with
`python -m claude_dispatcher.scratch_clone SRC DEST` (or the module seams),
never by hand; a refusal is stop-and-report, never a hand-copy fallback.

**Decided against:** staying advisory. The advisory form is the control for
this experiment and it already failed: "remove the `.git` FILE first" was
in every brief of the 2026-08-07..12 effort and three agents still `cp -a`'d
a linked worktree — most recently a `git revert --no-commit` that moved the
real index (module header, DF-4-1 description). An advisory helper is the
same sentence with a longer name; the failure mode — an agent improvising a
copy under time pressure — is untouched by adding an option it may skip.

**Measured basis for mandating now rather than after a trial period:** the
helper costs one line (`$(...)` captures the path), fails only closed (11
named Refusal states; exit 2 + stderr, destination cleaned), and is pinned
by 10 committed seals plus the round-2 fixes (2542 passed / 13 skipped full
suite at DF-4-3 completion). The cost a mandate imposes is exactly the cost
the incidents already justified.

**What would change the ruling:** measured over-refusal making agents route
around the helper in practice — grok's advisory MEDIUMs name the candidate
mechanisms (git-init shape drift on a distro git; no size budget on the
copy). The remedy would be fixing the helper, not demoting the mandate; the
mandate itself would only fall if the helper's guarantee were shown false
(a clone it blessed reaching the real repo), which is the one failure worse
than the incident class.

## Adjudication (DF-4-4): outside `--work-tree` into a clone is banned in the brief

The contract left this to P4 explicitly ("P4 owns whether the briefs ban
the flag outright", scratch_clone.py, Hazard A). **Decided:** banned
outright in `roles/coder.md` — `--work-tree`, `--git-dir`, or `GIT_DIR`
pointed into a scratch clone from outside it. **Decided against:** leaving
it unsaid because unenforceable — unenforceability is the reason brief text
exists at all; the helper removes the *reason* to type the command
(`swap_in`/`swap_back` are that operation as a seam) and the brief removes
the *permission*. Measured basis: from outside, the command never consults
the clone's discovery, so no property of the clone intercepts it; inside
the clone the quarantine already kills the command class loudly
(`fatal: invalid reference: HEAD`, exit 128).

## Adjudication (DF-4-4): DF-4-3 raised no dispute; the unpinned round-2 seals are ruled follow-up work

DF-4-3's summary declared **no dispute** — every panel fix was demonstrable
without new test infrastructure — and posed one observation for the
operator: the round-2 behaviors (anchored source proof, exact-shape
quarantine allowlist, landing-place symlink rule) are proven by ad-hoc
`/tmp` measurement but not pinned by committed seals. Grok's advisory
MEDIUM raised the same gap independently, with a concrete row list.

**Decided:** the seals should exist. The current 10 rows would still pass
if the allowlist, the toplevel-equality check, or the `ALLOW_MISSING`
branch were deleted — revert-silent coverage on the unit's core property.

**Decided against writing them here:** the surface is
`tests/test_scratch_clone.py`, which is DF-4-2's (seals) surface; this
row's writable set is `roles/coder.md` alone, and a ruling that a test
should change is not a test change (this file's README, the D-65 lesson).
Recorded as a recommendation to the operator for a follow-on seals row:
pin `SOURCE_UNUSABLE` for a garbage/dangling `.git` and an umbrella
subdir; one planted quarantine door each among `index`, `FETCH_HEAD`,
`logs/`, `core.hooksPath`; a relative dangling in-clone link that must
survive; a missing-dir `..` landing place that must refuse.

## Adjudication (DF-4-4): the `ALLOW_MISSING` fail-closed branch stands (grok advisory HIGH)

Grok (advisory, non-blocking) held that the landing-place rule only runs on
CPython 3.13.4+, so on 3.11/3.12 (`requires-python = ">=3.11"`) every
dangling symlink refuses and the destination is deleted — the round-1
over-refusal reborn as a per-interpreter default.

**Decided:** the branch stands as the round-2 section above records it —
without `ALLOW_MISSING` there is no loop-safe way to compute a dangling
link's landing place, and unprovable keeps the unsafe answer. The
degradation direction is refusal: loud, named, destination cleaned, never a
silent unsafe accept — and the brief's stop-and-report rule now makes that
refusal a reported finding rather than a dead end.

**Decided against** both proposed fixes, for now: bumping
`requires-python` to 3.13.4 for one branch of one module is a floor change
on the whole package and outside this row's writable set; a hand-rolled
loop-safe walk re-implements symlink resolution in a security-relevant
position, the exact open-form-check class both panel rounds spent
themselves removing.

**What would change the ruling:** a measured refusal storm on a real
3.11/3.12 agent image (dangling links are common in real worktrees). That
evidence would justify a seals+bodies row for the loop-safe walk — code
work with its own review, not a brief amendment.
