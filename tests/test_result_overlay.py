"""Native VIS overlay contracts for result images and mesh coordinates."""

import json

import cv2
import numpy as np
from fastapi.testclient import TestClient

from D2IC_GUI.dic_run import write_status
from D2IC_GUI.project import create_project
from D2IC_GUI.server import create_app, _transport_reference_raster
from d2ic.io.result_store import ResultStore


def _completed_run(tmp_path, *, binning=1, shape=(8, 10)):
    study = tmp_path / 'study'
    create_project(study)
    source = tmp_path / 'source.tif'
    height, width = shape
    image = np.arange(height * width, dtype=np.uint8).reshape(shape)
    reference = tmp_path / 'reference.tif'
    assert cv2.imwrite(str(reference), image)
    image = np.flipud(image).copy()
    assert cv2.imwrite(str(source), image)
    run = study / 'runs' / 'sample'
    store = ResultStore(run / 'results' / 'dic_store', metadata={'image_shape': list(shape)})
    nodes = np.array([[1., 1.], [7., 1.], [7., 6.], [1., 6.]])
    store.write_mesh(nodes, np.array([[0, 1, 2, 3]], dtype=np.int32))
    store.write_frame(0, u_nodal=np.tile([1., 1.], (4, 1)),
                      strain=np.zeros((4, 3)),
                      discrepancy_ref=np.arange((height//binning)*(width//binning), dtype=float).reshape(height//binning, width//binning))
    store.update_progress(status='completed', total_frames=1, completed_frames=1, last_frame=0)
    stat = source.stat()
    manifest = {
        'mode': 'dic', 'length_unit': 'mm', 'mm_per_pixel': .1,
        'visible_reference': {'path': str(reference), 'shape': list(shape), 'size': reference.stat().st_size,
                              'mtime_ns': reference.stat().st_mtime_ns, 'time_s': 0.},
        'visible_images': [{'path': str(source), 'shape': list(shape), 'size': stat.st_size,
                            'mtime_ns': stat.st_mtime_ns, 'time_s': .1}],
    }
    (run / 'manifest.json').write_text(json.dumps(manifest))
    (run / 'dic_config.toml').write_text(f'[dic]\nimage_binning = {binning}\n')
    write_status(run, 'completed')
    return study, run, source, image, TestClient(create_app(study))


def test_visible_frame_is_manifest_checked_and_full_resolution(tmp_path):
    _, _, source, image, client = _completed_run(tmp_path)
    response = client.get('/api/runs/sample/visible-image?frame=1')
    decoded = cv2.imdecode(np.frombuffer(response.content, np.uint8), cv2.IMREAD_GRAYSCALE)
    assert response.status_code == 200
    assert decoded.shape == image.shape
    low, high = np.percentile(image, [1, 99])
    expected = np.clip((image.astype(np.float32)-low)/max(high-low, 1)*255, 0, 255).astype(np.uint8)
    assert np.array_equal(decoded, expected)
    assert client.get('/api/runs/sample/visible-image?frame=2').status_code == 400

    source.write_bytes(b'changed source')
    assert client.get('/api/runs/sample/visible-image?frame=1').status_code == 400
    assert client.get('/api/runs/sample/visible-image?frame=0').status_code == 200


def test_overlay_mesh_uses_raw_pixel_displacement_and_native_extent(tmp_path):
    _, _, _, _, client = _completed_run(tmp_path)
    response = client.get('/api/runs/sample/mesh?overlay=current&frame=1')
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload['extent'] == [-.5, 9.5, -.5, 7.5]
    assert payload['nodes_xy'][0] == [2., 2.]
    assert client.get('/api/runs/sample/mesh').json()['extent'] == [1., 7., 1., 6.]


def test_field_overlay_png_is_rgba_native_and_residual_is_transportable(tmp_path):
    _, run, _, _, client = _completed_run(tmp_path, binning=2)
    response = client.get('/api/runs/sample/field-image?field=u1&frame=1&overlay=current')
    assert response.status_code == 200, response.text
    rgba = cv2.imdecode(np.frombuffer(response.content, np.uint8), cv2.IMREAD_UNCHANGED)
    assert rgba.shape == (8, 10, 4)
    assert rgba[0, 0, 3] == 0
    assert np.any(rgba[:, :, 3] > 0)

    residual = client.get('/api/runs/sample/field-image?field=Residual&frame=1&overlay=reference')
    assert residual.status_code == 200, residual.text
    residual_rgba = cv2.imdecode(np.frombuffer(residual.content, np.uint8), cv2.IMREAD_UNCHANGED)
    assert residual_rgba.shape == (8, 10, 4)
    assert residual_rgba[0, 0, 3] == 255
    current = client.get('/api/runs/sample/field-image?field=Residual&frame=1&overlay=current')
    assert current.status_code == 200
    current_rgba = cv2.imdecode(np.frombuffer(current.content, np.uint8), cv2.IMREAD_UNCHANGED)
    assert current_rgba[0, 0, 3] == 0
    assert current_rgba[3, 4, 3] > 0
    fields = client.get('/api/runs/sample/fields').json()
    assert fields['source_shape_hw'] == [8, 10]
    assert 'Residual' in fields['fields']
    assert (run / 'results' / 'previews' / 'u1_00001_current_v5.png').is_file()


def test_transport_residual_keeps_translation_values_and_nan_holes():
    array = np.arange(120., dtype=float).reshape(10, 12)
    array[3, 4] = np.nan
    nodes = np.array([[0., 0.], [11., 0.], [11., 9.], [0., 9.]])
    triangles = np.array([[0, 1, 2], [0, 2, 3]])
    transported = _transport_reference_raster(array, nodes, nodes + [2., 1.], triangles, (14, 16), 1)
    np.testing.assert_allclose(transported[1:11, 2:14], array, equal_nan=True)
    assert np.isnan(transported[0]).all()
    assert np.isnan(transported[:, :2]).all()


def test_residual_binning_leaves_incomplete_native_borders_transparent(tmp_path):
    _, _, _, _, client = _completed_run(tmp_path, binning=3, shape=(8, 11))
    response = client.get('/api/runs/sample/field-image?field=Residual&frame=1&overlay=reference')
    assert response.status_code == 200, response.text
    image = cv2.imdecode(np.frombuffer(response.content, np.uint8), cv2.IMREAD_UNCHANGED)
    assert image.shape == (8, 11, 4)
    assert np.all(image[6:, :, 3] == 0)
    assert np.all(image[:, 9:, 3] == 0)
    assert np.all(image[:6, :9, 3] == 255)


def test_residual_available_on_later_frame_is_advertised(tmp_path):
    _, run, _, _, client = _completed_run(tmp_path)
    store = ResultStore(run/'results'/'dic_store')
    store.write_frame(0, u_nodal=np.ones((4,2)), strain=np.zeros((4,3)))
    store.write_frame(1, u_nodal=np.ones((4,2)), strain=np.zeros((4,3)), discrepancy_ref=np.ones((8,10)))
    store.update_progress(status='completed', total_frames=2, completed_frames=2, last_frame=1)
    manifest = json.loads((run/'manifest.json').read_text())
    manifest['visible_images'].append({**manifest['visible_images'][0], 'time_s': .2})
    (run/'manifest.json').write_text(json.dumps(manifest))
    fields = client.get('/api/runs/sample/fields').json()
    assert 'Residual' in fields['fields']
    assert fields['residual_frames'] == [2]
    store.write_frame(1, u_nodal=np.ones((4,2)), strain=np.zeros((4,3)))
    fields = client.get('/api/runs/sample/fields').json()
    assert 'Residual' not in fields['fields']
    assert fields['residual_frames'] == []


def test_nodal_nan_regions_remain_transparent(tmp_path):
    _, run, _, _, client = _completed_run(tmp_path)
    store = ResultStore(run/'results'/'dic_store')
    strain = np.ones((4,3)); strain[1] = np.nan
    store.write_frame(0, u_nodal=np.ones((4,2)), strain=strain)
    response = client.get('/api/runs/sample/field-image?field=E11&frame=1&overlay=current')
    assert response.status_code == 200, response.text
    rgba = cv2.imdecode(np.frombuffer(response.content, np.uint8), cv2.IMREAD_UNCHANGED)
    assert np.any(rgba[:,:,3] > 0)
    assert rgba[0,0,3] == 0


def test_live_results_publish_only_committed_frames(tmp_path, monkeypatch):
    """An on-disk frame stays hidden until the progress/checkpoint commits it."""
    _, run, _, _, client = _completed_run(tmp_path)
    monkeypatch.setattr('D2IC_GUI.dic_run.worker_alive', lambda pid: True)
    manifest_path = run / 'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    manifest['mode'] = 'dic_thermal'
    manifest['visible_images'].append(dict(manifest['visible_images'][0], time_s=.2))
    manifest_path.write_text(json.dumps(manifest))
    write_status(run, 'running', pid=123)
    store = ResultStore(run / 'results' / 'dic_store')
    store.write_frame(1, u_nodal=np.tile([2., 2.], (4, 1)), strain=np.ones((4, 3)))
    store.update_progress(status='running', total_frames=2, completed_frames=1)
    store.save_checkpoint(fingerprint='test', u_prev=np.ones((4, 2)),
                          u_prevprev=None, completed_frames=1)

    payload = client.get('/api/runs/sample/fields').json()
    assert payload['state'] == 'running'
    assert payload['completed_frames'] == 1
    assert payload['total_frames'] == 2
    assert payload['times_s'] == [0., .1]
    assert 'Temperature' not in payload['fields']
    assert client.get('/api/runs').json()['runs'][0]['results_available']
    for route in ('mesh?overlay=current&frame=1', 'field-image?field=u1&frame=1&overlay=current',
                  'visible-image?frame=1', 'field-range?field=u1&scope=sequence',
                  'history?node=0', 'histories?nodes=0,1'):
        response = client.get('/api/runs/sample/' + route)
        assert response.status_code == 200, (route, response.text)
    history = client.get('/api/runs/sample/history?node=0').json()['history']
    assert len(history) == 2
    assert history[-1]['u1'] == .1
    assert client.get('/api/runs/sample/field-range?field=u1&scope=sequence').json()['max'] == .1
    for route in ('field-image?frame=2', 'mesh?overlay=current&frame=2', 'visible-image?frame=2'):
        assert client.get('/api/runs/sample/' + route).status_code == 400
    assert client.post('/api/runs/sample/export', json={}).status_code == 400

    # Progress alone cannot publish a frame beyond the saved checkpoint.
    store.update_progress(status='running', total_frames=2, completed_frames=2)
    assert client.get('/api/runs/sample/fields').json()['times_s'] == [0., .1]
    store.save_checkpoint(fingerprint='test', u_prev=np.ones((4, 2)),
                          u_prevprev=None, completed_frames=2)
    assert client.get('/api/runs/sample/fields').json()['times_s'] == [0., .1, .2]
    history = client.get('/api/runs/sample/history?node=0').json()['history']
    assert len(history) == 3
    assert history[-1]['u1'] == .2
    assert client.get('/api/runs/sample/field-range?field=u1&scope=sequence').json()['max'] == .2

    # The thermal file is published atomically only after fusion.
    np.savez(run / 'results' / 'thermal_fields.npz', temperature=np.full((3, 4), 20.),
             delta_temperature=np.zeros((3, 4)), temperature_element=np.full((3, 1), 20.))
    assert 'Temperature' in client.get('/api/runs/sample/fields').json()['fields']
    assert client.get('/api/runs/sample/history?node=0').json()['history'][-1]['Temperature'] == 20.
    for state in ('cancelled', 'failed'):
        write_status(run, state)
        assert client.get('/api/runs/sample/fields').json()['state'] == state
        assert client.get('/api/runs/sample/field-image?frame=2').status_code == 200


def test_live_results_wait_for_mesh_initialization(tmp_path, monkeypatch):
    _, run, _, _, client = _completed_run(tmp_path)
    monkeypatch.setattr('D2IC_GUI.dic_run.worker_alive', lambda pid: True)
    write_status(run, 'running', pid=123)
    (run / 'results' / 'dic_store' / 'mesh.npz').unlink()
    response = client.get('/api/runs/sample/fields')
    assert response.status_code == 400
    assert 'Initialisation' in response.text
