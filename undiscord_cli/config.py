from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, override

from pydantic import Field, field_validator
from pydantic_settings import (
    BaseSettings,
    InitSettingsSource,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="UNDISCORD_",
        env_file_encoding="utf-8",
        case_sensitive=False,
        hide_input_in_errors=True,
    )

    config_file: Path | None = Field(default=None, exclude=True, repr=False)
    auth_token: str = Field(min_length=1, repr=False)
    channel_id: str = Field(min_length=1)
    guild_id: str | None = None
    author_id: str | None = None
    content: str | None = None
    has_link: bool = False
    has_file: bool = False
    min_id: str | None = None
    max_id: str | None = None
    include_nsfw: bool = False
    include_pinned: bool = False
    pattern: str | None = None
    search_delay: int = Field(default=30000, ge=0)
    delete_delay: int = Field(default=1000, ge=0)
    dry_run: bool = False

    @field_validator("pattern")
    @classmethod
    def validate_pattern(cls, value: str | None) -> str | None:
        if value is not None:
            try:
                re.compile(value)
            except re.error as exc:
                raise ValueError("pattern must be a valid regular expression") from exc
        return value

    @classmethod
    @override
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        config_file = init_settings().get("config_file")
        filtered_json_config: dict[str, Any] = {}

        if config_file is not None:
            with Path(config_file).open("r", encoding="utf-8") as file:
                raw_config = json.load(file)

            if not isinstance(raw_config, dict):
                raise ValueError("Config file must contain a JSON object.")

            filtered_json_config = {
                key: value
                for key, value in raw_config.items()
                if key in settings_cls.model_fields and key != "config_file"
            }

        return (
            init_settings,
            env_settings,
            dotenv_settings,
            file_secret_settings,
            InitSettingsSource(settings_cls, filtered_json_config),
        )
