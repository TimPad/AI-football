"""Timed local evidence; no media URLs or generative image transformations."""
from hashlib import sha256
from pathlib import Path
import json
import math
import shutil
import subprocess
import tempfile
import cv2
import numpy as np
import polars as pl
from aifootball.analytics.exchange import canonical
from aifootball.perception.frames import iter_frames,video_fps
from aifootball.processor.job import file_hash,video_info
from aifootball.processor.workspace import Workspace
from aifootball.understanding.types import FrameAsset,MediaAsset,Window


def _run(args,*,timeout=90):
    with tempfile.TemporaryFile() as output,tempfile.TemporaryFile() as errors:
        try:completed=subprocess.run(args,stdout=output,stderr=errors,timeout=timeout,check=False)
        except (OSError,subprocess.TimeoutExpired):raise ValueError('FFmpeg: запуск или время выполнения') from None
        output.seek(0);raw=output.read(65537)
        if len(raw)>65536 or completed.returncode:raise ValueError('FFmpeg: повреждённое или неподдерживаемое медиа')
        return raw


def _probe(video):
    binary=shutil.which('ffprobe')
    if not binary:raise ValueError('Не найден FFmpeg/ffprobe')
    try:
        return json.loads(_run([binary,'-v','error','-show_entries','stream=codec_type:format=duration,start_time',
                               '-of','json',str(video)],timeout=15))
    except (json.JSONDecodeError,UnicodeError):raise ValueError('FFmpeg: неверные метаданные') from None


def _save_frame(frame,*,frame_id,video_ms,out,crop=None):
    image=frame
    scale=min(1,1280/max(image.shape[:2]))
    if scale<1:image=cv2.resize(image,(max(2,round(image.shape[1]*scale)),max(2,round(image.shape[0]*scale))),interpolation=cv2.INTER_AREA)
    for _ in range(8):
        okay,encoded=cv2.imencode('.jpg',image,[cv2.IMWRITE_JPEG_QUALITY,82])
        if not okay:raise ValueError('Не удалось сохранить JPEG')
        raw=encoded.tobytes()
        if len(raw)<=512*1024:break
        image=cv2.resize(image,(max(2,int(image.shape[1]*.8)),max(2,int(image.shape[0]*.8))),interpolation=cv2.INTER_AREA)
    else:raise ValueError('Превышен размер JPEG-доказательства')
    digest=sha256(raw).hexdigest()
    identity=sha256(canonical({'hash':digest,'frame_id':frame_id,'video_ms':video_ms,'crop':crop})).hexdigest()[:24]
    path=out/(identity+'.jpg');Workspace._atomic(path,raw)
    return FrameAsset(identity,frame_id,video_ms,path,digest,crop)


def _follow_expr(keys,axis):
    """Кусочно-линейная координата угла области по времени клипа t, с; запятые экранированы для -vf."""
    points=[(float(k[0]),int(k[1+axis])) for k in keys];expr=str(points[-1][1])
    for (t0,v0),(t1,v1) in reversed(list(zip(points,points[1:]))):
        expr=f'if(lt(t\\,{t1:.3f})\\,{v0}+({v1-v0})*(t-{t0:.3f})/{t1-t0:.3f}\\,{expr})'
    return f'if(lt(t\\,{points[0][0]:.3f})\\,{points[0][1]}\\,{expr})'


def _clip_view(crop,width,height):
    """Фильтр области клипа: (x,y,w,h) — неподвижная, {'size':[w,h],'keys':[[t,x,y],...]} — следящая."""
    if crop is None:return 'scale=w=min(960\\,iw):h=-2'
    follow=type(crop) is dict
    if follow:
        if set(crop)!={'size','keys'} or len(crop['size'])!=2 or not 0<len(crop['keys'])<=200:raise ValueError('Недопустимая область клипа')
        w,h=crop['size'];keys=crop['keys']
        if (any(type(k) not in (list,tuple) or len(k)!=3 or type(k[0]) not in (int,float) or not math.isfinite(k[0]) or k[0]<0
                or type(w) is not int or type(h) is not int
                or any(type(v) is not int or not 0<=v<=limit for v,limit in ((k[1],width-w),(k[2],height-h))) for k in keys)
            or any(b[0]<=a[0] for a,b in zip(keys,keys[1:]))):raise ValueError('Недопустимая область клипа')
        box=(0,0,w,h)
    else:
        if len(crop)!=4:raise ValueError('Недопустимая область клипа')
        box=tuple(crop)
    if (any(type(v) is not int or v<0 or v%2 for v in box) or not box[2] or not box[3] or
        box[0]+box[2]>width or box[1]+box[3]>height):raise ValueError('Недопустимая область клипа')
    w,h=box[2],box[3];scale=min(960/w,720/h);size=f'scale={round(w*scale/2)*2}:{round(h*scale/2)*2}'
    if follow:return f"setpts=PTS-STARTPTS,crop=w={w}:h={h}:x={_follow_expr(keys,0)}:y={_follow_expr(keys,1)},{size}"
    return f'crop={w}:{h}:{box[0]}:{box[1]},{size}'


def make_window(video:Path,*,start_ms:int,end_ms:int,out:Path,mode:str,fps=1,track_ids=(),crop=None)->Window:
    """crop — область исходника (см. _clip_view), вписанная в 960×720; без неё — весь кадр."""
    if (type(start_ms) is not int or type(end_ms) is not int or not 0<=start_ms<end_ms or
        end_ms-start_ms>20000 or type(fps) not in (int,float) or not math.isfinite(fps) or not 0<fps<=4 or
        mode not in ('native','frames') or math.ceil((end_ms-start_ms)*fps/1000)>32):
        raise ValueError('Неподдерживаемый диапазон/частота окна')
    info=video_info(video);src_fps=video_fps(video)
    if end_ms>round(info['duration_s']*1000):raise ValueError('Окно выходит за исходник')
    if crop is not None and mode!='native':raise ValueError('Область клипа только для native')
    view=_clip_view(crop,info['width'],info['height'])
    # Align to actual source-frame boundaries instead of inventing sub-frame precision.
    start_frame=math.ceil(start_ms*src_fps/1000-1e-6)
    end_frame=math.floor(end_ms*src_fps/1000+1e-6)
    actual_start=round(start_frame/src_fps*1000);actual_end=round(end_frame/src_fps*1000)
    if actual_end<=actual_start:raise ValueError('В окне нет полного исходного кадра')
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    media=None
    if mode=='native':
        binary=shutil.which('ffmpeg')
        if not binary:raise ValueError('Не найден FFmpeg')
        probe=_probe(video);has_audio=any(stream.get('codec_type')=='audio' for stream in probe.get('streams',[]))
        path=out/'clip.mp4'
        args=[binary,'-v','error','-y','-ss',f'{start_frame/src_fps:.9f}','-i',str(video),
              '-t',f'{(end_frame-start_frame)/src_fps:.9f}','-map','0:v:0']
        if has_audio:args+=['-map','0:a:0','-c:a','aac','-b:a','64k','-af','asetpts=PTS-STARTPTS']
        else:args+=['-an']
        args+=['-vf',view+',setpts=PTS-STARTPTS','-r','12','-c:v','libx264',
               '-preset','veryfast','-crf','28','-maxrate','1M','-bufsize','2M','-pix_fmt','yuv420p',
               # Один поток и bitexact: повторная сборка окна даёт тот же файл, и --resume находит оплаченные ответы.
               '-threads','1','-fflags','+bitexact','-flags:v','+bitexact','-flags:a','+bitexact','-map_metadata','-1',
               '-movflags','+faststart',str(path)]
        _run(args)
        if not path.exists() or path.stat().st_size>=6*1024*1024:raise ValueError('Клип превышает лимит 8 MiB base64')
        exported=_probe(path)
        try:duration=float(exported['format']['duration']);origin=float(exported['format'].get('start_time','0'))
        except (KeyError,TypeError,ValueError):raise ValueError('Неизвестные границы экспортированного клипа') from None
        if not math.isfinite(duration) or abs(duration-(actual_end-actual_start)/1000)>max(1/12,1/src_fps)+.05 or abs(origin)>.05:
            raise ValueError('Границы клипа не совпадают с исходным окном')
        actual_audio=any(stream.get('codec_type')=='audio' for stream in exported.get('streams',[]))
        if actual_audio!=has_audio:raise ValueError('Аудиодорожка потеряна при экспорте')
        media=MediaAsset('clip','video',path,file_hash(path),actual_start,actual_end,actual_audio)
    frames=tuple(_save_frame(frame,frame_id=fid,video_ms=round(ts*1000),out=out)
                 for fid,ts,frame in iter_frames(video,fps,start_ms=actual_start,end_ms=actual_end))
    if not frames or len(frames)>32:raise ValueError('Нет кадров или превышен лимит кадров окна')
    identity=sha256(canonical({'start_ms':actual_start,'end_ms':actual_end,'mode':mode,
                               'frames':[frame.sha256 for frame in frames],'clip':media.sha256 if media else None})).hexdigest()[:24]
    return Window(identity,actual_start,actual_end,frames,media,tuple(track_ids),mode)


def select_player_frames(video:Path,tracks:pl.DataFrame,out:Path,*,max_per_track=5):
    if type(max_per_track) is not int or not 1<=max_per_track<=5:raise ValueError('Лимит кадров игрока 1–5')
    required={'track_id','frame_id','ts','x1','y1','x2','y2','conf'}
    if not required<=set(tracks.columns):raise ValueError('Нет полей видеотреков')
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    cap=cv2.VideoCapture(str(video));result={};quality=[]
    if not cap.isOpened():raise ValueError('Не открывается видео')
    width=int(cap.get(cv2.CAP_PROP_FRAME_WIDTH));height=int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    try:
        for (track_id,),group in tracks.group_by('track_id',maintain_order=True):
            group=group.sort('ts').unique('frame_id',maintain_order=True)
            # Candidate slots span the whole track, not only the first few large boxes.
            indices=np.unique(np.linspace(0,len(group)-1,min(20,len(group)),dtype=int))
            candidates=[]
            for index in indices:
                row=group.row(int(index),named=True)
                if not all(math.isfinite(float(row[key])) for key in ('ts','x1','y1','x2','y2','conf')):continue
                x1,y1=max(0,math.floor(row['x1'])),max(0,math.floor(row['y1']))
                x2,y2=min(width,math.ceil(row['x2'])),min(height,math.ceil(row['y2']))
                if x2-x1<12 or y2-y1<20:continue
                area=(x2-x1)*(y2-y1);occlusion=0.
                other=tracks.filter((pl.col('frame_id')==row['frame_id'])&(pl.col('track_id')!=track_id))
                for box in other.iter_rows(named=True):
                    overlap=max(0,min(x2,box['x2'])-max(x1,box['x1']))*max(0,min(y2,box['y2'])-max(y1,box['y1']))
                    occlusion=max(occlusion,min(1,overlap/area))
                if occlusion>=.6:continue
                cap.set(cv2.CAP_PROP_POS_FRAMES,int(row['frame_id']));okay,frame=cap.read()
                if not okay:continue
                crop=frame[y1:y2,x1:x2];sharpness=float(cv2.Laplacian(cv2.cvtColor(crop,cv2.COLOR_BGR2GRAY),cv2.CV_64F).var())
                if not math.isfinite(sharpness) or sharpness<5:continue
                score=math.log1p(area)*math.log1p(sharpness)*max(0,min(1,float(row['conf'])))*(1-occlusion)
                candidates.append((score,row,crop,(x1,y1,x2,y2),sharpness,occlusion))
            chosen=[]
            for score,row,crop,bounds,sharpness,occlusion in sorted(candidates,key=lambda value:(-value[0],value[1]['frame_id'])):
                ms=round(row['ts']*1000)
                if any(abs(ms-frame.video_ms)<2000 for frame in chosen):continue
                frame=_save_frame(crop,frame_id=int(row['frame_id']),video_ms=ms,out=out,crop=bounds)
                chosen.append(frame);quality.append({'id':frame.id,'track_id':int(track_id),'video_ms':ms,
                    'area_px':int(crop.shape[0]*crop.shape[1]),'sharpness':sharpness,'occlusion':occlusion,'score':score})
                if len(chosen)==max_per_track:break
            if chosen:result[int(track_id)]=tuple(sorted(chosen,key=lambda frame:frame.video_ms))
    finally:cap.release()
    Workspace._atomic(out/'selection-quality.json',canonical({'frames':quality}))
    return result
