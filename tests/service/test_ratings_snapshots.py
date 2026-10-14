from copy import deepcopy
from uuid import UUID,uuid4
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from .test_analysis_jobs import analytics_match,grant
import pytest


def base(match):return f"/api/v1/tournaments/{match['tournament_id']}"


def revision(client,match):return client.get(base(match)+'/analytics').json()['revision']


def calculate(client,match,scope='private',**changes):
    return client.post(base(match)+'/analytics/calculate',json={'request_id':str(uuid4()),'expected_revision':revision(client,match),
        'scope':scope,'profile_id':'per10','time_basis':'reviewed_effective','level':'amateur','cutoff':'2026-10-14T23:59:59Z',**changes})


def prepare(client,match,send):
    for kind,payload in [('set_completeness',{'goals':'complete','assists':'complete','fouls':'complete','cards':'complete'}),
        ('set_notes',{'notes':'PRIVATE-PROTOCOL-NOTE'}),('set_status',{'status':'ended'}),('confirm',{'acknowledge_incomplete':True})]:
        response=send(match,kind,payload);assert response.status_code==200,response.text;match=response.json()
    protocol=client.get(f"/api/v1/matches/{match['id']}/versions").json()['items'][0]
    doc={'clock_basis':'game','time_basis':'reviewed_effective','analysis_scope':'full_match','duration_ms':2400000,
        'source_protocol_version_id':protocol['id'],'initial_five':{'home':[],'away':[]},'play_intervals':[[0,2400000]],
        'players':[{'player_id':p['player_id'],'presence':[[0,600000]],'roles':[{'role':'ala','intervals':[[0,600000]]}],
            'completeness':'complete','appeared':True} for p in match['lineup']]}
    part=client.put(f"/api/v1/matches/{match['id']}/participation",json={'request_id':str(uuid4()),'expected_revision':0,
        'expected_match_revision':match['revision'],'status':'confirmed','document':doc})
    assert part.status_code==200,part.text
    adoc={'clock_basis':'game','analysis_scope':'full_match','duration_ms':2400000,'source_participation_version_id':part.json()['id'],
        'actions':[],'notes':'PRIVATE-ACTION-NOTE','completeness':{key:[{'status':'complete'}] for key in
        ('shots','passes','carries','duels','recoveries','shot_blocks','turnovers','saves','distribution','errors')}}
    actions=client.put(f"/api/v1/matches/{match['id']}/performance-actions",json={'request_id':str(uuid4()),'expected_revision':0,
        'expected_match_revision':match['revision'],'status':'confirmed','document':adoc})
    assert actions.status_code==200,actions.text
    return match,protocol,part.json(),actions.json()


def publish_sources(client,match,part,actions,approve=True):
    return client.put(f"/api/v1/matches/{match['id']}/performance-publication",json={'request_id':str(uuid4()),
        'expected_revision':revision(client,match),'expected_match_revision':match['revision'],
        'participation_version_id':part['id'],'action_version_id':actions['id'],'approve_policy':approve})


def test_snapshot_replay_pagination_history_and_catalogue_role_do_not_mutate(admin_client,analytics_match,send_command):
    match,protocol,part,actions=prepare(admin_client,analytics_match,send_command)
    payload={'request_id':str(uuid4()),'expected_revision':0,'scope':'private','profile_id':'per10',
        'time_basis':'reviewed_effective','level':'amateur','cutoff':'2026-10-14T23:59:59Z'}
    response=admin_client.post(base(match)+'/analytics/calculate',json=payload);assert response.status_code==200,response.text
    first=response.json();assert admin_client.post(base(match)+'/analytics/calculate',json=payload).json()==first
    assert admin_client.post(base(match)+'/analytics/calculate',json={**payload,'level':'professional'}).status_code==409
    path=base(match)+'/ratings';page=admin_client.get(path,params={'snapshot_id':first['snapshot_id'],'limit':1}).json()
    assert page['total']==4 and page['items'][0]['match_count']==1 and page['items'][0]['score'] is None
    pid=page['items'][0]['player_id']
    from aifootball.service.catalog.models import Player
    with Session(admin_client.app.state.engine) as db:db.get(Player,UUID(pid)).position='forward';db.commit()
    second=calculate(admin_client,match);assert second.status_code==200,second.text
    assert second.json()['snapshot_id']!=first['snapshot_id']
    assert admin_client.get(path,params={'snapshot_id':first['snapshot_id'],'limit':1}).json()==page
    next_page=admin_client.get(path,params={'snapshot_id':first['snapshot_id'],'limit':1,'offset':1}).json()
    assert next_page['snapshot_id']==page['snapshot_id'] and next_page['items'][0]['player_id']!=pid
    history=admin_client.get(f'/api/v1/players/{pid}/ratings',params={'tournament_id':match['tournament_id'],'snapshot_id':first['snapshot_id']})
    assert history.status_code==200 and len(history.json()['matches'])==1
    assert history.json()['matches'][0]['role']=='ala'


def test_public_requires_published_sources_policy_and_separate_snapshot(admin_client,analytics_match,send_command):
    match,protocol,part,actions=prepare(admin_client,analytics_match,send_command)
    private=calculate(admin_client,match).json()
    assert publish_sources(admin_client,match,part,actions).status_code==422
    match=send_command(match,'publish',{'version_id':protocol['id']}).json()
    assert publish_sources(admin_client,match,part,actions,False).status_code==200
    assert calculate(admin_client,match,'public').status_code==422
    assert publish_sources(admin_client,match,part,actions).status_code==200
    public=calculate(admin_client,match,'public');assert public.status_code==200,public.text
    with TestClient(admin_client.app) as guest:
        path=base(match).replace('/api/v1/','/api/v1/public/')+'/ratings'
        assert guest.get(path).json()['snapshot_id'] is None
        assert guest.get(path,params={'snapshot_id':private['snapshot_id']}).status_code==404
        bad=admin_client.post(base(match)+'/analytics/publish',json={'request_id':str(uuid4()),'expected_revision':revision(admin_client,match),'snapshot_id':private['snapshot_id']})
        assert bad.status_code==422
        payload={'request_id':str(uuid4()),'expected_revision':revision(admin_client,match),'snapshot_id':public.json()['snapshot_id']}
        published=admin_client.post(base(match)+'/analytics/publish',json=payload);assert published.status_code==200,published.text
        assert admin_client.post(base(match)+'/analytics/publish',json=payload).json()==published.json()
        result=guest.get(path);assert result.status_code==200 and result.json()['total']==4
        assert all(s not in result.text for s in ('PRIVATE-','source_refs','track_ids','evidence_ids','context_hash'))
        first=result.json()
        assert calculate(admin_client,match,'public').status_code==200
        assert guest.get(path).json()==first


def test_changed_inputs_block_publication_and_new_version_does_not_duplicate_match(admin_client,analytics_match,send_command):
    match,protocol,part,actions=prepare(admin_client,analytics_match,send_command)
    match=send_command(match,'publish',{'version_id':protocol['id']}).json()
    assert publish_sources(admin_client,match,part,actions).status_code==200
    public=calculate(admin_client,match,'public').json()
    # Independent publication of a source is an input change, even with same facts.
    assert publish_sources(admin_client,match,part,actions).status_code==200
    response=admin_client.post(base(match)+'/analytics/publish',json={'request_id':str(uuid4()),'expected_revision':revision(admin_client,match),'snapshot_id':public['snapshot_id']})
    assert response.status_code==409 and response.json()['error']['code']=='stale_snapshot'
    old=calculate(admin_client,match).json()
    saved=admin_client.put(f"/api/v1/matches/{match['id']}/performance-actions",json={'request_id':str(uuid4()),'expected_revision':1,
        'expected_match_revision':match['revision'],'status':'confirmed','document':actions['document']})
    assert saved.status_code==200,saved.text
    new=calculate(admin_client,match).json()
    for snapshot in (old,new):
        rows=admin_client.get(base(match)+'/ratings',params={'snapshot_id':snapshot['snapshot_id']}).json()['items']
        assert all(p['match_count']==1 for p in rows)
    assert new['source_fingerprint']!=old['source_fingerprint']


def test_ordinary_admin_guest_foreign_snapshot_and_stale_commands_are_rejected(admin_client,analytics_match):
    assert calculate(admin_client,analytics_match,expected_revision=99).status_code==409
    grant(admin_client,False)
    assert admin_client.get(base(analytics_match)+'/analytics').status_code==403
    response=admin_client.post(base(analytics_match)+'/analytics/calculate',json={'request_id':str(uuid4()),'expected_revision':0})
    assert response.status_code==403


def test_replacing_cv_run_changes_fingerprint_without_second_appearance(admin_client,analytics_match,send_command):
    from .test_analysis_assignments import import_run,save_assignments,command
    match,protocol,part,actions=prepare(admin_client,analytics_match,send_command)
    run=import_run(admin_client,match);saved=save_assignments(admin_client,match,run);assert saved.status_code==200,saved.text
    first_run=command(admin_client,match,saved.json(),'confirm');assert first_run.status_code==200,first_run.text
    first=calculate(admin_client,match).json()
    review=command(admin_client,match,first_run.json(),'reviews');assert review.status_code==200,review.text
    replacement=command(admin_client,match,review.json(),'confirm');assert replacement.status_code==200,replacement.text
    second=calculate(admin_client,match).json()
    assert first['source_fingerprint']!=second['source_fingerprint']
    for snapshot in (first,second):
        page=admin_client.get(base(match)+'/ratings',params={'snapshot_id':snapshot['snapshot_id']}).json()
        assert all(r['match_count']==1 for r in page['items'])


def test_foreign_sources_rollback_and_historical_team_stage_filters(admin_client,analytics_match,send_command):
    match=send_command(analytics_match,'update_match',{'stage_label':'Полуфинал'}).json()
    match,protocol,part,actions=prepare(admin_client,match,send_command)
    first=calculate(admin_client,match).json();before=revision(admin_client,match)
    response=admin_client.put(f"/api/v1/matches/{match['id']}/performance-publication",json={'request_id':str(uuid4()),
        'expected_revision':before,'expected_match_revision':match['revision'],'participation_version_id':str(uuid4()),'approve_policy':True})
    assert response.status_code==404 and revision(admin_client,match)==before
    home=match['home']['team']['id']
    rows=admin_client.get(base(match)+'/ratings',params={'snapshot_id':first['snapshot_id'],'team_id':home,'stage_label':'Полуфинал'}).json()
    assert rows['total']==2 and all(r['teams']==[{'id':home,'name':match['home']['team']['name']}] for r in rows['items'])
    assert admin_client.get(base(match)+'/ratings',params={'stage_label':'Группа'}).json()['total']==0
    assert admin_client.get(base(match)+'/ratings',params={'snapshot_id':str(uuid4())}).status_code==404


def test_new_confirmed_source_marks_current_private_snapshot_stale(admin_client,analytics_match,send_command):
    match,protocol,part,actions=prepare(admin_client,analytics_match,send_command)
    first=calculate(admin_client,match).json()
    assert next(v for v in admin_client.get(base(match)+'/analytics').json()['snapshots'] if v['snapshot_id']==first['snapshot_id'])['stale'] is False
    saved=admin_client.put(f"/api/v1/matches/{match['id']}/performance-actions",json={'request_id':str(uuid4()),'expected_revision':1,
        'expected_match_revision':match['revision'],'status':'confirmed','document':actions['document']})
    assert saved.status_code==200,saved.text
    assert next(v for v in admin_client.get(base(match)+'/analytics').json()['snapshots'] if v['snapshot_id']==first['snapshot_id'])['stale'] is True
