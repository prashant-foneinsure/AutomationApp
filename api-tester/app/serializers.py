"""Shaping helpers for API responses.

Two inconsistencies this fixes, both of which would have bitten the frontend:

1. The database uses the project's existing PascalCase convention
   (GroupId, SortOrder) while request bodies use snake_case. Returning raw
   rows would force the UI to mix conventions, so responses are snake_case.
2. pyodbc returns naive datetime for datetime2. Values are written with
   SYSUTCDATETIME(), so they are UTC and are serialised with an explicit Z
   rather than being silently treated as local time.
"""
import re

_CAMEL = re.compile(r"(?<!^)(?=[A-Z])")


def to_snake(name: str) -> str:
    return _CAMEL.sub("_", name).lower()


def shape(row):
    """Convert one DB row (or None) to a JSON-ready snake_case dict."""
    if row is None:
        return None
    if isinstance(row, list):
        return [shape(r) for r in row]
    if not isinstance(row, dict):
        return row
    out = {}
    for key, value in row.items():
        out[to_snake(key)] = _iso(value)
    return out


def _iso(value):
    if hasattr(value, "isoformat") and not isinstance(value, str):
        iso = value.isoformat()
        # Naive datetimes here are UTC by construction (SYSUTCDATETIME).
        return iso + "Z" if "T" in iso and not iso.endswith(("Z", "+00:00")) else iso
    return value
