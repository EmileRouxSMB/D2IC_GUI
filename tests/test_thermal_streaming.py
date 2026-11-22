"""Progressive thermal fusion, unchanged arrays and failure-safe publication."""

import hashlib
from pathlib import Path
import weakref

import numpy as np
import pytest

from D2IC_GUI import thermal, worker


def _inputs():
    nodes = np.array([[1., 1.], [3., 1.], [3., 3.], [1., 3.]])
    elements = np.array([[0, 1, 2, 3]])
    images = [np.full((8, 8), 10.), np.full((8, 8), 14.)]
    return nodes, elements, images


def test_iterator_reads_only_the_requested_displacement():
    nodes, elements, images = _inputs()
    reads = []

    class Frames:
        def __len__(self):
            return 3

        def __getitem__(self, index):
            reads.append(index)
            return np.zeros_like(nodes)

    iterator = thermal.iter_thermal_sequence(
        [0., .5, 1.], [0., 1.], [0, 1], images, nodes, Frames(), elements, np.eye(3))
    assert reads == []
    reference = next(iterator)
    np.testing.assert_array_equal(reference['delta_temperature'], np.zeros(4))
    assert reads == []  # Reference displacement is implicit, not read.
    frame = next(iterator)
    np.testing.assert_allclose(frame['temperature'], 12.)
    np.testing.assert_allclose(frame['delta_temperature'], 2.)
    assert reads == [1]
    previous = weakref.ref(frame['temperature'])
    del frame
    last = next(iterator)
    assert previous() is None  # The iterator does not retain previous states.
    np.testing.assert_allclose(last['delta_temperature'], 4.)
    assert reads == [1, 2]


def test_iterator_and_compatibility_wrapper_preserve_invalid_states():
    nodes, elements, images = _inputs()
    displacements = np.zeros((4, 4, 2))
    args = ([-.5, 0., .5, 1.], [0., 1.], [0, 2], images,
            nodes, displacements, elements, np.eye(3))
    states = list(thermal.iter_thermal_sequence(*args))
    collected = thermal.fuse_thermal_sequence(*args)
    assert [state['time_valid'] for state in states] == [False, True, False, True]
    for actual, expected in zip(states, collected):
        for key in actual:
            np.testing.assert_equal(actual[key], expected[key])
    assert np.isnan(states[-1]['delta_temperature']).all()


@pytest.fixture
def fusion_run(tmp_path, monkeypatch):
    import DICTHFusion.registration as registration
    import d2ic.io.result_store as result_store
    from D2IC_GUI import imaging, project

    nodes, elements, images = _inputs()
    run = tmp_path/'run'
    (run/'results'/'dic_store').mkdir(parents=True)
    calibration = run/'visible_thermal.json'
    calibration.write_text('{}')
    rows = []
    for index in range(2):
        path = tmp_path/f'th_{index}.tif'
        path.write_bytes(b'source')
        stat = path.stat()
        rows.append({'path': str(path), 'time_s': float(index), 'frame': index,
                     'size': stat.st_size, 'mtime_ns': stat.st_mtime_ns})
    vis_rows = [{'path': f'vis_{index}.tif', 'time_s': time, 'frame': index}
                for index, time in enumerate([0., .5, 1.])]
    manifest = {
        'thermal_images': rows, 'visible_reference': vis_rows[0],
        'visible_images': vis_rows[1:], 'length_unit': 'px',
        'mm_per_pixel': 1., 'scale_confirmed': False,
        'calibration_sha256': hashlib.sha256(calibration.read_bytes()).hexdigest(),
    }
    config = {
        'synchronization': {'method': 'timestamps', 'visible_event_frame': 0,
                            'thermal_event_frame': 0, 'thermal_offset_s': 0.},
        'thermal': {'thermal_fps': 1.},
        'output': {'export_vtu': False, 'export_pvd': False, 'series_name': 'dic'},
    }
    reads = []

    class Store:
        def read_mesh(self):
            return {'nodes_xy': nodes, 'elements': elements}

        def read_frame(self, index):
            reads.append(index)
            return {'u_nodal': np.zeros((4, 2), dtype=np.float32),
                    'strain': np.zeros((4, 3), dtype=np.float32)}

        def read_history(self, *args):
            raise AssertionError('The worker must not load a complete history')

    monkeypatch.setattr(project, 'load_project', lambda _: config)
    monkeypatch.setattr(registration, 'load_registration', lambda _: ({}, np.eye(3)))
    monkeypatch.setattr(result_store, 'open_result_store', lambda _: Store())
    by_path = {row['path']: image for row, image in zip(rows, images)}
    monkeypatch.setattr(imaging, 'read_image', lambda path: by_path[str(path)])
    return run, manifest, config, reads


def test_worker_streams_to_the_existing_npz_schema(fusion_run):
    run, manifest, _, reads = fusion_run
    worker._fuse_thermal(run, manifest)
    assert reads == [0, 1]
    assert manifest['reference_temperature_available']
    assert manifest['coupled_vtu'] == []
    assert manifest['coupled_pvd'] is None
    assert [row['alpha'] for row in manifest['thermal_provenance']] == [0., .5, 0.]
    with np.load(run/'results'/'thermal_fields.npz', allow_pickle=False) as fields:
        assert set(fields.files) == {
            'temperature', 'delta_temperature', 'thermal_valid',
            'temperature_element', 'delta_temperature_element', 'thermal_valid_element'}
        np.testing.assert_allclose(fields['temperature'], [[10.]*4, [12.]*4, [14.]*4])
        np.testing.assert_allclose(fields['delta_temperature'], [[0.]*4, [2.]*4, [4.]*4])
        assert fields['temperature'].dtype == np.dtype(float)
        assert fields['thermal_valid'].dtype == np.dtype(bool)
        assert fields['temperature_element'].shape == (3, 1)
    assert not list((run/'results').glob('.thermal-fields-*'))
    assert not list((run/'results').glob('*.pending.npz'))


def test_worker_exports_the_current_frame_before_reading_the_next(fusion_run, monkeypatch):
    run, manifest, config, reads = fusion_run
    config['output']['export_vtu'] = True
    calls = []

    def export(path, nodes, elements, displacement, state, *, strain, **kwargs):
        index = len(calls)
        assert reads == list(range(index))
        assert strain.dtype == np.dtype(float)
        calls.append(Path(path).name)

    monkeypatch.setattr(thermal, 'write_thermal_vtu', export)
    worker._fuse_thermal(run, manifest)
    assert calls == ['coupled_0000.vtu', 'coupled_0001.vtu', 'coupled_0002.vtu']
    assert len(manifest['coupled_vtu']) == 3


@pytest.mark.parametrize('failure', ['fusion', 'compression'])
def test_failure_preserves_previous_archive_and_removes_temporaries(fusion_run, monkeypatch, failure):
    run, manifest, _, _ = fusion_run
    target = run/'results'/'thermal_fields.npz'
    target.write_bytes(b'previous complete archive')
    original = thermal.iter_thermal_sequence

    def interrupted(*args, **kwargs):
        yield next(original(*args, **kwargs))
        raise RuntimeError('injected fusion error')

    def compression(path, **arrays):
        Path(path).write_bytes(b'partial')
        raise RuntimeError('injected compression error')

    if failure == 'fusion':
        monkeypatch.setattr(thermal, 'iter_thermal_sequence', interrupted)
    else:
        monkeypatch.setattr(worker.np, 'savez_compressed', compression)
    with pytest.raises(RuntimeError, match='injected'):
        worker._fuse_thermal(run, manifest)
    assert target.read_bytes() == b'previous complete archive'
    assert not list((run/'results').glob('.thermal-fields-*'))
    assert not list((run/'results').glob('*.pending.npz'))
