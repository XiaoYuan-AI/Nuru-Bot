import asyncio

from nuru_bot.api import NuruApiError
from nuru_bot.companion import CompanionService, InteractionRequest
from nuru_bot.memory import MemoryStore
from nuru_bot.state import StateStore

from .helpers import make_config


class FakeApi:
    def __init__(self):
        self.prompts = []
        self.tool_calls = []

    def embed(self, text):
        return [float(len(text)), 1.0]

    def generate(self, prompt):
        self.prompts.append(prompt)
        return "remembered response"

    def moderate(self, text):
        return "Safe", []

    def execute_tool_call(self, tool_call):
        self.tool_calls.append(tool_call)
        return {"action": tool_call["action"], "success": True, "result": "ok"}


class FailingEmbeddingApi(FakeApi):
    def embed(self, text):
        raise NuruApiError("malformed embedding")


class ToolApi(FakeApi):
    def generate(self, prompt):
        self.prompts.append(prompt)
        return (
            "I'll calculate it.\n"
            '{"action": "calculator", "parameters": {"expression": "2 + 2"}}'
        )

    def execute_tool_call(self, tool_call):
        self.tool_calls.append(tool_call)
        return {
            "action": "calculator",
            "success": True,
            "result": {"expression": "2 + 2", "value": 4},
        }


class UnsafeToolApi(FakeApi):
    def generate(self, prompt):
        self.prompts.append(prompt)
        return '{"action": "calculator", "parameters": {"expression": "2 + 2"}, "safe": false}'


class UnsafeApi(FakeApi):
    def generate(self, prompt):
        self.prompts.append(prompt)
        return "unsafe response"

    def moderate(self, text):
        return "Unsafe", ["test"]


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


def test_companion_executes_tool_calls_and_keeps_visible_text():
    api = ToolApi()
    memory = MemoryStore(":memory:")
    state = StateStore(":memory:")
    service = CompanionService(
        api=api,
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
                content="what is 2 + 2?",
                source="text",
            )
        )
    )

    assert response.text == "I'll calculate it."
    assert response.tool_calls[0]["action"] == "calculator"
    assert response.tool_results[0]["result"]["value"] == 4
    assert api.tool_calls[0]["parameters"]["expression"] == "2 + 2"


def test_companion_skips_unsafe_tool_calls():
    api = UnsafeToolApi()
    memory = MemoryStore(":memory:")
    state = StateStore(":memory:")
    service = CompanionService(
        api=api,
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
                content="run unsafe calculator",
                source="text",
            )
        )
    )

    assert response.text == "Tool call was marked unsafe."
    assert response.tool_calls[0]["safe"] is False
    assert response.tool_results == [
        {
            "action": "calculator",
            "success": False,
            "result": "Tool call was marked unsafe.",
        }
    ]
    assert api.tool_calls == []


def test_companion_moderates_unsafe_output():
    memory = MemoryStore(":memory:")
    state = StateStore(":memory:")
    service = CompanionService(
        api=UnsafeApi(),
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
                content="say something risky",
                source="text",
            )
        )
    )

    assert response.text == "Filtered."


def test_companion_falls_back_when_embedding_api_returns_bad_payload():
    memory = MemoryStore(":memory:")
    state = StateStore(":memory:")
    service = CompanionService(
        api=FailingEmbeddingApi(),
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
                content="remember this despite embedding failure",
                source="text",
            )
        )
    )

    entries = memory.recent(user_id="user-1", channel_id="channel-1")
    assert response.text == "remembered response"
    assert [entry.role for entry in entries] == ["user", "assistant"]
    assert all(entry.embedding for entry in entries)


def test_companion_prompt_uses_user_and_channel_memory_context():
    api = FakeApi()
    memory = MemoryStore(":memory:")
    state = StateStore(":memory:")
    memory.add_entry(
        user_id="user-1",
        channel_id="channel-2",
        role="user",
        content="I love rhythm games",
        embedding=[1.0],
    )
    memory.add_entry(
        user_id="user-2",
        channel_id="channel-1",
        role="user",
        content="This channel likes karaoke",
        embedding=[1.0],
    )
    service = CompanionService(
        api=api,
        memory=memory,
        state=state,
        config=make_config(memory_context_limit=4),
    )

    asyncio.run(
        service.respond(
            InteractionRequest(
                user_id="user-1",
                channel_id="channel-1",
                author_name="Tester",
                content="what do you remember?",
                source="text",
            )
        )
    )

    prompt = api.prompts[0]
    assert "user for user user-1 in channel channel-2: I love rhythm games" in prompt
    assert "user for user user-2 in channel channel-1: This channel likes karaoke" in prompt


def test_companion_uses_working_memory_context_between_turns():
    api = FakeApi()
    memory = MemoryStore(":memory:")
    state = StateStore(":memory:")
    service = CompanionService(
        api=api,
        memory=memory,
        state=state,
        config=make_config(),
    )

    for content in ("remember strawberry speedrun", "what was recent?"):
        asyncio.run(
            service.respond(
                InteractionRequest(
                    user_id="user-1",
                    channel_id="channel-1",
                    author_name="Tester",
                    content=content,
                    source="text",
                )
            )
        )

    assert "strawberry" in api.prompts[1]
    assert service.working_memory.topics()[0] == "remember"


def test_companion_reflection_adds_private_memory():
    api = FakeApi()
    memory = MemoryStore(":memory:")
    state = StateStore(":memory:")
    service = CompanionService(
        api=api,
        memory=memory,
        state=state,
        config=make_config(reflection_interval_messages=1),
    )

    asyncio.run(
        service.respond(
            InteractionRequest(
                user_id="user-1",
                channel_id="channel-1",
                author_name="Tester",
                content="thanks for the rhythm game memory",
                source="text",
            )
        )
    )

    roles = [entry.role for entry in memory.recent(user_id="user-1", channel_id="channel-1")]
    assert "reflection" in roles
    assert "internal_monologue" in roles


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
