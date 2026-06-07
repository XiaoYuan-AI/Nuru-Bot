from __future__ import annotations

import logging
from dataclasses import dataclass

from .api import NuruApi, NuruApiError
from .config import BotConfig
from .memory import MemoryEntry, MemoryStore, fallback_embedding
from .state import MoodState, PersonaState, ResponseMode, StateStore


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

    async def respond(self, request: InteractionRequest) -> InteractionResponse:
        user_embedding = self.embed_text(request.content)
        mood = self.state.adjust_mood_from_text(request.content)
        persona = self.state.get_persona()
        memories = self.memory.search(
            query_embedding=user_embedding,
            user_id=request.user_id,
            channel_id=request.channel_id,
            limit=self.config.memory_context_limit,
        )
        self.memory.add_entry(
            user_id=request.user_id,
            channel_id=request.channel_id,
            role="user",
            content=request.content,
            embedding=user_embedding,
        )
        prompt = self.build_prompt(request, mood, persona, memories)
        response_text = self.api.generate(prompt)

        self.memory.add_entry(
            user_id=request.user_id,
            channel_id=request.channel_id,
            role="assistant",
            content=response_text,
            embedding=self.embed_text(response_text),
        )

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
        )

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
        response_text = self.api.generate(prompt)
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

    def build_prompt(
        self,
        request: InteractionRequest,
        mood: MoodState,
        persona: PersonaState,
        memories: list[MemoryEntry],
    ) -> str:
        memory_lines = "\n".join(
            f"- {entry.role} in channel {entry.channel_id}: {entry.content}"
            for entry in memories
        )
        if not memory_lines:
            memory_lines = "- No relevant memories yet."

        return (
            f"You are Nuru, a Discord AI VTuber presence.\n"
            f"Persona: {persona.name}. {persona.prompt}\n"
            f"Mood: {mood.label} with energy {mood.energy:.2f}.\n"
            f"Source: {request.source}.\n"
            f"Relevant long-term memories:\n{memory_lines}\n\n"
            f"{request.author_name}: {request.content}\n"
            "Nuru:"
        )
