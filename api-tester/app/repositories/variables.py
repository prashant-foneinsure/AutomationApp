"""GroupVariables: values captured from a passing run, reused by later tests."""
from ..db import connection
from ..serializers import shape


def list_for_group(group_id: int) -> list[dict]:
    return shape(connection.query(
        "SELECT Name, Value, JsonValue, SourceTestId, SourceRunId, UpdatedAt "
        "FROM GroupVariables WHERE GroupId = ? ORDER BY Name", (group_id,)))


def as_map(group_id: int) -> dict:
    """name -> value, the shape the placeholder substitution wants."""
    return {r["Name"]: (r["Value"] if r["Value"] is not None else "")
            for r in connection.query(
                "SELECT Name, Value FROM GroupVariables WHERE GroupId = ?", (group_id,))}


def upsert_many(group_id: int, captured: list[dict], source_test_id: int | None = None,
                source_run_id: int | None = None) -> list[str]:
    """Latest capture wins. Returns the names written."""
    if not captured:
        return []
    # One complete parameter tuple per row: the five VALUES columns plus GroupId
    # twice, because the MERGE uses it both in the ON clause and the INSERT.
    # Appending the GroupIds once at the end only ever worked for a single row.
    rows = [(c["name"], c.get("value"), c.get("json_value"),
             source_test_id, source_run_id, group_id, group_id)
            for c in captured]
    with connection.cursor() as cur:
        cur.fast_executemany = True
        cur.executemany(
            "MERGE GroupVariables AS t "
            "USING (VALUES (?, ?, ?, ?, ?)) AS s (Name, Value, JsonValue, SourceTestId, SourceRunId) "
            "ON t.GroupId = ? AND t.Name = s.Name "
            "WHEN MATCHED THEN UPDATE SET t.Value = s.Value, t.JsonValue = s.JsonValue, "
            "     t.SourceTestId = s.SourceTestId, t.SourceRunId = s.SourceRunId, "
            "     t.UpdatedAt = SYSUTCDATETIME() "
            "WHEN NOT MATCHED THEN INSERT (GroupId, Name, Value, JsonValue, SourceTestId, SourceRunId, UpdatedAt) "
            "     VALUES (?, s.Name, s.Value, s.JsonValue, s.SourceTestId, s.SourceRunId, SYSUTCDATETIME());",
            rows)
    return [c["name"] for c in captured]


def upsert_value(group_id: int, name: str, value: str) -> bool:
    """Write one value by hand. Returns True when the name was newly created.

    This is an upsert rather than a plain UPDATE because seeding a value by hand
    means creating a name that does not exist yet, and a plain UPDATE would
    silently affect zero rows and report success. (GroupId, Name) is the primary
    key, so the merge has a unique key to match on.
    """
    with connection.cursor() as cur:
        cur.execute(
            "MERGE GroupVariables AS t "
            "USING (VALUES (?, ?)) AS s (Name, Value) "
            "ON t.GroupId = ? AND t.Name = s.Name "
            "WHEN MATCHED THEN UPDATE SET t.Value = s.Value, "
            "     t.UpdatedAt = SYSUTCDATETIME() "
            "WHEN NOT MATCHED THEN INSERT (GroupId, Name, Value, UpdatedAt) "
            "     VALUES (?, s.Name, s.Value, SYSUTCDATETIME()) "
            "OUTPUT $action;",
            (name, value, group_id, group_id))
        row = cur.fetchone()
    return bool(row) and str(row[0]).upper() == "INSERT"


def delete(group_id: int, name: str) -> int:
    return connection.execute(
        "DELETE FROM GroupVariables WHERE GroupId = ? AND Name = ?", (group_id, name))


def clear_group(group_id: int) -> int:
    return connection.execute("DELETE FROM GroupVariables WHERE GroupId = ?", (group_id,))
