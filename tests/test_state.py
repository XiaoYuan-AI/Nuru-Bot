import json
import sqlite3

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


def test_mood_falls_back_when_persisted_json_is_malformed(tmp_path):
    database_path = tmp_path / "state.sqlite3"
    StateStore(database_path).close()
    _write_bot_state(database_path, "mood", "{not valid json")

    store = StateStore(database_path)

    assert store.get_mood().label == "curious"
    assert store.get_mood().energy == 0.5


def test_mood_clamps_out_of_range_persisted_energy(tmp_path):
    database_path = tmp_path / "state.sqlite3"
    StateStore(database_path).close()
    _write_bot_state(
        database_path,
        "mood",
        {"label": "excited", "energy": 2.0, "updated_at": "then"},
    )

    assert StateStore(database_path).get_mood().energy == 1.0


def test_persona_falls_back_when_persisted_payload_is_malformed(tmp_path):
    database_path = tmp_path / "state.sqlite3"
    StateStore(database_path).close()
    _write_bot_state(
        database_path,
        "persona",
        {"name": "", "prompt": "", "updated_at": "then"},
    )

    persona = StateStore(database_path).get_persona()

    assert persona.name == "nuru"
    assert persona.prompt


def _write_bot_state(database_path, key, payload):
    if not isinstance(payload, str):
        payload = json.dumps(payload)

    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            INSERT INTO bot_state(key, value_json, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key)
            DO UPDATE SET
                value_json = excluded.value_json,
                updated_at = excluded.updated_at
            """,
            (key, payload, "then"),
        )
