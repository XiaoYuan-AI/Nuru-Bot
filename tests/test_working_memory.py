from nuru_bot.working_memory import WorkingMemory


def test_working_memory_keeps_recent_exchanges_with_limit():
    memory = WorkingMemory(limit=2)

    memory.add(user="first topic", assistant="first reply", source="text")
    memory.add(user="second topic", assistant="second reply", source="voice")
    memory.add(user="third topic", assistant="third reply", source="text")

    recent = memory.recent()
    assert [exchange.user for exchange in recent] == ["second topic", "third topic"]
    assert recent[0].source == "voice"


def test_working_memory_limit_zero_drops_exchanges():
    memory = WorkingMemory(limit=0)

    memory.add(user="keep out", assistant="reply", source="text")

    assert memory.recent() == []
    assert memory.format_context() == ""


def test_working_memory_extracts_topics_and_formats_context():
    memory = WorkingMemory(limit=4)

    memory.add(
        user="rhythm games and rhythm maps",
        assistant="osu noted",
        source="text",
    )

    assert memory.topics(limit=2) == ["rhythm", "games"]
    context = memory.format_context()
    assert "Recent topics: rhythm, games" in context
    assert "- User: rhythm games and rhythm maps | Nuru: osu noted" in context
