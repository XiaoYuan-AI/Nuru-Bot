# Repository Guidelines

## Project Structure & Module Organization

Nuru Bot is a Python 3.13 Discord bot client for a local Nuru model service. Runtime code is in `nuru_bot/`; root `bot.py` and `main.py` are compatibility launchers.

```text
nuru_bot/
  api.py          # Local model, vision, embeddings, transcription, and TTS client
  bot.py          # Discord bot factory and package entry point
  commands.py     # Slash command registration
  companion.py    # Prompt, memory, mood, and response orchestration
  config.py       # Environment-driven settings
  diagnostics.py  # Offline/API/Discord doctor command
  events.py       # Text and reaction event handlers
  memory.py       # SQLite chat memory with embeddings
  state.py        # Persisted mood, persona, and response preferences
  voice.py        # Voice VAD, wake words, recording, playback, and idle commentary
tests/            # Pytest suite, fakes, and helpers
.env.example      # Configuration template
```

Local runtime state belongs under `data/`, which is ignored by Git.

## Build, Test, and Development Commands

Use `uv` for dependency management and execution.

- `uv sync`: install dependencies from `uv.lock`.
- `uv run python -m nuru_bot`: run the package entry point.
- `uv run python bot.py`: run the legacy launcher.
- `uv run pytest`: run the full test suite.
- `uv run python -m compileall bot.py main.py nuru_bot tests`: check syntax/importability.
- `uv lock --check`: verify `pyproject.toml` and `uv.lock` are synchronized.
- `uv run nuru-bot-doctor --skip-api`: smoke-test configuration without the local API.

## Coding Style & Naming Conventions

Follow standard Python style: 4-space indentation, `snake_case` functions and variables, `PascalCase` classes, and uppercase constants such as `DEFAULT_API_BASE_URL`. Keep config parsing in `nuru_bot/config.py`; add new environment variables to `.env.example`. Never hardcode tokens, guild IDs, channel IDs, or local absolute paths.

## Testing Guidelines

Tests use `pytest` and follow `tests/test_*.py` file names with `test_*` functions. Prefer fakes, temporary SQLite paths, and monkeypatched environment variables over live Discord, HTTP, or audio services. Add focused tests for memory/state persistence, API failures, event delivery, slash commands, voice behavior, and companion prompt flow.

## Commit & Pull Request Guidelines

Git history uses Conventional Commits, such as `feat: expand scoped memory context`, `fix: handle malformed voice recording data`, and `test: cover response preference persistence`. Use an imperative summary with `feat`, `fix`, `test`, `docs`, `refactor`, or `chore`.

Pull requests should describe behavior changes, list verification commands, link related issues, and call out new Discord permissions or environment variables. Do not commit `.env`, tokens, local databases, logs, `.venv/`, or caches.
