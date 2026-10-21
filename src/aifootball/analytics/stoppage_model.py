"""Остановки игры по секундам: логистическая регрессия по признакам CV поверх Витерби (events.viterbi_stoppages).

Признаки секунды s считаются в окне WINDOW_S с центром s + 0.5:
  speed_p50, speed_p80, speed_spread — скорость полевых в долях медианы матча (не зависит от уровня игры);
  player_edge_m — 2-й процентиль расстояния полевых до ближайшей линии (кто-то стоит у линии на вводе);
  ball_seen — доля кадров окна, где мяч найден детектором, а не дорисован интерполяцией;
  ball_speed — медиана скорости мяча по таким кадрам; ball_edge_m — его минимальное расстояние до линии;
  viterbi — секунда наполовину или больше внутри отрезка Витерби.
Без траектории мяча — отдельная модель без признаков мяча.

Коэффициенты — scripts/fit_stoppage_model.py по журналам касаний; проверка — на зале, которого не было в обучении.
"""
import numpy as np
import polars as pl

TEAMS = ("A", "B")
WINDOW_S = 3.0
MIN_ROWS = 10             # меньше строк полевых в окне — секунду не оцениваем (считаем игрой)
MIN_MATCH_SPEED_MS = 0.3  # медиана ниже — скоростей нет (синтетика, статичная запись), остановки не ищем
NO_BALL_EDGE_M = 3.0      # «мяч у линии», когда мяча в окне нет
THRESHOLD = 0.5
FEATURES = ("speed_p50", "speed_p80", "speed_spread", "player_edge_m", "ball_seen", "ball_speed", "ball_edge_m", "viterbi")

# scripts/fit_stoppage_model.py, 2026-10-19. Обучение: Ярославль 2020, 1:00–4:00 и 10:00–13:00 (307 с, 17 остановок).
# Проверка: Ярославль 2023, другой зал и камера (315 с, 18 остановок) — верно 0.82 (P 0.85, R 0.80, 17/18 остановок),
# без мяча 0.77; один Витерби 0.66 (13/18). На старом зале Витерби 0.71, классификатор 0.86 (в выборке).
WITH_BALL = {"features": FEATURES,
             "mean": [1.0194, 1.705, 0.8812, 0.7843, 0.5615, 3.0017, 1.5023, 0.2085],
             "std": [0.3648, 0.541, 0.25, 0.8242, 0.2866, 2.6098, 2.1722, 0.4062],
             "weights": [-0.1991, -1.45, 0.5021, 0.0338, -0.9295, -0.677, -0.3826, 0.6285], "bias": 0.0962}
NO_BALL = {"features": ("speed_p50", "speed_p80", "speed_spread", "player_edge_m", "viterbi"),
           "mean": [1.0194, 1.705, 0.8812, 0.7843, 0.2085],
           "std": [0.3648, 0.541, 0.25, 0.8242, 0.4062],
           "weights": [-0.059, -1.5904, 0.5603, -0.1225, 0.8037], "bias": 0.1506}


def _edge(x: np.ndarray, y: np.ndarray, length_m: float, width_m: float) -> np.ndarray:
    return np.minimum.reduce([x, length_m - x, y, width_m - y])


def second_features(players: pl.DataFrame, ball: pl.DataFrame | None, length_m: float, width_m: float,
                    viterbi: list[tuple[float, float]]) -> dict[int, list[float]]:
    """Секунда -> значения FEATURES. Секунды без полевых в окне пропускаются."""
    if "speed" not in players.columns:
        return {}
    field = players.filter((pl.col("role") == "player") & pl.col("team").is_in(TEAMS) & pl.col("speed").is_finite())
    if field.is_empty():
        return {}
    norm = float(field["speed"].median())
    if norm < MIN_MATCH_SPEED_MS:
        return {}
    ts_f = field["ts"].to_numpy()
    sp_f = field["speed"].to_numpy() / norm
    edge_f = _edge(field["x_m"].to_numpy(), field["y_m"].to_numpy(), length_m, width_m)
    frames = np.unique(players["ts"].to_numpy())
    if ball is not None and not ball.is_empty():
        seen = ball.filter(~pl.col("interpolated")) if "interpolated" in ball.columns else ball
        ts_b = seen["ts"].to_numpy()
        sp_b = seen["speed"].to_numpy() if "speed" in seen.columns else np.zeros(len(ts_b))
        edge_b = _edge(seen["x_m"].to_numpy(), seen["y_m"].to_numpy(), length_m, width_m)
    else:
        ts_b = sp_b = edge_b = np.zeros(0)
    half = WINDOW_S / 2
    out = {}
    for s in range(int(np.floor(ts_f.min())), int(np.floor(ts_f.max())) + 1):
        c = s + 0.5
        m = (ts_f >= c - half) & (ts_f < c + half)
        if m.sum() < MIN_ROWS:
            continue
        mb = (ts_b >= c - half) & (ts_b < c + half)
        n_frames = max(1, int(((frames >= c - half) & (frames < c + half)).sum()))
        covered = sum(max(0.0, min(b, s + 1) - max(a, s)) for a, b in viterbi)
        sp = sp_f[m]
        out[s] = [float(np.median(sp)), float(np.quantile(sp, 0.8)), float(np.std(sp)), float(np.quantile(edge_f[m], 0.02)),
                  min(1.0, mb.sum() / n_frames), float(np.median(sp_b[mb])) if mb.any() else 0.0,
                  float(np.min(edge_b[mb])) if mb.any() else NO_BALL_EDGE_M, float(covered >= 0.5)]
    return out


def stoppage_probability(features: dict[int, list[float]], model: dict) -> dict[int, float]:
    """Секунда -> вероятность остановки по логистической модели (признаки берутся по model['features'])."""
    if not features:
        return {}
    idx = [FEATURES.index(name) for name in model["features"]]
    seconds = sorted(features)
    X = np.array([[features[s][i] for i in idx] for s in seconds])
    z = (X - np.array(model["mean"])) / np.array(model["std"]) @ np.array(model["weights"]) + model["bias"]
    return dict(zip(seconds, (1 / (1 + np.exp(-z))).tolist()))


def stoppage_spans(players: pl.DataFrame, ball: pl.DataFrame | None, length_m: float, width_m: float,
                   viterbi: list[tuple[float, float]], model: dict | None = None) -> list[tuple[float, float]]:
    """Отрезки остановок [начало, конец] с точностью до секунды: подряд идущие секунды склеиваются."""
    if model is None:
        model = WITH_BALL if ball is not None and not ball.is_empty() else NO_BALL
    prob = stoppage_probability(second_features(players, ball, length_m, width_m, viterbi), model)
    spans: list[tuple[float, float]] = []
    for s in sorted(s for s, p in prob.items() if p >= THRESHOLD):
        if spans and spans[-1][1] == s:
            spans[-1] = (spans[-1][0], float(s + 1))
        else:
            spans.append((float(s), float(s + 1)))
    return spans
