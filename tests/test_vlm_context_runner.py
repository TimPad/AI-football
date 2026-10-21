from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
import importlib.util
import json
from pathlib import Path

import polars as pl
import pytest

from test_joint_vlm_pilot import Client
from test_vlm_context_commentary import response
from test_vlm_match_context import passport


def runner(monkeypatch):
    scripts=Path(__file__).parents[1]/'scripts';monkeypatch.syspath_prepend(str(scripts))
    spec=importlib.util.spec_from_file_location('context_runner',scripts/'verify_context_vlm.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def manifest(tmp_path,*,windows=1):
    video=tmp_path/'source.mp4';video.write_bytes(b'synthetic-video')
    artifacts=tmp_path/'artifacts';artifacts.mkdir()
    for name in ('tracks.parquet','state.parquet'): (artifacts/name).write_bytes(name.encode())
    (artifacts/'metrics.json').write_text('{"pitch":{}}')
    source=sha256(video.read_bytes()).hexdigest();(artifacts/'meta.json').write_text(json.dumps({'source_sha256':source}))
    p=passport();p['source_sha256']=source
    labels=tmp_path/'DO_NOT_SEND_GROUND_TRUTH.parquet'
    pl.DataFrame({'ts':[.5,2.,8.],'event':['A','dead','B']}).write_parquet(labels)
    return {'cases':[{'id':'case1','video':str(video),'artifacts':str(artifacts),'labels':str(labels),
                      'start_ms':0,'end_ms':windows*12000,'passport':p}]}


def prepare(case,begin,end,output):
    from aifootball.understanding.types import MediaAsset,Window
    folder=output/'media'/case['id']/str(begin);folder.mkdir(parents=True,exist_ok=True)
    path=folder/'clip.mp4';path.write_bytes(f'synthetic-{begin}'.encode())
    media=MediaAsset('clip','video',path,sha256(path.read_bytes()).hexdigest(),begin,end,False)
    return Window(f'w{begin}',begin,end,(),media,(1,),'native'),{'scope':'continuous_excerpt'},{}


def test_live_once_then_restart_uses_frozen_plan_and_cache(monkeypatch,tmp_path):
    m=runner(monkeypatch);inputs=manifest(tmp_path);client=Client(response());output=tmp_path/'out'
    first=m.run(inputs,output,apply=True,client=client,prepare=prepare)
    assert first['new_requests_this_run']==1 and client.calls==1
    monkeypatch.setattr(m,'context_prompt',lambda *a,**kw:(_ for _ in ()).throw(AssertionError('replanned')))
    second=m.run(inputs,output,cache_only=True,client=client,prepare=lambda *a:(_ for _ in ()).throw(AssertionError('rebuilt')))
    assert second['new_requests_this_run']==0 and client.calls==1
    assert second['cases'][0]['feed']==first['cases'][0]['feed']
    assert (output/'cases/case1/chronology.json').exists() and (output/'cases/case1/commentary.json').exists()


@pytest.mark.parametrize('change',['passport','source','tracks'])
def test_changed_inputs_are_rejected_in_same_workspace_before_network(monkeypatch,tmp_path,change):
    m=runner(monkeypatch);inputs=manifest(tmp_path);client=Client(response());output=tmp_path/'out'
    m.run(inputs,output,apply=True,client=client,prepare=prepare)
    modified=deepcopy(inputs);case=modified['cases'][0]
    if change=='passport':case['passport']['facts']['team_A_color']['value']='розовая'
    elif change=='source':Path(case['video']).write_bytes(b'changed-source')
    else:(Path(case['artifacts'])/'tracks.parquet').write_bytes(b'changed-tracks')
    with pytest.raises(ValueError):m.run(modified,output,apply=True,client=client,prepare=prepare)
    assert client.calls==1


@pytest.mark.parametrize('difference',['passport','artifacts','partial_interval'])
def test_overlapping_cases_of_same_source_are_rejected_before_any_call(monkeypatch,tmp_path,difference):
    m=runner(monkeypatch);inputs=manifest(tmp_path);second=deepcopy(inputs['cases'][0]);second['id']='case2'
    if difference=='passport':second['passport']['facts']['team_A_color']['value']='розовая'
    elif difference=='artifacts':
        artifacts=tmp_path/'other-artifacts';artifacts.mkdir()
        for original in Path(second['artifacts']).iterdir():(artifacts/original.name).write_bytes(original.read_bytes())
        (artifacts/'tracks.parquet').write_bytes(b'different-tracks')
        second['artifacts']=str(artifacts)
    else:second.update(start_ms=6000,end_ms=18000)
    inputs['cases'].append(second);client=Client(response())
    with pytest.raises(ValueError,match='overlapping cases'):
        m.run(inputs,tmp_path/'out',apply=True,client=client,prepare=prepare)
    assert client.calls==0


def test_crash_after_plan_and_before_response_does_not_retry(monkeypatch,tmp_path):
    m=runner(monkeypatch);inputs=manifest(tmp_path);client=Client(response());output=tmp_path/'out'
    def crash(*a,**kw):client.calls+=1;raise RuntimeError('crash-after-send')
    monkeypatch.setattr(client,'infer',crash)
    with pytest.raises(RuntimeError):m.run(inputs,output,apply=True,client=client,prepare=prepare)
    resumed=m.run(inputs,output,apply=True,client=client,prepare=prepare)
    assert client.calls==1 and resumed['new_requests_this_run']==0
    assert resumed['cases'][0]['windows'][0]['status']=='unavailable'


def test_crash_after_receipt_then_local_processing_is_free(monkeypatch,tmp_path):
    m=runner(monkeypatch);inputs=manifest(tmp_path);client=Client(response());output=tmp_path/'out'
    original=m.project_context
    monkeypatch.setattr(m,'project_context',lambda *a,**kw:(_ for _ in ()).throw(RuntimeError('projection-crash')))
    with pytest.raises(RuntimeError):m.run(inputs,output,apply=True,client=client,prepare=prepare)
    monkeypatch.setattr(m,'project_context',original)
    resumed=m.run(inputs,output,cache_only=True,client=client,prepare=prepare)
    assert client.calls==1 and resumed['new_requests_this_run']==0 and resumed['cases'][0]['windows'][0]['status']=='valid'


def test_all_gt_instants_counted_even_if_response_invalid_and_report_safe(monkeypatch,tmp_path):
    m=runner(monkeypatch);inputs=manifest(tmp_path);client=Client({'bad':'<script>alert(1)</script>','states':None})
    report=m.run(inputs,tmp_path/'out',apply=True,client=client,prepare=prepare)
    metrics=report['cases'][0]['evaluation']
    assert metrics['labelled']==3 and metrics['unknown']==3 and metrics['correct']==0
    html=(tmp_path/'out/report.html').read_text()
    assert '<script>alert(1)</script>' not in html and '&lt;script&gt;' in html


def test_no_ground_truth_in_prompt_and_memory_crosses_multiple_windows(monkeypatch,tmp_path):
    m=runner(monkeypatch);inputs=manifest(tmp_path,windows=3);seen=[]
    class Capturing(Client):
        def infer(self,window,prompt,**kwargs):
            seen.append(json.loads(prompt));return super().infer(window,prompt,**kwargs)
    client=Capturing(response());report=m.run(inputs,tmp_path/'out',apply=True,client=client,prepare=prepare)
    assert client.calls==3 and len(seen[2]['match_memory']['recent_events'])==2
    assert 'DO_NOT_SEND_GROUND_TRUTH' not in json.dumps(seen)
    assert len(report['cases'][0]['chronology']['events'])==3


def test_dry_run_reserves_no_calls_and_does_not_freeze_empty_history_plans(monkeypatch,tmp_path):
    m=runner(monkeypatch);inputs=manifest(tmp_path,windows=2);client=Client(response());out=tmp_path/'out'
    dry=m.run(inputs,out,client=client,prepare=prepare)
    live=m.run(inputs,out,apply=True,client=client,prepare=prepare)
    assert dry['budget']['requests']==0 and live['budget']['requests']==2 and client.calls==2
    second=live['cases'][0]['windows'][1]
    assert second['planned_memory_event_count']==1
