from functools import lru_cache
from pathlib import Path
from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DEBUG: bool = Field(default=False, env="DEBUG")

    # FastAPI
    APP_NAME: str = Field(..., env="APP_NAME")
    APP_VERSION: str = Field(default="1.0.0", env="APP_VERSION")

    # Log Service
    UVICORN_SERVICE_HOST: str = Field(default="0.0.0.0", env="UVICORN_SERVICE_HOST")
    UVICORN_SERVICE_PORT: int = Field(default=8000, env="UVICORN_SERVICE_PORT")
    UVICORN_SERVICE_ENABLED: bool = Field(default=False, env="UVICORN_SERVICE_ENABLED")

    # CORS
    CORS_ORIGINS: str = Field(default="http://localhost:3000,http://localhost:5173", env="CORS_ORIGINS")
    CORS_ALLOW_CREDENTIALS: bool = Field(default=True, env="CORS_ALLOW_CREDENTIALS")
    CORS_ALLOW_METHODS: str = Field(default="*", env="CORS_ALLOW_METHODS")
    CORS_ALLOW_HEADERS: str = Field(default="*", env="CORS_ALLOW_HEADERS")

    # Connection
    TIMEOUT: int = Field(default=30)

    # Proxy (MTProxy)
    PROXY_ENABLED: bool = Field(default=False, env="PROXY_ENABLED")
    PROXY_SERVER: str = Field(default=None, env="PROXY_SERVER")
    PROXY_PORT: int = Field(default=None, env="PROXY_PORT")
    PROXY_SECRET: str = Field(default=None, env="PROXY_SECRET")

    # Account Manager (Telegram API)
    API_ID: int = Field(..., env="API_ID")
    API_HASH: str = Field(..., env="API_HASH")
    APP_ID: int = Field(..., env="APP_ID")
    APP_TITLE: str = Field(..., env="APP_TITLE")
    APP_SHORTNAME: str = Field(..., env="APP_SHORTNAME")

    # Account auth
    SESSION_NAME: str = Field(default=None, env="SESSION_NAME")
    PHONE_NUMBER: str = Field(default=None, env="PHONE_NUMBER")

    # System info
    SYSTEM_VERSION: str = Field(default="Windows 11", env="SYSTEM_VERSION")
    DEVICE_MODEL: str = Field(default="Desktop", env="DEVICE_MODEL")

    MANAGERS_PATH: Path = Path(__file__).parents[2] / "storage" / "managers"
    PATTERN_PATH: Path = Path(__file__).parents[2] / "storage" / "patterns"
    QR_PATH: Path = Path(__file__).parents[2] / "storage" / "qr"
    SESSIONS_PATH: Path = Path(__file__).parents[2] / "storage" / "sessions"
    USERS_PATH: Path = Path(__file__).parents[2] / "storage" / "users"

    # Channels (comma-separated IDs)
    CHANNEL_IDS: str = Field(default="", env="CHANNELS_IDS")

    @property
    def channel_ids_list(self) -> List[int]:
        """Возвращает список ID каналов как integers."""
        if not self.CHANNEL_IDS or self.CHANNEL_IDS.strip() == "":
            return []
        return [int(x.strip()) for x in self.CHANNEL_IDS.split(",") if x.strip().isdigit()]

    @property
    def cors_origins_list(self) -> List[str]:
        """Возвращает список разрешенных CORS origins."""
        if not self.CORS_ORIGINS or self.CORS_ORIGINS.strip() == "":
            return []
        return [x.strip() for x in self.CORS_ORIGINS.split(",") if x.strip()]

    @property
    def cors_methods_list(self) -> List[str]:
        """Возвращает список разрешенных CORS методов."""
        if self.CORS_ALLOW_METHODS == "*":
            return ["*"]
        return [x.strip() for x in self.CORS_ALLOW_METHODS.split(",") if x.strip()]

    @property
    def cors_headers_list(self) -> List[str]:
        """Возвращает список разрешенных CORS заголовков."""
        if self.CORS_ALLOW_HEADERS == "*":
            return ["*"]
        return [x.strip() for x in self.CORS_ALLOW_HEADERS.split(",") if x.strip()]

    model_config = SettingsConfigDict(
        env_file=Path(__file__).parents[2] / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """Получить настройки (кэшируется)"""
    return Settings()


def check_config():
    from src.core import get_logger

    logger = get_logger()
    settings = get_settings()

    logger.debug(
        "\nSettings\n"
        f"  DEBUG: {settings.DEBUG}\n"
        f"  API_ID={settings.API_ID}\n"
        f"  API_HASH={settings.API_HASH}\n"
        f"  APP_ID={settings.APP_ID}\n"
        f"  APP_TITLE={settings.APP_TITLE}\n"
        f"  APP_SHORTNAME={settings.APP_SHORTNAME}\n"
        f"  SYSTEM_VERSION={settings.SYSTEM_VERSION}\n"
        f"  DEVICE_MODEL={settings.DEVICE_MODEL}\n"
        f"  SESSIONS_PATH={settings.SESSIONS_PATH}\n"
        f"  QR_PATH={settings.QR_PATH}\n"
        f"  CHANNEL_IDS={settings.CHANNEL_IDS}\n"
        f"  SESSION_NAME={settings.SESSION_NAME}\n"
        f"  PHONE_NUMBER={settings.PHONE_NUMBER}"
    )
