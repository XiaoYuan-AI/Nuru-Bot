from nuru_bot.memory import MemoryStore, fallback_embedding


def test_memory_store_persists_recent_and_searches_embeddings(tmp_path):
    database_path = tmp_path / "memory.sqlite3"
    store = MemoryStore(database_path)

    first_id = store.add_entry(
        user_id="user-1",
        channel_id="channel-1",
        role="user",
        content="I like rhythm games",
        embedding=fallback_embedding("rhythm games"),
    )
    store.add_entry(
        user_id="user-1",
        channel_id="channel-1",
        role="assistant",
        content="I will remember rhythm games.",
        embedding=fallback_embedding("remember rhythm"),
    )

    assert first_id == 1
    assert [entry.content for entry in store.recent(user_id="user-1")] == [
        "I like rhythm games",
        "I will remember rhythm games.",
    ]

    matches = store.search(
        query_embedding=fallback_embedding("rhythm"),
        user_id="user-1",
        channel_id="channel-1",
        limit=1,
    )

    assert matches
    assert "rhythm" in matches[0].content.lower()


def test_fallback_embedding_ignores_punctuation_for_memory_search(tmp_path):
    store = MemoryStore(tmp_path / "memory.sqlite3")
    store.add_entry(
        user_id="user-1",
        channel_id="channel-1",
        role="user",
        content="I like osu!",
        embedding=fallback_embedding("I like osu!"),
    )
    store.add_entry(
        user_id="user-1",
        channel_id="channel-1",
        role="user",
        content="I like cooking",
        embedding=fallback_embedding("I like cooking"),
    )

    matches = store.search(
        query_embedding=fallback_embedding("osu"),
        user_id="user-1",
        channel_id="channel-1",
        limit=1,
    )

    assert matches[0].content == "I like osu!"


def test_memory_reset_can_target_channel(tmp_path):
    store = MemoryStore(tmp_path / "memory.sqlite3")
    store.add_entry(
        user_id="user-1",
        channel_id="channel-1",
        role="user",
        content="keep",
        embedding=[],
    )
    store.add_entry(
        user_id="user-2",
        channel_id="channel-2",
        role="user",
        content="delete",
        embedding=[],
    )

    assert store.reset(channel_id="channel-2") == 1
    assert [entry.content for entry in store.recent()] == ["keep"]


def test_memory_search_falls_back_to_recent_when_entries_have_no_embeddings(tmp_path):
    store = MemoryStore(tmp_path / "memory.sqlite3")
    store.add_entry(
        user_id="user-1",
        channel_id="channel-1",
        role="user",
        content="older context",
        embedding=[],
    )
    store.add_entry(
        user_id="user-1",
        channel_id="channel-1",
        role="assistant",
        content="newer context",
        embedding=[],
    )

    matches = store.search(
        query_embedding=fallback_embedding("context"),
        user_id="user-1",
        channel_id="channel-1",
        limit=2,
    )

    assert [entry.content for entry in matches] == ["older context", "newer context"]
