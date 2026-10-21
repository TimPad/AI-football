"""Ручной журнал владения мячом: эталон для сверки владения и передач (cli eval-passes).

    python -m aifootball.tools.label_touches --video V --out data/gt/<матч>/touches.parquet
        [--scale 0.5] [--team-a "зелёные"] [--team-b "оранжевые"] [--from-start]

Смотрите видео и жмите клавишу, когда мяч ПОЛУЧАЕТ НОВЫЙ игрок (приём паса, перехват, отбор).
Пока мяч ведёт тот же игрок — ничего не жмите. Клавиши (не зависят от раскладки):
    1          мяч получил игрок команды A
    2          мяч получил игрок команды B
    3          мяч вне игры: аут, гол, фол, остановка (до следующей 1/2 мяч ничей)
    8          пас: игрок с мячом ударил по мячу, отдавая его; исход — по следующей отметке
               (свой — точная, соперник — перехват, 3 — в аут). Отбор без паса — без 8.
               Ввод мяча после остановки — как раньше, 1/2 за принявшего, без 8.
    0          удар по воротам
    пробел     пауза / пуск
    4 / 6      кадр назад / вперёд (стрелки тоже работают)
    5          назад на 2 секунды
    7 / 9      медленнее / быстрее
    Backspace  удалить последнюю отметку до текущего кадра и встать на неё
    Esc        выйти (всё уже сохранено)
Отметка ставится на показанный кадр: на паузе можно отмотать к моменту приёма и нажать там.
Повторный запуск продолжает с последней отметки; --from-start — с начала видео, чтобы дополнить
готовый журнал отметками 8 и 0: 1/2/3 тогда не ставятся, Backspace удаляет только 8 и 0.
Два 8 подряд без 1/2 между ними — первый пас не засчитается; если 1/2 за принявшего нет, запишите время.
"""

import argparse
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import polars as pl

from aifootball import schemas

KEY_ESC, KEY_SPACE = 27, 32
KEY_BACKSPACE = {8, 127}
KEY_EVENT = {ord("1"): "A", ord("2"): "B", ord("3"): "dead", ord("8"): "pass", ord("0"): "shot"}
KEY_FRAME_BACK = {ord("4"), 63234, 2424832, 65361}  # 4 и стрелка влево (macOS / Windows / Linux)
KEY_FRAME_FWD = {ord("6"), 63235, 2555904, 65363}
KEY_JUMP_BACK = ord("5")
KEY_SLOWER, KEY_FASTER = ord("7"), ord("9")
SPEEDS = (0.25, 0.5, 1.0, 1.5, 2.0)
JUMP_BACK_S = 2.0
RESUME_BACK_S = 3.0
EVENT_BGR = {"A": (60, 200, 60), "B": (0, 140, 255), "dead": (200, 200, 200), "pass": (255, 220, 0), "shot": (255, 0, 255)}
WINDOW = "label_touches"


class Touches:
    """Журнал отметок: не больше одной на кадр, пишется на диск после каждого изменения."""

    def __init__(self, path: Path, fps: float):
        self.path, self.fps = path, fps
        self.events: dict[int, str] = {}
        if path.exists():
            df = schemas.read(path, "touches")
            self.events = dict(zip(df["frame_id"].to_list(), df["event"].to_list()))

    def set(self, frame_id: int, event: str) -> None:
        self.events[frame_id] = event
        self._save()

    def pop_before(self, frame_id: int, kinds: tuple[str, ...] | None = None) -> int | None:
        """Удаляет последнюю отметку не позже frame_id (только из kinds, если заданы); возвращает её кадр."""
        earlier = [f for f, e in self.events.items() if f <= frame_id and (kinds is None or e in kinds)]
        if not earlier:
            return None
        last = max(earlier)
        del self.events[last]
        self._save()
        return last

    def _save(self) -> None:
        frames = sorted(self.events)
        df = pl.DataFrame({"frame_id": frames, "ts": [f / self.fps for f in frames],
                           "event": [self.events[f] for f in frames]}, schema=schemas.TOUCHES)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        schemas.write(df, self.path, "touches")


class Player:
    """Кадры видео по номеру: подряд читаем без перемотки, иначе — seek."""

    def __init__(self, video: Path):
        self.cap = cv2.VideoCapture(str(video))
        if not self.cap.isOpened():
            sys.exit(f"не открывается видео: {video}")
        self.total = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.fps = self.cap.get(cv2.CAP_PROP_FPS)
        self._next = 0
        self._last: tuple[int, np.ndarray] | None = None

    def frame(self, frame_id: int) -> np.ndarray:
        if self._last is not None and self._last[0] == frame_id:
            return self._last[1]
        if frame_id != self._next:
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, frame_id)
        ok, img = self.cap.read()
        if not ok:
            img = self._last[1] if self._last is not None else np.zeros((480, 640, 3), np.uint8)
        self._next = frame_id + 1
        self._last = (frame_id, img)
        return img


def render(img: np.ndarray, scale: float, pos: int, total: int, fps: float, speed: float, playing: bool,
           events: dict[int, str], flash: str | None) -> np.ndarray:
    shown = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA) if scale != 1 else img.copy()
    h, w = shown.shape[:2]
    t = pos / fps
    state = "PLAY" if playing else "PAUSE"
    header = f"{int(t // 60)}:{t % 60:04.1f}  x{speed}  {state}   1=A  2=B  3=dead  8=pass  0=shot  space  4/6 frame  5 -2s  7/9 speed"
    cv2.putText(shown, header, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 4, cv2.LINE_AA)
    cv2.putText(shown, header, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2, cv2.LINE_AA)
    # последние отметки до текущего кадра
    recent = [f for f in sorted(events) if f <= pos][-4:]
    for i, f in enumerate(recent):
        txt = f"{f / fps:6.1f}s  {events[f]}"
        cv2.putText(shown, txt, (10, 62 + 26 * i), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 4, cv2.LINE_AA)
        cv2.putText(shown, txt, (10, 62 + 26 * i), cv2.FONT_HERSHEY_SIMPLEX, 0.7, EVENT_BGR[events[f]], 2, cv2.LINE_AA)
    if flash is not None:
        cv2.rectangle(shown, (0, 0), (w - 1, h - 1), EVENT_BGR[flash], 10)
    # шкала времени с отметками
    bar_y = h - 22
    cv2.rectangle(shown, (0, bar_y - 12), (w, h), (30, 30, 30), -1)
    for f, e in events.items():
        x = int(f / max(1, total - 1) * (w - 1))
        cv2.line(shown, (x, bar_y - 8), (x, h - 4), EVENT_BGR[e], 2)
    x = int(pos / max(1, total - 1) * (w - 1))
    cv2.line(shown, (x, bar_y - 12), (x, h), (0, 0, 255), 3)
    return shown


def run(player: Player, touches: Touches, scale: float, start: int, adding: bool = False) -> None:
    pos, playing, speed_idx = start, False, SPEEDS.index(0.5)
    flash_until, flash_event = 0.0, None
    cv2.namedWindow(WINDOW, cv2.WINDOW_AUTOSIZE)
    while True:
        tick = time.monotonic()
        flash = flash_event if tick < flash_until else None
        cv2.imshow(WINDOW, render(player.frame(pos), scale, pos, player.total, player.fps, SPEEDS[speed_idx],
                                  playing, touches.events, flash))
        wait = 1000 / (player.fps * SPEEDS[speed_idx]) - (time.monotonic() - tick) * 1000 if playing else 30
        key = cv2.waitKeyEx(max(1, int(wait)))
        if key != -1 and key < 256:
            key &= 0xFF
        if key == KEY_ESC:
            break
        if key in KEY_EVENT:
            event = event_for_key(key, adding)
            if event is None:
                print("   дополнение журнала: 1/2/3 уже стоят, ставьте только 8 (пас) и 0 (удар)")
                continue
            touches.set(pos, event)
            flash_until, flash_event = time.monotonic() + 0.4, event
            print(f"   {pos / player.fps:6.1f} с  {event}")
        elif key == KEY_SPACE:
            playing = not playing
        elif key in KEY_FRAME_BACK:
            playing, pos = False, max(0, pos - 1)
        elif key in KEY_FRAME_FWD:
            playing, pos = False, min(player.total - 1, pos + 1)
        elif key == KEY_JUMP_BACK:
            pos = max(0, pos - int(JUMP_BACK_S * player.fps))
        elif key == KEY_SLOWER:
            speed_idx = max(0, speed_idx - 1)
        elif key == KEY_FASTER:
            speed_idx = min(len(SPEEDS) - 1, speed_idx + 1)
        elif key in KEY_BACKSPACE:
            removed = touches.pop_before(pos, ADD_EVENTS if adding else None)
            if removed is not None:
                playing, pos = False, removed
                print(f"   удалена отметка {removed / player.fps:.1f} с")
        elif playing:
            if pos >= player.total - 1:
                playing = False
                print("\nконец видео: Esc — выйти")
            else:
                pos += 1
    cv2.destroyAllWindows()


ADD_EVENTS = ("pass", "shot")


def event_for_key(key: int, adding: bool) -> str | None:
    """Отметка по клавише. При дополнении готового журнала — только пас и удар: повторные 1/2/3 его портят."""
    event = KEY_EVENT.get(key)
    return event if event is not None and (not adding or event in ADD_EVENTS) else None


def start_frame(touches: Touches, fps: float, from_start: bool) -> int:
    """С начала видео — для нового журнала и для дополнения готового; иначе за 3 с до последней отметки."""
    if from_start or not touches.events:
        return 0
    return max(0, max(touches.events) - int(RESUME_BACK_S * fps))


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--scale", type=float, default=0.5, help="масштаб окна")
    parser.add_argument("--team-a", default="команда A", help="как узнать команду A (для подсказки)")
    parser.add_argument("--team-b", default="команда B", help="как узнать команду B (для подсказки)")
    parser.add_argument("--from-start", action="store_true", help="с начала видео: дополнить готовый журнал")
    args = parser.parse_args(argv)

    player = Player(args.video)
    touches = Touches(args.out, player.fps)
    print(__doc__.split("\n\n", 2)[2].replace("команды A", f"команды A ({args.team_a})")
          .replace("команды B", f"команды B ({args.team_b})"))
    start = start_frame(touches, player.fps, args.from_start)
    if touches.events:
        print(f"в журнале {len(touches.events)} отметок — начинаю с {start / player.fps:.1f} с")
    adding = args.from_start and bool(touches.events)
    if adding:
        print("дополнение журнала: принимаются только 8 и 0, Backspace удаляет только их")
    run(player, touches, args.scale, start, adding)
    print(f"отметок: {len(touches.events)} -> {args.out}")


if __name__ == "__main__":
    main()
