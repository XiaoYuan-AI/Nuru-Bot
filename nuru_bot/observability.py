from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any


@dataclass(frozen=True)
class Observation:
    event: str
    latency_seconds: float
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


def start_timer() -> float:
    return perf_counter()


def record_observation(path: Path | None, observation: Observation) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "event": observation.event,
        "latency_seconds": observation.latency_seconds,
        "metadata": observation.metadata,
        "created_at": observation.created_at,
    }
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(payload, ensure_ascii=False) + "\n")
