from __future__ import annotations

import argparse
import asyncio
import io
import subprocess
import wave
from collections.abc import Callable
from dataclasses import dataclass

from .api import NuruApi, NuruApiError
from .companion import CompanionService, InteractionRequest
from .config import BotConfig, load_config
from .memory import MemoryStore
from .state import StateStore


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

    if include_api:
        api_client = api or NuruApi(
            config.api_base_url,
            config.request_timeout_seconds,
        )
        results.extend(check_api_contract(api_client))
        results.append(check_companion_pipeline(api_client, config))

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


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Check Nuru Bot runtime configuration and local service contracts.",
    )
    parser.add_argument("--skip-api", action="store_true", help="Do not call Nuru API endpoints.")
    parser.add_argument("--skip-ffmpeg", action="store_true", help="Do not check FFmpeg.")
    args = parser.parse_args()

    config = load_config(require_token=False)
    report = run_diagnostics(
        config,
        include_api=not args.skip_api,
        include_ffmpeg=not args.skip_ffmpeg,
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
        from .bot import create_client

        asyncio.set_event_loop(loop)
        client = create_client(config)
        command_count = len(getattr(client, "pending_application_commands", []))
    except Exception as exc:
        return DiagnosticResult("discord bot", False, str(exc))
    finally:
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
    for chunk in api.stream_tts("diagnostic tts"):
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
