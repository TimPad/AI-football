"""Opt-in joint VLM pilot; default dry run, --apply pays, --cache-only forbids I/O.

Inputs are a local JSON manifest with cases (id, video, artifacts, start_ms, end_ms,
optional labels and split). Real media, requests and reports stay in ignored output/.
This experiment does not import results, publish or update organizer data.
"""
import argparse
from dataclasses import replace
from hashlib import sha256
from html import escape
import json
from pathlib import Path
import time
from zipfile import ZipFile

import polars as pl

from aifootball.analytics.exchange import canonical
from aifootball.processor.budget import Budget
from aifootball.processor.job import file_hash, video_info
from aifootball.processor.media import make_window, select_player_frames
from aifootball.processor.qwen import QwenClient,QwenConfig
from aifootball.processor.workspace import Workspace
from aifootball.understanding.pilot import (
    VERSION, PilotStopped, joint_window, joint_prompt, paid_once, short_memory, validate_joint,project_joint,
)


def write_json(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    Workspace._atomic(path,canonical(value))


def prepare_context(window,tracks,info,pitch,state):
    hints=[]
    tracks=tracks.filter((pl.col('ts')>=window.start_ms/1000)&(pl.col('ts')<window.end_ms/1000))
    for offset in (1000,4000,7000,10000):
        target=(window.start_ms+offset)/1000
        if target>=window.end_ms/1000:continue
        nearby=tracks.with_columns((pl.col('ts')-target).abs().alias('_d')).sort('_d')
        if nearby.is_empty():continue
        fid=nearby['frame_id'][0]
        for row in nearby.filter(pl.col('frame_id')==fid).sort('conf',descending=True).head(12).iter_rows(named=True):
            box=[round(max(0,min(1,row[k]/info[dim])),3) for k,dim in
                 [('x1','width'),('y1','height'),('x2','width'),('y2','height')]]
            hints.append([round(row['ts']*1000)-window.start_ms,row['track_id'],row.get('team'),row.get('role'),*box])
    measured=[]
    part=state.filter((pl.col('ts')>=window.start_ms/1000)&(pl.col('ts')<window.end_ms/1000)&pl.col('speed').is_finite())
    for side in ('A','B'):
        group=part.filter((pl.col('team')==side)&(pl.col('role')=='player'))
        if not group.is_empty():
            measured.append({'side_hint':side,'tracked_fragments':group['track_id'].n_unique(),
                             'median_speed_m_s':round(group['speed'].median(),2),
                             'p95_speed_m_s':round(group['speed'].quantile(.95),2)})
    return {'scope':'continuous_excerpt','pitch_dimensions_m':{k:pitch[k] for k in ('length_m','width_m') if k in pitch},
            'cv_status':'unverified hints, not official facts','cv_hint_columns':['window_ms','track_id','team','role','x1','y1','x2','y2'],
            'cv_hints':hints,'measured_window':measured,'ball_tracking':'not supplied',
            'official_score':None,'regulation':None,'confirmed_side_mapping':None}


def detail_crops(video,tracks,window,out,known_numbers):
    part=tracks.filter((pl.col('ts')>=window.start_ms/1000)&(pl.col('ts')<window.end_ms/1000))
    if part.is_empty():return (),{}
    fids=[]
    for fraction in (.33,.67):
        target=(window.start_ms+(window.end_ms-window.start_ms)*fraction)/1000
        near=part.with_columns((pl.col('ts')-target).abs().alias('_d')).sort('_d')
        fids.append(near['frame_id'][0])
    chosen=part.filter(pl.col('frame_id').is_in(fids)&(pl.col('role')=='player')&pl.col('in_pitch')&
                       ~pl.col('track_id').is_in(sorted(known_numbers)))
    if chosen.is_empty():return (),{}
    frames=select_player_frames(video,chosen,out,max_per_track=1)
    quality=json.loads((out/'selection-quality.json').read_text())['frames']
    by_id={f.id:(tid,f) for tid,items in frames.items() for f in items}
    best=[by_id[q['id']] for q in sorted(quality,key=lambda q:(-q['score'],q['id']))[:2]]
    return tuple(f for _,f in best),{f.id:tid for tid,f in best}


def sample_states(doc,start_ms,labels,begin,end):
    """Only labelled instants; sparse touches are not continuous clock ground truth."""
    if not labels:return {'labelled':0,'correct':0,'wrong':0,'unknown':0,'rows':[]}
    rows=[]
    for truth in pl.read_parquet(labels).filter((pl.col('ts')>=begin/1000)&(pl.col('ts')<end/1000)).iter_rows(named=True):
        ms=round(truth['ts']*1000);expected='stoppage' if truth['event']=='dead' else 'playing'
        states={s['kind'] for s in doc['states'] if start_ms+s['start_ms']<=ms<start_ms+s['end_ms'] and s['kind']!='unknown'}
        actual=next(iter(states)) if len(states)==1 else 'unknown'
        rows.append({'video_ms':ms,'expected':expected,'actual':actual})
    return {'labelled':len(rows),'correct':sum(r['actual']==r['expected'] for r in rows),
            'wrong':sum(r['actual'] not in (r['expected'],'unknown') for r in rows),
            'unknown':sum(r['actual']=='unknown' for r in rows),'rows':rows}


def archived_baseline(settings,cases):
    if not settings:return None
    case=next(c for c in cases if c['id']==settings['case_id'])
    with ZipFile(settings['result']) as z:understanding=json.loads(z.read('understanding.json'))
    if understanding['source']['sha256']!=file_hash(Path(case['video'])):raise ValueError('baseline source mismatch')
    raw_kinds={};values=[]
    for path in Path(settings['cache']).glob('*.json'):
        envelope=json.loads(path.read_text());value=envelope['value']
        if sha256(canonical(value)).hexdigest()!=envelope['sha256']:raise ValueError('baseline cache hash')
        values.append(value)
        if 'kind' in value and value.get('request_id'):raw_kinds[value['request_id']]=value['kind']
    unique={}
    for value in values:
        doc=value.get('document',{});request=value.get('request_id')
        if (set(value)=={'document','usage','request_id','model'} and raw_kinds.get(request)=='match' and
            case['start_ms']<=doc.get('start_ms',-1)<doc.get('end_ms',-1)<=case['end_ms']):
            unique.setdefault(request,value)
    if not unique:raise ValueError('no comparable archived scene responses')
    rows=list(unique.values());states=[s for r in rows for s in r['document']['document']['states']]
    evaluation=sample_states({'states':states},0,case.get('labels'),case['start_ms'],case['end_ms'])
    return {'case_id':case['id'],'kind':'historical, successful scene calls only; not a fresh randomized A/B',
            'model':understanding['provider'],'requests':len(rows),
            'input_tokens':sum((r['usage'] or {}).get('prompt_tokens',0) for r in rows),
            'output_tokens':sum((r['usage'] or {}).get('completion_tokens',0) for r in rows),
            'states_at_labelled_instants':evaluation,
            'events':[e for r in rows for e in r['document']['document']['events']],
            'notes':'Repeated cache files deduplicated by provider request_id. Failed/identity/refinement calls excluded.'}


def render(report,target):
    blocks=[]
    windows=[w for c in report['cases'] for w in c['windows']]
    counts=(len(windows),sum(w['status']=='valid' for w in windows),sum(w.get('projection_status')=='valid' for w in windows))
    for case in report['cases']:
        lines=[]
        for row in case['windows']:
            doc=row.get('document',{});clip=escape(str(Path(row['clip']).relative_to(target.parent)),quote=True)
            posters=sorted(Path(row['clip']).parent.glob('*.jpg'))
            poster=f" poster='{escape(str(posters[0].relative_to(target.parent)),quote=True)}'" if posters else ''
            safe=row.get('projected_document') if row.get('projection_status')=='valid' else doc if row['status']=='valid' else None
            safe_comments=safe['commentary'] if safe is not None else []
            comments=''.join(f"<p><b>{(row['start_ms']+c['anchor_ms'])/1000:.1f} с</b> — {escape(c['text'])}</p>" for c in safe_comments)
            if row.get('local_repairs'):comments='<p>Применены локальные правки контракта; исходный ответ сохранён ниже.</p>'+comments
            lines.append(f"<article><h3>{row['start_ms']/1000:.1f}–{row['end_ms']/1000:.1f} с · {escape(row['status'])}</h3>"
                         f"<video controls preload='none'{poster} src='{clip}'></video>{comments}"
                         f"<details><summary>Общий ответ и проверка</summary><pre>{escape(json.dumps(row,ensure_ascii=False,indent=2))}</pre></details></article>")
        blocks.append(f"<section><h2>{escape(case['id'])} · {escape(case['split'])}</h2>{''.join(lines)}</section>")
    header=escape(json.dumps({k:v for k,v in report.items() if k!='cases'},ensure_ascii=False,indent=2))
    html=f"""<!doctype html><html lang='ru'><meta charset='utf-8'><title>Пилот единого VLM-разбора</title>
<style>body{{font:16px system-ui;max-width:1150px;margin:32px auto;padding:0 20px;background:#f4f6f8;color:#182333}}h1{{font-size:28px}}article{{background:white;padding:20px;margin:16px 0;border-radius:12px}}video{{max-width:100%;width:760px}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px}}summary{{cursor:pointer}}b{{font-variant-numeric:tabular-nums}}</style>
<h1>Эксперимент: один ответ VLM для нескольких задач</h1><p>Частный локальный отчёт. Автоматические наблюдения не подтверждены. Таймкоды записи, не чистое время матча. Публикация и интеграция в кабинет не выполнялись.</p>
<p><b>Окон: {counts[0]}</b> · Строго прошли контракт: {counts[1]} · Доступны после локальной проверки/правок: {counts[2]}</p>
<details><summary>Расход, ограничения и исходный режим</summary><pre>{header}</pre></details>{''.join(blocks)}</html>"""
    target.write_text(html)


def run(manifest,output,*,apply=False,cache_only=False,case_ids=(),continue_unavailable=False):
    config=QwenConfig.from_env();client=QwenClient(config)
    workspace=Workspace(output/'work',{'purpose':'joint-vlm-pilot-v1'})
    budget=Budget(workspace,max_requests=8,max_input_tokens=200000,max_output_tokens=32768)
    before=budget.snapshot();cases=[];started=time.monotonic()
    selected=[c for c in manifest['cases'] if not case_ids or c['id'] in case_ids]
    if not selected or len({c['id'] for c in selected})!=len(selected):raise ValueError('invalid case selection')
    count=sum((c['end_ms']-c['start_ms']+11999)//12000 for c in selected)
    if count>8 or any(not 0<=c['start_ms']<c['end_ms'] for c in selected):raise ValueError('pilot limited to 8 windows')
    for case in selected:
        video=Path(case['video']);artifacts=Path(case['artifacts']);info=video_info(video)
        if case['end_ms']>round(info['duration_s']*1000):raise ValueError('case outside video')
        source_hash=file_hash(video);meta=json.loads((artifacts/'meta.json').read_text())
        if meta.get('source_sha256') and meta['source_sha256']!=source_hash:raise ValueError('CV source mismatch')
        tracks=pl.read_parquet(artifacts/'tracks.parquet');state=pl.read_parquet(artifacts/'state.parquet')
        pitch=json.loads((artifacts/'metrics.json').read_text()).get('pitch',{})
        rows=[];memory=[];known_numbers=set()
        for begin in range(case['start_ms'],case['end_ms'],12000):
            end=min(begin+12000,case['end_ms']);folder=output/'work'/'media'/source_hash/f'{begin}-{end}'
            tids=tuple(sorted(tracks.filter((pl.col('ts')>=begin/1000)&(pl.col('ts')<end/1000))['track_id'].unique().to_list()))
            window=make_window(video,start_ms=begin,end_ms=end,out=folder,mode='native',fps=1,track_ids=tids)
            crops,crop_tracks=detail_crops(video,tracks,window,folder/'crops',known_numbers)
            window=joint_window(window,crops=crops)
            prompt=joint_prompt(window,context=prepare_context(window,tracks,info,pitch,state),crop_tracks=crop_tracks,memory=memory)
            row={'start_ms':window.start_ms,'end_ms':window.end_ms,'clip':str(window.media.path),'crop_count':len(crops),
                 'crop_tracks':crop_tracks,'crops':{f.id:str(f.path) for f in crops},'prompt_sha256':sha256(prompt.encode()).hexdigest()}
            write_json(folder/'prompt.json',{'prompt':json.loads(prompt),'crop_tracks':crop_tracks})
            if not apply and not cache_only:
                row['status']='dry_run';row['request_bytes']=len(client._body(window,prompt,4096))
            else:
                tick=time.monotonic()
                try:
                    result=paid_once(client,window,prompt,workspace,budget,allow_network=apply and not cache_only)
                    row.update(result);row['wall_s']=round(time.monotonic()-tick,3)
                    try:validate_joint(result['document'],window,crop_tracks=crop_tracks)
                    except (ValueError,KeyError,TypeError):row['status']='invalid_response'
                    else:
                        row['status']='valid';memory=short_memory(result['document'],window)
                        known_numbers.update(o['track_id'] for o in result['document']['observations'] if o['number'] is not None)
                    try:projected,repairs=project_joint(result['document'],window,crop_tracks=crop_tracks)
                    except (ValueError,KeyError,TypeError):row['projection_status']='unavailable'
                    else:
                        row.update(projected_document=projected,local_repairs=repairs,projection_status='valid')
                        row['states_at_labelled_instants']=sample_states(projected,window.start_ms,case.get('labels'),window.start_ms,window.end_ms)
                except PilotStopped as exc:row.update(status='stopped',reason=str(exc))
            rows.append(row);write_json(folder/'evaluation.json',row)
            print(json.dumps({'case':case['id'],'start_ms':window.start_ms,'status':row['status'],
                              'cache_hit':row.get('cache_hit'),'usage':row.get('usage')},ensure_ascii=False),flush=True)
            if row['status']=='stopped' and not continue_unavailable:break
        cases.append({'id':case['id'],'split':case.get('split','exploratory'),'source_sha256':source_hash,
                      'tracks_sha256':file_hash(artifacts/'tracks.parquet'),'has_audio':bool(rows and window.media.has_audio),'windows':rows})
        after=budget.snapshot()
        partial={'version':VERSION,'mode':'dry_run' if not apply and not cache_only else 'cache_only' if cache_only else 'apply',
                 'provider':{'model':config.model,'endpoint':config.base_url,'reasoning_effort':'none'},'cases':cases,
                 'budget':after,'new_requests_this_run':after['requests']-before['requests'],
                 'wall_s':round(time.monotonic()-started,3),'sports_accuracy_validated':False,
                 'baseline':archived_baseline(manifest.get('baseline'),manifest['cases'])}
        write_json(output/'report.json',partial);render(partial,output/'report.html')
        if any(row['status']=='stopped' for row in rows) and not continue_unavailable:break
    return partial


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    group=parser.add_mutually_exclusive_group();group.add_argument('--apply',action='store_true');group.add_argument('--cache-only',action='store_true')
    parser.add_argument('--case',action='append',default=[])
    parser.add_argument('--continue-unavailable',action='store_true',help='Skip unavailable windows without retrying them; process other windows within the same budget')
    args=parser.parse_args();args.output=args.output.resolve();args.output.mkdir(parents=True,exist_ok=True)
    try:report=run(json.loads(args.manifest.read_text()),args.output,apply=args.apply,cache_only=args.cache_only,
                   case_ids=args.case,continue_unavailable=args.continue_unavailable)
    except (ValueError,OSError):parser.exit(2,'Pilot stopped: verify local configuration, inputs or workspace; no automatic retry.\n')
    print(json.dumps({'report':str(args.output/'report.html'),'budget':report['budget'],
                      'new_requests_this_run':report['new_requests_this_run']},ensure_ascii=False),flush=True)
    if any(w['status'] not in ('valid','dry_run') for c in report['cases'] for w in c['windows']):raise SystemExit(2)


if __name__=='__main__':main()
