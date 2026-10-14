from uuid import uuid4
from copy import deepcopy
from .test_analysis_jobs import analytics_match,grant
import pytest


def body(match):
    pid=match['lineup'][0]['player_id']
    return {'request_id':str(uuid4()),'expected_revision':0,'expected_match_revision':match['revision'],'status':'confirmed',
        'document':{'clock_basis':'game','analysis_scope':'continuous_excerpt','duration_ms':180000,
            'actions':[{'id':str(uuid4()),'kind':'pass','player_id':pid,'start_ms':1000,'end_ms':1200,'success':True}],
            'completeness':{'passes':[{'status':'partial','intervals':[[0,180000]]}]}}}


def path(match):return f"/api/v1/matches/{match['id']}/performance-actions"


def test_manual_actions_preserve_scope_unknown_categories_and_idempotent_versions(admin_client,analytics_match):
    data=body(analytics_match);before=deepcopy(analytics_match['protocol'])
    first=admin_client.put(path(analytics_match),json=data);assert first.status_code==200,first.text
    saved=first.json();assert saved['canonical_actions'][0]['kind']=='pass'
    assert saved['document']['completeness']['passes'][0]['status']=='partial'
    assert 'shots' not in saved['document']['completeness']
    assert admin_client.put(path(analytics_match),json=data).json()==saved
    data.update(request_id=str(uuid4()),expected_revision=1);data['document']['actions'][0]['success']=False
    second=admin_client.put(path(analytics_match),json=data);assert second.status_code==200,second.text
    old=admin_client.get(path(analytics_match)+f"/versions/{saved['id']}").json()
    assert old['canonical_actions'][0]['success'] is True
    assert admin_client.get(f"/api/v1/matches/{analytics_match['id']}").json()['protocol']==before


def test_foreign_player_and_unreviewed_episode_are_rejected_before_recording(admin_client,analytics_match):
    data=body(analytics_match);data['document']['actions'][0]['player_id']=str(uuid4())
    assert admin_client.put(path(analytics_match),json=data).status_code==422
    data=body(analytics_match);data['document']['actions'][0]['source_episode_id']='e1'
    assert admin_client.put(path(analytics_match),json=data).status_code==422
    assert admin_client.get(path(analytics_match)).json()['versions']==[]


def test_ordinary_admin_cannot_read_or_write_manual_facts(admin_client,analytics_match):
    grant(admin_client,False)
    assert admin_client.get(path(analytics_match)).status_code==403
    assert admin_client.put(path(analytics_match),json=body(analytics_match)).status_code==403


@pytest.mark.parametrize('reviewed',['accepted','rejected','unreviewed'])
def test_video_goal_link_uses_only_reviewed_actor_and_does_not_duplicate_protocol(admin_client,analytics_match,send_command,reviewed):
    from .test_understanding import imported,review
    from .test_analysis_assignments import save_assignments,command,assignments
    pid=next(p['player_id'] for p in analytics_match['lineup'] if p['side']=='home')
    goal=str(uuid4())
    changed=send_command(analytics_match,'add_event',{'event':{'id':goal,'kind':'goal','side':'home',
        'player_id':pid,'period':1,'elapsed_ms':1000}})
    assert changed.status_code==200,changed.text
    match=changed.json();run=imported(admin_client,match)
    if reviewed!='unreviewed':
        decision=review(admin_client,match,run,reviewed);assert decision.status_code==200,decision.text
        run=admin_client.get(f"/api/v1/matches/{match['id']}/analysis/runs/{run['id']}").json()
    values=assignments(run)
    values[0]['player_id']=pid;values[1]['player_id']=pid
    run=save_assignments(admin_client,match,run,values).json();run=command(admin_client,match,run,'confirm').json()
    data=body(match);action=data['document']['actions'][0]
    action.update(kind='goal_candidate',player_id=pid,source_episode_id='e1',source_video_ms=1000)
    data['document'].update(source_analysis_run_id=run['id'],links=[{'canonical_event_id':goal,'source_event_id':action['id']}])
    response=admin_client.put(path(match),json=data)
    if reviewed=='accepted':
        assert response.status_code==200,response.text
        goals=[r for r in response.json()['canonical_actions'] if r['kind']=='goal']
        assert len(goals)==1 and goals[0]['player_id']==pid and len(goals[0]['source_refs'])==3
    else:assert response.status_code==422,response.text


def test_category_coverage_cannot_overlap_or_include_foreign_players(admin_client,analytics_match):
    data=body(analytics_match)
    data['document']['completeness']['passes'].append({'status':'complete','intervals':[[1000,3000]]})
    assert admin_client.put(path(analytics_match),json=data).status_code==422
    data=body(analytics_match);data['document']['completeness']['passes'][0]['player_ids']=[str(uuid4())]
    assert admin_client.put(path(analytics_match),json=data).status_code==422


def test_action_coordinates_use_actual_hall_and_reject_bool(admin_client,analytics_match):
    data=body(analytics_match)
    data['document']['actions'][0].update(start_xy=[40.5,15],end_xy=[41,15.5])
    good=admin_client.put(path(analytics_match),json=data);assert good.status_code==200,good.text
    assert good.json()['provenance']['pitch']=={'length_m':41,'width_m':15.5}
    data=body(analytics_match);data['expected_revision']=1;data['document']['actions'][0]['start_xy']=[True,1]
    assert admin_client.put(path(analytics_match),json=data).status_code==422


def test_contradictory_outcome_flags_are_rejected(admin_client,analytics_match):
    data=body(analytics_match);data['document']['actions'][0].update(success=True,outcome='failure')
    assert admin_client.put(path(analytics_match),json=data).status_code==422
