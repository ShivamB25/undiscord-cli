from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import call, patch

import httpx
from typer.testing import CliRunner

from undiscord_cli import cli
from undiscord_cli.client import MAX_CONSECUTIVE_403
from undiscord_cli.config import Settings

CHANNEL_ID = "111111111111111111"
GUILD_ID = "222222222222222222"


class FakeProgress:
    def __init__(self) -> None:
        self.updates: list[dict[str, object]] = []
        self.stopped = False

    def __enter__(self) -> FakeProgress:
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None

    def add_task(self, *args, **kwargs) -> int:
        return 1

    def update(self, task_id: int, **fields: object) -> None:
        self.updates.append(fields)

    def stop_task(self, task_id: int) -> None:
        self.stopped = True


class FakeSearchService:
    def __init__(
        self,
        messages: list[dict[str, object]],
        *,
        page_size: int = 2,
        statuses: dict[str, int] | None = None,
        remove_on_delete: bool = True,
    ) -> None:
        self.records = {str(message["id"]): dict(message) for message in messages}
        self.page_size = page_size
        self.statuses = statuses or {}
        self.remove_on_delete = remove_on_delete
        self.search_calls: list[dict[str, object]] = []
        self.delete_calls: list[tuple[str, str]] = []

    def __enter__(self) -> FakeSearchService:
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None

    def search_messages(
        self,
        channel_id: str,
        *,
        guild_id: str | None,
        author_id: str | None,
        content: str | None,
        has_link: bool,
        has_file: bool,
        min_id: str | None,
        max_id: str | None,
        include_nsfw: bool,
        offset: int,
    ) -> dict[str, object]:
        self.search_calls.append(
            {
                "channel_id": channel_id,
                "guild_id": guild_id,
                "author_id": author_id,
                "content": content,
                "has_link": has_link,
                "has_file": has_file,
                "min_id": min_id,
                "max_id": max_id,
                "include_nsfw": include_nsfw,
                "offset": offset,
            }
        )
        min_value = int(min_id) if min_id is not None else None
        max_value = int(max_id) if max_id is not None else None
        messages = [
            message
            for message in self.records.values()
            if (min_value is None or int(message["id"]) > min_value)
            and (max_value is None or int(message["id"]) < max_value)
        ]
        messages.sort(key=lambda message: int(message["id"]), reverse=True)
        page = messages[: self.page_size]
        return {"messages": [[dict(message) for message in page]]}

    def delete_message(self, channel_id: str, message_id: str) -> int:
        message_key = str(message_id)
        self.delete_calls.append((channel_id, message_key))
        status = self.statuses.get(message_key, 204)
        if status == 204 and self.remove_on_delete:
            self.records.pop(message_key, None)
        return status


class ContextPagingService(FakeSearchService):
    def __init__(self) -> None:
        super().__init__([])
        self.pages: dict[str | None, list[dict[str, object]]] = {
            None: [
                {"id": "8", "channel_id": CHANNEL_ID},
                {"id": "5", "hit": False, "channel_id": "other"},
                {"id": "8", "channel_id": CHANNEL_ID},
                {"id": "4", "channel_id": "other"},
            ],
            "8": [
                {"id": "7", "channel_id": CHANNEL_ID},
                {"id": "6", "channel_id": CHANNEL_ID},
            ],
            "6": [],
        }

    def search_messages(self, channel_id: str, **kwargs) -> dict[str, object]:
        max_id = kwargs["max_id"]
        self.search_calls.append({"channel_id": channel_id, **kwargs})
        page = self.pages.get(max_id, [])
        return (
            {"messages": [[dict(message) for message in page]]}
            if page
            else {"messages": []}
        )


class NonAdvancingService(FakeSearchService):
    def __init__(self) -> None:
        super().__init__([])

    def search_messages(self, channel_id: str, **kwargs) -> dict[str, object]:
        self.search_calls.append({"channel_id": channel_id, **kwargs})
        return {"messages": [[{"id": "9", "channel_id": CHANNEL_ID}]]}


class FailingSearchService(FakeSearchService):
    def __init__(self) -> None:
        super().__init__([])

    def search_messages(self, channel_id: str, **kwargs) -> dict[str, object]:
        raise httpx.RequestError(
            "super-secret-token",
            request=httpx.Request("GET", "https://discord.test/search"),
        )


class CliRegressionTests(unittest.TestCase):
    def settings(self, **overrides: object) -> Settings:
        values: dict[str, object] = {
            "config_file": None,
            "auth_token": "auth-token",
            "channel_id": CHANNEL_ID,
            "guild_id": GUILD_ID,
            "author_id": None,
            "content": None,
            "has_link": False,
            "has_file": False,
            "min_id": None,
            "max_id": None,
            "include_nsfw": False,
            "include_pinned": False,
            "pattern": None,
            "search_delay": 0,
            "delete_delay": 17,
            "dry_run": False,
        }
        values.update(overrides)
        return Settings(**values)

    def run_loop(
        self, service: FakeSearchService, settings: Settings
    ) -> tuple[tuple[int, int, int], FakeProgress, object]:
        progress = FakeProgress()
        with (
            patch.object(cli, "create_progress", return_value=progress),
            patch.object(cli.time, "sleep") as sleep,
        ):
            result = cli._delete_messages(service, settings)
        return result, progress, sleep

    def test_shrinking_search_pages_are_fully_processed(self) -> None:
        service = FakeSearchService(
            [
                {"id": str(message_id), "channel_id": CHANNEL_ID}
                for message_id in [4, 3, 2, 1]
            ]
        )

        result, _, _ = self.run_loop(service, self.settings())

        self.assertEqual((4, 0, 0), result)
        self.assertEqual(
            ["4", "3", "2", "1"], [call[1] for call in service.delete_calls]
        )
        self.assertEqual(
            [None, "3", "1"], [call["max_id"] for call in service.search_calls]
        )
        self.assertTrue(all(call["offset"] == 0 for call in service.search_calls))

    def test_dry_run_and_pinned_messages_keep_paging_without_delete_pacing(
        self,
    ) -> None:
        service = FakeSearchService(
            [
                {"id": "4", "channel_id": CHANNEL_ID, "pinned": True},
                {"id": "3", "channel_id": CHANNEL_ID},
                {"id": "2", "channel_id": CHANNEL_ID},
            ],
            remove_on_delete=False,
        )

        result, _, sleep = self.run_loop(
            service, self.settings(dry_run=True, include_pinned=False)
        )

        self.assertEqual((2, 0, 1), result)
        self.assertEqual(["3", "2"], [call[1] for call in service.delete_calls])
        sleep.assert_not_called()

    def test_context_and_duplicate_ids_do_not_advance_or_repeat_deletes(self) -> None:
        service = ContextPagingService()

        result, _, _ = self.run_loop(service, self.settings())

        self.assertEqual((3, 0, 0), result)
        self.assertEqual(["8", "7", "6"], [call[1] for call in service.delete_calls])
        self.assertEqual(
            [None, "8", "6"], [call["max_id"] for call in service.search_calls]
        )

    def test_non_advancing_cursor_terminates(self) -> None:
        service = NonAdvancingService()

        with self.assertRaises(RuntimeError):
            self.run_loop(service, self.settings())

        self.assertEqual(2, len(service.search_calls))
        self.assertEqual(["9"], [call[1] for call in service.delete_calls])

    def test_delete_delay_applies_once_to_success_and_failure(self) -> None:
        success_service = FakeSearchService([{"id": "2", "channel_id": CHANNEL_ID}])
        success_result, _, success_sleep = self.run_loop(
            success_service, self.settings()
        )

        failure_service = FakeSearchService(
            [{"id": "2", "channel_id": CHANNEL_ID}], statuses={"2": 500}
        )
        failure_result, _, failure_sleep = self.run_loop(
            failure_service, self.settings()
        )

        self.assertEqual((1, 0, 0), success_result)
        self.assertEqual((0, 1, 0), failure_result)
        success_sleep.assert_has_calls([call(0.017)])
        failure_sleep.assert_has_calls([call(0.017)])
        self.assertEqual(1, success_sleep.call_count)
        self.assertEqual(1, failure_sleep.call_count)

    def test_forbidden_safety_stop_is_bounded_and_updates_progress(self) -> None:
        service = FakeSearchService(
            [
                {"id": str(message_id), "channel_id": CHANNEL_ID}
                for message_id in range(MAX_CONSECUTIVE_403 + 2, 0, -1)
            ],
            page_size=MAX_CONSECUTIVE_403 + 2,
            statuses={
                str(message_id): 403
                for message_id in range(MAX_CONSECUTIVE_403 + 2, 0, -1)
            },
            remove_on_delete=False,
        )
        result, progress, _ = self.run_loop(service, self.settings())

        self.assertEqual((0, MAX_CONSECUTIVE_403, 0), result)
        self.assertEqual(MAX_CONSECUTIVE_403, len(service.delete_calls))
        self.assertEqual(MAX_CONSECUTIVE_403, progress.updates[-1]["failed"])
        self.assertTrue(progress.stopped)

    def test_cli_json_values_are_overridden_by_cli_and_negative_boolean_is_preserved(
        self,
    ) -> None:
        runner = CliRunner()
        service = FakeSearchService([])
        constructor_args: list[tuple[str, bool]] = []

        def build_client(token: str, dry_run: bool) -> FakeSearchService:
            constructor_args.append((token, dry_run))
            return service

        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "auth_token": "json-secret-token",
                        "channel_id": "333333333333333333",
                        "guild_id": "@me",
                        "has_link": True,
                        "dry_run": False,
                        "search_delay": 0,
                        "delete_delay": 0,
                    }
                ),
                encoding="utf-8",
            )
            with (
                patch.dict(os.environ, {}, clear=True),
                patch.object(cli, "DiscordClient", side_effect=build_client),
            ):
                result = runner.invoke(
                    cli.app,
                    [
                        "--config",
                        str(config_path),
                        "--token",
                        "cli-secret-token",
                        "--channel",
                        CHANNEL_ID,
                        "--no-has-link",
                        "--dry-run",
                        "--yes",
                    ],
                )

        self.assertEqual(0, result.exit_code)
        self.assertEqual([("cli-secret-token", True)], constructor_args)
        self.assertEqual(
            False,
            service.search_calls[0]["has_link"] if service.search_calls else False,
        )
        self.assertNotIn("cli-secret-token", result.output)
        self.assertNotIn("json-secret-token", result.output)

    def test_cli_search_failure_is_nonzero_and_token_safe(self) -> None:
        runner = CliRunner()
        service = FailingSearchService()

        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(cli, "DiscordClient", return_value=service),
        ):
            result = runner.invoke(
                cli.app,
                [
                    "--token",
                    "super-secret-token",
                    "--channel",
                    CHANNEL_ID,
                    "--guild-id",
                    "@me",
                    "--search-delay",
                    "0",
                    "--yes",
                ],
            )

        self.assertNotEqual(0, result.exit_code)
        self.assertNotIn("super-secret-token", result.output)
        self.assertIn("network error", result.output.lower())

    def test_cli_failed_delete_is_nonzero(self) -> None:
        runner = CliRunner()
        service = FakeSearchService(
            [{"id": "2", "channel_id": CHANNEL_ID}], statuses={"2": 500}
        )

        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(cli, "DiscordClient", return_value=service),
        ):
            result = runner.invoke(
                cli.app,
                [
                    "--token",
                    "super-secret-token",
                    "--channel",
                    CHANNEL_ID,
                    "--guild-id",
                    "@me",
                    "--search-delay",
                    "0",
                    "--delete-delay",
                    "0",
                    "--yes",
                ],
            )

        self.assertNotEqual(0, result.exit_code)
        self.assertNotIn("super-secret-token", result.output)

    def test_invalid_config_error_does_not_echo_input_values(self) -> None:
        runner = CliRunner()
        secret = "malformed-json-secret-token"

        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "config.json"
            config_path.write_text(
                '{"auth_token": "malformed-json-secret-token",',
                encoding="utf-8",
            )
            with patch.dict(os.environ, {}, clear=True):
                result = runner.invoke(cli.app, ["--config", str(config_path)])

        self.assertNotEqual(0, result.exit_code)
        self.assertNotIn(secret, result.output)
        self.assertIn("configuration error", result.output.lower())


if __name__ == "__main__":
    unittest.main()
