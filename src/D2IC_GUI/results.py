"""Scientific result access independent of the HTTP application.

Callers resolve a run directory. This module reads its frozen provenance and
committed fields, preserving the reference state, native VIS coordinates,
physical units and missing-value conventions. It owns neither HTTP responses
nor display caches and does not modify stored fields.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from d2ic.io.result_store import open_result_store

from .dic_run import inspect_run


def result_store(run):
    """Open committed per-frame results or the historical monolithic NPZ.

    An incomplete store remains unavailable until metadata and mesh exist.
    Frame visibility is delegated to the D2IC reader and its checkpoints.
    """
    store = run/'results'/'dic_store'
    if store.is_dir():
        if not (store/'metadata.json').is_file() or not (store/'mesh.npz').is_file():
            raise ValueError('Initialisation du calcul : aucun champ disponible pour le moment')
        return open_result_store(store)
    archive = run/'results'/'dic_results.npz'
    if not archive.is_file():
        raise ValueError('Initialisation du calcul : aucun champ disponible pour le moment')
    return open_result_store(archive)


def visible_shape(manifest, store=None):
    """Return the native VIS image shape in (height, width) pixels."""
    shape = manifest.get('visible_reference', {}).get('shape')
    if shape is None and store is not None:
        shape = store.metadata.get('image_shape')
    shape = np.asarray(shape)
    if (shape.shape != (2,) or not np.issubdtype(shape.dtype, np.integer)
            or np.any(shape <= 0)):
        raise ValueError('Dimensions natives VIS absentes ou invalides dans le manifeste')
    return int(shape[0]), int(shape[1])


def visible_source(run, manifest, frame):
    """Resolve and verify the exact VIS source recorded for frame k."""
    if frame < 0 or frame > len(manifest.get('visible_images', [])):
        raise ValueError('Instant VIS hors de la séquence')
    row = (manifest.get('visible_reference') if frame == 0
           else manifest['visible_images'][frame - 1])
    if not row or not row.get('path'):
        raise ValueError('Source VIS absente du manifeste')
    path = Path(row['path']).resolve()
    if not path.is_file():
        raise ValueError(f'Image VIS absente : {path}')
    stat = path.stat()
    if ('size' in row and stat.st_size != row['size']) or (
            'mtime_ns' in row and stat.st_mtime_ns != row['mtime_ns']):
        raise ValueError(f'Image VIS modifiée depuis le calcul : {path}')
    return path


def result_nodes(manifest, store, mesh, frame, overlay):
    """Return overlay coordinates in native VIS pixels, retaining raw u in pixels."""
    if overlay not in ('none', 'reference', 'current'):
        raise ValueError("overlay attendu : 'none', 'reference' ou 'current'")
    nodes = np.asarray(mesh['nodes_xy'], dtype=float)
    if overlay == 'none' or overlay == 'reference' or frame == 0:
        return nodes
    if frame < 0 or frame > store.frame_count:
        raise ValueError('Instant VIS hors de la séquence')
    record = store.read_frame(frame - 1)
    displacement = np.asarray(record['u_nodal'], dtype=float)
    if displacement.shape != nodes.shape or not np.isfinite(displacement).all():
        raise ValueError('Déplacements nodaux invalides pour l’overlay courant')
    # The stored displacement is in VIS pixels even when plotted values are in mm.
    return nodes + displacement


def run_field_values(run, manifest, store, field, frame, mesh=None):
    """Read a field at GUI frame 0 (reference) or a committed DIC frame.

    Displacement values use the run's px/mm unit, strains remain tensorial
    E12 and dimensionless, and temperatures retain their declared unit.
    Residuals are rasters and Temperature_element is cell-valued; the other
    fields are nodal. The reference adds zero displacement and strain.
    """
    if field not in ('u1', 'u2', 'u_norm', 'E11', 'E22', 'E12', 'Residual',
                     'Temperature', 'Delta_temperature', 'Temperature_element'):
        raise ValueError(f'Champ inconnu : {field}')
    if frame < 0 or frame > store.frame_count:
        raise ValueError('Instant VIS hors de la séquence')
    mesh = mesh if mesh is not None else store.read_mesh()
    nodes = np.asarray(mesh['nodes_xy'])
    elements = np.asarray(mesh['elements'])
    record = {} if frame == 0 else store.read_frame(frame - 1)
    if field == 'Residual':
        if 'discrepancy_ref' not in record:
            raise ValueError('Résidu indisponible pour cet instant')
        return np.asarray(record['discrepancy_ref'])
    if field in ('u1', 'u2', 'u_norm'):
        u = np.zeros_like(nodes) if frame == 0 else np.asarray(record['u_nodal'])
        values = u[:, 0] if field == 'u1' else u[:, 1] if field == 'u2' else np.linalg.norm(u, axis=1)
        if manifest['length_unit'] == 'mm':
            values = values * manifest['mm_per_pixel']
        return values
    if field in ('E11', 'E22', 'E12'):
        strain = np.zeros((len(nodes), 3)) if frame == 0 else np.asarray(record['strain'])
        return strain[:, ('E11', 'E22', 'E12').index(field)]
    path = run/'results'/'thermal_fields.npz'
    if not path.is_file():
        raise ValueError('Champs thermiques absents de ce run')
    with np.load(path, allow_pickle=False) as thermal:
        if field == 'Temperature_element':
            return np.asarray(thermal['temperature_element'][frame])
        key = 'temperature' if field == 'Temperature' else 'delta_temperature'
        return np.asarray(thermal[key][frame])


def run_histories_payload(run, nodes):
    """Read each stored frame and thermal archive once for selected VIS nodes."""
    status = inspect_run(run)
    manifest = status['manifest']
    store = result_store(run)
    count = len(store.read_mesh()['nodes_xy'])
    if not nodes or any(node < 0 or node >= count for node in nodes):
        raise ValueError('Indice de nœud hors maillage')
    nodes = list(dict.fromkeys(nodes))
    available = store.frame_count + 1
    times = ([manifest['visible_reference']['time_s']] +
             [row['time_s'] for row in manifest['visible_images']])[:available]
    u = np.zeros((len(times), len(nodes), 2))
    strain = np.zeros((len(times), len(nodes), 3))
    if store.path.is_file():  # Legacy NPZ: decompress each array once.
        u[1:] = store.read_history('u_nodal')[:, nodes]
        strain[1:] = store.read_history('strain')[:, nodes]
    else:
        for frame in range(1, len(times)):
            record = store.read_frame(frame - 1)
            u[frame] = np.asarray(record['u_nodal'])[nodes]
            strain[frame] = np.asarray(record['strain'])[nodes]

    thermal = None
    path = run/'results'/'thermal_fields.npz'
    if path.is_file():
        with np.load(path, allow_pickle=False) as fields:
            thermal = (np.asarray(fields['temperature'])[:, nodes],
                       np.asarray(fields['delta_temperature'])[:, nodes])
    scale = manifest['mm_per_pixel'] if manifest['length_unit'] == 'mm' else 1.
    histories = []
    for j, node in enumerate(nodes):
        rows = []
        for k, time in enumerate(times):
            row = {
                'time_s': time,
                'u1': float(u[k, j, 0]*scale),
                'u2': float(u[k, j, 1]*scale),
                'E11': float(strain[k, j, 0]),
                'E22': float(strain[k, j, 1]),
                'E12': float(strain[k, j, 2]),
            }
            if thermal is not None:
                row['Temperature'] = (float(thermal[0][k, j])
                                      if np.isfinite(thermal[0][k, j]) else None)
                row['Delta_temperature'] = (float(thermal[1][k, j])
                                            if np.isfinite(thermal[1][k, j]) else None)
            rows.append(row)
        histories.append({'node': node, 'history': rows})
    return {'length_unit': manifest['length_unit'],
            'temperature_unit': manifest.get('temperature_unit'),
            'histories': histories}


def section_payload(run, field, frame, x0, y0, x1, y1, samples, scope):
    """Sample nodal fields on a material segment in reference VIS pixels.

    Quadrilaterals use the viewer's 012/023 triangles; absent values remain
    null. Distances use the run length unit, including its reference state.
    """
    endpoints = np.asarray([x0, y0, x1, y1], dtype=float)
    if not np.isfinite(endpoints).all() or np.hypot(x1-x0, y1-y0) <= 0:
        raise ValueError('La coupe exige deux extrémités finies et distinctes')
    if field not in ('u1', 'u2', 'u_norm', 'E11', 'E22', 'E12',
                     'Temperature', 'Delta_temperature'):
        raise ValueError('Champ non pris en charge pour une coupe')
    if scope not in ('image', 'sequence'):
        raise ValueError('Portée attendue : image ou sequence')
    if samples < 2 or samples > 2000:
        raise ValueError('samples doit être compris entre 2 et 2000')

    manifest = inspect_run(run)['manifest']
    store = result_store(run)
    mesh = store.read_mesh()
    nodes = np.asarray(mesh['nodes_xy'], dtype=float)
    elements = np.asarray(mesh['elements'], dtype=int)
    triangles = (elements if elements.shape[1] == 3 else
                 np.concatenate([elements[:, [0, 1, 2]], elements[:, [0, 2, 3]]]))
    px = np.linspace(float(x0), float(x1), samples)
    py = np.linspace(float(y0), float(y1), samples)
    scale = float(manifest['mm_per_pixel']) if manifest['length_unit'] == 'mm' else 1.
    distance = np.hypot(px-px[0], py-py[0])*scale
    times = ([manifest['visible_reference']['time_s']] +
             [row['time_s'] for row in manifest['visible_images']])[:store.frame_count+1]
    frames = range(len(times)) if scope == 'sequence' else (frame,)
    if any(k < 0 or k >= len(times) for k in frames):
        raise ValueError('Instant VIS hors de la séquence')

    profiles = []
    for k in frames:
        nodal = np.asarray(run_field_values(run, manifest, store, field, k, mesh), dtype=float)
        vals = np.full(samples, np.nan)
        for tri_nodes in triangles:
            vertices = nodes[tri_nodes]
            a, b, c = vertices
            den = (b[1]-c[1])*(a[0]-c[0]) + (c[0]-b[0])*(a[1]-c[1])
            if abs(den) < 1e-14:
                continue
            candidates = np.flatnonzero(~np.isfinite(vals))
            qx, qy = px[candidates], py[candidates]
            w0 = ((b[1]-c[1])*(qx-c[0]) + (c[0]-b[0])*(qy-c[1]))/den
            w1 = ((c[1]-a[1])*(qx-c[0]) + (a[0]-c[0])*(qy-c[1]))/den
            w2 = 1-w0-w1
            inside = (w0 >= -1e-10) & (w1 >= -1e-10) & (w2 >= -1e-10)
            valid = inside & np.isfinite(nodal[tri_nodes]).all()
            if valid.any():
                vals[candidates[valid]] = (w0[valid]*nodal[tri_nodes[0]] +
                                           w1[valid]*nodal[tri_nodes[1]] +
                                           w2[valid]*nodal[tri_nodes[2]])
        profiles.append({
            'frame': k, 'time_s': float(times[k]), 'distance': distance.tolist(),
            'values': [float(v) if np.isfinite(v) else None for v in vals],
        })
    unit = (manifest.get('temperature_unit')
            if field in ('Temperature', 'Delta_temperature')
            else ('1' if field.startswith('E') else manifest['length_unit']))
    return {
        'field': field, 'length_unit': manifest['length_unit'],
        'temperature_unit': manifest.get('temperature_unit'),
        'value_unit': unit, 'profiles': profiles,
        'x_ref_px': px.tolist(), 'y_ref_px': py.tolist(),
    }


def _transport_reference_raster(array, reference_nodes, current_nodes, triangles, shape_hw, binning):
    """Transport a reference-grid scalar map to current VIS pixel centres.

    Invert the piecewise affine FE map on deformed triangles. Nearest-neighbour
    sampling preserves stored residual values and their NaN support. Row blocks
    bound the temporary memory used for full-resolution visualization.
    """
    import matplotlib.tri as tri
    height, width = shape_hw
    triangulation = tri.Triangulation(current_nodes[:, 0], current_nodes[:, 1], triangles)
    inverse_x = tri.LinearTriInterpolator(triangulation, reference_nodes[:, 0])
    inverse_y = tri.LinearTriInterpolator(triangulation, reference_nodes[:, 1])
    valid_source = np.isfinite(array).astype(np.uint8)
    source = np.where(valid_source, array, 0).astype(np.float32)
    result = np.full((height, width), np.nan, dtype=np.float32)
    for start in range(0, height, 128):
        stop = min(start + 128, height)
        yy, xx = np.mgrid[start:stop, :width]
        ref_x, ref_y = inverse_x(xx, yy), inverse_y(xx, yy)
        valid = ~(np.ma.getmaskarray(ref_x) | np.ma.getmaskarray(ref_y))
        map_x = ((ref_x.filled(-1e6) + .5) / binning - .5).astype(np.float32)
        map_y = ((ref_y.filled(-1e6) + .5) / binning - .5).astype(np.float32)
        values = cv2.remap(source, map_x, map_y, cv2.INTER_NEAREST,
                           borderMode=cv2.BORDER_CONSTANT, borderValue=0)
        support = cv2.remap(valid_source, map_x, map_y, cv2.INTER_NEAREST,
                            borderMode=cv2.BORDER_CONSTANT, borderValue=0).astype(bool)
        result[start:stop] = np.where(valid & support, values, np.nan)
    return result
