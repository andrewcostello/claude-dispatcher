"""Verify the per-repo .dispatcher.yaml loader.

The loader's contract is deliberately forgiving in one direction and strict
in the other: unknown top-level keys are tolerated and reported (future
schema sections must not break older dispatchers), while a malformed `test:`
value is always a hard error (silently skipping the verification gate would
defeat its purpose).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from claude_dispatcher import repo_config, yaml_io
from claude_dispatcher.repo_config import CONFIG_FILENAME, RepoConfig, RepoConfigError


def _write(tmp_path: Path, text: str) -> Path:
    cfg = tmp_path / CONFIG_FILENAME
    cfg.write_text(text, encoding="utf-8")
    return cfg


def test_absent_file_returns_empty_config(tmp_path: Path) -> None:
    """No .dispatcher.yaml is not an error — the caller journals a skip note."""
    cfg = repo_config.load(tmp_path)
    assert cfg == RepoConfig(test=None, unknown_keys=())


def test_happy_path_test_command(tmp_path: Path) -> None:
    _write(tmp_path, 'test: "pytest -q"\n')
    cfg = repo_config.load(tmp_path)
    assert cfg.test == "pytest -q"
    assert cfg.unknown_keys == ()


def test_test_command_stored_as_is_not_stripped(tmp_path: Path) -> None:
    """Surrounding whitespace on a real command is preserved verbatim."""
    _write(tmp_path, 'test: "  pytest -q  "\n')
    assert repo_config.load(tmp_path).test == "  pytest -q  "


def test_empty_file_returns_test_none(tmp_path: Path) -> None:
    _write(tmp_path, "")
    assert repo_config.load(tmp_path) == RepoConfig(test=None, unknown_keys=())


def test_comments_only_file_returns_test_none(tmp_path: Path) -> None:
    """ruamel returns None for a comments-only document; treat like empty."""
    _write(tmp_path, "# just a comment\n# another comment\n")
    assert repo_config.load(tmp_path) == RepoConfig(test=None, unknown_keys=())


def test_empty_string_test_rejected(tmp_path: Path) -> None:
    _write(tmp_path, 'test: ""\n')
    with pytest.raises(RepoConfigError):
        repo_config.load(tmp_path)


def test_whitespace_only_test_rejected(tmp_path: Path) -> None:
    _write(tmp_path, 'test: "   "\n')
    with pytest.raises(RepoConfigError):
        repo_config.load(tmp_path)


@pytest.mark.parametrize(
    "yaml_value",
    ["123", "true", "[a, b]", "{cmd: pytest}"],
    ids=["int", "bool", "list", "map"],
)
def test_non_string_test_rejected(tmp_path: Path, yaml_value: str) -> None:
    """Any non-str test value rejects — including bool, which YAML parses
    from bare `true` and which str-like checks can let slip through."""
    _write(tmp_path, f"test: {yaml_value}\n")
    with pytest.raises(RepoConfigError):
        repo_config.load(tmp_path)


def test_test_absent_but_other_keys_present(tmp_path: Path) -> None:
    _write(tmp_path, "e2e: make e2e\n")
    cfg = repo_config.load(tmp_path)
    assert cfg.test is None
    assert cfg.unknown_keys == ("e2e",)


def test_unknown_keys_reported_and_test_still_parsed(tmp_path: Path) -> None:
    """Future sections (e2e:, risk:) must never break an older loader."""
    _write(
        tmp_path,
        'risk: low\ntest: "pytest -q"\ne2e: make e2e\n',
    )
    cfg = repo_config.load(tmp_path)
    assert cfg.test == "pytest -q"
    assert cfg.unknown_keys == ("e2e", "risk")  # sorted


def test_root_list_rejected(tmp_path: Path) -> None:
    _write(tmp_path, "- a\n- b\n")
    with pytest.raises(RepoConfigError):
        repo_config.load(tmp_path)


def test_root_scalar_rejected(tmp_path: Path) -> None:
    _write(tmp_path, "just a string\n")
    with pytest.raises(RepoConfigError):
        repo_config.load(tmp_path)


def test_malformed_yaml_wrapped_with_path_and_cause(tmp_path: Path) -> None:
    cfg_path = _write(tmp_path, "test: [unclosed\n")
    with pytest.raises(RepoConfigError) as excinfo:
        repo_config.load(tmp_path)
    assert str(cfg_path) in str(excinfo.value)
    assert excinfo.value.__cause__ is not None


def test_error_messages_include_path(tmp_path: Path) -> None:
    cfg_path = _write(tmp_path, "test: 123\n")
    with pytest.raises(RepoConfigError) as excinfo:
        repo_config.load(tmp_path)
    assert str(cfg_path) in str(excinfo.value)


def test_repo_config_is_frozen(tmp_path: Path) -> None:
    cfg = repo_config.load(tmp_path)
    with pytest.raises(Exception):
        cfg.test = "mutated"  # type: ignore[misc]


def test_round_trip_preserves_unknown_keys_and_comments(tmp_path: Path) -> None:
    """The loader is read-only, but any future writer goes through yaml_io's
    round-trip mode — prove unknown keys and comments survive a load/dump
    cycle, and that repo_config.load of the same file reports them."""
    text = (
        "# header comment about this repo's gate\n"
        'test: "pytest -q"  # inline comment\n'
        "e2e: make e2e\n"
        "risk: low\n"
    )
    cfg_path = _write(tmp_path, text)

    doc = yaml_io.load(cfg_path)
    dumped = yaml_io.dumps(doc)
    assert "# header comment about this repo's gate" in dumped
    assert "# inline comment" in dumped
    assert "e2e" in dumped
    assert "risk" in dumped

    cfg = repo_config.load(tmp_path)
    assert cfg.test == "pytest -q"
    assert cfg.unknown_keys == ("e2e", "risk")
