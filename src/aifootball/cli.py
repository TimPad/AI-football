"""Пайплайн по шагам. Каждый шаг читает артефакт предыдущего из каталога матча.

    python -m aifootball.cli run     --video V --venue DIR --match DIR   # всё подряд
    python -m aifootball.cli detect  --video V --venue DIR --match DIR   # минуты
    python -m aifootball.cli track   --venue DIR --match DIR             # секунды
    python -m aifootball.cli project --venue DIR --match DIR
    python -m aifootball.cli metrics --venue DIR --match DIR
    python -m aifootball.cli check   --venue DIR --match DIR
    python -m aifootball.cli render  --video V --venue DIR --match DIR [--seconds 60]
    python -m aifootball.cli report --venue DIR --match DIR [--video V] [--halves 0:40-21:50,27:10-46:00]
    python -m aifootball.cli eval-ball --venue DIR --match DIR --labels data/gt/<матч>/ball.parquet
    python -m aifootball.cli eval-passes --venue DIR --match DIR --touches data/gt/<матч>/touches.parquet
"""

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from aifootball import schemas
from aifootball.analytics.checks import phase1_checks
from aifootball.analytics.metrics import compute_metrics
from aifootball.perception.frames import video_fps
from aifootball.perception.teams import assign_roles, assign_teams, team_color_centers
from aifootball.perception.track import track_people
from aifootball.state.project import project_tracks
from aifootball.venue import load_venue


def cmd_detect(args, venue) -> None:
    from aifootball.perception.detect import detect_video  # тянет torch — только здесь

    started = time.perf_counter()
    ball_detector = None
    if venue.ball_model:
        import cv2

        from aifootball.perception.ball_detect import BallDetector
        from aifootball.perception.detect import pick_device

        cap = cv2.VideoCapture(str(args.video))
        frame_shape = (int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)), int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)))
        cap.release()
        ball_detector = BallDetector(args.models / venue.ball_model, venue.require_polygon(), frame_shape,
                                     venue.ball_tile, venue.ball_margin_px, venue.conf_ball, pick_device())
    detections = detect_video(args.video, venue, args.models / venue.model, ball_detector=ball_detector)
    schemas.write(detections, args.match / "detections.parquet", "detections")
    schemas.write_json(
        {
            "video": str(args.video),
            "venue_id": venue.venue_id,
            "camera_profile_id": venue.camera_profile_id,
            "frame_width": venue.frame_width,
            "frame_height": venue.frame_height,
            "src_fps": video_fps(args.video),
            "target_fps": venue.target_fps,
            "model": venue.model,
            "imgsz": venue.imgsz,
            "ball_model": venue.ball_model,
            "schema_version": schemas.SCHEMA_VERSION,
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        },
        args.match / "meta.json",
    )
    people = detections.filter(detections["cls"] == "person")
    print(
        f"detect: {detections['frame_id'].n_unique()} кадров, {len(people)} людей, "
        f"{len(detections) - len(people)} мячей за {time.perf_counter() - started:.0f} с"
    )


def cmd_track(args, venue) -> None:
    from aifootball.perception.stitch import split_on_color_change, stitch_tracks

    detections = schemas.read(args.match / "detections.parquet", "detections")
    raw_tracks = track_people(detections, venue)
    split_tracks = split_on_color_change(raw_tracks, team_color_centers(raw_tracks, venue.min_team_observations))
    stitched_tracks = stitch_tracks(split_tracks, max_gap_s=venue.max_gap_s * 5.0)
    assigned_teams = assign_teams(stitched_tracks, min_observations=venue.min_team_observations)
    tracks = assign_roles(assigned_teams, venue)
    schemas.write(tracks, args.match / "tracks.parquet", "tracks")
    on_pitch = tracks.filter(tracks["in_pitch"])
    print(
        f"track: исходно {raw_tracks['track_id'].n_unique()} -> {tracks['track_id'].n_unique()} треков после сшивки, "
        f"на поле {on_pitch['track_id'].n_unique()}, "
        f"роли {tracks.group_by('role').len().sort('role').rows()}, "
        f"команды {tracks.group_by('team').len().sort('team').rows()}"
    )


def cmd_project(args, venue) -> None:
    tracks = schemas.read(args.match / "tracks.parquet", "tracks")
    state = project_tracks(tracks, venue)
    schemas.write(state, args.match / "state.parquet", "state")
    print(f"project: {len(state)} позиций, из них восстановлено {int(state['interpolated'].sum())}")


def cmd_metrics(args, venue) -> None:
    from aifootball.perception.ball import process_ball_trajectory

    state = schemas.read(args.match / "state.parquet", "state")
    det_path = args.match / "detections.parquet"
    detections = schemas.read(det_path, "detections") if det_path.exists() else None
    ball_state = process_ball_trajectory(detections, venue) if detections is not None else None

    metrics = compute_metrics(state, venue.length_m, venue.width_m, ball_state=ball_state)
    schemas.write_json(metrics, args.match / "metrics.json")
    for team, m in metrics["teams"].items():
        print(f"metrics: команда {team}: {m['distance_m']:.0f} м за {m['observed_s']:.0f} с наблюдения")
    if "possession" in metrics:
        poss = metrics["possession"]["possession_pct"]
        print(f"metrics: владение мячом A: {poss['A']}%, B: {poss['B']}%")


def cmd_check(args, venue) -> bool:
    state = schemas.read(args.match / "state.parquet", "state")
    result = phase1_checks(state, venue.length_m, venue.width_m)
    schemas.write_json(result, args.match / "checks.json")
    print("check:", json.dumps(result, ensure_ascii=False))
    return result["passed"]


def cmd_render(args, venue) -> None:
    from aifootball.viz.debug_video import render_debug_video

    tracks = schemas.read(args.match / "tracks.parquet", "tracks")
    state = schemas.read(args.match / "state.parquet", "state")
    out = args.match / "debug.mp4"
    written = render_debug_video(args.video, tracks, state, venue, out, max_seconds=args.seconds)
    print(f"render: {written} кадров -> {out}")


def cmd_run(args, venue) -> bool:
    if args.redetect or not (args.match / "detections.parquet").exists():
        cmd_detect(args, venue)
    else:
        print("detect: пропущен, detections.parquet уже есть (--redetect, чтобы пересчитать)")
    cmd_track(args, venue)
    cmd_project(args, venue)
    cmd_metrics(args, venue)
    passed = cmd_check(args, venue)
    cmd_render(args, venue)
    return passed


def cmd_eval(args, venue) -> None:
    from aifootball.analytics.validation import (
        evaluate_detections,
        evaluate_projection_error,
        evaluate_tracking,
    )

    results = {}
    if args.gt_detections and args.gt_detections.exists():
        gt_det = schemas.read(args.gt_detections, "detections")
        pred_det = schemas.read(args.match / "detections.parquet", "detections")
        results["detections"] = evaluate_detections(pred_det, gt_det, venue)

    if args.gt_state and args.gt_state.exists():
        gt_state = schemas.read(args.gt_state, "state")
        pred_state = schemas.read(args.match / "state.parquet", "state")
        pred_tracks = schemas.read(args.match / "tracks.parquet", "tracks")
        results["tracking"] = evaluate_tracking(pred_tracks, gt_state)
        results["projection_error"] = evaluate_projection_error(pred_state, gt_state, venue)

    out_path = args.match / "eval.json"
    schemas.write_json(results, out_path)
    print("eval:", json.dumps(results, ensure_ascii=False, indent=2))


def cmd_eval_ball(args, venue) -> None:
    from aifootball.analytics.validation import evaluate_ball

    labels = schemas.read(args.labels, "ball_labels")
    det_path = args.detections or args.match / "detections.parquet"
    detections = schemas.read(det_path, "detections")
    results = [evaluate_ball(detections, labels, venue, conf_min=c) for c in args.conf]
    schemas.write_json({"labels": str(args.labels), "detections": str(det_path), "results": results},
                       args.match / "eval_ball.json")

    first = results[0]
    print(f"eval-ball: мяч виден {first['visible']}, нет в кадре {first['absent']}, не видно {first['hidden']}")
    print("  conf    recall  найдено  ложные(нет в кадре)  precision  recall <6px / 6-10px / >=10px")
    for r in results:
        sizes = " / ".join(f"{b['found']}/{b['visible']}" for b in r["by_size"].values()) if r["by_size"] else "нет гомографии"
        print(f"  {r['conf_min']:<6}  {_fmt(r['recall'])}   {r['found']:>3}/{r['visible']:<3}  "
              f"{r['false_alarm_frames']:>3}/{r['absent']:<3} {_fmt(r['false_alarm_rate'])}       "
              f"{_fmt(r['precision'])}     {sizes}")


def cmd_eval_passes(args, venue) -> None:
    from aifootball.analytics.validation import evaluate_possession
    from aifootball.perception.ball import process_ball_trajectory

    touches = schemas.read(args.touches, "touches")
    state = schemas.read(args.match / "state.parquet", "state")
    ball_state = process_ball_trajectory(schemas.read(args.match / "detections.parquet", "detections"), venue)
    r = evaluate_possession(ball_state, state, touches)
    schemas.write_json({"touches": str(args.touches), **r}, args.match / "eval_passes.json")

    poss, ps = r["possession"], r["passes"]
    print(f"eval-passes: отрезок {r['span_s'][0]:.0f}–{r['span_s'][1]:.0f} с")
    print(f"  владение A/B: эталон {poss['truth_pct']['A']}% / {poss['truth_pct']['B']}%, "
          f"пайплайн {poss['pipeline_pct']['A']}% / {poss['pipeline_pct']['B']}%")
    print("  по времени (с), строки — эталон, столбцы — пайплайн: A / B / никто")
    for g, row in r["possession_by_time_s"].items():
        print(f"    {g:5s} {row['A']:6.1f} {row['B']:6.1f} {row['none']:6.1f}")
    for t in ("A", "B"):
        print(f"  пасы {t}: эталон {ps['truth'][t]['completed']}/{ps['truth'][t]['total']} точных, "
              f"пайплайн {ps['pipeline'][t]['completed']}/{ps['pipeline'][t]['total']}")
    print(f"  совпало пасов {ps['matched']}: recall {_fmt(ps['recall'])}, precision {_fmt(ps['precision'])}, "
          f"точность паса совпала у {ps['completed_agree']}")


def cmd_report(args, venue) -> None:
    from aifootball.analytics.periods import find_halves, parse_halves
    from aifootball.analytics.report_data import build_report
    from aifootball.report.render import image_requests, render_html

    state = schemas.read(args.match / "state.parquet", "state")
    tracks = schemas.read(args.match / "tracks.parquet", "tracks")
    if tracks.is_empty() or state.is_empty():
        raise ValueError("нет обработанных позиций для отчёта")
    import numpy as np
    times = tracks["ts"].unique().sort().to_numpy()
    dt = np.diff(times)
    step = float(np.median(dt[dt > 0])) if np.any(dt > 0) else 1.0 / venue.target_fps
    processed_end = float(times[-1]) + step
    video_s, estimated = _report_video_duration(args, processed_end)
    spans = parse_halves(args.halves, video_s) if args.halves else find_halves(tracks)
    if not spans:
        spans = [(float(times[0]), min(processed_end, video_s))]
    if args.halves and any(end > processed_end + 1e-3 for start, end in spans):
        raise ValueError("тайм выходит за обработанный участок записи")
    spans = [(start, min(end, processed_end, video_s)) for start, end in spans]
    if any(end <= start for start, end in spans):
        raise ValueError("нет обработанного участка внутри таймов")
    ball_state = None
    if args.with_ball:
        from aifootball.perception.ball import process_ball_trajectory

        ball_state = process_ball_trajectory(schemas.read(args.match / "detections.parquet", "detections"), venue)
    names = {"A": args.team_a or "Команда A", "B": args.team_b or "Команда B"}
    data = build_report(state, tracks, venue, spans, names, video_s, ball_state)
    data["match"]["video_duration_estimated"] = estimated
    schemas.write_json(data, args.match / "report.json")

    images = {}
    if args.video:
        from aifootball.report.frames import grab_images

        images = grab_images(args.video, image_requests(data))
    out = args.match / "report.html"
    out.write_text(render_html(data, images), encoding="utf-8")
    halves = " / ".join(f"{s / 60:.1f}–{e / 60:.1f} мин" for s, e in spans)
    print(f"report: таймы {halves}, игроков {len(data['periods'][0]['players'])}, "
          f"картинок {len(images)}, {out.stat().st_size / 1e6:.1f} МБ -> {out}")


def _report_video_duration(args, processed_end: float) -> tuple[float, bool]:
    """Длительность исходника; без источника явно помечаем оценку по артефактам."""
    import math
    import cv2

    meta_path = args.match / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    if not args.video:
        duration = meta.get("video_s")
        if isinstance(duration, (int, float)) and math.isfinite(duration) and duration > 0:
            return float(duration), False
    source = args.video or (Path(meta["video"]) if meta.get("video") else None)
    if source is not None and (args.video or source.exists()):
        cap = cv2.VideoCapture(str(source))
        try:
            fps = cap.get(cv2.CAP_PROP_FPS)
            frames = cap.get(cv2.CAP_PROP_FRAME_COUNT)
            if cap.isOpened() and fps > 0 and frames > 0:
                return frames / fps, False
        finally:
            cap.release()
        if args.video:
            raise ValueError(f"не открывается видео: {source}")
    return processed_end, True


def _fmt(x) -> str:
    return "  —  " if x is None else f"{x:.3f}"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    job = sub.add_parser('process-job', help='Обработать локальное видео по заданию сайта и упаковать результат')
    job.add_argument('--job', type=Path, required=True)
    job.add_argument('--video', type=Path, required=True)
    job.add_argument('--output', type=Path, required=True)
    job.add_argument('--models', type=Path, default=Path('models'))
    job.add_argument('--artifacts', type=Path, help='Повторно упаковать артефакты этого же задания/источника')
    job.add_argument('--partial-recording', action='store_true', help='Исходный файл содержит только фрагмент матча')
    job.add_argument('--halves', help='Интервалы относительно исходного видео: 0:40-21:50,27:10-46:00')

    def add(name, video=False, models=False, seconds=False):
        p = sub.add_parser(name)
        p.add_argument("--venue", type=Path, required=True)
        p.add_argument("--match", type=Path, required=True)
        if video:
            p.add_argument("--video", type=Path, required=True)
        if models:
            p.add_argument("--models", type=Path, default=Path("models"))
        if seconds:
            p.add_argument("--seconds", type=float, default=None, help="отрисовать только начало")
        return p

    add("detect", video=True, models=True)
    add("track")
    add("project")
    add("metrics")
    add("check")
    add("render", video=True, seconds=True)
    ev = add("eval")
    ev.add_argument("--gt-detections", type=Path, default=None, help="эталонные детекции")
    ev.add_argument("--gt-state", type=Path, default=None, help="эталонные траектории")
    evb = add("eval-ball")
    evb.add_argument("--labels", type=Path, required=True, help="ручная разметка мяча (tools.label_ball)")
    evb.add_argument("--detections", type=Path, default=None, help="по умолчанию detections.parquet матча")
    evb.add_argument("--conf", type=float, nargs="+", default=[0.05, 0.10, 0.25], help="пороги уверенности")
    evp = add("eval-passes")
    evp.add_argument("--touches", type=Path, required=True, help="ручной журнал владения (tools.label_touches)")
    rep = add("report")
    rep.add_argument("--video", type=Path, default=None, help="для миниатюр и стоп-кадров")
    rep.add_argument("--halves", default=None, help="таймы вручную: 0:40-21:50,27:10-46:00")
    rep.add_argument("--team-a", default=None)
    rep.add_argument("--team-b", default=None)
    rep.add_argument("--with-ball", action="store_true", help="владение и передачи (приблизительно)")
    run = add("run", video=True, models=True, seconds=True)
    run.add_argument("--redetect", action="store_true")
    return parser


COMMANDS = {
    "detect": cmd_detect, "track": cmd_track, "project": cmd_project, "metrics": cmd_metrics,
    "check": cmd_check, "eval": cmd_eval, "eval-ball": cmd_eval_ball, "eval-passes": cmd_eval_passes,
    "render": cmd_render, "run": cmd_run, "report": cmd_report,
}


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == 'process-job':
        from aifootball.processor.job import process_job
        try:
            process_job(args.job, args.video, args.output, models=args.models, artifacts=args.artifacts, halves=args.halves, partial_recording=args.partial_recording)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        return 0
    venue = load_venue(args.venue)
    result = COMMANDS[args.command](args, venue)
    return 1 if result is False else 0


if __name__ == "__main__":
    sys.exit(main())
