"""Object-store policy reads must not inherit a different Git interpretation."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from claude_dispatcher import repo_config
from test_verification_reentry import _events, _run_retry, repo


def _git(root: Path, *args: str, input_text: str | None = None) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, input=input_text, capture_output=True,
        text=True, check=True, timeout=30,
    ).stdout.strip()


def _repository(path: Path, command: str = "trusted-command") -> Path:
    path.mkdir()
    _git(path, "init", "-q", "-b", "main")
    _git(path, "config", "user.name", "Test")
    _git(path, "config", "user.email", "test@example.invalid")
    _git(path, "config", "core.hooksPath", "/dev/null")
    _git(path, "config", "commit.gpgsign", "false")
    (path / ".dispatcher.yaml").write_text(f"test: {command}\n", encoding="utf-8")
    _git(path, "add", ".dispatcher.yaml")
    _git(path, "commit", "-qm", "policy")
    return path


@pytest.mark.parametrize("kind", ["commit", "tree", "blob"])
def test_replace_refs_cannot_change_a_pinned_policy(tmp_path, monkeypatch, kind):
    monkeypatch.delenv("GIT_NO_REPLACE_OBJECTS", raising=False)
    root = _repository(tmp_path / "actual")
    base = _git(root, "rev-parse", "HEAD")
    (root / ".dispatcher.yaml").write_text("test: candidate-command\n", encoding="utf-8")
    _git(root, "add", ".dispatcher.yaml")
    _git(root, "commit", "-qm", "candidate")
    suffix = {"commit": "", "tree": "^{tree}", "blob": ":.dispatcher.yaml"}[kind]
    original = _git(root, "rev-parse", base + suffix)
    replacement = _git(root, "rev-parse", "HEAD" + suffix)
    _git(root, "replace", original, replacement)
    assert _git(root, "cat-file", "blob", base + ":.dispatcher.yaml") == "test: candidate-command"

    snapshot = repo_config.load_at_base(root, base)
    assert snapshot.config.test == "trusted-command"
    assert _git(root, "replace", "-l") == original, "reading must not delete the operator's refs"


@pytest.mark.parametrize("variable", ["GIT_DIR", "GIT_COMMON_DIR", "GIT_OBJECT_DIRECTORY"])
def test_inherited_repository_redirect_does_not_select_policy(tmp_path, monkeypatch, variable):
    actual = _repository(tmp_path / "actual")
    foreign = _repository(tmp_path / "foreign", "foreign-command")
    targets = {
        "GIT_DIR": foreign / ".git",
        "GIT_COMMON_DIR": foreign / ".git",
        "GIT_OBJECT_DIRECTORY": foreign / ".git" / "objects",
    }
    monkeypatch.setenv(variable, str(targets[variable]))
    before = dict(os.environ)
    snapshot = repo_config.load_at_base(actual, "main")
    assert snapshot.config.test == "trusted-command"
    assert dict(os.environ) == before, "isolate the subprocess, not the parent environment"


@pytest.mark.parametrize("variable", ["GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM"])
def test_inherited_config_files_are_not_loaded(tmp_path, monkeypatch, variable):
    root = _repository(tmp_path / "actual")
    malformed = tmp_path / "unrelated.gitconfig"
    malformed.write_text("[invalid configuration\n", encoding="utf-8")
    monkeypatch.delenv("GIT_CONFIG_NOSYSTEM", raising=False)
    monkeypatch.setenv(variable, str(malformed))
    assert repo_config.load_at_base(root, "main").config.test == "trusted-command"


def test_injected_config_parameters_do_not_change_the_read(tmp_path, monkeypatch):
    root = _repository(tmp_path / "actual")
    monkeypatch.setenv("GIT_CONFIG_PARAMETERS", "not a quoted config pair")
    assert repo_config.load_at_base(root, "main").config.test == "trusted-command"


@pytest.mark.parametrize("result_shape", ["completed-process", "tuple"])
def test_both_object_reads_receive_the_isolated_environment(monkeypatch, result_shape):
    overrides = {
        "GIT_DIR": "/foreign", "GIT_COMMON_DIR": "/foreign", "GIT_WORK_TREE": "/foreign",
        "GIT_OBJECT_DIRECTORY": "/foreign", "GIT_ALTERNATE_OBJECT_DIRECTORIES": "/foreign",
        "GIT_NAMESPACE": "foreign", "GIT_REPLACE_REF_BASE": "refs/foreign/",
        "GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "core.bare", "GIT_CONFIG_VALUE_0": "true",
        "GIT_CONFIG_PARAMETERS": "invalid", "GIT_CONFIG_GLOBAL": "/foreign",
        "GIT_CONFIG_SYSTEM": "/foreign", "GIT_CONFIG_NOSYSTEM": "0",
        "GIT_EXEC_PATH": "/foreign", "GIT_NO_LAZY_FETCH": "0",
        "GIT_OPTIONAL_LOCKS": "1", "GIT_TERMINAL_PROMPT": "1",
        "GIT_FUTURE_OVERRIDE": "unknown-to-this-build",
    }
    for key, value in overrides.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("ASSURANCE_KEEP_ME", "unchanged")
    before = dict(os.environ)
    calls = []

    def run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        assert kwargs["env"]["ASSURANCE_KEEP_ME"] == "unchanged"
        assert kwargs["env"]["PATH"] == before["PATH"]
        assert {k: v for k, v in kwargs["env"].items() if k.startswith("GIT_")} == {
            "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_NO_REPLACE_OBJECTS": "1", "GIT_NO_LAZY_FETCH": "1",
            "GIT_OPTIONAL_LOCKS": "0", "GIT_TERMINAL_PROMPT": "0",
        }
        if cmd == ["git", "ls-tree", "-z", "base:", "--", "policy"]:
            out = "100644 blob " + "1" * 40 + "\tpolicy\0"
        elif cmd == ["git", "cat-file", "blob", "base:policy"]:
            out = "policy from the object store"
        else:
            pytest.fail(f"unexpected object read: {cmd}")
        kwargs["env"]["ASSURANCE_KEEP_ME"] = "child-only mutation"
        if result_shape == "completed-process":
            return subprocess.CompletedProcess(cmd, 0, out, "")
        return 0, out, ""

    assert repo_config.blob_text_at("/repo", "base", "policy", run=run) == "policy from the object store"
    assert len(calls) == 2
    assert calls[0][1]["env"] is not calls[1][1]["env"]
    assert dict(os.environ) == before


@pytest.mark.parametrize("layout", ["checkout", "linked-worktree", "bare"])
def test_policy_read_preserves_supported_repository_layouts(tmp_path, layout):
    root = _repository(tmp_path / "actual")
    base = _git(root, "rev-parse", "HEAD")
    if layout == "linked-worktree":
        target = tmp_path / "linked"
        _git(root, "worktree", "add", "--quiet", "--detach", str(target), base)
    elif layout == "bare":
        target = tmp_path / "bare.git"
        _git(tmp_path, "clone", "--quiet", "--bare", "--no-hardlinks", str(root), str(target))
    else:
        target = root
    snapshot = repo_config.load_at_base(target, base)
    assert snapshot.base_ref == base and snapshot.present
    assert snapshot.config.test == "trusted-command"


def test_worker_replace_ref_cannot_turn_a_failing_test_into_done(repo, monkeypatch):
    monkeypatch.delenv("GIT_NO_REPLACE_OBJECTS", raising=False)
    bases = []

    def replace_policy(root, count, env):
        if count != 1:
            return
        bases.append(_git(root, "rev-parse", "main"))
        original = _git(root, "rev-parse", "main:.dispatcher.yaml")
        replacement = _git(root, "hash-object", "-w", "--stdin", input_text="test: 'true'\n")
        _git(root, "replace", original, replacement)

    rc, row, stages, spawns = _run_retry(
        repo, monkeypatch, origin="mechanical", regression=True, on_spawn=replace_policy,
    )
    assert rc != 0 and row["status"] == "Blocked", row
    assert row["mechanical_verification"] == "failed", row
    assert len(spawns) == 2
    events = [e.payload for e in _events(repo) if e.event_type == "verification_mechanical"]
    assert len(events) == 2 and all(p["outcome"] == "failed" for p in events)
    assert all(p["policy_base_sha"] == bases[0] for p in events)


def test_missing_policy_blob_does_not_fetch_from_a_promisor_remote(tmp_path):
    origin = _repository(tmp_path / "origin")
    root = tmp_path / "partial"
    _git(tmp_path, "clone", "--quiet", "--no-hardlinks", str(origin), str(root))
    base = _git(root, "rev-parse", "HEAD")
    blob = _git(root, "rev-parse", "HEAD:.dispatcher.yaml")
    object_file = root / ".git" / "objects" / blob[:2] / blob[2:]
    assert object_file.is_file(), "the fixture must remove a real loose object"
    object_file.rename(tmp_path / "withheld-policy-object")
    _git(root, "config", "core.repositoryformatversion", "1")
    _git(root, "config", "extensions.partialClone", "origin")
    _git(root, "config", "remote.origin.promisor", "true")

    with pytest.raises(repo_config.BaseConfigError):
        repo_config.load_at_base(root, base)
    check = subprocess.run(
        ["git", "--no-lazy-fetch", "cat-file", "-e", blob], cwd=root,
        capture_output=True, timeout=30,
    )
    assert check.returncode != 0, "a read must not silently provision missing policy"
