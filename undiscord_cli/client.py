from __future__ import annotations

import logging
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
        transport = httpx.HTTPTransport(retries=1)
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
        self.last_retry_after_seconds = 1.0

    def __enter__(self) -> "DiscordClient":
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

        params: list[tuple[str, str | int | bool]] = [("offset", offset)]
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
        params.append(("include_nsfw", include_nsfw))

        response = self._request_with_retry(
            "GET",
            f"/channels/{channel_id}/messages/search",
            params=params,
        )
        return response.json()

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def delete_message(self, channel_id: str, message_id: str) -> int:
        if self.dry_run:
            logger.info(
                "Dry run: would delete message %s in channel %s", message_id, channel_id
            )
            self.last_retry_after_seconds = 1.0
            return 204

        response = self._request_with_retry(
            "DELETE",
            f"/channels/{channel_id}/messages/{message_id}",
            raise_for_status=False,
        )
        self._parse_rate_limit(response)
        return response.status_code

    # ------------------------------------------------------------------
    # Rate-limit parsing
    # ------------------------------------------------------------------

    def _parse_rate_limit(self, response: httpx.Response) -> None:
        """Extract retry-after from the response.

        Discord sends the canonical value in the **JSON body** on 429s
        (as a float), and also in the ``Retry-After`` header.  The body
        value is more precise, so prefer it.
        """
        if response.status_code == 429:
            try:
                body = response.json()
                retry = body.get("retry_after")
                if retry is not None:
                    self.last_retry_after_seconds = float(retry)
                    is_global = body.get("global", False)
                    if is_global:
                        logger.warning(
                            "Hit GLOBAL rate limit — waiting %.2fs",
                            self.last_retry_after_seconds,
                        )
                    return
            except Exception:
                pass  # fall through to header

        # Fallback: header value (or sensible default)
        header_val = response.headers.get("Retry-After")
        self.last_retry_after_seconds = float(header_val) if header_val else 1.0

    # ------------------------------------------------------------------
    # Retry helper
    # ------------------------------------------------------------------

    def _request_with_retry(
        self, method: str, url: str, **kwargs: Any
    ) -> httpx.Response:
        raise_for_status = kwargs.pop("raise_for_status", True)

        for retry_count in range(MAX_RETRIES + 1):
            try:
                response = self._client.request(method, url, **kwargs)
                if raise_for_status:
                    response.raise_for_status()
                return response
            except httpx.HTTPStatusError as exc:
                if retry_count >= MAX_RETRIES:
                    logger.error(
                        "HTTP error after %s retries: %s %s returned %s",
                        MAX_RETRIES,
                        method,
                        url,
                        exc.response.status_code,
                    )
                    raise
                backoff = INITIAL_BACKOFF * (2**retry_count)
                logger.warning(
                    "HTTP error on %s %s (status %s). Retrying %s/%s in %.1fs",
                    method,
                    url,
                    exc.response.status_code,
                    retry_count + 1,
                    MAX_RETRIES,
                    backoff,
                )
                time.sleep(backoff)
            except httpx.RequestError as exc:
                if retry_count >= MAX_RETRIES:
                    logger.error(
                        "Request error after %s retries on %s %s: %s",
                        MAX_RETRIES,
                        method,
                        url,
                        exc,
                    )
                    raise
                backoff = INITIAL_BACKOFF * (2**retry_count)
                logger.warning(
                    "Request error on %s %s: %s. Retrying %s/%s in %.1fs",
                    method,
                    url,
                    exc,
                    retry_count + 1,
                    MAX_RETRIES,
                    backoff,
                )
                time.sleep(backoff)

        raise RuntimeError("Retry loop exited unexpectedly.")
