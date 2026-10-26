from typing import Any

import pytest

from qipu_records.cities import CITIES, get_city
from qipu_records.read import schema


@pytest.mark.parametrize(("city", "version"), [("vancouver", "v21-db2bcbe8fe"), ("san_francisco", "v21-6f12844404")])
def test_prompts_are_the_ones_the_published_runs_used(city: str, version: str) -> None:
    assert schema.prompt_version(get_city(city).system_prompt()) == version


def _objects(node: Any) -> list[dict[str, Any]]:
    if isinstance(node, dict):
        found = [node] if node.get("type") == "object" else []
        return found + [o for value in node.values() for o in _objects(value)]
    if isinstance(node, list):
        return [o for value in node for o in _objects(value)]
    return []


def test_every_object_is_strict() -> None:
    for obj in _objects(schema.RESPONSE):
        assert obj["additionalProperties"] is False
        assert obj["required"] == list(obj["properties"])


def test_user_message_carries_context_and_cuts_long_pages() -> None:
    message = schema.user_message("p" * 5000, "t" * 20000, 1974)
    assert "p" * schema.CONTEXT_CHARS in message
    assert "p" * (schema.CONTEXT_CHARS + 1) not in message
    assert "t" * schema.PAGE_TEXT_LIMIT in message
    assert "t" * (schema.PAGE_TEXT_LIMIT + 1) not in message
    assert "volume year 1974" in message


def test_unknown_city() -> None:
    with pytest.raises(ValueError, match="unknown city"):
        get_city("paris")
    assert set(CITIES) == {"vancouver", "san_francisco"}


def test_the_python_types_have_the_fields_the_schema_asks_for() -> None:
    item = schema.ITEM["properties"]
    assert set(schema.ModelItem.__annotations__) == set(item)
    assert set(schema.ModelParty.__annotations__) == set(item["parties"]["items"]["properties"])
    assert set(schema.ModelMoney.__annotations__) == set(item["money"]["items"]["properties"])
    assert set(schema.ModelPlace.__annotations__) == set(item["places"]["items"]["properties"])
    assert set(schema.ModelDate.__annotations__) == set(item["dates"]["items"]["properties"])
