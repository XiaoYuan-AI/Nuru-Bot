from __future__ import annotations

import argparse
import asyncio
import io
import subprocess
import wave
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .api import NuruApi, NuruApiError
from .companion import CompanionService, InteractionRequest
from .config import BotConfig, load_config
from .memory import MemoryStore
from .state import StateStore
from .voice import HotwordDetector, VoiceActivityDetector, play_tts_stream


@dataclass(frozen=True)
class DiagnosticResult:
    name: str
    ok: bool
    detail: str


@dataclass(frozen=True)
class DiagnosticReport:
    results: list[DiagnosticResult]

    @property
    def ok(self) -> bool:
        return all(result.ok for result in self.results)

    def format_text(self) -> str:
        lines = []
        for result in self.results:
            status = "PASS" if result.ok else "FAIL"
            lines.append(f"[{status}] {result.name}: {result.detail}")
        return "\n".join(lines)


def run_diagnostics(
    config: BotConfig,
    *,
    api: NuruApi | None = None,
    include_api: bool = True,
    include_ffmpeg: bool = True,
    voice_sample_path: str | Path | None = None,
    include_discord_live: bool = False,
    discord_live_speak_text: str | None = None,
    discord_live_timeout_seconds: float = 30.0,
    ffmpeg_checker: Callable[[str], DiagnosticResult] | None = None,
    live_bot_factory: Callable[[BotConfig], Any] | None = None,
) -> DiagnosticReport:
    results = [
        _check_discord_token(config),
        _check_storage(config),
        _check_bot_runtime(config),
    ]

    if include_ffmpeg:
        checker = ffmpeg_checker or check_ffmpeg
        results.append(checker(config.ffmpeg_executable))

    api_client: NuruApi | None = None
    own_api_client = False
    if include_api or voice_sample_path is not None or discord_live_speak_text:
        api_client = api or NuruApi(
            config.api_base_url,
            config.request_timeout_seconds,
        )
        own_api_client = api is None

    try:
        if include_api and api_client is not None:
            results.extend(check_api_contract(api_client))
            results.append(check_companion_pipeline(api_client, config))

        if voice_sample_path is not None and api_client is not None:
            results.append(check_voice_sample(api_client, config, voice_sample_path))

        if include_discord_live:
            results.append(
                asyncio.run(
                    check_discord_live(
                        config,
                        api=api_client,
                        speak_text=discord_live_speak_text,
                        timeout_seconds=discord_live_timeout_seconds,
                        bot_factory=live_bot_factory,
                    )
                )
            )
    finally:
        if own_api_client and api_client is not None:
            api_client.close()

    return DiagnosticReport(results)


def check_ffmpeg(executable: str) -> DiagnosticResult:
    try:
        completed = subprocess.run(
            [executable, "-version"],
            capture_output=True,
            check=False,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return DiagnosticResult(
            "ffmpeg",
            False,
            f"{executable!r} could not be executed: {exc}",
        )

    if completed.returncode != 0:
        return DiagnosticResult(
            "ffmpeg",
            False,
            f"{executable!r} exited with {completed.returncode}",
        )

    first_line = completed.stdout.splitlines()[0] if completed.stdout else executable
    return DiagnosticResult("ffmpeg", True, first_line)


def check_api_contract(api: NuruApi) -> list[DiagnosticResult]:
    checks = [
        ("api:model", lambda: bool(api.generate("diagnostic ping").strip())),
        ("api:embeddings", lambda: len(api.embed("diagnostic memory")) > 0),
        (
            "api:transcribe",
            lambda: api.transcribe_audio(_silent_wave_bytes()) is not None,
        ),
        ("api:tts-stream", lambda: _has_tts_chunk(api)),
    ]

    results: list[DiagnosticResult] = []
    for name, check in checks:
        try:
            ok = check()
        except NuruApiError as exc:
            results.append(DiagnosticResult(name, False, str(exc)))
            continue
        except Exception as exc:  # pragma: no cover - defensive diagnostics boundary
            results.append(DiagnosticResult(name, False, f"unexpected error: {exc}"))
            continue

        detail = "contract responded" if ok else "contract returned an empty response"
        results.append(DiagnosticResult(name, ok, detail))

    return results


def check_companion_pipeline(api: NuruApi, config: BotConfig) -> DiagnosticResult:
    memory = MemoryStore(":memory:")
    state = StateStore(":memory:")
    companion = CompanionService(
        api=api,
        memory=memory,
        state=state,
        config=config,
    )

    try:
        response = asyncio.run(
            companion.respond(
                InteractionRequest(
                    user_id="diagnostic-user",
                    channel_id="diagnostic-channel",
                    author_name="Diagnostic",
                    content="nuru diagnostic companion pipeline check",
                    source="diagnostic",
                )
            )
        )
    except NuruApiError as exc:
        return DiagnosticResult("companion pipeline", False, str(exc))
    except Exception as exc:  # pragma: no cover - defensive diagnostics boundary
        return DiagnosticResult("companion pipeline", False, f"unexpected error: {exc}")
    finally:
        memory.close()
        state.close()

    if not response.text.strip():
        return DiagnosticResult(
            "companion pipeline",
            False,
            "pipeline returned an empty response",
        )

    return DiagnosticResult(
        "companion pipeline",
        True,
        f"response mode {response.response_mode}",
    )


def check_voice_sample(
    api: NuruApi,
    config: BotConfig,
    voice_sample_path: str | Path,
) -> DiagnosticResult:
    path = Path(voice_sample_path)
    try:
        audio_data = path.read_bytes()
    except OSError as exc:
        return DiagnosticResult("voice sample", False, f"could not read {path}: {exc}")

    vad = VoiceActivityDetector(config.voice_vad_threshold)
    if not vad.detects_speech(audio_data):
        return DiagnosticResult(
            "voice sample",
            False,
            f"VAD did not detect speech above RMS threshold {config.voice_vad_threshold}",
        )

    memory = MemoryStore(":memory:")
    state = StateStore(":memory:")
    companion = CompanionService(
        api=api,
        memory=memory,
        state=state,
        config=config,
    )

    try:
        transcript = api.transcribe_audio(audio_data)
        if not HotwordDetector(config.wake_words).matches(transcript):
            return DiagnosticResult(
                "voice sample",
                False,
                f"transcript did not include wake word: {transcript!r}",
            )

        response = asyncio.run(
            companion.respond(
                InteractionRequest(
                    user_id="diagnostic-voice-user",
                    channel_id="diagnostic-voice-channel",
                    author_name="Diagnostic Voice",
                    content=transcript,
                    source="voice-sample",
                )
            )
        )
        if not response.text.strip():
            return DiagnosticResult("voice sample", False, "companion response was empty")

        if not _has_tts_chunk_for_text(api, response.text):
            return DiagnosticResult("voice sample", False, "TTS stream returned no audio")
    except NuruApiError as exc:
        return DiagnosticResult("voice sample", False, str(exc))
    except Exception as exc:  # pragma: no cover - defensive diagnostics boundary
        return DiagnosticResult("voice sample", False, f"unexpected error: {exc}")
    finally:
        memory.close()
        state.close()

    return DiagnosticResult(
        "voice sample",
        True,
        f"wake word accepted transcript: {transcript!r}",
    )


async def check_discord_live(
    config: BotConfig,
    *,
    api: NuruApi | None = None,
    speak_text: str | None = None,
    timeout_seconds: float = 30.0,
    bot_factory: Callable[[BotConfig], Any] | None = None,
    tts_player: Callable[[Any, NuruApi, BotConfig, str], Any] = play_tts_stream,
) -> DiagnosticResult:
    if not config.token:
        return DiagnosticResult(
            "discord live",
            False,
            "set DISCORD_TOKEN or TOKEN before running live Discord diagnostics",
        )
    if config.guild_id is None or config.voice_channel_id is None:
        return DiagnosticResult(
            "discord live",
            False,
            "DISCORD_GUILD_ID and DISCORD_VOICE_CHANNEL_ID are required",
        )
    if speak_text and api is None:
        return DiagnosticResult(
            "discord live",
            False,
            "live TTS playback requires API checks",
        )

    client = (bot_factory or _create_live_bot)(config)
    loop = asyncio.get_running_loop()
    ready_result: asyncio.Future[DiagnosticResult] = loop.create_future()

    def finish(result: DiagnosticResult) -> None:
        if not ready_result.done():
            ready_result.set_result(result)

    @client.event
    async def on_ready() -> None:
        voice_client = None
        try:
            guild = client.get_guild(config.guild_id)
            if guild is None:
                finish(
                    DiagnosticResult(
                        "discord live",
                        False,
                        f"guild {config.guild_id} was not found",
                    )
                )
                return

            channel = guild.get_channel(config.voice_channel_id)
            if channel is None:
                channel = client.get_channel(config.voice_channel_id)
            if channel is None or not hasattr(channel, "connect"):
                finish(
                    DiagnosticResult(
                        "discord live",
                        False,
                        f"voice channel {config.voice_channel_id} was not found",
                    )
                )
                return

            voice_client = await channel.connect()
            detail = f"connected to voice channel {config.voice_channel_id}"
            if speak_text and api is not None:
                maybe_awaitable = tts_player(voice_client, api, config, speak_text)
                if hasattr(maybe_awaitable, "__await__"):
                    await maybe_awaitable
                detail = f"{detail} and started TTS playback"

            finish(DiagnosticResult("discord live", True, detail))
        except Exception as exc:
            finish(DiagnosticResult("discord live", False, str(exc)))
        finally:
            if voice_client is not None and hasattr(voice_client, "disconnect"):
                await voice_client.disconnect(force=True)
            await client.close()

    start_task = asyncio.create_task(client.start(config.token))
    try:
        done, _ = await asyncio.wait(
            {ready_result, start_task},
            timeout=timeout_seconds,
            return_when=asyncio.FIRST_COMPLETED,
        )
        if ready_result in done:
            return ready_result.result()
        if start_task in done:
            exc = start_task.exception()
            if exc is None:
                return DiagnosticResult("discord live", False, "client stopped before ready")
            return DiagnosticResult("discord live", False, str(exc))

        await client.close()
        return DiagnosticResult(
            "discord live",
            False,
            f"timed out after {timeout_seconds:.1f}s",
        )
    finally:
        if not start_task.done():
            start_task.cancel()
            try:
                await start_task
            except asyncio.CancelledError:
                pass


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Check Nuru Bot runtime configuration and local service contracts.",
    )
    parser.add_argument("--skip-api", action="store_true", help="Do not call Nuru API endpoints.")
    parser.add_argument("--skip-ffmpeg", action="store_true", help="Do not check FFmpeg.")
    parser.add_argument(
        "--voice-sample",
        type=Path,
        help="Audio file containing a wake-word phrase to test VAD, transcription, response, and TTS.",
    )
    parser.add_argument(
        "--discord-live",
        action="store_true",
        help="Log in, find the configured guild/channel, connect to voice, then disconnect.",
    )
    parser.add_argument(
        "--discord-live-speak",
        help="Text to play through TTS during --discord-live.",
    )
    parser.add_argument(
        "--discord-live-timeout",
        type=float,
        default=30.0,
        help="Seconds to wait for live Discord diagnostics.",
    )
    args = parser.parse_args()
    if args.skip_api and args.voice_sample is not None:
        parser.error("--voice-sample requires API checks; remove --skip-api")
    if args.discord_live_speak and not args.discord_live:
        parser.error("--discord-live-speak requires --discord-live")
    if args.skip_api and args.discord_live_speak:
        parser.error("--discord-live-speak requires API checks; remove --skip-api")

    config = load_config(require_token=False)
    report = run_diagnostics(
        config,
        include_api=not args.skip_api,
        include_ffmpeg=not args.skip_ffmpeg,
        voice_sample_path=args.voice_sample,
        include_discord_live=args.discord_live,
        discord_live_speak_text=args.discord_live_speak,
        discord_live_timeout_seconds=args.discord_live_timeout,
    )
    print(report.format_text())
    raise SystemExit(0 if report.ok else 1)


def _check_discord_token(config: BotConfig) -> DiagnosticResult:
    if config.token:
        return DiagnosticResult("discord token", True, "token is configured")
    return DiagnosticResult(
        "discord token",
        False,
        "set DISCORD_TOKEN or TOKEN before starting the bot",
    )


def _check_storage(config: BotConfig) -> DiagnosticResult:
    try:
        memory = MemoryStore(config.data_path)
        state = StateStore(config.data_path)
        state.get_mood()
        memory.close()
        state.close()
    except Exception as exc:
        return DiagnosticResult("sqlite storage", False, str(exc))

    return DiagnosticResult("sqlite storage", True, str(config.data_path))


def _check_bot_runtime(config: BotConfig) -> DiagnosticResult:
    previous_loop = _current_event_loop()
    loop = asyncio.new_event_loop()
    try:
        from .bot import close_runtime_services, create_client

        asyncio.set_event_loop(loop)
        client = create_client(config)
        command_count = len(getattr(client, "pending_application_commands", []))
    except Exception as exc:
        return DiagnosticResult("discord bot", False, str(exc))
    finally:
        if "client" in locals():
            close_runtime_services(client)
        asyncio.set_event_loop(previous_loop)
        loop.close()

    if config.enable_slash_commands and command_count == 0:
        return DiagnosticResult(
            "discord bot",
            False,
            "slash commands are enabled but none were registered",
        )

    detail = (
        f"registered {command_count} slash command(s)"
        if config.enable_slash_commands
        else "slash commands disabled"
    )
    return DiagnosticResult("discord bot", True, detail)


def _current_event_loop() -> asyncio.AbstractEventLoop | None:
    try:
        return asyncio.get_event_loop()
    except RuntimeError:
        return None


def _create_live_bot(config: BotConfig) -> Any:
    from discord import Bot, Intents

    options: dict[str, str] = {}
    if config.discord_proxy:
        options["proxy"] = config.discord_proxy
    return Bot(intents=Intents.all(), **options)


def _has_tts_chunk(api: NuruApi) -> bool:
    return _has_tts_chunk_for_text(api, "diagnostic tts")


def _has_tts_chunk_for_text(api: NuruApi, text: str) -> bool:
    for chunk in api.stream_tts(text):
        if chunk:
            return True
    return False


def _silent_wave_bytes() -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wave_file:
        wave_file.setnchannels(1)
        wave_file.setsampwidth(2)
        wave_file.setframerate(16000)
        wave_file.writeframes(b"\x00\x00" * 1600)
    return buffer.getvalue()


if __name__ == "__main__":
    main()
