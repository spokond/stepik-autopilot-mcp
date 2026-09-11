from typing import Annotated

from pydantic import BaseModel, HttpUrl, UrlConstraints
from pydantic_core import Url
from pydantic_settings import BaseSettings, SettingsConfigDict

SQLiteDsn = Annotated[
    Url,
    UrlConstraints(
        allowed_schemes=[
            "sqlite",
            "sqlite+pysqlite",
            "sqlite+aiosqlite",
        ],
    ),
]


class OAuthSettings(BaseModel):
    client_id: str
    client_secret: str


class StepikSettings(BaseModel):
    base_url: HttpUrl
    oauth: OAuthSettings


class DatabaseSettings(BaseModel):
    url: SQLiteDsn
    echo: bool = False


class Settings(BaseSettings):
    stepik: StepikSettings
    db: DatabaseSettings

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
    )
