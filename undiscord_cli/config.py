from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="UNDISCORD_",
        env_file_encoding="utf-8",
    )

    auth_token: str = Field(repr=False)
    channel_id: str
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
    search_delay: int = 30000
    delete_delay: int = 1000
    dry_run: bool = False

    @classmethod
    def from_config_file(cls, path: str) -> "Settings":
        config_path = Path(path)
        with config_path.open("r", encoding="utf-8") as file:
            raw_config = json.load(file)

        if not isinstance(raw_config, dict):
            raise ValueError("Config file must contain a JSON object.")

        config_values: dict[str, Any] = {
            key: value for key, value in raw_config.items() if key in cls.model_fields
        }

        dotenv_values = cls._read_dotenv_file()

        for field_name in cls.model_fields:
            env_key = f"UNDISCORD_{field_name.upper()}"
            if env_key in os.environ or env_key in dotenv_values:
                config_values.pop(field_name, None)

        return cls(**config_values)

    @classmethod
    def _read_dotenv_file(cls) -> dict[str, str]:
        env_file = cls.model_config.get("env_file")
        if not env_file:
            return {}

        env_path = Path(str(env_file))
        if not env_path.exists():
            return {}

        values: dict[str, str] = {}
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")

        return values
