"""Integrity at the agreed rollback, provider fetch and weights download seams."""
import dataclasses
import hashlib
import io
import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from nvfku import providers, weights
from nvfku.journal import FileJournal, load_journal, rollback_journal
from nvfku.paths import Paths


class IntegrityRecoveryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.paths = Paths(home=self.root, state_root=self.root / 'state')
        self.game = self.root / 'game'
        self.game.mkdir()
        self.src = self.root / 'source.dll'
        self.src.write_bytes(b'INSTALLED')

    def test_symlink_backup_and_marker_must_match_recorded_link(self):
        for fault in ('marker', 'backup', 'both', 'missing-marker', 'missing-backup'):
            with self.subTest(fault=fault):
                dest = self.game / 'linked.dll'
                dest.unlink(missing_ok=True)
                dest.symlink_to('original target ')
                journal = FileJournal(self.paths, self.game, 'a1')
                op = journal.install_file(self.src, dest)
                journal.finish()
                pre = journal.dir / op.backup
                marker = pre.with_suffix(pre.suffix + '.symlink')
                if fault in ('marker', 'both'):
                    marker.write_text('changed')
                if fault in ('backup', 'both'):
                    pre.write_text('changed')
                if fault == 'missing-marker':
                    marker.unlink()
                if fault == 'missing-backup':
                    pre.unlink()
                self.assertFalse(rollback_journal(self.paths, journal.journal_id).ok)
                self.assertEqual(dest.read_bytes(), b'INSTALLED')
                pre.write_text('original target ')
                marker.write_text('original target ')
                self.assertTrue(rollback_journal(self.paths, journal.journal_id).ok)
                self.assertEqual(os.readlink(dest), 'original target ')

    def test_every_game_preimage_writer_checks_integrity(self):
        for writer in ('write_text', 'remove', 'adopt'):
            for symlink in (False, True):
                with self.subTest(writer=writer, symlink=symlink):
                    dest = self.game / 'original.dll'
                    dest.unlink(missing_ok=True)
                    backing = self.root / 'backing'
                    backing.write_bytes(b'ORIGINAL')
                    if symlink:
                        dest.symlink_to(backing)
                    else:
                        dest.write_bytes(b'ORIGINAL')
                    journal = FileJournal(self.paths, self.game, 'a1')
                    if writer == 'write_text':
                        op = journal.write_text(dest, 'INSTALLED')
                    elif writer == 'remove':
                        op = journal.remove(dest)
                    else:
                        op = journal.adopt(dest)
                        dest.unlink()
                        dest.write_bytes(b'INSTALLED')
                    journal.finish()
                    pre = journal.dir / op.backup
                    if pre.is_symlink():
                        pre.unlink()
                    pre.write_bytes(b'CORRUPTD')
                    if symlink:
                        pre.with_suffix(pre.suffix + '.symlink').write_text('CORRUPTD')
                    before = dest.read_bytes() if dest.exists() else None
                    self.assertFalse(rollback_journal(self.paths, journal.journal_id).ok)
                    self.assertEqual(dest.read_bytes() if dest.exists() else None, before)

    def test_component_cache_hit_checks_size_and_digest(self):
        component = providers.Component('fixture', 'fixture', 'v1', 'https://example.invalid/file', size=8, filename='file.dll')
        target = component.local_path(self.paths)
        for bad, digest in ((b'X', None), (b'CORRUPTD', hashlib.sha256(b'ORIGINAL').hexdigest())):
            with self.subTest(bad=bad):
                component.sha256 = digest
                target.write_bytes(bad)
                with mock.patch.object(providers, 'http_get', return_value=b'ORIGINAL') as get:
                    result = providers.fetch(component, self.paths, logger=lambda _: None)
                self.assertEqual(result.read_bytes(), b'ORIGINAL')
                get.assert_called_once()

    def test_component_short_write_never_publishes_partial_cache(self):
        component = providers.Component('fixture', 'fixture', 'v1', 'https://example.invalid/file', size=8, filename='file.dll')
        target = component.local_path(self.paths)
        original_write = Path.write_bytes
        def short_write(path, content):
            original_write(path, content[:1])
            raise OSError(28, 'No space left on device')
        with mock.patch.object(providers, 'http_get', return_value=b'ORIGINAL'):
            with mock.patch.object(Path, 'write_bytes', short_write):
                with self.assertRaises(OSError):
                    providers.fetch(component, self.paths, logger=lambda _: None)
            self.assertFalse(target.exists())
            self.assertEqual(list(target.parent.glob('*.part')), [])
            self.assertEqual(providers.fetch(component, self.paths, logger=lambda _: None).read_bytes(), b'ORIGINAL')

    def test_same_named_component_and_sums_follow_version_and_url(self):
        first = providers.Component('fixture', 'fixture', 'v1', 'https://example.invalid/v1/file', size=8, filename='file.dll')
        for updated in (dataclasses.replace(first, version='v2'), dataclasses.replace(first, url='https://other.invalid/file')):
            with self.subTest(updated=updated):
                with mock.patch.object(providers, 'http_get', side_effect=[b'ORIGINAL', b'OLD SUMS', b'UPDATED!', b'NEW SUMS']) as get:
                    providers.fetch(first, self.paths, logger=lambda _: None)
                    old_sums = providers.fetch_asset(first, 'SHA256SUMS.txt', self.paths, logger=lambda _: None)
                    result = providers.fetch(updated, self.paths, logger=lambda _: None)
                    sums = providers.fetch_asset(updated, 'SHA256SUMS.txt', self.paths, logger=lambda _: None)
                self.assertEqual(result.read_bytes(), b'UPDATED!')
                self.assertEqual(sums.read_bytes(), b'NEW SUMS')
                self.assertEqual(get.call_count, 4)
                # Clean fixtures through their known paths, not real downloads.
                first.local_path(self.paths).unlink()
                old_sums.unlink()

    def test_skip_download_checks_cache_without_network(self):
        component = providers.Component('fixture', 'fixture', 'v1', 'https://example.invalid/file', size=8, filename='file.dll', sha256=hashlib.sha256(b'ORIGINAL').hexdigest())
        target = component.local_path(self.paths)
        with mock.patch.object(providers, 'http_get', side_effect=AssertionError('network forbidden')):
            for bad in (None, b'X', b'CORRUPTD'):
                with self.subTest(bad=bad):
                    if bad is not None:
                        target.write_bytes(bad)
                    with self.assertRaises(ValueError):
                        providers.fetch(component, self.paths, logger=lambda _: None, skip_download=True)
            target.write_bytes(b'ORIGINAL')
            self.assertEqual(providers.fetch(component, self.paths, logger=lambda _: None, skip_download=True), target)

    def test_a1_reports_size_only_when_upstream_digest_unavailable(self):
        from engine.tests.test_install import Sandbox
        from nvfku import model
        from nvfku.route import a1_bridge
        sandbox = Sandbox()
        self.addCleanup(sandbox.cleanup)
        self.addCleanup(model.set_discovery_override, None)
        sandbox.stub_components()
        sandbox.stub_model()
        result = a1_bridge.install(sandbox.paths, sandbox.game(), skip_download=True,
                                   proc_root='/nonexistent-proc', logger=lambda _: None)
        self.assertTrue(any('size-only' in warning for warning in result.warnings), result.warnings)
        self.assertFalse(any('upstream SHA-256' in item for item in result.verified))

    def test_model_retry_refetches_legal_zip_with_bad_digest(self):
        from engine.tests.test_weights import _zip_with
        expected = b'ORIGINAL'
        build = weights.Build(hashlib.sha256(expected).hexdigest(), 8, 'fixture', 'v1', 'fixture', 'nvidia', False, 'fixture')
        source = weights.Source(build, 'https://example.invalid/model.zip', 'fixture.zip', weights.MODEL_NAME, True, 'fixture')
        responses = iter([_zip_with({weights.MODEL_NAME: b'CORRUPTD'}), _zip_with({weights.MODEL_NAME: expected})])
        def stream(url, target, **kwargs):
            target.write_bytes(next(responses))
        with mock.patch.object(weights, '_stream', side_effect=stream) as fetch:
            with self.assertRaisesRegex(weights.WeightsError, 'pinned digest'):
                weights.download(self.paths, source, logger=lambda _: None)
            self.assertEqual(fetch.call_count, 1, 'no unbounded automatic retry')
            recovered = weights.download(self.paths, source, logger=lambda _: None)
            self.assertEqual(recovered.read_bytes(), expected)
            self.assertEqual(fetch.call_count, 2)

    def test_model_retry_refetches_zip_missing_required_member(self):
        from engine.tests.test_weights import _zip_with
        expected = b'ORIGINAL'
        build = weights.Build(hashlib.sha256(expected).hexdigest(), 8, 'fixture', 'v1', 'fixture', 'nvidia', False, 'fixture')
        source = weights.Source(build, 'https://example.invalid/model.zip', 'fixture.zip', weights.MODEL_NAME, True, 'fixture')
        responses = iter([_zip_with({'README.txt': b'wrong archive'}), _zip_with({weights.MODEL_NAME: expected})])
        def stream(url, target, **kwargs):
            target.write_bytes(next(responses))
        with mock.patch.object(weights, '_stream', side_effect=stream) as fetch:
            with self.assertRaisesRegex(weights.WeightsError, 'does not contain'):
                weights.download(self.paths, source, logger=lambda _: None)
            self.assertEqual(fetch.call_count, 1)
            recovered = weights.download(self.paths, source, logger=lambda _: None)
            self.assertEqual(recovered.read_bytes(), expected)
            self.assertEqual(fetch.call_count, 2)

    def test_download_validates_staged_bytes_before_atomic_publish(self):
        component = providers.Component('fixture', 'fixture', 'v1', 'https://example.invalid/file', size=8, filename='file.dll', sha256=hashlib.sha256(b'ORIGINAL').hexdigest())
        target = component.local_path(self.paths)
        original_write = Path.write_bytes
        def damaged_write(path, content):
            return original_write(path, b'CORRUPTD')
        with mock.patch.object(providers, 'http_get', return_value=b'ORIGINAL'):
            with mock.patch.object(Path, 'write_bytes', damaged_write):
                with self.assertRaises(ValueError):
                    providers.fetch(component, self.paths, logger=lambda _: None)
        self.assertFalse(target.exists())

    def test_unsealed_symlink_uses_exact_validated_preimage(self):
        dest = self.game / 'linked.dll'
        dest.symlink_to('original target ')
        journal = FileJournal(self.paths, self.game, 'a1')
        replace = os.replace
        def interrupt(src, target):
            if Path(target) == dest:
                raise OSError('install interrupted')
            return replace(src, target)
        with mock.patch('nvfku.journal.os.replace', side_effect=interrupt):
            with self.assertRaises(OSError):
                journal.install_file(self.src, dest)
        self.assertTrue(rollback_journal(self.paths, journal.journal_id).ok)
        self.assertEqual(os.readlink(dest), 'original target ')

    def test_unpinned_download_cache_detects_same_size_local_corruption(self):
        component = providers.Component('fixture', 'fixture', 'v1', 'https://example.invalid/file', size=8, filename='file.dll')
        with mock.patch.object(providers, 'http_get', return_value=b'ORIGINAL') as get:
            target = providers.fetch(component, self.paths, logger=lambda _: None)
            target.write_bytes(b'CORRUPTD')
            with self.assertRaises(ValueError):
                providers.fetch(component, self.paths, skip_download=True, logger=lambda _: None)
            self.assertEqual(providers.fetch(component, self.paths, logger=lambda _: None).read_bytes(), b'ORIGINAL')
            self.assertEqual(get.call_count, 2)

    def test_malformed_cache_receipt_is_a_cache_miss_not_a_crash(self):
        component = providers.Component('fixture', 'fixture', 'v1', 'https://example.invalid/file', filename='file.dll')
        with mock.patch.object(providers, 'http_get', return_value=b'ORIGINAL'):
            target = providers.fetch(component, self.paths, logger=lambda _: None)
            receipt = target.with_name(target.name + '.integrity.json')
            receipt.write_text(json.dumps({'version': 'v1', 'url': component.url, 'sha256': 42, 'size': 8}))
            with self.assertRaises(ValueError):
                providers.fetch(component, self.paths, skip_download=True, logger=lambda _: None)
            self.assertEqual(providers.fetch(component, self.paths, logger=lambda _: None).read_bytes(), b'ORIGINAL')

    def test_concurrent_component_fetches_publish_complete_cache(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        component = providers.Component('fixture', 'fixture', 'v1', 'https://example.invalid/file', size=8, filename='file.dll')
        barrier = Barrier(2)
        def get(*args, **kwargs):
            barrier.wait(timeout=5)
            return b'ORIGINAL'
        with mock.patch.object(providers, 'http_get', side_effect=get):
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(lambda _: providers.fetch(component, self.paths, logger=lambda _: None), range(2)))
        self.assertTrue(all(path.read_bytes() == b'ORIGINAL' for path in results))
        with mock.patch.object(providers, 'http_get', side_effect=AssertionError('must reuse valid cache')):
            self.assertEqual(providers.fetch(component, self.paths, skip_download=True, logger=lambda _: None).read_bytes(), b'ORIGINAL')
        self.assertEqual(list(results[0].parent.glob('*.part')), [])

    def test_legacy_unsealed_regular_and_symlink_backups_remain_restorable(self):
        for shape in ('regular', 'text-link', 'actual-link'):
            with self.subTest(shape=shape):
                dest = self.game / 'original.dll'
                dest.unlink(missing_ok=True)
                if shape == 'regular':
                    dest.write_bytes(b'ORIGINAL')
                else:
                    dest.symlink_to('original target ')
                journal = FileJournal(self.paths, self.game, 'a1')
                op = journal.install_file(self.src, dest)
                manifest = journal.finish()
                data = json.loads(manifest.read_text())
                for key in ('pre_image', 'post_image', 'sha256', 'size'):
                    data['operations'][-1].pop(key, None)
                manifest.write_text(json.dumps(data))
                if shape == 'actual-link':
                    pre = journal.dir / op.backup
                    pre.unlink()
                    pre.symlink_to('original target ')
                self.assertTrue(rollback_journal(self.paths, journal.journal_id).ok)
                if shape == 'regular':
                    self.assertEqual(dest.read_bytes(), b'ORIGINAL')
                else:
                    self.assertEqual(os.readlink(dest), 'original target ')

    def test_model_size_mismatch_reports_original_reason_and_invalidates_zip(self):
        from engine.tests.test_weights import _zip_with
        expected = b'ORIGINAL'
        build = weights.Build(hashlib.sha256(expected).hexdigest(), 9, 'fixture', 'v1', 'fixture', 'nvidia', False, 'fixture')
        source = weights.Source(build, 'https://example.invalid/model.zip', 'fixture.zip', weights.MODEL_NAME, True, 'fixture')
        def stream(url, target, **kwargs):
            target.write_bytes(_zip_with({weights.MODEL_NAME: expected}))
        with mock.patch.object(weights, '_stream', side_effect=stream):
            with self.assertRaisesRegex(weights.WeightsError, '8 bytes, expected 9'):
                weights.download(self.paths, source, logger=lambda _: None)
        self.assertFalse((self.paths.download_cache() / 'weights' / source.archive).exists())

    def test_corrupt_regular_backup_is_rejected_and_can_be_repaired(self):
        for corruption in (b'X', b'CORRUPTD', None):
            with self.subTest(corruption=corruption):
                dest = self.game / 'original.dll'
                dest.write_bytes(b'ORIGINAL')
                journal = FileJournal(self.paths, self.game, 'a1')
                op = journal.install_file(self.src, dest)
                journal.finish()
                pre = journal.dir / op.backup
                if corruption is None:
                    pre.unlink()
                else:
                    pre.write_bytes(corruption)
                report = rollback_journal(self.paths, journal.journal_id)
                self.assertFalse(report.ok)
                self.assertEqual(dest.read_bytes(), b'INSTALLED')
                saved = load_journal(self.paths, journal.journal_id)
                self.assertFalse(saved.rolled_back)
                self.assertFalse(saved.operations[-1].rollback_done)
                pre.write_bytes(b'ORIGINAL')
                self.assertTrue(rollback_journal(self.paths, journal.journal_id).ok)
                self.assertEqual(dest.read_bytes(), b'ORIGINAL')
