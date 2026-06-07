import asyncio
import struct

from nuru_bot.api import NuruApiError
from nuru_bot.companion import InteractionResponse
from nuru_bot.state import MoodState, PersonaState
from nuru_bot.voice import VoiceRuntime, connect_voice_channel

from .helpers import make_config


class FakeApi:
    def __init__(self, transcript):
        self.transcript = transcript
        self.tts_requests = []

    def transcribe_audio(self, audio_data):
        if isinstance(self.transcript, Exception):
            raise self.transcript
        return self.transcript

    def stream_tts(self, text, *, voice=None):
        self.tts_requests.append((text, voice))
        yield b"audio"


class FakeCompanion:
    def __init__(self, response_mode="voice"):
        self.requests = []
        self.idle_requests = []
        self.response_mode = response_mode

    async def respond(self, request):
        self.requests.append(request)
        return InteractionResponse(
            text="voice reply",
            response_mode=self.response_mode,
            mood=MoodState(label="curious", energy=0.5, updated_at="now"),
            persona=PersonaState(name="nuru", prompt="test", updated_at="now"),
        )

    def idle_prompt(self, *, user_id, channel_id, author_name):
        self.idle_requests.append((user_id, channel_id, author_name))
        return "idle reply"


class FailingCompanion(FakeCompanion):
    async def respond(self, request):
        self.requests.append(request)
        raise NuruApiError("model unavailable")


class CrashingCompanion(FakeCompanion):
    async def respond(self, request):
        self.requests.append(request)
        raise RuntimeError("memory database unavailable")


class CapturingVoiceRuntime(VoiceRuntime):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.spoken = []

    async def speak(self, voice_client, text):
        self.spoken.append(text)


class FailingSpeakVoiceRuntime(CapturingVoiceRuntime):
    async def speak(self, voice_client, text):
        raise NuruApiError("tts unavailable")


class CrashingSpeakVoiceRuntime(CapturingVoiceRuntime):
    async def speak(self, voice_client, text):
        raise RuntimeError("ffmpeg unavailable")


class FakeVoiceClient:
    def __init__(self, *, members=None, playing=False):
        self.channel = type("Channel", (), {"id": 42, "members": members or []})()
        self.playing = playing
        self.played_sources = []
        self.stopped = False

    def is_connected(self):
        return True

    def is_playing(self):
        return self.playing

    def stop(self):
        self.stopped = True
        self.playing = False

    def play(self, source):
        self.played_sources.append(source)


class FakeRecordingVoiceClient(FakeVoiceClient):
    def __init__(self):
        super().__init__()
        self.recording = False
        self.started = False
        self.stopped_count = 0

    def start_recording(self, sink, callback, *args):
        self.recording = True
        self.started = True
        self.recording_callback = callback
        self.recording_args = args

    def stop_recording(self):
        self.recording = False
        self.stopped_count += 1


class FakeSink:
    def __init__(self, audio_data):
        self.audio_data = audio_data


def test_recording_callback_ignores_audio_without_hotword():
    companion = FakeCompanion()
    runtime = CapturingVoiceRuntime(
        config=make_config(voice_vad_threshold=10),
        api=FakeApi("just chatting"),
        companion=companion,
    )
    audio = _loud_pcm()

    asyncio.run(runtime.recording_callback(FakeSink({123: audio}), FakeVoiceClient()))

    assert companion.requests == []
    assert runtime.spoken == []


def test_recording_callback_responds_after_vad_and_hotword():
    companion = FakeCompanion(response_mode="voice")
    runtime = CapturingVoiceRuntime(
        config=make_config(voice_vad_threshold=10),
        api=FakeApi("hey nuru say hello"),
        companion=companion,
    )
    audio = _loud_pcm()
    member = type("Member", (), {"id": 123, "display_name": "Voice User"})()

    asyncio.run(
        runtime.recording_callback(
            FakeSink({123: audio}),
            FakeVoiceClient(members=[member]),
        )
    )

    assert companion.requests[0].content == "hey nuru say hello"
    assert companion.requests[0].channel_id == "42"
    assert companion.requests[0].author_name == "Voice User"
    assert runtime.spoken == ["voice reply"]


def test_recording_callback_uses_user_id_when_member_name_is_unavailable():
    companion = FakeCompanion(response_mode="voice")
    runtime = CapturingVoiceRuntime(
        config=make_config(voice_vad_threshold=10),
        api=FakeApi("hey nuru fallback name"),
        companion=companion,
    )

    asyncio.run(runtime.recording_callback(FakeSink({123: _loud_pcm()}), FakeVoiceClient()))

    assert companion.requests[0].author_name == "123"


def test_recording_callback_sends_text_to_configured_channel():
    companion = FakeCompanion(response_mode="text")
    runtime = CapturingVoiceRuntime(
        config=make_config(voice_vad_threshold=10, text_channel_id=99),
        api=FakeApi("nuru respond in text"),
        companion=companion,
    )
    sent_messages = []
    text_channel = type(
        "TextChannel",
        (),
        {"send": lambda self, text: _append_async(sent_messages, text)},
    )()
    runtime.client = type(
        "Client",
        (),
        {
            "get_channel": (
                lambda self, channel_id: text_channel if channel_id == 99 else None
            )
        },
    )()

    asyncio.run(runtime.recording_callback(FakeSink({123: _loud_pcm()}), FakeVoiceClient()))

    assert sent_messages == ["voice reply"]
    assert runtime.spoken == []


def test_recording_callback_restarts_recording_when_companion_fails():
    companion = FailingCompanion()
    runtime = CapturingVoiceRuntime(
        config=make_config(
            record_voice_audio=True,
            recording_segment_seconds=10,
            voice_vad_threshold=10,
        ),
        api=FakeApi("hey nuru fail safely"),
        companion=companion,
    )
    voice_client = FakeRecordingVoiceClient()

    async def run_callback():
        await runtime.recording_callback(FakeSink({123: _loud_pcm()}), voice_client)
        runtime.close()
        await asyncio.sleep(0)

    asyncio.run(run_callback())

    assert companion.requests[0].content == "hey nuru fail safely"
    assert voice_client.started
    assert voice_client.recording
    assert runtime.spoken == []


def test_recording_callback_restarts_recording_when_companion_crashes():
    companion = CrashingCompanion()
    runtime = CapturingVoiceRuntime(
        config=make_config(
            record_voice_audio=True,
            recording_segment_seconds=10,
            voice_vad_threshold=10,
        ),
        api=FakeApi("hey nuru recover safely"),
        companion=companion,
    )
    voice_client = FakeRecordingVoiceClient()

    async def run_callback():
        await runtime.recording_callback(FakeSink({123: _loud_pcm()}), voice_client)
        runtime.close()
        await asyncio.sleep(0)

    asyncio.run(run_callback())

    assert companion.requests[0].content == "hey nuru recover safely"
    assert voice_client.started
    assert voice_client.recording
    assert runtime.spoken == []


def test_recording_callback_restarts_recording_when_transcription_crashes():
    runtime = CapturingVoiceRuntime(
        config=make_config(
            record_voice_audio=True,
            recording_segment_seconds=10,
            voice_vad_threshold=10,
        ),
        api=FakeApi(RuntimeError("decoder crashed")),
        companion=FakeCompanion(),
    )
    voice_client = FakeRecordingVoiceClient()

    async def run_callback():
        await runtime.recording_callback(FakeSink({123: _loud_pcm()}), voice_client)
        runtime.close()
        await asyncio.sleep(0)

    asyncio.run(run_callback())

    assert voice_client.started
    assert voice_client.recording
    assert runtime.spoken == []


def test_recording_callback_restarts_recording_when_tts_delivery_fails():
    runtime = FailingSpeakVoiceRuntime(
        config=make_config(
            record_voice_audio=True,
            recording_segment_seconds=10,
            voice_vad_threshold=10,
        ),
        api=FakeApi("hey nuru tts failure"),
        companion=FakeCompanion(response_mode="voice"),
    )
    voice_client = FakeRecordingVoiceClient()

    async def run_callback():
        await runtime.recording_callback(FakeSink({123: _loud_pcm()}), voice_client)
        runtime.close()
        await asyncio.sleep(0)

    asyncio.run(run_callback())

    assert voice_client.started
    assert voice_client.recording


def test_start_recording_stops_segment_after_configured_delay():
    runtime = CapturingVoiceRuntime(
        config=make_config(recording_segment_seconds=0.01),
        api=FakeApi("nuru"),
        companion=FakeCompanion(),
    )
    voice_client = FakeRecordingVoiceClient()

    async def run_segment():
        runtime.start_recording(voice_client)
        await asyncio.sleep(0.05)

    asyncio.run(run_segment())

    assert voice_client.started
    assert not voice_client.recording
    assert voice_client.stopped_count == 1


def test_close_cancels_pending_recording_stop_task():
    runtime = CapturingVoiceRuntime(
        config=make_config(recording_segment_seconds=10),
        api=FakeApi("nuru"),
        companion=FakeCompanion(),
    )
    voice_client = FakeRecordingVoiceClient()

    async def run_close():
        runtime.start_recording(voice_client)
        runtime.close()
        await asyncio.sleep(0)

    asyncio.run(run_close())

    assert voice_client.recording
    assert runtime._recording_stop_task.cancelled()


def test_speak_streams_tts_chunks_into_ffmpeg_source(monkeypatch):
    captured_audio = []

    class FakeAudioSource:
        def __init__(self, stream, *, pipe, executable):
            captured_audio.append((stream.read(), pipe, executable))

    monkeypatch.setattr("nuru_bot.voice.FFmpegPCMAudio", FakeAudioSource)
    api = FakeApi("nuru")
    voice_client = FakeVoiceClient(playing=True)
    runtime = VoiceRuntime(
        config=make_config(tts_voice="vtuber", ffmpeg_executable="ffmpeg-test"),
        api=api,
        companion=FakeCompanion(),
    )

    asyncio.run(runtime.speak(voice_client, "hello stream"))

    assert api.tts_requests == [("hello stream", "vtuber")]
    assert captured_audio == [(b"audio", True, "ffmpeg-test")]
    assert voice_client.stopped
    assert len(voice_client.played_sources) == 1


def test_idle_commentary_runs_after_silence_when_one_user_is_alone():
    user = type("Member", (), {"id": 321, "display_name": "Solo", "bot": False})()
    companion = FakeCompanion()
    runtime = CapturingVoiceRuntime(
        config=make_config(idle_commentary_seconds=30),
        api=FakeApi("nuru"),
        companion=companion,
    )
    runtime.voice_client = FakeVoiceClient(members=[user])
    runtime.last_voice_activity_at = 0.0
    runtime.last_idle_commentary_at = 0.0

    assert asyncio.run(runtime.maybe_run_idle_commentary())
    assert companion.idle_requests == [("321", "42", "Solo")]
    assert runtime.spoken == ["idle reply"]
    assert runtime.last_idle_commentary_at > 0.0


def test_idle_commentary_returns_false_when_delivery_crashes():
    user = type("Member", (), {"id": 321, "display_name": "Solo", "bot": False})()
    companion = FakeCompanion()
    runtime = CrashingSpeakVoiceRuntime(
        config=make_config(idle_commentary_seconds=30),
        api=FakeApi("nuru"),
        companion=companion,
    )
    runtime.voice_client = FakeVoiceClient(members=[user])
    runtime.last_voice_activity_at = 0.0
    runtime.last_idle_commentary_at = 0.0

    assert not asyncio.run(runtime.maybe_run_idle_commentary())
    assert companion.idle_requests == [("321", "42", "Solo")]
    assert runtime.last_idle_commentary_at == 0.0


def test_idle_commentary_skips_when_multiple_humans_are_present():
    users = [
        type("Member", (), {"id": 1, "display_name": "One", "bot": False})(),
        type("Member", (), {"id": 2, "display_name": "Two", "bot": False})(),
    ]
    companion = FakeCompanion()
    runtime = CapturingVoiceRuntime(
        config=make_config(idle_commentary_seconds=30),
        api=FakeApi("nuru"),
        companion=companion,
    )
    runtime.voice_client = FakeVoiceClient(members=users)
    runtime.last_voice_activity_at = 0.0

    assert not asyncio.run(runtime.maybe_run_idle_commentary())
    assert companion.idle_requests == []


def test_connect_voice_channel_falls_back_to_client_channel_lookup():
    voice_client = FakeVoiceClient()
    channel = FakeConnectChannel(voice_client)
    client = FakeConnectClient(
        guild=FakeConnectGuild(channel=None),
        channel=channel,
    )

    connected = asyncio.run(
        connect_voice_channel(
            client,
            make_config(guild_id=123, voice_channel_id=456),
        )
    )

    assert connected is voice_client
    assert channel.connected


def test_connect_voice_channel_returns_none_when_connect_fails():
    channel = FakeConnectChannel(RuntimeError("voice unavailable"))
    client = FakeConnectClient(
        guild=FakeConnectGuild(channel=channel),
        channel=None,
    )

    connected = asyncio.run(
        connect_voice_channel(
            client,
            make_config(guild_id=123, voice_channel_id=456),
        )
    )

    assert connected is None


def _loud_pcm():
    return b"".join(struct.pack("<h", 2000) for _ in range(200))


async def _append_async(messages, text):
    messages.append(text)


class FakeConnectClient:
    def __init__(self, *, guild, channel):
        self.guild = guild
        self.channel = channel

    def get_guild(self, guild_id):
        return self.guild if guild_id == 123 else None

    def get_channel(self, channel_id):
        return self.channel if channel_id == 456 else None


class FakeConnectGuild:
    def __init__(self, *, channel):
        self.channel = channel

    def get_channel(self, channel_id):
        return self.channel if channel_id == 456 else None


class FakeConnectChannel:
    def __init__(self, result):
        self.result = result
        self.connected = False

    async def connect(self):
        if isinstance(self.result, Exception):
            raise self.result

        self.connected = True
        return self.result
