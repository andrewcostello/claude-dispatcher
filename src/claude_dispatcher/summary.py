"""Parser for the Tasker's per-task summary file.

The Tasker writes one Markdown file per session at $SUMMARY_PATH. This module
parses it into a structured object the dispatcher can write back to the YAML.

The parser is intentionally lenient: if a section is missing or malformed,
the parser returns what it could extract and marks the result `malformed=True`.
The dispatcher then marks the task Blocked with reason "summary file malformed"
rather than crashing the whole run.

The Tasker's summary format is documented at the bottom of
.claude/workflow/roles/tasker.md ("Phase 5: Write Summary File").
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


# Status values the Tasker can emit.
STATUS_DONE = "Done"
STATUS_BLOCKED = "Blocked"
STATUS_ESCALATED = "Escalated"
VALID_STATUSES = {STATUS_DONE, STATUS_BLOCKED, STATUS_ESCALATED}


@dataclass
class Summary:
    task_key: str | None = None
    status: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    iterations: int = 0
    linter_cycles: int = 0
    human_gate_fired: bool = False
    final_quality_score: int | None = None  # 0-25, or None if not reviewed
    what_landed: str = ""
    key_decisions: str = ""
    deferred_findings: list[str] = field(default_factory=list)
    review_consensus: list[dict[str, str]] = field(default_factory=list)
    files_changed: list[str] = field(default_factory=list)
    pr_url: str | None = None
    pr_not_raised_reason: str | None = None
    prepared_pr_title: str | None = None
    prepared_pr_branch: str | None = None
    prepared_pr_body: str | None = None
    escalation_reason: str = ""
    malformed: bool = False
    # Every reason the parser flagged this summary as malformed, in the order
    # they were discovered. Empty iff malformed is False. `malformed_reason`
    # is kept as the "; "-joined view for back-compat with callers that want a
    # single string.
    problems: list[str] = field(default_factory=list)
    malformed_reason: str = ""

    def add_problem(self, reason: str) -> None:
        """Record a parse problem: append it, flag malformed, refresh the joined reason."""
        self.problems.append(reason)
        self.malformed = True
        self.malformed_reason = "; ".join(self.problems)

    @property
    def awaiting_human_approval(self) -> bool:
        """True iff the Tasker stopped at the Critical/High PR gate."""
        return (
            self.status == STATUS_BLOCKED
            and self.prepared_pr_title is not None
            and self.prepared_pr_branch is not None
            and self.prepared_pr_body is not None
        )

    @property
    def deferred_findings_count(self) -> int:
        return len(self.deferred_findings)


_INT_RE = re.compile(r"-?\d+")


def _strip_md(value: str) -> str:
    """Strip surrounding `**` markers and whitespace from a metadata value."""
    return value.strip().strip("*").strip()


def _parse_int(raw: str, default: int = 0) -> int:
    match = _INT_RE.search(raw)
    if not match:
        return default
    return int(match.group(0))


def _parse_score(raw: str) -> int | None:
    """Parse '23/25' style scores. Returns the numerator or None."""
    raw = raw.strip()
    if "—" in raw or raw.lower().startswith("not reviewed"):
        return None
    m = re.search(r"(\d+)\s*/\s*\d+", raw)
    if m:
        return int(m.group(1))
    m = re.search(r"\d+", raw)
    return int(m.group(0)) if m else None


def _parse_yes_no(raw: str) -> bool:
    return raw.strip().lower().startswith("y")


def parse(path: str | Path) -> Summary:
    """Read and parse a summary file. Always returns a Summary — never raises."""
    p = Path(path)
    try:
        text = p.read_text(encoding="utf-8")
    except FileNotFoundError:
        s = Summary()
        s.add_problem(f"summary file not found: {p}")
        return s
    return parse_text(text)


def parse_text(text: str) -> Summary:
    """Parse a summary from in-memory text. Used by parse() and by tests."""
    s = Summary()
    # Title line: "# <TASK-KEY>: <one-liner>"
    title = re.search(r"^#\s+(\S+):", text, re.MULTILINE)
    if title:
        s.task_key = title.group(1)

    # Metadata lines: "**Status:** Done", "**Started:** ...", etc.
    for label, attr, conv in [
        ("Status", "status", lambda v: _strip_md(v).strip("`")),
        ("Started", "started_at", lambda v: _strip_md(v) or None),
        ("Completed", "completed_at", lambda v: _strip_md(v) or None),
        ("Iterations", "iterations", _parse_int),
        ("Linter cycles", "linter_cycles", _parse_int),
        ("Human gate fired", "human_gate_fired", _parse_yes_no),
        ("Final quality score", "final_quality_score", _parse_score),
    ]:
        m = re.search(rf"\*\*{re.escape(label)}:\*\*\s*(.+)$", text, re.MULTILINE)
        if m:
            setattr(s, attr, conv(m.group(1)))

    if s.status is None:
        s.add_problem("missing Status line (no `**Status:** <value>` found)")
    elif s.status not in VALID_STATUSES:
        s.add_problem(
            f"invalid status value: Status must be one of "
            f"{sorted(VALID_STATUSES)}; got {s.status!r}"
        )

    # An odd number of code-fence markers means a fence was opened and never
    # closed. That confuses _extract_section (every heading after the dangling
    # fence is swallowed as fence content) and usually signals a truncated
    # file — the Tasker's session was cut off mid-write.
    if len(re.findall(r"^```[\w-]*\s*$", text, re.MULTILINE)) % 2 != 0:
        s.add_problem(
            "unterminated code fence (fence-state confusion; "
            "likely a truncated summary file)"
        )

    s.what_landed = _extract_section(text, "What landed").strip()
    s.key_decisions = _extract_section(text, "Key decisions").strip()
    s.escalation_reason = _extract_section(
        text, "Escalation reason (if Blocked or Escalated)"
    ).strip()
    if not s.escalation_reason:
        s.escalation_reason = _extract_section(text, "Escalation reason").strip()

    s.deferred_findings = _extract_bullets(_extract_section(text, "Deferred findings"))
    s.files_changed = _extract_bullets(_extract_section(text, "Files changed"))
    s.review_consensus = _extract_review_table(_extract_section(text, "Review consensus"))

    _parse_pr_section(s, _extract_section(text, "PR"))
    return s


def _extract_section(text: str, heading: str) -> str:
    """Return the body under '## <heading>' up to the next '## ' heading or EOF.

    Treats fenced code blocks (``` ... ```) as opaque — '##' lines inside a
    fence do not count as new sections. The PR body, for example, holds a
    full PR description with its own `## What` / `## Ticket` headings inside
    a fence; without this guard those would close the PR section prematurely.
    """
    pattern = rf"^##\s+{re.escape(heading)}\s*$"
    lines = text.splitlines()
    out: list[str] = []
    inside = False
    in_fence = False
    for line in lines:
        # Track fence boundaries (a line that is just ``` or ```lang)
        if re.match(r"^```[\w-]*\s*$", line):
            in_fence = not in_fence
            if inside:
                out.append(line)
            continue
        if not in_fence and re.match(pattern, line):
            inside = True
            continue
        if inside and not in_fence and re.match(r"^##\s+\S", line):
            break
        if inside:
            out.append(line)
    return "\n".join(out)


def _extract_bullets(body: str) -> list[str]:
    return [
        line.strip()[2:].strip()
        for line in body.splitlines()
        if line.strip().startswith("- ")
    ]


def _extract_review_table(body: str) -> list[dict[str, str]]:
    """Parse the | Reviewer | Score | Verdict | table.

    Skips header and separator rows. Empty body returns [].
    """
    rows: list[dict[str, str]] = []
    for line in body.splitlines():
        line = line.strip()
        if not line.startswith("|") or line.startswith("|--") or line.startswith("|---"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 3:
            continue
        if cells[0].lower() == "reviewer":
            continue
        rows.append({
            "reviewer": cells[0],
            "score": cells[1],
            "verdict": cells[2] if len(cells) > 2 else "",
        })
    return rows


def _parse_pr_section(s: Summary, body: str) -> None:
    """Extract pr_url, not-raised reason, or prepared PR metadata."""
    body = body.strip()
    if not body:
        return

    # The first non-empty, non-header line is the status: URL | "Not raised: ..." | "Prepared, awaiting human approval"
    head_line = ""
    for line in body.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("###"):
            break
        head_line = line
        break

    if head_line.startswith("http"):
        s.pr_url = head_line.split()[0]
    elif head_line.lower().startswith("not raised"):
        # "Not raised: <reason>" — split on first ":"
        if ":" in head_line:
            s.pr_not_raised_reason = head_line.split(":", 1)[1].strip()
        else:
            s.pr_not_raised_reason = "unspecified"
    elif "awaiting human approval" in head_line.lower():
        # Parse the Prepared PR sub-section
        m = re.search(r"\*\*Title:\*\*\s*(.+)$", body, re.MULTILINE)
        if m:
            s.prepared_pr_title = m.group(1).strip()
        m = re.search(r"\*\*Branch:\*\*\s*(.+)$", body, re.MULTILINE)
        if m:
            s.prepared_pr_branch = m.group(1).strip()
        m = re.search(r"\*\*Body:\*\*\s*\n```(?:markdown)?\s*\n(.*?)\n```", body, re.DOTALL)
        if m:
            s.prepared_pr_body = m.group(1).strip()
        # An "awaiting approval" PR section must carry the prepared-PR metadata
        # so the dispatcher/human can actually raise it. Missing fields mean
        # the regexes failed to match the expected layout.
        missing = [
            name
            for name, val in (
                ("Title", s.prepared_pr_title),
                ("Branch", s.prepared_pr_branch),
                ("Body", s.prepared_pr_body),
            )
            if val is None
        ]
        if missing:
            s.add_problem(
                "PR section claims 'awaiting human approval' but the prepared-PR "
                f"{', '.join(missing)} field(s) could not be parsed"
            )
    else:
        # The PR section has content but its first line is none of the three
        # recognised forms (URL / "Not raised: ..." / "Prepared, awaiting
        # human approval"), so the PR-section regexes have nothing to bind to.
        s.add_problem(
            "unparseable PR section: first line "
            f"{head_line!r} is not a URL, 'Not raised: <reason>', or "
            "'Prepared, awaiting human approval'"
        )
