"""Static checks of a Windows payload; no Windows code is executed here."""

from pathlib import Path
import struct

import pytest

from D2IC_GUI.build_portable import write_launchers
from D2IC_GUI.build_windows import check_windows_payload, place_msvc_runtime


def _pe(path, machine=0x8664):
    data = bytearray(128)
    data[:2] = b'MZ'
    struct.pack_into('<I', data, 0x3C, 64)
    data[64:68] = b'PE\0\0'
    struct.pack_into('<H', data, 68, machine)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def _metadata(site, name, tag='py3-none-any'):
    info = site / (name.replace('-', '_') + '-1.0.dist-info')
    info.mkdir(parents=True)
    (info / 'METADATA').write_text(f'Metadata-Version: 2.1\nName: {name}\nVersion: 1.0\n')
    (info / 'WHEEL').write_text(f'Wheel-Version: 1.0\nTag: {tag}\n')
    return info


@pytest.fixture
def runtime(tmp_path):
    site = tmp_path / 'Lib/site-packages'
    _metadata(site, 'opencv-python-headless', 'cp312-cp312-win_amd64')
    for name in ('python.exe', 'msvcp140.dll', 'vcruntime140.dll', 'vcruntime140_1.dll',
                 'Lib/site-packages/lib/gmsh-4.15.dll', 'Lib/site-packages/jaxlib/_jax.pyd'):
        _pe(tmp_path / name)
    helper = site / 'D2IC_GUI/build_portable.py'
    helper.parent.mkdir()
    helper.write_text('# scientific validation source')
    return tmp_path


def test_windows_payload_accepts_pe_x64_and_target_tags(runtime):
    packages, count = check_windows_payload(runtime)
    assert packages['opencv-python-headless'] == '1.0'
    assert count == 6


def test_windows_payload_rejects_linux_wheels(runtime):
    _metadata(runtime / 'Lib/site-packages', 'jaxlib', 'cp312-cp312-manylinux_2_27_x86_64')
    with pytest.raises(RuntimeError, match='Wheel non Windows'):
        check_windows_payload(runtime)


def test_windows_payload_rejects_non_x64_binary(runtime):
    _pe(runtime / 'python.exe', machine=0x14C)
    with pytest.raises(RuntimeError, match='Architecture PE non x64'):
        check_windows_payload(runtime)


def test_windows_payload_rejects_gpu_dependency(runtime):
    _metadata(runtime / 'Lib/site-packages', 'nvidia-cublas-cu12')
    with pytest.raises(RuntimeError, match='Dépendance GPU'):
        check_windows_payload(runtime)


def test_microsoft_runtime_is_placed_beside_python(runtime):
    site = runtime / 'Lib/site-packages'
    metadata = _metadata(site, 'msvc-runtime', 'cp312-cp312-win_amd64')
    library = site / 'Scripts/msvcp140.dll'
    _pe(library)
    (metadata / 'RECORD').write_text('Scripts/msvcp140.dll,,\n')
    assert place_msvc_runtime(runtime) == ['msvcp140.dll']
    assert (runtime / 'msvcp140.dll').read_bytes() == library.read_bytes()


def test_windows_launcher_can_be_written_on_another_os(tmp_path):
    write_launchers(tmp_path, windows=True)
    text = (tmp_path / 'D2IC_GUI.cmd').read_text()
    assert 'python\\python.exe' in text and '-I -B -m D2IC_GUI.desktop' in text
    assert not (tmp_path / 'D2IC_GUI.sh').exists()
