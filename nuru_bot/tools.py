from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ToolCall:
    action: str
    parameters: dict[str, Any] = field(default_factory=dict)
    safe: bool = True


def extract_tool_calls(text: str) -> list[ToolCall]:
    calls = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("{") or not stripped.endswith("}"):
            continue
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        action = payload.get("action")
        parameters = payload.get("parameters")
        if not isinstance(action, str) or not isinstance(parameters, dict):
            continue
        calls.append(
            ToolCall(
                action=action,
                parameters=parameters,
                safe=bool(payload.get("safe", True)),
            )
        )
    return calls


def remove_tool_call_lines(text: str) -> str:
    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("{") and stripped.endswith("}"):
            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError:
                payload = None
            if isinstance(payload, dict) and "action" in payload:
                continue
        lines.append(line)
    return "\n".join(lines).strip()


def serialize_tool_call(call: ToolCall) -> dict[str, Any]:
    return {
        "action": call.action,
        "parameters": call.parameters,
        "safe": call.safe,
    }
