import requests
import argparse
import time
import re
import json
import logging
from datetime import datetime
from requests.exceptions import RequestException, HTTPError

# Constants
DISCORD_API_BASE_URL = "https://discord.com/api/v9"
MAX_CONSECUTIVE_403_ERRORS = 5  # Maximum number of consecutive 403 errors before stopping

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def to_snowflake(date_str):
    # Convert date to Discord snowflake ID
    date = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
    return str(int((date.timestamp() * 1000 - 1420070400000) * 4194304))

def delete_message(auth_token, channel_id, message_id):
    url = f"{DISCORD_API_BASE_URL}/channels/{channel_id}/messages/{message_id}"
    headers = {
        "Authorization": auth_token,
    }
    response = requests.delete(url, headers=headers)
    return response

def search_messages(auth_token, channel_id, author_id=None, content=None, has_link=False, has_file=False, min_id=None, max_id=None, include_nsfw=False, offset=0):
    url = f"{DISCORD_API_BASE_URL}/channels/{channel_id}/messages/search"
    params = {
        "author_id": author_id,
        "content": content,
        "has": "link" if has_link else None,
        "has": "file" if has_file else None,
        "min_id": min_id,
        "max_id": max_id,
        "include_nsfw": include_nsfw,
        "offset": offset,
    }
    headers = {
        "Authorization": auth_token,
    }
    response = requests.get(url, headers=headers, params=params)
    if response.status_code == 200:
        return response.json()
    else:
        response.raise_for_status()

def delete_messages(auth_token, channel_id, author_id=None, content=None, has_link=False, has_file=False, min_id=None, max_id=None, include_nsfw=False, include_pinned=False, pattern=None, search_delay=30000, delete_delay=1000):
    offset = 0
    total_deleted = 0
    total_failed = 0
    consecutive_403_errors = 0

    while True:
        try:
            messages = search_messages(auth_token, channel_id, author_id, content, has_link, has_file, min_id, max_id, include_nsfw, offset)
        except RequestException as e:
            logger.error(f"Error searching messages: {e}")
            break

        if not messages.get("messages"):
            logger.info("No more messages found.")
            break

        for message_group in messages["messages"]:
            for message in message_group:
                if not include_pinned and message.get("pinned"):
                    continue
                if pattern and not re.search(pattern, message["content"], re.IGNORECASE):
                    continue
                try:
                    response = delete_message(auth_token, channel_id, message["id"])
                    if response.status_code == 429:
                        retry_after = int(response.headers.get("Retry-After", 1))
                        logger.warning(f"Rate limited. Retrying after {retry_after} seconds.")
                        time.sleep(retry_after)
                        response = delete_message(auth_token, channel_id, message["id"])
                    if response.status_code == 204:
                        logger.info(f"Deleted message {message['id']}")
                        total_deleted += 1
                        consecutive_403_errors = 0  # Reset consecutive 403 errors counter
                    elif response.status_code == 403:
                        logger.warning(f"Failed to delete message {message['id']} with status code 403 (Forbidden). You might not have permission to delete this message.")
                        total_failed += 1
                        consecutive_403_errors += 1
                        if consecutive_403_errors >= MAX_CONSECUTIVE_403_ERRORS:
                            logger.error(f"Encountered {MAX_CONSECUTIVE_403_ERRORS} consecutive 403 errors. Stopping further attempts to delete messages from other users.")
                            return
                    else:
                        logger.error(f"Failed to delete message {message['id']} with status code {response.status_code}")
                        total_failed += 1
                except RequestException as e:
                    logger.error(f"Error deleting message {message['id']}: {e}")
                    total_failed += 1
                time.sleep(delete_delay / 1000.0)

        offset += len(messages["messages"])
        logger.info(f"Progress: {total_deleted} messages deleted, {total_failed} messages failed.")
        time.sleep(search_delay / 1000.0)

def load_config(config_file):
    with open(config_file, 'r') as file:
        config = json.load(file)
    return config

def main():
    parser = argparse.ArgumentParser(description="Bulk delete messages in a Discord channel or DM.")
    parser.add_argument("auth_token", help="Your Discord authorization token")
    parser.add_argument("channel_id", help="Channel ID where the messages are located")
    parser.add_argument("--author_id", help="Author ID of the messages you want to delete", default=None)
    parser.add_argument("--content", help="Filter messages that contain this text content", default=None)
    parser.add_argument("--has_link", action="store_true", help="Filter messages that contain a link", default=False)
    parser.add_argument("--has_file", action="store_true", help="Filter messages that contain a file", default=False)
    parser.add_argument("--min_id", help="Only delete messages after this ID", default=None)
    parser.add_argument("--max_id", help="Only delete messages before this ID", default=None)
    parser.add_argument("--include_nsfw", action="store_true", help="Include NSFW channels", default=False)
    parser.add_argument("--include_pinned", action="store_true", help="Include pinned messages", default=False)
    parser.add_argument("--pattern", help="Only delete messages that match this regex pattern", default=None)
    parser.add_argument("--search_delay", type=int, default=30000, help="Delay between each search request (in milliseconds)")
    parser.add_argument("--delete_delay", type=int, default=1000, help="Delay between each delete request (in milliseconds)")
    parser.add_argument("--config", help="Path to configuration JSON file", default=None)

    args = parser.parse_args()

    if args.config:
        config = load_config(args.config)
        args.auth_token = config.get("auth_token", args.auth_token)
        args.channel_id = config.get("channel_id", args.channel_id)
        args.author_id = config.get("author_id", args.author_id)
        args.content = config.get("content", args.content)
        args.has_link = config.get("has_link", args.has_link)
        args.has_file = config.get("has_file", args.has_file)
        args.min_id = config.get("min_id", args.min_id)
        args.max_id = config.get("max_id", args.max_id)
        args.include_nsfw = config.get("include_nsfw", args.include_nsfw)
        args.include_pinned = config.get("include_pinned", args.include_pinned)
        args.pattern = config.get("pattern", args.pattern)
        args.search_delay = config.get("search_delay", args.search_delay)
        args.delete_delay = config.get("delete_delay", args.delete_delay)

    try:
        delete_messages(
            auth_token=args.auth_token,
            channel_id=args.channel_id,
            author_id=args.author_id,
            content=args.content,
            has_link=args.has_link,
            has_file=args.has_file,
            min_id=args.min_id,
            max_id=args.max_id,
            include_nsfw=args.include_nsfw,
            include_pinned=args.include_pinned,
            pattern=args.pattern,
            search_delay=args.search_delay,
            delete_delay=args.delete_delay,
        )
    except KeyboardInterrupt:
        logger.info("Script interrupted by user. Exiting...")

if __name__ == "__main__":
    main()