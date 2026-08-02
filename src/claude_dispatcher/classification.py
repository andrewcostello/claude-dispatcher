"""Path-derived classification of a diff, via ``cmd/classify``.

Why this exists
---------------
Every panel-gating decision in this dispatcher is made from *ticket metadata* —
labels, ``type``, size. None of it looks at what the diff actually touches. That
is the same defect class as PR 1294 (a wallet-query regression shipped because a
change was judged "read-path" rather than by its surface) and PR 1298 (a
"client-only" debug panel that was really a fail-open gate).

``cmd/classify`` answers the question from the diff instead: which rules in
``config/risk-paths.json`` the changed files match, and therefore the risk tier,
component presets, whether a financial path is touched, and whether the change
qualifies for a reduced panel.

The contract here is deliberately one-directional:

    path evidence may only ever ADD review, never remove it.

So callers use this to *force* the panel on; a classification that says "low"
never cancels a panel some label or run-mode already required. That keeps the
change safe to roll out — the worst case is more review than before.

Degradation
-----------
Two different things can go wrong, and callers must be able to tell them apart:

  * the binary is **absent** — expected on any host without claude-workflow
    installed. Nothing was ever promised, so a caller degrades to whatever
    gating it had before.
  * the binary is **present but the invocation failed** — non-zero exit,
    timeout, unparsable JSON. Once a host *has* the binary, a crashed run, a
    broken rule table or a parser regression must not look identical to never
    having had it, or a safety net disappears silently.

:func:`classify_diff_result` reports that difference as a :class:`ClassifyResult`
(``status`` plus ``detail``). :func:`classify_diff` is the thin, older seam that
collapses both to ``None``; it is fine for callers that only ever *add* review
(panel gating), and wrong for callers where "no classification" would weaken a
gate — those use :func:`classify_diff_result` and fail closed on ``failed``.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = 60

#: Risk tiers, weakest first. Used for monotone comparisons.
RISK_ORDER = ("low", "medium", "high", "critical")

#: A classification was produced.
CLASSIFY_OK = "ok"
#: The binary is not installed on this host — degrade to the caller's own rules.
CLASSIFY_ABSENT = "absent"
#: There was nothing to classify (empty diff). Not a failure.
CLASSIFY_EMPTY = "empty"
#: The binary is installed but the invocation did not produce a classification.
#: Callers whose fallback is *weaker* gating must fail closed on this.
CLASSIFY_FAILED = "failed"


def _rank(risk: str) -> int:
    """Ordinal of a risk tier. Raises on an unrecognised tier — deliberately.

    This used to return 0 (the WEAKEST tier) for anything it did not
    recognise: "", None -> "none", a typo, a future tier this build predates.
    That turned every unknown into a confident "low", which is the exact shape
    of a gate that stops checking without saying so. An unknown tier is a
    failure to classify, and the caller must hear about it.
    """
    try:
        return RISK_ORDER.index((risk or "").lower())
    except ValueError as exc:
        raise ValueError(
            f"unrecognised risk tier {risk!r} (expected one of {list(RISK_ORDER)})"
        ) from exc


@dataclass(frozen=True)
class Classification:
    """What ``cmd/classify`` concluded about a diff."""

    risk: str = "low"
    components: tuple[str, ...] = field(default=())
    financial_paths_touched: bool = False
    client_only: bool = False
    server_surface: bool = False
    migration: bool = False
    human_pr_gate: bool = False
    recheck_min_severity: str = "high"
    panel_seats: int = 5
    panel_reduced: bool = False
    panel_reasons: tuple[str, ...] = field(default=())
    gate_signals: tuple[str, ...] = field(default=())
    unmatched_files: tuple[str, ...] = field(default=())
    risk_reasons: tuple[str, ...] = field(default=())

    @property
    def requires_full_panel(self) -> bool:
        """True when the diff's surface demands the multi-seat panel.

        This is ``cmd/classify``'s own conclusion: the panel is always required,
        and the only question is 5 seats or 1. A reduced panel means the change
        is confined to client presentation with no server/money/auth surface and
        no gate-signal hits in the changed lines.
        """
        return not self.panel_reduced

    @property
    def is_at_least(self) -> "callable":  # pragma: no cover - trivial
        return lambda tier: _rank(self.risk) >= _rank(tier)

    def summary_line(self) -> str:
        bits = [f"risk={self.risk}"]
        if self.components:
            bits.append("components=" + ",".join(self.components))
        if self.financial_paths_touched:
            bits.append("financial")
        if self.migration:
            bits.append("migration")
        if self.gate_signals:
            bits.append("gate-signals=" + ",".join(sorted(set(self.gate_signals))))
        if self.unmatched_files:
            bits.append(f"unclassified={len(self.unmatched_files)}")
        return " ".join(bits)

    def review_context(self) -> str:
        """A short block for the reviewer prompt.

        The panel currently receives no tier and no component context at all, so
        reviewers cannot know that a change sits on a path carrying hard 5/5
        dimension floors. This is that missing context.
        """
        lines = [
            f"**Risk tier (path-derived):** {self.risk}",
            f"**Components:** {', '.join(self.components) if self.components else '(none)'}",
        ]
        if self.components:
            lines.append(
                "These components carry hard per-dimension floors — treat "
                "Resilience, Idempotency, Performance and Observability findings "
                "on these paths as blocking, not advisory."
            )
        if self.financial_paths_touched:
            lines.append(
                "**This diff touches a financial path.** Money movement, "
                "settlement, refund or reversal logic is in scope."
            )
        if self.migration:
            lines.append("**This diff contains a schema migration.**")
        if self.gate_signals:
            lines.append(
                "**Gate/guard/flag signals in changed lines:** "
                + ", ".join(sorted(set(self.gate_signals)))
                + ". Check every one for fail-open behaviour in deployed environments."
            )
        if self.unmatched_files:
            lines.append(
                f"**{len(self.unmatched_files)} changed path(s) match no risk rule** "
                "and were treated as high risk by default. Judge them on their contents."
            )
        return "\n".join(lines)


@dataclass(frozen=True)
class ClassifyResult:
    """The outcome of a classification attempt — the answer *or* why there is none.

    ``status`` is one of :data:`CLASSIFY_OK`, :data:`CLASSIFY_ABSENT`,
    :data:`CLASSIFY_EMPTY`, :data:`CLASSIFY_FAILED`. ``detail`` is a short,
    journal-safe description of a non-ok status.

    The distinction that matters: :attr:`failed` means the binary was there and
    did not answer. A caller that would otherwise *relax* a gate must treat that
    as elevated risk, not as "no classification".
    """

    classification: Classification | None = None
    status: str = CLASSIFY_ABSENT
    detail: str | None = None

    @property
    def ok(self) -> bool:
        return self.classification is not None

    @property
    def failed(self) -> bool:
        return self.status == CLASSIFY_FAILED

    @property
    def absent(self) -> bool:
        return self.status == CLASSIFY_ABSENT


def _as_tuple(value) -> tuple[str, ...]:
    if not value:
        return ()
    if isinstance(value, str):
        return (value,)
    return tuple(str(v) for v in value)


def parse_classification(payload: dict) -> Classification:
    """Build a :class:`Classification` from ``cmd/classify -json`` output.

    STRICT BY DESIGN. This used to default a missing ``risk`` key to ``"low"``
    and, via :func:`_rank`, treat any unrecognised tier as the weakest one. The
    effect was that ``{}`` — well-formed, parseable, meaningless — produced a
    confident "low risk" verdict that sailed past the fail-closed guard, because
    the guard only fired when this function *raised*. Valid JSON that means
    nothing is not a classification.

    Raises ValueError on a payload that does not carry a usable risk tier. The
    caller turns that into CLASSIFY_FAILED, which fails closed.
    """
    if not isinstance(payload, dict):
        raise ValueError(f"classify output is {type(payload).__name__}, expected an object")
    if "risk" not in payload:
        raise ValueError(
            "classify output has no 'risk' key — this is not a classification, "
            "and defaulting it to 'low' would manufacture a passing verdict "
            "out of an absent one"
        )

    risk = str(payload["risk"]).lower()
    _rank(risk)  # raises on an unrecognised tier

    panel = payload.get("panel") or {}
    signals = payload.get("gate_signals") or []
    return Classification(
        risk=risk,
        components=_as_tuple(payload.get("components")),
        financial_paths_touched=bool(payload.get("financial_paths_touched")),
        client_only=bool(payload.get("client_only")),
        server_surface=bool(payload.get("server_surface")),
        migration=bool(payload.get("migration")),
        human_pr_gate=bool(payload.get("human_pr_gate")),
        recheck_min_severity=str(payload.get("recheck_min_severity", "high")),
        panel_seats=int(panel.get("seats", 5) or 5),
        panel_reduced=bool(panel.get("reduced")),
        panel_reasons=_as_tuple(panel.get("reasons")),
        gate_signals=tuple(
            str(s.get("signal", "")) for s in signals if isinstance(s, dict) and s.get("signal")
        ),
        unmatched_files=_as_tuple(payload.get("unmatched_files")),
        risk_reasons=_as_tuple(payload.get("risk_reasons")),
    )


def classify_binary() -> str | None:
    """Locate the ``classify`` binary, or return None if it is not installed."""
    override = os.environ.get("CLASSIFY_BIN")
    if override:
        return override if Path(override).is_file() else None

    found = shutil.which("classify")
    if found:
        return found

    home = os.environ.get("HOME", "")
    candidate = Path(home) / "Project/claude-workflow/cmd/classify/classify"
    return str(candidate) if candidate.is_file() else None


def classify_diff_result(
    *,
    diff: str,
    repo_root: str | Path | None = None,
    config: str | Path | None = None,
    binary: str | None = None,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> ClassifyResult:
    """Classify a diff, reporting *why* when there is no classification.

    ``-no-git`` is passed because the caller already knows its base and branch;
    this call is purely "what do these paths mean", not a repo-state check.

    Never raises: every failure mode is reported as
    ``ClassifyResult(status=CLASSIFY_FAILED, detail=...)``, which callers that
    would otherwise weaken a gate must treat as elevated.
    """
    if not diff or not diff.strip():
        return ClassifyResult(status=CLASSIFY_EMPTY, detail="empty diff")

    bin_path = binary or classify_binary()
    if not bin_path:
        log.debug("classify binary not found; skipping path-derived classification")
        return ClassifyResult(
            status=CLASSIFY_ABSENT, detail="classify binary not installed"
        )

    argv = [bin_path, "-json", "-no-git"]
    if repo_root:
        argv += ["-worktree", str(repo_root)]
    if config:
        argv += ["-config", str(config)]

    try:
        proc = subprocess.run(
            argv,
            input=diff,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        log.warning("classify invocation failed (%s)", exc)
        return ClassifyResult(
            status=CLASSIFY_FAILED,
            detail=f"classify invocation failed: {type(exc).__name__}: {exc}",
        )

    if proc.returncode != 0:
        stderr = (proc.stderr or "").strip()[:400]
        log.warning("classify exited %d. stderr: %s", proc.returncode, stderr)
        return ClassifyResult(
            status=CLASSIFY_FAILED,
            detail=f"classify exited {proc.returncode}: {stderr}",
        )

    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        log.warning("classify produced unparsable JSON (%s)", exc)
        return ClassifyResult(
            status=CLASSIFY_FAILED, detail=f"classify produced unparsable JSON: {exc}"
        )

    try:
        return ClassifyResult(
            classification=parse_classification(payload), status=CLASSIFY_OK
        )
    except (TypeError, ValueError, AttributeError) as exc:
        log.warning("classify output did not parse into a Classification (%s)", exc)
        return ClassifyResult(
            status=CLASSIFY_FAILED,
            detail=f"unusable classify output: {type(exc).__name__}: {exc}",
        )


def classify_diff(
    *,
    diff: str,
    repo_root: str | Path | None = None,
    config: str | Path | None = None,
    binary: str | None = None,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> Classification | None:
    """Classify a diff. Returns None when classification is unavailable.

    Collapses "absent" and "failed" into a single ``None`` — correct only for
    callers whose fallback is *no less* review than a classification could have
    demanded (panel gating). Anything that could self-approve on ``None`` must
    use :func:`classify_diff_result` instead and fail closed on ``.failed``.
    """
    return classify_diff_result(
        diff=diff,
        repo_root=repo_root,
        config=config,
        binary=binary,
        timeout_seconds=timeout_seconds,
    ).classification
