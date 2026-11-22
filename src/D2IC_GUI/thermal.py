"""Fusion of material DIC points with calibrated thermal image sequences."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import jax
import jax.numpy as jnp

from DICTHFusion.registration import sample_temperature, transform_points


def align_thermal_times(visible_times, thermal_times, *, method="timestamps",
                        visible_frames=None, thermal_frames=None,
                        visible_event_frame=None, thermal_event_frame=None,
                        thermal_offset_s=0.0):
    """Place TH acquisition times on the VIS clock, in seconds.

    ``event_frames`` shifts the observed TH event onto the observed VIS event;
    both frame number arrays must contain their selected event frame.
    """
    vis = _strict_times(visible_times, "visible_times")
    th = _strict_times(thermal_times, "thermal_times")
    offset = float(thermal_offset_s)
    if not np.isfinite(offset):
        raise ValueError("thermal_offset_s must be finite")
    if method == "event_frames":
        if visible_frames is None or thermal_frames is None:
            raise ValueError("event_frames requires both acquisition frame arrays")
        vf = np.asarray(visible_frames)
        tf = np.asarray(thermal_frames)
        if vf.shape != vis.shape or tf.shape != th.shape:
            raise ValueError("acquisition frames must match their time arrays")
        vi = np.flatnonzero(vf == visible_event_frame)
        ti = np.flatnonzero(tf == thermal_event_frame)
        if len(vi) != 1 or len(ti) != 1:
            raise ValueError("each event frame must occur exactly once")
        offset += vis[vi[0]] - th[ti[0]]
    elif method != "timestamps":
        raise ValueError("method must be 'timestamps' or 'event_frames'")
    return th + offset


def thermal_brackets(visible_times, thermal_times, thermal_frames=None, *,
                     thermal_fps=None, period_tolerance=0.05):
    """Find an exact TH frame or two successive acquisitions for each VIS time.

    Return arrays ``left``, ``right``, ``alpha``, ``valid`` and ``reason``.
    Invalid indices are -1; exact matches use the same index twice and alpha 0.
    Times are seconds on an already aligned clock. With acquisition numbers,
    a gap cannot be crossed. For timestamp-only metadata, provide thermal_fps:
    intervals up to (1 + period_tolerance) / thermal_fps are accepted.
    The default 5% allows timestamp jitter while rejecting a missed period.
    No time extrapolation or approximate coincidence is used.
    """
    vis = _strict_times(visible_times, "visible_times")
    th = _strict_times(thermal_times, "thermal_times")
    if thermal_frames is None:
        if thermal_fps is None or not np.isfinite(thermal_fps) or thermal_fps <= 0:
            raise ValueError("timestamp-only TH data require a positive thermal_fps")
        if not np.isfinite(period_tolerance) or not 0 <= period_tolerance < 1:
            raise ValueError("period_tolerance must be finite and in [0, 1)")
        frames = None
        maximum_interval = (1.0 + float(period_tolerance)) / float(thermal_fps)
    else:
        frames = np.asarray(thermal_frames)
        if frames.shape != th.shape or not np.issubdtype(frames.dtype, np.integer):
            raise ValueError("thermal_frames must contain one integer per TH image")
        if np.any(np.diff(frames) <= 0):
            raise ValueError("thermal_frames must increase strictly")
    left = np.full(len(vis), -1, dtype=int)
    right = np.full(len(vis), -1, dtype=int)
    alpha = np.full(len(vis), np.nan)
    reason = np.full(len(vis), "", dtype=object)
    for k, t in enumerate(vis):
        j = int(np.searchsorted(th, t))
        if j < len(th) and th[j] == t:
            left[k] = right[k] = j
            alpha[k] = 0.0
        elif j == 0 or j == len(th):
            reason[k] = "outside_thermal_range"
        elif ((frames is not None and frames[j] != frames[j - 1] + 1)
              or (frames is None and th[j] - th[j - 1] > maximum_interval)):
            reason[k] = "missing_thermal_frame"
        else:
            left[k], right[k] = j - 1, j
            alpha[k] = (t - th[j - 1]) / (th[j] - th[j - 1])
    return {"left": left, "right": right, "alpha": alpha,
            "valid": left >= 0, "reason": reason}


def _strict_times(times, name):
    times = np.asarray(times, dtype=float)
    if times.ndim != 1 or len(times) == 0 or not np.all(np.isfinite(times)):
        raise ValueError(f"{name} must be a nonempty finite 1D array")
    if np.any(np.diff(times) <= 0):
        raise ValueError(f"{name} must increase strictly")
    return times


def _temperature_at_points(visible_xy, matrix, thermal_images, left, right, alpha):
    """Read one or two TH images at the same projected VIS coordinates."""
    xy = np.asarray(visible_xy, dtype=float)
    if left < 0:
        return np.full(xy.shape[:-1], np.nan)
    if left == right:
        return np.asarray(sample_temperature(thermal_images[left],
                                             transform_points(matrix, xy)))
    return np.asarray(sample_thermal_pair(thermal_images[left], thermal_images[right],
                                          matrix, xy, alpha))


@jax.jit
def sample_thermal_pair(first_image, second_image, matrix, visible_xy, alpha):
    """JIT-compatible bilinear TH pair at VIS points (...,2), then linear time.

    The same projected coordinate is used in both images. Either invalid
    bilinear sample yields NaN; alpha is the VIS time weight in [0,1].
    """
    thermal_xy = transform_points(matrix, visible_xy)
    first = sample_temperature(first_image, thermal_xy)
    second = sample_temperature(second_image, thermal_xy)
    return jnp.where(jnp.isfinite(first) & jnp.isfinite(second),
                     (1 - alpha) * first + alpha * second, jnp.nan)


def fuse_thermal_frame(nodes_xy, displacement_xy, matrix, thermal_images,
                       left, right, alpha):
    """Sample TH at material nodes ``X + u`` (N,2), returning T and validity."""
    nodes = np.asarray(nodes_xy, dtype=float)
    displacement = np.asarray(displacement_xy, dtype=float)
    if nodes.ndim != 2 or nodes.shape[1] != 2 or displacement.shape != nodes.shape:
        raise ValueError("nodes and displacement must have shape (N, 2)")
    temperature = _temperature_at_points(nodes + displacement, matrix,
                                          thermal_images, left, right, alpha)
    return temperature, np.isfinite(temperature)


def _quadrature(elements_xy):
    """Return VIS quadrature points and current surface Jacobian weights."""
    corners = elements_xy.shape[1]
    if corners == 3:
        shape = np.array([[2 / 3, 1 / 6, 1 / 6],
                          [1 / 6, 2 / 3, 1 / 6],
                          [1 / 6, 1 / 6, 2 / 3]])
        points = np.einsum("pn,end->epd", shape, elements_xy)
        edge_a = elements_xy[:, 1] - elements_xy[:, 0]
        edge_b = elements_xy[:, 2] - elements_xy[:, 0]
        twice_area = np.abs(np.linalg.det(np.stack((edge_a, edge_b), axis=-1)))
        weights = np.broadcast_to((twice_area / 6)[:, None], points.shape[:2])
        return points, weights
    if corners != 4:
        raise ValueError("elements must be Q4 or T3")
    g = 1 / np.sqrt(3)
    xi_eta = np.array([[-g, -g], [g, -g], [g, g], [-g, g]])
    xi, eta = xi_eta.T
    signs = np.array([[-1, -1], [1, -1], [1, 1], [-1, 1]])
    sx, sy = signs.T
    shape = (1 + xi[:, None] * sx) * (1 + eta[:, None] * sy) / 4
    dxi = sx * (1 + eta[:, None] * sy) / 4
    deta = sy * (1 + xi[:, None] * sx) / 4
    points = np.einsum("pn,end->epd", shape, elements_xy)
    tangent_xi = np.einsum("pn,end->epd", dxi, elements_xy)
    tangent_eta = np.einsum("pn,end->epd", deta, elements_xy)
    jacobian = (tangent_xi[..., 0] * tangent_eta[..., 1]
                - tangent_xi[..., 1] * tangent_eta[..., 0])
    # Mixed signs indicate a folded quadrilateral rather than an area measure.
    folded = np.any(np.sign(jacobian) != np.sign(jacobian[:, :1]), axis=1)
    weights = np.where(folded[:, None], np.nan, np.abs(jacobian))
    return points, weights


def element_mean_temperature(nodes_xy, displacement_xy, elements, matrix,
                             thermal_images, left, right, alpha):
    """Area-weighted T on deformed Q4/T3 elements; any invalid point gives NaN.

    ``nodes_xy`` and ``displacement_xy`` are (N,2) VIS pixels, ``elements``
    is (Ne,3) or (Ne,4). Q4 uses 2x2 Gauss points; T3 uses three points.
    """
    nodes = np.asarray(nodes_xy, dtype=float)
    displacement = np.asarray(displacement_xy, dtype=float)
    cells = np.asarray(elements, dtype=int)
    if nodes.ndim != 2 or nodes.shape[1] != 2 or displacement.shape != nodes.shape:
        raise ValueError("nodes and displacement must have shape (N, 2)")
    if cells.ndim != 2 or cells.shape[1] not in (3, 4):
        raise ValueError("elements must have shape (Ne, 3) or (Ne, 4)")
    if cells.size and (cells.min() < 0 or cells.max() >= len(nodes)):
        raise ValueError("element node index out of bounds")
    points, weights = _quadrature((nodes + displacement)[cells])
    temperature = _temperature_at_points(points, matrix, thermal_images,
                                          left, right, alpha)
    valid = (np.all(np.isfinite(temperature) & np.isfinite(weights) & (weights > 0), axis=1)
             if left >= 0 else np.zeros(len(cells), dtype=bool))
    numerator = np.sum(temperature * weights, axis=1)
    denominator = np.sum(weights, axis=1)
    mean = np.full(len(cells), np.nan)
    np.divide(numerator, denominator, out=mean, where=valid)
    return mean, valid


def fuse_thermal_sequence(visible_times, thermal_times, thermal_frames,
                          thermal_images, nodes_xy, displacements_xy, elements,
                          matrix, *, thermal_fps=None, period_tolerance=0.05):
    """Return all fused states for an in-memory displacement history.

    This compatibility entry point accepts (Nt,N,2), including the reference.
    Workers with a frame reader use iter_thermal_sequence instead, avoiding
    accumulation of the displacement history and the list of thermal states.
    """
    vis = _strict_times(visible_times, "visible_times")
    nodes = np.asarray(nodes_xy, dtype=float)
    u = np.asarray(displacements_xy, dtype=float)
    if u.shape != (len(vis), len(nodes), 2):
        raise ValueError("displacements must have shape (Nt, N, 2)")
    return list(iter_thermal_sequence(
        vis, thermal_times, thermal_frames, thermal_images, nodes, u,
        elements, matrix, thermal_fps=thermal_fps,
        period_tolerance=period_tolerance))


def iter_thermal_sequence(visible_times, thermal_times, thermal_frames,
                          thermal_images, nodes_xy, displacements_xy, elements,
                          matrix, *, thermal_fps=None, period_tolerance=0.05):
    """Yield node/cell temperatures and provenance in VIS time order.

    displacements_xy is an indexable sequence of (N,2) native-pixel fields,
    including reference index zero. Only the current displacement is read;
    reference displacement is forced to zero. T_ref and its element means
    remain alive for delta T, without retaining earlier deformed states.
    The caller must consume each yielded state before requesting the next.
    """
    vis = _strict_times(visible_times, "visible_times")
    brackets = thermal_brackets(vis, thermal_times, thermal_frames,
                                thermal_fps=thermal_fps,
                                period_tolerance=period_tolerance)
    nodes = np.asarray(nodes_xy, dtype=float)
    if len(displacements_xy) != len(vis):
        raise ValueError("displacements must have shape (Nt, N, 2)")
    if len(thermal_images) != len(thermal_times):
        raise ValueError("one thermal image is required per thermal time")
    reference_nodes = reference_cells = None
    for k, t in enumerate(vis):
        displacement = (np.zeros_like(nodes) if k == 0
                        else np.asarray(displacements_xy[k], dtype=float))
        if displacement.shape != nodes.shape:
            raise ValueError("each displacement must have shape (N, 2)")
        left, right = int(brackets["left"][k]), int(brackets["right"][k])
        alpha = float(brackets["alpha"][k])
        temperature, node_valid = fuse_thermal_frame(
            nodes, displacement, matrix, thermal_images, left, right, alpha)
        mean, cell_valid = element_mean_temperature(
            nodes, displacement, elements, matrix, thermal_images, left, right, alpha)
        if k == 0:
            reference_nodes, reference_cells = temperature, mean
        delta = np.where(node_valid & np.isfinite(reference_nodes),
                         temperature - reference_nodes, np.nan)
        delta_mean = np.where(cell_valid & np.isfinite(reference_cells),
                              mean - reference_cells, np.nan)
        yield {
            "time_s": float(t), "left": left, "right": right,
            "alpha": alpha, "time_valid": bool(brackets["valid"][k]),
            "reason": str(brackets["reason"][k]),
            "temperature": temperature, "delta_temperature": delta,
            "thermal_valid": node_valid, "temperature_element": mean,
            "delta_temperature_element": delta_mean,
            "thermal_valid_element": cell_valid,
        }


def write_thermal_vtu(path, nodes_xy, elements, displacement_xy, thermal_state,
                      *, strain=None, length_unit="px", mm_per_pixel=None,
                      scale_confirmed=False):
    """Write coupled fields on the reference VIS mesh as one VTU file."""
    import meshio

    if not thermal_state["time_valid"]:
        raise ValueError("cannot export a VIS time without a TH bracket")
    nodes = np.asarray(nodes_xy, dtype=float)
    cells = np.asarray(elements, dtype=np.int32)
    displacement = np.asarray(displacement_xy, dtype=float)
    if nodes.ndim != 2 or nodes.shape[1] != 2 or displacement.shape != nodes.shape:
        raise ValueError("nodes and displacement must have shape (N, 2)")
    if cells.ndim != 2 or cells.shape[1] not in (3, 4):
        raise ValueError("elements must be T3 or Q4")
    if length_unit == "mm":
        if not scale_confirmed or mm_per_pixel is None or not np.isfinite(mm_per_pixel) or mm_per_pixel <= 0:
            raise ValueError("mm export requires a confirmed positive scale")
        scale = float(mm_per_pixel)
    elif length_unit == "px":
        scale = 1.0
    else:
        raise ValueError("length_unit must be 'px' or 'mm'")
    points = np.column_stack((nodes * scale, np.zeros(len(nodes))))
    vectors = np.column_stack((displacement * scale, np.zeros(len(nodes))))
    point_data = {"Displacement": vectors,
                  "Displacement_magnitude": np.linalg.norm(vectors, axis=1),
                  "Deformed_position": points + vectors,
                  "Temperature": np.asarray(thermal_state["temperature"]),
                  "Delta_temperature": np.asarray(thermal_state["delta_temperature"]),
                  "Thermal_valid": np.asarray(thermal_state["thermal_valid"], dtype=np.uint8)}
    if strain is not None:
        eps = np.asarray(strain)
        if eps.shape != (len(nodes), 3):
            raise ValueError("strain must have shape (N, 3): E11, E22, E12")
        e11, e22, e12 = eps.T
        zero = np.zeros(len(nodes))
        point_data.update({"Strain": np.column_stack((e11, e12, zero, e12, e22, zero,
                                                       zero, zero, zero)),
                           "E11": e11, "E22": e22, "E12": e12})
    cell_data = {"Temperature_element": [np.asarray(thermal_state["temperature_element"])],
                 "Delta_temperature_element": [np.asarray(thermal_state["delta_temperature_element"])],
                 "Thermal_valid_element": [np.asarray(thermal_state["thermal_valid_element"], dtype=np.uint8)]}
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    meshio.write(path, meshio.Mesh(points, [("triangle" if cells.shape[1] == 3 else "quad", cells)],
                                   point_data=point_data, cell_data=cell_data), file_format="vtu")
    return path


def write_thermal_pvd(path, datasets):
    """Write an ordered PVD collection of ``(VIS seconds, VTU path)`` pairs."""
    import xml.etree.ElementTree as ET

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    root = ET.Element("VTKFile", type="Collection", version="0.1", byte_order="LittleEndian")
    collection = ET.SubElement(root, "Collection")
    previous = -np.inf
    for time_s, vtu_path in datasets:
        time_s = float(time_s)
        if not np.isfinite(time_s) or time_s <= previous:
            raise ValueError("PVD VIS times must increase strictly")
        previous = time_s
        target = Path(vtu_path)
        try:
            name = target.relative_to(path.parent).as_posix()
        except ValueError:
            name = target.as_posix()
        ET.SubElement(collection, "DataSet", timestep=f"{time_s:.16g}",
                      group="", part="0", file=name)
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)
    return path
