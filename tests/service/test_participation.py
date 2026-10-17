from copy import deepcopy
from uuid import uuid4,UUID
import pytest
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient
from .test_analysis_jobs import analytics_match,grant
from .test_understanding import imported
from .test_analysis_assignments import save_assignments,command


def body(match,**changes):
    person=next(p for p in match['lineup'] if p['side']=='home')
    return {'request_id':str(uuid4()),'expected_revision':0,'expected_match_revision':match['revision'],'status':'confirmed',
        'document':{'clock_basis':'game','time_basis':'reviewed_effective','duration_ms':180000,
            'initial_five':{'home':[person['player_id']],'away':[]},
            'play_intervals':[[0,30000],[100000,150000]],
            'players':[{'player_id':person['player_id'],'completeness':'complete','appeared':True,
                'presence':[[0,60000],[90000,150000]],'roles':[{'role':'ala','intervals':[[0,60000],[90000,150000]]}]}]},**changes}


def path(match):return f"/api/v1/matches/{match['id']}/participation"


def test_participation_versions_replay_and_role_history_survive_catalogue_change(admin_client,analytics_match):
    data=body(analytics_match);before=deepcopy(analytics_match['protocol'])
    first=admin_client.put(path(analytics_match),json=data)
    assert first.status_code==200,first.text
    saved=first.json();pid=data['document']['players'][0]['player_id']
    assert saved['exposures'][pid]['ala']['on_pitch_s']==120
    assert saved['exposures'][pid]['ala']['effective_play_s']==80
    assert admin_client.put(path(analytics_match),json=data).json()==saved
    from aifootball.service.catalog.models import Player
    with Session(admin_client.app.state.engine) as db:
        db.get(Player,UUID(pid)).position='forward';db.commit()
    second=body(analytics_match,expected_revision=1,status='review')
    second['document']['players'][0]['roles'][0]['role']='pivot'
    newer=admin_client.put(path(analytics_match),json=second)
    assert newer.status_code==200 and newer.json()['id']!=saved['id']
    old=admin_client.get(path(analytics_match)+f"/versions/{saved['id']}").json()
    assert old['status']=='confirmed' and old['document']['players'][0]['roles'][0]['role']=='ala'
    assert admin_client.put(path(analytics_match),json=body(analytics_match)).status_code==409
    assert admin_client.get(f"/api/v1/matches/{analytics_match['id']}").json()['protocol']==before


def test_unknown_presence_is_not_inferred_from_cv(admin_client,analytics_match):
    data=body(analytics_match)
    p=data['document']['players'][0];p.update(presence=None,roles=[],completeness='unknown',appeared=None)
    data['document']['initial_five']['home']=[]
    result=admin_client.put(path(analytics_match),json=data)
    assert result.status_code==200,result.text
    assert result.json()['exposures'][p['player_id']]['unknown']['on_pitch_s'] is None


@pytest.mark.parametrize('invalid',['foreign_player','overlap','game_as_video','clean_without_source','stale_match'])
def test_invalid_participation_does_not_create_version(admin_client,analytics_match,invalid):
    data=body(analytics_match);doc=data['document']
    if invalid=='foreign_player':doc['players'][0]['player_id']=str(uuid4())
    if invalid=='overlap':doc['players'][0]['roles'].append({'role':'fixo','intervals':[[10000,20000]]})
    if invalid=='game_as_video':doc['clock_basis']='video'
    if invalid=='clean_without_source':doc['time_basis']='official_clean'
    if invalid=='stale_match':data['expected_match_revision']=0
    result=admin_client.put(path(analytics_match),json=data)
    assert result.status_code in (409,422),result.text
    assert admin_client.get(path(analytics_match)).json()['versions']==[]


def test_video_timeline_is_bounded_by_selected_confirmed_recording(admin_client,analytics_match):
    run=save_assignments(admin_client,analytics_match,imported(admin_client,analytics_match)).json()
    run=command(admin_client,analytics_match,run,'confirm').json()
    data=body(analytics_match);doc=data['document']
    # Подтверждение видео уже создало автоматическое участие.
    data['expected_revision']=admin_client.get(path(analytics_match)).json()['revision']
    doc.update(clock_basis='video',source_analysis_run_id=run['id'],duration_ms=240001)
    result=admin_client.put(path(analytics_match),json=data)
    assert result.status_code==422,result.text


def test_participation_requires_admin_plus_and_cookie_reads_need_no_csrf(admin_client,analytics_match):
    saved=admin_client.put(path(analytics_match),json=body(analytics_match));assert saved.status_code==200,saved.text
    with TestClient(admin_client.app) as browser:
        browser.cookies.update(admin_client.cookies)
        assert browser.get(path(analytics_match)).status_code==200
    grant(admin_client,False)
    assert admin_client.get(path(analytics_match)).status_code==403
    assert admin_client.put(path(analytics_match),json=body(analytics_match)).status_code==403
    with TestClient(admin_client.app) as guest:assert guest.get(path(analytics_match)).status_code==401
