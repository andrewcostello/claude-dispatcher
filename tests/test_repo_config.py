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


# --- panel.advisory (VG-5) ----------------------------------------------------


def test_panel_advisory_happy_path(tmp_path: Path) -> None:
    _write(tmp_path, 'test: "pytest -q"\npanel:\n  advisory: [grok]\n')
    cfg = repo_config.load(tmp_path)
    assert cfg.test == "pytest -q"
    assert cfg.panel_advisory == ("grok",)
    # `panel` is a KNOWN top-level key now — not reported as unknown.
    assert cfg.unknown_keys == ()


def test_panel_advisory_multiple_names_preserved_in_order(tmp_path: Path) -> None:
    _write(tmp_path, "panel:\n  advisory: [grok, foo]\n")
    cfg = repo_config.load(tmp_path)
    assert cfg.panel_advisory == ("grok", "foo")


def test_panel_absent_yields_empty_advisory(tmp_path: Path) -> None:
    _write(tmp_path, 'test: "pytest -q"\n')
    assert repo_config.load(tmp_path).panel_advisory == ()


def test_absent_file_yields_empty_advisory(tmp_path: Path) -> None:
    assert repo_config.load(tmp_path).panel_advisory == ()


def test_panel_without_advisory_yields_empty_tuple(tmp_path: Path) -> None:
    """`panel:` present but `advisory:` absent → (); the unknown inner key
    is reported as panel.<key>."""
    _write(tmp_path, "panel:\n  weight: 0.5\n")
    cfg = repo_config.load(tmp_path)
    assert cfg.panel_advisory == ()
    assert cfg.unknown_keys == ("panel.weight",)


def test_panel_advisory_empty_list_is_empty_tuple(tmp_path: Path) -> None:
    _write(tmp_path, "panel:\n  advisory: []\n")
    cfg = repo_config.load(tmp_path)
    assert cfg.panel_advisory == ()
    assert cfg.unknown_keys == ()


def test_panel_unknown_inner_keys_tolerated_and_reported(tmp_path: Path) -> None:
    _write(tmp_path, "panel:\n  advisory: [grok]\n  weight: 0.5\n")
    cfg = repo_config.load(tmp_path)
    assert cfg.panel_advisory == ("grok",)
    assert cfg.unknown_keys == ("panel.weight",)


def test_panel_inner_unknowns_sorted_with_top_level_unknowns(tmp_path: Path) -> None:
    _write(tmp_path, "e2e: make e2e\npanel:\n  weight: 1\n  advisory: [grok]\n")
    cfg = repo_config.load(tmp_path)
    assert cfg.unknown_keys == ("e2e", "panel.weight")


@pytest.mark.parametrize(
    "yaml_value",
    ["[grok]", '"grok"', "123", "true"],
    ids=["list", "string", "int", "bool"],
)
def test_panel_non_mapping_rejected(tmp_path: Path, yaml_value: str) -> None:
    cfg_path = _write(tmp_path, f"panel: {yaml_value}\n")
    with pytest.raises(RepoConfigError) as excinfo:
        repo_config.load(tmp_path)
    assert str(cfg_path) in str(excinfo.value)


@pytest.mark.parametrize(
    "yaml_value",
    ['"grok"', "123", "true", "{name: grok}"],
    ids=["string", "int", "bool", "map"],
)
def test_panel_advisory_non_list_rejected(tmp_path: Path, yaml_value: str) -> None:
    cfg_path = _write(tmp_path, f"panel:\n  advisory: {yaml_value}\n")
    with pytest.raises(RepoConfigError) as excinfo:
        repo_config.load(tmp_path)
    assert str(cfg_path) in str(excinfo.value)


@pytest.mark.parametrize(
    "entries",
    ['[""]', '["   "]', "[123]", "[true]", "[grok, 5]"],
    ids=["empty", "whitespace", "int", "bool", "mixed"],
)
def test_panel_advisory_bad_entries_rejected(tmp_path: Path, entries: str) -> None:
    """Edge 5 (strict half): every advisory entry must be a non-empty
    string — bool included, since YAML bare `true` is not a str."""
    cfg_path = _write(tmp_path, f"panel:\n  advisory: {entries}\n")
    with pytest.raises(RepoConfigError) as excinfo:
        repo_config.load(tmp_path)
    assert str(cfg_path) in str(excinfo.value)


def test_config_to_factory_path_produces_grok_reviewer(tmp_path: Path) -> None:
    """The config→factory pipeline (VG-5): a repo with
    `panel: {advisory: [grok]}` yields exactly one real GrokReviewer with
    the requested timeout — verified without ever running the panel live.
    """
    from claude_dispatcher import cross_family_reviewer as cfr

    _write(tmp_path, "panel:\n  advisory: [grok]\n")
    cfg = repo_config.load(tmp_path)
    assert cfg.panel_advisory == ("grok",)
    reviewers, unknown = cfr.advisory_reviewers_from_names(
        cfg.panel_advisory, timeout_seconds=123,
    )
    assert unknown == []
    assert len(reviewers) == 1
    assert isinstance(reviewers[0], cfr.GrokReviewer)
    assert reviewers[0].timeout_seconds == 123


# --- integration mode (PRF-1) -----------------------------------------------

def test_integration_absent_is_none(tmp_path: Path) -> None:
    """No `integration:` key → None, so the orchestrator uses its 'branch' default."""
    _write(tmp_path, 'test: "pytest -q"\n')
    assert repo_config.load(tmp_path).integration is None


def test_integration_pr(tmp_path: Path) -> None:
    _write(tmp_path, "integration: pr\n")
    cfg = repo_config.load(tmp_path)
    assert cfg.integration == "pr"
    assert cfg.unknown_keys == ()


def test_integration_branch(tmp_path: Path) -> None:
    _write(tmp_path, "integration: branch\n")
    assert repo_config.load(tmp_path).integration == "branch"


def test_integration_invalid_value_raises(tmp_path: Path) -> None:
    _write(tmp_path, "integration: gitflow\n")
    with pytest.raises(RepoConfigError) as ei:
        repo_config.load(tmp_path)
    assert "integration" in str(ei.value)


def test_integration_bool_rejected(tmp_path: Path) -> None:
    """A bare `true` is not 'branch'/'pr' → rejected (bool is not str)."""
    _write(tmp_path, "integration: true\n")
    with pytest.raises(RepoConfigError):
        repo_config.load(tmp_path)


# --- model_routing ------------------------------------------------------------


def test_model_routing_parsed_and_resolves(tmp_path):
    p = tmp_path / ".dispatcher.yaml"
    p.write_text(
        "model_routing:\n"
        "  Critical: claude-fable-5\n"
        "  high: claude-opus-4-8\n"
        "  default: claude-sonnet-5\n",
        encoding="utf-8",
    )
    cfg = repo_config.load(tmp_path)
    assert cfg.routed_model("Critical") == "claude-fable-5"
    assert cfg.routed_model("CRITICAL") == "claude-fable-5"   # case-insensitive
    assert cfg.routed_model("High") == "claude-opus-4-8"
    assert cfg.routed_model("Medium") == "claude-sonnet-5"    # falls to default
    assert cfg.routed_model(None) == "claude-sonnet-5"
    assert "model_routing" not in cfg.unknown_keys


def test_model_routing_absent_inherits(tmp_path):
    p = tmp_path / ".dispatcher.yaml"
    p.write_text("test: 'true'\n", encoding="utf-8")
    cfg = repo_config.load(tmp_path)
    assert cfg.routed_model("Critical") is None   # inherit CLI default


def test_model_routing_rejects_non_mapping(tmp_path):
    (tmp_path / ".dispatcher.yaml").write_text(
        "model_routing: [a, b]\n", encoding="utf-8")
    with pytest.raises(repo_config.RepoConfigError):
        repo_config.load(tmp_path)


def test_model_routing_rejects_blank_model(tmp_path):
    (tmp_path / ".dispatcher.yaml").write_text(
        "model_routing:\n  high: ''\n", encoding="utf-8")
    with pytest.raises(repo_config.RepoConfigError):
        repo_config.load(tmp_path)
