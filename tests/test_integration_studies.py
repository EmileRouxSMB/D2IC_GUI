"""Replay both scientific paths from external synthetic TIFFs and config.toml."""

import json
from pathlib import Path
import xml.etree.ElementTree as ET

import meshio
import numpy as np
from fastapi.testclient import TestClient

from D2IC_GUI.dic_run import prepare_run
from D2IC_GUI.examples.generate_synthetic_study import generate_study
from D2IC_GUI.imaging import save_mask
from D2IC_GUI.project import create_project, load_project, save_project
from D2IC_GUI.schema import validate
from D2IC_GUI.server import create_app
from D2IC_GUI.worker import run_worker
from d2ic.io.result_store import open_result_store


def _pvd_times(path):
    root=ET.parse(path).getroot()
    return [float(node.attrib['timestep']) for node in root.findall('.//DataSet')]


def test_replay_dic_and_coupled_studies(tmp_path):
    source=tmp_path/'source';generate_study(source)
    study=tmp_path/'study';config=create_project(study)
    config['paths'].update(visible_dir=str((source/'VIS').resolve()),
        reference_image='vis_0000_tick0000.tif',visible_pattern='vis_*.tif')
    config['time'].update(visible_frame_regex=r'tick(\d+)',visible_fps=100.)
    config['dic']['max_iters']=15
    config['mesh']['element_size_px']=24.
    config['output']['compute_residual_map']=True
    config['runtime'].update(jax_preferred='cpu',jax_fallback='cpu')
    mask=np.pad(np.ones((52,72),bool),((22,22),(28,28)))
    save_mask(study/'roi'/'mask_initial.tif',mask)
    save_mask(study/'roi'/'mask_final.tif',mask)
    save_project(study,config)

    dic_run=prepare_run(study)
    run_worker(dic_run)
    assert json.loads((dic_run/'status.json').read_text())['state']=='completed'
    import tomllib
    with (dic_run/'dic_config.toml').open('rb') as stream:
        output = tomllib.load(stream)['output']
        assert output['keep_results'] is False
        assert output['export_legacy_npz'] is False
    store = dic_run/'results'/'dic_store'
    assert len(list((store/'frames').glob('frame_*.npz'))) == 3
    assert json.loads((store/'progress.json').read_text())['completed_frames'] == 3
    assert json.loads((store/'metadata.json').read_text())['frame_times_s'] == [.15, .35, .45]
    dic_manifest=json.loads((dic_run/'manifest.json').read_text())
    assert all(Path(row['path']).is_absolute() for row in dic_manifest['visible_images'])
    import hashlib
    assert dic_manifest['mask_sha256']==hashlib.sha256((dic_run/'mask_final.tif').read_bytes()).hexdigest()
    assert dic_manifest['software_versions']['D2IC']
    assert _pvd_times(dic_run/'results'/'dic.pvd')==[0.,.15,.35,.45]
    assert len(meshio.read(dic_run/'results'/'dic_reference.vtu').points)>0
    assert not (dic_run/'results'/'dic_results.npz').exists()
    fields=open_result_store(store)
    assert np.allclose(np.median(fields.read_history('u_nodal'),axis=1),[[2,1],[4,2],[6,3]],atol=.15)
    assert np.max(np.abs(np.median(fields.read_history('strain'),axis=1)))<.01
    exported=TestClient(create_app(study)).post(
        f'/api/runs/{dic_run.name}/export',json={'legacy_npz':True})
    assert exported.status_code==200
    assert Path(exported.json()['legacy_npz']).is_file()
    dic_client=TestClient(create_app(study))
    dic_fields=dic_client.get(f'/api/runs/{dic_run.name}/fields').json()
    assert dic_fields['nodes'] > 0 and 'Residual' in dic_fields['fields']
    assert dic_client.get(f'/api/runs/{dic_run.name}/field-image',
                          params={'field':'u_norm','frame':1}).headers['content-type']=='image/png'
    assert dic_client.get(f'/api/runs/{dic_run.name}/field-image',
                          params={'field':'Residual','frame':1}).headers['content-type']=='image/png'
    history=dic_client.get(f'/api/runs/{dic_run.name}/history',params={'node':0}).json()['history']
    assert [row['time_s'] for row in history]==[0.,.15,.35,.45]

    config=load_project(study);config['project']['mode']='dic_thermal';config=validate(config)
    config['thermal'].update(image_dir=str((source/'TH').resolve()),
        image_pattern='th_*.tif',frame_regex=r'th_(\d+)',thermal_fps=10.)
    save_project(study,config)
    client=TestClient(create_app(study))
    points=[{'visible':[x,y],'thermal':[x*63/127,y*47/95]}
            for x,y in ((10,10),(110,10),(10,80),(110,80))]
    assert client.post('/api/registration/fit',json={'points':points,'model':'affine'}).status_code==200
    assert client.post('/api/registration/approve',json={'points':points,'model':'affine'}).status_code==200
    persisted=client.get('/api/registration').json()
    assert persisted['approved'] and len(persisted['points'])==4
    assert persisted['rms_px'] < 1e-8
    coupled=prepare_run(study)
    run_worker(coupled)
    assert json.loads((coupled/'status.json').read_text())['state']=='completed'
    manifest=json.loads((coupled/'manifest.json').read_text())
    assert [row['time_valid'] for row in manifest['thermal_provenance']]==[True,True,False,True]
    assert _pvd_times(coupled/'results'/'dic_coupled.pvd')==[0.,.15,.45]
    assert not (coupled/'results'/'coupled_0002.vtu').exists()
    frame=meshio.read(coupled/'results'/'coupled_0001.vtu')
    assert np.allclose(frame.point_data['Temperature'],20.3,atol=2e-5)
    assert np.allclose(frame.cell_data['Temperature_element'][0],20.3,atol=2e-5)
    assert np.all(frame.point_data['Thermal_valid'])
    coupled_fields=client.get(f'/api/runs/{coupled.name}/fields').json()
    assert 'Temperature' in coupled_fields['fields']
    assert client.get(f'/api/runs/{coupled.name}/field-image',
                      params={'field':'Temperature','frame':1}).headers['content-type']=='image/png'
    coupled_history=client.get(f'/api/runs/{coupled.name}/history',params={'node':0}).json()['history']
    assert np.isclose(coupled_history[1]['Temperature'],20.3,atol=2e-5)
    assert coupled_history[2]['Temperature'] is None
    assert all(Path(row['path']).is_file() for row in manifest['thermal_images'])
    assert not any((study/'runs').rglob('vis_*.tif'))
    assert not any((study/'runs').rglob('th_*.tif'))
