from __future__ import annotations

import logging

from discord import Client, VoiceClient, sinks

from .config import BotConfig


LOGGER = logging.getLogger(__name__)


async def connect_voice_channel(
    client: Client,
    config: BotConfig,
) -> VoiceClient | None:
    if config.guild_id is None or config.voice_channel_id is None:
        LOGGER.info("Voice connection skipped because guild or channel ID is unset")
        return None

    guild = client.get_guild(config.guild_id)
    if guild is None:
        LOGGER.warning("Discord guild %s was not found", config.guild_id)
        return None

    channel = guild.get_channel(config.voice_channel_id)
    if channel is None or not hasattr(channel, "connect"):
        LOGGER.warning("Discord voice channel %s was not found", config.voice_channel_id)
        return None

    voice_client = await channel.connect()
    LOGGER.info("Connected to voice channel %s", config.voice_channel_id)

    if config.record_voice_audio:
        start_recording(voice_client)

    return voice_client


def start_recording(voice_client: VoiceClient) -> None:
    voice_client.start_recording(sinks.WaveSink(), recording_callback, voice_client)


async def recording_callback(sink: sinks.WaveSink, voice_client: VoiceClient) -> None:
    for user_id in sink.audio_data:
        LOGGER.info("Captured voice audio for user %s", user_id)

    if voice_client.is_connected():
        start_recording(voice_client)
