from __future__ import annotations

import logging
from dataclasses import dataclass

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


@dataclass(frozen=True)
class RuntimeServices:
    api: NuruApi
    memory: MemoryStore
    state: StateStore
    companion: CompanionService
    voice_runtime: VoiceRuntime

    def close(self) -> None:
        self.voice_runtime.close()
        self.api.close()
        self.memory.close()
        self.state.close()


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

    services = RuntimeServices(
        api=api,
        memory=memory,
        state=state,
        companion=companion,
        voice_runtime=voice_runtime,
    )
    client.nuru_services = services

    register_events(client, config, companion, voice_runtime)
    if config.enable_slash_commands:
        register_commands(client, companion=companion, state=state)

    return client


def close_runtime_services(client: Bot) -> None:
    services = getattr(client, "nuru_services", None)
    if services is not None:
        services.close()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    config = load_config()
    client = create_client(config)
    LOGGER.info("Starting Nuru bot")
    try:
        client.run(config.token)
    finally:
        close_runtime_services(client)
