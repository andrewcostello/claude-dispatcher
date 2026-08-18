// Reads a Go file and reports (a) its STATE_MACHINE declaration and (b) the
// members of every enum-shaped const group, as JSON on stdout.
//
// It does NOT decide anything. The rules live once, in Python's
// state_machine.check_parsed, so this reader cannot drift into a laxer answer
// than the Python reader gives for the same declaration.
//
// The declaration is a Go const holding JSON:
//
//	const StateMachine = `{"name": "...", "state_enum": "BetState", ...}`
//
// JSON rather than a Go composite literal because the format is language-neutral
// and a backtick const is what a Go AST can read without evaluating anything. A
// composite literal would need a shared type, and a shared type needs an import,
// and an import needs a module cache.
//
// Go has no enum. The equivalent is a const group with a named type, in either
// spelling:
//
//	type BetState string
//	const ( BetStateAccepted BetState = "accepted" ... )
//
//	type BetState int
//	const ( BetStateAccepted BetState = iota; BetStateArmed )
//
// The iota form gives the type on the FIRST spec only and the rest inherit it,
// so the walk carries the last seen type forward inside one const block. Missing
// that is how a reader silently finds one member of a nine-member enum.
package main

import (
	"encoding/json"
	"fmt"
	"go/ast"
	"go/parser"
	"go/token"
	"os"
	"sort"
	"strconv"
)

const declName = "StateMachine"

type output struct {
	Declaration map[string]any      `json:"declaration"`
	Enums       map[string][]string `json:"enums"`
	Why         string              `json:"why"`
}

func main() {
	if len(os.Args) != 2 {
		fail("usage: go-state-machine <file.go>")
	}
	src, err := os.ReadFile(os.Args[1])
	if err != nil {
		fail(fmt.Sprintf("cannot read %s: %v", os.Args[1], err))
	}
	fset := token.NewFileSet()
	file, err := parser.ParseFile(fset, os.Args[1], src, parser.ParseComments)
	if err != nil {
		fail(fmt.Sprintf("file does not parse: %v", err))
	}

	out := output{Enums: map[string][]string{}}
	decl, why := findDeclaration(file)
	out.Declaration = decl
	out.Why = why
	collectEnums(file, out.Enums)
	emit(out)
}

// findDeclaration returns the decoded JSON in the `StateMachine` const/var, or a
// reason it could not. A present-but-unreadable declaration is NOT reported as
// absent: "no declaration" and "a broken declaration" are different faults and
// the Python side maps them to different names.
func findDeclaration(file *ast.File) (map[string]any, string) {
	var lit string
	found := false
	for _, d := range file.Decls {
		gen, ok := d.(*ast.GenDecl)
		if !ok || (gen.Tok != token.CONST && gen.Tok != token.VAR) {
			continue
		}
		for _, spec := range gen.Specs {
			vs, ok := spec.(*ast.ValueSpec)
			if !ok {
				continue
			}
			for i, name := range vs.Names {
				if name.Name != declName || i >= len(vs.Values) {
					continue
				}
				bl, ok := vs.Values[i].(*ast.BasicLit)
				if !ok || bl.Kind != token.STRING {
					return nil, declName + " is not a string literal holding JSON"
				}
				unquoted, err := strconv.Unquote(bl.Value)
				if err != nil {
					return nil, fmt.Sprintf("%s is not an unquotable string: %v", declName, err)
				}
				lit, found = unquoted, true
			}
		}
	}
	if !found {
		return nil, "no module-level " + declName + " literal"
	}
	var raw map[string]any
	if err := json.Unmarshal([]byte(lit), &raw); err != nil {
		return nil, fmt.Sprintf("%s does not hold valid JSON: %v", declName, err)
	}
	return raw, ""
}

// collectEnums groups const identifiers by their named type. Within one const
// block the type is carried forward, because the iota spelling states it once.
func collectEnums(file *ast.File, into map[string][]string) {
	for _, d := range file.Decls {
		gen, ok := d.(*ast.GenDecl)
		if !ok || gen.Tok != token.CONST {
			continue
		}
		lastType := ""
		for _, spec := range gen.Specs {
			vs, ok := spec.(*ast.ValueSpec)
			if !ok {
				continue
			}
			if t := typeName(vs.Type); t != "" {
				lastType = t
			}
			if lastType == "" {
				continue
			}
			for _, name := range vs.Names {
				if name.Name == "_" {
					continue // the skipped-zero idiom is not a member
				}
				into[lastType] = append(into[lastType], name.Name)
			}
		}
	}
	for k := range into {
		sort.Strings(into[k])
	}
}

func typeName(e ast.Expr) string {
	switch t := e.(type) {
	case *ast.Ident:
		return t.Name
	case *ast.SelectorExpr: // pkg.Type — named, but not ours to check
		return t.Sel.Name
	}
	return ""
}

func emit(out output) {
	enc := json.NewEncoder(os.Stdout)
	enc.SetEscapeHTML(false)
	if err := enc.Encode(out); err != nil {
		fail(fmt.Sprintf("cannot encode output: %v", err))
	}
}

// fail writes a JSON envelope, never a bare message: the caller decodes stdout
// and a plain string would surface as "unparseable helper output", which hides
// the real reason.
func fail(why string) {
	emit(output{Enums: map[string][]string{}, Why: why})
	os.Exit(1)
}
