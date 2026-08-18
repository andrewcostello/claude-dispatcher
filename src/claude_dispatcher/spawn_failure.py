"""Classify a failed spawn: infrastructure or quality (D-64).

The dispatcher had ONE branch — `exit_code != 0` — so every failure was a quality
failure. Consequences, all measured:

  * the cascade escalates on it. Trying harder cannot fix a server overload, the
    retry is spent against the same condition, and it burns a rung a real quality
    failure would have needed.
  * the row records `session_exit_code_1`, which reads as the agent failing. The
    status, the provider's own message and `terminal_reason` are in the log and
    nowhere a human looks.
  * the effort bump persists on the row, so a transient failure permanently
    raises the cost of every later dispatch of that task.

Live on 2026-08-18, W2-1-1: `api_error_status: 529`, `terminal_reason:
"api_error"`, provider message "529 Overloaded. This is a server-side issue,
usually temporary — try again in a moment." Recorded as
`blocked_reason: session_exit_code_1`.

Statuses are NOT one class. A 529 is retryable in seconds; a 429 quota resets
hours later, so an immediate retry is guaranteed to fail; a 401 needs a human and
no retry helps. Collapsing them is how "just re-run it" became the only advice.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import Enum

#: Statuses that mean "the provider could not serve this", by what to DO.
_OVERLOADED = frozenset({500, 502, 503, 504, 529})
_QUOTA = frozenset({429})

#: Public alias: the orchestrator asks "is this the failure another
#: subscription could answer?" and must not reach into a private name.
QUOTA_STATUSES = _QUOTA
_AUTH = frozenset({401, 403})


class FailureKind(str, Enum):
    QUALITY = "quality"
    INFRASTRUCTURE = "infrastructure"


class Retry(str, Enum):
    NOW = "retryable_now"
    LATER = "retryable_after_reset"
    NEVER = "needs_a_human"
    CASCADE = "escalate_to_a_stronger_rung"


@dataclass(frozen=True)
class Classification:
    kind: FailureKind
    retry: Retry
    reason: str
    api_error_status: int | None = None
    provider_message: str = ""

    @property
    def is_infrastructure(self) -> bool:
        return self.kind is FailureKind.INFRASTRUCTURE


def _looks_like_result(obj: object) -> bool:
    return isinstance(obj, dict) and (
        obj.get("type") == "result"
        or "api_error_status" in obj
        or "terminal_reason" in obj
    )


def _envelope(text: str) -> dict:
    """The CLI's JSON result envelope, or {}.

    Formatting-independent, and that is a correction rather than a preference: the
    first version matched the literal `"type":"result"` and so depended on the
    emitter using compact separators. Real CLI output is compact, so it passed a
    smoke test and failed against `json.dumps`, which spaces its colons. A parser
    that only works on one whitespace convention is a parser that will break on a
    version bump.

    Lines first, because the CLI emits one JSON document per line; then a
    balanced-brace scan from the END, because progress objects precede the result
    and a forward scan finds a stale status. Tolerant throughout — this runs on
    the output of a process that just died, so half-written JSON is the normal
    case rather than the exotic one.
    """
    if not text:
        return {}
    best: dict = {}
    for line in text.splitlines():
        line = line.strip()
        if not (line.startswith("{") and line.endswith("}")):
            continue
        try:
            got = json.loads(line)
        except ValueError:
            continue
        if _looks_like_result(got):
            best = got
    if best:
        return best

    for start in range(len(text) - 1, -1, -1):
        if text[start] != "{":
            continue
        depth, in_str, esc = 0, False, False
        for i in range(start, len(text)):
            c = text[i]
            if in_str:
                if esc:
                    esc = False
                elif c == "\\":
                    esc = True
                elif c == '"':
                    in_str = False
                continue
            if c == '"':
                in_str = True
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    try:
                        got = json.loads(text[start:i + 1])
                    except ValueError:
                        break
                    if _looks_like_result(got):
                        return got
                    break
    return {}


#: Last-resort scalar extraction from an UNPARSEABLE fragment. Normally parsing
#: JSON with a regex is the wrong tool; here the input is explicitly a fragment of
#: a dead process's output with no opening brace, so there is no document to parse
#: and the alternative is reporting a server overload as a quality failure.
#:
#: Found by classifying the REAL logged failure rather than a reconstruction of it:
#: the log tail is truncated to 600 characters and begins mid-token
#: (`heCreationInputTokens":56759,`), so both parse tiers returned nothing and the
#: 529 read as `session_exit_code_1` — the exact defect being fixed.
_STATUS_RE = re.compile(r'"api_error_status"\s*:\s*(\d{3})')
_TERMINAL_RE = re.compile(r'"terminal_reason"\s*:\s*"([a-z_]+)"')
_MESSAGE_RE = re.compile(r'"result"\s*:\s*"((?:[^"\\]|\\.){0,400})"')


def _scavenge(text: str) -> dict:
    """What can be read out of a fragment. Empty when nothing identifies it."""
    if not text:
        return {}
    out: dict = {}
    status = _STATUS_RE.findall(text)
    if status:
        out["api_error_status"] = int(status[-1])
    terminal = _TERMINAL_RE.findall(text)
    if terminal:
        out["terminal_reason"] = terminal[-1]
    if out:
        message = _MESSAGE_RE.findall(text)
        if message:
            # Decode as a JSON string, not with `unicode_escape`: the latter
            # re-interprets already-decoded UTF-8 byte-by-byte and turned the
            # provider's em dash into mojibake ("temporary â try again"). A
            # garbled quote from the provider is a quote an operator stops
            # trusting.
            try:
                out["result"] = json.loads(f'"{message[-1]}"')
            except ValueError:
                out["result"] = message[-1]
    return out


def classify(exit_code: int, stdout: str = "", stderr: str = "") -> Classification:
    """What kind of failure this was, and what to do about it.

    Defaults to QUALITY/CASCADE — today's behaviour — when nothing identifies it
    as infrastructure. An unrecognised failure must keep the existing handling
    rather than silently stop cascading.
    """
    env = (_envelope(stdout) or _envelope(stderr)
           or _scavenge(stdout) or _scavenge(stderr))
    status = env.get("api_error_status")
    status = int(status) if isinstance(status, (int, str)) and str(status).isdigit() else None
    terminal = str(env.get("terminal_reason") or "")
    message = str(env.get("result") or "").strip()

    if status is None and terminal != "api_error":
        return Classification(
            kind=FailureKind.QUALITY, retry=Retry.CASCADE,
            reason=f"session_exit_code_{exit_code}",
        )

    if status in _QUOTA:
        retry, what = Retry.LATER, "provider quota exhausted"
    elif status in _AUTH:
        retry, what = Retry.NEVER, "provider rejected our credentials"
    elif status in _OVERLOADED:
        retry, what = Retry.NOW, "provider overloaded"
    else:
        # `api_error` with an unknown or absent status is still infrastructure —
        # the provider said so. Retry now is the safe reading: it costs one spawn
        # and the alternative is stranding a task on a transient condition.
        retry, what = Retry.NOW, "provider error"

    detail = f" — {message}" if message else ""
    reason = (
        f"{what} (api_error_status={status if status is not None else 'unset'}, "
        f"{retry.value}){detail}"
    )
    return Classification(
        kind=FailureKind.INFRASTRUCTURE, retry=retry, reason=reason[:600],
        api_error_status=status, provider_message=message,
    )
