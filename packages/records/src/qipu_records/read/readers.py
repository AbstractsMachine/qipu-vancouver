"""The model that reads a page, behind one small interface.

Three readers ship:

* ``AnthropicReader``: Claude through the Anthropic API (the reader the published runs used);
* ``OpenAICompatibleReader``: any server that speaks the OpenAI chat API with JSON-schema output, such as vLLM, Ollama or
  OpenRouter, so an open-weights model can do the reading;
* ``ReplayReader``: answers recorded from an earlier run, so the pipeline can be run and tested without a key or a network.

API keys are read from the environment only. They are never written to disk or printed.
"""

from __future__ import annotations

import importlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from qipu_records.read import schema


@dataclass(frozen=True)
class Reading:
    """One page as the model read it."""

    page_id: str
    items: list[dict[str, Any]]
    model: str
    prompt_version: str
    input_tokens: int = 0
    output_tokens: int = 0


class ReaderError(RuntimeError):
    pass


class Reader(Protocol):
    model: str

    def read(self, page_id: str, system_prompt: str, user_message: str) -> Reading: ...


def _parse(page_id: str, text: str) -> list[dict[str, Any]]:
    try:
        items = json.loads(text)["items"]
    except (ValueError, KeyError, TypeError) as error:
        raise ReaderError(f"{page_id}: the answer is not the expected JSON ({error})") from error
    if not isinstance(items, list):
        raise ReaderError(f"{page_id}: 'items' is not a list")
    return items


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise ReaderError(f"set {name} in the environment (it is read from there only, never stored)")
    return value


def _import(sdk: str) -> Any:
    try:
        return importlib.import_module(sdk)
    except ImportError:
        raise ReaderError(f"this reader needs the {sdk} package: pip install 'qipu-records[{sdk}]'") from None


@dataclass
class AnthropicReader:
    model: str = "claude-haiku-5-5"
    effort: str = "medium"
    max_tokens: int = 16000
    _client: Any = field(default=None, init=False, repr=False)

    def read(self, page_id: str, system_prompt: str, user_message: str) -> Reading:
        if self._client is None:
            key = _require_env("ANTHROPIC_API_KEY")
            anthropic = _import("anthropic")
            self._client = anthropic.Anthropic(api_key=key, max_retries=4)
        message = self._client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=[{"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}],
            output_config={"effort": self.effort, "format": {"type": "json_schema", "schema": schema.RESPONSE}},
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
    _client: Any = field(default=None, init=False, repr=False)

    def read(self, page_id: str, system_prompt: str, user_message: str) -> Reading:
        if self._client is None:
            openai = _import("openai")
            key = os.environ.get(self.api_key_env) or "not-needed"
            self._client = openai.OpenAI(base_url=self.base_url, api_key=key, max_retries=4)
        response = self._client.chat.completions.create(
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


class ReplayReader:
    """Answers recorded in a JSON Lines file, one ``{"page_id", "model", "prompt_version", "items"}`` per line."""

    def __init__(self, path: Path) -> None:
        self.model = "replay"
        self._readings: dict[str, Reading] = {}
        with path.open(encoding="utf-8") as lines:
            for line in lines:
                row = json.loads(line)
                self._readings[row["page_id"]] = Reading(row["page_id"], row["items"], row["model"], row["prompt_version"])

    def read(self, page_id: str, system_prompt: str, user_message: str) -> Reading:
        try:
            return self._readings[page_id]
        except KeyError:
            raise ReaderError(f"{page_id}: no recorded answer") from None
