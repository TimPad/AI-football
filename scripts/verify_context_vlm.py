"""Opt-in match-context VLM pilot: dry-run by default; fixed six-call budget."""
import argparse
from dataclasses import asdict
from hashlib import sha256
from html import escape
import json
from pathlib import Path
import re
import time

import polars as pl

from aifootball.analytics.exchange import canonical
from aifootball.processor.budget import Budget
from aifootball.processor.job import file_hash,video_info
from aifootball.processor.media import make_window
from aifootball.processor.qwen import QwenClient,QwenConfig
from aifootball.processor.workspace import Workspace
from aifootball.understanding.types import FrameAsset,MediaAsset,Window
from aifootball.understanding.pilot import joint_window,paid_once,PilotStopped,request_key
from aifootball.understanding.match_context import MatchChronology,validate_passport
from aifootball.understanding.context_pilot import VERSION,context_prompt,project_context
from aifootball.understanding.commentary import compile_commentary
from verify_joint_vlm import prepare_context,detail_crops,sample_states,write_json


def input_identity(manifest,client):
    cases=manifest.get('cases');identities=[]
    if type(cases) is not list or not 1<=len(cases)<=6:raise ValueError('invalid cases')
    if len({c['id'] for c in cases})!=len(cases):raise ValueError('duplicate case')
    count=0
    for case in cases:
        if type(case['id']) is not str or not re.fullmatch('[a-zA-Z0-9_-]{1,60}',case['id']):raise ValueError('unsafe case ID')
        start,end=case['start_ms'],case['end_ms']
        if type(start) is not int or type(end) is not int or not 0<=start<end:raise ValueError('invalid interval')
        count+=(end-start+11999)//12000
        source=file_hash(Path(case['video']));p=validate_passport(case['passport'],source)
        if any(i['source_sha256']==source and start<i['end_ms'] and i['start_ms']<end for i in identities):
            raise ValueError('overlapping cases for the same source; use separate pilot workspaces')
        folder=Path(case['artifacts']);meta=json.loads((folder/'meta.json').read_text())
        if meta.get('source_sha256') and meta['source_sha256']!=source:raise ValueError('CV source mismatch')
        identities.append({'source_sha256':source,'start_ms':start,'end_ms':end,'passport':p,
                           'artifacts':{n:file_hash(folder/n) for n in ('tracks.parquet','state.parquet','metrics.json','meta.json')}})
    if count>6:raise ValueError('pilot limited to six windows')
    return {'purpose':VERSION,'preparation_version':'native-crops-v1','provider':{
        'model':client.config.model,'endpoint':client.config.base_url},'cases':identities}


def prepare_window(case,begin,end,output):
    video=Path(case['video']);artifacts=Path(case['artifacts']);info=video_info(video)
    if end>round(info['duration_s']*1000):raise ValueError('window outside video')
    tracks=pl.read_parquet(artifacts/'tracks.parquet');state=pl.read_parquet(artifacts/'state.parquet')
    pitch=json.loads((artifacts/'metrics.json').read_text()).get('pitch',{})
    tids=tuple(sorted(tracks.filter((pl.col('ts')>=begin/1000)&(pl.col('ts')<end/1000))['track_id'].unique().to_list()))
    folder=output/'media'/case['id']/f'{begin}-{end}'
    window=make_window(video,start_ms=begin,end_ms=end,out=folder,mode='native',fps=1,track_ids=tids)
    crops,crop_tracks=detail_crops(video,tracks,window,folder/'crops',set())
    return joint_window(window,crops=crops),prepare_context(window,tracks,info,pitch,state),crop_tracks


def pack_window(window):
    value=asdict(window)
    for item in value['frames']:item['path']=str(item['path'])
    value['media']['path']=str(value['media']['path'])
    return value


def unpack_window(value):
    frames=tuple(FrameAsset(**{**v,'path':Path(v['path']),'crop':None if v['crop'] is None else tuple(v['crop'])}) for v in value['frames'])
    media=MediaAsset(**{**value['media'],'path':Path(value['media']['path'])})
    return Window(value['id'],value['start_ms'],value['end_ms'],frames,media,tuple(value['track_ids']),value['mode'])


def baseline_case(manifest,case,source):
    if not manifest.get('baseline_report'):return None
    baseline=json.loads(Path(manifest['baseline_report']).read_text())
    old=next((c for c in baseline['cases'] if c['id']==case['id']),None)
    if old is None:return None
    if old['source_sha256']!=source:raise ValueError('baseline source mismatch')
    states=[]
    for row in old['windows']:
        if row.get('projection_status')!='valid':continue
        states.extend({**s,'start_ms':row['start_ms']+s['start_ms'],'end_ms':row['start_ms']+s['end_ms']}
                      for s in row['projected_document']['states'])
    evaluation=sample_states({'states':states},0,case.get('labels'),case['start_ms'],case['end_ms'])
    return {'evaluation':evaluation,'windows':old['windows'],'kind':'historical v1, same intervals; no new baseline calls'}


def render(report,target):
    sections=[]
    for case in report['cases']:
        rows=[]
        for index,row in enumerate(case['windows']):
            clip=escape(str(Path(row['clip']).relative_to(target.parent)),quote=True)
            posters=sorted(Path(row['clip']).parent.glob('*.jpg'))
            poster=f" poster='{escape(str(posters[0].relative_to(target.parent)),quote=True)}'" if posters else ''
            body=escape(json.dumps(row,ensure_ascii=False,indent=2))
            rows.append(f"<article id='{case['id']}-{index}'><h3>{row['start_ms']/1000:.1f}–{row['end_ms']/1000:.1f} с · {escape(row['status'])}</h3>"
                        f"<video id='v-{case['id']}-{index}' controls preload='none'{poster} src='{clip}'></video>"
                        f"<details><summary>Наблюдения, основания и исходный ответ</summary><pre>{body}</pre></details></article>")
        feed=[]
        for entry in case['feed']['entries']:
            index=next(i for i,w in enumerate(case['windows']) if w['start_ms']<=entry['video_ms']<w['end_ms'])
            local=(entry['video_ms']-case['windows'][index]['start_ms'])/1000
            sec=entry['video_ms']/1000;stamp=f'{int(sec//60):02}:{sec%60:04.1f}'
            feed.append(f"<li><a href='#{case['id']}-{index}' data-video='v-{case['id']}-{index}' data-time='{local:.3f}'>{stamp}</a> — {escape(entry['text'])}</li>")
        if not feed:feed=['<li>Нет событий с достаточным набором наблюдаемых признаков.</li>']
        comparison={'v2':case['evaluation'],'v1':case.get('baseline',{}).get('evaluation') if case.get('baseline') else None}
        sections.append(f"<section><h2>{escape(case['id'])}</h2><p>Реплики автоматически сформированы из непроверенных наблюдений.</p>"
                        f"<ol>{''.join(feed)}</ol><details><summary>Паспорт, память и сравнение</summary><pre>"
                        f"{escape(json.dumps({'passport':case['passport'],'comparison':comparison,'rejected_events':case['feed']['rejected_events']},ensure_ascii=False,indent=2))}</pre></details>{''.join(rows)}</section>")
    summary=escape(json.dumps({k:v for k,v in report.items() if k!='cases'},ensure_ascii=False,indent=2))
    target.write_text("""<!doctype html><html lang='ru'><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1'><title>VLM: контекст и текстовая лента</title>
<style>body{font:16px system-ui;max-width:1160px;margin:32px auto;padding:0 20px;background:#f4f6f8;color:#182333}article{background:white;padding:20px;margin:18px 0;border-radius:12px}video{max-width:100%;width:760px}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px}li{margin:12px 0}a{color:#075cd3}summary{cursor:pointer}</style>
<h1>VLM: контекст матча и текстовая лента</h1><p>Частный эксперимент. Таймкоды записи; игровые часы не рассчитаны. Наблюдения модели не подтверждены и не опубликованы.</p>
<details><summary>Режим, расход и ограничения</summary><pre>"""+summary+'</pre></details>'+''.join(sections)+"""
<script>document.addEventListener('click',e=>{const a=e.target.closest('a[data-video]');if(!a)return;e.preventDefault();const v=document.getElementById(a.dataset.video);v.scrollIntoView({block:'center',behavior:'smooth'});const seek=()=>{v.currentTime=Number(a.dataset.time);v.play().catch(()=>{});};if(v.readyState)seek();else{v.addEventListener('loadedmetadata',seek,{once:true});v.load();}});</script></html>""")


def run(manifest,output,*,apply=False,cache_only=False,client=None,prepare=None):
    if apply and cache_only:raise ValueError('conflicting modes')
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=True)
    client=client or QwenClient(QwenConfig.from_env());prepare=prepare or prepare_window
    identity=input_identity(manifest,client)
    baselines=[baseline_case(manifest,c,i['source_sha256']) for c,i in zip(manifest['cases'],identity['cases'])]
    workspace=Workspace(output/'work',identity)
    budget=Budget(workspace,max_requests=6,max_input_tokens=150000,max_output_tokens=24576)
    before=budget.snapshot();cases=[];started=time.monotonic();report={}
    with workspace.exclusive():
        for case,inputs,baseline in zip(manifest['cases'],identity['cases'],baselines):
            p=inputs['passport'];history=MatchChronology(inputs['source_sha256'],p);rows=[]
            result={'id':case['id'],'source_sha256':inputs['source_sha256'],'passport':p,'windows':rows,'baseline':baseline}
            cases.append(result)
            for begin in range(case['start_ms'],case['end_ms'],12000):
                end=min(begin+12000,case['end_ms'])
                plan_key='plan:'+sha256(canonical([inputs['source_sha256'],begin,end,VERSION])).hexdigest()
                plan=workspace.get_json(plan_key)
                if plan is None:
                    window,context,crop_tracks=prepare(case,begin,end,output)
                    memory=history.snapshot(window.start_ms,window.track_ids)
                    prompt=context_prompt(window,context=context,passport=p,memory=memory,crop_tracks=crop_tracks)
                    plan={'window':pack_window(window),'crop_tracks':crop_tracks,'prompt':prompt,
                          'request_key':request_key(client,window,prompt,4096),
                          'planned_memory_event_count':len(memory['recent_events'])}
                    if apply:workspace.put_json(plan_key,plan)
                else:window=unpack_window(plan['window'])
                prompt=plan['prompt'];crop_tracks=plan['crop_tracks']
                if request_key(client,window,prompt,4096)!=plan['request_key']:raise ValueError('frozen request mismatch')
                row={'start_ms':window.start_ms,'end_ms':window.end_ms,'clip':str(window.media.path),
                     'planned_memory_event_count':plan['planned_memory_event_count'],
                     'request_key':plan['request_key'],'prompt_sha256':sha256(prompt.encode()).hexdigest()}
                if not apply and not cache_only:row['status']='dry_run'
                else:
                    try:
                        received=paid_once(client,window,prompt,workspace,budget,allow_network=apply)
                        row.update(received)
                        try:projected,repairs=project_context(received['document'],window,crop_tracks=crop_tracks)
                        except (ValueError,KeyError,TypeError):
                            row['status']='invalid_response';history.gap(window.start_ms,window.end_ms,'invalid_response')
                        else:
                            row.update(status='valid',projected_document=projected,local_repairs=repairs)
                            history.add(window,projected,plan['request_key'])
                    except PilotStopped as exc:
                        row.update(status='unavailable',reason=str(exc));history.gap(window.start_ms,window.end_ms,'response_unavailable')
                rows.append(row)
                chronology=history.document();feed=compile_commentary(chronology,p)
                evaluation=sample_states({'states':chronology['states']},0,case.get('labels'),case['start_ms'],case['end_ms'])
                result.update(chronology=chronology,feed=feed,evaluation=evaluation)
                folder=output/'cases'/case['id'];write_json(folder/'chronology.json',chronology);write_json(folder/'commentary.json',feed)
                after=budget.snapshot()
                report={'version':VERSION,'mode':'apply' if apply else 'cache_only' if cache_only else 'dry_run','cases':cases,
                        'provider':identity['provider'],'budget':after,'new_requests_this_run':after['requests']-before['requests'],
                        'wall_s':round(time.monotonic()-started,3),'sports_accuracy_validated':False}
                write_json(output/'report.json',report);render(report,output/'report.html')
                print(json.dumps({'case':case['id'],'start_ms':window.start_ms,'status':row['status'],
                                  'cache_hit':row.get('cache_hit'),'usage':row.get('usage')},ensure_ascii=False),flush=True)
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    group=parser.add_mutually_exclusive_group();group.add_argument('--apply',action='store_true');group.add_argument('--cache-only',action='store_true')
    args=parser.parse_args()
    try:r=run(json.loads(args.manifest.read_text()),args.output,apply=args.apply,cache_only=args.cache_only)
    except (ValueError,OSError):parser.exit(2,'Context pilot stopped: verify inputs, frozen workspace and configuration; no automatic retry.\n')
    print(json.dumps({'budget':r['budget'],'new_requests_this_run':r['new_requests_this_run']},ensure_ascii=False),flush=True)
    if any(w['status'] not in ('valid','dry_run') for c in r['cases'] for w in c['windows']):raise SystemExit(2)


if __name__=='__main__':main()
