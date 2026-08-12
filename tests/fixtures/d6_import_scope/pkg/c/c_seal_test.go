package c

import "testing"

// TestSeal_C_DarkAnswersItsOwnTagAndNothingElse is package C's seal.
//
// Deliberately the same shape as package b's seal — two direct calls to Dark
// from its own body, no test helper — so that the two findings differ in their
// import position and in nothing else.
func TestSeal_C_DarkAnswersItsOwnTagAndNothingElse(t *testing.T) {
	if !Dark(Tag) {
		t.Errorf("Dark(%q) = false, want true", Tag)
	}
	if Dark("something else") {
		t.Errorf("Dark(%q) = true, want false", "something else")
	}
}
