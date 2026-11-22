import csv
import io
import json

import numpy as np
from fastapi.testclient import TestClient

from D2IC_GUI.dic_run import write_status
from D2IC_GUI.project import create_project
from D2IC_GUI.server import create_app
from d2ic.io.result_store import ResultStore


def _client(tmp_path, unit='px'):
    study=tmp_path/'study'; create_project(study)
    run=study/'runs'/'sample'
    store=ResultStore(run/'results'/'dic_store',metadata={'image_shape':[5,5]})
    store.write_mesh(np.array([[0.,0.],[4.,0.],[0.,4.],[4.,4.]]),
                     np.array([[0,1,2],[1,3,2]],dtype=np.int32))
    # u1=x+2y, so its section values are analytically known.
    u=np.array([[0.,0.],[4.,3.],[8.,0.],[12.,0.]])
    store.write_frame(0,u_nodal=u,strain=np.tile([1.,2.,3.],(4,1)))
    store.update_progress(status='completed',total_frames=1,completed_frames=1,last_frame=0)
    (run/'manifest.json').write_text(json.dumps({'mode':'dic','length_unit':unit,'mm_per_pixel':.5,
        'visible_reference':{'time_s':0.},'visible_images':[{'time_s':.25}]}))
    write_status(run,'completed')
    return TestClient(create_app(study)),run


def test_section_affine_scope_units_and_csv(tmp_path):
    client,_=_client(tmp_path,'mm')
    params={'field':'u1','x0':0,'y0':0,'x1':4,'y1':0,'samples':3,'scope':'image','frame':1}
    data=client.get('/api/runs/sample/section',params=params)
    assert data.status_code==200,data.text
    payload=data.json(); profile=payload['profiles'][0]
    assert profile['values']==[0.,1.,2.]
    assert profile['distance']==[0.,1.,2.]
    assert payload['length_unit']=='mm'
    seq=client.get('/api/runs/sample/section',params={**params,'scope':'sequence'}).json()
    assert [p['frame'] for p in seq['profiles']]==[0,1]
    rows=list(csv.reader(io.StringIO(client.get('/api/runs/sample/section.csv',params=params).text)))
    assert rows[0]==['frame','time_s','distance_mm','x_ref_px','y_ref_px','u1_mm']
    assert rows[1][2:]==['0.0','0.0','0.0','0.0']


def test_section_holes_and_outside_mesh_are_null(tmp_path):
    client,_=_client(tmp_path)
    response=client.get('/api/runs/sample/section',params={'field':'E11','frame':1,'x0':-2,'y0':1,'x1':5,'y1':1,'samples':8})
    assert response.status_code==200
    values=response.json()['profiles'][0]['values']
    assert values[:2]==[None,None] and values[-1] is None
    assert all(v==1. for v in values[2:-1])


def test_histories_csv_includes_reference(tmp_path):
    client,_=_client(tmp_path)
    response=client.get('/api/runs/sample/histories.csv?nodes=0,1&field=u1')
    assert response.status_code==200
    rows=list(csv.reader(io.StringIO(response.text)))
    assert rows[0]==['node','frame','time_s','u1_px']
    assert rows[1:]==[['0','0','0.0','0.0'],['0','1','0.25','0.0'],
                      ['1','0','0.0','0.0'],['1','1','0.25','4.0']]
    norm=list(csv.reader(io.StringIO(client.get('/api/runs/sample/histories.csv?nodes=1&field=u_norm').text)))
    assert norm[0]==['node','frame','time_s','u_norm_px']
    assert norm[-1]==['1','1','0.25','5.0']


def test_center_zero_uses_symmetric_colors_and_skips_cache(tmp_path,monkeypatch):
    import matplotlib.axes
    client,run=_client(tmp_path)
    seen=[]; original=matplotlib.axes.Axes.tripcolor
    def capture(self,*args,**kwargs):
        seen.append((kwargs.get('vmin'),kwargs.get('vmax')))
        return original(self,*args,**kwargs)
    monkeypatch.setattr(matplotlib.axes.Axes,'tripcolor',capture)
    response=client.get('/api/runs/sample/field-image?field=u1&frame=1&center_zero=true')
    assert response.status_code==200
    assert seen[-1]==(-12.,12.)
    response=client.get('/api/runs/sample/field-image?field=u1&frame=1&vmin=-2&vmax=7&center_zero=true')
    assert response.status_code==200
    assert seen[-1]==(-7.,7.)
    np.savez(run/'results'/'thermal_fields.npz',temperature=np.full((2,4),20.),
             delta_temperature=np.full((2,4),-3.),temperature_element=np.full((2,2),20.))
    response=client.get('/api/runs/sample/field-image?field=Temperature&frame=1&center_zero=true')
    assert response.status_code==200
    assert seen[-1]==(-20.,20.)


def test_section_preserves_internal_missing_thermal_values(tmp_path):
    client,run=_client(tmp_path)
    temperature=np.array([[20.,20.,20.,20.],[20.,20.,20.,np.nan]])
    np.savez(run/'results'/'thermal_fields.npz',temperature=temperature,
             delta_temperature=temperature-20)
    params={'field':'Temperature','frame':1,'x0':0,'y0':1,'x1':4,'y1':1,'samples':5}
    response=client.get('/api/runs/sample/section',params=params)
    assert response.status_code==200,response.text
    assert response.json()['profiles'][0]['values']==[20.,20.,20.,20.,None]
    params.update(x1=0,y1=1)
    assert client.get('/api/runs/sample/section',params=params).status_code==400
