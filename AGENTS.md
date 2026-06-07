# Repository Guidelines

## Project Structure & Module Organization

Nuru Bot is a Python 3.13 Discord bot packaged in `nuru_bot/`. Keep runtime
logic in package modules; the root `bot.py` and `main.py` files are compatibility
launchers only.

```text
nuru_bot/
  api.py          # Local Nuru HTTP client
  bot.py          # Discord bot factory and entry point
  commands.py     # Slash command registration
  companion.py    # Prompt, memory, and response orchestration
  config.py       # Environment-driven settings
  events.py       # Discord event handlers
  memory.py       # SQLite chat memory and embeddings
  state.py        # Persisted mood, persona, preferences
  voice.py        # Voice, recording, VAD, and TTS flow
tests/            # Pytest unit tests and fakes
.env.example      # Local configuration template
```

No committed asset directory is required today; add one only when fixtures or
media are needed by tests or docs.

## Build, Test, and Development Commands

Use `uv` for dependency and command execution.

- `uv sync`: install locked dependencies.
- `uv run python -m nuru_bot`: run the package entry point.
- `uv run python bot.py`: run the legacy launcher.
- `uv run pytest`: execute the test suite.
- `uv run python -m compileall bot.py main.py nuru_bot tests`: catch syntax and import errors.
- `uv lock --check`: verify `pyproject.toml` and `uv.lock` are synchronized.
- `uv run nuru-bot-doctor`: run local diagnostics for config, storage, bot setup, API, and audio tooling.

## Coding Style & Naming Conventions

Use 4-space indentation, type hints for public helpers, and small modules with a
single responsibility. Use `snake_case` for functions, variables, and modules;
`PascalCase` for classes; and uppercase names for constants such as
`DEFAULT_API_BASE_URL`. Keep configuration in `nuru_bot/config.py` and document
new environment variables in `.env.example`.

## Testing Guidelines

Tests use `pytest` and live in `tests/test_*.py`; test functions should be named
`test_*`. Prefer fakes and monkeypatched environment variables over live Discord,
HTTP, or audio service calls. Cover config parsing, state and memory persistence,
API error behavior, commands, voice runtime changes, and companion prompt flow.

## Commit & Pull Request Guidelines

The history uses Conventional Commits, for example `feat: add live Discord
diagnostics`, `fix: close vtuber runtime services`, and `test: cover command and
config behavior`. Use `feat`, `fix`, `test`, `docs`, `refactor`, or `chore` with
an imperative summary.

Pull requests should describe the behavior change, list verification commands,
link related issues, and call out any new Discord permissions or environment
variables. Never commit `.env`, tokens, local databases, logs, or virtual
environments.
