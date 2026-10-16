"""Provider response JSON Schema validation shared by model adapters."""

from __future__ import annotations

import json
from collections.abc import Mapping

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError

from ..core.run import JsonObject, JsonValue


def request_json_schema(options: JsonObject) -> Mapping[str, object] | None:
    for key, value in options.items:
        if key != "json_schema":
            continue
        plain = _plain_json(value)
        if not isinstance(plain, Mapping):
            raise TypeError("json_schema must be an object")
        return plain
    return None


def validate_json_response(content: JsonValue, schema: Mapping[str, object]) -> None:
    if not isinstance(content, str):
        raise TypeError("structured response content must be a JSON string")
    try:
        instance = json.loads(content)
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(instance)
    except (json.JSONDecodeError, SchemaError, ValidationError) as exc:
        raise ValueError("structured response violates JSON Schema") from exc


def _plain_json(value: JsonValue) -> object:
    if isinstance(value, JsonObject):
        return {key: _plain_json(item) for key, item in value.items}
    if isinstance(value, tuple):
        return [_plain_json(item) for item in value]
    return value


__all__ = ["request_json_schema", "validate_json_response"]
