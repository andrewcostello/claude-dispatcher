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
// call to `pkg.F` in another package is emitted anyway, spelled with the
// callee's IMPORT PATH, which is what go/types gives this program and the only
// name it has for a package it did not parse. The Python side then drops any
// edge whose callee is not declared anywhere in the tree, which is CallGraph's
// own recorded rule ("edges are kept only when BOTH ends are declared in the
// tree").
//
// P4 RULING (D6 adjudication round 3, 2026-08-11) — THE SENTENCE THAT STOOD
// HERE WAS FALSE AND IS STRUCK. It read: "the import block of the calling file
// names the import path, so the callee's KEY is derivable without the callee's
// source." The import path is derivable. The KEY is not, and the difference
// manufactures a BREACH.
//
// `go_symbol_key`'s qualifier is `<module_path>/<TREE-relative package_dir>`.
// The acceptance fixture's `cmd/gates` is therefore keyed
// `…/claude-workflow/gates/cmd/gates.F` while its IMPORT PATH — the only
// spelling this program can produce for it from another package — is
// `…/claude-workflow/gates.F`. The two strings differ whenever the module root
// is not the tree root, which is the acceptance fixture's own shape and every
// monorepo's. A helper-emitted cross-package callee key then matches nothing
// the callee's own unit declared, CallGraph's both-ends rule drops a REAL
// production edge, and a function production calls reads as uncalled.
//
// That is a false accusation of dark code in the mechanism whose whole purpose
// is accusing code of being dark, so it is the worst failure this unit has.
// The reconciliation lives on the Python side, in
// `go_reachability._import_path_qualifiers` and `_join_callee`; read those two
// before changing anything about how this program spells a callee, and read
// their WHAT THIS DOES NOT CLOSE list before assuming they close it.
//
// TWO SPELLINGS RECONCILED BY A REPAIR IS WEAKER THAN ONE SPELLING, and the
// ruling records why one spelling was NOT adopted: making the qualifier the
// import path requires computing the import path, and `<module path> +
// <in-module directory>` is not it for a vendored package or for a `replace`
// that renames. The only authority on a package's import path is the Go
// toolchain, which this program already execs. See the escalation recorded on
// `_import_path_qualifiers`.
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
// anything but its own stdin, and must not consult the network.
//
// P4 RULING (D6 adjudication, 2026-08-11) — TYPE RESOLUTION, AND WHAT IT COSTS.
// An earlier draft of this paragraph also said "must not read the filesystem
// … it parses the request's TEXT, in isolation, with go/parser". That is
// STRUCK, because the operator has ratified type-checking with go/types, and
// go/types cannot be run in that isolation. The rest of the paragraph stands.
//
// `analyze` type-checks each unit with go/types and
// `importer.ForCompiler(fset, "source", nil)`. THE IMPORTER CHOICE IS
// LOAD-BEARING AND MUST NOT BE "SIMPLIFIED" TO importer.Default().
// Measured 2026-08-11 under `env -u HOME -u GOCACHE -u XDG_CACHE_HOME
// GOPROXY=off GOMODCACHE=/nonexistent GOPATH=/nonexistent`:
//
//	importer.Default()               FAILS — "GOCACHE is not defined and
//	                                 neither $XDG_CACHE_HOME nor $HOME are
//	                                 defined". It needs a writable build cache.
//	importer.ForCompiler(…,"source") SURVIVES. It reads GOROOT/src instead of
//	                                 cached export data.
//
// The stdlib-only CHOICE is amended in SCOPE and not in rationale: it now
// means "no third-party MODULES", and go/types is standard library. What the
// original rationale bought — no network fetch, no writable HOME on the gate
// path — is preserved and was re-measured above.
//
// THREE COSTS, measured rather than predicted, because a ruling that records
// only the benefit is not a ruling:
//
//  1. IT READS THE FILESYSTEM AND IT EXECS THE GO COMMAND. The source importer
//     resolves imports through `go list`. Measured with GOROOT=/nonexistent:
//     "could not import strings (go/build: go list strings: fork/exec
//     /nonexistent/bin/go: no such file or directory)". So a working Go
//     toolchain and GOROOT/src are analysis-time inputs, not just build-time
//     ones, and imports resolve relative to the PROCESS WORKING DIRECTORY —
//     `_run_go_reachability_helper` must therefore run this program with its
//     cwd inside the unit's module or every cross-module import fails. The
//     property the struck sentence was protecting — that the analysis cannot
//     depend on a working tree the branch controls — is genuinely WEAKENED
//     here, and it is weakened knowingly: GOROOT, cwd and the on-disk module
//     graph are now verdict inputs. Source still travels as TEXT in the
//     request and the files named there are still the unit; what is new is
//     that resolving their IMPORTS touches the disk.
//
//     P4 QUANTIFIES THE EXPOSURE (D6 adjudication round 2, 2026-08-11),
//     because "knowingly weakened" is not a shape an operator can decide
//     against. THE QUESTION IS: what can a branch under judgement change,
//     other than the source it is being judged on, that moves a verdict? The
//     answer is NOT "nothing". It is a `go.mod` edit, a `replace` directive, a
//     `go.work` file, or a vendored source tree — all four measured, at
//     `feat/D6-adj2`, 2026-08-11, under the hostile environment above:
//
//     DELETING ONE LINE — a `replace` — with the Go source BYTE-IDENTICAL
//     takes the unit from 0 type errors and a clean graph to "could not
//     import example.com/dep". Under the type-error ruling below that unit
//     must travel the parse_error channel, so it reaches the caller as
//     CallGraph.unreadable_paths and `check_subject` step 1b abstains THE
//     WHOLE TREE with PARSE_FAILED. A one-line `go.mod` edit therefore
//     converts every finding in the repository into an abstention, and an
//     abstention is not a BREACH. That is the exposure at its sharpest: a
//     route from BREACH to silence, costing one line.
//
//     ADDING a `go.work` naming the sibling restores resolution with no
//     `replace` at all — 0 type errors again — so a file the branch CREATES
//     is a verdict input on its own.
//
//     EDITING the `module` line renames EVERY Symbol key in that module
//     (measured: `example.com/app/..light` becomes
//     `example.com/RENAMED/..light`). Pointing two modules at ONE module path
//     is the collision `PackageDir` exists to prevent, and that one is caught
//     rather than silent: it lands as a duplicate key across two units, which
//     the caller already refuses.
//
//     A VENDORED SOURCE TREE is the same lever as `replace`. Cost 2 below
//     establishes that a dependency needs its SOURCE on disk, and the branch
//     controls the disk.
//
//     NOTHING CLOSES THIS TODAY, and the near-miss is worth naming so nobody
//     mistakes it for a fix: `scripts/check_body_branch.sh` reads THIS HELPER
//     out of the base revision when its own `src/` lies inside the checkout
//     under judgement. That protects the ANALYZER. The `go.mod` being read
//     here belongs to the JUDGED repository, which is the branch, and no rule
//     reaches it.
//
//     WHAT IT DOES NOT BUY THE BRANCH: none of the four is a route to a false
//     `OK`. `Disposition.ABSTAIN` is "never suppressible, never declarable,
//     and always counted separately from OK", the unresolved-call count is a
//     first-class report field, and `unreadable_paths` names the file. The
//     branch can make the mechanism go quiet; it cannot make it agree. That is
//     the decision in front of the operator, with the shape stated rather than
//     footnoted.
//
//  2. A DEPENDENCY MUST HAVE ITS SOURCE ON DISK. Measured: a module requiring
//     `golang.org/x/text` with no module cache fails with "could not import";
//     the same dependency reached through a `replace` to a sibling directory
//     resolves cleanly under the identical hostile environment. So the
//     constraint is "source on disk", not "a module cache", and it binds
//     nothing in the acceptance repository today — all seven cmd/ modules
//     declare no `require` at all, measured 2026-08-11.
//
//  3. COST ON THE GATE PATH: 2.7 s for all seven modules of the acceptance
//     repository, one process per module, hostile environment, measured
//     2026-08-11 at 83b0b97. That is a PACKAGE-scale price and it is recorded
//     here the way the TypeScript comparator's 169 ms/file is recorded there.
//
// A TYPE ERROR IS NOT SILENCE. This is the second sentence this contract owed.
// `types.Config.Error` swallows errors by design and `conf.Check` returns a
// partially populated Info, so a package that does not type-check looks
// EXACTLY like one that does. Measured 2026-08-11 on a package with
// `var s string = 42`: 1 type error reported, and the walk still resolved
// every one of its 5 call sites — UNRESOLVED=0, a full graph, nothing in the
// output distinguishing it from a clean run. That is a fail-open wearing a
// type-checker's clothes, and it is the exact defect class this mechanism
// exists to catch, so:
//
//	`analyze` MUST count the type errors it was handed and MUST NOT emit a
//	graph document when that count is non-zero. A unit that did not
//	type-check is reported the way a unit that did not PARSE is — through
//	parse_error, so it reaches the caller as CallGraph.unreadable_paths and
//	the whole tree abstains with UndecidedReason.PARSE_FAILED.
//
// Rejected alternative: emitting the partial graph and trusting that lost
// edges show up as holes. They do not have to. A lost EDGE is not a hole, and
// a production closure that silently shrank makes a reached subject look
// unreached — which is a manufactured BREACH, the one direction
// anti-requirement 2 forbids. The live instance is build tags: go/parser does
// not evaluate `//go:build`, so two files guarded by mutually exclusive
// constraints declaring one name type-check as "X redeclared in this block".
// Measured 2026-08-11: 2 type errors, and the run still reported
// UNRESOLVED=0. `git grep -c "go:build"` over cmd/**/*.go matches nothing in
// the acceptance repository, so this binds nothing there today and is
// certainly not hypothetical elsewhere.
//
// Also measured, and both behave correctly rather than needing a rule:
// GENERICS type-check clean (a call through a type parameter's func value is
// a genuine unresolved site and is reported as one; note that a generic
// instantiation `F[T](x)` puts an *ast.IndexExpr in the Fun slot, so a walk
// that handles only Ident and SelectorExpr turns EVERY generic call into a
// false hole), and CGO fails its import (`could not import C`) and degrades to
// an unresolved call — the abstaining direction.
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
//	v(x), v a SOLE-BINDING FUNC LITERAL — the     (no edge)    no
//	  four obligations below                                   and NO hole
//	f()(x), fns[i](x), c.handler(x), reflection   (no edge)    unresolved[]
//
// P4 RULING (D6 adjudication, 2026-08-11) — A NAMED OUT-OF-TREE TARGET IS NOT
// A HOLE, AND THIS IS THE ROW THE FIRST REFERENCE WALK GOT WRONG.
// `unresolved[]` means THE WALK COULD NOT NAME THE TARGET. It does not mean
// "the target is not in this tree". A call whose target IS named and turns out
// to live outside the tree — `now.UTC()`, `re.FindAllStringSubmatch(…)`,
// `cmd.CombinedOutput()` — produces NO edge (both ends must be in the tree)
// and NO hole. It is a fully answered question whose answer is "nothing here".
//
// The two must never be conflated, because a hole ABSTAINS: every entry inside
// the production closure downgrades a would-be verdict to
// UndecidedReason.DYNAMIC_EDGE. A walk that files answered questions as holes
// abstains on everything and is indistinguishable from a walk that cannot see.
//
// This is not a narrowing of DYNAMIC_EDGE and it is not an assumption of
// harmlessness. It is total, and the totality is the point: a call site
// `x.M(…)` that lands on an in-tree method lands on a method NAMED M, because
// Go's method-call syntax names the method. So emitting one "interface" edge
// per in-tree method named M is a SUPERSET of the possible in-tree targets,
// and the residue is empty by construction rather than by assumption. Nothing
// is ever filed as harmless because it could not be typed.
//
// Measured under `feat/D6-seals` @ 5669cb7, 2026-08-11, over the vendored
// acceptance tree, by two independent walks: a name-level walk obeying the row
// above and a full go/types walk. The production closure holds 104 symbols;
// the first reference implementation reported 55 unresolved sites in it, of
// which ~50 were method calls through receivers it could not type. Under this
// row that population is not holes at all — only 2 of the 50 even name a
// method that exists in the tree — and BOTH walks agree the production closure
// holds exactly SEVEN unresolved sites, the same seven, every one of them a
// call through a FUNCTION VALUE. Type information moved 50 sites and moved the
// VERDICT on none of them.
//
// (Round 2 re-measured this with a third walk that classifies every
// *ast.CallExpr form rather than one — 1,114 SelectorExpr, 1,000 Ident, 17
// ArrayType conversions, 1 immediately-invoked FuncLit, nothing else — and
// agrees on the seven exactly. It corrected 106 to 104: round 1 spelled the
// synthetic package-var initialiser once per FILE and go_symbol_key spells it
// once per PACKAGE, and four such files sit in two packages. The 1,054 sites
// naming an out-of-tree target are the population this row is about. Five of
// the seven holes are cleared by the SOLE-BINDING FUNC LITERAL rule ruled
// below; the two `cancel` sites are not, and the argument for clearing them is
// refused below too.)
//
// P4 RULING (D6 adjudication round 2, 2026-08-11) — THE SOLE-BINDING FUNC
// LITERAL RULE IS ADOPTED. A call `v(…)` through a func-typed variable is NOT a
// hole, and produces no edge, when all four obligations below are DISCHARGED.
// It is a positive claim about what `v` holds, never "we could not find another
// assignment, so assume there is none" — an absence-based rule is the fail-open
// this codebase refuses, and the distinction is the whole of this ruling.
//
// THE POSITIVE CLAIM THIS RULE RESTS ON is a theorem about Go and not an
// observation about a tree: THE IDENTIFIERS THAT CAN NAME A FUNCTION-LOCAL
// VARIABLE ARE EXACTLY THE IDENTIFIERS INSIDE THAT FUNCTION'S OWN DECLARATION.
// Go gives no other way to reach a local — no package-scope name for it, no
// reflection route to a stack slot — except through its ADDRESS, which is
// obligation 3b. So the region that must be searched is one AST subtree, finite
// and wholly present in this unit, and the search over it is EXHAUSTIVE rather
// than best-effort. That is what makes the conclusion a claim rather than a
// failure to find a counterexample.
//
//	OBLIGATION 1 — LOCALITY. The binding occurrence of `v` is inside the
//	  BODY of the enclosing named declaration D. Established by finding it,
//	  not by failing to find one elsewhere. A package-level `var` of func
//	  type FAILS here (its binding is not in any D), and so does a
//	  PARAMETER of func type (bound by D's signature, so its value is the
//	  caller's and not visible here).
//	OBLIGATION 2 — SOLE BINDING IS A LITERAL. That one binding is a `:=` or
//	  a `var` spec whose initialiser, positionally matched to this name, is
//	  a single *ast.FuncLit. A TUPLE binding fails: the value then comes
//	  from one multi-valued expression and no literal is named. So does a
//	  named func on the right (`f := target`) — sound to add, and NOT
//	  claimed here — a range clause, and a declaration with no initialiser.
//	OBLIGATION 3 — EVERY OCCURRENCE IS A READ. Enumerate every identifier
//	  in D that denotes `v` and show each one is a READ, by an exhaustive
//	  switch on its PARENT node that DECLINES on any node type it does not
//	  classify.
//	OBLIGATION 3b — NO `&v`. Taking the address is the one route by which
//	  `v`'s value can change with no syntax naming `v` (`p := &v; *p = g`),
//	  and it is the clause that makes obligation 3 a claim about the VALUE
//	  rather than about the syntax.
//
// OBLIGATION 3 IS STATED FAIL-CLOSED, AND THE REASON IS A MEASURED DEFECT IN
// THIS ADJUDICATION'S OWN FIRST DRAFT. That draft enumerated the ASSIGNING
// constructs — *ast.AssignStmt — and cleared anything it did not recognise.
// Measured 2026-08-11: `for _, f = range fns` is an *ast.RangeStmt and not an
// *ast.AssignStmt, so it walked straight through and the rule CLEARED a call
// whose target is rebound once per iteration. An enumeration of the forms that
// WRITE is an open list that grows with the language and defaults to CLEAR; the
// inverted form — every occurrence must be shown to be a read — is closed under
// language growth, because a new writing construct still has to name `v` and
// its parent lands in the switch's decline branch. This is the repository's
// "be exhaustive, raise on unknown" rule applied to a soundness argument.
//
// WHY A CLEARED CALL PRODUCES NO EDGE RATHER THAN A "direct" ONE. The
// ATTRIBUTION rule below gives a closure no symbol of its own: the literal's
// calls are already attributed to D, and the call site is inside D too, so
// caller and callee are the same symbol. A cleared site is a fully answered
// question whose answer is "this reaches code already attributed here" — the
// same shape as a named out-of-tree target, and for the same reason it is not a
// hole. Nothing is lost from the graph and nothing is invented in it.
//
// MEASURED under `feat/D6-adj2`, 2026-08-11, by an implementation of the four
// obligations run over a 32-site package written to attack them. Every shape
// lands where soundness requires: reassignment later in the same scope, in an
// `if` branch, inside a nested literal, on another goroutine, behind a `goto`,
// in a `select` comm clause and through `for _, f = range` all DECLINE;
// `&v` taken locally and `&v` passed to a mutator both DECLINE; a package-level
// `var` of func type, a parameter, a range variable, a struct FIELD of func
// type, a tuple binding and a named-func initialiser all DECLINE. Escape BY
// VALUE — returned, stored in a struct, passed as an argument, captured
// read-only by another closure — CLEARS, because a copy of a func value cannot
// change the variable it was copied from. SHADOWING clears both calls and binds
// each to ITS OWN literal, measured: the rule keys on the *types.Var object and
// an inner `:=` is a different object. `go f()` and `defer f()` take the same
// ruling as the plain call form.
//
// P4 RULING (D6 adjudication round 2, 2026-08-11) — THE OUT-OF-TREE PROVENANCE
// CLAIM IS REFUSED, AND THE REFUSAL IS THE RULING. The candidate was: `cancel`
// is the second result of `context.WithCancel`/`WithTimeout`, whose body is out
// of tree, so the value returned is an out-of-tree function and calling it
// cannot reach an in-tree symbol. It is not the withdrawn "we could not type
// the receiver, so assume harmless"; it is a positive provenance claim, and it
// is FALSE.
//
// MEASURED 2026-08-11 by RUNNING a package built to test it, not by argument.
// Three standard-library shapes, all Go 1.24, in which out-of-tree code holds
// and invokes in-tree code:
//
//	sync.OnceFunc(inTreeA)   returns a func value whose body CALLS the
//	                         in-tree function it was handed.
//	iter.Pull(seq)           returns `next`, which CALLS the caller-supplied
//	                         in-tree `seq`.
//	httptest.NewServer(h{})  calls an in-tree method the tree NEVER NAMES.
//
// The program prints `REACHED: [inTreeA seq handler.ServeHTTP inTreeB]`. So an
// out-of-tree function value reaches in-tree code, and "the callee is
// out-of-tree" says nothing whatever about what its result executes.
//
// AND THE REFERENCE EDGE DOES NOT CLOSE IT — it closes two of the three and
// RELOCATES nothing on the third, which is the measurement that decides this.
// `sort.Slice(xs, less)` is the shape that works: `less` is MENTIONED, so a
// `reference` edge puts it in the closure, and the same holds for `inTreeA` and
// `seq` above. The third has no mention to hang an edge on. Measured over that
// package by the same walk: the production closure is {main, inTreeA, seq} and
// `(handler).ServeHTTP` and `inTreeB` are OUTSIDE it — while `go run` proves
// both execute. Interface satisfaction is not an edge (see the paragraph below,
// which is why), so nothing names the method and nothing can.
//
// That is what makes adopting the rule a fail-open rather than a narrowing.
// The three holes at those call sites are the ONLY record that the tree was not
// fully read. Erase them and the document claims a fully-resolved production
// closure while in-tree code that provably runs sits outside it — a "no path"
// answer computed around a gap the rule had just deleted, which turns a
// reached symbol into an unreached one and manufactures a BREACH.
// Anti-requirement 2 forbids exactly that direction.
//
// The keying requirement does not rescue it either, and this is worth saying
// because the requirement was the right one to impose. Keying on "the callee is
// established out-of-tree BY TYPE-CHECKING" rather than on a name list of
// stdlib functions removes the anti-requirement 3 objection — a hand list is
// what the deleted `_FALLBACK_PRODUCTION_KIND` table was — but it does not make
// the claim true, because type-checking establishes the callee's PACKAGE and
// the result's TYPE, and the claim is about the result's BODY. No narrowing
// survives either: "no func-typed or interface-typed argument at this call
// site" still loses to a handoff made at a DIFFERENT site (`sql.Register` then
// `sql.Open`), and repairing that is a whole-tree escape analysis, which is a
// different mechanism from the one proposed.
//
// So `cancel` stays a hole. Note that it does not even reach the provenance
// question: measured, both sites fail OBLIGATION 2 of the rule above, because
// `ctx, cancel := context.WithTimeout(…)` is a TUPLE binding. (Recorded in
// passing: both sites are `context.WithTimeout`, not `context.WithCancel`; the
// type is `context.CancelFunc` either way and the ruling is unchanged.)
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
	"fmt"
	"go/ast"
	"go/build"
	"go/importer"
	"go/parser"
	"go/token"
	"go/types"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"sort"
	"strings"
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

// The three spellings this program shares with the Python side, byte for byte.
// They are stated once THERE — go_symbol_key, GO_PACKAGE_VAR_SYMBOL and
// GO_INIT_SYMBOL_TEMPLATE — and these are their Go faces. Two spellings of one
// key is the failure this whole effort is about, so they are constants here
// rather than format strings assembled at four call sites.
const (
	keyPackageSeparator = "."
	packageVarSymbol    = "<vars>"
	// packageVarTestSymbol is the SECOND synthetic package-var initialiser, and
	// its existence is the repair of a measured verdict flip. See
	// declarePackageVar. It is spelled with the same characters no Go
	// declaration can produce, and it does NOT end in `<vars>`, so a reader
	// asking "is this the production initialiser" by suffix gets the right
	// answer.
	packageVarTestSymbol      = "<vars:test>"
	initSymbolTemplate        = "<init:%d>"
	externalTestPackageSuffix = "_test"
	// testFileSuffix is the toolchain's OWN rule for which binary a file is
	// compiled into — `go help test`: "files whose names end in _test.go". It
	// is not a second notion of "is this one of the tests": that question is
	// seal_verify.is_test_path's and it is asked by the CALLER, over the same
	// paths, for a different purpose (which ROOTS survive). This one decides
	// which BINARY a package-level var initialiser runs in, which is a fact
	// about the Go build and not about this repository's conventions.
	testFileSuffix = "_test.go"
)

// The two binaries one Go package compiles into, and the array index each
// package-var initialiser is filed under. Not a bool: the code below indexes
// arrays with it, and an index named `true` is how the wrong slot gets read.
const (
	binaryProduction = 0
	binaryTest       = 1
	binaryCount      = 2
)

// binaryOf is which binary the declarations in this file are compiled into.
func binaryOf(path string) int {
	if strings.HasSuffix(path, testFileSuffix) {
		return binaryTest
	}
	return binaryProduction
}

// The four wire `kind` strings of the EDGE GRAMMAR, and the four root kinds.
// Spelled once so a walk cannot grow a fifth by typing one.
const (
	edgeDirect    = "direct"
	edgeMethod    = "method"
	edgeInterface = "interface"
	edgeReference = "reference"

	rootMain       = "go_main"
	rootInit       = "go_init"
	rootPackageVar = "go_package_var"
	rootTest       = "test_function"
)

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
//	                                     of the PRODUCTION binary
//	<module>/<pkgdir-tail>.<vars:test>   the same, for the test binary — one per
//	                                     (package, binary), see declarePackageVar
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
//
// P4 RULING (D6 adjudication, 2026-08-11) — THE SENTENCE THIS CONTRACT OWED.
// `null` is ABSENT and `[]` is PRESENT-AND-EMPTY. They are two answers, not
// two spellings of one, and every decoder MUST read them that way.
//
// The two sentences above are compatible under exactly that one reading, and
// the contract could not previously be satisfied without it. Measured under
// `feat/D6-seals` @ 5669cb7, 2026-08-11, by marshalling the Response type in
// this file: with ParseError set and the four slices left nil, Go writes
//
//	{"schema":…,"unit":{…},"symbols":null,"roots":null,"edges":null,
//	 "unresolved":null,"parse_error":{…}}
//
// so EVERY parse_error document this program can produce carries the four
// arrays as `null`. A decoder that read `null` as PRESENT would see
// "parse_error AND arrays" — the state this contract calls
// HELPER_OUTPUT_INVALID — and would refuse every parse_error document, which
// build_call_graph escalates into a whole-check CallSiteReachabilityError:
// one unparseable file taking the entire check down, which is the outage
// CallGraph.unreadable_paths exists to prevent.
//
// REJECTED, and it is the obvious repair, so the rejection is the ruling:
// adding `,omitempty` to the four arrays. Measured the same way — under
// `,omitempty` Go writes `{}` for a nil slice AND `{}` for an empty one, so
// the tag destroys precisely the distinction the paragraph above depends on.
// The two states become one byte string and "[] is an answer" stops being
// expressible. The tags stay off; the reading is the repair.
// P3 (D6 body 2, 2026-08-11) — ImportPath IS THE ONE FIELD THAT IS NOT DERIVED
// FROM THE REQUEST, AND THAT IS THE WHOLE POINT OF IT.
//
// Everything else in this document is a function of the TEXT the caller sent.
// ImportPath is a function of the DISK, asked of the Go toolchain — `go list -e
// -find -f {{.ImportPath}} .` in this process's working directory, which the
// caller has already set to the unit's package directory so that the source
// importer can resolve imports at all.
//
// It exists because the Python side was computing the same string by directory
// arithmetic — nearest enclosing go.mod, plus the directory below it — and that
// arithmetic is WRONG on the two commonest shapes after `internal/`. Measured
// under `feat/D6-body2`, 2026-08-11, go1.24.4:
//
//	sub/vendor/example.com/lib  `go mod vendor` STRIPS the vendored module's
//	                            go.mod, so the arithmetic walks to the
//	                            ENCLOSING module and computes
//	                            example.com/app/vendor/example.com/lib. The
//	                            toolchain answers example.com/lib, which is
//	                            what the type-checker resolved the import to.
//
// It is empty on a parse_error document and non-empty on every graph document;
// the caller refuses a graph document that does not name it, because a unit
// whose import path is unknown is a unit no cross-package edge can be rejoined
// to, and a dropped production edge manufactures a BREACH.
//
// WHAT IT DOES NOT CLOSE, and it is measured rather than assumed — see the note
// on `unitImportPath`: a `replace` that RENAMES. The toolchain's answer for a
// directory is the answer of the module that OWNS the directory, and a renaming
// replace means the importing module knows the same package by a different
// name. "The import path of a directory" is not a function of the directory.
// P3 (D6, imports round, 2026-08-11) — `imports` IS THE SECOND FIELD THAT IS
// NOT A FUNCTION OF THE REQUEST TEXT ALONE, AND IT EXISTS TO MAKE D5'S IMPORT
// RELATION COMPUTABLE.
//
// `CallGraph.package_imports` decides, per subject, which unresolved calls could
// be the missing call site: two packages in different components of the
// UNDIRECTED import graph cannot hand each other a function value, so a hole in
// one is out of scope for a subject in the other. D5 owns that rule; this field
// is the FACT the rule is applied to, and without it every analyzed tree carries
// `ImportsUnavailable` and no hole is ever scoped away from any subject.
//
// It is `pkg.Imports()` — the packages go/types RESOLVED for this unit's import
// blocks — and never the literal strings of the import specs. The reason is the
// one property that cancels invisibly: a callee in another package is spelled
// `fn.Pkg().Path()` by calleeKey above, and `Imports()` is the same vocabulary
// from the same type-check. Reading the import specs instead would put the
// relation in a second vocabulary, and then an edge could be joined between two
// packages the relation reports as unable to name each other, with nothing red.
//
// Empty is an ANSWER (a package that imports nothing is legal Go) and absent is
// not, so the field is not `,omitempty` and the caller refuses a graph document
// that omits it — the same discipline, for the same reason, as ImportPath.
type Response struct {
	Schema string `json:"schema"`
	Unit   Unit   `json:"unit"`
	// ImportPath is the import path the Go toolchain resolves for this unit's
	// own directory. Not `,omitempty`: a graph document must NAME it, and an
	// absent field and an empty one must not be two spellings of one answer.
	ImportPath string `json:"import_path"`
	// Imports is every package this unit's files import, as go/types resolved
	// them, sorted and deduplicated. See the note above the type.
	Imports    []string    `json:"imports"`
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
	fset := token.NewFileSet()
	parsed := make([]*ast.File, 0, len(request.Files))
	for _, file := range request.Files {
		// The FILENAME handed to the parser is the request's tree-relative
		// path and never an on-disk one: every position this program reports —
		// symbol lines, call sites, and the parse_error path — is derived from
		// it, and a caller that got an absolute path back could not join a
		// site to a file it knows about.
		syntax, err := parser.ParseFile(fset, file.Path, file.Source, 0)
		if err != nil {
			return Response{ParseError: &ParseError{
				Path:    file.Path,
				Message: err.Error(),
			}}, nil
		}
		parsed = append(parsed, syntax)
	}

	// `[]` is an answer and `null` is not, so the four arrays are allocated
	// before anything can return early with a graph. A unit that declares
	// nothing is a package clause and imports, and that is a fact about the
	// package rather than a fault; the whole-tree emptiness guard lives at the
	// caller's GoReachabilityAnalyzer.graph, which is the only layer that knows
	// how many Go files the sweep found.
	response := Response{
		Imports:    []string{},
		Symbols:    []Symbol{},
		Roots:      []Root{},
		Edges:      []Edge{},
		Unresolved: []Hole{},
	}
	if len(parsed) == 0 {
		return response, nil
	}

	info := &types.Info{
		Types:      make(map[ast.Expr]types.TypeAndValue),
		Defs:       make(map[*ast.Ident]types.Object),
		Uses:       make(map[*ast.Ident]types.Object),
		Selections: make(map[*ast.SelectorExpr]*types.Selection),
	}
	var typeErrors []error
	conf := types.Config{
		// LOAD-BEARING, and it must not be "simplified" to importer.Default():
		// that one needs a writable build cache and dies with "GOCACHE is not
		// defined and neither $XDG_CACHE_HOME nor $HOME are defined" under a
		// bare environment. The source importer reads GOROOT/src instead. See
		// the P4 ruling on TYPE RESOLUTION at the top of this file.
		Importer: importer.ForCompiler(fset, "source", nil),
		// Non-nil so that Check does not stop at the first error and this
		// program can COUNT them. types.Config.Error swallowing errors while
		// Check returns a populated Info is the fail-open the count exists to
		// close.
		Error: func(err error) { typeErrors = append(typeErrors, err) },
	}
	pkg, _ := conf.Check(qualifierOf(request.Unit), fset, parsed, info)
	if len(typeErrors) > 0 {
		// A UNIT THAT DID NOT TYPE-CHECK IS NOT FULLY READ, and it travels the
		// channel an unparsed unit travels. Emitting the partial graph instead
		// is how a silently shrunken production closure makes a reached symbol
		// look unreached, which is a manufactured BREACH.
		return Response{ParseError: &ParseError{
			Path:    errorPath(fset, typeErrors[0], request.Files[0].Path),
			Message: typeErrors[0].Error(),
		}}, nil
	}
	if pkg == nil {
		return Response{}, fmt.Errorf(
			"go/types returned no package for %s and reported no error; that is "+
				"this program failing to do its job, not a fact about the unit",
			request.Unit.PackageDir,
		)
	}

	// Asked AFTER the unit has parsed and type-checked, so a broken unit is
	// reported as the parse_error it is rather than as a toolchain failure —
	// and so the exec is not paid for on a unit whose answer is already known.
	importPath, err := unitImportPath()
	if err != nil {
		return Response{}, err
	}
	response.ImportPath = importPath
	response.Imports = resolvedImports(pkg)

	walk := &walker{
		unit:      request.Unit,
		qualifier: qualifierOf(request.Unit),
		fset:      fset,
		info:      info,
		pkg:       pkg,
		keyOf:     make(map[types.Object]string),
		declKey:   make(map[*ast.FuncDecl]string),
		defIdent:  make(map[types.Object]*ast.Ident),
		methods:   make(map[string][]string),
		response:  &response,
	}
	for ident, obj := range info.Defs {
		if obj != nil {
			// One reverse index, built once: the SOLE-BINDING FUNC LITERAL rule
			// needs the declaring occurrence of a *types.Var and go/types offers
			// no way back from an object to its identifier.
			walk.defIdent[obj] = ident
		}
	}
	walk.declare(parsed, request)
	walk.walk(parsed, request)
	return response, nil
}

// resolvedImports is every package this unit imports, as go/types resolved it.
//
// COSTS NOTHING NEW. `conf.Check` a few lines above has already resolved every
// import of every file in this unit — that is what makes a cross-package callee
// nameable at all — so this reads a list the type-checker built. No `go list`
// pass is added by this field, and the per-unit exec count is unchanged at one.
//
// `pkg.Imports()` AND NOT THE IMPORT SPECS, and the choice is the whole reason
// the field is trustworthy. The two differ:
//
//   - go/types reports the path the importer RESOLVED, which is what
//     `fn.Pkg().Path()` returns for a callee in that package. The caller places
//     an import onto an in-tree package by matching this string against the
//     import paths the toolchain gave each unit, and joins a cross-package edge
//     by matching the SAME string. One vocabulary, one join, one failure mode;
//   - the specs are the text of the import block. Where the two disagree the
//     relation would say two packages cannot name each other while the edge set
//     said they do, and D5 would scope a hole away from a subject an edge proves
//     is in reach. Nothing would be red.
//
// Blank and dot imports are included, and must be: go/types records them in
// pkg.Imports() and both give the importing package a route to the imported
// one — `_` runs its initialisers, `.` puts its names in this file's scope.
//
// Sorted and deduplicated, because two runs over one unit must produce one
// document and the same package may be imported by several files of the unit.
func resolvedImports(pkg *types.Package) []string {
	paths := make([]string, 0, len(pkg.Imports()))
	seen := make(map[string]bool, len(pkg.Imports()))
	for _, imported := range pkg.Imports() {
		if imported == nil {
			continue
		}
		path := imported.Path()
		// An unnamed package is a package nothing can be joined to. It is
		// dropped rather than emitted as "", which would read as an import of
		// the empty path and could match nothing but would still be counted.
		if path == "" || seen[path] {
			continue
		}
		seen[path] = true
		paths = append(paths, path)
	}
	sort.Strings(paths)
	return paths
}

// unitImportPath asks the Go toolchain what this package's import path is.
//
// P3 (D6 body 2, 2026-08-11) — THE AUTHORITY ON AN IMPORT PATH IS THE TOOLCHAIN,
// AND THE ALTERNATIVE WAS NOT AN OPINION, IT WAS A MEASURED DEFECT.
//
// The Python side used to derive this string as `<module line of the nearest
// enclosing go.mod> + <directory below that go.mod>`. Measured under
// `feat/D6-body` @ f4c7c46 by building the tree and running it: over
// `sub/vendor/example.com/lib`, where `go mod vendor` has STRIPPED the vendored
// module's own go.mod, the arithmetic walks up to the enclosing module and
// answers `example.com/app/vendor/example.com/lib` while the type-checker
// resolved the import as `example.com/lib` — no prefix matches, the edge is
// dropped, and `lib.Do`, which production calls, reads UNCALLED. Measured under
// `feat/D6-body2` on the same tree: `go list -e -find -f {{.ImportPath}} .` in
// that directory answers `example.com/lib`.
//
// WHY `-find`, AND IT IS NOT A MICRO-OPTIMISATION. `-find` tells `go list` to
// locate the package and NOT resolve its imports. The import graph is already
// being resolved by go/types a few lines above, and paying for it twice on the
// gate path is how a per-unit budget becomes a per-tree one. Measured under
// go1.24.4, 2026-08-11: under 10 ms per unit on every shape in the matrix.
//
// WHY `-e`. Without it, a unit whose module graph is incomplete makes `go list`
// exit non-zero and this program refuse a unit that type-checked. `-e` reports
// what it found and leaves the refusal to the one condition below.
//
// WHAT IT DOES NOT CLOSE, and this is a CORRECTION to the escalation that asked
// for this field. Measured under `feat/D6-body2`, 2026-08-11, over
// `sub/go.mod` declaring `module example.com/app` with `replace
// example.com/upstream => ./local` and `sub/local/go.mod` declaring `module
// example.com/localfork`: `go list` in `sub/local` answers
// `example.com/localfork`, while the type-checker — resolving the import block
// of `sub/main.go` — spells the callee `example.com/upstream.Serve`. Both are
// correct. A package reached through a renaming `replace` HAS TWO import paths,
// one per module that names it, so "the import path of this directory" is not a
// function of this directory and no per-unit field can carry it. See the
// escalation recorded on `_import_path_qualifiers` in go_reachability.py.
//
// A FAILURE HERE IS THIS PROGRAM'S FAILURE, not a fact about the unit, so it
// returns an error and exits non-zero rather than emitting a document with the
// field empty. A graph document whose import path is unknown is a unit that
// nothing can be rejoined to, and a silently dropped cross-package edge is a
// manufactured BREACH — which is the failure this whole field exists to close.
func unitImportPath() (string, error) {
	command := exec.Command(goCommand(), "list", "-e", "-find", "-f", "{{.ImportPath}}", ".")
	var diagnostics strings.Builder
	command.Stderr = &diagnostics
	raw, err := command.Output()
	if err != nil {
		return "", fmt.Errorf(
			"`go list` could not name this package's import path: %v: %s",
			err, strings.TrimSpace(diagnostics.String()))
	}
	answer := strings.TrimSpace(string(raw))
	// `.` and `command-line-arguments` are what `go list` answers when it did
	// NOT resolve a package to an import path. Neither is a name anything can
	// be joined to, and accepting one would put an unjoinable key in the map
	// that decides whether a cross-package edge survives.
	if answer == "" || answer == "." || answer == "command-line-arguments" {
		return "", fmt.Errorf(
			"`go list` answered %q for this package's import path, which names "+
				"no package anything can be joined to: %s",
			answer, strings.TrimSpace(diagnostics.String()))
	}
	return answer, nil
}

// goCommand is go/build's own rule for finding the toolchain, spelled here
// because go/build does not export it: GOROOT/bin/go when that exists, and
// otherwise whatever `go` PATH resolves. The source importer a few lines above
// finds `go` the same way, so a divergence here would mean the two halves of
// this program asked two different toolchains.
func goCommand() string {
	if root := build.Default.GOROOT; root != "" {
		candidate := filepath.Join(root, "bin", "go")
		if info, err := os.Stat(candidate); err == nil && !info.IsDir() {
			return candidate
		}
	}
	return "go"
}

// errorPath is the file a type error names, or the unit's first file when the
// error carries no position. Never empty: the caller records it in
// CallGraph.unreadable_paths, and a whole-tree abstention with no file to fix
// is an abstention nobody can act on.
func errorPath(fset *token.FileSet, err error, fallback string) string {
	if typed, ok := err.(types.Error); ok && typed.Pos.IsValid() {
		if name := fset.Position(typed.Pos).Filename; name != "" {
			return name
		}
	}
	return fallback
}

// qualifierOf is go_symbol_key's qualifier, and the two must agree byte for
// byte. It is also what this program hands types.Config.Check as the package
// path, so every in-unit object's own Pkg().Path() IS the qualifier and an
// in-package key falls out of go/types rather than being reassembled.
func qualifierOf(unit Unit) string {
	qualifier := unit.ModulePath
	if unit.PackageDir != "" {
		qualifier = unit.ModulePath + "/" + unit.PackageDir
	}
	if strings.HasSuffix(unit.PackageName, externalTestPackageSuffix) {
		qualifier = qualifier + "[" + unit.PackageName + "]"
	}
	return qualifier
}

// walker holds one unit's answer while it is being derived. Nothing here is
// ranged over to produce output: symbols, roots and holes come out in
// declaration order and edges in call-site order, because a nondeterministic
// document moves the WITNESS PATH a human is asked to check.
type walker struct {
	unit      Unit
	qualifier string
	fset      *token.FileSet
	info      *types.Info
	pkg       *types.Package

	// keyOf maps an in-unit func or method OBJECT to its key. Membership is
	// this program's whole notion of "declared here": a callee go/types
	// resolved to an object outside it lives in another package.
	keyOf    map[types.Object]string
	declKey  map[*ast.FuncDecl]string
	defIdent map[types.Object]*ast.Ident
	// methods indexes in-unit METHOD keys by name, which is what makes the
	// interface fan-out a superset of the possible in-tree targets rather than
	// a guess: Go's method-call syntax names the method.
	methods map[string][]string

	// varKey is indexed by binaryProduction / binaryTest: ONE synthetic
	// initialiser symbol per (package, binary), never one per package. See
	// declarePackageVar for the measured verdict flip that forces the split.
	varKey [binaryCount]string

	response *Response
}

func (w *walker) key(receiver, name string) string {
	if receiver == "" {
		return w.qualifier + keyPackageSeparator + name
	}
	return w.qualifier + keyPackageSeparator + "(" + receiver + ")" + keyPackageSeparator + name
}

func (w *walker) position(pos token.Pos) token.Position { return w.fset.Position(pos) }

func (w *walker) site(pos token.Pos) string {
	at := w.position(pos)
	return fmt.Sprintf("%s:%d", at.Filename, at.Line)
}

// declare emits one Symbol per declaration and one Root per entrypoint.
//
// Every declaration, including the ones nothing references: a symbol absent
// from the map cannot be a subject, and a subject that cannot be found is an
// abstention rather than a pass.
func (w *walker) declare(files []*ast.File, request Request) {
	initOrdinal := 0
	for index, file := range files {
		path := request.Files[index].Path
		for _, decl := range file.Decls {
			switch typed := decl.(type) {
			case *ast.FuncDecl:
				w.declareFunc(typed, path, &initOrdinal)
			case *ast.GenDecl:
				if typed.Tok == token.VAR {
					w.declarePackageVar(typed, path)
				}
			}
		}
	}
}

func (w *walker) declareFunc(decl *ast.FuncDecl, path string, initOrdinal *int) {
	name := decl.Name.Name
	// A blank-named declaration cannot be referred to, by definition of the
	// language, so it is not callable surface — and one file may legally hold
	// several, which would be a duplicate key. That is the fingerprinter's
	// isBlank rule and it transfers unchanged.
	if name == "_" {
		return
	}
	receiver := receiverText(decl)
	kind := "func"
	if receiver != "" {
		kind = "method"
	}

	member := name
	isInit := receiver == "" && name == "init"
	if isInit {
		// `func init()` is NOT skipped here, which is the opposite of the
		// fingerprinter's rule and for an exactly inverted reason: Go RUNS it
		// before main, so it is a root, and everything only an init reaches
		// would otherwise read as a false BREACH. Several per package are
		// legal, so `init` alone is a duplicate key waiting to happen.
		member = fmt.Sprintf(initSymbolTemplate, *initOrdinal)
		*initOrdinal++
	}
	key := w.key(receiver, member)
	at := w.position(decl.Pos())
	w.response.Symbols = append(w.response.Symbols, Symbol{
		Key:  key,
		Path: path,
		Line: at.Line,
		Kind: kind,
	})
	w.declKey[decl] = key
	if obj := w.info.Defs[decl.Name]; obj != nil {
		w.keyOf[obj] = key
	}
	if receiver != "" {
		w.methods[name] = append(w.methods[name], key)
		return
	}

	evidence := fmt.Sprintf("%s:%d func %s, package %s", path, at.Line, name, w.unit.PackageName)
	switch {
	case isInit:
		w.response.Roots = append(w.response.Roots, Root{
			Symbol: key, Kind: rootInit, Evidence: evidence,
		})
	case name == "main" && w.unit.PackageName == "main":
		w.response.Roots = append(w.response.Roots, Root{
			Symbol: key, Kind: rootMain, Evidence: evidence,
		})
	case isTestName(name):
		// The NAMING half only. Whether the declaring FILE is one of the tests
		// is seal_verify.is_test_path's question and this program does not open
		// a second matcher for it; the caller applies it and drops a root whose
		// file disagrees.
		w.response.Roots = append(w.response.Roots, Root{
			Symbol: key, Kind: rootTest, Evidence: evidence,
		})
	}
}

// declarePackageVar mints the synthetic package-var initialiser symbol, ONCE
// PER (PACKAGE, BINARY) and not once per file, and not once per package.
//
// Synthetic rather than omitted, because a root with no symbol has no outgoing
// edges and would contribute silently nothing. Not per FILE, and the difference
// is measurable: spelling it per file reported a 106-symbol production closure
// over the acceptance fixture where a coarser spelling reports 104.
//
// P3 (D6 body 2, 2026-08-11) — WHY IT IS NOT PER PACKAGE EITHER, AND THE
// DEFECT THE SPLIT REPAIRS IS A VERDICT THAT FLIPPED ON A FILENAME.
//
// A per-package `<vars>` stands for initialisers that run in TWO different
// binaries, and it can carry only ONE path — the first contributing file's. The
// caller reads that path through seal_verify.is_test_path to decide whether the
// root survives at all. So one alphabetical accident decided both. Measured
// under `feat/D6-body` @ f4c7c46 over one package holding `var _ = onlyProd()`
// in one file and `var _ = onlyTest()` in a test file:
//
//	main.go + z_test.go   path = main.go, the root is KEPT as PRODUCTION, and
//	                      its edge to onlyTest certifies a function only a test
//	                      file initialises — hiding dark code;
//	a_test.go + b.go      path = a_test.go, the whole root is DROPPED, and
//	                      onlyProd — genuinely initialised in production —
//	                      reads FROM_NEITHER, a false BREACH.
//
// The same package, the same code, and the verdict flips on the alphabetical
// position of a test file's name. Measured under `feat/D6-body2` on the same
// two trees: both answer identically, because each binary's initialiser now has
// its own symbol taking its path from a file of its OWN kind.
//
// WHAT THE SPLIT DOES NOT BUY, and it is not this program's to buy: the
// `<vars:test>` root is still DROPPED by the caller, because D5 derives
// RootKind from the entrypoint kind ALONE and `go_package_var` derives
// PRODUCTION, which its own _validate_root then refuses against a test path.
// The true answer is a TEST root, and the one table lookup that would say so is
// escalated to D5's adjudicator. What the split DOES buy is that the drop is
// now confined to the test binary's initialisers instead of taking the
// production ones with it, and that no answer here depends on a filename's
// sort position.
//
// The test binary compiles the production files too, so its initialiser set is
// really a superset of production's. It is NOT spelled that way: the production
// symbol already carries those edges, and duplicating them under a root the
// caller drops would buy nothing and cost a second place where one initialiser
// is two symbols.
func (w *walker) declarePackageVar(decl *ast.GenDecl, path string) {
	binary := binaryOf(path)
	if w.varKey[binary] != "" {
		return
	}
	initialised := false
	for _, spec := range decl.Specs {
		if value, ok := spec.(*ast.ValueSpec); ok && len(value.Values) > 0 {
			initialised = true
			break
		}
	}
	if !initialised {
		return
	}
	symbol := packageVarSymbol
	if binary == binaryTest {
		symbol = packageVarTestSymbol
	}
	w.varKey[binary] = w.key("", symbol)
	at := w.position(decl.Pos())
	w.response.Symbols = append(w.response.Symbols, Symbol{
		Key:  w.varKey[binary],
		Path: path,
		Line: at.Line,
		Kind: "package_var",
	})
	w.response.Roots = append(w.response.Roots, Root{
		Symbol:   w.varKey[binary],
		Kind:     rootPackageVar,
		Evidence: fmt.Sprintf("%s:%d package-level var with an initialiser, package %s", path, at.Line, w.unit.PackageName),
	})
}

func receiverText(decl *ast.FuncDecl) string {
	if decl.Recv == nil || len(decl.Recv.List) == 0 {
		return ""
	}
	// EXACTLY as written, `*Config` and `Config` and `*Set[T]`. Pointer and
	// value receivers get DIFFERENT keys, which is the deliberate opposite of
	// the fingerprinter's receiverBaseName: a signature comparison asks "did
	// this contract change" and a call graph asks "does execution arrive here",
	// for which `func (T) M` and `func (*T) M` are two bodies.
	return types.ExprString(decl.Recv.List[0].Type)
}

// isTestName is cmd/go's isTest: a prefix, then a rune that is not lower-case.
// So `TestFoo` and a bare `Test` are entrypoints and `Testify` is not, which is
// the whole reason it is a rune check and not a prefix match.
func isTestName(name string) bool {
	for _, prefix := range []string{"Test", "Benchmark", "Fuzz", "Example"} {
		if !strings.HasPrefix(name, prefix) {
			continue
		}
		rest := name[len(prefix):]
		if rest == "" {
			return true
		}
		first := []rune(rest)[0]
		return !(first >= 'a' && first <= 'z')
	}
	return false
}

// walk emits the edges and the holes, one owner at a time.
//
// The OWNER is the innermost enclosing NAMED declaration, never a synthetic
// symbol for a func literal: subjects_of_seal defines a seal's subject as what
// the seal's own body calls directly, including nested closures and t.Run
// literals, and a symbol per closure would empty the subject set of every
// table-driven seal in the target repositories.
func (w *walker) walk(files []*ast.File, request Request) {
	for index, file := range files {
		// The OWNER of a package-level var initialiser is the synthetic symbol
		// of the BINARY its file is compiled into, so an initialiser in a
		// _test.go file cannot hang its edges off the production root. That is
		// the whole point of declarePackageVar's split; reading one varKey here
		// would put the split back.
		varKey := w.varKey[binaryOf(request.Files[index].Path)]
		for _, decl := range file.Decls {
			switch typed := decl.(type) {
			case *ast.FuncDecl:
				key, ok := w.declKey[typed]
				if !ok || typed.Body == nil {
					continue
				}
				w.walkOwner(key, typed, typed.Body)
			case *ast.GenDecl:
				if typed.Tok != token.VAR || varKey == "" {
					continue
				}
				for _, spec := range typed.Specs {
					value, ok := spec.(*ast.ValueSpec)
					if !ok {
						continue
					}
					for _, initialiser := range value.Values {
						// No enclosing named declaration, so the SOLE-BINDING
						// rule's obligation 1 can never be discharged here —
						// which is correct: a package-level var of func type is
						// exactly the shape that rule declines.
						w.walkOwner(varKey, nil, initialiser)
					}
				}
			}
		}
	}
}

func (w *walker) walkOwner(owner string, decl *ast.FuncDecl, body ast.Node) {
	// Identifiers already ANSWERED as the target of a call. ast.Inspect visits
	// a CallExpr before its Fun, so the mark is always set before the ident is
	// reached, and one pass suffices — which keeps edges in call-site order.
	consumed := make(map[*ast.Ident]bool)
	ast.Inspect(body, func(node ast.Node) bool {
		switch typed := node.(type) {
		case *ast.CallExpr:
			w.classifyCall(typed, owner, decl, consumed)
		case *ast.Ident:
			if consumed[typed] {
				return true
			}
			// A FUNCTION VALUE is "reference" and never "direct":
			// `sort.Slice(xs, less)` reaches `less` — a real way production
			// reaches code — but the value may never be invoked, so the fact is
			// weaker than a call and the path through it is over-approximated.
			// A method VALUE and a method EXPRESSION are the same kind.
			if fn, ok := w.info.Uses[typed].(*types.Func); ok {
				w.edge(owner, w.calleeKey(fn), edgeReference, w.site(typed.Pos()))
			}
		}
		return true
	})
}

func (w *walker) edge(caller, callee, kind, site string) {
	if callee == "" {
		return
	}
	w.response.Edges = append(w.response.Edges, Edge{
		Caller: caller, Callee: callee, Kind: kind, Site: site,
	})
}

func (w *walker) hole(caller string, pos token.Pos, detail string) {
	w.response.Unresolved = append(w.response.Unresolved, Hole{
		Caller: caller, Site: w.site(pos), Detail: detail,
	})
}

// calleeKey is the key of a resolved func object: the in-unit spelling when the
// object is declared here, and the object's own package path otherwise.
//
// An out-of-package key is emitted rather than dropped because the CALLER is
// the layer that knows the tree: it keeps an edge only when both ends are
// declared, so a stdlib target disappears there while a target in another
// package OF THE SAME TREE survives. Dropping here would decide a question this
// program cannot see.
func (w *walker) calleeKey(fn *types.Func) string {
	if key, ok := w.keyOf[fn]; ok {
		return key
	}
	pkgPath := ""
	if fn.Pkg() != nil {
		pkgPath = fn.Pkg().Path()
	}
	if pkgPath == "" {
		return ""
	}
	signature, _ := fn.Type().(*types.Signature)
	if signature != nil && signature.Recv() != nil {
		return pkgPath + keyPackageSeparator + "(" + receiverSpelling(signature.Recv().Type()) + ")" + keyPackageSeparator + fn.Name()
	}
	return pkgPath + keyPackageSeparator + fn.Name()
}

// isInterfaceReceiver is the DISCRIMINATOR of the method-call rule: is the
// target of this selection decided by the program, or by the value?
//
// The pointer is stripped first because `(*T).M` and `T.M` are one question
// here — a pointer to a concrete type is a concrete receiver — and the answer is
// taken from the UNDERLYING type, so a named interface (`type Fetcher
// interface{…}`) and a literal one give the same answer. A *types.TypeParam
// answers true: its underlying type is its constraint, the target depends on the
// instantiation, and a fan-out is the honest over-approximation.
//
// A nil type answers true, which is the fan-out branch: it is the branch that
// cannot manufacture a wrong single target, and this program does not have a
// third answer to give.
func isInterfaceReceiver(typ types.Type) bool {
	if typ == nil {
		return true
	}
	if pointer, ok := typ.Underlying().(*types.Pointer); ok {
		typ = pointer.Elem()
	}
	_, isInterface := typ.Underlying().(*types.Interface)
	return isInterface
}

func receiverSpelling(typ types.Type) string {
	bare := func(t types.Type) string {
		return types.TypeString(t, func(*types.Package) string { return "" })
	}
	if pointer, ok := typ.(*types.Pointer); ok {
		return "*" + bare(pointer.Elem())
	}
	return bare(typ)
}

func unparen(expr ast.Expr) ast.Expr {
	for {
		paren, ok := expr.(*ast.ParenExpr)
		if !ok {
			return expr
		}
		expr = paren.X
	}
}

// classifyCall is the EDGE GRAMMAR, applied to one *ast.CallExpr.
//
// Every form the Fun slot can hold is handled and the default DECLINES into a
// hole, because three probes in this effort reported a rate over a population
// that excluded the calls that mattered — a walk that reads only Ident and
// SelectorExpr turns every generic call `F[T](x)` into a false hole, since an
// instantiation puts an *ast.IndexExpr there.
func (w *walker) classifyCall(call *ast.CallExpr, owner string, decl *ast.FuncDecl, consumed map[*ast.Ident]bool) {
	fun := unparen(call.Fun)
	// A CONVERSION is not a call. `[]byte(s)`, `Fidelity(n)`, `(*T)(p)`: the
	// Fun slot holds a TYPE, go/types says so, and there is no callee to name —
	// an answered question, so neither an edge nor a hole.
	if tv, ok := w.info.Types[fun]; ok && tv.IsType() {
		markIdents(fun, consumed)
		return
	}
	switch typed := fun.(type) {
	case *ast.Ident:
		w.classifyIdentCall(typed, owner, decl, consumed)
	case *ast.SelectorExpr:
		w.classifySelectorCall(typed, owner, decl, consumed)
	case *ast.IndexExpr:
		w.classifyInstantiation(typed.X, call, owner, decl, consumed)
	case *ast.IndexListExpr:
		w.classifyInstantiation(typed.X, call, owner, decl, consumed)
	case *ast.FuncLit:
		// An immediately-invoked literal. Its body's calls are already
		// attributed to this owner by the ATTRIBUTION rule, so the site is a
		// fully answered question: no edge, and no hole.
		return
	default:
		w.hole(owner, call.Lparen, fmt.Sprintf(
			"the call target is a %T, which names no declaration this walk can "+
				"resolve", fun))
	}
}

func (w *walker) classifyIdentCall(ident *ast.Ident, owner string, decl *ast.FuncDecl, consumed map[*ast.Ident]bool) {
	consumed[ident] = true
	switch obj := w.info.Uses[ident].(type) {
	case *types.Builtin:
		// `println`, `len`, `append`. There is no declaration anywhere to reach,
		// so it is an answered question and emphatically not a hole: filing
		// builtins as holes puts every real Go tree into the abstention branch.
		return
	case *types.Func:
		w.edge(owner, w.calleeKey(obj), edgeDirect, w.site(ident.Pos()))
	case *types.Var:
		// A call through a func-typed variable. The SOLE-BINDING FUNC LITERAL
		// rule is the ONE way this stops being a hole, and it is a positive
		// claim about what the variable holds — never "we could not find
		// another assignment, so assume there is none".
		if w.soleBindingFuncLiteral(ident, obj, decl) {
			return
		}
		w.hole(owner, ident.Pos(), fmt.Sprintf(
			"call through the func-typed variable %q, whose value this walk "+
				"cannot pin to a single literal", ident.Name))
	default:
		w.hole(owner, ident.Pos(), fmt.Sprintf(
			"the identifier %q names no callable this walk can resolve", ident.Name))
	}
}

func (w *walker) classifySelectorCall(sel *ast.SelectorExpr, owner string, decl *ast.FuncDecl, consumed map[*ast.Ident]bool) {
	consumed[sel.Sel] = true
	// `pkg.F(x)`, a qualified identifier: the import block of this file names
	// the import path, so the callee is nameable without the callee's source.
	// That is DIRECT-strength — one declaration, named.
	//
	// NAMEABLE, not KEYED. The name this emits is the callee's IMPORT PATH and
	// the callee's own unit keys it by its TREE-relative directory; the two
	// differ whenever the module root is not the tree root. The Python side
	// rejoins them. See the P4 ruling in the package comment — the sentence
	// that used to claim derivability here was false, and its consequence was a
	// dropped production edge, which is a manufactured BREACH.
	if base, ok := sel.X.(*ast.Ident); ok {
		if _, isPackage := w.info.Uses[base].(*types.PkgName); isPackage {
			consumed[base] = true
			switch obj := w.info.Uses[sel.Sel].(type) {
			case *types.Builtin:
				return
			case *types.Func:
				w.edge(owner, w.calleeKey(obj), edgeDirect, w.site(sel.Sel.Pos()))
			case *types.Var:
				w.hole(owner, sel.Sel.Pos(), fmt.Sprintf(
					"call through the package-level func-typed variable %q",
					sel.Sel.Name))
			default:
				w.hole(owner, sel.Sel.Pos(), fmt.Sprintf(
					"the qualified identifier %q names no callable this walk can "+
						"resolve", sel.Sel.Name))
			}
			return
		}
	}

	selection := w.info.Selections[sel]
	if selection == nil {
		w.hole(owner, sel.Sel.Pos(), fmt.Sprintf(
			"the selector %q resolves to no selection this walk can read", sel.Sel.Name))
		return
	}
	switch selection.Kind() {
	case types.MethodVal, types.MethodExpr:
		fn, ok := selection.Obj().(*types.Func)
		if !ok {
			w.hole(owner, sel.Sel.Pos(), "a method selection whose object is not a func")
			return
		}
		if key, inUnit := w.keyOf[fn]; inUnit {
			// The receiver's type is known and the target is ONE declaration
			// here. A separate kind from `direct` on EdgeKind's own reasoning:
			// a report must be able to say which resolution it was leaning on.
			w.edge(owner, key, edgeMethod, w.site(sel.Sel.Pos()))
			return
		}
		// Either interface dispatch, or a method on a type declared outside
		// this unit. Both take the same answer: ONE edge per in-unit method of
		// that name. Go's method-call syntax NAMES the method, so within THIS
		// UNIT the fan-out is a superset of the possible targets and the
		// residue is empty — which is why the site is answered rather than
		// holed. An empty fan-out is an answer too: no in-unit method is named
		// `Format`, so `now.Format("")` reaches nothing here.
		//
		// P3 (D6 body 2, 2026-08-11) — THE DISCRIMINATOR IS THE RECEIVER, AND
		// IT IS APPLIED HERE. When the receiver's base type is not an
		// interface, go/types has ALREADY resolved the one target; the fan-out
		// is then not an over-approximation of an unknown, it is a wrong answer
		// to a question that was answered. `w.calleeKey(fn)` spells that target
		// — in-unit keys come out of `keyOf`, out-of-unit ones out of the
		// object's own package path, exactly as a cross-package FUNC call is
		// spelled — and the Python side rejoins it the same way.
		//
		// The fan-out survives for GENUINE interface dispatch, where
		// `selection.Obj()` is the interface's method, no implementation is
		// named, and one edge per in-unit method of that name is the superset
		// the note below describes. A TYPE PARAMETER counts as interface
		// dispatch: its underlying type is its constraint, which is an
		// interface, and the target depends on the instantiation.
		//
		// WHAT IT COSTS, measured under `feat/D6-body2`, 2026-08-11, over the
		// acceptance fixture: the edge set falls from 738 to 694 and NOTHING is
		// added. All 44 removed edges are `interface`, they come from eight
		// call sites, and every one of those sites is a `String()` on a
		// CONCRETE STDLIB receiver — `b.String()` on a strings.Builder at
		// cmd/gates/preserve.go:509 and three siblings, `t.String()` at
		// cmd/gates/preserve.go:739 and its sibling, `stderr.String()` in two
		// seal helpers. The fan-out was claiming that a call to
		// strings.Builder.String might reach (Fidelity).String, (EditKind).String,
		// (Divergence).String and eleven more methods of the judged tree. Zero
		// edges are ADDED, because every one of those sites resolves OUT of the
		// tree: the fan-out produced 44 false in-tree edges and no true one.
		// The production closure (104 symbols) and the hole count (3, of which
		// 2 inside the closure) are unchanged, so no verdict was resting on
		// them.
		//
		// THE DISPUTE THIS RAISED IS RULED, AND THE RULING WENT THIS RULE'S WAY
		// (P4, D6 adjudication round 4, 2026-08-11). The contradiction was
		// between two P4 artifacts rather than a defect in either: the seal row
		// `test_a_named_out_of_tree_target_is_not_a_hole_and_a_func_value_call_is`
		// REQUIRED the edge this rule removes, building `now.UTC()` on a
		// time.Time beside an in-unit `func (Clock) UTC` and asserting one
		// INTERFACE edge from `stamp` to `Clock.UTC` — the 45th instance of the
		// shape measured above. Its stated purpose ("a named out-of-tree target
		// is not a hole") and its hole-set assertion were green; only its
		// WITNESS failed, and the witness was a CONCRETE receiver, which is the
		// wrong witness for a property about UNRESOLVED targets. Priced by the
		// measurement above at 44 false edges and 0 true ones, THE WITNESS
		// MOVED and this rule stands.
		//
		// P4 RE-MEASURED THAT PRICE RATHER THAN INHERITING IT. Under
		// `feat/D6-adj4`, 2026-08-11, over the acceptance fixture, with this
		// branch forced never-taken (which is exactly round 2's rule) against
		// the shipped rule: 738 edges {655 direct, 39 method, 44 interface}
		// become 694 {655 direct, 39 method, 0 interface}, holes 3 either way.
		// All 44 are named `String`, they come from 8 sites, and every one is a
		// concrete receiver — `b.String()` at cmd/gates/preserve.go:509 and
		// cmd/iterate/preserve.go:458, `t.String()` at cmd/gates/preserve.go:739
		// and cmd/iterate/preserve.go:697, `stderr.String()` in four seal
		// helpers. Removed 44, added 0.
		//
		// Both ways of forcing the old witness green were rejected, and they are
		// named here so no later round re-proposes them. Emitting the resolved
		// edge AND the fan-out leaves the false certification that is half the
		// harm above. Suppressing the fan-out only where the resolved target
		// lands in-tree keeps a provably-false edge in exactly the case where it
		// is provably false.
		//
		// The amended row now carries BOTH receivers, because neither half
		// catches both errors: measured under `feat/D6-adj4`, forcing this
		// branch always-taken leaves `stamp` green and reddens the interface
		// half, and forcing it never-taken leaves `describe` green and reddens
		// the concrete half. A future round that deletes either receiver from
		// that fixture has removed the guard on one of these two directions.
		//
		// P4 RULING (D6 adjudication round 3, 2026-08-11) — "SUPERSET OF THE
		// POSSIBLE IN-TREE TARGETS" IS FALSE ACROSS PACKAGES, AND THE ERROR
		// RUNS BOTH WAYS AT ONE CALL SITE. `w.methods` holds this unit's
		// methods only, so a method call on a type declared in ANOTHER IN-TREE
		// package fans out over the wrong set.
		//
		// Measured under `feat/D6-body` @ `f4c7c46`, 2026-08-11, over a tree
		// with `example.com/app` at `sub/` and `example.com/app/internal/core`
		// declaring `func (t *T) Ptr()`, `func (t T) Value()` and `func New()
		// *T`, called from `sub/main.go` as `v := core.New(); v.Ptr();
		// (*v).Value()`:
		//
		//	no in-unit method named Ptr    `v.Ptr()` emits NOTHING. The graph
		//	                               holds core.(*T).Ptr and core.(T).Value
		//	                               with no incoming edge, so two methods
		//	                               production calls read as UNCALLED —
		//	                               a manufactured BREACH.
		//	an in-unit `func (Decoy) Ptr`  the SAME site emits an `interface`
		//	                               edge to `…/sub.(Decoy).Ptr`, a method
		//	                               production never calls — and
		//	                               core.(*T).Ptr STILL reads as
		//	                               uncalled. One call site, one false
		//	                               BREACH and one false certification.
		//
		// The fan-out is right for genuine INTERFACE dispatch, where
		// `selection.Obj()` is the interface's method and no implementation is
		// named. It is wrong for a CONCRETE receiver whose type is declared
		// elsewhere, where go/types has already resolved the one target and
		// `w.calleeKey(fn)` can spell it. THE DISCRIMINATOR IS THE RECEIVER,
		// not the unit: `selection.Kind() == types.MethodVal` and the receiver
		// base type's underlying type is not an `*types.Interface` means the
		// target is a single declaration, and it must be emitted as `edgeMethod`
		// with `w.calleeKey(fn)` so the Python side can rejoin it exactly as it
		// rejoins a cross-package func call.
		if !isInterfaceReceiver(selection.Recv()) {
			w.edge(owner, w.calleeKey(fn), edgeMethod, w.site(sel.Sel.Pos()))
			return
		}
		for _, key := range w.methods[sel.Sel.Name] {
			w.edge(owner, key, edgeInterface, w.site(sel.Sel.Pos()))
		}
	case types.FieldVal:
		// `c.handler(x)`: a struct FIELD of func type. Any file in the program
		// may store any value in it, so nothing names the target.
		w.hole(owner, sel.Sel.Pos(), fmt.Sprintf(
			"call through the struct field %q, which holds a func value",
			sel.Sel.Name))
	default:
		w.hole(owner, sel.Sel.Pos(), fmt.Sprintf(
			"selector %q has a selection kind this walk does not classify",
			sel.Sel.Name))
	}
}

// classifyInstantiation separates `F[T](x)` — a generic call, whose target is
// named — from `fns[i](x)`, which indexes a value and names nothing.
func (w *walker) classifyInstantiation(base ast.Expr, call *ast.CallExpr, owner string, decl *ast.FuncDecl, consumed map[*ast.Ident]bool) {
	switch typed := unparen(base).(type) {
	case *ast.Ident:
		if _, ok := w.info.Uses[typed].(*types.Func); ok {
			w.classifyIdentCall(typed, owner, decl, consumed)
			return
		}
	case *ast.SelectorExpr:
		if _, ok := w.info.Uses[typed.Sel].(*types.Func); ok {
			w.classifySelectorCall(typed, owner, decl, consumed)
			return
		}
	}
	w.hole(owner, call.Lparen, "call through an indexed value, which names no declaration")
}

func markIdents(expr ast.Expr, consumed map[*ast.Ident]bool) {
	ast.Inspect(expr, func(node ast.Node) bool {
		if ident, ok := node.(*ast.Ident); ok {
			consumed[ident] = true
		}
		return true
	})
}

// soleBindingFuncLiteral discharges the four obligations of the SOLE-BINDING
// FUNC LITERAL rule, or declines.
//
// THE POSITIVE CLAIM IT RESTS ON is a theorem about Go: the identifiers that
// can name a function-local variable are exactly the identifiers inside that
// function's own declaration. So the region to search is one finite AST subtree
// and the search over it is EXHAUSTIVE rather than best-effort.
//
// Obligation 3 is stated FAIL-CLOSED — every occurrence must be shown to be a
// READ — and that is deliberate. The first draft of this rule enumerated the
// ASSIGNING constructs and cleared anything it did not recognise;
// `for _, f = range fns` is an *ast.RangeStmt and not an *ast.AssignStmt, so it
// walked straight through and CLEARED a call whose target is rebound every
// iteration. An enumeration of the forms that WRITE is an open list that grows
// with the language and defaults to CLEAR; requiring proof of READ is closed
// under language growth.
//
// Keyed on the *types.Var and never on the NAME, which is what makes shadowing
// clear both calls and bind each to its own literal.
func (w *walker) soleBindingFuncLiteral(ident *ast.Ident, variable *types.Var, decl *ast.FuncDecl) bool {
	// OBLIGATION 1 — LOCALITY. Established by FINDING the binding inside D's
	// body, never by failing to find one elsewhere. A package-level var fails
	// here (its binding is in no D) and so does a parameter (bound by D's
	// signature, so its value is the caller's).
	if decl == nil || decl.Body == nil {
		return false
	}
	def, ok := w.defIdent[variable]
	if !ok || def.Pos() < decl.Body.Pos() || def.Pos() >= decl.Body.End() {
		return false
	}

	// OBLIGATION 2 — THE SOLE BINDING IS A LITERAL, positionally matched. A
	// TUPLE binding fails: the value comes from one multi-valued expression and
	// no literal is named — which is where `ctx, cancel := context.WithTimeout`
	// lands, so the two `cancel` sites never even reach the provenance
	// question. A named func on the right, a range clause and a declaration
	// with no initialiser fail here too.
	binder := w.bindingOf(decl, def)
	if binder == nil {
		return false
	}

	// OBLIGATIONS 3 and 3b — EVERY OCCURRENCE IS A READ, and `&v` is taken
	// nowhere.
	return w.everyOccurrenceIsARead(decl, variable, def, binder)
}

// bindingOf returns the statement that binds `def` to a single *ast.FuncLit, or
// nil. Nil is the answer for a tuple binding, a range variable, a named-func
// initialiser and a declaration with no value.
func (w *walker) bindingOf(decl *ast.FuncDecl, def *ast.Ident) ast.Node {
	var binder ast.Node
	ast.Inspect(decl.Body, func(node ast.Node) bool {
		if binder != nil {
			return false
		}
		switch typed := node.(type) {
		case *ast.AssignStmt:
			if typed.Tok != token.DEFINE {
				return true
			}
			for index, target := range typed.Lhs {
				if target != ast.Expr(def) {
					continue
				}
				if len(typed.Rhs) != len(typed.Lhs) {
					return false
				}
				if _, isLiteral := unparen(typed.Rhs[index]).(*ast.FuncLit); isLiteral {
					binder = typed
				}
				return false
			}
		case *ast.ValueSpec:
			for index, name := range typed.Names {
				if name != def {
					continue
				}
				if len(typed.Values) != len(typed.Names) {
					return false
				}
				if _, isLiteral := unparen(typed.Values[index]).(*ast.FuncLit); isLiteral {
					binder = typed
				}
				return false
			}
		}
		return true
	})
	return binder
}

// everyOccurrenceIsARead is the fail-closed half: an exhaustive switch on each
// occurrence's PARENT node that DECLINES on any node type it does not classify.
func (w *walker) everyOccurrenceIsARead(decl *ast.FuncDecl, variable *types.Var, def *ast.Ident, binder ast.Node) bool {
	read := true
	var stack []ast.Node
	ast.Inspect(decl, func(node ast.Node) bool {
		if node == nil {
			stack = stack[:len(stack)-1]
			return true
		}
		if ident, ok := node.(*ast.Ident); ok && len(stack) > 0 {
			if w.info.Uses[ident] == types.Object(variable) || w.info.Defs[ident] == types.Object(variable) {
				if !isReadOccurrence(ident, stack[len(stack)-1], def, binder) {
					read = false
				}
			}
		}
		stack = append(stack, node)
		return true
	})
	return read
}

func isReadOccurrence(ident *ast.Ident, parent ast.Node, def *ast.Ident, binder ast.Node) bool {
	if ident == def && parent == binder {
		// The binding itself, already established as a single func literal.
		return true
	}
	switch typed := parent.(type) {
	case *ast.AssignStmt:
		for _, target := range typed.Lhs {
			if target == ast.Expr(ident) {
				return false
			}
		}
		return true
	case *ast.ValueSpec:
		for _, name := range typed.Names {
			if name == ident {
				return false
			}
		}
		return true
	case *ast.RangeStmt:
		// `for _, f = range fns` rebinds f once per iteration and is NOT an
		// assignment statement. This is the measured defect the fail-closed
		// form exists to catch.
		if typed.Key == ast.Expr(ident) || typed.Value == ast.Expr(ident) {
			return false
		}
		return true
	case *ast.UnaryExpr:
		// OBLIGATION 3b. Taking the address is the one route by which the value
		// changes with no syntax naming it (`p := &v; *p = g`), and it is what
		// makes obligation 3 a claim about the VALUE rather than the syntax.
		return typed.Op != token.AND
	case *ast.IncDecStmt:
		return false
	case *ast.CallExpr, *ast.BinaryExpr, *ast.ParenExpr, *ast.SelectorExpr,
		*ast.IndexExpr, *ast.IndexListExpr, *ast.SliceExpr, *ast.StarExpr,
		*ast.TypeAssertExpr, *ast.KeyValueExpr, *ast.CompositeLit,
		*ast.ReturnStmt, *ast.ExprStmt, *ast.SendStmt, *ast.IfStmt,
		*ast.SwitchStmt, *ast.TypeSwitchStmt, *ast.ForStmt, *ast.CaseClause,
		*ast.CommClause, *ast.SelectStmt, *ast.BlockStmt, *ast.DeferStmt,
		*ast.GoStmt, *ast.Field, *ast.FuncLit, *ast.LabeledStmt:
		// Escape BY VALUE — returned, stored in a struct, passed as an
		// argument, captured read-only by another closure — CLEARS, because a
		// copy of a func value cannot change the variable it was copied from.
		return true
	default:
		// The decline branch, and the whole point of the inversion: a writing
		// construct this switch has never heard of still has to NAME the
		// variable, and its parent lands here.
		return false
	}
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
