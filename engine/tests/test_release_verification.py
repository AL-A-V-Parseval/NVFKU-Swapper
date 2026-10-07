"""Maintained release verification is invoked as a standalone CLI."""
import hashlib
import io
import tarfile
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class ReleaseVerificationTest(unittest.TestCase):
    def test_rejects_checksum_mismatch_before_extracting_any_payload(self):
        with tempfile.TemporaryDirectory() as raw:
            out = Path(raw)
            (out / 'fixture.tar.gz').write_bytes(b'changed after packaging')
            digest = hashlib.sha256(b'original artifact').hexdigest()
            (out / 'SHA256SUMS').write_text(f'{digest}  fixture.tar.gz\n')
            result = subprocess.run([sys.executable, str(ROOT / 'tools/verify_release.py'),
                '--out', raw], capture_output=True, text=True, timeout=10)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('checksum mismatch', result.stderr)
            self.assertEqual(sorted(p.name for p in out.iterdir()), ['SHA256SUMS', 'fixture.tar.gz'])

    def test_rejects_traversal_even_when_archive_checksum_matches(self):
        with tempfile.TemporaryDirectory() as raw:
            out = Path(raw)
            artifact = out / 'fixture.tar.gz'
            with tarfile.open(artifact, 'w:gz') as archive:
                info = tarfile.TarInfo('../../must-not-escape.fixture')
                info.size = 7
                archive.addfile(info, io.BytesIO(b'fixture'))
            (out / 'SHA256SUMS').write_text(
                f'{hashlib.sha256(artifact.read_bytes()).hexdigest()}  fixture.tar.gz\n')
            result = subprocess.run([sys.executable, str(ROOT / 'tools/verify_release.py'),
                '--out', raw], capture_output=True, text=True, timeout=10)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('unsafe archive path', result.stderr)

    def test_required_format_gate_runs_before_extraction(self):
        with tempfile.TemporaryDirectory() as raw:
            out = Path(raw)
            artifact = out / 'fixture.tar.gz'
            artifact.write_bytes(b'fixture')
            (out / 'SHA256SUMS').write_text(
                f'{hashlib.sha256(artifact.read_bytes()).hexdigest()}  fixture.tar.gz\n')
            result = subprocess.run([sys.executable, str(ROOT / 'tools/verify_release.py'),
                '--out', raw, '--require-format', 'deb'],
                capture_output=True, text=True, timeout=10)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('required format missing', result.stderr)


if __name__ == '__main__':
    unittest.main()
