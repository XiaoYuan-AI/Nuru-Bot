# Repository Guidelines

## Project Structure & Module Organization

This repository contains a Python Discord bot packaged under `nuru_bot/`.
Root files `bot.py` and `main.py` are compatibility launchers; keep runtime logic
inside the package modules.

- `nuru_bot/bot.py`: Discord client factory and application entry point.
- `nuru_bot/config.py`: environment parsing and default settings.
- `nuru_bot/api.py`: HTTP client for the local Nuru model and vision service.
- `nuru_bot/memory.py`: SQLite long-term memory with stored embeddings.
- `nuru_bot/state.py`: persisted mood, persona, and response preferences.
- `nuru_bot/events.py`: Discord event handlers.
- `nuru_bot/voice.py`: voice-channel connection and recording hooks.
- `.env.example`: documented local configuration template.

Tests live under `tests/` and focus on mock-friendly business logic rather than
live Discord connections.

## Build, Test, and Development Commands

Use `uv` for dependency and environment management.

```powershell
uv sync
uv run python -m nuru_bot
uv run python bot.py
uv run nuru-bot-doctor
uv run pytest
uv run python -m compileall bot.py main.py nuru_bot
uv lock --check
```

`uv sync` installs locked dependencies. `python -m nuru_bot` runs the package
entry point. `nuru-bot-doctor` checks runtime configuration, SQLite storage,
Discord bot construction, FFmpeg, local API contracts, and the companion
pipeline. `pytest` runs the unit tests. `compileall` catches syntax/import-time
issues without logging in to Discord. `uv lock --check` verifies `pyproject.toml`
and `uv.lock` are aligned.

## Coding Style & Naming Conventions

Write Python 3.13-compatible code with 4-space indentation and type hints for
public helpers. Prefer small modules with one clear responsibility. Use
`snake_case` for functions and variables, `PascalCase` for classes, and
uppercase names for constants such as `DEFAULT_API_BASE_URL`.

Keep configuration environment-driven. Do not hardcode new Discord IDs, tokens,
or service URLs outside `nuru_bot/config.py` defaults and `.env.example`.

## Testing Guidelines

Use `pytest` conventions: files named `tests/test_*.py` and test functions named
`test_*`. Mock Discord clients, HTTP calls, and environment variables rather than
requiring network access. At minimum, cover config parsing, API error handling,
memory persistence, state persistence, and prompt-building logic for changed
behavior.

## Commit & Pull Request Guidelines

Use Conventional Commits, matching the current history:

```text
feat: add new user-visible behavior
fix: correct broken behavior
refactor: reorganize code without changing intent
chore: update tooling or metadata
docs: update documentation
```

Pull requests should describe the change, list verification commands run, and
call out any required environment variables or Discord permission changes.

## Security & Configuration Tips

Never commit `.env`, Discord tokens, logs, generated model data, or local virtual
environments. Keep `.env.example` current when adding or renaming configuration
variables.
