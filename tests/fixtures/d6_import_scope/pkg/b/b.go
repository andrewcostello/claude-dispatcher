// Package b is package B of this fixture: the package cmd/app IMPORTS.
//
// Its Dark is reached from its own seal and from no production root, exactly as
// VerifyPreservation is on the acceptance tree. What makes it different from
// package c's Dark is one fact and one fact only: cmd/app's import block names
// this package, so a hole in cmd/app COULD be Dark's missing call site and the
// mechanism must abstain rather than breach.
package b

// Version is what cmd/app imports this package for.
//
// A constant and not a function, deliberately: a call would emit a
// cross-package EDGE, the analyzer unions those edges into the import relation,
// and the relation would then be derivable without reading a single import
// block. See cmd/app/main.go's run and PROVENANCE.md.
const Version = "importscope/b"

// Dark reports whether name is this package's own version string.
//
// Dark is called by TestSeal_B_DarkAnswersItsOwnVersionAndNothingElse and by
// nothing in production. That is the B1 shape: the seal proves it behaves and
// nothing proves it runs.
func Dark(name string) bool {
	return name == Version
}
