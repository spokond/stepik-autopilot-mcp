from pathlib import Path  # noqa: TC003
from typing import Annotated

from pydantic import BaseModel, Field, HttpUrl, SecretStr, UrlConstraints
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
    client_secret: SecretStr


class StepikSettings(BaseModel):
    base_url: HttpUrl
    oauth: OAuthSettings
    requests_per_second: float = Field(default=5.0, gt=0, le=100)
    request_burst: int = Field(default=10, ge=1, le=100)
    max_in_flight: int = Field(default=4, ge=1, le=20)
    ids_batch_size: int = Field(default=30, ge=1, le=30)


class DatabaseSettings(BaseModel):
    url: SQLiteDsn
    echo: bool = False


class Settings(BaseSettings):
    stepik: StepikSettings
    db: DatabaseSettings
    data_dir: Path | None = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
    )
