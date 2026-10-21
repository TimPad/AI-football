from uuid import uuid4
from .captain_helpers import captain
from .test_analysis_jobs import analytics_match
from .test_analysis_assignments import import_run,save_assignments

def owner(admin,match,side='home',email='identity@example.test'):
    client,_=captain(admin.app,email)
    account=client.get('/api/v1/captain/auth/me').json()['id']
    team_id=match[side]['team_id']
    grant=admin.post(f'/api/v1/teams/{team_id}/captain-grants',json={'request_id':str(uuid4()),'account_id':account,'reason':'Проверяет свою команду'})
    assert grant.status_code==200,grant.text
    return client,team_id,grant.json()

def issue(admin,match,run,team_id):
    return admin.post(f"/api/v1/matches/{match['id']}/analysis/runs/{run['id']}/team-review-tasks",json={'request_id':str(uuid4()),'expected_run_revision':run['revision'],'team_id':team_id})

def test_task_requires_verified_sides_and_only_reveals_own_snapshot(admin_client,analytics_match):
    cap,team_id,_=owner(admin_client,analytics_match)
    run=import_run(admin_client,analytics_match)
    assert issue(admin_client,analytics_match,run,team_id).status_code==409
    run=save_assignments(admin_client,analytics_match,run).json()
    response=issue(admin_client,analytics_match,run,team_id);assert response.status_code==201,response.text
    task=response.json();detail=cap.get('/api/v1/captain/identity-tasks/'+task['id'])
    assert detail.status_code==200,detail.text
    d=detail.json();assert {t['track_id'] for g in d['groups'] for t in g['tracks']}=={1,2}
    assert {p['player_id'] for p in d['players']}=={p['player_id'] for p in run['context']['rosters'] if p['side']=='home'}
    assert 'report' not in d and 'side_map' not in d and 'storage_key' not in d
    assert cap.get(f"/api/v1/captain/identity-tasks/{task['id']}/tracks/3/thumbnail").status_code==404
    assert cap.get(f"/api/v1/captain/identity-tasks/{task['id']}/tracks/1/thumbnail").status_code==404
    assert cap.get(f"/api/v1/matches/{analytics_match['id']}/analysis").status_code==401
    assert cap.get('/api/v1/captain/identity-tasks').json()['total']==1

def test_revocation_and_obsolete_material_prevent_reading(admin_client,analytics_match):
    cap,team_id,grant=owner(admin_client,analytics_match);run=save_assignments(admin_client,analytics_match,import_run(admin_client,analytics_match)).json()
    task=issue(admin_client,analytics_match,run,team_id).json();path='/api/v1/captain/identity-tasks/'+task['id']
    other,_=captain(admin_client.app,'foreign-identity@example.test');assert other.get(path).status_code==404
    # Changing only the opponent assignments leaves this task current.
    fresh=admin_client.get(f"/api/v1/matches/{analytics_match['id']}/analysis/runs/{run['id']}").json()
    values=[a for a in fresh['assignments'] if a['track_id']!=3]
    fresh=save_assignments(admin_client,analytics_match,fresh,values).json();assert cap.get(path).json()['status']=='open'
    # Our own assignment change invalidates the task, including its images.
    fresh=save_assignments(admin_client,analytics_match,fresh,[]).json();assert cap.get(path).json()['status']=='obsolete'
    assert cap.get(path+'/tracks/1/thumbnail').status_code==409
    revoked=admin_client.post(f"/api/v1/teams/{team_id}/captain-grants/{grant['id']}/revoke",json={'request_id':str(uuid4()),'reason':'Смена капитана'})
    assert revoked.status_code==200,revoked.text
    assert cap.get(path).status_code==404

def test_reading_a_task_does_not_lock_match_and_missing_camera_is_obsolete(admin_client,analytics_match):
    from sqlalchemy import event
    from sqlalchemy.orm import Session
    from aifootball.service.matches.models import Match
    cap,team_id,_=owner(admin_client,analytics_match);run=save_assignments(admin_client,analytics_match,import_run(admin_client,analytics_match)).json();task=issue(admin_client,analytics_match,run,team_id).json()
    statements=[]
    def capture(conn,cursor,statement,parameters,context,many):statements.append(statement)
    event.listen(admin_client.app.state.engine,'before_cursor_execute',capture)
    try:
        assert cap.get('/api/v1/captain/identity-tasks/'+task['id']).status_code==200
    finally:event.remove(admin_client.app.state.engine,'before_cursor_execute',capture)
    assert not any('FOR UPDATE' in s.upper() for s in statements)
    with Session(admin_client.app.state.engine) as db,db.begin():db.get(Match,analytics_match['id']).camera_profile_id=None
    response=cap.get('/api/v1/captain/identity-tasks/'+task['id']);assert response.status_code==200,response.text
    assert response.json()['status']=='obsolete'


import pytest
@pytest.mark.parametrize('replacement',['import','review'])
def test_replacement_run_obsoletes_old_task_and_prevents_reissue(admin_client,analytics_match,replacement):
    from .test_analysis_assignments import command
    cap,team_id,_=owner(admin_client,analytics_match)
    source=save_assignments(admin_client,analytics_match,import_run(admin_client,analytics_match)).json()
    if replacement=='review':
        source=command(admin_client,analytics_match,source,'confirm').json()
        source=command(admin_client,analytics_match,source,'publish').json()
        run=command(admin_client,analytics_match,source,'reviews').json()
    else:run=source
    task=issue(admin_client,analytics_match,run,team_id).json();path='/api/v1/captain/identity-tasks/'+task['id']
    if replacement=='review':new=command(admin_client,analytics_match,source,'reviews').json()
    else:new=import_run(admin_client,analytics_match)
    assert new['id']!=run['id']
    assert cap.get(path).json()['status']=='obsolete'
    assert cap.get(path+'/tracks/1/thumbnail').status_code==409
    assert cap.put(path+'/draft',json={'request_id':str(uuid4()),'expected_revision':task['revision'],'decisions':[]}).status_code==409
    assert cap.post(path+'/confirm',json={'request_id':str(uuid4()),'expected_revision':task['revision']}).status_code==409
    old=admin_client.get(f"/api/v1/matches/{analytics_match['id']}/analysis/runs/{run['id']}").json()
    assert issue(admin_client,analytics_match,old,team_id).status_code==409
    if replacement=='review':
        history=admin_client.get(f"/api/v1/matches/{analytics_match['id']}/analysis/runs/{source['id']}").json()
        assert history['status']=='confirmed' and history['published_run_id']==source['id']
