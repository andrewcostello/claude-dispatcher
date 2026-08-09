// A module of its own, with no dependencies and no place in any parent
// module, so `go run .` here works from an installed wheel, from a source
// checkout, and inside a repository that is itself a Go module — the target
// repo is one, and inheriting its go.mod would make this helper's behaviour
// depend on the tree it is judging.
//
// stdlib only, forever: go/parser, go/ast, go/printer, go/token, encoding/json.
// A dependency would need a module cache, and a module cache is a network
// fetch and a writable HOME on the gate path — two more ways to be
// ComparatorFault.TOOLCHAIN_UNUSABLE in CI.
module claude-dispatcher/go-signature-fingerprint

go 1.21
