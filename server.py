"""Loopback-only HTTP application for DIC study preparation and inspection."""

from __future__ import annotations

import base64
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import tomllib
from functools import lru_cache
from threading import Lock

import cv2
import numpy as np
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from .dic_run import (_snapshot_images, inspect_run, prepare_run, prepare_job,
                      start_run, stop_worker, verify_prepared_run, worker_alive, write_preparation, write_status)
from .imaging import (discover_visible_series, image_shape, inventory, mask_from_shapes,
                      morphology, read_image, read_mask, save_mask, thermal_inventory)
from .project import copy_project, create_project, load_project, relink_sources, resolve_path, save_project
from .readiness import evaluate_readiness
from .schema import SCHEMA_VERSION, THERMAL_SECTIONS, defaults, describe_fields, validate
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


def _mask_vector_svg(mask, stroke, fill, fill_opacity, stroke_width=0.6):
    """Encode a binary image region as native-pixel SVG contours."""
    mask = np.asarray(mask, dtype=bool)
    height, width = mask.shape
    contours, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_LIST,
                                   cv2.CHAIN_APPROX_SIMPLE)
    paths = []
    for contour in contours:
        points = contour.reshape(-1, 2)
        if len(points) == 1:
            x, y = points[0]
            paths.append(f'M {x - 0.5} {y - 0.5} h 1 v 1 h -1 Z')
            continue
        commands = [f'M {points[0, 0]} {points[0, 1]}']
        commands.extend(f'L {x} {y}' for x, y in points[1:])
        if len(points) > 2:
            commands.append('Z')
        paths.append(' '.join(commands))
    path_data = ' '.join(paths)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
            f'width="{width}" height="{height}" preserveAspectRatio="none">'
            f'<path d="{path_data}" fill="{fill}" fill-opacity="{fill_opacity}" '
            f'fill-rule="evenodd" stroke="{stroke}" stroke-width="{stroke_width}" '
            'stroke-linejoin="round" vector-effect="non-scaling-stroke"/></svg>')


def _svg_data_url(svg):
    return 'data:image/svg+xml;base64,' + base64.b64encode(svg.encode('utf-8')).decode('ascii')


def _mesh_vector_svg(nodes, elements, height, width, edge_width=0.2):
    """Encode unique finite-element edges as SVG in original VIS pixels."""
    nodes = np.asarray(nodes, dtype=float)
    elements = np.asarray(elements, dtype=np.int64)
    cell_edges = np.concatenate([
        elements[:, [index, (index + 1) % elements.shape[1]]]
        for index in range(elements.shape[1])
    ])
    edges = np.unique(np.sort(cell_edges, axis=1), axis=0)
    if not np.isfinite(nodes).all() or (edges.size and (edges.min() < 0 or edges.max() >= len(nodes))):
        raise ValueError('Coordonnées du maillage invalides pour le calque vectoriel')
    segments = ' '.join(
        f'M {nodes[a, 0]:.4f} {nodes[a, 1]:.4f} L {nodes[b, 0]:.4f} {nodes[b, 1]:.4f}'
        for a, b in edges)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
            f'width="{width}" height="{height}" preserveAspectRatio="none">'
            f'<path d="{segments}" fill="none" stroke="#ffb02a" stroke-width="{edge_width}" '
            'stroke-linecap="round" stroke-linejoin="round"/></svg>')


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


def create_app(initial_folder=None):
    """Create the local FastAPI app, optionally opening an existing study."""
    app = FastAPI(title='D2IC_GUI')
    launch_lock = Lock()
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
        roi_mask = mask.copy()
        photo_mask = None
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
            photo_mask = native
        except (ValueError, TypeError, ImportError) as error:
            photo_error = str(error)

        roi_svg = _mask_vector_svg(roi_mask, '#308c26', '#499b5c', 0.34)
        photo_svg = (_mask_vector_svg(photo_mask, '#146ed2', '#238cd2', 0.41)
                     if photo_mask is not None else None)
        return {'roi_data_url': _svg_data_url(roi_svg),
                'photometric_data_url': _svg_data_url(photo_svg) if photo_svg else None,
                'area_px': int(roi_mask.sum()),
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
        return {'version': SCHEMA_VERSION, 'fields': describe_fields(),
                'thermal_sections': sorted(THERMAL_SECTIONS)}

    @app.post('/api/readiness')
    def readiness(body: dict):
        """Explain required and optional setup work for the supplied form config."""
        def act():
            folder, _ = current()
            return evaluate_readiness(folder, body.get('config'))
        return guarded(act)

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

    @app.get('/api/runs/{run_id}/visible-image')
    def run_visible_image(run_id: str, frame: int = 0):
        """Serve the provenance-checked VIS source of an available result frame."""
        def act():
            run = find_run(run_id)
            status = inspect_run(run)
            manifest = status['manifest']
            store = result_store(run)
            if frame < 0 or frame > store.frame_count:
                raise ValueError('Instant VIS non encore disponible')
            path = visible_source(run, manifest, frame)
            shape = visible_shape(manifest, store)
            stat = path.stat()
            png = _preview_png(str(path), stat.st_mtime_ns, stat.st_size, True, True)
            decoded = cv2.imdecode(np.frombuffer(png, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
            if decoded is None or decoded.shape[:2] != shape:
                raise ValueError('Dimensions de l’image VIS différentes du manifeste')
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

    @app.get('/api/roi/vector-layer')
    def roi_vector_layer(mask_path: str, visible_dir: str, reference_image: str,
                         kind: str = 'geometry', roi_erosion_px: float = 0.0,
                         image_binning: int = 1, operation: str = 'none',
                         radius_px: int = 0, remove_islands: bool = True,
                         min_island_area_px: int = 64):
        """Return ROI boundaries as SVG paths in native VIS pixel coordinates."""
        def act():
            base = app.state.folder or Path.cwd()
            mask_file = resolve_path(base, mask_path)
            if mask_file.suffix.lower() not in {'.tif', '.tiff', '.png'} or not mask_file.is_file():
                raise ValueError('Choisir un fichier ROI TIFF ou PNG lisible')
            if not reference_image or Path(reference_image).name != reference_image:
                raise ValueError('Choisir une image de référence VIS')
            shape = image_shape(resolve_path(base, visible_dir) / reference_image, visible=True)
            mask = read_mask(mask_file)
            if mask.shape != shape or not mask.any():
                raise ValueError('Masque ROI vide ou de dimensions différentes de VIS')
            if kind not in ('geometry', 'photometric'):
                raise ValueError('Type de calque ROI inconnu')
            mask, _ = morphology(mask, operation, radius_px)
            if kind == 'photometric':
                from d2ic.io.app_utils import erode_correlation_roi
                from d2ic.io.binning import bin_mask
                from d2ic.mesh.generation import _remove_small_components
                if isinstance(image_binning, bool) or image_binning < 1:
                    raise ValueError('Le binning doit être un entier positif')
                if min_island_area_px < 0:
                    raise ValueError('L’aire minimale d’îlot doit être positive ou nulle')
                if remove_islands:
                    mask = _remove_small_components(mask, min_island_area_px)
                h, w = shape[0] // image_binning, shape[1] // image_binning
                reduced = bin_mask(mask, image_binning)[:h, :w]
                reduced = erode_correlation_roi(reduced, roi_erosion_px,
                                                image_binning=image_binning)
                mask = np.zeros(shape, dtype=bool)
                mask[:h * image_binning, :w * image_binning] = np.repeat(
                    np.repeat(reduced, image_binning, axis=0), image_binning, axis=1)
                color, fill, opacity = '#146ed2', '#238cd2', 0.41
            else:
                color, fill, opacity = '#308c26', '#499b5c', 0.34
            svg = _mask_vector_svg(mask, color, fill, opacity)
            return Response(svg.encode('utf-8'), media_type='image/svg+xml',
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
            for stale in ('mesh_preview.png','mesh_preview.json','mesh_layer.png','mesh_layer.svg'):
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
            mesh_svg = _mesh_vector_svg(nodes, cells, *gray.shape, edge_width=0.2)
            (folder/'roi'/'mesh_layer.svg').write_text(mesh_svg, encoding='utf-8')
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
                    'layer_url':'/api/mesh/layer-image',
                    'vector_url':'/api/mesh/vector-layer'}
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
            media_type = 'image/svg+xml' if path.suffix.lower() == '.svg' else 'image/png'
            return FileResponse(path,media_type=media_type,
                                headers={'Cache-Control': 'private, no-cache'})
        return guarded(act)

    @app.get('/api/mesh/preview-image')
    def mesh_preview_image():
        return validated_mesh_image('mesh_preview.png')

    @app.get('/api/mesh/layer-image')
    def mesh_layer_image():
        return validated_mesh_image('mesh_layer.png')

    @app.get('/api/mesh/vector-layer')
    def mesh_vector_layer():
        return validated_mesh_image('mesh_layer.svg')

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

    def require_idle(folder, cfg):
        root = resolve_path(folder, cfg['paths']['output_dir'])
        for status_path in root.glob('*/status.json'):
            if inspect_run(status_path.parent, details=False)['state'] == 'running':
                raise ValueError('Un calcul est déjà en cours ; attendre ou arrêter ce job')

    @app.post('/api/runs/prepare')
    def prepare(body: dict = None):
        def act():
            folder, cfg = current()
            if body and 'config' in body and validate(body['config']) != cfg:
                raise ValueError('Enregistrer les modifications avant de préparer le job')
            run = prepare_job(folder)
            return {'id': run.name, **inspect_run(run, details=False)}
        return guarded(act)

    @app.post('/api/runs/{run_id}/start')
    def launch_prepared(run_id: str):
        def act():
            folder, cfg = current()
            run = find_run(run_id)
            root = resolve_path(folder, cfg['paths']['output_dir']).resolve()
            if run.is_symlink() or run.resolve().parent != root:
                raise ValueError('Le job doit être un dossier direct de cette étude')
            status = inspect_run(run, details=False)
            if not status['can_start']:
                raise ValueError('Ce job ne peut pas être lancé ; corriger les erreurs et préparer un nouveau job')
            require_idle(folder, cfg)
            try:
                verify_prepared_run(run)
                pid = start_run(run)
            except Exception as error:
                report = status['preparation']
                report['ready'] = False
                report['required'].append({'view': 'Job Manager', 'message': str(error)})
                write_preparation(run, report)
                write_status(run, 'blocked', error=str(error))
                raise ValueError(str(error)) from error
            return {'id': run_id, 'state': 'running', 'pid': pid}
        with launch_lock:
            return guarded(act)

    @app.post('/api/runs')
    def launch(body: dict = None):
        def act():
            folder,cfg = current()
            if body and 'config' in body and validate(body['config']) != cfg:
                raise ValueError('Enregistrer les modifications de configuration avant le calcul')
            status = evaluate_readiness(folder, cfg)
            if not status['ready']:
                details = '; '.join(f"{item['view']} : {item['message']}" for item in status['required'])
                raise ValueError('Étapes obligatoires à compléter avant le calcul : ' + details)
            running = [p for p in (resolve_path(folder,cfg['paths']['output_dir'])).glob('*/status.json')
                       if json.loads(p.read_text()).get('state') == 'running'
                       and inspect_run(p.parent)['state'] == 'running']
            if running:
                raise ValueError('Un calcul est déjà en cours ; attendre ou annuler le run')
            run=prepare_run(folder)
            pid=start_run(run)
            return {'id':run.name,'state':'running','pid':pid}
        with launch_lock:
            return guarded(act)

    def result_store(run):
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
                                 'error':status.get('error'),
                                 'preparation':status.get('preparation'),
                                 'can_start':status['can_start'],
                                 'results_available': (path/'results'/'dic_store'/'mesh.npz').is_file()
                                     or (path/'results'/'dic_results.npz').is_file()})
            return {'runs':rows}
        return guarded(act)

    @app.get('/api/runs/{run_id}/fields')
    def run_fields(run_id: str):
        def act():
            run=find_run(run_id)
            status=inspect_run(run)
            manifest=status['manifest']
            store=result_store(run)
            mesh=store.read_mesh()
            try:
                shape = list(visible_shape(manifest, store))
            except ValueError:
                shape = None  # Legacy runs can still display their cropped field maps.
            count=store.frame_count+1
            nodes=len(mesh['nodes_xy'])
            cells=len(mesh['elements'])
            times=([manifest['visible_reference']['time_s']]+[row['time_s'] for row in manifest['visible_images']])[:count]
            names=['u1','u2','u_norm','E11','E22','E12']
            residual_frames = []
            if store.path.is_file():
                with np.load(store.path, allow_pickle=False) as archive:
                    if 'discrepancy_ref' in archive.files:
                        residual_frames = list(range(1, count))
            else:
                for index in range(count - 1):
                    # Opening the NPZ directory reads its keys without decompressing arrays.
                    with np.load(store.frames_path / f'frame_{index:04d}.npz', allow_pickle=False) as archive:
                        if 'discrepancy_ref' in archive.files:
                            residual_frames.append(index + 1)
            if residual_frames: names.append('Residual')
            if manifest['mode']=='dic_thermal' and (run/'results'/'thermal_fields.npz').is_file():
                names += ['Temperature','Delta_temperature','Temperature_element']
            return {'run_id':run_id,'times_s':times,'fields':names,'nodes':nodes,
                    'state':status['state'], 'completed_frames':count - 1,
                    'total_frames':len(manifest['visible_images']),
                    'elements':cells,'thermal_provenance':manifest.get('thermal_provenance',[]),
                    'source_shape_hw': shape, 'residual_frames': residual_frames,
                    'length_unit':manifest['length_unit'],
                    'temperature_unit':manifest.get('temperature_unit')}
        return guarded(act)

    @app.get('/api/runs/{run_id}/mesh')
    def run_mesh(run_id: str, overlay: str = 'none', frame: int = 0):
        def act():
            run=find_run(run_id)
            status=inspect_run(run)
            manifest=status['manifest']
            store=result_store(run); mesh=store.read_mesh()
            nodes=np.asarray(mesh['nodes_xy'], dtype=float)
            if nodes.ndim!=2 or nodes.shape[1]!=2 or not np.isfinite(nodes).all():
                raise ValueError('Coordonnées du maillage invalides')
            if overlay not in ('none', 'reference', 'current'):
                raise ValueError("overlay attendu : 'none', 'reference' ou 'current'")
            if overlay != 'none' and (frame < 0 or frame > store.frame_count):
                raise ValueError('Instant VIS hors de la séquence')
            if overlay == 'current' and frame > 0:
                nodes = result_nodes(manifest, store, mesh, frame, overlay)
            if overlay == 'none':
                extent=[float(nodes[:,0].min()),float(nodes[:,0].max()),
                        float(nodes[:,1].min()),float(nodes[:,1].max())]
            else:
                height, width = visible_shape(manifest, store)
                extent=[-.5, width-.5, -.5, height-.5]
            return {'run_id':run_id, 'nodes_xy':nodes.tolist(), 'elements':np.asarray(mesh['elements']).tolist(), 'extent':extent,
                    'source_shape_hw': list(visible_shape(manifest, store)) if overlay != 'none' else None}
        return guarded(act)

    @app.get('/api/runs/{run_id}/field-range')
    def field_range(run_id: str, field: str='u_norm', frame: int=0,
                    scope: str='image'):
        def act():
            run=find_run(run_id)
            status=inspect_run(run)
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
                    vmin: float | None=None, vmax: float | None=None,
                    overlay: str='none', center_zero: bool=False):
        def act():
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
            import matplotlib.tri as tri
            run=find_run(run_id)
            color_min, color_max = vmin, vmax
            status=inspect_run(run)
            manifest=status['manifest']; store=result_store(run); mesh=store.read_mesh()
            if overlay not in ('none', 'reference', 'current'):
                raise ValueError("overlay attendu : 'none', 'reference' ou 'current'")
            if overlay != 'none' and frame < 0:
                raise ValueError('Instant VIS hors de la séquence')
            if overlay != 'none' and frame > store.frame_count:
                raise ValueError('Instant VIS hors de la séquence')
            nodes=np.asarray(mesh['nodes_xy'], dtype=float)
            elements=np.asarray(mesh['elements'])
            values=np.asarray(run_field_values(run,manifest,store,field,frame,mesh))
            if center_zero and field != 'Residual':
                if vmin is not None and vmax is not None:
                    bound = max(abs(float(vmin)), abs(float(vmax)))
                else:
                    finite = values[np.isfinite(values)]
                    bound = float(np.max(np.abs(finite))) if finite.size else 0.
                if np.isfinite(bound):
                    bound = max(bound, 1e-12)
                    color_min, color_max = -bound, bound
            if overlay != 'none':
                nodes = result_nodes(manifest, store, mesh, frame, overlay)
                height, width = visible_shape(manifest, store)
            kinematic=field in ('u1','u2','u_norm','E11','E22','E12')
            if (color_min is None) != (color_max is None):
                raise ValueError('vmin et vmax doivent être fournis ensemble')
            if color_min is not None:
                if not kinematic and not center_zero: raise ValueError('Les bornes de couleur sont disponibles pour les champs cinématiques')
                if not np.isfinite(color_min) or not np.isfinite(color_max) or color_min>=color_max:
                    raise ValueError('Bornes de couleur invalides : vmin doit être fini et inférieur à vmax')
            preview_dir=run/'results'/'previews'
            # A versioned cache prevents old previews with axes/colorbars from being reused.
            version = 'v5' if overlay != 'none' else 'v3'
            preview=preview_dir/f'{field}_{frame:05d}_{overlay}_{version}.png'
            if overlay == 'none':
                # Continue reading the established v3 cache for ordinary opaque previews.
                preview=preview_dir/f'{field}_{frame:05d}_v3.png'
            if color_min is None and not center_zero and preview.is_file(): return FileResponse(preview, media_type='image/png')
            if field=='Residual':
                array=values
                if overlay == 'none':
                    figure,axis=plt.subplots(figsize=(8,5),dpi=110)
                    axis.imshow(array,cmap='magma',origin='upper')
                else:
                    config_path = run/'dic_config.toml'
                    if not config_path.is_file(): config_path = run/'config.toml'
                    dic_config = tomllib.loads(config_path.read_text()) if config_path.is_file() else {}
                    binning = int(dic_config.get('dic', {}).get('image_binning', 1))
                    if binning < 1 or array.ndim != 2 or array.shape[0] * binning > height or array.shape[1] * binning > width:
                        raise ValueError('Dimensions de la carte de résidu incompatibles avec le binning VIS')
                    figure = plt.figure(figsize=(width/120, height/120), dpi=120)
                    axis = figure.add_axes([0, 0, 1, 1])
                    if overlay == 'current':
                        triangles = elements if elements.shape[1] == 3 else np.concatenate([elements[:, [0,1,2]], elements[:, [0,2,3]]])
                        array = _transport_reference_raster(array, np.asarray(mesh['nodes_xy']), nodes,
                                                            triangles, (height, width), binning)
                        extent = [-.5, width-.5, height-.5, -.5]
                    else:
                        extent = [-.5, array.shape[1]*binning-.5, array.shape[0]*binning-.5, -.5]
                    axis.imshow(np.ma.masked_invalid(array), cmap='magma', origin='upper',
                                extent=extent, interpolation='nearest')
                    axis.set_xlim(-.5, width-.5); axis.set_ylim(height-.5, -.5)
                axis.set_axis_off(); figure.subplots_adjust(0,0,1,1)
            else:
                triangles=elements if elements.shape[1]==3 else np.concatenate([elements[:,[0,1,2]],elements[:,[0,2,3]]])
                xmin,xmax=nodes[:,0].min(),nodes[:,0].max()
                ymin,ymax=nodes[:,1].min(),nodes[:,1].max()
                mesh_width=max(float(xmax-xmin),1e-12); mesh_height=max(float(ymax-ymin),1e-12)
                if overlay != 'none':
                    dpi=120; fig_width=width/dpi; fig_height=height/dpi
                else:
                    dpi=120; fig_height=6.0; fig_width=fig_height*mesh_width/mesh_height
                figure=plt.figure(figsize=(fig_width,fig_height),dpi=dpi)
                axis=figure.add_axes([0,0,1,1])
                with np.errstate(invalid='ignore'):
                    options={'shading':'gouraud','cmap':'coolwarm'}
                    if color_min is not None: options.update(vmin=color_min,vmax=color_max)
                    if field == 'Temperature_element':
                        face_values=values if elements.shape[1]==3 else np.repeat(values,2)
                        options['shading']='flat'
                        triangulation=tri.Triangulation(nodes[:,0],nodes[:,1],triangles)
                        face_finite = np.isfinite(face_values)
                        triangulation.set_mask(~face_finite)
                        axis.tripcolor(triangulation,facecolors=np.nan_to_num(face_values,nan=0),**options)
                    else:
                        triangulation = tri.Triangulation(nodes[:,0],nodes[:,1],triangles)
                        if overlay != 'none':
                            finite = np.isfinite(values)
                            triangulation.set_mask(~np.all(finite[triangles], axis=1))
                        axis.tripcolor(triangulation, np.ma.masked_invalid(values), **options)
                if overlay == 'none':
                    axis.set_xlim(float(xmin),float(xmax)); axis.set_ylim(float(ymax),float(ymin))
                else:
                    axis.set_xlim(-.5, width-.5); axis.set_ylim(height-.5, -.5)
                axis.set_aspect('auto'); axis.set_axis_off()
            buffer=io.BytesIO(); figure.savefig(buffer,format='png',dpi=120,pad_inches=0,
                                                transparent=overlay != 'none'); plt.close(figure)
            if color_min is not None or center_zero: return Response(buffer.getvalue(),media_type='image/png')
            preview_dir.mkdir(exist_ok=True)
            temporary=preview.with_suffix('.tmp'); temporary.write_bytes(buffer.getvalue()); temporary.replace(preview)
            return FileResponse(preview,media_type='image/png')
        return guarded(act)

    def run_histories_payload(run_id, nodes):
        """Read each stored frame and thermal archive once for selected VIS nodes."""
        run=find_run(run_id)
        status=inspect_run(run)
        manifest=status['manifest']; store=result_store(run)
        count=len(store.read_mesh()['nodes_xy'])
        if not nodes or any(node<0 or node>=count for node in nodes):
            raise ValueError('Indice de nœud hors maillage')
        nodes=list(dict.fromkeys(nodes))
        available = store.frame_count + 1
        times=([manifest['visible_reference']['time_s']]+[row['time_s'] for row in manifest['visible_images']])[:available]
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

    def section_payload(run_id, field, frame, x0, y0, x1, y1, samples, scope):
        """Sample nodal fields on a material segment in reference VIS pixels.

        Quadrilaterals use the viewer's 012/023 triangles; absent values remain
        null. Distances use the run length unit, including its reference state.
        """
        endpoints=np.asarray([x0,y0,x1,y1],dtype=float)
        if not np.isfinite(endpoints).all() or np.hypot(x1-x0,y1-y0)<=0:
            raise ValueError('La coupe exige deux extrémités finies et distinctes')
        if field not in ('u1','u2','u_norm','E11','E22','E12','Temperature','Delta_temperature'):
            raise ValueError('Champ non pris en charge pour une coupe')
        if scope not in ('image','sequence'): raise ValueError('Portée attendue : image ou sequence')
        if samples < 2 or samples > 2000: raise ValueError('samples doit être compris entre 2 et 2000')
        run=find_run(run_id); manifest=inspect_run(run)['manifest']; store=result_store(run); mesh=store.read_mesh()
        nodes=np.asarray(mesh['nodes_xy'],dtype=float); elements=np.asarray(mesh['elements'],dtype=int)
        triangles=elements if elements.shape[1]==3 else np.concatenate([elements[:,[0,1,2]],elements[:,[0,2,3]]])
        px=np.linspace(float(x0),float(x1),samples); py=np.linspace(float(y0),float(y1),samples)
        scale=float(manifest['mm_per_pixel']) if manifest['length_unit']=='mm' else 1.
        distance=np.hypot(px-px[0],py-py[0])*scale
        times=([manifest['visible_reference']['time_s']]+[row['time_s'] for row in manifest['visible_images']])[:store.frame_count+1]
        frames=range(len(times)) if scope=='sequence' else (frame,)
        if any(k<0 or k>=len(times) for k in frames): raise ValueError('Instant VIS hors de la séquence')
        profiles=[]
        for k in frames:
            nodal=np.asarray(run_field_values(run,manifest,store,field,k,mesh),dtype=float)
            vals=np.full(samples,np.nan)
            for tri_nodes in triangles:
                vertices=nodes[tri_nodes]; a,b,c=vertices
                den=(b[1]-c[1])*(a[0]-c[0])+(c[0]-b[0])*(a[1]-c[1])
                if abs(den)<1e-14: continue
                candidates=np.flatnonzero(~np.isfinite(vals))
                qx,qy=px[candidates],py[candidates]
                w0=((b[1]-c[1])*(qx-c[0])+(c[0]-b[0])*(qy-c[1]))/den
                w1=((c[1]-a[1])*(qx-c[0])+(a[0]-c[0])*(qy-c[1]))/den
                w2=1-w0-w1; inside=(w0>=-1e-10)&(w1>=-1e-10)&(w2>=-1e-10)
                valid=inside & np.isfinite(nodal[tri_nodes]).all()
                if valid.any(): vals[candidates[valid]]=w0[valid]*nodal[tri_nodes[0]]+w1[valid]*nodal[tri_nodes[1]]+w2[valid]*nodal[tri_nodes[2]]
            profiles.append({'frame':k,'time_s':float(times[k]),'distance':distance.tolist(),
                             'values':[float(v) if np.isfinite(v) else None for v in vals]})
        unit=(manifest.get('temperature_unit') if field in ('Temperature','Delta_temperature') else ('1' if field.startswith('E') else manifest['length_unit']))
        return {'field':field,'length_unit':manifest['length_unit'],'temperature_unit':manifest.get('temperature_unit'),
                'value_unit':unit,'profiles':profiles,'x_ref_px':px.tolist(),'y_ref_px':py.tolist()}

    @app.get('/api/runs/{run_id}/section')
    def run_section(run_id: str, field: str='u1', frame: int=0, x0: float=0, y0: float=0,
                    x1: float=1, y1: float=0, samples: int=200, scope: str='image'):
        def act():
            payload=section_payload(run_id,field,frame,x0,y0,x1,y1,samples,scope)
            return {key:payload[key] for key in ('field','length_unit','temperature_unit','profiles')}
        return guarded(act)

    @app.get('/api/runs/{run_id}/section.csv')
    def run_section_csv(run_id: str, field: str='u1', frame: int=0, x0: float=0, y0: float=0,
                        x1: float=1, y1: float=0, samples: int=200, scope: str='image'):
        def act():
            payload=section_payload(run_id,field,frame,x0,y0,x1,y1,samples,scope)
            output=io.StringIO(); unit=payload['value_unit']
            writer=csv.writer(output); writer.writerow(['frame','time_s',f"distance_{payload['length_unit']}",'x_ref_px','y_ref_px',f'{field}_{unit}'])
            for profile in payload['profiles']:
                for d,x,y,v in zip(profile['distance'],payload['x_ref_px'],payload['y_ref_px'],profile['values']):
                    writer.writerow([profile['frame'],profile['time_s'],d,x,y,'' if v is None else v])
            return Response(output.getvalue(),media_type='text/csv',headers={'Content-Disposition':'attachment; filename="section.csv"'})
        return guarded(act)

    @app.get('/api/runs/{run_id}/histories.csv')
    def run_histories_csv(run_id: str, nodes: str, field: str='u1'):
        def act():
            try: selected=[int(part) for part in nodes.split(',')]
            except ValueError as error: raise ValueError('Liste de nœuds invalide') from error
            payload=run_histories_payload(run_id,selected)
            if field not in ('u1','u2','u_norm','E11','E22','E12','Temperature','Delta_temperature'):
                raise ValueError('Champ non pris en charge pour un historique')
            unit=(payload['temperature_unit'] if field in ('Temperature','Delta_temperature') else ('1' if field.startswith('E') else payload['length_unit']))
            output=io.StringIO(); writer=csv.writer(output); writer.writerow(['node','frame','time_s',f'{field}_{unit}'])
            for item in payload['histories']:
                for frame,row in enumerate(item['history']):
                    value=float(np.hypot(row['u1'],row['u2'])) if field=='u_norm' else row.get(field)
                    writer.writerow([item['node'],frame,row['time_s'],'' if value is None or not np.isfinite(value) else value])
            return Response(output.getvalue(),media_type='text/csv',headers={'Content-Disposition':'attachment; filename="histories.csv"'})
        return guarded(act)

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
            folder, cfg = current()
            require_idle(folder, cfg)
            pid=start_run(run, resume=True)
            return {'id':run_id,'state':'running','pid':pid}
        with launch_lock:
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
            if status['state'] == 'preparing':
                raise ValueError('Attendre la fin de la préparation avant de supprimer ce job')
            if status['state'] == 'running':
                raise ValueError('Arrêter le calcul avant de supprimer ce run')
            shutil.rmtree(run)
            return {'id': run_id, 'deleted': True}
        with launch_lock:
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
