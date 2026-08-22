"""Seals for `runs_dir` resolution: CLI flag > .dispatcher.yaml > built-in default.

Why this is sealed at all: `docs/runs/` is gitignored AND lives inside a
disposable worktree, so the audit trail dies with the worktree unless it is
pointed elsewhere. The literal used to be an argparse default in five
subcommands, so a move changed the WRITER and left the READERS on the old path —
a silent breakage of the audit tooling, which is the failure these rows guard.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from claude_dispatcher import cli, repo_config as rc


def _repo(tmp_path: Path, config: str | None = None) -> Path:
    if config is not None:
        (tmp_path / ".dispatcher.yaml").write_text(config)
    return tmp_path


def test_the_default_literal_lives_in_exactly_one_place() -> None:
    """Measured under: re-add `default="docs/runs"` to any subcommand and this
    reddens. Five copies is how the writer and the readers came apart.
    """
    src = Path(cli.__file__).read_text()
    assert 'default="docs/runs"' not in src
    assert src.count('"--runs-dir"') + src.count("'--runs-dir'") >= 5
    assert rc.DEFAULT_RUNS_DIR == "docs/runs"


def test_absent_config_falls_back_to_the_default_under_the_repo_root(
    tmp_path: Path,
) -> None:
    got = rc.resolve_runs_dir(None, repo_root=_repo(tmp_path))
    assert got == (tmp_path / "docs/runs").resolve()


def test_a_configured_relative_path_resolves_against_the_repo_root(
    tmp_path: Path,
) -> None:
    """Not cwd. Every worktree of a repo must agree on one location, which is the
    whole point — a cwd-relative answer would put each worktree's runs somewhere
    else and re-create the problem this key exists to fix.

    Measured under: resolve against `Path.cwd()` instead and this reddens.
    """
    root = _repo(tmp_path, "runs_dir: ../shared-runs\n")
    got = rc.resolve_runs_dir(None, repo_root=root)
    assert got == (tmp_path.parent / "shared-runs").resolve()


def test_a_configured_absolute_path_is_used_verbatim(tmp_path: Path) -> None:
    root = _repo(tmp_path, f"runs_dir: {tmp_path / 'abs-runs'}\n")
    assert rc.resolve_runs_dir(None, repo_root=root) == (tmp_path / "abs-runs").resolve()


def test_the_cli_flag_beats_the_config(tmp_path: Path) -> None:
    """Measured under: check the config before `explicit` and this reddens. An
    operator typing the flag must win, or the flag is decoration.
    """
    root = _repo(tmp_path, "runs_dir: /should/not/win\n")
    got = rc.resolve_runs_dir(str(tmp_path / "flag-wins"), repo_root=root)
    assert got == (tmp_path / "flag-wins").resolve()


def test_none_and_the_default_string_are_not_the_same_thing(tmp_path: Path) -> None:
    """The distinction the whole mechanism rests on: argparse must pass None when
    the flag is OMITTED, or a config value could never beat the built-in default.

    Measured under: set the argparse defaults back to "docs/runs" and the first
    row here reddens; pass "docs/runs" explicitly and it is honoured as a flag,
    which is correct and is why the two must stay distinguishable.
    """
    root = _repo(tmp_path, "runs_dir: ../configured\n")
    assert rc.resolve_runs_dir(None, repo_root=root) == \
        (tmp_path.parent / "configured").resolve()
    assert rc.resolve_runs_dir("docs/runs", repo_root=root) == \
        Path("docs/runs").resolve()


def test_an_unreadable_config_falls_back_rather_than_raising(tmp_path: Path) -> None:
    """This decides where a LOG goes. Refusing to run because the config is broken
    would be worse than writing it in the usual place — and `load` already raises
    loudly for every caller that gates on config validity.

    Measured under: drop the except clause and this reddens.
    """
    root = _repo(tmp_path, "runs_dir: [not, a, string]\n")
    assert rc.resolve_runs_dir(None, repo_root=root) == (tmp_path / "docs/runs").resolve()


def test_a_blank_or_non_string_runs_dir_is_a_load_error(tmp_path: Path) -> None:
    """`load` itself must still be strict: a repo that asked for a location and
    typo'd it should hear about it from every caller that validates config.
    """
    for bad in ("runs_dir: ''\n", "runs_dir: 3\n", "runs_dir: true\n"):
        (tmp_path / ".dispatcher.yaml").write_text(bad)
        with pytest.raises(rc.RepoConfigError, match="runs_dir"):
            rc.load(tmp_path)


def test_runs_dir_is_a_known_key_and_not_reported_unknown(tmp_path: Path) -> None:
    """Measured under: omit it from `known_top_level` and this reddens — the key
    would land in `unknown_keys`, be journaled as unrecognised, and be ignored.
    """
    (tmp_path / ".dispatcher.yaml").write_text("runs_dir: ../x\ntest: pytest\n")
    cfg = rc.load(tmp_path)
    assert cfg.runs_dir == "../x"
    assert "runs_dir" not in cfg.unknown_keys


def test_a_subcommand_reads_the_resolved_absolute_path(
    tmp_path: Path, monkeypatch, capsys,
) -> None:
    """End-to-end through `cli.main`, not through the resolver alone.

    `args.func` is bound when the parser is built, so a monkeypatched command
    module would not be reached — the honest check is that a REAL subcommand acts
    on the resolved path. `status` names the directory it looked in, so its own
    error message is the evidence: it must name the config-resolved ABSOLUTE path,
    not `./docs/runs`.

    Measured under: set the argparse default back to "docs/runs" and this reddens
    with `.../wt-d1/docs/runs/...`; leave `args.runs_dir` relative and it reddens
    with a cwd-relative path.
    """
    root = _repo(tmp_path, "runs_dir: ../resolved-here\n")
    monkeypatch.chdir(root)
    monkeypatch.setattr(cli.wt_mod, "detect_repo_root", lambda *a, **k: root)

    assert cli.main(["status", "some-run-id"]) != 0
    err = capsys.readouterr().err
    expected = (tmp_path.parent / "resolved-here" / "some-run-id").resolve()
    assert str(expected) in err, err
    assert "docs/runs" not in err
