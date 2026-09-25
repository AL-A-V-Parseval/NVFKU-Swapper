#!/usr/bin/env python3
"""Build a distributable release of NVFKU-Swapper.

The point of this script is one file: the DLSS Neural Rendering model. Everything
else here is copying. The model is 158 MiB of NVIDIA's proprietary binary that this
project does not host and did not write, and a release that ships it must be sure
which build it shipped — because the wrong one reports success on every evaluate and
then crashes the game minutes into play, which is not a failure anyone can diagnose
from a bug report.

So the model is **verified before it is packaged, and packaging refuses if it does
not match**. A release without it is a release whose users each have to find a
158 MiB file by hand; a release with the wrong one is worse than that.

What goes in the archive:

    nvfku-swapper/
      nvfku                        launcher (GUI)
      nvfku-cli                    launcher (the command line, same engine)
      engine/nvfku/                the Python engine, stdlib only
      app/                         the Flutter bundle
      vendor/weights/              the model, digest-verified
      docs/                        including weights.md, the provenance record
      README.md
      RELEASE.json                 what was built, and the digest that was checked

Usage:
    python3 tools/make_release.py [--out DIR] [--skip-build] [--no-app]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / "engine"
APP_BUNDLE = ROOT / "app/build/linux/x64/release/bundle"
VENDOR_WEIGHTS = ROOT / "vendor/weights"
MANIFEST_NAME = "nvngx_dlssnr.dll"

#: Read here rather than imported, so this script cannot drift from the engine's
#: idea of which build is correct. `--check` below fails loudly if that happens.
sys.path.insert(0, str(ENGINE))


def engine_constants() -> tuple[str, int, str]:
    from nvfku import weights

    return weights.TESTED_SHA256, weights.TESTED_SIZE, weights.RTX50_SOURCE.url


def sha256_of(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def verify_model(
    expected_sha: str,
    expected_size: int,
    *,
    model: Path | None = None,
) -> Path:
    """Return the verified model, or explain exactly what is wrong with it.

    Takes the path so the refusal paths can be tested without a 158 MiB fixture.
    """
    model = model or (VENDOR_WEIGHTS / MANIFEST_NAME)
    if not model.is_file():
        raise SystemExit(
            f"no vendored model at {model}\n"
            "  A release must carry one: run `python3 -m nvfku model --mirror-sync`\n"
            "  from the project root first, or pass --no-app for a source-only tree."
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


def build_app() -> None:
    """Build the Flutter bundle, if a toolchain is present."""
    flutter = shutil.which("flutter") or str(Path.home() / ".local/opt/flutter/bin/flutter")
    if not Path(flutter).exists():
        raise SystemExit(f"flutter not found at {flutter}; pass --skip-build")
    env = dict(os.environ)
    env.setdefault("PUB_CACHE", str(ROOT / ".pub-cache"))
    env["FLUTTER_SUPPRESS_ANALYTICS"] = "true"
    print(f"  building the app with {flutter}")
    result = subprocess.run(
        [flutter, "build", "linux", "--release"],
        cwd=ROOT / "app",
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        tail = "\n".join((result.stdout + result.stderr).splitlines()[-12:])
        raise SystemExit(f"flutter build failed:\n{tail}")


def copy_tree(source: Path, destination: Path, *, ignore=None) -> None:
    shutil.copytree(
        source,
        destination,
        ignore=ignore,
        dirs_exist_ok=True,
        symlinks=False,
    )


def ignore_engine(_directory: str, names: list[str]) -> set[str]:
    """Skip bytecode and test material: this ships a runtime, not a checkout."""
    return {n for n in names if n in {"__pycache__", "tests"} or n.endswith(".pyc")}


def write_launcher(path: Path, description: str) -> None:
    """A launcher that finds its own engine, so the tree is relocatable.

    `$HERE` rather than an absolute path: a release is unpacked wherever the user
    wants it, and a launcher that only works from the build directory is a bug
    report waiting to happen.
    """
    path.write_text(
        "#!/bin/sh\n"
        f"# {description}\n"
        "# Resolve this script's own directory, following symlinks, so the tree can\n"
        "# live anywhere and still find its engine.\n"
        'HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)\n'
        # `-m nvfku` is not optional: without it `python3 model --verify` is read
        # as "run the file model", which is what a first version of this did.
        f'PYTHONPATH="$HERE/engine${{PYTHONPATH:+:$PYTHONPATH}}" '
        'exec python3 -m nvfku "$@"\n',
        encoding="utf-8",
    )
    path.chmod(0o755)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default=str(ROOT / "dist"), help="where to write the archive")
    parser.add_argument("--skip-build", action="store_true", help="use the app bundle as it is")
    parser.add_argument("--no-app", action="store_true", help="engine and model only")
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify the vendored model and exit without packaging",
    )
    args = parser.parse_args()

    expected_sha, expected_size, source_url = engine_constants()

    if args.check:
        model = verify_model(expected_sha, expected_size)
        print(f"ok  {model}")
        print(f"    {model.stat().st_size} bytes")
        print(f"    {expected_sha}")
        return 0

    if not args.skip_build and not args.no_app:
        build_app()

    if not args.no_app and not APP_BUNDLE.is_dir():
        raise SystemExit(
            f"no app bundle at {APP_BUNDLE}\n"
            "  Run `flutter build linux --release` in app/, or pass --skip-build "
            "once it exists, or --no-app."
        )

    model = verify_model(expected_sha, expected_size)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    name = f"nvfku-swapper-{stamp}"
    archive = out_dir / f"{name}.tar.gz"

    # Staged in a temporary directory so a failure part-way through cannot leave a
    # half-populated release tree that looks complete.
    with tempfile.TemporaryDirectory(prefix="nvfku-release-", dir=out_dir) as staging_raw:
        staging = Path(staging_raw) / "nvfku-swapper"
        staging.mkdir()

        print("  engine")
        copy_tree(ENGINE / "nvfku", staging / "engine/nvfku", ignore=ignore_engine)

        print("  model")
        (staging / "vendor/weights").mkdir(parents=True)
        shutil.copy2(model, staging / "vendor/weights" / MANIFEST_NAME)
        if (ROOT / "vendor/README.md").is_file():
            shutil.copy2(ROOT / "vendor/README.md", staging / "vendor/README.md")

        print("  docs")
        copy_tree(ROOT / "docs", staging / "docs")
        for extra in ("README.md", "LICENSE"):
            if (ROOT / extra).is_file():
                shutil.copy2(ROOT / extra, staging / extra)

        if not args.no_app:
            print("  app bundle")
            copy_tree(APP_BUNDLE, staging / "app")

        write_launcher(
            staging / "nvfku",
            "NVFKU-Swapper command line: `nvfku <command>`.",
        )
        if not args.no_app:
            # The GUI launcher points at the bundle's own executable rather than
            # going through the engine.
            (staging / "nvfku-gui").write_text(
                "#!/bin/sh\n"
                "# NVFKU-Swapper graphical interface.\n"
                'HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)\n'
                'export NVFKU_ENGINE="$HERE"\n'
                'exec "$HERE/app/nvfku_ui" "$@"\n',
                encoding="utf-8",
            )
            (staging / "nvfku-gui").chmod(0o755)

        manifest = {
            "name": "NVFKU-Swapper",
            "built": stamp,
            "engine": "engine/nvfku (Python, standard library only)",
            "model": {
                "file": f"vendor/weights/{MANIFEST_NAME}",
                "sha256": expected_sha,
                "size": expected_size,
                "verified_before_packaging": True,
            },
            "model_source_url": source_url,
            "model_source_note": (
                "A community mirror of NVIDIA's signed runtime, not an NVIDIA "
                "download. See docs/weights.md."
            ),
            "includes_app": not args.no_app,
        }
        (staging / "RELEASE.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )

        print("  compressing")
        with tarfile.open(archive, "w:gz") as tar:
            tar.add(staging, arcname="nvfku-swapper")

    total = archive.stat().st_size
    print()
    print(f"wrote {archive} ({total / 1048576:.0f} MiB)")
    print(f"  model {MANIFEST_NAME} sha256 {expected_sha[:16]}… verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
