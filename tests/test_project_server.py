"""Focused project, metadata and approval boundaries for the local GUI."""

from pathlib import Path
import json

import numpy as np
import cv2
import pytest
import tifffile
from fastapi.testclient import TestClient

from D2IC_GUI.dic_run import prepare_run
from D2IC_GUI.imaging import inventory, save_mask
from D2IC_GUI.project import copy_project, create_project, load_project, save_project
from D2IC_GUI.schema import defaults, validate
from D2IC_GUI.server import create_app
from D2IC_GUI.worker import _rebuild_pvd


def test_schema_roundtrip_preserves_thermal_on_dic_switch(tmp_path):
    folder = tmp_path/'study'
    config = create_project(folder, mode='dic_thermal')
    config['thermal']['image_dir'] = '/data/TH'
    config['project']['mode'] = 'dic'
    save_project(folder, config)
    assert load_project(folder)['thermal']['image_dir'] == '/data/TH'
    assert 'thermal' not in defaults('dic')
    with pytest.raises(ValueError, match='output.export_pvd'):
        validate({'output': {'export_vtu': False}})


def test_segment_scale_uses_original_vis_pixel_distance():
    config = defaults('dic')
    config['scale'].update(method='segment', confirmed=True,
                           segment_xy_px=[[100.0, 200.0], [400.0, 600.0]],
                           segment_length_mm=25.0)
    validated = validate(config)
    assert validated['scale']['mm_per_pixel'] == pytest.approx(0.05)
    config['scale']['segment_xy_px'][1] = [100.0, 200.0]
    with pytest.raises(ValueError, match="Segment d'échelle confirmé invalide"):
        validate(config)


def test_photometric_erosion_schema_and_saved_mesh_remain_independent(tmp_path):
    from D2IC_GUI.imaging import read_mask
    from d2ic.io.config import load_sequence_config

    assert validate({})['dic']['roi_erosion_px'] == 0.0
    for radius in (-1, float('nan'), float('inf')):
        with pytest.raises(ValueError, match='dic.roi_erosion_px'):
            validate({'dic': {'roi_erosion_px': radius}})
    folder = _configured_study(tmp_path)
    client = TestClient(create_app(folder))
    config = load_project(folder)
    config['project']['mode'] = 'dic'
    save_project(folder, config)
    assert client.post('/api/mesh/preview').status_code == 200
    mesh_before = client.get('/api/mesh/layer-image').content
    mask_before = (folder / 'roi/mask_final.tif').read_bytes()
    config['dic']['roi_erosion_px'] = 3.0
    assert client.put('/api/project/config', json=config).status_code == 200
    assert load_project(folder)['dic']['roi_erosion_px'] == 3.0
    mesh_after = client.get('/api/mesh/layer-image')
    assert mesh_after.status_code == 200
    assert mesh_after.content == mesh_before
    run = prepare_run(folder)
    assert load_sequence_config(run / 'dic_config.toml').roi_erosion_px == 3.0
    assert (folder / 'roi/mask_final.tif').read_bytes() == mask_before
    np.testing.assert_array_equal(read_mask(run / 'mask_final.tif'),
                                  read_mask(folder / 'roi/mask_final.tif'))


def test_copy_keeps_external_image_and_copies_nonstandard_asset(tmp_path):
    original = tmp_path/'one'; images = tmp_path/'VIS'; images.mkdir()
    external = tmp_path/'external_mask.tif'
    save_mask(external, np.ones((4, 4), bool))
    config = create_project(original)
    config['paths']['visible_dir'] = '../VIS'
    config['roi']['initial_mask'] = str(external)
    save_project(original, config)
    duplicate = tmp_path/'two'
    copied = copy_project(original, duplicate)
    assert copied['paths']['visible_dir'] == str(images.resolve())
    assert (duplicate/'roi'/'external_mask.tif').is_file()
    assert copied['roi']['initial_mask'] == 'roi/external_mask.tif'
    assert not (duplicate/'runs').exists()


def test_tiff_metadata_at_50_hz(tmp_path):
    folder = tmp_path/'TH'; folder.mkdir()
    for k in range(3):
        # Standard DateTime is second-granularity; EXIF SubSecTimeOriginal
        # distinguishes acquisitions 20 ms apart.
        tifffile.imwrite(folder/f'th_{k}.tif', np.ones((3, 4), np.float32),
            datetime='2026:10:15 12:00:00',
            extratags=[(37521, 's', 4, f'{20*k:03d}', False)])
    result = inventory(tmp_path, 'TH', '*.tif', 'metadata', '', 50)
    times = [row['time_s'] for row in result['images']]
    assert np.allclose(np.diff(times), 0.02, atol=1e-5)
    assert all(row['frame'] is None for row in result['images'])


def _configured_study(tmp_path):
    from D2IC_GUI.examples.generate_synthetic_study import generate_study
    generate_study(tmp_path/'sources')
    folder = tmp_path/'study'
    config = create_project(folder, mode='dic_thermal')
    config['paths'].update(visible_dir=str(tmp_path/'sources'/'VIS'),
        reference_image='vis_0000_tick0000.tif', visible_pattern='vis_*.tif')
    config['time'].update(visible_frame_regex=r'tick(\d+)', visible_fps=100.0)
    config['thermal'].update(image_dir=str(tmp_path/'sources'/'TH'),
        image_pattern='th_*.tif', frame_regex=r'th_(\d+)', thermal_fps=10.0)
    mask = np.pad(np.ones((52, 72), bool), ((22,22),(28,28)))
    save_mask(folder/'roi'/'mask_initial.tif', mask)
    save_mask(folder/'roi'/'mask_final.tif', mask)
    save_project(folder, config)
    return folder


def test_calibration_digest_blocks_stale_approval(tmp_path):
    folder = _configured_study(tmp_path)
    client = TestClient(create_app(folder))
    points = [{'visible':[x,y], 'thermal':[x*63/127,y*47/95]}
              for x,y in ((10,10),(110,10),(10,80),(110,80))]
    assert client.post('/api/registration/fit', json={'points':points,'model':'affine'}).status_code == 200
    assert client.post('/api/registration/approve', json={'points':points,'model':'affine'}).status_code == 200
    calibration = folder/'calibration'/'visible_thermal.json'
    calibration.write_text(calibration.read_text() + ' ')
    with pytest.raises(ValueError, match='modifiée après approbation'):
        prepare_run(folder)


def test_blank_roi_drawing_refused(tmp_path):
    folder = _configured_study(tmp_path)
    client = TestClient(create_app(folder))
    import cv2, base64
    image = np.zeros((96,128,4), np.uint8)
    _, encoded = cv2.imencode('.png', image)
    drawing = 'data:image/png;base64,' + base64.b64encode(encoded).decode()
    response = client.post('/api/roi/save',json={'drawing_data_url':drawing})
    assert response.status_code == 400
    assert 'vide' in response.json()['detail']


def test_imported_roi_source_is_not_overwritten(tmp_path):
    folder = _configured_study(tmp_path)
    source = tmp_path/'imported_mask.tif'
    original = np.pad(np.ones((52, 72), bool), ((22, 22), (28, 28)))
    save_mask(source, original)
    before = source.read_bytes()
    config = load_project(folder)
    config['roi']['initial_mask'] = str(source)
    config['roi']['operation'] = 'erosion'
    config['roi']['radius_px'] = 1
    save_project(folder, config)
    client = TestClient(create_app(folder))
    preview = client.get('/api/roi/mask-image')
    assert preview.status_code == 200 and preview.headers['content-type'] == 'image/png'
    morphology_preview = client.post('/api/roi/preview', json={})
    assert morphology_preview.status_code == 200
    assert morphology_preview.json()['preview_data_url'].startswith('data:image/png;base64,')
    response = client.post('/api/roi/save', json={})
    assert response.status_code == 200
    assert source.read_bytes() == before
    assert load_project(folder)['roi']['initial_mask'] == 'roi/mask_initial.tif'
    assert (folder/'roi'/'mask_final.tif').is_file()


def test_reference_vtu_shape_and_worker_pid(tmp_path):
    import meshio
    from D2IC_GUI.dic_run import write_status, inspect_run
    run=tmp_path/'runs'/'one'; (run/'results').mkdir(parents=True)
    save_project(run, defaults())
    meshio.write(run/'results'/'dic_0000.vtu', meshio.Mesh(
        np.array([[0,0,0],[1,0,0],[0,1,0]], float), [('triangle',np.array([[0,1,2]]))],
        point_data={'Displacement':np.zeros((3,3))}))
    np.savez_compressed(run/'results'/'dic_results.npz',
                        nodes_xy=np.array([[0,0],[1,0],[0,1]]),elements=np.array([[0,1,2]]),
                        u_nodal=np.zeros((1,3,2)),strain=np.zeros((1,3,3)))
    manifest={'length_unit':'px','mm_per_pixel':1.,'visible_reference':{'time_s':0.},
              'visible_images':[{'time_s':.1}]}
    _rebuild_pvd(run,manifest)
    ref=meshio.read(run/'results'/'dic_reference.vtu')
    assert ref.point_data['Strain'].shape == (3,9)
    write_status(run,'running',pid=99999999)
    status=inspect_run(run)
    assert status['state']=='failed'


def test_versioned_run_fields_history_and_progress(tmp_path):
    from d2ic.io.result_store import ResultStore
    from D2IC_GUI.dic_run import inspect_run, write_status

    study = tmp_path/'study'
    create_project(study)
    run = study/'runs'/'sample'
    store = ResultStore(run/'results'/'dic_store', metadata={'image_shape': [8, 8]})
    store.write_mesh(np.array([[1., 1.], [5., 1.], [1., 5.]]),
                     np.array([[0, 1, 2]], dtype=np.int32))
    store.update_progress(status='running', total_frames=2)
    store.write_frame(0, u_nodal=np.full((3, 2), [2., 1.]),
                      strain=np.zeros((3, 3)))
    store.update_progress(status='running', completed_frames=1, last_frame=0)
    write_status(run, 'running', pid=99999999)
    status = inspect_run(run)
    assert status['completed_frames'] == 1
    assert status['total_frames'] == 2
    assert status['progress'] == .5

    store.write_frame(1, u_nodal=np.full((3, 2), [4., 2.]),
                      strain=np.zeros((3, 3)))
    store.update_progress(status='completed', completed_frames=2, last_frame=1)
    manifest = {'mode': 'dic', 'length_unit': 'px', 'mm_per_pixel': 1.,
                'visible_reference': {'time_s': 0.},
                'visible_images': [{'time_s': .1}, {'time_s': .2}]}
    (run/'manifest.json').write_text(json.dumps(manifest))
    write_status(run, 'completed')
    client = TestClient(create_app(study))
    fields = client.get('/api/runs/sample/fields')
    assert fields.status_code == 200
    assert fields.json()['times_s'] == [0., .1, .2]
    history = client.get('/api/runs/sample/history?node=1')
    assert history.status_code == 200
    assert [row['u1'] for row in history.json()['history']] == [0., 2., 4.]
    histories = client.get('/api/runs/sample/histories?nodes=0,1')
    assert histories.status_code == 200
    assert [item['node'] for item in histories.json()['histories']] == [0, 1]
    assert [row['u1'] for row in histories.json()['histories'][1]['history']] == [0., 2., 4.]
    mesh = client.get('/api/runs/sample/mesh')
    assert mesh.status_code == 200
    assert mesh.json()['nodes_xy'] == [[1., 1.], [5., 1.], [1., 5.]]
    assert mesh.json()['extent'] == [1., 5., 1., 5.]
    image_range = client.get('/api/runs/sample/field-range?field=u1&frame=1&scope=image')
    assert image_range.status_code == 200
    assert image_range.json()['min'] == pytest.approx(2.)
    sequence_range = client.get('/api/runs/sample/field-range?field=u1&scope=sequence')
    assert sequence_range.status_code == 200
    assert (sequence_range.json()['min'], sequence_range.json()['max']) == (0., 4.)
    preview = client.get('/api/runs/sample/field-image?field=u_norm&frame=1')
    assert preview.status_code == 200 and preview.headers['content-type'] == 'image/png'
    assert (run/'results'/'previews'/'u_norm_00001_v3.png').is_file()
    bounded = client.get('/api/runs/sample/field-image?field=u1&frame=1&vmin=0&vmax=3')
    assert bounded.status_code == 200
    assert not (run/'results'/'previews'/'u1_00001_v3_0_3.png').exists()
    assert client.get('/api/runs/sample/field-image?field=u1&frame=1&vmin=3&vmax=0').status_code == 400
    assert client.get('/api/runs/sample/field-image?field=Temperature&frame=1&vmin=0&vmax=1').status_code == 400
    np.savez(run/'results'/'thermal_fields.npz',
             temperature=np.full((3, 3), 20.),
             delta_temperature=np.zeros((3, 3)),
             temperature_element=np.full((3, 1), 20.))
    cell_image = client.get('/api/runs/sample/field-image?field=Temperature_element&frame=1')
    assert cell_image.status_code == 200 and cell_image.headers['content-type'] == 'image/png'



def test_element_temperature_preview_keeps_invalid_cells_blank(tmp_path):
    from d2ic.io.result_store import ResultStore
    from D2IC_GUI.dic_run import write_status

    study = tmp_path/'study'; create_project(study)
    run = study/'runs'/'cells'
    store = ResultStore(run/'results'/'dic_store', metadata={'image_shape': [11, 11]})
    nodes = np.array([[0., 0.], [10., 0.], [0., 10.], [10., 10.]])
    cells = np.array([[0, 1, 2], [1, 3, 2]], dtype=np.int32)
    store.write_mesh(nodes, cells)
    store.write_frame(0, u_nodal=np.zeros((4, 2)), strain=np.zeros((4, 3)))
    store.update_progress(status='completed', total_frames=1, completed_frames=1, last_frame=0)
    (run/'manifest.json').write_text(json.dumps({
        'mode': 'dic_thermal', 'length_unit': 'px', 'mm_per_pixel': 1.,
        'visible_reference': {'time_s': 0.}, 'visible_images': [{'time_s': .1}],
    }))
    np.savez(run/'results'/'thermal_fields.npz',
             temperature=np.full((2, 4), 20.), delta_temperature=np.zeros((2, 4)),
             temperature_element=np.array([[20., np.nan], [21., np.nan]]))
    write_status(run, 'completed')
    response = TestClient(create_app(study)).get('/api/runs/cells/field-image?field=Temperature_element&frame=1')
    assert response.status_code == 200, response.text
    pixels = cv2.imdecode(np.frombuffer(response.content, np.uint8), cv2.IMREAD_COLOR)
    assert not np.all(pixels[180, 180] == 255)  # valid triangle
    assert np.all(pixels[540, 540] == 255)  # invalid neighbouring triangle


def test_legacy_npz_run_remains_readable(tmp_path):
    from D2IC_GUI.dic_run import write_status

    study = tmp_path/'study'
    create_project(study)
    run = study/'runs'/'legacy'
    (run/'results').mkdir(parents=True)
    np.savez_compressed(run/'results'/'dic_results.npz',
        nodes_xy=np.array([[0., 0.], [1., 0.], [0., 1.]]),
        elements=np.array([[0, 1, 2]]),
        u_nodal=np.full((1, 3, 2), [3., -1.]),
        strain=np.zeros((1, 3, 3)))
    (run/'manifest.json').write_text(json.dumps({
        'mode': 'dic', 'length_unit': 'px', 'mm_per_pixel': 1.,
        'visible_reference': {'time_s': 0.},
        'visible_images': [{'time_s': .1}],
    }))
    write_status(run, 'completed')
    client = TestClient(create_app(study))
    history = client.get('/api/runs/legacy/history?node=0')
    assert history.status_code == 200
    assert [row['u1'] for row in history.json()['history']] == [0., 3.]


def test_relink_sources_checks_run_images_before_changing_config(tmp_path):
    import shutil
    from D2IC_GUI.project import relink_sources

    study = tmp_path/'study'
    original = tmp_path/'original'
    moved = tmp_path/'moved'
    original.mkdir(); moved.mkdir()
    image = np.arange(12, dtype=np.uint8).reshape(3, 4)
    tifffile.imwrite(original/'vis_0000.tif', image)
    config = create_project(study)
    config['paths'].update(visible_dir=str(original), reference_image='vis_0000.tif')
    save_project(study, config)
    run = study/'runs'/'old'; run.mkdir(parents=True)
    reference = original/'vis_0000.tif'
    row = {'path': str(reference), 'shape': [3, 4], 'size': reference.stat().st_size,
           'time_s': 0.}
    (run/'manifest.json').write_text(json.dumps({'visible_reference': row, 'visible_images': []}))
    shutil.copy2(reference, moved/reference.name)
    replacement, checked = relink_sources(study, visible_dir=moved)
    assert replacement['paths']['visible_dir'] == str(moved)
    assert checked['visible_dir'] == 1
    assert json.loads((run/'manifest.json').read_text())['visible_reference']['path'] == str(reference)
    (moved/reference.name).write_bytes(b'wrong')
    with pytest.raises(ValueError, match='Taille différente'):
        relink_sources(study, visible_dir=moved)
    assert load_project(study)['paths']['visible_dir'] == str(moved)


def test_local_file_explorer_filters_and_pages_without_study(tmp_path):
    """A local chooser keeps absolute paths while limiting listed file types."""
    (tmp_path/'VIS').mkdir()
    (tmp_path/'VIS'/'vis_01.tif').write_bytes(b'tiff')
    (tmp_path/'VIS'/'vis_02.png').write_bytes(b'png')
    (tmp_path/'VIS'/'notes.txt').write_text('notes')
    (tmp_path/'study').mkdir()
    (tmp_path/'study'/'config.toml').write_text('[project]\n')
    client = TestClient(create_app())

    images = client.get('/api/filesystem', params={
        'path': str(tmp_path/'VIS'), 'kind': 'image', 'limit': 1,
    })
    assert images.status_code == 200
    data = images.json()
    assert data['path'] == str((tmp_path/'VIS').resolve())
    assert data['total'] == 2 and data['has_more']
    assert data['entries'][0]['path'] == str((tmp_path/'VIS'/'vis_01.tif').resolve())
    next_page = client.get('/api/filesystem', params={
        'path': str(tmp_path/'VIS'), 'kind': 'image', 'offset': 1, 'limit': 1,
    }).json()
    assert next_page['entries'][0]['name'] == 'vis_02.png'
    searched = client.get('/api/filesystem', params={
        'path': str(tmp_path/'VIS'), 'kind': 'image', 'query': '02',
    }).json()
    assert [row['name'] for row in searched['entries']] == ['vis_02.png']
    studies = client.get('/api/filesystem', params={
        'path': str(tmp_path), 'kind': 'study',
    }).json()
    assert next(row for row in studies['entries'] if row['name'] == 'study')['is_study']
    assert client.get('/api/filesystem', params={
        'path': str(tmp_path), 'kind': 'image', 'limit': 201,
    }).status_code == 400
    missing = client.get('/api/filesystem', params={
        'path': str(tmp_path/'not_created'/'mask_initial.tif'), 'kind': 'mask',
    }).json()
    assert missing['path'] == str(tmp_path.resolve())


def test_visible_series_discovery_keeps_cameras_separate(tmp_path):
    from D2IC_GUI.imaging import discover_visible_series

    for camera in (1, 2):
        for frame in (0, 1, 2):
            (tmp_path/f'cam{camera}_frame{frame:04d}.tif').write_bytes(b'')
    (tmp_path/'notes.txt').write_text('not an image')
    found = discover_visible_series(tmp_path)
    assert found['image_count'] == 6
    assert [(row['pattern'], row['count']) for row in found['series']] == [
        ('cam1_frame[0-9]*.tif', 3), ('cam2_frame[0-9]*.tif', 3),
    ]
    assert all(row['first_image'].endswith('frame0000.tif') for row in found['series'])


def test_visible_series_discovery_handles_two_varying_indices(tmp_path):
    from D2IC_GUI.imaging import discover_visible_series

    for frame, tick in ((0, 0), (1, 2), (2, 4)):
        tifffile.imwrite(tmp_path/f'vis_{frame:04d}_tick{tick:04d}.tif',
                         np.ones((4, 5), np.uint8))
    client = TestClient(create_app())
    response = client.get('/api/visible/series', params={'directory': str(tmp_path)})
    assert response.status_code == 200
    assert response.json()['series'] == [{
        'pattern': 'vis_[0-9]*_tick[0-9]*.tif', 'count': 3,
        'first_image': 'vis_0000_tick0000.tif',
        'example': 'vis_0002_tick0004.tif',
        'frame_regex': r'vis_\d+_tick(\d+)',
    }]
    suggestion = response.json()['series'][0]
    rows = inventory(tmp_path, '.', suggestion['pattern'], 'filename',
                     suggestion['frame_regex'], 100)['images']
    assert [row['frame'] for row in rows] == [0, 2, 4]
    assert np.allclose([row['time_s'] for row in rows], [0, .02, .04])


def test_vis_schema_only_contains_image_opening_options():
    from D2IC_GUI.schema import describe_fields

    fields = describe_fields()
    visible = {path for path, metadata in fields.items()
               if metadata['view'] == 'VIS'}
    assert visible == {
        'paths.visible_dir', 'paths.visible_pattern', 'paths.reference_image', 'paths.excluded_images',
    }


@pytest.mark.parametrize('extension', ['.tif', '.tiff', '.bmp', '.png', '.jpg', '.jpeg'])
def test_visible_image_formats_work_from_discovery_to_preview(tmp_path, extension):
    import cv2
    from d2ic.io.app_utils import prepare_image
    from D2IC_GUI.dic_run import _snapshot_images
    from D2IC_GUI.imaging import discover_visible_series, read_image

    images = tmp_path/'VIS'
    images.mkdir()
    color = np.zeros((12, 16, 3), dtype=np.uint8)
    color[..., 0] = np.arange(16, dtype=np.uint8)
    color[..., 1] = 80
    color[..., 2] = 190
    for frame in (0, 1):
        path = images/f'vis_{frame:04d}{extension}'
        if extension in ('.tif', '.tiff'):
            tifffile.imwrite(path, color, photometric='rgb')
        else:
            assert cv2.imwrite(str(path), color[..., ::-1])

    suggestion = discover_visible_series(images)['series'][0]
    assert suggestion['count'] == 2
    assert suggestion['first_image'] == f'vis_0000{extension}'
    study = tmp_path/'study'
    config = create_project(study)
    config['paths'].update(visible_dir=str(images),
                           reference_image=suggestion['first_image'],
                           visible_pattern=suggestion['pattern'])
    config['time']['visible_frame_regex'] = suggestion['frame_regex']
    save_project(study, config)

    client = TestClient(create_app(study))
    listed = client.get('/api/visible')
    assert listed.status_code == 200
    assert len(listed.json()['images']) == 2
    image_path = images/f'vis_0000{extension}'
    preview = client.get('/api/image', params={'path': str(image_path)})
    assert preview.status_code == 200
    assert preview.headers['content-type'] == 'image/png'
    ref, deformed, _ = _snapshot_images(study, config)
    assert ref['shape'] == [12, 16] and len(deformed) == 1
    assert np.allclose(read_image(image_path, visible=True), prepare_image(image_path))


def test_thermal_tiff_remains_scalar_temperature(tmp_path):
    from D2IC_GUI.imaging import read_image

    path = tmp_path/'temperature.tif'
    temperature = np.arange(20, dtype=np.float32).reshape(4, 5) + 273.15
    tifffile.imwrite(path, temperature)
    assert np.array_equal(read_image(path), temperature)
    color = np.zeros((4, 5, 3), dtype=np.uint8)
    tifffile.imwrite(tmp_path/'false_color.tif', color, photometric='rgb')
    with pytest.raises(ValueError, match='2D'):
        read_image(tmp_path/'false_color.tif')


def test_visible_preview_uses_unsaved_folder_without_changing_study(tmp_path):
    images = tmp_path/'new_VIS'
    images.mkdir()
    for frame in (0, 1):
        tifffile.imwrite(images/f'vis_{frame:04d}.tif',
                         np.arange(20, dtype=np.uint8).reshape(4, 5))
    study = tmp_path/'study'
    create_project(study)
    client = TestClient(create_app(study))
    inspected = client.get('/api/visible/inspect', params={
        'directory': str(images), 'pattern': 'vis_*.tif',
        'frame_regex': r'vis_(\d+)', 'fps': 10,
    })
    assert inspected.status_code == 200
    assert len(inspected.json()['images']) == 2
    selected = str(images/'vis_0000.tif')
    assert client.get('/api/image', params={'path': selected}).status_code == 400
    preview = client.get('/api/image', params={
        'path': selected, 'visible_dir': str(images),
    })
    assert preview.status_code == 200
    assert preview.headers['content-type'] == 'image/png'
    assert load_project(study)['paths']['visible_dir'] == ''
    outside = tmp_path/'outside.tif'
    tifffile.imwrite(outside, np.ones((4, 5), np.uint8))
    assert client.get('/api/image', params={
        'path': str(outside), 'visible_dir': str(images),
    }).status_code == 400


def test_visible_preview_survives_missing_frame_numbers(tmp_path):
    import cv2

    images = tmp_path/'VIS'
    images.mkdir()
    for name in ('sample_A.png', 'sample_B.png'):
        assert cv2.imwrite(str(images/name), np.arange(20, dtype=np.uint8).reshape(4, 5))
    client = TestClient(create_app())
    response = client.get('/api/visible/inspect', params={
        'directory': str(images), 'pattern': 'sample_*.png',
        'source': 'filename', 'frame_regex': r'(\d+)',
    })
    assert response.status_code == 200
    body = response.json()
    assert len(body['images']) == 2
    assert body['warnings'][0]['kind'] == 'preview_only'
    assert all(row['time_s'] is None for row in body['images'])
    assert client.get('/api/image', params={
        'path': str(images/'sample_A.png'), 'visible_dir': str(images),
    }).status_code == 200


def test_roi_file_overlay_and_mesh_on_visible_image(tmp_path):
    import cv2

    study = _configured_study(tmp_path)
    source = tmp_path/'roi_selected.png'
    mask = np.zeros((96, 128), np.uint8)
    mask[20:78, 26:102] = 255
    assert cv2.imwrite(str(source), mask)
    client = TestClient(create_app(study))
    config = load_project(study)
    before = load_project(study)['roi']['initial_mask']
    query = {'mask_path': str(source),
             'visible_dir': config['paths']['visible_dir'],
             'reference_image': config['paths']['reference_image']}
    overlay = client.get('/api/roi/overlay-image', params=query)
    assert overlay.status_code == 200
    pixels = cv2.imdecode(np.frombuffer(overlay.content, np.uint8), cv2.IMREAD_COLOR)
    assert pixels.shape == (96, 128, 3)
    assert not np.array_equal(pixels[40, 40], pixels[5, 5])
    assert load_project(study)['roi']['initial_mask'] == before
    roi_layer = client.get('/api/roi/layer-image', params=query)
    assert roi_layer.status_code == 200
    roi_rgba = cv2.imdecode(np.frombuffer(roi_layer.content, np.uint8), cv2.IMREAD_UNCHANGED)
    assert roi_rgba.shape == (96, 128, 4)
    assert roi_rgba[5, 5, 3] == 0 and roi_rgba[40, 40, 3] > 0
    bad = tmp_path/'bad_roi.png'
    assert cv2.imwrite(str(bad), np.ones((8, 8), np.uint8))
    assert client.get('/api/roi/overlay-image', params={**query, 'mask_path': str(bad)}).status_code == 400
    assert client.get('/api/roi/layer-image', params={**query, 'mask_path': str(bad)}).status_code == 400

    config['roi']['initial_mask'] = str(source)
    config['mesh']['element_size_px'] = 24.0
    save_project(study, config)
    saved = client.post('/api/roi/save', json={'operation': 'none', 'radius_px': 0})
    assert saved.status_code == 200
    assert source.read_bytes() == cv2.imencode('.png', mask)[1].tobytes()
    mesh = client.post('/api/mesh/preview')
    assert mesh.status_code == 200, mesh.text
    assert mesh.json()['nodes'] > 0 and mesh.json()['elements'] > 0
    composite = client.get('/api/mesh/preview-image')
    assert composite.status_code == 200
    image = cv2.imdecode(np.frombuffer(composite.content, np.uint8), cv2.IMREAD_COLOR)
    assert image.shape == (96, 128, 3)
    layer_response = client.get('/api/mesh/layer-image')
    assert layer_response.status_code == 200
    mesh_rgba = cv2.imdecode(np.frombuffer(layer_response.content, np.uint8), cv2.IMREAD_UNCHANGED)
    assert mesh_rgba.shape == (96, 128, 4)
    assert mesh_rgba[0, 0, 3] == 0 and np.any(mesh_rgba[..., 3] > 0)
    internal_source = study / load_project(study)['roi']['initial_mask']
    save_mask(internal_source, np.zeros((96, 128), bool))
    assert client.get('/api/mesh/preview-image').status_code == 400
    assert client.get('/api/mesh/layer-image').status_code == 400


@pytest.mark.parametrize('binning', [1, 2, 3])
@pytest.mark.parametrize('radius', [0.0, 3.0])
@pytest.mark.parametrize('operation', ['none', 'erosion', 'dilation'])
def test_photometric_roi_layer_matches_solver_mask(tmp_path, binning, radius, operation):
    from d2ic.io.app_utils import erode_correlation_roi
    from d2ic.io.binning import bin_mask
    from D2IC_GUI.imaging import read_mask

    study = _configured_study(tmp_path)
    source = tmp_path / 'roi_with_hole.png'
    mask = np.zeros((96, 128), bool)
    mask[10:85, 12:115] = True
    mask[40:50, 50:60] = False
    mask[2:5, 2:5] = True  # Below the default 64 px island threshold.
    save_mask(source, mask)
    original = source.read_bytes()
    client = TestClient(create_app(study))
    config = load_project(study)
    config['roi'].update(initial_mask=str(source), operation=operation, radius_px=1)
    save_project(study, config)
    assert client.post('/api/roi/save', json={}).status_code == 200
    final = read_mask(study / load_project(study)['roi']['final_mask'])
    final[:8, :8] = False  # The solver discards the isolated small component.
    assert client.get('/api/schema').json()['fields']['dic.roi_erosion_px']['view'] == 'ROI'
    query = dict(mask_path=str(source), visible_dir=config['paths']['visible_dir'],
                 reference_image=config['paths']['reference_image'],
                 kind='photometric', roi_erosion_px=radius, image_binning=binning,
                 operation=operation, radius_px=1)
    response = client.get('/api/roi/layer-image', params=query)
    assert response.status_code == 200, response.text
    layer = cv2.imdecode(np.frombuffer(response.content, np.uint8), cv2.IMREAD_UNCHANGED)
    assert layer.shape == (96, 128, 4)
    expected = erode_correlation_roi(bin_mask(final, binning),
                                     radius, image_binning=binning)
    expected = np.repeat(np.repeat(expected, binning, axis=0), binning, axis=1)[:96, :128]
    np.testing.assert_array_equal(layer[..., 3] > 0, expected)
    assert source.read_bytes() == original
    assert load_project(study)['dic']['roi_erosion_px'] == 0.0
    for invalid in (-1, 1000):
        error = client.get('/api/roi/layer-image', params={**query, 'roi_erosion_px': invalid})
        assert error.status_code == 400
    assert client.get('/api/roi/layer-image', params={**query, 'image_binning': 0}).status_code == 400


def test_grayscale_alpha_tiff_roi_uses_dic_mask_semantics(tmp_path):
    from D2IC_GUI.imaging import read_mask

    study = _configured_study(tmp_path)
    selected = tmp_path/'roi_gray_alpha.tif'
    gray = np.zeros((96, 128), np.uint8)
    gray[20:78, 26:102] = 255
    gray[20, 27] = 128
    alpha = np.full_like(gray, 255)
    tifffile.imwrite(selected, np.stack([gray, alpha], axis=-1),
                     photometric='minisblack', extrasamples='unassalpha')
    decoded = read_mask(selected)
    assert decoded.shape == gray.shape
    assert decoded[40, 40] and not decoded[0, 0]
    config = load_project(study)
    client = TestClient(create_app(study))
    overlay = client.get('/api/roi/overlay-image', params={
        'mask_path': str(selected),
        'visible_dir': config['paths']['visible_dir'],
        'reference_image': config['paths']['reference_image'],
    })
    assert overlay.status_code == 200, overlay.text
    config['roi']['initial_mask'] = str(selected)
    save_project(study, config)
    saved = client.post('/api/roi/save', json={'operation': 'none', 'radius_px': 0})
    assert saved.status_code == 200, saved.text
    assert np.array_equal(read_mask(study/'roi'/'mask_final.tif'), decoded)
    mesh = client.post('/api/mesh/preview')
    assert mesh.status_code == 200, mesh.text
    assert client.get('/api/mesh/preview-image').status_code == 200


def test_open_study_from_folder_or_config_file(tmp_path):
    study = tmp_path/'nouvelle_etude'
    create_project(study, name='nouvelle_etude')
    client = TestClient(create_app())
    parent = client.get('/api/filesystem', params={
        'path': str(tmp_path), 'kind': 'study',
    }).json()
    entry = next(row for row in parent['entries'] if row['name'] == 'nouvelle_etude')
    assert entry['is_study']
    listing = client.get('/api/filesystem', params={
        'path': str(study), 'kind': 'study',
    }).json()
    config_entry = next(row for row in listing['entries'] if row['name'] == 'config.toml')
    assert config_entry['is_study_config']
    for chosen in (study, study/'config.toml'):
        opened = client.post('/api/project/open', json={'folder': str(chosen)})
        assert opened.status_code == 200
        assert opened.json()['folder'] == str(study.resolve())
        assert client.get('/api/project').json()['name'] == 'nouvelle_etude'


def test_save_as_copies_unsaved_form_without_changing_source(tmp_path):
    source = tmp_path/'original'
    target = tmp_path/'saved_as'
    image_dir = tmp_path/'VIS'
    image_dir.mkdir()
    create_project(source, name='Originale')
    client = TestClient(create_app(source))
    form = load_project(source)
    form['project']['name'] = 'Brouillon non enregistré'
    form['paths']['visible_dir'] = str(image_dir)
    form['mesh']['element_size_px'] = 31.0
    response = client.post('/api/project/copy', json={
        'folder': str(target), 'name': 'Nouvelle version', 'config': form,
    })
    assert response.status_code == 200, response.text
    copied = load_project(target)
    assert copied['project']['name'] == 'Nouvelle version'
    assert copied['paths']['visible_dir'] == str(image_dir.resolve())
    assert copied['mesh']['element_size_px'] == 31.0
    assert load_project(source)['project']['name'] == 'Originale'
    assert load_project(source)['mesh']['element_size_px'] == 15.0
    assert client.get('/api/project').json()['folder'] == str(target.resolve())


def test_vis_exclusion_is_saved_and_frozen_as_exact_d2ic_paths(tmp_path):
    from D2IC_GUI.examples.generate_synthetic_study import generate_study
    from d2ic.io.config import load_sequence_config
    import tomllib

    source = tmp_path / 'source'
    generate_study(source)
    study = tmp_path / 'study'
    config = create_project(study)
    config['paths'].update(visible_dir=str(source / 'VIS'),
        visible_pattern='vis_*.tif', reference_image='vis_0000_tick0000.tif',
        excluded_images=['vis_0002_tick0035.tif'])
    config['time'].update(visible_frame_regex=r'tick(\d+)', visible_fps=100.)
    config['runtime'].update(jax_preferred='cpu', jax_fallback='cpu')
    config['dic'].update(interpolation='linear', max_iters=15, roi_erosion_px=3.0)
    config['mesh']['element_size_px'] = 24.
    save_mask(study / 'roi' / 'mask_final.tif', np.ones((96, 128), bool))
    save_project(study, config)
    assert load_project(study)['paths']['excluded_images'] == ['vis_0002_tick0035.tif']

    run = prepare_run(study)
    manifest = json.loads((run / 'manifest.json').read_text())
    from datetime import datetime
    assert run.name == datetime.fromisoformat(manifest['created_utc']).strftime('%y-%m-%d-001')
    assert manifest['run_id'] == run.name
    paths = [Path(row['path']) for row in manifest['visible_images']]
    assert [path.name for path in paths] == ['vis_0001_tick0015.tif', 'vis_0003_tick0045.tif']
    assert all(path.is_absolute() for path in paths)
    dic = load_sequence_config(run / 'dic_config.toml')
    assert list(dic.image_paths) == paths
    assert dic.image_stride == 1
    assert dic.roi_erosion_px == 3.0
    from D2IC_GUI.worker import run_worker
    run_worker(run)
    from d2ic.io.app_utils import erode_correlation_roi
    with np.load(run / 'results/dic_store/roi.npz') as archive:
        np.testing.assert_array_equal(archive['roi_mask'], np.ones((96, 128), bool))
        np.testing.assert_array_equal(archive['correlation_mask'],
            erode_correlation_roi(archive['roi_mask'], 3.0))
    assert json.loads((run / 'results' / 'dic_store' / 'progress.json').read_text())['completed_frames'] == 2
    with (run / 'config.toml').open('rb') as stream:
        assert tomllib.load(stream)['paths']['excluded_images'] == ['vis_0002_tick0035.tif']


def test_vis_exclusion_rejects_missing_file_and_empty_analysis(tmp_path):
    from D2IC_GUI.examples.generate_synthetic_study import generate_study
    generate_study(tmp_path / 'source')
    study = tmp_path / 'study'
    config = create_project(study)
    config['paths'].update(visible_dir=str(tmp_path / 'source' / 'VIS'),
        visible_pattern='vis_*.tif', reference_image='vis_0000_tick0000.tif',
        excluded_images=['missing.tif'])
    config['time'].update(visible_frame_regex=r'tick(\d+)', visible_fps=100.)
    save_project(study, config)
    with pytest.raises(ValueError, match='absentes de la série'):
        prepare_run(study)
    config['paths']['excluded_images'] = [p.name for p in (tmp_path / 'source' / 'VIS').glob('*.tif')
                                           if p.name != 'vis_0000_tick0000.tif']
    save_project(study, config)
    with pytest.raises(ValueError, match='Aucune image VIS déformée active'):
        prepare_run(study)


def test_disabled_vis_is_not_read_or_time_validated(tmp_path):
    from D2IC_GUI.examples.generate_synthetic_study import generate_study
    generate_study(tmp_path / 'source')
    bad = tmp_path / 'source' / 'VIS' / 'vis_bad.tif'
    bad.write_bytes(b'not an image')
    study = tmp_path / 'study'
    config = create_project(study)
    config['paths'].update(visible_dir=str(bad.parent), visible_pattern='vis_*.tif',
        reference_image='vis_0000_tick0000.tif', excluded_images=[bad.name])
    config['time'].update(visible_frame_regex=r'tick(\d+)', visible_fps=100.)
    save_mask(study / 'roi' / 'mask_final.tif', np.ones((96, 128), bool))
    save_project(study, config)
    run = prepare_run(study)
    manifest = json.loads((run / 'manifest.json').read_text())
    assert len(manifest['visible_images']) == 3
    assert all(row['path'] != str(bad) for row in manifest['visible_images'])


def test_run_list_actions_stop_restart_and_delete_are_scoped(tmp_path, monkeypatch):
    import os
    from D2IC_GUI.dic_run import write_status
    import D2IC_GUI.server as server_module

    study = tmp_path / 'study'
    create_project(study)
    run = study / 'runs' / 'trial'
    run.mkdir(parents=True)
    (run / 'result.txt').write_text('local result')
    write_status(run, 'running', pid=os.getpid())
    client = TestClient(create_app(study))
    listed = client.get('/api/runs').json()['runs']
    assert listed[0]['id'] == 'trial' and listed[0]['state'] == 'running'
    assert client.delete('/api/runs/trial').status_code == 400
    assert (run / 'result.txt').is_file()

    stopped = []
    monkeypatch.setattr(server_module.os, 'killpg', lambda pid, sig: stopped.append(pid))
    assert client.post('/api/runs/trial/cancel').json()['state'] == 'cancelled'
    assert stopped == [os.getpid()]
    # Simulate a failed run whose original worker has exited.
    write_status(run, 'failed', error='interrupted')
    monkeypatch.setattr(server_module, 'start_run', lambda path, resume=False: 12345 if resume else None)
    assert client.post('/api/runs/trial/resume').status_code == 200
    assert client.delete('/api/runs/trial').json() == {'id': 'trial', 'deleted': True}
    assert not run.exists()
    assert client.get('/api/runs').json()['runs'] == []

    outside = tmp_path / 'outside'
    outside.mkdir()
    write_status(outside, 'failed')
    (study / 'runs' / 'linked').symlink_to(outside, target_is_directory=True)
    assert client.delete('/api/runs/linked').status_code == 400
    assert (outside / 'status.json').is_file()


def test_run_directory_ids_increment_by_utc_day_and_keep_legacy_names(tmp_path):
    from datetime import datetime, timezone
    from D2IC_GUI.dic_run import _allocate_run_dir

    root = tmp_path / 'runs'
    root.mkdir()
    (root / '20261017T120000-deadbeef').mkdir()
    (root / '26-10-17-001').mkdir()
    day = datetime(2026, 10, 17, 23, 59, tzinfo=timezone.utc)
    first = _allocate_run_dir(root, day)
    second = _allocate_run_dir(root, day)
    next_day = _allocate_run_dir(root, datetime(2026, 10, 18, 0, 0, tzinfo=timezone.utc))
    assert [p.name for p in (first, second, next_day)] == [
        '26-10-17-002', '26-10-17-003', '26-10-18-001']
    assert (root / '20261017T120000-deadbeef').is_dir()


def test_cubic_worker_subprocess_imports_local_im_jax(tmp_path):
    import subprocess
    import sys
    from D2IC_GUI.examples.generate_synthetic_study import generate_study

    generate_study(tmp_path / 'source')
    study = tmp_path / 'study'
    config = create_project(study)
    config['paths'].update(visible_dir=str(tmp_path / 'source' / 'VIS'),
        visible_pattern='vis_*.tif', reference_image='vis_0000_tick0000.tif')
    config['time'].update(visible_frame_regex=r'tick(\d+)', visible_fps=100.)
    config['runtime'].update(jax_preferred='cpu', jax_fallback='cpu')
    config['dic']['max_iters'] = 15
    config['mesh']['element_size_px'] = 24.
    save_mask(study / 'roi' / 'mask_final.tif', np.ones((96, 128), bool))
    save_project(study, config)
    run = prepare_run(study)
    result = subprocess.run([sys.executable, '-m', 'D2IC_GUI.worker', str(run)],
        cwd=Path(__file__).parents[2], capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stdout[-3000:] + result.stderr[-3000:]
    assert json.loads((run / 'status.json').read_text())['state'] == 'completed'
    assert json.loads((run / 'results' / 'dic_store' / 'progress.json').read_text())['completed_frames'] == 3


def test_gui_inventory_reads_headers_but_run_inventory_reads_pixels(tmp_path, monkeypatch):
    import cv2
    import D2IC_GUI.imaging as imaging

    images = tmp_path/'VIS'; images.mkdir()
    for frame in range(2):
        assert cv2.imwrite(str(images/f'vis_{frame:03d}.bmp'),
                           np.full((12, 16), frame, dtype=np.uint8))
    original = imaging.read_image
    def forbidden(*args, **kwargs):
        raise AssertionError('GUI inventory decoded pixels')
    monkeypatch.setattr(imaging, 'read_image', forbidden)
    preview = imaging.inventory(tmp_path, 'VIS', 'vis_*.bmp', 'filename',
                                r'vis_(\d+)', 10, visible=True, inspect_pixels=False)
    assert [row['shape'] for row in preview['images']] == [[12, 16], [12, 16]]
    with pytest.raises(AssertionError, match='decoded pixels'):
        imaging.inventory(tmp_path, 'VIS', 'vis_*.bmp', 'filename',
                          r'vis_(\d+)', 10, visible=True)
    monkeypatch.setattr(imaging, 'read_image', original)


def test_preview_png_cache_refreshes_when_source_changes(tmp_path, monkeypatch):
    import cv2
    import D2IC_GUI.server as server

    study = tmp_path/'study'; images = tmp_path/'VIS'; images.mkdir()
    path = images/'vis_000.png'
    assert cv2.imwrite(str(path), np.arange(400, dtype=np.uint8).reshape(20, 20))
    config = create_project(study)
    config['paths'].update(visible_dir=str(images), reference_image=path.name,
                           visible_pattern='vis_*.png')
    save_project(study, config)
    client = TestClient(create_app(study))
    original = server.read_image
    count = 0
    def counted(*args, **kwargs):
        nonlocal count
        count += 1
        return original(*args, **kwargs)
    monkeypatch.setattr(server, 'read_image', counted)
    first = client.get('/api/image', params={'path': str(path)})
    second = client.get('/api/image', params={'path': str(path)})
    assert first.status_code == second.status_code == 200
    assert count == 1
    assert cv2.imwrite(str(path), np.arange(400, dtype=np.uint8).reshape(20, 20)[::-1])
    third = client.get('/api/image', params={'path': str(path)})
    assert third.status_code == 200
    assert count == 2
    assert third.content != first.content


def test_thermal_series_inspection_and_unsaved_preview_are_tiff_only(tmp_path):
    images = tmp_path/'new_TH'
    images.mkdir()
    values = np.arange(20, dtype=np.float32).reshape(4, 5) + 273.15
    for frame in (0, 1):
        tifffile.imwrite(images/f'TH_{frame:04d}.tiff', values + frame)
    tifffile.imwrite(images/'TH_color.tif', np.zeros((4, 5, 3), np.uint8), photometric='rgb')
    tifffile.imwrite(images/'unrelated.tif', values)
    (images/'ignore.png').write_bytes(b'not a thermal TIFF')
    client = TestClient(create_app())

    detected = client.get('/api/thermal/series', params={'directory': str(images)})
    assert detected.status_code == 200, detected.text
    series = detected.json()
    assert series['image_count'] == 4
    proposal = next(item for item in series['series'] if item['count'] == 2)
    assert proposal['pattern'] == 'TH_[0-9]*.tiff'

    inspected = client.get('/api/thermal/inspect', params={
        'directory': str(images), 'pattern': 'TH_[0-9]*.tiff',
        'frame_regex': r'TH_(\d+)', 'fps': 50,
    })
    assert inspected.status_code == 200, inspected.text
    assert [Path(row['path']).name for row in inspected.json()['images']] == [
        'TH_0000.tiff', 'TH_0001.tiff']
    assert all(row['shape'] == [4, 5] for row in inspected.json()['images'])

    fallback = client.get('/api/thermal/inspect', params={
        'directory': str(images), 'pattern': 'TH_[0-9]*.tiff',
        'frame_regex': r'no_frame', 'fps': 50,
    })
    assert fallback.status_code == 200, fallback.text
    assert fallback.json()['warnings'][0]['kind'] == 'preview_only'
    assert all(row['time_s'] is None for row in fallback.json()['images'])

    preview = client.get('/api/image', params={
        'path': 'TH_0000.tiff', 'thermal_dir': str(images),
    })
    assert preview.status_code == 200
    assert preview.headers['content-type'] == 'image/png'
    outside = tmp_path/'outside.tif'
    tifffile.imwrite(outside, values)
    assert client.get('/api/image', params={
        'path': str(outside), 'thermal_dir': str(images),
    }).status_code == 400


def test_synchronization_exposes_frames_paths_and_configured_rates(tmp_path):
    folder = _configured_study(tmp_path)
    client = TestClient(create_app(folder))

    response = client.get('/api/synchronization')
    assert response.status_code == 200, response.text
    data = response.json()
    assert data['visible_fps'] == 100.0
    assert data['thermal_fps'] == 10.0
    rows = data['images']

    exact = next(row for row in rows if row['time_s'] == pytest.approx(0.0))
    assert exact['visible_frame'] == 0
    assert exact['thermal_left_frame'] == exact['thermal_right_frame'] == 0
    assert exact['thermal_left'] == exact['thermal_right']
    assert Path(exact['visible_path']).is_absolute()
    assert Path(exact['thermal_left']).is_absolute()

    interpolated = next(row for row in rows if row['time_s'] == pytest.approx(0.15))
    assert interpolated['visible_frame'] == 15
    assert interpolated['thermal_left_frame'] == 1
    assert interpolated['thermal_right_frame'] == 2
    assert interpolated['thermal_left_time_s'] == pytest.approx(0.1)
    assert interpolated['thermal_right_time_s'] == pytest.approx(0.2)
    assert interpolated['thermal_left'] != interpolated['thermal_right']
    assert interpolated['alpha'] == pytest.approx(0.5)
    assert Path(interpolated['thermal_left']).is_absolute()
    assert Path(interpolated['thermal_right']).is_absolute()
    config = load_project(folder)
    for path, directory_key, directory in [
        (interpolated['visible_path'], 'visible_dir', config['paths']['visible_dir']),
        (interpolated['thermal_left'], 'thermal_dir', config['thermal']['image_dir']),
        (interpolated['thermal_right'], 'thermal_dir', config['thermal']['image_dir']),
    ]:
        preview = client.get('/api/image', params={'path': path, directory_key: directory})
        assert preview.status_code == 200, preview.text
        assert preview.headers['content-type'] == 'image/png'


def test_thermal_exclusions_are_active_and_break_interpolation_gaps(tmp_path):
    folder = _configured_study(tmp_path)
    config = load_project(folder)
    config['thermal']['excluded_images'] = ['th_0001_t0.10s.tif']
    save_project(folder, config)
    client = TestClient(create_app(folder))
    active = client.get('/api/thermal')
    assert active.status_code == 200, active.text
    names = [Path(row['path']).name for row in active.json()['images']]
    assert 'th_0001_t0.10s.tif' not in names
    sync = client.get('/api/synchronization')
    assert sync.status_code == 200, sync.text
    row = next(row for row in sync.json()['images'] if row['time_s'] == pytest.approx(.15))
    assert not row['valid']
    assert row['reason'] == 'missing_thermal_frame'

    points = [{'visible':[x,y], 'thermal':[x/2,y/2]}
              for x,y in ((10,10),(110,10),(10,80),(110,80))]
    assert client.post('/api/registration/fit', json={'points':points,'model':'affine'}).status_code == 200
    assert client.post('/api/registration/approve', json={'points':points,'model':'affine'}).status_code == 200
    run = prepare_run(folder)
    manifest = json.loads((run/'manifest.json').read_text())
    th_names = [Path(row['path']).name for row in manifest['thermal_images']]
    assert th_names == ['th_0000_t0.00s.tif', 'th_0002_t0.20s.tif',
                        'th_0004_t0.40s.tif', 'th_0005_t0.50s.tif']
    assert all(Path(row['path']).is_absolute() for row in manifest['thermal_images'])


def test_thermal_exclusions_reject_unknown_or_empty_series(tmp_path):
    folder = _configured_study(tmp_path)
    config = load_project(folder)
    client = TestClient(create_app(folder))
    points = [{'visible':[x,y], 'thermal':[x*63/127,y*47/95]}
              for x,y in ((10,10),(110,10),(10,80),(110,80))]
    assert client.post('/api/registration/fit', json={'points':points,'model':'affine'}).status_code == 200
    assert client.post('/api/registration/approve', json={'points':points,'model':'affine'}).status_code == 200
    config = load_project(folder)
    config['thermal']['excluded_images'] = ['missing.tif']
    save_project(folder, config)
    with pytest.raises(ValueError, match='Images TH désactivées absentes de la série'):
        prepare_run(folder)
    config['thermal']['excluded_images'] = [path.name for path in
        (tmp_path/'sources'/'TH').glob('*.tif')]
    save_project(folder, config)
    with pytest.raises(ValueError, match='Aucune image TH active'):
        prepare_run(folder)


def test_thermal_exclusion_schema_requires_unique_basenames():
    config = defaults('dic_thermal')
    config['thermal']['excluded_images'] = ['frame.tif', 'frame.tif']
    with pytest.raises(ValueError, match='thermal.excluded_images'):
        validate(config)
    config['thermal']['excluded_images'] = ['../frame.tif']
    with pytest.raises(ValueError, match='thermal.excluded_images'):
        validate(config)
