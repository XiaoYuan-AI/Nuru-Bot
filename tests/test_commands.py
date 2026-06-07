import pytest

from nuru_bot.commands import (
    format_mood_status,
    reset_memory_for_scope,
    set_response_mode_for_scope,
    swap_personality,
)
from nuru_bot.state import StateStore


class FakeCompanion:
    def __init__(self):
        self.reset_calls = []

    def reset_memory(self, *, user_id=None, channel_id=None):
        self.reset_calls.append((user_id, channel_id))
        return 3


def test_reset_memory_for_user_scope():
    companion = FakeCompanion()

    message = reset_memory_for_scope(
        companion,
        scope="me",
        user_id="user-1",
        channel_id="channel-1",
    )

    assert message == "Cleared 3 remembered message(s) for you."
    assert companion.reset_calls == [("user-1", None)]


def test_reset_memory_for_channel_scope():
    companion = FakeCompanion()

    message = reset_memory_for_scope(
        companion,
        scope="channel",
        user_id="user-1",
        channel_id="channel-1",
    )

    assert message == "Cleared 3 remembered message(s) for this channel."
    assert companion.reset_calls == [(None, "channel-1")]


def test_format_mood_and_personality_swap(tmp_path):
    state = StateStore(tmp_path / "state.sqlite3")
    state.set_mood("excited", 0.75)

    assert swap_personality(state, "supportive") == "Personality changed to `supportive`."
    assert format_mood_status(state) == "Mood: excited (0.75 energy)\nPersona: supportive"


def test_response_mode_helper_sets_user_and_channel_preferences(tmp_path):
    state = StateStore(tmp_path / "state.sqlite3")

    assert (
        set_response_mode_for_scope(
            state,
            mode="voice",
            scope="channel",
            user_id="user-1",
            channel_id="channel-1",
        )
        == "Channel response mode set to `voice`."
    )
    assert (
        set_response_mode_for_scope(
            state,
            mode="both",
            scope="me",
            user_id="user-1",
            channel_id="channel-1",
        )
        == "Your response mode is now `both`."
    )
    assert state.get_response_mode(
        user_id="user-1",
        channel_id="channel-1",
        default="text",
    ) == "both"
    assert state.get_response_mode(
        user_id="user-2",
        channel_id="channel-1",
        default="text",
    ) == "voice"


def test_response_mode_helper_rejects_invalid_mode(tmp_path):
    state = StateStore(tmp_path / "state.sqlite3")

    with pytest.raises(ValueError):
        set_response_mode_for_scope(
            state,
            mode="invalid",
            scope="me",
            user_id="user-1",
            channel_id="channel-1",
        )
