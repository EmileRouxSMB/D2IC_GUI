#!/usr/bin/env python3
"""Assemble a Windows x64 CPU ZIP from Linux/macOS; execution needs Windows.

Uses genuine Windows CPython and wheels, without executing them on the host.
For a validated native Windows build, use build_portable.py on Windows.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import platform
import shutil
import struct
import sys
import tempfile

try:
    from .build_portable import ROOT, PACKAGES, clean_environment, prune_runtime, run, stage_sources, write_launchers
except ImportError:
    from build_portable import ROOT, PACKAGES, clean_environment, prune_runtime, run, stage_sources, write_launchers


VERIFY = '''"""Run the portable app's scientific checks on Windows."""
import json
import os
from pathlib import Path
import platform
import traceback

os.environ['JAX_PLATFORMS'] = 'cpu'
os.environ['JAX_PLATFORM_NAME'] = 'cpu'
root = Path(__file__).resolve().parent
report = {'platform': platform.platform(), 'validated_on_windows': False}
try:
    if os.name != 'nt':
        raise RuntimeError('Cette vérification doit être exécutée sous Windows.')
    from D2IC_GUI.build_portable import SMOKE
    exec(compile(SMOKE, '<validation_windows>', 'exec'), {})
    report['validated_on_windows'] = True
    print('Validation Windows réussie. Vous pouvez lancer D2IC_GUI.cmd.')
except BaseException:
    report['error'] = traceback.format_exc()
    raise
finally:
    (root / 'validation-windows.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
'''


def check_windows_payload(runtime):
    """Check target wheel tags, CPU dependencies and PE architecture statically."""
    site = runtime / 'Lib' / 'site-packages'
    packages = {d.metadata['Name']: d.version
                for d in importlib.metadata.distributions(path=[str(site)])}
    names = {name.lower().replace('_', '-') for name in packages}
    if 'opencv-python-headless' not in names or names & {'opencv-python', 'opencv-contrib-python'}:
        raise RuntimeError('Le paquet doit contenir exclusivement OpenCV headless')
    if any(name.startswith(('nvidia-', 'jax-cuda', 'jax-rocm')) for name in names):
        raise RuntimeError('Dépendance GPU inattendue')
    for wheel in site.glob('*.dist-info/WHEEL'):
        tags = [line[5:].strip() for line in wheel.read_text().splitlines() if line.startswith('Tag: ')]
        if not tags or not all(tag.endswith(('-any', '-win_amd64')) for tag in tags):
            raise RuntimeError(f'Wheel non Windows x64 : {wheel}: {tags}')
    binaries = [runtime / 'python.exe', *runtime.rglob('*.pyd'), *runtime.rglob('*.dll')]
    for binary in binaries:
        with binary.open('rb') as stream:
            if stream.read(2) != b'MZ':
                raise RuntimeError(f'Binaire non Windows : {binary}')
            stream.seek(0x3C)
            offset = struct.unpack('<I', stream.read(4))[0]
            stream.seek(offset)
            if stream.read(4) != b'PE\0\0' or struct.unpack('<H', stream.read(2))[0] != 0x8664:
                raise RuntimeError(f'Architecture PE non x64 : {binary}')
    if not list(runtime.rglob('gmsh*.dll')):
        raise RuntimeError('DLL Gmsh Windows absente')
    for name in ('msvcp140.dll', 'vcruntime140.dll', 'vcruntime140_1.dll'):
        if not (runtime / name).is_file():
            raise RuntimeError(f'Runtime Microsoft C++ absent près de python.exe : {name}')
    if not (site / 'D2IC_GUI' / 'build_portable.py').is_file():
        raise RuntimeError('Module de vérification scientifique absent')
    return packages, len(binaries)


def place_msvc_runtime(runtime):
    """Place the matching Microsoft CRT beside python.exe for Windows loading."""
    site = runtime / 'Lib' / 'site-packages'
    distribution = next(d for d in importlib.metadata.distributions(path=[str(site)])
                        if d.metadata['Name'].lower().replace('_', '-') == 'msvc-runtime')
    copied = []
    for record in distribution.files or ():
        path = distribution.locate_file(record)
        if path.suffix.lower() == '.dll' and path.is_file():
            shutil.copy2(path, runtime / path.name)
            copied.append(path.name)
    if 'msvcp140.dll' not in {name.lower() for name in copied}:
        raise RuntimeError('Le paquet msvc-runtime ne contient pas MSVCP140.dll')
    return copied


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'dist')
    parser.add_argument('--name', default='D2IC_GUI-cpu-windows-amd64')
    parser.add_argument('--uv', default=shutil.which('uv'))
    parser.add_argument('--constraints', type=Path)
    args = parser.parse_args(argv)
    uv = [args.uv] if args.uv else ([sys.executable, '-m', 'uv'] if importlib.util.find_spec('uv') else None)
    if uv is None:
        parser.error('Installer uv sur la machine de construction : python -m pip install uv')
    if Path(args.name).name != args.name or args.name in ('', '.', '..'):
        parser.error('--name doit être un nom de dossier simple')
    output = args.output.expanduser().resolve()
    final = output / args.name
    archive = output / (args.name + '.zip')
    if final.exists() or archive.exists():
        parser.error('Une sortie existe déjà ; choisir un autre --name')
    output.mkdir(parents=True, exist_ok=True)
    env = clean_environment()
    with tempfile.TemporaryDirectory(prefix='d2ic-windows-build-') as temporary:
        work = Path(temporary)
        staged, wheels, managed = work / 'sources', work / 'wheels', work / 'managed'
        hashes = stage_sources(ROOT, staged)
        for name in PACKAGES:
            run([*uv, '--quiet', 'build', '--wheel', '--out-dir', wheels,
                 '--python', sys.executable, staged / name], env=env)
        run([*uv, 'python', 'install', '--install-dir', managed, '--no-bin',
             'cpython-3.12-windows-x86_64-none'], env=env)
        installations = [p for p in managed.glob('cpython-*') if p.is_dir() and not p.is_symlink()]
        if len(installations) != 1:
            raise RuntimeError('Runtime Windows ambigu')
        bundle = work / args.name
        runtime = bundle / 'python'
        # uv adds a Unix convenience symlink to python3.12 even for a Windows
        # download. It is dangling and unnecessary: Windows uses python.exe.
        shutil.copytree(installations[0], runtime, ignore_dangling_symlinks=True)
        site = runtime / 'Lib' / 'site-packages'
        command = [*uv, 'pip', 'install', '--python', sys.executable,
                   '--target', site, '--python-platform', 'windows', '--python-version', '3.12',
                   '--only-binary', ':all:', '--link-mode', 'copy', 'msvc-runtime', *sorted(wheels.glob('*.whl'))]
        if args.constraints:
            command += ['--constraint', args.constraints.expanduser().resolve()]
        run(command, env=env)
        crt = place_msvc_runtime(runtime)
        prune_runtime(runtime)
        write_launchers(bundle, windows=True)
        (bundle / 'Verifier_D2IC_GUI.py').write_text(VERIFY, encoding='utf-8')
        (bundle / 'Verifier_D2IC_GUI.cmd').write_bytes(
            ('@echo off\r\nsetlocal\r\nset PYTHONUTF8=1\r\n'
             '"%~dp0python\\python.exe" -I -B "%~dp0Verifier_D2IC_GUI.py" > "%~dp0validation-windows.log" 2>&1\r\n'
             'type "%~dp0validation-windows.log"\r\npause\r\n').encode('utf-8'))
        (bundle / 'LIRE_MOI.txt').write_text(
            'D2IC_GUI CPU pour Windows x64\n\n'
            'Extraire tout le ZIP dans un dossier utilisateur.\n'
            'Lancer Verifier_D2IC_GUI.cmd, puis D2IC_GUI.cmd si la vérification réussit.\n'
            'Python est inclus. Aucune installation Python ou connexion Internet requise.\n'
            'Le navigateur habituel affiche le GUI local ; garder sa console ouverte.\n'
            'Les études et résultats doivent rester dans un dossier utilisateur.\n\n'
            'Cette archive a été assemblée hors Windows avec des binaires Windows x64.\n'
            'Son exécution n’a pas été validée sur Windows lors de cet assemblage.\n'
            'La vérification écrit validation-windows.json et validation-windows.log.\n', encoding='utf-8')
        packages, binaries = check_windows_payload(runtime)
        manifest = {'created_utc': datetime.now(timezone.utc).isoformat(),
                    'build_host': platform.platform(), 'target': 'windows-amd64',
                    'cpu_only': True, 'opencv': 'opencv-python-headless',
                    'validated_on_windows': False,
                    'static_validation': 'Wheels Windows/any, binaires PE x64, absence de plugins GPU',
                    'checked_pe_binaries': binaries, 'staged_source_sha256': hashes,
                    'bundled_microsoft_crt': crt,
                    'packages': packages}
        (bundle / 'requirements.lock').write_text(''.join(f'{name}=={version}\n' for name, version in sorted(packages.items())), encoding='utf-8')
        (bundle / 'build-manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
        try:
            # Compress on the temporary filesystem, then copy one finished ZIP.
            # Avoid thousands of small writes to mounted workspace volumes.
            prepared = shutil.make_archive(str(work / 'windows-archive'), 'zip',
                                           root_dir=work, base_dir=args.name)
            shutil.move(prepared, archive)
        except BaseException:
            archive.unlink(missing_ok=True)
            raise
        print(f'Archive Windows x64 : {archive} ({archive.stat().st_size / 1024**2:.1f} Mio)')
        print('Contrôle statique réussi ; validation d’exécution Windows à effectuer.')


if __name__ == '__main__':
    main()
