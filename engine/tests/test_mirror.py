"""The vendored mirror of the DLSS Neural Rendering model.

The mirror exists so a checkout can hold one *verified* copy of a 158 MiB
proprietary DLL without committing it, and so a routine "is it there?" question
costs nothing. That makes two properties worth pinning down here, because both
guard against a specific 158 MiB failure:

*   **A verified mirror is never re-downloaded.** The archive is ~104 MiB and the
    DLL ~158 MiB, so a `sync` that already has the pinned build must stop before it
    reaches the fetcher. That is asserted by mocking the downloader and checking it
    was never called, not by watching a log line.
*   **The destination is only ever absent or complete.** `sync` copies to a
    temporary file and moves it into place, so a failure mid-copy cannot publish a
    truncated file that a later `inspect` would call "present".

No test here touches the network or fabricates a 165,840,496-byte file. `mirror`
reads `weights.TESTED_SHA256` at call time, so `_pinned()` below substitutes that
constant for content a test generated and every digest check runs for real against
a few hundred bytes.
"""

from __future__ import annotations

import contextlib
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from nvfku import mirror, weights
from nvfku.paths import Paths


@contextlib.contextmanager
def _pinned(digest: str):
    """Pretend ``digest`` is the project's pinned digest for this block.

    ``mirror.weights`` is the same module object as ``weights``, so patching the
    attribute here is seen by every `mirror` call that reads it. This is the seam
    that makes the digest checks testable without network access: the alternative
    is a fixture of exactly 165,840,496 bytes whose SHA-256 happens to be the one
    NVIDIA signed, which no test suite can generate.
    """
    with mock.patch.object(weights, "TESTED_SHA256", digest):
        yield digest


def _fail_after(prefix: bytes, message: str = "no space left on device"):
    """A ``shutil.copyfileobj`` stand-in that writes part of the file, then fails.

    This is the shape of a real full disk or an interrupted process: the copy is
    under way, some bytes have landed, and the write stops. Patching it as the copy
    primitive is what lets a test drive `sync`'s own cleanup and atomicity rather
    than hoping the filesystem behaves badly at the right moment.
    """

    def copyfileobj(src, dst, length: int = 0) -> None:
        dst.write(prefix)
        dst.flush()
        raise OSError(message)

    return copyfileobj


class VendorDirTest(unittest.TestCase):
    """The vendored slot has to be found from the checkout, wherever it is."""

    def test_the_vendor_dir_is_derived_from_the_package_location(self) -> None:
        expected = Path(mirror.__file__).resolve().parents[2] / "vendor" / "weights"
        self.assertEqual(
            mirror.VENDOR_DIR,
            expected,
            "vendor/weights must sit under the project root, not at a hard-coded path",
        )
        self.assertEqual(
            mirror.VENDOR_DIR.parent.name,
            "vendor",
            "the mirror's parent directory must be vendor/, not somewhere else in the tree",
        )
        self.assertEqual(
            mirror.VENDOR_DIR.name,
            "weights",
            "the mirror must live in a subdirectory named weights, as the README documents",
        )


class InspectTest(unittest.TestCase):
    """`inspect` is the UI's call, so every bad state is an answer, never a raise."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        self.vendor = self.root / "vendor" / "weights"

    def _place(self, payload: bytes) -> Path:
        self.vendor.mkdir(parents=True, exist_ok=True)
        target = self.vendor / weights.MODEL_NAME
        target.write_bytes(payload)
        return target

    def test_a_missing_directory_is_not_present_and_does_not_raise(self) -> None:
        state = mirror.inspect(self.root / "never-created")
        self.assertFalse(
            state.present, "a directory that does not exist was reported as holding a model"
        )
        self.assertFalse(state.verified, "nothing on disk cannot be the pinned build")
        self.assertIsNone(state.sha256, "no file was read, so there is no digest to report")
        self.assertIsNone(state.size, "no file was read, so there is no size to report")
        self.assertTrue(state.url, "even the empty state must say where a copy would come from")
        self.assertTrue(state.describe(), "the UI always has something to render")

    def test_an_empty_directory_is_not_present(self) -> None:
        self.vendor.mkdir(parents=True)
        state = mirror.inspect(self.vendor)
        self.assertFalse(state.present, "an empty vendor directory is not a vendored copy")

    def test_a_wrong_digest_is_reported_with_the_actual_digest(self) -> None:
        """A same-size build that is not the measured one is the dangerous case."""
        payload = b"a build that is not the one the add-on was measured against"
        self._place(payload)
        state = mirror.inspect(self.vendor)
        self.assertTrue(state.present, "the file exists and must be reported as present")
        self.assertFalse(
            state.verified,
            "reporting a substituted build as verified is the exact failure this module exists to prevent",
        )
        self.assertEqual(
            state.sha256,
            hashlib.sha256(payload).hexdigest(),
            "the reported digest is not the file's digest, so the UI would name the wrong build",
        )
        self.assertEqual(
            state.size, len(payload), "the reported size does not match the file on disk"
        )
        self.assertIn(state.sha256, state.describe(), "the sentence names the digest it found")

    def test_the_pinned_digest_is_reported_as_verified(self) -> None:
        payload = b"content standing in for the pinned model"
        digest = hashlib.sha256(payload).hexdigest()
        self._place(payload)
        with _pinned(digest):
            state = mirror.inspect(self.vendor)
            self.assertTrue(state.verified, "matching the pinned digest is the only definition of verified")
            self.assertIn(
                "verified",
                state.describe(),
                "the human sentence does not tell the user the copy is the pinned build",
            )


class SyncTest(unittest.TestCase):
    """`sync` fetches only when it must, and publishes only complete files."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        self.vendor = self.root / "vendor" / "weights"
        self.paths = Paths(home=self.root, state_root=self.root / "state")

    def _place(self, payload: bytes) -> Path:
        self.vendor.mkdir(parents=True, exist_ok=True)
        target = self.vendor / weights.MODEL_NAME
        target.write_bytes(payload)
        return target

    def _downloaded(self, payload: bytes) -> Path:
        """The file `weights.download` would have returned, with no network."""
        source_file = self.root / "downloaded" / weights.MODEL_NAME
        source_file.parent.mkdir(parents=True, exist_ok=True)
        source_file.write_bytes(payload)
        return source_file

    def test_an_already_verified_mirror_is_not_downloaded_again(self) -> None:
        """The assertion that protects a 104 MiB fetch from happening every sync."""
        payload = b"the pinned model, for this test"
        digest = hashlib.sha256(payload).hexdigest()
        self._place(payload)
        with _pinned(digest):
            with mock.patch.object(weights, "download") as downloader:
                state = mirror.sync(
                    vendor_dir=self.vendor, paths=self.paths, logger=lambda *_: None
                )
        downloader.assert_not_called()
        self.assertTrue(state.verified, "an already-verified mirror was not reported back")
        self.assertEqual(
            state.sha256, digest, "the reported digest is not the one that was on disk"
        )

    def test_sync_copies_the_downloaded_file_into_place(self) -> None:
        payload = b"a few bytes standing in for 158 MiB"
        digest = hashlib.sha256(payload).hexdigest()
        cached = self._downloaded(payload)
        with _pinned(digest):
            with mock.patch.object(weights, "download", return_value=cached) as downloader:
                state = mirror.sync(
                    vendor_dir=self.vendor, paths=self.paths, logger=lambda *_: None
                )
            target = self.vendor / weights.MODEL_NAME
            self.assertEqual(
                downloader.call_count,
                1,
                "the pinned archive must come from weights.download",
            )
            self.assertTrue(
                target.is_file(),
                "sync must create vendor/weights itself, not assume the directory exists",
            )
            self.assertEqual(
                target.read_bytes(),
                payload,
                "the vendored bytes differ from the verified source",
            )
            self.assertTrue(
                state.verified,
                "sync did not report the copy it just verified as verified",
            )
            self.assertTrue(
                mirror.inspect(self.vendor).verified,
                "a fresh inspect must agree with the state sync returned",
            )

    def test_a_mismatch_deletes_the_destination_and_raises(self) -> None:
        """Copying is where a truncated write appears, so it is checked again."""
        self._place(b"a previous, still-wrong build")
        cached = self._downloaded(b"freshly fetched, and still not the pinned build")
        target = self.vendor / weights.MODEL_NAME
        with mock.patch.object(weights, "download", return_value=cached):
            with self.assertRaises(weights.WeightsError) as ctx:
                mirror.sync(
                    vendor_dir=self.vendor, paths=self.paths, logger=lambda *_: None
                )
        self.assertIn(
            "does not match the pinned digest",
            str(ctx.exception),
            "a mismatch was not reported as a mismatch",
        )
        self.assertIn("expected", str(ctx.exception), "the message must state what it wanted")
        self.assertFalse(
            target.exists(),
            "a copy that failed verification was left where an install could pick it up",
        )

    def test_a_failed_copy_leaves_no_temporary_files_behind(self) -> None:
        cached = self._downloaded(b"x" * 4096)
        self.vendor.mkdir(parents=True)
        with mock.patch.object(weights, "download", return_value=cached):
            with mock.patch.object(
                mirror.shutil, "copyfileobj", _fail_after(b"half a file")
            ):
                with self.assertRaises(weights.WeightsError):
                    mirror.sync(
                        vendor_dir=self.vendor, paths=self.paths, logger=lambda *_: None
                    )
        leftovers = sorted(entry.name for entry in self.vendor.iterdir())
        self.assertEqual(
            leftovers,
            [],
            f"a failed sync left files behind for a later run to trip over: {leftovers}",
        )

    def test_the_destination_is_never_a_partial_file(self) -> None:
        """The atomicity guarantee: the slot is empty or complete, never in between."""
        cached = self._downloaded(b"x" * 4096)
        target = self.vendor / weights.MODEL_NAME

        # Nothing was there before: a failure must not create anything at all.
        with mock.patch.object(weights, "download", return_value=cached):
            with mock.patch.object(
                mirror.shutil, "copyfileobj", _fail_after(b"half a file")
            ):
                with self.assertRaises(weights.WeightsError):
                    mirror.sync(
                        vendor_dir=self.vendor, paths=self.paths, logger=lambda *_: None
                    )
        self.assertFalse(
            target.exists(), "a failure during the copy published a partial file"
        )

        # A verified copy was there before: a failed refresh must leave it intact,
        # which only holds because the new bytes never touch the destination.
        good = b"a verified stand-in already in the slot"
        digest = hashlib.sha256(good).hexdigest()
        with _pinned(digest):
            self._place(good)
            with mock.patch.object(weights, "download", return_value=cached):
                with mock.patch.object(
                    mirror.shutil, "copyfileobj", _fail_after(b"half a file")
                ):
                    with self.assertRaises(weights.WeightsError):
                        mirror.sync(
                            vendor_dir=self.vendor,
                            paths=self.paths,
                            logger=lambda *_: None,
                            force=True,
                        )
            self.assertEqual(
                target.read_bytes(),
                good,
                "a failed refresh damaged the verified mirror it was replacing",
            )
            self.assertTrue(
                mirror.inspect(self.vendor).verified,
                "the surviving destination is no longer the complete verified file",
            )


class PruneTest(unittest.TestCase):
    """`prune` exists so 158 MiB can be removed without wondering what else went."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        self.vendor = self.root / "vendor" / "weights"

    def test_prune_removes_the_copy_and_reports_it(self) -> None:
        self.vendor.mkdir(parents=True)
        target = self.vendor / weights.MODEL_NAME
        target.write_bytes(b"a vendored copy")
        self.assertTrue(mirror.prune(self.vendor), "prune did not report removing the file")
        self.assertFalse(target.exists(), "the vendored file is still on disk after prune")

    def test_prune_on_an_empty_directory_reports_false(self) -> None:
        self.vendor.mkdir(parents=True)
        self.assertFalse(mirror.prune(self.vendor), "prune claimed to delete something that was not there")

    def test_prune_on_a_missing_directory_reports_false(self) -> None:
        self.assertFalse(mirror.prune(self.root / "gone"))


if __name__ == "__main__":
    unittest.main()
