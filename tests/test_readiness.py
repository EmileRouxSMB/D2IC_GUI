"""Readiness reporting and launch guard for study preparation."""

import json
from copy import deepcopy

import numpy as np
from fastapi.testclient import TestClient

from D2IC_GUI.imaging import image_shape, save_mask
from D2IC_GUI.project import create_project, load_project, save_project
from D2IC_GUI.schema import defaults
from D2IC_GUI.server import create_app


def _study(tmp_path):
    from D2IC_GUI.examples.generate_synthetic_study import generate_study

    source = tmp_path / "sources"
    generate_study(source)
    folder = tmp_path / "study"
    config = create_project(folder)
    config["paths"].update(visible_dir=str(source / "VIS"),
                           reference_image="vis_0000_tick0000.tif",
                           visible_pattern="vis_*.tif")
    config["time"].update(visible_frame_regex=r"tick(\d+)", visible_fps=100.0)
    save_project(folder, config)
    return folder, config


def test_readiness_reports_invalid_form_and_optional_pixel_scale(tmp_path):
    folder, config = _study(tmp_path)
    client = TestClient(create_app(folder))

    response = client.post("/api/readiness", json={"config": {"paths": {"visible_fps": -1}}})
    assert response.status_code == 200
    report = response.json()
    assert not report["ready"]
    assert any(item["view"] == "VIS" for item in report["required"])
    assert {step["view"]: step["status"] for step in report["steps"]}["Thermique"] == "inactive"

    # Once the form is valid, pixel-scale work does not prevent a px run.
    report = client.post("/api/readiness", json={"config": config}).json()
    assert any("facultative" in item["message"] for item in report["optional"])


def test_readiness_requires_final_roi_shape_and_current_mesh_preview(tmp_path):
    folder, config = _study(tmp_path)
    client = TestClient(create_app(folder))
    report = client.post("/api/readiness", json={"config": config}).json()
    assert not report["ready"]
    assert any(item["view"] == "ROI" for item in report["required"])

    mask = np.ones(image_shape(folder.parent / "sources" / "VIS" / config["paths"]["reference_image"], visible=True), dtype=bool)
    save_mask(folder / "roi" / "mask_initial.tif", mask)
    save_mask(folder / "roi" / "mask_final.tif", mask)
    save_project(folder, config)
    report = client.post("/api/readiness", json={"config": config}).json()
    assert any("Aperçu du maillage absent" in item["message"] for item in report["required"])
    assert client.post("/api/mesh/preview").status_code == 200
    assert client.post("/api/readiness", json={"config": config}).json()["ready"]

    config["mesh"]["element_size_px"] += 1
    report = client.post("/api/readiness", json={"config": config}).json()
    assert any("périmé" in item["message"] for item in report["required"])



def test_changed_binning_explains_how_to_unblock_launch(tmp_path):
    folder, config = _study(tmp_path)
    shape = image_shape(folder.parent / "sources" / "VIS" / config["paths"]["reference_image"], visible=True)
    mask = np.ones(shape, dtype=bool)
    save_mask(folder / "roi" / "mask_initial.tif", mask)
    save_mask(folder / "roi" / "mask_final.tif", mask)
    client = TestClient(create_app(folder))
    assert client.post("/api/mesh/preview").status_code == 200
    config["dic"]["image_binning"] = 2
    save_project(folder, config)
    response = client.post("/api/runs", json={"config": config})
    assert response.status_code == 400
    assert "binning 1 → 2" in response.json()["detail"]
    assert "Mailler" in response.json()["detail"]
    assert not (folder / "runs").exists()
    assert client.post("/api/mesh/preview").status_code == 200
    assert client.post("/api/readiness", json={"config": config}).json()["ready"]


def test_mm_output_requires_confirmed_scale(tmp_path):
    folder, config = _study(tmp_path)
    config["output"]["paraview_length_unit"] = "mm"
    client = TestClient(create_app(folder))
    report = client.post("/api/readiness", json={"config": config}).json()
    assert not report["ready"]
    assert any(item["view"] == "Échelle" for item in report["required"])


def test_launch_starts_only_after_readiness_passes(tmp_path, monkeypatch):
    import D2IC_GUI.server as server

    folder, config = _study(tmp_path)
    shape = image_shape(folder.parent / "sources" / "VIS" / config["paths"]["reference_image"], visible=True)
    mask = np.ones(shape, dtype=bool)
    save_mask(folder / "roi" / "mask_initial.tif", mask)
    save_mask(folder / "roi" / "mask_final.tif", mask)
    save_project(folder, config)
    client = TestClient(create_app(folder))
    assert client.post("/api/mesh/preview").status_code == 200

    class FakeRun:
        name = "fake"

    monkeypatch.setattr(server, "prepare_run", lambda _: FakeRun())
    monkeypatch.setattr(server, "start_run", lambda _: 123)
    response = client.post("/api/runs", json={"config": config})
    assert response.status_code == 200
    assert response.json() == {"id": "fake", "state": "running", "pid": 123}


def test_thermal_approval_digest_and_nan_synchronization_warning(tmp_path):
    folder, config = _study(tmp_path)
    config["project"]["mode"] = "dic_thermal"
    thermal_defaults = defaults("dic_thermal")
    for section in ("thermal", "registration", "synchronization"):
        config[section] = thermal_defaults[section]
    config["thermal"].update(image_dir=str(folder.parent / "sources" / "TH"),
                             image_pattern="th_*.tif", frame_regex=r"th_(\d+)",
                             thermal_fps=10.0)
    shape = image_shape(folder.parent / "sources" / "VIS" / config["paths"]["reference_image"], visible=True)
    mask = np.ones(shape, dtype=bool)
    save_mask(folder / "roi" / "mask_initial.tif", mask)
    save_mask(folder / "roi" / "mask_final.tif", mask)
    save_project(folder, config)
    client = TestClient(create_app(folder))
    assert client.post("/api/mesh/preview").status_code == 200
    points = [{"visible": [x, y], "thermal": [x * 63 / 127, y * 47 / 95]}
              for x, y in ((10, 10), (110, 10), (10, 80), (110, 80))]
    assert client.post("/api/registration/fit", json={"points": points, "model": "affine"}).status_code == 200
    assert client.post("/api/registration/approve", json={"points": points, "model": "affine"}).status_code == 200

    config = load_project(folder)
    report = client.post("/api/readiness", json={"config": config}).json()
    assert report["ready"]
    for stride, event, expected in [(1, 35, True), (2, 35, False), (1, 0, False)]:
        event_config = deepcopy(config)
        event_config["dic"]["image_stride"] = stride
        event_config["synchronization"].update(method="event_frames", visible_event_frame=event,
                                               thermal_event_frame=0)
        event_report = client.post("/api/readiness", json={"config": event_config}).json()
        assert event_report["ready"] is expected
        if not expected:
            assert any(item["view"] == "Synchro" for item in event_report["required"])
    shifted = {**config, "synchronization": {**config["synchronization"], "thermal_offset_s": -10.0}}
    report = client.post("/api/readiness", json={"config": shifted}).json()
    assert report["ready"]
    assert any("NaN" in item["message"] for item in report["optional"])
    assert next(step for step in report["steps"] if step["view"] == "Synchro")["status"] == "warning"

    calibration = folder / "calibration" / "visible_thermal.json"
    calibration.write_text(calibration.read_text() + " ")
    report = client.post("/api/readiness", json={"config": config}).json()
    assert not report["ready"]
    assert any(item["view"] == "Thermique" and "modifiée après approbation" in item["message"]
               for item in report["required"])


def test_launch_refuses_blocked_saved_study_without_freezing_run(tmp_path):
    folder, config = _study(tmp_path)
    client = TestClient(create_app(folder))
    response = client.post("/api/runs", json={"config": config})
    assert response.status_code == 400
    assert "étapes obligatoires" in response.json()["detail"].lower()
    assert not (folder / "runs").exists()


def test_morphology_and_empty_photometric_support_block_launch(tmp_path):
    folder, config = _study(tmp_path)
    mask = np.pad(np.ones((52, 72), bool), ((22, 22), (28, 28)))
    save_mask(folder / "roi" / "mask_initial.tif", mask)
    save_mask(folder / "roi" / "mask_final.tif", mask)
    client = TestClient(create_app(folder))
    assert client.post("/api/mesh/preview").status_code == 200
    assert client.post("/api/readiness", json={"config": config}).json()["ready"]
    for section, values in [("roi", {"operation": "erosion", "radius_px": 2}),
                            ("dic", {"roi_erosion_px": 10000.0})]:
        changed = deepcopy(config)
        changed[section].update(values)
        report = client.post("/api/readiness", json={"config": changed}).json()
        assert not report["ready"]
        assert any(item["view"] == "ROI" for item in report["required"])
        save_project(folder, changed)
        assert client.post("/api/runs", json={"config": changed}).status_code == 400
        save_project(folder, config)
    assert not (folder / "runs").exists()


def test_active_job_and_result_navigation_states(tmp_path, monkeypatch):
    import D2IC_GUI.readiness as readiness

    folder, config = _study(tmp_path)
    mask = np.ones((96, 128), bool)
    save_mask(folder / "roi" / "mask_initial.tif", mask)
    save_mask(folder / "roi" / "mask_final.tif", mask)
    client = TestClient(create_app(folder))
    assert client.post("/api/mesh/preview").status_code == 200
    run = folder / config["paths"]["output_dir"] / "test-run"
    run.mkdir(parents=True)
    status = run / "status.json"
    status.write_text(json.dumps({"state": "running", "pid": 123}))
    monkeypatch.setattr(readiness, "worker_alive", lambda pid: True)
    report = client.post("/api/readiness", json={"config": config}).json()
    assert not report["ready"]
    assert any(item["view"] == "Job Manager" for item in report["required"])
    assert json.loads(status.read_text())["state"] == "running"
    status.write_text(json.dumps({"state": "completed"}))
    report = client.post("/api/readiness", json={"config": config}).json()
    assert report["ready"]
    states = {step["view"]: step["status"] for step in report["steps"]}
    assert states["Résultats"] == states["Export"] == "complete"
    assert states["Thermique"] == states["Synchro"] == "inactive"
    # A malformed output option remains red even with no completed result.
    invalid = deepcopy(config)
    invalid["output"]["export_vtu"] = False
    report = client.post("/api/readiness", json={"config": invalid}).json()
    assert next(step for step in report["steps"] if step["view"] == "Export")["status"] == "blocked"


def _ready_job_study(tmp_path):
    folder, config = _study(tmp_path)
    shape = image_shape(folder.parent / 'sources' / 'VIS' / config['paths']['reference_image'], visible=True)
    mask = np.ones(shape, dtype=bool)
    save_mask(folder / 'roi' / 'mask_initial.tif', mask)
    save_mask(folder / 'roi' / 'mask_final.tif', mask)
    client = TestClient(create_app(folder))
    assert client.post('/api/mesh/preview').status_code == 200
    return folder, config, client


def test_prepare_blocked_job_keeps_errors_on_a_deletable_row(tmp_path, monkeypatch):
    import D2IC_GUI.server as server

    folder, config = _study(tmp_path)
    client = TestClient(create_app(folder))
    monkeypatch.setattr(server, 'start_run', lambda *args: (_ for _ in ()).throw(AssertionError('Must not launch')))
    response = client.post('/api/runs/prepare', json={'config': config})
    assert response.status_code == 200
    job = response.json()
    assert job['state'] == 'blocked'
    assert not job['can_start']
    assert any(item['view'] == 'ROI' for item in job['preparation']['required'])
    listed = client.get('/api/runs').json()['runs']
    assert len(listed) == 1
    assert listed[0]['preparation'] == job['preparation']
    assert client.post(f"/api/runs/{job['id']}/start").status_code == 400
    assert client.delete(f"/api/runs/{job['id']}").status_code == 200


def test_prepare_with_warning_then_explicit_start_uses_frozen_job(tmp_path, monkeypatch):
    import D2IC_GUI.server as server
    from D2IC_GUI.dic_run import write_status

    folder, config, client = _ready_job_study(tmp_path)
    launched = []

    def launch(path):
        launched.append(path)
        write_status(path, 'running', pid=123)
        return 123

    monkeypatch.setattr(server, 'start_run', launch)
    monkeypatch.setattr('D2IC_GUI.dic_run.worker_alive', lambda pid: True)
    job = client.post('/api/runs/prepare', json={'config': config}).json()
    assert job['state'] == 'pending'
    assert job['can_start']
    assert not job['preparation']['required']
    assert job['preparation']['optional']  # px scale is optional
    assert not launched
    run = folder / 'runs' / job['id']
    frozen = (run / 'dic_config.toml').read_text()
    # Changing the live study does not mutate the prepared numerical problem.
    config['dic']['tol'] *= 2
    save_project(folder, config)
    response = client.post(f"/api/runs/{job['id']}/start")
    assert response.status_code == 200
    assert launched == [run]
    assert (run / 'dic_config.toml').read_text() == frozen
    assert client.post(f"/api/runs/{job['id']}/start").status_code == 400
    assert len(launched) == 1
    assert client.get('/api/runs').json()['runs'][0]['preparation']['optional']


def test_changed_source_blocks_prepared_job_and_updates_row(tmp_path, monkeypatch):
    import os
    import D2IC_GUI.server as server

    folder, config, client = _ready_job_study(tmp_path)
    job = client.post('/api/runs/prepare', json={'config': config}).json()
    reference = folder.parent / 'sources' / 'VIS' / config['paths']['reference_image']
    stat = reference.stat()
    os.utime(reference, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1000000))
    monkeypatch.setattr(server, 'start_run', lambda *args: (_ for _ in ()).throw(AssertionError('Must not launch')))
    assert client.post(f"/api/runs/{job['id']}/start").status_code == 400
    listed = client.get('/api/runs').json()['runs'][0]
    assert listed['state'] == 'blocked'
    assert not listed['can_start']
    assert 'Image source modifiée' in listed['preparation']['required'][0]['message']


def test_full_source_validation_failure_keeps_preparation_row(tmp_path, monkeypatch):
    import D2IC_GUI.dic_run as dic_run

    folder, config, client = _ready_job_study(tmp_path)
    def unreadable(*args):
        raise ValueError('Pixels source illisibles')
    monkeypatch.setattr(dic_run, '_snapshot_images', unreadable)
    job = client.post('/api/runs/prepare', json={'config': config}).json()
    assert job['state'] == 'blocked'
    assert 'Pixels source illisibles' in job['preparation']['required'][0]['message']
    assert len(client.get('/api/runs').json()['runs']) == 1


def test_preparing_while_running_does_not_freeze_busy_error(tmp_path, monkeypatch):
    import D2IC_GUI.server as server
    from D2IC_GUI.dic_run import write_status

    folder, config, client = _ready_job_study(tmp_path)
    active = folder / 'runs' / 'active'
    active.mkdir(parents=True)
    write_status(active, 'running', pid=123)
    monkeypatch.setattr('D2IC_GUI.dic_run.worker_alive', lambda pid: True)
    monkeypatch.setattr('D2IC_GUI.readiness.worker_alive', lambda pid: True)
    launched = []
    monkeypatch.setattr(server, 'start_run', lambda path: launched.append(path))
    job = client.post('/api/runs/prepare', json={'config': config}).json()
    assert job['can_start']
    assert not job['preparation']['required']
    assert client.post(f"/api/runs/{job['id']}/start").status_code == 400
    assert not launched
    assert client.get(f"/api/runs/{job['id']}").json()['can_start']


def test_preparation_freezes_the_checked_configuration_during_parallel_save(tmp_path, monkeypatch):
    import D2IC_GUI.readiness as readiness

    folder, config, client = _ready_job_study(tmp_path)
    original = readiness.evaluate_readiness
    def check_then_save(folder, settings, **kwargs):
        report = original(folder, settings, **kwargs)
        changed = deepcopy(settings)
        changed['dic']['image_binning'] = 2
        save_project(folder, changed)
        return report
    monkeypatch.setattr(readiness, 'evaluate_readiness', check_then_save)
    job = client.post('/api/runs/prepare', json={'config': config}).json()
    assert job['can_start']
    assert load_project(folder)['dic']['image_binning'] == 2
    assert load_project(folder / 'runs' / job['id'])['dic']['image_binning'] == 1


def test_mask_changed_between_checks_and_copy_blocks_job(tmp_path, monkeypatch):
    import D2IC_GUI.dic_run as dic_run
    from D2IC_GUI.imaging import read_mask

    folder, config, client = _ready_job_study(tmp_path)
    original = dic_run._snapshot_images
    def change_mask(folder, settings):
        rows = original(folder, settings)
        path = folder / settings['roi']['final_mask']
        mask = read_mask(path)
        mask[0, 0] = not mask[0, 0]
        save_mask(path, mask)
        return rows
    monkeypatch.setattr(dic_run, '_snapshot_images', change_mask)
    job = client.post('/api/runs/prepare', json={'config': config}).json()
    assert not job['can_start']
    assert job['state'] == 'blocked'
    assert 'Masque modifié pendant la préparation' in job['preparation']['required'][0]['message']


def test_delete_waits_for_launch_and_cannot_remove_new_running_job(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    import D2IC_GUI.server as server
    from D2IC_GUI.dic_run import write_status

    folder, config, client = _ready_job_study(tmp_path)
    job = client.post('/api/runs/prepare', json={'config': config}).json()
    started, release = Event(), Event()
    def launch(run):
        started.set()
        assert release.wait(timeout=5)
        write_status(run, 'running', pid=123)
        return 123
    monkeypatch.setattr(server, 'start_run', launch)
    monkeypatch.setattr('D2IC_GUI.dic_run.worker_alive', lambda pid: True)
    with ThreadPoolExecutor(max_workers=2) as pool:
        starting = pool.submit(client.post, f"/api/runs/{job['id']}/start")
        assert started.wait(timeout=5)
        deleting = pool.submit(client.delete, f"/api/runs/{job['id']}")
        try:
            release.set()
            assert starting.result(timeout=5).status_code == 200
            assert deleting.result(timeout=5).status_code == 400
        finally:
            release.set()
    assert (folder / 'runs' / job['id'] / 'manifest.json').is_file()
