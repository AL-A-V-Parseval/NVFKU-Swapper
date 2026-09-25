# Third-party notices

This project's own code — the Python engine in `engine/`, the Flutter application in
`app/`, and the scripts in `tools/` — is released under the WTFPL. See
[LICENSE](LICENSE).

**That licence covers this project's code and nothing else.** The components below
belong to their authors, and several of them reach your machine through this tool.
WTFPL cannot relicense any of them, and nothing here should be read as claiming
otherwise.

There is a second thing to be clear about: one of these files is NOT open source and
IS redistributed by this project's release archives. It is called out first because
it is the only one where that is true.

---

## Redistributed in release archives

### `nvngx_dlssnr.dll` — the DLSS Neural Rendering model

| | |
|---|---|
| **Owner** | NVIDIA Corporation |
| **Licence** | Proprietary. No public licence permits redistribution. |
| **Size** | 165,840,496 bytes (158 MiB) |
| **SHA-256** | `e16bcf15e16e13f527491cdf7845b2fe6521a738d8f7c9c721866a8496e1fc8e` |
| **Where it came from** | `https://github.com/RankFTW/rhi-repo/releases/download/dlssnr-310.8.0/nvngx_dlssnr_310.8.0.zip` |
| **What that is** | A **community mirror** of NVIDIA's own signed runtime. It is not an NVIDIA download and NVIDIA does not publish one. |

This is the one file this project redistributes that it has no right to licence. A
release archive therefore carries it, and `RELEASE.json` records the digest that was
verified before packaging. The reasons, and the alternatives, are set out in
[docs/weights.md](docs/weights.md).

If you are NVIDIA and you object to this file being mirrored, the correct fix is to
publish the runtime yourself; the tool would then point at your download and this
notice would lose its first section.

---

## Downloaded at install time, never bundled

These are fetched from their own release pages when you install a route, and placed
beside a game as separate programs. **Nothing in this repository links against them,
imports them, or incorporates their source**, so their terms do not extend to this
project's code.

### `dlss5-bridge` — NIGos

- **Licence:** MIT
- **Source:** <https://github.com/NIGos/dlss5-bridge>
- **Ships:** `dlss5-bridge.addon64`, and its `SHA256SUMS.txt` / `THIRD-PARTY-NOTICES.txt`

### `addon-dlssnr-linux` — NapXDD

- **Licence:** **GPL-3.0** (the add-on derives from GPL-3.0 code; its README states so)
- **Source:** <https://github.com/NapXDD/addon-dlssnr-linux>
- **Ships:** `dlssnr-linux.addon64`, `nvngx.dll_nrfwd.dll`
- **Licence text:** <https://www.gnu.org/licenses/gpl-3.0.html>

Because GPL-3.0 requires corresponding source to accompany a binary distribution, the
source for this component is the repository above, at the release tag this tool
downloads (currently `v0.2.2`). Nothing here modifies it.

### `OptiScaler` and `OptiScaler_DLSSNR`

- **Licence:** **GPL-3.0**
- **Source:** <https://github.com/optiscaler/OptiScaler>, <https://github.com/Dagherbou/OptiScaler_DLSSNR>
- **Ships:** `OptiScaler.dll`, `OptiScaler.ini`, its backend folder, and its own
  `Licenses/` directory, which this tool copies through unmodified
- **Licence text:** <https://www.gnu.org/licenses/gpl-3.0.html>

### ReShade 6.8.0 — Patrick Mours (crosire)

- **Licence:** BSD 3-Clause
- **Source:** <https://reshade.me>, <https://github.com/crosire/reshade>
- **Ships:** the official `ReShade_Setup_6.8.0_Addon.exe` is downloaded and run on
  your machine; its output (`dxgi.dll`, `ReShade.ini`, `reshade-shaders/`) lands in
  the game directory

---

## Bundled with the Flutter application

The `app/` bundle in a release archive embeds the Flutter engine and framework, which
are BSD 3-Clause. Their notices travel with the Flutter SDK —
`$FLUTTER_ROOT/bin/cache/pkg/sky_engine/LICENSE` and
`$FLUTTER_ROOT/packages/flutter/LICENSE`.

`flutter_lints` is a build-time development dependency (BSD 3-Clause) and is not part
of any release artifact.

---

## Why this project can be WTFPL while shipping GPL-3.0 components

The GPL's copyleft attaches to a work derived from GPL code, or to a work that links
against it. Neither applies here:

- The engine speaks to these components over the filesystem — it downloads an
  archive and copies files next to a game's executable.
- No GPL source is compiled into, imported by, or copied into this project.
- The components remain separate programs, each with its own release and its own
  licence, invoked by the game rather than by this code.

This is aggregation, not derivation. It is also the arrangement
[DLSS5-Swapper](https://github.com/rakanki911/DLSS5-Swapper/blob/main/THIRD_PARTY_NOTICES.md)
uses, licensing its own code MIT while listing GPL-3.0 components separately.

**If that ever changes** — if any of their source is incorporated rather than
invoked, or if this project is linked against a GPL library — then this project's
licence has to become GPL-3.0, and this section has to be deleted rather than
edited.
