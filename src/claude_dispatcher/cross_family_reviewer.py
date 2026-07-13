"""Cross-family reviewer panel.

After a Tasker reports Done, the dispatcher can run a panel of three
independent reviewers — one Claude, one Gemini, one Codex — over the
committed diff and the Tasker's summary.md.

Consensus uses a **relaxed corroboration bar** (see `aggregate`):
  * any CRITICAL finding from any valid seat blocks immediately;
  * HIGH findings block only when ≥2 valid families independently raise one;
  * a lone uncorroborated HIGH / CHANGES_REQUESTED is journaled but does not
    block ship;
  * ≥2 valid (parseable) seats are required for "approve"; fewer → "incomplete".

The motivation is that the Tasker's in-cycle review panel is same-family
(also Claude), so it shares its blind spots. Cross-family review surfaces
defects that same-family review misses, without requiring unanimous APPROVE
(which almost never converges across three strict reviewers).

The panel is gated by risk tier (`panel_required`). High-risk tickets
(critical/security/financial/high) run the panel; size XS/S leaves without
risk labels, and docs/test tickets, skip it.

Three layers:
  * `Reviewer` ABC + three subclasses — each owns a CLI invocation.
  * `parse_review_output` — pulls verdict + dimensions + findings out of a
    reviewer's stdout, tolerant of preamble/narrative.
  * `run_panel` — invokes all three in parallel, aggregates verdicts.

The output of one reviewer is a `ReviewerVerdict`. The output of the panel
is a `PanelVerdict` whose `consensus` field is what the orchestrator gates
on.

A probationary ADVISORY tier (first occupant: Grok Build via the `grok`
CLI) can run alongside the authoritative three: advisory reviewers execute
in the same parallel pass but their verdicts/findings attach to
`PanelVerdict.advisory` only — they never affect `consensus`,
`blocking_findings`, or `is_approve`. Repos opt in via `.dispatcher.yaml`
(`panel: {advisory: [grok]}`); promotion to an authoritative seat is a
future explicit human decision based on the journaled scorecard events.
"""

from __future__ import annotations

import os
import re
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable, Iterable

# --- constants --------------------------------------------------------------

# Labels that force the cross-family panel to run. Matched case-insensitively
# against the ticket's labels. We accept the bare token, plus the common
# prefix forms (risk:, tier:, severity:, priority:). This is intentionally
# generous — false-positive panel runs are cheap; false-negative skips
# defeat the safety net entirely.
_PANEL_REQUIRED_BARE = frozenset(
    {"critical", "security", "financial", "high"}
)
_PANEL_REQUIRED_PREFIXES = ("risk:", "tier:", "severity:", "priority:")

# Labels / types that explicitly skip the panel even if a high-risk label
# is also attached. Empty for now — the design says docs and tests skip,
# but those are encoded via the type field, not labels.
_PANEL_SKIP_TYPES = frozenset({"docs", "documentation", "test", "tests"})

# Default per-reviewer wall-clock budget. Each reviewer ingests the entire
# diff + summary; for typical BSA-sized tickets this fits in <2 min, but we
# leave headroom for the 90th percentile. The panel runs reviewers in
# parallel, so the panel wall-clock is bounded by the slowest reviewer.
DEFAULT_REVIEWER_TIMEOUT_SECONDS = 600

# A reviewer's diff context is capped to keep prompts under model context
# limits. Real BSA diffs land at ~300-2000 lines; 8000 lines is the safety
# bound. Above that we truncate with a marker. Tickets larger than this
# should be split anyway.
MAX_DIFF_LINES = 8000


# --- public dataclasses -----------------------------------------------------


class Verdict(str, Enum):
    """One reviewer's overall verdict on the change."""

    APPROVE = "APPROVE"
    CHANGES_REQUESTED = "CHANGES_REQUESTED"
    REJECT = "REJECT"
    # Reviewer ran but its output couldn't be parsed (even after retry).
    PARSE_FAILED = "PARSE_FAILED"
    # CLI not found, network down, timed out — reviewer couldn't run at all.
    UNAVAILABLE = "UNAVAILABLE"


class Severity(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


_BLOCKING_SEVERITIES = frozenset({Severity.CRITICAL, Severity.HIGH})


@dataclass
class Finding:
    severity: Severity
    location: str  # "file:line" or "file:?" — never empty (parser falls back to "unknown:?")
    description: str
    fix: str = ""

    def to_dict(self) -> dict:
        return {
            "severity": self.severity.value,
            "location": self.location,
            "description": self.description,
            "fix": self.fix,
        }


@dataclass
class ReviewerVerdict:
    """One reviewer's parsed output. `family` is "claude"/"gemini"/"codex"."""

    family: str
    verdict: Verdict
    dimensions: dict[str, int] = field(default_factory=dict)
    findings: list[Finding] = field(default_factory=list)
    notes: str = ""
    raw_output: str = ""
    error: str | None = None  # populated when verdict is UNAVAILABLE or PARSE_FAILED
    duration_seconds: float | None = None

    def is_blocker(self) -> bool:
        """True iff this reviewer's verdict alone blocks panel approval.

        UNAVAILABLE does NOT block by itself — panel-level logic decides
        whether a missing reviewer is fatal (see PanelVerdict.consensus).
        """
        if self.verdict in (Verdict.CHANGES_REQUESTED, Verdict.REJECT):
            return True
        if self.verdict == Verdict.PARSE_FAILED:
            return True
        if any(f.severity in _BLOCKING_SEVERITIES for f in self.findings):
            return True
        return False

    def blocking_findings(self) -> list[Finding]:
        return [f for f in self.findings if f.severity in _BLOCKING_SEVERITIES]

    def to_dict(self) -> dict:
        return {
            "family": self.family,
            "verdict": self.verdict.value,
            "dimensions": dict(self.dimensions),
            "findings": [f.to_dict() for f in self.findings],
            "notes": self.notes,
            "error": self.error,
            "duration_seconds": self.duration_seconds,
        }


@dataclass
class PanelVerdict:
    """Aggregate of the three reviewers. `consensus` is the orchestrator gate.

    consensus values (relaxed corroboration bar — see aggregate()):
      - "approve" — ≥2 valid seats reviewed; no CRITICAL; HIGH findings from
                    fewer than 2 families (lone HIGH is logged, not blocking).
      - "block"   — any CRITICAL, or HIGH findings from ≥2 valid families.
      - "incomplete" — fewer than two seats produced a valid (parseable, ran)
                    review — i.e. the panel is mostly/entirely UNAVAILABLE
                    and/or PARSE_FAILED, so it cannot be trusted as a real
                    review. Defaults to "block" semantically; the orchestrator
                    must NOT auto-integrate on "incomplete" either.

    `advisory` carries verdicts from probationary (advisory-tier) reviewers.
    They are journaled and rendered for scorecard comparison but have ZERO
    effect on `consensus`, `blocking_findings`, or `is_approve` — only the
    authoritative `reviewers` list feeds the consensus math.
    """

    consensus: str  # "approve" | "block" | "incomplete"
    reviewers: list[ReviewerVerdict]
    summary: str
    # All CRITICAL/HIGH findings across all AUTHORITATIVE reviewers, in
    # input order. Advisory findings never appear here.
    blocking_findings: list[Finding] = field(default_factory=list)
    # Advisory (probationary, non-blocking) reviewer verdicts.
    advisory: list[ReviewerVerdict] = field(default_factory=list)

    @property
    def is_approve(self) -> bool:
        return self.consensus == "approve"

    def to_dict(self) -> dict:
        return {
            "consensus": self.consensus,
            "summary": self.summary,
            "reviewers": [r.to_dict() for r in self.reviewers],
            "blocking_findings": [f.to_dict() for f in self.blocking_findings],
            "advisory": [r.to_dict() for r in self.advisory],
        }


# --- risk-tier gating -------------------------------------------------------


def has_risk_label(labels: Iterable[str] | None) -> bool:
    """True if any label is a panel-forcing risk tier (critical/security/…)."""
    if not labels:
        return False
    for raw in labels:
        if not raw:
            continue
        lab = str(raw).strip().lower()
        if lab in _PANEL_REQUIRED_BARE:
            return True
        for prefix in _PANEL_REQUIRED_PREFIXES:
            if lab.startswith(prefix):
                bare = lab.split(":", 1)[1].strip()
                if bare in _PANEL_REQUIRED_BARE:
                    return True
                break
    return False


def is_small_leaf(labels: Iterable[str] | None) -> bool:
    """True when the task is size XS or S (cheap leaf work).

    Used to skip the cross-family panel under both auto and always modes when
    no risk label is present — three reviewers on a leaf is poor cost/speed.
    """
    if not labels:
        return False
    for raw in labels:
        lab = str(raw).strip().lower()
        if lab in ("size:xs", "size:s"):
            return True
    return False


def panel_required(
    labels: Iterable[str] | None,
    *,
    task_type: str | None = None,
) -> bool:
    """Return True if this ticket's risk tier requires the cross-family panel.

    The required tiers are: critical, security, financial, high. Matches
    case-insensitively against either the bare token (`critical`) or any of
    the common prefix forms (`risk:critical`, `tier:critical`, etc.).

    Docs / test tickets skip the panel even if labelled high-risk — they
    don't ship code paths that need this safety net.
    """
    if task_type and task_type.lower() in _PANEL_SKIP_TYPES:
        return False

    return has_risk_label(labels)


# --- output parser ----------------------------------------------------------


_VERDICT_TOKENS = {
    "APPROVE": Verdict.APPROVE,
    "CHANGES_REQUESTED": Verdict.CHANGES_REQUESTED,
    "CHANGES REQUESTED": Verdict.CHANGES_REQUESTED,
    "REQUEST_CHANGES": Verdict.CHANGES_REQUESTED,
    "REQUEST CHANGES": Verdict.CHANGES_REQUESTED,
    "REJECT": Verdict.REJECT,
    "UNAVAILABLE": Verdict.UNAVAILABLE,
}

# Canonical dimension names the parser looks for, in display order. The
# parser is tolerant — it accepts "- Correctness: 4", "* Correctness: 4",
# "Correctness: 4/5", "**Correctness:** 4", and similar.
DIMENSION_NAMES = (
    "Correctness",
    "Security",
    "Compliance",
    "Resilience",
    "Idempotency",
    "Observability",
    "Performance",
    "Maintainability",
)


def parse_review_output(family: str, raw: str) -> ReviewerVerdict:
    """Pull a structured verdict out of a reviewer's stdout.

    Tolerant of preamble, narrative, and ANSI escapes. The parser locates the
    `## Verdict` and `## Dimension scores` sections and reads from there. If
    a structured verdict can't be found, returns a ReviewerVerdict with
    verdict=PARSE_FAILED so the panel can decide whether to retry.
    """
    rv = ReviewerVerdict(family=family, verdict=Verdict.PARSE_FAILED, raw_output=raw)
    if not raw or not raw.strip():
        rv.error = "empty output"
        return rv

    cleaned = _strip_ansi(raw)

    # 1. Verdict line — find "## Verdict" then take the first non-empty
    #    non-comment line below, normalize.
    verdict = _extract_verdict(cleaned)
    if verdict is None:
        rv.error = "no parseable Verdict section"
        return rv
    rv.verdict = verdict

    # 2. Dimension scores. Missing scores are silently 0 — the panel can
    #    still evaluate findings.
    rv.dimensions = _extract_dimensions(cleaned)

    # 3. Findings — anchored at "## Findings" through end-of-text or next
    #    "## " heading that isn't a finding subsection.
    rv.findings = _extract_findings(cleaned)

    # 4. Notes (optional narrative). Trim aggressively.
    rv.notes = _extract_section(cleaned, "Notes").strip()[:2000]

    # An UNAVAILABLE reviewer with zero findings and all-zero dimensions is
    # a self-reported unavailability — surface it as such.
    if rv.verdict == Verdict.UNAVAILABLE and not rv.error:
        rv.error = "reviewer self-reported UNAVAILABLE"

    return rv


_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")


def _strip_ansi(text: str) -> str:
    """Strip ANSI escape sequences that some CLIs emit even with TTY off."""
    return _ANSI_RE.sub("", text)


def _extract_section(text: str, heading: str) -> str:
    """Return the body under '## <heading>' up to the next '## ' or EOF.

    Treats '### ' as a sub-heading (still inside the parent section). The
    Findings section uses '### CRITICAL: ...' so we can't terminate on '###'.
    """
    pattern = re.compile(
        rf"^##\s+{re.escape(heading)}\s*$", re.MULTILINE | re.IGNORECASE
    )
    m = pattern.search(text)
    if not m:
        return ""
    start = m.end()
    # Find the next top-level "## " heading (NOT "### ")
    next_top = re.search(r"^##\s+(?!#)", text[start:], re.MULTILINE)
    end = start + next_top.start() if next_top else len(text)
    return text[start:end]


def _extract_verdict(text: str) -> Verdict | None:
    body = _extract_section(text, "Verdict")
    if not body.strip():
        # Fallback: scan for a bare verdict token anywhere in the first
        # 4KB of output. Some reviewers ignore the template and write the
        # verdict as their last line.
        scan = text[:4096].upper()
        for token, verdict in _VERDICT_TOKENS.items():
            if re.search(rf"\b{re.escape(token)}\b", scan):
                return verdict
        return None
    upper = body.upper()
    for token, verdict in _VERDICT_TOKENS.items():
        if re.search(rf"\b{re.escape(token)}\b", upper):
            return verdict
    return None


_SCORE_RE = re.compile(r"(-?\d+)")


def _extract_dimensions(text: str) -> dict[str, int]:
    body = _extract_section(text, "Dimension scores")
    if not body.strip():
        # Try the long form too — "Dimension scores (1-5 each)"
        body = _extract_section(text, "Dimension scores (1-5 each)")
    out: dict[str, int] = {}
    if not body.strip():
        return out
    for dim in DIMENSION_NAMES:
        # Match: optional bullet/asterisk/dash, optional ** bold, dim name, colon,
        # rest-of-line. We don't constrain the value here — `_SCORE_RE` picks the
        # first signed integer out of whatever followed (handles "4", "4/5",
        # "**4**", "-2", " 3 (with note)", etc.).
        pat = re.compile(
            rf"^[\s\-\*]*\**\s*{re.escape(dim)}\**\s*:\s*(.+)$",
            re.MULTILINE | re.IGNORECASE,
        )
        m = pat.search(body)
        if not m:
            continue
        sm = _SCORE_RE.search(m.group(1))
        if not sm:
            continue
        try:
            score = int(sm.group(1))
        except ValueError:
            continue
        # Clamp to [0, 5] — anything outside is a parser/reviewer error.
        out[dim] = max(0, min(score, 5))
    return out


_FINDING_HEAD_RE = re.compile(
    r"^###\s+(CRITICAL|HIGH|MEDIUM|LOW)\s*:?\s*(.*?)\s*$",
    re.MULTILINE | re.IGNORECASE,
)


def _extract_findings(text: str) -> list[Finding]:
    body = _extract_section(text, "Findings")
    if not body.strip():
        return []
    # Locate each finding head (### SEVERITY: location) and split.
    heads = list(_FINDING_HEAD_RE.finditer(body))
    out: list[Finding] = []
    for i, h in enumerate(heads):
        sev_token = h.group(1).upper()
        location_raw = h.group(2).strip() or "unknown:?"
        try:
            sev = Severity(sev_token)
        except ValueError:
            continue
        body_start = h.end()
        body_end = heads[i + 1].start() if i + 1 < len(heads) else len(body)
        chunk = body[body_start:body_end].strip()
        desc, fix = _split_description_fix(chunk)
        out.append(
            Finding(
                severity=sev,
                location=location_raw or "unknown:?",
                description=desc,
                fix=fix,
            )
        )
    return out


_DESC_LABEL_RE = re.compile(r"^\s*\**\s*description\s*:?\s*\**\s*", re.IGNORECASE)
_FIX_LABEL_RE = re.compile(r"^\s*\**\s*fix\s*:?\s*\**\s*", re.IGNORECASE)


def _split_description_fix(chunk: str) -> tuple[str, str]:
    """Split a finding body into (description, fix).

    Tolerates "Description: ..." / "Fix: ..." labels OR a "Problem:" /
    "Fix:" pair OR a single blob (taken as description, fix empty).
    """
    if not chunk:
        return "", ""
    # Find the start of a "Fix:" line.
    lines = chunk.splitlines()
    fix_idx = None
    for i, ln in enumerate(lines):
        if _FIX_LABEL_RE.match(ln):
            fix_idx = i
            break
    if fix_idx is None:
        # No explicit Fix — take everything as description.
        desc = _strip_label(chunk, ("description", "problem")).strip()
        return desc, ""
    desc_lines = lines[:fix_idx]
    fix_lines = lines[fix_idx:]
    desc = _strip_label("\n".join(desc_lines), ("description", "problem")).strip()
    # The Fix block: strip the "Fix:" label off the first line.
    first = _FIX_LABEL_RE.sub("", fix_lines[0]).strip()
    fix = "\n".join([first, *fix_lines[1:]]).strip()
    return desc, fix


def _strip_label(text: str, labels: tuple[str, ...]) -> str:
    """If the first non-empty line is `Label:`, strip it."""
    lines = text.splitlines()
    out = []
    stripped_one = False
    for ln in lines:
        if not stripped_one and ln.strip():
            for label in labels:
                if re.match(rf"^\s*\**\s*{re.escape(label)}\s*:?\s*\**\s*", ln, re.IGNORECASE):
                    ln = re.sub(
                        rf"^\s*\**\s*{re.escape(label)}\s*:?\s*\**\s*", "",
                        ln, flags=re.IGNORECASE,
                    )
                    break
            stripped_one = True
        out.append(ln)
    return "\n".join(out)


# --- reviewer adapters ------------------------------------------------------


_PROMPTS_DIR = Path(__file__).parent / "reviewer_prompts"


def _load_prompt(family: str) -> str:
    """Concatenate the family-specific preamble and the shared template."""
    fam_path = _PROMPTS_DIR / f"{family}.md"
    shared_path = _PROMPTS_DIR / "_shared.md"
    if not fam_path.exists():
        raise FileNotFoundError(f"reviewer prompt missing: {fam_path}")
    if not shared_path.exists():
        raise FileNotFoundError(f"shared reviewer prompt missing: {shared_path}")
    return f"{fam_path.read_text(encoding='utf-8')}\n\n{shared_path.read_text(encoding='utf-8')}"


def build_review_prompt(
    *,
    family: str,
    ticket_key: str,
    ticket_summary: str,
    summary_md: str,
    diff: str,
    branch: str,
    base_branch: str,
) -> str:
    """Render the per-family prompt. The shared block has format slots; the
    preamble has none.
    """
    tmpl = _load_prompt(family)
    return tmpl.format(
        ticket_key=ticket_key,
        ticket_summary=ticket_summary,
        summary_md=summary_md,
        diff=diff,
        branch=branch,
        base_branch=base_branch,
    )


def collect_diff(
    *,
    repo_root: Path,
    base_branch: str,
    branch: str,
    max_lines: int = MAX_DIFF_LINES,
) -> str:
    """Return `git diff <base>...<branch>` truncated to max_lines.

    Uses three-dot to show only the changes introduced on `branch` since
    its fork point from `base_branch`. The triple-dot form is the right
    semantic for "show me what this change added", not "show me the
    cross-merge differences".
    """
    proc = subprocess.run(
        ["git", "diff", f"{base_branch}...{branch}"],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    if proc.returncode != 0:
        # Fall back to .. (two-dot) — useful when fork point is broken
        # (e.g., a brand new orphan branch).
        proc = subprocess.run(
            ["git", "diff", f"{base_branch}..{branch}"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
    if proc.returncode != 0:
        return f"<git diff failed: {proc.stderr.strip()[:500]}>"
    diff = proc.stdout
    lines = diff.splitlines()
    if len(lines) > max_lines:
        head = "\n".join(lines[:max_lines])
        return f"{head}\n\n... [diff truncated at {max_lines} lines of {len(lines)} total] ..."
    return diff


class ReviewerUnavailable(Exception):
    """Raised by a `Reviewer._invoke_cli` when the CLI ran but produced no
    usable output.

    Unlike a generic exception (which `review()` wraps as "cli invocation
    raised: ..."), the message of this exception becomes the verdict's
    `error` reason verbatim. Use it when the adapter has positively
    determined the reviewer is unavailable — e.g. agy exiting 0 with empty
    stdout (antigravity-cli#76) — and must NOT fall through to a parse
    attempt or a retry.
    """


class Reviewer:
    """Abstract base for one reviewer in the cross-family panel.

    Subclasses implement `_invoke_cli` to call their family's binary; the
    base class handles parsing, retry on parse failure, and UNAVAILABLE
    soft-fail semantics.
    """

    family: str = ""
    cli_bin: str = ""

    def __init__(self, *, cli_bin: str | None = None, timeout_seconds: int = DEFAULT_REVIEWER_TIMEOUT_SECONDS):
        if cli_bin is not None:
            self.cli_bin = cli_bin
        self.timeout_seconds = timeout_seconds

    def review(self, prompt: str) -> ReviewerVerdict:
        """Invoke the CLI, parse the output, retry once on parse failure.

        Returns a ReviewerVerdict — never raises. Errors are captured on
        the verdict (UNAVAILABLE for execution failures, PARSE_FAILED for
        unrecoverable output mangling).
        """
        import time

        start = time.monotonic()
        try:
            stdout = self._invoke_cli(prompt)
        except ReviewerUnavailable as e:
            # MUST precede `except Exception`: ReviewerUnavailable is a
            # subclass of Exception and carries a verbatim error string. If
            # the generic handler caught it first, the reason would be
            # mangled into "cli invocation raised: ...".
            # The adapter positively determined the reviewer is unavailable
            # (e.g. agy empty-stdout, antigravity-cli#76). The message is the
            # reason verbatim — no parse attempt, no retry.
            return ReviewerVerdict(
                family=self.family, verdict=Verdict.UNAVAILABLE,
                error=str(e),
                duration_seconds=time.monotonic() - start,
            )
        except FileNotFoundError as e:
            return ReviewerVerdict(
                family=self.family, verdict=Verdict.UNAVAILABLE,
                error=f"cli not found: {e}",
                duration_seconds=time.monotonic() - start,
            )
        except subprocess.TimeoutExpired:
            return ReviewerVerdict(
                family=self.family, verdict=Verdict.UNAVAILABLE,
                error=f"cli timed out after {self.timeout_seconds}s",
                duration_seconds=time.monotonic() - start,
            )
        except Exception as e:
            return ReviewerVerdict(
                family=self.family, verdict=Verdict.UNAVAILABLE,
                error=f"cli invocation raised: {e}",
                duration_seconds=time.monotonic() - start,
            )

        rv = parse_review_output(self.family, stdout)
        rv.duration_seconds = time.monotonic() - start

        if rv.verdict != Verdict.PARSE_FAILED:
            return rv

        # One retry with a strict-template reminder appended.
        retry_prompt = (
            prompt
            + "\n\n---\n\nIMPORTANT: Your previous output could not be parsed. "
            "You MUST emit the exact sections and headers from the output template. "
            "Start your response with `## Verdict` on its own line. Do not include "
            "anything before that header. The very next line must be one of: "
            "APPROVE, CHANGES_REQUESTED, REJECT.\n"
        )
        try:
            stdout2 = self._invoke_cli(retry_prompt)
        except Exception as e:
            rv.error = f"retry raised: {e}"
            return rv
        rv2 = parse_review_output(self.family, stdout2)
        rv2.duration_seconds = time.monotonic() - start
        if rv2.verdict == Verdict.PARSE_FAILED:
            rv2.error = "parse failed twice; second attempt also unparseable"
        return rv2

    def _invoke_cli(self, prompt: str) -> str:  # pragma: no cover (subclass)
        raise NotImplementedError


class ClaudeReviewer(Reviewer):
    """Reviewer that shells out to `claude --print`.

    Uses the same flag set as the dispatcher's Tasker spawn:
    `--print --output-format json --permission-mode bypassPermissions
    --allow-dangerously-skip-permissions`. The reviewer needs no tool use
    beyond reading the prompt, but the bypass flags prevent any incidental
    tool-permission prompt from stalling stdin.
    """

    family = "claude"
    cli_bin = "claude"

    def _invoke_cli(self, prompt: str) -> str:
        proc = subprocess.run(
            [
                self.cli_bin, "--print",
                "--output-format", "json",
                "--permission-mode", "bypassPermissions",
                "--allow-dangerously-skip-permissions",
            ],
            input=prompt,
            capture_output=True,
            text=True,
            check=False,
            timeout=self.timeout_seconds,
            # claude reviewer rides the subscription, not the metered API
            env={k: v for k, v in os.environ.items()
                 if k not in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")},
        )
        if proc.returncode != 0:
            raise RuntimeError(
                f"claude exit={proc.returncode}: {proc.stderr.strip()[-400:]}"
            )
        # --output-format json wraps the final assistant message in a JSON
        # envelope. Extract the message text; if envelope parsing fails,
        # fall through to using stdout as-is (the parser is tolerant).
        return _extract_claude_message(proc.stdout) or proc.stdout


class GeminiReviewer(Reviewer):
    """Reviewer that shells out to `agy --print ""` with the prompt piped on
    stdin.

    Google rebranded `gemini` CLI → `agy` (Antigravity CLI). The model
    family identifier stays "gemini" so historical panel records and
    column headers (panel_verdict_gemini) remain comparable; only the
    binary name and flag set changed.

    Empty positional arg + stdin avoids E2BIG on large diffs (Linux
    ARG_MAX ~128KB per arg; a 3000-line diff easily exceeds that). Agy's
    `--print ""` accepts the real prompt on stdin, mirroring the old
    gemini `-p ""` behavior. `--print-timeout` is set to match the
    dispatcher's outer timeout so agy doesn't internally bail at its
    5-minute default before subprocess.run does.

    Agy has no `--yolo` / `-o text` equivalents — both are silently
    ignored (printed help, returncode 0), so we deliberately omit them.
    `--dangerously-skip-permissions` is NOT used: it causes agy to
    auto-execute tool calls (workspace init, file edits) when the prompt
    looks remotely actionable, which is wrong for a stateless reviewer.
    """

    family = "gemini"
    cli_bin = "agy"

    def _invoke_cli(self, prompt: str) -> str:
        proc = subprocess.run(
            [
                self.cli_bin, "--print", "",
                "--print-timeout", f"{int(self.timeout_seconds)}s",
            ],
            input=prompt,
            capture_output=True,
            text=True,
            check=False,
            timeout=self.timeout_seconds,
        )
        if proc.returncode != 0:
            raise RuntimeError(
                f"agy exit={proc.returncode}: {proc.stderr.strip()[-400:]}"
            )
        # antigravity-cli#76: agy can exit 0 yet emit nothing on stdout when
        # stdout is a non-TTY pipe — which is exactly how the panel consumes
        # it (subprocess.run with capture_output). An empty string must NOT
        # reach the parser: there it becomes PARSE_FAILED (a blocker that
        # also burns a full retry invocation) and could, if the parser ever
        # changed, be mistaken for a real verdict. Treat exit-0-empty-stdout
        # as a positive UNAVAILABLE signal instead.
        if not proc.stdout.strip():
            raise ReviewerUnavailable(
                "empty stdout (suspected antigravity-cli#76)"
            )
        return proc.stdout


class CodexReviewer(Reviewer):
    """Reviewer that shells out to `codex exec --sandbox workspace-write`.

    `exec` runs Codex non-interactively; `--sandbox workspace-write` grants
    it write access to the workspace without approval gates. This replaces
    the old `--full-auto` shortcut, which codex deprecated (it expanded to
    `--sandbox workspace-write --ask-for-approval on-failure`; `exec` never
    prompts for approval, so only the sandbox half is meaningful here).

    Codex's stdout interleaves agent progress (commands run, files read)
    with the final response, so we use `--output-last-message <tmpfile>` to
    capture ONLY the final assistant message — same role as Claude's
    `--output-format json` envelope.

    `--color never` disables ANSI so the parser doesn't have to strip it.
    `--skip-git-repo-check` lets us run outside a repo (review doesn't need
    git context — it has the diff already in the prompt).
    """

    family = "codex"
    cli_bin = "codex"

    def _invoke_cli(self, prompt: str) -> str:
        import tempfile

        # tempfile.NamedTemporaryFile with delete=False so codex can write
        # to it; we read and unlink ourselves. Use the default tmpdir.
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", prefix="codex-review-", delete=False,
        ) as tf:
            out_path = Path(tf.name)
        try:
            # Pass `-` as the positional prompt so codex reads from stdin.
            # Per `codex exec --help`: "If not provided as an argument (or
            # if `-` is used), instructions are read from stdin." This
            # avoids E2BIG when the prompt exceeds Linux's per-arg limit
            # (~128KB), which happens on diffs >~2000 lines.
            #
            # Passing `input=` makes subprocess.run allocate a stdin PIPE,
            # write the prompt, then CLOSE it — codex receives EOF and exits
            # its read loop. A non-TTY stdin left OPEN (inherited from the
            # parent) makes `codex exec` block forever waiting for EOF
            # (openai/codex#20919); `input=` provably avoids that here. Any
            # future codex invocation that does NOT feed the prompt on stdin
            # MUST pass `stdin=subprocess.DEVNULL` for the same reason.
            proc = subprocess.run(
                [
                    self.cli_bin, "exec",
                    "--sandbox", "workspace-write",
                    "--color", "never",
                    "--skip-git-repo-check",
                    "--output-last-message", str(out_path),
                    "-",
                ],
                input=prompt,
                capture_output=True,
                text=True,
                check=False,
                timeout=self.timeout_seconds,
            )
            if proc.returncode != 0:
                raise RuntimeError(
                    f"codex exit={proc.returncode}: {proc.stderr.strip()[-400:]}"
                )
            # Prefer the captured last-message file; fall back to stdout.
            try:
                text = out_path.read_text(encoding="utf-8")
            except (OSError, FileNotFoundError):
                text = ""
            return text or proc.stdout
        finally:
            try:
                out_path.unlink()
            except OSError:
                pass


class GrokReviewer(Reviewer):
    """Advisory-tier reviewer that shells out to `grok` (xAI's Grok CLI).

    First occupant of the panel's probationary seat: it runs in parallel
    with the authoritative three but NEVER affects consensus — its verdicts
    and findings are journaled for scorecard comparison only.

    Contract live-verified against grok 0.2.39 (2026-06-10):

      * Headless single-shot: `grok --prompt-file <path> --output-format
        plain --always-approve` writes the final response text to stdout
        and exits 0.
      * stderr is noisy (ANSI ERROR log lines) even on success — never
        parse stderr; it is only quoted in error messages.
      * `-p/--single <PROMPT>` also works but carries the prompt as one
        argv element → E2BIG risk on large diffs (Linux ARG_MAX ~128KB per
        arg). The prompt therefore goes through a tempfile via
        `--prompt-file`, mirroring CodexReviewer's tempfile pattern
        (NamedTemporaryFile delete=False, unlink in finally).
      * stdin is explicitly DEVNULL: the prompt comes from the file, and a
        non-TTY stdin left open is exactly the hang class CodexReviewer
        documents (openai/codex#20919) — don't risk grok sharing it.
      * grok has no internal print-timeout flag; the subprocess timeout
        (self.timeout_seconds) is the only budget.
      * Failure mapping: nonzero exit → RuntimeError with exit code +
        stderr tail (base class maps it to UNAVAILABLE); exit 0 with
        empty/whitespace-only stdout → ReviewerUnavailable("empty stdout"),
        like GeminiReviewer's agy#76 handling. Missing/expired grok auth
        emits only stderr errors, so it lands in one of those two paths
        and degrades cleanly to UNAVAILABLE.
    """

    family = "grok"
    cli_bin = "grok"

    def _invoke_cli(self, prompt: str) -> str:
        import tempfile

        # delete=False so the file survives the `with` for grok to read;
        # we unlink ourselves in the finally.
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", prefix="grok-review-", delete=False,
            encoding="utf-8",
        ) as tf:
            tf.write(prompt)
            prompt_path = Path(tf.name)
        try:
            proc = subprocess.run(
                [
                    self.cli_bin,
                    "--prompt-file", str(prompt_path),
                    "--output-format", "plain",
                    "--always-approve",
                ],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                check=False,
                timeout=self.timeout_seconds,
            )
            if proc.returncode != 0:
                raise RuntimeError(
                    f"grok exit={proc.returncode}: {proc.stderr.strip()[-400:]}"
                )
            if not proc.stdout.strip():
                raise ReviewerUnavailable("empty stdout")
            return proc.stdout
        finally:
            try:
                prompt_path.unlink()
            except OSError:
                pass


# --- codex usage parsing ----------------------------------------------------


@dataclass
class CodexUsage:
    """Per-turn token usage extracted from `codex exec --json` stdout.

    All fields default to None so the dispatcher operates fine when codex is
    invoked without `--json`, when the stream carries no usage event, or when
    the JSON schema drifts. Mirrors `spawn.SpawnUsage`'s resilient-by-design
    contract.

    `reasoning_output_tokens` is the version-gated field: codex added it to
    the usage event somewhere between 0.122 and 0.139. Builds older than that
    (e.g. 0.121.0) omit it entirely, so we keep it `None` (= "not reported")
    rather than coercing a missing key to 0 (= "reported zero"). Downstream
    quota math must treat None and 0 differently.
    """

    input_tokens: int | None = None
    cached_input_tokens: int | None = None
    output_tokens: int | None = None
    reasoning_output_tokens: int | None = None
    total_tokens: int | None = None

    def to_dict(self) -> dict:
        return {
            "input_tokens": self.input_tokens,
            "cached_input_tokens": self.cached_input_tokens,
            "output_tokens": self.output_tokens,
            "reasoning_output_tokens": self.reasoning_output_tokens,
            "total_tokens": self.total_tokens,
        }


# Keys that mark a dict as a codex usage object. Across 0.122–0.139 the usage
# payload always carries at least input + output token counts.
_USAGE_MARKER_KEYS = ("input_tokens", "output_tokens", "total_tokens")


def _coerce_usage_dict(obj: object) -> dict | None:
    """Return the usage dict reachable from one parsed JSON value, or None.

    Tolerates the shapes codex has shipped:
      * the usage object itself: ``{"input_tokens": ...}``
      * a ``token_count`` event:  ``{"type": "token_count", "usage": {...}}``
      * a nested ``info`` block:   ``{"info": {"total_token_usage": {...}}}``
        (and the ``{"msg": {"info": {...}}}`` wrapper some builds emit).
    """
    if not isinstance(obj, dict):
        return None

    def _has_markers(d: object) -> bool:
        return isinstance(d, dict) and any(k in d for k in _USAGE_MARKER_KEYS)

    # Direct usage object.
    if _has_markers(obj):
        return obj
    # token_count / generic events nest under "usage".
    if _has_markers(obj.get("usage")):
        return obj["usage"]
    # info.total_token_usage (optionally wrapped in "msg").
    for container in (obj, obj.get("msg")):
        if isinstance(container, dict):
            info = container.get("info")
            if isinstance(info, dict) and _has_markers(info.get("total_token_usage")):
                return info["total_token_usage"]
    return None


def parse_codex_usage(stdout: str) -> CodexUsage:
    """Pull token usage out of `codex exec --json` stdout.

    The `--json` stream is line-delimited JSON; usage is reported per turn and
    accumulates, so we scan every line and keep the LAST usage object found
    (the cumulative total for the run). A single non-streamed JSON object is
    also accepted. Returns an empty CodexUsage on any error — callers that
    don't request usage (or run an older codex) get all-None, never a raise.
    """
    if not stdout or not stdout.strip():
        return CodexUsage()

    import json

    def _int(v):
        try:
            return int(v) if v is not None else None
        except (TypeError, ValueError):
            return None

    usage_dict: dict | None = None
    stripped = stdout.strip()

    # Fast path: the whole blob is one JSON value (non-streamed).
    try:
        whole = json.loads(stripped)
    except (json.JSONDecodeError, ValueError):
        whole = None
    if whole is not None:
        usage_dict = _coerce_usage_dict(whole)

    # Streamed path: scan each line, keep the last usage object seen.
    if usage_dict is None:
        for line in stripped.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue
            found = _coerce_usage_dict(obj)
            if found is not None:
                usage_dict = found  # keep last (cumulative) wins

    if usage_dict is None:
        return CodexUsage()

    # reasoning_output_tokens: only set when the key is actually present, so
    # absence (older codex) stays None rather than collapsing to 0.
    reasoning = (
        _int(usage_dict.get("reasoning_output_tokens"))
        if "reasoning_output_tokens" in usage_dict
        else None
    )
    return CodexUsage(
        input_tokens=_int(usage_dict.get("input_tokens")),
        cached_input_tokens=_int(usage_dict.get("cached_input_tokens")),
        output_tokens=_int(usage_dict.get("output_tokens")),
        reasoning_output_tokens=reasoning,
        total_tokens=_int(usage_dict.get("total_tokens")),
    )


def _extract_claude_message(stdout: str) -> str | None:
    """If stdout is a `claude --output-format json` envelope, return the
    `result` field (the final assistant message text). Returns None on any
    parse failure — caller falls back to raw stdout.
    """
    import json

    if not stdout or not stdout.strip():
        return None
    try:
        doc = json.loads(stdout.strip())
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(doc, dict):
        return None
    # The CLI uses `result` for the assistant's final message text.
    # Older builds used `response`; accept both.
    for key in ("result", "response", "text"):
        v = doc.get(key)
        if isinstance(v, str) and v.strip():
            return v
    return None


# --- panel runner -----------------------------------------------------------


# Default panel composition. Tests substitute with mock reviewers.
def default_reviewers(timeout_seconds: int = DEFAULT_REVIEWER_TIMEOUT_SECONDS) -> list[Reviewer]:
    # ForeverIndy cost optimisation: the authoritative panel is the three
    # FLAT-RATE-subscription families (Gemini, Codex, Grok). Claude is dropped
    # from the panel because (a) it is the metered/per-token agent AND already
    # the Tasker, so Claude-reviewing-Claude is same-family/partially circular,
    # and (b) leaning on the fixed-cost reviewers makes the panel effectively
    # free. The corroboration gate (see aggregate()) blocks only on a CRITICAL
    # or a HIGH that ≥2 of these three independently raise, so no single family
    # (incl. a flaky/UNAVAILABLE Grok seat) can solo-block.
    return [
        GeminiReviewer(timeout_seconds=timeout_seconds),
        CodexReviewer(timeout_seconds=timeout_seconds),
        GrokReviewer(timeout_seconds=timeout_seconds),
    ]


# Registry of advisory (probationary, non-blocking) reviewer families a repo
# may opt into via `.dispatcher.yaml` `panel.advisory`. Promotion of an
# advisory family into the authoritative panel is a future explicit human
# decision — never automatic.
ADVISORY_FAMILIES: dict[str, type[Reviewer]] = {"grok": GrokReviewer}


def advisory_reviewers_from_names(
    names: Iterable[str],
    *,
    timeout_seconds: int = DEFAULT_REVIEWER_TIMEOUT_SECONDS,
) -> tuple[list[Reviewer], list[str]]:
    """Instantiate advisory reviewers from config names.

    Returns ``(reviewers, unknown_names)`` — unknown names are returned
    (never raised) so the caller can journal/log them without an unknown
    config entry crashing the authoritative panel. Matching is
    case-insensitive on the trimmed name.
    """
    reviewers: list[Reviewer] = []
    unknown: list[str] = []
    for raw in names:
        cls = ADVISORY_FAMILIES.get(str(raw).strip().lower())
        if cls is None:
            unknown.append(str(raw))
        else:
            reviewers.append(cls(timeout_seconds=timeout_seconds))
    return reviewers, unknown


def run_panel(
    *,
    ticket_key: str,
    ticket_summary: str,
    summary_md: str,
    diff: str,
    branch: str,
    base_branch: str,
    reviewers: list[Reviewer] | None = None,
    advisory_reviewers: list[Reviewer] | None = None,
    log: Callable[[str], None] = lambda _m: None,
) -> PanelVerdict:
    """Invoke all reviewers in parallel and aggregate.

    Each reviewer's prompt is the same content shape but with a
    family-specific preamble. They run on separate threads and as soon as
    all three complete the panel composes its consensus.

    A reviewer that returns UNAVAILABLE (or PARSE_FAILED) is counted as a
    degraded seat: a single one is tolerated, but a panel with fewer than two
    VALID (parseable, ran) reviews degrades to "incomplete" because we cannot
    prove the code was actually reviewed. The orchestrator treats "incomplete"
    the same as "block" for auto-integration gating (see aggregate()).

    `advisory_reviewers` (probationary tier) run in the SAME executor pass,
    in parallel with the authoritative set, but their verdicts attach to
    ``PanelVerdict.advisory`` and never feed the consensus. An advisory
    worker that leaks an exception is recorded as UNAVAILABLE for that
    family instead of crashing the panel; authoritative worker exceptions
    still re-raise (framework bugs must stay loud).

    `log` is an optional one-arg sink for progress messages — the
    orchestrator wires this to its run.log.
    """
    revs = reviewers if reviewers is not None else default_reviewers()
    advs = list(advisory_reviewers) if advisory_reviewers else []
    if not revs:
        return PanelVerdict(
            consensus="incomplete", reviewers=[],
            summary="no reviewers configured", blocking_findings=[],
        )

    results: list[ReviewerVerdict | None] = [None] * len(revs)
    adv_results: list[ReviewerVerdict | None] = [None] * len(advs)
    log_lock = threading.Lock()

    def _safe_log(msg: str) -> None:
        with log_lock:
            log(msg)

    def _review_one(r: Reviewer) -> ReviewerVerdict:
        prompt = build_review_prompt(
            family=r.family,
            ticket_key=ticket_key,
            ticket_summary=ticket_summary,
            summary_md=summary_md,
            diff=diff,
            branch=branch,
            base_branch=base_branch,
        )
        return r.review(prompt)

    def _log_verdict(r: Reviewer, rv: ReviewerVerdict, *, advisory: bool) -> None:
        tag = f"{r.family} (advisory)" if advisory else r.family
        _safe_log(
            f"  panel[{ticket_key}] {tag}: verdict={rv.verdict.value} "
            f"findings={len(rv.findings)} "
            f"blocking={len(rv.blocking_findings())} "
            f"dur={rv.duration_seconds:.1f}s" if rv.duration_seconds is not None
            else f"  panel[{ticket_key}] {tag}: verdict={rv.verdict.value}"
        )

    def _run_one(idx: int, r: Reviewer) -> None:
        _safe_log(f"  panel[{ticket_key}] {r.family}: starting")
        rv = _review_one(r)
        results[idx] = rv
        _log_verdict(r, rv, advisory=False)

    def _run_one_advisory(idx: int, r: Reviewer) -> None:
        _safe_log(f"  panel[{ticket_key}] {r.family} (advisory): starting")
        try:
            rv = _review_one(r)
        except Exception as e:
            # An advisory seat must never take the authoritative panel
            # down — a leaked exception (e.g. missing prompt file for the
            # family) is recorded as UNAVAILABLE and the panel proceeds.
            rv = ReviewerVerdict(
                family=r.family, verdict=Verdict.UNAVAILABLE,
                error=f"advisory worker raised: {e}",
            )
        adv_results[idx] = rv
        _log_verdict(r, rv, advisory=True)

    with ThreadPoolExecutor(max_workers=len(revs) + len(advs)) as exe:
        futures = [exe.submit(_run_one, i, r) for i, r in enumerate(revs)]
        adv_futures = [
            exe.submit(_run_one_advisory, i, r) for i, r in enumerate(advs)
        ]
        for f in as_completed(futures):
            # Re-raise any unexpected AUTHORITATIVE worker exceptions
            # (Reviewer.review() is supposed to capture all internal
            # errors; an exception here means our framework leaked).
            f.result()
        for f in as_completed(adv_futures):
            # Advisory workers swallow their own exceptions; waiting here
            # only ensures the pass is complete before aggregation.
            f.result()

    completed = [r for r in results if r is not None]
    advisory_verdicts = [
        rv if rv is not None else ReviewerVerdict(
            family=r.family, verdict=Verdict.UNAVAILABLE,
            error="advisory worker produced no result",
        )
        for r, rv in zip(advs, adv_results)
    ]
    return aggregate(completed, advisory=advisory_verdicts)


def aggregate(
    reviews: list[ReviewerVerdict],
    advisory: list[ReviewerVerdict] | None = None,
) -> PanelVerdict:
    """Compose a PanelVerdict from a set of reviewer outputs.

    Rules (ForeverIndy corroboration gate — see the block comment below):
      * a CRITICAL from ANY family blocks immediately;
      * a HIGH blocks only when ≥2 VALID families independently raise a
        blocking finding (corroboration);
      * otherwise the panel APPROVES — but only if ≥2 seats produced a real,
        parseable review (the valid set). A panel with fewer than two valid
        seats (all/most UNAVAILABLE and/or PARSE_FAILED) is "incomplete",
        never "approve": auto-integrate must not proceed on effectively
        unreviewed code.

    `advisory` verdicts are attached verbatim to ``PanelVerdict.advisory``
    and have ZERO effect on the consensus math above — an advisory
    CRITICAL never blocks, and an advisory APPROVE never rescues a missing
    authoritative seat.
    """
    advisory_list = list(advisory) if advisory else []
    if not reviews:
        return PanelVerdict(
            consensus="incomplete", reviewers=[],
            summary="no reviewer results", blocking_findings=[],
            advisory=advisory_list,
        )

    blocking_findings: list[Finding] = []
    for r in reviews:
        blocking_findings.extend(r.blocking_findings())

    # --- ForeverIndy corroboration gate -------------------------------------
    # Original rule: unanimous APPROVE; any single dissenter (or one
    # UNAVAILABLE seat) blocks. With three independent strict LLM reviewers
    # that each reliably surface a DIFFERENT idiosyncratic HIGH finding on any
    # diff, unanimous-approve never converges — good work parks while reviewers
    # play whack-a-mole. Instead we require CORROBORATION:
    #   * a CRITICAL from ANY family blocks immediately (real ship-stoppers:
    #     cross-household data leak, auth bypass, billing error, regulatory —
    #     no second vote needed);
    #   * a non-CRITICAL (HIGH) blocker blocks only when ≥2 AVAILABLE families
    #     each independently raise a blocking finding (a peer confirms it);
    #   * a single uncorroborated dissenter does NOT block — its findings are
    #     still recorded (journal + summary) and harvested into the review
    #     backlog to fix later, but the task ships;
    #   * an UNAVAILABLE seat no longer blocks on its own (it can't corroborate
    #     or dissent); only a panel with no VALID review is "incomplete".
    #
    # PARSE_FAILED is treated like UNAVAILABLE for the "did the panel actually
    # review anything" question. A PARSE_FAILED seat RAN but produced no
    # parseable verdict or findings, so — exactly like an UNAVAILABLE seat — it
    # can neither corroborate a block nor stand as evidence the code was
    # reviewed. Crucially it must NOT prop up an auto-integrate "approve":
    # without this, a MAJORITY- or ALL-PARSE_FAILED panel used to fall through
    # to "approve" and auto-integrate effectively-unreviewed (money-adjacent)
    # code. It drops out of the `valid` set below. (It already contributes zero
    # blocking findings, so the block-side corroboration count is unchanged.)
    available = [r for r in reviews if r.verdict != Verdict.UNAVAILABLE]
    valid = [r for r in available if r.verdict != Verdict.PARSE_FAILED]
    families_with_blocking = sum(1 for r in valid if r.blocking_findings())
    any_critical = any(f.severity == Severity.CRITICAL for f in blocking_findings)

    # Block wins over everything (a real ship-stopper was found). Otherwise an
    # "approve" requires enough VALID seats that the code was actually reviewed.
    #
    # Default bar is ≥2 valid seats when ≥3 were invited (classic panel: one
    # flaky UNAVAILABLE still ships). When fewer seats were invited (panel:
    # single, or a test override), one valid APPROVE is enough so a lone
    # healthy seat is not incomplete-blocked.
    min_valid_for_approve = 2 if len(reviews) >= 3 else 1
    if any_critical or families_with_blocking >= 2:
        consensus = "block"
    elif len(valid) >= min_valid_for_approve:
        consensus = "approve"
    else:
        consensus = "incomplete"

    summary = _summarize(reviews, consensus, blocking_findings)
    return PanelVerdict(
        consensus=consensus,
        reviewers=list(reviews),
        summary=summary,
        blocking_findings=blocking_findings,
        advisory=advisory_list,
    )


def _summarize(
    reviews: list[ReviewerVerdict],
    consensus: str,
    blocking_findings: list[Finding],
) -> str:
    """One-line human-readable summary stamped on the YAML row."""
    verdicts = ", ".join(f"{r.family}={r.verdict.value}" for r in reviews)
    parts = [f"consensus={consensus}", verdicts]
    if blocking_findings:
        sevs = [f.severity.value for f in blocking_findings]
        parts.append(
            f"blocking={len(blocking_findings)} "
            f"({sum(1 for s in sevs if s == 'CRITICAL')}C/"
            f"{sum(1 for s in sevs if s == 'HIGH')}H)"
        )
    return " | ".join(parts)


def render_findings_markdown(panel: PanelVerdict) -> str:
    """Render the panel's blocking findings as a markdown block suitable
    for appending to the Tasker's summary.md so humans see them at triage.

    When advisory reviewers ran, a clearly-labelled non-blocking appendix
    follows the authoritative content — in BOTH the approve and block
    render paths. Advisory findings never appear under "Blocking findings".
    """
    if panel.consensus == "approve":
        md = f"## Cross-family panel\n\nVerdict: APPROVE ({panel.summary})\n"
        if panel.advisory:
            md += "\n" + _render_advisory_appendix(panel)
        return md

    lines = [
        "## Cross-family panel",
        "",
        f"**Verdict:** {panel.consensus.upper()}",
        f"**Summary:** {panel.summary}",
        "",
        "### Per-reviewer verdicts",
        "",
        "| Family | Verdict | Findings | Dimensions |",
        "|--------|---------|----------|------------|",
    ]
    for r in panel.reviewers:
        dim_str = ", ".join(
            f"{name[:4]}={r.dimensions.get(name, '–')}" for name in DIMENSION_NAMES
        )
        lines.append(
            f"| {r.family} | {r.verdict.value} | "
            f"{len(r.findings)} ({len(r.blocking_findings())} blocking) | "
            f"{dim_str} |"
        )
    if panel.blocking_findings:
        lines += ["", "### Blocking findings", ""]
        for f in panel.blocking_findings:
            lines.append(f"- **{f.severity.value}** at `{f.location}` — {f.description}")
            if f.fix:
                lines.append(f"  - *Fix:* {f.fix}")
    out = "\n".join(lines) + "\n"
    if panel.advisory:
        out += "\n" + _render_advisory_appendix(panel)
    return out


def _render_advisory_appendix(panel: PanelVerdict) -> str:
    """Render the advisory (probationary) seats as a non-blocking appendix.

    Visually separate from the authoritative sections: its heading states
    the tier and every finding line is prefixed with `[advisory:family]` so
    nothing in it can be mistaken for a blocking finding.
    """
    lines = [
        "### Advisory reviewers (non-blocking, probationary)",
        "",
        "Recorded for scorecard comparison only — these verdicts and",
        "findings do NOT count toward consensus and can never block.",
        "",
        "| Family | Verdict | Findings |",
        "|--------|---------|----------|",
    ]
    for r in panel.advisory:
        lines.append(f"| {r.family} | {r.verdict.value} | {len(r.findings)} |")
    any_findings = any(r.findings for r in panel.advisory)
    if any_findings:
        lines += ["", "#### Advisory findings (non-blocking)", ""]
        for r in panel.advisory:
            for f in r.findings:
                lines.append(
                    f"- [advisory:{r.family}] **{f.severity.value}** at "
                    f"`{f.location}` — {f.description}"
                )
                if f.fix:
                    lines.append(f"  - *Fix:* {f.fix}")
    return "\n".join(lines) + "\n"
