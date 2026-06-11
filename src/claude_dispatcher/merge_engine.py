"""Mechanical merge engine for PR-flow mode (PRF-4).

In ``pr`` integration mode the dispatcher — not a human — owns merging. After
each task reaches ``Awaiting Review`` (its PR is open against the run's feature
branch), and again standalone via ``dispatcher merge-prs <run-id>`` for a
post-run / next-morning catch-up, a *merge pass* runs:

    For each Awaiting Review row, in topological (blockedBy) order, merge its
    PR into the feature branch when BOTH:
      (a) it is **approved per the ladder** —
            * risk ``low`` (PRF-3 classifier) → the dispatcher self-approves,
              recording ``pr_approved_by: dispatcher-agent`` + the verdict;
            * risk ``elevated`` → an external GitHub approval is required
              (``gh pr view <n> --json reviews``); until present the row stays
              Awaiting Review and a notification fires ONCE per task (not per
              pass).
      (b) **every blockedBy row is already Merged** — the topological gate, so
          a PR always merges on top of merged dependency code.

    Merge is ``gh pr merge --merge``. Success → the row moves to ``Merged`` and
    a ``pr_merged`` event is journaled (merger identity + feature-branch sha).
    A conflict / unmergeable PR leaves the row Awaiting Review with
    ``needs_rebase: true`` + a ``pr_merge_failed`` event + a one-shot
    notification; the engine does NOT auto-rebase (a deliberate non-goal — the
    supervising agent handles rebases) and CONTINUES with the other eligible
    PRs.

Topological ordering is enforced in code via :func:`plan.mergeable_now` (the
MERGE-ordering building block PRF-2 shipped): a row is a merge candidate only
when its own status is Awaiting Review AND every dependency is already Merged.
After each successful merge the candidate set is recomputed, so a dependency
that merges this pass unblocks its dependent within the same pass — but a
dependent can never merge before its dependency, even when it was approved
first.

This module is pure orchestration over four separately-tested pieces:
:func:`plan.mergeable_now` (ordering), :func:`risk.classify` (the ladder's
low/elevated split), :func:`pr.pr_review_state` / :func:`pr.merge_pr` (the gh
side effects), and :class:`journal.Journal` / :class:`notify.Notifier` (audit +
attention). It performs NO local-mutating git on the repo — the only writes are
to the tasks YAML (under the file lock) — so it is safe to run on the main
thread while worker threads create worktrees off the same repo.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from . import journal as journal_mod
from . import notify as notify_mod
from . import plan as plan_mod
from . import pr as pr_mod
from . import risk as risk_mod
from . import yaml_io


# The dispatcher's identity, recorded as approver (for self-approved low-risk
# PRs) and as merger (for every merge) in the journal + YAML.
DISPATCHER_APPROVER = "dispatcher-agent"


@dataclass
class MergeEngineConfig:
    """Everything the merge pass needs, independent of ``orchestrator.RunConfig``.

    Built once by the orchestrator (per run) and by the standalone ``merge-prs``
    command (reconstructed from the genesis ``run_config``), so the engine has a
    single, small contract that both entry points satisfy.
    """

    tasks_path: Path
    repo_root: Path
    # The PR base — the run's feature branch (``orchestrator``'s repointed
    # ``base_branch`` in pr mode). PRs merge INTO this; risk diffs are measured
    # against it.
    feature_branch: str
    gh_bin: str = "gh"
    # Pre-loaded repo risk config; None → loaded from repo_root on first use.
    risk_config: risk_mod.RiskConfig | None = None
    lock_timeout_seconds: float = 30.0
    run_id: str = ""


@dataclass
class MergePassState:
    """Cross-pass dedupe state for the once-per-task notifications.

    The orchestrator constructs ONE of these per run and threads it through
    every merge pass, so an elevated PR that stays unapproved across many passes
    (or a conflicting PR re-seen each pass) notifies the human exactly once. The
    standalone command builds a fresh one — a single invocation is one logical
    "pass set" anyway.
    """

    approval_notified: set[str] = field(default_factory=set)
    rebase_notified: set[str] = field(default_factory=set)


@dataclass
class MergePassResult:
    """What one ``merge_pass`` call did, for logging / the command's stdout."""

    merged: list[str] = field(default_factory=list)
    awaiting_approval: list[str] = field(default_factory=list)
    needs_rebase: list[str] = field(default_factory=list)
    # Awaiting Review rows that had no usable PR number/branch to act on.
    unactionable: list[str] = field(default_factory=list)


def merge_pass(
    cfg: MergeEngineConfig,
    *,
    journal: journal_mod.Journal | None = None,
    notifier: notify_mod.Notifier | None = None,
    log: Callable[[str], None] | None = None,
    state: MergePassState | None = None,
) -> MergePassResult:
    """Run one merge pass: merge every currently-eligible PR, cascading.

    Loops over the recomputed mergeable set until no further merge lands, so a
    dependency that merges unblocks its dependent within the same call. Rows
    that are mergeable-by-ordering but NOT approved (elevated, no external
    approval) or that hit a conflict are recorded once and skipped for the rest
    of this call — they do not spin the loop. Never raises: every git/gh/journal
    failure is contained and surfaced, so a single bad PR can't abort the pass.
    """
    state = state if state is not None else MergePassState()
    logf = log or (lambda _m: None)
    risk_cfg = cfg.risk_config or risk_mod.load_risk_config(cfg.repo_root)
    result = MergePassResult()

    # Keys decided "no merge this call" (unapproved / conflict / unactionable),
    # so they aren't re-evaluated each loop iteration. A merged key leaves the
    # mergeable set on its own (status flips to Merged).
    skip: set[str] = set()

    while True:
        tasks = _load_tasks(cfg)
        # Exclude rows already given up THIS invocation (per-call `skip`) and
        # rows that hit a conflict/error in an EARLIER pass of the same run
        # (state.rebase_notified). The latter won't merge without an out-of-band
        # rebase, which never happens mid-run — so re-attempting it every pass
        # would only re-call gh and re-emit events. A fresh state (the standalone
        # `merge-prs` catch-up) has an empty rebase set, so it DOES retry, which
        # is exactly when a rebase may have landed. Approval-pending rows are
        # deliberately NOT excluded — the human/bot may approve between passes.
        candidates = [
            t for t in plan_mod.mergeable_now(tasks)
            if t.key not in skip and t.key not in state.rebase_notified
        ]
        if not candidates:
            break

        progressed = False
        for task in candidates:
            outcome = _consider_one(
                cfg, task, risk_cfg,
                journal=journal, notifier=notifier, log=logf, state=state,
            )
            if outcome == "merged":
                result.merged.append(task.key)
                progressed = True
            else:
                skip.add(task.key)
                if outcome == "awaiting-approval":
                    result.awaiting_approval.append(task.key)
                elif outcome == "needs-rebase":
                    result.needs_rebase.append(task.key)
                elif outcome == "unactionable":
                    result.unactionable.append(task.key)

        if not progressed:
            break

    return result


def _consider_one(
    cfg: MergeEngineConfig,
    task: plan_mod.Task,
    risk_cfg: risk_mod.RiskConfig,
    *,
    journal: journal_mod.Journal | None,
    notifier: notify_mod.Notifier | None,
    log: Callable[[str], None],
    state: MergePassState,
) -> str:
    """Apply the approval ladder to one mergeable task and, if cleared, merge.

    Returns one of ``"merged"``, ``"awaiting-approval"``, ``"needs-rebase"``,
    or ``"unactionable"``. The dependency gate (b) is already satisfied — the
    caller only passes rows from :func:`plan.mergeable_now`.
    """
    row = task.raw
    number = row.get("pr_number")
    branch = row.get("branch")
    pr_url = _str_or_none(row.get("pr_url"))
    summary = str(row.get("summary") or "")

    # number must be a usable PR id. None/blank/non-integer (e.g. a hand-edited
    # YAML for the standalone command) is unactionable rather than a crash —
    # one bad row must never abort the whole pass.
    try:
        number = int(number) if number is not None else None
    except (TypeError, ValueError):
        number = None
    if number is None or not branch:
        log(f"  merge: {task.key} Awaiting Review but has no usable "
            f"pr_number/branch — cannot merge (left as-is)")
        _emit(journal, journal_mod.EventType.pr_merge_failed, {
            "kind": "error",
            "needs_rebase": False,
            "detail": "missing or non-integer pr_number, or missing branch, "
                      "on Awaiting Review row",
        }, task_key=task.key)
        return "unactionable"

    # --- ladder step (a): approval ----------------------------------------
    verdict = _classify(cfg, row, str(branch), risk_cfg)
    if verdict.is_low:
        approver = DISPATCHER_APPROVER
        log(f"  merge: {task.key} risk=low — dispatcher self-approves "
            f"(PR #{number})")
    else:
        review = pr_mod.pr_review_state(
            cwd=cfg.repo_root, number=number, gh_bin=cfg.gh_bin,
        )
        if review.error:
            log(f"  merge: {task.key} risk=elevated — could not read review "
                f"state ({review.error}); treating as not approved")
        if not review.approved:
            # Hold at Awaiting Review; notify once per task across passes.
            if task.key not in state.approval_notified:
                _notify(notifier, journal,
                        notify_mod.pr_awaiting_external_approval_notification(
                            task_key=task.key, summary=summary, pr_url=pr_url,
                            pr_number=number, reasons=list(verdict.reasons),
                            run_id=cfg.run_id, tasks_yaml=str(cfg.tasks_path),
                        ), task_key=task.key)
                state.approval_notified.add(task.key)
            log(f"  merge: {task.key} risk=elevated, no external approval — "
                f"held at Awaiting Review (PR #{number})")
            return "awaiting-approval"
        approver = f"external:{review.approver}" if review.approver else "external"
        log(f"  merge: {task.key} risk=elevated — external approval present "
            f"(approver={approver}, PR #{number})")

    _emit(journal, journal_mod.EventType.pr_approved, {
        "number": number,
        "approver": approver,
        "risk_level": verdict.level,
        "reasons": list(verdict.reasons),
    }, task_key=task.key)

    # --- merge -------------------------------------------------------------
    merge = pr_mod.merge_pr(
        cwd=cfg.repo_root, number=number, gh_bin=cfg.gh_bin, method="merge",
    )
    if merge.merged:
        sha = _feature_branch_sha(cfg)
        _mutate_row(cfg, task.key, lambda r: _apply_merged(r, approver, sha))
        log(f"  merge: {task.key} MERGED PR #{number} into "
            f"{cfg.feature_branch} (approver={approver})")
        _emit(journal, journal_mod.EventType.pr_merged, {
            "number": number,
            "merger": DISPATCHER_APPROVER,
            "approver": approver,
            "target": cfg.feature_branch,
            "feature_branch_sha": sha,
        }, task_key=task.key)
        return "merged"

    # Merge failed. Conflict → needs_rebase (the supervising agent rebases);
    # any other error → surfaced too, but never flagged needs_rebase (a rebase
    # would not fix an auth/usage error). Either way the row stays Awaiting
    # Review and the engine continues with the other eligible PRs.
    kind = "conflict" if merge.conflict else "error"
    detail = merge.error or "gh pr merge failed"
    log(f"  merge: {task.key} PR #{number} merge failed ({kind}): {detail}")
    if merge.conflict:
        _mutate_row(cfg, task.key, lambda r: r.__setitem__("needs_rebase", True))
    else:
        _mutate_row(cfg, task.key,
                    lambda r: r.__setitem__("merge_error", detail[:300]))
    _emit(journal, journal_mod.EventType.pr_merge_failed, {
        "number": number,
        "kind": kind,
        "needs_rebase": bool(merge.conflict),
        "detail": detail[:300],
    }, task_key=task.key)
    if task.key not in state.rebase_notified:
        _notify(notifier, journal,
                notify_mod.pr_needs_rebase_notification(
                    task_key=task.key, summary=summary, pr_url=pr_url,
                    pr_number=number, detail=detail, run_id=cfg.run_id,
                    tasks_yaml=str(cfg.tasks_path),
                ), task_key=task.key)
        state.rebase_notified.add(task.key)
    return "needs-rebase"


def _apply_merged(row: Any, approver: str, sha: str | None) -> None:
    """Stamp a row Merged: terminal status + the audit fields. Clears any stale
    ``needs_rebase`` / ``merge_error`` from an earlier failed attempt that has
    since been resolved and re-merged."""
    row["status"] = plan_mod.MERGED
    row["merged_at"] = _now_iso()
    row["pr_approved_by"] = approver
    row["merged_by"] = DISPATCHER_APPROVER
    if sha:
        row["merged_sha"] = sha
    row.pop("needs_rebase", None)
    row.pop("merge_error", None)


# --- helpers ----------------------------------------------------------------


def _classify(
    cfg: MergeEngineConfig, row: Any, branch: str, risk_cfg: risk_mod.RiskConfig,
) -> risk_mod.RiskVerdict:
    """Classify the task's PR branch from the repo root (no worktree needed).

    Diffs ``feature_branch...branch`` so the standalone command works even when
    the task's worktree is gone. Fails closed (elevated) inside risk.classify if
    the diff can't be computed.
    """
    return risk_mod.classify(
        row, cfg.repo_root, cfg.feature_branch,
        head_ref=branch, config=risk_cfg,
    )


def _feature_branch_sha(cfg: MergeEngineConfig) -> str | None:
    """The local feature-branch tip SHA, recorded in the pr_merged event.

    ``gh pr merge`` merges on the forge (origin); the local ref may lag until a
    fetch. This records the best-available local tip for the audit trail —
    keeping the local feature branch in lockstep with the remote is the
    supervising agent's / next run's job (``ensure_feature_branch``), not this
    phase's.
    """
    import subprocess
    try:
        proc = subprocess.run(
            ["git", "rev-parse", cfg.feature_branch],
            cwd=str(cfg.repo_root), capture_output=True, text=True,
            check=False, timeout=30,
        )
    except OSError:
        return None
    if proc.returncode != 0:
        return None
    return (proc.stdout or "").strip() or None


def _load_tasks(cfg: MergeEngineConfig) -> list[plan_mod.Task]:
    """Load the tasks YAML into Task views, tolerating a transient read race.

    A malformed YAML (mid-write by a worker) yields an empty list rather than
    raising — the next pass re-reads. The file lock makes a torn read unlikely,
    but the engine must never crash the run on one.
    """
    try:
        with yaml_io.FileLock(cfg.tasks_path, timeout_seconds=cfg.lock_timeout_seconds):
            doc = yaml_io.load(cfg.tasks_path)
        return plan_mod.load_tasks(doc)
    except Exception as e:  # noqa: BLE001 - defensive: a torn/locked read must not crash the pass
        # A persistent failure (genuinely malformed YAML) would otherwise make
        # the pass a silent no-op; warn so it's diagnosable. The run-start
        # preflight + workers validate the YAML, so this is rare in practice.
        sys.stderr.write(
            f"warning: merge_engine could not load tasks YAML "
            f"({cfg.tasks_path}): {e} — merge pass skipped this cycle\n"
        )
        return []


def _mutate_row(cfg: MergeEngineConfig, task_key: str, mutator) -> bool:
    """Locked load-mutate-save of one row by key. Mirrors orchestrator._mutate_row.

    Returns True if the row was found, False otherwise (a row edited out from
    under us is logged, not fatal)."""
    with yaml_io.FileLock(cfg.tasks_path, timeout_seconds=cfg.lock_timeout_seconds):
        doc = yaml_io.load(cfg.tasks_path)
        for row in doc.get("tasks", []):
            if str(row.get("key")) == task_key:
                mutator(row)
                yaml_io.dump(doc, cfg.tasks_path)
                return True
    sys.stderr.write(
        f"warning: merge_engine._mutate_row: task {task_key!r} not in YAML "
        f"(skipping merge stamp; YAML may have been edited mid-run)\n"
    )
    return False


def _emit(
    journal: journal_mod.Journal | None,
    event_type: journal_mod.EventType,
    payload: dict[str, Any] | None = None,
    *,
    task_key: str | None = None,
) -> None:
    """Append one journal event, best-effort (a write must never abort a pass).
    No-op when journaling is disabled. Mirrors orchestrator._emit_event."""
    if journal is None:
        return
    try:
        journal.append(event_type, payload or {}, task_key=task_key)
    except Exception as e:  # pragma: no cover - defensive
        et = getattr(event_type, "value", event_type)
        sys.stderr.write(
            f"warning: merge_engine journal append failed for {et!r}"
            + (f" (task {task_key})" if task_key else "") + f": {e}\n"
        )


def _notify(
    notifier: notify_mod.Notifier | None,
    journal: journal_mod.Journal | None,
    notification: notify_mod.Notification,
    *,
    task_key: str | None = None,
) -> None:
    """Send a notification + journal a notify_sent event, both best-effort.
    Mirrors orchestrator._send_notification's guarantees."""
    delivered = False
    if notifier is not None:
        try:
            delivered = bool(notifier.send(notification))
        except Exception:  # pragma: no cover - defensive
            delivered = False
    _emit(journal, journal_mod.EventType.notify_sent, {
        "title": notification.title,
        "urgency": notification.urgency,
        "tags": list(notification.tags),
        "delivered": delivered,
    }, task_key=task_key)


def _str_or_none(value: Any) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    return s or None


def _now_iso() -> str:
    import datetime as dt
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")
