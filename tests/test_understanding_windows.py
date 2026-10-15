import polars as pl
import pytest


def test_no_ball_still_gets_overview_windows():
    from aifootball.understanding.windows import plan_windows
    windows=plan_windows(duration_ms=25000,tracks=pl.DataFrame(),ball_candidates=[],mode='native')
    assert windows[0]['start_ms']==0
    assert max(w['end_ms'] for w in windows)==25000
    assert [w['start_ms'] for w in windows if w['kind']=='overview']==[0,6000,12000,18000,24000]
    assert all(w['end_ms']-w['start_ms']<=20000 for w in windows)


def test_ball_boundary_candidate_is_bounded_and_deterministic():
    from aifootball.understanding.windows import plan_windows
    candidates=[{'video_ms':24000,'conf':.9},{'video_ms':24500,'conf':.6}]
    first=plan_windows(duration_ms=25000,tracks=pl.DataFrame(),ball_candidates=candidates,mode='frames')
    assert first==plan_windows(duration_ms=25000,tracks=pl.DataFrame(),ball_candidates=list(reversed(candidates)),mode='frames')
    refined=[w for w in first if w['kind']=='ball']
    assert len(refined)==1
    assert refined[0]['end_ms']==25000 and refined[0]['start_ms']>=17000
    assert all((w['end_ms']-w['start_ms'])*w['fps']<=32000 for w in first)


def test_only_tracks_observed_in_window_are_sent():
    from aifootball.understanding.windows import plan_windows
    tracks=pl.DataFrame({'track_id':[1,2],'ts':[1.,20.]})
    windows=plan_windows(duration_ms=25000,tracks=tracks,ball_candidates=[])
    assert windows[0]['track_ids']==[1]
    assert windows[-1]['track_ids']==[]


@pytest.mark.parametrize('duration',[0,-1,True,86400001])
def test_invalid_duration_rejected(duration):
    from aifootball.understanding.windows import plan_windows
    with pytest.raises(ValueError):plan_windows(duration_ms=duration,tracks=pl.DataFrame(),ball_candidates=[])


def test_large_image_displacement_produces_refinement_not_official_event():
    from aifootball.understanding.windows import plan_windows
    tracks=pl.DataFrame({'track_id':[1,1],'ts':[1.,1.5],
        'x1':[10.,110.],'x2':[30.,130.],'y1':[10.,10.],'y2':[60.,60.]})
    windows=plan_windows(duration_ms=15000,tracks=tracks,ball_candidates=[])
    refined=[item for item in windows if item['kind']=='motion']
    assert len(refined)==1 and refined[0]['fps']==4
    assert refined[0]['track_ids']==[1]
