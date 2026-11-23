"""Признаки внешности: цвет верха, шорт и обуви; модели timm — только при скачанных весах."""

import os
from pathlib import Path

import numpy as np
import pytest

from aifootball.perception.appearance import APPEARANCE_DIMS, ENCODERS, TimmEmbedder, color_feature, decode, encode

CACHE = Path('models/hf')


def person(shirt, shorts, shoes, h=200, w=80, seed=0):
    rng = np.random.default_rng(seed)
    image = np.zeros((h, w, 3), np.uint8)
    image[: int(h * 0.5)] = shirt
    image[int(h * 0.5) : int(h * 0.85)] = shorts
    image[int(h * 0.85) :] = shoes
    noise = rng.integers(-8, 9, image.shape)
    return np.clip(image.astype(int) + noise, 0, 255).astype(np.uint8)


def test_color_feature_tells_kits_apart_and_is_normalized():
    red = color_feature(person((30, 30, 200), (20, 20, 20), (250, 250, 250)))
    red2 = color_feature(person((30, 30, 200), (20, 20, 20), (250, 250, 250), seed=1))
    blue_shoes = color_feature(person((30, 30, 200), (20, 20, 20), (200, 60, 30), seed=2))
    orange = color_feature(person((0, 140, 255), (20, 20, 20), (250, 250, 250), seed=3))
    assert np.linalg.norm(red) == pytest.approx(1.0)
    # Отличие в одной полосе из трёх: общая только яркость этой полосы — около (1 + 1 + 0,5) / 3.
    assert red @ red2 > 0.95
    assert red @ blue_shoes < 0.9 and red @ orange < 0.9


@pytest.mark.parametrize('kind', ['dino', 'siglip'])
def test_timm_encoders_embed_crops_to_unit_vectors(kind):
    pytest.importorskip('timm')
    if not any(CACHE.glob(f'models--timm--{ENCODERS[kind].split(".")[0]}*')):
        pytest.skip(f'нет скачанных весов {ENCODERS[kind]} в {CACHE}')
    os.environ['HF_HUB_OFFLINE'] = '1'
    embed = TimmEmbedder(kind, CACHE)
    out = embed([person((30, 30, 200), (20, 20, 20), (250, 250, 250)), person((0, 140, 255), (20, 20, 20), (0, 0, 0))])
    assert len(out) == 2 and all(abs(np.linalg.norm(v) - 1) < 1e-5 for v in out)


def test_color_feature_survives_the_package_encoding():
    a = color_feature(person((30, 30, 200), (20, 20, 20), (250, 250, 250)))
    b = color_feature(person((0, 140, 255), (20, 20, 20), (250, 250, 250), seed=3))
    assert a.size == APPEARANCE_DIMS and len(encode(a)) == 208  # 156 байт в base64
    assert decode(encode(a)) @ a > 0.999
    assert decode(encode(a)) @ decode(encode(b)) == pytest.approx(a @ b, abs=0.01)
