from __future__ import annotations

import json
import re
import sqlite3
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal


ResponseMode = Literal["text", "voice", "both"]
POSITIVE_MOOD_WORDS = {"thanks", "thank", "love", "great", "nice", "good", "happy"}
NEGATIVE_MOOD_WORDS = {"bad", "hate", "angry", "sad", "annoying", "stupid"}
WORD_PATTERN = re.compile(r"[a-z0-9_']+")

DEFAULT_PERSONA_PROMPTS = {
    "nuru": "Playful, curious, lightly teasing, and emotionally responsive.",
    "supportive": "Warm, patient, concise, and focused on helping the user.",
    "chaotic": "High-energy, witty, spontaneous, but still safe and coherent.",
}


@dataclass(frozen=True)
class MoodState:
    label: str
    energy: float
    updated_at: str


@dataclass(frozen=True)
class PersonaState:
    name: str
    prompt: str
    updated_at: str


class StateStore:
    def __init__(self, database_path: str | Path) -> None:
        self.database_path = str(database_path)
        if self.database_path != ":memory:":
            Path(self.database_path).parent.mkdir(parents=True, exist_ok=True)

        self._lock = threading.RLock()
        self._connection = sqlite3.connect(self.database_path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._initialize()

    def get_mood(self) -> MoodState:
        payload = self._get_json("mood")
        if payload is None:
            return MoodState(label="curious", energy=0.5, updated_at=_now())
        return MoodState(
            label=str(payload["label"]),
            energy=float(payload["energy"]),
            updated_at=str(payload["updated_at"]),
        )

    def set_mood(self, label: str, energy: float) -> MoodState:
        mood = MoodState(label=label, energy=max(0.0, min(1.0, energy)), updated_at=_now())
        self._set_json("mood", mood.__dict__)
        return mood

    def adjust_mood_from_text(self, text: str) -> MoodState:
        current = self.get_mood()
        words = set(_word_tokens(text))

        delta = 0.0
        if words & POSITIVE_MOOD_WORDS:
            delta += 0.1
        if words & NEGATIVE_MOOD_WORDS:
            delta -= 0.1

        energy = max(0.0, min(1.0, current.energy + delta))
        if energy >= 0.7:
            label = "excited"
        elif energy <= 0.3:
            label = "subdued"
        else:
            label = "curious"

        return self.set_mood(label, energy)

    def get_persona(self) -> PersonaState:
        payload = self._get_json("persona")
        if payload is None:
            return PersonaState(
                name="nuru",
                prompt=DEFAULT_PERSONA_PROMPTS["nuru"],
                updated_at=_now(),
            )
        return PersonaState(
            name=str(payload["name"]),
            prompt=str(payload["prompt"]),
            updated_at=str(payload["updated_at"]),
        )

    def set_persona(self, name: str, prompt: str | None = None) -> PersonaState:
        normalized = name.strip().lower()
        if not normalized:
            raise ValueError("persona name cannot be empty")

        persona_prompt = prompt or DEFAULT_PERSONA_PROMPTS.get(
            normalized,
            f"Adopt the '{normalized}' personality while staying coherent and kind.",
        )
        persona = PersonaState(name=normalized, prompt=persona_prompt, updated_at=_now())
        self._set_json("persona", persona.__dict__)
        return persona

    def set_response_mode(
        self,
        *,
        scope_type: Literal["user", "channel"],
        scope_id: str,
        mode: ResponseMode,
    ) -> None:
        if mode not in {"text", "voice", "both"}:
            raise ValueError("response mode must be text, voice, or both")
        if scope_type not in {"user", "channel"}:
            raise ValueError("scope_type must be user or channel")

        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT INTO response_preferences
                    (scope_type, scope_id, response_mode, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(scope_type, scope_id)
                DO UPDATE SET
                    response_mode = excluded.response_mode,
                    updated_at = excluded.updated_at
                """,
                (scope_type, scope_id, mode, _now()),
            )

    def clear_response_mode(
        self,
        *,
        scope_type: Literal["user", "channel"],
        scope_id: str,
    ) -> int:
        if scope_type not in {"user", "channel"}:
            raise ValueError("scope_type must be user or channel")

        with self._lock, self._connection:
            cursor = self._connection.execute(
                """
                DELETE FROM response_preferences
                WHERE scope_type = ? AND scope_id = ?
                """,
                (scope_type, scope_id),
            )
            return int(cursor.rowcount)

    def get_response_mode(
        self,
        *,
        user_id: str | None,
        channel_id: str | None,
        default: ResponseMode,
    ) -> ResponseMode:
        if user_id is not None:
            user_mode = self._get_response_mode("user", user_id)
            if user_mode is not None:
                return user_mode
        if channel_id is not None:
            channel_mode = self._get_response_mode("channel", channel_id)
            if channel_mode is not None:
                return channel_mode
        return default

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def _initialize(self) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS bot_state (
                    key TEXT PRIMARY KEY,
                    value_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS response_preferences (
                    scope_type TEXT NOT NULL,
                    scope_id TEXT NOT NULL,
                    response_mode TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(scope_type, scope_id)
                )
                """
            )

    def _get_json(self, key: str) -> dict[str, object] | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT value_json FROM bot_state WHERE key = ?",
                (key,),
            ).fetchone()
        if row is None:
            return None
        return json.loads(str(row["value_json"]))

    def _set_json(self, key: str, value: dict[str, object]) -> None:
        updated_at = _now()
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT INTO bot_state(key, value_json, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key)
                DO UPDATE SET
                    value_json = excluded.value_json,
                    updated_at = excluded.updated_at
                """,
                (key, json.dumps(value), updated_at),
            )

    def _get_response_mode(
        self,
        scope_type: Literal["user", "channel"],
        scope_id: str,
    ) -> ResponseMode | None:
        with self._lock:
            row = self._connection.execute(
                """
                SELECT response_mode
                FROM response_preferences
                WHERE scope_type = ? AND scope_id = ?
                """,
                (scope_type, scope_id),
            ).fetchone()
        if row is None:
            return None

        value = str(row["response_mode"])
        if value not in {"text", "voice", "both"}:
            return None
        return value  # type: ignore[return-value]


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _word_tokens(text: str) -> list[str]:
    return WORD_PATTERN.findall(text.lower())
