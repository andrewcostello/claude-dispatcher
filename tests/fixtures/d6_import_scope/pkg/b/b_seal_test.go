package b

import "testing"

// TestSeal_B_DarkAnswersItsOwnVersionAndNothingElse is package B's seal.
//
// It calls Dark DIRECTLY, from its own body, twice, and calls no test helper.
// That is what makes Dark a seal-derived SUBJECT: subjects_of_seal reads the
// non-test symbols a seal's own body calls, and a function nobody sealed yields
// no finding at all.
func TestSeal_B_DarkAnswersItsOwnVersionAndNothingElse(t *testing.T) {
	if !Dark(Version) {
		t.Errorf("Dark(%q) = false, want true", Version)
	}
	if Dark("something else") {
		t.Errorf("Dark(%q) = true, want false", "something else")
	}
}
