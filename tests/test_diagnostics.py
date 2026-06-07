import struct
import wave
import asyncio
from pathlib import Path

from nuru_bot.config import BotConfig, load_config
from nuru_bot.diagnostics import (
    DiagnosticResult,
    check_api_contract,
    check_discord_live,
    check_voice_sample,
    run_diagnostics,
)


class HealthyApi:
    def generate(self, prompt):
        return "ok"

    def embed(self, text):
        return [1.0, 0.0]

    def transcribe_audio(self, audio_data):
        return ""

    def stream_tts(self, text):
        yield b"audio"


class EmptyTtsApi(HealthyApi):
    def stream_tts(self, text):
        if False:
            yield b""


class VoiceSampleApi(HealthyApi):
    def __init__(self, transcript="hey nuru diagnostic"):
        self.transcript = transcript
        self.generated_prompts = []

    def generate(self, prompt):
        self.generated_prompts.append(prompt)
        return "voice response"

    def transcribe_audio(self, audio_data):
        return self.transcript


def test_run_diagnostics_reports_token_storage_ffmpeg_and_api(tmp_path):
    config = _config(tmp_path / "state.sqlite3", token="token")

    report = run_diagnostics(
        config,
        api=HealthyApi(),
        ffmpeg_checker=lambda executable: DiagnosticResult("ffmpeg", True, executable),
    )

    assert report.ok
    assert [result.name for result in report.results] == [
        "discord token",
        "sqlite storage",
        "discord bot",
        "ffmpeg",
        "api:model",
        "api:embeddings",
        "api:transcribe",
        "api:tts-stream",
        "companion pipeline",
    ]


def test_run_diagnostics_can_skip_external_checks(tmp_path):
    config = _config(tmp_path / "state.sqlite3", token="")

    report = run_diagnostics(config, include_api=False, include_ffmpeg=False)

    assert not report.ok
    assert [result.name for result in report.results] == [
        "discord token",
        "sqlite storage",
        "discord bot",
    ]
    assert "set DISCORD_TOKEN" in report.format_text()


def test_check_api_contract_fails_empty_tts_stream():
    results = check_api_contract(EmptyTtsApi())

    tts_result = next(result for result in results if result.name == "api:tts-stream")
    assert not tts_result.ok
    assert tts_result.detail == "contract returned an empty response"


def test_check_voice_sample_accepts_hotword_audio(tmp_path):
    sample_path = _write_wave(tmp_path / "voice.wav", sample_value=2000)
    api = VoiceSampleApi("hey Nuru please respond")

    result = check_voice_sample(api, _config(tmp_path / "state.sqlite3", "token"), sample_path)

    assert result.ok
    assert "wake word accepted" in result.detail
    assert api.generated_prompts


def test_check_voice_sample_rejects_quiet_audio(tmp_path):
    sample_path = _write_wave(tmp_path / "quiet.wav", sample_value=1)

    result = check_voice_sample(
        VoiceSampleApi("hey nuru"),
        _config(tmp_path / "state.sqlite3", "token"),
        sample_path,
    )

    assert not result.ok
    assert "VAD did not detect speech" in result.detail


def test_check_voice_sample_requires_wake_word(tmp_path):
    sample_path = _write_wave(tmp_path / "voice.wav", sample_value=2000)

    result = check_voice_sample(
        VoiceSampleApi("no hotword here"),
        _config(tmp_path / "state.sqlite3", "token"),
        sample_path,
    )

    assert not result.ok
    assert "did not include wake word" in result.detail


def test_run_diagnostics_can_include_voice_sample(tmp_path):
    sample_path = _write_wave(tmp_path / "voice.wav", sample_value=2000)
    config = _config(tmp_path / "state.sqlite3", token="token")

    report = run_diagnostics(
        config,
        api=VoiceSampleApi("hey nuru diagnostic"),
        include_ffmpeg=False,
        voice_sample_path=sample_path,
    )

    assert report.ok
    assert report.results[-1].name == "voice sample"


def test_check_discord_live_connects_and_disconnects(tmp_path):
    bot = FakeLiveBot()
    config = _config(tmp_path / "state.sqlite3", token="token")

    result = asyncio.run(
        check_discord_live(
            config,
            bot_factory=lambda config: bot,
        )
    )

    assert result.ok
    assert result.detail == "connected to voice channel 456"
    assert bot.started_with_token == "token"
    assert bot.voice_client.disconnected
    assert bot.closed


def test_check_discord_live_can_start_tts_playback(tmp_path):
    bot = FakeLiveBot()
    played = []

    async def fake_tts_player(voice_client, api, config, text):
        played.append((voice_client, api, text))

    result = asyncio.run(
        check_discord_live(
            _config(tmp_path / "state.sqlite3", token="token"),
            api=HealthyApi(),
            speak_text="diagnostic speech",
            bot_factory=lambda config: bot,
            tts_player=fake_tts_player,
        )
    )

    assert result.ok
    assert result.detail == "connected to voice channel 456 and started TTS playback"
    assert played[0][2] == "diagnostic speech"


def test_check_discord_live_requires_token(tmp_path):
    result = asyncio.run(
        check_discord_live(
            _config(tmp_path / "state.sqlite3", token=""),
            bot_factory=lambda config: FakeLiveBot(),
        )
    )

    assert not result.ok
    assert "DISCORD_TOKEN" in result.detail


def test_run_diagnostics_can_include_discord_live(tmp_path):
    bot = FakeLiveBot()
    report = run_diagnostics(
        _config(tmp_path / "state.sqlite3", token="token"),
        include_api=False,
        include_ffmpeg=False,
        include_discord_live=True,
        live_bot_factory=lambda config: bot,
    )

    assert report.ok
    assert report.results[-1].name == "discord live"


def test_run_diagnostics_reports_registered_slash_commands(tmp_path):
    config = _config(tmp_path / "state.sqlite3", token="token")

    report = run_diagnostics(config, include_api=False, include_ffmpeg=False)

    bot_result = next(result for result in report.results if result.name == "discord bot")
    assert bot_result.ok
    assert bot_result.detail == "registered 4 slash command(s)"


def test_load_config_can_skip_token_requirement(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DISCORD_TOKEN", raising=False)
    monkeypatch.delenv("TOKEN", raising=False)

    config = load_config(require_token=False)

    assert config.token == ""


def _config(database_path: Path, token: str) -> BotConfig:
    return BotConfig(
        token=token,
        api_base_url="http://127.0.0.1:8000",
        request_timeout_seconds=1.0,
        data_path=database_path,
        discord_proxy=None,
        activity_name="test",
        guild_id=123,
        voice_channel_id=456,
        text_channel_id=None,
        connect_voice_on_ready=False,
        record_voice_audio=False,
        enable_text_chat=True,
        enable_reaction_chat=False,
        enable_slash_commands=True,
        enable_idle_commentary=False,
        idle_commentary_seconds=30.0,
        voice_vad_threshold=500.0,
        recording_segment_seconds=5.0,
        wake_words=("nuru",),
        default_response_mode="text",
        memory_context_limit=6,
        tts_voice=None,
        ffmpeg_executable="ffmpeg",
    )


def _write_wave(path: Path, sample_value: int) -> Path:
    frames = b"".join(struct.pack("<h", sample_value) for _ in range(1600))
    with wave.open(str(path), "wb") as wave_file:
        wave_file.setnchannels(1)
        wave_file.setsampwidth(2)
        wave_file.setframerate(16000)
        wave_file.writeframes(frames)
    return path


class FakeLiveBot:
    def __init__(self):
        self.voice_client = FakeDiagnosticVoiceClient()
        self.channel = FakeDiagnosticVoiceChannel(self.voice_client)
        self.guild = FakeDiagnosticGuild(self.channel)
        self.started_with_token = None
        self.closed = False

    def event(self, callback):
        setattr(self, callback.__name__, callback)
        return callback

    def get_guild(self, guild_id):
        return self.guild if guild_id == 123 else None

    def get_channel(self, channel_id):
        return self.channel if channel_id == 456 else None

    async def start(self, token):
        self.started_with_token = token
        await self.on_ready()

    async def close(self):
        self.closed = True


class FakeDiagnosticGuild:
    def __init__(self, channel):
        self.channel = channel

    def get_channel(self, channel_id):
        return self.channel if channel_id == 456 else None


class FakeDiagnosticVoiceChannel:
    def __init__(self, voice_client):
        self.voice_client = voice_client

    async def connect(self):
        return self.voice_client


class FakeDiagnosticVoiceClient:
    def __init__(self):
        self.disconnected = False

    async def disconnect(self, *, force=False):
        self.disconnected = force
