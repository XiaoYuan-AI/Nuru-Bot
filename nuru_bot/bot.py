from __future__ import annotations

import logging

from discord import Bot, Intents

from .api import NuruApi
from .commands import register_commands
from .companion import CompanionService
from .config import BotConfig, load_config
from .memory import MemoryStore
from .events import register_events
from .state import StateStore
from .voice import VoiceRuntime


LOGGER = logging.getLogger(__name__)


def create_client(config: BotConfig | None = None) -> Bot:
    config = config or load_config()
    client_options: dict[str, str] = {}

    if config.discord_proxy:
        client_options["proxy"] = config.discord_proxy

    client = Bot(intents=Intents.all(), **client_options)
    api = NuruApi(config.api_base_url, config.request_timeout_seconds)
    memory = MemoryStore(config.data_path)
    state = StateStore(config.data_path)
    companion = CompanionService(
        api=api,
        memory=memory,
        state=state,
        config=config,
    )
    voice_runtime = VoiceRuntime(
        config=config,
        api=api,
        companion=companion,
    )

    register_events(client, config, companion, voice_runtime)
    if config.enable_slash_commands:
        register_commands(client, companion=companion, state=state)

    return client


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    config = load_config()
    client = create_client(config)
    LOGGER.info("Starting Nuru bot")
    client.run(config.token)
