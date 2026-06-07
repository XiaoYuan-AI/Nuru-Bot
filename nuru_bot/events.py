from __future__ import annotations

import asyncio
import logging

from discord import Activity, ActivityType, Client, DMChannel, Message, Reaction, User

from .api import NuruApi, NuruApiError
from .config import BotConfig
from .voice import connect_voice_channel


LOGGER = logging.getLogger(__name__)
IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".gif", ".webp")


def register_events(client: Client, config: BotConfig, api: NuruApi) -> None:
    @client.event
    async def on_ready() -> None:
        LOGGER.info("Logged in as %s", client.user)
        activity = Activity(name=config.activity_name, type=ActivityType.playing)
        await client.change_presence(activity=activity)

        if config.connect_voice_on_ready:
            await connect_voice_channel(client, config)

    if config.enable_dm_chat:

        @client.event
        async def on_message(message: Message) -> None:
            await handle_dm_message(client, message, api)

    if config.enable_reaction_chat:

        @client.event
        async def on_reaction_add(reaction: Reaction, user: User) -> None:
            await handle_dm_reaction(client, reaction, user, api)


async def handle_dm_message(client: Client, message: Message, api: NuruApi) -> None:
    if message.author == client.user:
        return
    if not isinstance(message.channel, DMChannel):
        return
    if not message.content and not message.attachments:
        return

    prompt_parts = await _message_prompt_parts(message, api)
    if not prompt_parts:
        return

    try:
        response = await asyncio.to_thread(api.generate, "\n".join(prompt_parts))
    except NuruApiError:
        LOGGER.exception("Failed to generate a DM response")
        await message.channel.send("The local model service did not return a response.")
        return

    await message.channel.send(response)


async def handle_dm_reaction(
    client: Client,
    reaction: Reaction,
    user: User,
    api: NuruApi,
) -> None:
    if user == client.user:
        return
    if not isinstance(reaction.message.channel, DMChannel):
        return
    if not reaction.emoji:
        return

    prompt = f"{user.name}'s reaction is: {reaction.emoji}"
    try:
        response = await asyncio.to_thread(api.generate, prompt)
    except NuruApiError:
        LOGGER.exception("Failed to generate a reaction response")
        await reaction.message.channel.send(
            "The local model service did not return a response."
        )
        return

    await reaction.message.channel.send(response)


async def _message_prompt_parts(message: Message, api: NuruApi) -> list[str]:
    prompt_parts: list[str] = []

    for attachment in message.attachments:
        filename = attachment.filename.lower()
        if not filename.endswith(IMAGE_EXTENSIONS):
            continue

        try:
            image_data = await attachment.read()
            description = await asyncio.to_thread(api.describe_image, image_data)
        except NuruApiError:
            LOGGER.exception("Failed to describe image attachment %s", attachment.filename)
            continue

        prompt_parts.append(f"(Image description: {description})")

    if message.content:
        prompt_parts.append(f"{message.author}: {message.content}")

    return prompt_parts
