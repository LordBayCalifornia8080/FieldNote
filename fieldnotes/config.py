from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FN_", env_file=".env", extra="ignore")

    database_path: Path = Path("fieldnotes.db")
    cookie_secure: bool = False
    site_name: str = Field(default="Fieldnotes", min_length=1, max_length=80)
    session_hours: int = Field(default=12, ge=1, le=168)
    login_limit: int = Field(default=20, ge=2, le=100)


@lru_cache
def get_settings():
    return Settings()
