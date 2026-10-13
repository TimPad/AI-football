from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')
    database_url: str
    allowed_origin: str = 'http://127.0.0.1:8000'
    secure_cookies: bool = False
    session_hours: int = 12
    attachment_root: Path = Path('data/service/attachments')
