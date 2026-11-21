"""Separate D2IC process; invoked with ``python -m D2IC_GUI.worker RUN``."""

from __future__ import annotations

import json
from contextlib import contextmanager
from tempfile import TemporaryDirectory
from functools import lru_cache
import sys
import traceback
from pathlib import Path

import numpy as np

# In a source checkout, the outer im_jax/ directory shadows the actual
# im_jax package unless its project root is on the worker's import path.
_LOCAL_IM_JAX = Path(__file__).resolve().parents[1] / 'im_jax'
if (_LOCAL_IM_JAX / 'im_jax' / '__init__.py').is_file():
    sys.path.insert(0, str(_LOCAL_IM_JAX))

from .dic_run import write_status


def _verify_source_rows(rows):
    for row in rows:
        path = Path(row['path'])
        if not path.is_file():
            raise FileNotFoundError(f'Image source disparue : {path}')
        stat = path.stat()
        if stat.st_size != row['size'] or stat.st_mtime_ns != row['mtime_ns']:
            raise RuntimeError(f'Image source modifiée pendant le calcul : {path}')


def _annotate_result_store(run, manifest):
    """Persist measured VIS times and physical conventions with the fields."""
    from d2ic.io.result_store import SCHEMA_VERSION
    from .project import load_project
    import os
    import tempfile

    metadata_path = run/'results'/'dic_store'/'metadata.json'
    metadata = json.loads(metadata_path.read_text(encoding='utf-8'))
    config = load_project(run)
    metadata.update({
        'reference_time_s': manifest['visible_reference']['time_s'],
        'frame_times_s': [row['time_s'] for row in manifest['visible_images']],
        'visible_time_source': config['time']['visible_source'],
        'coordinate_unit': 'px_VIS_native',
        'displacement_unit': 'px_VIS_native',
        'strain_measure': 'Green-Lagrange',
        'strain_shear_convention': 'tensorial_E12',
        'export_length_unit': manifest['length_unit'],
        'mm_per_pixel': manifest['mm_per_pixel'],
    })
    fd, temporary = tempfile.mkstemp(dir=metadata_path.parent, suffix='.tmp')
    with os.fdopen(fd, 'w', encoding='utf-8') as stream:
        json.dump(metadata, stream, indent=2)
        stream.flush(); os.fsync(stream.fileno())
    os.replace(temporary, metadata_path)
    manifest['result_schema_version'] = SCHEMA_VERSION


def _rebuild_pvd(run, manifest):
    """Date the DIC VTU by measured VIS image times, including reference."""
    from d2ic.io.paraview import write_pvd
    import meshio

    from .project import load_project
    output_cfg = load_project(run)['output']
    results = run/'results'
    vtus = sorted(path for path in results.glob('dic_*.vtu')
                  if path.stem[4:].isdigit())
    if not vtus:
        return
    deformed = manifest['visible_images']
    if len(vtus) != len(deformed):
        raise RuntimeError(f'{len(vtus)} VTU pour {len(deformed)} images VIS calculées')
    from d2ic.io.result_store import open_result_store
    source = results/'dic_store'
    mesh = open_result_store(source if source.is_dir() else results/'dic_results.npz').read_mesh()
    nodes, cells = mesh['nodes_xy'], mesh['elements']
    kind = 'triangle' if cells.shape[1] == 3 else 'quad'
    mm = manifest['length_unit'] == 'mm'
    factor = manifest['mm_per_pixel'] if mm else 1.0
    points = np.column_stack([nodes * factor, np.zeros(len(nodes))])
    zero = np.zeros_like(points)
    initial = meshio.Mesh(points, [(kind, cells)], point_data={
        'Displacement': zero, 'Deformed_position': points,
        'Displacement_magnitude': np.zeros(len(nodes)),
        'E11': np.zeros(len(nodes)), 'E22': np.zeros(len(nodes)),
        'E12': np.zeros(len(nodes)), 'Strain': np.zeros((len(nodes), 9)),
    })
    initial_path = results/'dic_reference.vtu'
    meshio.write(initial_path, initial)
    exported_vtus = []
    for path in vtus:
        if mm:
            # Keep the D2IC pixel export untouched so rebuilding after a
            # resumed run cannot multiply coordinates a second time.
            mesh = meshio.read(path)
            mesh.points *= factor
            for name in ('Displacement', 'Deformed_position', 'Displacement_magnitude'):
                if name in mesh.point_data:
                    mesh.point_data[name] *= factor
            converted = results / f'{path.stem}_mm.vtu'
            meshio.write(converted, mesh)
            exported_vtus.append(converted)
        else:
            exported_vtus.append(path)
    datasets = [(manifest['visible_reference']['time_s'], initial_path)]
    datasets += [(row['time_s'], path) for row, path in zip(deformed, exported_vtus)]
    old_pvd = results/'dic.pvd'
    if output_cfg['export_pvd']:
        pvd_path = results/(output_cfg['series_name']+'.pvd')
        write_pvd(pvd_path, datasets)
        manifest['dic_pvd'] = str(pvd_path.resolve())
    else:
        manifest['dic_pvd'] = None
    if old_pvd.is_file() and (not output_cfg['export_pvd'] or old_pvd != results/(output_cfg['series_name']+'.pvd')):
        old_pvd.unlink()
    manifest['dic_vtu'] = [str(path.resolve()) for _, path in datasets]


@contextmanager
def _thermal_field_buffers(output, frame_count, node_count, element_count):
    """Allocate disk-backed output arrays and release mappings on every exit.

    The final NPZ schema is unchanged. Keeping contiguous NPY buffers on disk
    avoids retaining all thermal states and stacking them again in RAM. Close
    mappings explicitly before deleting temporary files, including on Windows.
    """
    layout = {
        'temperature': (node_count, float),
        'delta_temperature': (node_count, float),
        'thermal_valid': (node_count, bool),
        'temperature_element': (element_count, float),
        'delta_temperature_element': (element_count, float),
        'thermal_valid_element': (element_count, bool),
    }
    with TemporaryDirectory(prefix='.thermal-fields-', dir=output) as temporary:
        buffers = {}
        try:
            for name, (count, dtype) in layout.items():
                buffers[name] = np.lib.format.open_memmap(
                    Path(temporary) / f'{name}.npy', mode='w+', dtype=dtype,
                    shape=(frame_count, count))
            yield buffers
        finally:
            for buffer in buffers.values():
                buffer._mmap.close()


def _fuse_thermal(run, manifest):
    """Project transported DIC material points into approved TH acquisitions."""
    from .project import load_project
    from .imaging import read_image
    from .thermal import align_thermal_times, iter_thermal_sequence, write_thermal_vtu, write_thermal_pvd
    from DICTHFusion.registration import load_registration
    import hashlib

    cfg = load_project(run)
    calibration_path = run/'visible_thermal.json'
    if hashlib.sha256(calibration_path.read_bytes()).hexdigest() != manifest['calibration_sha256']:
        raise RuntimeError('Calibration figée modifiée pendant le run')
    _, matrix = load_registration(calibration_path)
    th_rows = manifest['thermal_images']
    _verify_source_rows(th_rows)
    vis_rows = [manifest['visible_reference'], *manifest['visible_images']]
    sync = cfg['synchronization']
    aligned = align_thermal_times(
        [row['time_s'] for row in vis_rows], [row['time_s'] for row in th_rows],
        method=sync['method'], visible_frames=[row.get('frame') for row in vis_rows],
        thermal_frames=[row.get('frame') for row in th_rows],
        visible_event_frame=sync['visible_event_frame'],
        thermal_event_frame=sync['thermal_event_frame'],
        thermal_offset_s=sync['thermal_offset_s'])
    th_frames = None if th_rows[0].get('frame') is None else [row['frame'] for row in th_rows]
    # The temporal fusion reads only the one or two TH acquisitions needed
    # for the current VIS state, even when the original sequence is long.
    @lru_cache(maxsize=2)
    def thermal_image(index):
        return read_image(th_rows[index]['path']).astype(float)

    class ThermalSequence:
        def __len__(self):
            return len(th_rows)

        def __getitem__(self, index):
            if not 0 <= index < len(th_rows):
                raise IndexError(index)
            return thermal_image(index)

    thermal_images = ThermalSequence()
    from d2ic.io.result_store import open_result_store
    source = run/'results'/'dic_store'
    dic = open_result_store(source if source.is_dir() else run/'results'/'dic_results.npz')
    mesh = dic.read_mesh()
    nodes, elements = mesh['nodes_xy'], mesh['elements']
    @lru_cache(maxsize=1)
    def dic_frame(index):
        if index == 0:
            return {'u_nodal': np.zeros((len(nodes), 2)),
                    'strain': np.zeros((len(nodes), 3))}
        return dic.read_frame(index - 1)

    class Displacements:
        def __len__(self):
            return len(vis_rows)

        def __getitem__(self, index):
            if not 0 <= index < len(vis_rows):
                raise IndexError(index)
            return dic_frame(index)['u_nodal']

    states = iter_thermal_sequence(
        [row['time_s'] for row in vis_rows], aligned, th_frames,
        thermal_images, nodes, Displacements(), elements, matrix,
        thermal_fps=cfg['thermal']['thermal_fps'])
    output = run/'results'
    pending = output/'thermal_fields.pending.npz'
    datasets = []
    provenance = []
    try:
        with _thermal_field_buffers(output, len(vis_rows), len(nodes), len(elements)) as buffers:
            for k, state in enumerate(states):
                if k == 0:
                    reference_available = bool(state['time_valid'] and np.any(state['thermal_valid']))
                    manifest['reference_temperature_available'] = reference_available
                    if not reference_available:
                        manifest['reference_temperature_warning'] = (
                            'T_ref indisponible au premier temps VIS ; Delta_temperature reste absent')
                for name, buffer in buffers.items():
                    buffer[k] = state[name]

                left, right = state['left'], state['right']
                provenance.append({
                    'visible_path': vis_rows[k]['path'], 'time_s': state['time_s'],
                    'thermal_left': th_rows[left]['path'] if left >= 0 else None,
                    'thermal_right': th_rows[right]['path'] if right >= 0 else None,
                    'thermal_left_time_s': float(aligned[left]) if left >= 0 else None,
                    'thermal_right_time_s': float(aligned[right]) if right >= 0 else None,
                    'alpha': state['alpha'] if state['time_valid'] else None,
                    'time_valid': state['time_valid'], 'reason': state['reason'],
                    'valid_nodes': int(np.count_nonzero(state['thermal_valid'])),
                    'valid_elements': int(np.count_nonzero(state['thermal_valid_element'])),
                })
                if not state['time_valid'] or not cfg['output']['export_vtu']:
                    continue
                record = dic_frame(k)
                path = output/f'coupled_{k:04d}.vtu'
                write_thermal_vtu(
                    path, nodes, elements, record['u_nodal'], state,
                    strain=np.asarray(record['strain'], dtype=float),
                    length_unit=manifest['length_unit'],
                    mm_per_pixel=manifest['mm_per_pixel'],
                    scale_confirmed=manifest['scale_confirmed'])
                datasets.append((state['time_s'], path))

            _verify_source_rows(th_rows)
            if datasets and cfg['output']['export_pvd']:
                pvd = write_thermal_pvd(
                    output/(cfg['output']['series_name']+'_coupled.pvd'), datasets)
                manifest['coupled_pvd'] = str(pvd.resolve())
            else:
                manifest['coupled_pvd'] = None
            # NumPy writes the contiguous memmaps into the ZIP by chunks;
            # do not stack or copy them into full in-memory histories here.
            np.savez_compressed(pending, **buffers)
        pending.replace(output/'thermal_fields.npz')
    finally:
        pending.unlink(missing_ok=True)
        dic_frame.cache_clear()
        thermal_image.cache_clear()
    manifest['thermal_npz'] = str((output/'thermal_fields.npz').resolve())
    manifest['thermal_provenance'] = provenance
    manifest['coupled_vtu'] = [str(path.resolve()) for _, path in datasets]


def run_worker(run):
    """Execute D2IC, verify frozen sources, and publish only a complete run."""
    from d2ic.pipelines.sequence_platehole import run_sequence_from_config

    run = Path(run).resolve()
    manifest_path = run/'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    import os
    write_status(run, 'running', pid=os.getpid())
    try:
        _verify_source_rows([manifest['visible_reference'], *manifest['visible_images']])
        run_sequence_from_config(run/'dic_config.toml', output_prefix='dic',
                                 collection_dir=run/'results')
        _verify_source_rows([manifest['visible_reference'], *manifest['visible_images']])
        from d2ic.io.result_store import open_result_store
        store_path = run/'results'/'dic_store'
        if not store_path.is_dir():
            raise RuntimeError('D2IC n’a pas produit le magasin de résultats nécessaire à la reprise')
        store = open_result_store(store_path)
        paths = [str(Path(p).resolve()) for p in store.metadata['def_paths']]
        expected = [row['path'] for row in manifest['visible_images']]
        if paths != expected or store.frame_count != len(expected):
            raise RuntimeError('Images VIS réellement calculées différentes du manifeste figé')
        mesh = store.read_mesh()
        manifest['nodes'] = int(mesh['nodes_xy'].shape[0])
        manifest['elements'] = int(mesh['elements'].shape[0])
        manifest['frames'] = store.frame_count
        manifest['dic_store'] = str(store_path.resolve())
        _annotate_result_store(run, manifest)
        _rebuild_pvd(run, manifest)
        if manifest['mode'] == 'dic_thermal':
            _fuse_thermal(run, manifest)
        temporary_manifest = manifest_path.with_suffix('.tmp')
        temporary_manifest.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
        temporary_manifest.replace(manifest_path)
        write_status(run, 'completed', dic_store=str(store_path.resolve()))
    except BaseException as error:
        write_status(run, 'failed', error=str(error), traceback=traceback.format_exc())
        raise


if __name__ == '__main__':
    run_worker(sys.argv[1])
