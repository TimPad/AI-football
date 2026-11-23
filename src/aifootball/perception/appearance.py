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
INPUT = (112, 224)  # ширина, высота
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
