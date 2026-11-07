#!/usr/bin/env python3
"""Build a CPU-only portable GUI on the target OS, using a bundled CPython.

Run from the checkout: python D2IC_GUI/build_portable.py --help.
Only the build machine requires Python >=3.12, uv and Internet access.
The resulting directory/archive runs offline without installed Python.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import tomllib


ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ("D2IC", "DICTHFusion", "im_jax", "D2IC_GUI")
IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", ".git", "*.egg-info")

SMOKE = r'''
import importlib.metadata as md
import json
from pathlib import Path
import tempfile
import re
import subprocess
import sys
import cv2
import gmsh
import im_jax
import jax
import jax.numpy as jnp
import numpy as np
from D2IC_GUI.server import create_app
from d2ic.mesh.generation import mask_to_mesh_gmsh

names = {d.metadata['Name'].lower().replace('_', '-') for d in md.distributions()}
assert 'opencv-python-headless' in names
assert not names.intersection({'opencv-python', 'opencv-contrib-python', 'opencv-contrib-python-headless'})
assert not any(n.startswith(('nvidia-', 'jax-cuda', 'jax-rocm')) for n in names)
assert {d.platform for d in jax.devices()} == {'cpu'}
np.testing.assert_allclose(jax.jit(jax.grad(lambda x: jnp.sum(x*x)))(jnp.array([1., 2.])), [2., 4.])
assert re.search(r'^\s*GUI:\s+NONE\s*$', cv2.getBuildInformation(), re.MULTILINE)
mask = np.pad(np.ones((24, 32), bool), ((4, 4), (4, 4)))
mesh = mask_to_mesh_gmsh(mask, 8., numpy_output=True)
assert len(mesh.nodes_xy) and len(mesh.elements)
with tempfile.TemporaryDirectory() as tmp:
    import tifffile
    from D2IC_GUI.project import create_project, save_project
    from D2IC_GUI.imaging import save_mask
    from D2IC_GUI.dic_run import prepare_run
    from d2ic.io.result_store import open_result_store
    cfg = create_project(tmp)
    vis = Path(tmp) / 'VIS'
    vis.mkdir()
    image = np.random.default_rng(12).integers(0, 256, mask.shape, dtype=np.uint8)
    for index in range(2):
        tifffile.imwrite(vis / f'vis_{index:04d}.tif', image)
    cfg['paths'].update(visible_dir=str(vis), reference_image='vis_0000.tif', visible_pattern='vis_*.tif')
    cfg['runtime'].update(jax_preferred='cpu', jax_fallback='cpu')
    cfg['mesh']['element_size_px'] = 8.
    cfg['dic'].update(max_iters=2, roi_erosion_px=1.)
    save_mask(Path(tmp) / cfg['roi']['final_mask'], mask)
    save_project(tmp, cfg)
    run = prepare_run(tmp)
    worker = subprocess.run([sys.executable, '-I', '-B', '-m', 'D2IC_GUI.worker', str(run)],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if worker.returncode:
        raise RuntimeError('Worker autonome échoué :\n' + worker.stdout[-6000:])
    assert json.loads((run / 'status.json').read_text())['state'] == 'completed'
    store = open_result_store(run / 'results/dic_store')
    np.testing.assert_allclose(store.read_history('u_nodal'), 0., atol=1e-3)
    app = create_app(tmp)
    assert app.title
static = Path(__import__('D2IC_GUI').__file__).parent / 'static'
assert all((static / p).is_file() for p in ('index.html', 'app.js', 'image_zoom.js', 'roi_shapes.js', 'style.css'))
print('Smoke CPU/headless/JIT/Gmsh/worker cubique/actifs : OK')
'''


def run(command, *, cwd=None, env=None, capture=False):
    """Execute argument lists without a shell, preserving paths with spaces."""
    shown = list(map(str, command))
    if '-c' in shown:
        shown[shown.index('-c') + 1] = '<validation Python>'
    print('+', shlex.join(shown), flush=True)
    return subprocess.run(list(map(str, command)), cwd=cwd, env=env, check=True,
                          text=True, stdout=subprocess.PIPE if capture else None)


def stage_sources(root, target):
    """Copy local scientific sources; change OpenCV metadata only in copies."""
    hashes = {}
    for name in PACKAGES:
        source, dest = root / name, target / name
        dest.mkdir(parents=True)
        for pattern in ('*.py', '*.toml', '*LICENSE*', '*COPYING*', '*README*', '*readme*'):
            for path in source.glob(pattern):
                if path.is_file():
                    shutil.copy2(path, dest / path.name)
        if name == 'D2IC':
            shutil.copytree(source / 'src', dest / 'src', ignore=IGNORE)
        elif name == 'im_jax':
            shutil.copytree(source / 'im_jax', dest / 'im_jax', ignore=IGNORE)
        elif name == 'D2IC_GUI':
            shutil.copytree(source / 'static', dest / 'static', ignore=IGNORE)
        config = dest / 'pyproject.toml'
        text = config.read_text(encoding='utf-8')
        text = re.sub(r'(?<![\w-])opencv-python(?=["<>=!~\[])',
                      'opencv-python-headless', text)
        if name == 'im_jax':
            # The staging tree deliberately has no .git directory.
            text = text.replace('[tool.setuptools_scm]',
                '[tool.setuptools_scm]\nfallback_version = "0.0.0+portable"')
        config.write_text(text, encoding='utf-8')
        tomllib.loads(text)
        digest = hashlib.sha256()
        for path in sorted(dest.rglob('*')):
            if path.is_file():
                digest.update(path.relative_to(dest).as_posix().encode())
                digest.update(path.read_bytes())
        hashes[name] = digest.hexdigest()
    return hashes


def clean_environment():
    env = os.environ.copy()
    for name in ('PYTHONPATH', 'PYTHONHOME', 'VIRTUAL_ENV', 'CONDA_PREFIX'):
        env.pop(name, None)
    env.update(JAX_PLATFORMS='cpu', JAX_PLATFORM_NAME='cpu',
               MPLBACKEND='Agg', PYTHONDONTWRITEBYTECODE='1', UV_NO_PROGRESS='1')
    return env


def runtime_python(folder):
    if os.name == 'nt':
        return folder / 'python.exe'
    return folder / 'bin' / 'python3.12'


def linux_gmsh_libraries(runtime, bundle, env):
    """Copy Gmsh's non-glibc shared libraries into the Linux bundle."""
    if sys.platform != 'linux':
        return
    gmsh = next(runtime.rglob('libgmsh.so*'), None)
    if gmsh is None:
        raise RuntimeError('Bibliothèque native Gmsh absente du runtime')
    output = run(['ldd', gmsh], env=env, capture=True).stdout
    if 'not found' in output:
        raise RuntimeError('Dépendance Gmsh absente sur la machine de construction :\n'
                           + output + '\nSous Debian/Ubuntu, vérifier libglu1-mesa.')
    core = re.compile(r'^(lib(c|m|dl|pthread|rt|resolv|util|anl)\.so|ld-linux|ld-musl)')
    libdir = bundle / 'lib'
    libdir.mkdir(exist_ok=True)
    for line in output.splitlines():
        match = re.match(r'\s*(\S+)\s+=>\s+(/\S+)', line)
        if match and not core.match(match[1]):
            shutil.copy2(match[2], libdir / match[1])


def prune_runtime(runtime):
    """Remove Python caches and test suites, retaining metadata and licenses."""
    for path in sorted(runtime.rglob('*'), reverse=True):
        if path.is_dir() and not path.is_symlink() and path.name in ('__pycache__', 'tests', 'test'):
            shutil.rmtree(path)
    # CPython development headers/static libraries are not needed by the JIT.
    shutil.rmtree(runtime / 'include', ignore_errors=True)
    # Terminal capability aliases differ only by case on Unix. They are unused
    # by this browser GUI and prevent copying to case-insensitive filesystems.
    shutil.rmtree(runtime / 'share' / 'terminfo', ignore_errors=True)
    for path in runtime.rglob('libpython*.a'):
        path.unlink()


def write_launchers(bundle, *, windows=None):
    """Launch the embedded interpreter; never use the user's Python."""
    if windows is None:
        windows = os.name == 'nt'
    if windows:
        text = '@echo off\r\nsetlocal\r\nset PYTHONUTF8=1\r\n"%~dp0python\\python.exe" -I -B -m D2IC_GUI.desktop %*\r\nif errorlevel 1 pause\r\n'
        (bundle / 'D2IC_GUI.cmd').write_bytes(text.encode('utf-8'))
    else:
        script = bundle / ('D2IC_GUI.command' if sys.platform == 'darwin' else 'D2IC_GUI.sh')
        script.write_text('''#!/bin/sh
APP_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
export LD_LIBRARY_PATH="$APP_DIR/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
exec "$APP_DIR/python/bin/python3.12" -I -B -m D2IC_GUI.desktop "$@"
''', encoding='utf-8')
        script.chmod(0o755)
    (bundle / 'LIRE_MOI.txt').write_text(
        'D2IC_GUI CPU — double-cliquer sur le lanceur D2IC_GUI.\n'
        'Le navigateur s’ouvre sur un serveur local ; aucune connexion Internet n’est nécessaire.\n'
        'Garder la fenêtre du lanceur ouverte. Ctrl+C arrête le serveur.\n'
        'Options : --no-browser ; --port NUMERO ; chemin du dossier d’étude.\n'
        'Les études et résultats doivent être enregistrés dans un dossier utilisateur.\n'
        'Ce paquet est destiné au même système et à la même architecture que sa construction.\n', encoding='utf-8')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'dist')
    parser.add_argument('--name', default=f'D2IC_GUI-cpu-{platform.system().lower()}-{platform.machine().lower()}')
    parser.add_argument('--python', default='3.12', help='Version CPython 3.12, éventuellement avec correctif exact')
    parser.add_argument('--uv', default=shutil.which('uv'), help='Chemin vers uv (installer avec python -m pip install uv)')
    parser.add_argument('--constraints', type=Path, help='Contraintes de versions issues d’un précédent paquet')
    parser.add_argument('--no-archive', action='store_true', help='Produire seulement le dossier autonome')
    args = parser.parse_args(argv)
    uv = [args.uv] if args.uv else ([sys.executable, '-m', 'uv']
        if importlib.util.find_spec('uv') else None)
    if uv is None:
        parser.error('uv est requis sur la machine de construction : python -m pip install uv')
    if not re.fullmatch(r'3\.12(?:\.\d+)?', args.python):
        parser.error('--python doit être une version CPython 3.12')
    if Path(args.name).name != args.name or args.name in ('', '.', '..'):
        parser.error('--name doit être un nom de dossier simple')
    output = args.output.expanduser().resolve()
    final = output / args.name
    archive_format = 'zip' if os.name == 'nt' else 'gztar'
    archive_path = output / (args.name + ('.zip' if os.name == 'nt' else '.tar.gz'))
    if final.exists() or (not args.no_archive and archive_path.exists()):
        parser.error(f'Sortie déjà présente : {final}. Choisir un autre --name ou --output.')
    output.mkdir(parents=True, exist_ok=True)
    env = clean_environment()
    with tempfile.TemporaryDirectory(prefix='d2ic-cpu-build-') as temporary:
        work = Path(temporary)
        staged, wheels, managed = work / 'sources', work / 'wheels', work / 'managed'
        hashes = stage_sources(ROOT, staged)
        for name in PACKAGES:
            run([*uv, '--quiet', 'build', '--wheel', '--out-dir', wheels,
                 '--python', sys.executable, staged / name], env=env)
        run([*uv, 'python', 'install', '--install-dir', managed,
             '--no-bin', args.python], env=env)
        installed = [p for p in managed.glob('cpython-*') if p.is_dir() and not p.is_symlink()]
        if len(installed) != 1:
            raise RuntimeError(f'Installation CPython ambiguë dans {managed}')
        bundle = work / args.name
        bundle.mkdir()
        runtime = bundle / 'python'
        shutil.copytree(installed[0], runtime, symlinks=True)
        python = runtime_python(runtime)
        # This is our private COPY of CPython, never the builder's interpreter.
        # uv marks its managed runtimes as externally managed by default.
        command = [*uv, 'pip', 'install', '--python', python,
                   '--break-system-packages', '--only-binary', ':all:',
                   *sorted(wheels.glob('*.whl'))]
        if args.constraints:
            command += ['--constraint', args.constraints.expanduser().resolve()]
        run(command, env=env)
        linux_gmsh_libraries(runtime, bundle, env)
        if sys.platform == 'linux':
            env['LD_LIBRARY_PATH'] = str(bundle / 'lib') + os.pathsep + env.get('LD_LIBRARY_PATH', '')
        run([*uv, 'pip', 'check', '--python', python], env=env)
        prune_runtime(runtime)
        write_launchers(bundle)
        # Move before validation: exercise a relocated interpreter, away from sources.
        try:
            shutil.move(bundle, final)
            python = runtime_python(final / 'python')
            if sys.platform == 'linux':
                env['LD_LIBRARY_PATH'] = str(final / 'lib')
            run([python, '-I', '-B', '-c', SMOKE], cwd=work, env=env)
            packages = json.loads(run([python, '-I', '-B', '-c',
                'import importlib.metadata as m,json; print(json.dumps({d.metadata["Name"]:d.version for d in m.distributions()}))'],
                cwd=work, env=env, capture=True).stdout)
            (final / 'requirements.lock').write_text(''.join(f'{k}=={v}\n' for k, v in sorted(packages.items())), encoding='utf-8')
            manifest = {'created_utc': datetime.now(timezone.utc).isoformat(),
                'platform': platform.platform(), 'architecture': platform.machine(),
                'libc': platform.libc_ver(),
                'cpu_only': True, 'opencv': 'opencv-python-headless',
                'staged_source_sha256': hashes, 'packages': packages,
                'validation': 'CPU, headless, JIT, Gmsh, worker cubique et actifs après déplacement',
                'unpacked_bytes': sum(p.stat().st_size for p in final.rglob('*') if p.is_file())}
            (final / 'build-manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
            if not args.no_archive:
                shutil.make_archive(str(output / args.name), archive_format, root_dir=output, base_dir=args.name)
                print(f'Archive : {archive_path} ({archive_path.stat().st_size / 1024**2:.1f} Mio)')
            print(f'Application : {final} ({manifest["unpacked_bytes"] / 1024**2:.1f} Mio)')
        except BaseException:
            if final.is_dir():
                (final / 'BUILD_FAILED.txt').write_text('Copie, validation ou archivage échoué : ne pas distribuer ce dossier.\n', encoding='utf-8')
            raise


if __name__ == '__main__':
    main()
