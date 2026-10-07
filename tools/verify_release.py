#!/usr/bin/env python3
"""Verify trusted local release artifacts, extracting only into temporary roots.

This is a build gate, not a sandbox for downloaded executables: AppImage
extraction executes its runtime, and CLI smoke executes the packaged engine.
No GUI, package installation, network download, or real game mutation is run.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def artifact_kind(name):
    for suffix, kind in (('.tar.gz', 'tar'), ('.deb', 'deb'), ('.AppImage', 'appimage')):
        if name.endswith(suffix):
            return kind
    raise ValueError(f'unsupported artifact: {name}')


def checked_artifacts(out):
    rows = (out / 'SHA256SUMS').read_text().splitlines()
    require(bool(rows), 'empty SHA256SUMS')
    artifacts = []
    names = set()
    for row in rows:
        digest, name = row.split('  ', 1)
        require(re.fullmatch(r'[0-9a-f]{64}', digest), 'invalid SHA256 digest')
        require(Path(name).name == name and name not in {'.', '..'}, 'unsafe artifact filename')
        require(name not in names, f'duplicate artifact: {name}')
        names.add(name)
        path = out / name
        require(not path.is_symlink() and path.is_file(), f'missing or symlinked artifact: {name}')
        require(sha256(path) == digest, f'checksum mismatch: {name}')
        artifacts.append((path, artifact_kind(name)))
    return artifacts


def extract_tar(archive, destination):
    """Accept only ordinary files/directories; reject links and traversal up front.

    Explicit validation also works on Python 3.9, which lacks tar data filters.
    The destination is always a new, private TemporaryDirectory subtree.
    """
    members = archive.getmembers()
    for member in members:
        name = Path(member.name)
        require(not name.is_absolute() and '..' not in name.parts,
                f'unsafe archive path: {member.name}')
        require(member.isfile() or member.isdir(), f'unsafe archive type: {member.name}')
    for member in members:
        target = destination / member.name
        if member.isdir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        with archive.extractfile(member) as source, target.open('wb') as output:
            for block in iter(lambda: source.read(1024 * 1024), b''):
                output.write(block)
        target.chmod(member.mode & 0o777)


def ar_members(path):
    data = path.read_bytes()
    require(data[:8] == b'!<arch>\n', 'invalid Debian ar header')
    result = {}
    offset = 8
    while offset < len(data):
        header = data[offset:offset + 60]
        require(len(header) == 60 and header[58:60] == b'`\n', 'invalid Debian ar member')
        name = header[:16].decode().strip().rstrip('/')
        size = int(header[48:58])
        require(size >= 0 and offset + 60 + size <= len(data), 'truncated Debian ar member')
        require(name not in result, f'duplicate Debian member: {name}')
        result[name] = data[offset + 60:offset + 60 + size]
        offset += 60 + size + size % 2
    return result


def check_payload(payload, source_root, label):
    for name in ('engine/nvfku/__main__.py', 'engine/nvfku/journal.py',
                 'engine/nvfku/route/transaction.py', 'app/nvfku_ui', 'nvfku',
                 'nvfku-cli', 'LICENSE', 'THIRD_PARTY_NOTICES.md', 'RELEASE.json'):
        require((payload / name).is_file(), f'{label}: missing {name}')
    manifest = json.loads((payload / 'RELEASE.json').read_text())
    require(manifest.get('model_bundled') is False, f'{label}: model must not be bundled')
    require(bool(manifest.get('version')), f'{label}: missing version')
    require(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]+', manifest.get('build_id', '')),
            f'{label}: missing build identity')
    provenance = manifest.get('source_provenance', {})
    require(re.fullmatch(r'[0-9a-f]{40,64}', provenance.get('revision') or ''),
            f'{label}: source revision unavailable')
    require(isinstance(provenance.get('dirty'), bool), f'{label}: unknown worktree state')
    require(re.fullmatch(r'[0-9a-f]{64}', provenance.get('tree_sha256') or ''),
            f'{label}: missing source tree fingerprint')
    require(manifest.get('runtime', {}).get('python_min') == '3.9', f'{label}: unexpected Python floor')
    for path in payload.rglob('*'):
        require(path.name not in {'nvngx_dlssnr.dll', '__pycache__'}, f'{label}: excluded file {path}')
    for source in (source_root / 'engine/nvfku').rglob('*.py'):
        target = payload / 'engine/nvfku' / source.relative_to(source_root / 'engine/nvfku')
        require(target.is_file() and target.read_bytes() == source.read_bytes(),
                f'{label}: source bytes differ: {target.name}')
    for name in ('nvfku', 'nvfku-cli', 'app/nvfku_ui'):
        require(os.access(payload / name, os.X_OK), f'{label}: not executable: {name}')
    with tempfile.TemporaryDirectory(prefix='nvfku-smoke-') as raw:
        home = Path(raw) / 'home'
        home.mkdir()
        env = {**os.environ, 'HOME': str(home), 'XDG_DATA_HOME': str(home / 'data'),
               'XDG_CONFIG_HOME': str(home / 'config'), 'XDG_CACHE_HOME': str(home / 'cache'),
               'PYTHONDONTWRITEBYTECODE': '1'}
        env.pop('PYTHONPATH', None)
        for arguments, code in ((['--version'], 0), (['--json', 'settings'], 0),
                                (['--json', 'backups'], 0),
                                (['--json', 'rollback', 'missing-acceptance-journal'], 1)):
            result = subprocess.run([str(payload / 'nvfku-cli'), '--state-dir', str(home / 'state'),
                *arguments], cwd=raw, env=env, capture_output=True, text=True, timeout=30)
            require(result.returncode == code, f'{label}: CLI smoke failed: {arguments}: {result.stderr}')
            if '--json' in arguments:
                document = json.loads(result.stdout)
                if 'rollback' in arguments:
                    require(document.get('ok') is False, f'{label}: unexpected rollback success')
                if 'backups' in arguments:
                    require(document == [], f'{label}: smoke state was not isolated')
    print(f'{label}: payload/provenance/source identity/executable modes/isolated CLI PASS')
    return manifest


def desktop(path):
    subprocess.run(['desktop-file-validate', str(path)], capture_output=True, text=True, check=True)


def native_links(bundle):
    for binary in (bundle / 'nvfku_ui', *sorted((bundle / 'lib').glob('*.so'))):
        result = subprocess.run(['ldd', str(binary)], capture_output=True, text=True, check=True)
        require('not found' not in result.stdout, f'unresolved native dependency: {binary}: {result.stdout}')
    print('Native dependencies resolve on this host (not a cross-distribution guarantee)')


def verify(out, source_root, required_formats):
    artifacts = checked_artifacts(out)
    require(set(required_formats) <= {kind for _, kind in artifacts}, 'required format missing')
    print('All artifact SHA256 checks PASS')
    identities = {}
    with tempfile.TemporaryDirectory(prefix='nvfku-release-inspect-') as raw:
        for index, (artifact, kind) in enumerate(artifacts):
            destination = Path(raw) / str(index)
            destination.mkdir()
            if kind == 'tar':
                with tarfile.open(artifact) as archive:
                    extract_tar(archive, destination)
                payload = destination / 'nvfku-swapper'
            elif kind == 'deb':
                members = ar_members(artifact)
                require(members.get('debian-binary') == b'2.0\n', 'unsupported Debian package version')
                with tarfile.open(fileobj=io.BytesIO(members['data.tar.gz'])) as archive:
                    extract_tar(archive, destination)
                payload = destination / 'usr/lib/nvfku'
                desktop(destination / 'usr/share/applications/nvfku-swapper.desktop')
            else:
                subprocess.run([str(artifact.resolve()), '--appimage-extract'], cwd=destination,
                    capture_output=True, text=True, check=True, timeout=60)
                appdir = destination / 'squashfs-root'
                require(os.access(appdir / 'AppRun', os.X_OK), 'AppRun is not executable')
                desktop(appdir / 'nvfku-swapper.desktop')
                payload = appdir / 'usr/lib/nvfku'
            manifest = check_payload(payload, source_root, artifact.name)
            identity = (manifest['source_provenance'], manifest['runtime'])
            build_id = manifest['build_id']
            require(build_id not in identities or identities[build_id] == identity,
                    f'inconsistent source/runtime for build {build_id}')
            identities[build_id] = identity
            if kind == 'deb':
                with tarfile.open(fileobj=io.BytesIO(members['control.tar.gz'])) as archive:
                    control = archive.extractfile('control').read().decode()
                require('python3 (>= 3.9)' in control, 'Debian Python constraint missing')
                require(f"libc6 (>= {manifest['runtime']['glibc_min']})" in control,
                        'Debian glibc constraint missing')
                require('libstdc++6' in control, 'Debian C++ dependency missing')
                print(control.split('Description:')[0].strip())
            native_links(payload / 'app')
    print('Release verification PASS; GUI/native AppImage/FUSE and clean-distro runtime remain manual gates.')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--source-root', type=Path, default=ROOT)
    parser.add_argument('--require-format', action='append', default=[], choices=['tar', 'deb', 'appimage'])
    args = parser.parse_args(argv)
    try:
        verify(args.out.resolve(), args.source_root.resolve(), args.require_format)
    except (ValueError, KeyError, OSError, subprocess.SubprocessError, tarfile.TarError) as exc:
        print(f'release verification failed: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
