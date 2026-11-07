"""Loopback-only HTTP application for DIC study preparation and inspection."""

from __future__ import annotations

import base64
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
from functools import lru_cache

import cv2
import numpy as np
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from .dic_run import _snapshot_images, inspect_run, prepare_run, start_run, stop_worker, worker_alive
from .imaging import (discover_visible_series, image_shape, inventory, mask_from_shapes,
                      morphology, read_image, read_mask, save_mask, thermal_inventory)
from .project import copy_project, create_project, load_project, relink_sources, resolve_path, save_project
from .schema import defaults, describe_fields, validate
from .thermal import align_thermal_times, thermal_brackets
from d2ic.io.result_store import open_result_store

STATIC = Path(__file__).parent/'static'


@lru_cache(maxsize=12)
def _preview_png(path, mtime_ns, size, visible, full):
    """Cache display PNGs by source identity; never cache calculation inputs."""
    array = read_image(Path(path), visible=visible).astype(np.float32)
    finite = np.isfinite(array)
    if not finite.any():
        raise ValueError(f'Image sans valeur finie : {path}')
    # A deterministic spatial sample keeps display contrast cheap on large frames.
    stride = max(1, int(np.sqrt(array.size / 250000)))
    sample = array[::stride, ::stride]
    sample = sample[np.isfinite(sample)]
    low, high = np.percentile(sample, [1, 99])
    gray = np.clip((array-low)/max(high-low, 1)*255, 0, 255).astype(np.uint8)
    if not full and max(gray.shape) > 1600:
        factor = 1600/max(gray.shape)
        gray = cv2.resize(gray, None, fx=factor, fy=factor, interpolation=cv2.INTER_AREA)
    ok, encoded = cv2.imencode('.png', gray)
    if not ok:
        raise ValueError('Impossible de produire un aperçu PNG')
    return encoded.tobytes()


def create_app(initial_folder=None):
    """Create the local FastAPI app, optionally opening an existing study."""
    app = FastAPI(title='D2IC_GUI')
    app.state.folder = Path(initial_folder).expanduser().resolve() if initial_folder else None
    app.mount('/static', StaticFiles(directory=STATIC), name='static')

    def current():
        folder = app.state.folder
        if folder is None:
            raise HTTPException(400, 'Ouvrir ou créer une étude avant cette action')
        return folder, load_project(folder)

    def shape_preview_layers(body, folder):
        """Build native-resolution ROI and photometry layers for draft shapes."""
        reference = body.get('reference_image')
        if not reference or Path(reference).name != reference:
            raise ValueError('Choisir une image de référence VIS')
        visible_dir = body.get('visible_dir')
        if not visible_dir:
            raise ValueError('Choisir le dossier des images VIS')
        image_path = resolve_path(folder, visible_dir) / reference
        shape_hw = image_shape(image_path, visible=True)
        mask = mask_from_shapes(body.get('shapes', []), shape_hw)
        roi_layer = np.zeros((*shape_hw, 4), dtype=np.uint8)
        roi_layer[mask] = (73, 155, 92, 88)
        contours, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_LIST,
                                       cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(roi_layer, contours, -1, (48, 140, 38, 210), 1, cv2.LINE_8)
        photo_layer = None
        correlation_pixels = 0
        photo_error = None
        try:
            from d2ic.io.app_utils import erode_correlation_roi
            from d2ic.io.binning import bin_mask
            from d2ic.mesh.generation import _remove_small_components

            erosion_px = float(body.get('roi_erosion_px', 0.0))

            def integer_option(key, default):
                value = body.get(key, default)
                if isinstance(value, bool) or not isinstance(value, (int, float, np.integer, np.floating)):
                    raise ValueError(f'{key} doit être un entier')
                numeric = float(value)
                if not np.isfinite(numeric) or not numeric.is_integer():
                    raise ValueError(f'{key} doit être un entier')
                return int(numeric)

            binning = integer_option('image_binning', 1)
            min_area = integer_option('min_island_area_px', 64)
            if not np.isfinite(erosion_px) or erosion_px < 0:
                raise ValueError('Le rayon d’érosion photométrique doit être positif ou nul')
            if binning < 1 or min_area < 0:
                raise ValueError('Binning et aire minimale d’îlot invalides')
            if body.get('remove_islands', True):
                mask = _remove_small_components(mask, min_area)
            h, w = shape_hw[0] // binning, shape_hw[1] // binning
            correlation = bin_mask(mask, binning)[:h, :w]
            correlation = erode_correlation_roi(correlation, erosion_px,
                                                image_binning=binning)
            correlation_pixels = int(np.asarray(correlation, dtype=bool).sum())
            native = np.zeros(shape_hw, dtype=bool)
            native[:h * binning, :w * binning] = np.repeat(
                np.repeat(correlation, binning, axis=0), binning, axis=1)
            photo_layer = np.zeros((*shape_hw, 4), dtype=np.uint8)
            photo_layer[native] = (210, 140, 35, 105)
            edges, _ = cv2.findContours(native.astype(np.uint8), cv2.RETR_LIST,
                                        cv2.CHAIN_APPROX_SIMPLE)
            cv2.drawContours(photo_layer, edges, -1, (210, 110, 20, 230), 1,
                             cv2.LINE_8)
        except (ValueError, TypeError, ImportError) as error:
            photo_error = str(error)

        def data_url(layer):
            if layer is None:
                return None
            ok, encoded = cv2.imencode('.png', layer)
            if not ok:
                raise ValueError('Impossible de produire le calque ROI')
            return 'data:image/png;base64,' + base64.b64encode(encoded).decode('ascii')

        return {'roi_data_url': data_url(roi_layer),
                'photometric_data_url': data_url(photo_layer),
                'area_px': int(mask.sum()),
                'correlation_pixels': correlation_pixels,
                'photometric_error': photo_error}

    def guarded(fn):
        try:
            return fn()
        except HTTPException:
            raise
        except (ValueError, FileNotFoundError, FileExistsError, KeyError) as error:
            raise HTTPException(400, str(error)) from error

    @app.get('/')
    def index():
        return FileResponse(STATIC/'index.html')

    @app.get('/api/schema')
    def schema():
        return {'version': 1, 'fields': describe_fields()}

    @app.get('/api/filesystem')
    def filesystem(path: str = '', kind: str = 'any', query: str = '',
                   offset: int = 0, limit: int = 200):
        """List local paths for the study picker without reading file data."""
        def act():
            suffixes = {
                'any': None,
                'image': {'.tif', '.tiff', '.png', '.jpg', '.jpeg', '.bmp'},
                'mask': {'.tif', '.tiff', '.png'},
                'registration': {'.json'},
                'study': {'config.toml'},
                'directory': set(),
            }
            if kind not in suffixes or offset < 0 or not 1 <= limit <= 200:
                raise ValueError('Paramètres de navigation invalides')
            base = app.state.folder or Path.cwd()
            target = Path(path).expanduser() if path else base
            if not target.is_absolute():
                target = base / target
            target = target.resolve()
            if target.is_file():
                target = target.parent
            while not target.exists() and target != target.parent:
                target = target.parent
            if not target.is_dir():
                raise ValueError(f'Dossier introuvable : {target}')
            rows = []
            try:
                with os.scandir(target) as scanner:
                    for entry in scanner:
                        try:
                            directory = entry.is_dir()
                            file = entry.is_file()
                        except OSError:
                            continue
                        if not directory and not file:
                            continue
                        if query.casefold() not in entry.name.casefold():
                            continue
                        if file and suffixes[kind] is not None:
                            if kind == 'study':
                                if entry.name != 'config.toml':
                                    continue
                            elif Path(entry.name).suffix.lower() not in suffixes[kind]:
                                continue
                        rows.append({'name': entry.name, 'path': str(Path(entry.path).resolve()),
                                     'is_dir': directory,
                                     'is_study': directory and (Path(entry.path)/'config.toml').is_file(),
                                     'is_study_config': file and entry.name == 'config.toml'})
            except OSError as error:
                raise ValueError(f'Dossier illisible : {target} ({error.strerror})') from error
            rows.sort(key=lambda row: (not row['is_dir'], row['name'].casefold()))
            return {'path': str(target), 'parent': str(target.parent) if target.parent != target else None,
                    'is_study': (target/'config.toml').is_file(),
                    'entries': rows[offset:offset+limit], 'total': len(rows),
                    'offset': offset, 'has_more': offset+limit < len(rows)}
        return guarded(act)

    @app.get('/api/project')
    def get_project():
        if app.state.folder is None:
            return {'name': 'Nouvelle étude', 'folder': None, 'config': defaults()}
        folder, config = current()
        return {'name': config['project']['name'], 'folder': str(folder),
                'config': config, 'missing_sources': __import__('D2IC_GUI.project', fromlist=['missing_sources']).missing_sources(folder, config)}

    @app.post('/api/project/new')
    def new_project(body: dict):
        def act():
            folder = Path(body['folder']).expanduser().resolve()
            config = create_project(folder, body.get('name','Nouvelle étude'), body.get('mode','dic'))
            app.state.folder = folder
            return {'folder': str(folder), 'config': config}
        return guarded(act)

    @app.post('/api/project/open')
    def open_project(body: dict):
        def act():
            folder = Path(body['folder']).expanduser().resolve()
            if folder.name == 'config.toml' and folder.is_file():
                folder = folder.parent
            config = load_project(folder)
            app.state.folder = folder
            return {'folder': str(folder), 'config': config}
        return guarded(act)

    @app.post('/api/project/copy')
    def duplicate_project(body: dict):
        def act():
            folder, _ = current()
            target = Path(body['folder']).expanduser().resolve()
            config = copy_project(folder, target, body.get('name'), settings=body.get('config'))
            app.state.folder = target
            return {'folder': str(target), 'config': config}
        return guarded(act)

    @app.post('/api/project/relink')
    def relink_project(body: dict):
        def act():
            folder, _ = current()
            config, checked = relink_sources(folder,
                visible_dir=body.get('visible_dir'), thermal_dir=body.get('thermal_dir'))
            return {'config': config, 'checked_sources': checked}
        return guarded(act)

    @app.put('/api/project/config')
    def put_config(body: dict):
        def act():
            folder, old = current()
            config = validate(body)
            # A change of registration path or approval state requires a fresh
            # explicit approval; the sidecar digest is verified at fusion time.
            save_project(folder, config)
            return {'config': config, 'saved': True}
        return guarded(act)

    def source_inventory(thermal=False):
        folder, cfg = current()
        if thermal:
            if cfg['project']['mode'] != 'dic_thermal':
                raise ValueError('Parcours thermique inactif')
            th = cfg['thermal']
            return thermal_inventory(folder, th['image_dir'], th['image_pattern'], th['time_source'],
                                     th['frame_regex'], th['thermal_fps'],
                                     th.get('excluded_images', []), inspect_pixels=False)
        path, time = cfg['paths'], cfg['time']
        rows = inventory(folder, path['visible_dir'], path['visible_pattern'],
                         time['visible_source'], time['visible_frame_regex'], time['visible_fps'],
                         visible=True, inspect_pixels=False)
        return rows

    @app.get('/api/visible/series')
    def visible_series(directory: str = ''):
        def act():
            if not directory:
                return {'directory': '', 'series': [], 'image_count': 0}
            base = app.state.folder or Path.cwd()
            target = Path(directory).expanduser()
            if not target.is_absolute():
                target = base / target
            return discover_visible_series(target)
        return guarded(act)

    @app.get('/api/visible')
    def visible():
        return guarded(lambda: source_inventory(False))

    @app.get('/api/visible/inspect')
    def inspect_visible(directory: str, pattern: str, source: str = 'filename',
                        frame_regex: str = r'(\d+)', fps: float = 10.0):
        """Preview the current VIS form without writing config.toml."""
        def act():
            if not directory or not pattern or Path(pattern).name != pattern:
                raise ValueError('Choisir un dossier et un motif VIS valide')
            base = app.state.folder or Path.cwd()
            image_dir = resolve_path(base, directory)
            if not image_dir.is_dir():
                raise ValueError(f'Dossier VIS introuvable : {image_dir}')
            try:
                result = inventory(base, directory, pattern, source, frame_regex, fps,
                                   visible=True, inspect_pixels=False)
            except (ValueError, RuntimeError) as error:
                allowed = {'.tif', '.tiff', '.bmp', '.png', '.jpg', '.jpeg'}
                rows = []
                for path in sorted(image_dir.glob(pattern)):
                    if not path.is_file() or path.parent != image_dir or path.suffix.lower() not in allowed:
                        continue
                    try:
                        shape = list(image_shape(path, visible=True))
                    except (ValueError, RuntimeError, OSError):
                        continue
                    stat = path.stat()
                    rows.append({'path': str(path.resolve()), 'shape': shape,
                                 'time_s': None, 'frame': None,
                                 'size': stat.st_size, 'mtime_ns': stat.st_mtime_ns})
                if not rows:
                    raise ValueError(f'Aucune image VIS lisible pour {image_dir / pattern}') from error
                result = {'images': rows, 'warnings': [
                    {'kind': 'preview_only', 'message': str(error)}
                ]}
            result['directory'] = str(image_dir)
            return result
        return guarded(act)

    @app.get('/api/thermal/series')
    def thermal_series(directory: str = ''):
        def act():
            if not directory:
                return {'directory': '', 'series': [], 'image_count': 0}
            base = app.state.folder or Path.cwd()
            target = Path(directory).expanduser()
            if not target.is_absolute():
                target = base / target
            return discover_visible_series(target, allowed_suffixes={'.tif', '.tiff'})
        return guarded(act)

    @app.get('/api/thermal')
    def thermal():
        return guarded(lambda: source_inventory(True))

    @app.get('/api/thermal/inspect')
    def inspect_thermal(directory: str, pattern: str, source: str = 'filename',
                        frame_regex: str = r'(\d+)', fps: float = 50.0):
        """Preview the current TH form without writing config.toml."""
        def act():
            if not directory or not pattern or Path(pattern).name != pattern:
                raise ValueError('Choisir un dossier et un motif TH valide')
            base = app.state.folder or Path.cwd()
            image_dir = resolve_path(base, directory)
            if not image_dir.is_dir():
                raise ValueError(f'Dossier TH introuvable : {image_dir}')
            matches = [path for path in image_dir.glob(pattern)
                       if path.is_file() and path.parent == image_dir
                       and path.resolve().parent == image_dir
                       and path.suffix.lower() in {'.tif', '.tiff'}]
            if not matches:
                raise ValueError(f'Aucun TIFF TH pour {image_dir / pattern}')
            try:
                result = inventory(base, directory, pattern, source, frame_regex, fps,
                                   inspect_pixels=False, allowed_suffixes={'.tif', '.tiff'})
                if any(Path(row['path']).parent != image_dir for row in result['images']):
                    raise ValueError('La série TH doit contenir des TIFF directement dans le dossier choisi')
            except (ValueError, RuntimeError) as error:
                rows = []
                for path in sorted(matches, key=lambda item: item.name.casefold()):
                    try:
                        shape = list(image_shape(path, visible=False))
                    except (ValueError, RuntimeError, OSError):
                        continue
                    stat = path.stat()
                    rows.append({'path': str(path.resolve()), 'shape': shape,
                                 'time_s': None, 'frame': None,
                                 'size': stat.st_size, 'mtime_ns': stat.st_mtime_ns})
                if not rows:
                    raise ValueError(f'Aucun TIFF TH 2D lisible pour {image_dir / pattern}') from error
                result = {'images': rows, 'warnings': [
                    {'kind': 'preview_only', 'message': str(error)}
                ]}
            result['directory'] = str(image_dir)
            return result
        return guarded(act)

    @app.get('/api/image')
    def image(path: str = Query(...), full: bool = Query(False),
              visible_dir: str = Query(''), thermal_dir: str = Query('')):
        def act():
            requested = Path(path)
            if visible_dir and thermal_dir:
                raise ValueError('Choisir un seul dossier source pour l’aperçu')
            if visible_dir:
                base = app.state.folder or Path.cwd()
                source = resolve_path(base, visible_dir)
                requested = (requested if requested.is_absolute() else source/requested).resolve()
                if requested.parent != source or requested.suffix.lower() not in {
                    '.tif', '.tiff', '.bmp', '.png', '.jpg', '.jpeg'
                }:
                    raise ValueError('Aperçu VIS limité au dossier choisi')
                is_visible = True
            elif thermal_dir:
                base = app.state.folder or Path.cwd()
                source = resolve_path(base, thermal_dir)
                requested = (requested if requested.is_absolute() else source/requested).resolve()
                if (requested.parent != source or requested.suffix.lower() not in {'.tif', '.tiff'}):
                    raise ValueError('Aperçu TH limité aux TIFF du dossier choisi')
                is_visible = False
            else:
                folder, cfg = current()
                if not requested.is_absolute():
                    requested = resolve_path(folder, requested)
                    if not requested.is_file():
                        requested = resolve_path(folder, cfg['paths']['visible_dir']) / path
                requested = requested.resolve()
                roots = [folder, resolve_path(folder, cfg['paths']['visible_dir'])]
                if 'thermal' in cfg and cfg['thermal']['image_dir']:
                    roots.append(resolve_path(folder, cfg['thermal']['image_dir']))
                if not any(requested == root or root in requested.parents for root in roots):
                    raise ValueError('Aperçu limité aux fichiers de cette étude')
                is_visible = requested.parent == resolve_path(folder, cfg['paths']['visible_dir'])
            stat = requested.stat()
            png = _preview_png(str(requested), stat.st_mtime_ns, stat.st_size,
                               is_visible, full)
            return Response(png, media_type='image/png',
                            headers={'Cache-Control': 'private, no-cache'})
        return guarded(act)

    def roi_from_body(body, cfg, folder):
        path = resolve_path(folder, cfg['roi']['initial_mask'])
        existing = read_mask(path) if path.is_file() else None
        drawing = body.get('drawing_data_url')
        drawn = None
        if 'mask' in body:
            drawn = np.asarray(body['mask'], dtype=bool)
            if drawn.ndim != 2:
                raise ValueError('Le masque dessiné doit être une matrice 2D')
        if drawing and drawn is None:
            raw = base64.b64decode(drawing.split(',', 1)[-1])
            rgba = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
            if rgba is None:
                raise ValueError('Dessin ROI PNG illisible')
            drawn = rgba[:, :, 3] > 0 if rgba.ndim == 3 and rgba.shape[2] == 4 else rgba > 0
        ref = cfg['paths']['reference_image']
        if ref:
            ref_path = resolve_path(folder, cfg['paths']['visible_dir']) / ref
            shape = read_image(ref_path, visible=True).shape
        else:
            shape = existing.shape if existing is not None else None
        if shape is None:
            raise ValueError('Choisir la référence VIS avant de dessiner la ROI')
        if drawn is not None and drawn.shape != shape:
            raise ValueError(f'Dessin ROI {drawn.shape} différent de VIS {shape}; recharger la vue')
        if existing is not None and existing.shape != shape:
            raise ValueError('Masque initial de dimensions différentes de la VIS')
        if drawn is not None and not drawn.any():
            raise ValueError('Le dessin ROI est vide ; dessiner ou importer un masque')
        mask = drawn if drawn is not None else existing
        if mask is None:
            raise ValueError('Dessiner ou importer un masque initial')
        return mask

    @app.get('/api/roi/overlay-image')
    def roi_overlay_image(mask_path: str, visible_dir: str, reference_image: str):
        """Render the selected ROI over the current VIS reference before saving."""
        def act():
            base = app.state.folder or Path.cwd()
            mask_file = resolve_path(base, mask_path)
            if mask_file.suffix.lower() not in {'.tif', '.tiff', '.png'} or not mask_file.is_file():
                raise ValueError('Choisir un fichier ROI TIFF ou PNG lisible')
            if not reference_image or Path(reference_image).name != reference_image:
                raise ValueError('Choisir une image de référence VIS')
            visible_file = resolve_path(base, visible_dir) / reference_image
            visible = read_image(visible_file, visible=True).astype(np.float32)
            mask = read_mask(mask_file)
            if mask.shape != visible.shape:
                raise ValueError(f'Dimensions ROI {mask.shape} différentes de VIS {visible.shape}')
            if not mask.any():
                raise ValueError('Le fichier ROI est vide')
            finite = np.isfinite(visible)
            if not finite.any():
                raise ValueError('Image VIS sans valeur finie')
            low, high = np.percentile(visible[finite], [1, 99])
            gray = np.clip((visible - low) / max(high - low, 1) * 255, 0, 255).astype(np.uint8)
            rgb = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
            tint = np.zeros_like(rgb)
            tint[:] = (92, 158, 59)
            rgb[mask] = cv2.addWeighted(rgb, 0.65, tint, 0.35, 0)[mask]
            contours, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
            cv2.drawContours(rgb, contours, -1, (72, 160, 48), 1, cv2.LINE_AA)
            ok, encoded = cv2.imencode('.png', rgb)
            if not ok:
                raise ValueError('Impossible de produire l’aperçu ROI')
            return Response(encoded.tobytes(), media_type='image/png')
        return guarded(act)

    @app.post('/api/roi/shapes/preview')
    def roi_shapes_preview(body: dict):
        def act():
            folder, _ = current()
            return shape_preview_layers(body, folder)
        return guarded(act)

    @app.post('/api/roi/shapes/save')
    def roi_shapes_save(body: dict):
        """Write a new native VIS mask without changing project configuration."""
        def act():
            folder, _ = current()
            reference = body.get('reference_image')
            if not reference or Path(reference).name != reference:
                raise ValueError('Choisir une image de référence VIS')
            visible_dir = body.get('visible_dir')
            if not visible_dir:
                raise ValueError('Choisir le dossier des images VIS')
            shape_hw = image_shape(resolve_path(folder, visible_dir) / reference,
                                   visible=True)
            mask = mask_from_shapes(body.get('shapes', []), shape_hw)
            if not mask.any():
                raise ValueError('La ROI dessinée est vide ; ajouter une forme')
            roi_dir = folder / 'roi'
            roi_dir.mkdir(parents=True, exist_ok=True)
            index = 1
            while True:
                target = roi_dir / f'drawn_roi_{index:03d}.tif'
                try:
                    with target.open('xb'):
                        pass
                    break
                except FileExistsError:
                    pass
                index += 1
            try:
                save_mask(target, mask)
            except BaseException:
                target.unlink(missing_ok=True)
                raise
            return {'mask_path': str(target.resolve()),
                    'initial_mask_path': target.relative_to(folder).as_posix(),
                    'area_px': int(mask.sum())}
        return guarded(act)

    @app.get('/api/roi/layer-image')
    def roi_layer_image(mask_path: str, visible_dir: str, reference_image: str,
                        kind: str = 'geometry', roi_erosion_px: float = 0.0,
                        image_binning: int = 1, operation: str = 'none',
                        radius_px: int = 0, remove_islands: bool = True,
                        min_island_area_px: int = 64):
        """Transparent ROI layer aligned with the selected full-resolution VIS image."""
        def act():
            base = app.state.folder or Path.cwd()
            mask_file = resolve_path(base, mask_path)
            if mask_file.suffix.lower() not in {'.tif', '.tiff', '.png'} or not mask_file.is_file():
                raise ValueError('Choisir un fichier ROI TIFF ou PNG lisible')
            if not reference_image or Path(reference_image).name != reference_image:
                raise ValueError('Choisir une image de référence VIS')
            visible_file = resolve_path(base, visible_dir) / reference_image
            shape = image_shape(visible_file, visible=True)
            mask = read_mask(mask_file)
            if mask.shape != shape:
                raise ValueError(f'Dimensions ROI {mask.shape} différentes de VIS {shape}')
            if not mask.any():
                raise ValueError('Le fichier ROI est vide')
            if kind not in ('geometry', 'photometric'):
                raise ValueError('Type de calque ROI inconnu')
            mask, _ = morphology(mask, operation, radius_px)
            if kind == 'photometric':
                from d2ic.io.app_utils import erode_correlation_roi
                from d2ic.io.binning import bin_mask
                from d2ic.mesh.generation import _remove_small_components

                # Same working mask and original-pixel radius as the solver.
                if min_island_area_px < 0:
                    raise ValueError('L’aire minimale d’îlot doit être positive ou nulle')
                if remove_islands:
                    mask = _remove_small_components(mask, min_island_area_px)
                working_mask = bin_mask(mask, image_binning)
                h, w = shape[0] // image_binning, shape[1] // image_binning
                working_mask = working_mask[:h, :w]
                photo = erode_correlation_roi(working_mask,
                    roi_erosion_px, image_binning=image_binning)
                mask = np.zeros(shape, dtype=bool)
                mask[:h * image_binning, :w * image_binning] = np.repeat(
                    np.repeat(photo, image_binning, axis=0), image_binning, axis=1)
            layer = np.zeros((*shape, 4), dtype=np.uint8)
            layer[mask] = (210, 140, 35, 105) if kind == 'photometric' else (73, 155, 92, 88)
            contours, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_LIST,
                                           cv2.CHAIN_APPROX_SIMPLE)
            color = (210, 110, 20, 230) if kind == 'photometric' else (48, 140, 38, 210)
            cv2.drawContours(layer, contours, -1, color, 1,
                             cv2.LINE_8 if kind == 'photometric' else cv2.LINE_AA)
            ok, encoded = cv2.imencode('.png', layer)
            if not ok:
                raise ValueError('Impossible de produire le calque ROI')
            return Response(encoded.tobytes(), media_type='image/png',
                            headers={'Cache-Control': 'private, no-cache'})
        return guarded(act)

    @app.get('/api/roi/mask-image')
    def roi_mask_image(kind: str = 'initial'):
        def act():
            if kind not in ('initial', 'final'):
                raise ValueError('Type de masque ROI inconnu')
            folder, cfg = current()
            path = resolve_path(folder, cfg['roi'][f'{kind}_mask'])
            if not path.is_file():
                raise ValueError(f'Aucun masque {kind} à charger')
            mask = read_mask(path)
            rgba = np.zeros((*mask.shape, 4), dtype=np.uint8)
            rgba[mask] = (73, 155, 92, 115)
            ok, encoded = cv2.imencode('.png', rgba)
            if not ok:
                raise ValueError('Impossible de préparer le masque initial')
            return Response(encoded.tobytes(), media_type='image/png')
        return guarded(act)

    @app.post('/api/roi/preview')
    def roi_preview(body: dict):
        def act():
            folder, cfg = current()
            mask = roi_from_body(body, cfg, folder)
            result, metrics = morphology(mask, body.get('operation',cfg['roi']['operation']),
                                         body.get('radius_px',cfg['roi']['radius_px']))
            rgba = np.zeros((*result.shape, 4), dtype=np.uint8)
            rgba[result] = (73, 155, 92, 115)
            ok, encoded = cv2.imencode('.png', rgba)
            if not ok:
                raise ValueError('Impossible de produire l’aperçu du masque final')
            return {'message': 'Aperçu ROI calculé', 'area_px': metrics['area_final_px'],
                    'metrics': metrics,
                    'preview_data_url': 'data:image/png;base64,' + base64.b64encode(encoded).decode('ascii')}
        return guarded(act)

    @app.post('/api/roi/save')
    def roi_save(body: dict):
        def act():
            folder, cfg = current()
            mask = roi_from_body(body, cfg, folder)
            final, metrics = morphology(mask, body.get('operation',cfg['roi']['operation']),
                                        body.get('radius_px',cfg['roi']['radius_px']))
            for key, name, value in (('initial_mask', 'mask_initial.tif', mask),
                                     ('final_mask', 'mask_final.tif', final)):
                target = resolve_path(folder, cfg['roi'][key])
                if target != folder and folder not in target.parents:
                    # An imported mask is a source, not a file to overwrite.
                    cfg['roi'][key] = f'roi/{name}'
                    target = folder/'roi'/name
                save_mask(target, value)
            for stale in ('mesh_preview.png','mesh_preview.json','mesh_layer.png'):
                (folder/'roi'/stale).unlink(missing_ok=True)
            cfg['roi']['operation'] = body.get('operation',cfg['roi']['operation'])
            cfg['roi']['radius_px'] = body.get('radius_px',cfg['roi']['radius_px'])
            save_project(folder, cfg)
            return {'message': 'Masque initial et final enregistrés ; maillage à régénérer',
                    'metrics': metrics,
                    'initial_mask_path': cfg['roi']['initial_mask'],
                    'final_mask_path': cfg['roi']['final_mask'],
                    'mask_path': str(resolve_path(folder,cfg['roi']['final_mask']))}
        return guarded(act)

    @app.post('/api/mesh/preview')
    def mesh_preview():
        def act():
            from d2ic.mesh.generation import mask_to_mesh_gmsh
            folder,cfg=current()
            mask_path=resolve_path(folder,cfg['roi']['final_mask'])
            if not mask_path.is_file():
                raise ValueError('Masque final absent ; enregistrer la ROI avant le maillage')
            mask=read_mask(mask_path)
            mesh=mask_to_mesh_gmsh(mask,cfg['mesh']['element_size_px'],
                  binning=cfg['dic']['image_binning'],
                  remove_islands=cfg['mesh']['remove_islands'],
                  min_island_area_px=cfg['mesh']['min_island_area_px'],
                  numpy_output=True)
            nodes=np.asarray(mesh.nodes_xy)
            cells=np.asarray(mesh.elements)
            ref=resolve_path(folder,cfg['paths']['visible_dir'])/cfg['paths']['reference_image']
            base=read_image(ref, visible=True).astype(np.float32)
            lo,hi=np.percentile(base,[1,99]);gray=np.clip((base-lo)/(max(hi-lo,1))*255,0,255).astype(np.uint8)
            rgb=cv2.cvtColor(gray,cv2.COLOR_GRAY2BGR)
            layer=np.zeros((*gray.shape,4),dtype=np.uint8)
            for cell in cells:
                polygon=np.rint(nodes[cell]).astype(np.int32)
                cv2.polylines(rgb,[polygon],True,(42,176,255),1,cv2.LINE_AA)
                cv2.polylines(layer,[polygon],True,(42,176,255,255),1,cv2.LINE_AA)
            preview=folder/'roi'/'mesh_preview.png'
            preview.parent.mkdir(parents=True,exist_ok=True)
            if not cv2.imwrite(str(preview),rgb):
                raise ValueError('Écriture de l’aperçu maillage impossible')
            if not cv2.imwrite(str(folder/'roi'/'mesh_layer.png'),layer):
                raise ValueError('Écriture du calque maillage impossible')
            digest=hashlib.sha256(mask_path.read_bytes()).hexdigest()
            source_mask = resolve_path(folder, cfg['roi']['initial_mask'])
            meta={'mask_sha256':digest,
                  'source_mask_sha256': hashlib.sha256(source_mask.read_bytes()).hexdigest(),
                  'nodes':len(nodes),'elements':len(cells),
                  'element_size_px':cfg['mesh']['element_size_px'],
                  'image_binning':cfg['dic']['image_binning'],
                  'remove_islands':cfg['mesh']['remove_islands'],
                  'min_island_area_px':cfg['mesh']['min_island_area_px']}
            (folder/'roi'/'mesh_preview.json').write_text(json.dumps(meta,indent=2))
            return {**meta,'preview_url':'/api/mesh/preview-image',
                    'layer_url':'/api/mesh/layer-image'}
        return guarded(act)

    def validated_mesh_image(name):
        def act():
            folder,cfg=current()
            path=folder/'roi'/name
            meta_path=folder/'roi'/'mesh_preview.json'
            mask=resolve_path(folder,cfg['roi']['final_mask'])
            if not path.is_file() or not meta_path.is_file() or not mask.is_file():
                raise ValueError('Aperçu maillage absent ou périmé')
            meta=json.loads(meta_path.read_text())
            source_mask = resolve_path(folder, cfg['roi']['initial_mask'])
            expected={'mask_sha256':hashlib.sha256(mask.read_bytes()).hexdigest(),
                      'source_mask_sha256': hashlib.sha256(source_mask.read_bytes()).hexdigest() if source_mask.is_file() else None,
                      'element_size_px':cfg['mesh']['element_size_px'],
                      'image_binning':cfg['dic']['image_binning'],
                      'remove_islands':cfg['mesh']['remove_islands'],
                      'min_island_area_px':cfg['mesh']['min_island_area_px']}
            if any(meta.get(key)!=value for key,value in expected.items()):
                raise ValueError('Aperçu maillage périmé après modification du masque ou des paramètres')
            return FileResponse(path,media_type='image/png',
                                headers={'Cache-Control': 'private, no-cache'})
        return guarded(act)

    @app.get('/api/mesh/preview-image')
    def mesh_preview_image():
        return validated_mesh_image('mesh_preview.png')

    @app.get('/api/mesh/layer-image')
    def mesh_layer_image():
        return validated_mesh_image('mesh_layer.png')

    def fitted(body, save=False):
        folder, cfg = current()
        points = body['points']
        vis = np.asarray([pair['visible'] for pair in points], dtype=float)
        th = np.asarray([pair['thermal'] for pair in points], dtype=float)
        vis_dir = resolve_path(folder, cfg['paths']['visible_dir'])
        ref = (vis_dir/cfg['paths']['reference_image']).resolve()
        vis_shape = read_image(ref, visible=True).shape
        th_first = source_inventory(True)['images'][0]['path']
        th_shape = read_image(th_first).shape
        from DICTHFusion.registration import fit_registration, save_registration
        matrix, residuals = fit_registration(vis, th, vis_shape, th_shape, body.get('model','affine'))
        rms = float(np.sqrt(np.mean(np.square(residuals))))
        if save:
            path = resolve_path(folder, cfg['registration']['file'])
            path.parent.mkdir(parents=True, exist_ok=True)
            save_registration(path, matrix, body.get('model','affine'),
                              list(zip(vis.tolist(), th.tolist())), ref, th_first,
                              vis_shape, th_shape, residuals)
            cfg['registration']['approved'] = False
            save_project(folder, cfg)
        return {'H': np.asarray(matrix).tolist(), 'residuals': np.asarray(residuals).tolist(),
                'rms_px': rms, 'message': 'Correspondance ajustée ; validation manuelle requise'}

    @app.get('/api/registration')
    def registration_state():
        def act():
            folder, cfg = current()
            path = resolve_path(folder, cfg['registration']['file'])
            if not path.is_file():
                return {'points': [], 'approved': False}
            from DICTHFusion.registration import load_registration
            data, matrix = load_registration(path)
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            approval_path = path.parent/'approval.json'
            approved = False
            if cfg['registration']['approved'] and approval_path.is_file():
                approved = json.loads(approval_path.read_text()).get('sha256') == digest
            return {'points': [{'visible': pair['visible_xy'],
                                'thermal': pair['thermal_xy']}
                               for pair in data['points']],
                    'model': data['model'], 'H': np.asarray(matrix).tolist(),
                    'residuals': [pair['residual_thermal_px'] for pair in data['points']],
                    'rms_px': data['rms_thermal_px'], 'approved': approved}
        return guarded(act)

    @app.post('/api/registration/fit')
    def registration_fit(body: dict):
        return guarded(lambda: fitted(body, True))

    @app.post('/api/registration/approve')
    def registration_approve(body: dict):
        def act():
            folder, cfg = current()
            path = resolve_path(folder, cfg['registration']['file'])
            if not path.is_file():
                raise ValueError('Ajuster et inspecter la correspondance avant approbation')
            from DICTHFusion.registration import load_registration
            data, matrix = load_registration(path)
            if body.get('points'):
                supplied = [{'visible_xy': list(pair['visible']), 'thermal_xy': list(pair['thermal'])}
                            for pair in body['points']]
                stored = [{k: pair[k] for k in ('visible_xy','thermal_xy')} for pair in data['points']]
                if supplied != stored or body.get('model',data['model']) != data['model']:
                    raise ValueError('Les points ou le modèle ont changé ; réajuster avant validation')
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            approval = {'sha256': digest, 'visible_shape_hw': data['visible_shape_hw'],
                        'thermal_shape_hw': data['thermal_shape_hw']}
            (path.parent/'approval.json').write_text(json.dumps(approval,indent=2),encoding='utf-8')
            cfg['registration']['approved'] = True
            save_project(folder,cfg)
            return {'message': 'Correspondance approuvée pour ce fichier exact', 'sha256': digest}
        return guarded(act)

    @app.get('/api/synchronization')
    def synchronization():
        def act():
            folder, cfg = current()
            ref, vis, _ = _snapshot_images(folder, cfg)
            th = source_inventory(True)['images']
            vis_all = [ref,*vis]
            time_cfg = cfg['time']
            if time_cfg['visible_source'] == 'filename':
                expression = re.compile(time_cfg['visible_frame_regex'])
                for image in vis_all:
                    if image.get('frame') is None:
                        match = expression.search(Path(image['path']).name)
                        image['frame'] = int(match.group(1)) if match else None
            sync = cfg['synchronization']
            aligned = align_thermal_times([r['time_s'] for r in vis_all],
                      [r['time_s'] for r in th], method=sync['method'],
                      visible_frames=[r.get('frame') for r in vis_all],
                      thermal_frames=[r.get('frame') for r in th],
                      visible_event_frame=sync['visible_event_frame'],
                      thermal_event_frame=sync['thermal_event_frame'],
                      thermal_offset_s=sync['thermal_offset_s'])
            th_frames = None if th[0]['frame'] is None else [r['frame'] for r in th]
            brackets = thermal_brackets([r['time_s'] for r in vis_all], aligned, th_frames,
                                        thermal_fps=cfg['thermal']['thermal_fps'])
            # Keep acquisition numbers visible even when timestamps supply the time axis.
            # These display numbers do not change the synchronization calculation.
            def display_frame(image, frame_regex):
                if image is None:
                    return None
                if image.get('frame') is not None:
                    return image['frame']
                try:
                    match = re.search(frame_regex, Path(image['path']).name)
                    return int(match.group(1)) if match else None
                except (re.error, IndexError, TypeError, ValueError):
                    return None

            rows=[]
            for k,row in enumerate(vis_all):
                left,right = int(brackets['left'][k]), int(brackets['right'][k])
                rows.append({'visible_path':row['path'],'time_s':row['time_s'],
                             'visible_frame':display_frame(row, time_cfg['visible_frame_regex']),
                             'thermal_left':th[left]['path'] if left>=0 else None,
                             'thermal_right':th[right]['path'] if right>=0 else None,
                             'thermal_left_time_s':float(aligned[left]) if left>=0 else None,
                             'thermal_right_time_s':float(aligned[right]) if right>=0 else None,
                             'thermal_left_frame':display_frame(th[left], cfg['thermal']['frame_regex']) if left>=0 else None,
                             'thermal_right_frame':display_frame(th[right], cfg['thermal']['frame_regex']) if right>=0 else None,
                             'alpha':float(brackets['alpha'][k]) if left>=0 else None,
                             'valid':bool(brackets['valid'][k]), 'reason':str(brackets['reason'][k])})
            return {'images': rows, 'count':len(rows),
                    'visible_fps':cfg['time']['visible_fps'],
                    'thermal_fps':cfg['thermal']['thermal_fps']}
        return guarded(act)

    @app.post('/api/runs')
    def launch(body: dict = None):
        def act():
            folder,cfg = current()
            if body and 'config' in body and validate(body['config']) != cfg:
                raise ValueError('Enregistrer les modifications de configuration avant le calcul')
            running = [p for p in (resolve_path(folder,cfg['paths']['output_dir'])).glob('*/status.json')
                       if json.loads(p.read_text()).get('state') == 'running'
                       and inspect_run(p.parent)['state'] == 'running']
            if running:
                raise ValueError('Un calcul est déjà en cours ; attendre ou annuler le run')
            run=prepare_run(folder)
            pid=start_run(run)
            return {'id':run.name,'state':'running','pid':pid}
        return guarded(act)

    def result_store(run):
        store = run/'results'/'dic_store'
        return open_result_store(store if store.is_dir() else run/'results'/'dic_results.npz')

    def run_field_values(run, manifest, store, field, frame, mesh=None):
        """Return nodal values in the units used by the result viewer."""
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

    def find_run(run_id):
        folder,cfg=current()
        if '/' in run_id or '..' in run_id:
            raise ValueError('Identifiant de run invalide')
        run=resolve_path(folder,cfg['paths']['output_dir'])/run_id
        if not (run/'status.json').is_file():
            raise ValueError(f'Run introuvable : {run_id}')
        return run

    @app.get('/api/runs')
    def list_runs():
        def act():
            folder,cfg=current()
            root=resolve_path(folder,cfg['paths']['output_dir'])
            if not root.is_dir():
                return {'runs':[]}
            rows=[]
            for path in sorted(root.iterdir(), reverse=True):
                if (path/'status.json').is_file():
                    status=inspect_run(path, details=False)
                    rows.append({'id':path.name,'state':status['state'],
                                 'updated_utc':status.get('updated_utc'),
                                 'completed_frames':status.get('completed_frames',0),
                                 'total_frames':status.get('total_frames',0),
                                 'progress':status.get('progress'),
                                 'error':status.get('error')})
            return {'runs':rows}
        return guarded(act)

    @app.get('/api/runs/{run_id}/fields')
    def run_fields(run_id: str):
        def act():
            run=find_run(run_id)
            status=inspect_run(run)
            if status['state']!='completed':
                raise ValueError('Les champs ne sont disponibles que pour un run terminé')
            manifest=status['manifest']
            store=result_store(run)
            mesh=store.read_mesh()
            count=store.frame_count+1
            nodes=len(mesh['nodes_xy'])
            cells=len(mesh['elements'])
            times=[manifest['visible_reference']['time_s']]+[row['time_s'] for row in manifest['visible_images']]
            names=['u1','u2','u_norm','E11','E22','E12']
            if store.frame_count and 'discrepancy_ref' in store.read_frame(0): names.append('Residual')
            if manifest['mode']=='dic_thermal':
                names += ['Temperature','Delta_temperature','Temperature_element']
            return {'run_id':run_id,'times_s':times,'fields':names,'nodes':nodes,
                    'elements':cells,'thermal_provenance':manifest.get('thermal_provenance',[]),
                    'length_unit':manifest['length_unit'],
                    'temperature_unit':manifest.get('temperature_unit')}
        return guarded(act)

    @app.get('/api/runs/{run_id}/mesh')
    def run_mesh(run_id: str):
        def act():
            run=find_run(run_id)
            status=inspect_run(run)
            if status['state']!='completed': raise ValueError('Run non terminé')
            mesh=result_store(run).read_mesh()
            nodes=np.asarray(mesh['nodes_xy'], dtype=float)
            if nodes.ndim!=2 or nodes.shape[1]!=2 or not np.isfinite(nodes).all():
                raise ValueError('Coordonnées du maillage invalides')
            return {'run_id':run_id, 'nodes_xy':nodes.tolist(),
                    'extent':[float(nodes[:,0].min()),float(nodes[:,0].max()),
                              float(nodes[:,1].min()),float(nodes[:,1].max())]}
        return guarded(act)

    @app.get('/api/runs/{run_id}/field-range')
    def field_range(run_id: str, field: str='u_norm', frame: int=0,
                    scope: str='image'):
        def act():
            run=find_run(run_id)
            status=inspect_run(run)
            if status['state']!='completed': raise ValueError('Run non terminé')
            if scope not in ('image','sequence'):
                raise ValueError('Portée attendue : image ou sequence')
            manifest=status['manifest']; store=result_store(run); mesh=store.read_mesh()
            frames=range(store.frame_count+1) if scope=='sequence' else (frame,)
            finite_ranges=[]
            for index in frames:
                values=np.asarray(run_field_values(run,manifest,store,field,index,mesh),dtype=float)
                finite=values[np.isfinite(values)]
                if finite.size: finite_ranges.append((float(finite.min()),float(finite.max())))
            if not finite_ranges: raise ValueError('Le champ ne contient aucune valeur finie')
            return {'field':field,'scope':scope,'frame':frame if scope=='image' else None,
                    'min':min(row[0] for row in finite_ranges),
                    'max':max(row[1] for row in finite_ranges)}
        return guarded(act)

    @app.get('/api/runs/{run_id}/field-image')
    def field_image(run_id: str, field: str='u_norm', frame: int=0,
                    vmin: float | None=None, vmax: float | None=None):
        def act():
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
            import matplotlib.tri as tri
            run=find_run(run_id)
            status=inspect_run(run)
            if status['state']!='completed': raise ValueError('Run non terminé')
            manifest=status['manifest']; store=result_store(run); mesh=store.read_mesh()
            nodes=np.asarray(mesh['nodes_xy'], dtype=float)
            elements=np.asarray(mesh['elements'])
            values=np.asarray(run_field_values(run,manifest,store,field,frame,mesh))
            kinematic=field in ('u1','u2','u_norm','E11','E22','E12')
            if (vmin is None) != (vmax is None):
                raise ValueError('vmin et vmax doivent être fournis ensemble')
            if vmin is not None:
                if not kinematic: raise ValueError('Les bornes de couleur sont disponibles pour les champs cinématiques')
                if not np.isfinite(vmin) or not np.isfinite(vmax) or vmin>=vmax:
                    raise ValueError('Bornes de couleur invalides : vmin doit être fini et inférieur à vmax')
            preview_dir=run/'results'/'previews'
            # A versioned cache prevents old previews with axes/colorbars from being reused.
            preview=preview_dir/f'{field}_{frame:05d}_v3.png'
            if vmin is None and preview.is_file(): return FileResponse(preview, media_type='image/png')
            if field=='Residual':
                array=values
                figure,axis=plt.subplots(figsize=(8,5),dpi=110)
                axis.imshow(array,cmap='magma',origin='upper')
                axis.set_axis_off(); figure.subplots_adjust(0,0,1,1)
            else:
                triangles=elements if elements.shape[1]==3 else np.concatenate([elements[:,[0,1,2]],elements[:,[0,2,3]]])
                xmin,xmax=nodes[:,0].min(),nodes[:,0].max()
                ymin,ymax=nodes[:,1].min(),nodes[:,1].max()
                width=max(float(xmax-xmin),1e-12); height=max(float(ymax-ymin),1e-12)
                dpi=120; fig_height=6.0; fig_width=fig_height*width/height
                figure=plt.figure(figsize=(fig_width,fig_height),dpi=dpi)
                axis=figure.add_axes([0,0,1,1])
                with np.errstate(invalid='ignore'):
                    options={'shading':'gouraud','cmap':'coolwarm'}
                    if vmin is not None: options.update(vmin=vmin,vmax=vmax)
                    if field == 'Temperature_element':
                        face_values=values if elements.shape[1]==3 else np.repeat(values,2)
                        options['shading']='flat'
                        triangulation=tri.Triangulation(nodes[:,0],nodes[:,1],triangles)
                        triangulation.set_mask(~np.isfinite(face_values))
                        axis.tripcolor(triangulation,facecolors=np.nan_to_num(face_values,nan=0),**options)
                    else:
                        axis.tripcolor(tri.Triangulation(nodes[:,0],nodes[:,1],triangles),
                                       np.ma.masked_invalid(values),**options)
                axis.set_xlim(float(xmin),float(xmax)); axis.set_ylim(float(ymax),float(ymin))
                axis.set_aspect('auto'); axis.set_axis_off()
            buffer=io.BytesIO(); figure.savefig(buffer,format='png',dpi=120,pad_inches=0); plt.close(figure)
            if vmin is not None: return Response(buffer.getvalue(),media_type='image/png')
            preview_dir.mkdir(exist_ok=True)
            temporary=preview.with_suffix('.tmp'); temporary.write_bytes(buffer.getvalue()); temporary.replace(preview)
            return FileResponse(preview,media_type='image/png')
        return guarded(act)

    def run_histories_payload(run_id, nodes):
        """Read each stored frame and thermal archive once for selected VIS nodes."""
        run=find_run(run_id)
        status=inspect_run(run)
        if status['state']!='completed': raise ValueError('Run non terminé')
        manifest=status['manifest']; store=result_store(run)
        count=len(store.read_mesh()['nodes_xy'])
        if not nodes or any(node<0 or node>=count for node in nodes):
            raise ValueError('Indice de nœud hors maillage')
        nodes=list(dict.fromkeys(nodes))
        times=[manifest['visible_reference']['time_s']]+[row['time_s'] for row in manifest['visible_images']]
        u=np.zeros((len(times),len(nodes),2)); strain=np.zeros((len(times),len(nodes),3))
        if store.path.is_file():  # legacy monolithic NPZ: decompress each array once
            u[1:]=store.read_history('u_nodal')[:,nodes]
            strain[1:]=store.read_history('strain')[:,nodes]
        else:
            for frame in range(1,len(times)):
                record=store.read_frame(frame-1)
                u[frame]=np.asarray(record['u_nodal'])[nodes]
                strain[frame]=np.asarray(record['strain'])[nodes]
        thermal=None
        path=run/'results'/'thermal_fields.npz'
        if path.is_file():
            with np.load(path,allow_pickle=False) as fields:
                thermal=(np.asarray(fields['temperature'])[:,nodes],
                         np.asarray(fields['delta_temperature'])[:,nodes])
        scale=manifest['mm_per_pixel'] if manifest['length_unit']=='mm' else 1.
        histories=[]
        for j,node in enumerate(nodes):
            rows=[]
            for k,time in enumerate(times):
                row={'time_s':time,'u1':float(u[k,j,0]*scale),'u2':float(u[k,j,1]*scale),
                     'E11':float(strain[k,j,0]),'E22':float(strain[k,j,1]),
                     'E12':float(strain[k,j,2])}
                if thermal is not None:
                    row['Temperature']=float(thermal[0][k,j]) if np.isfinite(thermal[0][k,j]) else None
                    row['Delta_temperature']=float(thermal[1][k,j]) if np.isfinite(thermal[1][k,j]) else None
                rows.append(row)
            histories.append({'node':node,'history':rows})
        return {'length_unit':manifest['length_unit'],
                'temperature_unit':manifest.get('temperature_unit'),'histories':histories}

    @app.get('/api/runs/{run_id}/histories')
    def run_histories(run_id: str, nodes: str):
        def act():
            try: selected=[int(part) for part in nodes.split(',')]
            except ValueError as error: raise ValueError('Liste de nœuds invalide') from error
            return run_histories_payload(run_id,selected)
        return guarded(act)

    @app.get('/api/runs/{run_id}/history')
    def run_history(run_id: str, node: int=0):
        def act():
            result=run_histories_payload(run_id,[node]); item=result['histories'][0]
            return {'node':node,'length_unit':result['length_unit'],
                    'temperature_unit':result['temperature_unit'],'history':item['history']}
        return guarded(act)

    @app.post('/api/runs/{run_id}/export')
    def run_export(run_id: str, body: dict | None = None):
        def act():
            run=find_run(run_id)
            status=inspect_run(run)
            if status['state']!='completed': raise ValueError('Run non terminé')
            manifest=status['manifest']
            archive=run/'results'/'dic_results.npz'
            if body and body.get('legacy_npz'):
                source=result_store(run)
                if hasattr(source, 'export_npz'):
                    source.export_npz(archive)
                elif not archive.is_file():
                    raise ValueError('Résultats DIC indisponibles pour une archive NPZ')
            return {'message':'Chemins des exports du run figé',
                    'dic_pvd':manifest.get('dic_pvd'),
                    'coupled_pvd':manifest.get('coupled_pvd'),
                    'vtu':manifest.get('coupled_vtu',manifest.get('dic_vtu',[])),
                    'legacy_npz':str(archive.resolve()) if archive.is_file() else None,
                    'manifest':str((run/'manifest.json').resolve())}
        return guarded(act)

    @app.get('/api/runs/{run_id}')
    def run_status(run_id: str):
        return guarded(lambda: inspect_run(find_run(run_id)))

    @app.post('/api/runs/{run_id}/resume')
    def resume_run(run_id: str):
        def act():
            run=find_run(run_id)
            status=inspect_run(run)
            if status['state'] not in ('failed','cancelled'):
                raise ValueError('Seul un calcul interrompu ou échoué peut reprendre')
            pid=status.get('pid')
            if worker_alive(pid):
                raise ValueError('Attendre la fin du processus précédent avant la reprise')
            # The D2IC result store verifies the frozen config and image
            # fingerprint before accepting a saved frame checkpoint.
            pid=start_run(run, resume=True)
            return {'id':run_id,'state':'running','pid':pid}
        return guarded(act)

    @app.delete('/api/runs/{run_id}')
    def delete_run(run_id: str):
        def act():
            run = find_run(run_id)
            folder, cfg = current()
            root = resolve_path(folder, cfg['paths']['output_dir']).resolve()
            if run.is_symlink() or run.resolve().parent != root:
                raise ValueError('Le run doit être un dossier direct de cette étude')
            status = inspect_run(run)
            if status['state'] == 'running':
                raise ValueError('Arrêter le calcul avant de supprimer ce run')
            shutil.rmtree(run)
            return {'id': run_id, 'deleted': True}
        return guarded(act)

    @app.post('/api/runs/{run_id}/cancel')
    def cancel_run(run_id: str):
        def act():
            run=find_run(run_id)
            status=inspect_run(run)
            if status['state']!='running':
                return status
            pid=status.get('pid')
            if pid:
                if not stop_worker(pid):
                    return inspect_run(run)
            from .dic_run import write_status
            write_status(run,'cancelled',pid=pid,message='Calcul interrompu par l’utilisateur')
            return inspect_run(run)
        return guarded(act)

    return app


app = create_app()
