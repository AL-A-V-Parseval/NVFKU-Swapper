"""The model catalog and the pinned download.

The point of this module is that a 158 MiB proprietary DLL can be *identified*.
Without a digest table it is an opaque blob, and a user has no way to tell the
build the add-on was measured against from one that reports success on every
evaluate and then crashes the game minutes into play. So these tests are mostly
about the statements the tool makes: which build is this, is it the tested one, and
is the file we just downloaded actually the file we asked for.
"""

from __future__ import annotations

import hashlib
import io
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from nvfku import weights
from nvfku.paths import Paths


class CatalogTest(unittest.TestCase):
    """The digest table itself."""

    def test_the_tested_build_matches_the_one_the_addon_names(self) -> None:
        # This constant is quoted by NapXDD's README and repeated in the UI, so a
        # typo here would send people to a build that was never measured.
        self.assertEqual(
            weights.TESTED_SHA256,
            "e16bcf15e16e13f527491cdf7845b2fe6521a738d8f7c9c721866a8496e1fc8e",
        )
        self.assertEqual(weights.TESTED_SIZE, 165_840_496)
        tested = [b for b in weights.builds() if b.tested]
        self.assertEqual(len(tested), 1, "exactly one build may be called tested")
        self.assertEqual(tested[0].sha256, weights.TESTED_SHA256)

    def test_it_identifies_the_builds_found_on_this_machine(self) -> None:
        cases = {
            "984bee0f775c277d5829b8fd6775d53a7b0f75396c852b3aaf06a18375f81014":
                "Magpie-Experimental",
            "8270b350cd82de5ce89806872cdd6b6a9249b80836b91bbeb3573470744cc206":
                "DLSS5-Swapper",
        }
        for digest, fragment in cases.items():
            build = weights.identify(digest)
            self.assertIsNotNone(build, digest)
            self.assertIn(fragment, build.source)
            self.assertFalse(build.tested, "neither of these is the tested build")

    def test_an_unknown_digest_is_reported_as_unknown(self) -> None:
        self.assertIsNone(weights.identify("0" * 64))

    def test_identification_is_case_insensitive(self) -> None:
        # Digests arrive from tools in either case; a mismatch on case would make
        # the tool deny knowing a build it does know.
        self.assertIsNotNone(weights.identify(weights.TESTED_SHA256.upper()))

    def test_every_build_states_where_it_came_from(self) -> None:
        """A build with no provenance is a build nobody can judge."""
        for build in weights.builds():
            self.assertTrue(build.source.strip(), build.label)
            self.assertTrue(build.label.strip())
            self.assertTrue(build.note.strip(), build.label)
            self.assertIn(build.vendor, {"nvidia", "community"})

    def test_the_cross_generation_build_is_listed_but_not_offered(self) -> None:
        """Honest about what we can and cannot fetch.

        The ShortFuse rebuild is documented for RTX 20/30/40, but no pinned archive
        was found for it. Listing it is useful; inventing a URL for it would not be.
        """
        crossgen = weights.CROSSGEN
        self.assertIsNone(weights.source_for(crossgen))
        self.assertIn("20/30/40", crossgen.note)

    def test_only_the_tested_build_has_a_pinned_source(self) -> None:
        self.assertEqual(len(weights.SOURCES), 1)
        source = weights.SOURCES[0]
        self.assertEqual(source.build.sha256, weights.TESTED_SHA256)
        self.assertTrue(source.url.startswith("https://"))
        # And the source says who signed it, because that is the fact a user cannot
        # check for themselves without opening the file's properties.
        self.assertTrue(source.vendor_signed)

    def test_the_source_is_labelled_a_community_mirror_not_nvidia(self) -> None:
        """The one thing this must never get wrong.

        The DLL is NVIDIA's signed binary; the *download* is a community re-host.
        Presenting it as an NVIDIA download would be a lie the user cannot check.
        """
        source = weights.RTX50_SOURCE
        self.assertIn("rhi-repo", source.url)
        self.assertIn("rankftw", source.url.lower())


def _zip_with(entries: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
    return buffer.getvalue()


class ExtractTest(unittest.TestCase):
    """Extraction verifies the *inner* DLL, not the archive."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def _source(self, payload: bytes) -> weights.Source:
        digest = hashlib.sha256(payload).hexdigest()
        build = weights.Build(
            sha256=digest,
            size=len(payload),
            label="test build",
            version="test",
            source="a test",
            vendor="nvidia",
            tested=False,
            note="a test",
        )
        return weights.Source(
            build=build,
            url="https://example.invalid/x.zip",
            archive="x.zip",
            inner=weights.MODEL_NAME,
            vendor_signed=True,
            origin="test",
        )

    def test_a_matching_archive_is_extracted(self) -> None:
        payload = b"P" * 4096
        source = self._source(payload)
        archive = self.root / source.archive
        archive.write_bytes(_zip_with({weights.MODEL_NAME: payload}))

        out = weights.extract(source, archive, self.root)
        self.assertEqual(out.read_bytes(), payload)

    def test_a_directory_prefix_inside_the_zip_is_tolerated(self) -> None:
        payload = b"P" * 4096
        source = self._source(payload)
        archive = self.root / source.archive
        archive.write_bytes(_zip_with({f"sub/dir/{weights.MODEL_NAME}": payload}))

        out = weights.extract(source, archive, self.root)
        self.assertEqual(out.read_bytes(), payload)

    def test_a_substituted_payload_is_discarded(self) -> None:
        """The whole reason for pinning a digest.

        A zip whose digest cannot be pinned (it changes on repack) still has an
        inner file whose digest can be. If they disagree the file is deleted rather
        than installed, so a substituted model cannot reach a game.
        """
        expected = b"E" * 4096
        source = self._source(expected)
        archive = self.root / source.archive
        archive.write_bytes(_zip_with({weights.MODEL_NAME: b"X" * 4096}))

        with self.assertRaises(weights.WeightsError) as ctx:
            weights.extract(source, archive, self.root)
        self.assertIn("does not match the pinned digest", str(ctx.exception))
        # And nothing was left behind for a later step to pick up.
        self.assertFalse((self.root / source.build.short / weights.MODEL_NAME).exists())

    def test_an_archive_missing_the_dll_says_what_it_holds(self) -> None:
        source = self._source(b"P" * 16)
        archive = self.root / source.archive
        archive.write_bytes(_zip_with({"README.txt": b"hello", "other.dll": b"x"}))

        with self.assertRaises(weights.WeightsError) as ctx:
            weights.extract(source, archive, self.root)
        message = str(ctx.exception)
        self.assertIn(weights.MODEL_NAME, message)
        self.assertIn("README.txt", message, "it names what it found instead")

    def test_a_corrupt_archive_is_removed_so_a_retry_can_work(self) -> None:
        """A truncated download must not be cached as if it were complete."""
        source = self._source(b"P" * 16)
        archive = self.root / source.archive
        archive.write_bytes(b"this is not a zip")

        with self.assertRaises(weights.WeightsError) as ctx:
            weights.extract(source, archive, self.root)
        self.assertIn("not a valid zip", str(ctx.exception))
        self.assertFalse(archive.exists(), "the bad archive was left in the cache")

    def test_a_second_extract_reuses_the_verified_file(self) -> None:
        payload = b"P" * 4096
        source = self._source(payload)
        archive = self.root / source.archive
        archive.write_bytes(_zip_with({weights.MODEL_NAME: payload}))

        first = weights.extract(source, archive, self.root)
        # Delete the archive: a verified file must not need it again.
        archive.unlink()
        second = weights.extract(source, archive, self.root)
        self.assertEqual(first, second)
        self.assertTrue(second.is_file())


class InstallTest(unittest.TestCase):
    """Placing a model copies; it never moves the verified original."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        self.paths = Paths(
            home=self.root, state_root=self.root / "state", steam_root=None
        )
        self.game_dir = self.root / "game"
        self.game_dir.mkdir()

    def _cached(self, payload: bytes = b"M" * 8192) -> weights.Source:
        digest = hashlib.sha256(payload).hexdigest()
        build = weights.Build(
            sha256=digest,
            size=len(payload),
            label="cached",
            version="t",
            source="t",
            vendor="nvidia",
            tested=True,
            note="t",
        )
        source = weights.Source(
            build=build,
            url="https://example.invalid/x.zip",
            archive="x.zip",
            inner=weights.MODEL_NAME,
            vendor_signed=True,
            origin="test",
        )
        cache = self.paths.download_cache() / "weights"
        cache.mkdir(parents=True, exist_ok=True)
        (cache / source.archive).write_bytes(_zip_with({weights.MODEL_NAME: payload}))
        return source

    def test_install_places_the_model_beside_the_executable(self) -> None:
        source = self._cached()
        placed = weights.install(self.paths, self.game_dir, source, logger=lambda *_: None)
        self.assertEqual(placed, self.game_dir / weights.MODEL_NAME)
        self.assertTrue(placed.is_file())
        # The verified copy survives, because every future install draws on it.
        self.assertTrue(
            (self.paths.download_cache() / "weights").is_dir(),
            "the cache was consumed rather than copied from",
        )

    def test_install_is_idempotent_when_the_right_build_is_already_there(self) -> None:
        source = self._cached()
        weights.install(self.paths, self.game_dir, source, logger=lambda *_: None)
        before = (self.game_dir / weights.MODEL_NAME).stat().st_mtime
        weights.install(self.paths, self.game_dir, source, logger=lambda *_: None)
        after = (self.game_dir / weights.MODEL_NAME).stat().st_mtime
        self.assertEqual(before, after, "an already-correct model was rewritten")

    def test_a_failed_download_leaves_no_partial_file(self) -> None:
        """A half-downloaded 104 MiB file must not sit in the cache looking valid."""
        source = self._cached()
        (self.paths.download_cache() / "weights" / source.archive).unlink()

        def explode(*args, **kwargs):
            raise OSError("network is down")

        with mock.patch.object(weights, "_stream", explode):
            with self.assertRaises(weights.WeightsError) as ctx:
                weights.download(self.paths, source, logger=lambda *_: None)
        self.assertIn("download failed", str(ctx.exception))
        leftovers = list((self.paths.download_cache() / "weights").glob("*.part"))
        self.assertEqual(leftovers, [], f"partial files left: {leftovers}")


if __name__ == "__main__":
    unittest.main()


def _table_slice(source: str, language: str) -> dict[str, str]:
    """The `key: value` pairs of one language table in `l10n.dart`.

    A small parser rather than a search over the whole file, because the two tables
    sit side by side by design and a file-wide search cannot tell which language a
    string came from -- which is exactly the mistake this is here to catch.
    """
    import re

    marker = "englishStrings" if language == "en" else "chineseStrings"
    start = source.index(marker)
    end = source.index("\n};", start)
    body = source[start:end]

    out: dict[str, str] = {}
    for match in re.finditer(r"'([\w.]+)':\s*((?:'(?:[^'\\]|\\.)*'\s*)+)", body):
        parts = re.findall(r"'((?:[^'\\]|\\.)*)'", match.group(2))
        out[match.group(1)] = "".join(parts)
    return out


class DocumentationTest(unittest.TestCase):
    """The provenance record must exist, and the UI must not contradict it.

    The user-facing statements about where the model comes from were removed at the
    author's request. The *record* is not removed: `docs/weights.md` and
    `RELEASE.json` still name the source and the digest, because that is what makes a
    shipped 158 MiB binary accountable. These tests protect the record, not the UI.
    """

    def setUp(self) -> None:
        self.root = Path(__file__).resolve().parents[2]
        self.addCleanup(lambda: None)

    def test_the_weights_doc_exists_and_names_the_pinned_digest(self) -> None:
        doc = self.root / "docs/weights.md"
        self.assertTrue(doc.is_file(), "docs/weights.md is referenced but missing")
        text = doc.read_text(encoding="utf-8")
        self.assertIn(weights.TESTED_SHA256, text)
        self.assertIn(weights.RTX50_SOURCE.url, text)

    def test_the_weights_doc_says_the_download_is_a_mirror(self) -> None:
        """The distinction a user cannot check without opening file properties.

        This is in the written record rather than the UI, deliberately: the record
        travels with the source and the release, and cannot be lost to a redesign.
        """
        text = (self.root / "docs/weights.md").read_text(encoding="utf-8").lower()
        self.assertIn("community mirror", text)
        self.assertIn("not an nvidia download", text)

    def test_no_user_facing_string_claims_nvidia_binaries_are_never_downloaded(
        self,
    ) -> None:
        """A claim that is no longer true is worse than no claim.

        Four places used to assert this — the About page, the sidebar footer, the
        settings text and the legal note — and every one became false the moment the
        model fetcher landed. Removing the statements was a choice; leaving a *false*
        one behind would not have been.
        """
        l10n = (self.root / "app/lib/src/l10n.dart").read_text(encoding="utf-8")
        forbidden = (
            "never downloaded by this tool",
            "NVIDIA binaries and model weights are never downloaded",
            "本工具下载，需要你自己提供",
            "不会下载或再分发",
            "NVIDIA 的二进制永远不会被下载",
            "本工具不分发它的任何文件",
            "this tool redistributes nothing of theirs",
        )
        for phrase in forbidden:
            self.assertNotIn(
                phrase,
                l10n,
                f"{phrase!r} is no longer true now that the model fetcher exists",
            )

    def test_the_release_manifest_records_the_model_source(self) -> None:
        """`RELEASE.json` is generated, so this checks the generator.

        Whoever unpacks the archive gets the digest and the fact that the mirror is
        not NVIDIA's own download, which is the minimum for the file to be
        accountable after the fact.
        """
        script = (self.root / "tools/make_release.py").read_text(encoding="utf-8")
        self.assertIn("model_source_note", script)
        self.assertIn("community mirror", script.lower())


if __name__ == "__main__":
    unittest.main()
