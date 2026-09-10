from __future__ import annotations

import logging
import math
import time
from datetime import datetime
from typing import Any

import httpx

DISCORD_API_BASE_URL = "https://discord.com/api/v9"
MAX_RETRIES = 3
INITIAL_BACKOFF = 1.0
MAX_CONSECUTIVE_403 = 5
MAX_SEARCH_OFFSET = 9975

# Mimic a standard browser User-Agent to avoid Cloudflare blocks on raw
# library UAs like "python-httpx/0.28".  This is the same string the
# Discord desktop client sends (Electron / Chromium based).
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/128.0.6613.186 Safari/537.36"
)

logger = logging.getLogger(__name__)


def to_snowflake(date_str: str) -> str:
    """Convert a datetime string to a Discord snowflake ID."""
    date = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
    return str(int((date.timestamp() * 1000 - 1420070400000) * 4194304))


class DiscordClient:
    def __init__(self, auth_token: str, dry_run: bool = False) -> None:
        # Keep retries in the explicit request policy below.  HTTPX's native
        # transport retry would otherwise retry connection failures twice.
        transport = httpx.HTTPTransport()
        self._client = httpx.Client(
            base_url=DISCORD_API_BASE_URL,
            headers={
                "Authorization": auth_token,
                "User-Agent": _USER_AGENT,
                "Content-Type": "application/json",
            },
            timeout=httpx.Timeout(30.0, connect=10.0),
            transport=transport,
        )
        self.dry_run = dry_run

    def __enter__(self) -> DiscordClient:
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

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
    ) -> dict[str, Any]:
        # Discord hard-caps search offset at 9975.
        if offset > MAX_SEARCH_OFFSET:
            logger.warning(
                "Offset %s exceeds Discord maximum (%s). Clamping.",
                offset,
                MAX_SEARCH_OFFSET,
            )
            offset = MAX_SEARCH_OFFSET

        params: list[tuple[str, str | int | float | bool | None]] = [
            ("sort_by", "timestamp"),
            ("sort_order", "desc"),
            ("offset", offset),
        ]
        path = f"/channels/{channel_id}/messages/search"
        if guild_id is not None and guild_id != "@me":
            path = f"/guilds/{guild_id}/messages/search"
            params.append(("channel_id", channel_id))

        if author_id is not None:
            params.append(("author_id", author_id))
        if content is not None:
            params.append(("content", content))
        if has_link:
            params.append(("has", "link"))
        if has_file:
            params.append(("has", "file"))
        if min_id is not None:
            params.append(("min_id", min_id))
        if max_id is not None:
            params.append(("max_id", max_id))
        if include_nsfw:
            params.append(("include_nsfw", "true"))

        response = self._request_with_retry(
            "GET",
            path,
            params=params,
            retry_search_index=True,
        )
        return response.json()

    def get_channel(self, channel_id: str) -> dict[str, Any]:
        response = self._request_with_retry("GET", f"/channels/{channel_id}")
        return response.json()

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def delete_message(self, channel_id: str, message_id: str) -> int:
        if self.dry_run:
            logger.info(
                "Dry run: would delete message %s in channel %s", message_id, channel_id
            )
            return 204

        response = self._request_with_retry(
            "DELETE",
            f"/channels/{channel_id}/messages/{message_id}",
            raise_for_status=False,
        )
        return response.status_code

    # ------------------------------------------------------------------
    # Retry helper
    # ------------------------------------------------------------------

    @staticmethod
    def _coerce_retry_after(value: object) -> float | None:
        """Return a finite, non-negative delay or ``None`` for bad input."""
        if isinstance(value, bool) or not isinstance(value, (str, int, float)):
            return None

        try:
            delay = float(value)
        except TypeError, ValueError, OverflowError:
            return None

        if not math.isfinite(delay) or delay < 0:
            return None
        return delay

    @classmethod
    def _retry_after_seconds(cls, response: httpx.Response) -> float | None:
        """Read Discord's JSON retry delay, falling back to its header."""
        try:
            body = response.json()
        except ValueError:
            body = None

        if isinstance(body, dict):
            delay = cls._coerce_retry_after(body.get("retry_after"))
            if delay is not None:
                return delay

        return cls._coerce_retry_after(response.headers.get("Retry-After"))

    @classmethod
    def _retry_delay(
        cls,
        response: httpx.Response | None,
        retry_count: int,
        *,
        search_indexing: bool = False,
    ) -> float:
        retry_after: float | None = None
        if response is not None and response.status_code in (202, 429):
            retry_after = cls._retry_after_seconds(response)
        delay = (
            retry_after
            if retry_after is not None
            else float(INITIAL_BACKOFF * (2**retry_count))
        )

        # A zero delay is valid for rate limits, but a zero-delay indexing
        # response would busy-loop while Discord is still building the index.
        if search_indexing:
            return max(delay, 0.1)
        return delay

    def _request_with_retry(
        self,
        method: str,
        url: str,
        *,
        raise_for_status: bool = True,
        retry_search_index: bool = False,
        params: list[tuple[str, str | int | float | bool | None]] | None = None,
    ) -> httpx.Response:
        for retry_count in range(MAX_RETRIES + 1):
            try:
                response = self._client.request(method, url, params=params)
                response.raise_for_status()
            except (httpx.HTTPStatusError, httpx.RequestError) as exc:
                if isinstance(exc, httpx.HTTPStatusError):
                    response = exc.response
                    status_code = response.status_code
                    retry_reason = f"HTTP status {status_code}"
                    if not (status_code == 429 or 500 <= status_code < 600):
                        if raise_for_status:
                            raise
                        return response

                    delay = self._retry_delay(response, retry_count)
                    if retry_count >= MAX_RETRIES:
                        # Keep a final 429 cooldown even when this operation
                        # cannot retry further, so a later request does not
                        # violate the limit.
                        if status_code == 429:
                            time.sleep(delay)
                        if raise_for_status:
                            raise
                        return response
                else:
                    if retry_count >= MAX_RETRIES:
                        logger.error(
                            "Request error after %s retries on %s %s (%s)",
                            MAX_RETRIES,
                            method,
                            url,
                            type(exc).__name__,
                        )
                        raise

                    delay = self._retry_delay(None, retry_count)
                    retry_reason = f"request error ({type(exc).__name__})"

                logger.warning(
                    "Retrying %s %s after %s (%s/%s) in %.1fs",
                    method,
                    url,
                    retry_reason,
                    retry_count + 1,
                    MAX_RETRIES,
                    delay,
                )
                time.sleep(delay)
                continue

            if retry_search_index and response.status_code == 202:
                if retry_count >= MAX_RETRIES:
                    raise httpx.HTTPStatusError(
                        f"Discord message search index was not ready after {MAX_RETRIES} retries",
                        request=response.request,
                        response=response,
                    )

                delay = self._retry_delay(
                    response,
                    retry_count,
                    search_indexing=True,
                )
                logger.warning(
                    "Message search index is pending on %s %s. Retrying %s/%s in %.1fs",
                    method,
                    url,
                    retry_count + 1,
                    MAX_RETRIES,
                    delay,
                )
                time.sleep(delay)
                continue

            return response

        raise RuntimeError("Retry loop exited unexpectedly.")
