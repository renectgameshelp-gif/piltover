import os
from pathlib import Path
from typing import Self

from pydantic import BaseModel, model_validator, Base64Bytes, Field
from pydantic_settings import BaseSettings, SettingsConfigDict, PydanticBaseSettingsSource, TomlConfigSettingsSource

_ENV_VAR = "GATEWAY_CONFIG"


class _Gateway(BaseModel):
    host: str = "127.0.0.1"
    port: int = 4430
    privkey_file: Path | None = None
    pubkey_file: Path | None = None
    salt_key: Base64Bytes
    # How long to wait for a worker result before sending MsgsAck to the client.
    task_ack_timeout: float = 1.5
    # How long to keep waiting after MsgsAck for most RPC methods.
    task_result_timeout: float = 30.0
    # How long to keep waiting after MsgsAck for uploads and other heavy RPC methods.
    task_result_slow_timeout: float = 600.0

    @model_validator(mode="after")
    def set_default_keys(self) -> Self:
        from .system import SYSTEM_CONFIG

        if self.privkey_file is None:
            self.privkey_file = SYSTEM_CONFIG.data_dir / "secrets/privkey.asc"
        if self.pubkey_file is None:
            self.pubkey_file = SYSTEM_CONFIG.data_dir / "secrets/pubkey.asc"
        return self


class GatewayConfig(BaseSettings):
    gateway: _Gateway = Field(init=False)

    model_config = SettingsConfigDict(toml_file=os.environ.get(_ENV_VAR, "config/gateway.toml"))

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


if _ENV_VAR in os.environ:
    GATEWAY_CONFIG = GatewayConfig().gateway
else:
    GATEWAY_CONFIG = None
