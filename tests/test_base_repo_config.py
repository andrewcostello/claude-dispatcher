"""The Git-backed config loader shares validation, never a candidate fallback."""

from __future__ import annotations

import subprocess
from dataclasses import FrozenInstanceError

import pytest

from claude_dispatcher import repo_config
from test_verification_reentry import _git, repo
from test_orchestrator_panel import _CRITICAL_TASK_YAML, _seed_yaml


@pytest.mark.parametrize("content,test", [
    (None, None), ("", None), ("# policy intentionally unset\n", None),
    ("future: enabled\n", None),
    ("test: '  python -m pytest  '\n", "  python -m pytest  "),
    ("test: |\n  first\n  second\n", "first\nsecond\n"),
    ("test: pytest\ntest_exclusion: pytest-deselect\npanel: {advisory: []}\n", "pytest"),
])
def test_snapshot_retains_source_presence_and_parser_semantics(repo, content, test):
    path = repo / repo_config.CONFIG_FILENAME
    if content is not None:
        path.write_text(content, encoding="utf-8")
    _seed_yaml(repo, _CRITICAL_TASK_YAML)
    base = _git(repo, "rev-parse", "HEAD")
    expected = repo_config.load(repo)
    path.write_text("test: candidate-command\n", encoding="utf-8")
    snapshot = repo_config.load_at_base(repo, base)
    assert snapshot.base_ref == base
    assert snapshot.present is (content is not None)
    assert snapshot.config == expected
    assert snapshot.config.test == test
    with pytest.raises(FrozenInstanceError):
        snapshot.base_ref = "changed"


@pytest.mark.parametrize("content", [
    "test: [unfinished\n", "test: true\n", "test: ''\n", "[not, a, mapping]\n",
    "test: first\ntest: second\n", "panel: {honour_classification_seats: 'false'}\n",
    "test_exclusion: unknown\n", "roles: {immutable_paths: ['!tests/**']}\n",
])
def test_invalid_base_policy_is_not_repaired_by_a_valid_working_copy(repo, content):
    path = repo / repo_config.CONFIG_FILENAME
    path.write_text(content, encoding="utf-8")
    _seed_yaml(repo, _CRITICAL_TASK_YAML)
    base = _git(repo, "rev-parse", "HEAD")
    with pytest.raises(repo_config.RepoConfigError):
        repo_config.load(repo)
    path.write_text("test: candidate-command\n", encoding="utf-8")
    with pytest.raises(repo_config.RepoConfigError) as err:
        repo_config.load_at_base(repo, base)
    assert base in str(err.value)


@pytest.mark.parametrize("kind", ["symlink", "directory", "non-utf8"])
def test_nonregular_or_undecodable_base_policy_is_not_absence(repo, kind):
    path = repo / repo_config.CONFIG_FILENAME
    if kind == "symlink":
        (repo / "policy.yaml").write_text("test: candidate-command\n", encoding="utf-8")
        path.symlink_to("policy.yaml")
    elif kind == "directory":
        path.mkdir()
        (path / "keep").write_text("not a policy file\n", encoding="utf-8")
    else:
        path.write_bytes(b"test: \xff\n")
    _seed_yaml(repo, _CRITICAL_TASK_YAML)
    base = _git(repo, "rev-parse", "HEAD")
    with pytest.raises(repo_config.BaseConfigError):
        repo_config.load_at_base(repo, base)


@pytest.mark.parametrize("base", [None, "", "   ", 123, "not-a-ref", "f" * 40])
def test_missing_or_unresolvable_base_does_not_load_candidate(repo, base):
    (repo / repo_config.CONFIG_FILENAME).write_text("test: candidate-command\n", encoding="utf-8")
    _seed_yaml(repo, _CRITICAL_TASK_YAML)
    with pytest.raises(repo_config.BaseConfigError):
        repo_config.load_at_base(repo, base)


@pytest.mark.parametrize("failure", [FileNotFoundError("git unavailable"), subprocess.TimeoutExpired("git", 30)])
def test_policy_read_failure_is_not_reported_as_absence(repo, monkeypatch, failure):
    (repo / repo_config.CONFIG_FILENAME).write_text("test: candidate-command\n", encoding="utf-8")
    _seed_yaml(repo, _CRITICAL_TASK_YAML)
    base = _git(repo, "rev-parse", "HEAD")

    def fail(*args, **kwargs):
        raise failure

    monkeypatch.setattr(repo_config, "_run_git", fail)
    with pytest.raises(repo_config.BaseConfigError):
        repo_config.load_at_base(repo, base)
