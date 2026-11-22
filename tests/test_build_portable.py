"""Packaging invariants without downloading a Python runtime."""

from pathlib import Path
import re
import tomllib

from D2IC_GUI import build_portable as build


def test_staging_replaces_opencv_only_in_copies_and_includes_assets(tmp_path):
    originals = {name: (build.ROOT / name / 'pyproject.toml').read_bytes()
                 for name in build.PACKAGES}
    hashes = build.stage_sources(build.ROOT, tmp_path / 'sources')
    for name in build.PACKAGES:
        assert (build.ROOT / name / 'pyproject.toml').read_bytes() == originals[name]
        staged = tmp_path / 'sources' / name
        metadata = tomllib.loads((staged / 'pyproject.toml').read_text())
        dependencies = {re.split(r'[<>=!~;\[]', req)[0] for req in metadata['project']['dependencies']}
        assert 'opencv-python' not in dependencies
        if name != 'im_jax':
            assert 'opencv-python-headless' in dependencies
        assert len(hashes[name]) == 64
        assert not list(staged.rglob('__pycache__'))
    package = tmp_path / 'sources/D2IC_GUI/src/D2IC_GUI'
    assert (package / 'parameters.toml').is_file()
    assert (package / 'examples/generate_synthetic_study.py').is_file()
    static = package / 'static'
    assert all((static / name).is_file() for name in ('app.js', 'image_zoom.js', 'index.html'))


def test_pruning_keeps_runtime_code_and_license_metadata(tmp_path):
    for name in ('lib/pkg/tests/case.py', 'lib/pkg/__pycache__/a.pyc',
                 'lib/pkg/__init__.py', 'lib/pkg.dist-info/licenses/LICENSE',
                 'lib/pkg.dist-info/METADATA', 'include/python3.12/Python.h',
                 'share/terminfo/e/eterm',
                 'lib/libpython3.12.a'):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('kept unless development data')
    build.prune_runtime(tmp_path)
    assert not (tmp_path / 'lib/pkg/tests').exists()
    assert not (tmp_path / 'lib/pkg/__pycache__').exists()
    assert not (tmp_path / 'include').exists()
    assert not (tmp_path / 'share/terminfo').exists()
    assert not (tmp_path / 'lib/libpython3.12.a').exists()
    assert (tmp_path / 'lib/pkg/__init__.py').is_file()
    assert (tmp_path / 'lib/pkg.dist-info/licenses/LICENSE').is_file()
    assert (tmp_path / 'lib/pkg.dist-info/METADATA').is_file()


def test_build_environment_forces_cpu_without_inheriting_external_python(monkeypatch):
    monkeypatch.setenv('PYTHONPATH', '/external/source')
    monkeypatch.setenv('PYTHONHOME', '/external/python')
    monkeypatch.setenv('JAX_PLATFORMS', 'cuda')
    env = build.clean_environment()
    assert 'PYTHONPATH' not in env and 'PYTHONHOME' not in env
    assert env['JAX_PLATFORMS'] == env['JAX_PLATFORM_NAME'] == 'cpu'


def test_launchers_reference_embedded_python_and_accept_arguments(tmp_path):
    build.write_launchers(tmp_path)
    scripts = list(tmp_path.glob('D2IC_GUI.*'))
    assert len(scripts) == 1
    text = scripts[0].read_text()
    assert '-I -B -m D2IC_GUI.desktop' in text
    assert 'python' in text
    assert '"$@"' in text or '%*' in text
    assert (tmp_path / 'LIRE_MOI.txt').is_file()
