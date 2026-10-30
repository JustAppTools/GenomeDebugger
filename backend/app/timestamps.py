"""Chronological keys without rewriting immutable timestamp provenance."""
from datetime import datetime, timezone


def timestamp_key(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("Missing timezone")
        return parsed.astimezone(timezone.utc).isoformat(timespec="microseconds")
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("Record timestamp must be a valid ISO 8601 datetime with a timezone") from exc


def legacy_timestamp_key(value):
    try:
        return timestamp_key(value)
    except ValueError:
        # Existing malformed dates remain readable, after all dated records.
        return None
