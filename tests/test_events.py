import asyncio

import nuru_bot.events as events
from nuru_bot.companion import InteractionRequest, InteractionResponse
from nuru_bot.state import MoodState, PersonaState


def test_deliver_interaction_response_sends_text_and_voice():
    channel = FakeChannel()
    voice_runtime = FakeVoiceRuntime(connected=True)
    response = _response("both")

    asyncio.run(events.deliver_interaction_response(channel, response, voice_runtime))

    assert channel.sent == ["hello"]
    assert voice_runtime.spoken == ["hello"]


def test_deliver_interaction_response_warns_when_voice_only_without_connection():
    channel = FakeChannel()
    voice_runtime = FakeVoiceRuntime(connected=False)

    asyncio.run(
        events.deliver_interaction_response(channel, _response("voice"), voice_runtime)
    )

    assert channel.sent == ["I am not connected to a voice channel yet."]
    assert voice_runtime.spoken == []


def test_handle_dm_reaction_honors_voice_response_mode(monkeypatch):
    monkeypatch.setattr(events, "DMChannel", FakeDmChannel)
    channel = FakeDmChannel()
    user = FakeUser()
    companion = FakeCompanion(_response("voice"))
    voice_runtime = FakeVoiceRuntime(connected=True)

    asyncio.run(
        events.handle_dm_reaction(
            FakeClient(),
            FakeReaction(FakeMessage(channel)),
            user,
            companion,
            voice_runtime,
        )
    )

    assert channel.sent == []
    assert voice_runtime.spoken == ["hello"]
    assert companion.requests == [
        InteractionRequest(
            user_id="123",
            channel_id="456",
            author_name="Tester",
            content="tester_name's reaction is: :sparkles:",
            source="reaction",
        )
    ]


def _response(response_mode):
    return InteractionResponse(
        text="hello",
        response_mode=response_mode,
        mood=MoodState(label="curious", energy=0.5, updated_at="now"),
        persona=PersonaState(name="nuru", prompt="prompt", updated_at="now"),
    )


class FakeChannel:
    def __init__(self):
        self.sent = []

    async def send(self, message):
        self.sent.append(message)


class FakeDmChannel(FakeChannel):
    id = 456


class FakeVoiceClient:
    def __init__(self, connected):
        self.connected = connected

    def is_connected(self):
        return self.connected


class FakeVoiceRuntime:
    def __init__(self, connected):
        self.voice_client = FakeVoiceClient(connected) if connected else None
        self.spoken = []

    async def speak(self, voice_client, text):
        self.spoken.append(text)


class FakeCompanion:
    def __init__(self, response):
        self.response = response
        self.requests = []

    async def respond(self, request):
        self.requests.append(request)
        return self.response


class FakeClient:
    user = object()


class FakeUser:
    id = 123
    name = "tester_name"
    display_name = "Tester"


class FakeMessage:
    def __init__(self, channel):
        self.channel = channel


class FakeReaction:
    emoji = ":sparkles:"

    def __init__(self, message):
        self.message = message
