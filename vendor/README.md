# What goes in this directory

`vendor/weights/nvngx_dlssnr.dll` — one verified copy of the DLSS Neural
Rendering model, kept inside the checkout by `nvfku model --mirror-sync`.

```
sha256  e16bcf15e16e13f527491cdf7845b2fe6521a738d8f7c9c721866a8496e1fc8e
size    165,840,496 bytes (158 MiB)
```

That digest is the build NapXDD measured stable with `addon-dlssnr-linux` v0.2.2,
and it is the same value this project calls `weights.TESTED_SHA256`. It matters
more than the file name or the size: every build seen on a real machine is
165,840,496 bytes, and only this one was measured. A different build is not a
cosmetic difference — it reports success on every evaluate and then crashes the
game minutes into play. See [`docs/weights.md`](../docs/weights.md) for how the
known builds were catalogued.

## Why it is not committed

The DLL is **NVIDIA's proprietary signed binary**. It is not ours to put in a
source tree: redistributing it would be both a 158 MiB repository and a
redistribution this project deliberately does not do. The `.gitignore` therefore
excludes everything here except this file, and a fresh clone has an empty
`vendor/weights/` until someone syncs it. The download itself is a
**community mirror, not an NVIDIA download**: the pinned URL is a re-host by
[`RankFTW/rhi-repo`](https://github.com/RankFTW/rhi-repo), the same one
DLSS5-Feeder's installer uses because Discord CDN links expire. The signature on
the binary is NVIDIA's; the hosting is somebody else's.

The mirror exists for the machines in between: a checkout that has fetched the
model once can carry it to another machine, or keep it across a `git clean`,
without spending the ~104 MiB download again.

## Populate, check, remove

```sh
nvfku model --mirror-status          # what is here now, in one sentence
nvfku model --mirror-status --json   # the same as machine-readable fields
nvfku model --mirror-sync            # fetch the pinned build and verify it into place
nvfku model --mirror-prune           # delete it, reclaiming the 158 MiB
```

The same three calls exist in the engine, for the UI and for scripts:

```python
from nvfku import mirror

print(mirror.inspect().describe())   # never raises, even when nothing is here
mirror.sync()                        # no-ops, without downloading, if already verified
mirror.prune()                       # True if a file was removed
```

Two properties of `sync` are worth knowing before trusting the result:

*   **It does not download what it already has.** If `inspect()` reports the
    pinned digest, `sync` returns immediately; the 104 MiB fetch happens only
    when the mirror is missing or wrong.
*   **It writes atomically, then verifies what landed.** The copy goes to a
    temporary file beside the target and is moved into place with `os.replace`,
    so a crash cannot leave a partial 158 MiB file that later looks present. The
    destination is then read back and hashed again — a check the source file's
    earlier verification cannot make — and deleted if it disagrees.
