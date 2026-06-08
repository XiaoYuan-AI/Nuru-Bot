from __future__ import annotations

import re
from collections import Counter, deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


TOPIC_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9_]{3,}")


@dataclass(frozen=True)
class WorkingExchange:
    user: str
    assistant: str
    source: str
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


class WorkingMemory:
    def __init__(self, limit: int) -> None:
        self.limit = max(0, limit)
        self._exchanges: deque[WorkingExchange] = deque()

    def add(
        self,
        *,
        user: str,
        assistant: str,
        source: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if self.limit <= 0:
            return
        self._exchanges.append(
            WorkingExchange(
                user=user,
                assistant=assistant,
                source=source,
                metadata=metadata or {},
            )
        )
        while len(self._exchanges) > self.limit:
            self._exchanges.popleft()

    def recent(self) -> list[WorkingExchange]:
        return list(self._exchanges)

    def topics(self, limit: int = 8) -> list[str]:
        counter: Counter[str] = Counter()
        for exchange in self._exchanges:
            counter.update(TOPIC_PATTERN.findall(exchange.user.lower()))
        return [topic for topic, _count in counter.most_common(limit)]

    def format_context(self) -> str:
        if not self._exchanges:
            return ""
        topics = ", ".join(self.topics())
        lines = [
            f"- User: {exchange.user} | Nuru: {exchange.assistant}"
            for exchange in self._exchanges
        ]
        header = f"Recent topics: {topics}" if topics else "Recent exchanges:"
        return header + "\n" + "\n".join(lines)
