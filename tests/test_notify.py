"""Unit tests for the notification module.

No real network calls. NtfyNotifier and SlackNotifier are exercised via
a mocked urllib.request.urlopen so we verify URL, headers, and payload
shape end-to-end without hitting ntfy.sh / Slack.
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from urllib.error import URLError

import pytest

from claude_dispatcher import notify


# --- Notification helpers ---------------------------------------------------


def test_task_blocked_notification_shape():
    n = notify.task_blocked_notification(
        task_key="T-1",
        summary="schema migration",
        reason="panel block",
        run_id="run-x",
        summary_path="/tmp/summary.md",
        tasks_yaml="/tmp/tasks.yaml",
    )
    assert "T-1" in n.title
    assert "panel block" in n.body
    assert "schema migration" in n.body
    assert n.urgency == "default"
    assert "blocked" in n.tags
    # click_url prefers summary_path over tasks_yaml
    assert n.click_url and "summary.md" in n.click_url


def test_awaiting_pr_approval_notification_is_high_urgency():
    n = notify.awaiting_pr_approval_notification(
        task_key="T-2",
        summary="add escrow",
        pr_title="feat(wallet): add escrow",
        pr_branch="feat/T-2",
        run_id="run-y",
    )
    assert n.urgency == "high"
    assert "approval" in n.tags or "rotating_light" in n.tags
    assert "T-2" in n.title
    assert "feat/T-2" in n.body


def test_run_complete_notification_high_urgency_when_blocked():
    n = notify.run_complete_notification(
        run_id="r1", done=2, blocked=1, escalated=0,
        blocked_rollup=[("T-3", "spawn_failed: timeout")],
    )
    assert n.urgency == "high"
    assert "T-3" in n.body
    assert "spawn_failed" in n.body


def test_run_complete_notification_default_urgency_when_clean():
    n = notify.run_complete_notification(
        run_id="r2", done=5, blocked=0, escalated=0,
    )
    assert n.urgency == "default"
    assert "5" in n.body  # done count


def test_run_complete_notification_pr_mode_pending_merge_summary():
    """pr mode (PRF-5): the merge tallies add a pending-merge line, and pending
    merges/rebases bump urgency to high even on an otherwise clean run."""
    n = notify.run_complete_notification(
        run_id="r", done=4, blocked=0, escalated=0,
        merged=2, awaiting_review=2, needs_rebase=1,
    )
    assert "*Merged:* 2" in n.body
    assert "*Awaiting merge:* 2" in n.body
    assert "*Needs rebase:* 1" in n.body
    assert "2 PR(s) awaiting merge, 1 need rebase" in n.body
    # Clean (no blocked/escalated) but merges pending → still a loud ping.
    assert n.urgency == "high"


def test_run_complete_notification_pr_mode_all_merged_is_calm():
    """All PRs landed (nothing awaiting, none needing rebase) → default urgency
    and no pending line, just the merge tally."""
    n = notify.run_complete_notification(
        run_id="r", done=3, blocked=0, escalated=0,
        merged=3, awaiting_review=0, needs_rebase=0,
    )
    assert "*Merged:* 3" in n.body
    assert "awaiting merge" not in n.body
    assert n.urgency == "default"


def test_run_complete_notification_branch_mode_omits_merge_line():
    """Acceptance: branch-mode message unchanged — no merge tallies passed → no
    Merged/Awaiting line at all."""
    n = notify.run_complete_notification(
        run_id="r", done=5, blocked=0, escalated=0,
    )
    assert "Merged" not in n.body
    assert "Awaiting merge" not in n.body


def test_run_complete_notification_truncates_long_rollup():
    rollup = [(f"T-{i}", f"reason {i}") for i in range(50)]
    n = notify.run_complete_notification(
        run_id="r", done=0, blocked=50, escalated=0,
        blocked_rollup=rollup,
    )
    # Only the first 10 are listed in detail.
    assert "T-0" in n.body
    assert "T-9" in n.body
    assert "T-10" not in n.body
    assert "and 40 more" in n.body


def test_worker_exception_notification_high_urgency():
    n = notify.worker_exception_notification(
        task_key="T-4", run_id="r",
        exception_repr="RuntimeError('boom')",
    )
    assert n.urgency == "high"
    assert "crash" in n.tags
    assert "boom" in n.body


def test_path_to_url_returns_file_uri(tmp_path):
    p = tmp_path / "x.md"
    p.write_text("hi")
    url = notify._path_to_url(str(p))
    assert url and url.startswith("file://")


def test_path_to_url_none_passthrough():
    assert notify._path_to_url(None) is None
    assert notify._path_to_url("") is None


# --- NullNotifier ------------------------------------------------------------


def test_null_notifier_records_but_does_nothing():
    nn = notify.NullNotifier()
    n = notify.Notification(title="t", body="b")
    assert nn.send(n) is True
    assert len(nn.sent) == 1
    assert nn.sent[0] is n


# --- NtfyNotifier -----------------------------------------------------------


class _FakeResponse:
    def __init__(self, status: int = 200) -> None:
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _capture_urlopen(monkeypatch, response_status: int = 200):
    """Patch urllib.request.urlopen and return the list it appends to."""
    captured: list = []

    def fake(req, timeout=None):
        captured.append({
            "url": req.full_url,
            "method": req.get_method(),
            "headers": dict(req.header_items()),
            "data": req.data,
            "timeout": timeout,
        })
        return _FakeResponse(response_status)

    monkeypatch.setattr("urllib.request.urlopen", fake)
    return captured


def test_ntfy_sends_post_with_title_priority_tags_and_click(monkeypatch):
    captured = _capture_urlopen(monkeypatch)
    nn = notify.NtfyNotifier(topic="andrew-test-topic")
    ok = nn.send(notify.Notification(
        title="hello",
        body="world",
        urgency="high",
        click_url="file:///tmp/summary.md",
        tags=["warning", "blocked"],
    ))
    assert ok is True
    assert len(captured) == 1
    c = captured[0]
    assert c["url"] == "https://ntfy.sh/andrew-test-topic"
    assert c["method"] == "POST"
    assert c["data"] == b"world"
    # urllib lower-cases header names in header_items.
    norm = {k.lower(): v for k, v in c["headers"].items()}
    assert norm["title"] == "hello"
    assert norm["priority"] == "5"  # high → 5
    assert norm["markdown"] == "yes"
    assert "warning" in norm["tags"] and "blocked" in norm["tags"]
    assert norm["click"] == "file:///tmp/summary.md"


def test_ntfy_strips_topic_leading_slashes(monkeypatch):
    captured = _capture_urlopen(monkeypatch)
    nn = notify.NtfyNotifier(topic="/leading/slashes")
    nn.send(notify.Notification(title="t", body="b"))
    assert captured[0]["url"] == "https://ntfy.sh/leading/slashes"


def test_ntfy_strips_trailing_slash_from_server(monkeypatch):
    captured = _capture_urlopen(monkeypatch)
    nn = notify.NtfyNotifier(topic="x", server="https://ntfy.example.com/")
    nn.send(notify.Notification(title="t", body="b"))
    assert captured[0]["url"] == "https://ntfy.example.com/x"


def test_ntfy_priority_mapping():
    nn = notify.NtfyNotifier(topic="x")
    assert notify._NTFY_PRIORITY["low"] == "2"
    assert notify._NTFY_PRIORITY["default"] == "3"
    assert notify._NTFY_PRIORITY["high"] == "5"


def test_ntfy_swallows_network_error(monkeypatch):
    def boom(req, timeout=None):
        raise URLError("connection refused")

    monkeypatch.setattr("urllib.request.urlopen", boom)
    nn = notify.NtfyNotifier(topic="x")
    # Must NOT raise; returns False.
    assert nn.send(notify.Notification(title="t", body="b")) is False


def test_ntfy_swallows_timeout(monkeypatch):
    def slow(req, timeout=None):
        raise TimeoutError("read timed out")

    monkeypatch.setattr("urllib.request.urlopen", slow)
    nn = notify.NtfyNotifier(topic="x")
    assert nn.send(notify.Notification(title="t", body="b")) is False


def test_ntfy_title_strips_non_ascii(monkeypatch):
    captured = _capture_urlopen(monkeypatch)
    nn = notify.NtfyNotifier(topic="x")
    nn.send(notify.Notification(title="hi → there 💥", body="b"))
    norm = {k.lower(): v for k, v in captured[0]["headers"].items()}
    # Non-ASCII collapsed to spaces; ASCII chars preserved.
    assert "hi" in norm["title"]
    assert "there" in norm["title"]
    assert "→" not in norm["title"]
    assert "💥" not in norm["title"]


# --- SlackNotifier ----------------------------------------------------------


def test_slack_posts_json_payload(monkeypatch):
    captured = _capture_urlopen(monkeypatch)
    sn = notify.SlackNotifier(webhook_url="https://hooks.slack.com/services/T/B/X")
    ok = sn.send(notify.Notification(
        title="dispatcher: T-1 Blocked",
        body="*Task:* T-1\n*Reason:* spawn_failed",
        urgency="high",
        click_url="file:///tmp/summary.md",
        tags=["warning", "blocked"],
    ))
    assert ok is True
    c = captured[0]
    assert c["url"] == "https://hooks.slack.com/services/T/B/X"
    # urllib normalises header name to title-case for Content-Type
    norm = {k.lower(): v for k, v in c["headers"].items()}
    assert norm["content-type"] == "application/json"
    body = json.loads(c["data"].decode("utf-8"))
    assert "text" in body  # required for accessibility fallback
    assert body["blocks"][0]["type"] == "header"
    assert "T-1 Blocked" in body["blocks"][0]["text"]["text"]
    section = body["blocks"][1]
    assert section["type"] == "section"
    assert "spawn_failed" in section["text"]["text"]
    # Context block has both the tags and the click URL.
    ctx = body["blocks"][2]
    assert ctx["type"] == "context"
    ctx_texts = " ".join(e["text"] for e in ctx["elements"])
    assert "warning" in ctx_texts and "blocked" in ctx_texts
    assert "open context" in ctx_texts


def test_slack_swallows_network_error(monkeypatch):
    def boom(req, timeout=None):
        raise URLError("dns fail")

    monkeypatch.setattr("urllib.request.urlopen", boom)
    sn = notify.SlackNotifier(webhook_url="https://x")
    assert sn.send(notify.Notification(title="t", body="b")) is False


def test_slack_truncates_long_body(monkeypatch):
    captured = _capture_urlopen(monkeypatch)
    sn = notify.SlackNotifier(webhook_url="https://x")
    sn.send(notify.Notification(title="t", body="x" * 5000))
    body = json.loads(captured[0]["data"].decode("utf-8"))
    section_text = body["blocks"][1]["text"]["text"]
    assert len(section_text) <= 2900


# --- MultiNotifier ----------------------------------------------------------


def test_multi_notifier_fans_out_to_all_channels():
    a = notify.NullNotifier()
    b = notify.NullNotifier()
    m = notify.MultiNotifier([a, b])
    m.send(notify.Notification(title="t", body="b"))
    assert len(a.sent) == 1
    assert len(b.sent) == 1


def test_multi_notifier_continues_on_partial_failure(monkeypatch):
    class _Failing(notify.Notifier):
        name = "fail"
        def send(self, n): return False

    good = notify.NullNotifier()
    m = notify.MultiNotifier([_Failing(), good])
    # Returns True iff ANY channel succeeded.
    assert m.send(notify.Notification(title="t", body="b")) is True
    assert len(good.sent) == 1


def test_multi_notifier_empty_channels_is_noop():
    m = notify.MultiNotifier([])
    assert m.send(notify.Notification(title="t", body="b")) is True


# --- factory ---------------------------------------------------------------


def test_build_notifier_no_config_returns_null():
    n = notify.build_notifier(notify.NotifyConfig())
    assert isinstance(n, notify.NullNotifier)


def test_build_notifier_only_ntfy_returns_ntfy():
    n = notify.build_notifier(notify.NotifyConfig(ntfy_topic="x"))
    assert isinstance(n, notify.NtfyNotifier)
    assert n.topic == "x"


def test_build_notifier_only_slack_returns_slack():
    n = notify.build_notifier(notify.NotifyConfig(slack_webhook_url="https://x"))
    assert isinstance(n, notify.SlackNotifier)


def test_build_notifier_both_returns_multi():
    n = notify.build_notifier(notify.NotifyConfig(
        ntfy_topic="x", slack_webhook_url="https://x",
    ))
    assert isinstance(n, notify.MultiNotifier)
    assert len(n.channels) == 2
    families = [c.name for c in n.channels]
    assert "ntfy" in families
    assert "slack" in families


def test_build_notifier_from_env_prefers_cli_over_env():
    env = {
        "DISPATCHER_NTFY_TOPIC": "from-env",
        "DISPATCHER_SLACK_WEBHOOK": "https://env",
    }
    n = notify.build_notifier_from_env(
        cli_ntfy_topic="from-cli",
        cli_slack_webhook="https://cli",
        env=env,
    )
    # Verify CLI values won by inspecting the wrapped channels.
    assert isinstance(n, notify.MultiNotifier)
    ntfy = next(c for c in n.channels if c.name == "ntfy")
    slack = next(c for c in n.channels if c.name == "slack")
    assert ntfy.topic == "from-cli"
    assert slack.webhook_url == "https://cli"


def test_build_notifier_from_env_falls_back_to_env():
    env = {
        "DISPATCHER_NTFY_TOPIC": "env-topic",
        "DISPATCHER_SLACK_WEBHOOK": "https://env",
    }
    n = notify.build_notifier_from_env(env=env)
    assert isinstance(n, notify.MultiNotifier)


def test_build_notifier_from_env_no_config_returns_null():
    n = notify.build_notifier_from_env(env={})
    assert isinstance(n, notify.NullNotifier)
