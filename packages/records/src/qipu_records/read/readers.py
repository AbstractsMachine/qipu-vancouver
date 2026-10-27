"""The model that reads a page, behind one small interface.

Three readers ship:

* ``AnthropicReader``: Claude through the Anthropic API (the reader the published runs used);
* ``OpenAICompatibleReader``: any server that speaks the OpenAI chat API with JSON-schema output, such as vLLM, Ollama
  or OpenRouter, so an open-weights model can do the reading;
* ``ReplayReader``: answers recorded from an earlier run, so the pipeline can be run and tested without a key or a
  network.

API keys are read from the environment only. They are never written to disk or printed.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, Protocol, TypeGuard

from qipu_records.read import schema
from qipu_records.read.schema import ModelItem

if TYPE_CHECKING:
    from anthropic import Anthropic
    from anthropic.types import OutputConfigParam, TextBlockParam
    from openai import OpenAI

Effort = Literal["low", "medium", "high", "xhigh", "max"]

REQUEST_TIMEOUT_S = 300.0
"""One page takes well under a minute to read. The SDKs' own default is ten minutes; a shorter limit lets their retries
recover from a stalled connection before a long run loses its morning."""


@dataclass(frozen=True)
class Reading:
    """One page as the model read it."""

    page_id: str
    items: list[ModelItem]
    model: str
    prompt_version: str
    input_tokens: int = 0
    output_tokens: int = 0


class ReaderError(RuntimeError):
    """The model's answer for one page cannot be used. The page is left unread, to be tried again."""


class ReaderConfigError(RuntimeError):
    """The reader cannot work at all: no API key, or its client library is not installed."""


class Reader(Protocol):
    """What the pipeline needs of a model: a name, and a read() that turns one page into a Reading."""

    model: str

    def read(self, page_id: str, system_prompt: str, user_message: str) -> Reading: ...


def _is_item(value: object) -> TypeGuard[ModelItem]:
    """An object whose quote, if present, is text: the least an item needs before the checks can look at it."""
    return isinstance(value, dict) and isinstance(value.get("quote", ""), str)


def parse_items(page_id: str, answer: object) -> list[ModelItem]:
    """The items of a decoded answer, or ReaderError when it is not ``{"items": [{...}, ...]}``."""
    items = answer.get("items") if isinstance(answer, dict) else None
    if not isinstance(items, list):
        raise ReaderError(f"{page_id}: the answer has no list of items")
    if not all(_is_item(item) for item in items):
        raise ReaderError(f"{page_id}: an item in the answer is not an object with a text quote")
    return [item for item in items if _is_item(item)]


def _parse(page_id: str, text: str) -> list[ModelItem]:
    try:
        answer = json.loads(text)
    except ValueError as error:
        raise ReaderError(f"{page_id}: the answer is not the expected JSON ({error})") from error
    return parse_items(page_id, answer)


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise ReaderConfigError(f"set {name} in the environment (it is read from there only, never stored)")
    return value


def _missing(sdk: str) -> ReaderConfigError:
    return ReaderConfigError(f"this reader needs the {sdk} package: pip install 'qipu-records[{sdk}]'")


@dataclass
class AnthropicReader:
    """Reads pages with Claude through the Anthropic API. ReaderConfigError without ANTHROPIC_API_KEY or the SDK."""

    model: str = "claude-haiku-5-5"
    effort: Effort = "medium"
    max_tokens: int = 16000
    _client: Anthropic | None = field(default=None, init=False, repr=False)

    def _connect(self) -> Anthropic:
        if self._client is None:
            key = _require_env("ANTHROPIC_API_KEY")
            try:
                from anthropic import Anthropic  # noqa: PLC0415 - an optional extra, loaded only when this reader is used
            except ImportError:
                raise _missing("anthropic") from None
            self._client = Anthropic(api_key=key, max_retries=4, timeout=REQUEST_TIMEOUT_S)
        return self._client

    def read(self, page_id: str, system_prompt: str, user_message: str) -> Reading:
        system: list[TextBlockParam] = [{"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}]
        output: OutputConfigParam = {
            "effort": self.effort,
            "format": {"type": "json_schema", "schema": schema.RESPONSE},
        }
        message = self._connect().messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system,
            output_config=output,
            messages=[{"role": "user", "content": user_message}],
        )
        text = next((block.text for block in message.content if block.type == "text"), "")
        return Reading(
            page_id,
            _parse(page_id, text),
            self.model,
            schema.prompt_version(system_prompt),
            message.usage.input_tokens,
            message.usage.output_tokens,
        )


@dataclass
class OpenAICompatibleReader:
    """A model behind an OpenAI-compatible endpoint, e.g. ``http://localhost:8000/v1`` for vLLM."""

    model: str
    base_url: str
    api_key_env: str = "OPENAI_API_KEY"
    max_tokens: int = 16000
    _client: OpenAI | None = field(default=None, init=False, repr=False)

    def _connect(self) -> OpenAI:
        if self._client is None:
            try:
                from openai import OpenAI  # noqa: PLC0415 - an optional extra, loaded only when this reader is used
            except ImportError:
                raise _missing("openai") from None
            key = os.environ.get(self.api_key_env) or "not-needed"
            self._client = OpenAI(base_url=self.base_url, api_key=key, max_retries=4, timeout=REQUEST_TIMEOUT_S)
        return self._client

    def read(self, page_id: str, system_prompt: str, user_message: str) -> Reading:
        response = self._connect().chat.completions.create(
            model=self.model,
            max_tokens=self.max_tokens,
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_message}],
            response_format={
                "type": "json_schema",
                "json_schema": {"name": "decisions", "strict": True, "schema": schema.RESPONSE},
            },
        )
        usage = response.usage
        return Reading(
            page_id,
            _parse(page_id, response.choices[0].message.content or ""),
            self.model,
            schema.prompt_version(system_prompt),
            usage.prompt_tokens if usage else 0,
            usage.completion_tokens if usage else 0,
        )


def reading_from_row(row: dict[str, Any]) -> Reading:
    page_id = str(row["page_id"])
    return Reading(page_id, parse_items(page_id, row), str(row["model"]), str(row["prompt_version"]))


def load_readings(path: Path) -> dict[str, Reading]:
    """Every reading in a readings.jsonl file, by page id. A line that is not a reading is a ReaderConfigError that
    names the file and the line, since a run cannot replay a file it cannot read."""
    readings: dict[str, Reading] = {}
    with path.open(encoding="utf-8") as lines:
        for number, line in enumerate(lines, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
                reading = reading_from_row(row)
            except (ValueError, KeyError, TypeError, ReaderError) as error:
                raise ReaderConfigError(f"{path}:{number}: not a recorded reading ({error})") from error
            readings[reading.page_id] = reading
    return readings


class ReplayReader:
    """Answers recorded in a JSON Lines file, one ``{"page_id", "model", "prompt_version", "items"}`` per line."""

    def __init__(self, path: Path) -> None:
        self.model = "replay"
        self._readings = load_readings(path)

    def read(self, page_id: str, system_prompt: str, user_message: str) -> Reading:
        try:
            return self._readings[page_id]
        except KeyError:
            raise ReaderError(f"{page_id}: no recorded answer") from None
