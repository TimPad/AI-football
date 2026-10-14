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


@pytest.mark.parametrize('mode',['native','frames'])
def test_full_file_coverage_is_not_full_match_statement(case,mode):
    from aifootball.processor.understand import run_understanding
    job,video,artifacts,ws,budget=case
    doc,_=run_understanding(job,video,artifacts,ws,client=Client(),budget=budget,mode=mode,analysis_scope='highlights')
    assert doc['source']['analysis_scope']=='highlights'
    assert doc['coverage']['status']=='complete'
    assert doc['identity_suggestions']==[]


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


def test_invalid_budget_is_rejected_before_source_or_api(tmp_path):
    from aifootball.processor.job import process_job
    with pytest.raises(ValueError,match='budget|бюджет'):
        process_job(tmp_path/'j.zip',tmp_path/'v.mp4',tmp_path/'r.zip',understand=True,vlm_max_requests=-1)
