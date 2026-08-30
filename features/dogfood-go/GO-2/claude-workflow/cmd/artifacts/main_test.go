// Seals for the GO-2 contract (features/dogfood-go/GO-2/CONTRACT.md in
// claude-dispatcher). Three layers:
//
//  1. Synthetic fixtures: a temp git repo with a real `go build`, so every
//     state in §3 is reached by an actual binary disagreeing with its actual
//     source, never by a hand-written stamp standing in for one.
//  2. The real tree: relationships that must hold at ANY HEAD — every tracked
//     ELF is stamped, lives in the module it was built from, is unique by
//     bytes and by module, and the verdict agrees with git.
//  3. The worked oracle at docs/explicit-state @ 1db2d41 (§5), replayed in a
//     throwaway clone.
//
// Nothing here skips. A seal that cannot look fails; the tree it needs is the
// repository this module lives in (override with ARTIFACTS_REPO). The oracle
// needs full history: a shallow CI checkout must use fetch-depth: 0, and so
// must the checker itself (`git log rev..HEAD` is meaningless without it).
package main

import (
	"bytes"
	"crypto/sha256"
	"debug/buildinfo"
	"encoding/hex"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"runtime"
	"sort"
	"strings"
	"testing"
	"time"
)

// ---------------------------------------------------------------- fixtures

// fixture is a temp git repository with one or more single-file Go modules
// under cmd/, mirroring the target tree's one-module-per-tool layout.
type fixture struct {
	t     *testing.T
	repo  string
	clock int // commit timestamps are deterministic and strictly increasing
}

func newFixture(t *testing.T) *fixture {
	t.Helper()
	f := &fixture{t: t, repo: t.TempDir()}
	f.git("init", "-q", "-b", "main")
	f.git("config", "user.name", "seal")
	f.git("config", "user.email", "seal@example.invalid")
	f.git("config", "commit.gpgsign", "false")
	return f
}

func (f *fixture) env() []string {
	return append(os.Environ(),
		"GIT_CONFIG_GLOBAL=/dev/null", "GIT_CONFIG_NOSYSTEM=1",
		"GIT_AUTHOR_NAME=seal", "GIT_AUTHOR_EMAIL=seal@example.invalid",
		"GIT_COMMITTER_NAME=seal", "GIT_COMMITTER_EMAIL=seal@example.invalid",
		"GOFLAGS=", "GOWORK=off", "GOTOOLCHAIN=local",
	)
}

func (f *fixture) run(dir string, extraEnv []string, name string, args ...string) string {
	f.t.Helper()
	cmd := exec.Command(name, args...)
	cmd.Dir = dir
	cmd.Env = append(f.env(), extraEnv...)
	out, err := cmd.CombinedOutput()
	if err != nil {
		f.t.Fatalf("%s %s (in %s): %v\n%s", name, strings.Join(args, " "), dir, err, out)
	}
	return strings.TrimSpace(string(out))
}

func (f *fixture) git(args ...string) string { return f.run(f.repo, nil, "git", args...) }

// commit stages everything and commits with a deterministic, increasing date.
// Returns the full SHA.
func (f *fixture) commit(msg string) string {
	f.t.Helper()
	f.clock++
	date := fmt.Sprintf("2026-01-01T00:00:%02dZ", f.clock)
	f.git("add", "-A")
	f.run(f.repo, []string{"GIT_AUTHOR_DATE=" + date, "GIT_COMMITTER_DATE=" + date},
		"git", "commit", "-q", "--allow-empty", "-m", msg)
	return f.git("rev-parse", "HEAD")
}

func (f *fixture) head() string { return f.git("rev-parse", "HEAD") }

func (f *fixture) write(rel, content string) {
	f.t.Helper()
	p := filepath.Join(f.repo, rel)
	if err := os.MkdirAll(filepath.Dir(p), 0o755); err != nil {
		f.t.Fatal(err)
	}
	if err := os.WriteFile(p, []byte(content), 0o644); err != nil {
		f.t.Fatal(err)
	}
}

// module lays down cmd/<name>/{go.mod,main.go}. version is what main prints;
// changing it is the "source changed" event every scenario turns on.
func (f *fixture) module(name, version string) {
	f.t.Helper()
	f.write("cmd/"+name+"/go.mod", "module example.invalid/tools/"+name+"\n\ngo 1.21\n")
	f.source(name, version)
}

func (f *fixture) source(name, version string) {
	f.t.Helper()
	f.write("cmd/"+name+"/main.go", "package main\n\nimport \"fmt\"\n\nfunc main() { fmt.Println(\""+version+"\") }\n")
}

// build compiles cmd/<name> to cmd/<name>/<out>. vcs=false is the
// `-buildvcs=false` artifact the checker must refuse to judge.
func (f *fixture) build(name, out string, vcs bool) string {
	f.t.Helper()
	dir := filepath.Join(f.repo, "cmd", name)
	flag := "-buildvcs=true"
	if !vcs {
		flag = "-buildvcs=false"
	}
	f.run(dir, nil, "go", "build", flag, "-o", out, ".")
	return "cmd/" + name + "/" + out
}

func (f *fixture) stamp(rel string, kind Kind, pin *Pin) {
	f.t.Helper()
	if err := WriteStamp(filepath.Join(f.repo, rel), kind, pin); err != nil {
		f.t.Fatalf("WriteStamp(%s): %v", rel, err)
	}
}

func (f *fixture) check() Report {
	f.t.Helper()
	r, err := Check(f.repo)
	if err != nil {
		f.t.Fatalf("Check(%s): %v", f.repo, err)
	}
	return r
}

// finding returns the one Finding for rel, failing if it is absent or doubled.
func (f *fixture) finding(rel string) Finding {
	f.t.Helper()
	return findingFor(f.t, f.check(), rel)
}

func findingFor(t *testing.T, r Report, rel string) Finding {
	t.Helper()
	var hits []Finding
	for _, x := range r.Findings {
		if x.Path == rel {
			hits = append(hits, x)
		}
	}
	if len(hits) != 1 {
		t.Fatalf("want exactly one finding for %s, got %d in %v", rel, len(hits), paths(r))
	}
	return hits[0]
}

func paths(r Report) []string {
	var ps []string
	for _, f := range r.Findings {
		ps = append(ps, f.Path+"="+string(f.State))
	}
	return ps
}

func shas(cs []Commit) []string {
	var out []string
	for _, c := range cs {
		out = append(out, c.SHA)
	}
	return out
}

func sealSHA(t *testing.T, path string) string {
	t.Helper()
	b, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	s := sha256.Sum256(b)
	return hex.EncodeToString(s[:])
}

func wantState(t *testing.T, f Finding, s State) {
	t.Helper()
	if f.State != s {
		t.Fatalf("%s: want %s, got %s (detail %q, stale-since %v)", f.Path, s, f.State, f.Detail, shas(f.StaleSince))
	}
}

func wantStaleSince(t *testing.T, f Finding, want ...string) {
	t.Helper()
	got := shas(f.StaleSince)
	if strings.Join(got, ",") != strings.Join(want, ",") {
		t.Fatalf("%s: StaleSince want %v (oldest first), got %v", f.Path, want, got)
	}
}

// ------------------------------------------------- the set is derived, not listed

// The artifact set follows the index and the bytes: an untracked ELF is
// nothing, a tracked non-ELF is nothing, and `git add` alone grows the set. No
// literal anywhere can reproduce that.
func TestTrackedELF_FollowsTheIndexNotAList(t *testing.T) {
	t.Parallel()
	f := newFixture(t)
	f.module("tool", "v1")
	f.commit("source")
	tracked := f.build("tool", "tool", true)
	f.write("cmd/tool/notes", "not an executable\n")
	f.write("cmd/tool/short", "\x7fEL") // shorter than the magic: must not panic
	f.commit("track one binary")
	f.build("tool", "scratch", true) // built, never added

	got, err := TrackedELF(f.repo)
	if err != nil {
		t.Fatal(err)
	}
	if strings.Join(got, ",") != tracked {
		t.Fatalf("TrackedELF: want [%s], got %v", tracked, got)
	}

	f.git("add", "cmd/tool/scratch")
	got, err = TrackedELF(f.repo)
	if err != nil {
		t.Fatal(err)
	}
	sort.Strings(got)
	if strings.Join(got, ",") != "cmd/tool/scratch,cmd/tool/tool" {
		t.Fatalf("after git add, TrackedELF should grow with the index: got %v", got)
	}
}

func TestTrackedELF_OutsideARepositoryIsAnError(t *testing.T) {
	t.Parallel()
	dir := t.TempDir()
	if _, err := TrackedELF(dir); err == nil {
		t.Fatal("TrackedELF on a non-repository returned no error: an empty set here would certify nothing")
	}
	if _, err := Check(dir); err == nil {
		t.Fatal("Check on a non-repository returned no error")
	}
}

// ------------------------------------------------------------ the stamp

// WriteStamp is the only producer: every field comes from the binary's own
// buildinfo or its bytes, and the sidecar is readable on its own.
func TestWriteStamp_CopiesBuildinfoAndBindsBytes(t *testing.T) {
	t.Parallel()
	f := newFixture(t)
	f.module("tool", "v1")
	rev := f.commit("source")
	rel := f.build("tool", "tool", true)
	abs := filepath.Join(f.repo, rel)

	if StampPath(abs) != abs+".stamp" {
		t.Fatalf("StampPath: got %s", StampPath(abs))
	}
	f.stamp(rel, KindDistributed, nil)

	raw, err := os.ReadFile(abs + ".stamp")
	if err != nil {
		t.Fatalf("stamp not written beside the binary: %v", err)
	}
	var keys map[string]json.RawMessage
	if err := json.Unmarshal(raw, &keys); err != nil {
		t.Fatalf("stamp is not JSON: %v\n%s", err, raw)
	}
	for _, k := range []string{"kind", "module", "revision", "time", "modified", "go", "sha256", "pin"} {
		if _, ok := keys[k]; !ok {
			t.Errorf("stamp lacks %q: a reader cannot judge from the sidecar alone\n%s", k, raw)
		}
	}

	s, err := ReadStamp(abs + ".stamp")
	if err != nil {
		t.Fatal(err)
	}
	if s.Kind != KindDistributed || s.Pin != nil {
		t.Errorf("kind/pin: got %q %v", s.Kind, s.Pin)
	}
	if s.Module != "example.invalid/tools/tool" {
		t.Errorf("module: got %q, want the buildinfo main module", s.Module)
	}
	if s.Revision != rev {
		t.Errorf("revision: got %q, want HEAD at build %s", s.Revision, rev)
	}
	if s.Modified {
		t.Error("modified: clean build stamped as dirty")
	}
	if s.Go != runtime.Version() {
		t.Errorf("go: got %q, want %q", s.Go, runtime.Version())
	}
	if s.SHA256 != sealSHA(t, abs) {
		t.Errorf("sha256: got %q, want %q", s.SHA256, sealSHA(t, abs))
	}
	when, err := time.Parse(time.RFC3339, s.Time)
	if err != nil {
		t.Fatalf("time %q is not RFC 3339: %v", s.Time, err)
	}
	commitTime, err := time.Parse(time.RFC3339, f.git("log", "-1", "--format=%cI"))
	if err != nil {
		t.Fatal(err)
	}
	if !when.Equal(commitTime) {
		t.Errorf("time: got %s, want the commit time %s", when, commitTime)
	}

	// The binary's own buildinfo must agree with what was stamped — the
	// checker verifies the sidecar was not edited by hand.
	bi, err := ReadBuildInfo(abs)
	if err != nil {
		t.Fatal(err)
	}
	if bi.Module != s.Module || bi.Revision != s.Revision || bi.Time != s.Time || bi.Modified != s.Modified || bi.Go != s.Go {
		t.Errorf("ReadBuildInfo disagrees with the stamp it produced:\n%+v\n%+v", bi, s)
	}
}

func TestWriteStamp_RefusesWhatItCannotDescribe(t *testing.T) {
	t.Parallel()
	f := newFixture(t)
	f.module("tool", "v1")
	f.commit("source")
	withVCS := filepath.Join(f.repo, f.build("tool", "tool", true))
	noVCS := filepath.Join(f.repo, f.build("tool", "novcs", false))

	cases := []struct {
		name string
		bin  string
		kind Kind
		pin  *Pin
	}{
		{"pinned without a pin", withVCS, KindPinned, nil},
		{"distributed with a pin", withVCS, KindDistributed, &Pin{By: "x", Reason: "y"}},
		{"unknown kind", withVCS, Kind("cached"), nil},
		{"no vcs.* in buildinfo", noVCS, KindDistributed, nil},
		{"no such file", filepath.Join(f.repo, "cmd/tool/missing"), KindDistributed, nil},
	}
	for _, c := range cases {
		if err := WriteStamp(c.bin, c.kind, c.pin); err == nil {
			t.Errorf("%s: WriteStamp succeeded; a stamp that was never checked is a hand-written one", c.name)
		}
		if _, err := os.Stat(c.bin + ".stamp"); err == nil {
			t.Errorf("%s: a stamp was left on disk after a refused write", c.name)
		}
	}
	if _, err := ReadBuildInfo(noVCS); err == nil {
		t.Error("ReadBuildInfo on a -buildvcs=false binary returned no error")
	}
}

func TestReadStamp_RejectsMalformed(t *testing.T) {
	t.Parallel()
	dir := t.TempDir()
	good := Stamp{Kind: KindDistributed, Module: "m", Revision: strings.Repeat("a", 40), Time: "2026-01-01T00:00:00Z", Go: "go1.21", SHA256: strings.Repeat("b", 64)}
	pinned := good
	pinned.Kind, pinned.Pin = KindPinned, &Pin{By: "GO-2-1", Reason: "fixture"}
	for _, ok := range []Stamp{good, pinned} {
		p := filepath.Join(dir, "ok.stamp")
		b, _ := json.Marshal(ok)
		os.WriteFile(p, b, 0o644)
		if _, err := ReadStamp(p); err != nil {
			t.Fatalf("well-formed stamp rejected: %v\n%s", err, b)
		}
	}
	mutate := func(fn func(*Stamp)) string {
		s := good
		fn(&s)
		b, _ := json.Marshal(s)
		return string(b)
	}
	bad := map[string]string{
		"not json":             "{",
		"unknown kind":         mutate(func(s *Stamp) { s.Kind = "cached" }),
		"empty kind":           mutate(func(s *Stamp) { s.Kind = "" }),
		"distributed with pin": mutate(func(s *Stamp) { s.Pin = &Pin{By: "x", Reason: "y"} }),
		"pinned without pin":   mutate(func(s *Stamp) { s.Kind = KindPinned }),
		"short revision":       mutate(func(s *Stamp) { s.Revision = "abc1234" }),
		"sha256 not 64 hex":    mutate(func(s *Stamp) { s.SHA256 = "deadbeef" }),
		"module missing":       mutate(func(s *Stamp) { s.Module = "" }),
		"revision not hex":     mutate(func(s *Stamp) { s.Revision = strings.Repeat("z", 40) }),
	}
	for name, content := range bad {
		p := filepath.Join(dir, "bad.stamp")
		os.WriteFile(p, []byte(content), 0o644)
		if _, err := ReadStamp(p); err == nil {
			t.Errorf("%s: ReadStamp accepted %s", name, content)
		}
	}
}

// ------------------------------------------------------- the state machine

// The same bytes, judged before and after a source commit: CURRENT becomes
// STALE and StaleSince names exactly the commit, not the rebuild commit and
// not a commit in another module.
func TestJudge_CurrentBecomesStaleWhenItsSourceMoves(t *testing.T) {
	t.Parallel()
	f := newFixture(t)
	f.module("tool", "v1")
	f.module("other", "v1")
	f.commit("source")
	rel := f.build("tool", "tool", true)
	f.stamp(rel, KindDistributed, nil)
	f.commit("track binary and stamp") // touches no source

	fd := f.finding(rel)
	wantState(t, fd, Current)
	wantStaleSince(t, fd)
	if fd.Stamp == nil || fd.Stamp.Modified {
		t.Fatalf("CURRENT must carry its clean stamp: %+v", fd.Stamp)
	}
	if fd.Stamp.SHA256 != sealSHA(t, filepath.Join(f.repo, rel)) {
		t.Fatal("finding's stamp does not describe the file on disk")
	}
	if !Green(fd.State) || len(f.check().Red()) != 0 {
		t.Fatalf("a current binary is green; red = %v", paths(f.check()))
	}

	f.source("other", "v2")
	f.commit("other module changes")
	wantState(t, f.finding(rel), Current) // a neighbour's commit is not mine

	f.source("tool", "v2")
	c := f.commit("tool changes")
	fd = f.finding(rel)
	wantState(t, fd, Stale)
	wantStaleSince(t, fd, c)
	if fd.StaleSince[0].Date != "2026-01-01" || fd.StaleSince[0].Subject != "tool changes" {
		t.Errorf("StaleSince must name the commit: %+v", fd.StaleSince[0])
	}
	if Green(fd.State) {
		t.Fatal("STALE is red")
	}

	f.write("cmd/tool/go.mod", "module example.invalid/tools/tool\n\ngo 1.22\n")
	c2 := f.commit("go.mod bump")
	wantStaleSince(t, f.finding(rel), c, c2) // go.mod is source; oldest first
}

// Judge alone, for a lone binary, agrees with Check: the state machine has one
// entry point and `all` may be empty.
func TestJudge_StandsAloneForASingleBinary(t *testing.T) {
	t.Parallel()
	f := newFixture(t)
	f.module("tool", "v1")
	f.commit("source")
	rel := f.build("tool", "tool", true)
	f.stamp(rel, KindDistributed, nil)
	f.commit("track")
	got := Judge(f.repo, rel, nil)
	want := f.finding(rel)
	if got.State != want.State || got.Path != want.Path {
		t.Fatalf("Judge %v != Check %v", got, want)
	}
}

func TestJudge_DirtyIsRedEvenWhenNothingMoved(t *testing.T) {
	t.Parallel()
	f := newFixture(t)
	f.module("tool", "v1")
	f.commit("source")
	f.source("tool", "v1-uncommitted")
	rel := f.build("tool", "tool", true) // built from an uncommitted tree
	f.git("checkout", "--", "cmd/tool/main.go")
	f.stamp(rel, KindDistributed, nil)
	f.commit("track")

	fd := f.finding(rel)
	wantState(t, fd, Dirty)
	wantStaleSince(t, fd)
	if !fd.Stamp.Modified {
		t.Fatal("stamp must record modified=true")
	}

	// Stale outranks dirty: the commits it lacks are the more specific fact.
	f.source("tool", "v2")
	c := f.commit("tool changes")
	fd = f.finding(rel)
	wantState(t, fd, Stale)
	wantStaleSince(t, fd, c)
	if !fd.Stamp.Modified {
		t.Fatal("STALE must still carry modified=true")
	}
}

func TestJudge_UndeclaredUntilStamped(t *testing.T) {
	t.Parallel()
	f := newFixture(t)
	f.module("tool", "v1")
	f.commit("source")
	rel := f.build("tool", "tool", true)
	f.commit("track binary without a stamp")

	fd := f.finding(rel)
	wantState(t, fd, Undeclared)
	if fd.Stamp != nil {
		t.Fatal("UNDECLARED has no stamp")
	}
	if Green(fd.State) {
		t.Fatal("UNDECLARED is red")
	}

	f.stamp(rel, KindDistributed, nil)
	f.commit("declare")
	wantState(t, f.finding(rel), Current)
}

func TestJudge_OrphanedStamp(t *testing.T) {
	t.Parallel()
	f := newFixture(t)
	f.module("tool", "v1")
	f.commit("source")
	rel := f.build("tool", "tool", true)
	f.stamp(rel, KindDistributed, nil)
	f.commit("track")

	f.git("rm", "-q", rel)
	f.commit("binary gone, stamp kept")
	fd := findingFor(t, f.check(), StampPath(rel))
	wantState(t, fd, Orphaned)

	// A stamp whose sibling is tracked but is not an ELF is just as orphaned.
	f.write(rel, "#!/bin/sh\necho replaced\n")
	f.commit("binary replaced by a script")
	fd = findingFor(t, f.check(), StampPath(rel))
	wantState(t, fd, Orphaned)
	for _, x := range f.check().Findings {
		if x.Path == rel {
			t.Fatalf("a tracked non-ELF is not an artifact, but was judged: %v", x)
		}
	}
}

// A binary with no vcs.* buildinfo cannot be judged, and "cannot be judged" is
// red — even with a well-formed stamp whose sha256 matches. WriteStamp will
// not produce that stamp (sealed above), so it is written by hand here.
func TestJudge_UnstampedIsNeverGreen(t *testing.T) {
	t.Parallel()
	f := newFixture(t)
	f.module("tool", "v1")
	f.commit("source")
	rel := f.build("tool", "tool", false)
	s := Stamp{Kind: KindDistributed, Module: "example.invalid/tools/tool", Revision: f.head(),
		Time: "2026-01-01T00:00:01Z", Go: runtime.Version(), SHA256: sealSHA(t, filepath.Join(f.repo, rel))}
	b, _ := json.Marshal(s)
	f.write(StampPath(rel), string(b))
	f.commit("track")

	fd := f.finding(rel)
	wantState(t, fd, Unstamped)
	if Green(fd.State) {
		t.Fatal("UNSTAMPED is red")
	}

	// A tracked ELF that is not a Go binary at all: UNDECLARED without a
	// stamp, UNSTAMPED with one. Never CURRENT.
	f.write("cmd/tool/blob", "\x7fELF"+strings.Repeat("\x00", 64))
	f.commit("track a non-Go ELF")
	wantState(t, f.finding("cmd/tool/blob"), Undeclared)
	f.write(StampPath("cmd/tool/blob"), string(b))
	f.commit("hand-stamp it")
	wantState(t, f.finding("cmd/tool/blob"), Unstamped)
}

func TestJudge_MalformedStamp(t *testing.T) {
	t.Parallel()
	f := newFixture(t)
	f.module("tool", "v1")
	f.commit("source")
	rel := f.build("tool", "tool", true)
	f.stamp(rel, KindDistributed, nil)
	f.commit("track")
	wantState(t, f.finding(rel), Current)

	raw, _ := os.ReadFile(filepath.Join(f.repo, StampPath(rel)))
	var s Stamp
	json.Unmarshal(raw, &s)
	s.Pin = &Pin{By: "nobody", Reason: "a pin on a distributed stamp"}
	b, _ := json.Marshal(s)
	f.write(StampPath(rel), string(b))
	f.commit("malformed")
	wantState(t, f.finding(rel), Malformed)

	f.write(StampPath(rel), "{not json")
	f.commit("unparseable")
	wantState(t, f.finding(rel), Malformed)

	// A hand-edited revision with the sha256 still matching: the stamp lies
	// about what built the bytes. Buildinfo is the witness; the row is red.
	s.Pin = nil
	s.Revision = strings.Repeat("0", 40)
	b, _ = json.Marshal(s)
	f.write(StampPath(rel), string(b))
	f.commit("edited by hand")
	if fd := f.finding(rel); Green(fd.State) {
		t.Fatalf("a stamp whose revision disagrees with the binary's buildinfo judged %s", fd.State)
	}
}

// Rebuilt without restamping: the stamp describes bytes that no longer exist.
// It outranks STALE (the old stamp's revision does lack commits) because the
// stamp is not evidence about this file at all.
func TestJudge_StampDriftAndPinBroken(t *testing.T) {
	t.Parallel()
	for _, kind := range []Kind{KindDistributed, KindPinned} {
		kind := kind
		t.Run(string(kind), func(t *testing.T) {
			t.Parallel()
			f := newFixture(t)
			f.module("tool", "v1")
			f.commit("source")
			rel := f.build("tool", "tool", true)
			var pin *Pin
			if kind == KindPinned {
				pin = &Pin{By: "seal", Reason: "fixture"}
			}
			f.stamp(rel, kind, pin)
			f.commit("track")

			f.source("tool", "v2")
			f.commit("source moves")
			f.build("tool", "tool", true)
			f.commit("rebuild, forget the stamp")

			fd := f.finding(rel)
			if kind == KindPinned {
				wantState(t, fd, PinBroken)
			} else {
				wantState(t, fd, StampDrift)
			}
			if Green(fd.State) {
				t.Fatal("drift is red")
			}
		})
	}
}

// A pin's age is not a defect, but it is reported: StaleSince is filled and
// modified is recorded, and the verdict stays green.
func TestJudge_PinnedIsGreenAndStillReportsItsAge(t *testing.T) {
	t.Parallel()
	f := newFixture(t)
	f.module("tool", "v1")
	f.commit("source")
	f.source("tool", "v1-dirty")
	rel := f.build("tool", "tool", true)
	f.git("checkout", "--", "cmd/tool/main.go")
	pin := &Pin{By: "GO-2-1", Reason: "differential baseline"}
	f.stamp(rel, KindPinned, pin)
	f.commit("pin")
	f.source("tool", "v2")
	c := f.commit("source moves on")

	fd := f.finding(rel)
	wantState(t, fd, Pinned)
	wantStaleSince(t, fd, c)
	if !Green(fd.State) {
		t.Fatal("PINNED is green")
	}
	if fd.Stamp == nil || fd.Stamp.Pin == nil || *fd.Stamp.Pin != *pin || !fd.Stamp.Modified {
		t.Fatalf("pinned finding must carry its pin and its dirty flag: %+v", fd.Stamp)
	}
	if len(f.check().Red()) != 0 {
		t.Fatalf("a pinned binary alone is a green tree: %v", paths(f.check()))
	}
}

// The two accidents the task names, in the state machine's own words: same
// bytes at two paths, and the same module built twice. Both sides are red —
// the checker cannot know which is the accident — and each names the other.
// Two DIFFERENT modules are not duplicates, or the state would be "any two".
func TestJudge_DuplicateByBytesAndByModule(t *testing.T) {
	t.Parallel()
	f := newFixture(t)
	f.module("tool", "v1")
	f.module("other", "v1")
	f.commit("source")
	// One build per commit: an untracked build output makes the next build
	// dirty, which is exactly how the target tree's +dirty stamps happened.
	tool := f.build("tool", "tool", true)
	f.stamp(tool, KindDistributed, nil)
	f.commit("tool")
	other := f.build("other", "other", true)
	f.stamp(other, KindDistributed, nil)
	f.commit("other")
	for _, rel := range []string{tool, other} {
		wantState(t, f.finding(rel), Current)
	}

	// By bytes: cmd/reviewer/deepseek ≡ cmd/deepseek/deepseek.
	sealCopy(t, filepath.Join(f.repo, other), filepath.Join(f.repo, "cmd/tool/other"))
	f.stamp("cmd/tool/other", KindDistributed, nil)
	f.commit("a byte-identical copy in another directory")
	a, b := f.finding(other), f.finding("cmd/tool/other")
	wantState(t, a, Duplicate)
	wantState(t, b, Duplicate)
	if !strings.Contains(a.Detail, "cmd/tool/other") || !strings.Contains(b.Detail, other) {
		t.Errorf("Detail must name the sibling: %q / %q", a.Detail, b.Detail)
	}
	wantState(t, f.finding(tool), Current) // the unrelated module is untouched
	f.git("rm", "-q", "cmd/tool/other", StampPath("cmd/tool/other"))
	f.commit("remove the copy")
	wantState(t, f.finding(other), Current)

	// By module: cmd/reviewer/main vs cmd/reviewer/reviewer — different
	// bytes, different revisions, one program.
	f.source("tool", "v2")
	f.commit("tool moves")
	main := f.build("tool", "main", true)
	f.stamp(main, KindDistributed, nil)
	f.commit("the same module built again under another name")
	a, b = f.finding(tool), f.finding(main)
	if a.Stamp.SHA256 == b.Stamp.SHA256 {
		t.Fatal("fixture: the two builds should differ in bytes")
	}
	wantState(t, a, Duplicate)
	wantState(t, b, Duplicate)
	if !strings.Contains(a.Detail, main) || !strings.Contains(b.Detail, tool) {
		t.Errorf("Detail must name the sibling: %q / %q", a.Detail, b.Detail)
	}
	wantState(t, f.finding(other), Current)
}

// A revision that is not in HEAD's history: staleness is not computable and
// is therefore not asserted either way. Merging the revision in resolves it —
// FOREIGN is about ancestry, not about where the build happened.
func TestJudge_ForeignUntilItsRevisionIsAnAncestor(t *testing.T) {
	t.Parallel()
	f := newFixture(t)
	f.module("tool", "v1")
	f.commit("source")
	f.git("checkout", "-q", "-b", "side")
	f.source("tool", "v-side")
	side := f.commit("side work")
	rel := f.build("tool", "tool", true)
	f.stamp(rel, KindDistributed, nil)
	bin, _ := os.ReadFile(filepath.Join(f.repo, rel))
	stamp, _ := os.ReadFile(filepath.Join(f.repo, StampPath(rel)))
	os.Remove(filepath.Join(f.repo, rel))
	os.Remove(filepath.Join(f.repo, StampPath(rel)))
	f.git("checkout", "-q", "main")
	f.write(rel, string(bin))
	f.write(StampPath(rel), string(stamp))
	f.commit("binary from a branch that is not merged")

	fd := f.finding(rel)
	wantState(t, fd, Foreign)
	if !strings.Contains(fd.Detail, side[:7]) {
		t.Errorf("Detail must name the foreign revision %s: %q", side[:7], fd.Detail)
	}
	if fd.Stamp == nil || fd.Stamp.Revision != side {
		t.Fatalf("FOREIGN still carries its stamp: %+v", fd.Stamp)
	}
	if Green(fd.State) {
		t.Fatal("FOREIGN is red")
	}

	f.git("merge", "-q", "--no-edit", "side")
	wantState(t, f.finding(rel), Current)
}

func sealCopy(t *testing.T, from, to string) {
	t.Helper()
	b, err := os.ReadFile(from)
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(to, b, 0o755); err != nil {
		t.Fatal(err)
	}
}

// ------------------------------------------------- the checker cannot look

// TestHelperProcess is the `artifacts` binary: re-exec'd with the arguments
// after "--". It is how exit codes are sealed without a second build.
func TestHelperProcess(t *testing.T) {
	if os.Getenv("ARTIFACTS_SEAL_HELPER") != "1" {
		return
	}
	os.Args = append([]string{"artifacts"}, flag.Args()...)
	main()
	os.Exit(99) // main returned without exiting: not a code the contract names
}

func runCLI(t *testing.T, dir string, extraEnv []string, args ...string) (int, string) {
	t.Helper()
	cmd := exec.Command(os.Args[0], append([]string{"-test.run=^TestHelperProcess$", "--"}, args...)...)
	cmd.Dir = dir
	cmd.Env = append(os.Environ(), "ARTIFACTS_SEAL_HELPER=1")
	cmd.Env = append(cmd.Env, extraEnv...)
	out, err := cmd.CombinedOutput()
	code := 0
	var exit *exec.ExitError
	if errors.As(err, &exit) {
		code = exit.ExitCode()
	} else if err != nil {
		t.Fatalf("re-exec: %v\n%s", err, out)
	}
	return code, string(out)
}

func TestCLI_ExitCodesNameTheOutcome(t *testing.T) {
	t.Parallel()
	f := newFixture(t)
	f.module("tool", "v1")
	f.commit("source")
	rel := f.build("tool", "tool", true)
	f.stamp(rel, KindDistributed, nil)
	f.commit("track")

	if code, out := runCLI(t, f.repo, nil, "check", "-repo", f.repo); code != exitGreen {
		t.Fatalf("green tree: exit %d, want %d\n%s", code, exitGreen, out)
	}

	f.source("tool", "v2")
	c := f.commit("tool moves")
	code, out := runCLI(t, f.repo, nil, "check", "-repo", f.repo)
	if code != exitRed {
		t.Fatalf("red tree: exit %d, want %d\n%s", code, exitRed, out)
	}
	for _, want := range []string{rel, string(Stale), c[:7]} {
		if !strings.Contains(out, want) {
			t.Errorf("red output must name the artifact, its state and the commit it lacks; missing %q:\n%s", want, out)
		}
	}

	if code, out := runCLI(t, f.repo, nil, "check", "-repo", t.TempDir()); code != exitCannot {
		t.Fatalf("not a repository: exit %d, want %d\n%s", code, exitCannot, out)
	}
	if code, _ := runCLI(t, f.repo, nil); code != exitInvalid {
		t.Fatalf("no subcommand: exit %d, want %d", code, exitInvalid)
	}
	if code, _ := runCLI(t, f.repo, nil, "frobnicate"); code != exitInvalid {
		t.Fatalf("unknown subcommand: exit %d, want %d", code, exitInvalid)
	}

	// `stamp` from the CLI is WriteStamp: it must refuse the same things.
	if code, _ := runCLI(t, f.repo, nil, "stamp", "-kind", "pinned", filepath.Join(f.repo, rel)); code != exitInvalid {
		t.Fatalf("stamp -kind pinned without a pin: exit %d, want %d", code, exitInvalid)
	}
	if code, out := runCLI(t, f.repo, nil, "stamp", "-kind", "pinned", "-pin-by", "seal", "-pin-reason", "fixture", filepath.Join(f.repo, rel)); code != 0 {
		t.Fatalf("stamp: exit %d\n%s", code, out)
	}
	s, err := ReadStamp(filepath.Join(f.repo, StampPath(rel)))
	if err != nil || s.Kind != KindPinned || s.Pin == nil || s.Pin.By != "seal" {
		t.Fatalf("CLI stamp did not write what it was told: %+v %v", s, err)
	}
}

// The trap named in advance: a checker that cannot look must not report a
// clean tree. Without git the exit is 3, never 0 — and without the go tool the
// verdict is unchanged, because buildinfo is read from the file.
func TestCLI_WithoutGitIsLoudAndWithoutGoIsUnchanged(t *testing.T) {
	t.Parallel()
	f := newFixture(t)
	f.module("tool", "v1")
	f.commit("source")
	rel := f.build("tool", "tool", true)
	f.stamp(rel, KindDistributed, nil)
	f.commit("track")
	f.source("tool", "v2")
	f.commit("tool moves") // the tree is red; a checker that cannot see git must not say otherwise

	gitPath, err := exec.LookPath("git")
	if err != nil {
		t.Fatal(err)
	}
	onlyGit := t.TempDir()
	if err := os.Symlink(gitPath, filepath.Join(onlyGit, "git")); err != nil {
		t.Fatal(err)
	}
	nothing := t.TempDir()

	code, out := runCLI(t, f.repo, []string{"PATH=" + nothing}, "check", "-repo", f.repo)
	if code != exitCannot {
		t.Fatalf("without git: exit %d, want %d (0 would certify a tree nobody looked at)\n%s", code, exitCannot, out)
	}
	if !strings.Contains(strings.ToLower(out), "git") {
		t.Errorf("without git: the failure must say why:\n%s", out)
	}

	code, out = runCLI(t, f.repo, []string{"PATH=" + onlyGit}, "check", "-repo", f.repo)
	if code != exitRed || !strings.Contains(out, string(Stale)) {
		t.Fatalf("with git but no go tool: exit %d, want %d and a STALE row (the go tool is not needed to read buildinfo)\n%s", code, exitRed, out)
	}
}

// ----------------------------------------------------------- the real tree

var (
	cmdLiteral = regexp.MustCompile(`"(cmd/[a-z0-9_-]+/[a-z0-9_-]+)"`)
	modLine    = regexp.MustCompile(`(?m)^module\s+(\S+)`)
)

// realTree is the repository these seals guard. It is the enclosing checkout,
// or ARTIFACTS_REPO. It must be claude-workflow — a tree with no cmd/ modules
// would make every seal below vacuous, so that is a failure, not a skip.
func realTree(t *testing.T) string {
	t.Helper()
	repo := os.Getenv("ARTIFACTS_REPO")
	if repo == "" {
		out, err := exec.Command("git", "rev-parse", "--show-toplevel").Output()
		if err != nil {
			t.Fatalf("not inside a repository and ARTIFACTS_REPO unset: %v", err)
		}
		repo = strings.TrimSpace(string(out))
	}
	own, err := os.ReadFile("go.mod")
	if err != nil {
		t.Fatal(err)
	}
	prefix := path0(modLine.FindStringSubmatch(string(own)))
	prefix = prefix[:strings.LastIndex(prefix, "/")+1]
	mods, _ := filepath.Glob(filepath.Join(repo, "cmd", "*", "go.mod"))
	siblings := 0
	for _, m := range mods {
		b, _ := os.ReadFile(m)
		if strings.HasPrefix(path0(modLine.FindStringSubmatch(string(b))), prefix) && filepath.Base(filepath.Dir(m)) != "artifacts" {
			siblings++
		}
	}
	if siblings == 0 {
		t.Fatalf("%s has no cmd/*/go.mod under %s: these seals need claude-workflow (set ARTIFACTS_REPO)", repo, prefix)
	}
	return repo
}

func path0(m []string) string {
	if len(m) < 2 {
		return ""
	}
	return m[1]
}

func sealGit(t *testing.T, repo string, args ...string) string {
	t.Helper()
	cmd := exec.Command("git", args...)
	cmd.Dir = repo
	out, err := cmd.Output()
	if err != nil {
		t.Fatalf("git %s: %v", strings.Join(args, " "), err)
	}
	return strings.TrimSpace(string(out))
}

func sealLsFiles(t *testing.T, repo string) []string {
	t.Helper()
	out := sealGit(t, repo, "ls-files", "-z")
	var files []string
	for _, f := range strings.Split(out, "\x00") {
		if f != "" {
			files = append(files, f)
		}
	}
	return files
}

// treeELFs is the test's own derivation of the set: the index plus the magic.
// It is deliberately independent of TrackedELF.
func treeELFs(t *testing.T, repo string) []string {
	t.Helper()
	var elfs []string
	for _, f := range sealLsFiles(t, repo) {
		fh, err := os.Open(filepath.Join(repo, f))
		if err != nil {
			continue
		}
		var magic [4]byte
		n, _ := fh.Read(magic[:])
		fh.Close()
		if n == 4 && bytes.Equal(magic[:], []byte("\x7fELF")) {
			elfs = append(elfs, f)
		}
	}
	sort.Strings(elfs)
	return elfs
}

// moduleOf is the module declared by the go.mod beside the artifact.
func moduleOf(t *testing.T, repo, rel string) string {
	t.Helper()
	b, err := os.ReadFile(filepath.Join(repo, filepath.Dir(rel), "go.mod"))
	if err != nil {
		return ""
	}
	return path0(modLine.FindStringSubmatch(string(b)))
}

type built struct {
	module, revision string
	modified         bool
}

func builtFrom(t *testing.T, path string) (built, error) {
	t.Helper()
	bi, err := buildinfo.ReadFile(path)
	if err != nil {
		return built{}, err
	}
	b := built{module: bi.Main.Path}
	for _, s := range bi.Settings {
		switch s.Key {
		case "vcs.revision":
			b.revision = s.Value
		case "vcs.modified":
			b.modified = s.Value == "true"
		}
	}
	if b.revision == "" {
		return b, errors.New("no vcs.revision")
	}
	return b, nil
}

// Every tracked ELF is declared, lives in the module that built it, and is
// the only artifact of that module and of those bytes. This is the whole GO-2
// unit as one invariant; at 1db2d41 it fails on exactly the two pairs the task
// names, and GO-2-3 makes it hold.
func TestTree_EveryArtifactIsDeclaredUniqueAndInItsOwnModule(t *testing.T) {
	repo := realTree(t)
	elfs := treeELFs(t, repo)
	tracked := map[string]bool{}
	for _, f := range sealLsFiles(t, repo) {
		tracked[f] = true
	}

	byModule := map[string][]string{}
	bySHA := map[string][]string{}
	for _, rel := range elfs {
		if !tracked[StampPath(rel)] {
			t.Errorf("%s: tracked ELF without a tracked %s — UNDECLARED", rel, StampPath(rel))
		}
		b, err := builtFrom(t, filepath.Join(repo, rel))
		if err != nil {
			t.Errorf("%s: cannot read Go buildinfo (%v) — a tracked binary that cannot be judged", rel, err)
			continue
		}
		if own := moduleOf(t, repo, rel); own != b.module {
			t.Errorf("%s: built from module %q but lives beside go.mod %q — an artifact in the wrong module", rel, b.module, own)
		}
		byModule[b.module] = append(byModule[b.module], rel)
		bySHA[sealSHA(t, filepath.Join(repo, rel))] = append(bySHA[sealSHA(t, filepath.Join(repo, rel))], rel)
	}
	for m, rels := range byModule {
		if len(rels) > 1 {
			t.Errorf("module %s is tracked as %d binaries: %v — one program, one artifact", m, len(rels), rels)
		}
	}
	for s, rels := range bySHA {
		if len(rels) > 1 {
			t.Errorf("byte-identical binaries at %v (sha256 %s…) — one of them is an accident", rels, s[:8])
		}
	}
	for _, f := range sealLsFiles(t, repo) {
		if strings.HasSuffix(f, ".stamp") && !tracked[strings.TrimSuffix(f, ".stamp")] {
			t.Errorf("%s: stamp without a tracked binary — ORPHANED", f)
		}
	}
}

// The invoked program exists. Consumers hardcode artifact paths as string
// literals (cmd/iterate's reviewer and recheck defaults); every such literal
// that points into a cmd/ module must resolve to a tracked ELF. This is how
// "cmd/reviewer/main stays" is derived from its caller, not from a list.
func TestTree_EveryPathAConsumerInvokesIsATrackedArtifact(t *testing.T) {
	repo := realTree(t)
	elfs := map[string]bool{}
	for _, e := range treeELFs(t, repo) {
		elfs[e] = true
	}
	invoked := map[string][]string{}
	for _, f := range sealLsFiles(t, repo) {
		if !strings.HasSuffix(f, ".go") || strings.HasSuffix(f, "_test.go") {
			continue
		}
		src, err := os.ReadFile(filepath.Join(repo, f))
		if err != nil {
			t.Fatal(err)
		}
		for _, m := range cmdLiteral.FindAllStringSubmatch(string(src), -1) {
			rel := m[1]
			if moduleOf(t, repo, rel) == "" || strings.HasSuffix(rel, ".go") {
				continue
			}
			invoked[rel] = append(invoked[rel], f)
		}
	}
	if len(invoked) == 0 {
		t.Fatal("no consumer literal found: cmd/iterate hardcodes cmd/reviewer/main and cmd/recheck/recheck, so this seal has stopped looking")
	}
	for rel, callers := range invoked {
		if !elfs[rel] {
			t.Errorf("%s is invoked by %v but is not a tracked ELF", rel, callers)
		}
	}
}

// The checker's verdict on the live tree agrees with git. For every finding,
// the test recomputes ancestry and the source commits after the stamped
// revision and requires the state the contract assigns. This holds at any
// HEAD, so it is what stops the next rebuild-without-restamp from going green.
func TestTree_VerdictsAgreeWithGit(t *testing.T) {
	repo := realTree(t)
	report, err := Check(repo)
	if err != nil {
		t.Fatalf("Check could not judge the tree: %v", err)
	}
	elfs := treeELFs(t, repo)
	seen := map[string]bool{}
	for _, f := range report.Findings {
		seen[f.Path] = true
	}
	for _, rel := range elfs {
		if !seen[rel] {
			t.Errorf("%s is a tracked ELF with no finding: the checker did not look at it", rel)
		}
	}
	for _, f := range report.Findings {
		f := f
		if f.Stamp == nil {
			continue // UNDECLARED / MALFORMED / ORPHANED carry no revision to cross-check
		}
		abs := filepath.Join(repo, f.Path)
		if sha := sealSHA(t, abs); sha != f.Stamp.SHA256 {
			if f.State != StampDrift && f.State != PinBroken {
				t.Errorf("%s: bytes differ from the stamp but state is %s", f.Path, f.State)
			}
			continue
		}
		if f.State == Duplicate || f.State == Unstamped {
			continue
		}
		b, err := builtFrom(t, abs)
		if err != nil {
			t.Errorf("%s: %s but buildinfo is unreadable (%v)", f.Path, f.State, err)
			continue
		}
		if b.revision != f.Stamp.Revision || b.modified != f.Stamp.Modified || b.module != f.Stamp.Module {
			t.Errorf("%s: stamp %+v does not match the binary's buildinfo %+v", f.Path, *f.Stamp, b)
		}
		dir := filepath.Dir(f.Path)
		ancestor := exec.Command("git", "merge-base", "--is-ancestor", f.Stamp.Revision, "HEAD")
		ancestor.Dir = repo
		isAncestor := ancestor.Run() == nil
		var commits []string
		if isAncestor {
			out := sealGit(t, repo, "log", "--reverse", "--format=%H", f.Stamp.Revision+"..HEAD", "--", dir+"/*.go", dir+"/go.mod")
			if out != "" {
				commits = strings.Split(out, "\n")
			}
		}
		var want State
		switch {
		case f.Stamp.Kind == KindPinned:
			want = Pinned
		case !isAncestor:
			want = Foreign
		case len(commits) > 0:
			want = Stale
		case f.Stamp.Modified:
			want = Dirty
		default:
			want = Current
		}
		if f.State != want {
			t.Errorf("%s: git says %s (ancestor=%v, %d source commits after %s, modified=%v) but the checker says %s", f.Path, want, isAncestor, len(commits), f.Stamp.Revision[:7], f.Stamp.Modified, f.State)
		}
		if isAncestor && strings.Join(shas(f.StaleSince), ",") != strings.Join(commits, ",") {
			t.Errorf("%s: StaleSince %v, git says %v", f.Path, shas(f.StaleSince), commits)
		}
	}
	for _, r := range report.Red() {
		if r.Detail == "" && len(r.StaleSince) == 0 {
			t.Errorf("%s is %s with neither Detail nor StaleSince: a red without a reason", r.Path, r.State)
		}
	}
}

// ------------------------------------------- the worked oracle at 1db2d41

const oracleRev = "1db2d41"

// oracleClone is docs/explicit-state @ 1db2d41 in a throwaway clone, HEAD
// detached there, with an identity that can commit.
func oracleClone(t *testing.T) *fixture {
	t.Helper()
	src := realTree(t)
	probe := exec.Command("git", "cat-file", "-e", oracleRev+"^{commit}")
	probe.Dir = src
	if err := probe.Run(); err != nil {
		t.Fatalf("%s is not in %s: the oracle needs full history (a shallow checkout cannot judge staleness either — fetch-depth: 0)", oracleRev, src)
	}
	f := &fixture{t: t, repo: t.TempDir()}
	f.run(filepath.Dir(f.repo), nil, "git", "clone", "-q", "--no-checkout", src, f.repo)
	f.git("checkout", "-q", "--detach", oracleRev)
	f.git("config", "user.name", "seal")
	f.git("config", "user.email", "seal@example.invalid")
	f.git("config", "commit.gpgsign", "false")
	return f
}

// Before anything is declared: the nine are exactly the tree's tracked ELFs,
// all UNDECLARED, and the two pairs the task names are what buildinfo and the
// bytes say they are. Once all nine are stamped, the state machine says
// DUPLICATE for both pairs and names the sibling.
func TestOracle_TheNineAtExplicitStateAreUndeclaredAndTwoPairsCollide(t *testing.T) {
	f := oracleClone(t)
	derived := treeELFs(t, f.repo)
	got, err := TrackedELF(f.repo)
	if err != nil {
		t.Fatal(err)
	}
	sort.Strings(got)
	if strings.Join(got, ",") != strings.Join(derived, ",") {
		t.Fatalf("TrackedELF %v != tree %v", got, derived)
	}
	if len(derived) != 9 {
		t.Fatalf("the contract measured nine tracked ELFs at %s, the tree has %d: %v", oracleRev, len(derived), derived)
	}
	report := f.check()
	if len(report.Findings) != 9 || len(report.Red()) != 9 {
		t.Fatalf("undeclared tree: want 9 red findings, got %v", paths(report))
	}
	for _, x := range report.Findings {
		wantState(t, x, Undeclared)
	}

	main, _ := builtFrom(t, filepath.Join(f.repo, "cmd/reviewer/main"))
	reviewer, _ := builtFrom(t, filepath.Join(f.repo, "cmd/reviewer/reviewer"))
	if main.module != reviewer.module || main.revision == reviewer.revision {
		t.Fatalf("cmd/reviewer/{main,reviewer} should be one module at two revisions: %+v %+v", main, reviewer)
	}
	if a, b := sealSHA(t, filepath.Join(f.repo, "cmd/reviewer/deepseek")), sealSHA(t, filepath.Join(f.repo, "cmd/deepseek/deepseek")); a != b || !strings.HasPrefix(a, "6ad7a782") {
		t.Fatalf("cmd/reviewer/deepseek should be byte-identical to cmd/deepseek/deepseek (6ad7a782…): %s %s", a, b)
	}

	for _, rel := range derived {
		if rel == "cmd/classify/classify" {
			f.stamp(rel, KindPinned, &Pin{By: "GO-2-1", Reason: "differential baseline"})
		} else {
			f.stamp(rel, KindDistributed, nil)
		}
	}
	f.commit("declare all nine")
	report = f.check()
	for rel, sibling := range map[string]string{
		"cmd/reviewer/main":     "cmd/reviewer/reviewer",
		"cmd/reviewer/reviewer": "cmd/reviewer/main",
		"cmd/reviewer/deepseek": "cmd/deepseek/deepseek",
		"cmd/deepseek/deepseek": "cmd/reviewer/deepseek",
	} {
		x := findingFor(t, report, rel)
		wantState(t, x, Duplicate)
		if !strings.Contains(x.Detail, sibling) {
			t.Errorf("%s: Detail %q does not name %s", rel, x.Detail, sibling)
		}
	}
}

// §5, exactly: the seven declared as ruled, the two accidents untracked,
// nothing rebuilt. One PINNED, one CURRENT, five red, each with its reason.
func TestOracle_SevenDeclaredAtExplicitStateJudgeAsTheContractSays(t *testing.T) {
	f := oracleClone(t)
	for _, rel := range treeELFs(t, f.repo) {
		switch rel {
		case "cmd/reviewer/reviewer", "cmd/reviewer/deepseek":
			f.git("rm", "-q", rel)
		case "cmd/classify/classify":
			f.stamp(rel, KindPinned, &Pin{By: "GO-2-1", Reason: "differential baseline exec'd as pinnedBinary by cmd/classify seals (B1 lineage); rebuild is an operator decision"})
		default:
			f.stamp(rel, KindDistributed, nil)
		}
	}
	f.commit("declare seven, untrack two accidents")
	report := f.check()

	full := func(short string) string { return f.git("rev-parse", short+"^{commit}") }
	type row struct {
		state    State
		modified bool
		since    []string
	}
	want := map[string]row{
		"cmd/classify/classify": {Pinned, true, []string{full("2b18e02")}},
		"cmd/deepseek/deepseek": {Current, false, nil},
		"cmd/gates/gates":       {Stale, true, []string{full("2b18e02")}},
		"cmd/iterate/iterate":   {Foreign, true, nil},
		"cmd/recheck/recheck":   {Dirty, true, nil},
		"cmd/repro/repro":       {Stale, true, []string{full("fd4ce07")}},
		"cmd/reviewer/main": {Stale, true, []string{
			full("fd4ce07"), full("cb37065"), full("a25c0e0"), full("c14da76"), full("b2a9ba5"), full("7916067"), full("1db2d41"),
		}},
	}
	if len(report.Findings) != len(want) {
		t.Fatalf("want %d findings, got %v", len(want), paths(report))
	}
	for rel, w := range want {
		x := findingFor(t, report, rel)
		wantState(t, x, w.state)
		if x.Stamp == nil || x.Stamp.Modified != w.modified {
			t.Errorf("%s: modified want %v, stamp %+v", rel, w.modified, x.Stamp)
		}
		wantStaleSince(t, x, w.since...)
	}
	if len(report.Red()) != 5 {
		t.Errorf("want five red, got %v", paths(report))
	}

	classify := findingFor(t, report, "cmd/classify/classify")
	if !strings.HasPrefix(classify.Stamp.SHA256, "ad289891") {
		t.Errorf("classify pin sha256 %s, contract measured ad289891…", classify.Stamp.SHA256)
	}
	rm := findingFor(t, report, "cmd/reviewer/main")
	if !strings.HasPrefix(rm.Stamp.Revision, "52d46438") || rm.StaleSince[0].Date != "2026-07-19" {
		t.Errorf("reviewer/main: built at %s, stale since %+v; contract says 52d46438, 2026-07-19", rm.Stamp.Revision, rm.StaleSince[0])
	}
	for _, c := range rm.StaleSince {
		if strings.HasPrefix(c.SHA, full("840928c")) {
			t.Error("840928c touches only binaries and must not count as a source change")
		}
	}
	it := findingFor(t, report, "cmd/iterate/iterate")
	if !strings.HasPrefix(it.Stamp.Revision, "830ff3cc") || !strings.Contains(it.Detail, "830ff3cc") {
		t.Errorf("iterate: FOREIGN must name the revision 830ff3cc: %+v %q", it.Stamp, it.Detail)
	}
}
