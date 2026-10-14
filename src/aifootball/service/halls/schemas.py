from typing import Annotated
from uuid import UUID,uuid4
from pydantic import Field,model_validator
from aifootball.service.tournaments.schemas import Input

Finite=Annotated[float,Field(allow_inf_nan=False)]


class HallFields(Input):
    name:str=Field(min_length=1,max_length=200)
    address:str=Field(min_length=1,max_length=1000)
    pitch_length_m:float=Field(gt=0,le=300,allow_inf_nan=False)
    pitch_width_m:float=Field(gt=0,le=300,allow_inf_nan=False)
    ceiling_height_m:float|None=Field(default=None,gt=0,le=100,allow_inf_nan=False)
    latitude:float|None=Field(default=None,ge=-90,le=90,allow_inf_nan=False)
    longitude:float|None=Field(default=None,ge=-180,le=180,allow_inf_nan=False)
    surface:str=Field(default='',max_length=200)
    description:str=Field(default='',max_length=4000)

    @model_validator(mode='after')
    def paired_location(self):
        if (self.latitude is None)!=(self.longitude is None):
            raise ValueError('Укажите широту и долготу вместе')
        return self


class HallCreate(HallFields):
    request_id:UUID=Field(default_factory=uuid4)


class HallUpdate(HallCreate):
    expected_revision:int=Field(ge=0,strict=True)
    archived:bool=False


class ControlPoint(Input):
    px:tuple[Finite,Finite]
    m:tuple[Finite,Finite]


class LensCalibration(Input):
    K:tuple[tuple[Finite,Finite,Finite],tuple[Finite,Finite,Finite],tuple[Finite,Finite,Finite]]
    dist:list[Finite]=Field(min_length=4,max_length=8)

    @model_validator(mode='after')
    def camera_matrix(self):
        if len(self.dist) not in {4,5,8} or self.K[0][0]<=0 or self.K[1][1]<=0 or self.K[2]!=(0,0,1):
            raise ValueError('Проверьте матрицу камеры K и коэффициенты дисторсии')
        return self


class CameraCreate(Input):
    request_id:UUID=Field(default_factory=uuid4)
    expected_hall_revision:int=Field(ge=0,strict=True)
    name:str=Field(min_length=1,max_length=200)
    frame_width:int=Field(ge=16,le=16384,strict=True)
    frame_height:int=Field(ge=16,le=16384,strict=True)
    points:list[ControlPoint]=Field(min_length=4,max_length=50)
    pitch_polygon_px:list[tuple[Finite,Finite]]=Field(min_length=3,max_length=50)
    calibration:LensCalibration|None=None
