"""The release packager, and the one thing it must never get wrong.

Everything in `tools/make_release.py` is copying except the model check. The model
is 158 MiB of NVIDIA's proprietary binary with no official download, and the wrong
build does not fail cleanly: it reports success on every evaluate and then crashes
the game minutes into play. A user cannot diagnose that from a bug report, and a
packager that ships it silently is the only thing standing between them and it.

So the refusal paths are tested here, in the same spirit as the digest table itself.
"""

from __future__ import annotations

import hashlib
import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _load_packager():
    """Import `tools/make_release.py`, which is a script rather than a module."""
    path = ROOT / "tools/make_release.py"
    spec = importlib.util.spec_from_file_location("make_release", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class ModelVerificationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.packager = _load_packager()
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def _model(self, content: bytes) -> tuple[Path, str, int]:
        path = self.root / "nvngx_dlssnr.dll"
        path.write_bytes(content)
        return path, hashlib.sha256(content).hexdigest(), len(content)

    def test_a_matching_model_is_accepted(self) -> None:
        path, digest, size = self._model(b"M" * 4096)
        self.assertEqual(
            self.packager.verify_model(digest, size, model=path), path
        )

    def test_a_missing_model_refuses_and_says_how_to_get_one(self) -> None:
        """The message has to be actionable: this is the first thing a builder hits."""
        with self.assertRaises(SystemExit) as ctx:
            self.packager.verify_model("a" * 64, 4096, model=self.root / "absent.dll")
        message = str(ctx.exception)
        self.assertIn("no vendored model", message)
        self.assertIn("mirror-sync", message, "it names the command that fixes it")

    def test_a_wrong_size_is_refused_before_hashing(self) -> None:
        """Sizes first: it is free, and a truncated file is the common failure."""
        path, digest, _ = self._model(b"M" * 4096)
        with self.assertRaises(SystemExit) as ctx:
            self.packager.verify_model(digest, 999_999, model=path)
        self.assertIn("bytes, expected", str(ctx.exception))

    def test_a_substituted_model_is_refused(self) -> None:
        """The case that matters: right size, wrong build.

        Every build of this file is the same size, so a size check alone passes a
        model that will crash the game. Only the digest separates them.
        """
        path, _, size = self._model(b"X" * 4096)
        with self.assertRaises(SystemExit) as ctx:
            self.packager.verify_model("b" * 64, size, model=path)
        message = str(ctx.exception)
        self.assertIn("does not match the digest", message)
        self.assertIn("crash games", message, "it states the consequence")

    def test_the_expected_constants_come_from_the_engine(self) -> None:
        """No second copy of the digest to drift out of sync."""
        import sys

        sys.path.insert(0, str(ROOT / "engine"))
        from nvfku import weights

        sha, size, url = self.packager.engine_constants()
        self.assertEqual(sha, weights.TESTED_SHA256)
        self.assertEqual(size, weights.TESTED_SIZE)
        self.assertEqual(url, weights.RTX50_SOURCE.url)


class LauncherTest(unittest.TestCase):
    """The launcher must find its engine from wherever it is unpacked."""

    def setUp(self) -> None:
        self.packager = _load_packager()
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def test_the_cli_launcher_runs_the_module_not_a_file(self) -> None:
        """`python3 model --verify x` is read as "run the file `model`".

        That is precisely the bug a first version shipped: the `-m nvfku` was
        dropped, so every subcommand failed with a confusing message about a
        missing file named after the subcommand.
        """
        target = self.root / "nvfku"
        self.packager.write_launcher(target, "test launcher")
        text = target.read_text(encoding="utf-8")
        self.assertIn("python3 -m nvfku", text)
        self.assertIn('"$@"', text)
        self.assertIn("HERE=", text, "it resolves its own directory")
        self.assertTrue(target.stat().st_mode & 0o111, "it is executable")

    def test_it_uses_a_relative_root_so_the_tree_can_move(self) -> None:
        target = self.root / "nvfku"
        self.packager.write_launcher(target, "test launcher")
        text = target.read_text(encoding="utf-8")
        self.assertNotIn(str(ROOT), text, "an absolute build path got baked in")
        self.assertIn('$HERE/engine', text)


if __name__ == "__main__":
    unittest.main()
