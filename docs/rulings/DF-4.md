# DF-4 rulings — scratch clone (recorded by the DF-4-3 bodies role)

Documentation records, per the round-2 adjudication's invitation. No gate
reads this file.

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
