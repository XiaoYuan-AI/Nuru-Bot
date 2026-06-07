import asyncio
import struct

from nuru_bot.companion import InteractionResponse
from nuru_bot.state import MoodState, PersonaState
from nuru_bot.voice import VoiceRuntime

from .helpers import make_config


class FakeApi:
    def __init__(self, transcript):
        self.transcript = transcript

    def transcribe_audio(self, audio_data):
        return self.transcript

    def stream_tts(self, text, *, voice=None):
        yield b"audio"


class FakeCompanion:
    def __init__(self, response_mode="voice"):
        self.requests = []
        self.response_mode = response_mode

    async def respond(self, request):
        self.requests.append(request)
        return InteractionResponse(
            text="voice reply",
            response_mode=self.response_mode,
            mood=MoodState(label="curious", energy=0.5, updated_at="now"),
            persona=PersonaState(name="nuru", prompt="test", updated_at="now"),
        )


class CapturingVoiceRuntime(VoiceRuntime):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.spoken = []

    async def speak(self, voice_client, text):
        self.spoken.append(text)


class FakeVoiceClient:
    def __init__(self):
        self.channel = type("Channel", (), {"id": 42})()

    def is_connected(self):
        return True


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

    asyncio.run(runtime.recording_callback(FakeSink({123: audio}), FakeVoiceClient()))

    assert companion.requests[0].content == "hey nuru say hello"
    assert companion.requests[0].channel_id == "42"
    assert runtime.spoken == ["voice reply"]


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


def _loud_pcm():
    return b"".join(struct.pack("<h", 2000) for _ in range(200))


async def _append_async(messages, text):
    messages.append(text)
