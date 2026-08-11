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
