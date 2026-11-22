import pytest

from aifootball.perception.frames import iter_frames, video_fps
from conftest import decoded_times, write_vfr_video


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
    with pytest.raises(ValueError, match='разрешение.*320.*240.*1000.*500'):
        list(iter_frames(tiny_video, 10, expected_width=1000, expected_height=500))


def test_missing_file_fails_clearly(tmp_path):
    with pytest.raises(FileNotFoundError, match='не открывается'):
        list(iter_frames(tmp_path / 'nope.mp4', target_fps=10))


@pytest.fixture
def vfr_video(tmp_path):
    return write_vfr_video(tmp_path / 'vfr.mp4')


def test_frame_time_is_decoded_timestamp_not_number_over_fps(vfr_video):
    """Время кадра — его метка в потоке: номер / fps на такой записи уходит на десятки кадров."""
    times = decoded_times(vfr_video)
    frames = list(iter_frames(vfr_video, target_fps=100))
    assert [f[0] for f in frames] == list(range(len(times)))
    assert [f[1] for f in frames] == pytest.approx(times, abs=1e-6)
    fps = video_fps(vfr_video)
    assert max(abs(f[0] / fps - f[1]) for f in frames) > 10  # без метки время ушло бы на 10+ с


class GrabCounter:
    """Считает кадры, прочитанные из Python; кадры, которые OpenCV читает при перемотке, сюда не входят."""

    grabs = 0

    def __init__(self, *args):
        self.cap = GrabCounter.real(*args)

    def grab(self):
        type(self).grabs += 1
        return self.cap.grab()

    def __getattr__(self, name):
        return getattr(self.cap, name)


def test_resume_after_known_frame_keeps_numbers_times_and_pixels(vfr_video, monkeypatch):
    """Перемотка к уже прочитанному кадру и сверка его метки: дальше всё как при чтении подряд."""
    import cv2

    full = list(iter_frames(vfr_video, target_fps=100))
    anchor = full[150][:2]
    fps = video_fps(vfr_video)
    assert abs(anchor[0] - anchor[1] * fps) > 20  # OpenCV по времени назвал бы этот кадр другим номером
    start_ms = int(anchor[1] * 1000) + 1
    expected = [f for f in full if f[1] >= start_ms / 1000]
    GrabCounter.real, GrabCounter.grabs = cv2.VideoCapture, 0
    monkeypatch.setattr(cv2, 'VideoCapture', GrabCounter)
    tail = list(iter_frames(vfr_video, 100, start_ms=start_ms, after=anchor))
    assert [f[:2] for f in tail] == [f[:2] for f in expected]
    assert all((a[2] == b[2]).all() for a, b in zip(tail, expected))
    assert GrabCounter.grabs < len(full) - 100  # перемотка, а не чтение 150 кадров подряд


def test_without_seek_resume_reads_frames_in_order(vfr_video):
    full = list(iter_frames(vfr_video, target_fps=1))
    tail = list(iter_frames(vfr_video, 1, start_ms=70000, seek=False))
    assert [f[:2] for f in tail] == [f[:2] for f in full if f[1] >= 70]


def test_unknown_anchor_falls_back_to_reading_in_order(vfr_video):
    full = list(iter_frames(vfr_video, target_fps=100))
    tail = list(iter_frames(vfr_video, 100, start_ms=70000, after=(full[150][0], full[150][1] + 0.123)))
    assert [f[:2] for f in tail] == [f[:2] for f in full if f[1] >= 70]


def test_video_duration_counts_only_decoded_frames(vfr_video):
    """Контейнер считает и отброшенные кадры с отрицательной меткой: длительность по ним длиннее записи."""
    import cv2

    from aifootball.processor.job import video_info

    times = decoded_times(vfr_video)
    cap = cv2.VideoCapture(str(vfr_video))
    container_frames, fps = cap.get(cv2.CAP_PROP_FRAME_COUNT), cap.get(cv2.CAP_PROP_FPS)
    cap.release()
    assert container_frames > len(times)
    assert video_info(vfr_video)['duration_s'] == pytest.approx(times[-1] + 1 / fps, abs=1e-6)
