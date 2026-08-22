# PROVENANCE — the D5 canonical fixture

These files are a VERBATIM copy of `cmd/classify/` in the `claude-workflow`
repository at commit `929d362014ff96042e7373420941409dc987200e` (`wt-b1-baseline`), taken 2026-08-10.
They are the B1 tree in which `ResolveConfigDual` was implemented, sealed
green, and called from no production path.

Nothing here is edited. `go.mod` is copied as `go.mod.recorded` so this
directory is not a Go module and no `go build ./...` anywhere can pick it up;
its one line of content is `module github.com/yourorg/claude-workflow/classify`,
which is where the `Symbol.key` spellings in the seal file come from.

## Measured: occurrences of the identifier `ResolveConfigDual`, per file

Counted by `grep -o` over every `.go` file in the directory at that commit.
The `vendored` column says whether the file is copied here.

    file                          occ  test   vendored
    baseline_seal_test.go           0  yes    no
    capability.go                   0  no     yes
    capability_seal_test.go         0  yes    no
    contract.go                     2  no     yes
    contract_seal_test.go          11  yes    yes
    init.go                         0  no     yes
    main.go                         0  no     yes
    main_test.go                    0  yes    no
    readset.go                      0  no     yes
    readset_seal_test.go            0  yes    no
    repair_seal_test.go            20  yes    no
    seal_helpers_test.go            0  yes    no

## Measured: the two production occurrences, and why they are the whole point

`contract.go:712` opens the function's own doc comment with its own name;
`contract.go:742` is the declaration. There is no third. So:

  * the naive scan — *"an exported func with no non-test mention"* — reports
    `ResolveConfigDual` CLEAN. Measured here, it reports **all fourteen**
    exported functions in the production set clean, because Go's doc-comment
    convention starts a comment with the name of the thing it documents. On
    idiomatic Go that scan has no discriminating power at all;
  * the refined scan — mentions on non-comment, non-declaration production
    lines — scores `ResolveConfigDual` **0**, alongside `DesugarConfigScaffold`,
    `EmitterCovers`, `GenerateReadSet`, `ProjectPanelToV1`,
    `SemanticEquivalentV1` and `SidecarSurvives`. It scores `V2SidecarPath` 3,
    and a grep cannot say whether any of those three lines runs.

## Measured: the production path that does the subject's job instead

    main               main.go:180
      resolveConfigPath  main.go:297
        findConfig         main.go:439
          configCandidates   main.go:401   ← takes the FIRST candidate that exists

So two differing `risk-paths.json` tables resolve silently to `.agent`, and the
§3.3 rule nobody disputes is enforced nowhere.

## Why the whole directory is not here

Only the six files above are needed to make both sides of the count live: the
five production files (so "zero non-test mentions outside contract.go's two" is
a complete claim over the production set) and the test file that carries the
subject's own seals. The other six files at that commit are in the table above;
only `repair_seal_test.go` mentions the subject at all, and its 20 occurrences
are recorded rather than vendored.
