# Where the DLSS Neural Rendering model comes from

`nvngx_dlssnr.dll` is the file this whole tool exists to drive. It is worth being
precise about what it is, because almost everything confusing about installing
DLSS 5 on Linux comes from one misunderstanding about it.

## It is not a weights file, and it has no official download

It is a **165,840,496-byte DLL** (158 MiB) that NVIDIA ships as part of its DLSS
Neural Rendering runtime. It is not a set of weights in a container, and there is
no page on nvidia.com where you can download it:

| Possible source | What it actually provides |
|---|---|
| [NVIDIA/DLSS](https://github.com/NVIDIA/DLSS) (the DLSS SDK) | Headers and an import library. No runtime, no model. |
| The Linux driver on this machine (615.71.09) | Three files in `/usr/lib/nvidia/wine/` totalling 12 MiB — `nvngx.dll`, `_nvngx.dll`, `nvngx_dlssg.dll`. **No NR model.** |
| A game you own | Yes. Recent titles that ship DLSS 5 carry it. |
| An NVIDIA **Windows** driver package | Yes. This is what the community docs point at. |
| A community release | Usually a re-host of one of the above. |

The Linux driver is the interesting row. It ships the frame-generation model but
not the neural-rendering one, so "the model comes from your driver" is true on
Windows and false here.

## Why the build matters more than the file

NapXDD's add-on README is explicit:

> The add-on has only run stably with this exact model — `sha256 e16bcf15…6e1fc8e`
> (165,840,496 bytes). A different model version may not fail cleanly: in testing,
> a mismatched model reported Success on every evaluate and then **crashed the game
> minutes into gameplay.**

That failure mode is why this tool classifies by digest instead of by filename or
size. Every build on this machine is 165,840,496 bytes; only one of them is the one
that was measured.

## Known builds

| SHA-256 (first 16) | Build | Where it comes from | Measured stable |
|---|---|---|---|
| `e16bcf15e16e13f5` | DLSS NR **310.8.0**, NVIDIA-signed | The build the add-on names. Redistributed by `RankFTW/rhi-repo`. | **Yes** |
| `e67dee209320cdaf` | DLSS NR 310.8, ShortFuse cross-generation | For RTX 20/30/40. Not downloadable here — no pinned archive was found. | No |
| `984bee0f775c277d` | NVNGX DLSSNR | `DLSS5-Tools/Magpie-Experimental` | No |
| `8270b350cd82de5c` | NVNGX DLSSNR | Shipped inside Cyberpunk 2077, MSFS2024, and bundled by DLSS5-Swapper 2.2.7 | No |

Run `nvfku model --list` for the live version of this table, and
`nvfku model --verify <path>` to identify a file you already have.

## The three ways to get it, in order of preference

1. **A game you own already has it.** Most reliable, no download, and already on
   disk. `nvfku model --list` plus the scan will find these; A1 prefers a tested
   build wherever it finds one.
2. **Extract it from an NVIDIA Windows driver package.** The only source that is
   NVIDIA's own. Not automated here: the package is ~900 MiB and its internal
   layout is not pinned, so a script that reaches into it would break silently.
3. **Fetch the pinned copy.** `nvfku model --fetch`, or the action A1's plan
   offers when no tested build is present.

## What the pinned download is, exactly

```
https://github.com/RankFTW/rhi-repo/releases/download/dlssnr-310.8.0/nvngx_dlssnr_310.8.0.zip
sha256 (inner nvngx_dlssnr.dll) e16bcf15e16e13f527491cdf7845b2fe6521a738d8f7c9c721866a8496e1fc8e
```

**This is a community mirror, not an NVIDIA download.** The DLL inside it is
NVIDIA's own signed binary; the hosting is somebody else's. The tool says so
wherever it names the source, because that distinction is one a user cannot check
for themselves without opening the file's properties.

The URL is the same one
[DLSS5-Feeder](https://github.com/jlrouzies-fr/DLSS5-Feeder)'s installer uses. That
script moved to it from Discord CDN links specifically because those carry an
expiry and rot; a pinned GitHub release tag does not.

The digest is checked on the **inner DLL**, not the zip. A zip's digest changes
whenever it is repacked, so pinning it would make the check fail on a re-upload
that is byte-identical inside. A mismatch deletes the file rather than installing
it.

## Why this tool downloads it at all

The rest of this project refuses to fetch NVIDIA binaries, and that policy is
still in force for `nvngx_dlss.dll` and the DLSS Super Resolution runtime. The NR
model is a deliberate exception, for one reason: the alternative was a warning that
names a 158 MiB file with no way to get it and no digest to check it against, and
the observed outcome of that is people running a build that reports success on
every evaluate and then crashes their game mid-session.

A pinned URL with a pinned digest is checkable. A one-line warning is not.
