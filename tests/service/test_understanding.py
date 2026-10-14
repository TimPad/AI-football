from uuid import uuid4,UUID
from copy import deepcopy
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from .test_analysis_jobs import analytics_match,new_job,grant
from .test_analysis_import import upload
from .test_analysis_assignments import save_assignments,command
from test_understanding_exchange import result_v2
from test_analysis_exchange import result_zip


def path(match,run):return f"/api/v1/matches/{match['id']}/analysis/runs/{run['id']}/understanding"


def review(client,match,run,decision='accepted',*,request_id=None,revision=None,correction=None):
    return client.put(path(match,run)+'/reviews',json={'request_id':request_id or str(uuid4()),
        'expected_revision':run['revision'] if revision is None else revision,'event_id':'e1',
        'decision':decision,'correction':correction,'reason':'Проверено по кадрам'})


def imported(client,match,mutate=None):
    job=new_job(client,match);response=upload(client,match,result_v2(job,mutate=mutate))
    assert response.status_code==200,response.text
    return response.json()


def test_private_understanding_is_separate_and_goal_review_cannot_change_protocol(admin_client,analytics_match):
    run=imported(admin_client,analytics_match)
    assert 'understanding' not in run and 'understanding_reviews' not in run
    before=admin_client.get(f"/api/v1/matches/{analytics_match['id']}").json()
    detail=admin_client.get(path(analytics_match,run))
    assert detail.status_code==200,detail.text
    assert detail.json()['understanding']['events'][0]['kind']=='goal_candidate'
    assert detail.json()['verified_summary']==[]
    reviewed=review(admin_client,analytics_match,run)
    assert reviewed.status_code==200,reviewed.text
    assert reviewed.json()['revision']==1
    assert reviewed.json()['verified_summary'][0]['event_ids']==['e1']
    after=admin_client.get(f"/api/v1/matches/{analytics_match['id']}").json()
    assert after['protocol']==before['protocol']
    assert after['projection']['effective_score']==before['projection']['effective_score']
    image=admin_client.get(path(analytics_match,run)+'/evidence/f1')
    assert image.status_code==200 and image.content.startswith(b'\xff\xd8')
    assert image.headers['Cache-Control']=='private, no-store'
    assert image.headers['X-Content-Type-Options']=='nosniff'


def test_private_get_and_image_work_with_session_cookie_without_csrf_header(admin_client,analytics_match):
    run=imported(admin_client,analytics_match)
    with TestClient(admin_client.app) as browser:
        browser.cookies.update(admin_client.cookies)
        assert browser.get(path(analytics_match,run)).status_code==200
        assert browser.get(path(analytics_match,run)+'/evidence/f1').status_code==200
        # Writes still require the anti-forgery header.
        assert review(browser,analytics_match,run).status_code==403


def test_understanding_requires_admin_plus_and_scoped_evidence(admin_client,analytics_match):
    run=imported(admin_client,analytics_match)
    assert admin_client.get(path({'id':str(uuid4())},run)).status_code==404
    assert admin_client.get(path(analytics_match,run)+'/evidence/missing').status_code==404
    grant(admin_client,False)
    assert admin_client.get(path(analytics_match,run)).status_code==403
    assert admin_client.get(path(analytics_match,run)+'/evidence/f1').status_code==403
    assert review(admin_client,analytics_match,run).status_code==403
    assert admin_client.get(f"/api/v1/matches/{analytics_match['id']}/analysis/runs/{run['id']}").status_code==200
    with TestClient(admin_client.app) as guest:
        assert guest.get(path(analytics_match,run)).status_code==401
        assert guest.get(path(analytics_match,run)+'/evidence/f1').status_code==401
        public=guest.get(f"/api/v1/public/matches/{analytics_match['id']}/analysis")
        assert 'evidence' not in public.text and 'goal_candidate' not in public.text


def test_review_retry_and_revision_conflict_keep_one_audit_entry(admin_client,analytics_match):
    run=imported(admin_client,analytics_match);request_id=str(uuid4())
    first=review(admin_client,analytics_match,run,request_id=request_id)
    assert first.status_code==200,first.text
    assert review(admin_client,analytics_match,run,request_id=request_id).json()==first.json()
    assert review(admin_client,analytics_match,run,decision='rejected',request_id=request_id).status_code==409
    assert review(admin_client,analytics_match,run,decision='rejected').status_code==409
    from aifootball.service.analysis.models import AnalysisUnderstandingDecision
    with Session(admin_client.app.state.engine) as db:
        decisions=db.query(AnalysisUnderstandingDecision).filter_by(run_id=UUID(run['id'])).all()
        assert len(decisions)==1 and decisions[0].after['decision']=='accepted'


@pytest.mark.parametrize('correction',[{'end_ms':999999},{'kind':'confirmed_goal'},
    {'track_ids':[999]},{'player_id':'11111111-1111-4111-8111-111111111111'},{'evidence_ids':['missing']}])
def test_correction_validates_same_schema_before_mutation(admin_client,analytics_match,correction):
    run=imported(admin_client,analytics_match)
    assert review(admin_client,analytics_match,run,'corrected',correction=correction).status_code==422
    detail=admin_client.get(path(analytics_match,run)).json()
    assert detail['revision']==0 and detail['reviews']=={}


def test_corrected_then_rejected_changes_only_verified_projection(admin_client,analytics_match):
    run=imported(admin_client,analytics_match)
    corrected=review(admin_client,analytics_match,run,'corrected',correction={'kind':'shot_candidate'})
    assert corrected.status_code==200,corrected.text
    assert corrected.json()['understanding']['events'][0]['kind']=='goal_candidate'
    assert corrected.json()['effective_events'][0]['kind']=='shot_candidate'
    rejected=review(admin_client,analytics_match,run,'rejected',revision=1)
    assert rejected.status_code==200 and rejected.json()['verified_summary']==[]
    assert rejected.json()['understanding']['events'][0]['kind']=='goal_candidate'


def test_confirmed_source_is_immutable_and_review_clone_preserves_decisions(admin_client,analytics_match):
    run=imported(admin_client,analytics_match)
    assert review(admin_client,analytics_match,run).status_code==200
    run=admin_client.get(f"/api/v1/matches/{analytics_match['id']}/analysis/runs/{run['id']}").json()
    run=save_assignments(admin_client,analytics_match,run).json()
    run=command(admin_client,analytics_match,run,'confirm').json()
    assert review(admin_client,analytics_match,run,'rejected').status_code==409
    clone=command(admin_client,analytics_match,run,'reviews').json()
    view=admin_client.get(path(analytics_match,clone)).json()
    assert view['reviews']['e1']['decision']=='accepted'
    assert review(admin_client,analytics_match,clone,'rejected').status_code==200
    assert admin_client.get(path(analytics_match,run)).json()['reviews']['e1']['decision']=='accepted'


def test_legacy_run_has_empty_understanding(admin_client,analytics_match):
    job=new_job(admin_client,analytics_match);run=upload(admin_client,analytics_match,result_zip(job)).json()
    response=admin_client.get(path(analytics_match,run))
    assert response.status_code==200,response.text
    assert response.json()['understanding'] is None
    assert review(admin_client,analytics_match,run).status_code==422


def test_foreign_suggested_uuid_is_rejected_before_files_are_saved(admin_client,analytics_match):
    before_files=set(admin_client.app.state.settings.attachment_root.rglob('*.zip'))
    job=new_job(admin_client,analytics_match)
    def mutate(manifest,doc):
        doc['identity_suggestions']=[{'track_id':1,'player_id':str(uuid4()),'status':'candidate',
            'number':'1','team':'A','evidence_ids':['f1'],'reasons':[]}]
    response=upload(admin_client,analytics_match,result_v2(job,mutate=mutate))
    assert response.status_code==422
    assert set(admin_client.app.state.settings.attachment_root.rglob('*.zip'))==before_files


def test_identity_suggestion_waits_for_explicit_side_confirmation(admin_client,analytics_match):
    def mutate(manifest,doc):
        doc['observations']=[{'track_id':1,'video_ms':1000,'role':'player','number':'1','team':'A',
            'evidence_ids':['f1'],'visible_features':[],'limitations':[]}]
    run=imported(admin_client,analytics_match,mutate)
    first=admin_client.get(path(analytics_match,run)).json()
    assert first['side_map_verified'] is False
    assert first['identity_suggestions'][0]['player_id'] is None
    run=save_assignments(admin_client,analytics_match,run).json()
    later=admin_client.get(path(analytics_match,run)).json()
    assert later['side_map_verified'] is True
    assert later['identity_suggestions'][0]['player_id'] in {p['player_id'] for p in run['context']['rosters'] if p['side']=='home'}


def test_correction_cannot_attach_player_track_from_another_time(admin_client,analytics_match):
    run=imported(admin_client,analytics_match)
    assert review(admin_client,analytics_match,run,'corrected',correction={'track_ids':[3]}).status_code==422


def test_settings_repr_does_not_reveal_database_password():
    from aifootball.service.config import Settings
    settings=Settings(database_url='postgresql+psycopg://user:DO_NOT_LOG@localhost/db')
    assert 'DO_NOT_LOG' not in repr(settings)
