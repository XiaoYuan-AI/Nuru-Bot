from pathlib import Path

from nuru_bot.config import BotConfig


def make_config(**overrides):
    values = {
        "token": "dummy",
        "api_base_url": "http://127.0.0.1:8000",
        "request_timeout_seconds": 1.0,
        "data_path": Path(":memory:"),
        "discord_proxy": None,
        "activity_name": "test",
        "guild_id": None,
        "voice_channel_id": None,
        "text_channel_id": None,
        "connect_voice_on_ready": False,
        "record_voice_audio": False,
        "enable_text_chat": True,
        "enable_reaction_chat": False,
        "enable_slash_commands": True,
        "enable_idle_commentary": False,
        "idle_commentary_seconds": 30.0,
        "voice_vad_threshold": 500.0,
        "recording_segment_seconds": 5.0,
        "wake_words": ("nuru",),
        "default_response_mode": "text",
        "memory_context_limit": 6,
        "tts_voice": None,
        "ffmpeg_executable": "ffmpeg",
    }
    values.update(overrides)
    return BotConfig(**values)
