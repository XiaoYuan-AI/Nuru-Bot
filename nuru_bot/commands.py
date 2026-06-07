from __future__ import annotations

import discord

from .companion import CompanionService
from .state import DEFAULT_PERSONA_PROMPTS, ResponseMode, StateStore


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
        if scope == "channel":
            deleted = companion.reset_memory(channel_id=str(ctx.channel_id))
            await ctx.respond(
                f"Cleared {deleted} remembered message(s) for this channel.",
                ephemeral=True,
            )
            return

        deleted = companion.reset_memory(user_id=str(ctx.author.id))
        await ctx.respond(
            f"Cleared {deleted} remembered message(s) for you.",
            ephemeral=True,
        )

    @bot.slash_command(name="mood", description="Show Nuru's current mood state.")
    async def mood(ctx: discord.ApplicationContext) -> None:
        mood_state = state.get_mood()
        persona = state.get_persona()
        await ctx.respond(
            (
                f"Mood: {mood_state.label} ({mood_state.energy:.2f} energy)\n"
                f"Persona: {persona.name}"
            ),
            ephemeral=True,
        )

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
        new_persona = state.set_persona(str(persona))
        await ctx.respond(
            f"Personality changed to `{new_persona.name}`.",
            ephemeral=True,
        )

    @bot.slash_command(
        name="response_mode",
        description="Choose whether Nuru answers with text, voice, or both.",
    )
    async def response_mode(
        ctx: discord.ApplicationContext,
        mode: discord.Option(str, choices=["text", "voice", "both"]),
        scope: discord.Option(str, choices=["me", "channel"]) = "me",
    ) -> None:
        response_mode_value: ResponseMode = _coerce_response_mode(str(mode))
        if scope == "channel":
            state.set_response_mode(
                scope_type="channel",
                scope_id=str(ctx.channel_id),
                mode=response_mode_value,
            )
            await ctx.respond(
                f"Channel response mode set to `{response_mode_value}`.",
                ephemeral=True,
            )
            return

        state.set_response_mode(
            scope_type="user",
            scope_id=str(ctx.author.id),
            mode=response_mode_value,
        )
        await ctx.respond(
            f"Your response mode is now `{response_mode_value}`.",
            ephemeral=True,
        )


def _coerce_response_mode(value: str) -> ResponseMode:
    if value not in {"text", "voice", "both"}:
        raise ValueError("response mode must be text, voice, or both")
    return value  # type: ignore[return-value]
