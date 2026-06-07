from __future__ import annotations

import discord

from .companion import CompanionService
from .state import DEFAULT_PERSONA_PROMPTS, ResponseMode, StateStore


type CommandScope = str


def register_commands(
    bot: discord.Bot,
    *,
    companion: CompanionService,
    state: StateStore,
) -> None:
    @bot.slash_command(
        name="memory_reset",
        description="Clear Nuru's remembered chat history for you or this channel.",
    )
    async def memory_reset(
        ctx: discord.ApplicationContext,
        scope: discord.Option(str, choices=["me", "channel"]) = "me",
    ) -> None:
        message = reset_memory_for_scope(
            companion,
            scope=str(scope),
            user_id=str(ctx.author.id),
            channel_id=str(ctx.channel_id),
        )
        await ctx.respond(message, ephemeral=True)

    @bot.slash_command(name="mood", description="Show Nuru's current mood state.")
    async def mood(ctx: discord.ApplicationContext) -> None:
        await ctx.respond(format_mood_status(state), ephemeral=True)

    @bot.slash_command(
        name="personality",
        description="Swap Nuru's persisted personality profile.",
    )
    async def personality(
        ctx: discord.ApplicationContext,
        persona: discord.Option(
            str,
            choices=list(DEFAULT_PERSONA_PROMPTS),
            description="Personality profile to use.",
        ),
    ) -> None:
        message = swap_personality(state, str(persona))
        await ctx.respond(
            message,
            ephemeral=True,
        )

    @bot.slash_command(
        name="response_mode",
        description="Choose whether Nuru answers with text, voice, or both.",
    )
    async def response_mode(
        ctx: discord.ApplicationContext,
        mode: discord.Option(str, choices=["text", "voice", "both", "default"]),
        scope: discord.Option(str, choices=["me", "channel"]) = "me",
    ) -> None:
        message = set_response_mode_for_scope(
            state,
            mode=str(mode),
            scope=str(scope),
            user_id=str(ctx.author.id),
            channel_id=str(ctx.channel_id),
        )
        await ctx.respond(message, ephemeral=True)


def reset_memory_for_scope(
    companion: CompanionService,
    *,
    scope: CommandScope,
    user_id: str,
    channel_id: str,
) -> str:
    if scope == "channel":
        deleted = companion.reset_memory(channel_id=channel_id)
        return f"Cleared {deleted} remembered message(s) for this channel."

    if scope != "me":
        raise ValueError("scope must be me or channel")

    deleted = companion.reset_memory(user_id=user_id)
    return f"Cleared {deleted} remembered message(s) for you."


def format_mood_status(state: StateStore) -> str:
    mood_state = state.get_mood()
    persona = state.get_persona()
    return (
        f"Mood: {mood_state.label} ({mood_state.energy:.2f} energy)\n"
        f"Persona: {persona.name}"
    )


def swap_personality(state: StateStore, persona: str) -> str:
    new_persona = state.set_persona(persona)
    return f"Personality changed to `{new_persona.name}`."


def set_response_mode_for_scope(
    state: StateStore,
    *,
    mode: str,
    scope: CommandScope,
    user_id: str,
    channel_id: str,
) -> str:
    if mode == "default":
        if scope == "channel":
            state.clear_response_mode(
                scope_type="channel",
                scope_id=channel_id,
            )
            return "Channel response mode preference cleared."

        if scope != "me":
            raise ValueError("scope must be me or channel")

        state.clear_response_mode(
            scope_type="user",
            scope_id=user_id,
        )
        return "Your response mode preference was cleared."

    response_mode_value: ResponseMode = _coerce_response_mode(mode)
    if scope == "channel":
        state.set_response_mode(
            scope_type="channel",
            scope_id=channel_id,
            mode=response_mode_value,
        )
        return f"Channel response mode set to `{response_mode_value}`."

    if scope != "me":
        raise ValueError("scope must be me or channel")

    state.set_response_mode(
        scope_type="user",
        scope_id=user_id,
        mode=response_mode_value,
    )
    return f"Your response mode is now `{response_mode_value}`."


def _coerce_response_mode(value: str) -> ResponseMode:
    if value not in {"text", "voice", "both"}:
        raise ValueError("response mode must be text, voice, or both")
    return value  # type: ignore[return-value]
