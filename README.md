# Nuru Bot

Nuru Bot is a Discord bot client that connects Discord events to a local Nuru
model service.

## Project Layout

```text
.
|-- bot.py              # Compatibility launcher: python bot.py
|-- main.py             # Compatibility launcher: python main.py
|-- nuru_bot/
|   |-- api.py          # Local HTTP model/vision API client
|   |-- bot.py          # Discord client factory and app entry point
|   |-- commands.py     # Slash command registration
|   |-- companion.py    # Prompting, memory use, and response orchestration
|   |-- config.py       # Environment configuration parsing
|   |-- events.py       # Discord event handlers
|   |-- memory.py       # SQLite long-term chat memory and embeddings
|   |-- state.py        # SQLite mood, persona, and response preferences
|   `-- voice.py        # Voice-channel connection and recording hooks
`-- pyproject.toml
```

## Configuration

Create a `.env` file from `.env.example` and set at least:

```env
DISCORD_TOKEN=your-discord-bot-token
```

The old `TOKEN` environment variable is still accepted, but `DISCORD_TOKEN` is
preferred.

Useful options:

```env
NURU_API_BASE_URL=http://127.0.0.1:8000
NURU_DATA_PATH=data/nuru_bot.sqlite3
DISCORD_PROXY=http://127.0.0.1:10808
DISCORD_GUILD_ID=1061629481267245086
DISCORD_VOICE_CHANNEL_ID=1385943585597292706
NURU_CONNECT_VOICE_ON_READY=true
NURU_ENABLE_TEXT_CHAT=false
NURU_ENABLE_REACTION_CHAT=false
NURU_DEFAULT_RESPONSE_MODE=text
NURU_WAKE_WORDS=nuru,hey nuru
```

## Run

```powershell
uv run python -m nuru_bot
```

The root launchers also work:

```powershell
uv run python bot.py
uv run python main.py
```

## Test

```powershell
uv run pytest
uv run python -m compileall bot.py main.py nuru_bot tests
```
