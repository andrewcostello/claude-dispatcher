// Package c is package C of this fixture: it imports nothing in this tree and
// nothing in this tree imports it.
//
// It is package b's CONTROL, and it is deliberately the same shape in every
// respect that could move a verdict — one exported dark function, one seal that
// calls it directly twice, one constant, one stdlib import in the test file,
// zero production callers. The only difference between the two packages is
// whether cmd/app's import block names them, so a difference in their verdicts
// can be caused by that and by nothing else.
package c

// Tag is this package's own name for itself. Nothing outside this package reads
// it; it exists so that b and c differ in no way that a reader could mistake
// for the reason their verdicts differ.
const Tag = "importscope/c"

// Dark reports whether name is this package's own tag.
//
// Dark is called by TestSeal_C_DarkAnswersItsOwnTagAndNothingElse and by
// nothing in production — the same B1 shape as package b's Dark.
func Dark(name string) bool {
	return name == Tag
}
