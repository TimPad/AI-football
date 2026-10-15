from copy import deepcopy
import pytest
from understanding_fixtures import event


def window(identifier,start,end,*,events=None,states=None,phases=None,summary=None):
    return {'window_id':identifier,'start_ms':start,'end_ms':end,'evidence':[],
            'document':{'time_basis':'video','observations':[],'events':events or [],'states':states or [],
                        'phases':phases or [],'summary':summary or []}}


def reconcile(results,duration=20000):
    from aifootball.understanding.reconcile import reconcile_windows
    return reconcile_windows(results,duration_ms=duration,source_sha256='a'*64)


def state(kind,start,end):return {'kind':kind,'start_ms':start,'end_ms':end,'evidence_ids':[],'limitations':[]}


def test_overlap_event_is_one_stable_candidate_not_model_id():
    first=window('w1',0,12000,events=[event(start_ms=7000,end_ms=8000)])
    second=window('w2',6000,18000,events=[event(id='other',start_ms=7100,end_ms=8100)])
    out=reconcile([first,second])
    assert len(out['events'])==1
    assert out['events'][0]['id'] not in ('e1','other')
    assert out['events'][0]['start_ms']==7000 and out['events'][0]['end_ms']==8100
    assert out==reconcile([second,first])
    assert first['document']['events'][0]['start_ms']==7000


def test_different_event_types_at_same_moment_do_not_merge():
    result=reconcile([window('w',0,12000,events=[event(),event(id='e2',kind='shot_candidate')])])
    assert len(result['events'])==2


def test_state_conflict_and_uncovered_gap_remain_unknown():
    out=reconcile([window('w1',0,8000,states=[state('playing',0,8000)]),
                   window('w2',6000,12000,states=[state('stoppage',6000,12000)])])
    assert [(s['start_ms'],s['end_ms'],s['kind']) for s in out['states']]==[
        (0,6000,'playing'),(6000,8000,'unknown'),(8000,12000,'stoppage'),(12000,20000,'unknown')]
    assert out['coverage']['unknown_intervals']==[[12000,20000]]
    assert out['coverage']['status']=='partial'


def test_timestamp_not_inside_validated_window_is_rejected():
    with pytest.raises(ValueError):reconcile([window('w',6000,12000,events=[event()])])


def test_summary_refs_are_remapped_to_final_ids():
    summary=[{'text':'Возможный гол','event_ids':['e1'],'metric_refs':[]}]
    out=reconcile([window('w',0,12000,events=[event()],summary=summary)])
    assert out['summary'][0]['event_ids']==[out['events'][0]['id']]
    assert out['summary'][0]['event_ids']!=['e1']


def test_absent_windows_do_not_invent_playing_or_perfect_coverage():
    out=reconcile([])
    assert out['coverage']=={'covered_intervals':[],'unknown_intervals':[[0,20000]],'status':'unavailable'}
    assert out['states'][0]['kind']=='unknown'


def test_delayed_commentary_without_visual_grounding_stays_candidate():
    audio={'kind':'commentary','text':'Гол!','start_ms':3000,'end_ms':4000,'clip_sha256':'b'*64}
    out=reconcile([window('w',0,12000,events=[event(audio_observations=[audio])])])
    assert out['events'][0]['kind']=='goal_candidate'
    assert out['events'][0]['limitations']==['Мяч не виден']
