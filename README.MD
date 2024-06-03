
## Overview
The Undiscord Command Line script allows you to bulk delete messages in a Discord channel or DM (Direct Message) using the Discord API. This script is designed to be run from the command line and supports various filtering options to target specific messages.

## Features
- **Bulk Deletion**: Delete multiple messages in a Discord channel or DM.
- **Filtering**: Filter messages by author ID, content, presence of links or files, date range, and more.
- **Rate Limiting Handling**: Automatically handle Discord API rate limits with retry mechanisms.
- **Configuration File**: Load settings from a JSON configuration file.
- **Logging**: Detailed logging using Python's `logging` module.
- **Graceful Exit**: Handle keyboard interrupts gracefully to stop the script.
- **Fail-Safe Mechanism**: Stop attempting to delete messages from other users if a certain number of consecutive 403 errors are encountered.

## Requirements
- Python 3.x
- `requests` library: Install it using `pip install requests`

## Installation
1. Clone the repository or download the script.
2. Install the required Python library:
   ```sh
   pip install requests
   ```

## Usage
The script can be run from the command line with various options. Below are the available command-line arguments and their descriptions.

### Command-Line Arguments
```sh
usage: undiscord.py [-h] [--author_id AUTHOR_ID] [--content CONTENT] [--has_link] [--has_file] [--min_id MIN_ID] [--max_id MAX_ID] [--include_nsfw] [--include_pinned] [--pattern PATTERN] [--search_delay SEARCH_DELAY] [--delete_delay DELETE_DELAY] [--config CONFIG] auth_token channel_id

Bulk delete messages in a Discord channel or DM.

positional arguments:
  auth_token            Your Discord authorization token
  channel_id            Channel ID where the messages are located

optional arguments:
  -h, --help            show this help message and exit
  --author_id AUTHOR_ID
                        Author ID of the messages you want to delete
  --content CONTENT     Filter messages that contain this text content
  --has_link            Filter messages that contain a link
  --has_file            Filter messages that contain a file
  --min_id MIN_ID       Only delete messages after this ID
  --max_id MAX_ID       Only delete messages before this ID
  --include_nsfw        Include NSFW channels
  --include_pinned      Include pinned messages
  --pattern PATTERN     Only delete messages that match this regex pattern
  --search_delay SEARCH_DELAY
                        Delay between each search request (in milliseconds)
  --delete_delay DELETE_DELAY
                        Delay between each delete request (in milliseconds)
  --config CONFIG       Path to configuration JSON file
```

### Examples
#### Basic Usage
```sh
python undiscord.py YOUR_AUTH_TOKEN YOUR_CHANNEL_ID
```

#### Using Filters
```sh
python undiscord.py YOUR_AUTH_TOKEN YOUR_CHANNEL_ID --author_id YOUR_AUTHOR_ID --content "search text" --has_link --has_file --min_id MIN_ID --max_id MAX_ID --include_nsfw --include_pinned --pattern "regex pattern" --search_delay 30000 --delete_delay 1000
```

#### Using a Configuration File
Create a JSON configuration file (e.g., `config.json`):
```json
{
    "auth_token": "YOUR_AUTH_TOKEN",
    "channel_id": "YOUR_CHANNEL_ID",
    "author_id": "YOUR_AUTHOR_ID",
    "content": "search text",
    "has_link": false,
    "has_file": false,
    "min_id": "MIN_ID",
    "max_id": "MAX_ID",
    "include_nsfw": false,
    "include_pinned": false,
    "pattern": "regex pattern",
    "search_delay": 30000,
    "delete_delay": 1000
}
```

Run the script with the configuration file:
```sh
python undiscord.py --config path/to/config.json
```

## Detailed Description of Arguments
- **auth_token**: Your Discord authorization token. Required.
- **channel_id**: The ID of the channel where the messages are located. Required.
- **--author_id**: The author ID of the messages you want to delete. Optional.
- **--content**: Filter messages that contain this text content. Optional.
- **--has_link**: Filter messages that contain a link. Optional.
- **--has_file**: Filter messages that contain a file. Optional.
- **--min_id**: Only delete messages after this ID. Optional.
- **--max_id**: Only delete messages before this ID. Optional.
- **--include_nsfw**: Include NSFW channels. Optional.
- **--include_pinned**: Include pinned messages. Optional.
- **--pattern**: Only delete messages that match this regex pattern. Optional.
- **--search_delay**: Delay between each search request (in milliseconds). Optional. Default is 30000 ms.
- **--delete_delay**: Delay between each delete request (in milliseconds). Optional. Default is 1000 ms.
- **--config**: Path to a configuration JSON file. Optional.

## Error Handling
- **403 Forbidden**: This error indicates that you do not have permission to delete the message. If the script encounters 5 consecutive 403 errors, it will stop attempting to delete messages from other users and log an error.
- **429 Too Many Requests**: This error indicates rate limiting. The script will wait for the specified retry period and then retry the request.
- **Network Errors**: The script will log network-related errors and continue with the next message.

## Logging
The script uses Python's `logging` module to log detailed information about its execution. Logs include information about successful deletions, failed deletions, and any errors encountered.

## Graceful Exit
The script handles keyboard interrupts (Ctrl+C) gracefully, allowing you to stop the script without abrupt termination.

## Disclaimer
Use this script responsibly and in accordance with Discord's terms of service. The author is not responsible for any misuse of this script.

## License
This project is licensed under the MIT License. See the LICENSE file for details.

## Contributions
Contributions are welcome! Feel free to open issues or submit pull requests on the GitHub repository.

## Support
For support, please open an issue on the GitHub repository.
