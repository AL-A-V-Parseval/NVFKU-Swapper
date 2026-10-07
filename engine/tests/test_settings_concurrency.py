"""Concurrent public CLI updates must merge instead of saving stale snapshots."""
import json
import multiprocessing
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from nvfku import __main__ as cli
from nvfku import settings


def _update(state, home, option, value, first_loaded, second_loaded, first):
    # Delay the first filesystem read's return to make the old lost-update
    # schedule deterministic. A correct lock keeps the second read outside it.
    os.environ['HOME'] = str(home)
    original = settings.load_settings
    reads = 0

    def delayed(paths):
        nonlocal reads
        snapshot = original(paths)
        reads += 1
        # The theme-only command first reads configuration for Steam discovery;
        # coordinate its actual settings read, not that unrelated earlier query.
        if not first and reads == 1:
            return snapshot
        if first:
            first_loaded.set()
            second_loaded.wait(0.5)
        else:
            second_loaded.set()
        return snapshot

    with patch.object(settings, 'load_settings', delayed):
        code = cli.main(['--state-dir', str(state), '--json', 'settings', option, value])
    raise SystemExit(code)


class SettingsConcurrencyTest(unittest.TestCase):
    def test_concurrent_cli_updates_preserve_unrelated_fields(self):
        with tempfile.TemporaryDirectory(prefix='nvfku-settings-test-') as raw:
            root = Path(raw)
            home = root / 'home'
            home.mkdir()
            state = root / 'state'
            context = multiprocessing.get_context('fork')
            first_loaded, second_loaded = context.Event(), context.Event()
            a = context.Process(target=_update, args=(state, home, '--steam-root',
                '/temporary/Steam', first_loaded, second_loaded, True))
            b = context.Process(target=_update, args=(state, home, '--theme',
                'light', first_loaded, second_loaded, False))
            a.start()
            self.assertTrue(first_loaded.wait(5), 'first CLI did not load settings')
            b.start()
            try:
                for process in (a, b):
                    process.join(10)
                    self.assertEqual(process.exitcode, 0)
            finally:
                for process in (a, b):
                    if process.is_alive():
                        process.terminate()
                    process.join()
            result = subprocess.run([sys.executable, '-m', 'nvfku', '--state-dir',
                str(state), '--json', 'settings'], env={**os.environ, 'HOME': str(home)},
                capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            document = json.loads(result.stdout)['settings']
            self.assertEqual(document['steam_root'], '/temporary/Steam')
            self.assertEqual(document['theme'], 'light')


if __name__ == '__main__':
    unittest.main()
