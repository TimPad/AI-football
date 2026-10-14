import shutil
import subprocess
from pathlib import Path
import cv2
import numpy as np
import polars as pl
import pytest
from conftest import write_video


@pytest.mark.parametrize('mode',['frames','native'])
def test_window_retains_source_offset_and_missing_audio(tmp_path,mode):
    if mode=='native' and not shutil.which('ffmpeg'):pytest.skip('FFmpeg unavailable')
    from aifootball.processor.media import make_window
    video=write_video(tmp_path/'silent.mp4',n_frames=80,fps=4)
    window=make_window(video,start_ms=6000,end_ms=12000,out=tmp_path/'window',mode=mode)
    assert window.start_ms==6000 and window.end_ms==12000
    assert len(window.frames)==6
    assert all(6000<=frame.video_ms<12000 for frame in window.frames)
    assert window.frames[0].frame_id==24
    if mode=='native':
        assert window.media.start_ms==6000 and window.media.has_audio is False
        assert window.media.path.stat().st_size<6*1024*1024
    else:assert window.media is None


def test_clip_preserves_synthetic_audio(tmp_path):
    if not shutil.which('ffmpeg'):pytest.skip('FFmpeg unavailable')
    from aifootball.processor.media import make_window
    silent=write_video(tmp_path/'silent.mp4',n_frames=80,fps=4)
    video=tmp_path/'tone.mp4'
    result=subprocess.run(['ffmpeg','-v','error','-y','-i',str(silent),'-f','lavfi','-i',
        'sine=frequency=440:duration=20','-c:v','copy','-c:a','aac','-shortest',str(video)],capture_output=True)
    assert result.returncode==0
    window=make_window(video,start_ms=6000,end_ms=12000,out=tmp_path/'window',mode='native')
    assert window.media.has_audio is True
    assert window.media.start_ms==6000 and window.media.end_ms==12000


@pytest.mark.parametrize('start,end,fps',[(-1,1000,1),(0,21000,1),(1000,1000,1),(0,12000,4),(0,1000,0)])
def test_unsupported_windows_fail_before_api(tmp_path,start,end,fps):
    from aifootball.processor.media import make_window
    video=write_video(tmp_path/'silent.mp4',n_frames=100,fps=4)
    with pytest.raises(ValueError):make_window(video,start_ms=start,end_ms=end,out=tmp_path/'window',mode='frames',fps=fps)


def test_missing_ffmpeg_is_clear_error(tmp_path,monkeypatch):
    from aifootball.processor.media import make_window
    video=write_video(tmp_path/'silent.mp4',n_frames=100,fps=4)
    monkeypatch.setattr(shutil,'which',lambda name:None)
    with pytest.raises(ValueError,match='FFmpeg'):make_window(video,start_ms=0,end_ms=1000,out=tmp_path/'w',mode='native')


def test_crops_are_bounded_and_distinct_in_time(tmp_path):
    from aifootball.processor.media import select_player_frames
    video=tmp_path/'players.mp4'
    writer=cv2.VideoWriter(str(video),cv2.VideoWriter.fourcc(*'mp4v'),2,(320,240))
    board=((np.indices((240,320)).sum(axis=0)//4%2)*255).astype(np.uint8)
    for _ in range(24):writer.write(np.repeat(board[:,:,None],3,axis=2))
    writer.release()
    tracks=pl.DataFrame({'track_id':[1]*24,'frame_id':list(range(24)),
        'ts':[i/2 for i in range(24)],'x1':[-5]*24,'y1':[20]*24,'x2':[100]*24,'y2':[245]*24,'conf':[.9]*24})
    frames=select_player_frames(video,tracks,tmp_path/'evidence')[1]
    assert 2<=len(frames)<=5
    assert all(frame.crop==(0,20,100,240) for frame in frames)
    assert len({frame.frame_id for frame in frames})==len(frames)
    assert all(b.video_ms-a.video_ms>=2000 for a,b in zip(sorted(frames,key=lambda f:f.video_ms),sorted(frames,key=lambda f:f.video_ms)[1:]))
    assert all(frame.path.stat().st_size<=512*1024 for frame in frames)


def test_fully_overlapped_player_is_not_good_number_evidence(tmp_path):
    from aifootball.processor.media import select_player_frames
    video=tmp_path/'sharp.mp4'
    writer=cv2.VideoWriter(str(video),cv2.VideoWriter.fourcc(*'mp4v'),2,(320,240))
    board=((np.indices((240,320)).sum(axis=0)//4%2)*255).astype(np.uint8)
    for _ in range(10):writer.write(np.repeat(board[:,:,None],3,axis=2))
    writer.release()
    tracks=pl.DataFrame({'track_id':[1,2],'frame_id':[2,2],'ts':[1.,1.],
        'x1':[10,10],'y1':[10,10],'x2':[100,100],'y2':[200,200],'conf':[.9,.9]})
    assert select_player_frames(video,tracks,tmp_path/'evidence')=={}
    assert 1 in select_player_frames(video,tracks.filter(pl.col('track_id')==1),tmp_path/'single')


def test_blurry_uniform_crop_is_not_number_evidence(tmp_path):
    from aifootball.processor.media import select_player_frames
    video=write_video(tmp_path/'flat.mp4',n_frames=5,fps=2)
    tracks=pl.DataFrame({'track_id':[1],'frame_id':[2],'ts':[1.],
        'x1':[10],'y1':[10],'x2':[100],'y2':[200],'conf':[.9]})
    assert select_player_frames(video,tracks,tmp_path/'evidence')=={}


def test_non_frame_boundary_is_not_claimed_as_exact_source_time(tmp_path):
    from aifootball.processor.media import make_window
    video=write_video(tmp_path/'silent.mp4',n_frames=40,fps=4)
    window=make_window(video,start_ms=1234,end_ms=6321,out=tmp_path/'w',mode='frames')
    assert window.start_ms==1250 and window.end_ms==6250
    assert all(1250<=frame.video_ms<6250 for frame in window.frames)


def test_native_clip_size_is_checked_before_probe_or_api(tmp_path,monkeypatch):
    if not shutil.which('ffmpeg'):pytest.skip('FFmpeg unavailable')
    import aifootball.processor.media as media
    video=write_video(tmp_path/'silent.mp4',n_frames=40,fps=4)
    real=media._run
    def oversized(args,**kwargs):
        if Path(args[0]).name=='ffmpeg':
            Path(args[-1]).write_bytes(b'x'*(6*1024*1024));return b''
        return real(args,**kwargs)
    monkeypatch.setattr(media,'_run',oversized)
    with pytest.raises(ValueError,match='8 MiB'):media.make_window(video,start_ms=0,end_ms=2000,out=tmp_path/'w',mode='native')
