from dataclasses import dataclass
from pathlib import Path
from typing import Literal


@dataclass(frozen=True)
class FrameAsset:
    id: str
    frame_id: int
    video_ms: int
    path: Path
    sha256: str
    crop: tuple[int,int,int,int] | None


@dataclass(frozen=True)
class MediaAsset:
    id: str
    kind: Literal['video','audio']
    path: Path
    sha256: str
    start_ms: int
    end_ms: int
    has_audio: bool


@dataclass(frozen=True)
class Window:
    id: str
    start_ms: int
    end_ms: int
    frames: tuple[FrameAsset,...]
    media: MediaAsset | None
    track_ids: tuple[int,...]
    mode: Literal['frames','native']


@dataclass(frozen=True)
class InferenceResult:
    document: dict
    usage: dict | None
    request_id: str | None
    response_model: str
