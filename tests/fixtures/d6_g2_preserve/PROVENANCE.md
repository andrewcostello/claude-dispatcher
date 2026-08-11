# PROVENANCE — the D6 acceptance fixture

These files are a VERBATIM copy of `cmd/gates/` and `cmd/iterate/` in the
**`claude-workflow`** repository at commit
`83b0b9729f03ab8092da7c3997459c7c6110db97` (branch `feat/G2-adj`), taken
2026-08-11.

`claude-workflow` is a DIFFERENT repository from this one. `git rev-parse
83b0b97` fails inside `claude-dispatcher`, so a seal cannot read this tree out
of an object store at test time and vendoring is the only route. That is also
why the two `go.mod` files are copied as `go.mod.recorded`: this directory is
then not a Go module and no `go build ./...` anywhere can pick it up. The seals
copy the tree into `tmp_path` and rename them back, because `discover_units`
reads `module_path` from the nearest enclosing `go.mod` and a fixture that
withheld it would be exercising a different function.

Their one line of content is where every `Symbol.key` in the seal file comes
from:

    cmd/gates/go.mod      module github.com/yourorg/claude-workflow/gates
    cmd/iterate/go.mod    module github.com/yourorg/claude-workflow/iterate

## Why this tree and not `cmd/classify`

D5's fixture (`d5_b1_classify`) is one dark function in one module. This one is
the same shape TWICE, in two modules that both declare `package main` and both
declare a top-level `func VerifyPreservation` with an identical signature. That
is not decoration: it is the only fixture in which a key spelled
`main.VerifyPreservation` COLLIDES, and D5's `Symbol` compares on `key` alone,
so a collision here is one symbol wearing two declarations. It is what makes
`go_symbol_key`'s module qualification checkable rather than asserted.

## Measured: occurrences of the identifier `VerifyPreservation`, per file

Counted 2026-08-11 by `git show 83b0b97:<file> | grep -c`, over every `.go`
file of the two packages at that commit. `calls` counts `VerifyPreservation(`
call expressions; `comments` counts occurrences on lines beginning `//`; the
rest are the `func` declaration lines of the seals themselves and string
literals inside `t.Errorf` messages.

    file                                    occ  calls  comments  vendored
    cmd/gates/main.go                         0      0         0  yes
    cmd/gates/main_test.go                    0      0         0  NO
    cmd/gates/preserve.go                     9      0         8  yes   (+1 decl)
    cmd/gates/preserve_seal_test.go          23      8         7  yes
    cmd/gates/preserve_seal_helpers_test.go   3      0         3  yes
    cmd/iterate/main.go                       0      0         0  yes
    cmd/iterate/main_test.go                  0      0         0  NO
    cmd/iterate/preserve.go                   9      0         8  yes   (+1 decl)
    cmd/iterate/preserve_seal_test.go        31      8        10  yes
    cmd/iterate/preserve_seal_helpers_test.go 2      0         2  yes

So: **18 non-test occurrences, of which 2 are declarations and 16 are comments,
and ZERO are call expressions.** Neither `main.go` mentions it at all.

## Measured: which seals call it, and how many times each

Two independent methods agree — a line-oriented scan that attributes each
`VerifyPreservation(` to the enclosing `func`, and the reference call-graph walk
described in the seal file's JOINT SATISFIABILITY section.

    cmd/gates/preserve_seal_test.go                                    calls
      TestSeal_G1_VerifyPreservation_ReportsEditsOutsideTheLicensedPaths   2
      TestSeal_G1_VerifyPreservation_TreatsADeletionUnderGatesAsAViolation 4
      TestSeal_G1_VerifyPreservation_RefusesWhatItCannotCheck              2
    cmd/iterate/preserve_seal_test.go
      TestSeal_G2_Licence_GatesIsLicensedForGatesAndForbiddenForIterate    1
      TestSeal_G2_VerifyPreservation_CatchesEveryArrayMalformationFromTheLicenceAlone  2
      TestSeal_G2_VerifyPreservation_DerivesTheLicenceFromTheEditListNotTheOutput      2
      TestSeal_G2_VerifyPreservation_RefusesWhatItCannotCheckOnItsOwnTerms 3

**Seven seals, sixteen calls — three in `cmd/gates` and FOUR in `cmd/iterate`.**
Every call is lexically inside the seal function's own body, some inside plain
`for` loops; none is routed through a helper, which is what the two helper files'
zero call counts establish. The scaffold's contract predicts "five seals and
nine calls" for `cmd/iterate` and that is **wrong, measured**: its own list names
four distinct functions and then adds "and the licence row", which is the first
of the four. See the DISPUTES section of `tests/test_go_reachability.py`.

## Measured: the naive scan certifies both, and this fixture is sharper than B1

Over the four vendored PRODUCTION files (`main.go` and `preserve.go` of each
module), 2026-08-11:

  * ten exported top-level funcs, five per module;
  * the naive scan — *"an exported func with no non-test mention"* — flags
    **none of the ten**. Both `VerifyPreservation` doc comments open with the
    function's own name (`// VerifyPreservation checks a produced document
    against the original at the ...`), which is Go's doc-comment convention, so
    the scan has no discriminating power on idiomatic Go at all;
  * the refined scan — mentions on non-comment, non-declaration production
    lines — scores **0 for exactly `VerifyPreservation`, in each module, and for
    nothing else.** In `d5_b1_classify` that same scan scored 0 for seven
    functions of fourteen. This fixture isolates the defect to one name per
    module.

## Why `main_test.go` is not here

Neither file mentions the subject, and dropping both changes nothing this
fixture is for. **Measured 2026-08-11** by running the reference implementation
over the tree with and without them: the seven `VerifyPreservation` findings and
the production closure's unresolved calls are identical in both runs; what
changes is only the noise — 120 seals and 178 findings become 30 and 72. The
files are recorded here rather than vendored, exactly as `d5_b1_classify` records
the six files it omits.

**P4 correction (D6 adjudication, 2026-08-11):** an earlier version of this
paragraph said "the production closure's 55 unresolved calls". The 55 was a
measurement of a walk that filed stdlib method calls as holes, which
`main.go`'s EDGE GRAMMAR says they are not. Re-measured by two independent
walks — name-level and full `go/types` — the production closure holds **106
symbols and SEVEN unresolved calls**, every one of them a call through a
function value: `cancel` (`context.CancelFunc`) twice in `cmd/gates/main.go`
(`runOne`, `runCmd`) and a `setMember` closure five times in
`cmd/iterate/preserve.go` (`ApplyRoundRecord`). The count is unchanged by
dropping `main_test.go`, which is what this paragraph claims.

## Why every other vendored file IS here

  * `main.go` supplies `func main`, the only `EntrypointKind.GO_MAIN` root in
    each module. Without it every subject abstains at `check_subject` step 2 with
    `NO_ENTRYPOINT` and the fixture proves nothing. It is also what makes
    "production mentions it zero times" a complete claim rather than a claim
    about one file.
  * `preserve.go` carries the declaration and all eight doc comments — the whole
    of the naive scan's certification.
  * `preserve_seal_test.go` carries the seals.
  * `preserve_seal_helpers_test.go` carries the helpers those seals call. It is
    NOT optional: with it absent, every helper call becomes a target the walk
    cannot name, `SubjectGap.UNNAMEABLE` outranks the real subject, and each seal
    contributes one abstention instead of a finding about
    `VerifyPreservation`. Omitting it would have made the fixture green for the
    wrong reason.
