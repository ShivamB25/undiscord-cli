from __future__ import annotations

import unittest
from typing import Any
from unittest.mock import call, patch

import httpx

from undiscord_cli.client import (
    DISCORD_API_BASE_URL,
    MAX_RETRIES,
    DiscordClient,
)


class DiscordClientTests(unittest.TestCase):
    def _client_for(
        self,
        outcomes: list[tuple[int, dict[str, Any]] | BaseException],
        *,
        dry_run: bool = False,
    ) -> tuple[DiscordClient, list[httpx.Request]]:
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            outcome = outcomes[len(requests) - 1]
            if isinstance(outcome, BaseException):
                raise outcome
            status_code, response_kwargs = outcome
            return httpx.Response(status_code, request=request, **response_kwargs)

        client = DiscordClient("test-token", dry_run=dry_run)
        client._client.close()
        client._client = httpx.Client(
            base_url=DISCORD_API_BASE_URL,
            transport=httpx.MockTransport(handler),
        )
        self.addCleanup(client.close)
        return client, requests

    def test_get_429_honors_json_delay_before_recovery(self) -> None:
        client, requests = self._client_for(
            [
                (
                    429,
                    {
                        "json": {"retry_after": 3.5},
                        "headers": {"Retry-After": "9"},
                    },
                ),
                (200, {"json": {"guild_id": "guild-1"}}),
            ]
        )

        with patch("undiscord_cli.client.time.sleep") as sleep:
            result = client.get_channel("channel-1")

        self.assertEqual(result, {"guild_id": "guild-1"})
        self.assertEqual(len(requests), 2)
        self.assertEqual(sleep.call_args_list, [call(3.5)])

    def test_delete_429_honors_json_delay_before_recovery(self) -> None:
        client, requests = self._client_for(
            [
                (
                    429,
                    {
                        "json": {"retry_after": 2.25},
                        "headers": {"Retry-After": "9"},
                    },
                ),
                (204, {}),
            ]
        )

        with patch("undiscord_cli.client.time.sleep") as sleep:
            status_code = client.delete_message("channel-1", "message-1")

        self.assertEqual(status_code, 204)
        self.assertEqual(len(requests), 2)
        self.assertEqual(sleep.call_args_list, [call(2.25)])

    def test_final_delete_429_returns_status_after_cooldown(self) -> None:
        client, requests = self._client_for(
            [
                (
                    429,
                    {"json": {"retry_after": 3.5}},
                )
                for _ in range(MAX_RETRIES + 1)
            ]
        )

        with patch("undiscord_cli.client.time.sleep") as sleep:
            status_code = client.delete_message("channel-1", "message-1")

        self.assertEqual(status_code, 429)
        self.assertEqual(len(requests), MAX_RETRIES + 1)
        self.assertEqual(sleep.call_args_list, [call(3.5)] * (MAX_RETRIES + 1))

    def test_malformed_rate_limit_delays_fall_back_to_exponential_backoff(self) -> None:
        malformed_values: list[object] = [[1], True, "NaN", "Infinity"]

        for malformed_value in malformed_values:
            with self.subTest(malformed_value=malformed_value):
                client, requests = self._client_for(
                    [
                        (
                            429,
                            {
                                "json": {"retry_after": malformed_value},
                                "headers": {"Retry-After": "not-a-delay"},
                            },
                        ),
                        (200, {"json": {"guild_id": "guild-1"}}),
                    ]
                )

                with patch("undiscord_cli.client.time.sleep") as sleep:
                    self.assertEqual(
                        client.get_channel("channel-1"), {"guild_id": "guild-1"}
                    )

                self.assertEqual(len(requests), 2)
                self.assertEqual(sleep.call_args_list, [call(1.0)])

    def test_transient_5xx_and_network_error_recover(self) -> None:
        client, requests = self._client_for(
            [
                (503, {}),
                httpx.ConnectError("temporary connection failure"),
                (200, {"json": {"guild_id": "guild-1"}}),
            ]
        )

        with patch("undiscord_cli.client.time.sleep") as sleep:
            result = client.get_channel("channel-1")

        self.assertEqual(result, {"guild_id": "guild-1"})
        self.assertEqual(len(requests), 3)
        self.assertEqual(sleep.call_args_list, [call(1.0), call(2.0)])

    def test_get_5xx_exhaustion_is_bounded_and_raises(self) -> None:
        client, requests = self._client_for([(503, {}) for _ in range(MAX_RETRIES + 1)])

        with patch("undiscord_cli.client.time.sleep") as sleep:
            with self.assertRaises(httpx.HTTPStatusError) as raised:
                client.get_channel("channel-1")

        self.assertEqual(raised.exception.response.status_code, 503)
        self.assertEqual(len(requests), MAX_RETRIES + 1)
        self.assertEqual(
            sleep.call_args_list,
            [call(1.0), call(2.0), call(4.0)],
        )

    def test_permanent_statuses_are_not_retried(self) -> None:
        for status_code in (400, 401, 403, 404):
            with self.subTest(status_code=status_code):
                client, requests = self._client_for([(status_code, {})])

                with patch("undiscord_cli.client.time.sleep") as sleep:
                    with self.assertRaises(httpx.HTTPStatusError):
                        client.get_channel("channel-1")

                self.assertEqual(len(requests), 1)
                sleep.assert_not_called()

                client, requests = self._client_for([(status_code, {})])
                with patch("undiscord_cli.client.time.sleep") as sleep:
                    result = client.delete_message("channel-1", "message-1")

                self.assertEqual(result, status_code)
                self.assertEqual(len(requests), 1)
                sleep.assert_not_called()

    def test_search_202_retries_until_index_is_ready(self) -> None:
        client, requests = self._client_for(
            [
                (202, {"json": {"retry_after": 0}}),
                (200, {"json": {"messages": [], "total_results": 0}}),
            ]
        )

        with patch("undiscord_cli.client.time.sleep") as sleep:
            result = client.search_messages(
                "channel-1",
                guild_id="guild-1",
                author_id=None,
                content=None,
                has_link=False,
                has_file=False,
                min_id=None,
                max_id=None,
                include_nsfw=False,
                offset=0,
            )

        self.assertEqual(result, {"messages": [], "total_results": 0})
        self.assertEqual(len(requests), 2)
        self.assertEqual(sleep.call_args_list, [call(0.1)])

    def test_search_202_exhaustion_raises_explicit_error(self) -> None:
        client, requests = self._client_for(
            [(202, {"json": {"retry_after": 1.0}}) for _ in range(MAX_RETRIES + 1)]
        )

        with patch("undiscord_cli.client.time.sleep") as sleep:
            with self.assertRaises(httpx.HTTPStatusError) as raised:
                client.search_messages(
                    "channel-1",
                    guild_id="guild-1",
                    author_id=None,
                    content=None,
                    has_link=False,
                    has_file=False,
                    min_id=None,
                    max_id=None,
                    include_nsfw=False,
                    offset=0,
                )

        self.assertEqual(raised.exception.response.status_code, 202)
        self.assertIn("index was not ready", str(raised.exception))
        self.assertEqual(len(requests), MAX_RETRIES + 1)
        self.assertEqual(sleep.call_args_list, [call(1.0)] * MAX_RETRIES)

    def test_search_routes_guild_and_dm_requests_with_filters(self) -> None:
        client, requests = self._client_for(
            [
                (200, {"json": {"messages": []}}),
                (200, {"json": {"messages": []}}),
            ]
        )

        kwargs = {
            "author_id": "author-1",
            "content": "hello world",
            "has_link": True,
            "has_file": True,
            "min_id": "100",
            "max_id": "200",
            "include_nsfw": True,
            "offset": 7,
        }
        client.search_messages("channel-1", guild_id="guild-1", **kwargs)
        client.search_messages("channel-1", guild_id="@me", **kwargs)

        guild_request, dm_request = requests
        self.assertEqual(
            guild_request.url.path,
            "/api/v9/guilds/guild-1/messages/search",
        )
        self.assertEqual(
            dm_request.url.path,
            "/api/v9/channels/channel-1/messages/search",
        )
        self.assertEqual(guild_request.url.params["channel_id"], "channel-1")
        self.assertNotIn("channel_id", dm_request.url.params)
        self.assertEqual(guild_request.url.params.get_list("has"), ["link", "file"])
        self.assertEqual(dm_request.url.params.get_list("has"), ["link", "file"])
        for request in (guild_request, dm_request):
            self.assertEqual(request.url.params["sort_by"], "timestamp")
            self.assertEqual(request.url.params["sort_order"], "desc")
            self.assertEqual(request.url.params["offset"], "7")
            self.assertEqual(request.url.params["author_id"], "author-1")
            self.assertEqual(request.url.params["content"], "hello world")
            self.assertEqual(request.url.params["min_id"], "100")
            self.assertEqual(request.url.params["max_id"], "200")
            self.assertEqual(request.url.params["include_nsfw"], "true")

    def test_dry_run_does_not_issue_delete_request(self) -> None:
        client, requests = self._client_for([], dry_run=True)

        with patch("undiscord_cli.client.time.sleep"):
            status_code = client.delete_message("channel-1", "message-1")

        self.assertEqual(status_code, 204)
        self.assertEqual(requests, [])
        self.assertFalse(hasattr(client, "last_retry_after_seconds"))


if __name__ == "__main__":
    unittest.main()
