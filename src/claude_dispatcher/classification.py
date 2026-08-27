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
Two entry points, because callers differ in what a failure must mean:

* :func:`classify_diff_strict` — ``None`` only when the binary is genuinely
  ABSENT (or the diff is empty); a PRESENT binary that fails (non-zero exit,
  timeout, unparsable JSON, any exception) raises :class:`ClassificationError`.
  ``risk.classify`` uses this and fails closed on the error, because its
  ``low`` means auto-merge without human review.
* :func:`classify_diff` — the lenient wrapper: every failure collapses to
  ``None`` and callers fall back to metadata gating. Right for the panel
  callers, whose worst case on ``None`` is the review they already had.
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


def _rank(risk: str) -> int:
    try:
        return RISK_ORDER.index((risk or "").lower())
    except ValueError:
        return 0


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


def _as_tuple(value) -> tuple[str, ...]:
    if not value:
        return ()
    if isinstance(value, str):
        return (value,)
    return tuple(str(v) for v in value)


def parse_classification(payload: dict) -> Classification:
    """Build a :class:`Classification` from ``cmd/classify -json`` output."""
    panel = payload.get("panel") or {}
    signals = payload.get("gate_signals") or []
    return Classification(
        risk=str(payload.get("risk", "low")).lower(),
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


class ClassificationError(RuntimeError):
    """The ``classify`` binary is present but produced no usable classification.

    Distinct from the binary being absent (``None`` from
    :func:`classify_diff_strict`): a host that has the binary must not have a
    crash, a broken rule table or a parser regression look like never having
    had it. The message carries the reason for the journal.
    """


def classify_diff_strict(
    *,
    diff: str,
    repo_root: str | Path | None = None,
    config: str | Path | None = None,
    binary: str | None = None,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> Classification | None:
    """Classify a diff; ``None`` only for an absent binary or an empty diff.

    Any failure of a PRESENT binary raises :class:`ClassificationError`.
    ``-no-git`` is passed because the caller already knows its base and branch;
    this call is purely "what do these paths mean", not a repo-state check.
    """
    if not diff or not diff.strip():
        return None

    bin_path = binary or classify_binary()
    if not bin_path:
        log.debug("classify binary not found; skipping path-derived classification")
        return None

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
    except Exception as exc:  # OSError, TimeoutExpired, anything: all fail closed
        raise ClassificationError(
            f"classify invocation failed ({type(exc).__name__}: {exc})"
        ) from exc

    # Exit 3 is INVALID_INPUT — an unparsable diff or no rule table for the
    # project. Still a failure of a present binary: the caller decides.
    if proc.returncode != 0:
        raise ClassificationError(
            f"classify exited {proc.returncode}: "
            f"{(proc.stderr or '').strip()[:400] or '(no stderr)'}"
        )

    try:
        return parse_classification(json.loads(proc.stdout))
    except Exception as exc:  # JSONDecodeError, or a payload of the wrong shape
        raise ClassificationError(
            f"classify produced unusable output ({type(exc).__name__}: {exc})"
        ) from exc


def classify_diff(
    *,
    diff: str,
    repo_root: str | Path | None = None,
    config: str | Path | None = None,
    binary: str | None = None,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> Classification | None:
    """Classify a diff, or ``None`` when classification is unavailable for ANY
    reason — absent binary, failed invocation, bad output. Callers that must
    tell those apart use :func:`classify_diff_strict`.
    """
    try:
        return classify_diff_strict(
            diff=diff, repo_root=repo_root, config=config, binary=binary,
            timeout_seconds=timeout_seconds,
        )
    except ClassificationError as exc:
        log.warning("%s; falling back to metadata gating", exc)
        return None
