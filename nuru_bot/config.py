from __future__ import annotations

from dataclasses import dataclass
from os import getenv
from pathlib import Path

from dotenv import load_dotenv


DEFAULT_API_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_DISCORD_PROXY = "http://127.0.0.1:10808"
DEFAULT_GUILD_ID = 1061629481267245086
DEFAULT_VOICE_CHANNEL_ID = 1385943585597292706
DEFAULT_DATA_PATH = "data/nuru_bot.sqlite3"

TRUE_VALUES = {"1", "true", "yes", "on"}
FALSE_VALUES = {"0", "false", "no", "off", ""}


@dataclass(frozen=True)
class BotConfig:
    token: str
    api_base_url: str
    request_timeout_seconds: float
    data_path: Path
    discord_proxy: str | None
    activity_name: str
    guild_id: int | None
    voice_channel_id: int | None
    connect_voice_on_ready: bool
    record_voice_audio: bool
    enable_text_chat: bool
    enable_reaction_chat: bool
    enable_slash_commands: bool
    enable_idle_commentary: bool
    idle_commentary_seconds: float
    voice_vad_threshold: float
    wake_words: tuple[str, ...]
    default_response_mode: str
    memory_context_limit: int
    tts_voice: str | None
    ffmpeg_executable: str


def load_config() -> BotConfig:
    load_dotenv()

    token = _optional_env("DISCORD_TOKEN") or _optional_env("TOKEN")
    if token is None:
        raise RuntimeError("Set DISCORD_TOKEN or TOKEN in the environment.")

    return BotConfig(
        token=token,
        api_base_url=_env("NURU_API_BASE_URL", DEFAULT_API_BASE_URL),
        request_timeout_seconds=_float_env("NURU_REQUEST_TIMEOUT_SECONDS", 30.0),
        data_path=Path(_env("NURU_DATA_PATH", DEFAULT_DATA_PATH)),
        discord_proxy=_optional_env("DISCORD_PROXY", DEFAULT_DISCORD_PROXY),
        activity_name=_env("NURU_ACTIVITY_NAME", "Still WIP"),
        guild_id=_optional_int_env("DISCORD_GUILD_ID", DEFAULT_GUILD_ID),
        voice_channel_id=_optional_int_env(
            "DISCORD_VOICE_CHANNEL_ID",
            DEFAULT_VOICE_CHANNEL_ID,
        ),
        connect_voice_on_ready=_bool_env("NURU_CONNECT_VOICE_ON_READY", True),
        record_voice_audio=_bool_env("NURU_RECORD_VOICE_AUDIO", False),
        enable_text_chat=_bool_env(
            "NURU_ENABLE_TEXT_CHAT",
            _bool_env("NURU_ENABLE_DM_CHAT", False),
        ),
        enable_reaction_chat=_bool_env("NURU_ENABLE_REACTION_CHAT", False),
        enable_slash_commands=_bool_env("NURU_ENABLE_SLASH_COMMANDS", True),
        enable_idle_commentary=_bool_env("NURU_ENABLE_IDLE_COMMENTARY", True),
        idle_commentary_seconds=_float_env("NURU_IDLE_COMMENTARY_SECONDS", 30.0),
        voice_vad_threshold=_float_env("NURU_VAD_RMS_THRESHOLD", 500.0),
        wake_words=_tuple_env("NURU_WAKE_WORDS", ("nuru", "hey nuru")),
        default_response_mode=_response_mode_env("NURU_DEFAULT_RESPONSE_MODE", "text"),
        memory_context_limit=_int_env("NURU_MEMORY_CONTEXT_LIMIT", 6),
        tts_voice=_optional_env("NURU_TTS_VOICE"),
        ffmpeg_executable=_env("NURU_FFMPEG_EXECUTABLE", "ffmpeg"),
    )


def _env(name: str, default: str) -> str:
    value = getenv(name)
    if value is None:
        return default
    return value.strip()


def _optional_env(name: str, default: str | None = None) -> str | None:
    value = getenv(name)
    if value is None:
        value = default
    if value is None:
        return None

    value = value.strip()
    return value or None


def _bool_env(name: str, default: bool) -> bool:
    value = getenv(name)
    if value is None:
        return default

    normalized = value.strip().lower()
    if normalized in TRUE_VALUES:
        return True
    if normalized in FALSE_VALUES:
        return False

    raise ValueError(f"{name} must be one of: true, false, 1, 0, yes, no, on, off")


def _float_env(name: str, default: float) -> float:
    value = getenv(name)
    if value is None or not value.strip():
        return default

    try:
        return float(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number") from exc


def _int_env(name: str, default: int) -> int:
    value = getenv(name)
    if value is None or not value.strip():
        return default

    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc


def _optional_int_env(name: str, default: int | None = None) -> int | None:
    value = getenv(name)
    if value is None or not value.strip():
        return default

    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc


def _tuple_env(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    value = getenv(name)
    if value is None or not value.strip():
        return default

    parsed = tuple(item.strip().lower() for item in value.split(",") if item.strip())
    return parsed or default


def _response_mode_env(name: str, default: str) -> str:
    value = _env(name, default).lower()
    if value not in {"text", "voice", "both"}:
        raise ValueError(f"{name} must be text, voice, or both")
    return value
