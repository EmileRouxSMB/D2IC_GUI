"""Shared VIS photometric masks and identities for mesh previews.

Geometry remains in native VIS pixels. Photometric masks are prepared on the
binned solver grid; display expansion restores the original shape, including
empty margins for incomplete edge blocks. File decoding and HTTP rendering
remain responsibilities of the callers.
"""

from __future__ import annotations

import hashlib

import numpy as np

from .project import resolve_path


def photometric_mask(mask, *, image_binning, roi_erosion_px,
                     remove_islands, min_island_area_px):
    """Return the solver-grid observation mask for a validated native ROI.

    Preserve the D2IC order: remove small native-pixel islands, bin, crop to
    complete blocks, then erode observations. The erosion radius is expressed
    in original VIS pixels, not binned pixels. Caller-specific validation and
    error messages stay with the draft form, image route or readiness check.
    D2IC imports remain deferred so importing this module does not initialize
    the numerical dependencies. Its private island helper is isolated here.
    """
    from d2ic.io.app_utils import erode_correlation_roi
    from d2ic.io.binning import bin_mask
    from d2ic.mesh.generation import _remove_small_components

    observation_mask = mask
    if remove_islands:
        observation_mask = _remove_small_components(mask, min_island_area_px)
    reduced = bin_mask(observation_mask, image_binning)
    height, width = mask.shape
    reduced = reduced[:height // image_binning, :width // image_binning]
    return erode_correlation_roi(reduced, roi_erosion_px,
                                image_binning=image_binning)


def native_photometric_mask(mask, shape_hw, image_binning):
    """Expand a solver-grid mask for display without interpolating its values.

    Pixels outside complete binning blocks remain false; this display mask
    never replaces either the native geometric ROI or the solver-grid mask.
    """
    height, width = shape_hw
    h, w = height // image_binning, width // image_binning
    native = np.zeros(shape_hw, dtype=bool)
    native[:h * image_binning, :w * image_binning] = np.repeat(
        np.repeat(mask, image_binning, axis=0), image_binning, axis=1)
    return native


def mesh_preview_identity(folder, settings, *, require_source=False):
    """Return the existing mask digests and controls identifying a preview.

    Producers require the source mask to exist. Readers retain the historical
    ``None`` identity for a missing source and let their own validation report
    a stale preview. The photometric radius is deliberately absent: it does
    not change geometry and must not invalidate a mesh preview.
    """
    final_mask = resolve_path(folder, settings['roi']['final_mask'])
    source_mask = resolve_path(folder, settings['roi']['initial_mask'])
    return {
        'mask_sha256': hashlib.sha256(final_mask.read_bytes()).hexdigest(),
        'source_mask_sha256': (hashlib.sha256(source_mask.read_bytes()).hexdigest()
                               if require_source or source_mask.is_file() else None),
        'element_size_px': settings['mesh']['element_size_px'],
        'image_binning': settings['dic']['image_binning'],
        'remove_islands': settings['mesh']['remove_islands'],
        'min_island_area_px': settings['mesh']['min_island_area_px'],
    }
