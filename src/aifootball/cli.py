"""Пайплайн по шагам. Каждый шаг читает артефакт предыдущего из каталога матча.

    python -m aifootball.cli run     --video V --venue DIR --match DIR   # всё подряд
    python -m aifootball.cli detect  --video V --venue DIR --match DIR   # минуты
    python -m aifootball.cli track   --venue DIR --match DIR             # секунды
    python -m aifootball.cli project --venue DIR --match DIR
    python -m aifootball.cli metrics --venue DIR --match DIR
    python -m aifootball.cli check   --venue DIR --match DIR
    python -m aifootball.cli render  --video V --venue DIR --match DIR [--seconds 60]
    python -m aifootball.cli eval-ball --venue DIR --match DIR --labels data/gt/<матч>/ball.parquet
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
from aifootball.perception.teams import assign_roles, assign_teams
from aifootball.perception.track import track_people
from aifootball.state.project import project_tracks
from aifootball.venue import load_venue


def cmd_detect(args, venue) -> None:
    from aifootball.perception.detect import detect_video  # тянет torch — только здесь

    started = time.perf_counter()
    detections = detect_video(args.video, venue, args.models / venue.model)
    schemas.write(detections, args.match / "detections.parquet", "detections")
    schemas.write_json(
        {
            "video": str(args.video),
            "venue_id": venue.venue_id,
            "src_fps": video_fps(args.video),
            "target_fps": venue.target_fps,
            "model": venue.model,
            "imgsz": venue.imgsz,
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
    from aifootball.perception.stitch import stitch_tracks

    detections = schemas.read(args.match / "detections.parquet", "detections")
    raw_tracks = track_people(detections, venue)
    stitched_tracks = stitch_tracks(raw_tracks, max_gap_s=venue.max_gap_s * 5.0)
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
        results["detections"] = evaluate_detections(pred_det, gt_det)

    if args.gt_state and args.gt_state.exists():
        gt_state = schemas.read(args.gt_state, "state")
        pred_state = schemas.read(args.match / "state.parquet", "state")
        pred_tracks = schemas.read(args.match / "tracks.parquet", "tracks")
        results["tracking"] = evaluate_tracking(pred_tracks, gt_state)
        results["projection_error"] = evaluate_projection_error(pred_state, gt_state, venue.width_m)

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
        sizes = " / ".join(f"{b['found']}/{b['visible']}" for b in r["by_size"].values())
        print(f"  {r['conf_min']:<6}  {_fmt(r['recall'])}   {r['found']:>3}/{r['visible']:<3}  "
              f"{r['false_alarm_frames']:>3}/{r['absent']:<3} {_fmt(r['false_alarm_rate'])}       "
              f"{_fmt(r['precision'])}     {sizes}")


def _fmt(x) -> str:
    return "  —  " if x is None else f"{x:.3f}"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

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
    run = add("run", video=True, models=True, seconds=True)
    run.add_argument("--redetect", action="store_true")
    return parser


COMMANDS = {
    "detect": cmd_detect, "track": cmd_track, "project": cmd_project, "metrics": cmd_metrics,
    "check": cmd_check, "eval": cmd_eval, "eval-ball": cmd_eval_ball, "render": cmd_render, "run": cmd_run,
}


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    venue = load_venue(args.venue)
    result = COMMANDS[args.command](args, venue)
    return 1 if result is False else 0


if __name__ == "__main__":
    sys.exit(main())
