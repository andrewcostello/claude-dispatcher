"""D1 seals (P2): the base-pinned `roles:` policy, and the reader it must share.

Two properties dominate this file:

  * **Invariant 6** — the policy comes from the protected base's object store,
    never from a working tree. On the in-worktree gating path the working copy IS
    the checkout of the branch being judged, so a branch could otherwise supply
    the policy that judges it. `test_base_read_ignores_an_uncommitted_file` and
    `test_base_read_ignores_working_tree_edits` are that seal.
  * **Invariant 5 (one fact, one place)** — there must be exactly ONE base-pinned
    reader of `.dispatcher.yaml`. `test_load_policy_delegates_to_the_one_base_reader`
    pins `load_role_policy_from_base` to `repo_config.load_text_at_base` by
    substituting that seam: a second, private git read inside role_protocol
    bypasses the substitution and reddens the row.

Also sealed here: a repo that adds a `roles:` section today lands it in
`RepoConfig.unknown_keys` and its additions are silently DROPPED. That is a
protection the repo asked for and did not get, so it must not stay silent.

P4, 2026-08-10 — the config surface a target repo may write CHANGED
--------------------------------------------------------------------
The SEALS row is inverted to `ALLOW_ONLY_GLOBS`
(`tests/test_role_layout_coverage.py`, and the ruling recorded in
`tests/test_role_protocol_table.py`). `role_policy_from_mapping` refuses
`immutable_paths:` on any role that is not `DENY_GLOBS`, so `roles: seals:
immutable_paths:` stops being a legal thing for a repo to write and becomes a
typed `RoleProtocolError`. No behaviour in `role_policy_from_mapping` changes —
the same rule now catches one more role — but the SURFACE does, and a surface
change that only shows up in a target repo's config is the kind that goes
unnoticed, so it is sealed as a row rather than left as a note.

The knob that goes with it: after the inversion there is no per-repo and no
per-task way to NARROW the seal author's writable set either. `disputed_paths:`
is ADJUDICATE-only and `immutable_paths:` only ADDs to a deny set. P4's ruling
is that this is correct and deliberate — an allow-only role's writable set must
be the same fact in every repo, or the gate's answer depends on the config of
the repo it is judging — and that it costs nothing measurable: no
`.dispatcher.yaml` in this repository carries a `roles:` section, and no task
row in `features/` carries `immutable_paths:` or `role: seals` (measured
2026-08-10). Making `immutable_paths:` SUBTRACT from an allow set would be
coherent under `validate_override`'s stated invariant (removing an allow only
GROWS the protected set) and is explicitly NOT done here: it is new narrowing
syntax for a field documented as ADD-only, and no unit has asked for it.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from claude_dispatcher import repo_config, role_protocol
from claude_dispatcher.repo_config import (
    CONFIG_FILENAME,
    BaseConfigError,
    RepoConfigError,
)
from claude_dispatcher.role_protocol import (
    CONFIG_SECTION,
    PolicySource,
    Role,
    RoleProtocolError,
    built_in_policy,
    load_role_policy_from_base,
    role_policy_from_mapping,
)


def _git(args: list[str], cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=str(cwd), check=True, capture_output=True)


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(["init", "-q", "-b", "main"], repo)
    _git(["config", "user.email", "t@t"], repo)
    _git(["config", "user.name", "T"], repo)
    (repo / "README.md").write_text("seed\n", encoding="utf-8")
    _git(["add", "."], repo)
    _git(["commit", "-q", "-m", "base"], repo)
    return repo


def _commit(repo: Path, name: str, text: str) -> None:
    (repo / name).write_text(text, encoding="utf-8")
    _git(["add", "--", name], repo)
    _git(["commit", "-q", "-m", f"add {name}"], repo)


# --------------------------------------------------------------------------- #
# role_policy_from_mapping — strict, ADD-only, pure
# --------------------------------------------------------------------------- #


def test_absent_section_yields_the_compiled_in_defaults() -> None:
    """An absent section has exactly one meaning and it is the strict one: the
    compiled-in table is the strictest thing this module has, so defaults are
    safe here in a way an absent `risk:` list would not be.

    Red now: `role_policy_from_mapping` / `built_in_policy` raise
    NotImplementedError.
    Green when: None yields the built-in policy verbatim.
    """
    assert role_policy_from_mapping(None) == built_in_policy()
    assert role_policy_from_mapping(None).source is PolicySource.BUILT_IN_DEFAULTS


@pytest.mark.parametrize(
    "section, case",
    [
        (["bodies"], "list"),
        ("bodies", "string"),
        (7, "int"),
        (True, "bool"),
        # A key outside AUTHORABLE_ROLES: a typo must not silently drop the
        # protection the repo asked for.
        ({"implementer": {"immutable_paths": ["**/x/**"]}}, "unknown-role-key"),
        # A repo may not grant the legacy escape hatch a policy, and certainly
        # may not restrict it — that would change pre-protocol tasks' behaviour.
        ({"legacy": {"immutable_paths": ["**/x/**"]}}, "legacy-key"),
        # Per-role value must be a mapping.
        ({"bodies": ["**/x/**"]}, "role-value-list"),
        ({"bodies": "**/x/**"}, "role-value-string"),
        ({"bodies": None}, "role-value-null"),
        # Tolerating unknown NESTED keys would silently drop a protection.
        ({"bodies": {"deny": ["**/x/**"]}}, "unknown-nested-key"),
        ({"bodies": {"immutable_paths": ["**/x/**"], "extra": 1}}, "extra-nested-key"),
        # immutable_paths shape.
        ({"bodies": {"immutable_paths": "**/x/**"}}, "bare-string"),
        ({"bodies": {"immutable_paths": [""]}}, "blank-entry"),
        ({"bodies": {"immutable_paths": ["**/x/**", 3]}}, "int-entry"),
        ({"bodies": {"immutable_paths": None}}, "null-list"),
        # Removal is not expressible; a negation-shaped entry is an error.
        ({"bodies": {"immutable_paths": ["!**/tests/**"]}}, "negation-bang"),
        ({"bodies": {"immutable_paths": ["-**/tests/**"]}}, "negation-dash"),
        ({"bodies": {"immutable_paths": ["**/tests/**:allow"]}}, "negation-suffix"),
        # ADJUDICATE is ALLOW_ONLY: an addition there has no meaning.
        ({"adjudicate": {"immutable_paths": ["**/x/**"]}}, "adjudicate"),
        # P4 (2026-08-10): SEALS is ALLOW_ONLY too, for the same reason and with
        # the same consequence — see the seal below and the module docstring.
        ({"seals": {"immutable_paths": ["**/cmd/**"]}}, "seals"),
    ],
)
def test_a_malformed_roles_section_is_refused(section: object, case: str) -> None:
    """A policy-bearing value that is not the shape the author thought it was
    must fail, never be coerced (the `repo_config` `test:` precedent).

    **AMENDED BY P4, 2026-08-10** — the `seals` row is a CONFIG-SURFACE CHANGE,
    not a new strictness. `role_policy_from_mapping` already refuses
    `immutable_paths:` on any role whose rule is not `DENY_GLOBS` ("only a
    deny-based role has a deny set to add to"), and the SEALS inversion moves
    SEALS across that line. So a target repo that writes

        roles:
          seals:
            immutable_paths: ["**/cmd/**"]

    goes from a working, honoured addition to a typed `RoleProtocolError` at
    policy-load time. It fails loudly rather than silently dropping the
    protection the repo asked for, which is this file's whole doctrine, but the
    surface a repo may write DID change and this row is where that is stated.

    Nothing in this repository breaks: `.dispatcher.yaml` here carries no
    `roles:` section at all, no `features/*/tasks.yaml` row carries
    `immutable_paths:`, and none carries `role: seals` (all three measured
    2026-08-10).

    Red until the SEALS row is inverted.
    Green when: every shape above raises.
    Falsify: tolerate unknown nested keys as `repo_config` does at the top
    level — the two nested-key rows go red.
    """
    with pytest.raises(RoleProtocolError):
        role_policy_from_mapping(section)


def test_valid_additions_are_unioned_onto_the_compiled_in_globs() -> None:
    """Config may only ADD. The compiled-in entries are therefore already a
    floor, which is why this module needs no separate floor tier the way
    `risk.py` does.

    **AMENDED BY P4, 2026-08-10.** The second fixture was `seals:`, whose rule
    is now `ALLOW_ONLY_GLOBS` — an addition there is a typed error (the `seals`
    row of `test_a_malformed_roles_section_is_refused` above), so this seal
    would have gone red for a reason that has nothing to do with unioning.
    Retargeted to `scaffold:`, which is a deny role and stays one, and which
    exercises the identical property. The duplicate-entry half is preserved by
    naming a glob `scaffold` genuinely carries (`**/tests/**`) alongside a new
    one, so "redundant, not narrowing" is still asserted.

    Only TWO deny roles remain after the inversion, and both are used here, so
    this seal now covers the whole deny table rather than two of three.

    Red now: NotImplementedError.
    Green when: each role's globs are its defaults first, then the additions,
    with no default dropped and no duplicate appended.
    Falsify: replace the list instead of unioning — the `defaults ==
    globs[:len(defaults)]` assertion goes red.
    """
    defaults = built_in_policy()
    section = {
        "bodies": {"immutable_paths": ["**/fixtures/**"]},
        # An entry that duplicates a compiled-in glob is redundant, not narrowing.
        "scaffold": {"immutable_paths": ["**/tests/**", "**/cmd/**"]},
    }
    policy = role_policy_from_mapping(section)

    bodies_defaults = defaults.rule_for(Role.BODIES).globs
    bodies = policy.rule_for(Role.BODIES).globs
    assert bodies[: len(bodies_defaults)] == bodies_defaults
    assert bodies[len(bodies_defaults) :] == ("**/fixtures/**",)

    scaffold_defaults = defaults.rule_for(Role.SCAFFOLD).globs
    scaffold = policy.rule_for(Role.SCAFFOLD).globs
    assert "**/tests/**" in scaffold_defaults, (
        "the duplicate-entry fixture no longer duplicates anything; this seal "
        "would then stop asserting that a redundant addition is dropped"
    )
    assert scaffold[: len(scaffold_defaults)] == scaffold_defaults
    assert scaffold[len(scaffold_defaults) :] == ("**/cmd/**",)
    assert len(scaffold) == len(set(scaffold)), f"duplicate glob appended: {scaffold}"

    # Roles the section did not mention keep their defaults exactly.
    for role in (Role.SEALS, Role.ADJUDICATE, Role.LEGACY):
        assert policy.rule_for(role) == defaults.rule_for(role)


def test_an_empty_roles_mapping_is_the_defaults_not_an_empty_policy() -> None:
    """`roles: {}` must not read as "no restrictions" — invariant 4's exact
    failure mode.

    Red now: NotImplementedError.
    Green when: an empty mapping yields the compiled-in table unchanged.
    """
    policy = role_policy_from_mapping({})
    for role in Role:
        assert policy.rule_for(role).globs == built_in_policy().rule_for(role).globs


# --------------------------------------------------------------------------- #
# load_role_policy_from_base — one reader, no fallbacks
# --------------------------------------------------------------------------- #


def test_load_policy_delegates_to_the_one_base_reader(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Invariant 5: `repo_config.load_text_at_base` is THE base-pinned reader.

    Two readers of one file's gate policy would diverge on exactly the
    interesting cases (symlink, submodule, non-UTF-8) — and
    `risk.load_risk_config_from_base` already contains this read on an unmerged
    branch, so the pressure to write a second copy is real.

    Red now: NotImplementedError.
    Green when: the substituted seam is the source of the text, called with the
    repo root and the base ref.
    Falsify: inline a private `git show` in role_protocol — the substitution is
    bypassed, the injected section is never seen, and this goes red.
    """
    calls: list[tuple[str, str]] = []

    def _reader(repo_root, base_ref):
        calls.append((str(repo_root), base_ref))
        return "roles:\n  bodies:\n    immutable_paths: ['**/fixtures/**']\n"

    monkeypatch.setattr(repo_config, "load_text_at_base", _reader)
    policy = load_role_policy_from_base("/repo", "origin/main")

    assert calls == [("/repo", "origin/main")]
    assert policy.source is PolicySource.BASE_PINNED_CONFIG
    assert policy.base_ref == "origin/main"
    assert "**/fixtures/**" in policy.rule_for(Role.BODIES).globs


@pytest.mark.parametrize(
    "text, case",
    [
        (None, "no .dispatcher.yaml at base"),
        ("test: pytest -q\n", "file present, no roles: section"),
        ("", "empty file"),
    ],
)
def test_an_absent_section_at_base_yields_the_built_in_defaults(
    monkeypatch: pytest.MonkeyPatch, text: str | None, case: str
) -> None:
    """Red now: NotImplementedError.
    Green when: absence yields the compiled-in policy with source
    BUILT_IN_DEFAULTS (the strictest state, so it is safe).
    """
    monkeypatch.setattr(repo_config, "load_text_at_base", lambda *_a: text)
    policy = load_role_policy_from_base("/repo", "main")
    assert policy.source is PolicySource.BUILT_IN_DEFAULTS, case
    assert policy.rules == built_in_policy().rules


def test_an_unreadable_base_never_falls_back_to_defaults_or_to_head(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """"I could not read the policy" must not read as "the policy permits this",
    and a *silent* fall back to the defaults would also hide that the repo's
    additions were dropped.

    Red now: NotImplementedError is not BaseConfigError.
    Green when: the reader's failure propagates (the caller maps it to
    UNDETERMINED).
    Falsify: `except BaseConfigError: return built_in_policy()` — this goes red.
    """

    def _boom(*_a, **_k):
        raise BaseConfigError("fatal: bad revision 'main'")

    monkeypatch.setattr(repo_config, "load_text_at_base", _boom)
    with pytest.raises(BaseConfigError):
        load_role_policy_from_base("/repo", "main")


@pytest.mark.parametrize(
    "text, case",
    [
        ("roles: [bodies]\n", "section is not a mapping"),
        ("roles:\n  bodies:\n    immutable_paths: ['!**/tests/**']\n", "narrowing"),
        ("roles:\n  implementer:\n    immutable_paths: ['**/x/**']\n", "unknown role"),
        ("test: [unclosed\n", "malformed YAML"),
    ],
)
def test_an_invalid_section_at_base_raises_rather_than_degrading(
    monkeypatch: pytest.MonkeyPatch, text: str, case: str
) -> None:
    """Red now: NotImplementedError is not a ValueError.
    Green when: an invalid or unparseable policy raises rather than silently
    applying a weaker one.
    """
    monkeypatch.setattr(repo_config, "load_text_at_base", lambda *_a: text)
    with pytest.raises((RoleProtocolError, RepoConfigError)):
        load_role_policy_from_base("/repo", "main")


# --------------------------------------------------------------------------- #
# repo_config.load_text_at_base — the reader itself, against real git
# --------------------------------------------------------------------------- #


def test_base_read_returns_the_committed_text(git_repo: Path) -> None:
    """Red now: `load_text_at_base` raises NotImplementedError.
    Green when: it returns the file's text from the ref's object store.
    """
    _commit(git_repo, CONFIG_FILENAME, "test: pytest -q\n")
    assert repo_config.load_text_at_base(git_repo, "main") == "test: pytest -q\n"


def test_base_read_returns_none_when_the_tree_has_no_config(git_repo: Path) -> None:
    """Absence is one state with one meaning; the caller then applies its
    compiled-in defaults.

    Red now: NotImplementedError.
    Green when: a ref whose tree lacks the file yields None.
    """
    assert repo_config.load_text_at_base(git_repo, "main") is None


def test_base_read_ignores_an_uncommitted_file(git_repo: Path) -> None:
    """Invariant 6, the load-bearing half: a branch may not supply the policy
    that judges it. The working copy here HAS a config; the base tree does not.

    Red now: NotImplementedError.
    Green when: the working copy is not read — the answer is None.
    Falsify: implement with `Path(repo_root)/.dispatcher.yaml).read_text()` —
    this row goes red, and it is the only row that catches that mistake.
    """
    (git_repo / CONFIG_FILENAME).write_text(
        "roles:\n  bodies:\n    immutable_paths: []\n", encoding="utf-8"
    )
    assert repo_config.load_text_at_base(git_repo, "main") is None


def test_base_read_ignores_working_tree_edits(git_repo: Path) -> None:
    """The same invariant where the file exists at base and the branch edited it.

    Red now: NotImplementedError.
    Green when: the COMMITTED text comes back, not the edited one.
    """
    _commit(git_repo, CONFIG_FILENAME, "test: pytest -q\n")
    (git_repo / CONFIG_FILENAME).write_text("test: 'true'\n", encoding="utf-8")
    assert repo_config.load_text_at_base(git_repo, "main") == "test: pytest -q\n"


def test_base_read_raises_on_an_unresolvable_ref(git_repo: Path) -> None:
    """Red now: NotImplementedError is not BaseConfigError.
    Green when: an unresolvable ref raises BaseConfigError, never None.
    """
    with pytest.raises(BaseConfigError):
        repo_config.load_text_at_base(git_repo, "origin/does-not-exist")


def test_base_read_raises_on_a_symlinked_config(git_repo: Path) -> None:
    """A symlink is a redirect to somewhere the base does not govern.

    Red now: NotImplementedError.
    Green when: a non-regular-file entry raises BaseConfigError.
    Falsify: `git show ref:.dispatcher.yaml` alone — git prints the link target
    and this row goes red.
    """
    _commit(git_repo, "real.yaml", "test: pytest -q\n")
    (git_repo / CONFIG_FILENAME).symlink_to("real.yaml")
    _git(["add", "--", CONFIG_FILENAME], git_repo)
    _git(["commit", "-q", "-m", "symlink the config"], git_repo)
    with pytest.raises(BaseConfigError):
        repo_config.load_text_at_base(git_repo, "main")


def test_base_read_raises_on_a_submodule_entry(git_repo: Path) -> None:
    """A gitlink (mode 160000) at the config path is not a file this base
    governs either.

    Red now: NotImplementedError.
    Green when: a submodule entry raises BaseConfigError.
    """
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(git_repo),
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    subprocess.run(
        ["git", "update-index", "--add", "--cacheinfo", f"160000,{sha},{CONFIG_FILENAME}"],
        cwd=str(git_repo),
        check=True,
        capture_output=True,
    )
    _git(["commit", "-q", "-m", "gitlink at the config path"], git_repo)
    with pytest.raises(BaseConfigError):
        repo_config.load_text_at_base(git_repo, "main")


def test_base_read_raises_on_non_utf8_bytes(git_repo: Path) -> None:
    """Red now: NotImplementedError.
    Green when: undecodable bytes raise rather than returning None or mojibake.
    """
    (git_repo / CONFIG_FILENAME).write_bytes(b"test: \xff\xfe\n")
    _git(["add", "--", CONFIG_FILENAME], git_repo)
    _git(["commit", "-q", "-m", "binary config"], git_repo)
    with pytest.raises(BaseConfigError):
        repo_config.load_text_at_base(git_repo, "main")


# --------------------------------------------------------------------------- #
# `roles:` must not be silently dropped by repo_config.load
# --------------------------------------------------------------------------- #


def test_a_roles_section_is_not_reported_as_an_unknown_key(tmp_path: Path) -> None:
    """A repo that adds `roles:` today gets the compiled-in defaults and NO
    signal that its additions were dropped: the key lands in
    `RepoConfig.unknown_keys` and is ignored. A silently dropped protection is
    the failure this loader's strictness exists to avoid.

    Red now: `repo_config.load` still reports `roles` as unknown (the scaffold's
    own NOTE says so), so this fails on the live loader — not on a stub.
    Green when: `load` recognises the section (per the plan's wiring note, via
    `role_protocol.role_policy_from_mapping`).
    """
    (tmp_path / CONFIG_FILENAME).write_text(
        "test: pytest -q\n"
        f"{CONFIG_SECTION}:\n"
        "  bodies:\n"
        "    immutable_paths: ['**/fixtures/**']\n",
        encoding="utf-8",
    )
    cfg = repo_config.load(tmp_path)
    assert cfg.test == "pytest -q"
    assert CONFIG_SECTION not in cfg.unknown_keys, (
        "the repo asked for extra immutable paths and the loader dropped them "
        "into unknown_keys"
    )


def test_an_invalid_roles_section_makes_the_config_load_fail(tmp_path: Path) -> None:
    """The strictness half: an unparseable policy must not load as "no policy".

    Red now: `load` tolerates the section as an unknown key and returns
    successfully — again a live-loader failure, not a stub artefact.
    Green when: an invalid `roles:` section raises.
    Falsify: keep `roles` in the tolerated-unknown set — this goes red.
    """
    (tmp_path / CONFIG_FILENAME).write_text(
        f"{CONFIG_SECTION}:\n  implementer:\n    immutable_paths: ['**/x/**']\n",
        encoding="utf-8",
    )
    with pytest.raises((RepoConfigError, RoleProtocolError)):
        repo_config.load(tmp_path)


def test_a_narrowing_roles_section_makes_the_config_load_fail(tmp_path: Path) -> None:
    """A self-weakening policy is the defect class this project exists to close,
    so it must be refused at the loader, not merely at diff time.

    Red now: `load` returns successfully with `roles` in unknown_keys.
    Green when: the negation-shaped entry raises.
    """
    (tmp_path / CONFIG_FILENAME).write_text(
        f"{CONFIG_SECTION}:\n  bodies:\n    immutable_paths: ['!**/tests/**']\n",
        encoding="utf-8",
    )
    with pytest.raises((RepoConfigError, RoleProtocolError)):
        repo_config.load(tmp_path)


def test_the_module_reads_the_section_name_it_documents() -> None:
    """A rename of the section on one side only would make the loader and the
    parser disagree about where the policy lives.

    Red now: `role_policy_from_mapping` raises NotImplementedError.
    Green when: CONFIG_SECTION is the key both sides use.
    """
    assert CONFIG_SECTION == "roles"
    section = {"bodies": {"immutable_paths": ["**/fixtures/**"]}}
    doc = {CONFIG_SECTION: section}
    assert role_policy_from_mapping(doc.get(CONFIG_SECTION)) == (
        role_policy_from_mapping(section)
    )
