from nuru_bot.state import StateStore


def test_mood_and_persona_persist_across_store_instances(tmp_path):
    database_path = tmp_path / "state.sqlite3"
    store = StateStore(database_path)
    store.set_mood("excited", 0.8)
    store.set_persona("supportive")
    store.close()

    reopened = StateStore(database_path)

    assert reopened.get_mood().label == "excited"
    assert reopened.get_mood().energy == 0.8
    assert reopened.get_persona().name == "supportive"


def test_user_response_mode_overrides_channel_default(tmp_path):
    store = StateStore(tmp_path / "state.sqlite3")
    store.set_response_mode(scope_type="channel", scope_id="channel-1", mode="voice")
    store.set_response_mode(scope_type="user", scope_id="user-1", mode="both")

    assert (
        store.get_response_mode(
            user_id="user-1",
            channel_id="channel-1",
            default="text",
        )
        == "both"
    )
    assert (
        store.get_response_mode(
            user_id="user-2",
            channel_id="channel-1",
            default="text",
        )
        == "voice"
    )


def test_response_modes_persist_across_store_instances(tmp_path):
    database_path = tmp_path / "state.sqlite3"
    store = StateStore(database_path)
    store.set_response_mode(scope_type="channel", scope_id="channel-1", mode="voice")
    store.set_response_mode(scope_type="user", scope_id="user-1", mode="both")
    store.close()

    reopened = StateStore(database_path)

    assert (
        reopened.get_response_mode(
            user_id="user-1",
            channel_id="channel-1",
            default="text",
        )
        == "both"
    )
    assert (
        reopened.get_response_mode(
            user_id="user-2",
            channel_id="channel-1",
            default="text",
        )
        == "voice"
    )


def test_clear_response_mode_restores_fallback(tmp_path):
    store = StateStore(tmp_path / "state.sqlite3")
    store.set_response_mode(scope_type="channel", scope_id="channel-1", mode="voice")
    store.set_response_mode(scope_type="user", scope_id="user-1", mode="both")

    assert (
        store.get_response_mode(
            user_id="user-1",
            channel_id="channel-1",
            default="text",
        )
        == "both"
    )
    assert store.clear_response_mode(scope_type="user", scope_id="user-1") == 1
    assert (
        store.get_response_mode(
            user_id="user-1",
            channel_id="channel-1",
            default="text",
        )
        == "voice"
    )
    assert store.clear_response_mode(scope_type="channel", scope_id="channel-1") == 1
    assert (
        store.get_response_mode(
            user_id="user-1",
            channel_id="channel-1",
            default="text",
        )
        == "text"
    )


def test_mood_adjusts_from_sentiment_words(tmp_path):
    store = StateStore(tmp_path / "state.sqlite3")

    assert store.adjust_mood_from_text("thanks, that was great").label == "curious"
    assert store.adjust_mood_from_text("I love this good thing").energy > 0.5


def test_mood_ignores_sentiment_substrings_inside_other_words(tmp_path):
    store = StateStore(tmp_path / "state.sqlite3")

    assert store.adjust_mood_from_text("goodbye badminton").energy == 0.5
    assert store.adjust_mood_from_text("thank-you, nice work").energy == 0.6
