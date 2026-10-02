"""TestGroups: the top-level container ("Event API testing")."""
from ..db import connection
from ..serializers import shape


def list_groups() -> list[dict]:
    return shape(connection.query("""
        SELECT g.GroupId, g.Name, g.Description, g.CreatedAt, g.UpdatedAt,
               (SELECT COUNT(*) FROM ApiTests t WHERE t.GroupId = g.GroupId) AS test_count,
               (SELECT MAX(r.StartedAt) FROM TestRuns r
                  JOIN ApiTests t2 ON t2.TestId = r.TestId
                 WHERE t2.GroupId = g.GroupId) AS last_run_at
          FROM TestGroups g
         ORDER BY CASE WHEN (SELECT MAX(r.StartedAt) FROM TestRuns r
                               JOIN ApiTests t2 ON t2.TestId = r.TestId
                              WHERE t2.GroupId = g.GroupId) IS NULL THEN 1 ELSE 0 END,
                  (SELECT MAX(r.StartedAt) FROM TestRuns r
                     JOIN ApiTests t2 ON t2.TestId = r.TestId
                    WHERE t2.GroupId = g.GroupId) DESC, g.Name
    """))


def get_group(group_id: int) -> dict | None:
    return shape(connection.query_one(
        "SELECT GroupId, Name, Description, CreatedAt, UpdatedAt "
        "FROM TestGroups WHERE GroupId = ?", (group_id,)))


def create_group(name: str, description: str | None = None) -> int:
    with connection.cursor() as cur:
        cur.execute("INSERT INTO TestGroups (Name, Description) "
                    "OUTPUT INSERTED.GroupId VALUES (?, ?)", (name, description))
        return int(cur.fetchone()[0])


def update_group(group_id: int, name: str, description: str | None = None) -> None:
    connection.execute(
        "UPDATE TestGroups SET Name = ?, Description = ?, "
        "UpdatedAt = SYSUTCDATETIME() WHERE GroupId = ?",
        (name, description, group_id))


def delete_group(group_id: int) -> int:
    """Cascades to tests, runs, cases, feedback and variables."""
    return connection.execute("DELETE FROM TestGroups WHERE GroupId = ?", (group_id,))


def exists(group_id: int) -> bool:
    return connection.scalar(
        "SELECT COUNT(*) FROM TestGroups WHERE GroupId = ?", (group_id,)) > 0
