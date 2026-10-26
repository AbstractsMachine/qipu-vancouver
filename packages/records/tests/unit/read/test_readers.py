import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from qipu_records.read import schema
from qipu_records.read.readers import (
    AnthropicReader,
    OpenAICompatibleReader,
    ReaderConfigError,
    ReaderError,
    ReplayReader,
    _parse,
)


def test_replay_returns_the_recorded_answer(tmp_path: Path) -> None:
    path = tmp_path / "readings.jsonl"
    row = {"page_id": "x:1", "model": "m", "prompt_version": "v", "items": [{"quote": "q"}]}
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")
    reading = ReplayReader(path).read("x:1", "system", "user")
    assert (reading.items, reading.model, reading.prompt_version) == ([{"quote": "q"}], "m", "v")
    with pytest.raises(ReaderError, match="no recorded answer"):
        ReplayReader(path).read("x:2", "system", "user")


def test_answers_that_are_not_the_schema_are_refused() -> None:
    assert _parse("p", '{"items": []}') == []
    for bad in ("not json", '{"rows": []}', '{"items": {}}'):
        with pytest.raises(ReaderError):
            _parse("p", bad)


def test_missing_key_is_reported_before_any_call(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(ReaderConfigError, match="ANTHROPIC_API_KEY"):
        AnthropicReader().read("p", "system", "user")


ANSWER = '{"items": [{"quote": "Acquisition for Park Site"}]}'


def test_anthropic_reader_sends_the_schema_and_caches_the_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: dict[str, Any] = {}

    def create(**kwargs: Any) -> SimpleNamespace:
        sent.update(kwargs)
        return SimpleNamespace(
            content=[SimpleNamespace(type="thinking"), SimpleNamespace(type="text", text=ANSWER)],
            usage=SimpleNamespace(input_tokens=1900, output_tokens=3500),
        )

    reader = AnthropicReader()
    reader._client = SimpleNamespace(messages=SimpleNamespace(create=create))
    reading = reader.read("19740219:4", "SYSTEM", "USER")
    assert reading.items == [{"quote": "Acquisition for Park Site"}]
    assert (reading.input_tokens, reading.output_tokens) == (1900, 3500)
    assert reading.prompt_version == schema.prompt_version("SYSTEM")
    assert sent["output_config"]["format"]["schema"] is schema.RESPONSE
    assert sent["system"][0]["cache_control"] == {"type": "ephemeral"}


def test_openai_compatible_reader_asks_for_strict_json(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: dict[str, Any] = {}

    def create(**kwargs: Any) -> SimpleNamespace:
        sent.update(kwargs)
        message = SimpleNamespace(content=ANSWER)
        usage = SimpleNamespace(prompt_tokens=10, completion_tokens=20)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)], usage=usage)

    reader = OpenAICompatibleReader(model="open-model", base_url="http://localhost:8000/v1")
    reader._client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    reading = reader.read("19740219:4", "SYSTEM", "USER")
    assert reading.model == "open-model"
    assert reading.items[0]["quote"] == "Acquisition for Park Site"
    assert sent["response_format"]["json_schema"]["strict"] is True
    assert sent["messages"][0] == {"role": "system", "content": "SYSTEM"}


def test_a_missing_client_library_is_explained(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "openai", None)
    with pytest.raises(ReaderConfigError, match=r"pip install 'qipu-records\[openai\]'"):
        OpenAICompatibleReader(model="m", base_url="http://localhost:8000/v1").read("p", "s", "u")
