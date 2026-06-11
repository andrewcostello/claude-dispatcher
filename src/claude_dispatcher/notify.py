"""Notification sinks for dispatcher events.

The orchestrator fires notifications at four event points so a human can
discover that they're needed without watching the terminal:

  * `task_blocked`  — any Tasker landed in Blocked status (panel block
                      after iterate exhausted, spawn failure, malformed
                      summary, auto-integrate failure, worker exception)
  * `awaiting_pr_approval` — supervised PR gate fired (Tasker prepared a
                      PR and is parked for human approval). Highest
                      urgency — the run is literally waiting on the human.
  * `run_complete`  — the dispatch loop exited. One rollup notification
                      with Done/Blocked/Escalated counts and the
                      Blocked-reason rollup.
  * `worker_exception` — a worker thread raised something other than a
                      normal task failure. The dispatcher itself errored.

Channels are pluggable: `NtfyNotifier` posts to `https://ntfy.sh/<topic>`
(zero-account, free push to phone via the ntfy app); `SlackNotifier`
POSTs to a Slack incoming-webhook URL. `MultiNotifier` fans out to a
list. `NullNotifier` is the no-op default when no channel is configured.

This module is intentionally synchronous and best-effort: a notification
failure logs but never raises into the orchestrator. The dispatcher's
job is to dispatch tasks, not to deliver SMS.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Callable


# --- event dataclass --------------------------------------------------------


@dataclass
class Notification:
    """One event to be delivered. `urgency` is a soft hint for channels
    that support priority levels (ntfy maps to its 1-5 scale; Slack
    ignores). `click_url` is the click-to-open target — typically a
    file:// URL to the affected summary.md or the tasks YAML.
    """

    title: str
    body: str
    urgency: str = "default"  # "low" | "default" | "high"
    click_url: str | None = None
    # Free-form tags for filtering / search. Both channels render these.
    tags: list[str] = field(default_factory=list)


# --- channel implementations ------------------------------------------------


class Notifier:
    """Abstract base. `send` MUST NOT raise — concrete subclasses catch
    and log internally."""

    name: str = "base"

    def send(self, n: Notification) -> bool:  # pragma: no cover (abstract)
        raise NotImplementedError


class NullNotifier(Notifier):
    """No-op. Used when no notification channel is configured. Recording
    a notification still counts in `sent` for diagnostic purposes.
    """

    name = "null"

    def __init__(self) -> None:
        self.sent: list[Notification] = []

    def send(self, n: Notification) -> bool:
        self.sent.append(n)
        return True


_NTFY_PRIORITY = {
    "low": "2",       # min on ntfy is 1; we don't go below 2 to keep on-screen
    "default": "3",
    "high": "5",      # ntfy "max" — bypasses Do Not Disturb where supported
}


class NtfyNotifier(Notifier):
    """POST to `https://ntfy.sh/<topic>` (or a self-hosted ntfy server).

    No auth required for ntfy.sh. The topic IS the secret — pick something
    unguessable. ntfy supports rich headers: Title, Priority, Tags,
    Click (URL opened on tap), Markdown (rendered when the client toggles
    it on). We use all four.
    """

    name = "ntfy"

    def __init__(self, topic: str, *, server: str = "https://ntfy.sh") -> None:
        self.topic = topic.strip().lstrip("/")
        self.server = server.rstrip("/")
        # 5 sec is plenty for a single HTTP POST to ntfy.sh. We do NOT
        # want to block the dispatch loop on a slow network.
        self.timeout_seconds = 5

    @property
    def url(self) -> str:
        return f"{self.server}/{self.topic}"

    def send(self, n: Notification) -> bool:
        headers = {
            "Title": _ascii_safe(n.title)[:200],
            "Priority": _NTFY_PRIORITY.get(n.urgency, "3"),
            "Markdown": "yes",
        }
        if n.tags:
            # ntfy renders tags as emoji prefixes when they match known
            # tag names ("warning", "rotating_light", etc.) and as
            # plain text otherwise.
            headers["Tags"] = ",".join(t.strip().replace(",", "") for t in n.tags)
        if n.click_url:
            headers["Click"] = n.click_url
        try:
            req = urllib.request.Request(
                self.url,
                data=n.body.encode("utf-8"),
                method="POST",
                headers=headers,
            )
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                return 200 <= resp.status < 300
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            # Best-effort: log to stderr but don't break the dispatch loop.
            import sys
            sys.stderr.write(f"notify[ntfy]: send failed: {e}\n")
            return False


class SlackNotifier(Notifier):
    """POST to a Slack incoming webhook URL.

    Uses Slack's `blocks` payload for rich formatting: a header (title),
    a section (body markdown), and a context block (tags + click URL).
    The webhook URL is the secret — keep it out of argv; pass via env var.
    """

    name = "slack"

    def __init__(self, webhook_url: str) -> None:
        self.webhook_url = webhook_url
        self.timeout_seconds = 5

    def send(self, n: Notification) -> bool:
        # Build a small Block Kit payload.
        blocks: list[dict] = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": _ascii_safe(n.title)[:150]},
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": (n.body or "—")[:2900]},
            },
        ]
        ctx_elements: list[dict] = []
        if n.tags:
            ctx_elements.append({
                "type": "mrkdwn",
                "text": " · ".join(f"`{t}`" for t in n.tags),
            })
        if n.click_url:
            ctx_elements.append({
                "type": "mrkdwn",
                "text": f"<{n.click_url}|open context>",
            })
        if ctx_elements:
            blocks.append({"type": "context", "elements": ctx_elements})

        # Slack's incoming-webhook also requires a top-level `text` field
        # for accessibility / fallback notification text. Use the title.
        payload = {
            "text": _ascii_safe(n.title)[:150],
            "blocks": blocks,
        }
        try:
            req = urllib.request.Request(
                self.webhook_url,
                data=json.dumps(payload).encode("utf-8"),
                method="POST",
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                return 200 <= resp.status < 300
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            import sys
            sys.stderr.write(f"notify[slack]: send failed: {e}\n")
            return False


class MultiNotifier(Notifier):
    """Fan out one notification to every configured channel. A failure
    on one channel doesn't prevent others from receiving it.
    """

    name = "multi"

    def __init__(self, channels: list[Notifier]) -> None:
        self.channels = list(channels)

    def send(self, n: Notification) -> bool:
        if not self.channels:
            return True
        any_ok = False
        for ch in self.channels:
            if ch.send(n):
                any_ok = True
        return any_ok


# --- config + factory -------------------------------------------------------


@dataclass
class NotifyConfig:
    """How to construct the orchestrator's Notifier.

    Values are typically pulled from CLI flags + env vars in cli.py /
    orchestrator._build_config. Keeping the dataclass small means a test
    can construct a NotifyConfig() directly to drive the build path.
    """

    ntfy_topic: str | None = None
    ntfy_server: str = "https://ntfy.sh"
    slack_webhook_url: str | None = None


def build_notifier(cfg: NotifyConfig) -> Notifier:
    """Construct the right Notifier shape from config.

    No channel configured → NullNotifier (silent).
    One channel → that channel directly.
    Multiple → MultiNotifier wrapping both.
    """
    channels: list[Notifier] = []
    if cfg.ntfy_topic:
        channels.append(NtfyNotifier(cfg.ntfy_topic, server=cfg.ntfy_server))
    if cfg.slack_webhook_url:
        channels.append(SlackNotifier(cfg.slack_webhook_url))
    if not channels:
        return NullNotifier()
    if len(channels) == 1:
        return channels[0]
    return MultiNotifier(channels)


def build_notifier_from_env(
    *,
    cli_ntfy_topic: str | None = None,
    cli_ntfy_server: str | None = None,
    cli_slack_webhook: str | None = None,
    env: dict[str, str] | None = None,
) -> Notifier:
    """Build a Notifier preferring CLI args over env vars.

    Env vars (lowest priority):
      DISPATCHER_NTFY_TOPIC, DISPATCHER_NTFY_SERVER, DISPATCHER_SLACK_WEBHOOK
    """
    e = env if env is not None else os.environ
    cfg = NotifyConfig(
        ntfy_topic=cli_ntfy_topic or e.get("DISPATCHER_NTFY_TOPIC") or None,
        ntfy_server=cli_ntfy_server or e.get("DISPATCHER_NTFY_SERVER") or "https://ntfy.sh",
        slack_webhook_url=cli_slack_webhook or e.get("DISPATCHER_SLACK_WEBHOOK") or None,
    )
    return build_notifier(cfg)


# --- helpers ----------------------------------------------------------------


def _ascii_safe(s: str) -> str:
    """ntfy and Slack tolerate UTF-8, but ntfy's headers go through HTTP
    and some clients/proxies mangle non-ASCII in headers. We strip
    aggressively for the Title only — body is full UTF-8 either way.
    """
    return "".join(c if 32 <= ord(c) < 127 else " " for c in s)


# --- public event helpers used by the orchestrator --------------------------
#
# These are tiny adapters that turn dispatcher events into Notification
# objects. Putting them here (not in orchestrator.py) keeps the
# orchestrator's call sites short and the message formatting
# unit-testable.


def task_blocked_notification(
    *,
    task_key: str,
    summary: str,
    reason: str,
    run_id: str,
    summary_path: str | None = None,
    tasks_yaml: str | None = None,
) -> Notification:
    body_lines = [
        f"*Task:* `{task_key}` — {summary}",
        f"*Run:* `{run_id}`",
        f"*Reason:* {reason}",
    ]
    if summary_path:
        body_lines.append(f"*Summary:* `{summary_path}`")
    return Notification(
        title=f"[dispatcher] {task_key} Blocked",
        body="\n".join(body_lines),
        urgency="default",
        click_url=_path_to_url(summary_path or tasks_yaml),
        tags=["warning", "blocked"],
    )


def awaiting_pr_approval_notification(
    *,
    task_key: str,
    summary: str,
    pr_title: str | None,
    pr_branch: str | None,
    run_id: str,
    summary_path: str | None = None,
) -> Notification:
    body_lines = [
        f"*Task:* `{task_key}` — {summary}",
        f"*Run:* `{run_id}`",
    ]
    if pr_title:
        body_lines.append(f"*PR title:* {pr_title}")
    if pr_branch:
        body_lines.append(f"*Branch:* `{pr_branch}`")
    body_lines.append("Run is parked at the PR-approval gate. Approve via "
                      "supervised stdin (`approve` / `reject` / `skip`).")
    return Notification(
        title=f"[dispatcher] {task_key} awaiting PR approval",
        body="\n".join(body_lines),
        urgency="high",
        click_url=_path_to_url(summary_path),
        tags=["rotating_light", "approval"],
    )


def pr_awaiting_external_approval_notification(
    *,
    task_key: str,
    summary: str,
    pr_url: str | None,
    pr_number: int | None,
    reasons: list[str] | None,
    run_id: str,
    tasks_yaml: str | None = None,
) -> Notification:
    """An elevated-risk PR is mergeable (all deps merged) but lacks the external
    GitHub approval the ladder requires. Fired once per task (the merge engine
    dedupes across passes), so a human/bot knows their review is the only thing
    holding the merge.
    """
    body_lines = [
        f"*Task:* `{task_key}` — {summary}",
        f"*Run:* `{run_id}`",
    ]
    if pr_number is not None:
        body_lines.append(f"*PR:* #{pr_number}")
    if reasons:
        body_lines.append("*Elevated because:* " + "; ".join(reasons[:4]))
    body_lines.append("Merge is blocked pending an external GitHub approval "
                      "(`gh pr review --approve`, or a reviewer bot).")
    return Notification(
        title=f"[dispatcher] {task_key} PR awaiting approval to merge",
        body="\n".join(body_lines),
        urgency="high",
        click_url=pr_url or _path_to_url(tasks_yaml),
        tags=["rotating_light", "approval"],
    )


def pr_needs_rebase_notification(
    *,
    task_key: str,
    summary: str,
    pr_url: str | None,
    pr_number: int | None,
    detail: str | None,
    run_id: str,
    tasks_yaml: str | None = None,
) -> Notification:
    """A PR could not be merged into the feature branch — a conflict or other
    unmergeable state. The merge engine does NOT auto-rebase (a deliberate
    non-goal); the supervising agent resolves it. Fired once per task.
    """
    body_lines = [
        f"*Task:* `{task_key}` — {summary}",
        f"*Run:* `{run_id}`",
    ]
    if pr_number is not None:
        body_lines.append(f"*PR:* #{pr_number}")
    if detail:
        body_lines.append(f"*Detail:* {detail[:200]}")
    body_lines.append("Left Awaiting Review with `needs_rebase: true`. The "
                      "dispatcher does not auto-rebase — resolve and re-run "
                      "the merge pass (`dispatcher merge-prs <run-id>`).")
    return Notification(
        title=f"[dispatcher] {task_key} PR needs rebase",
        body="\n".join(body_lines),
        urgency="high",
        click_url=pr_url or _path_to_url(tasks_yaml),
        tags=["warning", "rebase"],
    )


def run_complete_notification(
    *,
    run_id: str,
    done: int,
    blocked: int,
    escalated: int,
    blocked_rollup: list[tuple[str, str]] | None = None,
    tasks_yaml: str | None = None,
) -> Notification:
    parts = [f"*Run:* `{run_id}`",
             f"*Done:* {done}  |  *Blocked:* {blocked}  |  *Escalated:* {escalated}"]
    if blocked_rollup:
        parts.append("")
        parts.append("*Blocked reasons:*")
        for key, reason in blocked_rollup[:10]:
            parts.append(f"• `{key}` — {reason[:160]}")
        if len(blocked_rollup) > 10:
            parts.append(f"…and {len(blocked_rollup) - 10} more")
    urgency = "high" if (blocked or escalated) else "default"
    return Notification(
        title=f"[dispatcher] run complete: {done} done / {blocked} blocked",
        body="\n".join(parts),
        urgency=urgency,
        click_url=_path_to_url(tasks_yaml),
        tags=(["white_check_mark"] if not (blocked or escalated) else ["warning"]),
    )


def worker_exception_notification(
    *,
    task_key: str,
    run_id: str,
    exception_repr: str,
    tasks_yaml: str | None = None,
) -> Notification:
    return Notification(
        title=f"[dispatcher] worker thread crashed on {task_key}",
        body="\n".join([
            f"*Task:* `{task_key}`",
            f"*Run:* `{run_id}`",
            f"*Exception:* `{exception_repr[:500]}`",
            "The dispatcher itself errored on this task — not a normal "
            "Tasker failure. Investigate run.log.",
        ]),
        urgency="high",
        click_url=_path_to_url(tasks_yaml),
        tags=["rotating_light", "crash"],
    )


def _path_to_url(path: str | None) -> str | None:
    """Convert a local filesystem path to a file:// URL. Returns None if
    path is None/empty — caller decides what (if any) URL to attach.
    """
    if not path:
        return None
    from pathlib import Path

    try:
        return Path(path).resolve().as_uri()
    except (ValueError, OSError):
        return None


# Notification callback signature used internally by the orchestrator.
# Functions of this shape can be injected by tests for assertions.
NotifyFn = Callable[[Notification], bool]
