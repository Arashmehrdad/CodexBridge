from __future__ import annotations

from pathlib import Path

from codexbridge.events import ArtifactWriter, append_jsonl, read_jsonl, redact_and_truncate, truncate_text


def test_event_jsonl_round_trip_and_limit(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    for index in range(3):
        append_jsonl(path, {"run_id": "r", "message": str(index), "data": {}})
    events = read_jsonl(path, limit=2)
    assert [event["message"] for event in events] == ["1", "2"]


def test_artifact_writer_redacts_secret_values(tmp_path: Path) -> None:
    writer = ArtifactWriter(tmp_path)
    writer.write_text("stdout.txt", "API_KEY=abc123")
    assert "abc123" not in (tmp_path / "stdout.txt").read_text(encoding="utf-8")


def test_redaction_and_truncation_nested_values() -> None:
    value = redact_and_truncate({"token": "token: abc", "text": "x" * 50}, limit=10)
    assert "abc" not in value["token"]
    assert "[truncated" in value["text"]


def test_truncate_text_keeps_short_text() -> None:
    assert truncate_text("short", 10) == "short"
