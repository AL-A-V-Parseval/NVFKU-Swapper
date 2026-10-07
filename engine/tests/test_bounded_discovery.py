"""Cold discovery through public Steam scan and model.discover seams."""
import os
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from unittest import mock

from nvfku import model, steam
from nvfku.paths import Paths
from engine.tests.test_install import Sandbox


class BoundedDiscoveryTest(unittest.TestCase):
    def setUp(self):
        self.sandbox = Sandbox()
        self.addCleanup(self.sandbox.cleanup)
        self.root = self.sandbox.install_dir
        self.paths = self.sandbox.paths

    def test_large_no_match_tree_stops_at_directory_budget_and_reports_incomplete(self):
        for index in range(100):
            (self.root / f'tree{index:03d}' / 'deep').mkdir(parents=True)
        visited = []
        scandir = os.scandir
        def count(path):
            if Path(path).is_relative_to(self.root):
                visited.append(Path(path))
            return scandir(path)
        with mock.patch('os.scandir', side_effect=count):
            game = steam.scan(self.paths, max_directories=4)[0]
        self.assertLessEqual(len(visited), 4)
        self.assertFalse(game.detection_complete)
        self.assertIn('directory budget', ' '.join(game.detection_warnings))
        self.assertFalse(game.to_dict()['detection_complete'])

    def test_deep_live_plugin_models_are_found_but_backups_are_not(self):
        live = self.root / 'Project/Plugins/Runtime/vendor/deep/nvngx_dlssnr.dll'
        live.parent.mkdir(parents=True)
        live.write_bytes(b'fixture-model')
        backup = self.root / '_DLSS5_Backup/originals/nvngx_dlssnr.dll'
        backup.parent.mkdir(parents=True)
        backup.write_bytes(b'backup')
        game = steam.scan(self.paths)[0]
        self.assertEqual(game.nvngx_dlssnr, [live])
        self.assertTrue(game.detection_complete)

    def test_wide_tree_and_time_budget_return_explicit_partial_results(self):
        for index in range(100):
            (self.root / f'empty{index}').write_bytes(b'')
        game = steam.scan(self.paths, max_entries=5)[0]
        self.assertFalse(game.detection_complete)
        self.assertLessEqual(game.detection_entries, 5)
        self.assertIn('entry budget', ' '.join(game.detection_warnings))
        timed = steam.scan(self.paths, budget_seconds=0)[0]
        self.assertFalse(timed.detection_complete)
        self.assertEqual(timed.detection_directories, 0)
        self.assertIn('time budget', ' '.join(timed.detection_warnings))

    def test_model_discovery_reuses_scanned_deep_nr_without_rewalking_game(self):
        live = self.root / 'Project/Plugins/Runtime/vendor/deep/nvngx_dlssnr.dll'
        live.parent.mkdir(parents=True)
        live.write_bytes(b'fixture-model')
        game = steam.scan(self.paths)[0]
        visited = []
        scandir = os.scandir
        def count(path):
            if Path(path).is_relative_to(self.root):
                visited.append(Path(path))
            return scandir(path)
        with mock.patch('os.scandir', side_effect=count):
            candidates = model.discover(self.paths, game)
        self.assertEqual([candidate.path for candidate in candidates], [live])
        self.assertEqual(visited, [], 'discovery must reuse scan evidence')

    def test_incomplete_model_discovery_does_not_claim_no_model(self):
        game = steam.scan(self.paths, budget_seconds=0)[0]
        with self.assertRaisesRegex(RuntimeError, 'discovery incomplete'):
            model.discover(self.paths, game)

    def test_cached_inventory_retains_completeness_and_model_reuse(self):
        live = self.root / 'bin/x64/nvngx_dlssnr.dll'
        live.write_bytes(b'fixture-model')
        steam.scan_with_cache(self.paths)
        cached = steam.scan_with_cache(self.paths)[0]
        self.assertTrue(cached.detection_complete)
        with mock.patch('os.scandir', side_effect=AssertionError('game inventory rewalked')):
            self.assertEqual(model.discover(self.paths, cached)[0].path, live)

    def test_partial_scan_is_retried_instead_of_cached_as_complete(self):
        ticks = iter([0, 3])
        with mock.patch('nvfku.steam.time.monotonic', side_effect=lambda: next(ticks, 3)):
            first = steam.scan_with_cache(self.paths)[0]
        self.assertFalse(first.detection_complete)
        recovered = steam.scan_with_cache(self.paths)[0]
        self.assertTrue(recovered.detection_complete)
        self.assertEqual(recovered.rendering_api, 'DirectX 12')

    def test_missing_declared_size_does_not_add_an_unbounded_size_walk(self):
        manifest = self.sandbox.library / 'steamapps' / f'appmanifest_{self.sandbox.appid}.acf'
        manifest.write_text(manifest.read_text().replace('"SizeOnDisk" "1000"', ''))
        visited = Counter()
        scandir = os.scandir
        def count(path):
            if Path(path).is_relative_to(self.root):
                visited[str(path)] += 1
            return scandir(path)
        with mock.patch('os.scandir', side_effect=count):
            game = steam.scan(self.paths)[0]
        self.assertTrue(all(count == 1 for count in visited.values()), visited)
        self.assertIsNone(game.size_on_disk, 'undeclared/pruned payload size is unknown')

    def test_single_inventory_preserves_unique_active_reshade_evidence(self):
        ini = self.sandbox.exe_dir / 'ReShade.ini'
        ini.write_text('[GENERAL]')
        proxy = self.sandbox.exe_dir / 'dxgi.dll'
        proxy.write_bytes(b'ReShade fixture')
        game = steam.scan(self.paths)[0]
        self.assertTrue(game.reshade_installed)
        self.assertEqual(game.reshade_files.count(ini), 1)
        self.assertEqual(game.reshade_files.count(proxy), 1)

    def test_cold_scan_visits_live_directories_once_and_prunes_assets(self):
        for index in range(30):
            (self.root / 'Content' / str(index) / 'Textures').mkdir(parents=True)
        visited = Counter()
        scandir = os.scandir
        def count(path):
            directory = Path(path)
            if directory.is_relative_to(self.root):
                visited[str(directory.relative_to(self.root))] += 1
            return scandir(path)
        with mock.patch('os.scandir', side_effect=count):
            game = steam.scan(self.paths)[0]
        self.assertEqual(game.rendering_api, 'DirectX 12')
        self.assertTrue(game.native_dlss)
        self.assertFalse(any('Content' in path for path in visited), visited)
        self.assertTrue(all(count == 1 for count in visited.values()), visited)
        self.assertLessEqual(sum(visited.values()), 3, visited)
