from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pydantic import ValidationError
from rich.console import Console

from undiscord_cli import console as console_module
from undiscord_cli.config import Settings


class SettingsSourceTests(unittest.TestCase):
    def _settings(self, **values: object) -> Settings:
        return Settings(_env_file=None, **values)

    def test_source_precedence_preserves_cli_false_and_zero_overrides(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "auth_token": "json-token",
                        "channel_id": "json-channel",
                        "search_delay": 20,
                        "delete_delay": 30,
                        "dry_run": True,
                        "include_nsfw": True,
                        "unknown_setting": "ignored",
                    }
                ),
                encoding="utf-8",
            )
            dotenv_path = Path(directory) / ".env"
            dotenv_path.write_text(
                "export UNDISCORD_DELETE_DELAY=0\n"
                "UNDISCORD_DRY_RUN=false\n"
                "UNDISCORD_INCLUDE_NSFW=false\n",
                encoding="utf-8",
            )

            with patch.dict(
                os.environ,
                {
                    "undiscord_auth_token": "env-token",
                    "UNDISCORD_CHANNEL_ID": "env-channel",
                },
                clear=True,
            ):
                settings = Settings(
                    config_file=config_path,
                    _env_file=dotenv_path,
                    auth_token="cli-token",
                    channel_id="cli-channel",
                    search_delay=0,
                    dry_run=False,
                )

            self.assertEqual(settings.auth_token, "cli-token")
            self.assertEqual(settings.channel_id, "cli-channel")
            self.assertEqual(settings.search_delay, 0)
            self.assertEqual(settings.delete_delay, 0)
            self.assertFalse(settings.dry_run)
            self.assertFalse(settings.include_nsfw)

    def test_dotenv_supports_export_interpolation_and_case_insensitive_keys(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            dotenv_path = Path(directory) / ".env"
            dotenv_path.write_text(
                'export undiscord_auth_token="${UNDISCORD_SUFFIX}-token"\n'
                "undiscord_channel_id=dotenv-channel\n",
                encoding="utf-8",
            )

            with patch.dict(os.environ, {"UNDISCORD_SUFFIX": "expanded"}, clear=True):
                settings = Settings(_env_file=dotenv_path)

            self.assertEqual(settings.auth_token, "expanded-token")
            self.assertEqual(settings.channel_id, "dotenv-channel")

    def test_config_files_are_instance_specific(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            first_path = Path(directory) / "first.json"
            second_path = Path(directory) / "second.json"
            first_path.write_text(
                json.dumps({"auth_token": "first-token", "channel_id": "first"}),
                encoding="utf-8",
            )
            second_path.write_text(
                json.dumps({"auth_token": "second-token", "channel_id": "second"}),
                encoding="utf-8",
            )

            first = self._settings(config_file=first_path)
            second = self._settings(config_file=second_path)

            self.assertEqual(
                (first.auth_token, first.channel_id), ("first-token", "first")
            )
            self.assertEqual(
                (second.auth_token, second.channel_id), ("second-token", "second")
            )
            self.assertIsNone(first.model_dump().get("config_file"))
            self.assertNotIn("config_file", first.model_dump())

    def test_explicit_config_file_errors_are_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            missing_path = Path(directory) / "missing.json"
            with self.assertRaises(FileNotFoundError):
                self._settings(
                    config_file=missing_path,
                    auth_token="token",
                    channel_id="channel",
                )

            malformed_path = Path(directory) / "malformed.json"
            malformed_path.write_text("{", encoding="utf-8")
            with self.assertRaises(json.JSONDecodeError):
                self._settings(config_file=malformed_path)

            array_path = Path(directory) / "array.json"
            array_path.write_text("[]", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "JSON object"):
                self._settings(config_file=array_path)

    def test_invalid_timing_and_pattern_fail_during_settings_construction(self) -> None:
        for field_name in ("search_delay", "delete_delay"):
            with self.subTest(field_name=field_name):
                with self.assertRaises(ValidationError):
                    self._settings(
                        auth_token="token",
                        channel_id="channel",
                        **{field_name: -1},
                    )

        with self.assertRaises(ValidationError):
            self._settings(
                auth_token="token",
                channel_id="channel",
                pattern="[",
            )

    def test_validation_errors_do_not_expose_credentials_or_empty_values(self) -> None:
        secret = "secret-token-value"
        with self.assertRaises(ValidationError) as context:
            self._settings(auth_token=secret, channel_id="")

        error_text = str(context.exception)
        self.assertNotIn(secret, error_text)
        self.assertNotIn("input_value", error_text)

        with self.assertRaises(ValidationError):
            self._settings(auth_token="", channel_id="channel")


class ConsoleSafetyTests(unittest.TestCase):
    def test_print_config_masks_short_tokens_and_escapes_setting_values(self) -> None:
        secret = "short"
        settings = Settings(
            _env_file=None,
            auth_token=secret,
            channel_id="[red]channel-value[/red]",
            content="[bold]message[/bold]",
        )
        output = io.StringIO()
        captured_console = Console(file=output, color_system=None, width=120)

        with patch.object(console_module, "console", captured_console):
            console_module.print_config(settings)

        rendered = output.getvalue()
        self.assertNotIn(secret, rendered)
        self.assertIn("********", rendered)
        self.assertIn("[red]channel-value[/red]", rendered)
        self.assertIn("[bold]message[/bold]", rendered)


if __name__ == "__main__":
    unittest.main()
