from __future__ import annotations

import asyncio
import logging

from discord import Activity, ActivityType, Client, DMChannel, Message, Reaction, User

from .api import NuruApiError
from .companion import CompanionService, InteractionRequest, InteractionResponse
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
            await handle_dm_reaction(client, reaction, user, companion, voice_runtime)


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

    await deliver_interaction_response(message.channel, response, voice_runtime)


async def handle_dm_reaction(
    client: Client,
    reaction: Reaction,
    user: User,
    companion: CompanionService,
    voice_runtime: VoiceRuntime,
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

    await deliver_interaction_response(reaction.message.channel, response, voice_runtime)


async def deliver_interaction_response(
    channel: object,
    response: InteractionResponse,
    voice_runtime: VoiceRuntime,
) -> None:
    if response.response_mode in {"text", "both"}:
        await _send_channel_message(
            channel,
            response.text,
            failure_log="Failed to send text interaction response",
        )

    if response.response_mode in {"voice", "both"}:
        voice_client = voice_runtime.voice_client
        if voice_client is not None and voice_client.is_connected():
            try:
                await voice_runtime.speak(voice_client, response.text)
            except Exception:
                LOGGER.exception("Failed to deliver voice interaction response")
                if response.response_mode == "voice":
                    await _send_channel_message(
                        channel,
                        "I could not play that in voice.",
                        failure_log="Failed to send voice delivery fallback",
                    )
            return

        if response.response_mode == "voice":
            await _send_channel_message(
                channel,
                "I am not connected to a voice channel yet.",
                failure_log="Failed to send missing voice connection fallback",
            )


async def _send_channel_message(
    channel: object,
    text: str,
    *,
    failure_log: str,
) -> bool:
    send = getattr(channel, "send", None)
    if send is None:
        return False

    try:
        await send(text)
    except Exception:
        LOGGER.exception(failure_log)
        return False
    return True


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
