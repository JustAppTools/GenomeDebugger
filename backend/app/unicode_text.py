"""Reject text and numbers that cannot survive JSON serialization unchanged."""

import math

MAX_JSON_DEPTH = 64
# Leave room for source, bundle, and saved-result envelopes around admitted JSON.
MAX_MODEL_JSON_DEPTH = MAX_JSON_DEPTH + 32


def validate_json_values(value, *, max_depth: int = MAX_MODEL_JSON_DEPTH) -> None:
    pending = [(value, 0)]
    while pending:
        item, depth = pending.pop()
        if isinstance(item, str):
            try:
                item.encode('utf-8')
            except UnicodeEncodeError as exc:
                raise ValueError('Text contains an invalid Unicode surrogate; supply valid Unicode text') from exc
        elif isinstance(item, float) and not math.isfinite(item):
            raise ValueError('JSON numbers must be finite; NaN, Infinity, and overflowing numbers are unsupported')
        elif isinstance(item, dict):
            depth += 1
            if depth > max_depth:
                raise ValueError(f'JSON nesting exceeds the supported depth of {max_depth}')
            pending.extend((child, depth) for child in item.keys())
            pending.extend((child, depth) for child in item.values())
        elif isinstance(item, (list, tuple)):
            depth += 1
            if depth > max_depth:
                raise ValueError(f'JSON nesting exceeds the supported depth of {max_depth}')
            pending.extend((child, depth) for child in item)


# Retain the existing import name for callers using the earlier text validator.
validate_unicode = validate_json_values
