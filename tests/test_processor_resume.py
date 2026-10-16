import json
from pathlib import Path
from types import SimpleNamespace
from hashlib import sha256
import os
import sys
import subprocess
import numpy as np
import polars as pl
import pytest
from conftest import write_video
from test_processor_job import job_package
from aifootball import schemas


class Array:
    def __init__(self,values):self.values=np.array(values)
    def cpu(self):return self
    def numpy(self):return self.values


class Predictor:
    calls=0
    empty=False
    def __init__(self,path):pass
    def predict(self,frames,**kwargs):
        type(self).calls+=len(frames)
        result=[]
        for frame in frames:
            boxes=SimpleNamespace(xyxy=Array([] if self.empty else [[80,30,105,90]]),
                cls=Array([] if self.empty else [0]),conf=Array([] if self.empty else [.95]))
            result.append(SimpleNamespace(boxes=boxes))
        return result


@pytest.fixture
def cv_case(venue,tmp_path,monkeypatch):
    monkeypatch.setitem(sys.modules,'ultralytics',SimpleNamespace(YOLO=Predictor))
    Predictor.calls=0;Predictor.empty=False
    job,_=job_package(venue,tmp_path)
    video=write_video(tmp_path/'video.mp4',n_frames=125,fps=1,size=(400,200))
    models=tmp_path/'models';models.mkdir();(models/venue.model).write_bytes(b'synthetic weights')
    from aifootball.processor.workspace import Workspace
    return job,video,models,lambda name:Workspace(tmp_path/name,{'test':'resume'})


def test_resume_replays_same_tracks_and_skips_completed_yolo(cv_case,monkeypatch):
    from aifootball.processor.cv import run_cv
    from aifootball.processor.workspace import Workspace
    job,video,models,ws=cv_case
    full=run_cv(job,video,ws('full'),models=models)
    Predictor.calls=0
    original=Workspace.put_json
    def interrupt(self,key,value):
        original(self,key,value)
        if key=='cv:chunk:0':raise RuntimeError('power loss')
    monkeypatch.setattr(Workspace,'put_json',interrupt)
    with pytest.raises(RuntimeError,match='power loss'):run_cv(job,video,ws('resumed'),models=models)
    before=Predictor.calls
    monkeypatch.setattr(Workspace,'put_json',original)
    resumed=run_cv(job,video,ws('resumed'),models=models)
    assert Predictor.calls-before==65  # frames [60,125); saved first minute is not predicted again
    for name in ('detections','tracks','state'):
        assert pl.read_parquet(full/f'{name}.parquet').equals(pl.read_parquet(resumed/f'{name}.parquet'))
    assert pl.read_parquet(resumed/'detections.parquet')['ts'].max()==124
    assert pl.read_parquet(resumed/'tracks.parquet')['track_id'].n_unique()==1
    before=Predictor.calls
    run_cv(job,video,ws('resumed'),models=models)
    assert Predictor.calls==before


def test_empty_detection_chunks_are_completed_not_predicted_again(cv_case):
    from aifootball.processor.cv import run_cv
    job,video,models,ws=cv_case;Predictor.empty=True
    root=run_cv(job,video,ws('empty'),models=models)
    assert schemas.read(root/'detections.parquet','detections').is_empty()
    assert ws('empty').get_json('cv:chunk:1')['sample_count']==60
    assert ws('empty').get_json('cv:chunk:2')['sample_count']==5
    # Задание разрешает 10 кадров/с, видео — 1 кадр/с: обработка и проверки идут на частоте видео
    assert json.loads((root/'meta.json').read_text())['target_fps']==1.0
    before=Predictor.calls;run_cv(job,video,ws('empty'),models=models)
    assert Predictor.calls==before


def test_resumed_cv_rejects_changed_weights(cv_case):
    from aifootball.processor.cv import run_cv
    job,video,models,ws=cv_case
    run_cv(job,video,ws('weights'),models=models)
    next(models.glob('*.pt')).write_bytes(b'different weights')
    with pytest.raises(ValueError,match='fingerprint'):run_cv(job,video,ws('weights'),models=models)


def test_corrupted_chunk_is_not_reused(cv_case):
    from aifootball.processor.cv import run_cv
    job,video,models,ws=cv_case
    run_cv(job,video,ws('corrupt'),models=models)
    chunk=next((ws('corrupt').root/'detections').glob('*.parquet'));chunk.write_bytes(b'bad')
    with pytest.raises(ValueError,match='chunk'):run_cv(job,video,ws('corrupt'),models=models)


def test_range_sampler_keeps_global_ids_and_original_grid(tmp_path):
    from aifootball.perception.frames import iter_frames
    video=write_video(tmp_path/'fps.mp4',n_frames=253,fps=25)
    full=[(fid,ts) for fid,ts,_ in iter_frames(video,10)]
    ranged=[(fid,ts) for fid,ts,_ in iter_frames(video,10,start_ms=1234,end_ms=9001)]
    assert ranged==[(fid,ts) for fid,ts in full if 1.234<=ts<9.001]


def test_batches_record_empty_frames_and_preserve_time(cv_case):
    from aifootball.perception.detect import detect_batches
    from aifootball.venue import load_venue
    from aifootball.processor.job import read_job
    job,video,models,ws=cv_case;Predictor.empty=True
    venue_root=ws('venue').root
    for name,raw in read_job(job).files.items():(venue_root/name).write_bytes(raw)
    venue=load_venue(venue_root)
    batches=list(detect_batches(video,venue,models/venue.model,batch_size=16,start_ms=60000))
    assert sum(len(batch.frame_ids) for batch in batches)==65
    assert batches[0].frame_ids[0]==60 and batches[0].timestamps[0]==60
    assert all(batch.detections.is_empty() for batch in batches)


def test_real_process_exit_releases_lock_and_keeps_committed_chunk(cv_case):
    from aifootball.processor.cv import run_cv
    job,video,models,ws=cv_case;root=ws('process-exit').root
    script='''
import sys,os
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path('tests').resolve()))
from test_processor_resume import Predictor
sys.modules['ultralytics']=SimpleNamespace(YOLO=Predictor)
from aifootball.processor.workspace import Workspace
from aifootball.processor.cv import run_cv
original=Workspace.put_json
def interrupted(self,key,value):
    original(self,key,value)
    if key=='cv:chunk:0':os._exit(23)
Workspace.put_json=interrupted
run_cv(Path(sys.argv[1]),Path(sys.argv[2]),Workspace(Path(sys.argv[4]),{'test':'resume'}),models=Path(sys.argv[3]))
'''
    result=subprocess.run([sys.executable,'-c',script,str(job),str(video),str(models),str(root)],capture_output=True,text=True)
    assert result.returncode==23,result.stderr
    assert ws('process-exit').get_json('cv:chunk:0')['sample_count']==60
    Predictor.calls=0
    output=run_cv(job,video,ws('process-exit'),models=models)
    assert Predictor.calls==65
    assert schemas.read(output/'tracks.parquet','tracks')['track_id'].n_unique()==1


def test_existing_process_job_still_packages_contract_v1(cv_case,tmp_path):
    from aifootball.processor.job import process_job
    from aifootball.analytics.exchange import validate_result
    job,video,models,_=cv_case
    output=process_job(job,video,tmp_path/'result.zip',models=models)
    result=validate_result(output)
    assert result.manifest['contract_version']=='1'
    assert result.manifest['source_video']['duration_s']==125
    assert Predictor.calls==125


def test_understand_cli_packages_v2_and_scope_change_reuses_cv(cv_case,tmp_path,monkeypatch):
    from aifootball.processor.job import process_job
    from aifootball.analytics.exchange import validate_result
    from test_understanding_processor import Client
    import aifootball.processor.qwen as qwen
    job,video,models,_=cv_case;client=Client()
    monkeypatch.setattr(qwen.QwenConfig,'from_env',classmethod(lambda cls:client.config))
    monkeypatch.setattr(qwen,'QwenClient',lambda config:client)
    work=tmp_path/'cli-work'
    first=validate_result(process_job(job,video,tmp_path/'first.zip',models=models,understand=True,
        work_dir=work,vlm_mode='frames',analysis_scope='unknown'))
    assert first.manifest['contract_version']=='2'
    assert first.understanding['source']['analysis_scope']=='unknown'
    predictions=Predictor.calls;requests=sum(client.calls.values())
    second=validate_result(process_job(job,video,tmp_path/'second.zip',models=models,understand=True,
        work_dir=work,resume=True,vlm_mode='frames',analysis_scope='unknown'))
    assert sum(client.calls.values())==requests and Predictor.calls==predictions
    third=validate_result(process_job(job,video,tmp_path/'third.zip',models=models,understand=True,
        work_dir=work,resume=True,vlm_mode='frames',analysis_scope='highlights'))
    assert third.understanding['source']['analysis_scope']=='highlights'
    assert sum(client.calls.values())>requests and Predictor.calls==predictions
    assert second.report==third.report


def test_understand_off_does_not_read_api_configuration(cv_case,tmp_path,monkeypatch):
    from aifootball.processor.job import process_job
    import aifootball.processor.qwen as qwen
    def forbidden(cls):raise AssertionError('API configuration must stay unused')
    monkeypatch.setattr(qwen.QwenConfig,'from_env',classmethod(forbidden))
    job,video,models,_=cv_case
    assert process_job(job,video,tmp_path/'plain.zip',models=models).exists()
