"""Fetch the pinned TypeScript parser into the dispatcher's own package.

An INSTALL-TIME step, and never a judgement-time one. Run it once per install::

    python3 -m claude_dispatcher.ts_parser_vendor

WHY THIS EXISTS AS A SEPARATE STEP
----------------------------------
`role_protocol.ts_parser_home` resolves the TypeScript parser out of the
dispatcher's own package directory and out of nowhere else — never the target
repository's `node_modules`, never `npx`, never an environment variable. That
rule needs a parser to actually be in that directory, and the operator's ruling
of 2026-08-10 says how it gets there: as a **separately-versioned artifact**
pinned by digest, not as a 9.1 MB blob in this repository's git history.

So the bytes arrive over the network once, at install time, and are pinned
twice over:

  * `TS_VENDORED_PARSER_TARBALL_INTEGRITY` gates the download, checked before
    the archive is opened, so a hostile or corrupted response is refused rather
    than parsed;
  * `TS_VENDORED_PARSER_SHA256` gates the extracted parser — and, far more
    importantly, is re-checked by `role_protocol._ts_prepared_parser` on **every
    process that renders a TypeScript signature.**

THIS MODULE IS NOT ON THE TRUST BOUNDARY, and that is deliberate
-----------------------------------------------------------------
It is not on `FLOOR_GLOBS` and does not need to be. Every check it performs is
performed again, from the bytes on disk, by the floored module — so a branch
that rewrote this file to fetch a poisoned parser, or to skip its checks
entirely, would produce a gate that FAULTS, not a gate that lies. This file can
decide whether the gate runs. It cannot decide what the gate answers.

That asymmetry is the reason the fetch is allowed to be a script at all. Every
alternative the scaffold rejected — `npx`, a global install, an env-var
override — failed because it put a *mutable, unfloorable* input on the path
that computes a verdict. A fetcher whose product is re-verified at use puts
nothing there.

WHAT IT DOES WITH NO NETWORK
----------------------------
It exits non-zero with a NAMED reason (`network-unreachable`) and writes
nothing. Never a silent absence: absence of the parser is
`ComparatorFault.HELPER_MISSING` at run time, which is blocking, so a machine
that could not fetch reports TypeScript as UNCHECKED rather than as clean.

It also never leaves a half-populated directory. The tarball is downloaded to
memory, every member is extracted to memory, and every digest is checked
BEFORE anything touches the destination — and the two files are then written
via a temporary name and `os.replace`, the parser LAST, so the presence of the
parser implies the license arrived. A run that fails at any point leaves the
destination exactly as it found it.

OFFLINE INSTALLS
----------------
`--from-tarball <path>` installs from a tarball obtained by any means. It is
not a trust hole: the file is checked against the same pinned
`TS_VENDORED_PARSER_TARBALL_INTEGRITY` and the same
`TS_VENDORED_PARSER_SHA256` as a download, so what it relaxes is *how the bytes
travelled*, never *which bytes are acceptable*.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import io
import os
import sys
import tarfile
import urllib.error
import urllib.request
from pathlib import Path

from . import role_protocol


#: Refusal to grow past this before a single byte is hashed. The pinned tarball
#: is 4.4 MB; the cap is generous enough to survive a repack and small enough
#: that a redirect to something enormous is a refusal rather than a machine with
#: no memory left. The integrity check would reject such a response anyway —
#: this only decides whether the rejection costs a download.
_MAX_TARBALL_BYTES = 64 * 1024 * 1024

#: How long the whole download may take. A hung connection must become a named
#: failure, not a wedged install.
_DOWNLOAD_TIMEOUT_SECONDS = 120


class VendorFailure(Exception):
    """A named refusal. `reason` is the machine-readable half.

    Named rather than free text because "the fetch did not happen" has several
    causes with different remedies — no network, a bad mirror, a read-only
    install directory — and an operator reading one line of output has to be
    able to tell which one they are in.
    """

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(f"{reason}: {message}")
        self.reason = reason
        self.message = message


def vendored_parser_directory() -> Path:
    """Where the artifact lands: the same rule `ts_parser_home` resolves by.

    `Path(role_protocol.__file__).parent / TS_HELPER_PACKAGE_DIR`, which is the
    dispatcher's installed location and nothing else — the CWD, the target
    repository and the environment do not appear. Written against
    `role_protocol.__file__` rather than this module's own `__file__` so that
    the fetcher cannot be moved out from under the resolver by a refactor; they
    have to name the same package or this stops being the same directory.

    On an editable install that is inside this checkout, and the two fetched
    files are gitignored. On a wheel install it is inside `site-packages`. In
    both cases it is a MUTABLE path that `scripts/check_body_branch.sh` cannot
    read, which is exactly why `role_protocol` re-hashes the parser at use.
    """
    return Path(role_protocol.__file__).parent / role_protocol.TS_HELPER_PACKAGE_DIR


def _npm_integrity(blob: bytes) -> str:
    """npm's `sha512-<base64>` spelling of a blob's digest."""
    return "sha512-" + base64.b64encode(hashlib.sha512(blob).digest()).decode("ascii")


def _download(url: str) -> bytes:
    """The tarball's bytes, or a named failure. No `npm`, no `npx`, no config.

    Plain HTTPS to the pinned absolute URL. npm is never invoked, because npm
    resolves a registry through its own config and reads a project-local
    `.npmrc` from the CWD — the exact "a location the branch influences"
    objection that rejected `npm root -g` in `role_protocol`'s design header.
    A URL constant has no such config.
    """
    request = urllib.request.Request(
        url, headers={"Accept": "application/octet-stream"}
    )
    try:
        with urllib.request.urlopen(
            request, timeout=_DOWNLOAD_TIMEOUT_SECONDS
        ) as response:
            blob = response.read(_MAX_TARBALL_BYTES + 1)
    except urllib.error.HTTPError as exc:
        raise VendorFailure(
            "registry-refused",
            f"{url} returned HTTP {exc.code} {exc.reason}",
        ) from exc
    except (urllib.error.URLError, OSError) as exc:
        raise VendorFailure(
            "network-unreachable",
            f"{url} could not be reached ({exc}). The parser is a "
            "separately-versioned artifact and this machine could not fetch "
            "it. Nothing was written. Until it is fetched, TypeScript is "
            "UNCHECKED and BLOCKING (ComparatorFault.HELPER_MISSING) — never "
            "clean. On an air-gapped machine, obtain the tarball elsewhere and "
            "pass --from-tarball; it is checked against the same pinned digests",
        ) from exc

    if len(blob) > _MAX_TARBALL_BYTES:
        raise VendorFailure(
            "tarball-too-large",
            f"{url} served more than {_MAX_TARBALL_BYTES} bytes",
        )
    return blob


def _members_from_tarball(blob: bytes) -> dict[str, bytes]:
    """The pinned members' bytes, after the tarball itself has been verified.

    The integrity check comes first, so `tarfile` is only ever handed bytes this
    build already vouched for. Members are read by exact name — no wildcard, no
    `extractall` — which is also why the classic tar path-traversal problem does
    not arise: nothing is ever written to a path the archive chose.
    """
    integrity = _npm_integrity(blob)
    if integrity != role_protocol.TS_VENDORED_PARSER_TARBALL_INTEGRITY:
        raise VendorFailure(
            "tarball-integrity-mismatch",
            f"the downloaded tarball hashes to {integrity}, not the pinned "
            f"{role_protocol.TS_VENDORED_PARSER_TARBALL_INTEGRITY}. Nothing "
            "was written. Do NOT edit the pin to match the download",
        )

    extracted: dict[str, bytes] = {}
    try:
        with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as archive:
            for member_name, local_name in (
                role_protocol.TS_VENDORED_PARSER_TARBALL_MEMBERS
            ):
                member = archive.extractfile(member_name)
                if member is None:
                    raise VendorFailure(
                        "member-missing",
                        f"the tarball has no readable {member_name}",
                    )
                extracted[local_name] = member.read()
    except tarfile.TarError as exc:
        raise VendorFailure("tarball-unreadable", f"{exc}") from exc
    return extracted


def _check_digests(extracted: dict[str, bytes]) -> None:
    """Both pinned sha256s, before anything is written.

    The parser's digest is the one that matters and it is checked again at every
    use; this call is the fetch-time half. The license's is checked here only —
    see `TS_VENDORED_PARSER_LICENSE_SHA256` for why it deliberately stays off
    the verdict path.
    """
    for local_name, expected in (
        (role_protocol.TS_VENDORED_PARSER, role_protocol.TS_VENDORED_PARSER_SHA256),
        (
            role_protocol.TS_VENDORED_PARSER_LICENSE,
            role_protocol.TS_VENDORED_PARSER_LICENSE_SHA256,
        ),
    ):
        blob = extracted[local_name]
        digest = hashlib.sha256(blob).hexdigest()
        if digest != expected:
            raise VendorFailure(
                "artifact-digest-mismatch",
                f"{local_name} hashes to {digest}, not the pinned {expected}. "
                "Nothing was written",
            )

    parser = extracted[role_protocol.TS_VENDORED_PARSER]
    if len(parser) != role_protocol.TS_VENDORED_PARSER_BYTES:
        raise VendorFailure(
            "artifact-size-mismatch",
            f"{role_protocol.TS_VENDORED_PARSER} is {len(parser)} bytes, not "
            f"the pinned {role_protocol.TS_VENDORED_PARSER_BYTES}",
        )


def _install(extracted: dict[str, bytes], directory: Path) -> None:
    """Write the verified members, license first and parser LAST.

    Each file goes to a temporary name in the destination directory and is then
    `os.replace`d into place, which is atomic on the same filesystem. Ordering
    puts the parser last so that a crash between the two writes cannot produce a
    directory holding a parser and no license — the state that would let a
    half-finished fetch look further along than it is.

    It is belt-and-braces rather than the guarantee: `ts_parser_home` demands
    all three files and refuses with HELPER_MISSING naming the one that is
    absent, so a partial directory is a named fault either way. This ordering
    means the partial state is also the *conservative* one.
    """
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise VendorFailure(
            "destination-unwritable",
            f"{directory} could not be created ({exc}). A wheel install under "
            "a system prefix may need elevation, or a re-install as the owning "
            "user",
        ) from exc

    staged: list[Path] = []
    try:
        for local_name in (
            role_protocol.TS_VENDORED_PARSER_LICENSE,
            role_protocol.TS_VENDORED_PARSER,
        ):
            target = directory / local_name
            temporary = directory / f".{local_name}.incoming-{os.getpid()}"
            staged.append(temporary)
            temporary.write_bytes(extracted[local_name])
            os.replace(temporary, target)
            staged.remove(temporary)
    except OSError as exc:
        raise VendorFailure(
            "destination-unwritable",
            f"writing into {directory} failed ({exc})",
        ) from exc
    finally:
        for leftover in staged:
            try:
                leftover.unlink()
            except OSError:  # pragma: no cover - best-effort cleanup
                pass


def _already_installed(directory: Path) -> bool:
    """Is the floored artifact already in place?

    Asked through `role_protocol._verify_vendored_parser` — the SAME function
    the verdict path uses — rather than through a second digest comparison
    written here. A fetcher that decided "already installed" by its own rule
    could report success over a parser the gate will refuse, which is a report
    that costs an operator the afternoon.
    """
    if not (directory / role_protocol.TS_VENDORED_PARSER_LICENSE).is_file():
        return False
    try:
        role_protocol._verify_vendored_parser(directory)
    except role_protocol.ComparatorUnavailable:
        return False
    return True


def vendor(from_tarball: Path | None = None, force: bool = False) -> Path:
    """Fetch, verify and install. Returns the directory. Raises `VendorFailure`.

    Idempotent: an already-verified artifact is left alone and no network is
    touched, so a re-run on an offline machine that is already provisioned
    succeeds instead of failing. `force` re-fetches regardless.
    """
    directory = vendored_parser_directory()
    if not force and _already_installed(directory):
        return directory

    if from_tarball is not None:
        try:
            blob = from_tarball.read_bytes()
        except OSError as exc:
            raise VendorFailure(
                "tarball-unreadable", f"{from_tarball} could not be read ({exc})"
            ) from exc
    else:
        blob = _download(role_protocol.TS_VENDORED_PARSER_TARBALL_URL)

    extracted = _members_from_tarball(blob)
    _check_digests(extracted)
    _install(extracted, directory)

    # Verified once more, from the bytes now on disk and through the function
    # the gate itself calls. A fetcher that reported success on a write it
    # never confirmed would be a stamp file with extra steps.
    role_protocol._verify_vendored_parser(directory)
    return directory


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python3 -m claude_dispatcher.ts_parser_vendor",
        description=(
            "Fetch the pinned TypeScript parser into the dispatcher's package "
            "directory. Install-time step; never run during a judgement."
        ),
    )
    parser.add_argument(
        "--from-tarball",
        type=Path,
        default=None,
        metavar="PATH",
        help=(
            "install from a local npm tarball instead of downloading. Checked "
            "against the same pinned digests"
        ),
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="re-fetch even if a verified parser is already installed",
    )
    args = parser.parse_args(argv)

    try:
        directory = vendor(from_tarball=args.from_tarball, force=args.force)
    except VendorFailure as exc:
        print(f"ts-parser-vendor FAILED [{exc.reason}] {exc.message}", file=sys.stderr)
        return 1

    print(
        f"ts-parser-vendor OK typescript {role_protocol.TS_VENDORED_PARSER_VERSION} "
        f"-> {directory}"
    )

    # The parser is in place and verified; whether the GATE can run also needs
    # the helper entry point, which is a different commit's. Report it rather
    # than imply a working comparator, so an operator is never told the gate is
    # ready by a step that only installed half of it.
    try:
        role_protocol.ts_parser_home()
    except role_protocol.ComparatorUnavailable as exc:
        print(
            f"ts-parser-vendor NOTE the gate is not yet runnable: "
            f"{exc.fault.value}: {exc.message}",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
