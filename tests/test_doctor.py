"""Tests for `dispatcher doctor` — machine probe + machine.yaml profile.

Hermetic: every test restricts PATH to a tmp_path bin dir of stub scripts
(#!/bin/sh shebangs are absolute-pathed, so the restricted PATH doesn't
break the stubs themselves) and points XDG_CONFIG_HOME at tmp_path. No
network, no real ~/.config writes.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from claude_dispatcher import cli, doctor, yaml_io


def make_stub(bin_dir: Path, name: str, body: str) -> Path:
    """Create an executable #!/bin/sh stub named `name` in bin_dir."""
    bin_dir.mkdir(parents=True, exist_ok=True)
    stub = bin_dir / name
    stub.write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8")
    stub.chmod(0o755)
    return stub


@pytest.fixture
def hermetic_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Restrict PATH to a stub bin dir and XDG_CONFIG_HOME to tmp_path.

    Returns the bin dir; the machine.yaml lands under
    tmp_path/config/claude-dispatcher/machine.yaml.
    """
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    monkeypatch.setenv("PATH", str(bin_dir))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    return bin_dir


def machine_yaml_path(tmp_path: Path) -> Path:
    return tmp_path / "config" / "claude-dispatcher" / "machine.yaml"


def stub_required(bin_dir: Path) -> None:
    """Stub the two --check-required binaries with well-formed versions."""
    make_stub(bin_dir, "claude", 'echo "2.0.5 (Claude Code)"')
    make_stub(bin_dir, "git", 'echo "git version 2.43.0"')


# --- probe_binary edge cases -------------------------------------------------


def test_absent_binary_probes_to_null_fields(hermetic_env: Path) -> None:
    """Edge case 1: binary absent from PATH → present false, fields null."""
    entry = doctor.probe_binary("grok")
    assert entry == {
        "present": False,
        "path": None,
        "version": None,
        "version_raw": None,
    }


def test_version_exit_nonzero_captured(hermetic_env: Path) -> None:
    """Edge case 2: --version exits non-zero → present, version null, error noted."""
    make_stub(hermetic_env, "docker", "echo boom >&2\nexit 3")
    entry = doctor.probe_binary("docker")
    assert entry["present"] is True
    assert entry["path"] == str(hermetic_env / "docker")
    assert entry["version"] is None
    assert "exited 3" in entry["version_error"]


def test_version_printed_to_stderr_is_parsed(hermetic_env: Path) -> None:
    """Edge case 3: some CLIs print their version to stderr."""
    make_stub(hermetic_env, "codex", 'echo "codex 1.4.2" >&2')
    entry = doctor.probe_binary("codex")
    assert entry["version"] == "1.4.2"
    assert entry["version_raw"] == "codex 1.4.2"


def test_version_with_noise_parses_first_semver_token(hermetic_env: Path) -> None:
    """Edge case 4: noise around the version token."""
    make_stub(hermetic_env, "claude", 'echo "2.0.5 (Claude Code)"')
    entry = doctor.probe_binary("claude")
    assert entry["version"] == "2.0.5"
    assert entry["version_raw"] == "2.0.5 (Claude Code)"


def test_version_token_excludes_adjacent_punctuation(hermetic_env: Path) -> None:
    """Real-world docker output: '... 29.1.3, build ...' must not keep the comma."""
    make_stub(hermetic_env, "docker", 'echo "Docker version 29.1.3, build 29.1.3-0ubuntu3"')
    entry = doctor.probe_binary("docker")
    assert entry["version"] == "29.1.3"


def test_prerelease_suffix_is_kept(hermetic_env: Path) -> None:
    make_stub(hermetic_env, "buf", 'echo "1.2.3-rc1"')
    entry = doctor.probe_binary("buf")
    assert entry["version"] == "1.2.3-rc1"


def test_unparseable_version_output_is_error_not_crash(hermetic_env: Path) -> None:
    make_stub(hermetic_env, "gh", 'echo "no digits here"')
    entry = doctor.probe_binary("gh")
    assert entry["present"] is True
    assert entry["version"] is None
    assert entry["version_raw"] == "no digits here"
    assert "no version token" in entry["version_error"]


def test_hanging_version_probe_is_killed_by_timeout(hermetic_env: Path) -> None:
    """Edge case 9: a hanging --version is killed and recorded as an error.

    Uses an injected sub-second timeout so the test never waits the real 10s.
    """
    # /bin/sleep absolute-pathed: PATH is restricted, so a bare `sleep`
    # inside the stub would fail with 127 instead of hanging.
    make_stub(hermetic_env, "qwen", "/bin/sleep 30")
    entry = doctor.probe_binary("qwen", timeout=0.2)
    assert entry["present"] is True
    assert entry["version"] is None
    assert "timed out" in entry["version_error"]


# --- profile content ----------------------------------------------------------


def test_profile_shape_and_static_stats_probe(hermetic_env: Path) -> None:
    stub_required(hermetic_env)
    profile = doctor.build_profile()

    assert profile["schema_version"] == 1
    assert profile["probed_at"].endswith("Z")
    assert set(profile["agents"]) == set(doctor.AGENT_BINS)
    assert set(profile["tools"]) == set(doctor.TOOL_BINS)
    assert profile["host"]["hostname"]
    assert profile["dispatcher"]["python_version"]

    # stats_probe comes from the static table for present CLIs...
    assert profile["agents"]["claude"]["stats_probe"] == "json-output"
    # ...and is null (like every probed field) for absent ones.
    assert profile["agents"]["codex"]["stats_probe"] is None
    assert profile["agents"]["grok"]["stats_probe"] is None


def test_doctor_writes_fresh_file_with_manual_seed(
    hermetic_env: Path, tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    stub_required(hermetic_env)
    assert cli.main(["doctor"]) == 0

    path = machine_yaml_path(tmp_path)
    text = path.read_text(encoding="utf-8")
    assert "manual:" in text
    assert "user-owned" in text  # explanatory comment seed

    doc = yaml_io.load(path)
    assert doc["schema_version"] == 1
    assert doc["agents"]["claude"]["present"] is True
    assert doc["agents"]["claude"]["version"] == "2.0.5"
    assert doc["tools"]["git"]["version"] == "2.43.0"

    out = capsys.readouterr().out
    assert "claude" in out and "2.0.5" in out
    assert str(path) in out


# --- re-probe / merge semantics -----------------------------------------------


def test_reprobe_preserves_manual_section_and_comments(
    hermetic_env: Path, tmp_path: Path
) -> None:
    """Edge case 5: manual section content and comments survive a re-probe."""
    stub_required(hermetic_env)
    path = machine_yaml_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text(
        "# top-of-file comment the user wrote\n"
        "schema_version: 1\n"
        'probed_at: "2020-01-01T00:00:00Z"\n'
        "agents:\n"
        "  claude: {present: false, path: null, version: null, version_raw: null, stats_probe: null}\n"
        "manual:\n"
        "  # never delete this comment\n"
        "  preferred_agent: claude\n"
        "  notes: hands off\n"
        "unrecognized_key: keep me too\n",
        encoding="utf-8",
    )

    assert cli.main(["doctor"]) == 0

    text = path.read_text(encoding="utf-8")
    assert "# top-of-file comment the user wrote" in text
    assert "# never delete this comment" in text
    assert "preferred_agent: claude" in text
    assert "notes: hands off" in text

    doc = yaml_io.load(path)
    # probed fields refreshed in place
    assert doc["agents"]["claude"]["present"] is True
    assert doc["agents"]["claude"]["version"] == "2.0.5"
    assert doc["probed_at"] != "2020-01-01T00:00:00Z"
    # manual + unrecognized top-level keys untouched
    assert doc["manual"]["preferred_agent"] == "claude"
    assert doc["unrecognized_key"] == "keep me too"


def test_unparseable_existing_file_exits_2_without_overwrite(
    hermetic_env: Path, tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    """Edge case 6: corrupt machine.yaml → exit 2, file byte-identical."""
    stub_required(hermetic_env)
    path = machine_yaml_path(tmp_path)
    path.parent.mkdir(parents=True)
    garbage = "manual: {unclosed: [\n"
    path.write_text(garbage, encoding="utf-8")

    assert cli.main(["doctor"]) == 2
    assert path.read_text(encoding="utf-8") == garbage
    assert "refusing to overwrite" in capsys.readouterr().err


def test_existing_file_not_a_mapping_exits_2_without_overwrite(
    hermetic_env: Path, tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    stub_required(hermetic_env)
    path = machine_yaml_path(tmp_path)
    path.parent.mkdir(parents=True)
    original = "- just\n- a list\n"
    path.write_text(original, encoding="utf-8")

    assert cli.main(["doctor"]) == 2
    assert path.read_text(encoding="utf-8") == original
    assert "not a YAML mapping" in capsys.readouterr().err


# --- config dir resolution ------------------------------------------------------


def test_xdg_config_home_is_respected(hermetic_env: Path, tmp_path: Path) -> None:
    """Edge case 7a: XDG_CONFIG_HOME set → file lands under it."""
    stub_required(hermetic_env)
    assert cli.main(["doctor"]) == 0
    assert machine_yaml_path(tmp_path).is_file()


def test_xdg_unset_defaults_to_home_dot_config(
    hermetic_env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Edge case 7b: XDG_CONFIG_HOME unset → ~/.config (HOME faked to tmp)."""
    stub_required(hermetic_env)
    monkeypatch.delenv("XDG_CONFIG_HOME")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    assert cli.main(["doctor"]) == 0
    assert (tmp_path / "home" / ".config" / "claude-dispatcher" / "machine.yaml").is_file()


def test_config_dir_flag_overrides(hermetic_env: Path, tmp_path: Path) -> None:
    stub_required(hermetic_env)
    override = tmp_path / "elsewhere"
    assert cli.main(["doctor", "--config-dir", str(override)]) == 0
    assert (override / "machine.yaml").is_file()


# --- --check exit codes -----------------------------------------------------------


def test_check_passes_when_required_present(hermetic_env: Path) -> None:
    """Edge case 8: claude + git present → --check exits 0 (soft missing OK)."""
    stub_required(hermetic_env)  # everything else (gh, docker, ...) is missing
    assert cli.main(["doctor", "--check"]) == 0


def test_check_fails_when_claude_missing(
    hermetic_env: Path, capsys: pytest.CaptureFixture
) -> None:
    make_stub(hermetic_env, "git", 'echo "git version 2.43.0"')
    assert cli.main(["doctor", "--check"]) == 1
    err = capsys.readouterr().err
    assert "claude" in err
    assert "soft" in err


def test_check_fails_when_git_missing(
    hermetic_env: Path, capsys: pytest.CaptureFixture
) -> None:
    make_stub(hermetic_env, "claude", 'echo "2.0.5 (Claude Code)"')
    assert cli.main(["doctor", "--check"]) == 1
    assert "git" in capsys.readouterr().err


def test_soft_missing_never_affects_exit_code(
    hermetic_env: Path, tmp_path: Path
) -> None:
    """Edge case 8 (cont.): plain doctor exits 0 even with everything missing."""
    assert cli.main(["doctor"]) == 0  # no binaries at all, still fine
    doc = yaml_io.load(machine_yaml_path(tmp_path))
    assert doc["agents"]["claude"]["present"] is False
    assert doc["tools"]["git"]["present"] is False


# --- endpoint agents section + --probe-endpoints ------------------------------

import http.client
import http.server
import json
import threading
import time

from claude_dispatcher import endpoint_agents as ea


_ENDPOINT_KEYS = ("MOONSHOT_API_KEY", "ZAI_API_KEY", "DEEPSEEK_API_KEY")


@pytest.fixture
def endpoint_env(monkeypatch: pytest.MonkeyPatch):
    """kimi + deepseek keyed, glm not; every probe is forbidden by default."""
    monkeypatch.setenv("MOONSHOT_API_KEY", "mk-test")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "dk-test")
    monkeypatch.delenv("ZAI_API_KEY", raising=False)

    def forbidden(*a, **kw):
        raise AssertionError("no probe may run without --probe-endpoints")

    monkeypatch.setattr(doctor, "_post_messages", forbidden)
    return monkeypatch


def _message(model: str = "kimi-k2.7-code") -> str:
    return json.dumps({
        "id": "msg_1", "type": "message", "role": "assistant", "model": model,
        "content": [{"type": "text", "text": "Hi"}], "stop_reason": "max_tokens",
        "usage": {"input_tokens": 8, "output_tokens": 1},
    })


def _error(kind: str, message: str) -> str:
    return json.dumps({"type": "error", "error": {"type": kind, "message": message}})


def test_doctor_shows_endpoint_readiness_offline(
    hermetic_env: Path, endpoint_env, capsys: pytest.CaptureFixture
) -> None:
    stub_required(hermetic_env)
    assert cli.main(["doctor"]) == 0
    out = capsys.readouterr().out
    lines = {ln.split()[0]: ln for ln in out.splitlines() if ln.startswith("  ")}
    assert "endpoint agents:" in out
    assert lines["kimi"].startswith("  kimi       ✓") and "MOONSHOT_API_KEY set" in lines["kimi"]
    assert lines["glm"].startswith("  glm        ✗") and "set ZAI_API_KEY" in lines["glm"]
    assert lines["deepseek"].startswith("  deepseek   ✓")
    assert "probe" not in out  # offline: not even a "skipped" row


@pytest.mark.parametrize(
    "status, body, kind, needle",
    [
        (200, _message(), doctor.PROBE_OK, "answered"),
        (200, _message("kimi-k2.7-code-preview"), doctor.PROBE_OK, "as 'kimi-k2.7-code-preview'"),
        (200, "{}", doctor.PROBE_ERROR, "not a messages response"),
        (200, "", doctor.PROBE_ERROR, "not a messages response"),
        (204, "", doctor.PROBE_ERROR, "not a messages response"),
        (200, "<html><body>login</body></html>", doctor.PROBE_ERROR, "not a messages response"),
        (200, _error("not_found_error", "model: kimi-k2.7-code"), doctor.PROBE_MODEL, "default_model"),
        (200, _error("authentication_error", "invalid x-api-key"), doctor.PROBE_AUTH, "key"),
        (401, _error("authentication_error", "invalid token"), doctor.PROBE_AUTH, "401"),
        (403, "", doctor.PROBE_AUTH, "403"),
        (401, "Unauthorized", doctor.PROBE_AUTH, "Unauthorized"),
        (404, _error("not_found_error", "model: kimi-k2.7-code"), doctor.PROBE_MODEL, "'kimi-k2.7-code'"),
        (404, _error("not_found_error", "The model `kimi-k2.7-code` does not exist"), doctor.PROBE_MODEL, "does not exist"),
        (400, _error("invalid_request_error", "Model Not Exist"), doctor.PROBE_MODEL, "Model Not Exist"),
        (404, _error("not_found_error", "Not Found"), doctor.PROBE_ERROR, "base_url"),
        (404, "<html>404</html>", doctor.PROBE_ERROR, "404"),
        (400, _error("invalid_request_error", "messages: at least one message is required"), doctor.PROBE_ERROR, "400"),
        (302, "", doctor.PROBE_ERROR, "refusing to follow"),
        (429, _error("rate_limit_error", "slow down"), doctor.PROBE_ERROR, "429"),
        (500, "boom", doctor.PROBE_ERROR, "500"),
        (503, "", doctor.PROBE_ERROR, "no body"),
    ],
)
def test_classify_probe_response(status, body, kind, needle) -> None:
    got_kind, detail = doctor.classify_probe_response(
        status, body, model="kimi-k2.7-code", location="https://elsewhere.example/x",
    )
    assert got_kind == kind, detail
    assert needle in detail


def test_probe_flag_probes_each_keyed_agent_once(
    hermetic_env: Path, endpoint_env, capsys: pytest.CaptureFixture
) -> None:
    stub_required(hermetic_env)
    calls: list[tuple[str, str, str]] = []

    def fake_post(url, key, model, *, timeout, max_body):
        calls.append((url, key, model))
        assert timeout == doctor.ENDPOINT_PROBE_TIMEOUT
        assert max_body == doctor.ENDPOINT_PROBE_MAX_BODY
        return 200, _message(model), {"content-type": "application/json"}

    endpoint_env.setattr(doctor, "_post_messages", fake_post)
    assert cli.main(["doctor", "--probe-endpoints"]) == 0

    assert sorted(calls) == sorted([
        ("https://api.moonshot.ai/anthropic/v1/messages", "mk-test", ea.ENDPOINT_AGENTS["kimi"].default_model),
        ("https://api.deepseek.com/anthropic/v1/messages", "dk-test", ea.ENDPOINT_AGENTS["deepseek"].default_model),
    ])
    out = capsys.readouterr().out
    assert "kimi       ✓ probe ok: model kimi-k2.7-code answered" in out
    assert "deepseek   ✓ probe ok" in out
    assert "glm        - probe skipped: key unset" in out


def test_probe_flag_reports_auth_and_model_failures_distinctly_and_exits_1(
    hermetic_env: Path, endpoint_env, capsys: pytest.CaptureFixture
) -> None:
    stub_required(hermetic_env)

    def fake_post(url, key, model, *, timeout, max_body):
        if "moonshot" in url:
            return 401, _error("authentication_error", "invalid token"), {}
        return 404, _error("not_found_error", f"model: {model}"), {}

    endpoint_env.setattr(doctor, "_post_messages", fake_post)
    assert cli.main(["doctor", "--probe-endpoints"]) == 1
    captured = capsys.readouterr()
    assert "kimi       ✗ probe AUTH FAILED: 401 authentication_error" in captured.out
    assert "deepseek   ✗ probe MODEL ID NOT FOUND: model 'deepseek-v4-pro' rejected" in captured.out
    assert "default_model" in captured.out
    assert "endpoints not ok: kimi (auth), deepseek (model)" in captured.err
    # the profile is still written; probe failures gate only the exit code
    assert machine_yaml_path(hermetic_env.parent).exists()


def test_probe_failure_and_check_failure_both_reported(
    hermetic_env: Path, endpoint_env, capsys: pytest.CaptureFixture
) -> None:
    make_stub(hermetic_env, "git", 'echo "git version 2.43.0"')  # claude missing
    endpoint_env.setattr(doctor, "_post_messages", lambda *a, **kw: (500, "boom", {}))
    assert cli.main(["doctor", "--check", "--probe-endpoints"]) == 1
    err = capsys.readouterr().err
    assert "required entries missing: claude" in err
    assert "endpoints not ok: kimi (error), deepseek (error)" in err


@pytest.mark.parametrize(
    "exc, kind",
    [
        (ConnectionRefusedError(111, "refused"), doctor.PROBE_UNREACHABLE),
        (TimeoutError("timed out"), doctor.PROBE_UNREACHABLE),
        (http.client.BadStatusLine("garbage"), doctor.PROBE_UNREACHABLE),
        (http.client.IncompleteRead(b"x"), doctor.PROBE_UNREACHABLE),
        (ValueError("unknown url type"), doctor.PROBE_ERROR),
    ],
)
def test_probe_endpoint_never_raises(exc, kind) -> None:
    def raising(*a, **kw):
        raise exc

    got, detail = doctor.probe_endpoint(
        "kimi", {"MOONSHOT_API_KEY": "k"}, post=raising,
    )
    assert got == kind
    assert "api.moonshot.ai" in detail


def test_probe_endpoint_unresolvable_is_error_not_exception() -> None:
    kind, detail = doctor.probe_endpoint("kimi", {}, post=lambda *a, **kw: (200, "", {}))
    assert kind == doctor.PROBE_ERROR
    assert "MOONSHOT_API_KEY" in detail


def test_probe_endpoint_wall_clock_budget_bounds_a_stalled_call() -> None:
    def stalled(*a, **kw):
        time.sleep(2)
        return 200, _message(), {}

    t0 = time.monotonic()
    kind, detail = doctor.probe_endpoint(
        "kimi", {"MOONSHOT_API_KEY": "k"}, timeout=0.2, post=stalled,
    )
    assert time.monotonic() - t0 < 1.5
    assert kind == doctor.PROBE_UNREACHABLE
    assert "within 0.2s" in detail


class _ProbeHandler(http.server.BaseHTTPRequestHandler):
    """Loopback provider: /ok answers a message, /redirect bounces, /garbage
    breaks HTTP, /leak must never be reached (it is the redirect target)."""

    seen: list[dict] = []

    def log_message(self, *a):  # keep pytest output clean
        pass

    def do_POST(self):
        length = int(self.headers.get("content-length") or 0)
        body = self.rfile.read(length)
        self.seen.append({
            "path": self.path, "headers": dict(self.headers), "body": json.loads(body),
        })
        if self.path == "/ok/v1/messages":
            payload = _message().encode()
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        elif self.path == "/redirect/v1/messages":
            self.send_response(302)
            self.send_header("location", "/leak/v1/messages")
            self.send_header("content-length", "0")
            self.end_headers()
        elif self.path == "/garbage/v1/messages":
            self.wfile.write(b"this is not http\r\n")
            self.wfile.flush()
            self.close_connection = True
        else:
            self.send_response(200)
            self.send_header("content-length", "0")
            self.end_headers()


@pytest.fixture
def loopback_provider(monkeypatch: pytest.MonkeyPatch):
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _ProbeHandler)
    _ProbeHandler.seen = []
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    root = f"http://127.0.0.1:{server.server_port}"

    def spec(name: str, route: str) -> ea.EndpointAgentSpec:
        return ea.EndpointAgentSpec(
            name=name, provider="Loopback", base_url=f"{root}/{route}",
            key_env="LOOP_KEY", default_model="loop-model",
        )

    monkeypatch.setattr(ea, "ENDPOINT_AGENTS", {
        "ok": spec("ok", "ok"),
        "redirect": spec("redirect", "redirect"),
        "garbage": spec("garbage", "garbage"),
    })
    try:
        yield _ProbeHandler.seen
    finally:
        server.shutdown()
        server.server_close()


def test_real_post_sends_bearer_only_one_token_prompt(loopback_provider) -> None:
    kind, detail = doctor.probe_endpoint("ok", {"LOOP_KEY": "loop-secret"}, timeout=5)
    assert (kind, detail) == (doctor.PROBE_OK, "model loop-model answered (as 'kimi-k2.7-code')")
    [req] = loopback_provider
    headers = {k.lower(): v for k, v in req["headers"].items()}
    assert headers["authorization"] == "Bearer loop-secret"
    assert "x-api-key" not in headers  # no more permissive than the CLI's AUTH_TOKEN path
    assert headers["anthropic-version"] == doctor.ANTHROPIC_VERSION_HEADER
    assert req["body"] == {
        "model": "loop-model", "max_tokens": 1,
        "messages": [{"role": "user", "content": "hi"}],
    }


def test_real_post_refuses_redirects_and_does_not_resend_credentials(loopback_provider) -> None:
    kind, detail = doctor.probe_endpoint("redirect", {"LOOP_KEY": "s"}, timeout=5)
    assert kind == doctor.PROBE_ERROR
    assert "redirected (302)" in detail and "/leak/v1/messages" in detail
    assert [r["path"] for r in loopback_provider] == ["/redirect/v1/messages"]


def test_real_post_garbage_response_is_unreachable_not_a_crash(loopback_provider) -> None:
    kind, detail = doctor.probe_endpoint("garbage", {"LOOP_KEY": "s"}, timeout=5)
    assert kind == doctor.PROBE_UNREACHABLE
    assert "/garbage/v1/messages" in detail
