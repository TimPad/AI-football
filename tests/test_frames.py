import pytest

from aifootball.perception.frames import iter_frames, video_fps


def test_samples_25fps_down_to_10(tiny_video):
    frames = list(iter_frames(tiny_video, target_fps=10))

    # 50 кадров при 25 fps = 2 секунды -> 20 кадров при 10 fps
    assert len(frames) == 20
    assert [f[0] for f in frames[:5]] == [0, 3, 5, 8, 10]
    assert frames[1][1] == pytest.approx(0.12)
    assert frames[0][2].shape == (240, 320, 3)


def test_target_above_source_keeps_every_frame(tiny_video):
    assert len(list(iter_frames(tiny_video, target_fps=100))) == 50


def test_reports_fps(tiny_video):
    assert video_fps(tiny_video) == pytest.approx(25.0)


def test_camera_profile_resolution_must_match_video(tiny_video):
    assert len(list(iter_frames(tiny_video, 10, expected_width=320, expected_height=240))) == 20
    with pytest.raises(ValueError, match="разрешение.*320.*240.*1000.*500"):
        list(iter_frames(tiny_video, 10, expected_width=1000, expected_height=500))


def test_missing_file_fails_clearly(tmp_path):
    with pytest.raises(FileNotFoundError, match="не открывается"):
        list(iter_frames(tmp_path / "nope.mp4", target_fps=10))
