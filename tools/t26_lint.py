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
The claude-workflow checkout is found via $CLAUDE_WORKFLOW_REPO, then
../claude-workflow, then /home/andrew/Project/claude-workflow — absence is
a FAILURE, not a skip: an unverifiable citation is a stale citation.
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

# A line is an annotation when it carries one of these (task-fixed
# heuristic: the sentence that retires a name necessarily names it).
ANNOTATION_RE = re.compile(r"retired|SUPERSEDED|deleted|disposition|prior versions",
                           re.IGNORECASE)
# Statement-of-absence exemption: "no `request_id`" (§3.3) names the
# identifier precisely to say the wire does not carry it — an annotation of
# absence, not a live mechanism. Only a directly negated mention qualifies.
NEGATED_RE = r"(?:no|never a|without)\s+`?%s`?"

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


def check_retired(doc: Doc, errors: list[str]) -> None:
    """(3) retired identifiers only in §11/header/annotation lines."""
    for i, sec, line in doc.normative():
        for name in RETIRED:
            if not re.search(r"\b" + name + r"\b", line):
                continue
            if ANNOTATION_RE.search(line):
                continue
            if re.search(NEGATED_RE % re.escape(name), line):
                continue  # statement of absence — not a live mechanism
            errors.append(f"retired-name: line {i} (§{sec}): `{name}` outside "
                          f"§11/version-history/annotation")


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

def find_workflow_repo() -> Path | None:
    for cand in (os.environ.get("CLAUDE_WORKFLOW_REPO"),
                 str(REPO_ROOT.parent / "claude-workflow"),
                 "/home/andrew/Project/claude-workflow"):
        if cand and (Path(cand) / ".git").exists():
            return Path(cand)
    return None


def git_show(repo: Path, sha: str, path: str) -> str | None:
    proc = subprocess.run(["git", "-C", str(repo), "show", f"{sha}:{path}"],
                          capture_output=True, text=True)
    return proc.stdout if proc.returncode == 0 else None


def parse_pins(doc: Doc, errors: list[str]) -> tuple[str, str] | None:
    m = re.search(r"\*\*Review baseline for citations:\*\* "
                  r"`claude-dispatcher@([0-9a-f]+)`, `claude-workflow@([0-9a-f]+)`",
                  doc.text)
    if not m:
        errors.append("citations: no 'Review baseline for citations' header line")
        return None
    return m.group(1), m.group(2)


def resolve_py(repo: Path, sha: str, path: str) -> tuple[str, str] | None:
    for cand in (path, f"src/claude_dispatcher/{path}", f"tests/fixtures/{path}"):
        content = git_show(repo, sha, cand)
        if content is not None:
            return cand, content
    return None


def check_citations(doc: Doc, errors: list[str]) -> None:
    """(6) file:line citations resolve at the pinned baselines; symbol
    checks where the doc cites symbols. Historical sections (§11, the
    version-history header) cite lines against OLD baselines by definition
    and are exempt — the same scoping §12 gives the retired-name rule."""
    pins = parse_pins(doc, errors)
    if pins is None:
        return
    disp_sha, wf_sha = pins
    wf_repo = find_workflow_repo()
    if wf_repo is None:
        errors.append("citations: claude-workflow checkout not found "
                      "(set CLAUDE_WORKFLOW_REPO); citations unverifiable = stale")
        return
    cache: dict[tuple[str, str], str | None] = {}

    def content_for(path: str) -> tuple[str, str] | None:
        if path.endswith(".go"):
            real = GO_PATH_MAP.get(path, path)
            key = ("workflow", real)
            if key not in cache:
                cache[key] = git_show(wf_repo, wf_sha, real)
            return (real, cache[key]) if cache[key] is not None else None
        key = ("dispatcher", path)
        if key not in cache:
            hit = resolve_py(REPO_ROOT, disp_sha, path)
            cache[key] = hit[1] if hit else None
            if hit:
                cache[("dispatcher-name", path)] = hit[0]
        if cache[key] is None:
            return None
        return (str(cache.get(("dispatcher-name", path), path)), str(cache[key]))

    for i, sec, line in doc.normative():
        for m in CITATION_RE.finditer(line):
            path, linespec = m.group("path"), m.group("lines")
            hit = content_for(path)
            if hit is None:
                errors.append(f"citations: line {i} (§{sec}): {path} not found "
                              f"at pinned baseline")
                continue
            real, content = hit
            nlines = content.count("\n") + 1
            maxline = max(int(x) for x in re.findall(r"\d+", linespec))
            if maxline > nlines:
                errors.append(f"citations: line {i} (§{sec}): {real}:{maxline} "
                              f"beyond EOF ({nlines} lines at pin)")
    # symbol-level checks
    for repo_name, path, symbols in SYMBOL_CHECKS:
        if repo_name == "workflow":
            content = git_show(wf_repo, wf_sha, path)
        else:
            content = git_show(REPO_ROOT, disp_sha, path)
        if content is None:
            errors.append(f"citations: symbol file {path} missing at pin")
            continue
        for sym in symbols:
            if sym not in content:
                errors.append(f"citations: symbol `{sym}` not found in {path} at pin")


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
        if "retired" in cells[1].lower():
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


def main() -> int:
    doc = Doc(DESIGN)
    errors: list[str] = []
    check_t_index(doc, errors)
    check_section_refs(doc, errors)
    check_retired(doc, errors)
    check_mutations(doc, errors)
    check_supersession(doc, errors)
    check_field_lists(doc, errors)
    check_citations(doc, errors)
    check_plan_tmap(doc, errors)
    if errors:
        for e in errors:
            print(f"t26_lint: FAIL: {e}", file=sys.stderr)
        print(f"t26_lint: {len(errors)} violation(s)", file=sys.stderr)
        return 1
    print("t26_lint: all checks green (T-index, §-refs, retired names, "
          "mutation-once, supersession, field-list-once, citations @ pins, "
          "plan §3 T-map)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
