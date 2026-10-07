#!/usr/bin/env python3
"""Build the three distributable formats: tar.gz, .deb and AppImage.

Why this exists rather than `dpkg-deb` and `linuxdeploy`:

* `dpkg-deb` is not installable here (no sudo, and this is an Arch-family machine),
  so the `.deb` is assembled directly. A `.deb` is an `ar` archive holding
  `debian-binary`, `control.tar.gz` and `data.tar.gz` — all three are documented
  formats that Python already writes, so no tool is required.
* `linuxdeploy` would bundle a Linux desktop stack the AppImage does not need.
  Flutter's own bundle is already self-contained apart from the GTK stack, which
  AppImages conventionally take from the host.

**None of the three formats contains the NVIDIA model.** It is 158 MiB, it has no
licence permitting redistribution, and Debian's policy forbids it in a `.deb`
outright. It is fetched and verified on first use instead:

    nvfku model --mirror-sync

`--with-model` exists for a private build where that is acceptable. It refuses to
combine with `--format deb`, because that combination is the one that causes real
trouble downstream.

Usage:
    python3 tools/package.py --format tar
    python3 tools/package.py --format deb
    python3 tools/package.py --format appimage
    python3 tools/package.py                    # all three
"""

from __future__ import annotations

import argparse
import gzip
import fcntl
import hashlib
import io
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import uuid
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / "engine"
APP_BUNDLE = ROOT / "app/build/linux/x64/release/bundle"
VENDOR_WEIGHTS = ROOT / "vendor/weights"
MANIFEST_NAME = "nvngx_dlssnr.dll"

PACKAGE = "nvfku-swapper"
SUMMARY = "Install DLSS 5 Neural Rendering into Linux games"
HOMEPAGE = "https://github.com/AL-A-V-Parseval/NVFKU-Swapper"
MAINTAINER = "AL-A-V-Parseval <jackyji070122@gmail.com>"

#: The GTK stack the Flutter bundle links but does not ship. Named for Debian, since
#: that is what the `.deb` control file needs; an AppImage takes them from the host
#: and the tarball's launcher does too.
DEB_DEPENDS = "libgtk-3-0, libblkid1, libepoxy0, libglib2.0-0, libgcc-s1"
_BUILD_ID = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]


def artifact_path(out_dir: Path, name: str) -> Path:
    target = out_dir / name
    if target.exists() or target.is_symlink():
        raise SystemExit(f"refusing to overwrite existing artifact: {target}")
    return target

sys.path.insert(0, str(ENGINE))


def version() -> str:
    from nvfku import __version__

    return __version__


def sha256_of(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def engine_constants() -> tuple[str, int, str]:
    """The digest, size and source URL of the one build this project trusts.

    Read from the engine rather than repeated here, so the packager cannot drift
    from what the installer considers correct.
    """
    from nvfku import weights

    return weights.TESTED_SHA256, weights.TESTED_SIZE, weights.RTX50_SOURCE.url


def verify_model(
    expected_sha: str,
    expected_size: int,
    *,
    path: Path | None = None,
) -> Path:
    """The verified model, or a refusal naming exactly what is wrong.

    Takes its path so the refusal branches can be tested without a 158 MiB fixture.
    This is the one check in this file that is not copying, and it is the reason the
    file exists: every build of `nvngx_dlssnr.dll` is the same size, so only the
    digest separates the measured build from one that reports success on every
    evaluate and then crashes the game minutes into play.
    """
    model = path or (VENDOR_WEIGHTS / MANIFEST_NAME)
    if not model.is_file():
        raise SystemExit(
            f"no vendored model at {model}\n"
            "  Run `python3 -m nvfku model --mirror-sync` first, or drop "
            "--with-model to package without it."
        )
    size = model.stat().st_size
    if size != expected_size:
        raise SystemExit(
            f"the vendored model is {size} bytes, expected {expected_size}\n"
            f"  {model}\n"
            "  Delete it and re-run `model --mirror-sync`."
        )
    digest = sha256_of(model)
    if digest != expected_sha:
        raise SystemExit(
            "the vendored model does not match the digest this build was tested with\n"
            f"  expected {expected_sha}\n"
            f"  got      {digest}\n"
            f"  {model}\n"
            "  Packaging refuses rather than shipping a build that will crash games."
        )
    return model


def ignore_engine(_directory: str, names: list[str]) -> set[str]:
    return {n for n in names if n in {"__pycache__", "tests"} or n.endswith(".pyc")}


# --------------------------------------------------------------------- icon

#: Drawn as SVG and rasterised, rather than shipped as a binary blob nobody can
#: edit. The mark is the two arrows this tool is about: files swapped in, files
#: swapped back out.
_ICON_SVG = """<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}"
     viewBox="0 0 256 256">
  <rect width="256" height="256" rx="56" fill="#0A0A0B"/>
  <rect x="8" y="8" width="240" height="240" rx="48" fill="none"
        stroke="#6CC10A" stroke-opacity="0.35" stroke-width="3"/>
  <g stroke="#6CC10A" stroke-width="16" stroke-linecap="round"
     stroke-linejoin="round" fill="none">
    <path d="M78 104 h84 l-24 -26"/>
    <path d="M178 152 h-84 l24 26"/>
  </g>
</svg>
"""


def write_icon(destination: Path, size: int = 256) -> Path:
    """Rasterise the mark to a PNG. Returns the file written."""
    svg = destination.with_suffix(".svg")
    svg.write_text(_ICON_SVG.format(size=size), encoding="utf-8")
    for tool, args in (
        ("rsvg-convert", ["-w", str(size), "-h", str(size)]),
        ("convert", ["-background", "none", "-resize", f"{size}x{size}"]),
    ):
        if shutil.which(tool) is None:
            continue
        result = subprocess.run(
            [tool, *args, str(svg), str(destination)],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0 and destination.is_file():
            return destination
    raise SystemExit(
        "no SVG rasteriser found (need rsvg-convert or ImageMagick convert); an "
        "AppImage requires an icon and this script will not ship a broken one"
    )


# ------------------------------------------------------------------- payload


def payload_tree(staging: Path, *, with_model: bool) -> None:
    """Lay out the files every format shares.

    The arrangement is a prefix, so each format decides where the prefix goes:
    `/usr/lib/nvfku` for the `.deb`, the AppDir root for the AppImage, the archive
    root for the tarball.
    """
    staging.mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        ENGINE / "nvfku", staging / "engine/nvfku", ignore=ignore_engine, dirs_exist_ok=True
    )
    shutil.copytree(APP_BUNDLE, staging / "app", dirs_exist_ok=True)
    for name in ("README.md", "README.zh.md", "LICENSE", "THIRD_PARTY_NOTICES.md"):
        if (ROOT / name).is_file():
            shutil.copy2(ROOT / name, staging / name)
    if (ROOT / "docs").is_dir():
        shutil.copytree(ROOT / "docs", staging / "docs", dirs_exist_ok=True)
    if with_model:
        model = verify_model(*engine_constants()[0:2])
        (staging / "vendor/weights").mkdir(parents=True, exist_ok=True)
        shutil.copy2(model, staging / "vendor/weights" / MANIFEST_NAME)


#: The shell wrapper every format uses. `$HERE` so the tree is relocatable: a
#: release is unpacked wherever the user wants it.
_LAUNCHER = """#!/bin/sh
# NVFKU-Swapper. Resolves its own directory so the tree can live anywhere.
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
if [ -x "$HERE/app/nvfku_ui" ]; then
  export NVFKU_ENGINE="$HERE"
  exec "$HERE/app/nvfku_ui" "$@"
fi
echo "NVFKU-Swapper: app/nvfku_ui is missing from $HERE" >&2
exit 1
"""

_CLI = """#!/bin/sh
# NVFKU-Swapper command line.
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
PYTHONPATH="$HERE/engine${PYTHONPATH:+:$PYTHONPATH}" exec python3 -m nvfku "$@"
"""

_DESKTOP = """[Desktop Entry]
Type=Application
Name=NVFKU-Swapper
Comment={summary}
Exec={exec}
Icon={icon}
Terminal=false
Categories=Utility;Settings;
Keywords=DLSS;NVIDIA;Proton;Steam;ReShade;OptiScaler;
"""


def write_launchers(staging: Path) -> None:
    for name, text in (("nvfku", _LAUNCHER), ("nvfku-cli", _CLI)):
        path = staging / name
        path.write_text(text, encoding="utf-8")
        path.chmod(0o755)


# ------------------------------------------------------------------- tar.gz


def build_tar(out_dir: Path, *, with_model: bool) -> Path:
    stamp = _BUILD_ID
    name = f"{PACKAGE}-{version()}-{stamp}"
    archive = artifact_path(out_dir, f"{name}.tar.gz")
    with tempfile.TemporaryDirectory(prefix="nvfku-tar-") as raw:
        staging = Path(raw) / PACKAGE
        payload_tree(staging, with_model=with_model)
        write_launchers(staging)
        (staging / "RELEASE.json").write_text(
            _release_json(with_model, "tar.gz"), encoding="utf-8"
        )
        print("  compressing")
        with tarfile.open(archive, "w:gz") as tar:
            tar.add(staging, arcname=PACKAGE)
    return archive


# ----------------------------------------------------------------------- deb


def _ar_member(name: str, data: bytes) -> bytes:
    """One `ar` entry, with the even-byte padding the format requires.

    Written by hand because the `ar` header is 60 fixed bytes and Python has no
    stdlib writer. The trailing newline in the name field is part of the format,
    not a typo.
    """
    header = (
        f"{name + '/':<16}"
        f"{int(time.time()):<12}"
        f"{0:<6}{0:<6}{0o100644:<8o}"
        f"{len(data):<10}"
        "`\n"
    ).encode("ascii")
    assert len(header) == 60, len(header)
    padding = b"\n" if len(data) % 2 else b""
    return header + data + padding


def _tar_gz(root: Path) -> bytes:
    """A gzipped tar of an existing directory tree, reproducibly.

    `add()` rather than building entries by hand. A hand-built version sorted the
    paths, which put `usr` before `usr/lib` and made tar record `usr` as a *file* —
    extraction then died with "Not a directory". `add()` walks the tree, so parents
    precede children by construction, and it reads each entry's mode from disk.

    mtime and ownership are pinned: two builds of the same source should produce the
    same bytes, and a wall-clock timestamp would make that untrue.
    """
    buffer = io.BytesIO()

    def normalise(info: tarfile.TarInfo) -> tarfile.TarInfo:
        info.mtime = 0
        info.uid = info.gid = 0
        info.uname = info.gname = "root"
        return info

    with tarfile.open(fileobj=buffer, mode="w") as tar:
        for child in sorted(root.iterdir()):
            tar.add(child, arcname=child.name, recursive=True, filter=normalise)
    return gzip.compress(buffer.getvalue(), mtime=0)


def build_deb(out_dir: Path, *, with_model: bool) -> Path:
    if with_model:
        raise SystemExit("Debian packages must not contain the proprietary model")
    stamp = _BUILD_ID
    archive = artifact_path(out_dir, f"{PACKAGE}_{version()}_{stamp}_amd64.deb")
    with tempfile.TemporaryDirectory(prefix="nvfku-deb-") as raw:
        # The payload root IS the install prefix. `payload_tree` lays out `app/`,
        # `engine/` and the launchers relative to wherever it is pointed, so
        # pointing it at `/usr/lib/nvfku` is what puts them in the right place — a
        # first version pointed it at the archive root by mistake, which would have
        # unpacked a Flutter bundle into `/`.
        staging = Path(raw) / "data/usr/lib/nvfku"
        payload_tree(staging, with_model=with_model)
        write_launchers(staging)

        # The two entry points a Debian user expects on $PATH, the desktop entry,
        # the icon, and the docs. These live outside the payload prefix, so they are
        # written here rather than by `payload_tree`.
        data_root = Path(raw) / "data"
        (data_root / "usr/bin").mkdir(parents=True, exist_ok=True)
        (data_root / "usr/bin/nvfku-swapper").write_text(
            "#!/bin/sh\n"
            "# NVFKU-Swapper. The payload lives in /usr/lib/nvfku.\n"
            'exec /usr/lib/nvfku/nvfku "$@"\n',
            encoding="utf-8",
        )
        (data_root / "usr/bin/nvfku-swapper").chmod(0o755)
        (data_root / "usr/bin/nvfku").write_text(
            "#!/bin/sh\n"
            "PYTHONPATH=/usr/lib/nvfku/engine exec python3 -m nvfku \"$@\"\n",
            encoding="utf-8",
        )
        (data_root / "usr/bin/nvfku").chmod(0o755)

        desktop_dir = data_root / "usr/share/applications"
        desktop_dir.mkdir(parents=True, exist_ok=True)
        (desktop_dir / f"{PACKAGE}.desktop").write_text(
            _DESKTOP.format(summary=SUMMARY, exec="nvfku-swapper", icon=PACKAGE),
            encoding="utf-8",
        )
        icon_dir = data_root / "usr/share/icons/hicolor/256x256/apps"
        icon_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory() as icon_tmp:
            shutil.copy2(
                write_icon(Path(icon_tmp) / f"{PACKAGE}.png", 256),
                icon_dir / f"{PACKAGE}.png",
            )
        doc_dir = data_root / "usr/share/doc/nvfku-swapper"
        doc_dir.mkdir(parents=True, exist_ok=True)
        for doc in ("LICENSE", "THIRD_PARTY_NOTICES.md", "README.md", "README.zh.md"):
            source = staging / doc
            if source.is_file():
                shutil.copy2(source, doc_dir / doc)
        (data_root / "usr/lib/nvfku/RELEASE.json").write_text(
            _release_json(with_model, "deb"), encoding="utf-8"
        )

        installed_kb = (sum(p.stat().st_size for p in data_root.rglob("*") if p.is_file()) + 1023) // 1024
        control = (
            f"Package: {PACKAGE}\n"
            f"Version: {version()}\n"
            "Section: utils\n"
            "Priority: optional\n"
            f"Architecture: amd64\n"
            f"Depends: {deb_dependencies(runtime_requirements())}\n"
            f"Installed-Size: {installed_kb}\n"
            f"Maintainer: {MAINTAINER}\n"
            f"Homepage: {HOMEPAGE}\n"
            f"Description: {SUMMARY}\n"
            " Two routes for loading a DLSS Neural Rendering proxy into a Proton game:\n"
            " a ReShade overlay route with live controls, and a single-DLL OptiScaler\n"
            " route with no prerequisite. Every change is journalled, so an install can\n"
            " be undone exactly.\n"
            " .\n"
            " The DLSS NR model is not bundled. It is 158 MiB, proprietary, and has no\n"
            " licence permitting redistribution, so Debian policy would refuse it. Run\n"
            " 'nvfku model --mirror-sync' once to fetch and verify it.\n"
        ).encode()

        print("  assembling control and data members")
        control_dir = Path(raw) / "control"
        control_dir.mkdir()
        (control_dir / "control").write_bytes(control)
        (control_dir / "changelog").write_bytes(
            (
                f"{PACKAGE} ({version()}) unstable; urgency=medium\n\n"
                f"  * Initial packaging.\n\n"
                f" -- {MAINTAINER}  {time.strftime('%a, %d %b %Y')} 00:00:00 +0000\n"
            ).encode()
        )
        shutil.copy2(staging / "THIRD_PARTY_NOTICES.md", control_dir / "copyright")
        control_tar = _tar_gz(control_dir)
        data_tar = _tar_gz(data_root)

        with archive.open("xb") as handle:
            handle.write(b"!<arch>\n")
            handle.write(_ar_member("debian-binary", b"2.0\n"))
            handle.write(_ar_member("control.tar.gz", control_tar))
            handle.write(_ar_member("data.tar.gz", data_tar))
    return archive


# ------------------------------------------------------------------ appimage

_APPRUN = """#!/bin/sh
# AppImage entry point. The AppDir is $APPDIR and this script lives at its root.
HERE="$(dirname "$(readlink -f "$0")")"
export NVFKU_ENGINE="$HERE/usr/lib/nvfku"
exec "$HERE/usr/lib/nvfku/nvfku" "$@"
"""


def build_appimage(out_dir: Path, *, with_model: bool) -> Path:
    tool = shutil.which("appimagetool") or str(
        Path.home() / ".local/opt/appimage/appimagetool"
    )
    if not Path(tool).is_file():
        raise SystemExit(
            f"appimagetool not found at {tool}\n"
            "  fetch it from https://github.com/AppImage/appimagetool/releases"
        )
    stamp = _BUILD_ID
    archive = artifact_path(out_dir, f"{PACKAGE}-{version()}-{stamp}-x86_64.AppImage")

    with tempfile.TemporaryDirectory(prefix="nvfku-appdir-") as raw:
        appdir = Path(raw) / f"{PACKAGE}.AppDir"
        payload_tree(appdir / "usr/lib/nvfku", with_model=with_model)
        # `payload_tree` already put `app/` and `engine/` under this prefix, and
        # the launcher resolves `$HERE/app`, so it works from here unchanged.
        write_launchers(appdir / "usr/lib/nvfku")
        (appdir / "usr/lib/nvfku/RELEASE.json").write_text(
            _release_json(with_model, "appimage"), encoding="utf-8"
        )

        (appdir / "AppRun").write_text(_APPRUN, encoding="utf-8")
        (appdir / "AppRun").chmod(0o755)
        (appdir / f"{PACKAGE}.desktop").write_text(
            _DESKTOP.format(summary=SUMMARY, exec="AppRun", icon=PACKAGE),
            encoding="utf-8",
        )
        icon = write_icon(appdir / f"{PACKAGE}.png", 256)
        shutil.copy2(icon, appdir / ".DirIcon")

        env = dict(os.environ)
        # appimagetool tries to embed a desktop-file update tool; there is none here,
        # and it is optional, so it is told not to look rather than allowed to fail.
        env["ARCH"] = "x86_64"
        env.setdefault("NO_STRIP", "1")
        print("  running appimagetool")
        result = subprocess.run(
            [str(tool), "--no-appstream", str(appdir), str(archive)],
            capture_output=True,
            text=True,
            env=env,
        )
        if result.returncode != 0 or not archive.is_file():
            tail = "\n".join((result.stdout + result.stderr).splitlines()[-15:])
            raise SystemExit(f"appimagetool failed:\n{tail}")
        archive.chmod(0o755)
    return archive


# --------------------------------------------------------------------- shared


def runtime_requirements() -> dict:
    """Measure required ELF symbol versions, retaining the declared glibc floor."""
    requirements = {"python_min": "3.9", "architecture": "x86_64",
                    "glibc_min": "2.34", "glibcxx_min": None, "cxxabi_min": None}
    candidates = [APP_BUNDLE / "nvfku_ui", *sorted((APP_BUNDLE / "lib").glob("*.so"))]
    for binary in candidates:
        if not binary.is_file():
            continue
        with binary.open("rb") as handle:
            if handle.read(4) != b"\x7fELF":
                continue
        try:
            result = subprocess.run(["readelf", "--version-info", str(binary)],
                capture_output=True, text=True, check=True)
        except (OSError, subprocess.CalledProcessError) as exc:
            raise SystemExit(f"cannot determine ELF runtime requirements for {binary}: {exc}") from exc
        for symbol, key in (("GLIBC", "glibc_min"), ("GLIBCXX", "glibcxx_min"), ("CXXABI", "cxxabi_min")):
            tags = re.findall(r"\b" + symbol + r"_([0-9.]+)\b", result.stdout)
            for tag in tags:
                current = requirements[key]
                if current is None or tuple(map(int, tag.split("."))) > tuple(map(int, current.split("."))):
                    requirements[key] = tag
    return requirements


def deb_dependencies(runtime: dict) -> str:
    # GNU's ABI history: https://gcc.gnu.org/onlinedocs/libstdc++/manual/abi.html
    # Conservative for old symbols; explicit mappings for newer toolchains.
    releases = ["4.1.1"] * 9 + ["4.2.0", "4.3.0", "4.4.0", "4.4.1", "4.4.2",
        "4.5.0", "4.6.0", "4.6.1", "4.7.0", "4.8.0", "4.8.3", "4.9.0",
        "5.1.0", "6.1.0", "7.1.0", "7.2.0", "8.1.0", "9.1.0", "9.2.0",
        "9.3.0", "11.1.0", "12.1.0", "13.1.0", "13.2.0", "14.1.0", "15.1.0"]
    cxx_release = "4.1.1"
    tag = runtime["glibcxx_min"]
    if tag:
        parts = tuple(map(int, tag.split(".")))
        if parts == (3, 4):
            index = 0
        elif len(parts) == 3 and parts[:2] == (3, 4) and parts[2] < len(releases):
            index = parts[2]
        else:
            raise SystemExit(f"unknown GLIBCXX requirement: {tag}; update the ABI mapping before packaging")
        cxx_release = releases[index]
    abi = runtime["cxxabi_min"]
    if abi:
        minimums = {"1.3": "4.1.1", "1.3.1": "4.1.1", "1.3.2": "4.3.0",
            "1.3.3": "4.4.0", "1.3.4": "4.5.0", "1.3.5": "4.6.0", "1.3.6": "4.7.0",
            "1.3.7": "4.8.0", "1.3.8": "4.9.0", "1.3.9": "5.1.0", "1.3.10": "6.1.0",
            "1.3.11": "7.1.0", "1.3.12": "9.1.0", "1.3.13": "11.1.0",
            "1.3.14": "13.1.0", "1.3.15": "14.1.0", "1.3.16": "15.1.0", "1.3.17": "16.1.0"}
        if abi not in minimums:
            raise SystemExit(f"unknown CXXABI requirement: {abi}")
        cxx_release = max((cxx_release, minimums[abi]), key=lambda s: tuple(map(int, s.split("."))))
    return (f"python3 (>= 3.9), libc6 (>= {runtime['glibc_min']}), "
            f"libstdc++6 (>= {cxx_release}), {DEB_DEPENDS}")


def source_provenance() -> dict:
    """Identify the actual worktree, including uncommitted and untracked source."""
    try:
        revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
            capture_output=True, text=True, check=True).stdout.strip()
        status = subprocess.run(["git", "status", "--porcelain", "--untracked-files=all"],
            cwd=ROOT, capture_output=True, check=True).stdout
        listing = subprocess.run(["git", "ls-files", "-z", "--cached", "--others",
            "--exclude-standard"], cwd=ROOT, capture_output=True, check=True).stdout
        digest = hashlib.sha256()
        for name in sorted(set(listing.split(b"\0")) - {b""}):
            path = ROOT / os.fsdecode(name)
            digest.update(name + b"\0")
            if path.is_symlink():
                digest.update(b"symlink:" + os.fsencode(os.readlink(path)))
            elif path.is_file():
                digest.update(sha256_of(path).encode())
            else:
                digest.update(b"absent")
            digest.update(b"\0")
        return {"revision": revision, "dirty": bool(status), "tree_sha256": digest.hexdigest()}
    except (OSError, subprocess.CalledProcessError) as exc:
        return {"revision": None, "dirty": None, "tree_sha256": None,
                "unavailable": str(exc)}


def _release_json(with_model: bool, kind: str) -> str:
    import json

    return (
        json.dumps(
            {
                "name": "NVFKU-Swapper",
                "version": version(),
                "format": kind,
                "build_id": _BUILD_ID,
                "source_provenance": source_provenance(),
                "runtime": runtime_requirements(),
                "built": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "licence": "WTFPL (this project's code only)",
                "model_bundled": with_model,
                "model": (
                    {
                        "file": f"vendor/weights/{MANIFEST_NAME}",
                        "state": "bundled, digest verified before packaging",
                    }
                    if with_model
                    else {
                        "state": "not bundled",
                        "how_to_get": "nvfku model --mirror-sync",
                        "why": (
                            "158 MiB, proprietary, no licence permits redistribution. "
                            "See THIRD_PARTY_NOTICES.md and docs/weights.md."
                        ),
                    }
                ),
                # Where the model came from, and what that source is. Recorded in
                # every manifest because a release archive is the thing a user
                # unpacks, and this is the only place it can be learned after the
                # fact that the binary inside is a community mirror rather than an
                # NVIDIA download.
                "model_source_url": engine_constants()[2],
                "model_source_note": (
                    "A community mirror of NVIDIA's signed runtime, not an NVIDIA "
                    "download. See THIRD_PARTY_NOTICES.md and docs/weights.md."
                ),
                "source": HOMEPAGE,
            },
            indent=2,
        )
        + "\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--format",
        choices=["tar", "deb", "appimage", "all"],
        default="all",
        help="which to build (default: all)",
    )
    parser.add_argument("--out", default=str(ROOT / "dist"))
    parser.add_argument(
        "--with-model",
        action="store_true",
        help=(
            "bundle the 158 MiB NVIDIA model. Refused for .deb: it has no licence "
            "permitting redistribution, and Debian policy forbids it."
        ),
    )
    args = parser.parse_args()

    wanted = ["tar", "deb", "appimage"] if args.format == "all" else [args.format]
    if args.with_model and "deb" in wanted:
        raise SystemExit(
            "--with-model and --format deb are refused together.\n"
            "  nvngx_dlssnr.dll is NVIDIA's, proprietary, and has no licence that\n"
            "  permits redistribution. A .deb carrying it is not distributable —\n"
            "  lintian flags it and no Debian archive will accept it. Every other\n"
            "  format downloads it on first use instead."
        )

    if not APP_BUNDLE.is_dir():
        raise SystemExit(
            f"no app bundle at {APP_BUNDLE}\n"
            "  Run `flutter build linux --release` in app/ first."
        )

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    # Keep one inode for cooperating builders while merging the checksum set.
    with (out_dir / ".package.lock").open("a+b") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        return _build_candidates(args, wanted, out_dir)


def _build_candidates(args, wanted, out_dir):
    sums = out_dir / "SHA256SUMS"
    entries = {}
    if sums.is_file():
        for line in sums.read_text(encoding="utf-8").splitlines():
            parts = line.split("  ", 1)
            if len(parts) != 2 or not re.fullmatch(r"[0-9a-f]{64}", parts[0]):
                raise SystemExit("invalid SHA256SUMS entry; refusing to replace the manifest")
            digest, name = parts
            if name in entries:
                raise SystemExit(f"duplicate checksum filename: {name}")
            if Path(name).name != name or name in {".", ".."}:
                raise SystemExit(f"unsafe checksum filename: {name}")
            previous = out_dir / name
            if previous.is_file():
                if sha256_of(previous) != digest:
                    raise SystemExit(f"existing artifact no longer matches SHA256SUMS: {name}")
                entries[name] = digest

    built: list[Path] = []
    for kind in wanted:
        print(f"{kind}:")
        if kind == "tar":
            built.append(build_tar(out_dir, with_model=args.with_model))
        elif kind == "deb":
            built.append(build_deb(out_dir, with_model=args.with_model))
        else:
            built.append(build_appimage(out_dir, with_model=args.with_model))

    print()
    for path in built:
        digest = sha256_of(path)
        print(f"  {path.name}")
        print(f"    {path.stat().st_size / 1048576:.1f} MiB  sha256 {digest[:32]}…")
    print()
    # A checksum file alongside the artifacts. Anyone downloading a release binary
    # should be able to verify it, and the sums are already computed for the report.
    for artifact in built:
        entries[artifact.name] = sha256_of(artifact)
    from nvfku.paths import atomic_write_text
    atomic_write_text(sums, "\n".join(f"{digest}  {name}" for name, digest in entries.items()) + "\n")
    print()
    print(f"wrote {sums.name}")
    print(sums.read_text(), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
