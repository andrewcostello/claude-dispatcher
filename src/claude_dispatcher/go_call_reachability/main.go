// Command go_call_reachability reports the declared symbols, the entrypoints
// and the call edges of ONE Go package, as a stable JSON document.
//
// UNIT D6, P1 SCAFFOLD. This file is a CONTRACT: the request and response
// types below, their JSON tags, and the EDGE GRAMMAR in the comments are
// normative. `analyze` is not implemented and `main` exits non-zero. P3 fills
// it in; nothing here may be relaxed without a P4 ruling.
//
// `respond` IS implemented, and that is the one exception, on D4's reasoning
// for ts_parser_home: this unit was asked for a wire protocol, and a wire
// protocol left as a stub is a note rather than an answer — a seal author
// cannot exercise "the schema is checked before anything is read" against a
// function that raises before it reads. It also keeps this file compiling and
// vet-clean, which is the only way the next author can tell that the CONTRACT
// half is well formed. See the CHOICE at respond.
//
// # WHY THIS PROGRAM EXISTS
//
// The Python side of the gate must not contain a Go parser. That argument is
// go_signature_fingerprint's and it is not repeated. What is NEW here, and is
// the reason this is a second program rather than a fourth field on the first
// one, is the UNIT OF WORK: a signature is a per-file property and a call graph
// is not. GoHelperRequest is contracted as "one revision of one file, not a
// batch" and that rule is right for signatures and fatal here — a per-file
// protocol makes every cross-file call inside one package an unresolved edge,
// which is an abstention on almost everything.
//
// The cost that divergence avoids is measured, not assumed. The TypeScript
// comparator kept the one-process-per-file rule and pays 169 ms per file on
// the gate path (role_protocol.py, TYPESCRIPT_SUPPORT enrolment checklist item
// 3, measured 2026-08-10): about 68 seconds for a 200-file branch, recorded
// there as a ruled price with no caching route, because the equivalent fix — a
// persistent process — is refused by the one-file-per-invocation rule itself.
// This protocol does not open that hole: it costs one process per PACKAGE.
//
// # THE UNIT OF INVOCATION IS ONE PACKAGE
//
// Not one file (a call graph is not a per-file property) and not one module
// (see below). One package: every file in one directory that carries the same
// `package` clause, INCLUDING that package's `_test.go` files, because the
// seals whose subjects this mechanism judges are in them and a seal that is
// not in the graph contributes no subject at all.
//
// A directory holding an external test package (`package foo_test` beside
// `package foo`) is TWO units and must be sent as two requests. They are two
// packages by the language's own rules — `foo_test` reaches `foo` only through
// an import, exactly as any other package does — and merging them would put
// two unqualified identifier scopes in one resolution pass, which is the one
// thing a name-level resolver may not do.
//
// One package rather than one module, because the package is the exact scope in
// which Go's unqualified-identifier resolution is decidable from text alone. A
// call to `pkg.F` in another package is emitted anyway: the import block of the
// calling file names the import path, so the callee's KEY is derivable without
// the callee's source. The Python side then drops any edge whose callee is not
// declared anywhere in the tree, which is CallGraph's own recorded rule
// ("edges are kept only when BOTH ends are declared in the tree").
//
// # PROTOCOL
//
// One request object on stdin, which is then closed. One response object on
// stdout, always, followed by a newline. Diagnostics go to stderr and are never
// mixed into stdout.
//
// Exit status and document are separate channels, verbatim from the sibling:
//
//	exit 0        stdout holds a valid response document. That INCLUDES a
//	              document whose parse_error is set: unparseable Go is a
//	              successful run of this program and a fact about the file.
//	exit non-zero the caller reports AnalyzerFault.HELPER_FAILED and does not
//	              read stdout at all. Never exit non-zero for a bad input FILE;
//	              exit non-zero only when this program itself could not do its
//	              job (bad request document, unwritable stdout).
//
// The caller enforces a wall-clock timeout and reports
// AnalyzerFault.HELPER_TIMEOUT. This program must therefore never block on
// anything but its own stdin, must not consult the network, must not read the
// filesystem, and must not need GOPATH, a module cache or a build of the
// package it is reading: it parses the request's TEXT, in isolation, with
// go/parser.
//
// Source travels as TEXT and never as a filename. That is kept from
// GoHelperRequest unchanged and for its reason: a program that took paths would
// make the analysis depend on the working tree, and the working tree is exactly
// what the branch under judgement controls.
//
// # DETERMINISM IS PART OF THE CONTRACT
//
// Two runs over identical input must produce byte-identical documents.
// Symbols, roots and unresolved sites are emitted in DECLARATION order; edges
// are emitted in the order their call sites appear in the source, file by file
// in the order the request lists them. No map may be ranged over to produce
// output. The Python side sorts again at construction (build_call_graph), so a
// nondeterminism here does not move a VERDICT — but it does move the WITNESS
// PATH a human is asked to check, which is the whole evidence a BREACH offers.
//
// # THE EDGE GRAMMAR — WHAT BECOMES AN EDGE, AND HOW WELL IT IS KNOWN
//
// This is the normative half of the unit. Each row names the Go shape, the
// `kind` string on the wire, and the caller's EdgeKind. Two of the four kinds
// force PathQuality.OVER_APPROXIMATED at the caller and two do not.
//
//	Go shape                                     kind         over-approx?
//	-------------------------------------------  -----------  ------------
//	f(x), f an ident declared in this package     "direct"     no
//	pkg.F(x), pkg an import alias in this file    "direct"     no
//	x.M(x), x's declared type resolved by name    "method"     no
//	x.M(x), x an interface-typed or unresolved    "interface"  YES
//	  receiver — one edge per in-tree method M
//	F, x.M, T.M mentioned as a VALUE, not called  "reference"  YES
//	f()(x), fns[i](x), c.handler(x), reflection   (no edge)    unresolved[]
//
// A METHOD is DIRECT-strength and is a separate kind anyway, for the reason
// EdgeKind records: a stdlib-only walk resolves these less often than a
// type-checked one would, and a report must be able to say which kind of
// resolution it was leaning on. "Resolved by name" means the receiver's type
// is readable from the text without inference — a parameter `x T`, a
// `var x T`, a `x := T{...}` composite literal, a `x := &T{...}`, or a method
// on a receiver inside the same package. Anything weaker is "interface".
//
// INTERFACE SATISFACTION IS NOT AN EDGE. Go's satisfaction is implicit and
// structural, so a name-level walk cannot compute it and must not pretend to:
// a type declaring the methods of an interface produces NO edge, and
// `var _ I = (*T)(nil)` — the compile-time assertion idiom — produces no edge
// either, because it names no method. What produces edges is a CALL through an
// interface-typed value, and the honest resolution of it is one "interface"
// edge to EVERY in-tree method of that name. That over-approximates toward
// REACHED, which is the permissive direction, and it is marked rather than
// hidden. Promotion through an embedded field lands here too: whether an embed
// promotes is what decides which interfaces a type satisfies (the reason
// go_signature_fingerprint's v2 grammar moved its `embedded:` marker), and it
// is not decidable at name level.
//
// A FUNCTION VALUE is "reference" and never "direct". `sort.Slice(xs, less)`
// reaches `less` — this is a real way production reaches code and dropping it
// would be a large false-BREACH source — but the value may never be invoked, so
// the fact is weaker than a call and the path through it is over-approximated.
// A method VALUE (`x.M` uncalled) and a method EXPRESSION (`T.M`) are the same
// kind for the same reason.
//
// `go f()` and `defer f()` are CALLS and take the kind their call form would
// take. They are named here only because a walk that keys on *ast.CallExpr gets
// them for free and a walk that keys on statement types silently drops both.
//
// # ATTRIBUTION: A CLOSURE'S CALLS BELONG TO THE FUNCTION THAT WROTE IT
//
// Every call inside an *ast.FuncLit is attributed to the innermost enclosing
// NAMED declaration, never to a synthetic symbol for the literal. This is
// load-bearing and not a convenience: subjects_of_seal defines a seal's subject
// as what the seal's own body calls directly, "including nested closures,
// table-driven subtest bodies, and t.Run literals declared inside it", and a
// synthetic symbol per closure would empty the subject set of every
// table-driven seal in the target repositories.
//
// # ROOTS
//
// Emitted with the symbol they enter at, so the caller never has to guess:
//
//	go_main         `func main()` in a file declaring `package main`
//	go_init         `func init()` in any package
//	go_package_var  a package-level `var x = <expression>`; the symbol is
//	                synthetic and spelled with a suffix no declaration can
//	                produce, because a root with no symbol has no outgoing
//	                edges and would contribute silently nothing
//	test_function   a func in a `_test.go` file whose name is a test name
//
// This program does NOT decide whether a root is production or test, and it
// does not decide whether a file is one of the tests. RootKind is derived by
// the Python side from the entrypoint kind and from seal_verify.is_test_path,
// which is this repository's one matcher for that question; `_validate_root`
// refuses any row that asserts otherwise. Emitting `test_function` for a func
// in a `_test.go` file is a NAMING claim only — the naming half is the only
// half that is per-language.
//
// # PARSE FAILURE, AND WHY IT IS NOT AN ERROR
//
// A file go/parser refuses sets `parse_error` and the four graph arrays are
// omitted; exit stays 0. The caller reports it through
// CallGraph.unreadable_paths, which makes the whole tree abstain with
// UndecidedReason.PARSE_FAILED — and PARSE_FAILED outranks NO_ENTRYPOINT when
// both hold, because an unparsed file is exactly where an undiscovered
// `func main` would be, so a "this tree has no entrypoint" claim computed
// around it is a claim computed around a hole.
//
// CHOICE (the caller's contract does not say how many bad files a response may
// name): only the FIRST refusing file is reported. Rejected alternative: an
// array of every file that would not parse, which is strictly more information
// and is out because the caller's abstention is whole-tree either way, so the
// extra entries change no verdict — and a second field carrying a partial list
// (the files parsed BEFORE the first failure) would be a second answer to
// "which file do I fix", from a document that stopped reading.
//
// # BUILD CONSTRAINTS ARE NOT EVALUATED
//
// go/parser does not evaluate `//go:build`, and this program does not add an
// evaluator. Every file in the request is parsed, so an edge that exists only
// on Windows counts here. That over-approximates toward REACHED and is a real
// hole rather than a conservative choice; it is limit 6 in the Python module
// and it is recorded rather than narrowed, because evaluating constraints would
// make "which platform" an input to a verdict.
//
// It has one consequence the caller must be told about rather than left to
// discover: two files in one package, guarded by mutually exclusive
// constraints, may legally declare the SAME top-level name. That is a duplicate
// symbol key, and the response contract below rules on it. Measured on
// claude-workflow @ docs/explicit-state, 2026-08-11: `git grep -c "go:build"`
// over `cmd/**/*.go` matches nothing at all, so the cost binds nothing in the
// acceptance repository today.
//
// # DUPLICATE KEYS
//
// A duplicate `symbols[].key` within one response is a DEFECT and the caller
// refuses the document. The reason is sharper here than it was for the
// fingerprinter, whose duplicate-key guard exists because two fingerprints for
// one key means one of them is unreachable: D5's Symbol declares `path` and
// `line` as `field(compare=False)`, so identity is over `key` ALONE — two
// symbols with one key are ONE symbol whose `path` is decided by dict insertion
// order, and `path` is what seal_verify.is_test_path reads to decide whether a
// symbol is excluded from a subject set and whether a root is TEST or
// PRODUCTION. A duplicate key can therefore turn a BREACH into an exclusion.
//
// Duplicate EDGES are the opposite ruling: they are deduplicated by the caller
// and are NOT a fault. `f(f(x))` is ordinary Go and emits two identical
// (caller, callee, kind, site) tuples, so refusing them would blame the machine
// for a legal program — which is the lesson go_signature_fingerprint's isBlank
// records after GOROOT produced duplicate keys from `stringer` output.
package main

import (
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
)

// SchemaVersion is echoed on every response and checked by the caller against
// its own GO_REACHABILITY_SCHEMA. A mismatch is
// AnalyzerFault.HELPER_OUTPUT_INVALID and never a best-effort read.
//
// Bump it whenever the SYMBOL SPELLING or the EDGE GRAMMAR changes, and not
// only when a field moves. A symbol key is compared for equality across the
// root set, the edge set and the subject set; a spelling change that went
// unversioned would make every subject look unreachable, which is the loudest
// false report this mechanism can produce — a repository-wide BREACH flood
// against innocent code.
const SchemaVersion = "claude-dispatcher/go-call-reachability/v1"

// errNotImplemented is what a P1 scaffold returns. P3 deletes it.
var errNotImplemented = errors.New("not implemented: this is the D6 P1 scaffold")

// Unit names the package one invocation covers.
//
// ModulePath comes from the `module` line of the go.mod that governs the
// directory and is supplied by the caller rather than read here, because
// reading it would mean opening a file — and this program does not touch the
// filesystem, so that the analysis cannot depend on a working tree the branch
// controls.
//
// PackageDir is the tree-relative posix directory. It is part of the key, and
// not decoration: seven modules in the acceptance repository declare
// `package main`, and two of them (cmd/gates and cmd/iterate, measured on
// feat/G2-adj @ 83b0b97, 2026-08-11) declare a top-level func with the SAME
// name, `VerifyPreservation`. A key spelled `main.VerifyPreservation` collides
// across those two, and under D5's key-only Symbol identity a collision is not
// a near-miss — it is one symbol wearing two declarations.
//
// PackageName distinguishes `foo` from `foo_test` in one directory.
type Unit struct {
	ModulePath  string `json:"module_path"`
	PackageDir  string `json:"package_dir"`
	PackageName string `json:"package_name"`
}

// File is one source file of the unit: its tree-relative posix path, and its
// text. Path is used for messages, for symbol records and for call sites, and
// it must not be opened.
type File struct {
	Path   string `json:"path"`
	Source string `json:"source"`
}

// Request is the single JSON object this program reads from stdin.
type Request struct {
	Schema string `json:"schema"`
	Unit   Unit   `json:"unit"`
	Files  []File `json:"files"`
}

// Symbol is one declared callable, plus the synthetic symbols a root needs.
//
// Key is fully qualified and is the ONLY field any decision reads:
//
//	<module>/<pkgdir-tail>.Name          a top-level func
//	<module>/<pkgdir-tail>.(*T).Name     a method, pointer receiver
//	<module>/<pkgdir-tail>.(T).Name      a method, value receiver
//	<module>/<pkgdir-tail>.<vars>        the synthetic package-var initialiser
//
// The exact spelling is produced by the Python side's go_symbol_key and this
// program must agree with it byte for byte; it is stated once, there, because
// two spellings of one key is the failure this whole effort is about.
//
// Pointer and value receivers get DIFFERENT keys, which is the opposite of the
// fingerprinter's rule (receiverBaseName strips `*` so that changing the
// receiver's pointer-ness is one symbol changing rather than two symbols
// swapping). The two units want opposite things and the divergence is
// deliberate: a signature comparison is asking "did this contract change", for
// which one key is right, and a call graph is asking "does execution arrive
// here", for which `func (T) M` and `func (*T) M` are two bodies and Go
// forbids declaring both.
type Symbol struct {
	Key  string `json:"key"`
	Path string `json:"path"`
	Line int    `json:"line"`
	// Kind is reportage only — "func", "method", "package_var" — and is never
	// part of any comparison. A second comparison surface is a second thing to
	// keep in agreement.
	Kind string `json:"kind"`
}

// Root is one entrypoint, naming the symbol execution enters at.
//
// Evidence is what was read to derive it, in a form a human can check by hand:
// "cmd/gates/main.go:196 func main, package main". Not decoration — a root
// nobody can verify is a root nobody will believe when it produces a BREACH,
// and "derived from the tree rather than hand-listed" is auditable only through
// this field.
type Root struct {
	Symbol   string `json:"symbol"`
	Kind     string `json:"kind"`
	Evidence string `json:"evidence"`
}

// Edge is one caller reaching one callee, at one site, this well known.
// Kind is one of the four in the EDGE GRAMMAR above.
type Edge struct {
	Caller string `json:"caller"`
	Callee string `json:"callee"`
	Kind   string `json:"kind"`
	// Site is `path:line` of the call site itself, which is where a human looks
	// and — for a BREACH — where the missing call has to be written.
	Site string `json:"site"`
}

// Hole is one call site whose target this program could not name.
//
// THE NON-VACUITY RECORD OF THE WHOLE DOCUMENT. It is the quantity that decides
// whether a "no path" answer is conclusive, so a response that reports none of
// them is either a very well-resolved package or a walk that is not counting,
// and those two must not be the same value. Detail is prose for a human and no
// decision reads it.
type Hole struct {
	Caller string `json:"caller"`
	Site   string `json:"site"`
	Detail string `json:"detail"`
}

// ParseError is the go/parser message for the FIRST file that would not parse.
type ParseError struct {
	Path    string `json:"path"`
	Message string `json:"message"`
}

// Response is the single JSON object this program writes to stdout.
//
// ParseError and the four arrays are mutually exclusive. A document carrying
// both, or neither, is AnalyzerFault.HELPER_OUTPUT_INVALID at the caller — as
// is a document with a duplicate Symbol key, an unknown `kind` string, or an
// empty stdout.
//
// When ParseError is absent all four arrays MUST be present, possibly empty.
// `[]` is an answer and `null` is not, and the distinction is what lets the
// caller tell "this package declares nothing" from "this program stopped
// emitting a field". It is also what makes the caller's ignore-unknown-fields
// rule safe: a field renamed without a schema bump shows up as a missing
// required array rather than as a silently smaller graph.
type Response struct {
	Schema     string      `json:"schema"`
	Unit       Unit        `json:"unit"`
	Symbols    []Symbol    `json:"symbols"`
	Roots      []Root      `json:"roots"`
	Edges      []Edge      `json:"edges"`
	Unresolved []Hole      `json:"unresolved"`
	ParseError *ParseError `json:"parse_error,omitempty"`
}

// analyze parses one unit's files and returns its symbols, roots, edges and
// holes, or the first parse error.
//
// NOT IMPLEMENTED. The full definition of what an edge is, how well each kind
// is known, how a closure's calls are attributed and what a build constraint
// does is the EDGE GRAMMAR at the top of this file; it is stated once, there,
// and this function implements it. Do not restate it here — two copies of a
// contract is the defect the sibling unit exists to remove.
//
// P3's obligations that are not in the grammar and are easy to lose:
//
//   - every DECLARATION becomes a Symbol, including the ones nothing
//     references. A symbol absent from the map cannot be a subject, and a
//     subject that cannot be found is UndecidedReason.SUBJECT_UNIDENTIFIED —
//     an abstention — rather than a pass;
//   - a blank-named declaration (`func _()`) is skipped. It cannot be referred
//     to by definition of the language, so it is not callable surface, and one
//     file may legally hold several — which would be a duplicate key. That is
//     go_signature_fingerprint's isBlank, measured on GOROOT/src 2026-08-09,
//     and the reasoning transfers unchanged;
//   - `func init()` is NOT skipped here, which is the opposite of the
//     fingerprinter's rule and for a reason that is exactly inverted. It skips
//     init because an initialiser is not referenceable and therefore has no
//     contract to preserve; this program emits it because Go RUNS it before
//     main, so it is a root, and everything only an init reaches would
//     otherwise read as a false BREACH. Several inits per package are legal, so
//     their keys must be disambiguated — see go_symbol_key.
func analyze(request Request) (Response, error) {
	_ = request
	return Response{}, fmt.Errorf(
		"analyze must parse every file of the unit with go/parser, emit one "+
			"Symbol per declaration, one Root per entrypoint, one Edge per "+
			"resolved call or reference under the EDGE GRAMMAR, and one Hole "+
			"per call site it could not name — with a parse_error document "+
			"and no arrays as the only other permitted answer: %w",
		errNotImplemented,
	)
}

// respond is main's body, with the streams injected so the protocol is testable
// without a process. Returning an error means "this program could not do its
// job" and is the ONLY route to a non-zero exit.
//
// CHOICE (a P1 scaffold implements nothing, and this is the exception): the
// wire protocol is implemented and `analyze` is not. The unit was asked for a
// protocol — what a request is, what a response is, what a schema mismatch
// does — and a protocol whose only executable form raises before it reads is a
// protocol no seal can exercise; that is D4's argument for implementing
// ts_parser_home, applied to the artifact this unit was actually asked for.
// Rejected alternative: stub this too, which is what a literal reading of
// "stubs only" gives and which costs the one property that makes the rest of
// the file checkable — that it compiles, vets clean, and refuses a wrong schema
// today rather than on the day a body lands.
func respond(stdin io.Reader, stdout io.Writer) error {
	raw, err := io.ReadAll(stdin)
	if err != nil {
		return fmt.Errorf("cannot read the request from stdin: %w", err)
	}
	if len(raw) == 0 {
		return fmt.Errorf("empty request on stdin; expected one %s object", SchemaVersion)
	}

	var request Request
	if err := json.Unmarshal(raw, &request); err != nil {
		return fmt.Errorf("request is not a well-formed JSON object: %w", err)
	}
	// Checked FIRST, before the request is read for anything else, so that a
	// helper and a caller who disagree about the edge grammar never exchange
	// a document either of them would act on.
	if request.Schema != SchemaVersion {
		return fmt.Errorf(
			"request schema %q is not %q; a helper and a caller that disagree "+
				"about the edge grammar would compute reachability over graphs "+
				"that mean different things", request.Schema, SchemaVersion)
	}

	response, err := analyze(request)
	if err != nil {
		return err
	}
	response.Schema = SchemaVersion
	response.Unit = request.Unit

	document, err := json.Marshal(response)
	if err != nil {
		return fmt.Errorf("cannot encode the response: %w", err)
	}
	if _, err := stdout.Write(append(document, '\n')); err != nil {
		return fmt.Errorf("cannot write the response to stdout: %w", err)
	}
	return nil
}

func main() {
	if err := respond(os.Stdin, os.Stdout); err != nil {
		fmt.Fprintf(os.Stderr, "go_call_reachability: %v\n", err)
		os.Exit(1)
	}
}
