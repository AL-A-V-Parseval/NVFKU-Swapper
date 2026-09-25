# Project-local isolation
# ========================
# Everything this project needs lives inside this directory or inside
# ~/.local/opt/flutter.  Nothing is installed into the system Python, the
# system Flutter (there is none), or the shared ~/.pub-cache.
#
#   source tools/env.sh
#
# After that:
#   nvfku ...        # engine CLI (runs in .venv)
#   flutter ...         # pinned SDK
#   dart ...            # pinned SDK

# --- resolve the project root from this file's own location ---------------
_DLSS5_ENV_SELF="${BASH_SOURCE[0]:-${(%):-%x}}"
DLSS5_ROOT="$(cd "$(dirname "$_DLSS5_ENV_SELF")/.." && pwd)"
export DLSS5_ROOT

# --- Python: project venv, never the system interpreter -------------------
if [ ! -x "$DLSS5_ROOT/.venv/bin/python" ]; then
  echo "nvfku: creating project venv" >&2
  python3 -m venv "$DLSS5_ROOT/.venv"
fi
export VIRTUAL_ENV="$DLSS5_ROOT/.venv"
export PATH="$VIRTUAL_ENV/bin:$PATH"
export PYTHONPATH="$DLSS5_ROOT/engine${PYTHONPATH:+:$PYTHONPATH}"
export PYTHONDONTWRITEBYTECODE=1

# --- Flutter/Dart: pinned SDK + project-local package cache ---------------
export FLUTTER_ROOT="${FLUTTER_ROOT:-$HOME/.local/opt/flutter}"
export PUB_CACHE="$DLSS5_ROOT/.pub-cache"
export PATH="$FLUTTER_ROOT/bin:$FLUTTER_ROOT/bin/cache/dart-sdk/bin:$PATH"

# --- CMake: use the project-local copy when the system has none -----------
# Flutter's Linux desktop build requires CMake, which is not part of a base
# CachyOS install and would otherwise need `sudo pacman -S cmake`. A prebuilt
# archive in ~/.local/opt keeps the toolchain inside this project's isolation
# boundary and needs no root.
if [ -x "$HOME/.local/opt/cmake/bin/cmake" ]; then
  export PATH="$HOME/.local/opt/cmake/bin:$PATH"
  export CMAKE_ROOT="$HOME/.local/opt/cmake/share/cmake-4.2"
fi

# --- keep build output off the NTFS mount's slow paths --------------------
# The project lives on an ntfs3 mount.  Flutter writes a lot of small files
# during a build; keeping the *build* directory on the native filesystem is
# dramatically faster than writing through ntfs3.
export DLSS5_BUILD_DIR="${DLSS5_BUILD_DIR:-$HOME/.cache/nvfku-build}"

# --- engine state (journals, backups, download cache) ---------------------
export DLSS5_STATE_DIR="${DLSS5_STATE_DIR:-$HOME/.local/share/nvfku}"

# --- never inherit a proxy into the tool's own downloads -----------------
# This machine's Clash proxy at 127.0.0.1:7897 intermittently fails TLS while
# direct connections to GitHub and Google Storage work, so the engine defaults
# to direct and callers can opt back in per invocation.
export DLSS5_HTTP_PROXY="${DLSS5_HTTP_PROXY:-direct}"

echo "nvfku env ready"
echo "  root      $DLSS5_ROOT"
echo "  python    $(command -v python3) $(python3 -V 2>&1 | cut -d' ' -f2)"
echo "  flutter   $FLUTTER_ROOT"
echo "  pub cache $PUB_CACHE"
echo "  state     $DLSS5_STATE_DIR"
