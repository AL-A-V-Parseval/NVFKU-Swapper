"""Installable routes.

Each module exposes the same surface so the CLI and the UI can treat them
uniformly:

    ROUTE, TITLE
    is_viable(game) -> (bool, [reason, ...])
    plan(paths, game) -> RoutePlan
    install(paths, game, dry_run=...) -> list[Operation]

The routes differ in *where* they attach, and on Linux that difference is the
whole story:

    a1_bridge      ReShade add-on chain, local dxgi.dll proxy, D3D11/D3D12
    a2_optiscaler  DLL proxy replacing the upscaler, D3D11/D3D12

A Vulkan-layer route is deliberately absent: Wine's loader enumerates zero
third-party layers, so a layer-based route cannot work for a Proton game. That
is why there is no Vulkan route here, rather than an unfinished one.
"""

from __future__ import annotations

from . import a1_bridge, a2_optiscaler

ALL = (a1_bridge, a2_optiscaler)

BY_KEY = {module.ROUTE: module for module in ALL}

__all__ = ["a1_bridge", "a2_optiscaler", "ALL", "BY_KEY"]
