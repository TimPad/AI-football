import copy
from hashlib import sha256
import pytest
from test_analysis_exchange import result_zip
from understanding_fixtures import understanding_document, make_frame, event


@pytest.fixture
def case():
    from aifootball.analytics.exchange import validate_result
    result=validate_result(result_zip())
    doc=understanding_document(result.manifest,result.tracks,
                               duration_ms=round(result.manifest['source_video']['duration_s']*1000))
    return doc,result.manifest,result.tracks


def validate(case, **kwargs):
    from aifootball.understanding.schema import validate_understanding
    doc,manifest,tracks=case
    return validate_understanding(doc,manifest=manifest,tracks=tracks,**kwargs)


def test_unknown_file_coverage_is_valid_but_not_full_match(case):
    out=validate(case)
    assert out['source']['analysis_scope']=='unknown'
    assert out['coverage']['status']=='unavailable'
    assert out is not case[0]


@pytest.mark.parametrize('name',[[],{},True,3,None])
def test_malformed_metric_name_is_a_repairable_validation_error(case,name):
    case[0]['summary']=[{'text':'Метрика','event_ids':[],'metric_refs':[{
        'period_key':'all','track_id':case[2]['tracks'][0]['track_id'],'metric_name':name}]}]
    with pytest.raises(ValueError):validate(case)


def test_number_without_image_evidence_is_rejected(case):
    case[0]['observations']=[{'track_id':case[2]['tracks'][0]['track_id'],'video_ms':1000,
        'role':'player','number':'7','team':'A','evidence_ids':[],'visible_features':[],'limitations':[]}]
    with pytest.raises(ValueError,match='evidence'):validate(case)


def test_processing_counts_are_bounded_consistent_and_optional_for_legacy(case):
    assert 'processing' not in validate(case)
    case[0]['processing']={'status':'complete','tasks_planned':1,'tasks_completed':1,
        'scene_tasks_planned':1,'scene_tasks_completed':1,'identity_tasks_planned':0,'identity_tasks_completed':0,'issues':[]}
    assert validate(case)['processing']['status']=='complete'
    case[0]['processing']['issues']=['Бюджет обработки исчерпан']
    with pytest.raises(ValueError,match='processing status'):validate(case)
    case[0]['processing'].update(status='partial',identity_tasks_completed=1)
    with pytest.raises(ValueError,match='stage count'):validate(case)


@pytest.mark.parametrize('mutate',[
    lambda d:d.update(extra=1),
    lambda d:d.update(schema_version='9'),
    lambda d:d['source'].update(duration_ms=float('nan')),
    lambda d:d['source'].update(analysis_scope='full'),
    lambda d:d['source'].update(sha256='f'*64),
    lambda d:d['context'].update(job_id='not-uuid'),
    lambda d:d['context'].update(extra=1),
    lambda d:d['provider']['settings'].update(api_key='secret'),
    lambda d:d['budget'].update(requests=True),
    lambda d:d['coverage'].update(status='complete'),
    lambda d:d['coverage'].update(unknown_intervals=[[1,d['source']['duration_ms']]]),
    lambda d:d['coverage'].update(covered_intervals=[[0,1000]]),
    lambda d:d.update(events=[event(start_ms=-1)]),
    lambda d:d.update(events=[event(end_ms=d['source']['duration_ms']+1)]),
    lambda d:d.update(events=[event(kind='confirmed_goal')]),
    lambda d:d.update(events=[event(evidence_ids=['missing'])]),
    lambda d:d.update(events=[event(track_ids=[999999])]),
    lambda d:d.update(events=[event(),event()]),
    lambda d:d.update(summary=[{'text':'Гол','event_ids':['absent'],'metric_refs':[]}]),
    lambda d:d.update(events=[event()]*10001),
    lambda d:d.update(observations=[{}]*10001),
    lambda d:d.update(evidence=[{}]*501),
])
def test_rejects_untrusted_document_before_storage(case,mutate):
    mutate(case[0])
    with pytest.raises(ValueError):validate(case)


def test_evidence_must_exist_and_match_hash(case,tmp_path):
    frame=make_frame(tmp_path)
    raw=frame.path.read_bytes()
    evidence={'id':frame.id,'frame_id':frame.frame_id,'video_ms':frame.video_ms,
              'path':f'evidence/{frame.id}.jpg','sha256':frame.sha256,'crop':None,'kind':'overview'}
    case[0]['evidence']=[evidence]
    with pytest.raises(ValueError,match='evidence'):validate(case,files={})
    with pytest.raises(ValueError,match='hash'):validate(case,files={evidence['path']:b'bad'})
    assert validate(case,files={evidence['path']:raw})['evidence'][0]['id']=='f25'
    with pytest.raises(ValueError):validate(case,files={evidence['path']:raw+b'x'*(512*1024)})


def test_player_uuid_must_belong_to_roster(case):
    tid=case[2]['tracks'][0]['track_id']
    suggestion={'track_id':tid,'player_id':'11111111-1111-4111-8111-111111111111',
                'status':'candidate','number':'7','team':'A','evidence_ids':[],'reasons':[]}
    case[0]['evidence']=[{'id':'f1','frame_id':25,'video_ms':1000,'path':'evidence/f1.jpg','sha256':'a'*64,'crop':None,'kind':'overview'}]
    suggestion['evidence_ids']=['f1']
    case[0]['identity_suggestions']=[suggestion]
    with pytest.raises(ValueError,match='roster'):validate(case,rosters=[])
    assert validate(case,rosters=[{'player_id':suggestion['player_id']}])['identity_suggestions'][0]['player_id']==suggestion['player_id']


def test_window_timestamps_translate_once_and_do_not_mutate_input(tmp_path):
    from aifootball.understanding.types import Window
    from aifootball.understanding.schema import validate_window_response
    frame=make_frame(tmp_path,video_ms=11200)
    window=Window('w1',10000,12000,(frame,),None,(1,),'frames')
    answer={'time_basis':'window','observations':[], 'states':[], 'phases':[],
            'events':[event(start_ms=200,end_ms=900,evidence_ids=[frame.id],track_ids=[1])], 'summary':[]}
    result=validate_window_response(answer,window)
    assert result['document']['events'][0]['start_ms']==10200
    assert result['document']['events'][0]['end_ms']==10900
    assert answer['events'][0]['start_ms']==200
    with pytest.raises(ValueError):validate_window_response(result['document'],window)
    answer['events'][0]['end_ms']=2001
    with pytest.raises(ValueError):validate_window_response(answer,window)


def test_native_audio_observation_bound_to_source_clip(tmp_path):
    from aifootball.understanding.types import Window,MediaAsset
    from aifootball.understanding.schema import validate_window_response
    media=MediaAsset('clip','video',tmp_path/'clip.mp4','a'*64,10000,12000,True)
    window=Window('w1',10000,12000,(),media,(),'native')
    audio={'kind':'whistle','text':None,'start_ms':200,'end_ms':500,'clip_sha256':'a'*64}
    answer={'time_basis':'window','observations':[],'states':[],'phases':[],
            'events':[event(start_ms=200,end_ms=900,audio_observations=[audio])],'summary':[]}
    out=validate_window_response(answer,window)
    assert out['document']['events'][0]['audio_observations'][0]['start_ms']==10200
    audio['clip_sha256']='b'*64
    with pytest.raises(ValueError):validate_window_response(answer,window)


def test_json_size_cap(case):
    case[0]['summary']=[{'text':'x'*10000,'event_ids':[],'metric_refs':[]}]*900
    with pytest.raises(ValueError):validate(case)


@pytest.mark.parametrize('item',[
    event(kind=[]),event(team={}),event(track_ids=[True]),
])
def test_malformed_event_fields_raise_contract_error(case,item):
    case[0]['events']=[item]
    with pytest.raises(ValueError):validate(case)


def test_free_summary_without_fact_reference_is_rejected(case):
    case[0]['summary']=[{'text':'Игрок был лучшим','event_ids':[],'metric_refs':[]}]
    with pytest.raises(ValueError):validate(case)


def test_actual_token_overrun_remains_reportable(case):
    # Estimates cannot retract tokens already billed by the provider.
    case[0]['budget'].update(requests=1,max_input_tokens=100,input_tokens=120)
    assert validate(case)['budget']['input_tokens']==120


@pytest.mark.parametrize('kind',['kickoff','kick_in','corner','free_kick_candidate','penalty_candidate',
    'timeout','shot_candidate','save_candidate','goal_candidate','substitution_candidate',
    'keeper_out_candidate','pressing_candidate','compact_block_candidate','unknown'])
def test_supported_futsal_event_is_preserved_as_observation(case,kind):
    case[0]['events']=[event(kind=kind)]
    assert validate(case)['events'][0]['kind']==kind


@pytest.mark.parametrize('kind',['pre_match','playing','stoppage','break','post_match','unknown'])
def test_supported_game_state_remains_bounded(case,kind):
    case[0]['states']=[{'kind':kind,'start_ms':1000,'end_ms':2000,'evidence_ids':[],'limitations':[]}]
    assert validate(case)['states'][0]['kind']==kind
