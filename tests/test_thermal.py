"""Scientific checks for material VIS/TH fusion and ParaView export."""

import xml.etree.ElementTree as ET

import numpy as np
import jax
import jax.numpy as jnp
import pytest

from D2IC_GUI.thermal import (
    align_thermal_times, element_mean_temperature, fuse_thermal_sequence,
    thermal_brackets, sample_thermal_pair, write_thermal_pvd, write_thermal_vtu,
)


def _square():
    return np.array([[1., 1.], [3., 1.], [3., 3.], [1., 3.]])


def test_alignment_and_successive_thermal_brackets():
    shifted = align_thermal_times([10, 11], [30, 30.5, 31],
                                  method="event_frames", visible_frames=[0, 1],
                                  thermal_frames=[4, 5, 6],
                                  visible_event_frame=0, thermal_event_frame=4)
    np.testing.assert_allclose(shifted, [10, 10.5, 11])
    found = thermal_brackets([9, 10, 10.25, 10.75, 11, 12],
                             shifted, [4, 5, 6])
    assert found["valid"].tolist() == [False, True, True, True, True, False]
    assert found["left"].tolist() == [-1, 0, 0, 1, 2, -1]
    np.testing.assert_allclose(found["alpha"][2:4], [0.5, 0.5])
    assert found["reason"][0] == "outside_thermal_range"
    gap = thermal_brackets([0.5, 1.0], [0., 1.], [0, 2])
    assert gap["reason"][0] == "missing_thermal_frame"
    assert gap["valid"][1]


def test_material_transport_bilinear_time_and_reference():
    nodes = _square()
    images = [np.fromfunction(lambda y, x: x + 2 * y + c, (12, 12))
              for c in (0., 10., 20.)]
    transform = np.array([[1., 0., 2.], [0., 1., 1.], [0., 0., 1.]])
    u = np.zeros((3, 4, 2))
    u[0] = 9  # reference displacement must be zero
    u[1:, :, 0] = 1
    states = fuse_thermal_sequence([0., 0.5, 2.], [0., 1., 2.], [0, 1, 2],
                                   images, nodes, u, [[0, 1, 2, 3]], transform)
    expected_ref = nodes[:, 0] + 2 + 2 * (nodes[:, 1] + 1)
    np.testing.assert_allclose(states[0]["temperature"], expected_ref)
    np.testing.assert_allclose(states[0]["delta_temperature"], 0)
    np.testing.assert_allclose(states[1]["temperature"], expected_ref + 6)
    np.testing.assert_allclose(states[1]["delta_temperature"], 6)
    assert (states[1]["left"], states[1]["right"], states[1]["alpha"]) == (0, 1, 0.5)
    assert states[2]["time_valid"]  # exact last TH remains valid


def test_invalid_reference_and_partial_quadrature():
    nodes = _square()
    transform = np.eye(3)
    image = np.full((5, 5), 20.)
    image[1, 1] = np.nan
    states = fuse_thermal_sequence([0., 1.], [1., 2.], [0, 1],
                                   [image, image], nodes, np.zeros((2, 4, 2)),
                                   [[0, 1, 2, 3]], transform)
    assert not states[0]["time_valid"]
    assert np.isnan(states[1]["delta_temperature"]).all()
    assert np.isnan(states[1]["delta_temperature_element"]).all()
    # A quadrature point can fail even when the element's corner nodes are valid.
    sample = np.full((5, 5), 20.)
    sample[2, 2] = np.nan
    mean, valid = element_mean_temperature(nodes, np.zeros_like(nodes), [[0, 1, 2, 3]],
                                           transform, [sample], 0, 0, 0.)
    assert not valid[0] and np.isnan(mean[0])


@pytest.mark.parametrize("cells", [[[0, 1, 2, 3]], [[0, 1, 2]]])
def test_deformed_element_quadrature_constant_and_linear(cells):
    nodes = _square()
    u = np.array([[0., 0.], [1., 0.], [1., 1.], [0., 1.]])
    constant = np.full((10, 10), 17.)
    mean, valid = element_mean_temperature(nodes, u, cells, np.eye(3),
                                           [constant], 0, 0, 0.)
    assert valid[0]
    np.testing.assert_allclose(mean, 17, atol=1e-13)
    gradient = np.fromfunction(lambda y, x: x + y, (10, 10))
    mean, valid = element_mean_temperature(nodes, u, cells, np.eye(3),
                                           [gradient], 0, 0, 0.)
    assert valid[0]
    # Q4 maps an affine parallelogram; T3 uses its first three vertices.
    expected = np.mean((nodes + u)[np.asarray(cells)[0]], axis=0).sum()
    np.testing.assert_allclose(mean, expected, atol=1e-13)


def test_vtu_pvd_fields_and_length_scale(tmp_path):
    meshio = pytest.importorskip("meshio")
    nodes = _square()
    states = fuse_thermal_sequence([0., 1., 2.], [0., 1.], [0, 1],
                                   [np.full((8, 8), 10.), np.full((8, 8), 12.)],
                                   nodes, np.zeros((3, 4, 2)), [[0, 1, 2, 3]],
                                   np.eye(3))
    assert not states[2]["time_valid"]
    files = []
    for k in (0, 1):
        target = tmp_path / f"thermal_{k}.vtu"
        write_thermal_vtu(target, nodes, [[0, 1, 2, 3]], np.ones_like(nodes),
                          states[k], strain=np.zeros((4, 3)), length_unit="mm",
                          mm_per_pixel=0.25, scale_confirmed=True)
        files.append((states[k]["time_s"], target))
    with pytest.raises(ValueError):
        write_thermal_vtu(tmp_path / "invalid.vtu", nodes, [[0, 1, 2, 3]],
                          np.zeros_like(nodes), states[2])
    result = meshio.read(files[1][1])
    np.testing.assert_allclose(result.points[:, :2], nodes * 0.25)
    np.testing.assert_allclose(result.point_data["Displacement"][:, :2], 0.25)
    np.testing.assert_allclose(result.point_data["Delta_temperature"], 2.)
    assert result.cell_data["Temperature_element"][0].shape == (1,)
    assert result.cell_data["Thermal_valid_element"][0][0] == 1
    pvd = write_thermal_pvd(tmp_path / "thermal.pvd", files)
    entries = ET.parse(pvd).findall(".//DataSet")
    assert [float(e.attrib["timestep"]) for e in entries] == [0., 1.]
    assert all((tmp_path / e.attrib["file"]).exists() for e in entries)



def test_reference_interpolation_and_jit_pair():
    nodes = _square()
    images = [np.full((8, 8), 10.), np.full((8, 8), 20.),
              np.full((8, 8), 30.)]
    states = fuse_thermal_sequence([0.5, 1.5], [0., 1., 2.], [0, 1, 2],
                                   images, nodes, np.zeros((2, 4, 2)),
                                   [[0, 1, 2, 3]], np.eye(3))
    np.testing.assert_allclose(states[0]["temperature"], 15.)
    np.testing.assert_allclose(states[0]["delta_temperature"], 0.)
    np.testing.assert_allclose(states[1]["delta_temperature"], 10.)
    np.testing.assert_allclose(states[1]["delta_temperature_element"], 10.)
    kernel = jax.jit(sample_thermal_pair)
    sampled = kernel(jnp.asarray(images[0]), jnp.asarray(images[1]),
                     jnp.eye(3), jnp.asarray(nodes), 0.5)
    np.testing.assert_allclose(sampled, 15.)



def test_missing_frame_and_invalid_projection_do_not_extrapolate():
    nodes = _square()
    images = [np.full((5, 5), 10.), np.full((5, 5), 20.)]
    times = [0., 0.5, 1.]
    states = fuse_thermal_sequence(times, [0., 1.], [0, 2], images, nodes,
                                   np.zeros((3, 4, 2)), [[0, 1, 2, 3]], np.eye(3))
    assert states[1]["reason"] == "missing_thermal_frame"
    assert np.isnan(states[1]["temperature"]).all()
    assert states[2]["time_valid"]  # exact TH remains usable after a gap
    outside = np.array([[1., 0., 20.], [0., 1., 0.], [0., 0., 1.]])
    states = fuse_thermal_sequence([0., 1.], [0., 1.], [0, 1], images, nodes,
                                   np.zeros((2, 4, 2)), [[0, 1, 2, 3]], outside)
    assert not states[0]["thermal_valid"].any()
    assert not states[0]["thermal_valid_element"].any()
    assert np.isnan(states[1]["delta_temperature"]).all()



def test_metadata_thermal_times_use_nominal_50_hz_period():
    times = [0., 0.02, 0.06]
    found = thermal_brackets([0., 0.01, 0.03, 0.06], times,
                             thermal_fps=50.)
    assert found["valid"].tolist() == [True, True, False, True]
    np.testing.assert_allclose(found["alpha"][1], 0.5)
    assert found["reason"][2] == "missing_thermal_frame"
    with pytest.raises(ValueError):
        thermal_brackets([0.01], times)
    nodes = _square()
    states = fuse_thermal_sequence([0., 0.01, 0.03, 0.06], times, None,
                                   [np.full((8, 8), v) for v in (10., 20., 30.)],
                                   nodes, np.zeros((4, 4, 2)),
                                   [[0, 1, 2, 3]], np.eye(3), thermal_fps=50.)
    np.testing.assert_allclose(states[1]["temperature"], 15.)
    assert not states[2]["time_valid"]



def test_metadata_timestamp_jitter_and_missing_period():
    # 50 Hz period is 20 ms; 1 us acquisition jitter is acceptable.
    found = thermal_brackets([0.01, 0.03], [0., 0.020001, 0.060001],
                             thermal_fps=50.)
    assert found["valid"].tolist() == [True, False]
    assert found["reason"][1] == "missing_thermal_frame"
    with pytest.raises(ValueError, match="period_tolerance"):
        thermal_brackets([0.01], [0., 0.02], thermal_fps=50.,
                         period_tolerance=1.)
