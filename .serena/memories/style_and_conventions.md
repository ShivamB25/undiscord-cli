Conventions:
- Use Python type hints broadly; modern annotations style.
- Keep HTTP/network behavior in client.py, not cli.py.
- Keep CLI orchestration and user flow in cli.py.
- Keep output/formatting concerns in console.py only.
- Config precedence: CLI args > env vars (.env/UNDISCORD_*) > defaults.
- Avoid leaking auth token; masked display only.
- Preserve 403 safety stop and 429/rate-limit handling.
- Preserve snowflake windowing behavior for Discord search offset cap (~9975).
- Package manager is uv; avoid ad-hoc pip workflows in repo docs and automation.