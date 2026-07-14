from os import environ
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict, PydanticBaseSettingsSource, TomlConfigSettingsSource


class _CacheConfig(BaseModel):
    backend: Literal["memory", "redis", "memcached", "none"] = "memory"
    endpoint: str | None = None
    port: int | None = None
    db: str | None = None


class _TracingConfig(BaseModel):
    backend: Literal["console", "zipkin", "noop"] = "noop"
    zipkin_address: str | None = None


class _GroupCallSfuConfig(BaseModel):
    enabled: bool = False
    api_url: str = "http://127.0.0.1:3200"
    callback_host: str = "127.0.0.1"
    callback_port: int = 4431
    public_ip: str = "127.0.0.1"
    rtc_port: int = 10000


class _BotApiConfig(BaseModel):
    enabled: bool = True
    host: str = "127.0.0.1"
    port: int = 8081


class _System(BaseModel):
    data_dir: Path = Path("data")
    database_connection_string: str = "sqlite://data/secrets/piltover.db"
    rabbitmq_address: str | None = None
    redis_address: str | None = None
    cache: _CacheConfig
    debug_tracing: _TracingConfig
    group_call_sfu: _GroupCallSfuConfig = _GroupCallSfuConfig()
    bot_api: _BotApiConfig = _BotApiConfig()
    debug_enable_aiomonitor: bool = False
    enable_system_bot: bool = False


class SystemConfig(BaseSettings):
    system: _System = Field(init=False)

    model_config = SettingsConfigDict(toml_file=environ.get("SYSTEM_CONFIG", "config/system.toml"))

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return TomlConfigSettingsSource(settings_cls),


SYSTEM_CONFIG = SystemConfig().system
