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


def test_deliver_interaction_response_speaks_when_text_send_fails():
    channel = FailingChannel()
    voice_runtime = FakeVoiceRuntime(connected=True)

    asyncio.run(events.deliver_interaction_response(channel, _response("both"), voice_runtime))

    assert voice_runtime.spoken == ["hello"]


def test_deliver_interaction_response_sends_fallback_when_voice_playback_fails():
    channel = FakeChannel()
    voice_runtime = FailingVoiceRuntime()

    asyncio.run(events.deliver_interaction_response(channel, _response("voice"), voice_runtime))

    assert channel.sent == ["I could not play that in voice."]


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


def test_handle_text_message_uses_author_name_fallback(monkeypatch):
    monkeypatch.setattr(events, "DMChannel", FakeDmChannel)
    channel = FakeDmChannel()
    author = FakeNamedUser()
    message = FakeTextEventMessage(channel=channel, content="hello", author=author)
    companion = FakeCompanion(_response("text"))
    voice_runtime = FakeVoiceRuntime(connected=False)

    asyncio.run(
        events.handle_text_message(
            FakeClient(),
            message,
            companion,
            voice_runtime,
        )
    )

    assert channel.sent == ["hello"]
    assert companion.requests[0].author_name == "NameOnly"
    assert companion.requests[0].user_id == "789"


def test_handle_dm_reaction_uses_user_name_fallback(monkeypatch):
    monkeypatch.setattr(events, "DMChannel", FakeDmChannel)
    channel = FakeDmChannel()
    user = FakeNamedUser()
    companion = FakeCompanion(_response("text"))
    voice_runtime = FakeVoiceRuntime(connected=False)

    asyncio.run(
        events.handle_dm_reaction(
            FakeClient(),
            FakeReaction(FakeMessage(channel)),
            user,
            companion,
            voice_runtime,
        )
    )

    assert channel.sent == ["hello"]
    assert companion.requests[0].author_name == "NameOnly"
    assert companion.requests[0].content == "NameOnly's reaction is: :sparkles:"


def test_handle_text_message_sends_fallback_when_companion_crashes(monkeypatch):
    monkeypatch.setattr(events, "DMChannel", FakeDmChannel)
    channel = FakeDmChannel()
    message = FakeTextEventMessage(channel=channel, content="hello")
    companion = CrashingCompanion(_response("text"))
    voice_runtime = FakeVoiceRuntime(connected=False)

    asyncio.run(
        events.handle_text_message(
            FakeClient(),
            message,
            companion,
            voice_runtime,
        )
    )

    assert channel.sent == ["I could not finish that response."]
    assert companion.requests[0].content == "hello"


def test_handle_dm_reaction_sends_fallback_when_companion_crashes(monkeypatch):
    monkeypatch.setattr(events, "DMChannel", FakeDmChannel)
    channel = FakeDmChannel()
    user = FakeUser()
    companion = CrashingCompanion(_response("text"))
    voice_runtime = FakeVoiceRuntime(connected=False)

    asyncio.run(
        events.handle_dm_reaction(
            FakeClient(),
            FakeReaction(FakeMessage(channel)),
            user,
            companion,
            voice_runtime,
        )
    )

    assert channel.sent == ["I could not finish that response."]
    assert companion.requests[0].content == "tester_name's reaction is: :sparkles:"


def test_message_prompt_parts_ignores_empty_content_after_bot_mention():
    mention = FakeMention(bot=True, mention="<@999>")
    message = FakeTextMessage(content="<@999>   ", mentions=[mention])
    companion = FakeCompanion(_response("text"))

    prompt_parts = asyncio.run(events._message_prompt_parts(message, companion))

    assert prompt_parts == []


def test_message_prompt_parts_keeps_content_after_bot_mention():
    mention = FakeMention(bot=True, mention="<@999>")
    message = FakeTextMessage(content="<@999> hello there", mentions=[mention])
    companion = FakeCompanion(_response("text"))

    prompt_parts = asyncio.run(events._message_prompt_parts(message, companion))

    assert prompt_parts == ["hello there"]


def test_message_prompt_parts_skips_failed_image_and_empty_mention():
    mention = FakeMention(bot=True, mention="<@999>")
    attachment = FakeAttachment("image.png")
    message = FakeTextMessage(
        content="<@999>",
        attachments=[attachment],
        mentions=[mention],
    )
    companion = FakeCompanion(_response("text"), describe_error=events.NuruApiError("bad"))

    prompt_parts = asyncio.run(events._message_prompt_parts(message, companion))

    assert prompt_parts == []


def test_message_prompt_parts_keeps_text_when_image_read_crashes():
    attachment = FakeAttachment("image.png", read_error=RuntimeError("cdn failed"))
    message = FakeTextMessage(content="hello anyway", attachments=[attachment])
    companion = FakeCompanion(_response("text"))

    prompt_parts = asyncio.run(events._message_prompt_parts(message, companion))

    assert prompt_parts == ["hello anyway"]


def test_message_prompt_parts_keeps_text_when_image_description_crashes():
    attachment = FakeAttachment("image.png")
    message = FakeTextMessage(content="hello anyway", attachments=[attachment])
    companion = FakeCompanion(_response("text"), describe_error=RuntimeError("vision failed"))

    prompt_parts = asyncio.run(events._message_prompt_parts(message, companion))

    assert prompt_parts == ["hello anyway"]


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


class FailingChannel(FakeChannel):
    async def send(self, message):
        raise RuntimeError("send failed")


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


class FailingVoiceRuntime(FakeVoiceRuntime):
    def __init__(self):
        super().__init__(connected=True)

    async def speak(self, voice_client, text):
        raise RuntimeError("tts failed")


class FakeCompanion:
    def __init__(self, response, describe_error=None):
        self.response = response
        self.api = FakeApi(describe_error)
        self.requests = []

    async def respond(self, request):
        self.requests.append(request)
        return self.response


class CrashingCompanion(FakeCompanion):
    async def respond(self, request):
        self.requests.append(request)
        raise RuntimeError("state store unavailable")


class FakeApi:
    def __init__(self, describe_error=None):
        self.describe_error = describe_error

    def describe_image(self, image_data):
        if self.describe_error is not None:
            raise self.describe_error
        return f"{len(image_data)} bytes"


class FakeClient:
    user = object()


class FakeUser:
    id = 123
    name = "tester_name"
    display_name = "Tester"


class FakeNamedUser:
    id = 789
    name = "NameOnly"


class FakeMessage:
    def __init__(self, channel):
        self.channel = channel


class FakeTextEventMessage:
    def __init__(self, *, channel, content, author=None):
        self.author = author or FakeUser()
        self.channel = channel
        self.content = content
        self.attachments = []
        self.mentions = []


class FakeTextMessage:
    def __init__(self, content, attachments=None, mentions=None):
        self.content = content
        self.attachments = attachments or []
        self.mentions = mentions or []


class FakeAttachment:
    def __init__(self, filename, read_error=None):
        self.filename = filename
        self.read_error = read_error

    async def read(self):
        if self.read_error is not None:
            raise self.read_error
        return b"image"


class FakeMention:
    def __init__(self, *, bot, mention):
        self.bot = bot
        self.mention = mention


class FakeReaction:
    emoji = ":sparkles:"

    def __init__(self, message):
        self.message = message
