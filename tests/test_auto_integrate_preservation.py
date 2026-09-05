"""Integration must preserve files it does not own, using real Git merges."""

from pathlib import Path

import pytest

from claude_dispatcher import auto_integrate as ai
from test_auto_integrate import _git, _make_feat_branch, repo


@pytest.mark.parametrize("local_path", ["notes.txt", "design/draft.txt"])
def test_unrelated_untracked_files_survive_integration(repo: Path, local_path: str):
    _make_feat_branch(repo, "feat/work", {"feature.txt": "feature\n"}, "feature")
    local = repo / local_path
    local.parent.mkdir(parents=True, exist_ok=True)
    local.write_bytes(b"uncommitted design\x00\xff\n")
    before = local.read_bytes()
    yaml_path = repo / "bay-session-tasks.yaml"
    yaml_path.write_text("project: TEST\ntasks: []\n# live dispatcher state\n")
    yaml_before = yaml_path.read_bytes()

    result = ai.integrate(
        repo_root=repo, yaml_path=yaml_path,
        base_branch="main", feat_branch="feat/work", task_key="PRESERVE-1",
        log=lambda _: None,
    )

    assert result.status == "integrated", result.detail
    assert local.read_bytes() == before
    assert yaml_path.read_bytes() == yaml_before
    assert (repo / "feature.txt").read_text() == "feature\n"
    assert _git(["ls-files", "--", local_path], cwd=repo) == ""
    assert _git(["stash", "list"], cwd=repo) == ""


@pytest.mark.parametrize("ignored", [False, True])
@pytest.mark.parametrize("local_path", ["draft.txt", "design/draft.txt", "odd\nname.txt"])
def test_colliding_local_files_block_without_data_loss(
    repo: Path, local_path: str, ignored: bool,
):
    if ignored:
        (repo / ".gitignore").write_text(f"/{local_path}\n")
        _git(["add", ".gitignore"], cwd=repo)
        _git(["commit", "-m", "ignore local draft"], cwd=repo)
    _git(["checkout", "-b", "feat/collision"], cwd=repo)
    local = repo / local_path
    local.parent.mkdir(parents=True, exist_ok=True)
    local.write_text("feature version\n")
    _git(["add", "-f", "--", local_path], cwd=repo)
    _git(["commit", "-m", "feature version"], cwd=repo)
    _git(["checkout", "main"], cwd=repo)
    local.parent.mkdir(parents=True, exist_ok=True)
    local.write_text("irreplaceable local draft\n")
    before = local.read_bytes()
    head_before = _git(["rev-parse", "HEAD"], cwd=repo)
    yaml_path = repo / "bay-session-tasks.yaml"
    yaml_path.write_text("project: TEST\ntasks: []\n# live dispatcher state\n")
    yaml_before = yaml_path.read_bytes()

    result = ai.integrate(
        repo_root=repo, yaml_path=yaml_path,
        base_branch="main", feat_branch="feat/collision", task_key="PRESERVE-2",
        log=lambda _: None,
    )

    assert result.status == "skipped-conflict", result.detail
    assert result.merge_sha is None
    assert local.read_bytes() == before
    assert yaml_path.read_bytes() == yaml_before
    assert _git(["rev-parse", "HEAD"], cwd=repo) == head_before
    assert not (repo / ".git" / "MERGE_HEAD").exists()
    assert _git(["stash", "list"], cwd=repo) == ""


@pytest.mark.parametrize("kind", ["directory", "parent file", "parent symlink"])
def test_file_directory_and_symlink_collisions_are_preserved(repo: Path, kind: str):
    _make_feat_branch(repo, "feat/work", {"design/draft.txt": "feature\n"}, "feature")
    if kind == "directory":
        local = repo / "design/draft.txt/local.txt"
        local.parent.mkdir(parents=True)
        local.write_text("local\n")
    elif kind == "parent file":
        local = repo / "design"
        local.write_text("local\n")
    else:
        local = repo.parent / "outside.txt"
        local.write_text("local\n")
        (repo / "design").symlink_to(local)
    head = _git(["rev-parse", "HEAD"], cwd=repo)

    result = ai.integrate(
        repo_root=repo, yaml_path=repo / "bay-session-tasks.yaml",
        base_branch="main", feat_branch="feat/work", task_key="PRESERVE-3",
        log=lambda _: None,
    )

    assert result.status == "skipped-conflict", result.detail
    assert local.read_text() == "local\n"
    assert _git(["rev-parse", "HEAD"], cwd=repo) == head
    if kind == "parent symlink":
        assert (repo / "design").is_symlink()


def test_failed_addition_preflight_does_not_start_merge(repo: Path, monkeypatch):
    _make_feat_branch(repo, "feat/work", {"feature.txt": "feature\n"}, "feature")
    original_run = ai._run
    commands = []

    def fail_additions(args, *, cwd):
        commands.append(args)
        if "--diff-filter=A" in args:
            return 1, "", "injected diff failure"
        return original_run(args, cwd=cwd)

    monkeypatch.setattr(ai, "_run", fail_additions)
    head = _git(["rev-parse", "HEAD"], cwd=repo)
    result = ai.integrate(
        repo_root=repo, yaml_path=repo / "bay-session-tasks.yaml",
        base_branch="main", feat_branch="feat/work", task_key="PRESERVE-4",
        log=lambda _: None,
    )
    assert result.status == "error"
    assert "injected diff failure" in result.detail
    assert not any(args[1] in {"merge", "stash", "clean"} for args in commands)
    assert _git(["rev-parse", "HEAD"], cwd=repo) == head


@pytest.mark.parametrize("ignored", [False, True])
def test_rename_destination_is_checked_as_an_addition(repo: Path, ignored: bool):
    if ignored:
        (repo / ".gitignore").write_text("/archive.txt\n")
        _git(["add", ".gitignore"], cwd=repo)
        _git(["commit", "-m", "ignore local archive"], cwd=repo)
    _git(["checkout", "-b", "feat/rename"], cwd=repo)
    _git(["mv", "-f", "README.md", "archive.txt"], cwd=repo)
    _git(["commit", "-m", "rename readme"], cwd=repo)
    _git(["checkout", "main"], cwd=repo)
    local = repo / "archive.txt"
    local.write_text("local archive\n")
    head = _git(["rev-parse", "HEAD"], cwd=repo)

    result = ai.integrate(
        repo_root=repo, yaml_path=repo / "bay-session-tasks.yaml",
        base_branch="main", feat_branch="feat/rename", task_key="PRESERVE-5",
        log=lambda _: None,
    )

    assert result.status == "skipped-conflict", result.detail
    assert "local file would be overwritten" in result.detail
    assert local.read_text() == "local archive\n"
    assert (repo / "README.md").is_file()
    assert _git(["rev-parse", "HEAD"], cwd=repo) == head
