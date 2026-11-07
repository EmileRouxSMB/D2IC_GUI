"""Source-image inventory and binary VIS ROI preparation."""

from __future__ import annotations

from pathlib import Path
from glob import escape as glob_escape
import re
from datetime import datetime

import cv2
import numpy as np
import tifffile
from PIL import Image

from .project import resolve_path
from d2ic.io.app_utils import ROI_MASK_DESCRIPTION, imread_gray, read_roi_mask


def read_image(path, *, visible=False):
    """Read VIS through D2IC or keep scalar TH values unchanged.

    VIS TIFF/BMP/PNG/JPEG images use the exact grayscale conversion used by
    the numerical solver. TH TIFF values remain raw temperature samples.
    ROI files use read_mask instead.
    """
    path = Path(path)
    if visible:
        try:
            image = imread_gray(path)
        except RuntimeError as error:
            raise ValueError(f'Image VIS introuvable ou invalide : {path}') from error
    elif path.suffix.lower() in ('.tif', '.tiff'):
        image = tifffile.imread(path)
    else:
        image = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if image is None or image.ndim != 2:
        raise ValueError(f'Image 2D introuvable ou invalide : {path}')
    return image



def image_shape(path, *, visible=False):
    """Read (height, width) from image headers for responsive GUI inventories.

    Pixel decoding remains mandatory in the scientific run inventory.
    """
    path = Path(path)
    try:
        if path.suffix.lower() in ('.tif', '.tiff'):
            with tifffile.TiffFile(path) as tif:
                shape = tif.series[0].shape
                if not visible and len(shape) != 2:
                    raise ValueError(f'Image 2D introuvable ou invalide : {path}')
                if visible and (len(shape) not in (2, 3) or
                                len(shape) == 3 and shape[2] not in (2, 3, 4)):
                    raise ValueError(f'Image VIS introuvable ou invalide : {path}')
                return tuple(shape[:2])
        with Image.open(path) as image:
            width, height = image.size
            if not visible and len(image.getbands()) != 1:
                raise ValueError(f'Image 2D introuvable ou invalide : {path}')
            return height, width
    except (OSError, IndexError, KeyError, tifffile.TiffFileError) as error:
        raise ValueError(f'Image introuvable ou invalide : {path}') from error


def read_mask(path):
    """Decode a VIS ROI file into a 2D boolean mask with D2IC semantics.

    Grayscale-alpha TIFF/PNG files use the first channel; RGB masks follow
    the same grayscale conversion and threshold as the numerical pipeline.
    """
    path = Path(path)
    if path.suffix.lower() not in {'.tif', '.tiff', '.png'}:
        raise ValueError(f'Format ROI attendu : TIFF ou PNG ({path})')
    try:
        image = imread_gray(path)
    except (RuntimeError, ValueError, OSError) as error:
        raise ValueError(f'Fichier ROI introuvable ou invalide : {path}') from error
    if image.ndim != 2:
        raise ValueError(f'Le masque ROI doit être une image 2D : {path}')
    return read_roi_mask(path, image)


def _metadata_time(path):
    """Read TIFF DateTime plus EXIF subsecond tag, returning seconds."""
    if Path(path).suffix.lower() not in ('.tif', '.tiff'):
        raise ValueError(f'Horodatage TIFF indisponible : {path}')
    with tifffile.TiffFile(path) as tif:
        tags = tif.pages[0].tags
        tag = tags.get('DateTimeOriginal') or tags.get('DateTime')
        if tag is None:
            raise ValueError(f'Horodatage absent : {path}')
        raw = str(tag.value).strip('\x00')
        try:
            stamp = datetime.strptime(raw, '%Y:%m:%d %H:%M:%S.%f')
        except ValueError:
            try:
                stamp = datetime.strptime(raw, '%Y:%m:%d %H:%M:%S')
            except ValueError as error:
                raise ValueError(f'Horodatage TIFF inexploitable : {path}: {raw}') from error
        subtag = (tags.get('SubSecTimeOriginal') or tags.get('SubSecTime')
                  or tags.get(37521) or tags.get(37520))
        if subtag is not None and stamp.microsecond == 0:
            digits = str(subtag.value).strip('\x00 ')
            if not digits.isdigit():
                raise ValueError(f'Fractions de seconde TIFF invalides : {path}: {digits}')
            stamp = stamp.replace(microsecond=int((digits + '000000')[:6]))
        return stamp.timestamp()



def discover_visible_series(directory, *, allowed_suffixes=None):
    """Suggest filename-based VIS series without loading image pixels.

    Numeric runs that vary together form one series. If the final index repeats
    for different earlier identifiers (for example two cameras), split them.
    The returned glob is verified against the discovered filenames.
    """
    folder = Path(directory).expanduser().resolve()
    if not folder.is_dir():
        raise ValueError(f'Dossier image introuvable : {folder}')
    allowed = ({'.tif', '.tiff', '.png', '.jpg', '.jpeg', '.bmp'}
               if allowed_suffixes is None else set(allowed_suffixes))
    images = sorted((path for path in folder.iterdir()
                     if path.is_file() and path.suffix.lower() in allowed),
                    key=lambda path: path.name.casefold())
    signatures = {}
    for path in images:
        parts = re.split(r'(\d+)', path.stem)
        signature = (tuple(parts[::2]), path.suffix)
        signatures.setdefault(signature, []).append((path, tuple(parts[1::2])))
    proposals = []
    for (words, suffix), rows in signatures.items():
        groups = [rows]
        if len(words) > 1:
            last_indices = [numbers[-1] for _, numbers in rows]
            if len(set(last_indices)) < len(rows):
                partitions = {}
                for row in rows:
                    partitions.setdefault(row[1][:-1], []).append(row)
                groups = list(partitions.values())
        for group in groups:
            group.sort(key=lambda row: tuple(int(number) for number in row[1]))
            columns = list(zip(*(numbers for _, numbers in group))) if group[0][1] else []
            pattern = glob_escape(words[0])
            for index, column in enumerate(columns):
                pattern += ('[0-9]*' if len(set(column)) > 1 else glob_escape(column[0]))
                pattern += glob_escape(words[index + 1])
            pattern += glob_escape(suffix)
            varying = [index for index, column in enumerate(columns) if len(set(column)) > 1]
            frame_regex = ''
            if varying:
                frame_index = varying[-1]
                prefix = re.escape(words[0])
                for index in range(frame_index):
                    prefix += (r'\d+' if index in varying else re.escape(columns[index][0]))
                    prefix += re.escape(words[index + 1])
                frame_regex = prefix + r'(\d+)'
            actual = {path.name for path in folder.glob(pattern) if path.is_file()}
            expected = {path.name for path, _ in group}
            if actual != expected:
                # Ambiguous glob: expose the files separately instead of
                # silently including another acquisition in a DIC run.
                for path, _ in group:
                    proposals.append({'pattern': glob_escape(path.name), 'count': 1,
                                      'first_image': path.name, 'example': path.name,
                                      'frame_regex': ''})
                continue
            proposals.append({'pattern': pattern, 'count': len(group),
                              'first_image': group[0][0].name,
                              'example': group[-1][0].name,
                              'frame_regex': frame_regex})
    proposals.sort(key=lambda row: (-row['count'], row['pattern'].casefold()))
    return {'directory': str(folder), 'series': proposals, 'image_count': len(images)}


def inventory(folder, directory, pattern, source, frame_regex, fps, reference=None, *, visible=False, exclude_names=(), inspect_pixels=True, allowed_suffixes=None):
    """List original images with absolute paths, (H,W), seconds and time source."""
    image_dir = resolve_path(folder, directory)
    if not image_dir.is_dir():
        raise ValueError(f'Dossier image introuvable : {image_dir}')
    files = list(image_dir.glob(pattern))
    if allowed_suffixes is not None:
        allowed = {suffix.lower() for suffix in allowed_suffixes}
        files = [path for path in files if path.suffix.lower() in allowed]
    if reference:
        ref = Path(reference)
        ref = ref if ref.is_absolute() else image_dir / ref
        ref = ref.resolve()
        files = [p for p in files if p.resolve() != ref]
        if not ref.is_file():
            raise ValueError(f'Référence VIS introuvable : {ref}')
    if exclude_names:
        files = [p for p in files if p.name not in exclude_names]
    if not files:
        raise ValueError(f'Aucune image pour {image_dir / pattern}')
    expression = re.compile(frame_regex) if source == 'filename' else None
    if source == 'filename' and fps <= 0:
        raise ValueError('Cadence positive requise pour les numéros de trames')
    rows = []
    for path in files:
        # The directory is already absolute. Resolving each frame causes many
        # filesystem calls on network-backed image series.
        path = path.resolve() if inspect_pixels else path.absolute()
        shape = read_image(path, visible=visible).shape if inspect_pixels else image_shape(path, visible=visible)
        if source == 'filename':
            match = expression.search(path.name)
            if not match:
                raise ValueError(f'Numéro de trame absent du nom : {path}')
            frame = int(match.group(1))
            seconds = frame / fps
        elif source == 'metadata':
            frame = None
            seconds = _metadata_time(path)
        else:
            raise ValueError(f'Source temporelle inconnue : {source}')
        stat = path.stat()
        rows.append({'path': str(path), 'shape': list(shape), 'time_s': float(seconds),
                     'time_source': source, 'frame': frame, 'size': stat.st_size,
                     'mtime_ns': stat.st_mtime_ns})
    rows.sort(key=lambda row: row['time_s'])
    times = [row['time_s'] for row in rows]
    warnings = []
    if len(times) != len(set(times)):
        raise ValueError('Temps d’acquisition dupliqués ; corriger les noms ou métadonnées')
    if len({tuple(row['shape']) for row in rows}) != 1:
        raise ValueError('Dimensions des images incohérentes dans la séquence')
    frames = [row['frame'] for row in rows]
    if all(number is not None for number in frames):
        missing = sorted(set(range(min(frames), max(frames) + 1)) - set(frames))
        if missing:
            warnings.append({'kind': 'missing_frames', 'frames': missing})
    original_paths = [p.resolve() if inspect_pixels else p.absolute() for p in files]
    if original_paths != [Path(row['path']) for row in rows]:
        warnings.append({'kind': 'reordered_by_time'})
    return {'images': rows, 'warnings': warnings}


def thermal_inventory(folder, directory, pattern, source, frame_regex, fps,
                     exclude_names=(), *, inspect_pixels=True):
    """Inventory the active scalar TIFF temperature sequence.

    Exclusions are file basenames and must belong to the selected TIFF glob.
    This keeps disabled frames out of temporal interpolation and provenance.
    """
    if not pattern or Path(pattern).name != pattern:
        raise ValueError('Motif TH invalide')
    image_dir = resolve_path(folder, directory)
    available = {path.name for path in image_dir.glob(pattern)
                 if path.is_file() and path.parent == image_dir
                 and path.suffix.lower() in {'.tif', '.tiff'}}
    unknown = set(exclude_names) - available
    if unknown:
        raise ValueError('Images TH désactivées absentes de la série : '
                         + ', '.join(sorted(unknown)))
    if not (available - set(exclude_names)):
        raise ValueError('Aucune image TH active dans la séquence')
    result = inventory(folder, directory, pattern, source, frame_regex, fps,
                       exclude_names=exclude_names, inspect_pixels=inspect_pixels,
                       allowed_suffixes={'.tif', '.tiff'})
    if any(Path(row['path']).parent != image_dir for row in result['images']):
        raise ValueError('La série TH doit contenir des TIFF directement dans le dossier choisi')
    return result


def morphology(mask, operation='none', radius_px=0):
    """Apply a disk on a binary VIS mask, with outside pixels false."""
    mask = np.asarray(mask, dtype=bool)
    if mask.ndim != 2:
        raise ValueError('Le masque doit être 2D')
    if radius_px < 0 or int(radius_px) != radius_px:
        raise ValueError('Rayon entier positif requis')
    if operation not in ('none', 'dilation', 'erosion'):
        raise ValueError('Opération ROI inconnue')
    if radius_px == 0 or operation == 'none':
        result = mask.copy()
    else:
        r = int(radius_px)
        y, x = np.ogrid[-r:r+1, -r:r+1]
        kernel = ((x*x + y*y) <= r*r).astype(np.uint8)
        source = mask.astype(np.uint8)
        code = cv2.MORPH_DILATE if operation == 'dilation' else cv2.MORPH_ERODE
        result = cv2.morphologyEx(source, code, kernel, borderType=cv2.BORDER_CONSTANT,
                                  borderValue=0).astype(bool)
    if not result.any():
        raise ValueError('La ROI finale est vide ; réduire l’érosion ou corriger le masque')
    count, labels = cv2.connectedComponents(result.astype(np.uint8))
    return result, {'area_initial_px': int(mask.sum()), 'area_final_px': int(result.sum()),
                    'components': count - 1}


def mask_from_shapes(shapes, shape_hw):
    """Rasterize rectangle and ellipse ROI shapes at native VIS pixel centers.

    ``shape_hw`` is ``(height, width)``. Shape coordinates ``x0,y0,x1,y1``
    are finite floating-point VIS pixels; integer array indices denote pixel
    centers. Shapes are applied in order to an initially empty mask.
    """
    if (len(shape_hw) != 2 or any(not isinstance(value, (int, np.integer))
                                  or value <= 0 for value in shape_hw)):
        raise ValueError('Dimensions VIS invalides pour le dessin ROI')
    height, width = map(int, shape_hw)
    if not isinstance(shapes, list):
        raise ValueError('Les formes ROI doivent être une liste')
    mask = np.zeros((height, width), dtype=bool)
    for index, shape in enumerate(shapes):
        if not isinstance(shape, dict):
            raise ValueError(f'Forme ROI invalide à la position {index}')
        kind = shape.get('kind')
        operation = shape.get('operation')
        if kind not in ('rectangle', 'ellipse'):
            raise ValueError(f'Type de forme ROI inconnu : {kind}')
        if operation not in ('add', 'subtract'):
            raise ValueError(f'Opération de forme ROI inconnue : {operation}')
        try:
            x0, y0, x1, y1 = (float(shape[key]) for key in ('x0', 'y0', 'x1', 'y1'))
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(f'Coordonnées ROI invalides à la position {index}') from error
        if not np.isfinite([x0, y0, x1, y1]).all():
            raise ValueError(f'Coordonnées ROI non finies à la position {index}')
        if x0 == x1 or y0 == y1:
            raise ValueError('Une forme ROI doit avoir une largeur et une hauteur non nulles')
        left, right = sorted((x0, x1))
        top, bottom = sorted((y0, y1))
        left, right = max(0.0, left), min(width - 1.0, right)
        top, bottom = max(0.0, top), min(height - 1.0, bottom)
        selected = np.zeros_like(mask)
        if left <= right and top <= bottom:
            xs = np.arange(max(0, int(np.ceil(left))), min(width, int(np.floor(right)) + 1))
            ys = np.arange(max(0, int(np.ceil(top))), min(height, int(np.floor(bottom)) + 1))
            if xs.size and ys.size:
                xx, yy = np.meshgrid(xs, ys)
                if kind == 'rectangle':
                    selected[np.ix_(ys, xs)] = True
                else:
                    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
                    rx, ry = abs(x1 - x0) / 2, abs(y1 - y0) / 2
                    inside = ((xx - cx) / rx) ** 2 + ((yy - cy) / ry) ** 2 <= 1.0
                    selected[np.ix_(ys, xs)] = inside
        if operation == 'add':
            mask |= selected
        else:
            mask &= ~selected
    return mask


def save_mask(path, mask):
    """Save a binary TIFF ROI with an explicit white-foreground marker."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tifffile.imwrite(path, (np.asarray(mask, dtype=bool) * 255).astype(np.uint8),
                     description=ROI_MASK_DESCRIPTION)
    return path
