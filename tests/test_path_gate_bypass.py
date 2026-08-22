r"""Seals: a gate judges the FILE, not the string git printed for it.

The class
---------
Three CRITICALs, one defect, three places: **a path rendering that a gate
cannot see, reaching self-approval.**

    1. `risk.collect_diff` hands `risk.evaluate` git's C-quoted *rendering*
       of an awkward filename. Four of the nine default `forbidden_paths` —
       including `.github/**` — then match nothing, and a CI-config PR
       classifies `low`, which is exactly what `merge_engine` self-approves.
    2. The risk-gate seals that exist today are green on a fixture the
       production collector cannot emit, so nobody noticed.
    3. `seal_verify`'s `is_test_path` is asked the same question about the
       same rendering by `partition_changed`, answers "not a test", and the
       false-passing-seal gate SKIPS.

This has been fixed three times and survived each time, one module to the
left: git C-quoting defeated `role_protocol`'s deny table (fixed by decoding
in `changed_paths_between`); a real newline then defeated the glob→regex
translator (fixed with `re.DOTALL` in `risk._compiled`, which serves both
gates through one translator); and it is still open in `risk`'s own diff
collection and in `seal_verify`'s partition.

WHY THIS FILE INSISTS ON A REAL REPOSITORY
-------------------------------------------
Finding 2 is the reason every seal here runs `git` and reads what git
actually printed. A seal that is green on an input production cannot produce
is not protection — it reads as protection while testing nothing. So no row
below asserts against a hand-written path string alone; each one either

  * drives the production collector (`risk.collect_diff`,
    `seal_verify.partition_changed`, `role_protocol.changed_paths_between`,
    `merge_engine.merge_pass`) over a real repository, or
  * asserts a unit fact AND, in the same test, shows the real collector
    emitting that exact input.

Each row's docstring says under "Producible because" how that was
established.

WHAT WAS MEASURED (2026-08-09, against this worktree at `3f77755`)
-------------------------------------------------------------------
`git diff --numstat --no-renames main...f` on a repo containing one file per
character class, and the `.github/**` verdict `risk.evaluate` reaches for
each collected string:

    real filename                  collected by risk.collect_diff        .github/** ?
    .github/workflows/cix.yml      '.github/workflows/cix.yml'           True
    .github/workflows/ci x.yml     '.github/workflows/ci x.yml'          True
    .github/workflows/ci"x.yml     '".github/workflows/ci\"x.yml"'       False
    .github/workflows/ci\x.yml     '".github/workflows/ci\\\\x.yml"'     False
    .github/workflows/ci<TAB>x.yml '".github/workflows/ci\t x.yml"'      False
    .github/workflows/ci<LF>x.yml  '".github/workflows/ci\n x.yml"'      False
    .github/workflows/ci<CR>x.yml  '".github/workflows/ci\r x.yml"'      False
    .github/workflows/ci<ESC>x.yml '".github/workflows/ci\033x.yml"'     False
    .github/workflows/ciéx.yml     '".github/workflows/ci\303\251x.yml"' False

`core.quotePath=false` — which `role_protocol` passes and `risk` does not —
changes exactly ONE row of that table: the last one. Quote, backslash, TAB,
LF, CR and ESC are still C-quoted, because the setting governs high bytes and
those six classes are ASCII. Adding the flag to `risk`'s argv is therefore
not the fix; it is one ninth of it. (Measured, not inferred: the same repo
diffed with and without the flag, byte for byte identical except the `é`
line.) `--numstat -z` does emit raw paths — and a raw LF with them, which is
why the `re.DOTALL` already in `risk._compiled` is load-bearing for that
route and must stay.

WHICH GLOBS THE RENDERING DEFEATS, AND WHY IT IS NOT ALL OF THEM
------------------------------------------------------------------
The rendering wraps the path in `"`. `risk._compiled` anchors both ends, so
a glob is defeated exactly when a leading or trailing literal is pushed off
the end — and survives when `**/` swallows the opening quote and a trailing
`**` swallows the closing one:

    **/migrations/**   SURVIVES  (`(?:.*/)?` eats the `"`, `.*` eats the `"`)
    **/auth/**         SURVIVES
    **/*.proto         DEFEATED  (trailing literal `.proto` is not last)
    .github/**         DEFEATED  (leading literal `.github/` is not first)
    Dockerfile*        DEFEATED
    compose*.y*ml      DEFEATED
    go.mod / go.sum / pyproject.toml   not reachable (fixed root names never
                                       need quoting; their tree cannot)

That asymmetry is the whole reason a partial fix is plausible and must be
sealed against: two of the nine denials keep working by luck, which makes the
gate look mostly-alive while `.github/**` is wide open. And "keeps working"
is generous — a surviving denial still writes the RENDERING into its reason,
so the journal escalates `"db/migrations/0001_\303\255nit.sql"`, a file no
one can open. Both halves are asserted in
`test_every_default_forbidden_path_holds_against_the_collectors_rendering`.

DIRECTION OF EACH HOLE
----------------------
Fail-OPEN (a change gets past a gate that should stop it):

  * `forbidden_paths` misses the rendered path — `.github/**` &c. This is
    the CRITICAL: it ends in `merge_engine` self-approving and merging.
  * `risk.classify` returns `low` with reasons `()` for a filename that is
    not even valid UTF-8, where `role_protocol.changed_paths_between` raises.
  * `seal_verify.partition_changed` files the rendered test path under
    non-tests, so `run_seal_inversion` reports "skipped — no test files
    changed" and the false-passing-seal gate does not run at all.

Fail-CLOSED (honest work refused), sealed because this unit has ruled twice
that a false refusal is a defect too, and because a fixer who reads only the
fail-open rows will fix half the collector:

  * `test_globs` / `generated_globs` miss the rendered path, so a test file's
    churn is COUNTED toward the effective diff.
  * the docs-only carve-out (`_is_doc`, `.lower().endswith('.md')`) is denied
    to `docs/rëadme.md`, because the rendering ends in `"` and not in `.md`.
  * `is_test_path`'s ONE end-anchored alternative is `conftest\.py$`, and
    Python's `$` also matches immediately before a string-final newline. So
    the DIFFERENT file `src/conftest.py<LF>` is judged a test and denied to a
    body agent. This is precisely the `$`-for-`\Z` mistake that
    `risk._compiled`'s own docstring forbids, already present in the sibling
    matcher.

CORRECTIONS TO THE FINDINGS (measured; see the report for the full list)
--------------------------------------------------------------------------
  * "`is_test_path`'s regex ANCHOR bypass allows test modification" is two
    claims and only one is an anchor. The bypass that lets a seal through is
    the RENDERING, and it enters at `partition_changed`, which does not
    decode — `is_test_path` is handed a string that is not a path. The
    genuine anchor defect is `conftest\.py$` and it points the other way (it
    over-blocks). Separately, the two `^`-anchored alternatives `^tests?/`
    and `^spec/` are provably DEAD: `is_test_path` searches `"/" + path`, so
    position 0 is always `/` and `^` can never reach `tests`. They are
    harmless only because `/tests?/` and `/spec/` duplicate them — and the
    docstring's claim that the leading-slash normalisation is what those
    alternatives "need" is exactly backwards. Not sealed: removing dead
    alternatives is the fixer's call and a seal on them would over-constrain.
  * "`.github/**` forbidden-path gate is bypassed, so a CI-config PR
    self-approves" is CONFIRMED end to end, and it needs no adversary. The
    reproduction below uses `.github/workflows/déploy.yml` — an ordinary
    filename with an accent, not an attack — and it merges.
  * `risk.collect_diff`'s `path = "\t".join(parts[2:])  # paths with tabs are
    rare but possible` is dead code under the current argv: git escapes a TAB
    to `\t` inside the quoted form, so `parts` never has more than three
    entries. It is the tell that the author believed raw paths were arriving.
    Not sealed — the correct fix may make it live again (`-z`) or delete it.

WHAT THESE SEALS DELIBERATELY DO NOT DICTATE
----------------------------------------------
Which module decodes. `risk.py` owns the risk gate's collection and
`seal_verify.py` owns the seal gate's; `role_protocol._unquote_git_path` is
the existing, tested reverse of `quote_c_style` and the obvious thing to
share, but hoisting it, re-implementing it, or switching both collectors to
`-z` are all fixes these rows accept. Every assertion is on a collector's
output or on a gate's verdict, never on an argv or an import. (Both modules
are now on `role_protocol.FLOOR_GLOBS`, so the fix is a reviewed edit on the
protected base, not a body branch — see `tests/test_floor_closure.py`.)

The one thing they do dictate is that a fix must not be a strip: a filename
may legitimately contain `"`, and `"tests"/x.py` — a real directory named
with quotes — is NOT `tests/x.py`.
`test_a_name_that_merely_looks_quoted_is_not_decoded_twice` is green today
and reddens on any `strip('"')`-shaped fix.

DISPUTES FOR P4 — raised, not acted on
----------------------------------------
  1. **The anchor fix cannot land without amending an existing seal.**
     `tests/test_role_protocol_table.py::_TEST_PATH_PROBES` keys its probe
     table on the LITERAL text of each `seal_verify._TEST_PATH` alternative
     and checks those keys against the live pattern, so changing
     `conftest\.py$` to `conftest\.py\Z` reddens all 26 rows of
     `test_every_seal_verify_test_path_is_denied_to_every_delegated_role`.
     Measured: with the reference fix and no amendment, the full suite is
     26 failed, all of them that one parametrized seal; with the single key
     amended to `conftest\.py\Z`, 0 failed. The amendment is one token in a
     seal, so it is P4's to make and neither a body author's nor mine.
     (A fixer could dodge it by normalising inside `is_test_path` instead of
     changing the pattern; that is also a legitimate fix and reddens
     nothing.)

  2. **Four rows in `tests/test_glob_newline.py` are green on an input the
     production collector cannot emit.** Left ALONE — amending them is P4's
     call — but named precisely, because they are finding 2 itself:

         test_a_newline_named_file_under_a_forbidden_tree_is_still_forbidden
         test_a_newline_named_file_alone_under_a_forbidden_tree_classifies_low
         test_the_docs_only_carve_out_is_not_decided_by_a_glob
         test_a_newline_named_test_file_is_still_excluded_from_the_effective_diff

     Each drives `risk.evaluate` / `risk.effective_diff_lines` / `_is_doc`
     with a path containing a real line feed. Those three are reachable in
     production from exactly one place — `risk.classify` → `collect_diff` →
     `merge_engine` — and `collect_diff` renders a line feed as the two
     characters `\` `n` inside quotes. It has never handed `evaluate` a real
     newline and cannot. So those four rows are green, and the gate they
     describe is open on the input it actually receives. The remaining rows
     of that file are NOT in this category and must stay: everything in its
     sections 1 and 2 runs through `role_protocol.first_matching_glob` /
     `changed_paths_between`, which DOES decode and therefore does produce a
     real newline; `test_matches_any_glob_reads_a_newline_named_file_as_
     being_where_it_is` is producible by that same route; and section 4's
     `blast_radius` header is git's true rendering, written out.

     Note what this file does about it rather than to it:
     `test_every_character_git_quotes_leaves_the_ci_denylist_intact` asks for
     the same protection over the collector's own output, so once the
     collector is fixed the line feed arrives for real and `re.DOTALL`
     is pinned by a producible seal. Verified: on a fixed tree with
     `re.DOTALL` removed from `risk._compiled`, that row reddens on the line
     feed entry and only on it.

  3. **`is_test_path`'s docstring is wrong about its own normalisation.** It
     says the leading `"/"` is there because the pattern's `^`-anchored
     alternatives "need" it. The opposite: prefixing `/` puts a `/` at
     position 0, so `^tests?/` and `^spec/` can never match anything, and
     the pattern works only because `/tests?/` and `/spec/` duplicate them.
     Prose, and removing dead alternatives is a judgement call, so nothing
     here seals it.

NON-VACUITY AND JOINT SATISFIABILITY — evidence recorded in the report and
per row under "Red now" / "Green when" / "Falsify". Every row that reports a
bypass judges the awkward path AND its ordinary twin, wherever possible in
ONE call and ONE assertion, so no row can pass by the gate refusing
everything, and a fix that catches only the twin still reddens.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from claude_dispatcher import merge_engine as me
from claude_dispatcher import notify as notify_mod
from claude_dispatcher import risk, seal_verify, yaml_io
from claude_dispatcher.risk import ELEVATED, LOW
from claude_dispatcher.role_protocol import RoleDiffError, changed_paths_between

# The characters git C-quotes, written out. Named rather than inlined because
# a bare control character in a path literal is invisible in a diff and
# unreadable in a failure message. `PLAIN` and `SPACE` are the two that are
# NOT quoted and are the in-table controls.
PLAIN = ""
SPACE = " "
QUOTE = '"'
BACKSLASH = "\\"
TAB = "\t"
LF = "\n"
CR = "\r"
ESC = "\x1b"
ACCENT = "é"

#: Every character class, with the two unquoted controls first. Written out
#: literally; nothing below is derived from it by comprehension over a live
#: constant.
CHARACTER_TABLE: tuple[tuple[str, str], ...] = (
    ("plain", PLAIN),
    ("space", SPACE),
    ("double quote", QUOTE),
    ("backslash", BACKSLASH),
    ("tab", TAB),
    ("line feed", LF),
    ("carriage return", CR),
    ("escape", ESC),
    ("non-ASCII", ACCENT),
)


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", *args], cwd=str(repo), capture_output=True, text=True,
    )
    assert proc.returncode == 0, f"git {args!r} failed: {proc.stderr}"
    return proc.stdout


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A repo on `main` with one base commit; each seal branches off it.

    A real repository, never a stubbed `run`. The whole defect lives in the
    gap between git's rendering of an awkward name and what the gate matches,
    and a stub would let every row here pass against a string git never
    emits — which is finding 2 restated.
    """
    r = tmp_path / "repo"
    r.mkdir()
    _git(r, "init", "-q", "-b", "main")
    _git(r, "config", "user.email", "t@t")
    _git(r, "config", "user.name", "T")
    (r / "seed.txt").write_text("seed\n", encoding="utf-8")
    _git(r, "add", ".")
    _git(r, "commit", "-q", "-m", "base")
    _git(r, "checkout", "-q", "-b", "feat/x")
    return r


def _commit_files(repo: Path, *relpaths: str, body: str = "a\nb\nc\n") -> None:
    for rel in relpaths:
        p = repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "work")


def _row(key: str, *, pr_number: int, branch: str, labels: list[str]) -> dict:
    return {
        "key": key,
        "summary": f"summary {key}",
        "description": f"desc {key}",
        "type": "Task",
        "labels": labels,
        "status": "Awaiting Review",
        "branch": branch,
        "pr_number": pr_number,
        "pr_url": f"https://github.com/test/repo/pull/{pr_number}",
        "verified": True,
        "verification_iterations": 0,
    }


# --------------------------------------------------------------------------- #
# 1. `risk.collect_diff` — the collector hands on a rendering, not a path
# --------------------------------------------------------------------------- #


def test_the_risk_collector_names_the_file_rather_than_gits_rendering_of_it(
    repo: Path,
) -> None:
    r"""The defect at its smallest, and the root of all three findings.

    Two CI workflow files land in one commit, differing only by an accent.
    `risk.collect_diff` must report the two names the repository contains.

    Producible because: this IS the production collector, run on a real
    repository, with the argv `risk.collect_diff` builds. Nothing is
    hand-written except the two filenames, and `déploy.yml` is an ordinary
    name, not an adversarial one.

    Red now: the accented entry comes back as
    `'".github/workflows/d\303\251ploy.yml"'` — twenty-eight characters of
    git rendering, wrapped in quotes, with the accent octal-escaped.
    Green when: both entries are the names on disk.
    Falsify: the plain twin is in the same sorted assertion and is already
    correct, so a "fix" that mangles every path reddens on it.
    """
    accented = ".github/workflows/déploy.yml"
    plain = ".github/workflows/deploy.yml"
    _commit_files(repo, accented, plain)

    collected = sorted(f.path for f in risk.collect_diff(repo, "main", "feat/x"))

    assert collected == sorted([accented, plain]), (
        "the risk gate is handed git's rendering of the filename instead of "
        "the filename; a rendering is not a path and matches no glob"
    )


def test_every_character_git_quotes_reaches_the_risk_gate_as_the_path_it_is(
    repo: Path,
) -> None:
    r"""The exhaustive table — because a fix for one character is not a fix.

    One CI workflow file per character class, all in one commit, one
    `collect_diff` call, one assertion. Two of the nine (plain, space) are
    correct today and are the in-table controls.

    This row is also the seal against the smallest plausible wrong fix:
    adding `-c core.quotePath=false` to `risk`'s argv, which
    `role_protocol` already carries. Measured, that flag repairs the
    non-ASCII row and NOTHING else — quote, backslash, TAB, LF, CR and ESC
    are C-quoted whatever it says, because it governs high bytes only. A
    branch that adds the flag and stops still leaves six rows red here.

    Producible because: every one of these filenames was created on this
    filesystem and committed by git in this test; the renderings asserted
    against are whatever `collect_diff` returns, not a transcription.

    Red now: seven of the nine entries come back quoted and escaped.
    Green when: all nine come back as themselves.
    Falsify: the two unquoted controls are in the same assertion.
    """
    names = {label: f".github/workflows/ci{char}x.yml"
             for label, char in CHARACTER_TABLE}
    _commit_files(repo, *names.values())

    collected = sorted(f.path for f in risk.collect_diff(repo, "main", "feat/x"))

    assert collected == sorted(names.values()), (
        "`collect_diff` renames files according to what characters are in "
        f"them; expected the nine names on disk, got {collected!r}"
    )


def test_every_character_git_quotes_leaves_the_ci_denylist_intact(
    repo: Path,
) -> None:
    r"""The same nine files, carried all the way to the verdict.

    The row above stops at `collect_diff`'s output. This one is the same
    diff judged by `risk.classify`, and it exists because of finding 2: the
    newline seals in `tests/test_glob_newline.py` prove things about
    `risk.evaluate` on a path containing a real line feed, and
    `risk.collect_diff` cannot emit one — git C-quotes it to the two
    characters `\` `n`. So the glob engine's `re.DOTALL` is, on the risk
    gate's route, currently protecting an input that never arrives.

    Once the collector hands over real names that changes: a line feed in a
    workflow filename becomes a real line feed in the string
    `_first_matching_glob` sees, and `re.DOTALL` becomes load-bearing here
    too. This row is the one that would have caught the original defect and
    is the one that keeps the `DOTALL` fix honest afterwards — it asks for
    the DENIAL, over the collector's own output, for every character class
    at once.

    Producible because: the nine files are committed to this repository and
    the verdict is `risk.classify`'s over the real diff, with no fixture
    path written by hand anywhere in the chain.

    Red now: two reasons (plain, space) out of nine.
    Green when: nine reasons, one per file, each naming `.github/**`.
    Falsify: the two unquoted controls are in the same call and already
    produce their reasons; `test_an_ordinary_change_is_still_low_risk` keeps
    a forbid-everything classifier out; and removing `re.DOTALL` from
    `risk._compiled` on a fixed tree reddens exactly the line-feed entry.
    """
    names = {label: f".github/workflows/ci{char}x.yml"
             for label, char in CHARACTER_TABLE}
    _commit_files(repo, *names.values())

    task = {"labels": ["size:XS"], "verified": True, "verification_iterations": 0}
    verdict = risk.classify(task, repo, "main", head_ref="feat/x")
    got = sorted(r for r in verdict.reasons if r.startswith("forbidden path touched:"))

    want = sorted(
        f"forbidden path touched: {path} (matches .github/**)"
        for path in names.values()
    )
    assert got == want, (
        "a change to CI configuration stopped being a change to CI "
        "configuration because of a character in the filename; the classes "
        f"that got through are {sorted(set(want) - set(got))!r}"
    )
    assert verdict.level == ELEVATED


def test_a_filename_the_collector_cannot_render_is_not_a_low_risk_verdict(
    repo: Path,
) -> None:
    r"""Exhaustiveness at the bottom of the table: the unknown must RAISE.

    A filename that is not valid UTF-8 is legal on this filesystem and git
    will happily track it. `role_protocol.changed_paths_between` already
    refuses such a diff outright ("a path the gate cannot render is a path
    it cannot match, and an unmatchable path reports as a pass"). `risk`
    takes the other road and returns `low` with NO reasons — it reports that
    it looked at a `.github/` change and found nothing wrong with it.

    The seal states the property, not the mechanism: whatever `risk` does
    with an unrenderable path, the answer is not `low`. Raising inside
    `collect_diff` gets there via the existing `RiskDiffError` fail-closed
    path in `classify`; so does decoding it to something matchable.

    Producible because: the byte sequence is written to disk with
    `os.fsencode` and committed, and the assertion on
    `changed_paths_between` in the same test shows the sibling collector
    hitting the same input and refusing it — so this is not a hypothetical
    rendering, it is one the tree can hold today.

    Red now: `('low', ())`.
    Green when: not `low` (a reason naming the path, or a raise mapped to
    elevated by `classify`).
    Falsify: `innocent`, judged by the same call shape in the same test, is
    `low` today and must stay `low`, so a classifier that elevated
    everything reddens.
    """
    gh = os.fsencode(str(repo)) + b"/.github"
    os.makedirs(gh, exist_ok=True)
    with open(gh + b"/ci\xff.yml", "wb") as fh:
        fh.write(b"on: push\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "a workflow whose name is not UTF-8")

    # Evidence that this input is real and that the repo's other collector
    # already treats it as a hard failure rather than as an empty diff.
    with pytest.raises(RoleDiffError):
        changed_paths_between(repo, "main", "feat/x")

    task = {"labels": ["size:XS"], "verified": True, "verification_iterations": 0}
    verdict = risk.classify(task, repo, "main", head_ref="feat/x")

    # The refusal control: an ordinary branch off the same base stays low.
    _git(repo, "checkout", "-q", "main")
    _git(repo, "checkout", "-q", "-b", "feat/ordinary")
    _commit_files(repo, "src/util.py")
    innocent = risk.classify(task, repo, "main", head_ref="feat/ordinary")

    assert (verdict.level, innocent.level) == (ELEVATED, LOW), (
        "a workflow file whose name is not valid UTF-8 classified low-risk "
        f"with reasons {verdict.reasons!r}; the gate reported that it "
        "checked and found nothing"
    )


# --------------------------------------------------------------------------- #
# 2. The consequence in the classifier: the forbidden-path denylist
# --------------------------------------------------------------------------- #


def test_every_default_forbidden_path_holds_against_the_collectors_rendering(
    repo: Path,
) -> None:
    r"""Six of the nine defaults, each with an ordinary twin, in one diff.

    `go.mod`, `go.sum` and `pyproject.toml` are omitted deliberately and not
    by oversight: they are fixed root filenames, so git never has cause to
    quote them and no rendering of them exists to test. The other six each
    get an accented file under them plus its ASCII twin.

    Measured today, the rendering defeats four and two survive by luck:
    `**/migrations/**` and `**/auth/**` still match because `(?:.*/)?`
    swallows the opening quote and the trailing `.*` swallows the closing
    one. That is why this row is a table rather than one `.github/**` case —
    a gate that is two-thirds alive invites a fix that only repairs the part
    someone noticed.

    Producible because: every path is a file committed to this repository
    and the verdict is read off `risk.classify` over the real diff.

    Red now: six of the twelve expected reasons are wrong, in two different
    ways, and the difference matters to whoever reads the journal.
    `**/*.proto`, `.github/**`, `Dockerfile*` and `compose*.y*ml` produce NO
    reason at all for their accented file — that is the bypass.
    `**/migrations/**` and `**/auth/**` do produce one, but it names
    `"db/migrations/0001_\303\255nit.sql"`, a file that does not exist. So
    even where the denylist survives, its report is unusable: a human
    checking the escalation cannot find the file it names.
    Green when: twelve reasons, one per path, each naming a real file.
    Falsify: the six ASCII twins are in the same call and already produce
    their reasons, so a fix that only reworded the message still reddens;
    and `test_an_ordinary_change_is_still_low_risk` keeps a
    forbid-everything classifier out.
    """
    pairs = (
        ("**/migrations/**", "db/migrations/0001_ínit.sql", "db/migrations/0002_init.sql"),
        ("**/*.proto", "api/úser.proto", "api/user.proto"),
        ("**/auth/**", "internal/auth/tóken.go", "internal/auth/token.go"),
        (".github/**", ".github/workflows/dépl.yml", ".github/workflows/depl.yml"),
        ("Dockerfile*", "Dockerfile.pród", "Dockerfile.prod"),
        ("compose*.y*ml", "compose.pród.yml", "compose.prod.yml"),
    )
    _commit_files(repo, *[p for _, awkward, plain in pairs for p in (awkward, plain)])

    task = {"labels": ["size:XS"], "verified": True, "verification_iterations": 0}
    verdict = risk.classify(task, repo, "main", head_ref="feat/x")
    got = sorted(r for r in verdict.reasons if r.startswith("forbidden path touched:"))

    want = sorted(
        f"forbidden path touched: {path} (matches {glob})"
        for glob, awkward, plain in pairs
        for path in (awkward, plain)
    )
    assert got == want, (
        "the denylist stopped seeing files whose names carry an accent; the "
        f"missing entries are {sorted(set(want) - set(got))!r}"
    )
    assert verdict.level == ELEVATED


def test_an_ordinary_change_is_still_low_risk(repo: Path) -> None:
    """The refusal control for every classifier row in this file.

    Green now. Green when: still green.
    Falsify: it is the row that a forbid-everything or elevate-everything
    "fix" reddens, which is the only way the rows above could go green
    without the gate actually working.
    """
    _commit_files(repo, "src/util.py")
    task = {"labels": ["size:XS"], "verified": True, "verification_iterations": 0}
    verdict = risk.classify(task, repo, "main", head_ref="feat/x")
    assert (verdict.level, verdict.reasons) == (LOW, ())


def test_a_ci_config_pr_does_not_self_approve_because_of_its_filename(
    repo: Path,
) -> None:
    r"""The CRITICAL end to end, stated as the thing a human would read in
    the tasks YAML the morning after.

    Two PRs, identical in every respect except one accent in a workflow
    filename, in ONE merge pass against one stubbed `gh`. The gate's job is
    to hold both for external approval, because both edit CI configuration.

    This is at the merge-engine level and not only at `risk.classify`
    because the unit-level statement alone would let the fix be made in the
    wrong layer — and because "self-approves" is a property of
    `merge_engine`'s ladder (`verdict.is_low` → `DISPATCHER_APPROVER`), not
    of the classifier. Nothing here stubs the risk gate.

    Producible because: `merge_pass` is the production entry point, the two
    branches are real refs with real commits, and the only stub is `gh`
    (network). `déploy.yml` needs no adversary to exist.

    Red now: `merged == ['Q']`, `Q`'s row reads
    `pr_approved_by: dispatcher-agent`, `status: Merged`.
    Green when: `merged == []` and both rows are held at Awaiting Review.
    Falsify: `P`, the ASCII twin, is in the same pass and is already held —
    so a change that simply stopped merging anything would leave `P`'s row
    identical and could not be told from a fix by the assertion below alone;
    that is why the assertion is on BOTH rows and on `awaiting_approval`,
    and why `test_an_ordinary_change_is_still_low_risk` pins the low path
    open.
    """
    gh = repo / "fake_gh.py"
    gh.write_text(
        "#!/usr/bin/env python3\n"
        "import sys, json\n"
        "a = sys.argv[1:]\n"
        'if "view" in a:\n'
        '    print(json.dumps({"reviews": []}))\n'
        "    sys.exit(0)\n"
        "sys.exit(0)\n",
        encoding="utf-8",
    )
    gh.chmod(0o755)
    _git(repo, "checkout", "-q", "main")
    _git(repo, "branch", "feature/x", "main")

    for branch, filename in (
        ("feat-accented", ".github/workflows/déploy.yml"),
        ("feat-plain", ".github/workflows/deploy.yml"),
    ):
        wt = repo.parent / f"wt-{branch}"
        _git(repo, "worktree", "add", "-b", branch, str(wt), "feature/x")
        target = wt / filename
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("on: push\njobs: {}\n", encoding="utf-8")
        _git(wt, "add", "-A")
        _git(wt, "commit", "-q", "-m", "ci")
        _git(repo, "worktree", "remove", "--force", str(wt))

    tasks_path = repo / "tasks.yaml"
    yaml_io.dump(
        {"project": "T", "epic": "X", "tasks": [
            _row("Q", pr_number=1, branch="feat-accented", labels=["size:XS"]),
            _row("P", pr_number=2, branch="feat-plain", labels=["size:XS"]),
        ]},
        tasks_path,
    )
    cfg = me.MergeEngineConfig(
        tasks_path=tasks_path, repo_root=repo, feature_branch="feature/x",
        gh_bin=str(gh), run_id="run-1",
    )

    result = me.merge_pass(cfg, notifier=notify_mod.NullNotifier())

    rows = {t["key"]: t for t in yaml_io.load(tasks_path)["tasks"]}
    assert [
        (result.merged, sorted(result.awaiting_approval)),
        (rows["Q"]["status"], rows["Q"].get("pr_approved_by")),
        (rows["P"]["status"], rows["P"].get("pr_approved_by")),
    ] == [
        ([], ["P", "Q"]),
        ("Awaiting Review", None),
        ("Awaiting Review", None),
    ], (
        "a PR that edits .github/ self-approved and merged with no human in "
        "the loop, because its filename carried an accent and the denylist "
        "was shown git's rendering instead of the name"
    )


def test_a_test_file_is_excluded_from_the_effective_diff_however_git_renders_it(
    repo: Path,
) -> None:
    r"""The same blindness pointing the SAFE way — a false refusal, sealed
    for correctness and so the fixer does not repair only the fail-open half.

    `test_globs` shrinks the counted diff so thorough tests cannot push a
    small change out of low-risk. A test file whose name git must quote is
    not recognised as a test, so its churn is counted. Nobody is exploited by
    this; a change is over-escalated. Recorded plainly.

    Producible because: both files are committed here and the counts come
    from `risk.collect_diff` + `risk.effective_diff_lines` over the real
    diff. `tést_thing.py` is an ordinary filename.

    Red now: `[300, 0]` — the accented test file's 300 lines are counted and
    its twin's are not.
    Green when: `[0, 0]`.
    Falsify: the ASCII twin is in the same assertion, so a matcher that
    excluded nothing reddens on the second entry, and one that excluded
    everything reddens `test_an_ordinary_change_is_still_low_risk`.
    """
    body = "x = 1\n" * 300
    _commit_files(repo, "tests/tést_thing.py", body=body)
    _git(repo, "checkout", "-q", "main")
    _git(repo, "checkout", "-q", "-b", "feat/twin")
    _commit_files(repo, "tests/test_thing.py", body=body)

    def _count(branch: str) -> int:
        return risk.effective_diff_lines(
            risk.collect_diff(repo, "main", branch), risk.RiskConfig()
        )

    assert [_count("feat/x"), _count("feat/twin")] == [0, 0], (
        "`tests/**` excludes a file under `tests/` whatever characters its "
        "name contains"
    )


def test_the_docs_only_carve_out_survives_an_accent_in_the_filename(
    repo: Path,
) -> None:
    r"""The other false refusal, and a correction to an existing correction.

    `tests/test_glob_newline.py` establishes — correctly — that `_is_doc` is
    `path.lower().endswith('.md')`, a plain string test with no glob in it,
    and is therefore indifferent to a newline. True, and it stays true. But
    the collector's rendering ends in `"`, not in `.md`, so on the input
    production actually supplies the carve-out IS lost. The two statements
    are about different inputs and neither weakens the other; this row exists
    because the earlier one reads, at a glance, as "the carve-out is not part
    of this defect".

    Size XL and `verified: false` make the carve-out load-bearing: without
    it, both branches are elevated for reasons that have nothing to do with
    the filename, and the row would prove nothing.

    Producible because: both branches are committed and judged by
    `risk.classify` over the real diff.

    Red now: `(ELEVATED, LOW)` — the accented documentation change is
    escalated and its twin is not.
    Green when: `(LOW, LOW)`.
    Falsify: the ASCII twin, judged by the same call in the same test, is
    `low` today; a fix that granted the carve-out to everything reddens
    `test_every_default_forbidden_path_holds_against_the_collectors_rendering`.
    """
    _commit_files(repo, "docs/rëadme.md", body="# doc\n" * 400)
    _git(repo, "checkout", "-q", "main")
    _git(repo, "checkout", "-q", "-b", "feat/twin")
    _commit_files(repo, "docs/readme.md", body="# doc\n" * 400)

    task = {"labels": ["size:XL"], "verified": False, "verification_iterations": 3}

    def _level(branch: str) -> str:
        return risk.classify(task, repo, "main", head_ref=branch).level

    assert (_level("feat/x"), _level("feat/twin")) == (LOW, LOW), (
        "a documentation-only change stopped being documentation because "
        "its filename carries an accent"
    )


# --------------------------------------------------------------------------- #
# 3. `seal_verify` — the same rendering, the same predicate, the gate SKIPS
# --------------------------------------------------------------------------- #


def test_the_seal_partition_names_the_files_rather_than_gits_rendering(
    repo: Path,
) -> None:
    r"""`partition_changed` is the third collector and the third place the
    rendering leaks in.

    A fix plus its seal: one production file, one test file whose name git
    must quote, one ASCII test file as the control. All three must come back
    as themselves, and the two test files must land on the tests side.

    Producible because: this is `seal_verify.partition_changed` itself, over
    a real repository, reading real `git diff --name-status` output.

    Red now: tests holds only `tests/test_thing.py`; non_tests holds
    `src/prod.py` and `'"tests/t\303\251st_thing.py"'`.
    Green when: tests holds both test paths under their real names.
    Falsify: the ASCII test file is already on the correct side, so a
    partition that put everything in `tests` reddens on `src/prod.py`.
    """
    _commit_files(repo, "src/prod.py", "tests/tést_thing.py", "tests/test_thing.py")

    tests, non_tests = seal_verify.partition_changed(repo, "main")

    assert (sorted(p for _s, p in tests), sorted(p for _s, p in non_tests)) == (
        ["tests/test_thing.py", "tests/tést_thing.py"],
        ["src/prod.py"],
    ), (
        "the seal gate was handed git's rendering of a test filename and "
        "filed the seal under 'not a test'"
    )


def test_the_seal_inversion_gate_is_not_skipped_by_the_name_of_the_seal(
    repo: Path,
) -> None:
    r"""The consequence, and the sharpest of the three: the whole
    false-passing-seal gate does not run.

    Two branches with the same shape — a production change plus one new test
    — differing only by an accent in the test's filename. `run_seal_inversion`
    must reach the same judgement on both. Today the accented one never gets
    judged at all: with no path recognised as a test, the gate returns
    `skipped, "no test files changed — nothing claims to seal"` before it
    inverts anything.

    The assertion compares the two OUTCOMES rather than naming one, because
    which verdict a stub `test_command` earns is not this row's business —
    the defect is that one branch is judged and the other is waved through.

    Producible because: both branches are real commits and
    `run_seal_inversion` is called with no stubs but the test command.

    Red now: `("skipped", "failed")`.
    Green when: the two outcomes are equal.
    Falsify: the ASCII twin is the second half of the tuple and is a real
    judgement today, so a change that made everything skip reddens.
    """
    _commit_files(repo, "src/prod.py")
    _git(repo, "checkout", "-q", "main")
    _git(repo, "checkout", "-q", "-b", "feat/accented")
    _commit_files(repo, "src/prod.py", "tests/tést_thing.py")
    _git(repo, "checkout", "-q", "main")
    _git(repo, "checkout", "-q", "-b", "feat/plain")
    _commit_files(repo, "src/prod.py", "tests/test_thing.py")

    def _outcome(branch: str) -> str:
        _git(repo, "checkout", "-q", branch)
        return seal_verify.run_seal_inversion(
            worktree=repo, base="main", test_command="true", timeout_seconds=30,
        ).outcome

    accented, plain = _outcome("feat/accented"), _outcome("feat/plain")

    assert accented == plain, (
        "the seal-inversion gate skipped a fix branch entirely because the "
        f"new test's filename carried an accent ({accented!r} vs {plain!r} "
        "for the identical branch with an ASCII name)"
    )
    assert plain != "skipped", (
        "control: the ASCII twin must be a real judgement, or the row above "
        "would pass by both branches skipping"
    )


def test_is_test_path_is_anchored_at_the_end_of_the_string_not_at_a_line_break(
    repo: Path,
) -> None:
    r"""The genuine ANCHOR defect, pointing the other way.

    `_TEST_PATH`'s one end-anchored alternative is `conftest\.py$`. Python's
    `$` matches at the end of the string OR immediately before a
    string-final newline, so the file `src/conftest.py<LF>` — a DIFFERENT
    file from `src/conftest.py`, which a body agent may legitimately add — is
    judged one of the repo's tests and denied.

    This is the exact mistake `risk._compiled`'s docstring names and forbids
    ("`$` in place of `\Z` — the 'handle line endings' reflex... `$` also
    matches immediately BEFORE a string-final newline"), present in the
    sibling matcher, where it has never been sealed. `\r` is already correct
    for the same reason `\Z` is, and is the in-assertion control.

    Producible because: the file is created and committed here, and
    `changed_paths_between` — the collector that feeds the role gate's
    delegation to this predicate — is asserted in the same test to return
    that exact string with a REAL line feed in it. This is not a rendering;
    the decode is working and this is what it hands over.

    Red now: `[True, True, False, False]` — the first entry is the bug.
    Green when: `[False, True, False, False]`.
    Falsify: `src/conftest.py` is in the same assertion and must stay True,
    so a fix that simply deleted the alternative reddens; and
    `test_the_seal_partition_names_the_files_rather_than_gits_rendering`
    keeps a says-no-to-everything predicate out.
    """
    newline_named = "src/conftest.py" + LF
    _commit_files(repo, newline_named, "src/conftest.py")

    assert sorted(changed_paths_between(repo, "main", "feat/x")) == sorted(
        [newline_named, "src/conftest.py"]
    ), "producibility: the role gate's collector emits this name, decoded"

    assert [
        seal_verify.is_test_path(newline_named),
        seal_verify.is_test_path("src/conftest.py"),
        seal_verify.is_test_path("src/conftest.py" + CR),
        seal_verify.is_test_path("src/prod.py" + LF),
    ] == [False, True, False, False], (
        "`conftest\\.py$` matched a file whose name merely ENDS with a "
        "newline after those characters; `$` is not `\\Z`"
    )


# --------------------------------------------------------------------------- #
# 4. The class, stated once: three collectors, one answer
# --------------------------------------------------------------------------- #


def test_the_three_collectors_name_the_same_files(repo: Path) -> None:
    r"""One branch, three production collectors, one set of names.

    `role_protocol.changed_paths_between` decodes; `risk.collect_diff` and
    `seal_verify.partition_changed` do not. That divergence IS the class —
    the same repository state, read three ways, produces three different
    answers, and the two that skip the decode are the two with a live
    CRITICAL. Sealing the agreement rather than the mechanism leaves the
    fixer free to hoist the existing `_unquote_git_path`, to re-implement it,
    or to move all three to `-z`.

    The branch carries one file per hole plus an ordinary control, so this
    row cannot pass by all three collectors being equally broken on an easy
    input.

    Producible because: it is three production entry points over one real
    repository. Nothing here is written by hand except the filenames.

    Red now: `changed_paths_between` returns the four real names; the other
    two return three renderings and one name.
    Green when: all three return the same four names.
    Falsify: the ordinary file is in the set, so three collectors that all
    returned `()` would still have to agree on it; and each collector has
    its own row above pinning what the shared answer must BE.
    """
    names = [
        ".github/workflows/dépl.yml",
        "tests/tést_thing.py",
        'src/say"hi".py',
        "src/ordinary.py",
    ]
    _commit_files(repo, *names)

    from_role = sorted(changed_paths_between(repo, "main", "feat/x"))
    from_risk = sorted(f.path for f in risk.collect_diff(repo, "main", "feat/x"))
    tests, non_tests = seal_verify.partition_changed(repo, "main")
    from_seal = sorted(p for _s, p in [*tests, *non_tests])

    assert [from_role, from_risk, from_seal] == [sorted(names)] * 3, (
        "the three gates read one repository and disagree about what is in "
        "it; the two that disagree with the decoder are the two with an open "
        "CRITICAL"
    )


# --------------------------------------------------------------------------- #
# 5. Green today — the rows a wrong-layer or strip-shaped fix reddens
# --------------------------------------------------------------------------- #


def test_a_name_that_merely_looks_quoted_is_not_decoded_twice(
    repo: Path,
) -> None:
    r"""GREEN TODAY. The seal against the fix everyone reaches for first.

    A quote is a legal character in a filename, so a directory really can be
    called `"tests"` — quotes included. Git renders that as
    `"\"tests\"/x.py"`: the OUTER quotes are the rendering and the inner
    escaped ones are the name. A fix that strips or `.strip('"')`s instead of
    reversing `quote_c_style` turns it into `tests/x.py` and starts calling
    an ordinary source file one of the repo's seals — the same over-block as
    the anchor row, arrived at from the other side.

    Both halves are asserted: `changed_paths_between`, which decodes
    correctly today, must keep returning the name WITH its quotes; and
    `is_test_path` must keep answering False for it, because the directory is
    not `tests`.

    Producible because: the directory and file are created and committed
    here, and the decoded name is read off the collector.

    Green now. Green when: still green.
    Falsify (this is the mutation that reddens it): replace the decode with
    `line.strip('"')` — or add one to `risk.collect_diff` /
    `seal_verify.partition_changed` as the "fix" — and the second entry
    becomes True while the first loses its quotes.
    """
    real_name = '"tests"/x.py'
    _commit_files(repo, real_name, "src/ordinary.py")

    decoded = sorted(changed_paths_between(repo, "main", "feat/x"))

    assert [decoded, seal_verify.is_test_path(real_name)] == [
        sorted([real_name, "src/ordinary.py"]),
        False,
    ], (
        "a directory literally named `\"tests\"` is not the directory "
        "`tests`; the quotes are part of the name, not git's rendering"
    )


def test_an_ordinary_fix_branch_is_still_judged_by_the_seal_gate(
    repo: Path,
) -> None:
    """GREEN TODAY. The refusal control for the whole `seal_verify` section.

    Green now. Green when: still green.
    Falsify: it is the row that a partition which called everything a test
    (making `non_tests` empty, so the gate skips as "test-only") reddens.
    """
    _commit_files(repo, "src/prod.py", "tests/test_thing.py")
    result = seal_verify.run_seal_inversion(
        worktree=repo, base="main", test_command="true", timeout_seconds=30,
    )
    assert result.outcome != "skipped", result.detail
