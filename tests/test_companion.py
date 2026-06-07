import asyncio

from nuru_bot.companion import CompanionService, InteractionRequest
from nuru_bot.memory import MemoryStore
from nuru_bot.state import StateStore

from .helpers import make_config


class FakeApi:
    def __init__(self):
        self.prompts = []

    def embed(self, text):
        return [float(len(text)), 1.0]

    def generate(self, prompt):
        self.prompts.append(prompt)
        return "remembered response"


def test_companion_stores_user_and_assistant_entries_in_same_scope():
    memory = MemoryStore(":memory:")
    state = StateStore(":memory:")
    state.set_response_mode(scope_type="user", scope_id="user-1", mode="both")
    service = CompanionService(
        api=FakeApi(),
        memory=memory,
        state=state,
        config=make_config(),
    )

    response = asyncio.run(
        service.respond(
            InteractionRequest(
                user_id="user-1",
                channel_id="channel-1",
                author_name="Tester",
                content="thanks for remembering osu",
                source="text",
            )
        )
    )

    entries = memory.recent(user_id="user-1", channel_id="channel-1")
    assert [entry.role for entry in entries] == ["user", "assistant"]
    assert entries[1].content == "remembered response"
    assert response.response_mode == "both"
    assert response.mood.energy > 0.5


def test_companion_prompt_does_not_treat_current_message_as_memory():
    api = FakeApi()
    memory = MemoryStore(":memory:")
    state = StateStore(":memory:")
    service = CompanionService(
        api=api,
        memory=memory,
        state=state,
        config=make_config(),
    )

    asyncio.run(
        service.respond(
            InteractionRequest(
                user_id="user-1",
                channel_id="channel-1",
                author_name="Tester",
                content="brand new active turn",
                source="text",
            )
        )
    )

    prompt = api.prompts[0]
    assert "- No relevant memories yet." in prompt
    assert prompt.count("brand new active turn") == 1


def test_idle_prompt_uses_recent_scoped_memories():
    api = FakeApi()
    memory = MemoryStore(":memory:")
    state = StateStore(":memory:")
    memory.add_entry(
        user_id="user-1",
        channel_id="voice-1",
        role="user",
        content="I like quiet commentary",
        embedding=[1.0],
    )
    service = CompanionService(
        api=api,
        memory=memory,
        state=state,
        config=make_config(),
    )

    assert service.idle_prompt(
        user_id="user-1",
        channel_id="voice-1",
        author_name="Tester",
    ) == "remembered response"

    entries = memory.recent(user_id="user-1", channel_id="voice-1")
    assert "quiet commentary" in api.prompts[0]
    assert [entry.role for entry in entries] == ["user", "assistant"]
    assert entries[1].content == "remembered response"
