from uuid import uuid4
from io import BytesIO
from zipfile import ZipFile
import json
import yaml
import pytest
from fastapi.testclient import TestClient


def hall_body(**changes):
    return {'request_id':str(uuid4()),'name':'Зал на Волге','address':'Кострома, Спортивная, 1',
            'pitch_length_m':41,'pitch_width_m':15.5,'latitude':57.767,'longitude':40.927,
            'surface':'Паркет','description':'Камера на балконе',**changes}


def create_hall(client, **changes):
    response=client.post('/api/v1/halls',json=hall_body(**changes))
    assert response.status_code==201,response.text
    return response.json()


def camera_body(hall, **changes):
    return {'request_id':str(uuid4()),'expected_hall_revision':hall['revision'],'name':'Основная камера',
        'frame_width':1000,'frame_height':500,
        'points':[{'px':[0,0],'m':[0,0]},{'px':[999,0],'m':[41,0]},
                  {'px':[999,499],'m':[41,15.5]},{'px':[0,499],'m':[0,15.5]}],
        'pitch_polygon_px':[[0,0],[999,0],[999,499],[0,499]],**changes}


def test_hall_retry_revision_validation_and_private_catalog(admin_client):
    body=hall_body()
    first=admin_client.post('/api/v1/halls',json=body)
    assert first.status_code==201,first.text
    hall=first.json()
    assert admin_client.post('/api/v1/halls',json=body).json()==hall
    assert admin_client.get('/api/v1/halls').json()['total']==1
    assert hall['pitch_length_m']==41 and hall['pitch_width_m']==15.5
    assert admin_client.post('/api/v1/halls',json={**body,'name':'Другой'}).status_code==409
    updated=admin_client.put('/api/v1/halls/'+hall['id'],json={**body,'request_id':str(uuid4()),
        'expected_revision':hall['revision'],'address':'Новый адрес','archived':False})
    assert updated.status_code==200,updated.text
    assert updated.json()['revision']==hall['revision']+1
    assert admin_client.put('/api/v1/halls/'+hall['id'],json={**body,'request_id':str(uuid4()),
        'expected_revision':hall['revision'],'archived':False}).status_code==409
    for fields in [{'pitch_length_m':0},{'pitch_width_m':-1},{'address':'  '},
                   {'latitude':91},{'longitude':181},{'latitude':None}, {'pitch_length_m':'NaN'}]:
        assert admin_client.post('/api/v1/halls',json=hall_body(**fields)).status_code==422
    with TestClient(admin_client.app) as guest:
        assert guest.get('/api/v1/halls').status_code==401


def test_match_pins_hall_and_camera_and_exports_real_cv_config(admin_client,match_factory,send_command,tmp_path):
    hall=create_hall(admin_client)
    body=camera_body(hall)
    response=admin_client.post(f"/api/v1/halls/{hall['id']}/camera-profiles",json=body)
    assert response.status_code==201,response.text
    camera=response.json()
    assert admin_client.post(f"/api/v1/halls/{hall['id']}/camera-profiles",json=body).json()==camera
    assert camera['leave_one_out_error_m'] is None
    m=match_factory(hall_id=hall['id'],camera_profile_id=camera['id'])
    assert m['hall_snapshot']['pitch_length_m']==41
    assert m['venue_label']==hall['name']
    endpoint=f"/api/v1/matches/{m['id']}/cv-config"
    archive=admin_client.get(endpoint)
    assert archive.status_code==200,archive.text
    with ZipFile(BytesIO(archive.content)) as zipped:
        assert set(zipped.namelist())=={'venue.yaml','homography.json','pitch_polygon.json','source.json'}
        for name in zipped.namelist(): (tmp_path/name).write_bytes(zipped.read(name))
        config=yaml.safe_load(zipped.read('venue.yaml'))
        assert config['pitch']=={'length_m':41,'width_m':15.5}
        assert config['processing']['camera_profile_id']==camera['id']
        assert json.loads(zipped.read('source.json'))['match_id']==m['id']
    from aifootball.venue import load_venue
    from aifootball.state.project import project_tracks
    from aifootball.geometry.homography import apply_homography
    import numpy as np
    venue=load_venue(tmp_path)
    assert venue.length_m==41 and venue.frame_width==1000
    assert np.allclose(apply_homography(venue.H,[[999,499]]),[[41,15.5]])
    import polars as pl
    state=project_tracks(pl.DataFrame({'frame_id':[1],'ts':[0.1],'track_id':[1],
        'role':['player'],'team':['A'],'foot_x':[999.0],'foot_y':[499.0],'in_pitch':[True]}),venue)
    assert np.allclose(state.select('x_m','y_m').to_numpy(),[[41,15.5]])
    body=hall_body(request_id=str(uuid4()),expected_revision=hall['revision'],pitch_length_m=42,archived=False)
    changed=admin_client.put('/api/v1/halls/'+hall['id'],json=body)
    assert changed.status_code==200,changed.text
    saved=admin_client.get('/api/v1/matches/'+m['id']).json()
    assert saved['hall_snapshot']['pitch_length_m']==41
    assert admin_client.get(endpoint).content==archive.content
    profiles=admin_client.get(f"/api/v1/halls/{hall['id']}/camera-profiles").json()['items']
    assert profiles[0]['matches_current_dimensions'] is False
    assert send_command(saved,'update_match',{'hall_id':hall['id'],'camera_profile_id':camera['id']}).status_code==200
    fresh=match_factory(hall_id=hall['id'])
    assert fresh['hall_snapshot']['pitch_length_m']==42
    assert send_command(fresh,'update_match',{'camera_profile_id':camera['id']}).status_code==422


@pytest.mark.parametrize('changes',[
    {'points':[{'px':[0,0],'m':[0,0]}]*4},
    {'points':[{'px':[i,i],'m':[i,i]} for i in range(4)]},
    {'pitch_polygon_px':[[0,0],[999,499],[999,0],[0,499]]},
    {'pitch_polygon_px':[[0,0],[1,1],[2,2]]},
    {'frame_width':10},
    {'points':[{'px':[0,0],'m':[0,0]},{'px':[999,0],'m':[41,15.5]},
               {'px':[999,499],'m':[41,0]},{'px':[0,499],'m':[0,15.5]}]},
    {'points':[{'px':[0,0],'m':[50,0]},{'px':[999,0],'m':[41,0]},
               {'px':[999,499],'m':[41,15.5]},{'px':[0,499],'m':[0,15.5]}]},
])
def test_camera_rejects_invalid_geometry(admin_client,changes):
    hall=create_hall(admin_client)
    response=admin_client.post(f"/api/v1/halls/{hall['id']}/camera-profiles",json=camera_body(hall,**changes))
    assert response.status_code==422,response.text
    assert admin_client.get(f"/api/v1/halls/{hall['id']}/camera-profiles").json()['total']==0


def test_camera_foreign_archived_hall_and_required_selection(admin_client,match_factory,send_command):
    a=create_hall(admin_client); b=create_hall(admin_client,name='Другой зал')
    camera=admin_client.post(f"/api/v1/halls/{b['id']}/camera-profiles",json=camera_body(b)).json()
    m=match_factory(hall_id=a['id'])
    assert send_command(m,'update_match',{'camera_profile_id':camera['id']}).status_code==422
    assert send_command(m,'update_match',{'hall_id':None}).status_code==422
    url=f"/api/v1/tournaments/{m['tournament_id']}/matches"
    body={key:m[key] for key in ['home_entry_id','away_entry_id','regulation_id','scheduled_at']}
    assert admin_client.post(url,json=body).status_code==422
    assert admin_client.get('/api/v1/matches/'+m['id']+'/cv-config').status_code==422
    archived=admin_client.put('/api/v1/halls/'+a['id'],json={**hall_body(),
        'expected_revision':a['revision'],'archived':True}).json()
    assert archived['archived']
    assert admin_client.post(url,json={**body,'hall_id':a['id']}).status_code==422
    assert admin_client.get('/api/v1/matches/'+m['id']).json()['hall_snapshot']['name']==a['name']
    with TestClient(admin_client.app) as guest:
        public=guest.get('/api/v1/public/matches/'+m['id']).json()
        assert public['hall']['id']==a['id'] and public['hall']['address']==a['address']
        assert 'description' not in public['hall']
        assert guest.get('/api/v1/matches/'+m['id']+'/cv-config').status_code==401


def test_camera_versions_calibration_and_stale_hall_revision(admin_client,match_factory):
    hall=create_hall(admin_client)
    path=f"/api/v1/halls/{hall['id']}/camera-profiles"
    calibration={'K':[[1000,0,500],[0,1000,250],[0,0,1]],'dist':[0,0,0,0,0]}
    first=admin_client.post(path,json=camera_body(hall,calibration=calibration)).json()
    assert first['version']==1
    # Removing a corner must not leave three collinear points on a diagonal.
    extra={'px':[999*0.37,499*0.43],'m':[41*0.37,15.5*0.43]}
    second=admin_client.post(path,json=camera_body(hall,points=[*camera_body(hall)['points'],extra],calibration=calibration))
    assert second.status_code==201,second.text
    second=second.json()
    assert second['version']==2 and second['id']!=first['id']
    assert second['leave_one_out_error_m']==pytest.approx(0,abs=1e-4)
    assert admin_client.post(path,json=camera_body(hall,expected_hall_revision=0)).status_code==409
    assert admin_client.get(path).json()['total']==2
    m=match_factory(hall_id=hall['id'],camera_profile_id=second['id'])
    archive=admin_client.get(f"/api/v1/matches/{m['id']}/cv-config")
    with ZipFile(BytesIO(archive.content)) as zipped:
        assert json.loads(zipped.read('calib.json'))==calibration
        assert json.loads(zipped.read('source.json'))['camera_profile_version']==2
