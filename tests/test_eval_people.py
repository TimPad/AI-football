"""Скрипт замера сборки людей: интервал Уилсона, разложенная по похожести выборка пар, оценка порога."""

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest

spec = importlib.util.spec_from_file_location('eval_people', Path('scripts/eval_people.py'))
eval_people = importlib.util.module_from_spec(spec)
sys.modules['eval_people'] = eval_people
spec.loader.exec_module(eval_people)


def test_wilson_interval():
    low, high = eval_people.wilson(72, 75)
    assert low == pytest.approx(0.889, abs=1e-3) and high == pytest.approx(0.986, abs=1e-3)
    assert eval_people.wilson(0, 0) == (0.0, 1.0)


def test_stratified_pairs_cover_every_similarity_band():
    rng = np.random.default_rng(0)
    sims = {(i, i + 1000): float(s) for i, s in enumerate(rng.uniform(0, 1, 500))}
    chosen = eval_people.stratified(sims, n=50, bands=10, seed=1)
    assert len(chosen) == 50 and len(set(chosen)) == 50
    values = sorted(sims[p] for p in chosen)
    assert values[0] < 0.1 and values[-1] > 0.9


def test_auc_and_paired_bootstrap():
    assert eval_people.auc([0.9, 0.8], [0.1, 0.2]) == 1.0
    assert eval_people.auc([0.5], [0.5]) == 0.5
    truth = [True] * 20 + [False] * 20
    good = [0.9] * 20 + [0.1] * 20
    noisy = [0.6, 0.4] * 10 + [0.5] * 20
    low, high = eval_people.paired_bootstrap(truth, good, noisy, n=300)
    assert low > 0


def test_same_rate_by_similarity_is_a_step_function():
    labelled = [(0.1, False), (0.2, False), (0.6, True), (0.7, False), (0.9, True), (0.95, True)]
    p = eval_people.same_rate(labelled, bands=3)
    assert p(0.15) == 0.0 and p(0.65) == 0.5 and p(0.99) == 1.0
