from pathlib import Path

import pytest

from nuru_bot.config import load_config


CONFIG_ENV_NAMES = [
    "DISCORD_TOKEN",
    "TOKEN",
    "NURU_API_BASE_URL",
    "NURU_REQUEST_TIMEOUT_SECONDS",
    "NURU_DATA_PATH",
    "DISCORD_PROXY",
    "NURU_ACTIVITY_NAME",
    "DISCORD_GUILD_ID",
    "DISCORD_VOICE_CHANNEL_ID",
    "DISCORD_TEXT_CHANNEL_ID",
    "NURU_CONNECT_VOICE_ON_READY",
    "NURU_RECORD_VOICE_AUDIO",
    "NURU_ENABLE_TEXT_CHAT",
    "NURU_ENABLE_DM_CHAT",
    "NURU_ENABLE_REACTION_CHAT",
    "NURU_ENABLE_SLASH_COMMANDS",
    "NURU_ENABLE_IDLE_COMMENTARY",
    "NURU_IDLE_COMMENTARY_SECONDS",
    "NURU_VAD_RMS_THRESHOLD",
    "NURU_RECORDING_SEGMENT_SECONDS",
    "NURU_WAKE_WORDS",
    "NURU_DEFAULT_RESPONSE_MODE",
    "NURU_MEMORY_CONTEXT_LIMIT",
    "NURU_WORKING_MEMORY_LIMIT",
    "NURU_REFLECTION_INTERVAL_MESSAGES",
    "NURU_REFLECTION_MEMORY_LIMIT",
    "NURU_ENABLE_MODERATION",
    "NURU_OBSERVABILITY_LOG_PATH",
    "NURU_TTS_VOICE",
    "NURU_FFMPEG_EXECUTABLE",
]


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    for name in CONFIG_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)


def test_load_config_uses_environment_values(monkeypatch):
    monkeypatch.setenv("DISCORD_TOKEN", "discord-token")
    monkeypatch.setenv("NURU_API_BASE_URL", "http://api.local/")
    monkeypatch.setenv("NURU_DATA_PATH", "runtime/state.sqlite3")
    monkeypatch.setenv("DISCORD_PROXY", "")
    monkeypatch.setenv("DISCORD_TEXT_CHANNEL_ID", "123")
    monkeypatch.setenv("NURU_ENABLE_TEXT_CHAT", "true")
    monkeypatch.setenv("NURU_ENABLE_IDLE_COMMENTARY", "false")
    monkeypatch.setenv("NURU_WAKE_WORDS", "Nuru,Hey Nuru")
    monkeypatch.setenv("NURU_RECORDING_SEGMENT_SECONDS", "2.5")
    monkeypatch.setenv("NURU_DEFAULT_RESPONSE_MODE", "both")
    monkeypatch.setenv("NURU_MEMORY_CONTEXT_LIMIT", "9")
    monkeypatch.setenv("NURU_WORKING_MEMORY_LIMIT", "7")
    monkeypatch.setenv("NURU_REFLECTION_INTERVAL_MESSAGES", "3")
    monkeypatch.setenv("NURU_REFLECTION_MEMORY_LIMIT", "11")
    monkeypatch.setenv("NURU_ENABLE_MODERATION", "false")
    monkeypatch.setenv("NURU_OBSERVABILITY_LOG_PATH", "runtime/events.jsonl")
    monkeypatch.setenv("NURU_TTS_VOICE", "vtuber")

    config = load_config()

    assert config.token == "discord-token"
    assert config.api_base_url == "http://api.local/"
    assert config.data_path == Path("runtime/state.sqlite3")
    assert config.discord_proxy is None
    assert config.text_channel_id == 123
    assert config.enable_text_chat
    assert not config.enable_idle_commentary
    assert config.wake_words == ("nuru", "hey nuru")
    assert config.recording_segment_seconds == 2.5
    assert config.default_response_mode == "both"
    assert config.memory_context_limit == 9
    assert config.working_memory_limit == 7
    assert config.reflection_interval_messages == 3
    assert config.reflection_memory_limit == 11
    assert not config.enable_moderation
    assert config.observability_log_path == Path("runtime/events.jsonl")
    assert config.tts_voice == "vtuber"


def test_load_config_accepts_legacy_token_and_dm_chat_flag(monkeypatch):
    monkeypatch.setenv("TOKEN", "legacy-token")
    monkeypatch.setenv("NURU_ENABLE_DM_CHAT", "true")

    config = load_config()

    assert config.token == "legacy-token"
    assert config.enable_text_chat


def test_load_config_does_not_default_to_specific_discord_network(monkeypatch):
    monkeypatch.setenv("DISCORD_TOKEN", "discord-token")

    config = load_config()

    assert config.discord_proxy is None
    assert config.guild_id is None
    assert config.voice_channel_id is None


def test_load_config_requires_token():
    with pytest.raises(RuntimeError):
        load_config()


def test_load_config_rejects_invalid_response_mode(monkeypatch):
    monkeypatch.setenv("DISCORD_TOKEN", "discord-token")
    monkeypatch.setenv("NURU_DEFAULT_RESPONSE_MODE", "video")

    with pytest.raises(ValueError):
        load_config()


def test_load_config_rejects_non_positive_recording_segment(monkeypatch):
    monkeypatch.setenv("DISCORD_TOKEN", "discord-token")
    monkeypatch.setenv("NURU_RECORDING_SEGMENT_SECONDS", "0")

    with pytest.raises(ValueError):
        load_config()


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("NURU_REQUEST_TIMEOUT_SECONDS", "0"),
        ("NURU_REQUEST_TIMEOUT_SECONDS", "-1"),
        ("NURU_IDLE_COMMENTARY_SECONDS", "29.9"),
        ("NURU_VAD_RMS_THRESHOLD", "-0.1"),
        ("NURU_MEMORY_CONTEXT_LIMIT", "-1"),
        ("NURU_WORKING_MEMORY_LIMIT", "-1"),
        ("NURU_REFLECTION_INTERVAL_MESSAGES", "-1"),
        ("NURU_REFLECTION_MEMORY_LIMIT", "-1"),
    ],
)
def test_load_config_rejects_invalid_numeric_limits(monkeypatch, name, value):
    monkeypatch.setenv("DISCORD_TOKEN", "discord-token")
    monkeypatch.setenv(name, value)

    with pytest.raises(ValueError):
        load_config()
