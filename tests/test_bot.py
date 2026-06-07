import asyncio

from nuru_bot.bot import close_runtime_services, create_client

from .helpers import make_config


def test_create_client_attaches_runtime_services():
    loop = asyncio.new_event_loop()
    previous_loop = _current_event_loop()
    client = None
    try:
        asyncio.set_event_loop(loop)
        client = create_client(make_config(enable_slash_commands=True))
        services = client.nuru_services

        assert services.api is not None
        assert services.memory is not None
        assert services.state is not None
        assert services.companion is not None
        assert services.voice_runtime is not None
        assert len(client.pending_application_commands) == 4
    finally:
        if client is not None:
            close_runtime_services(client)
        asyncio.set_event_loop(previous_loop)
        loop.close()


def _current_event_loop():
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        return None
