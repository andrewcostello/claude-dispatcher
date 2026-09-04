

# --- Go: a symbol MOVED between files of one package is not a change -------


def test_a_go_symbol_moved_within_its_package_is_not_a_signature_change():
    """Splitting one Go file into several does not change the package surface.

    Go's SURFACE_RULES row says `merges_across_files=False` because "every
    cross-file contribution is an ADDED key ... redeclaring an existing key
    does not compile". True for ADDITIONS, and it misses MOVES: a symbol
    deleted from ledger.go and added to post.go redeclares nothing, compiles,
    and leaves every caller untouched. The per-file view sees only the
    deletion.

    Measured 2026-09-03: WAL-LEDGER-3 split a 400-line ledger.go into
    ledger.go + post.go + validate.go, moving Post, Validate, ServiceCredit
    and CreditCorrection byte-identically. The role gate reported "4 changed
    scaffolded signature(s)" and BLOCKED. Compared package-wide: 5 exported
    functions before, 5 after, 0 changed. That is 17 more bodies tasks that
    would block for tidying their own scaffold.
    """
    from claude_dispatcher import role_protocol as rp
    changes = (
        rp.SignatureChange(path="pkg/ledger/ledger.go", symbol="Post",
                           before="func Post(ctx, req) (Posted, error)", after=None),
        rp.SignatureChange(path="pkg/ledger/ledger.go", symbol="Gone",
                           before="func Gone() error", after=None),
    )
    # `Post` reappears intact in a sibling file; `Gone` does not.
    package_now = {
        "pkg/ledger/post.go": {"Post": "func Post(ctx, req) (Posted, error)"},
        "pkg/ledger/validate.go": {"Validate": "func Validate(req) error"},
    }
    kept = rp.drop_moved_go_symbols(changes, package_now)
    assert [c.symbol for c in kept] == ["Gone"], [c.symbol for c in kept]


def test_a_go_symbol_that_reappears_with_a_different_signature_still_counts():
    """A move is only a move when the signature is IDENTICAL. Relocating a
    function AND widening its parameters is still a contract change."""
    from claude_dispatcher import role_protocol as rp
    changes = (
        rp.SignatureChange(path="pkg/ledger/ledger.go", symbol="Post",
                           before="func Post(ctx, req) (Posted, error)", after=None),
    )
    package_now = {"pkg/ledger/post.go": {
        "Post": "func Post(ctx, req, extra) (Posted, error)"}}
    assert len(rp.drop_moved_go_symbols(changes, package_now)) == 1


def test_only_removals_are_reconciled():
    """A symbol changed IN PLACE (after is not None) is a real change and must
    survive, whatever else the package holds."""
    from claude_dispatcher import role_protocol as rp
    changes = (
        rp.SignatureChange(path="pkg/ledger/ledger.go", symbol="Post",
                           before="func Post(a) error", after="func Post(a, b) error"),
    )
    package_now = {"pkg/ledger/ledger.go": {"Post": "func Post(a) error"}}
    assert len(rp.drop_moved_go_symbols(changes, package_now)) == 1


def test_the_move_reconciliation_is_actually_called(tmp_path):
    """END TO END through check_branch, not the helper in isolation.

    `drop_moved_go_symbols` was merged (PR #93) DEFINED AND NEVER CALLED — the
    seventh correct-but-inert change in one session. Sealing the helper
    directly passes whatever the caller does, so this seal drives a real
    branch: a Go file split in two, every symbol moved intact.
    """
    import subprocess
    from claude_dispatcher import role_protocol as rp

    def git(*a):
        return subprocess.run(["git", *a], cwd=tmp_path, capture_output=True,
                              text=True, check=True).stdout
    git("init", "-q", "-b", "main"); git("config", "user.email", "t@t")
    git("config", "user.name", "t")
    pkg = tmp_path / "pkg" / "ledger"; pkg.mkdir(parents=True)
    (pkg / "ledger.go").write_text(
        "package ledger\n\n"
        "func Post(a int) error { return nil }\n\n"
        "func Validate(a int) error { return nil }\n", encoding="utf-8")
    git("add", "-A"); git("commit", "-qm", "scaffold")
    base = git("rev-parse", "HEAD").strip()

    git("checkout", "-q", "-b", "bodies")
    # The split: Post moves out verbatim, Validate stays.
    (pkg / "ledger.go").write_text(
        "package ledger\n\nfunc Validate(a int) error { return nil }\n",
        encoding="utf-8")
    (pkg / "post.go").write_text(
        "package ledger\n\nfunc Post(a int) error { return nil }\n",
        encoding="utf-8")
    git("add", "-A"); git("commit", "-qm", "split the file")

    res = rp.check_branch(repo_root=tmp_path, role=rp.Role.BODIES,
                          base_ref=base, branch_ref="bodies")
    changed = tuple(res.signature.changes) if res.signature else ()
    moved = [c.symbol for c in changed if c.symbol == "Post"]
    assert not moved, (
        f"a symbol moved intact within its package was reported as changed: "
        f"{[(c.symbol, c.path, c.after) for c in changed]}"
    )


def test_a_renamed_go_parameter_IS_a_change_and_here_is_why():
    """A Go parameter rename counts, and the reason is not obvious.

    Go parameters are positional, so no caller can observe a name, and it is
    tempting to conclude a rename should not block — I tried exactly that on
    2026-09-03 after WAL-LEDGER-3 lost a task cycle to `c` -> `credit`, and
    `tests/test_go_comparator.py` refused it in eight rows.

    THE CATCH IT PAYS FOR: `Move(src, dst string)` -> `Move(dst, src string)`
    is type-identical, compiles at every call site, and inverts the meaning of
    every one of them. A syntactic single-file comparison cannot tell that
    swap from two renames, so both are ruled the same way. On a ledger --
    `debit, credit`, `from, to` -- that swap is the worst class of defect
    available, and the parameter name is the only signal that distinguishes it.

    Recorded as a seal so the next reader meets the reasoning rather than
    rediscovering the cost. The right fix is to TELL the agent (PR #95), not to
    loosen the check.
    """
    from claude_dispatcher import role_protocol as rp
    fp = rp.support_for_path("x.go").fingerprinter.fingerprints
    a = fp("a.go", "package p\n\nfunc Move(src, dst string) {}\n")
    renamed = fp("b.go", "package p\n\nfunc Move(source, target string) {}\n")
    swapped = fp("c.go", "package p\n\nfunc Move(dst, src string) {}\n")
    assert a["Move"] != renamed["Move"], "a rename must count"
    assert a["Move"] != swapped["Move"], (
        "the swap is the catch the rename false positive pays for"
    )
