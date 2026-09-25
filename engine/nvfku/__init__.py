"""nvfku - a Linux-native installer for community DLSS 5 routes.

The package is deliberately split so the engine has **no GUI dependency**:

    nvfku.paths      filesystem layer, symlink-safe writes
    nvfku.pe         minimal PE reader (bitness, imports, strings)
    nvfku.steam      Steam library discovery, game classification
    nvfku.journal    transactional file journal and exact rollback
    nvfku.providers  upstream release resolution and hash pinning
    nvfku.plan       dry-run plans shared by every route
    nvfku.route.*    one module per installable route

Routes implemented here differ from the Windows tools because the Linux
constraints differ.  In particular ``winevulkan`` never enumerates third-party
Vulkan layers (``vkEnumerateInstanceLayerProperties`` returns zero layers), so
no route may depend on registering a layer for a game to load.
"""

from __future__ import annotations

__version__ = "0.1.0"
__all__ = ["__version__"]
