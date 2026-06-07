from __future__ import annotations

import logging

from discord import Client, Intents

from .api import NuruApi
from .config import BotConfig, load_config
from .events import register_events


LOGGER = logging.getLogger(__name__)


def create_client(config: BotConfig | None = None) -> Client:
    config = config or load_config()
    client_options: dict[str, str] = {}

    if config.discord_proxy:
        client_options["proxy"] = config.discord_proxy

    client = Client(intents=Intents.all(), **client_options)
    api = NuruApi(config.api_base_url, config.request_timeout_seconds)
    register_events(client, config, api)
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
