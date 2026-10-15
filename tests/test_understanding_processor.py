from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from collections import Counter
import pytest
from conftest import write_video
from test_processor_job import job_package
from report_fixtures import synthetic_match
from aifootball import schemas


class Client:
    def __init__(self,fail=None):
        from aifootball.processor.qwen import QwenConfig
        self.config=QwenConfig('test-key','https://example.invalid/v1');self.calls=Counter();self.fail=fail
    def infer(self,window,prompt,*,max_output_tokens):
        from aifootball.understanding.types import InferenceResult
        self.calls[window.id]+=1
        if self.fail and self.fail(window):raise RuntimeError('power loss')
        return InferenceResult({'time_basis':'window','observations':[],'states':[],'phases':[],'events':[],'summary':[]},
                               {'prompt_tokens':100,'completion_tokens':20},'fake-request','qwen3.8-omni-flash')


@pytest.fixture
def case(venue,tmp_path):
    from aifootball.processor.job import read_job
    from aifootball.processor.workspace import Workspace
    from aifootball.processor.budget import Budget
    job,_=job_package(venue,tmp_path)
    video=write_video(tmp_path/'silent.mp4',n_frames=100,fps=4,size=(400,200))
    state,tracks=synthetic_match(seconds=20,sprint=False)
    artifacts=tmp_path/'artifacts';schemas.write(state,artifacts/'state.parquet','state');schemas.write(tracks,artifacts/'tracks.parquet','tracks')
    ws=Workspace(tmp_path/'understanding',{'source':'test'})
    return read_job(job),video,artifacts,ws,Budget(ws,max_requests=50)


def test_completed_windows_are_not_called_again_after_real_restart(case):
    from aifootball.processor.understand import run_understanding
    job,video,artifacts,ws,budget=case;count=0
    def fail_second(window):
        nonlocal count
        count+=1
        return count==2
    first=Client(fail=fail_second)
    with pytest.raises(RuntimeError):run_understanding(job,video,artifacts,ws,client=first,budget=budget,mode='frames')
    resumed=Client()
    doc,files=run_understanding(job,video,artifacts,ws,client=resumed,budget=budget,mode='frames')
    first_id=next(iter(first.calls))
    assert resumed.calls[first_id]==0
    assert doc['coverage']['status']=='complete'
    assert doc['budget']['usage_unknown'] is True
    assert all(name.startswith('evidence/') and name.endswith('.jpg') for name in files)


def test_saved_provider_receipt_is_recovered_if_completed_window_write_is_interrupted(case,monkeypatch):
    from aifootball.processor.understand import run_understanding
    job,video,artifacts,ws,budget=case;put=ws.put_json;interrupted=False
    def crash(key,value):
        nonlocal interrupted
        if key.startswith('understanding:') and not interrupted:
            interrupted=True;raise RuntimeError('power loss before completed-window commit')
        return put(key,value)
    monkeypatch.setattr(ws,'put_json',crash);first=Client()
    with pytest.raises(RuntimeError):run_understanding(job,video,artifacts,ws,client=first,budget=budget,mode='frames')
    resumed=Client();doc,_=run_understanding(job,video,artifacts,ws,client=resumed,budget=budget,mode='frames')
    assert resumed.calls[next(iter(first.calls))]==0
    assert doc['budget']['requests']==5


@pytest.mark.parametrize('mode',['native','frames'])
def test_full_file_coverage_is_not_full_match_statement(case,mode):
    from aifootball.processor.understand import run_understanding
    job,video,artifacts,ws,budget=case
    doc,_=run_understanding(job,video,artifacts,ws,client=Client(),budget=budget,mode=mode,analysis_scope='highlights')
    assert doc['source']['analysis_scope']=='highlights'
    assert doc['coverage']['status']=='complete'
    assert doc['identity_suggestions']==[]


def test_exported_evidence_contains_referenced_frames_only(case):
    from aifootball.processor.understand import run_understanding
    from aifootball.understanding.types import InferenceResult
    job,video,artifacts,ws,budget=case
    class OneEvidence(Client):
        def infer(self,window,prompt,*,max_output_tokens):
            self.calls[window.id]+=1
            return InferenceResult({'time_basis':'window','observations':[],'phases':[],'events':[],'summary':[],
                'states':[{'kind':'playing','start_ms':0,'end_ms':window.end_ms-window.start_ms,
                           'evidence_ids':[window.frames[0].id],'limitations':[]}]},
                {'prompt_tokens':100,'completion_tokens':20},'fake','qwen3.8-omni-flash')
    doc,files=run_understanding(job,video,artifacts,ws,client=OneEvidence(),budget=budget,mode='frames')
    refs={eid for s in doc['states'] for eid in s['evidence_ids']}
    assert {e['id'] for e in doc['evidence']}==refs
    assert len(files)<10


def test_request_budget_stops_before_next_paid_attempt(case):
    from aifootball.processor.understand import run_understanding
    from aifootball.processor.budget import Budget
    from aifootball.processor.workspace import Workspace
    job,video,artifacts,ws,_=case
    limited=Workspace(ws.root/'limited',{'source':'test'})
    budget=Budget(limited,max_requests=1)
    client=Client();doc,_=run_understanding(job,video,artifacts,limited,client=client,budget=budget,mode='frames')
    assert sum(client.calls.values())==1
    assert doc['budget']['requests']==1 and doc['coverage']['status']=='partial'


def test_cli_understand_options_are_explicit():
    from aifootball.cli import build_parser
    args=build_parser().parse_args(['process-job','--job','j.zip','--video','v.mp4','--output','r.zip',
        '--understand','--work-dir','work','--resume','--vlm-mode','frames','--analysis-scope','highlights',
        '--vlm-max-requests','1'])
    assert args.understand and args.resume and args.vlm_max_requests==1
    assert args.analysis_scope=='highlights'


def test_resume_requires_existing_work_directory_before_video_or_api(tmp_path):
    from aifootball.processor.job import process_job
    with pytest.raises(ValueError,match='resume|work'):
        process_job(tmp_path/'j.zip',tmp_path/'v.mp4',tmp_path/'r.zip',resume=True)


def test_retry_attempts_cannot_bypass_request_budget(case):
    from aifootball.processor.understand import run_understanding
    from aifootball.processor.workspace import Workspace
    from aifootball.processor.budget import Budget
    from aifootball.processor.qwen import QwenError
    job,video,artifacts,ws,_=case
    class Busy(Client):
        def infer(self,window,prompt,*,max_output_tokens):
            self.calls[window.id]+=1
            raise QwenError('http_429',retryable=True,retry_after=0)
    client=Busy();limited=Workspace(ws.root/'retry',{'source':'test'})
    doc,_=run_understanding(job,video,artifacts,limited,client=client,budget=Budget(limited,max_requests=1),mode='frames',sleep=lambda delay:None)
    assert sum(client.calls.values())==1
    assert doc['coverage']['status']=='unavailable'


def test_schema_repair_is_one_additional_paid_attempt(case):
    from aifootball.processor.understand import run_understanding
    from aifootball.understanding.types import InferenceResult
    job,video,artifacts,ws,budget=case
    class Repair(Client):
        def infer(self,window,prompt,*,max_output_tokens):
            if not self.calls:
                self.calls[window.id]+=1
                return InferenceResult({'bad':'schema'},{'prompt_tokens':100,'completion_tokens':10},'bad-request','qwen3.8-omni-flash')
            return super().infer(window,prompt,max_output_tokens=max_output_tokens)
    client=Repair();doc,_=run_understanding(job,video,artifacts,ws,client=client,budget=budget,mode='frames')
    assert max(client.calls.values())==2
    assert doc['budget']['requests']==6
    assert doc['coverage']['status']=='complete'


def test_invalid_metric_type_is_repaired_and_does_not_poison_resume(case):
    from aifootball.processor.understand import run_understanding
    from aifootball.understanding.types import InferenceResult
    job,video,artifacts,ws,budget=case
    class Malformed(Client):
        def infer(self,window,prompt,*,max_output_tokens):
            if not self.calls:
                self.calls[window.id]+=1
                return InferenceResult({'time_basis':'window','observations':[],'states':[],'phases':[],'events':[],
                    'summary':[{'text':'Метрика','event_ids':[],'metric_refs':[{'period_key':'all','track_id':1,'metric_name':[]}]}]},
                    {'prompt_tokens':100,'completion_tokens':10},'malformed','qwen3.8-omni-flash')
            return super().infer(window,prompt,max_output_tokens=max_output_tokens)
    client=Malformed();doc,_=run_understanding(job,video,artifacts,ws,client=client,budget=budget,mode='frames')
    assert doc['budget']['requests']==6 and doc['coverage']['status']=='complete'
    resumed=Client();run_understanding(job,video,artifacts,ws,client=resumed,budget=budget,mode='frames')
    assert not resumed.calls


def test_resume_skips_malformed_raw_receipt_after_interrupted_validation(case,monkeypatch):
    from aifootball.processor.understand import run_understanding
    from aifootball.understanding.types import InferenceResult
    job,video,artifacts,ws,budget=case;put=ws.put_json;crashed=False
    def interrupt(key,value):
        nonlocal crashed
        put(key,value)
        if key.startswith('raw:') and not crashed:
            crashed=True;raise RuntimeError('interrupted after receipt')
    class Malformed(Client):
        def infer(self,window,prompt,*,max_output_tokens):
            return InferenceResult({'time_basis':'window','observations':[],'states':[],'phases':[],'events':[],
                'summary':[{'text':'Метрика','event_ids':[],'metric_refs':[{'period_key':'all','track_id':1,'metric_name':[]}]}]},
                {'prompt_tokens':100,'completion_tokens':10},'malformed','qwen3.8-omni-flash')
    monkeypatch.setattr(ws,'put_json',interrupt)
    with pytest.raises(RuntimeError):run_understanding(job,video,artifacts,ws,client=Malformed(),budget=budget,mode='frames')
    resumed=Client();doc,_=run_understanding(job,video,artifacts,ws,client=resumed,budget=budget,mode='frames')
    assert doc['coverage']['status']=='complete' and doc['budget']['requests']==6


@pytest.mark.parametrize('unfinished',['identity','refinement'])
def test_processing_status_exposes_unfinished_tasks_even_with_full_temporal_coverage(case,monkeypatch,unfinished):
    from aifootball.processor import understand as module
    from aifootball.processor.workspace import Workspace
    from aifootball.processor.budget import Budget
    from aifootball.understanding.types import InferenceResult
    from understanding_fixtures import make_frame
    job,video,artifacts,ws,_=case
    write_video(video,n_frames=32,fps=4,size=(400,200))
    specs=[{'id':'scene','start_ms':0,'end_ms':8000,'fps':1,'track_ids':[1]}]
    if unfinished=='refinement':specs.append({'id':'refine','start_ms':0,'end_ms':5000,'fps':1,'track_ids':[1]})
    monkeypatch.setattr(module,'plan_windows',lambda **kwargs:specs)
    monkeypatch.setattr(module,'select_player_frames',lambda *args:{1:[make_frame(ws.root,frame_id=0,video_ms=0)]} if unfinished=='identity' else {})
    class Playing(Client):
        def infer(self,window,prompt,*,max_output_tokens):
            self.calls[window.id]+=1
            return InferenceResult({'time_basis':'window','observations':[],'events':[],'phases':[],'summary':[],
                'states':[{'kind':'playing','start_ms':0,'end_ms':window.end_ms-window.start_ms,
                           'evidence_ids':[window.frames[0].id],'limitations':[]}]},
                {'prompt_tokens':100,'completion_tokens':20},'fake','qwen3.8-omni-flash')
    limited=Workspace(ws.root/'partial',{'source':'test'})
    result,_=module.run_understanding(job,video,artifacts,limited,client=Playing(),budget=Budget(limited,max_requests=1),mode='frames')
    assert result['coverage']['status']=='complete'
    assert result['processing']['status']=='partial'
    assert result['processing']['tasks_planned']==2 and result['processing']['tasks_completed']==1
    assert any('Бюджет' in issue for issue in result['processing']['issues'])


def test_invalid_budget_is_rejected_before_source_or_api(tmp_path):
    from aifootball.processor.job import process_job
    with pytest.raises(ValueError,match='budget|бюджет'):
        process_job(tmp_path/'j.zip',tmp_path/'v.mp4',tmp_path/'r.zip',understand=True,vlm_max_requests=-1)


def test_exhausted_budget_still_assembles_already_paid_later_windows(case):
    import json
    from aifootball.processor.understand import run_understanding
    from aifootball.processor.budget import Budget
    from aifootball.processor.workspace import Workspace
    job,video,artifacts,ws,_=case
    probe=Workspace(ws.root/'probe',{'source':'test'});counter=Client()
    run_understanding(job,video,artifacts,probe,client=counter,budget=Budget(probe,max_requests=500),mode='frames')
    total=sum(counter.calls.values());assert total>2
    paid=Workspace(ws.root/'paid',{'source':'test'});budget=Budget(paid,max_requests=total)
    first=Client();run_understanding(job,video,artifacts,paid,client=first,budget=budget,mode='frames')
    lost=next(iter(first.calls))
    for path in (paid.root/'cache').glob('*.json'):
        value=json.loads(path.read_text()).get('value')
        if isinstance(value,dict) and lost in (value.get('window_id'),(value.get('document') or {}).get('window_id')):path.unlink()
    resumed=Client()
    doc,_=run_understanding(job,video,artifacts,paid,client=resumed,budget=budget,mode='frames')
    assert sum(resumed.calls.values())==0
    assert doc['processing']['tasks_completed']==total-1
    assert 'Бюджет обработки исчерпан' in doc['processing']['issues'] and doc['processing']['status']=='partial'


def test_identity_answer_keeps_number_observations_and_ignores_scene_claims():
    from aifootball.processor.understand import identity_only
    answer={'time_basis':'window','observations':[{'track_id':3}],'events':[{'id':'e'}],'states':[{}],'phases':[{}],
            'summary':[{'text':'Игрок в атаке','event_ids':[],'metric_refs':[]}]}
    out=identity_only(answer)
    assert out['observations']==[{'track_id':3}] and not any(out[k] for k in ('events','states','phases','summary'))
    assert answer['summary'] and identity_only(None) is None
