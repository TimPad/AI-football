"""Regular coverage plus bounded refinements; absence of a ball is not a stoppage."""
from hashlib import sha256
import math
import polars as pl
from aifootball.analytics.exchange import canonical


def plan_windows(*,duration_ms:int,tracks:pl.DataFrame,ball_candidates:list[dict],mode='native'):
    if type(duration_ms) is not int or not 1<=duration_ms<=86400000 or mode not in ('native','frames'):
        raise ValueError('Invalid window planning parameters')
    specs=[{'start_ms':start,'end_ms':min(duration_ms,start+12000),'fps':1,'kind':'overview'}
           for start in range(0,duration_ms,6000)]
    candidates={}
    def candidate(ms,confidence,kind):
        if (type(ms) not in (int,float) or not math.isfinite(ms) or not 0<=ms<duration_ms or
            type(confidence) not in (int,float) or not math.isfinite(confidence) or confidence<.2):return
        bucket=(int(ms)//6000,kind);previous=candidates.get(bucket)
        value=(float(confidence),-int(ms))
        if previous is None or value>previous:candidates[bucket]=value
    for ball in ball_candidates:
        if not isinstance(ball,dict):continue
        ms=ball.get('video_ms')
        if ms is None and type(ball.get('ts')) in (int,float):ms=ball['ts']*1000
        candidate(ms,ball.get('conf',1),'ball')
    if {'track_id','ts','x1','y1','x2','y2'}<=set(tracks.columns):
        for _,group in tracks.group_by('track_id',maintain_order=True):
            previous=None
            for row in group.sort('ts').iter_rows(named=True):
                values=[row[k] for k in ('ts','x1','y1','x2','y2')]
                if not all(type(value) in (int,float) and math.isfinite(value) for value in values):continue
                if previous is not None:
                    dt=row['ts']-previous['ts'];height=max(row['y2']-row['y1'],previous['y2']-previous['y1'],1)
                    dx=(row['x1']+row['x2']-previous['x1']-previous['x2'])/2
                    dy=(row['y1']+row['y2']-previous['y1']-previous['y2'])/2
                    ratio=math.hypot(dx,dy)/height
                    if .05<=dt<=1.5 and ratio>.75:candidate(round(row['ts']*1000),min(1,ratio),'motion')
                previous=row
    for (bucket,kind),(confidence,negative_ms) in sorted(candidates.items()):
        center=-negative_ms;start=max(0,min(center-4000,duration_ms-8000));end=min(duration_ms,start+8000)
        specs.append({'start_ms':start,'end_ms':end,'fps':4,'kind':kind})
    ordered=sorted(specs,key=lambda item:(item['start_ms'],item['end_ms'],item['kind']))
    result=[];seen=set()
    for spec in ordered:
        key=(spec['start_ms'],spec['end_ms'],spec['fps'])
        if key in seen:continue
        seen.add(key)
        ids=[]
        if {'track_id','ts'}<=set(tracks.columns):
            ids=sorted(tracks.filter((pl.col('ts')>=spec['start_ms']/1000)&(pl.col('ts')<spec['end_ms']/1000))['track_id'].unique().to_list())
        result.append({**spec,'id':sha256(canonical(spec)).hexdigest()[:24],'track_ids':ids,'mode':mode})
    return result
