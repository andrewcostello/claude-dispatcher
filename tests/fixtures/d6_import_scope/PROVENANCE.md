# PROVENANCE — the D6 IMPORT-SCOPE fixture

**Written for this branch, 2026-08-11, on `feat/D6-import-fixture`, base
`444b1fb`.** Unlike `d6_g2_preserve` and `d5_b1_classify`, this tree is **NOT a
copy of anything**: no upstream commit exists to cite. It was authored here, by
hand, to close the one gap DISPUTE I2 in `go_reachability.py`'s
`_package_imports` ruled a blocker on enrolling the Go row.

## Why it had to be authored rather than borrowed

The P4 ruling records the measurement: **both D6 acceptance packages have ZERO
in-tree imports**, so `_package_imports` already returns `imports=frozenset()`
for both, and an analyzer that never read an import block emits a
byte-identical relation to the correct one. A seal cannot separate two
functions that return the same value. Two other routes were weighed and both
were rejected in that ruling, for reasons re-checked here and unchanged:

  * **D5's `_REACH_EDGES` is a TRANSCRIBED relation.** It exercises the
    consumer (`import_components`, `holes_in_scope`), never the derivation. The
    gap is whether the Go row reads import blocks at all;
  * **the live `evenplay-mono/apps/website-public-api` tree declares
    `go 1.25.0`** and this machine's toolchain is go1.24.4, so
    `_go_environment`'s `GOTOOLCHAIN=local` correctly refuses it: 13 unreadable
    files and `ImportsUnavailable`. A seal may not depend on the machine's
    toolchain. **This fixture declares `go 1.21`** so that it is readable by
    every toolchain from 1.21 up, which is the point of the number.

## How a reader reproduces it

There is nothing to fetch. The six files below ARE the artifact, and the whole
of it is legal, `gofmt`-clean, `go vet`-clean Go:

    cd tests/fixtures/d6_import_scope
    cp -a . /tmp/importscope && cd /tmp/importscope
    mv go.mod.recorded go.mod
    gofmt -l .        # measured 2026-08-11: no output
    go vet ./...      # measured 2026-08-11: exit 0, no output
    go test ./...     # measured 2026-08-11: cmd/app [no test files], pkg/b ok, pkg/c ok

`go.mod` is recorded as **`go.mod.recorded`** for the same reason
`d6_g2_preserve` records its two: this directory is then not a Go module and no
`go build ./...` anywhere in `claude-dispatcher` can pick the vendored tree up.
The seals copy the tree into `tmp_path` and rename it back, because
`discover_units` reads `module_path` from the nearest enclosing `go.mod` and a
fixture that withheld it would be exercising a different function.

Its one line of content is where every `Symbol.key` in the seals comes from:

    go.mod    module example.com/importscope

## The shape, and the one asymmetry the whole fixture is

The P4 specified the minimum: *one module, at least three packages, `A` imports
`B`, `C` imports neither, and a hole in `A`.* This is that, and the file names
say which is which:

    cmd/app/main.go        A — package main. Imports pkg/b. Holds the hole.
    pkg/b/b.go             B — imported by A. Declares the dark Dark.
    pkg/b/b_seal_test.go   B's seal. Calls Dark directly, twice.
    pkg/c/c.go             C — imported by nothing, imports nothing in tree.
    pkg/c/c_seal_test.go   C's seal. Calls Dark directly, twice.

`pkg/b` and `pkg/c` are deliberately the SAME SHAPE in every respect that could
move a verdict — one exported dark function, one constant, one seal calling it
directly twice from its own body, no test helper, no production caller, one
stdlib import in the test file. **The only difference between them is that
`cmd/app`'s import block names `pkg/b` and does not name `pkg/c`.** That is what
makes `pkg/c` an in-test control judged in the same call rather than a second
assertion.

## What the shape did NOT state, and what had to be added

Four additions. Each is load-bearing and each is measured, not assumed.

1. **A PRODUCTION ENTRYPOINT.** `check_subject` step 2 abstains with
   `NO_ENTRYPOINT` on a tree with no production root, *before* step 3 is ever
   reached, so a three-package tree with no `func main` proves nothing about
   scoping. `A` is `package main` and carries it. Measured: `discover_roots`
   answers one `EntrypointKind.GO_MAIN` root, `cmd/app.main`.

2. **`A`'s USE OF `B` IS A CONSTANT, NEVER A CALL — and this is the sharpest
   thing in the fixture.** Go refuses an unused import, so `A` must use `B`
   somehow. `_package_imports` unions the analyzer's own cross-package CALL
   EDGES into `imports` ("AN EDGE THIS TREE HOLDS IS ALSO EVIDENCE THAT ONE
   PACKAGE CAN NAME ANOTHER"). If `A` CALLED into `B`, the `A -> B` relation
   edge would have a second, independent source and an analyzer that stopped
   reading import blocks would still answer it.

   **Measured 2026-08-11 under `feat/D6-import-fixture`, base `444b1fb`**, by
   driving the real `check_tree` over this tree and over a variant identical
   except that `run` calls a `b.Announce()` instead of reading `b.Version`:

       mutation                                 this fixture     call-edge variant
       none (HEAD)                              B ABSTAIN        B ABSTAIN
       `imports=frozenset()` (the FAIL-OPEN)    B **BREACH**     B **BREACH**
       import blocks never read, `named` only   B **BREACH**     B ABSTAIN  <- INVISIBLE

   So the constant is what makes the narrower fail-open — *the analyzer stops
   reading import blocks* — visible at all. The variant's `external_import_count`
   does move under that mutation (3 -> 0), and no verdict moves with it, which
   is the P4's ruling that the count "is a REPORT, not a guard" as an executable
   fact.

3. **A SEAL-DERIVED SUBJECT IN EACH OF `B` AND `C`.** `discover_seals` derives
   subjects from what a seal's own body CALLS; a function nobody sealed yields
   no finding at all and the fixture would be green by having nothing to judge.
   Each seal calls its package's `Dark` directly, twice, and calls no helper —
   so `subjects_of_seal` returns one subject and never `SubjectGap.UNNAMEABLE`
   or `SubjectGap.ALL_TARGETS_IN_TESTS`.

4. **`C` MUST BE UNREACHABLE FROM PRODUCTION.** Step 1 answers `FROM_PRODUCTION`
   before any abstention is considered, so a `C.Dark` that production called
   would never reach step 3 and would breach for the wrong reason. Measured:
   the production closure is exactly `{cmd/app.main, cmd/app.run}` — two
   symbols, neither in `pkg/b` nor in `pkg/c`.

## The hole, and why it is a genuine one

`cmd/app/main.go`'s `run` binds `ctx, cancel := context.WithTimeout(...)` and
`defer cancel()`. `cancel` is a `context.CancelFunc` — a value of function type
— and the binding is a TUPLE binding, which the Go helper's SOLE-BINDING FUNC
LITERAL rule declines by name: *"A TUPLE binding fails: the value comes from one
multi-valued expression and no literal is named — which is where
`ctx, cancel := context.WithTimeout` lands, so the two `cancel` sites never even
reach the provenance question."*

This is one of the two hole shapes **measured on the acceptance tree** (the
other being a closure), not a shape invented for this fixture. Production
reaches this input on any Go tree that uses `context.WithTimeout` and defers its
cancel, which is idiomatic Go and is what `cmd/gates/main.go` does twice.

## Measured, over the vendored tree as it stands

**Under `feat/D6-import-fixture`, base `444b1fb`, 2026-08-11**, by driving the
real `build_call_graph` / `discover_roots` / `reachable_from` / `check_tree`
with `GO_REACHABILITY_ANALYZER` in `ANALYZERS`:

    units / packages                       3
    symbols                                6
    unreadable files                       0
    edges                                  5   (1 production, 4 seal->Dark)
    cross-package edges                    0   <- see addition 2
    unresolved calls, tree-wide            1
    unresolved calls, in the closure       1   == report.unresolved_call_count
      at                                   cmd/app/main.go:38, "call through the
                                           func-typed variable \"cancel\""
    production roots                       1   cmd/app.main, GO_MAIN
    test roots (seals)                     2
    production closure                     2   {cmd/app.main, cmd/app.run}
    findings                               2   one per seal, one subject each

    relation                               ImportRelation (not ImportsUnavailable)
      cmd/app   imports {pkg/b}   unplaced ()   external 3   (context, fmt, time)
      pkg/b     imports {}        unplaced ()   external 1   (testing)
      pkg/c     imports {}        unplaced ()   external 1   (testing)

    import_components
      {cmd/app, pkg/b}   and   {pkg/c}

    verdicts
      pkg/b.Dark   UNDECIDED / DYNAMIC_EDGE / NOT_APPLICABLE  -> ABSTAIN
      pkg/c.Dark   FROM_TESTS_ONLY / NOT_APPLICABLE / reason None -> BREACH

Import-block LINE counts, by the same crude sweep
`test_the_acceptance_trees_import_counts_are_the_measured_ones` uses (every
`.go` file of the package, test files included):

    cmd/app   4 lines, 1 of them in-tree
    pkg/b     1 line,  0 in-tree
    pkg/c     1 line,  0 in-tree

**One in-tree import line in the whole tree. That is the fixture.** The
acceptance tree has 41 + 39 import lines and ZERO in-tree, which is why it
cannot do this job and this one can.

## The four mutations this fixture separates

**Measured 2026-08-11 under `feat/D6-import-fixture`, base `444b1fb`**, each
mutation applied alone to `_package_imports` in a copy of `src/`, verdicts read
off the real `check_tree`:

    mutation                                          pkg/b.Dark   pkg/c.Dark
    none (HEAD)                                       ABSTAIN      BREACH
    every package's `imports` emptied — THE FAIL-OPEN **BREACH**   BREACH
    import blocks never read, call edges only         **BREACH**   BREACH
    reverted to ImportsUnavailable                    ABSTAIN      **ABSTAIN**
    every package's `unplaced_imports` non-empty
      (one component, the whole-tree behaviour)       ABSTAIN      **ABSTAIN**

Every one of the four moves a verdict here. On the acceptance tree the first two
move nothing at all — that is DISPUTE I2, and this table is its closure.

At the level of the whole suite, same revision, same clones (the `.git` FILE
removed, so the same 7 floor/provenance rows ERROR in every run and are constant
across all of them; "before" is the same clone with Part 12's rows and this
fixture removed):

    clone baseline                                 2425 / 13 / 7   2429 / 13 / 7

    mutation                                       before          after
    every package's `imports` emptied
      — THE FAIL-OPEN                              **0 FAILED**    3 failed
    import blocks never read, call edges only      **0 FAILED**    3 failed
    reverted to ImportsUnavailable                 1 failed        5 failed
    every package's unplaced_imports non-empty     1 failed        3 failed
    out-of-tree imports uncounted                  (not measured)  2 failed
    in-tree imports counted as external too        (not measured)  1 failed
    this fixture edited so cmd/app CALLS pkg/b     n/a             1 failed

**Joint satisfiability**: all four rows of Part 12 are green together against
the SHIPPED body, measured in the `cp -a` clone above — 2429 passed, 13 skipped,
0 failed, 7 expected errors. No throwaway reference implementation was needed,
because the body these rows judge already exists; the gap DISPUTE I2 named was
never that the body was wrong, it was that nothing could tell whether it was.

## Why no `main_test.go`, no decoy, no second module

Each omission is an omission of something `d6_g2_preserve` has, and each is
deliberate:

  * **no second module.** The P4's shape says ONE module, and one is what
    isolates the variable: with two, a reader cannot tell whether the scoping
    followed the import or the module boundary, which is the exact confusion the
    acceptance tree's two-module shape already causes;
  * **no name collision, no decoy, no method receivers.** `d6_g2_preserve`
    carries those and seals them; repeating them here would make a failure
    ambiguous between this fixture's question and that one's;
  * **no `main_test.go`.** `cmd/app` has no test file at all, so `A` contributes
    no seal and no subject. Nothing here needs one, and a seal in `A` would add
    a finding whose verdict is a fact about `A`'s own package rather than about
    scoping.
