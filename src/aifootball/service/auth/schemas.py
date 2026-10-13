from pydantic import BaseModel, ConfigDict, Field


class Login(BaseModel):
    model_config = ConfigDict(extra='forbid')
    login: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=1024)
