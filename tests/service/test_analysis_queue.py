from uuid import uuid4
from sqlalchemy import event
from sqlalchemy.orm import Session
from .test_analysis_jobs import analytics_match,new_job,grant
from .test_analysis_import import upload
from .test_analysis_assignments import save_assignments,command
from test_analysis_exchange import result_zip

def queue(client,m,query=''):
    r=client.get(f"/api/v1/tournaments/{m['tournament_id']}/analysis-queue"+query);assert r.status_code==200,r.text
    return r.json()

def test_queue_derives_work_from_jobs_runs_and_separate_publication(admin_client,analytics_match):
    m=analytics_match;assert queue(admin_client,m)['items'][0]['status']=='not_started'
    job=new_job(admin_client,m);assert queue(admin_client,m)['items'][0]['status']=='awaiting_result'
    run=upload(admin_client,m,result_zip(job)).json();item=queue(admin_client,m)['items'][0];assert item['status']=='review' and item['unresolved']==3
    run=save_assignments(admin_client,m,run).json();assert queue(admin_client,m)['items'][0]['unresolved']==0
    run=command(admin_client,m,run,'confirm').json();assert queue(admin_client,m)['items'][0]['status']=='unpublished'
    run=command(admin_client,m,run,'publish').json();assert queue(admin_client,m)['items'][0]['status']=='published'
    review=command(admin_client,m,run,'reviews').json();item=queue(admin_client,m)['items'][0];assert item['status']=='review' and item['run_id']==review['id'] and item['published_run_id']==run['id']
    assert queue(admin_client,m,'?status=published')['total']==0
    grant(admin_client,False)
    assert admin_client.get(f"/api/v1/tournaments/{m['tournament_id']}/analysis-queue").status_code==403

def test_queue_context_freshness_and_page_query_count(admin_client,analytics_match):
    from aifootball.service.matches.models import LineupMember
    m=analytics_match;job=new_job(admin_client,m);upload(admin_client,m,result_zip(job))
    with Session(admin_client.app.state.engine) as db,db.begin():db.query(LineupMember).filter_by(match_id=m['id']).first().shirt_number='99'
    assert queue(admin_client,m)['items'][0]['status']=='stale'
    for i in range(8):
        r=admin_client.post(f"/api/v1/tournaments/{m['tournament_id']}/matches",json={'home_entry_id':m['home_entry_id'],'away_entry_id':m['away_entry_id'],'regulation_id':m['regulation_id'],'scheduled_at':f'2026-11-{i+1:02}T19:00:00+03:00','hall_id':m['hall_id'],'camera_profile_id':m['camera_profile_id']});assert r.status_code==201,r.text
    statements=[]
    def capture(conn,cursor,statement,params,context,many):
        if statement.lstrip().upper().startswith(('SELECT','WITH')):statements.append(statement)
    event.listen(admin_client.app.state.engine,'before_cursor_execute',capture)
    try:data=queue(admin_client,m,'?limit=100')
    finally:event.remove(admin_client.app.state.engine,'before_cursor_execute',capture)
    assert data['total']==9 and len(data['items'])==9
    assert len(statements)<=9, len(statements)
    assert queue(admin_client,m,'?status=not_started&limit=2&offset=2')['total']==8

def test_queue_shows_captain_side_readiness_and_invalidates_changed_assignments(admin_client,analytics_match):
    from .test_team_identity_tasks import owner,issue
    from .test_team_identity_confirmations import draft,confirm,getrun
    m=analytics_match;cap,team_id,_=owner(admin_client,m);job=new_job(admin_client,m)
    run=upload(admin_client,m,result_zip(job)).json();run=save_assignments(admin_client,m,run,[]).json()
    task=draft(cap,issue(admin_client,m,run,team_id).json());assert confirm(cap,task).status_code==200
    item=queue(admin_client,m)['items'][0];assert item['teams'][0]['status']=='team_confirmed' and item['teams'][1]['status']=='not_issued'
    fresh=getrun(admin_client,m,run);assert save_assignments(admin_client,m,fresh,[]).status_code==200
    assert queue(admin_client,m)['items'][0]['teams'][0]['status']=='obsolete'

def test_queue_quality_failure_is_a_specific_blocker(admin_client,analytics_match):
    m=analytics_match;job=new_job(admin_client,m)
    def bad(manifest,report,tracks,checks):checks.update(passed=False,critical_errors=['Синтетическая ошибка камеры'])
    response=upload(admin_client,m,result_zip(job,mutate=bad));assert response.status_code==200,response.text
    assert queue(admin_client,m)['items'][0]['status']=='quality_blocked'
