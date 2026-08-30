// Command artifacts judges every tracked binary in the repository against the
// source it claims to be built from. Contract: features/dogfood-go/GO-2/CONTRACT.md
// in claude-dispatcher (the GO-2 unit).
//
// This module has NO tracked binary of its own. Run it with `go run . check`.
package main

import (
	"fmt"
	"os"
)

// Kind is why a binary is tracked at all. There is no third kind: a tracked
// ELF that is neither is UNDECLARED, and UNDECLARED is red.
type Kind string

const (
	// KindDistributed binaries are invoked by path by consumers (role files,
	// cmd/iterate's defaults). They must track their module's source at HEAD.
	KindDistributed Kind = "distributed"
	// KindPinned binaries are frozen references (a differential baseline). They
	// must equal their pin byte-for-byte and must NOT track HEAD; their age is
	// never a defect. Rebuilding one is an operator decision, not a body's.
	KindPinned Kind = "pinned"
)

// Pin says who froze a pinned binary and why. Required iff Kind == KindPinned;
// its presence on a distributed stamp is a malformed stamp, not a hint.
type Pin struct {
	By     string `json:"by"`     // commit or decision id that froze it
	Reason string `json:"reason"` // what consumes it as a reference
}

// Stamp is the sidecar `<binary>.stamp`, tracked next to the binary. It holds
// everything a reader needs to tell stale from current without running
// `go version -m`. It is WRITTEN from the binary's own buildinfo (WriteStamp),
// never by hand, and the SHA256 binds it to the exact bytes it describes.
type Stamp struct {
	Kind     Kind   `json:"kind"`
	Module   string `json:"module"`   // buildinfo main module path
	Revision string `json:"revision"` // vcs.revision, full 40 hex
	Time     string `json:"time"`     // vcs.time, RFC 3339
	Modified bool   `json:"modified"` // vcs.modified: built from an uncommitted tree
	Go       string `json:"go"`       // toolchain that built it
	SHA256   string `json:"sha256"`   // of the binary the stamp describes
	Pin      *Pin   `json:"pin"`      // nil unless Kind == KindPinned; see ReadStamp
}

// State is the one verdict an artifact gets. Precedence when several apply is
// the declaration order below: the first listed state that holds wins, and
// Finding.StaleSince is populated whenever it is computable regardless.
type State string

const (
	Undeclared State = "UNDECLARED"  // tracked ELF with no stamp: an accident until declared
	Orphaned   State = "ORPHANED"    // a stamp whose binary is missing or not an ELF
	Unstamped  State = "UNSTAMPED"   // no readable Go buildinfo or no vcs.* keys: cannot be judged, never green
	Malformed  State = "MALFORMED"   // stamp does not parse or violates the Kind/Pin rule
	StampDrift State = "STAMP_DRIFT" // distributed; bytes != stamp.SHA256: rebuilt without restamping
	PinBroken  State = "PIN_BROKEN"  // pinned; bytes != stamp.SHA256: someone rebuilt the fixture
	Duplicate  State = "DUPLICATE"   // same bytes, or same Module, as another tracked binary
	Foreign    State = "FOREIGN"     // Revision is not in HEAD's history: staleness is not computable
	Stale      State = "STALE"       // distributed; module source changed after Revision
	Dirty      State = "DIRTY"       // distributed; Modified: unreproducible whatever its age
	Pinned     State = "PINNED"      // pinned; bytes == pin. Green.
	Current    State = "CURRENT"     // distributed; clean and no source commit after Revision. Green.
)

// Green is the closed set of states that pass. Everything else is red.
func Green(s State) bool { return s == Pinned || s == Current }

// Commit is one source-touching commit an artifact lacks.
type Commit struct {
	SHA     string
	Date    string // YYYY-MM-DD
	Subject string
}

// Finding is the verdict for one artifact (or one orphaned stamp).
type Finding struct {
	Path       string   // repo-relative path of the binary (or the stamp, for Orphaned)
	State      State    //
	Stamp      *Stamp   // nil for Undeclared / Malformed / Orphaned-without-parse
	StaleSince []Commit // oldest first; populated whenever computable, for any State
	Detail     string   // the specific reason, e.g. the sibling path for Duplicate
}

// Report is one whole-repository judgement.
type Report struct {
	Findings []Finding
}

// Red returns the findings that are not Green, in tree order.
func (r Report) Red() []Finding {
	var red []Finding
	for _, f := range r.Findings {
		if !Green(f.State) {
			red = append(red, f)
		}
	}
	return red
}

// Exit codes follow the repository convention (README "Exit codes" column).
const (
	exitGreen   = 0 // every tracked binary is Pinned or Current
	exitRed     = 1 // at least one finding is red
	exitCannot  = 3 // the checker could not judge: git or buildinfo unavailable. NEVER 0.
	exitInvalid = 3
)

func hole(name string) string {
	return "GO-2 hole: " + name + " is a scaffold stub; GO-2-3 fills it"
}

// TrackedELF derives the artifact set from the tree: `git ls-files -z` filtered
// by the 4-byte ELF magic. It is never a hand list. An error is an error — an
// empty set on failure would certify nothing.
func TrackedELF(repo string) ([]string, error) {
	panic(hole("TrackedELF"))
}

// ReadBuildInfo reads the binary's embedded buildinfo (debug/buildinfo; no `go`
// tool needed) into a Stamp with Kind, Pin and SHA256 unset. Missing buildinfo
// or missing vcs.* keys is an error, never an empty Stamp.
func ReadBuildInfo(path string) (Stamp, error) {
	panic(hole("ReadBuildInfo"))
}

// StampPath is the sidecar's location: the binary's own path plus ".stamp".
func StampPath(binary string) string { return binary + ".stamp" }

// ReadStamp parses and validates a sidecar. Rules: Kind ∈ {distributed, pinned};
// Pin != nil iff Kind == pinned; Revision is 40 hex; SHA256 is 64 hex.
// A violation is an error the caller maps to Malformed.
func ReadStamp(path string) (Stamp, error) {
	panic(hole("ReadStamp"))
}

// WriteStamp is the `stamp` subcommand: ReadBuildInfo + sha256 of the file,
// plus the declared Kind and Pin. The only way a stamp comes to exist.
func WriteStamp(binary string, kind Kind, pin *Pin) error {
	panic(hole("WriteStamp"))
}

// SourceCommitsAfter lists commits in revision..HEAD that touch moduleDir,
// excluding tracked binaries and stamps (a rebuild commit is not a source
// change). ErrForeign when revision is not an ancestor of HEAD.
func SourceCommitsAfter(repo, moduleDir, revision string) ([]Commit, error) {
	panic(hole("SourceCommitsAfter"))
}

// Judge is the state machine for one tracked binary. `all` is every other
// tracked binary's (path, sha256, module) so Duplicate can be decided.
func Judge(repo, path string, all []Finding) Finding {
	panic(hole("Judge"))
}

// Check judges every tracked ELF and every stamp in the repository. The error
// return is reserved for "could not judge" (exitCannot); a red report is not
// an error.
func Check(repo string) (Report, error) {
	panic(hole("Check"))
}

func main() {
	if len(os.Args) < 2 {
		fmt.Fprintln(os.Stderr, "usage: artifacts check [-repo DIR] | stamp -kind distributed|pinned [-pin-by ID -pin-reason TEXT] BINARY")
		os.Exit(exitInvalid)
	}
	panic(hole("main"))
}
