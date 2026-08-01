"""Deterministic risk classifier for the Phase 3 approval ladder.

The dispatcher's PR-flow approval ladder (Phase 3) lets a supervising agent
auto-approve only **low-risk** PRs; everything else falls to a reviewer bot or
to a human. "Low-risk" must be a *deterministic*, config-driven judgement — not
an LLM's vibe — so the same diff always lands in the same bucket and the rule
that disqualified it is named explicitly.

This module owns that judgement. :func:`classify` takes a task row, the task's
worktree, and a base ref, and returns a :class:`RiskVerdict` of ``low`` or
``elevated`` with the reasons. A verdict is ``low`` only when *every* low-risk
condition holds; any single violation flips it to ``elevated`` and the violated
rule is recorded in ``reasons``.

Defaults mirror the plan (``docs/improvement-plan.md`` Phase 3). A repo tunes
them via a ``risk:`` section in ``.dispatcher.yaml``; an absent section uses the
defaults wholesale and a partial section merges over them
(:func:`risk_config_from_mapping`).

Two carve-outs from the plan:

  * **docs-only** (``*.md``-only diffs) is low-risk at *any* size — a large
    documentation change should never need elevated review.
  * **test-only** diffs are deliberately *not* auto-low-risk: a test change can
    silently weaken assertions, so it goes through the normal rule set like any
    other diff (it may still come out low, but it is never short-circuited).

**Effective diff** is the counting rule shared with the Phase 7b mutation
escalation: insertions+deletions summed over only the files that are *not* test
or generated code (per the per-repo globs). Thorough tests or regenerated
protobuf output on an otherwise small change must not push it out of low-risk.
The exclusion is for *counting only* — excluded files still ship through the PR
and its gates like everything else.

The rule logic is split out as a pure function (:func:`evaluate`) that takes
already-collected inputs, with :func:`classify` as the thin adapter that reads
the task row and runs git. This keeps the rules unit-testable without a git
repo, and confines the subprocess work to one small, separately-tested place.

**Path evidence (GO-1).** This module answers a different question from
``cmd/classify``: binary low-vs-elevated for auto-merge, not the four-tier
review depth. It keeps its own rules — but it does not maintain its own idea of
which paths are dangerous. When a classification is available
(:mod:`claude_dispatcher.classification`), a ``high``/``critical`` tier, a
touched financial path, or any gate-signal hit forces ``elevated``, OR'd over
the rule verdict. That is one-directional by contract — the same contract
``classification`` states for panel gating: **path evidence may only ever raise
to elevated, never lower to low.**

**Failing closed.** ``low`` here means *auto-merge without human review*, so the
two ways a classification can go missing are not interchangeable:

  * the ``classify`` binary is **absent** — expected on a host without
    claude-workflow installed. The verdict is exactly what the rules alone
    produced, and the journal records that there was no table.
  * the binary is **present but the invocation failed** — non-zero exit,
    timeout, unparsable JSON, an unreadable diff. That is ``elevated``, with the
    failure named in the reasons. A crashed binary or a broken rule table must
    never be indistinguishable from never having had one, or a change
    self-approves on the strength of a bug. This mirrors the existing
    :class:`RiskDiffError` branch: if we cannot measure it, we cannot call it
    low.
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass, field, replace
from functools import lru_cache
from pathlib import Path
from typing import Any, Sequence

from ruamel.yaml.error import YAMLError

from claude_dispatcher import classification as classification_mod
from claude_dispatcher import yaml_io

CONFIG_FILENAME = ".dispatcher.yaml"

# Verdict levels. Strings (not an enum) to match the rest of the codebase,
# where statuses and outcomes travel as plain strings through the journal/YAML.
LOW = "low"
ELEVATED = "elevated"

# Size ordering for the max_size threshold. Mirrors the size: label vocabulary
# validated in plan.py (size:(XS|S|M|L|XL)).
_SIZE_ORDER = {"XS": 0, "S": 1, "M": 2, "L": 3, "XL": 4}


class RiskConfigError(ValueError):
    """Raised when a ``risk:`` section exists but is malformed or invalid.

    The message includes the offending value so the failure is diagnosable from
    the journal alone, matching ``repo_config.RepoConfigError``'s contract.
    """


class RiskDiffError(RuntimeError):
    """Raised when the effective diff cannot be computed from git.

    :func:`classify` catches this and returns an ``elevated`` verdict — if we
    cannot measure the diff we cannot prove it is low-risk, so we fail closed.
    """


@dataclass(frozen=True)
class RiskConfig:
    """Tunable thresholds for the low-risk classifier.

    Every collection field is a tuple so the config is hashable and safe to
    share. ``max_size`` is one of the :data:`_SIZE_ORDER` keys; the loader
    guarantees that, so the classifier can index it without re-checking.
    """

    max_size: str = "S"
    forbidden_labels: tuple[str, ...] = ("security", "critical", "financial")
    forbidden_paths: tuple[str, ...] = (
        "**/migrations/**",
        "**/*.proto",
        "**/auth/**",
        ".github/**",
        "go.mod",
        "go.sum",
        "pyproject.toml",
        "Dockerfile*",
        "compose*.y*ml",
    )
    max_effective_diff_lines: int = 200
    test_globs: tuple[str, ...] = (
        "*_test.go",
        "**/testdata/**",
        "tests/**",
        "*.spec.*",
    )
    generated_globs: tuple[str, ...] = ("*.pb.go", "**/sqlc/**", "*_pb2.py")
    docs_only_low_risk: bool = True


# The defaults that apply when a repo has no ``risk:`` section at all. Mirrors
# the plan's proposed defaults verbatim.
DEFAULT_RISK_CONFIG = RiskConfig()


@dataclass(frozen=True)
class RiskVerdict:
    """The classifier's answer: a level and the reasons behind it.

    For an ``elevated`` verdict, ``reasons`` names every violated rule (the
    classifier collects all of them rather than stopping at the first, so a
    caller — and a human reading the journal — sees the full picture). For a
    ``low`` verdict, ``reasons`` is empty except for the docs-only carve-out,
    which records why size was bypassed.

    ``classification_summary`` is ``cmd/classify``'s ``summary_line()`` when a
    path classification was obtained, ``"unavailable: <detail>"`` when the binary
    was present but failed to produce one, and None when there was no binary at
    all. It is recorded even when the classification changed nothing, so the
    journal distinguishes "the table said low" from "the table broke" from
    "there was no table".
    """

    level: str
    reasons: tuple[str, ...] = field(default=())
    classification_summary: str | None = None

    @property
    def is_low(self) -> bool:
        return self.level == LOW


@dataclass(frozen=True)
class FileDiff:
    """One file's contribution to a diff: its path and line churn.

    ``insertions``/``deletions`` are 0 for a binary file (git reports ``-`` for
    those, which is not a line count).
    """

    path: str
    insertions: int
    deletions: int


# --------------------------------------------------------------------------- #
# Glob matching
# --------------------------------------------------------------------------- #
#
# The forbidden/test/generated patterns use gitignore-style ``**`` semantics,
# which neither fnmatch nor PurePath.match handle the way the plan intends
# (fnmatch's ``*`` crosses ``/`` but a leading ``**/`` will not match *zero*
# leading directories). We translate each pattern to an anchored regex once:
#
#   ``**/``  -> ``(?:.*/)?``   (zero or more leading path segments)
#   ``**``   -> ``.*``         (any run, crossing ``/``)
#   ``*``    -> ``.*``         (fnmatch-style — crosses ``/`` on purpose, so a
#                               bare ``*_test.go`` matches at any depth)
#   ``?``    -> ``.``
#
# This gives the intuitively-correct result for every pattern in the defaults:
# ``**/migrations/**`` matches both ``migrations/x`` and ``a/b/migrations/x``;
# root anchors like ``go.mod`` / ``Dockerfile*`` match only at the root.


def _glob_to_regex(pattern: str) -> str:
    out: list[str] = []
    i, n = 0, len(pattern)
    while i < n:
        c = pattern[i]
        if c == "*":
            if i + 1 < n and pattern[i + 1] == "*":
                if i + 2 < n and pattern[i + 2] == "/":
                    out.append("(?:.*/)?")  # **/ — zero or more segments
                    i += 3
                    continue
                out.append(".*")  # trailing/standalone **
                i += 2
                continue
            out.append(".*")  # single * (crosses / by design)
            i += 1
            continue
        if c == "?":
            out.append(".")
            i += 1
            continue
        out.append(re.escape(c))
        i += 1
    return "".join(out)


@lru_cache(maxsize=512)
def _compiled(pattern: str) -> re.Pattern[str]:
    return re.compile(_glob_to_regex(pattern) + r"\Z")


def matches_any_glob(path: str, patterns: Sequence[str]) -> bool:
    """True if ``path`` matches any of the gitignore-style ``patterns``.

    ``path`` is expected in posix form (forward slashes), which is what git
    emits. Matching is anchored (full-path), so ``go.mod`` matches only the
    root manifest, never ``vendor/go.mod``.
    """
    return any(_compiled(p).match(path) for p in patterns)


def _first_matching_glob(path: str, patterns: Sequence[str]) -> str | None:
    """The first pattern in ``patterns`` that matches ``path``, else None."""
    for p in patterns:
        if _compiled(p).match(path):
            return p
    return None


def _is_doc(path: str) -> bool:
    """True for a Markdown file — the docs-only carve-out's membership test."""
    return path.lower().endswith(".md")


# --------------------------------------------------------------------------- #
# Effective diff
# --------------------------------------------------------------------------- #


def effective_diff_lines(
    changed_files: Sequence[FileDiff], config: RiskConfig
) -> int:
    """Sum insertions+deletions over files that are neither test nor generated.

    This is the shared counting rule: test code (``test_globs``) and generated
    code (``generated_globs``) are excluded from the line count, so thorough
    tests or regenerated output on a small change cannot inflate it out of
    low-risk. Excluded files are dropped from the *count* only.
    """
    total = 0
    for f in changed_files:
        if matches_any_glob(f.path, config.test_globs) or matches_any_glob(
            f.path, config.generated_globs
        ):
            continue
        total += f.insertions + f.deletions
    return total


# --------------------------------------------------------------------------- #
# Rule evaluation (pure)
# --------------------------------------------------------------------------- #


def evaluate(
    *,
    size_label: str | None,
    labels: Sequence[str],
    changed_files: Sequence[FileDiff],
    verified: Any,
    verification_iterations: Any,
    config: RiskConfig = DEFAULT_RISK_CONFIG,
    classification: classification_mod.Classification
    | classification_mod.ClassifyResult
    | None = None,
) -> RiskVerdict:
    """Apply the low-risk rule set to already-collected inputs.

    ALL conditions must hold for a ``low`` verdict; each independent violation
    appends a reason. The docs-only carve-out short-circuits to ``low`` ahead of
    every other rule (it is low-risk "at any size", which in practice means it
    also bypasses the effective-diff threshold, since ``*.md`` files count
    toward that diff).

    ``verified`` / ``verification_iterations`` are read raw from the task row
    (the fields VG-4 writes); first-pass verification requires ``verified`` to
    be exactly ``True`` and the iteration count to be exactly ``0``.

    ``classification`` is optional path evidence from ``cmd/classify``: a
    :class:`~claude_dispatcher.classification.Classification`, a
    :class:`~claude_dispatcher.classification.ClassifyResult` (which also carries
    *why* there is no classification), or ``None``. It is applied *after* the
    rules and only ever raises the verdict (:func:`_apply_classification`).
    ``None`` means "no path evidence, and no claim about why" and leaves the rule
    verdict untouched — a ``ClassifyResult`` whose status is ``failed`` does not.
    """
    return _apply_classification(
        _evaluate_rules(
            size_label=size_label,
            labels=labels,
            changed_files=changed_files,
            verified=verified,
            verification_iterations=verification_iterations,
            config=config,
        ),
        classification,
    )


def _evaluate_rules(
    *,
    size_label: str | None,
    labels: Sequence[str],
    changed_files: Sequence[FileDiff],
    verified: Any,
    verification_iterations: Any,
    config: RiskConfig,
) -> RiskVerdict:
    """The size/label/path/diff/verification rule set, with no path evidence."""
    files = list(changed_files)

    # docs-only: *.md-only diffs are low-risk at any size. Requires at least one
    # file — an empty diff is not a documentation change. This short-circuit is
    # deliberately ahead of every other rule, including forbidden_paths: the plan
    # says docs are "always low-risk", so a Markdown file under a denylisted tree
    # (e.g. .github/SECURITY.md, internal/auth/THREAT_MODEL.md) still classifies
    # low — the path denylist guards code/config in those trees, not prose.
    if config.docs_only_low_risk and files and all(_is_doc(f.path) for f in files):
        return RiskVerdict(LOW, ("docs-only (*.md) change — low-risk at any size",))

    reasons: list[str] = []

    # Size threshold.
    if size_label is None or size_label not in _SIZE_ORDER:
        reasons.append(f"size label missing or unrecognised: {size_label!r}")
    elif _SIZE_ORDER[size_label] > _SIZE_ORDER[config.max_size]:
        reasons.append(f"size {size_label} exceeds max_size {config.max_size}")

    # Forbidden labels — exact label-string match.
    for lbl in labels:
        if lbl in config.forbidden_labels:
            reasons.append(f"forbidden label: {lbl}")

    # Forbidden paths — any touched path disqualifies (test/generated exclusion
    # does NOT apply here; a forbidden path is forbidden regardless of kind).
    for f in files:
        pat = _first_matching_glob(f.path, config.forbidden_paths)
        if pat is not None:
            reasons.append(f"forbidden path touched: {f.path} (matches {pat})")

    # Effective diff size.
    effective = effective_diff_lines(files, config)
    if effective > config.max_effective_diff_lines:
        reasons.append(
            f"effective diff {effective} lines exceeds max_effective_diff_lines "
            f"{config.max_effective_diff_lines}"
        )

    # First-pass verification (VG-4): verified, with zero iterations.
    if verified is not True or verification_iterations != 0:
        reasons.append(
            "first-pass verification not satisfied "
            f"(verified={verified!r}, verification_iterations="
            f"{verification_iterations!r})"
        )

    return RiskVerdict(ELEVATED, tuple(reasons)) if reasons else RiskVerdict(LOW, ())


# --------------------------------------------------------------------------- #
# Path evidence (GO-1)
# --------------------------------------------------------------------------- #
#
# ``cmd/classify`` already computes, from the project's own rule table, which
# paths carry risk — the tier, whether money moves, and whether the changed
# lines touch a gate/guard/flag. Rather than grow a second denylist here, this
# module consumes that answer. The three signals below are the ones that bear on
# "may the dispatcher self-approve this PR": a high/critical surface, money, or
# a gate whose fail-open mode nobody has looked at.


def _classification_reasons(
    cls: classification_mod.Classification,
) -> tuple[str, ...]:
    """The path-evidence reasons that force ``elevated``, if any."""
    reasons: list[str] = []
    if cls.is_at_least("high"):
        reasons.append(f"path-derived risk tier {cls.risk} (cmd/classify)")
    if cls.financial_paths_touched:
        reasons.append("path-derived: financial path touched (cmd/classify)")
    if cls.gate_signals:
        reasons.append(
            "path-derived: gate/guard/flag signals in changed lines: "
            + ", ".join(sorted(set(cls.gate_signals)))
        )
    return tuple(reasons)


def _as_classify_result(
    value: classification_mod.Classification
    | classification_mod.ClassifyResult
    | None,
) -> classification_mod.ClassifyResult:
    """Normalise ``evaluate``'s ``classification=`` input to a ClassifyResult.

    A bare ``Classification`` is an answer; a bare ``None`` is "no evidence, no
    claim about why" — deliberately the *absent* status, so the long-standing
    ``classification=None`` contract (verdict unchanged) is preserved. Only a
    caller that explicitly passes a ``failed`` ClassifyResult gets the
    fail-closed branch.
    """
    if value is None:
        return classification_mod.ClassifyResult(
            status=classification_mod.CLASSIFY_ABSENT
        )
    if isinstance(value, classification_mod.ClassifyResult):
        return value
    return classification_mod.ClassifyResult(
        classification=value, status=classification_mod.CLASSIFY_OK
    )


def _apply_classification(
    verdict: RiskVerdict,
    cls: classification_mod.Classification
    | classification_mod.ClassifyResult
    | None,
) -> RiskVerdict:
    """OR path evidence over a rule verdict — one-directional, raise only.

    A classification that names no risky signal never downgrades an ``elevated``
    verdict and never clears a reason; it only records its summary line. An
    *absent* binary (or a bare ``None``) returns the rule verdict unchanged, so a
    host without ``classify`` behaves exactly as it did before.

    A binary that was present and **failed** raises to ``elevated`` instead: on
    this seam ``low`` means auto-merge, so degrading to the weaker rule set on a
    crash, a broken rule table or a parser regression would let a change
    self-approve on the strength of a bug.

    The docs-only carve-out is *not* exempt: it is a statement about size ("a
    large documentation change should never need elevated review"), not about
    surface, and path evidence outranks it in the raising direction. Its reason
    is kept alongside the path reasons so the journal shows both halves.
    """
    result = _as_classify_result(cls)

    if result.failed:
        detail = (result.detail or "classify produced no classification")[:300]
        return RiskVerdict(
            ELEVATED,
            verdict.reasons + (f"path classification failed: {detail}",),
            classification_summary=f"unavailable: {detail}",
        )

    if result.classification is None:
        return verdict

    reasons = _classification_reasons(result.classification)
    summary = result.classification.summary_line()
    if not reasons:
        return replace(verdict, classification_summary=summary)
    return RiskVerdict(
        ELEVATED, verdict.reasons + reasons, classification_summary=summary
    )


# --------------------------------------------------------------------------- #
# Git plumbing
# --------------------------------------------------------------------------- #


def _git_diff(
    worktree: Path, args: Sequence[str], base_ref: str, head_ref: str
) -> str:
    """``git diff <args> base...head`` in ``worktree``, two-dot on failure.

    Shared by the numstat count (:func:`collect_diff`) and the raw unified diff
    fed to ``cmd/classify`` (:func:`collect_raw_diff`) so both use the same
    range semantics and the same failure mode: :class:`RiskDiffError`.
    """

    def _run(spec: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", "diff", *args, spec],
            cwd=str(worktree),
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
        )

    try:
        proc = _run(f"{base_ref}...{head_ref}")
        if proc.returncode != 0:
            proc = _run(f"{base_ref}..{head_ref}")
    except OSError as exc:
        raise RiskDiffError(f"git diff failed to launch in {worktree}: {exc}") from exc
    if proc.returncode != 0:
        raise RiskDiffError(
            f"git diff {base_ref!r}...{head_ref!r} in {worktree} failed: "
            f"{(proc.stderr or '').strip()}"
        )
    return proc.stdout


def resolve_ref(worktree: str | Path, ref: str) -> str:
    """The commit SHA ``ref`` names right now, in ``worktree``.

    The verdict reads the diff twice — numstat for the size/path rules, the
    unified diff for ``cmd/classify`` — and both run against refs that a
    concurrent push or checkout can move between the two calls. That would let
    the size rules describe one commit while the path evidence describes another,
    which is precisely the kind of split-brain the classifier exists to prevent.
    :func:`classify` resolves each ref to a SHA once and reads only those.

    Raises :class:`RiskDiffError` if the ref does not resolve — the same
    fail-closed path as an unreadable diff.
    """
    argv = ["git", "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"]
    try:
        proc = subprocess.run(
            argv,
            cwd=str(worktree),
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RiskDiffError(
            f"git rev-parse failed to launch in {worktree}: {exc}"
        ) from exc
    sha = (proc.stdout or "").strip()
    if proc.returncode != 0 or not sha:
        raise RiskDiffError(
            f"could not resolve ref {ref!r} in {worktree}: "
            f"{(proc.stderr or '').strip() or 'no such commit'}"
        )
    return sha


def collect_raw_diff(
    worktree: str | Path, base_ref: str, head_ref: str = "HEAD"
) -> str:
    """The unified diff of ``base_ref...head_ref`` — ``cmd/classify``'s input.

    Untruncated on purpose: classification is a per-path question, and a
    truncated diff would silently drop paths and therefore drop evidence.
    """
    return _git_diff(Path(worktree), ("--no-renames",), base_ref, head_ref)


def path_classification(
    worktree: str | Path, base_ref: str, head_ref: str = "HEAD"
) -> classification_mod.ClassifyResult:
    """Classify the diff's paths via ``cmd/classify``.

    Never raises: every outcome is a :class:`~claude_dispatcher.classification.
    ClassifyResult`, and the caller decides what a non-answer means. The binary
    lookup happens first so a host without ``classify`` installed does not pay
    for the extra diff — and so an absent binary is distinguishable from a
    present one that failed.

    Once the binary *is* present, a git failure counts as a failure too: we were
    supposed to get path evidence for this diff and we did not.
    """
    if classification_mod.classify_binary() is None:
        return classification_mod.ClassifyResult(
            status=classification_mod.CLASSIFY_ABSENT,
            detail="classify binary not installed",
        )
    try:
        diff = collect_raw_diff(worktree, base_ref, head_ref)
    except (RiskDiffError, subprocess.SubprocessError, OSError) as exc:
        return classification_mod.ClassifyResult(
            status=classification_mod.CLASSIFY_FAILED,
            detail=f"could not read the diff to classify: {exc}",
        )
    try:
        return classification_mod.classify_diff_result(diff=diff, repo_root=worktree)
    except Exception as exc:  # classify_diff_result degrades, but never trust that
        return classification_mod.ClassifyResult(
            status=classification_mod.CLASSIFY_FAILED,
            detail=f"classify raised {type(exc).__name__}: {exc}",
        )


def collect_diff(
    worktree: str | Path, base_ref: str, head_ref: str = "HEAD"
) -> list[FileDiff]:
    """Per-file line churn of ``base_ref...head_ref`` run from ``worktree``.

    Uses ``git diff --numstat --no-renames``: ``--no-renames`` keeps each line a
    clean ``ins<TAB>del<TAB>path`` (a rename is reported as a delete plus an add
    with full paths), so parsing never has to decode git's ``{old => new}``
    rename syntax. The three-dot range (changes on the branch since its
    merge-base) falls back to two-dot if the refs share no merge-base, mirroring
    ``cross_family_reviewer``. Binary files (``-`` counts) contribute 0 lines.

    ``head_ref`` defaults to ``HEAD`` (the worktree's checked-out tip — the
    PRF-3 in-worktree path). The PRF-4 merge engine passes an explicit branch
    ref so it can classify a task's PR branch from the repo root, where no
    worktree is checked out on it.
    """
    stdout = _git_diff(
        Path(worktree), ("--numstat", "--no-renames"), base_ref, head_ref
    )

    files: list[FileDiff] = []
    for line in stdout.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        ins_s, del_s = parts[0], parts[1]
        path = "\t".join(parts[2:])  # paths with tabs are rare but possible
        ins = 0 if ins_s == "-" else int(ins_s)
        dels = 0 if del_s == "-" else int(del_s)
        files.append(FileDiff(path=path, insertions=ins, deletions=dels))
    return files


def classify(
    task_row: Any,
    worktree: str | Path,
    base_ref: str,
    *,
    head_ref: str = "HEAD",
    config: RiskConfig | None = None,
) -> RiskVerdict:
    """Classify a task's PR as ``low`` or ``elevated`` risk.

    ``task_row`` is the task's YAML mapping (a ruamel CommentedMap or plain
    dict) — the size is read from its ``size:`` label and first-pass
    verification from its ``verified`` / ``verification_iterations`` fields.
    The effective diff is measured from ``base_ref...head_ref`` run in
    ``worktree``.

    ``head_ref`` defaults to ``HEAD``. The PRF-4 merge engine passes the task's
    PR branch and ``worktree=repo_root`` so it can classify from the repo even
    when no worktree is checked out on the branch (e.g. the standalone
    ``merge-prs`` command on a finished run).

    ``config`` defaults to the repo's ``risk:`` section loaded from
    ``worktree`` (or the built-in defaults when absent). A caller that has
    already loaded the config can pass it to skip the re-read. If the diff
    cannot be computed we fail closed with an ``elevated`` verdict — we cannot
    prove low-risk without measuring the change.

    Path evidence from ``cmd/classify`` is folded in when available
    (:func:`path_classification`). With no binary installed the verdict is
    exactly the rule set's; with a binary that failed, it is ``elevated`` — see
    the module docstring on failing closed.

    Both diff reads run against SHAs resolved once up front, so a branch that
    moves mid-verdict cannot have the rules judging one commit and the path
    evidence another.
    """
    cfg = config if config is not None else load_risk_config(worktree)

    labels = [str(lbl) for lbl in (_row_get(task_row, "labels") or [])]
    size_label = _size_from_labels(labels)
    verified = _row_get(task_row, "verified")
    verification_iterations = _row_get(task_row, "verification_iterations")

    # Pin both ends to SHAs before reading anything, so the numstat the rules
    # count and the unified diff cmd/classify sees describe the SAME commits even
    # if the branch moves underneath us mid-verdict.
    try:
        base_sha = resolve_ref(worktree, base_ref)
        head_sha = resolve_ref(worktree, head_ref)
        changed_files = collect_diff(worktree, base_sha, head_sha)
    except RiskDiffError as exc:
        return RiskVerdict(ELEVATED, (f"could not compute effective diff: {exc}",))

    return evaluate(
        size_label=size_label,
        labels=labels,
        changed_files=changed_files,
        verified=verified,
        verification_iterations=verification_iterations,
        config=cfg,
        classification=path_classification(worktree, base_sha, head_sha),
    )


def _row_get(task_row: Any, key: str) -> Any:
    """Read ``key`` from a task row, tolerating a non-mapping row."""
    try:
        return task_row.get(key)
    except AttributeError:
        return None


def _size_from_labels(labels: Sequence[str]) -> str | None:
    """The size value from a ``size:`` label, or None if absent."""
    for lbl in labels:
        if lbl.startswith("size:"):
            return lbl.split(":", 1)[1]
    return None


# --------------------------------------------------------------------------- #
# Config loading
# --------------------------------------------------------------------------- #


def load_risk_config(repo_root: str | Path) -> RiskConfig:
    """Load the ``risk:`` section from ``<repo_root>/.dispatcher.yaml``.

    Absent file, empty file, or no ``risk:`` key → the built-in defaults. A
    present section merges over the defaults (:func:`risk_config_from_mapping`).
    """
    path = Path(repo_root) / CONFIG_FILENAME
    if not path.exists():
        return DEFAULT_RISK_CONFIG
    try:
        doc = yaml_io.load(path)
    except YAMLError as exc:
        raise RiskConfigError(f"malformed YAML in {path}: {exc}") from exc
    if not isinstance(doc, dict):
        return DEFAULT_RISK_CONFIG
    return risk_config_from_mapping(doc.get("risk"))


def risk_config_from_mapping(section: Any) -> RiskConfig:
    """Merge a parsed ``risk:`` mapping over the defaults.

    ``None`` (key absent) → defaults wholesale. A present section overrides only
    the keys it names; unknown keys are tolerated and ignored (same forward-compat
    stance as ``repo_config``). Wrong types raise :class:`RiskConfigError` rather
    than silently degrading a safety threshold.
    """
    if section is None:
        return DEFAULT_RISK_CONFIG
    if not isinstance(section, dict):
        raise RiskConfigError(
            f"'risk' must be a mapping, got {type(section).__name__}"
        )

    d = DEFAULT_RISK_CONFIG

    max_size = d.max_size
    if "max_size" in section:
        max_size = section["max_size"]
        if not isinstance(max_size, str) or max_size not in _SIZE_ORDER:
            raise RiskConfigError(
                f"'risk.max_size' must be one of {sorted(_SIZE_ORDER)}, "
                f"got {max_size!r}"
            )

    max_lines = d.max_effective_diff_lines
    if "max_effective_diff_lines" in section:
        max_lines = section["max_effective_diff_lines"]
        # bool is an int subclass; reject it so `true` can't pose as a count.
        if isinstance(max_lines, bool) or not isinstance(max_lines, int) or max_lines < 0:
            raise RiskConfigError(
                f"'risk.max_effective_diff_lines' must be a non-negative integer, "
                f"got {max_lines!r}"
            )

    docs_only = d.docs_only_low_risk
    if "docs_only_low_risk" in section:
        docs_only = section["docs_only_low_risk"]
        if not isinstance(docs_only, bool):
            raise RiskConfigError(
                f"'risk.docs_only_low_risk' must be a boolean, got {docs_only!r}"
            )

    return RiskConfig(
        max_size=max_size,
        forbidden_labels=_str_tuple(section, "forbidden_labels", d.forbidden_labels),
        forbidden_paths=_str_tuple(section, "forbidden_paths", d.forbidden_paths),
        max_effective_diff_lines=max_lines,
        test_globs=_str_tuple(section, "test_globs", d.test_globs),
        generated_globs=_str_tuple(section, "generated_globs", d.generated_globs),
        docs_only_low_risk=docs_only,
    )


def _str_tuple(
    section: dict[str, Any], key: str, default: tuple[str, ...]
) -> tuple[str, ...]:
    """Read ``key`` as a list of non-empty strings, or fall back to ``default``.

    A present value must be a list whose entries are all non-empty strings (the
    same strictness ``repo_config`` applies to ``panel.advisory``) — anything
    else raises rather than silently dropping a path from a safety denylist.
    """
    if key not in section:
        return default
    value = section[key]
    if not isinstance(value, list):
        raise RiskConfigError(
            f"'risk.{key}' must be a list of strings, got {value!r}"
        )
    for entry in value:
        # bool is not a str subclass, so a bare `true` entry is rejected here.
        if not isinstance(entry, str) or not entry.strip():
            raise RiskConfigError(
                f"entries of 'risk.{key}' must be non-empty strings, got {entry!r}"
            )
    return tuple(value)
