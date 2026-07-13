"""Blast-radius artifact: the diff's touched symbols and their references
OUTSIDE the diff.

The 2026-07 escape audit found the dominant shipped-escape class (62/171,
36%, incl. two production incidents) was *wrong-scope*: the diff was correct
and the bug lived in a sibling surface — another reader/writer of the same
state that no reviewer opened. Reviewers cannot be relied on to grep; this
module does the mechanical half (enumerate the sibling surfaces) so the
panel only has to do the judgment half (does the change apply there too?).

Pure subprocess logic mirroring ``cross_family_reviewer.collect_diff``: no
journal/YAML access, injectable inputs, bounded output. Failure policy is
FAIL OPEN — an empty artifact never blocks a review; the panel simply runs
without the enrichment (and the artifact says so).
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

# Bounds — the artifact rides inside a reviewer prompt next to a diff that is
# itself capped, so it must stay small and information-dense.
MAX_SYMBOLS = 20
MAX_FILES_PER_SYMBOL = 12
MAX_CHARS = 6000

# Definition patterns per language family. Each captures the defined name in
# group 1 from an added/removed line ("+"/"-" prefix already stripped).
_DEF_PATTERNS = (
    re.compile(r"^func\s+(?:\([^)]*\)\s*)?([A-Za-z_]\w+)\s*\("),        # Go
    re.compile(r"^(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_]\w+)"),  # JS/TS
    re.compile(r"^(?:export\s+)?(?:abstract\s+)?class\s+([A-Za-z_]\w+)"),  # JS/TS/Py
    re.compile(r"^(?:export\s+)?const\s+([A-Za-z_]\w+)\s*=\s*(?:async\s+)?\("),  # arrow fn
    re.compile(r"^def\s+([A-Za-z_]\w+)\s*\("),                          # Python
)

# git embeds the enclosing declaration in hunk headers: `@@ -a,b +c,d @@ <decl>`
_HUNK_DECL = re.compile(
    r"^@@ [^@]+ @@ .*?(?:func\s+(?:\([^)]*\)\s*)?|def\s+|function\s+|class\s+)"
    r"([A-Za-z_]\w+)"
)

# Names too generic to grep usefully — matches would be all noise.
_STOPLIST = frozenset({
    "main", "init", "new", "run", "get", "set", "String", "Error", "Close",
    "test", "setup", "render", "handler", "handle", "index", "update",
})

# A referencing file that matches any of these is not a review-relevant
# sibling surface: tests don't ship, generated code follows its source.
_EXCLUDE_REF = re.compile(
    r"(_test\.|\.test\.|\.spec\.|/tests?/|/__tests__/|/testdata/|/mocks?/"
    r"|/pb/|\.pb\.go|_pb2\.|/sqlc/|\.gen\.|/gen/|/generated/|node_modules/"
    r"|/vendor/|\.lock$|package-lock)"
)


def changed_files(diff: str) -> list[str]:
    """The b-side paths of every file the diff touches, in order."""
    out: list[str] = []
    for m in re.finditer(r"^diff --git a/.+? b/(.+)$", diff, re.MULTILINE):
        if m.group(1) not in out:
            out.append(m.group(1))
    return out


def extract_symbols(diff: str, *, max_symbols: int = MAX_SYMBOLS) -> list[str]:
    """Symbols the diff defines, modifies, or whose bodies it edits.

    Two sources: definition lines that were added/removed, and the enclosing
    declaration git prints in each hunk header (which catches body-only
    edits — the classic sibling-surface case). Ordered by first appearance,
    deduped, stoplisted, bounded.
    """
    seen: list[str] = []

    def _add(name: str) -> None:
        if len(name) < 4 or name.lower() in _STOPLIST or name.startswith("Test"):
            return
        if name not in seen:
            seen.append(name)

    for line in diff.splitlines():
        hm = _HUNK_DECL.match(line)
        if hm:
            _add(hm.group(1))
            continue
        if line[:1] in ("+", "-") and line[:3] not in ("+++", "---"):
            body = line[1:].strip()
            for pat in _DEF_PATTERNS:
                m = pat.match(body)
                if m:
                    _add(m.group(1))
                    break
    return seen[:max_symbols]


def _grep_refs(
    repo_root: Path, ref: str, symbol: str, *, timeout_seconds: int = 30,
) -> list[str]:
    """Paths at ``ref`` that mention ``symbol`` as a whole word (via
    ``git grep -l -w``), or [] on any failure (fail open)."""
    try:
        proc = subprocess.run(
            ["git", "grep", "-l", "-w", "--", symbol, ref],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except (subprocess.TimeoutExpired, OSError):
        return []
    if proc.returncode != 0:  # 1 = no matches; >1 = error. Either way: none.
        return []
    # Output lines are "<ref>:<path>".
    return [ln.split(":", 1)[1] for ln in proc.stdout.splitlines() if ":" in ln]


def build_blast_radius(
    *,
    repo_root: Path,
    branch: str,
    diff: str,
    max_symbols: int = MAX_SYMBOLS,
    max_files_per_symbol: int = MAX_FILES_PER_SYMBOL,
    max_chars: int = MAX_CHARS,
) -> str:
    """Render the blast-radius markdown for a reviewer prompt.

    For each symbol the diff touches: the non-test, non-generated files at
    ``branch`` that reference it and are NOT part of the diff — the sibling
    surfaces the reviewer must adjudicate (change applies there too /
    intentionally doesn't / gap). Returns "" when the diff yields no
    grep-able symbols; returns a short note instead of failing when git is
    unavailable.
    """
    symbols = extract_symbols(diff, max_symbols=max_symbols)
    if not symbols:
        return ""
    in_diff = set(changed_files(diff))

    lines: list[str] = []
    for sym in symbols:
        refs = [
            p for p in _grep_refs(repo_root, branch, sym)
            if p not in in_diff and not _EXCLUDE_REF.search("/" + p)
        ]
        if not refs:
            continue
        shown = refs[:max_files_per_symbol]
        extra = len(refs) - len(shown)
        suffix = f" (+{extra} more)" if extra > 0 else ""
        lines.append(f"- `{sym}` is referenced outside this diff by: "
                     + ", ".join(f"`{p}`" for p in shown) + suffix)

    if not lines:
        return ""

    header = (
        "The following symbols are touched by this diff AND referenced by "
        "files the diff does not change. For each, decide: does the change "
        "apply to that sibling surface too (cite why not needed), or is the "
        "sibling silently diverging (that is a finding — the dominant "
        "shipped-escape class is a correct diff whose twin surface was "
        "never updated)?\n\n"
    )
    body = header + "\n".join(lines)
    if len(body) > max_chars:
        body = body[:max_chars] + "\n... [blast radius truncated]"
    return body
