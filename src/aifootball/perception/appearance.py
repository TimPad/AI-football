"""Признаки внешности фрагмента для сборки людей (analytics/people.py).

color_feature — без модели: гистограммы HSV (оттенок × насыщенность 12×4 и яркость 4) трёх полос рамки — верх
(15–50% высоты), шорты (50–85%) и обувь (85–100%), по центральным 60% ширины, чтобы меньше брать пол. Корень из
нормированных гистограмм (расстояние Хеллингера) и общая нормировка: косинус — похожесть.

TimmEmbedder — замороженные признаки моделей timm с весами Apache-2.0 (выбор и лицензии — в плане этапа 1 и
документе замера): DINOv2 ViT-S/14 с регистрами и SigLIP 2 ViT-B/16. Вход 112×224 (кратно патчам 14 и 16),
нормировка — из настроек весов, выход — нормированный вектор. Веса лежат в models/hf (в Git не попадают).
"""

from pathlib import Path

import cv2
import numpy as np

BANDS = ((0.15, 0.5), (0.5, 0.85), (0.85, 1.0))
# Признак цвета в пакете результата (track-index.json, поле фрагмента appearance): 156 чисел от 0 до 1,
# по байту на число, base64. Похожесть фрагментов в кабинете — косинус раскодированных признаков.
APPEARANCE_KIND = 'color-hsv-v1'
APPEARANCE_DIMS = 3 * (12 * 4 + 4)
INPUT = (112, 224)  # ширина, высота
# Признак SigLIP 2 фрагмента в пакете (поле embedding): нормированный вектор, по байту со знаком на число, base64.
# По нему кабинет обучает модель матча (docs/superpowers/specs/2026-11-26-identity-queue-design.md).
EMBEDDING_KIND = 'siglip2-b16-int8-v1'
EMBEDDING_DIMS = 768
ENCODERS = {
    'dino': 'vit_small_patch14_reg4_dinov2.lvd142m',
    'siglip': 'vit_base_patch16_siglip_224.v2_webli',
}


def color_feature(crop: np.ndarray) -> np.ndarray:
    h, w = crop.shape[:2]
    hsv = cv2.cvtColor(crop[:, int(w * 0.2) : max(int(w * 0.8), int(w * 0.2) + 1)], cv2.COLOR_BGR2HSV)
    parts = []
    for a, b in BANDS:
        band = hsv[int(h * a) : max(int(h * b), int(h * a) + 1)]
        hs = cv2.calcHist([band], [0, 1], None, [12, 4], [0, 180, 0, 256]).ravel()
        v = cv2.calcHist([band], [2], None, [4], [0, 256]).ravel()
        hist = np.concatenate([hs, v])
        parts.append(np.sqrt(hist / max(float(hist.sum()), 1.0)))
    f = np.concatenate(parts)
    return f / max(float(np.linalg.norm(f)), 1e-9)


def encode(feature: np.ndarray) -> str:
    """Признак цвета (числа 0..1) — по байту на число, base64."""
    import base64

    q = np.clip(np.rint(np.asarray(feature, np.float64) * 255), 0, 255).astype(np.uint8)
    return base64.b64encode(q.tobytes()).decode('ascii')


def decode(text: str) -> np.ndarray:
    """Обратно в нормированный вектор."""
    import base64

    v = np.frombuffer(base64.b64decode(text, validate=True), np.uint8).astype(np.float64) / 255
    return v / max(float(np.linalg.norm(v)), 1e-9)


class TimmEmbedder:
    def __init__(self, kind: str, cache: Path, device: str | None = None):
        import os

        os.environ.setdefault('HF_HUB_CACHE', str(Path(cache).resolve()))
        import timm
        import torch

        from aifootball.perception.detect import pick_device

        self.torch = torch
        self.device = device or pick_device()
        self.model = timm.create_model(ENCODERS[kind], pretrained=True, num_classes=0, dynamic_img_size=True)
        self.model = self.model.eval().to(self.device)
        cfg = self.model.pretrained_cfg
        self.mean = np.array(cfg['mean'], np.float32)
        self.std = np.array(cfg['std'], np.float32)

    def __call__(self, crops: list[np.ndarray]) -> list[np.ndarray]:
        if not crops:
            return []
        batch = []
        for crop in crops:
            rgb = cv2.cvtColor(cv2.resize(crop, INPUT, interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2RGB)
            batch.append(((rgb.astype(np.float32) / 255.0 - self.mean) / self.std).transpose(2, 0, 1))
        x = self.torch.from_numpy(np.stack(batch)).to(self.device)
        with self.torch.no_grad():
            out = self.model(x).float().cpu().numpy()
        return [v / max(float(np.linalg.norm(v)), 1e-9) for v in out]


def encode_embedding(feature: np.ndarray) -> str:
    """Признак SigLIP 2 — по байту со знаком на число, base64. Наибольший модуль — 127: при чтении вектор
    нормируется, а точность выше, чем у умножения нормированного вектора на 127 (косинус 0,9999 против 0,998)."""
    import base64

    v = np.asarray(feature, np.float64)
    q = np.clip(np.rint(v * (127 / max(float(np.abs(v).max()), 1e-9))), -127, 127).astype(np.int8)
    return base64.b64encode(q.tobytes()).decode('ascii')


def decode_embedding(text: str) -> np.ndarray:
    import base64

    v = np.frombuffer(base64.b64decode(text, validate=True), np.int8).astype(np.float64) / 127
    return v / max(float(np.linalg.norm(v)), 1e-9)


def siglip_embedder(models: Path | None):
    """SigLIP 2 из models/hf без скачивания (HF_HUB_OFFLINE); весов нет — None."""
    if models is None:
        return None
    cache = Path(models) / 'hf'
    if not (cache / f'models--timm--{ENCODERS["siglip"]}').exists():
        return None
    import os

    os.environ.setdefault('HF_HUB_OFFLINE', '1')
    return TimmEmbedder('siglip', cache)
