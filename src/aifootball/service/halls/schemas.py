from typing import Annotated, Literal
from uuid import UUID, uuid4

from pydantic import Field, model_validator

from aifootball.service.tournaments.schemas import Input

Finite = Annotated[float, Field(allow_inf_nan=False)]


class HallFields(Input):
    name: str = Field(min_length=1, max_length=200)
    address: str = Field(min_length=1, max_length=1000)
    pitch_length_m: float = Field(gt=0, le=300, allow_inf_nan=False)
    pitch_width_m: float = Field(gt=0, le=300, allow_inf_nan=False)
    ceiling_height_m: float | None = Field(default=None, gt=0, le=100, allow_inf_nan=False)
    latitude: float | None = Field(default=None, ge=-90, le=90, allow_inf_nan=False)
    longitude: float | None = Field(default=None, ge=-180, le=180, allow_inf_nan=False)
    surface: str = Field(default='', max_length=200)
    description: str = Field(default='', max_length=4000)

    @model_validator(mode='after')
    def paired_location(self):
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError('Укажите широту и долготу вместе')
        return self


class HallCreate(HallFields):
    request_id: UUID = Field(default_factory=uuid4)
    address_selection_token: str | None = Field(default=None, max_length=12000)


class HallUpdate(HallCreate):
    expected_revision: int = Field(ge=0, strict=True)
    archived: bool = False


class ControlPoint(Input):
    px: tuple[Finite, Finite]
    m: tuple[Finite, Finite]


class LensCalibration(Input):
    K: tuple[tuple[Finite, Finite, Finite], tuple[Finite, Finite, Finite], tuple[Finite, Finite, Finite]]
    dist: list[Finite] = Field(min_length=4, max_length=8)

    @model_validator(mode='after')
    def camera_matrix(self):
        if len(self.dist) not in {4, 5, 8} or self.K[0][0] <= 0 or self.K[1][1] <= 0 or self.K[2] != (0, 0, 1):
            raise ValueError('Проверьте матрицу камеры K и коэффициенты дисторсии')
        return self


Fraction = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]


class CameraCreate(Input):
    request_id: UUID = Field(default_factory=uuid4)
    expected_hall_revision: int = Field(ge=0, strict=True)
    name: str = Field(min_length=1, max_length=200)
    frame_width: int = Field(ge=16, le=16384, strict=True)
    frame_height: int = Field(ge=16, le=16384, strict=True)
    points: list[ControlPoint] = Field(min_length=4, max_length=50)
    # fixed — неподвижная камера; ptz — трансляция с оператором: пан и зум, точки — на эталонном кадре.
    motion: Literal['fixed', 'ptz'] = 'fixed'
    pitch_polygon_px: list[tuple[Finite, Finite]] | None = Field(default=None, min_length=3, max_length=50)
    # Графика трансляции поворотной камеры (табло, логотипы): прямоугольники в долях кадра x1, y1, x2, y2.
    overlay: list[tuple[Fraction, Fraction, Fraction, Fraction]] | None = Field(default=None, max_length=20)
    calibration: LensCalibration | None = None

    @model_validator(mode='after')
    def motion_geometry(self):
        if self.motion == 'fixed':
            if self.pitch_polygon_px is None:
                raise ValueError('Отметьте контур поля на кадре')
            if self.overlay is not None:
                raise ValueError('Графика трансляции задаётся только поворотной камере')
            return self
        if self.pitch_polygon_px is not None:
            raise ValueError('У поворотной камеры контур поля не размечается: он строится по точкам')
        if self.calibration is not None:
            raise ValueError('Поворотной камере калибровка объектива не задаётся: зум меняет дисторсию')
        if any(x1 >= x2 or y1 >= y2 for x1, y1, x2, y2 in self.overlay or []):
            raise ValueError('Прямоугольник графики: левый верхний угол левее и выше правого нижнего')
        return self

    def digest_exclude(self):
        """Поля, которых не было в прежних запросах: повтор старого запроса неподвижной камеры даёт тот же хэш."""
        return {'motion', 'overlay'} if self.motion == 'fixed' else set()
