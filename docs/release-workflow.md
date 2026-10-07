# Development checks and Linux release gates

## Supported baseline

- Engine: Python **3.9+**, Linux, standard library only.
- Frontend: Flutter **3.47.5** stable (framework revision `6a19cca56475dbfba1478ee68d7bd0c2ef891da1`), x86_64 Linux and GTK 3.
- Native glibc floor: **2.34**, raised automatically if the built runner or a bundled library requires newer GLIBC symbols. This is an ABI constraint, not a claim that every distro with glibc 2.34 works.
- Release manifest records measured GLIBC, GLIBCXX and CXXABI requirements. Debian control includes Python, libc6 and libstdc++6 minimum versions. C++ package version mappings follow [GNU's ABI history](https://gcc.gnu.org/onlinedocs/libstdc++/manual/abi.html); unknown versions fail packaging rather than silently under-declaring the dependency.
- The CI Linux build baseline is Ubuntu 22.04. The workflow is configured, not evidence that a remote run has passed. Clean-distro GUI acceptance remains required before a public release.

## Local verification

From the repository root:

```bash
source tools/env.sh
python -m unittest discover -s engine/tests -q
python -m compileall -q engine/nvfku tools
git diff --check
```

From the app directory:

```bash
source ../tools/env.sh
flutter test --no-pub --reporter expanded
flutter analyze --no-pub
flutter build linux --release --no-pub
```

On a clean checkout run `flutter pub get` first. Tests use temporary state/game directories or test adapters; they do not install routes into a real game. The settings CLI serializes the full read/modify/write operation, while frontend settings writes also preserve UI intent order. A whole-document `save_settings` remains a low-level snapshot operation: use field-patch updates for concurrent callers.

## Packaging and immutable candidates

```bash
python tools/package.py --format all --out dist/my-candidate
python tools/verify_release.py --out dist/my-candidate \
  --require-format tar --require-format deb --require-format appimage
```

The packager generates a time/random build identity shared by the formats in one invocation; filenames include that identity. It refuses to overwrite an existing artifact. Use a new candidate directory for each release attempt. Partial builds preserve existing valid SHA256SUMS entries; changed prior artifacts cause refusal, not silent checksum replacement.

Each RELEASE manifest includes source revision, dirty state and a content fingerprint of the git-listed worktree (including non-ignored untracked source). Ignored tool caches, build directories and proprietary models are outside that source fingerprint. It identifies the source snapshot, not a reproducible-build guarantee or a signature. Keep the source unchanged while building a candidate; verify source identity again after extraction.

Standard tar, deb and AppImage candidates contain **no NVIDIA model**. Private `--with-model` is permitted only for an individual tar or AppImage build, never `deb` or `all`. The verifier deliberately accepts only model-free public candidates.

The maintained [release verifier](../tools/verify_release.py) replaces dependence on one historical dist directory. It checks:

- All listed artifact digests; safe filenames and required formats.
- Temporary extraction (tar/deb ordinary files and directories only; archive links and traversal are rejected).
- Required payload, proprietary model/cache exclusion, executable modes, metadata and engine source bytes.
- Isolated CLI version/settings/backups/missing-journal rollback; all writable state is temporary.
- Desktop entry validity, declared Debian interpreter/glibc constraints and host native dependency resolution.
- Shared source/runtime identity for formats claiming the same build ID.

**Use this tool only on trusted local builds.** AppImage extraction runs its embedded runtime; packaged CLI smoke runs the packaged engine. Checksums are not an authenticity check. There is no GUI launch, actual deb installation, native/FUSE AppImage startup, game operation or model download in this gate.

AppImage building requires a separately provisioned `appimagetool` plus SVG rasterization. CI automatically builds and verifies tar/deb; local release acceptance must also build/verify AppImage. No workflow publishes a GitHub Release, pushes tags or installs a candidate.

## Cache migration and verification levels

Component cache keys now include version and URL identity; local receipts record content digest/size. Old unversioned caches are not silently adopted: fetch the components again before offline `--skip-download`. A valid local receipt protects against accidental cache corruption; it is **not** publisher authentication. Where a publisher/pinned digest is unavailable, report the size/local-integrity level explicitly.

A model ZIP with an invalid member or wrong model digest is discarded so a later explicit retry can fetch again. The model digest remains mandatory; retry does not bypass it.

Newly recorded game-file backups have integrity metadata, checked before restore. Legacy journals lacking that metadata retain compatibility but cannot offer the same proof. Missing/damaged backups stop rollback; they are not replaced by a download of guessed originals.

## Manual release checklist

1. Test a clean supported distro with the packaged interpreter/native dependencies, not only the development checkout.
2. Start the GUI via desktop entry; check GTK title bar, Chinese/English, themes, narrow/short windows, enlarged text and reduced motion.
3. Check full keyboard navigation, focus/selected semantics, dialog return and a screen reader.
4. Check chooser/drag-and-drop and AppImage native/FUSE startup.
5. Profile scrolling with representative high-resolution covers and slow mounts; automated decode/layout bounds do not measure real GPU frame time.
6. Perform separately authorized real-game compatibility/Steam/renderer checks before making runtime support claims.

Persistent manifest write failure, process exit between undo and save, legacy unsealed operations, external ReShade writes and lack of file/directory fsync remain documented limitations. These fixes do not make rollback power-loss-proof.
