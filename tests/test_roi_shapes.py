"""Pixel-center rasterization and draft ROI shape API contracts."""

import base64
import cv2
import numpy as np
import pytest
import tifffile
from fastapi.testclient import TestClient

from D2IC_GUI.imaging import mask_from_shapes, read_mask, save_mask
from D2IC_GUI.project import create_project, load_project, save_project
from D2IC_GUI.server import create_app
from d2ic.io.app_utils import read_roi_mask


def _rectangle(operation='add', **coords):
    return {'kind': 'rectangle', 'operation': operation,
            'x0': 2, 'y0': 3, 'x1': 8, 'y1': 9, **coords}


def test_rectangle_ellipse_and_ordered_subtraction_use_pixel_centers():
    rectangle = mask_from_shapes([_rectangle()], (14, 12))
    assert rectangle.sum() == 7 * 7
    assert rectangle[3, 2] and rectangle[9, 8]
    assert not rectangle[2, 2] and not rectangle[10, 8]

    ellipse = mask_from_shapes([{'kind': 'ellipse', 'operation': 'add',
                                 'x0': 2, 'y0': 2, 'x1': 8, 'y1': 8}], (11, 11))
    assert ellipse[5, 5] and ellipse[2, 5] and ellipse[5, 8]
    assert not ellipse[2, 2] and not ellipse[0, 5]

    ring = mask_from_shapes([
        {'kind': 'rectangle', 'operation': 'add', 'x0': 1, 'y0': 1, 'x1': 9, 'y1': 9},
        {'kind': 'ellipse', 'operation': 'subtract', 'x0': 3, 'y0': 3, 'x1': 7, 'y1': 7},
    ], (11, 11))
    assert ring[1, 1] and not ring[5, 5] and not ring[3, 5] and ring[3, 4]


def test_shape_coordinate_order_and_image_clipping():
    mask = mask_from_shapes([{'kind': 'rectangle', 'operation': 'add',
                              'x0': 8, 'y0': 7, 'x1': -3, 'y1': -2}], (6, 7))
    assert mask.shape == (6, 7)
    assert mask.all()
    outside = mask_from_shapes([{'kind': 'ellipse', 'operation': 'add',
                                 'x0': 9, 'y0': 2, 'x1': 12, 'y1': 5}], (8, 8))
    assert not outside.any()


@pytest.mark.parametrize('coords', [
    {'x0': 2, 'y0': 2, 'x1': 2, 'y1': 5},
    {'x0': 2, 'y0': 2, 'x1': 5, 'y1': 2},
    {'x0': float('nan'), 'y0': 2, 'x1': 5, 'y1': 5},
])
def test_shapes_reject_zero_area_or_nonfinite_coordinates(coords):
    with pytest.raises(ValueError):
        mask_from_shapes([{'kind': 'rectangle', 'operation': 'add', **coords}], (8, 8))


def test_marked_tiff_keeps_white_foreground_even_when_roi_covers_over_95_percent(tmp_path):
    roi = np.ones((20, 24), dtype=bool)
    roi[8:11, 10:13] = False
    path = tmp_path / 'mostly_full_roi.tif'
    save_mask(path, roi)
    decoded = tifffile.imread(path)
    assert np.array_equal(decoded > 0, roi)
    assert np.array_equal(read_roi_mask(path, decoded), roi)
    assert np.array_equal(read_mask(path), roi)


def test_unmarked_legacy_tiff_keeps_auto_inversion_heuristic(tmp_path):
    legacy = np.ones((20, 24), dtype=np.uint8) * 255
    legacy[8, 10] = 0
    path = tmp_path / 'legacy_roi.tif'
    tifffile.imwrite(path, legacy)
    loaded = read_roi_mask(path, legacy)
    assert loaded.sum() == 1 and loaded[8, 10]


def _study(tmp_path):
    study = tmp_path / 'study'
    config = create_project(study)
    visible = tmp_path / 'visible'
    visible.mkdir()
    image = np.arange(20 * 24, dtype=np.uint8).reshape(20, 24)
    assert cv2.imwrite(str(visible / 'ref.png'), image)
    config['paths'].update(visible_dir=str(visible), reference_image='ref.png')
    save_project(study, config)
    return study, visible, image


def test_shape_preview_uses_native_roi_and_binned_photometric_pixels(tmp_path):
    study, visible, _ = _study(tmp_path)
    client = TestClient(create_app(study))
    body = {'visible_dir': str(visible), 'reference_image': 'ref.png',
            'shapes': [_rectangle(x0=2, y0=2, x1=13, y1=13)],
            'roi_erosion_px': 0.0, 'image_binning': 2,
            'remove_islands': False, 'min_island_area_px': 0}
    response = client.post('/api/roi/shapes/preview', json=body)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result['area_px'] == 12 * 12
    assert result['correlation_pixels'] == 6 * 6
    assert result['photometric_error'] is None
    roi_png = base64.b64decode(result['roi_data_url'].split(',', 1)[1])
    roi = cv2.imdecode(np.frombuffer(roi_png, np.uint8), cv2.IMREAD_UNCHANGED)
    assert roi.shape == (20, 24, 4) and roi[2, 2, 3] > 0 and roi[0, 0, 3] == 0
    photo_png = base64.b64decode(result['photometric_data_url'].split(',', 1)[1])
    photo = cv2.imdecode(np.frombuffer(photo_png, np.uint8), cv2.IMREAD_UNCHANGED)
    assert photo.shape == (20, 24, 4) and photo[2, 2, 3] > 0
    assert photo[0, 0, 3] == 0

    empty = client.post('/api/roi/shapes/preview', json={**body, 'shapes': []})
    assert empty.status_code == 200 and empty.json()['area_px'] == 0

    small_binned_island = client.post('/api/roi/shapes/preview', json={
        **body,
        'shapes': [{'kind': 'rectangle', 'operation': 'add',
                    'x0': 2, 'y0': 2, 'x1': 11, 'y1': 11}],
        'remove_islands': True, 'min_island_area_px': 64,
    })
    assert small_binned_island.status_code == 200, small_binned_island.text
    assert small_binned_island.json()['area_px'] == 100
    # The 100 px island survives native-resolution filtering before binning;
    # its 25 binned pixels are below 64, but are not filtered a second time.
    assert small_binned_island.json()['correlation_pixels'] == 25
    for key in ('image_binning', 'min_island_area_px'):
        invalid_integer = client.post('/api/roi/shapes/preview', json={
            **body, key: 1.5,
        })
        assert invalid_integer.status_code == 200
        assert invalid_integer.json()['photometric_data_url'] is None
        assert key in invalid_integer.json()['photometric_error']


def test_shape_save_creates_new_mask_without_overwriting_import_or_config(tmp_path):
    study, visible, _ = _study(tmp_path)
    imported = tmp_path / 'imported.tif'
    imported_mask = np.zeros((20, 24), dtype=np.uint8)
    imported_mask[0, 0] = 255
    assert cv2.imwrite(str(imported), imported_mask)
    config = load_project(study)
    config['roi']['initial_mask'] = str(imported)
    save_project(study, config)
    config_bytes = (study / 'config.toml').read_bytes()
    source_bytes = imported.read_bytes()

    body = {'visible_dir': str(visible), 'reference_image': 'ref.png',
            'shapes': [
                {'kind': 'rectangle', 'operation': 'add',
                 'x0': 0, 'y0': 0, 'x1': 23, 'y1': 19},
                {'kind': 'rectangle', 'operation': 'subtract',
                 'x0': 10, 'y0': 8, 'x1': 12, 'y1': 10},
            ]}
    client = TestClient(create_app(study))
    result = client.post('/api/roi/shapes/save', json=body)
    assert result.status_code == 200, result.text
    payload = result.json()
    assert payload['initial_mask_path'] == 'roi/drawn_roi_001.tif'
    assert payload['mask_path'].endswith('/roi/drawn_roi_001.tif')
    assert payload['area_px'] == 20 * 24 - 9
    saved = read_mask(study / payload['initial_mask_path'])
    assert saved.sum() == 20 * 24 - 9 and saved[0, 0] and not saved[8, 10]
    assert imported.read_bytes() == source_bytes
    assert (study / 'config.toml').read_bytes() == config_bytes
    # The conventional save/maillage path must preserve the drawn mask's
    # explicit polarity when it copies the TIFF to mask_initial/final.
    config = load_project(study)
    config['roi']['initial_mask'] = payload['initial_mask_path']
    assert client.put('/api/project/config', json=config).status_code == 200
    saved_roi = client.post('/api/roi/save', json={'operation': 'none', 'radius_px': 0})
    assert saved_roi.status_code == 200, saved_roi.text
    final = read_mask(study / 'roi' / 'mask_final.tif')
    assert np.array_equal(final, saved)

    second = client.post('/api/roi/shapes/save', json=body)
    assert second.json()['initial_mask_path'] == 'roi/drawn_roi_002.tif'


def test_odd_image_photometry_excludes_incomplete_blocks_without_changing_roi(tmp_path):
    study, visible, _ = _study(tmp_path)
    assert cv2.imwrite(str(visible / 'odd.png'), np.ones((5, 5), dtype=np.uint8))
    client = TestClient(create_app(study))
    body = {'visible_dir': str(visible), 'reference_image': 'odd.png',
            'shapes': [_rectangle(x0=0, y0=0, x1=4, y1=4)],
            'image_binning': 2, 'remove_islands': False, 'roi_erosion_px': 0}
    response = client.post('/api/roi/shapes/preview', json=body)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result['area_px'] == 25 and result['correlation_pixels'] == 4
    assert result['photometric_error'] is None
    image = cv2.imdecode(np.frombuffer(base64.b64decode(
        result['photometric_data_url'].split(',', 1)[1]), np.uint8), cv2.IMREAD_UNCHANGED)
    assert image.shape == (5, 5, 4)
    assert image[0, 0, 3] and not image[4, :, 3].any() and not image[:, 4, 3].any()
    saved = client.post('/api/roi/shapes/save', json=body).json()
    layer = client.get('/api/roi/layer-image', params={
        'mask_path': saved['initial_mask_path'], 'visible_dir': str(visible),
        'reference_image': 'odd.png', 'kind': 'photometric', 'image_binning': 2,
        'remove_islands': False, 'roi_erosion_px': 0})
    assert layer.status_code == 200, layer.text
    imported = cv2.imdecode(np.frombuffer(layer.content, np.uint8), cv2.IMREAD_UNCHANGED)
    np.testing.assert_array_equal(imported, image)
