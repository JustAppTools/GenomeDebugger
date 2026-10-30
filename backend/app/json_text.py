"""Decode untrusted JSON with bounded, lossless model values."""

import json

from .unicode_text import MAX_JSON_DEPTH, validate_json_values


def parse_json(text: str | bytes):
    try:
        value = json.loads(text)
    except RecursionError as exc:
        raise ValueError(f'JSON nesting exceeds the supported depth of {MAX_JSON_DEPTH}') from exc
    validate_json_values(value, max_depth=MAX_JSON_DEPTH)
    return value
