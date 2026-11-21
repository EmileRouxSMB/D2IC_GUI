"""Translate a GUI study into one immutable sequential D2IC run."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from importlib.metadata import PackageNotFoundError, version
import json
import os
from pathlib import Path
import re
import signal
import shutil
import sys
import traceback
import subprocess
import numpy as np

from .imaging import inventory, thermal_inventory, read_image, read_mask, _metadata_time
from .project import dump_toml, load_project, resolve_path


def _time_of(path, source, frame_regex, fps):
    if source == 'metadata':
        return _metadata_time(path)
    match = re.search(frame_regex, Path(path).name)
    if not match or fps <= 0:
        raise ValueError(f'Temps VIS inexploitable pour {path}')
    return int(match.group(1)) / fps


def _snapshot_images(folder, settings):
    paths, time = settings['paths'], settings['time']
    img_dir = resolve_path(folder, paths['visible_dir'])
    excluded = set(paths.get('excluded_images', []))
    available = {p.name for p in img_dir.glob(paths['visible_pattern']) if p.is_file()}
    unknown = excluded - available
    if unknown:
        raise ValueError('Images VIS désactivées absentes de la série : ' + ', '.join(sorted(unknown)))
    ref_name = Path(paths['reference_image']).name
    if not (available - excluded - {ref_name}):
        raise ValueError('Aucune image VIS déformée active pour le calcul')
    rows = inventory(folder, paths['visible_dir'], paths['visible_pattern'],
                     time['visible_source'], time['visible_frame_regex'], time['visible_fps'],
                     reference=paths['reference_image'], visible=True, exclude_names=excluded)
    ref = Path(paths['reference_image'])
    ref = (ref if ref.is_absolute() else img_dir / ref).resolve()
    if ref.parent != img_dir:
        raise ValueError('La référence VIS doit être dans paths.visible_dir pour D2IC')
    ref_image = read_image(ref, visible=True)
    if list(ref_image.shape) != rows['images'][0]['shape']:
        raise ValueError('Dimensions de la référence VIS différentes de la séquence')
    stat = ref.stat()
    ref_row = {'path': str(ref), 'shape': list(ref_image.shape),
               'time_s': _time_of(ref, time['visible_source'], time['visible_frame_regex'], time['visible_fps']),
               'time_source': time['visible_source'], 'size': stat.st_size, 'mtime_ns': stat.st_mtime_ns}
    deformed = rows['images']
    if not deformed:
        raise ValueError('Aucune image VIS déformée active pour le calcul')
    if not all(row['time_s'] > ref_row['time_s'] for row in deformed):
        raise ValueError('Les images déformées doivent suivre le temps de référence VIS')
    return ref_row, deformed, rows['warnings']


def _package_version(name):
    try:
        return version(name)
    except PackageNotFoundError:
        return 'source locale non installée'


def _allocate_run_dir(out_root, created_at):
    """Create a daily incremental run directory, safe against a concurrent creator."""
    out_root = Path(out_root)
    out_root.mkdir(parents=True, exist_ok=True)
    prefix = created_at.strftime('%y-%m-%d')
    expression = re.compile(rf'^{re.escape(prefix)}-(\d+)$')
    used = [int(match.group(1)) for path in out_root.iterdir()
            if (match := expression.fullmatch(path.name))]
    number = max(used, default=0) + 1
    while True:
        run = out_root / f'{prefix}-{number:03d}'
        try:
            run.mkdir(exist_ok=False)
            return run
        except FileExistsError:
            number += 1


def prepare_run(folder, *, run=None, settings=None):
    """Freeze settings, mask and absolute VIS source manifest before launch."""
    folder = Path(folder).expanduser().resolve()
    settings = load_project(folder) if settings is None else settings
    ref, deformed, warnings = _snapshot_images(folder, settings)
    mask = resolve_path(folder, settings['roi']['final_mask'])
    if not mask.is_file():
        raise ValueError(f'Masque final absent : {mask} ; préparer la ROI')
    if not np.any(read_mask(mask)):
        raise ValueError('Le masque final est vide ; corriger la ROI')
    thermal_rows = None
    calibration_info = None
    if settings['project']['mode'] == 'dic_thermal':
        if not settings['registration']['approved']:
            raise ValueError('Correspondance VIS–TH non approuvée')
        registration = resolve_path(folder, settings['registration']['file'])
        if not registration.is_file():
            raise ValueError(f'Calibration absente : {registration}')
        approval_path = registration.parent/'approval.json'
        if not approval_path.is_file():
            raise ValueError('Approbation liée à la calibration absente ; réapprouver')
        approval = json.loads(approval_path.read_text())
        digest = hashlib.sha256(registration.read_bytes()).hexdigest()
        if approval.get('sha256') != digest:
            raise ValueError('Calibration modifiée après approbation ; réapprouver')
        from DICTHFusion.registration import load_registration
        calibration_info, _ = load_registration(registration)
        th = settings['thermal']
        thermal_rows = thermal_inventory(folder, th['image_dir'], th['image_pattern'],
                                         th['time_source'], th['frame_regex'], th['thermal_fps'],
                                         th.get('excluded_images', []))['images']
        if calibration_info['visible_shape_hw'] != ref['shape'] or calibration_info['thermal_shape_hw'] != thermal_rows[0]['shape']:
            raise ValueError('Dimensions VIS/TH différentes de celles de la calibration ; réajuster')
    # Freeze the exact active sequence; the D2IC core reads these paths directly.
    img_dir = resolve_path(folder, settings['paths']['visible_dir'])
    sampled = [Path(row['path']) for row in deformed]
    sampled = sampled[::settings['dic']['image_stride']]
    expected_by_path = {Path(row['path']): row for row in deformed}
    times = [expected_by_path[p]['time_s'] for p in sampled]
    if times != sorted(times) or len(times) != len(set(times)):
        raise ValueError('Le tri D2IC des images diffère de leur ordre temporel ; renommer les fichiers')
    if not sampled:
        raise ValueError('Aucune image VIS déformée retenue après le pas d’échantillonnage')
    created_at = datetime.now(timezone.utc)
    out_root = resolve_path(folder, settings['paths']['output_dir'])
    run = _allocate_run_dir(out_root, created_at) if run is None else Path(run)
    run_id = run.name
    (run/'results').mkdir()
    shutil.copy2(mask, run/'mask_final.tif')
    if calibration_info is not None:
        shutil.copy2(registration, run/'visible_thermal.json')
    (run/'config.toml').write_text(dump_toml(settings), encoding='utf-8')
    dic = {
        'paths': {'img_dir': str(img_dir), 'ref_image_name': Path(ref['path']).name,
                  'mask_path': str((run/'mask_final.tif').resolve()),
                  'image_pattern': settings['paths']['visible_pattern'],
                  'image_stride': 1, 'image_paths': [str(p) for p in sampled],
                  'out_dir': str((run/'results').resolve())},
        'mesh': settings['mesh'],
        'dic': {key: settings['dic'][key] for key in ('max_iters','tol','reg_strength','regularization',
               'strain_gauge_length','interpolation','image_binning','roi_erosion_px')},
        'output': {'export_png': settings['output']['export_png'],
                   'plot_include_discrepancy': settings['output']['compute_residual_map'],
                   'export_vtu': settings['output']['export_vtu'], 'export_vtk_images': False,
                   'save_npz': True, 'export_legacy_npz': False, 'keep_results': False, 'save_mesh': True},
        'runtime': settings['runtime'],
    }
    (run/'dic_config.toml').write_text(dump_raw_toml(dic), encoding='utf-8')
    manifest = {'manifest_schema_version': 1, 'run_id': run_id,
                'created_utc': created_at.isoformat(),
                'project_folder': str(folder), 'mode': settings['project']['mode'],
                'visible_reference': ref, 'visible_images': [expected_by_path[p] for p in sampled],
                'warnings': warnings, 'mask_final': str((run/'mask_final.tif').resolve()),
                'mask_sha256': hashlib.sha256((run/'mask_final.tif').read_bytes()).hexdigest(),
                'software_versions': {name: _package_version(name) for name in ('D2IC', 'DICTHFusion', 'jax', 'numpy')},
                'length_unit': settings['output']['paraview_length_unit'],
                'mm_per_pixel': settings['scale']['mm_per_pixel'],
                'scale_confirmed': settings['scale']['confirmed'],
                'temperature_unit': settings.get('thermal', {}).get('unit')}
    if thermal_rows is not None:
        manifest['thermal_images'] = thermal_rows
        manifest['calibration_sha256'] = digest
        manifest['calibration_snapshot'] = str((run/'visible_thermal.json').resolve())
    (run/'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    write_status(run, 'pending')
    return run




def write_preparation(run, report):
    """Publish a preparation report atomically while the job list is polled."""
    path = Path(run)/'preparation.json'
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(path)


def prepare_job(folder):
    """Create a visible job, freeze valid inputs and retain all diagnostics.

    A blocked job is a preparation report, never an executable run. Correct
    the study and prepare a new job to obtain a new immutable snapshot.
    """
    from .readiness import evaluate_readiness

    folder = Path(folder).resolve()
    settings = load_project(folder)
    run = _allocate_run_dir(resolve_path(folder, settings['paths']['output_dir']),
                            datetime.now(timezone.utc))
    (run/'config.toml').write_text(dump_toml(settings), encoding='utf-8')
    write_status(run, 'preparing')
    try:
        report = evaluate_readiness(folder, settings, check_active_run=False)
        if report['ready']:
            preview = json.loads((folder/'roi'/'mesh_preview.json').read_text(encoding='utf-8'))
            prepare_run(folder, run=run, settings=settings)
            frozen = json.loads((run/'manifest.json').read_text(encoding='utf-8'))
            if frozen['mask_sha256'] != preview['mask_sha256']:
                raise ValueError('Masque modifié pendant la préparation ; préparer un nouveau job')
    except Exception as error:
        # Full pixel decoding and snapshot creation can fail after the quick
        # checks. Keep that failure on the same row rather than losing the job.
        report = {'ready': False, 'required': [
            {'view': 'Job Manager', 'message': str(error)}], 'optional': []}
    write_preparation(run, report)
    write_status(run, 'pending' if report['ready'] else 'blocked')
    return run


def verify_prepared_run(run):
    """Reject a frozen job whose external sources or copied assets changed."""
    run = Path(run)
    manifest = json.loads((run/'manifest.json').read_text(encoding='utf-8'))
    for row in [manifest['visible_reference'], *manifest['visible_images'],
                *manifest.get('thermal_images', [])]:
        path = Path(row['path'])
        if not path.is_file():
            raise ValueError(f"Image source disparue : {path} ; préparer un nouveau job")
        stat = path.stat()
        if stat.st_size != row['size'] or stat.st_mtime_ns != row['mtime_ns']:
            raise ValueError(f"Image source modifiée : {path} ; préparer un nouveau job")
    if hashlib.sha256((run/'mask_final.tif').read_bytes()).hexdigest() != manifest['mask_sha256']:
        raise ValueError('Masque figé modifié ; préparer un nouveau job')
    if manifest.get('calibration_sha256'):
        digest = hashlib.sha256((run/'visible_thermal.json').read_bytes()).hexdigest()
        if digest != manifest['calibration_sha256']:
            raise ValueError('Calibration figée modifiée ; préparer un nouveau job')


def dump_raw_toml(data):
    import tomli_w
    return tomli_w.dumps(data)


def write_status(run, state, **details):
    path = Path(run)/'status.json'
    data = {'state': state, 'updated_utc': datetime.now(timezone.utc).isoformat(), **details}
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(data, indent=2), encoding='utf-8')
    temp.replace(path)


def start_run(run, *, resume=False):
    """Launch the JAX pipeline in a separate local process."""
    run = Path(run).resolve()
    log = (run/'run.log').open('a' if resume else 'w', encoding='utf-8')
    process_options = {'stdout': log, 'stderr': subprocess.STDOUT}
    if os.name == 'nt':
        process_options['creationflags'] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        process_options['start_new_session'] = True
    process = subprocess.Popen([sys.executable, '-m', 'D2IC_GUI.worker', str(run)],
                               **process_options)
    log.close()
    write_status(run, 'running', pid=process.pid)
    return process.pid


def worker_alive(pid):
    """Return whether a worker PID still runs (a zombie cannot be resumed)."""
    if not isinstance(pid, int) or pid <= 0:
        return False
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
        open_process = kernel32.OpenProcess
        open_process.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        open_process.restype = wintypes.HANDLE
        get_exit_code = kernel32.GetExitCodeProcess
        get_exit_code.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
        get_exit_code.restype = wintypes.BOOL
        close_handle = kernel32.CloseHandle
        close_handle.argtypes = (wintypes.HANDLE,)
        close_handle.restype = wintypes.BOOL
        handle = open_process(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        try:
            exit_code = wintypes.DWORD()
            return bool(get_exit_code(handle, ctypes.byref(exit_code)) and exit_code.value == 259)
        finally:
            close_handle(handle)
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    # Reap a finished child even on systems without Linux /proc (e.g. macOS).
    try:
        if os.waitpid(pid, os.WNOHANG)[0] == pid:
            return False
    except ChildProcessError:
        pass  # A worker from a previous server instance is not our child.
    try:
        state = Path(f'/proc/{pid}/stat').read_text().split()[2]
    except OSError:
        return True
    return state != 'Z'


def stop_worker(pid):
    """Stop a worker and its child processes using the native OS mechanism."""
    if not isinstance(pid, int) or pid <= 0:
        return False
    if os.name == 'nt':
        result = subprocess.run(['taskkill', '/PID', str(pid), '/T', '/F'],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                check=False)
        return result.returncode == 0
    try:
        os.killpg(pid, signal.SIGTERM)
        return True
    except ProcessLookupError:
        return False


def inspect_run(run, *, details=True):
    """Read persisted state and detect a worker lost across server restarts."""
    run = Path(run)
    status = json.loads((run/'status.json').read_text())
    if status['state'] == 'running' and not worker_alive(status.get('pid')):
        write_status(run, 'failed', error='Processus interrompu avant la fin du run')
        status = json.loads((run/'status.json').read_text())
    progress_path = run/'results'/'dic_store'/'progress.json'
    if progress_path.is_file():
        progress = json.loads(progress_path.read_text(encoding='utf-8'))
        status['completed_frames'] = int(progress.get('completed_frames') or 0)
        status['total_frames'] = int(progress.get('total_frames') or 0)
        if status['total_frames']:
            status['progress'] = status['completed_frames'] / status['total_frames']
    preparation = run/'preparation.json'
    if preparation.is_file():
        status['preparation'] = json.loads(preparation.read_text(encoding='utf-8'))
    status['can_start'] = (status['state'] == 'pending'
                           and status.get('preparation', {}).get('ready', False)
                           and (run/'manifest.json').is_file())
    status['run_id'] = run.name
    if details:
        status['log_tail'] = (run/'run.log').read_text(encoding='utf-8')[-8000:] if (run/'run.log').exists() else ''
    if details and (run/'manifest.json').is_file():
        status['manifest'] = json.loads((run/'manifest.json').read_text())
    return status
