import json

from nuru_bot.observability import Observation, record_observation, start_timer


def test_start_timer_returns_monotonic_marker():
    assert isinstance(start_timer(), float)


def test_record_observation_writes_jsonl(tmp_path):
    path = tmp_path / "logs" / "observability.jsonl"

    record_observation(
        path,
        Observation(
            event="companion.respond",
            latency_seconds=0.25,
            metadata={"status": "ok"},
            created_at="now",
        ),
    )

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload == {
        "event": "companion.respond",
        "latency_seconds": 0.25,
        "metadata": {"status": "ok"},
        "created_at": "now",
    }


def test_record_observation_noops_when_path_is_none():
    record_observation(
        None,
        Observation(event="ignored", latency_seconds=0.0),
    )
