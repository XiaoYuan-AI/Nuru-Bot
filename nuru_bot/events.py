from __future__ import annotations

import asyncio
import logging

from discord import Activity, ActivityType, Client, DMChannel, Message, Reaction, User

from .api import NuruApiError
from .companion import CompanionService, InteractionRequest
from .config import BotConfig
from .voice import VoiceRuntime


LOGGER = logging.getLogger(__name__)
IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".gif", ".webp")


def register_events(
    client: Client,
    config: BotConfig,
    companion: CompanionService,
    voice_runtime: VoiceRuntime,
) -> None:
    @client.event
    async def on_ready() -> None:
        LOGGER.info("Logged in as %s", client.user)
        activity = Activity(name=config.activity_name, type=ActivityType.playing)
        await client.change_presence(activity=activity)

        if config.connect_voice_on_ready:
            await voice_runtime.connect(client)

    if config.enable_text_chat:

        @client.event
        async def on_message(message: Message) -> None:
            await handle_text_message(client, message, companion, voice_runtime)

    if config.enable_reaction_chat:

        @client.event
        async def on_reaction_add(reaction: Reaction, user: User) -> None:
            await handle_dm_reaction(client, reaction, user, companion)


async def handle_text_message(
    client: Client,
    message: Message,
    companion: CompanionService,
    voice_runtime: VoiceRuntime,
) -> None:
    if message.author == client.user:
        return
    if not message.content and not message.attachments:
        return
    if not _should_respond_to_message(client, message):
        return

    prompt_parts = await _message_prompt_parts(message, companion)
    if not prompt_parts:
        return

    try:
        response = await companion.respond(
            InteractionRequest(
                user_id=str(message.author.id),
                channel_id=str(message.channel.id),
                author_name=message.author.display_name,
                content="\n".join(prompt_parts),
                source="text",
            )
        )
    except NuruApiError:
        LOGGER.exception("Failed to generate a text response")
        await message.channel.send("The local model service did not return a response.")
        return

    if response.response_mode in {"text", "both"}:
        await message.channel.send(response.text)

    if response.response_mode in {"voice", "both"}:
        voice_client = voice_runtime.voice_client
        if voice_client is not None and voice_client.is_connected():
            await voice_runtime.speak(voice_client, response.text)
        elif response.response_mode == "voice":
            await message.channel.send("I am not connected to a voice channel yet.")


async def handle_dm_reaction(
    client: Client,
    reaction: Reaction,
    user: User,
    companion: CompanionService,
) -> None:
    if user == client.user:
        return
    if not isinstance(reaction.message.channel, DMChannel):
        return
    if not reaction.emoji:
        return

    try:
        response = await companion.respond(
            InteractionRequest(
                user_id=str(user.id),
                channel_id=str(reaction.message.channel.id),
                author_name=user.display_name,
                content=f"{user.name}'s reaction is: {reaction.emoji}",
                source="reaction",
            )
        )
    except NuruApiError:
        LOGGER.exception("Failed to generate a reaction response")
        await reaction.message.channel.send(
            "The local model service did not return a response."
        )
        return

    await reaction.message.channel.send(response.text)


async def _message_prompt_parts(
    message: Message,
    companion: CompanionService,
) -> list[str]:
    prompt_parts: list[str] = []

    for attachment in message.attachments:
        filename = attachment.filename.lower()
        if not filename.endswith(IMAGE_EXTENSIONS):
            continue

        try:
            image_data = await attachment.read()
            description = await asyncio.to_thread(
                companion.api.describe_image,
                image_data,
            )
        except NuruApiError:
            LOGGER.exception("Failed to describe image attachment %s", attachment.filename)
            continue

        prompt_parts.append(f"(Image description: {description})")

    if message.content:
        prompt_parts.append(_strip_bot_mention(message))

    return prompt_parts


def _should_respond_to_message(client: Client, message: Message) -> bool:
    if isinstance(message.channel, DMChannel):
        return True

    if client.user is not None and client.user.mentioned_in(message):
        return True

    return False


def _strip_bot_mention(message: Message) -> str:
    content = message.content
    for mention in getattr(message, "mentions", []):
        if getattr(mention, "bot", False):
            content = content.replace(mention.mention, "").strip()
    return content
