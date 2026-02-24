Core development commands:
- uv sync
- uv run undiscord --help
- uv run undiscord --channel <CHANNEL_ID> --guild-id <GUILD_ID> --author-id <AUTHOR_ID> --yes
- uv run undiscord --channel <CHANNEL_ID> --author-id <AUTHOR_ID> --yes  # auto-detect guild context
- uv run undiscord --dry-run --yes
- uv run python -m undiscord_cli --help
- uv run python main.py --help
- uv build

Useful git/system commands on Darwin:
- git status
- git diff
- git log --oneline -10
- ls -la
- grep -R "pattern" .
- find . -name "*.py"