from nuru_bot.tools import extract_tool_calls, remove_tool_call_lines, serialize_tool_call


def test_extract_tool_calls_reads_valid_json_lines():
    calls = extract_tool_calls(
        'visible text\n{"action": "calculator", "parameters": {"expression": "2+2"}}'
    )

    assert len(calls) == 1
    assert calls[0].action == "calculator"
    assert calls[0].parameters == {"expression": "2+2"}
    assert calls[0].safe


def test_extract_tool_calls_ignores_invalid_or_incomplete_lines():
    calls = extract_tool_calls(
        "\n".join(
            [
                "{not json",
                '["not", "object"]',
                '{"action": "calculator"}',
                '{"parameters": {}}',
            ]
        )
    )

    assert calls == []


def test_remove_tool_call_lines_keeps_visible_text():
    text = remove_tool_call_lines(
        'First line\n{"action": "calendar", "parameters": {}}\nSecond line'
    )

    assert text == "First line\nSecond line"


def test_serialize_tool_call_uses_plain_payload():
    call = extract_tool_calls('{"action": "calendar", "parameters": {}, "safe": false}')[0]

    assert serialize_tool_call(call) == {
        "action": "calendar",
        "parameters": {},
        "safe": False,
    }
