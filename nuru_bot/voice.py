from __future__ import annotations

import asyncio
import io
import logging
import math
import time
import wave
from collections.abc import Iterable, Iterator

from discord import Client, FFmpegPCMAudio, VoiceClient, sinks

from .api import NuruApi, NuruApiError
from .companion import CompanionService, InteractionRequest
from .config import BotConfig


LOGGER = logging.getLogger(__name__)


class VoiceActivityDetector:
    def __init__(self, rms_threshold: float) -> None:
        self.rms_threshold = rms_threshold

    def detects_speech(self, audio_data: bytes) -> bool:
        pcm = _extract_pcm(audio_data)
        if len(pcm) < 2:
            return False

        sample_count = len(pcm) // 2
        if sample_count == 0:
            return False

        total = 0
        for index in range(0, len(pcm) - 1, 2):
            sample = int.from_bytes(pcm[index : index + 2], "little", signed=True)
            total += sample * sample

        rms = math.sqrt(total / sample_count)
        return rms >= self.rms_threshold


class HotwordDetector:
    def __init__(self, hotwords: Iterable[str]) -> None:
        self.hotwords = tuple(word.lower() for word in hotwords if word.strip())

    def matches(self, transcript: str) -> bool:
        lowered = transcript.lower()
        return any(hotword in lowered for hotword in self.hotwords)


class IteratorAudioStream(io.RawIOBase):
    def __init__(self, chunks: Iterator[bytes]) -> None:
        self._chunks = chunks
        self._buffer = bytearray()
        self._closed = False

    def readable(self) -> bool:
        return True

    def read(self, size: int = -1) -> bytes:
        if self._closed:
            return b""

        if size is None or size < 0:
            parts = [bytes(self._buffer)]
            self._buffer.clear()
            parts.extend(self._chunks)
            self._closed = True
            return b"".join(parts)

        while len(self._buffer) < size:
            try:
                self._buffer.extend(next(self._chunks))
            except StopIteration:
                self._closed = True
                break

        data = bytes(self._buffer[:size])
        del self._buffer[:size]
        return data


class VoiceRuntime:
    def __init__(
        self,
        *,
        config: BotConfig,
        api: NuruApi,
        companion: CompanionService,
    ) -> None:
        self.config = config
        self.api = api
        self.companion = companion
        self.vad = VoiceActivityDetector(config.voice_vad_threshold)
        self.hotwords = HotwordDetector(config.wake_words)
        self.last_voice_activity_at = time.monotonic()
        self.last_idle_commentary_at = 0.0
        self.voice_client: VoiceClient | None = None
        self.client: Client | None = None
        self._idle_task: asyncio.Task[None] | None = None
        self._recording_stop_task: asyncio.Task[None] | None = None

    async def connect(self, client: Client) -> VoiceClient | None:
        self.client = client
        voice_client = await connect_voice_channel(client, self.config)
        self.voice_client = voice_client

        if voice_client is None:
            return None

        if self.config.record_voice_audio:
            self.start_recording(voice_client)

        if self.config.enable_idle_commentary:
            self.start_idle_commentary_loop(client)

        return voice_client

    def start_recording(self, voice_client: VoiceClient) -> None:
        if getattr(voice_client, "recording", False):
            return

        voice_client.start_recording(sinks.WaveSink(), self.recording_callback, voice_client)
        self._schedule_recording_stop(voice_client)

    async def recording_callback(
        self,
        sink: sinks.WaveSink,
        voice_client: VoiceClient,
    ) -> None:
        for user_id, audio in sink.audio_data.items():
            audio_bytes = extract_audio_bytes(audio)
            if not self.vad.detects_speech(audio_bytes):
                continue

            self.last_voice_activity_at = time.monotonic()
            try:
                transcript = await asyncio.to_thread(self.api.transcribe_audio, audio_bytes)
            except NuruApiError:
                LOGGER.exception("Failed to transcribe voice audio")
                continue

            if not self.hotwords.matches(transcript):
                LOGGER.info("Ignoring voice transcript without wake word: %s", transcript)
                continue

            channel_id = _voice_channel_id(voice_client)
            try:
                response = await self.companion.respond(
                    InteractionRequest(
                        user_id=str(user_id),
                        channel_id=channel_id,
                        author_name=_voice_author_name(voice_client, user_id),
                        content=transcript,
                        source="voice",
                    )
                )
            except NuruApiError:
                LOGGER.exception("Failed to generate a voice response")
                continue

            if response.response_mode in {"text", "both"}:
                await _send_channel_text(
                    self.client,
                    self.config,
                    voice_client,
                    response.text,
                )
            if response.response_mode in {"voice", "both"}:
                await self.speak(voice_client, response.text)

        if voice_client.is_connected() and self.config.record_voice_audio:
            self.start_recording(voice_client)

    async def speak(self, voice_client: VoiceClient, text: str) -> None:
        await play_tts_stream(voice_client, self.api, self.config, text)

    def start_idle_commentary_loop(self, client: Client) -> None:
        if self._idle_task is not None and not self._idle_task.done():
            return
        self._idle_task = client.loop.create_task(self._idle_commentary_loop(client))

    def close(self) -> None:
        if self._idle_task is not None and not self._idle_task.done():
            self._idle_task.cancel()
        if self._recording_stop_task is not None and not self._recording_stop_task.done():
            self._recording_stop_task.cancel()

    async def _idle_commentary_loop(self, client: Client) -> None:
        while not client.is_closed():
            await asyncio.sleep(5)
            await self.maybe_run_idle_commentary()

    def _schedule_recording_stop(self, voice_client: VoiceClient) -> None:
        if self._recording_stop_task is not None and not self._recording_stop_task.done():
            self._recording_stop_task.cancel()
        self._recording_stop_task = asyncio.create_task(
            self._stop_recording_after_segment(voice_client)
        )

    async def _stop_recording_after_segment(self, voice_client: VoiceClient) -> None:
        await asyncio.sleep(self.config.recording_segment_seconds)
        if not voice_client.is_connected():
            return
        if not getattr(voice_client, "recording", False):
            return

        try:
            voice_client.stop_recording()
        except Exception:
            LOGGER.exception("Failed to stop segmented voice recording")

    async def maybe_run_idle_commentary(self) -> bool:
        voice_client = self.voice_client
        if voice_client is None or not voice_client.is_connected():
            return False
        if voice_client.is_playing():
            return False

        now = time.monotonic()
        if now - self.last_voice_activity_at < self.config.idle_commentary_seconds:
            return False
        if now - self.last_idle_commentary_at < self.config.idle_commentary_seconds:
            return False

        alone_user = _single_human_member(voice_client)
        if alone_user is None:
            return False

        self.last_idle_commentary_at = now
        try:
            text = await asyncio.to_thread(
                self.companion.idle_prompt,
                user_id=str(alone_user.id),
                channel_id=_voice_channel_id(voice_client),
                author_name=alone_user.display_name,
            )
            await self.speak(voice_client, text)
        except NuruApiError:
            LOGGER.exception("Failed to generate idle commentary")
            return False

        return True


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
    return voice_client


async def play_tts_stream(
    voice_client: VoiceClient,
    api: NuruApi,
    config: BotConfig,
    text: str,
) -> None:
    if not text.strip():
        return

    chunks = api.stream_tts(text, voice=config.tts_voice)
    source = FFmpegPCMAudio(
        IteratorAudioStream(chunks),
        pipe=True,
        executable=config.ffmpeg_executable,
    )
    if voice_client.is_playing():
        voice_client.stop()
    voice_client.play(source)


def extract_audio_bytes(audio: object) -> bytes:
    file_obj = getattr(audio, "file", None)
    if file_obj is not None:
        if hasattr(file_obj, "seek"):
            file_obj.seek(0)
        data = file_obj.read()
        if isinstance(data, bytes):
            return data

    data = getattr(audio, "data", None)
    if isinstance(data, bytes):
        return data

    if isinstance(audio, bytes):
        return audio

    return b""


def _extract_pcm(audio_data: bytes) -> bytes:
    if audio_data.startswith(b"RIFF"):
        try:
            with wave.open(io.BytesIO(audio_data), "rb") as wave_file:
                return wave_file.readframes(wave_file.getnframes())
        except wave.Error:
            return audio_data
    return audio_data


def _voice_channel_id(voice_client: VoiceClient) -> str:
    channel = getattr(voice_client, "channel", None)
    channel_id = getattr(channel, "id", "voice")
    return str(channel_id)


def _voice_author_name(voice_client: VoiceClient, user_id: object) -> str:
    channel = getattr(voice_client, "channel", None)
    members = getattr(channel, "members", None)
    if members is None:
        return str(user_id)

    expected_id = str(user_id)
    for member in members:
        if str(getattr(member, "id", "")) != expected_id:
            continue

        display_name = getattr(member, "display_name", None)
        if display_name:
            return str(display_name)

        name = getattr(member, "name", None)
        if name:
            return str(name)

    return str(user_id)


def _single_human_member(voice_client: VoiceClient) -> object | None:
    channel = getattr(voice_client, "channel", None)
    members = getattr(channel, "members", None)
    if members is None:
        return None

    human_members = [
        member
        for member in members
        if not getattr(member, "bot", False)
    ]
    if len(human_members) != 1:
        return None
    return human_members[0]


async def _send_channel_text(
    client: Client | None,
    config: BotConfig,
    voice_client: VoiceClient,
    text: str,
) -> None:
    if client is not None and config.text_channel_id is not None:
        configured_channel = client.get_channel(config.text_channel_id)
        configured_send = getattr(configured_channel, "send", None)
        if configured_send is not None:
            await configured_send(text)
            return

    channel = getattr(voice_client, "channel", None)
    send = getattr(channel, "send", None)
    if send is None:
        return
    await send(text)
