// A module of its own, with no dependencies and no place in any parent
// module, so `go build .` here works from an installed wheel, from a source
// checkout, and inside a repository that is itself a Go module — the target
// repo is one (seven of them, in fact: cmd/{classify,deepseek,gates,iterate,
// recheck,repro,reviewer} each carry their own go.mod, measured by
// `git show <rev>:cmd/<name>/go.mod` on feat/G2-adj @ 83b0b97, 2026-08-11) and
// inheriting any of their go.mod files would make this helper's behaviour
// depend on the tree it is judging.
//
// stdlib only, forever: go/parser, go/ast, go/token, encoding/json.
// go_signature_fingerprint/go.mod records the rule and this module repeats it
// rather than citing it, because a rule stated in one module's go.mod does not
// bind another's: a dependency would need a module cache, and a module cache is
// a network fetch and a writable HOME on the gate path — two more ways to be
// AnalyzerFault.TOOLCHAIN_UNUSABLE in CI.
//
// WHAT THE RULE COSTS HERE, and it costs more than it cost the fingerprinter,
// so it is written down rather than inherited. The correct tool for a call
// graph is golang.org/x/tools/go/ssa with callgraph/rta, which does real type
// resolution and would answer interface dispatch properly. It is refused on
// the reasoning above, and the price is paid in exactly two places, both of
// which the Python side already has vocabulary for: a call through an
// interface and a call through a function value are resolved BY NAME over the
// set of in-tree candidates (EdgeKind.INTERFACE, EdgeKind.REFERENCE), which
// over-approximates toward REACHED and is marked PathQuality.OVER_APPROXIMATED
// so it can never be spelled like a resolved path. See the EDGE GRAMMAR in
// main.go.
module claude-dispatcher/go-call-reachability

go 1.21
