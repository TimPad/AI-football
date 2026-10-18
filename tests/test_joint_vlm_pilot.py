"""Synthetic tests: no real media, provider or service database."""
from dataclasses import replace
from hashlib import sha256
import json

import httpx
import pytest

from aifootball.processor.budget import Budget
from aifootball.processor.qwen import QwenClient, QwenConfig, QwenError
from aifootball.processor.workspace import Workspace
from aifootball.understanding.types import InferenceResult, MediaAsset, Window


def environment(tmp_path):
    path=tmp_path/'clip.mp4';path.write_bytes(b'synthetic-media')
    media=MediaAsset('clip','video',path,sha256(path.read_bytes()).hexdigest(),0,12000,False)
    window=Window('window',0,12000,(),media,(1,),'native')
    workspace=Workspace(tmp_path/'work',{'purpose':'joint-vlm-pilot-v1'})
    budget=Budget(workspace,max_requests=8,max_input_tokens=200000,max_output_tokens=32768)
    return window,workspace,budget


class Client(QwenClient):
    def __init__(self,document=None,fail=False):
        super().__init__(QwenConfig('synthetic-secret','https://example.invalid/v1'))
        self.calls=0;self.document=document or {};self.fail=fail

    def infer(self,*args,**kwargs):
        self.calls+=1
        if self.fail:raise QwenError('transport',retryable=True,usage_unknown=True)
        return InferenceResult(self.document,{'prompt_tokens':100,'completion_tokens':20},'request-1',self.config.model)


def joint_document():
    return {'schema_version':'joint-pilot-v1','time_basis':'window',
            'states':[{'kind':'playing','start_ms':0,'end_ms':12000,'evidence_ids':['clip'],'limitations':[]}],
            'events':[],'phases':[],'observations':[],
            'commentary':[{'anchor_ms':1000,'text':'Команды разыгрывают мяч.','event_ids':[],'state_indices':[0]}],
            'highlight_candidates':[]}


def test_live_first_call_and_cache_only_restart_are_one_paid_call(tmp_path):
    from aifootball.understanding.pilot import paid_once
    window,workspace,budget=environment(tmp_path);client=Client(joint_document())
    first=paid_once(client,window,'Return JSON',workspace,budget,allow_network=True)
    restarted=Workspace(workspace.root,{'purpose':'joint-vlm-pilot-v1'})
    second=paid_once(client,replace(window,id='another-job'), 'Return JSON',restarted,budget,allow_network=False)
    assert client.calls==1 and first['cache_hit'] is False and second['cache_hit'] is True
    assert second['document']==first['document'] and budget.snapshot()['requests']==1


def test_timeout_is_reserved_and_never_automatically_retried(tmp_path):
    from aifootball.understanding.pilot import paid_once,PilotStopped
    window,workspace,budget=environment(tmp_path);client=Client(fail=True)
    with pytest.raises(PilotStopped,match='outcome_unknown'):
        paid_once(client,window,'JSON',workspace,budget,allow_network=True)
    with pytest.raises(PilotStopped,match='outcome_unknown'):
        paid_once(client,window,'JSON',workspace,budget,allow_network=True)
    assert client.calls==1 and budget.snapshot()['usage_unknown']
    assert budget.snapshot()['input_tokens']==25000


def test_unknown_pending_after_crash_does_not_send_again(tmp_path):
    from aifootball.understanding.pilot import paid_once,request_key,PilotStopped
    window,workspace,budget=environment(tmp_path);client=Client()
    key=request_key(client,window,'JSON',4096)
    budget.reserve_call(key,25000,4096)
    with pytest.raises(PilotStopped,match='outcome_unknown'):
        paid_once(client,window,'JSON',workspace,budget,allow_network=True)
    assert client.calls==0


def test_response_receipt_recovers_crash_before_cache_commit(tmp_path):
    from aifootball.understanding.pilot import paid_once,request_key
    window,workspace,budget=environment(tmp_path);client=Client()
    key=request_key(client,window,'JSON',4096);rid=budget.reserve_call(key,25000,4096)
    workspace.put_json('raw:'+rid,{'document':joint_document(),'usage':{'prompt_tokens':100,'completion_tokens':20},
                                  'request_id':'existing','model':client.config.model})
    result=paid_once(client,window,'JSON',workspace,budget,allow_network=False)
    assert result['cache_hit'] and client.calls==0
    assert budget.snapshot()['input_tokens']==100 and not budget.snapshot()['usage_unknown']


def test_changed_effective_prompt_or_mode_cannot_hit_wrong_cache(tmp_path):
    from aifootball.understanding.pilot import paid_once,PilotStopped,request_key
    window,workspace,budget=environment(tmp_path);client=Client()
    paid_once(client,window,'JSON context A',workspace,budget,allow_network=True)
    with pytest.raises(PilotStopped,match='cache_miss'):
        paid_once(client,window,'JSON context B',workspace,budget,allow_network=False)
    assert request_key(client,window,'JSON',1024)!=request_key(client,window,'JSON',4096)
    assert client.calls==1


def test_budget_blocks_before_network_and_raw_invalid_schema_is_reusable(tmp_path):
    from aifootball.understanding.pilot import paid_once,PilotStopped,validate_joint
    window,workspace,_=environment(tmp_path);client=Client({'unexpected':'saved'})
    budget=Budget(Workspace(tmp_path/'zero',{'purpose':'test'}),max_requests=0)
    with pytest.raises(PilotStopped,match='budget_exhausted'):
        paid_once(client,window,'JSON',budget.workspace,budget,allow_network=True)
    assert client.calls==0
    _,workspace,budget=environment(tmp_path)
    result=paid_once(client,window,'JSON',workspace,budget,allow_network=True)
    with pytest.raises(ValueError):validate_joint(result['document'],window)
    assert paid_once(client,window,'JSON',workspace,budget,allow_network=True)['cache_hit']
    assert client.calls==1


def test_native_joint_payload_has_one_clip_and_no_duplicate_overview(tmp_path):
    from aifootball.understanding.pilot import joint_window
    from understanding_fixtures import make_frame
    window,_,_=environment(tmp_path)
    overview=make_frame(tmp_path)
    converted=joint_window(replace(window,frames=(overview,)))
    body=json.loads(Client()._body(converted,'JSON',4096))
    content=body['messages'][0]['content']
    assert sum(p['type']=='video_url' for p in content)==1
    assert not any(p['type']=='image_url' for p in content)


def test_joint_validation_checks_grounding_and_bounds(tmp_path):
    from aifootball.understanding.pilot import validate_joint
    window,_,_=environment(tmp_path);doc=joint_document()
    assert validate_joint(doc,window)==doc
    doc['commentary'][0]['event_ids']=['invented']
    with pytest.raises(ValueError):validate_joint(doc,window)
    doc=joint_document();doc['states'][0]['end_ms']=12001
    with pytest.raises(ValueError):validate_joint(doc,window)
    doc=joint_document();doc['states'][0]['evidence_ids']=['unseen-frame']
    with pytest.raises(ValueError):validate_joint(doc,window)


def test_number_must_reference_transmitted_crop_for_same_track(tmp_path):
    from aifootball.understanding.pilot import validate_joint
    from understanding_fixtures import make_frame
    window,_,_=environment(tmp_path);frame=replace(make_frame(tmp_path),crop=(0,0,32,32))
    window=replace(window,frames=(frame,));doc=joint_document()
    doc['observations']=[{'track_id':1,'video_ms':1000,'number':'7','role':'player','team':None,
                          'evidence_ids':['clip'],'limitations':[]}]
    with pytest.raises(ValueError):validate_joint(doc,window,crop_tracks={frame.id:1})
    doc['observations'][0]['evidence_ids']=[frame.id]
    assert validate_joint(doc,window,crop_tracks={frame.id:1})
    with pytest.raises(ValueError):validate_joint(doc,window,crop_tracks={frame.id:2})


def test_concurrent_worker_is_blocked_before_second_network_call(tmp_path):
    from aifootball.understanding.pilot import paid_once
    window,workspace,budget=environment(tmp_path)
    other=Workspace(workspace.root,{'purpose':'joint-vlm-pilot-v1'})
    class Contending(Client):
        def infer(self,*args,**kwargs):
            with pytest.raises(ValueError,match='locked'):
                paid_once(Client(),window,'JSON',other,budget,allow_network=True)
            return super().infer(*args,**kwargs)
    client=Contending()
    paid_once(client,window,'JSON',workspace,budget,allow_network=True)
    assert client.calls==1 and budget.snapshot()['requests']==1


def test_saved_fenced_json_is_locally_recovered_without_second_request(tmp_path):
    from aifootball.understanding.pilot import paid_once
    from test_qwen_client import sse,completed
    window,workspace,budget=environment(tmp_path);calls=[]
    def respond(request):
        calls.append(request)
        return httpx.Response(200,content=sse(completed('```json\n'+json.dumps(joint_document())+'\n```')))
    client=QwenClient(QwenConfig('test','https://example.invalid/v1'),transport=httpx.MockTransport(respond))
    assert paid_once(client,window,'JSON',workspace,budget,allow_network=True)['document']==joint_document()
    assert paid_once(client,window,'JSON',workspace,budget,allow_network=True)['cache_hit']
    assert len(calls)==1 and not budget.snapshot()['usage_unknown']


def runner():
    import importlib.util
    from pathlib import Path
    spec=importlib.util.spec_from_file_location('joint_runner',Path(__file__).parents[1]/'scripts/verify_joint_vlm.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('commentary',[None,[{}],[{'anchor_ms':'bad'}]])
def test_report_can_display_rejected_response_without_interpreting_it(tmp_path,commentary):
    row={'start_ms':0,'end_ms':12000,'clip':str(tmp_path/'clip.mp4'),'status':'invalid_response',
         'document':{'commentary':commentary,'other':'<script>alert(1)</script>'}}
    runner().render({'cases':[{'id':'test','split':'tune','windows':[row]}]},tmp_path/'report.html')
    content=(tmp_path/'report.html').read_text()
    assert '<script>alert(1)</script>' not in content and '&lt;script&gt;' in content


def test_context_cannot_borrow_cv_tracks_from_another_window(tmp_path):
    import polars as pl
    window,_,_=environment(tmp_path);window=replace(window,start_ms=12000,end_ms=24000)
    tracks=pl.DataFrame({'frame_id':[3],'ts':[3.0],'track_id':[1],'team':['A'],'role':['player'],
                         'x1':[0.],'y1':[0.],'x2':[32.],'y2':[32.],'conf':[.9]})
    state=pl.DataFrame(schema={'ts':pl.Float64,'speed':pl.Float64,'team':pl.String,'role':pl.String,'track_id':pl.Int32})
    context=runner().prepare_context(window,tracks,{'width':320,'height':240},{},state)
    assert context['cv_hints']==[]


def test_local_projection_repairs_only_metadata_nulls_and_discards_ungrounded_lines(tmp_path):
    from aifootball.understanding.pilot import project_joint
    window,_,_=environment(tmp_path);doc=joint_document();doc.pop('schema_version');doc.pop('time_basis')
    doc['phases']=[{'kind':'unknown','start_ms':0,'end_ms':12000,'team':None,'possession':'unknown',
                    'attacking_direction':'unknown','evidence_ids':['clip'],'limitations':[]}]
    doc['commentary'].append({'anchor_ms':1000,'text':'Недоказанное описание','event_ids':[],'state_indices':[]})
    original=json.dumps(doc,sort_keys=True)
    projected,repairs=project_joint(doc,window)
    assert projected['schema_version']=='joint-pilot-v1' and projected['time_basis']=='window'
    assert projected['phases'][0]['possession'] is None and len(projected['commentary'])==1
    assert projected['commentary'][0]['text']=='Команды разыгрывают мяч.' and len(repairs)==4
    assert json.dumps(doc,sort_keys=True)==original


def test_local_projection_never_fabricates_evidence_or_fixes_invalid_times(tmp_path):
    from aifootball.understanding.pilot import project_joint
    window,_,_=environment(tmp_path);doc=joint_document();doc['states'][0]['end_ms']=15000
    with pytest.raises(ValueError):project_joint(doc,window)
    doc=joint_document();doc['commentary'][0]['event_ids']=['invented']
    with pytest.raises(ValueError):project_joint(doc,window)


def test_saved_wire_survives_crash_without_new_paid_call(tmp_path):
    from aifootball.understanding.pilot import paid_once,request_key
    window,workspace,budget=environment(tmp_path);client=Client()
    key=request_key(client,window,'JSON',4096);rid=budget.reserve_call(key,25000,4096)
    workspace.put_json('wire:'+rid,{'content':json.dumps(joint_document()),'usage':{'prompt_tokens':100,'completion_tokens':20},
                                   'request_id':'saved-wire','model':client.config.model})
    result=paid_once(client,window,'JSON',workspace,budget,allow_network=False)
    assert result['cache_hit'] and result['document']==joint_document() and client.calls==0
    assert budget.snapshot()['requests']==1 and budget.snapshot()['input_tokens']==100
