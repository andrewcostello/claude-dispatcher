// Command go_signature_fingerprint reports the declared signatures of ONE Go
// source file, as a stable JSON fingerprint document.
//
// UNIT D2, P1 SCAFFOLD. This file is a CONTRACT: the request and response
// types below, their JSON tags, and the fingerprint grammar in the comments
// are normative. fingerprintFile is not implemented and main panics. P3 fills
// them in; nothing here may be relaxed without a P4 ruling.
//
// # WHY THIS PROGRAM EXISTS
//
// The Python side of the gate must not contain a Go parser. A second parser
// is a second definition of what a Go signature is, and the two drift the
// first time the language gains syntax — generics being the worked example: a
// hand-rolled reader written before 1.18 silently drops every type parameter,
// and a dropped type parameter is a contract change reported as no change.
// go/ast is the one source of truth; this program is the only thing that reads
// Go, and the Python side only ever compares the strings it emits.
//
// # PROTOCOL
//
// One request object on stdin, which is then closed. One response object on
// stdout, always, followed by a newline. Diagnostics go to stderr and are
// never mixed into stdout.
//
// Exit status and document are separate channels:
//
//	exit 0        stdout holds a valid response document. That INCLUDES a
//	              document whose parse_error is set: unparseable Go is a
//	              successful run of this program and a fact about the file,
//	              which the caller reports as UNCHECKED_UNPARSEABLE.
//	exit non-zero the caller reports ComparatorFault.HELPER_FAILED and does
//	              not read stdout at all. Never exit non-zero for a bad input
//	              FILE; exit non-zero only when this program itself could not
//	              do its job (bad request document, unwritable stdout).
//
// The caller enforces a wall-clock timeout and reports
// ComparatorFault.HELPER_TIMEOUT. This program must therefore never block on
// anything but its own stdin, must not consult the network, must not read the
// filesystem, and must not need GOPATH, a module cache or a build of the
// package the file belongs to: it parses ONE file's text, in isolation, with
// go/parser. Type resolution is deliberately out of scope (see the Python-side
// GoSignatureFingerprinter docstring, which is the full statement of what a Go
// signature is and what is deliberately excluded).
//
// # DETERMINISM IS PART OF THE CONTRACT
//
// Two runs over identical text must produce byte-identical documents, and
// symbols are emitted in DECLARATION order. A fingerprint is only ever
// compared for equality against another run of this same program, so any
// nondeterminism — a map iteration, a timestamp, a path — reads to the caller
// as every symbol having changed, i.e. as a branch that rewrote the world.
package main

// SchemaVersion is echoed on every response and checked by the caller against
// its own GO_HELPER_SCHEMA. A mismatch is ComparatorFault.HELPER_OUTPUT_INVALID
// and never a best-effort read.
//
// Bump it whenever the FINGERPRINT GRAMMAR changes, not only when a field
// moves: fingerprints are compared across two invocations, so a grammar change
// that went unversioned would make an unchanged file look wholly rewritten.
const SchemaVersion = "claude-dispatcher/go-signature-fingerprint/v1"

// Request is the single JSON object this program reads from stdin.
//
// Source travels as TEXT, not as a path. The two revisions the gate compares
// are a merge-base blob and a branch blob read out of git's object store;
// neither is on disk, and a program that took a filename would force the
// caller to materialise temp files and make the answer depend on the working
// tree — which is the thing the branch under judgement controls.
type Request struct {
	Schema string `json:"schema"`
	// Path is used for messages and for nothing else. It must not be opened.
	Path   string `json:"path"`
	Source string `json:"source"`
}

// Symbol is one declared signature.
//
// Symbol is the qualified key the caller matches across revisions:
//
//	Name          a top-level func
//	Recv.Name     a method; Recv is the receiver base type with any '*' and
//	              any type arguments stripped, so a value receiver becoming a
//	              pointer receiver is a CHANGE to a symbol rather than one
//	              symbol removed and another added
//	Name          a type declaration
//	Iface.Method  an interface method
//
// Fingerprint is opaque to the caller: compared for equality and printed,
// never parsed. Rendered through go/printer so gofmt-able differences,
// comments and redundant parens are not changes.
//
// Kind is reportage only ("func", "method", "type", "interface_method") and is
// never part of the comparison — a symbol that changed kind changed its
// fingerprint too, and a second comparison surface is a second thing to keep
// in agreement.
type Symbol struct {
	Symbol      string `json:"symbol"`
	Fingerprint string `json:"fingerprint"`
	Kind        string `json:"kind"`
}

// Response is the single JSON object this program writes to stdout.
//
// Symbols and ParseError are mutually exclusive. A document carrying both, or
// neither, is ComparatorFault.HELPER_OUTPUT_INVALID at the caller — as is a
// document with a duplicate Symbol key, or an empty stdout.
//
// Symbols may be an empty LIST for a file that genuinely declares nothing
// ("package main" and no more). That is an answer. Emitting no document at all
// is a failure. The distinction only survives because this program always
// writes the object, so the caller can tell "no symbols" from "no output" —
// and it must, because the first clears one file and the second would clear
// every branch.
type Response struct {
	Schema  string   `json:"schema"`
	Symbols []Symbol `json:"symbols"`
	// ParseError is the go/parser message, verbatim. Set only when the source
	// is not valid Go; the caller turns it into SourceUnparseable, which is
	// UNCHECKED_UNPARSEABLE and blocks a bodies branch.
	ParseError string `json:"parse_error,omitempty"`
}

// fingerprintFile parses one file's text and returns its symbols in
// declaration order, or a parse error message.
//
// The full definition of what a Go signature is — what is in scope (every
// top-level declaration exported or not; every struct field in declaration
// order, with its tag verbatim; type parameters; variadics; named results;
// alias vs definition) and what is deliberately excluded (function bodies,
// comments, the receiver's variable name, package-level const/var, imports,
// type resolution, build constraints) — is the docstring of
// GoSignatureFingerprinter in role_protocol.py. It is stated once, there, and
// this function implements it. Do not restate it here; two copies of a
// contract is the defect this whole unit exists to remove.
func fingerprintFile(path string, source string) (symbols []Symbol, parseError string) {
	panic("D2 P3: fingerprintFile is not implemented")
}

func main() {
	panic("D2 P3: the go/ast fingerprint helper is not implemented")
}
