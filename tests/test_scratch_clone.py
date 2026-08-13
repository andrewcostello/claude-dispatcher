"""Unit DF-4 seals — the P1 scaffold's IMPLEMENTED surface only.

The specification is `src/claude_dispatcher/scratch_clone.py`'s module
docstring; the rulings argued there are not relitigated here. The five
control-flow faces are P3 stubs, so this file seals what P1 ships: the
refusal table and its totality guard, the error record, and — because the
first panel review blocked on it — :func:`scrubbed_git_env`, proven against
a LIVE sentinel repository per routing variable, not by inspecting a dict.

Measured under: ``6293f424`` (`main`, the branch base), git 2.51.0,
CPython 3.13.7, 2026-08-13. The sentinel repos live in pytest ``tmp_path``
sandboxes; that is the point of them.

The sentinel seals encode the panel's requirement verbatim: point each
repository-routing variable at a sentinel real repository and prove that
neither quarantine creation (``git init``) nor the probe's question
(``rev-parse --absolute-git-dir`` / ``--git-common-dir``) reads through or
modifies the sentinel once the environment is scrubbed. One control seal
keeps the teeth visible: UNscrubbed, ``GIT_DIR`` makes the same probe
attest the sentinel — so a scrub regression cannot pass as "the probe just
works".
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from claude_dispatcher import scratch_clone as sc
from claude_dispatcher.scratch_clone import (
    GIT_ENV_PINS,
    Refusal,
    ScratchCloneError,
    refusal_message,
    scrubbed_git_env,
)

# ---------------------------------------------------------------------------
# Refusal table
# ---------------------------------------------------------------------------


def test_refusal_message_total_over_enum() -> None:
    """Every member has a row; every row is a non-empty REFUSED line."""
    for refusal in Refusal:
        message = refusal_message(refusal)
        assert message
        assert "REFUSED" in message


def test_refusal_message_appends_detail() -> None:
    message = refusal_message(Refusal.COPY_FAILED, detail="ENOSPC on /tmp")
    assert message.endswith("[ENOSPC on /tmp]")
    assert refusal_message(Refusal.COPY_FAILED) == message[: -len(" [ENOSPC on /tmp]")]


def test_totality_guard_raises_with_the_asked_refusal(monkeypatch) -> None:
    """A missing row raises, and the error carries the refusal that was
    ASKED about — the caller's state is not misreported as a table bug."""
    monkeypatch.setattr(
        sc,
        "_REFUSAL_MESSAGES",
        {k: v for k, v in sc._REFUSAL_MESSAGES.items() if k is not Refusal.PURGE_FAILED},
    )
    with pytest.raises(ScratchCloneError) as excinfo:
        refusal_message(Refusal.PURGE_FAILED)
    assert excinfo.value.refusal is Refusal.PURGE_FAILED


def test_error_carries_refusal_detail_and_cleanup_flag() -> None:
    err = ScratchCloneError(
        Refusal.SEVER_INCOMPLETE, detail="sub/.git", cleanup_failed=True
    )
    assert err.refusal is Refusal.SEVER_INCOMPLETE
    assert err.detail == "sub/.git"
    assert err.cleanup_failed is True
    assert "[sub/.git]" in str(err)


# ---------------------------------------------------------------------------
# scrubbed_git_env — the dict-level contract
# ---------------------------------------------------------------------------

#: The routing variables the panel named, plus the numbered GIT_CONFIG rows
#: an exact-name list would miss. The scrub is drop-by-prefix, so this list
#: seals coverage without becoming the enumeration the module refuses to be.
ROUTING_VARS = [
    "GIT_DIR",
    "GIT_COMMON_DIR",
    "GIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_CONFIG",
    "GIT_CONFIG_COUNT",
    "GIT_CONFIG_KEY_0",
    "GIT_CONFIG_VALUE_0",
    "GIT_CEILING_DIRECTORIES",
    "GIT_TEMPLATE_DIR",
    "GIT_NAMESPACE",
    "GIT_DISCOVERY_ACROSS_FILESYSTEM",
]


@pytest.mark.parametrize("name", ROUTING_VARS)
def test_scrub_drops_each_routing_variable(name: str) -> None:
    base = {name: "/somewhere/real/.git", "PATH": "/usr/bin"}
    env = scrubbed_git_env(base)
    assert name not in env


def test_scrub_pins_config_away_from_files_and_keeps_the_rest() -> None:
    base = {"PATH": "/usr/bin", "HOME": "/home/x", "LANG": "C.UTF-8"}
    env = scrubbed_git_env(base)
    for key, value in GIT_ENV_PINS.items():
        assert env[key] == value
    assert env["PATH"] == "/usr/bin"
    assert env["HOME"] == "/home/x"
    assert env["LANG"] == "C.UTF-8"


def test_scrub_is_pure_and_defaults_to_os_environ(monkeypatch) -> None:
    base = {"GIT_DIR": "/x/.git", "PATH": "/usr/bin"}
    before = dict(base)
    scrubbed_git_env(base)
    assert base == before, "scrub mutated its input"

    monkeypatch.setenv("GIT_DIR", "/y/.git")
    assert "GIT_DIR" not in scrubbed_git_env()


# ---------------------------------------------------------------------------
# scrubbed_git_env — sentinel seals (live git, per routing variable)
# ---------------------------------------------------------------------------


def _git(args: list[str], cwd: Path, env: dict[str, str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=cwd, env=env, capture_output=True, text=True
    )


def _clean_env() -> dict[str, str]:
    # The suite's own environment must not leak into the seals it runs.
    return scrubbed_git_env()


@pytest.fixture
def sentinel(tmp_path: Path) -> Path:
    """A real repo with a commit — the thing no subprocess may reach."""
    repo = tmp_path / "sentinel"
    repo.mkdir()
    env = _clean_env()
    assert _git(["init", "-q", "."], repo, env).returncode == 0
    (repo / "f.txt").write_text("original\n")
    assert _git(["add", "f.txt"], repo, env).returncode == 0
    assert (
        _git(
            ["-c", "user.email=s@s", "-c", "user.name=s", "commit", "-qm", "one"],
            repo,
            env,
        ).returncode
        == 0
    )
    return repo


def _sentinel_fingerprint(repo: Path) -> tuple[str, str, str]:
    env = _clean_env()
    head = _git(["rev-parse", "HEAD"], repo, env).stdout
    status = _git(["status", "--porcelain"], repo, env).stdout
    refs = _git(["for-each-ref"], repo, env).stdout
    return head, status, refs


def _contaminated(sentinel: Path, name: str) -> dict[str, str]:
    """A base env carrying `name` pointed at the sentinel, per variable."""
    targets = {
        "GIT_DIR": str(sentinel / ".git"),
        "GIT_COMMON_DIR": str(sentinel / ".git"),
        "GIT_WORK_TREE": str(sentinel),
        "GIT_INDEX_FILE": str(sentinel / ".git" / "index"),
        "GIT_OBJECT_DIRECTORY": str(sentinel / ".git" / "objects"),
        "GIT_ALTERNATE_OBJECT_DIRECTORIES": str(sentinel / ".git" / "objects"),
    }
    return {**_clean_env(), name: targets[name]}


SENTINEL_VARS = [
    "GIT_DIR",
    "GIT_COMMON_DIR",
    "GIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
]


def test_unscrubbed_git_dir_reroutes_the_probe(sentinel: Path, tmp_path: Path) -> None:
    """The control: without the scrub the probe attests the SENTINEL.

    This is the measured escape channel 1, kept red-able on purpose: if it
    ever starts answering in-clone, git's discovery rules changed and every
    scrub seal below is attesting a property git now grants for free.
    """
    clone = tmp_path / "clone-control"
    clone.mkdir()
    assert _git(["init", "-q", "--template=", "."], clone, _clean_env()).returncode == 0
    dirty = _contaminated(sentinel, "GIT_DIR")
    answer = _git(["rev-parse", "--absolute-git-dir"], clone, dirty).stdout.strip()
    assert answer == str((sentinel / ".git").resolve())


@pytest.mark.parametrize("name", SENTINEL_VARS)
def test_scrubbed_probe_lands_in_clone_and_sentinel_untouched(
    sentinel: Path, tmp_path: Path, name: str
) -> None:
    """Per variable: scrubbed, BOTH probe questions answer the clone, and
    the sentinel's HEAD/status/refs are byte-identical afterwards."""
    clone = tmp_path / f"clone-{name.lower()}"
    clone.mkdir()
    assert _git(["init", "-q", "--template=", "."], clone, _clean_env()).returncode == 0
    before = _sentinel_fingerprint(sentinel)

    env = scrubbed_git_env(_contaminated(sentinel, name))
    quarantine = (clone / ".git").resolve()
    for question in ("--absolute-git-dir", "--git-common-dir"):
        probe = _git(["rev-parse", question], clone, env)
        assert probe.returncode == 0, probe.stderr
        # --git-common-dir answers RELATIVE to the invocation dir ('.git');
        # the module contract requires resolving it against that dir.
        answer = Path(probe.stdout.strip())
        if not answer.is_absolute():
            answer = clone / answer
        assert answer.resolve() == quarantine

    assert _sentinel_fingerprint(sentinel) == before


@pytest.mark.parametrize("name", SENTINEL_VARS)
def test_scrubbed_init_creates_here_and_sentinel_untouched(
    sentinel: Path, tmp_path: Path, name: str
) -> None:
    """Per variable: scrubbed, ``git init`` creates the quarantine AT THE
    TARGET (measured unscrubbed: GIT_DIR made init create NO .git at the
    target and reinitialize the sentinel) and the sentinel is unchanged."""
    fresh = tmp_path / f"fresh-{name.lower()}"
    fresh.mkdir()
    before = _sentinel_fingerprint(sentinel)

    env = scrubbed_git_env(_contaminated(sentinel, name))
    init = _git(["init", "-q", "--template=", "."], fresh, env)
    assert init.returncode == 0, init.stderr
    assert (fresh / ".git").is_dir(), "init did not create the quarantine here"

    assert _sentinel_fingerprint(sentinel) == before


# ---------------------------------------------------------------------------
# The five faces are stubs, and say which phase owns their bodies
# ---------------------------------------------------------------------------


def test_stubs_refuse_loudly_and_name_the_body_phase(tmp_path: Path) -> None:
    with pytest.raises(NotImplementedError, match="cp -a"):
        sc.make_scratch_clone(tmp_path / "a", tmp_path / "b")
    for stub in (
        lambda: sc.assert_isolated(tmp_path),
        lambda: sc.swap_in(None, "x", b""),
        lambda: sc.swap_back(None, None),
        lambda: sc.main(["a", "b"]),
    ):
        with pytest.raises(NotImplementedError, match="P3"):
            stub()
