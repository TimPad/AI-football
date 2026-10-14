from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')
    database_url: str = Field(repr=False)
    allowed_origin: str = 'http://127.0.0.1:8000'
    secure_cookies: bool = False
    session_hours: int = 12
    attachment_root: Path = Path('data/service/attachments')
    analysis_zip_limit: int = 100 * 1024 * 1024
    analysis_unpacked_limit: int = 300 * 1024 * 1024
    analysis_file_limit: int = 2048
    analysis_json_limit: int = 64 * 1024 * 1024
    analysis_thumb_limit: int = 2 * 1024 * 1024
