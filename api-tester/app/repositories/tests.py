"""ApiTests: individual cURL definitions inside a group."""
import json

from ..db import connection
from ..serializers import shape

COLUMNS = "TestId, GroupId, Name, Curl, HttpMethod, Extractors, SortOrder, Notes, CreatedAt, UpdatedAt"


def _shape(row: dict | None) -> dict | None:
    row = shape(row)
    if not row:
        return None
    # Return extractors as real JSON, not a string, so the UI can bind to it.
    raw = row.get("extractors")
    if raw:
        try:
            row["extractors"] = json.loads(raw)
        except (TypeError, ValueError):
            row["extractors"] = []
    else:
        row["extractors"] = []
    return row


def list_tests(group_id: int) -> list[dict]:
    rows = connection.query(
        f"SELECT {COLUMNS} FROM ApiTests WHERE GroupId = ? "
        "ORDER BY SortOrder, TestId", (group_id,))
    return [_shape(r) for r in rows]


def get_test(test_id: int) -> dict | None:
    return _shape(connection.query_one(
        f"SELECT {COLUMNS} FROM ApiTests WHERE TestId = ?", (test_id,)))


def next_sort_order(group_id: int) -> int:
    highest = connection.scalar(
        "SELECT MAX(SortOrder) FROM ApiTests WHERE GroupId = ?", (group_id,))
    return (highest or 0) + 10


def create_test(group_id: int, name: str, curl: str,
                http_method: str | None = None, sort_order: int | None = None,
                notes: str | None = None, extractors: list | None = None) -> int:
    order = next_sort_order(group_id) if sort_order is None else sort_order
    payload = json.dumps(extractors) if extractors else None
    with connection.cursor() as cur:
        cur.execute(
            "INSERT INTO ApiTests (GroupId, Name, Curl, HttpMethod, SortOrder, Notes, Extractors) "
            "OUTPUT INSERTED.TestId VALUES (?, ?, ?, ?, ?, ?, ?)",
            (group_id, name, curl, http_method, order, notes, payload))
        return int(cur.fetchone()[0])


_UPDATABLE = {
    "name": "Name", "curl": "Curl", "http_method": "HttpMethod",
    "sort_order": "SortOrder", "notes": "Notes",
}


def update_test(test_id: int, **fields) -> None:
    sets, params = [], []
    for key, column in _UPDATABLE.items():
        if key in fields and fields[key] is not None:
            sets.append(f"{column} = ?")
            params.append(fields[key])
    if "extractors" in fields:
        value = fields["extractors"]
        sets.append("Extractors = ?")
        params.append(json.dumps(value) if value else None)
    if not sets:
        return
    sets.append("UpdatedAt = SYSUTCDATETIME()")
    params.append(test_id)
    connection.execute(
        f"UPDATE ApiTests SET {', '.join(sets)} WHERE TestId = ?", tuple(params))


def delete_test(test_id: int) -> int:
    return connection.execute("DELETE FROM ApiTests WHERE TestId = ?", (test_id,))


def exists(test_id: int) -> bool:
    return connection.scalar(
        "SELECT COUNT(*) FROM ApiTests WHERE TestId = ?", (test_id,)) > 0


def group_id_for(test_id: int) -> int | None:
    return connection.scalar("SELECT GroupId FROM ApiTests WHERE TestId = ?", (test_id,))
