"""Resume expensive detections, then replay the existing tracking pipeline once."""
from datetime import datetime,timezone
from hashlib import sha256
import os
from pathlib import Path
from types import SimpleNamespace
import math
import polars as pl
from aifootball import schemas
from aifootball.analytics.exchange import canonical
from aifootball.processor.job import read_job,source_for_job,file_hash
from aifootball.processor.workspace import Workspace
from aifootball.venue import load_venue

CHUNK_MS=60000


def _write_detections(data,path):
    # Preserve the existing Arrow schema tag in addition to atomic replacement.
    schemas.write(data,path,'detections')
    with path.open('rb') as stream:os.fsync(stream.fileno())
    descriptor=os.open(path.parent,os.O_RDONLY)
    try:os.fsync(descriptor)
    finally:os.close(descriptor)


def run_cv(job_path:Path,video:Path,workspace:Workspace,*,models:Path,ball_model:str|None=None)->Path:
    from aifootball.perception.detect import detect_batches,pick_device
    from aifootball.perception.frames import video_fps
    from aifootball.processor.job import EVENTS_MIN_FPS,ball_model_path
    from aifootball import cli
    job=read_job(job_path);source=source_for_job(job,video)
    with workspace.exclusive():
        root=workspace.root/'artifacts';venue_root=workspace.root/'venue';chunks=workspace.root/'detections'
        for directory in (root,venue_root,chunks):directory.mkdir(exist_ok=True)
        for name,raw in job.files.items():Workspace._atomic(venue_root/name,raw)
        venue=load_venue(venue_root);weights=Path(models)/venue.model
        ball_weights=ball_model_path(models,ball_model) if ball_model else None
        if ball_weights and venue.target_fps<EVENTS_MIN_FPS:
            raise ValueError(f'Для передач нужна обработка не реже {EVENTS_MIN_FPS} кадров/с: создайте новое задание')
        fingerprint={'source':source,'context_hash':job.contract['context_hash'],'weights_sha256':file_hash(weights),
                     'venue_files':{name:sha256(raw).hexdigest() for name,raw in job.files.items()},
                     'pipeline':'cv-chunks-v1','chunk_ms':CHUNK_MS}
        if ball_weights:fingerprint['ball_model']={'name':ball_model,'sha256':file_hash(ball_weights)}
        previous=workspace.get_json('cv:fingerprint')
        if previous is not None and previous!=fingerprint:raise ValueError('CV fingerprint mismatch')
        workspace.put_json('cv:fingerprint',fingerprint)
        duration_ms=round(source['duration_s']*1000);count=math.ceil(duration_ms/CHUNK_MS)
        saved=[]
        for index in range(count):
            item=workspace.get_json(f'cv:chunk:{index}')
            if item is None:break
            path=chunks/f'{index:06d}.parquet'
            if not path.exists() or file_hash(path)!=item['sha256'] or item.get('end_ms')!=min((index+1)*CHUNK_MS,duration_ms):
                raise ValueError('corrupt detection chunk')
            saved.append(item)
        start=len(saved);current=start;parts=[];sampled=[]

        def persist(index):
            data=pl.concat(parts) if parts else schemas.empty('detections')
            if not sampled:raise ValueError('No sampled frames in detection chunk')
            path=chunks/f'{index:06d}.parquet'
            _write_detections(data,path)
            item={'start_ms':index*CHUNK_MS,'end_ms':min((index+1)*CHUNK_MS,duration_ms),
                  'sample_count':len(sampled),'first_frame_id':sampled[0][0],'last_frame_id':sampled[-1][0],
                  'last_ts':sampled[-1][1],'sha256':file_hash(path)}
            workspace.put_json(f'cv:chunk:{index}',item)
            return item

        if start<count:
            ball_detector=None
            if ball_weights:
                from aifootball.perception.ball_detect import BallDetector
                ball_detector=BallDetector(ball_weights,venue.require_polygon(),(source['height'],source['width']),
                                           venue.ball_tile,venue.ball_margin_px,venue.conf_ball,pick_device())
            for batch in detect_batches(Path(video),venue,weights,start_ms=start*CHUNK_MS,ball_detector=ball_detector):
                for frame_id,ts in zip(batch.frame_ids,batch.timestamps):
                    index=min(count-1,int(ts*1000//CHUNK_MS))
                    if index!=current:
                        if index!=current+1:raise ValueError('gap in sampled detection timeline')
                        saved.append(persist(current));parts.clear();sampled.clear();current=index
                    sampled.append((frame_id,ts))
                    part=batch.detections.filter(pl.col('frame_id')==frame_id)
                    if not part.is_empty():parts.append(part)
            if not sampled or current!=count-1:raise ValueError('Incomplete video decoding')
            tolerance=max(1/venue.target_fps,1/video_fps(video))+.001
            if source['duration_s']-sampled[-1][1]>tolerance:raise ValueError('Incomplete video decoding')
            saved.append(persist(current))
        all_detections=pl.concat([schemas.read(chunks/f'{i:06d}.parquet','detections') for i in range(count)])
        _write_detections(all_detections,root/'detections.parquet')
        meta={'video':str(video),'venue_id':venue.venue_id,'camera_profile_id':venue.camera_profile_id,
              'frame_width':source['width'],'frame_height':source['height'],'video_s':source['duration_s'],
              'src_fps':video_fps(video),'target_fps':venue.target_fps,'model':venue.model,'imgsz':venue.imgsz,
              'ball_model':ball_model,'ball_model_sha256':fingerprint['ball_model']['sha256'] if ball_weights else None,
              'schema_version':schemas.SCHEMA_VERSION,
              'source_sha256':source['sha256'],'context_hash':job.contract['context_hash'],
              'created_at':datetime.now(timezone.utc).isoformat(timespec='seconds')}
        Workspace._atomic(root/'meta.json',canonical(meta))
        args=SimpleNamespace(video=Path(video),match=root,models=Path(models))
        # Replay one tracker across the whole source, never one tracker per chunk.
        cli.cmd_track(args,venue)
        if schemas.read(root/'tracks.parquet','tracks').is_empty():
            schemas.write(schemas.empty('state'),root/'state.parquet','state')
            Workspace._atomic(root/'metrics.json',canonical({}))
            Workspace._atomic(root/'checks.json',canonical({'passed':False,'critical_errors':['Нет обработанных позиций']}))
        else:
            for command in (cli.cmd_project,cli.cmd_metrics,cli.cmd_check):command(args,venue)
        workspace.put_json('cv:complete',{'chunks':count,'duration_ms':duration_ms,'source_sha256':source['sha256']})
        return root
