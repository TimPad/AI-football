from uuid import uuid4
from .test_analysis_jobs import analytics_match
from .test_analysis_assignments import import_run,save_assignments,command
from .test_team_identity_tasks import owner,issue
import pytest

def path(task):return '/api/v1/captain/identity-tasks/'+task['id']
def choose(task,kind='player',reason=''):
    return [{'group_id':g['id'],'kind':kind,'player_id':task['players'][0]['player_id'] if kind=='player' else None,'reason':reason} for g in task['groups']]
def draft(cap,task,decisions=None):
    r=cap.put(path(task)+'/draft',json={'request_id':str(uuid4()),'expected_revision':task['revision'],'decisions':decisions if decisions is not None else choose(task)});assert r.status_code==200,r.text
    return r.json()
def confirm(cap,task,body=None):
    return cap.post(path(task)+'/confirm',json=body or {'request_id':str(uuid4()),'expected_revision':task['revision']})
def getrun(admin,match,run):return admin.get(f"/api/v1/matches/{match['id']}/analysis/runs/{run['id']}").json()

def test_two_captains_independently_confirm_and_technical_confirmation_is_separate(admin_client,analytics_match):
    home,ht,_=owner(admin_client,analytics_match);away,at,_=owner(admin_client,analytics_match,'away','away@example.test')
    run=save_assignments(admin_client,analytics_match,import_run(admin_client,analytics_match),[]).json()
    h=issue(admin_client,analytics_match,run,ht).json();a=issue(admin_client,analytics_match,getrun(admin_client,analytics_match,run),at).json()
    h=draft(home,h);assert getrun(admin_client,analytics_match,run)['assignments']==[]
    body={'request_id':str(uuid4()),'expected_revision':h['revision']};r=confirm(home,h,body);assert r.status_code==200,r.text
    assert confirm(home,h,body).json()==r.json();assert r.json()['status']=='team_confirmed'
    current=getrun(admin_client,analytics_match,run);assert current['players']==[] and current['published_run_id'] is None and current['active_run_id'] is None
    assert {a['track_id'] for a in current['assignments']}=={1,2}
    assert command(admin_client,analytics_match,current,'confirm').status_code==409
    a=draft(away,a);r=confirm(away,a);assert r.status_code==200,r.text
    current=getrun(admin_client,analytics_match,run);assert {a['track_id'] for a in current['assignments']}=={1,2,3}
    assert current['players']==[] and current['status']=='review'
    technical=command(admin_client,analytics_match,current,'confirm');assert technical.status_code==200,technical.text
    assert technical.json()['published_run_id'] is None
    assert confirm(home,h).status_code==409
    review=command(admin_client,analytics_match,technical.json(),'reviews').json()
    assert review['identity_workflow']=='team'
    assert command(admin_client,analytics_match,review,'confirm').status_code==409

def test_unknown_material_issue_foreign_player_and_idempotency(admin_client,analytics_match):
    cap,team_id,_=owner(admin_client,analytics_match);run=save_assignments(admin_client,analytics_match,import_run(admin_client,analytics_match),[]).json();task=issue(admin_client,analytics_match,run,team_id).json()
    values=choose(task);values[0]['player_id']=str(uuid4())
    assert cap.put(path(task)+'/draft',json={'request_id':str(uuid4()),'expected_revision':0,'decisions':values}).status_code==422
    task=draft(cap,task,choose(task,'material_issue','Разные люди в группе'));assert confirm(cap,task).status_code==409
    task=draft(cap,task,choose(task,'unknown','Нет в списке'));r=confirm(cap,task);assert r.status_code==200,r.text
    current=getrun(admin_client,analytics_match,run);assert all(a['player_id'] is None and a['excluded_reason'] for a in current['assignments'])
    # A captain cannot replace the decision by merely saving another draft after confirmation.
    assert cap.put(path(task)+'/draft',json={'request_id':str(uuid4()),'expected_revision':task['revision'],'decisions':choose(task)}).status_code==409

def test_correction_blocks_freeze_and_admin_fallback_is_explicit(admin_client,analytics_match):
    cap,team_id,_=owner(admin_client,analytics_match);run=save_assignments(admin_client,analytics_match,import_run(admin_client,analytics_match)).json();task=draft(cap,issue(admin_client,analytics_match,run,team_id).json());done=confirm(cap,task);assert done.status_code==200,done.text;task=done.json()
    correction=cap.post(path(task)+'/corrections',json={'request_id':str(uuid4()),'expected_revision':task['revision']});assert correction.status_code==200,correction.text
    assert command(admin_client,analytics_match,getrun(admin_client,analytics_match,run),'confirm').status_code==409
    current=getrun(admin_client,analytics_match,run);base=f"/api/v1/matches/{analytics_match['id']}/analysis/runs/{run['id']}"
    for side in ['home','away']:
        r=admin_client.post(base+'/team-confirmations',json={'request_id':str(uuid4()),'expected_run_revision':current['revision'],'side':side,'reason':'Капитан недоступен, сверено по материалу'});assert r.status_code==200,r.text
        current=getrun(admin_client,analytics_match,run)
    assert cap.get(path(task)).json()['status']=='revoked'
    assert command(admin_client,analytics_match,current,'confirm').status_code==200

@pytest.mark.parametrize('start,expected',[(59.2,200),(58.9,422)])
def test_existing_overlap_tolerance_applies_to_captain_confirmation(admin_client,analytics_match,start,expected):
    def overlap(m,r,t,c):t['tracks'][1]['intervals']=[[start,240]]
    cap,team_id,_=owner(admin_client,analytics_match);run=save_assignments(admin_client,analytics_match,import_run(admin_client,analytics_match,overlap),[]).json()
    task=draft(cap,issue(admin_client,analytics_match,run,team_id).json());response=confirm(cap,task);assert response.status_code==expected,response.text
    if expected==422:assert getrun(admin_client,analytics_match,run)['assignments']==[]

def test_confirm_uses_frozen_draft_and_rejects_reused_body_and_own_changes(admin_client,analytics_match):
    cap,team_id,_=owner(admin_client,analytics_match);run=save_assignments(admin_client,analytics_match,import_run(admin_client,analytics_match),[]).json();task=issue(admin_client,analytics_match,run,team_id).json()
    values=choose(task);payload={'request_id':str(uuid4()),'expected_revision':0,'decisions':values}
    r=cap.put(path(task)+'/draft',json=payload);assert r.status_code==200,r.text;task=r.json()
    assert cap.put(path(task)+'/draft',json=payload).json()==task
    payload['decisions']=[];assert cap.put(path(task)+'/draft',json=payload).status_code==409
    assert confirm(cap,task,{'request_id':str(uuid4()),'expected_revision':0}).status_code==409
    current=getrun(admin_client,analytics_match,run);changed=save_assignments(admin_client,analytics_match,current,[{'track_id':1,'excluded_reason':'Дубль'}]);assert changed.status_code==200
    assert confirm(cap,task).status_code==409

def test_source_context_change_requires_new_processing_job(admin_client,analytics_match):
    from sqlalchemy.orm import Session
    from aifootball.service.matches.models import Match
    cap,team_id,_=owner(admin_client,analytics_match);run=save_assignments(admin_client,analytics_match,import_run(admin_client,analytics_match),[]).json();task=draft(cap,issue(admin_client,analytics_match,run,team_id).json())
    # A real edit changes the source snapshot; copying a review cannot manufacture a new job.
    with Session(admin_client.app.state.engine) as db,db.begin():
        match=db.get(Match,analytics_match['id']);match.venue_label='Другой зал в сведениях'
    # venue_label is descriptive, so alter the immutable-roster source itself.
    from aifootball.service.matches.models import LineupMember
    with Session(admin_client.app.state.engine) as db,db.begin():
        member=db.query(LineupMember).filter_by(match_id=analytics_match['id']).first();member.shirt_number='99'
    assert cap.get(path(task)).json()['status']=='obsolete'
    assert confirm(cap,task).status_code==409

def test_admin_edits_invalidate_captain_authorship_and_old_confirmation_stays_immutable(admin_client,analytics_match):
    from sqlalchemy import select
    from sqlalchemy.orm import Session
    from aifootball.service.analysis.team_review.models import TeamIdentityConfirmation
    cap,team_id,_=owner(admin_client,analytics_match);run=save_assignments(admin_client,analytics_match,import_run(admin_client,analytics_match),[]).json();task=draft(cap,issue(admin_client,analytics_match,run,team_id).json());confirmed=confirm(cap,task).json()
    with Session(admin_client.app.state.engine) as db:
        old=db.get(TeamIdentityConfirmation,confirmed['confirmation_id']);saved=(old.assignment_fingerprint,old.actor_id,old.decisions)
    current=getrun(admin_client,analytics_match,run);values=current['assignments'];values[0]={'track_id':values[0]['track_id'],'excluded_reason':'Исправлено администратором'}
    edited=save_assignments(admin_client,analytics_match,current,values);assert edited.status_code==200
    statuses=admin_client.get(f"/api/v1/matches/{analytics_match['id']}/analysis/runs/{run['id']}/team-confirmations").json();assert statuses['sides'][0]['status']=='obsolete'
    assert command(admin_client,analytics_match,edited.json(),'confirm').status_code==409
    with Session(admin_client.app.state.engine) as db:
        old=db.get(TeamIdentityConfirmation,confirmed['confirmation_id']);assert (old.assignment_fingerprint,old.actor_id,old.decisions)==saved
