import pytest
from aifootball.understanding.evaluate import evaluate_understanding

def documents(events=None,truth=None):
    return ({'source':{'sha256':'a'*64},'events':events or [],'observations':[],
             'identity_suggestions':[],'coverage':{'covered_intervals':[[0,5000]],'unknown_intervals':[[5000,10000]]},'states':[]},
            {'source_sha256':'a'*64,'split':'control','events':truth or [],'observations':[],'states':[],
             'coverage':[[0,10000]]})

def event(start=1000,end=2000,kind='goal_candidate'):
    return {'kind':kind,'start_ms':start,'end_ms':end}

def test_category_without_examples_is_not_perfect_accuracy():
    result=evaluate_understanding(*documents())
    assert result['events']['goal_candidate']['recall'] is None
    assert result['events']['goal_candidate']['gt_count']==0

def test_duplicate_predictions_match_truth_only_once_and_missing_events_count():
    pred,truth=documents([event(),event(1100,2100),event(kind='corner')],[event(),event(20000,21000)])
    result=evaluate_understanding(pred,truth)
    assert result['events']['goal_candidate']=={'gt_count':2,'predicted_count':2,'tp':1,'fp':1,'fn':1,'precision':.5,'recall':.5,'mean_boundary_error_ms':0}
    assert result['events']['corner']['precision']==0 and result['events']['corner']['recall'] is None
    assert result['coverage']['known_fraction']==.5

def test_matching_maximizes_one_to_one_count_at_tolerance_boundary():
    pred,truth=documents([event(1000,2000),event(3000,4000)],[event(3000,4000),event(5000,6000)])
    assert evaluate_understanding(pred,truth)['events']['goal_candidate']['tp']==2

def test_wrong_number_and_uuid_and_unknown_labels_are_separate():
    pred,truth=documents();truth['observations']=[{'track_id':1,'video_ms':1000,'number':'7','player_id':'demo-a'}, {'track_id':2,'video_ms':1000,'number':None,'player_id':None}]
    pred['observations']=[{'track_id':1,'video_ms':1000,'number':'8'}];pred['identity_suggestions']=[{'track_id':1,'player_id':'demo-b'}]
    result=evaluate_understanding(pred,truth)
    assert result['numbers']=={'labelled':1,'observed':1,'correct':0,'accuracy':0,'coverage':1,'unknown_labels':1}
    assert result['identity']['precision']==0 and result['identity']['coverage']==1

@pytest.mark.parametrize('change',[{'source_sha256':'b'*64},{'split':'training'},{'split':'control','tune_intervals':[[0,5000]],'control_intervals':[[4000,8000]]}])
def test_rejects_wrong_source_and_leaking_splits(change):
    pred,truth=documents();truth.update(change)
    with pytest.raises(ValueError):evaluate_understanding(pred,truth)

def test_states_compare_duration_only_on_labelled_known_time():
    pred,truth=documents();pred['states']=[{'kind':'playing','start_ms':0,'end_ms':3000},{'kind':'unknown','start_ms':3000,'end_ms':5000}];truth['states']=[{'kind':'playing','start_ms':0,'end_ms':5000}]
    assert evaluate_understanding(pred,truth)['states']=={'labelled_ms':5000,'known_ms':3000,'correct_ms':3000,'accuracy':1,'coverage':.6}


def test_mixed_identity_track_cannot_score_as_a_correct_whole_track_assignment():
    pred,truth=documents()
    truth['observations']=[{'track_id':1,'video_ms':1000,'number':'7','player_id':'demo-a'},
                           {'track_id':1,'video_ms':8000,'number':'8','player_id':'demo-b'}]
    pred['identity_suggestions']=[{'track_id':1,'player_id':'demo-b','status':'candidate'}]
    result=evaluate_understanding(pred,truth)['identity']
    assert result['precision']==0 and result['correct']==0
    assert result['conflicting_tracks']==1
    truth['observations'].reverse()
    assert evaluate_understanding(pred,truth)['identity']==result
