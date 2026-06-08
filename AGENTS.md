# Repository Guidelines

## Project Structure & Module Organization

Nuru Bot is a Python 3.13 Discord bot client for a local Nuru model service. Core package code lives in `nuru_bot/`; root `bot.py` and `main.py` are compatibility launchers.

```text
nuru_bot/
  api.py          # Local model, embeddings, transcription, and TTS client
  bot.py          # Discord client factory and package entry point
  commands.py     # Slash command registration
  companion.py    # Prompt, memory, mood, and response orchestration
  config.py       # Environment-driven settings
  diagnostics.py  # Doctor command and runtime checks
  events.py       # Discord text/reaction handlers
  memory.py       # SQLite long-term memory
  state.py        # Mood, persona, and response preferences
  voice.py        # Voice VAD, wake words, recording, playback, idle comments
tests/            # Pytest suite, fakes, and helpers
.env.example      # Configuration template
```

Keep local runtime files in `data/`; it is ignored by Git.

## Build, Test, and Development Commands

Use `uv` for dependency management and execution.

- `uv sync`: install dependencies from `uv.lock`.
- `uv run python -m nuru_bot`: run the package entry point.
- `uv run python bot.py`: run the legacy launcher.
- `uv run pytest`: run the full test suite.
- `uv run python -m compileall bot.py main.py nuru_bot tests`: check syntax.
- `uv lock --check`: confirm lockfile consistency.
- `uv run nuru-bot-doctor --skip-api`: smoke-test local configuration without the model API.

## Coding Style & Naming Conventions

Use standard Python style: 4-space indentation, `snake_case` functions and variables, `PascalCase` classes, and uppercase constants such as `DEFAULT_API_BASE_URL`. Keep configuration parsing in `nuru_bot/config.py`, and add new variables to `.env.example`. Never hardcode tokens, guild IDs, channel IDs, or absolute local paths.

## Testing Guidelines

Tests use `pytest` and follow `tests/test_*.py` file names with `test_*` functions. Prefer fakes, temporary SQLite paths, and monkeypatched environment variables over live Discord, HTTP, or audio services. Add focused tests for memory/state persistence, API failures, slash commands, voice behavior, and companion prompt flow.

## Commit & Pull Request Guidelines

History uses Conventional Commits, for example `fix: reject invalid api response objects` and `docs: document vtuber runtime configuration`. Use imperative summaries with types such as `feat`, `fix`, `test`, `docs`, `refactor`, or `chore`.

Pull requests should describe behavior changes, list verification commands, link related issues, and call out new Discord permissions or environment variables. Do not commit `.env`, tokens, local databases, logs, `.venv/`, or caches.
