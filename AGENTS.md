# Repository Guidelines

## Project Structure & Module Organization

Nuru Bot is a Python 3.13 Discord bot that connects Discord text, voice, and slash-command events to a local Nuru model service. Runtime code lives in `nuru_bot/`; root `bot.py` and `main.py` are compatibility launchers.

```text
nuru_bot/
  api.py          # Local model, vision, embedding, transcription, and TTS client
  bot.py          # Discord bot factory and package entry point
  commands.py     # Slash command registration
  companion.py    # Prompt, memory, mood, and response orchestration
  config.py       # Environment-driven settings
  events.py       # Discord message and reaction handlers
  memory.py       # SQLite chat memory and embeddings
  state.py        # Persisted mood, persona, and response preferences
  voice.py        # Voice connection, VAD, wake words, recording, and playback
tests/            # Pytest suite and fakes
.env.example      # Configuration template
```

## Build, Test, and Development Commands

Use `uv` for dependency management and local execution.

- `uv sync`: install dependencies from `uv.lock`.
- `uv run python -m nuru_bot`: run the package entry point.
- `uv run python bot.py`: run the legacy launcher.
- `uv run pytest`: run all tests.
- `uv run python -m compileall bot.py main.py nuru_bot tests`: check syntax/importability.
- `uv lock --check`: verify `pyproject.toml` and `uv.lock` are synchronized.
- `uv run nuru-bot-doctor --skip-api`: smoke-test configuration and local bot setup without the Nuru API.

## Coding Style & Naming Conventions

Follow standard Python style with 4-space indentation, `snake_case` functions and variables, `PascalCase` classes, and uppercase constants such as `DEFAULT_API_BASE_URL`. Keep configuration parsing in `nuru_bot/config.py`; add new environment variables to `.env.example` and avoid hardcoded tokens, guild IDs, or channel IDs.

## Testing Guidelines

Tests use `pytest` and are named `tests/test_*.py` with `test_*` functions. Prefer fakes, temporary SQLite paths, and monkeypatched environment variables over live Discord, HTTP, or audio services. Add focused coverage for memory/state persistence, API error handling, event delivery, slash commands, voice runtime behavior, and companion prompt flow.

## Commit & Pull Request Guidelines

Git history uses Conventional Commits, for example `feat: allow response mode preferences to reset` and `fix: tokenize fallback memory embeddings`. Use `feat`, `fix`, `test`, `docs`, `refactor`, or `chore` with an imperative summary.

Pull requests should describe the behavior change, list verification commands, link related issues, and call out new Discord permissions or environment variables. Do not commit `.env`, tokens, local databases, logs, `.venv/`, or generated caches.
