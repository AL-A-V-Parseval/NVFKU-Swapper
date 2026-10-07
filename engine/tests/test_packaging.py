"""Release policy at the packaging entry points and artifact seam."""
import contextlib
import multiprocessing
import io
import json
from pathlib import Path
import sys
import subprocess
import shutil
import tempfile
import tarfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools import package


def concurrent_package(out, kind, first_entered, second_entered):
    def build(destination, *, with_model):
        if kind == 'tar':
            first_entered.set()
            second_entered.wait(0.5)
        else:
            second_entered.set()
        artifact = destination / ('first.tar.gz' if kind == 'tar' else 'second.deb')
        artifact.write_bytes(kind.encode())
        return artifact
    with patch('sys.argv', ['package.py', '--format', kind, '--out', str(out)]), \
         patch.object(package, 'APP_BUNDLE', out), \
         patch.object(package, 'build_' + kind, side_effect=build), \
         contextlib.redirect_stdout(io.StringIO()):
        raise SystemExit(package.main())


class PackagingTest(unittest.TestCase):
    def test_all_with_model_refuses_before_creating_any_artifact(self):
        with tempfile.TemporaryDirectory() as raw:
            def build(out, *, with_model):
                artifact = out / 'mock-artifact'
                artifact.write_bytes(b'fixture only')
                return artifact
            with patch('sys.argv', ['package.py', '--format', 'all', '--with-model', '--out', raw]), \
                 patch.object(package, 'APP_BUNDLE', Path(raw)), \
                 patch.object(package, 'build_tar', side_effect=build) as tar, \
                 patch.object(package, 'build_deb', side_effect=build) as deb, \
                 patch.object(package, 'build_appimage', side_effect=build) as image, \
                 contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaises(SystemExit):
                    package.main()
                tar.assert_not_called()
                deb.assert_not_called()
                image.assert_not_called()
            self.assertEqual(list(Path(raw).iterdir()), [])

    def test_deb_builder_itself_refuses_model_before_copying(self):
        with tempfile.TemporaryDirectory() as raw, patch.object(package, 'payload_tree',
                side_effect=AssertionError('model payload must not be copied')):
            with self.assertRaises(SystemExit):
                package.build_deb(Path(raw), with_model=True)
            self.assertEqual(list(Path(raw).iterdir()), [])

    def test_partial_rebuild_preserves_checksums_for_other_existing_artifacts(self):
        with tempfile.TemporaryDirectory() as raw:
            out = Path(raw)
            previous = out / 'older.deb'
            previous.write_bytes(b'previous deb')
            (out / 'SHA256SUMS').write_text(f'{package.sha256_of(previous)}  older.deb\n')
            def build(destination, *, with_model):
                artifact = destination / 'new.tar.gz'
                artifact.write_bytes(b'new tar')
                return artifact
            with patch('sys.argv', ['package.py', '--format', 'tar', '--out', raw]), \
                 patch.object(package, 'APP_BUNDLE', out), \
                 patch.object(package, 'build_tar', side_effect=build), \
                 contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(package.main(), 0)
            self.assertEqual((out / 'SHA256SUMS').read_text(),
                f'{package.sha256_of(previous)}  older.deb\n'
                f'{package.sha256_of(out / "new.tar.gz")}  new.tar.gz\n')

    def test_existing_artifact_is_never_silently_overwritten(self):
        with tempfile.TemporaryDirectory() as raw:
            def payload(staging, *, with_model):
                staging.mkdir(parents=True)
                (staging / 'fixture').write_bytes(b'original fixture')
            with patch.object(package, 'payload_tree', side_effect=payload), \
                 contextlib.redirect_stdout(io.StringIO()):
                first = package.build_tar(Path(raw), with_model=False)
                before = first.read_bytes()
                with self.assertRaises(SystemExit):
                    package.build_tar(Path(raw), with_model=False)
                self.assertEqual(first.read_bytes(), before)

    def test_release_manifest_identifies_source_and_build_not_only_version(self):
        with tempfile.TemporaryDirectory() as raw:
            def payload(staging, *, with_model):
                staging.mkdir(parents=True)
            with patch.object(package, 'payload_tree', side_effect=payload), \
                 contextlib.redirect_stdout(io.StringIO()):
                artifact = package.build_tar(Path(raw), with_model=False)
            with tarfile.open(artifact) as archive:
                metadata = json.load(archive.extractfile('nvfku-swapper/RELEASE.json'))
        self.assertRegex(metadata['build_id'], r'^[A-Za-z0-9][A-Za-z0-9._-]+$')
        source = metadata['source_provenance']
        self.assertRegex(source['revision'], r'^[0-9a-f]{40,64}$')
        self.assertIsInstance(source['dirty'], bool)
        self.assertRegex(source['tree_sha256'], r'^[0-9a-f]{64}$')
        self.assertEqual(metadata['runtime']['python_min'], '3.9')

    def test_deb_declares_python_and_measured_native_runtime_minimum(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            bundle = root / 'bundle'
            bundle.mkdir()
            (bundle / 'nvfku_ui').write_bytes(b'\x7fELFfixture')
            out = root / 'out'
            out.mkdir()
            def payload(staging, *, with_model):
                staging.mkdir(parents=True)
                shutil.copytree(bundle, staging / 'app')
                (staging / 'THIRD_PARTY_NOTICES.md').write_text('fixture notices')
            def icon(destination, size=256):
                destination.write_bytes(b'fixture icon')
                return destination
            original_run = subprocess.run
            def run(args, **kwargs):
                if args[0] == 'readelf':
                    return subprocess.CompletedProcess(args, 0,
                        stdout='Name: GLIBC_2.40\nName: GLIBC_2.34\nName: GLIBCXX_3.4.32\n', stderr='')
                return original_run(args, **kwargs)
            with patch.object(package, 'payload_tree', side_effect=payload), \
                 patch.object(package, 'write_icon', side_effect=icon), \
                 patch.object(package, 'APP_BUNDLE', bundle), \
                 patch.object(package.subprocess, 'run', side_effect=run), \
                 contextlib.redirect_stdout(io.StringIO()):
                artifact = package.build_deb(out, with_model=False)
            data = artifact.read_bytes()
            offset = 8
            members = {}
            while offset < len(data):
                header = data[offset:offset+60]
                size = int(header[48:58])
                members[header[:16].decode().strip().rstrip('/')] = data[offset+60:offset+60+size]
                offset += 60 + size + size % 2
            with tarfile.open(fileobj=io.BytesIO(members['control.tar.gz'])) as archive:
                control = archive.extractfile('control').read().decode()
            self.assertIn('python3 (>= 3.9)', control)
            self.assertIn('libc6 (>= 2.40)', control)
            self.assertIn('libstdc++6 (>= 13.2.0)', control)
            with tarfile.open(fileobj=io.BytesIO(members['data.tar.gz'])) as archive:
                manifest = json.load(archive.extractfile('usr/lib/nvfku/RELEASE.json'))
            self.assertEqual(manifest['runtime']['glibc_min'], '2.40')
            self.assertEqual(manifest['runtime']['glibcxx_min'], '3.4.32')

    def test_changed_previous_artifact_is_refused_before_any_new_build(self):
        with tempfile.TemporaryDirectory() as raw:
            out = Path(raw)
            artifact = out / 'old.deb'
            artifact.write_bytes(b'original')
            (out / 'SHA256SUMS').write_text(f'{package.sha256_of(artifact)}  old.deb\n')
            artifact.write_bytes(b'tampered')
            with patch('sys.argv', ['package.py', '--format', 'tar', '--out', raw]), \
                 patch.object(package, 'APP_BUNDLE', out), \
                 patch.object(package, 'build_tar', side_effect=AssertionError('must reject before build')):
                with self.assertRaises(SystemExit):
                    package.main()

    def test_malformed_checksum_manifest_is_not_silently_replaced(self):
        with tempfile.TemporaryDirectory() as raw:
            out = Path(raw)
            original = 'not-a-sha256  missing.deb\n'
            (out / 'SHA256SUMS').write_text(original)
            with patch('sys.argv', ['package.py', '--format', 'tar', '--out', raw]), \
                 patch.object(package, 'APP_BUNDLE', out), \
                 patch.object(package, 'build_tar', side_effect=AssertionError('invalid manifest must stop build')):
                with self.assertRaises(SystemExit):
                    package.main()
            self.assertEqual((out / 'SHA256SUMS').read_text(), original)

    def test_concurrent_partial_builds_do_not_lose_each_others_checksums(self):
        with tempfile.TemporaryDirectory() as raw:
            out = Path(raw)
            context = multiprocessing.get_context('fork')
            first_entered, second_entered = context.Event(), context.Event()
            first = context.Process(target=concurrent_package, args=(out, 'tar', first_entered, second_entered))
            second = context.Process(target=concurrent_package, args=(out, 'deb', first_entered, second_entered))
            first.start()
            self.assertTrue(first_entered.wait(5))
            second.start()
            try:
                for process in (first, second):
                    process.join(10)
                    self.assertEqual(process.exitcode, 0)
            finally:
                for process in (first, second):
                    if process.is_alive():
                        process.terminate()
                    process.join()
            names = {line.split('  ', 1)[1] for line in (out / 'SHA256SUMS').read_text().splitlines()}
            self.assertEqual(names, {'first.tar.gz', 'second.deb'})

    def test_private_and_public_format_policy_matrix(self):
        for kind, with_model, refused in (('deb', True, True), ('all', True, True),
                ('tar', True, False), ('appimage', True, False),
                ('deb', False, False), ('all', False, False)):
            with self.subTest(format=kind, with_model=with_model), tempfile.TemporaryDirectory() as raw:
                out = Path(raw)
                def build(destination, *, with_model):
                    artifact = destination / 'fixture-artifact'
                    artifact.write_bytes(b'no actual model')
                    return artifact
                arguments = ['package.py', '--format', kind, '--out', raw]
                if with_model:
                    arguments.append('--with-model')
                with patch('sys.argv', arguments), patch.object(package, 'APP_BUNDLE', out), \
                     patch.object(package, 'build_tar', side_effect=build) as tar, \
                     patch.object(package, 'build_deb', side_effect=build) as deb, \
                     patch.object(package, 'build_appimage', side_effect=build) as image, \
                     contextlib.redirect_stdout(io.StringIO()):
                    if refused:
                        with self.assertRaises(SystemExit):
                            package.main()
                        self.assertEqual(tar.call_count + deb.call_count + image.call_count, 0)
                    else:
                        self.assertEqual(package.main(), 0)
                        self.assertEqual(tar.call_count + deb.call_count + image.call_count,
                                         3 if kind == 'all' else 1)


if __name__ == '__main__':
    unittest.main()
