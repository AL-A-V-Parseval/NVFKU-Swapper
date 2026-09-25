"""A verified copy of the model kept inside the project tree.

The project deliberately does not commit ``nvngx_dlssnr.dll``: it is NVIDIA's
proprietary 158 MiB binary, redistributing it in a source tree would be both
enormous and a redistribution nobody asked for, and ``vendor/README.md`` records
that. What this module adds is the layer between "committed" and "downloaded onto
this machine": a *vendored mirror*, one file under ``<project_root>/vendor/weights``
that a checkout can carry from machine to machine and that every operation here
still checks against the one pinned digest.

Three properties shape the implementation, and each exists because of a specific
way a 158 MiB file goes wrong:

*   **A vendored copy is judged by its digest, never by its presence.** The same
    158 MiB can be a build that was measured stable or one that reports success on
    every evaluate and then crashes the game, so ``inspect`` reports which one is
    on disk. It also never raises: its caller is a UI that has to render something
    whether the directory is missing, the file is missing, unreadable, or simply
    not the pinned build.
*   **A sync does not download unless it has to.** The pinned archive is ~104 MiB
    and the DLL ~158 MiB, so a routine "make sure the mirror is there" call must be
    free when the mirror is already correct. ``sync`` returns the existing state
    without touching the fetcher.
*   **The destination is written atomically and then read back.** Copying to a
    temporary file beside the target and ``os.replace``-ing it means an interrupted
    copy can never leave a partial 158 MiB file that a later ``inspect`` would
    describe as present, and re-hashing the destination after the move catches a
    short write that the source file's earlier verification could not see.

The digest this compares against is read from :mod:`nvfku.weights` at call time
rather than imported as a constant. That keeps this module and ``weights`` from
ever disagreeing about the pinned build, and it is what lets the tests substitute a
digest for content they generated instead of fabricating a 165,840,496-byte file.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from . import weights
from .paths import Paths, human_size

#: ``<project_root>/vendor/weights``.
#:
#: Derived from ``__file__`` rather than written out absolutely, so a checkout
#: still finds its mirror after being moved. The file is ``engine/nvfku/mirror.py``:
#: its parent is the package, and the project root is two levels above that.
VENDOR_DIR: Path = Path(__file__).resolve().parents[2] / "vendor" / "weights"

#: The name a vendored copy must have. Bound to the same constant the rest of the
#: tool installs under rather than re-spelled, because two spellings of a file name
#: this load-bearing would eventually drift apart.
MODEL_NAME = weights.MODEL_NAME


@dataclass
class MirrorState:
    """What the vendored copy is right now, as statements a UI can render.

    ``present`` and ``verified`` are separate on purpose: "there is a file here"
    and "it is the build this project measured" are different facts, and a user
    deciding whether to trust a tree needs both. ``sha256`` and ``size`` are
    ``None`` when they could not be read, which is itself a state rather than an
    error.
    """

    path: Path | None
    present: bool
    verified: bool
    sha256: str | None
    size: int | None
    url: str

    def describe(self) -> str:
        """One sentence a user can read without knowing any of the above."""
        if not self.present:
            # No location is named here: with nothing on disk there is no path to
            # name, and inventing the default one would be wrong as soon as a
            # caller inspected somewhere else.
            return (
                "nothing has been vendored yet; the pinned build can be synced from "
                f"{self.url}"
            )
        where = self.path
        if self.sha256 is None:
            return f"a file exists at {where} but could not be read, so it is unverified"
        amount = human_size(self.size) if self.size is not None else "unknown size"
        if self.verified:
            return f"vendored copy at {where} is verified: {amount}, sha256 {self.sha256}"
        return (
            f"vendored copy at {where} is {amount}, sha256 {self.sha256}, which is not "
            f"the pinned {weights.TESTED_SHA256} and must not be used"
        )


def inspect(vendor_dir: Path | None = None) -> MirrorState:
    """Report on the vendored copy, for any failure mode, without raising.

    Every way this can go wrong -- the directory was never created, the file was
    deleted, a permission bit changed, the bytes are a different build -- comes
    back as a state, because one of them happening must not blank a screen that
    only meant "nothing has been vendored yet".
    """

    directory = Path(vendor_dir) if vendor_dir is not None else VENDOR_DIR
    target = directory / MODEL_NAME
    url = weights.RTX50_SOURCE.url

    try:
        size = target.stat().st_size
    except OSError:
        # Missing directory, missing file and denied stat all mean the same thing
        # to a caller: there is nothing usable here. `path` is None so a renderer
        # cannot print a location as if it held a file.
        return MirrorState(
            path=None, present=False, verified=False, sha256=None, size=None, url=url
        )

    try:
        digest = weights._digest(target)
    except OSError:
        # It is on disk but cannot be read, which is *not* the same as absent: the
        # UI should say the file is there and unverified rather than offer to
        # overwrite something the user can see in their file manager.
        return MirrorState(
            path=target, present=True, verified=False, sha256=None, size=size, url=url
        )

    return MirrorState(
        path=target,
        present=True,
        verified=digest == weights.TESTED_SHA256,
        sha256=digest,
        size=size,
        url=url,
    )


def sync(
    source: weights.Source | None = None,
    *,
    vendor_dir: Path | None = None,
    paths: Paths | None = None,
    logger=print,
    force: bool = False,
) -> MirrorState:
    """Populate the vendored copy from the pinned archive.

    Reuses :func:`nvfku.weights.download` rather than fetching anything itself, so
    the archive cache, the proxy handling and the digest check on arrival stay in
    one place. ``force`` re-copies even when the mirror is already verified; it is
    for repairing a file the user suspects, not for bypassing verification, which
    always runs.
    """
    source = source if source is not None else weights.RTX50_SOURCE
    directory = Path(vendor_dir) if vendor_dir is not None else VENDOR_DIR
    target = directory / MODEL_NAME

    # The digest checked is the project's pinned constant rather than
    # `source.build.sha256`, because this one slot holds the single build that was
    # measured and `inspect` judges by the same constant; a source naming some
    # other build must not be able to make the two disagree. Reading it from
    # `weights` at call time is also what lets the tests pin a digest for content
    # they generated, with no 158 MiB fixture and no network.
    expected = weights.TESTED_SHA256

    # The property that protects a 104 MiB download: a sync that finds the pinned
    # build already in place reports it and stops before it touches the network.
    if not force:
        current = inspect(directory)
        if current.verified:
            logger(f"  present  {target} is already verified")
            return current

    if paths is None:
        # Only this branch needs the state layer: `inspect` and `prune` are the
        # UI's calls and have no reason to touch a state root at all. `Paths.discover`
        # is cheap and creates nothing, so a caller that will not download is not
        # paying for a cache it never uses.
        paths = Paths.discover()

    logger(f"  source   {source.url}")
    cached = weights.download(paths, source, logger=logger)

    directory.mkdir(parents=True, exist_ok=True)
    # Written beside the target, then moved: a crash halfway through a 158 MiB copy
    # must not leave a file that a later `inspect` has to call "present". The
    # temporary name is dotted so a user looking at the tree sees it is not the
    # model, and `os.replace` is atomic within one filesystem.
    fd, scratch_name = tempfile.mkstemp(
        prefix=".nvngx-", suffix=".part", dir=str(directory)
    )
    os.close(fd)
    scratch = Path(scratch_name)
    try:
        with cached.open("rb") as src, scratch.open("wb") as dst:
            shutil.copyfileobj(src, dst, length=1024 * 256)
        os.replace(scratch, target)
    except OSError as exc:
        scratch.unlink(missing_ok=True)
        raise weights.WeightsError(
            f"could not write the vendored copy: {exc}"
        ) from None
    except BaseException:
        # A KeyboardInterrupt or any other abort still must not leave a `.part`
        # beside the target for a later sync to trip over.
        scratch.unlink(missing_ok=True)
        raise

    # Read the destination back instead of trusting the copy that produced it. The
    # source was verified when it was downloaded, but the bytes that matter now are
    # the ones in the vendor tree, and a short write is exactly what only shows up
    # here. On disagreement the destination is deleted rather than left looking
    # like a mirror somebody could install from.
    try:
        digest = weights._digest(target)
    except OSError as exc:
        target.unlink(missing_ok=True)
        raise weights.WeightsError(
            f"the vendored copy could not be read back: {exc}"
        ) from None
    if digest != expected:
        target.unlink(missing_ok=True)
        raise weights.WeightsError(
            "the vendored copy does not match the pinned digest\n"
            f"  expected {expected}\n"
            f"  got      {digest}\n"
            f"  {target} was deleted rather than left in place"
        )

    size = target.stat().st_size
    logger(f"  vendored {target} ({human_size(size)})")
    # Built from the digest just read rather than by re-inspecting: hashing 158 MiB
    # a second time to restate a fact already in hand would be pure cost.
    return MirrorState(
        path=target,
        present=True,
        verified=True,
        sha256=digest,
        size=size,
        url=source.url,
    )


def prune(vendor_dir: Path | None = None) -> bool:
    """Delete the vendored copy, reporting whether there was one.

    Only this file is removed. The download cache, the journal and any copy a game
    already carries are left alone: a user asking for 158 MiB back should not have
    to wonder what else the command took.
    """
    directory = Path(vendor_dir) if vendor_dir is not None else VENDOR_DIR
    target = directory / MODEL_NAME
    try:
        target.unlink()
    except FileNotFoundError:
        # Also the empty-directory case, which is the common one on a fresh clone.
        return False
    except OSError as exc:
        # Reported rather than answered with `False`: "nothing was deleted" would
        # be technically true and would hide a permission problem the user can fix.
        raise weights.WeightsError(f"could not remove {target}: {exc}") from None
    return True
