from __future__ import annotations

import argparse
import asyncio
import io
import subprocess
import wave
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .api import NuruApi, NuruApiError
from .companion import CompanionService, InteractionRequest
from .config import BotConfig, load_config
from .memory import MemoryStore
from .state import StateStore
from .voice import HotwordDetector, VoiceActivityDetector


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
    ffmpeg_checker: Callable[[str], DiagnosticResult] | None = None,
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
    if include_api or voice_sample_path is not None:
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
    args = parser.parse_args()
    if args.skip_api and args.voice_sample is not None:
        parser.error("--voice-sample requires API checks; remove --skip-api")

    config = load_config(require_token=False)
    report = run_diagnostics(
        config,
        include_api=not args.skip_api,
        include_ffmpeg=not args.skip_ffmpeg,
        voice_sample_path=args.voice_sample,
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
