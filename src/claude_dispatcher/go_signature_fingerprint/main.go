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

import (
	"encoding/json"
	"fmt"
	"go/ast"
	"go/parser"
	"go/printer"
	"go/token"
	"io"
	"os"
	"strings"
)

// SchemaVersion is echoed on every response and checked by the caller against
// its own GO_HELPER_SCHEMA. A mismatch is ComparatorFault.HELPER_OUTPUT_INVALID
// and never a best-effort read.
//
// Bump it whenever the FINGERPRINT GRAMMAR changes, not only when a field
// moves: fingerprints are compared across two invocations, so a grammar change
// that went unversioned would make an unchanged file look wholly rewritten.
// v2 (2026-08-10) changed the grammar in two places, both to close a FALSE
// NEGATIVE the P2 seals reproduced:
//
//	struct embed  `embedded T` became `embedded:T`. The old marker sat in the
//	              exact column a field NAME occupies, and `embedded` is a legal
//	              identifier, so `struct{ embedded embedded }` and
//	              `struct{ embedded }` rendered the same bytes while only the
//	              second promotes. `:` cannot appear in an identifier, so the
//	              marker is now somewhere a name cannot reach — the same
//	              property `interfaceParts` already had by putting its marker
//	              first.
//	interface     an interface literal's element list carries each method's
//	              SIGNATURE whenever no `Iface.Method` sub-symbol will carry it
//	              (see interfaceParts).
const SchemaVersion = "claude-dispatcher/go-signature-fingerprint/v2"

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
	fset := token.NewFileSet()
	file, err := parser.ParseFile(fset, path, source, parser.SkipObjectResolution)
	if err != nil {
		// Verbatim, per the Response contract. Exit status stays 0: an
		// unparseable file is a successful run of this program.
		return nil, err.Error()
	}

	// Non-nil even when empty: "declares nothing" is an answer and must
	// marshal as [], never as null. See Response.
	symbols = []Symbol{}
	for _, decl := range file.Decls {
		switch d := decl.(type) {
		case *ast.FuncDecl:
			if isBlank(d.Name) || isPackageInit(d) {
				continue
			}
			symbols = append(symbols, funcSymbol(d))
		case *ast.GenDecl:
			// token.CONST, token.VAR and token.IMPORT are deliberately
			// excluded; the reasons are in the Python-side docstring.
			if d.Tok != token.TYPE {
				continue
			}
			for _, spec := range d.Specs {
				if ts, ok := spec.(*ast.TypeSpec); ok && !isBlank(ts.Name) {
					symbols = append(symbols, typeSymbols(ts)...)
				}
			}
		}
	}
	return symbols, ""
}

// isBlank reports whether a declaration is named `_`.
//
// A blank-named declaration is skipped, and this is a CORRECTNESS requirement
// rather than a tidy-up. The blank identifier cannot be referenced from
// anywhere by definition of the language, so `func _()` and `type _ T` are not
// callable surface and there is no contract in them to preserve. More sharply:
// one file may legally hold SEVERAL of them — `stringer` emits a `func _()`
// compile-time assertion per constant block, and crypto/tls/common_string.go
// in GOROOT carries three — so emitting them would produce duplicate symbol
// keys, which the caller correctly reads as ComparatorFault.
// HELPER_OUTPUT_INVALID. Ordinary generated Go would have blamed the machine
// and left the branch UNDETERMINED. Measured on GOROOT/src, 2026-08-09.
//
// Struct fields named `_` are NOT skipped: padding is positional, it is part
// of the declared shape, and it lives inside a fingerprint rather than being a
// key, so it cannot collide.
func isBlank(name *ast.Ident) bool {
	return name == nil || name.Name == "_"
}

// isPackageInit reports whether a declaration is a package initialiser.
//
// Skipped for the same two reasons as the blank identifier, and the language
// spec supplies both. `func init` may not be referred to from anywhere, so it
// is not callable surface; and a file may declare SEVERAL of them, which the
// spec permits explicitly and which real code uses (GOROOT's runtime/proc.go
// and cmd/go/main.go both do). Emitting them would produce duplicate keys and
// turn an ordinary file into ComparatorFault.HELPER_OUTPUT_INVALID. Measured
// on GOROOT/src, 2026-08-09: 11 files of 4,505.
//
// Nothing is lost by the skip even in principle: the spec fixes an
// initialiser's signature at no parameters and no results, so its fingerprint
// is a constant and could never report a change.
//
// A METHOD named `init` is NOT this — `func (s *S) init()` is an ordinary
// in-package method, is referenceable, is sealable by an in-package test, and
// only one may exist per receiver. Hence the receiver check.
func isPackageInit(decl *ast.FuncDecl) bool {
	return decl.Recv == nil && decl.Name != nil && decl.Name.Name == "init"
}

// renderFset is deliberately EMPTY and shared. go/printer asks it for the line
// of every position; a file set that knows none of them reports line 0 for all
// of them, so the printer sees no line breaks in the source and emits one line.
// That is what makes a declaration reflowed across several lines fingerprint
// identically to the same declaration on one — the gofmt-able difference the
// contract promises is not a change. Comments are not parsed at all, so none
// can reach the output.
var renderFset = token.NewFileSet()

// render is the fallback renderer: one AST node, printed through go/printer.
//
// Every composite type this contract has an opinion about (struct bodies,
// interface bodies) is rendered by the functions below instead, because
// go/printer preserves field GROUPING (`A, B int` and `A int; B int` print
// differently) and that is a spelling difference, not a contract change.
// render is what everything else resolves to, and it is deterministic.
func render(node ast.Node) string {
	var out strings.Builder
	if err := printer.Fprint(&out, renderFset, node); err != nil {
		// Unreachable for a parsed node with a strings.Builder sink, but a
		// silent "" here would be a fingerprint that matches every other
		// unprintable one, so it is made loud and unmistakable instead.
		return "<unprintable " + err.Error() + ">"
	}
	return out.String()
}

// typeFingerprint renders one type expression.
//
// Struct and interface literals are rendered by this file so that field
// grouping and member order are normalised; everything else goes to render.
// The recursion is one level deep by construction — a struct nested inside a
// slice or map type falls through to render, which keeps its grouping. That is
// a FALSE POSITIVE (a regrouped nested struct reads as a change) and never a
// false negative, which is the direction this gate is allowed to be wrong in.
func typeFingerprint(expr ast.Expr) string {
	switch t := expr.(type) {
	case *ast.StructType:
		return "struct{" + structFields(t.Fields) + "}"
	case *ast.InterfaceType:
		// withSignatures: an interface literal reached through here is a TYPE
		// EXPRESSION — an alias' right-hand side, a field, parameter, result or
		// constraint type, or a literal embedded in another interface — and
		// nothing above it emits Iface.Method sub-symbols. If the element list
		// does not carry the signature, nothing does.
		elements, _ := interfaceParts(t.Methods, true)
		return "interface{" + elements + "}"
	}
	return render(expr)
}

// fieldSignature renders a parameter, result or type-parameter list.
//
// Grouped declarations are EXPANDED — `func f(src, dst string)` and
// `func f(src string, dst string)` are the same declaration spelled two ways —
// so a regrouping is not a change while a reorder still is. An unnamed entry
// renders as its type alone, which is how `func f(string)` stays distinct from
// `func f(s string)`.
func fieldSignature(list *ast.FieldList) string {
	if list == nil {
		return ""
	}
	parts := make([]string, 0, len(list.List))
	for _, field := range list.List {
		rendered := typeFingerprint(field.Type)
		if len(field.Names) == 0 {
			parts = append(parts, rendered)
			continue
		}
		for _, name := range field.Names {
			parts = append(parts, name.Name+" "+rendered)
		}
	}
	return strings.Join(parts, ", ")
}

// typeParameters renders `[T any, U comparable]`, or "" when there are none.
func typeParameters(list *ast.FieldList) string {
	if list == nil || len(list.List) == 0 {
		return ""
	}
	return "[" + fieldSignature(list) + "]"
}

// results renders the result list, ALWAYS parenthesised when there is one, so
// that `func f() error` and `func f() (error)` are the same fingerprint.
func results(list *ast.FieldList) string {
	if list == nil || len(list.List) == 0 {
		return ""
	}
	return " (" + fieldSignature(list) + ")"
}

// signature renders everything after the `func` keyword and the receiver.
func signature(name string, fn *ast.FuncType) string {
	return name + typeParameters(fn.TypeParams) +
		"(" + fieldSignature(fn.Params) + ")" + results(fn.Results)
}

// receiverBaseName strips `*`, parentheses and any type arguments to get the
// key half of a method's `Recv.Name`, so a value receiver becoming a pointer
// receiver is a CHANGE to one symbol rather than one removed and one added.
func receiverBaseName(expr ast.Expr) string {
	for {
		switch e := expr.(type) {
		case *ast.StarExpr:
			expr = e.X
		case *ast.ParenExpr:
			expr = e.X
		case *ast.IndexExpr:
			expr = e.X
		case *ast.IndexListExpr:
			expr = e.X
		case *ast.Ident:
			return e.Name
		case *ast.SelectorExpr:
			return e.Sel.Name
		default:
			return render(expr)
		}
	}
}

// funcSymbol is one top-level func or method.
//
// The receiver's TYPE is in the fingerprint (pointer-ness included); the
// receiver's variable NAME is not, and that exclusion is ruled at
// GO_SIGNATURE_EDIT_RULINGS.
func funcSymbol(decl *ast.FuncDecl) Symbol {
	name := decl.Name.Name
	if decl.Recv == nil || len(decl.Recv.List) != 1 {
		return Symbol{
			Symbol:      name,
			Fingerprint: "func " + signature(name, decl.Type),
			Kind:        "func",
		}
	}
	receiver := decl.Recv.List[0].Type
	return Symbol{
		Symbol:      receiverBaseName(receiver) + "." + name,
		Fingerprint: "func (" + typeFingerprint(receiver) + ") " + signature(name, decl.Type),
		Kind:        "method",
	}
}

// structFields renders every field in DECLARATION order: name, type, tag
// verbatim, and whether the field is embedded — the last marked explicitly
// rather than inferred from the absence of a name, because a fingerprint that
// needs to be reasoned about is one two shapes can collide in.
//
// The marker is `embedded:` and the colon is the whole of it. An explicit
// marker only works while the marker cannot be SPELLED by the other branch, and
// v1's `embedded ` could be: it sat in the exact position a field name occupies
// one branch below, and `embedded` is a legal identifier. So
//
//	type S struct{ embedded embedded }   // a named field, promoting nothing
//	type S struct{ embedded }            // an embed, promoting everything
//
// rendered the same bytes, and adding or removing an embed — Go's only
// promotion mechanism, and therefore what decides which interfaces the outer
// type satisfies — was no change at all. `:` may not appear in an identifier,
// so the marker now lives where a name cannot reach it, which is the property
// interfaceParts already had by putting its marker FIRST.
//
// Inferring the embed's name from its type instead would not do: every embed
// would then collide with the field that names its own type (`Foo` vs
// `Foo Foo`), trading a rare collision for a universal one.
func structFields(list *ast.FieldList) string {
	if list == nil {
		return ""
	}
	parts := make([]string, 0, len(list.List))
	for _, field := range list.List {
		tag := ""
		if field.Tag != nil {
			// The raw literal, quoting included: a tag is a string the
			// runtime parses, and this gate does not decide which of two
			// spellings a reflection library agrees with.
			tag = " " + field.Tag.Value
		}
		rendered := typeFingerprint(field.Type)
		if len(field.Names) == 0 {
			parts = append(parts, "embedded:"+rendered+tag)
			continue
		}
		for _, name := range field.Names {
			parts = append(parts, name.Name+" "+rendered+tag)
		}
	}
	return strings.Join(parts, "; ")
}

// interfaceParts splits an interface body into its rendered element list and
// its methods.
//
// The `method ` marker LEADS, and unlike v1's struct marker it cannot be
// shadowed: the other branch renders a type expression, and no type expression
// renders as `method X`.
//
// EVERY METHOD'S SIGNATURE IS CARRIED SOMEWHERE, EXACTLY ONCE. The two callers
// differ in where "somewhere" is, which is what withSignatures selects:
//
//	false  typeSymbols, for a top-level interface DEFINITION. It emits one
//	       `Iface.Method` sub-symbol per named method, and that sub-symbol holds
//	       the signature. Repeating it in the element list would report one edit
//	       twice — the same split the Python side makes between a class
//	       fingerprint and its methods.
//	true   typeFingerprint, for an interface literal in any other position:
//	       an alias' right-hand side, a struct field, parameter, result or
//	       constraint type, or a literal embedded in another interface. NOTHING
//	       above those emits sub-symbols, so v1 stored the signature nowhere at
//	       all and retyping a method of such a literal — source-breaking for
//	       every implementation — was reported as no change. A renamed, added or
//	       removed method was always caught, because the element list carries
//	       names; only the signature was lost, which is why the hole read as
//	       "probes report a change" from the outside.
//
// A method named `_` gets its signature inline even when withSignatures is
// false, because typeSymbols skips blank keys and would otherwise leave that
// one method's signature unstored. The invariant is the point: the signature is
// in the element list precisely when no sub-symbol will carry it.
//
// The signature is rendered by `signature`, never by go/printer, so parameter
// GROUPING and line breaks stay normalised: `Do(a, b int)` and `Do(a int, b
// int)` are one declaration spelled twice, and rendering the literal through
// go/printer to recover the signature would have carried the spelling with it.
func interfaceParts(list *ast.FieldList, withSignatures bool) (elements string, methods []*ast.Field) {
	if list == nil {
		return "", nil
	}
	parts := make([]string, 0, len(list.List))
	for _, field := range list.List {
		if len(field.Names) == 1 {
			if fn, ok := field.Type.(*ast.FuncType); ok {
				name := field.Names[0].Name
				if withSignatures || isBlank(field.Names[0]) {
					parts = append(parts, "method "+signature(name, fn))
				} else {
					parts = append(parts, "method "+name)
				}
				methods = append(methods, field)
				continue
			}
		}
		// An embedded interface, or a type-set element such as `~int | string`.
		parts = append(parts, "embedded "+typeFingerprint(field.Type))
	}
	return strings.Join(parts, "; "), methods
}

// typeSymbols is one type declaration, plus one symbol per interface method.
func typeSymbols(spec *ast.TypeSpec) []Symbol {
	name := spec.Name.Name
	head := "type " + name + typeParameters(spec.TypeParams)

	// The `=` is semantic, not spelling, so it is checked before the shape of
	// the right-hand side. An alias to an interface literal contributes no
	// Iface.Method symbols: the whole right-hand side is inside this one
	// fingerprint, so a changed method is still a change — reported against
	// the alias rather than against the method. That is an invariant and not
	// only a description: it holds because typeFingerprint asks interfaceParts
	// for the signatures, which is what the branch below deliberately does not.
	if spec.Assign.IsValid() {
		return []Symbol{{
			Symbol:      name,
			Fingerprint: head + " = " + typeFingerprint(spec.Type),
			Kind:        "type",
		}}
	}

	// A DEFINITION of an interface is the one shape with sub-symbols, so it is
	// the one shape whose element list may omit signatures. It is rendered here
	// rather than through typeFingerprint for exactly that reason.
	iface, ok := spec.Type.(*ast.InterfaceType)
	if !ok {
		return []Symbol{{
			Symbol:      name,
			Fingerprint: head + " " + typeFingerprint(spec.Type),
			Kind:        "type",
		}}
	}
	elements, methods := interfaceParts(iface.Methods, false)
	symbols := []Symbol{{
		Symbol:      name,
		Fingerprint: head + " interface{" + elements + "}",
		Kind:        "type",
	}}
	for _, method := range methods {
		if isBlank(method.Names[0]) {
			continue
		}
		fn := method.Type.(*ast.FuncType)
		member := method.Names[0].Name
		symbols = append(symbols, Symbol{
			Symbol:      name + "." + member,
			Fingerprint: "func " + signature(member, fn),
			Kind:        "interface_method",
		})
	}
	return symbols
}

// respond is main's body, with the streams injected so the protocol is
// testable without a process. Returning an error means "this program could not
// do its job" and is the ONLY route to a non-zero exit.
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
	if request.Schema != SchemaVersion {
		return fmt.Errorf(
			"request schema %q is not %q; a helper and a caller that disagree "+
				"about the grammar would compare fingerprints that mean "+
				"different things", request.Schema, SchemaVersion)
	}

	symbols, parseError := fingerprintFile(request.Path, request.Source)
	response := Response{Schema: SchemaVersion}
	if parseError != "" {
		// Mutually exclusive with Symbols, which stays nil.
		response.ParseError = parseError
	} else {
		response.Symbols = symbols
	}

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
		fmt.Fprintf(os.Stderr, "go_signature_fingerprint: %v\n", err)
		os.Exit(1)
	}
}
