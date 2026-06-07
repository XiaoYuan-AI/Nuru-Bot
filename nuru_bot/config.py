from __future__ import annotations

from dataclasses import dataclass
from os import getenv

from dotenv import load_dotenv


DEFAULT_API_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_DISCORD_PROXY = "http://127.0.0.1:10808"
DEFAULT_GUILD_ID = 1061629481267245086
DEFAULT_VOICE_CHANNEL_ID = 1385943585597292706

TRUE_VALUES = {"1", "true", "yes", "on"}
FALSE_VALUES = {"0", "false", "no", "off", ""}


@dataclass(frozen=True)
class BotConfig:
    token: str
    api_base_url: str
    request_timeout_seconds: float
    discord_proxy: str | None
    activity_name: str
    guild_id: int | None
    voice_channel_id: int | None
    connect_voice_on_ready: bool
    record_voice_audio: bool
    enable_dm_chat: bool
    enable_reaction_chat: bool


def load_config() -> BotConfig:
    load_dotenv()

    token = _optional_env("DISCORD_TOKEN") or _optional_env("TOKEN")
    if token is None:
        raise RuntimeError("Set DISCORD_TOKEN or TOKEN in the environment.")

    return BotConfig(
        token=token,
        api_base_url=_env("NURU_API_BASE_URL", DEFAULT_API_BASE_URL),
        request_timeout_seconds=_float_env("NURU_REQUEST_TIMEOUT_SECONDS", 30.0),
        discord_proxy=_optional_env("DISCORD_PROXY", DEFAULT_DISCORD_PROXY),
        activity_name=_env("NURU_ACTIVITY_NAME", "Still WIP"),
        guild_id=_optional_int_env("DISCORD_GUILD_ID", DEFAULT_GUILD_ID),
        voice_channel_id=_optional_int_env(
            "DISCORD_VOICE_CHANNEL_ID",
            DEFAULT_VOICE_CHANNEL_ID,
        ),
        connect_voice_on_ready=_bool_env("NURU_CONNECT_VOICE_ON_READY", True),
        record_voice_audio=_bool_env("NURU_RECORD_VOICE_AUDIO", False),
        enable_dm_chat=_bool_env("NURU_ENABLE_DM_CHAT", False),
        enable_reaction_chat=_bool_env("NURU_ENABLE_REACTION_CHAT", False),
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


def _optional_int_env(name: str, default: int | None = None) -> int | None:
    value = getenv(name)
    if value is None or not value.strip():
        return default

    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
