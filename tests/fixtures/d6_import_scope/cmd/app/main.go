// Package main is package A of this fixture: the package that IMPORTS, that
// declares this tree's only production entrypoint, and that holds this tree's
// only unresolved call.
//
// It imports pkg/b and it does NOT import pkg/c. That single asymmetry is the
// whole fixture: a hole here is in scope for a subject in pkg/b and out of
// scope for a subject in pkg/c, and the two subjects are otherwise identical.
package main

import (
	"context"
	"fmt"
	"time"

	"example.com/importscope/pkg/b"
)

func main() {
	run()
}

// run holds this tree's only hole, and the hole is deliberate.
//
// `cancel` is a context.CancelFunc — a VALUE of function type, bound by a TUPLE
// assignment from context.WithTimeout. The Go helper's SOLE-BINDING FUNC
// LITERAL rule declines a tuple binding by name ("no literal is named — which
// is where `ctx, cancel := context.WithTimeout` lands"), so the deferred call
// through it cannot be named and is reported as unresolved. This is one of the
// two hole shapes measured on the acceptance tree, not a shape invented here.
//
// b is used for its CONSTANT and never for a function. See PROVENANCE.md: a
// call into pkg/b would give the import relation a second, independent source
// — the analyzer unions its own cross-package call edges into `imports` — and
// an analyzer that stopped reading import blocks would still answer pkg/b here.
// Measured: with a call edge in place, the mutation is invisible.
func run() {
	ctx, cancel := context.WithTimeout(context.Background(), 50*time.Millisecond)
	defer cancel()
	fmt.Println(b.Version, ctx.Err())
}
