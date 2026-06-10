"""Independent LLM verifier (plan Phase 4).

After a Tasker reports Done, the dispatcher spawns an independent verifier
over the task row, the Tasker's summary.md, and the committed diff. The
verifier answers exactly one question: does the diff actually do what the
task asked — nothing stubbed, deferred, or quietly narrowed? It is NOT a
code reviewer; quality belongs to the review panel
(cross_family_reviewer). This module is the verifier mechanism only — the
orchestrator wiring lands in a later phase.

Three layers:
  * `build_verifier_prompt` — renders verifier_prompts/verifier.md with the
    task row, summary, and (truncated) diff.
  * `run_verifier` — spawns the claude CLI with the prompt on stdin and
    captures usage from the JSON envelope.
  * `parse_verdict` — pulls a strict verdict line out of the verifier's
    response, tolerant of surrounding narrative.

Conservative contract: the verifier can block an integration but can never
rubber-stamp one by accident. A spawn failure, unparseable output,
conflicting verdict lines, or any other ambiguity is INCOMPLETE — never
VERIFIED. The `reason` codes let the caller distinguish "couldn't run"
(REASON_SPAWN_FAILED, `error` populated) from "ran and found gaps"
(reason None, `gaps` populated).

No retry logic, no orchestrator imports, no journal writes — the module is
independently testable with a monkeypatched `subprocess.run`.
"""

from __future__ import annotations

import json
import re
import subprocess
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Mapping

from .spawn import SpawnUsage, parse_usage_from_json

# --- constants ----------------------------------------------------------------

# The verifier ingests the entire diff + summary; for typical ticket-sized
# diffs this fits in <2 min, but we leave headroom for the 90th percentile.
DEFAULT_VERIFIER_TIMEOUT_SECONDS = 600

# The diff context is capped to keep prompts under model context limits.
# Real diffs land at ~300-2000 lines; 8000 lines is the safety bound. Above
# that we truncate with a marker. Tickets larger than this should be split
# anyway.
MAX_DIFF_LINES = 8000

# Reason codes stamped on a VerifierVerdict when the INCOMPLETE verdict was
# produced by the parser/spawn machinery rather than by the verifier model
# itself. A clean VERIFIED and an INCOMPLETE-with-parsed-gaps both carry
# reason=None.
REASON_MALFORMED = "verifier_output_malformed"
REASON_GAPS_UNPARSED = "verifier_gaps_unparsed"
REASON_CONFLICTING = "verifier_conflicting_verdicts"
REASON_SPAWN_FAILED = "verifier_spawn_failed"


# --- public dataclasses -------------------------------------------------------


class VerdictKind(str, Enum):
    """The verifier's binary answer: claim holds, or it doesn't."""

    VERIFIED = "VERIFIED"
    INCOMPLETE = "INCOMPLETE"


@dataclass
class Gap:
    """One numbered gap from an INCOMPLETE verdict.

    `location` is "file:line" or "file:?" when the verifier identified a
    file, else None (the gap is described in prose only).
    """

    index: int
    location: str | None
    description: str

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "location": self.location,
            "description": self.description,
        }


@dataclass
class VerifierVerdict:
    """The parsed verdict. `reason` is None for a clean VERIFIED and for an
    INCOMPLETE whose gaps parsed; otherwise it carries one of the REASON_*
    codes explaining why the parser/spawn machinery forced INCOMPLETE.
    """

    verdict: VerdictKind
    gaps: list[Gap] = field(default_factory=list)
    reason: str | None = None
    raw_output: str = ""

    def to_dict(self) -> dict:
        # raw_output intentionally stays off the wire (it can be huge);
        # mirrors ReviewerVerdict.to_dict in cross_family_reviewer.
        return {
            "verdict": self.verdict.value,
            "gaps": [g.to_dict() for g in self.gaps],
            "reason": self.reason,
        }


@dataclass
class VerifierResult:
    """One verifier run: the verdict plus run metadata.

    `error` is populated only on spawn failure (verdict will then be
    INCOMPLETE with reason=REASON_SPAWN_FAILED). `usage` is all-None when
    the CLI didn't produce a parseable JSON envelope.
    """

    verdict: VerifierVerdict
    usage: SpawnUsage = field(default_factory=SpawnUsage)
    duration_seconds: float | None = None
    error: str | None = None

    def to_dict(self) -> dict:
        return {
            "verdict": self.verdict.to_dict(),
            "usage": asdict(self.usage),
            "duration_seconds": self.duration_seconds,
            "error": self.error,
        }


# --- prompt building ----------------------------------------------------------


_PROMPTS_DIR = Path(__file__).parent / "verifier_prompts"


def _load_prompt() -> str:
    """Load the verifier prompt template (a packaging error if missing)."""
    path = _PROMPTS_DIR / "verifier.md"
    if not path.exists():
        raise FileNotFoundError(f"verifier prompt missing: {path}")
    return path.read_text(encoding="utf-8")


def build_verifier_prompt(
    task: Mapping,
    diff: str,
    summary_text: str,
    *,
    max_diff_lines: int = MAX_DIFF_LINES,
) -> str:
    """Render the verifier prompt for one task.

    `task` is a plain mapping (the YAML task row). Missing fields degrade
    to ""/"unknown" rather than raising — the verifier prompt explains the
    absence is the Tasker's problem, not ours. The diff is truncated at
    `max_diff_lines` with an explicit marker so the verifier knows it saw
    a prefix, not the whole change.
    """
    labels = task.get("labels") or []
    diff_lines = diff.splitlines()
    if len(diff_lines) > max_diff_lines:
        head = "\n".join(diff_lines[:max_diff_lines])
        diff = (
            f"{head}\n\n... [diff truncated at {max_diff_lines} lines "
            f"of {len(diff_lines)} total] ..."
        )
    return _load_prompt().format(
        task_key=str(task.get("key") or "unknown"),
        task_summary=str(task.get("summary") or ""),
        task_type=str(task.get("type") or "unknown"),
        task_labels=", ".join(str(lab) for lab in labels),
        task_description=str(task.get("description") or ""),
        summary_md=summary_text,
        diff=diff,
    )


# --- verdict parsing ----------------------------------------------------------


_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")


def _strip_ansi(text: str) -> str:
    """Strip ANSI escape sequences that some CLIs emit even with TTY off."""
    return _ANSI_RE.sub("", text)


# A STRICT verdict line: a line that is ONLY the verdict, tolerating leading
# bullet/whitespace and optional surrounding backticks or ** bold. The `$`
# (end-of-line under MULTILINE) anchor is load-bearing: the prompt's
# instruction echo `Verdict: VERIFIED | INCOMPLETE` must NOT match, and a
# response truncated mid-token (`Verdict: VERIF`) must NOT match either.
_VERDICT_LINE_RE = re.compile(
    r"^[ \t]*(?:[-*>]\s+)?(?:\*\*|`+)?\s*"
    r"Verdict:\s*(VERIFIED|INCOMPLETE)"
    r"\s*(?:\*\*|`+)?[ \t]*$",
    re.MULTILINE,
)

# A numbered gap item: "1. text" or "1) text".
_GAP_ITEM_RE = re.compile(r"^\s*(\d+)[.)]\s+(\S.*?)\s*$")

# A numbered item whose text never arrived (output truncated mid-item,
# e.g. a bare "2." as the last line). Skipped — it is neither a gap nor a
# continuation of the previous one.
_GAP_ITEM_STUB_RE = re.compile(r"^\s*\d+[.)]?\s*$")

# Optional "Gaps:" header between the verdict line and the first item.
_GAPS_HEADER_RE = re.compile(r"^\s*(?:\*\*)?Gaps:?(?:\*\*)?\s*$", re.IGNORECASE)

# A code-fence line terminates gap scanning (the verdict block is fenced).
_FENCE_RE = re.compile(r"^\s*```")

# Leading location token of a gap item: `path.ext:NN`, `path.ext:?`, or bare
# `path.ext`, followed by an em/en dash, hyphen, or colon separator. The
# first token must contain a dot-extension so prose like "The summary..."
# never reads as a location.
_GAP_LOCATION_RE = re.compile(
    r"^(?P<loc>[^\s:—–]+\.[A-Za-z0-9_]+(?::(?:\d+|\?))?)"
    r"\s*(?:[—–-]|:)\s+(?P<desc>\S.*)$"
)


def parse_verdict(raw: str) -> VerifierVerdict:
    """Pull a structured verdict out of the verifier's response text.

    Tolerant of surrounding prose, narrative, and ANSI escapes; strict
    about the verdict line itself. Never raises. The decision table is
    conservative — ambiguity never auto-verifies:

      * no strict verdict line   → INCOMPLETE, reason=REASON_MALFORMED
      * both verdicts present    → INCOMPLETE, reason=REASON_CONFLICTING
                                   (gaps = whatever parses after the last
                                   INCOMPLETE line)
      * only VERIFIED line(s)    → VERIFIED, no gaps
      * only INCOMPLETE line(s)  → INCOMPLETE; gaps parsed after the LAST
                                   verdict line. Zero parseable gaps →
                                   reason=REASON_GAPS_UNPARSED.
    """
    raw = raw or ""
    cleaned = _strip_ansi(raw)
    matches = list(_VERDICT_LINE_RE.finditer(cleaned))
    if not matches:
        # Covers empty/whitespace-only/garbage/truncated-mid-token output.
        return VerifierVerdict(
            verdict=VerdictKind.INCOMPLETE,
            reason=REASON_MALFORMED,
            raw_output=raw,
        )

    kinds = {m.group(1) for m in matches}
    if kinds == {"VERIFIED"}:
        return VerifierVerdict(verdict=VerdictKind.VERIFIED, raw_output=raw)

    # INCOMPLETE is present (alone or alongside VERIFIED). Gaps live in the
    # text following the LAST INCOMPLETE line.
    last_incomplete = [m for m in matches if m.group(1) == "INCOMPLETE"][-1]
    gaps = _parse_gaps(cleaned[last_incomplete.end():])

    if "VERIFIED" in kinds:
        # Self-contradicting output. Keep any gaps for the human, but the
        # reason code marks the verdict as machine-forced.
        return VerifierVerdict(
            verdict=VerdictKind.INCOMPLETE,
            gaps=gaps,
            reason=REASON_CONFLICTING,
            raw_output=raw,
        )
    if not gaps:
        return VerifierVerdict(
            verdict=VerdictKind.INCOMPLETE,
            reason=REASON_GAPS_UNPARSED,
            raw_output=raw,
        )
    return VerifierVerdict(
        verdict=VerdictKind.INCOMPLETE, gaps=gaps, raw_output=raw
    )


def _parse_gaps(text: str) -> list[Gap]:
    """Parse numbered gap items from the text after a verdict line.

    Skips an optional `Gaps:` header and blank lines, stops at a closing
    ``` fence, and folds continuation lines into the preceding item. A
    partially emitted item (e.g. `2.` with no text after a mid-stream
    truncation) simply doesn't parse — earlier items are kept.
    """
    items: list[tuple[int, str]] = []  # (number, accumulated text)
    for line in text.splitlines():
        if _FENCE_RE.match(line):
            break
        if not line.strip():
            continue
        if _GAPS_HEADER_RE.match(line):
            continue
        if _GAP_ITEM_STUB_RE.match(line):
            continue
        m = _GAP_ITEM_RE.match(line)
        if m:
            items.append((int(m.group(1)), m.group(2)))
        elif items:
            # Continuation of a multi-line item description.
            num, acc = items[-1]
            items[-1] = (num, f"{acc} {line.strip()}")
        # else: prose before the first numbered item — ignore.

    gaps: list[Gap] = []
    for num, item in items:
        loc_match = _GAP_LOCATION_RE.match(item)
        if loc_match:
            gaps.append(
                Gap(
                    index=num,
                    location=loc_match.group("loc"),
                    description=loc_match.group("desc").strip(),
                )
            )
        else:
            gaps.append(Gap(index=num, location=None, description=item))
    return gaps


# --- claude CLI spawn adapter ---------------------------------------------------


def _extract_message(stdout: str) -> str | None:
    """If stdout is a `claude --output-format json` envelope, return the
    `result` field (the final assistant message text). Returns None on any
    parse failure — caller falls back to raw stdout.

    Local mirror of cross_family_reviewer._extract_claude_message, kept
    here so this module's only intra-package dependency is spawn.
    """
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


def run_verifier(
    *,
    task: Mapping,
    diff: str,
    summary_text: str,
    claude_bin: str = "claude",
    timeout_seconds: int = DEFAULT_VERIFIER_TIMEOUT_SECONDS,
) -> VerifierResult:
    """Spawn an independent claude verifier over one task's diff + summary.

    Uses the same flag set as the dispatcher's Tasker spawn and the panel's
    ClaudeReviewer: `--print --output-format json --permission-mode
    bypassPermissions --allow-dangerously-skip-permissions`. The verifier
    needs no tool use beyond reading the prompt, but the bypass flags
    prevent any incidental tool-permission prompt from stalling stdin.

    Never raises. Conservative contract: a spawn or parse failure is never
    VERIFIED. CLI missing / timeout / nonzero exit / any other exception
    yields verdict=INCOMPLETE with reason=REASON_SPAWN_FAILED and `error`
    set to a short reason string, so the caller can distinguish "couldn't
    run" (REASON_SPAWN_FAILED + error) from "ran and found gaps" (reason
    None, gaps populated).
    """
    start = time.monotonic()

    def _spawn_failed(message: str) -> VerifierResult:
        return VerifierResult(
            verdict=VerifierVerdict(
                verdict=VerdictKind.INCOMPLETE, reason=REASON_SPAWN_FAILED
            ),
            error=message,
            duration_seconds=time.monotonic() - start,
        )

    try:
        prompt = build_verifier_prompt(task, diff, summary_text)
        proc = subprocess.run(
            [
                claude_bin, "--print",
                "--output-format", "json",
                "--permission-mode", "bypassPermissions",
                "--allow-dangerously-skip-permissions",
            ],
            input=prompt,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_seconds,
        )
    except FileNotFoundError as e:
        return _spawn_failed(f"cli not found: {e}")
    except subprocess.TimeoutExpired:
        return _spawn_failed(f"cli timed out after {timeout_seconds}s")
    except Exception as e:  # resilient by design — never crash the caller
        return _spawn_failed(f"cli invocation raised: {e}")

    if proc.returncode != 0:
        return _spawn_failed(
            f"claude exit={proc.returncode}: {proc.stderr.strip()[-400:]}"
        )

    usage = parse_usage_from_json(proc.stdout)
    # Unwrap the JSON envelope; fall back to raw stdout (parse_verdict is
    # tolerant and conservatively yields INCOMPLETE on anything unparseable).
    message = _extract_message(proc.stdout) or proc.stdout
    return VerifierResult(
        verdict=parse_verdict(message),
        usage=usage,
        duration_seconds=time.monotonic() - start,
    )
