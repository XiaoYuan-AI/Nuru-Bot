from __future__ import annotations

import json
import math
import re
import sqlite3
import threading
from hashlib import sha256
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable


TOKEN_PATTERN = re.compile(r"[a-z0-9_']+")


@dataclass(frozen=True)
class MemoryEntry:
    id: int
    user_id: str
    channel_id: str
    role: str
    content: str
    embedding: list[float]
    created_at: str


class MemoryStore:
    def __init__(self, database_path: str | Path) -> None:
        self.database_path = str(database_path)
        if self.database_path != ":memory:":
            Path(self.database_path).parent.mkdir(parents=True, exist_ok=True)

        self._lock = threading.RLock()
        self._connection = sqlite3.connect(self.database_path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._initialize()

    def add_entry(
        self,
        *,
        user_id: str,
        channel_id: str,
        role: str,
        content: str,
        embedding: Iterable[float],
    ) -> int:
        created_at = datetime.now(UTC).isoformat()
        embedding_json = json.dumps([float(value) for value in embedding])

        with self._lock, self._connection:
            cursor = self._connection.execute(
                """
                INSERT INTO memory_entries
                    (user_id, channel_id, role, content, embedding_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (user_id, channel_id, role, content, embedding_json, created_at),
            )
            return int(cursor.lastrowid)

    def recent(
        self,
        *,
        user_id: str | None = None,
        channel_id: str | None = None,
        limit: int = 10,
    ) -> list[MemoryEntry]:
        if limit <= 0:
            return []

        where, params = self._scope_filter(user_id=user_id, channel_id=channel_id)
        params.append(limit)

        rows = self._query(
            f"""
            SELECT * FROM memory_entries
            {where}
            ORDER BY id DESC
            LIMIT ?
            """,
            params,
        )
        return list(reversed([self._row_to_entry(row) for row in rows]))

    def search(
        self,
        *,
        query_embedding: Iterable[float],
        user_id: str | None = None,
        channel_id: str | None = None,
        limit: int = 5,
    ) -> list[MemoryEntry]:
        if limit <= 0:
            return []

        query = [float(value) for value in query_embedding]
        if not query:
            return self.recent(user_id=user_id, channel_id=channel_id, limit=limit)

        where, params = self._scope_filter(user_id=user_id, channel_id=channel_id)
        rows = self._query(
            f"""
            SELECT * FROM memory_entries
            {where}
            ORDER BY id DESC
            LIMIT 200
            """,
            params,
        )

        scored_entries: list[tuple[float, MemoryEntry]] = []
        for row in rows:
            entry = self._row_to_entry(row)
            if not entry.embedding:
                continue
            scored_entries.append((_cosine_similarity(query, entry.embedding), entry))

        if not scored_entries:
            return self.recent(user_id=user_id, channel_id=channel_id, limit=limit)

        scored_entries.sort(key=lambda item: item[0], reverse=True)
        return [entry for _, entry in scored_entries[:limit]]

    def reset(
        self,
        *,
        user_id: str | None = None,
        channel_id: str | None = None,
    ) -> int:
        where, params = self._scope_filter(user_id=user_id, channel_id=channel_id)
        query = "DELETE FROM memory_entries"
        if where:
            query = f"{query} {where}"

        with self._lock, self._connection:
            cursor = self._connection.execute(query, params)
            return int(cursor.rowcount)

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def _initialize(self) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS memory_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    channel_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    embedding_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            self._connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_memory_scope
                ON memory_entries(user_id, channel_id, id)
                """
            )

    def _query(self, query: str, params: list[object]) -> list[sqlite3.Row]:
        with self._lock:
            return list(self._connection.execute(query, params))

    @staticmethod
    def _scope_filter(
        *,
        user_id: str | None,
        channel_id: str | None,
    ) -> tuple[str, list[object]]:
        clauses: list[str] = []
        params: list[object] = []

        if user_id is not None:
            clauses.append("user_id = ?")
            params.append(user_id)
        if channel_id is not None:
            clauses.append("channel_id = ?")
            params.append(channel_id)

        if not clauses:
            return "", params
        return f"WHERE {' AND '.join(clauses)}", params

    @staticmethod
    def _row_to_entry(row: sqlite3.Row) -> MemoryEntry:
        return MemoryEntry(
            id=int(row["id"]),
            user_id=str(row["user_id"]),
            channel_id=str(row["channel_id"]),
            role=str(row["role"]),
            content=str(row["content"]),
            embedding=json.loads(row["embedding_json"]),
            created_at=str(row["created_at"]),
        )


def fallback_embedding(text: str, dimensions: int = 64) -> list[float]:
    vector = [0.0] * dimensions
    for token in _tokenize(text):
        digest = sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % dimensions
        vector[index] += 1.0

    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector
    return [value / norm for value in vector]


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    width = min(len(left), len(right))
    if width == 0:
        return 0.0

    left_slice = left[:width]
    right_slice = right[:width]
    numerator = sum(a * b for a, b in zip(left_slice, right_slice, strict=True))
    left_norm = math.sqrt(sum(value * value for value in left_slice))
    right_norm = math.sqrt(sum(value * value for value in right_slice))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return numerator / (left_norm * right_norm)


def _tokenize(text: str) -> list[str]:
    return TOKEN_PATTERN.findall(text.lower())
