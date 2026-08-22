// A module of its own, with no dependencies and no place in any parent module,
// so `go run .` here works from an installed wheel, from a source checkout, and
// inside a repository that is itself a Go module — the target repo is one, and
// inheriting its go.mod would make this helper's behaviour depend on the tree it
// is judging. Same argument as go_signature_fingerprint and
// go_call_reachability, and it is load-bearing for the same reason.
//
// stdlib only, forever: go/parser, go/ast, go/token, encoding/json, strconv.
// A dependency needs a module cache, and a module cache is a network fetch and a
// writable HOME on the gate path.
module claude-dispatcher/go-state-machine

go 1.21
