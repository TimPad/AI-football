"""Optional, resumable multimodal stage. Nothing here changes official match facts."""
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
import random
import time
import polars as pl
from aifootball import schemas
from aifootball.analytics.exchange import canonical
from aifootball.processor.job import source_for_job
from aifootball.processor.media import make_window,select_player_frames
from aifootball.processor.qwen import QwenError
from aifootball.understanding.types import Window
from aifootball.understanding.schema import validate_window_response,validate_understanding,SCOPES
from aifootball.understanding.windows import plan_windows
from aifootball.understanding.prompts import match_prompt,identity_prompt,PROMPT_VERSION
from aifootball.understanding.identity import resolve_identity
from aifootball.understanding.reconcile import reconcile_windows


def _evidence(frame):
    return {'id':frame.id,'frame_id':frame.frame_id,'video_ms':frame.video_ms,'path':f'evidence/{frame.id}.jpg',
            'sha256':frame.sha256,'crop':list(frame.crop) if frame.crop else None,'kind':'player_crop' if frame.crop else 'overview'}


def _context(window,tracks,source,scope):
    boxes={};teams={}
    for frame in window.frames:
        rows=tracks.filter(pl.col('frame_id')==frame.frame_id)
        entries=[]
        for row in rows.iter_rows(named=True):
            if row['track_id'] not in window.track_ids:continue
            normalized=[max(0,min(1,float(row[key])/source[dimension])) for key,dimension in
                        [('x1','width'),('y1','height'),('x2','width'),('y2','height')]]
            entries.append([row['track_id'],*[round(value,4) for value in normalized]])
            teams[row['track_id']]=row.get('team')
        boxes[frame.id]=entries
    return {'analysis_scope':scope,'track_boxes':boxes,'track_teams':teams}


def identity_only(document):
    """A player crop does not support scene claims: keep only observations of a number answer."""
    return {**document,'events':[],'states':[],'phases':[],'summary':[]} if isinstance(document,dict) else document


def run_understanding(job,video:Path,artifacts:Path,workspace,*,client,budget,mode='native',analysis_scope='unknown',sleep=time.sleep):
    if mode not in ('native','frames') or analysis_scope not in SCOPES:raise ValueError('Invalid understanding settings')
    source=source_for_job(job,video);duration=round(source['duration_s']*1000)
    tracks=schemas.read(Path(artifacts)/'tracks.parquet','tracks')
    detections_path=Path(artifacts)/'detections.parquet'
    ball=[]
    if detections_path.exists():ball=schemas.read(detections_path,'detections').filter(pl.col('cls')=='ball').select('ts','conf').to_dicts()
    config=client.config
    fingerprint={'source':source,'context':job.contract['context_hash'],'model':config.model,'endpoint':config.base_url,
                 'prompt':PROMPT_VERSION,'mode':mode,'analysis_scope':analysis_scope,
                 'tracks_sha256':sha256((Path(artifacts)/'tracks.parquet').read_bytes()).hexdigest()}
    stage_key=sha256(canonical(fingerprint)).hexdigest()
    stage=workspace.root/'media'/stage_key;stage.mkdir(parents=True,exist_ok=True)
    scene_specs=plan_windows(duration_ms=duration,tracks=tracks,ball_candidates=ball,mode=mode)
    player_frames=select_player_frames(video,tracks,stage/'players')
    identity_jobs=[]
    for tid,frames in sorted(player_frames.items()):
        groups=[]
        for frame in frames:
            if not groups or frame.video_ms-groups[-1][0].video_ms>=20000:groups.append([])
            groups[-1].append(frame)
        for group in groups:
            begin=group[0].video_ms;end=min(duration,group[-1].video_ms+1)
            identity=sha256(canonical({'track':tid,'frames':[frame.sha256 for frame in group],'times':[frame.video_ms for frame in group]})).hexdigest()[:24]
            identity_jobs.append(Window(identity,begin,end,tuple(group),None,(tid,),'frames'))
    tasks=[];pending=list(identity_jobs)
    for index,spec in enumerate(scene_specs):
        tasks.append(('match',spec))
        if index%2==1 and pending:tasks.append(('identity',pending.pop(0)))
    tasks.extend(('identity',window) for window in pending)
    successful=[];identity_results=[];evidence={};image_files={};issues=[];response_models=set()
    completed={'match':0,'identity':0};exhausted=False
    for kind,spec in tasks:
        try:
            window=spec if kind=='identity' else make_window(video,start_ms=spec['start_ms'],end_ms=spec['end_ms'],
                out=stage/spec['id'],mode=mode,fps=spec['fps'],track_ids=spec['track_ids'])
        except ValueError:
            issues.append('Не удалось подготовить медиа одного из окон');continue
        new_ids={frame.id for frame in window.frames}-evidence.keys()
        if len(evidence)+len(new_ids)>500:
            issues.append('Достигнут предел доказательств; дальнейшие окна не отправлены');break
        measured=_context(window,tracks,source,analysis_scope)
        prompt=identity_prompt(window,measured=measured) if kind=='identity' else match_prompt(window,measured=measured)
        key='understanding:'+sha256(canonical({'stage':stage_key,'kind':kind,'window':window.id,
            'prompt':prompt,'images':[frame.sha256 for frame in window.frames],
            'media':window.media.sha256 if window.media else None})).hexdigest()
        cached=workspace.get_json(key);stop=False
        def validated_response(document):
            return validate_window_response(identity_only(document) if kind=='identity' else document,window)
        if cached is None:
            for rid in budget.reservations_for(key):
                receipt=workspace.get_json('raw:'+rid)
                if receipt is None:continue
                budget.settle_call(rid,receipt['usage'])
                try:validated=validated_response(receipt['document'])
                except ValueError:continue
                cached={'document':validated,'usage':receipt['usage'],'request_id':receipt['request_id'],'model':receipt['model']}
                workspace.put_json(key,cached);break
        # После исчерпания бюджета новых платных попыток нет, но уже оплаченные окна дальше по порядку собираются.
        if cached is None and exhausted:continue
        if cached is None:
            repaired=False;validated=None
            estimate=len(prompt.encode())//2+1600*len(window.frames)+(round((window.end_ms-window.start_ms)*1.2) if window.media else 0)
            for attempt in range(3):
                try:reservation=budget.reserve_call(key,estimate,4096)
                except ValueError:
                    issues.append('Бюджет обработки исчерпан');exhausted=True;break
                try:
                    response=client.infer(window,prompt,max_output_tokens=4096)
                except QwenError as exc:
                    budget.settle_call(reservation,None)
                    if exc.code=='response_json' and not repaired:
                        repaired=True;prompt+='\nИсправь формат: верни один полный JSON-объект.';continue
                    if exc.retryable and attempt<2:
                        sleep(min(60,exc.retry_after if exc.retry_after is not None else 2**attempt+random.uniform(0,.25)));continue
                    issues.append('Ошибка запроса анализа: '+exc.code)
                    stop=exc.code in ('http_401','http_402','http_403','request_config') or exc.retryable
                    break
                workspace.put_json('raw:'+reservation, {'window_id':window.id,'kind':kind,
                    'document':response.document,'usage':response.usage,'request_id':response.request_id,
                    'model':response.response_model,'prompt_sha256':sha256(prompt.encode()).hexdigest()})
                budget.settle_call(reservation,response.usage)
                try:
                    validated=validated_response(response.document)
                except ValueError:
                    if not repaired and attempt<2:
                        repaired=True;prompt+='\nИсправь схему и ссылки; только переданные IDs, локальное время, неизвестное не выдумывай.';continue
                    issues.append('Ответ одного из окон не прошёл проверку');break
                cached={'document':validated,'usage':response.usage,'request_id':response.request_id,'model':response.response_model}
                workspace.put_json(key,cached);break
        if cached is not None:
            result=cached['document'];response_models.add(cached['model'])
            # Cached global timestamps and references are rechecked by reconciliation/schema.
            referenced={eid for field in ('observations','states','phases','events')
                        for item in result['document'][field] for eid in item['evidence_ids']}
            window_evidence=[]
            for frame in window.frames:
                if frame.id not in referenced:continue
                item=_evidence(frame);evidence[frame.id]=item;window_evidence.append(item)
                image_files[item['path']]=frame.path.read_bytes()
            result={**result,'window_id':kind+'-'+window.id,'evidence':window_evidence}
            (identity_results if kind=='identity' else successful).append(result)
            completed[kind]+=1
        if stop:break
    merged=reconcile_windows(successful,duration_ms=duration,source_sha256=source['sha256'],prompt_version=PROMPT_VERSION)
    observations=merged['observations']+[item for result in identity_results for item in result['document']['observations']]
    unique={canonical(item):item for item in observations};observations=[unique[key] for key in sorted(unique)]
    for state in merged['states']:
        if state['kind']=='unknown' and issues:state['limitations']=sorted(set(state['limitations']+issues))[:100]
    context={key:job.contract[key] if key in job.contract else job.contract['context']['camera']['id'] for key in
             ('job_id','match_id','context_hash','camera_profile_id')}
    task_count=len(tasks);done=sum(completed.values())
    processing={'status':'unavailable' if not done else 'complete' if done==task_count and not issues else 'partial',
        'tasks_planned':task_count,'tasks_completed':done,
        'scene_tasks_planned':len(scene_specs),'scene_tasks_completed':completed['match'],
        'identity_tasks_planned':len(identity_jobs),'identity_tasks_completed':completed['identity'],
        'issues':sorted(set(issues))[:100]}
    cv_teams={}
    for (tid,),group in tracks.partition_by('track_id',as_dict=True).items():
        teams={team for team in group['team'].to_list() if team is not None}
        cv_teams[tid]=next(iter(teams)) if len(teams)==1 else None
    doc={'schema_version':'1','processing':processing,'source':{'sha256':source['sha256'],'duration_ms':duration,'width':source['width'],
        'height':source['height'],'analysis_scope':analysis_scope},'context':context,
        'provider':{'name':'qwen','model':config.model,'response_model':','.join(sorted(response_models)) or None,
                    'endpoint':config.base_url,'region':'ap-southeast-1' if 'ap-southeast-1.' in config.base_url else None,
                    'prompt_version':PROMPT_VERSION,'settings':{'mode':mode,'reasoning_effort':'none'}},
        'budget':budget.snapshot(),'coverage':merged['coverage'],'evidence':[evidence[key] for key in sorted(evidence)],
        'observations':observations,'identity_suggestions':resolve_identity(observations,job.contract['context']['rosters'],side_map=None,track_teams=cv_teams),
        'states':merged['states'],'phases':merged['phases'],'events':merged['events'],'summary':merged['summary']}
    manifest={'source_video':source,**context}
    track_index={'tracks':[{'track_id':tid} for tid in tracks['track_id'].unique().to_list()]}
    return validate_understanding(doc,manifest=manifest,tracks=track_index,files=image_files,
                                  rosters=job.contract['context']['rosters']),image_files
