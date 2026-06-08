from __future__ import annotations

import logging
from dataclasses import dataclass

from .api import NuruApi, NuruApiError
from .config import BotConfig
from .memory import MemoryEntry, MemoryStore, fallback_embedding
from .observability import Observation, record_observation, start_timer
from .state import MoodState, PersonaState, ResponseMode, StateStore
from .tools import ToolCall, extract_tool_calls, remove_tool_call_lines, serialize_tool_call
from .working_memory import WorkingMemory


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class InteractionRequest:
    user_id: str
    channel_id: str
    author_name: str
    content: str
    source: str


@dataclass(frozen=True)
class InteractionResponse:
    text: str
    response_mode: ResponseMode
    mood: MoodState
    persona: PersonaState
    tool_calls: list[dict[str, object]] | None = None
    tool_results: list[dict[str, object]] | None = None


class CompanionService:
    def __init__(
        self,
        *,
        api: NuruApi,
        memory: MemoryStore,
        state: StateStore,
        config: BotConfig,
    ) -> None:
        self.api = api
        self.memory = memory
        self.state = state
        self.config = config
        self.working_memory = WorkingMemory(config.working_memory_limit)
        self._response_count = 0

    async def respond(self, request: InteractionRequest) -> InteractionResponse:
        started = start_timer()
        status = "ok"
        tool_count = 0
        try:
            response = await self._respond(request)
            tool_count = len(response.tool_calls or [])
            return response
        except Exception:
            status = "error"
            raise
        finally:
            self.record_response_observation(
                started=started,
                status=status,
                request=request,
                tool_count=tool_count,
            )

    async def _respond(self, request: InteractionRequest) -> InteractionResponse:
        user_embedding = self.embed_text(request.content)
        mood = self.state.adjust_mood_from_text(request.content)
        persona = self.state.get_persona()
        memories = self.find_relevant_memories(request, user_embedding)
        self.memory.add_entry(
            user_id=request.user_id,
            channel_id=request.channel_id,
            role="user",
            content=request.content,
            embedding=user_embedding,
        )
        prompt = self.build_prompt(request, mood, persona, memories)
        raw_response_text = self.api.generate(prompt)
        tool_calls = extract_tool_calls(raw_response_text)
        tool_results = self.execute_tool_calls(tool_calls)
        response_text = remove_tool_call_lines(raw_response_text)
        if not response_text and tool_results:
            response_text = self.format_tool_results(tool_results)
        response_text = self.moderate_generated_text(response_text)

        self.memory.add_entry(
            user_id=request.user_id,
            channel_id=request.channel_id,
            role="assistant",
            content=response_text,
            embedding=self.embed_text(response_text),
        )
        self.working_memory.add(
            user=request.content,
            assistant=response_text,
            source=request.source,
            metadata={
                "tool_calls": [serialize_tool_call(call) for call in tool_calls],
                "tool_results": tool_results,
            },
        )
        self._response_count += 1
        self.maybe_reflect(request)

        response_mode = self.state.get_response_mode(
            user_id=request.user_id,
            channel_id=request.channel_id,
            default=self.config.default_response_mode,
        )
        return InteractionResponse(
            text=response_text,
            response_mode=response_mode,
            mood=mood,
            persona=persona,
            tool_calls=[serialize_tool_call(call) for call in tool_calls],
            tool_results=tool_results,
        )

    def record_response_observation(
        self,
        *,
        started: float,
        status: str,
        request: InteractionRequest,
        tool_count: int,
    ) -> None:
        try:
            record_observation(
                self.config.observability_log_path,
                Observation(
                    event="companion.respond",
                    latency_seconds=start_timer() - started,
                    metadata={
                        "status": status,
                        "source": request.source,
                        "user_id": request.user_id,
                        "channel_id": request.channel_id,
                        "tool_count": tool_count,
                    },
                ),
            )
        except OSError:
            LOGGER.warning("Failed to write response observation", exc_info=True)

    def idle_prompt(self, *, user_id: str, channel_id: str, author_name: str) -> str:
        mood = self.state.get_mood()
        persona = self.state.get_persona()
        memories = self.memory.recent(
            user_id=user_id,
            channel_id=channel_id,
            limit=min(3, self.config.memory_context_limit),
        )
        prompt = self.build_prompt(
            InteractionRequest(
                user_id=user_id,
                channel_id=channel_id,
                author_name=author_name,
                content="The user is alone in voice and has been silent. Make a short idle comment.",
                source="idle",
            ),
            mood,
            persona,
            memories,
        )
        response_text = self.moderate_generated_text(self.api.generate(prompt))
        self.memory.add_entry(
            user_id=user_id,
            channel_id=channel_id,
            role="assistant",
            content=response_text,
            embedding=self.embed_text(response_text),
        )
        return response_text

    def embed_text(self, text: str) -> list[float]:
        try:
            return self.api.embed(text)
        except NuruApiError:
            LOGGER.warning("Falling back to local deterministic embedding", exc_info=True)
            return fallback_embedding(text)

    def reset_memory(
        self,
        *,
        user_id: str | None = None,
        channel_id: str | None = None,
    ) -> int:
        return self.memory.reset(user_id=user_id, channel_id=channel_id)

    def find_relevant_memories(
        self,
        request: InteractionRequest,
        query_embedding: list[float],
    ) -> list[MemoryEntry]:
        limit = max(0, self.config.memory_context_limit)
        if limit == 0:
            return []

        scopes = (
            (request.user_id, request.channel_id),
            (request.user_id, None),
            (None, request.channel_id),
        )
        memories: list[MemoryEntry] = []
        seen_ids: set[int] = set()

        for user_id, channel_id in scopes:
            matches = self.memory.search(
                query_embedding=query_embedding,
                user_id=user_id,
                channel_id=channel_id,
                limit=limit,
            )
            for entry in matches:
                if entry.id in seen_ids:
                    continue

                memories.append(entry)
                seen_ids.add(entry.id)
                if len(memories) >= limit:
                    return memories

        return memories

    def build_prompt(
        self,
        request: InteractionRequest,
        mood: MoodState,
        persona: PersonaState,
        memories: list[MemoryEntry],
    ) -> str:
        memory_lines = "\n".join(
            (
                f"- {entry.role} for user {entry.user_id} "
                f"in channel {entry.channel_id}: {entry.content}"
            )
            for entry in memories
        )
        if not memory_lines:
            memory_lines = "- No relevant memories yet."
        working_memory = self.working_memory.format_context()
        if not working_memory:
            working_memory = "- No recent exchanges yet."

        return (
            f"You are Nuru, a Discord AI VTuber presence.\n"
            f"Persona: {persona.name}. {persona.prompt}\n"
            f"Mood: {mood.label} with energy {mood.energy:.2f}.\n"
            f"Source: {request.source}.\n"
            f"Relevant long-term memories:\n{memory_lines}\n\n"
            f"Recent working memory:\n{working_memory}\n\n"
            "You may emit one JSON tool call line when useful. Supported actions: "
            "calendar, set_reminder, list_reminders, calculator.\n"
            f"{request.author_name}: {request.content}\n"
            "Nuru:"
        )

    def execute_tool_calls(self, tool_calls: list[ToolCall]) -> list[dict[str, object]]:
        results: list[dict[str, object]] = []
        execute_tool_call = getattr(self.api, "execute_tool_call", None)
        for tool_call in tool_calls:
            if not callable(execute_tool_call):
                results.append(
                    {
                        "action": tool_call.action,
                        "success": False,
                        "result": "Tool execution is unavailable.",
                    }
                )
                continue
            try:
                results.append(execute_tool_call(serialize_tool_call(tool_call)))
            except NuruApiError:
                LOGGER.warning("Tool execution failed", exc_info=True)
                results.append(
                    {
                        "action": tool_call.action,
                        "success": False,
                        "result": "Tool execution failed.",
                    }
                )
        return results

    def moderate_generated_text(self, text: str) -> str:
        if not self.config.enable_moderation or not text.strip():
            return text
        moderate = getattr(self.api, "moderate", None)
        if not callable(moderate):
            return text
        try:
            label, _categories = moderate(text)
        except NuruApiError:
            LOGGER.warning("Moderation failed; keeping generated text", exc_info=True)
            return text
        if label.casefold() == "safe":
            return text
        return "Filtered."

    def maybe_reflect(self, request: InteractionRequest) -> None:
        interval = self.config.reflection_interval_messages
        if interval <= 0 or self._response_count % interval != 0:
            return
        memories = self.memory.recent(
            user_id=request.user_id,
            channel_id=request.channel_id,
            limit=self.config.reflection_memory_limit,
        )
        if not memories:
            return
        memory_lines = "\n".join(f"- {entry.role}: {entry.content}" for entry in memories)
        try:
            summary = self.api.generate(
                "Privately summarize the stream-relevant memories below.\n" + memory_lines
            )
            monologue = self.api.generate(
                "Write one private internal monologue sentence that updates Nuru's mood."
            )
        except NuruApiError:
            LOGGER.warning("Reflection failed", exc_info=True)
            return
        self.state.adjust_mood_from_text(monologue)
        self.memory.add_entry(
            user_id=request.user_id,
            channel_id=request.channel_id,
            role="reflection",
            content=summary,
            embedding=self.embed_text(summary),
        )
        self.memory.add_entry(
            user_id=request.user_id,
            channel_id=request.channel_id,
            role="internal_monologue",
            content=monologue,
            embedding=self.embed_text(monologue),
        )

    @staticmethod
    def format_tool_results(tool_results: list[dict[str, object]]) -> str:
        first = tool_results[0]
        action = str(first.get("action", "tool"))
        result = first.get("result")
        if action == "calculator" and isinstance(result, dict):
            return f"Calculated: {result.get('value')}"
        if action == "set_reminder":
            return "Reminder set."
        if action == "list_reminders":
            return f"Reminders: {result}"
        if action == "calendar":
            return f"Calendar: {result}"
        return "Done."
