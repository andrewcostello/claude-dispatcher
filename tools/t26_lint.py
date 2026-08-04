#!/usr/bin/env python3
"""T26 — the mechanical doc lint for the classification→gating design.

Design v20 §12 makes this document carry its own lint: six consecutive
review rounds were burned on drift THIS tool now catches mechanically —
stale §10 restatements (root cause B applied to the doc itself), retired
names surviving their own replacement (eleven occurrences of the
dual-definition class), and file:line citations rotting under a moving
baseline.

Checks (exit nonzero on any violation):
  1. every T<n> cited in §§0–9/§12 has exactly one §10 index row
  2. every §-reference resolves to a real heading
  3. retired identifiers appear only in §11 tables, the version-history
     header, or retirement/supersession annotation lines
  4. createCommitOnBranch / updateRefs / createRef each bound normatively
     exactly once (mutation-name-once — §10's T26 anchor)
  5. supersession markers are intact ([SUPERSEDED rN ...] form)
  6. file:line citations resolve at the header's pinned baselines
     (git show at the pinned SHA), with symbol-level checks where the doc
     cites symbols
  7. the implementation plan's §3 T-map covers every non-retired T
  8. each §9 event field list appears normatively once (field-list-once)

Baselines come from the doc header's "Review baseline for citations" line.
The claude-workflow peer checkout is resolved by ONE predicate —
peer_available(), $CLAUDE_WORKFLOW_REPO then <repo>/../claude-workflow —
which scripts/test.sh consumes via `--probe-peer` and the pytest seal
imports directly, so the three callers cannot disagree about the
environment. With the peer present, check 6 runs and an unverifiable
citation is a failure. Without it, `--no-citations` runs checks 1–5/7–8
and says so loudly on stderr; that degraded mode is for dispatched-task
worktrees only — `make verify-t26` and CI always require the peer.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DESIGN = REPO_ROOT / "docs/plans/2026-08-02-classification-gating-design.md"
PLAN = REPO_ROOT / "docs/plans/2026-08-03-classification-gating-implementation-plan.md"

# §12's retired-identifier list. `integrity_hold` is retired AS AN EVENT
# NAME; the hold branch `refs/heads/dispatcher/integrity-hold` (hyphenated)
# is live and never matches the underscore token.
RETIRED = ["AuthoritySnapshot", "LegacyNoConfig", "MOVED_TO_HOLD",
           "integrity_hold", "FOREIGN_OBSERVED", "AuthorizedBaseTransition",
           "request_id"]

# Exemptions are OCCURRENCE-level and anchored to specific retirement
# patterns — never to domain vocabulary. "disposition" and "deleted" are
# ordinary §6.0/§9 words, so their presence on a line proves nothing (panel
# finding: a retired name returning to a live-mechanism line was silently
# exempt whenever the line also used a domain word). An occurrence is an
# annotation when it is:
#   (a) inside a review-round parenthetical "(round N, seat: …)" — a quote
#       of what an OLD version said;
#   (b) within a short window of the words "retired"/"retires" or a
#       "[SUPERSEDED …]" marker on the same line — the sentence that retires
#       a name necessarily names it;
#   (c) a directly negated mention ("no `request_id`") — a statement of
#       absence, not a live mechanism.
ANNOTATION_WINDOW = 160
ANNOTATION_NEAR_RE = re.compile(r"retire[sd]?|\[SUPERSEDED", re.IGNORECASE)
NEGATED_RE = r"(?:no|never a?|without)\s+`?%s`?"

MUTATIONS = ["createCommitOnBranch", "updateRefs", "createRef"]

# Parentheticals citing review rounds are historical annotations, not
# normative bindings (they quote what an OLD version said).
ROUND_PAREN = re.compile(r"\((?:round|Round)[^()]*(?:\([^()]*\)[^()]*)*\)")

# §9 event names whose `name{...}` field list must be bound exactly once.
EVENT_NAMES = ["effect_lifecycle", "hold_lifecycle", "panel_decided",
               "merge_planned", "approval_evaluated", "authorization_granted",
               "consent", "protocol_genesis", "merge_unit_declared",
               "merge_unit_member_added", "protocol_epoch_advanced",
               "panel_roster_declared", "panel_roster_augmented", "seat_result"]

# Symbol-level checks: (repo, path, symbols) — where the doc cites symbols
# alongside a file (design §3.2 classify()/decidePanel(); §5.1
# _resolved_quality/cross_family_panel; §0.2 _has_commits_on_branch via
# orchestrator.py:3231's direct-to-base branch; §7 merge_prs --force;
# §6.0 merge-commit via `gh pr merge --merge`; §4.4 -reviewers flag).
SYMBOL_CHECKS = [
    ("workflow", "cmd/classify/main.go",
     ["func classify(", "func decidePanel(", "config_scaffold,omitempty"]),
    ("dispatcher", "src/claude_dispatcher/orchestrator.py",
     ["_resolved_quality", "cross_family_panel", "_has_commits_on_branch"]),
    ("dispatcher", "src/claude_dispatcher/merge_prs.py", ["--force"]),
    ("dispatcher", "src/claude_dispatcher/merge_engine.py", ["--merge"]),
    ("workflow", "cmd/reviewer/main.go", ["reviewers"]),
]

CITATION_RE = re.compile(
    r"(?P<path>[A-Za-z0-9_./-]*[A-Za-z0-9_-]\.(?:go|py)):(?P<lines>\d+(?:[–\-]\d+)?(?:,\d+(?:[–\-]\d+)?)*)")

# Bare Go filenames the doc uses in context (workflow repo).
GO_PATH_MAP = {
    "main.go": "cmd/classify/main.go",
    "gates/main.go": "cmd/gates/main.go",
    "iterate/main.go": "cmd/iterate/main.go",
}


class Doc:
    """The design doc, split into lines tagged with their section."""

    def __init__(self, path: Path):
        self.text = path.read_text(encoding="utf-8")
        self.lines: list[tuple[int, str, str]] = []  # (lineno, section, text)
        cur = "header"
        for i, line in enumerate(self.text.splitlines(), 1):
            m = re.match(r"^#{2,3} (\d+(?:\.\d+)?)[. ]", line)
            if m:
                cur = m.group(1)
            self.lines.append((i, cur, line))
        self.headings = {s for _, s, _ in self.lines if s != "header"}

    def normative(self):
        """Lines outside the version-history header and §11's tables."""
        for i, sec, line in self.lines:
            if sec == "header" or sec.split(".")[0] == "11":
                continue
            yield i, sec, line

    def section(self, name: str) -> str:
        return "\n".join(l for _, s, l in self.lines if s == name)


def check_t_index(doc: Doc, errors: list[str]) -> None:
    """(1) every T<n> cited in §§0–9/§12 has exactly one §10 row."""
    rows: dict[int, int] = {}
    for _, sec, line in doc.lines:
        if sec != "10" or not line.strip().startswith("|"):
            continue
        first = line.strip().strip("|").split("|")[0]
        for n in re.findall(r"\bT(\d+)\b", first):
            rows[int(n)] = rows.get(int(n), 0) + 1
    cited: dict[int, int] = {}
    for i, sec, line in doc.lines:
        top = sec.split(".")[0]
        if sec == "header" or top not in {"0", "1", "2", "3", "4", "5", "6",
                                          "7", "8", "9", "12"}:
            continue
        for n in re.findall(r"\bT(\d+)\b", line):
            cited.setdefault(int(n), i)
    for n, lineno in sorted(cited.items()):
        if rows.get(n, 0) != 1:
            errors.append(f"T-index: T{n} (cited at line {lineno}) has "
                          f"{rows.get(n, 0)} §10 rows, want exactly 1")


def check_section_refs(doc: Doc, errors: list[str]) -> None:
    """(2) §-references resolve (single refs and §§a–b ranges)."""
    for i, _, line in doc.lines:
        for a, b in re.findall(r"§§(\d+)[–\-—](\d+)", line):
            for end in (a, b):
                if end not in doc.headings:
                    errors.append(f"§-ref: line {i}: range endpoint §{end} unresolved")
        for ref in re.findall(r"§(\d+(?:\.\d+)?)", line):
            if ref not in doc.headings:
                errors.append(f"§-ref: line {i}: §{ref} unresolved")


def _round_paren_spans(line: str) -> list[tuple[int, int]]:
    """Spans of "(round N, …)" / "(Round N, …)" parentheticals, one level of
    nesting allowed — historical quotes of prior versions."""
    return [m.span() for m in ROUND_PAREN.finditer(line)]


def _occurrence_exempt(line: str, name: str, start: int, end: int) -> bool:
    for a, b in _round_paren_spans(line):
        if a <= start and end <= b:
            return True
    lo, hi = max(0, start - ANNOTATION_WINDOW), min(len(line), end + ANNOTATION_WINDOW)
    if ANNOTATION_NEAR_RE.search(line[lo:hi]):
        return True
    prefix = line[max(0, start - 24):start]
    return bool(re.search(NEGATED_RE % re.escape(name) + r"$",
                          prefix + line[start:end]))


def check_retired(doc: Doc, errors: list[str]) -> None:
    """(3) retired identifiers only in §11/header or inside a retirement
    annotation — occurrence-level, anchored to retirement patterns, immune
    to domain words like 'disposition'/'deleted' on the same line."""
    for i, sec, line in doc.normative():
        for name in RETIRED:
            for m in re.finditer(r"\b" + name + r"\b", line):
                if _occurrence_exempt(line, name, m.start(), m.end()):
                    continue
                errors.append(f"retired-name: line {i} (§{sec}): `{name}` "
                              f"outside §11/version-history/annotation")


def check_mutations(doc: Doc, errors: list[str]) -> None:
    """(4) each GraphQL mutation name bound normatively exactly once."""
    for name in MUTATIONS:
        hits = []
        for i, sec, line in doc.normative():
            clean = ROUND_PAREN.sub("(HIST)", line)
            hits += [i] * len(re.findall(r"\b" + name + r"\b", clean))
        if len(hits) != 1:
            errors.append(f"mutation-once: `{name}` bound {len(hits)} times "
                          f"(lines {hits}), want exactly 1")


def check_supersession(doc: Doc, errors: list[str]) -> None:
    """(5) supersession markers intact."""
    tagged = len(re.findall(r"\[SUPERSEDED r\d+[^\]]*\]", doc.text))
    bracketed = len(re.findall(r"\[SUPERSEDED[^\]]*\]", doc.text))
    bare = len(re.findall(r"SUPERSEDED", doc.text))
    if tagged == 0:
        errors.append("supersession: no [SUPERSEDED rN ...] markers found")
    if bare != bracketed:
        # every mention must be in bracket form — either a live rN-tagged
        # marker or the doc's own references to the marker convention.
        errors.append(f"supersession: {bare - bracketed} SUPERSEDED mention(s) "
                      f"outside the [SUPERSEDED ...] bracket form")


def check_field_lists(doc: Doc, errors: list[str]) -> None:
    """(8) each §9 event field list appears normatively once."""
    for name in EVENT_NAMES:
        hits = [i for i, _, line in doc.normative()
                if re.search(r"`" + name + r"\{", line)]
        if len(hits) != 1:
            errors.append(f"field-list-once: `{name}{{...}}` appears "
                          f"{len(hits)} times (lines {hits}), want exactly 1")


# ─── citations at the pinned baselines ───────────────────────────────────────

# ─── the ONE peer-checkout predicate ────────────────────────────────────────
# Defined here, consumed by scripts/test.sh (via --probe-peer), by this
# module's citation check, and by the pytest seal — so the three cannot
# disagree about which environment they are in. `.git` is tested with
# exists() because a linked git WORKTREE carries `.git` as a FILE, which is
# exactly the layout this dispatcher creates for tasks (panel round 2: a
# `-d` test disagreed with this one in both directions).
_WORKFLOW_CANDIDATES = ["$CLAUDE_WORKFLOW_REPO", "<repo>/../claude-workflow"]


def find_workflow_repo() -> Path | None:
    for cand in (os.environ.get("CLAUDE_WORKFLOW_REPO"),
                 str(REPO_ROOT.parent / "claude-workflow")):
        if cand and (Path(cand) / ".git").exists():
            return Path(cand)
    return None


def peer_available() -> bool:
    """The single environment predicate: True on a dev machine with the
    claude-workflow peer checkout, False in a dispatched worktree without
    one (degraded mode — every doc-local check still runs)."""
    return find_workflow_repo() is not None


GIT_TIMEOUT_SECONDS = 30  # repo convention: every git subprocess is bounded


class GitResult:
    """git output plus WHY it is missing — a timeout, a bad pin and a real
    absence must not all read as 'stale citation' (panel round 2)."""

    __slots__ = ("text", "error")

    def __init__(self, text: str | None, error: str | None = None):
        self.text = text
        self.error = error

    @property
    def ok(self) -> bool:
        return self.text is not None


def git_show(repo: Path, sha: str, path: str) -> GitResult:
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo), "show", f"{sha}:{path}"],
            capture_output=True, text=True, timeout=GIT_TIMEOUT_SECONDS,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})
    except subprocess.TimeoutExpired:
        return GitResult(None, f"timeout after {GIT_TIMEOUT_SECONDS}s")
    except OSError as exc:                                  # git missing, etc.
        return GitResult(None, f"git could not run: {exc}")
    if proc.returncode != 0:
        lines = (proc.stderr or "").strip().splitlines()
        return GitResult(None, lines[-1] if lines else f"git exit {proc.returncode}")
    return GitResult(proc.stdout)


def pin_resolves(repo: Path, sha: str) -> str | None:
    """Verify the baseline SHA exists in the checkout ONCE up front, so an
    unresolvable pin reports one accurate error naming the SHA and repo
    instead of N 'stale citation' lines."""
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo), "cat-file", "-e", f"{sha}^{{commit}}"],
            capture_output=True, text=True, timeout=GIT_TIMEOUT_SECONDS,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})
    except subprocess.TimeoutExpired:
        return f"timeout resolving pin {sha} in {repo}"
    except OSError as exc:
        return f"git could not run in {repo}: {exc}"
    if proc.returncode != 0:
        return (f"pinned baseline {sha} does not resolve in {repo} "
                f"(fetch it, or re-pin the header)")
    return None


def parse_pins(doc: Doc, errors: list[str]) -> tuple[str, str] | None:
    m = re.search(r"\*\*Review baseline for citations:\*\* "
                  r"`claude-dispatcher@([0-9a-f]+)`, `claude-workflow@([0-9a-f]+)`",
                  doc.text)
    if not m:
        errors.append("citations: no 'Review baseline for citations' header line")
        return None
    return m.group(1), m.group(2)


def resolve_py(repo: Path, sha: str, path: str) -> tuple[str, str] | str:
    """(real_path, text) or an error REASON — a timeout must not be reported
    as a stale citation (panel round 3, finding 48)."""
    reasons = []
    for cand in (path, f"src/claude_dispatcher/{path}", f"tests/fixtures/{path}"):
        res = git_show(repo, sha, cand)
        if res.ok:
            return cand, res.text
        reasons.append(f"{cand}: {res.error}")
        if res.error and "timeout" in res.error:
            return f"{path} unreadable at pin ({res.error})"
    return f"{path} not found at pinned baseline ({'; '.join(reasons)})"


def _citation_context(doc: Doc, errors: list[str]):
    """(dispatcher_sha, workflow_sha, workflow_repo) or None when the check
    cannot run — peer absence and an unresolvable pin are each reported as
    THEMSELVES, once, never as N stale-citation lines."""
    pins = parse_pins(doc, errors)
    if pins is None:
        return None
    disp_sha, wf_sha = pins
    wf_repo = find_workflow_repo()
    if wf_repo is None:
        errors.append(
            "citations: peer checkout ABSENT — claude-workflow citations are "
            f"unverifiable (tried: {', '.join(_WORKFLOW_CANDIDATES)}; set "
            "CLAUDE_WORKFLOW_REPO, or pass --no-citations in environments "
            "without the peer checkout)")
        return None
    pin_problems = [p for p in (pin_resolves(REPO_ROOT, disp_sha),
                                pin_resolves(wf_repo, wf_sha)) if p]
    if pin_problems:
        errors.extend(f"citations: {p}" for p in pin_problems)
        return None
    return disp_sha, wf_sha, wf_repo


def _content_resolver(disp_sha: str, wf_sha: str, wf_repo: Path):
    """path → (real_path, text) on success, or an error REASON string."""
    cache: dict[str, tuple[str, str] | str] = {}

    def content_for(path: str) -> tuple[str, str] | str:
        if path in cache:
            return cache[path]
        if path.endswith(".go"):
            real = GO_PATH_MAP.get(path, path)
            res = git_show(wf_repo, wf_sha, real)
            got: tuple[str, str] | str = (real, res.text) if res.ok else \
                f"{real} unreadable at pin ({res.error})"
        else:
            got = resolve_py(REPO_ROOT, disp_sha, path)
        cache[path] = got
        return got

    return content_for


def _check_line_citations(doc: Doc, content_for, errors: list[str]) -> None:
    for i, sec, line in doc.normative():
        for m in CITATION_RE.finditer(line):
            path, linespec = m.group("path"), m.group("lines")
            hit = content_for(path)
            if isinstance(hit, str):
                errors.append(f"citations: line {i} (§{sec}): {hit}")
                continue
            real, content = hit
            nlines = content.count("\n") + 1
            maxline = max(int(x) for x in re.findall(r"\d+", linespec))
            if maxline > nlines:
                errors.append(f"citations: line {i} (§{sec}): {real}:{maxline} "
                              f"beyond EOF ({nlines} lines at pin)")


def _check_symbol_citations(disp_sha: str, wf_sha: str, wf_repo: Path,
                            errors: list[str]) -> None:
    for repo_name, path, symbols in SYMBOL_CHECKS:
        repo, sha = ((wf_repo, wf_sha) if repo_name == "workflow"
                     else (REPO_ROOT, disp_sha))
        res = git_show(repo, sha, path)
        if not res.ok:
            errors.append(f"citations: symbol file {path} unreadable at pin "
                          f"({res.error})")
            continue
        for sym in symbols:
            if sym not in res.text:
                errors.append(f"citations: symbol `{sym}` not found in {path} at pin")


def check_citations(doc: Doc, errors: list[str]) -> None:
    """(6) file:line citations resolve at the pinned baselines; symbol
    checks where the doc cites symbols. Historical sections (§11, the
    version-history header) cite lines against OLD baselines by definition
    and are exempt — the same scoping §12 gives the retired-name rule."""
    ctx = _citation_context(doc, errors)
    if ctx is None:
        return
    disp_sha, wf_sha, wf_repo = ctx
    _check_line_citations(doc, _content_resolver(disp_sha, wf_sha, wf_repo),
                          errors)
    _check_symbol_citations(disp_sha, wf_sha, wf_repo, errors)


def check_plan_tmap(doc: Doc, errors: list[str]) -> None:
    """(7) the implementation plan's §3 T-map covers every non-retired T."""
    non_retired: set[int] = set()
    for _, sec, line in doc.lines:
        if sec != "10" or not line.strip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 3:
            continue
        nums = [int(n) for n in re.findall(r"\bT(\d+)\b", cells[0])]
        if not nums:
            continue
        # Retired rows carry `—` in the anchor column BY DEFINITION (§10's
        # own rule) — matching on the marker, never on the word "retired"
        # in a Title cell, so a live obligation whose title happens to use
        # the word cannot be silently excluded (panel finding).
        if cells[2] == "—":
            continue
        non_retired.update(nums)
    plan_text = PLAN.read_text(encoding="utf-8")
    m = re.search(r"^## 3\..*?$(.*?)^## 4\.", plan_text, re.M | re.S)
    if not m:
        errors.append("plan T-map: cannot locate plan §3")
        return
    mapped = {int(n) for n in re.findall(r"\bT(\d+)\b", m.group(1))}
    missing = sorted(non_retired - mapped)
    if missing:
        errors.append(f"plan T-map: non-retired obligations missing from plan "
                      f"§3: {['T%d' % n for n in missing]}")


def main(argv: list[str] | None = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--no-citations", action="store_true",
                    help="skip the pinned-baseline citation check (for "
                         "environments without the claude-workflow peer "
                         "checkout, e.g. dispatched-task worktrees; the full "
                         "check runs in `make verify-t26` and CI)")
    ap.add_argument("--probe-peer", action="store_true",
                    help="exit 0 if the claude-workflow peer checkout is "
                         "resolvable, 1 otherwise, printing what was tried; "
                         "this is THE environment predicate scripts/test.sh "
                         "and the pytest seal consume")
    args = ap.parse_args(argv)
    if args.probe_peer:
        repo = find_workflow_repo()
        if repo is None:
            print(f"t26_lint --probe-peer: peer ABSENT (tried: "
                  f"{', '.join(_WORKFLOW_CANDIDATES)})", file=sys.stderr)
            return 1
        print(f"t26_lint --probe-peer: peer at {repo}")
        return 0
    doc = Doc(DESIGN)
    errors: list[str] = []
    check_t_index(doc, errors)
    check_section_refs(doc, errors)
    check_retired(doc, errors)
    check_mutations(doc, errors)
    check_supersession(doc, errors)
    check_field_lists(doc, errors)
    if args.no_citations:
        # stderr + unbuffered: the degraded announcement must survive CI log
        # capture and pytest's stdout capture (panel round 2).
        print("t26_lint: DEGRADED [citations SKIPPED] — no claude-workflow "
              f"peer checkout (tried: {', '.join(_WORKFLOW_CANDIDATES)}); "
              "every doc-local check still enforced. `make verify-t26` and "
              "CI require the peer.", file=sys.stderr, flush=True)
    else:
        check_citations(doc, errors)
    check_plan_tmap(doc, errors)
    if errors:
        for e in errors:
            print(f"t26_lint: FAIL [{e.split(':', 1)[0]}]: {e}", file=sys.stderr)
        print(f"t26_lint: {len(errors)} violation(s)", file=sys.stderr)
        return 1
    checks = ("T-index, §-refs, retired names, mutation-once, supersession, "
              "field-list-once, plan §3 T-map"
              + ("" if args.no_citations else ", citations @ pins"))
    print(f"t26_lint: all checks green ({checks})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
