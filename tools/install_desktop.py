#!/usr/bin/env python3
"""Put NVFKU-Swapper in the desktop application menu — for a source checkout.

The `.deb` already installs a menu entry, but it points at `/usr/bin/nvfku-swapper`
and `/usr/lib/nvfku`, and the whole point of this project's setup is that it runs
from a checkout with nothing installed system-wide. So a checkout needs its own
entry, and this writes one into the *user* XDG directories:

    ~/.local/share/applications/nvfku-swapper.desktop
    ~/.local/share/icons/hicolor/<size>/apps/nvfku-swapper.png

Everything it writes is confined to `$XDG_DATA_HOME`, so it needs no root and is
undone by `--uninstall`.

Re-run it after moving the checkout: the `Exec` line holds an absolute path, and a
stale one produces a menu entry that silently does nothing.

Usage:
    python3 tools/install_desktop.py                 # install or refresh
    python3 tools/install_desktop.py --check         # report, change nothing
    python3 tools/install_desktop.py --uninstall     # remove
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_BUNDLE = ROOT / "app/build/linux/x64/release/bundle"
LAUNCHER = APP_BUNDLE / "nvfku_ui"

APP_ID = "nvfku-swapper"
#: What the window reports as its application id. Without this the shell groups the
#: running window under a generic entry instead of under this icon.
WM_CLASS = "com.nvfku.nvfku_ui"

#: The sizes worth generating. The PNGs are what most menus actually draw; the SVG
#: is for the `scalable` theme, which is what a HiDPI menu prefers.
PNG_SIZES = (48, 128, 256, 512)

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


def data_home() -> Path:
    return Path(os.environ.get("XDG_DATA_HOME") or (Path.home() / ".local/share"))


def desktop_file() -> Path:
    return data_home() / "applications" / f"{APP_ID}.desktop"


def icon_dir(size: int | None) -> Path:
    if size is None:
        return data_home() / "icons/hicolor/scalable/apps"
    return data_home() / "icons/hicolor" / f"{size}x{size}" / "apps"


def rasterise(svg_text: str, destination: Path, size: int) -> None:
    """SVG to PNG, via whichever rasteriser exists."""
    svg = destination.with_suffix(".svg")
    svg.write_text(svg_text.format(size=size), encoding="utf-8")
    for tool, args in (
        ("rsvg-convert", ["-w", str(size), "-h", str(size)]),
        ("convert", ["-background", "none", "-resize", f"{size}x{size}"]),
    ):
        if shutil.which(tool) is None:
            continue
        result = subprocess.run(
            [tool, *args, str(svg), str(destination)], capture_output=True, text=True
        )
        if result.returncode == 0 and destination.is_file():
            svg.unlink(missing_ok=True)
            return
    svg.unlink(missing_ok=True)
    raise SystemExit(
        "no SVG rasteriser found (need rsvg-convert or ImageMagick `convert`); "
        "a menu entry without its icon is worse than no entry"
    )


def entry_text() -> str:
    """The `.desktop` contents.

    `Path=` is set as well as `Exec=`. It is not required, but it tells the shell
    what the application's working directory is, which is what makes "open the
    containing folder" behave and keeps a relative-path bug from starting the app
    somewhere unexpected.
    """
    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Version=1.0\n"
        f"Name=NVFKU-Swapper\n"
        "GenericName=DLSS 5 installer\n"
        "Comment=Install DLSS 5 Neural Rendering into Linux games\n"
        f"Exec={LAUNCHER}\n"
        f"Path={APP_BUNDLE}\n"
        f"Icon={APP_ID}\n"
        "Terminal=false\n"
        # One main category and one subcategory. `Utility;Settings;` is two main
        # categories, which `desktop-file-validate` warns about and which makes the
        # entry appear twice in a menu that groups by category — a duplicate in the
        # list is worse than a single imperfect placement.
        "Categories=Utility;X-GNOME-Utilities;\n"
        "Keywords=DLSS;NVIDIA;Proton;Steam;ReShade;OptiScaler;NVFKU;\n"
        f"StartupWMClass={WM_CLASS}\n"
        "StartupNotify=true\n"
    )


def refresh_caches() -> list[str]:
    """Tell the shell the menu changed. Returns what was run, for reporting.

    `update-desktop-database` and `gtk-update-icon-cache` are both optional — the
    entry still works without them, it just may not appear until the next login —
    so a missing tool is reported rather than treated as a failure.
    """
    ran: list[str] = []
    applications = data_home() / "applications"
    if shutil.which("update-desktop-database"):
        subprocess.run(
            ["update-desktop-database", str(applications)],
            capture_output=True,
            check=False,
        )
        ran.append("update-desktop-database")
    for theme_root in (data_home() / "icons/hicolor",):
        if theme_root.is_dir() and shutil.which("gtk-update-icon-cache"):
            subprocess.run(
                ["gtk-update-icon-cache", "-q", "-t", "-f", str(theme_root)],
                capture_output=True,
                check=False,
            )
            ran.append("gtk-update-icon-cache")
    return ran


def report() -> int:
    """Say what is installed and whether it still points somewhere real."""
    present = desktop_file().is_file()
    print(f"  desktop entry: {desktop_file()}")
    print(f"    {'present' if present else 'absent'}")
    icons = sorted(p for p in (data_home() / "icons/hicolor").glob("*/apps/nvfku-swapper.*"))
    print(f"  icons: {len(icons)}")
    for icon in icons:
        print(f"    {icon.relative_to(data_home())}")

    problems: list[str] = []
    if not LAUNCHER.is_file():
        problems.append(
            f"the launcher is missing: {LAUNCHER}\n"
            "    Build it first:  cd app && flutter build linux --release"
        )
    if present:
        text = desktop_file().read_text(encoding="utf-8")
        for line in text.splitlines():
            if line.startswith(("Exec=", "Path=")):
                _, _, target = line.partition("=")
                if not Path(target).exists():
                    problems.append(f"{line.split('=')[0]} points at something absent: {target}")
    if problems:
        print()
        for problem in problems:
            print(f"  ! {problem}")
        return 1
    return 0


def uninstall() -> int:
    removed = 0
    if desktop_file().is_file():
        desktop_file().unlink()
        removed += 1
        print(f"  removed {desktop_file()}")
    icon = data_home() / "icons/hicolor/scalable/apps" / f"{APP_ID}.svg"
    if icon.is_file():
        icon.unlink()
        removed += 1
    for size in PNG_SIZES:
        path = icon_dir(size) / f"{APP_ID}.png"
        if path.is_file():
            path.unlink()
            removed += 1
            print(f"  removed {path.relative_to(data_home())}")
    if removed == 0:
        print("  nothing to remove")
    refresh_caches()
    return 0


def install() -> int:
    if not LAUNCHER.is_file():
        raise SystemExit(
            f"no app bundle at {APP_BUNDLE}\n"
            "  Build it first:  cd app && flutter build linux --release\n"
            "  (The menu entry points at the built launcher, so writing one before "
            "the build would create an entry that does nothing.)"
        )

    desktop_file().parent.mkdir(parents=True, exist_ok=True)
    desktop_file().write_text(entry_text(), encoding="utf-8")
    # The spec wants the file executable when it may carry a trusted flag; harmless
    # otherwise, and some shells warn without it.
    desktop_file().chmod(0o755)
    print(f"  wrote {desktop_file()}")

    svg_text = _ICON_SVG
    scalable = icon_dir(None) / f"{APP_ID}.svg"
    scalable.parent.mkdir(parents=True, exist_ok=True)
    scalable.write_text(svg_text.format(size=256), encoding="utf-8")
    for size in PNG_SIZES:
        target = icon_dir(size) / f"{APP_ID}.png"
        target.parent.mkdir(parents=True, exist_ok=True)
        rasterise(svg_text, target, size)
        print(f"  wrote {target.relative_to(data_home())}")

    ran = refresh_caches()
    print()
    if ran:
        print(f"  refreshed: {', '.join(ran)}")
    else:
        print(
            "  no caches refreshed (update-desktop-database / gtk-update-icon-cache "
            "are not installed); the entry appears on next login"
        )
    print()
    print("  Look for it as 'NVFKU-Swapper' under Utilities or Settings.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--uninstall", action="store_true", help="remove everything it wrote")
    group.add_argument("--check", action="store_true", help="report without changing anything")
    args = parser.parse_args()

    if args.uninstall:
        return uninstall()
    if args.check:
        return report()
    return install()


if __name__ == "__main__":
    raise SystemExit(main())
