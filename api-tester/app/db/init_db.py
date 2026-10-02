"""Create AutomationAppDb if missing, then apply schema.sql.

Run directly:  python -m app.db.init_db
Safe to re-run -- both steps are guarded.
"""
import os
import re
import sys

from . import connection
from .. import config

SCHEMA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schema.sql")


def database_exists() -> bool:
    # Must query master: connecting to the target database fails outright when
    # it does not exist yet, which is exactly the case we are bootstrapping.
    return connection.scalar(
        "SELECT CASE WHEN DB_ID(?) IS NULL THEN 0 ELSE 1 END", (config.DB_NAME,),
        database="master",
    ) == 1


def create_database() -> bool:
    """Create the database if absent. CREATE DATABASE must be its own batch,
    so the existence check happens first and separately."""
    if database_exists():
        return False
    # Ident is not parameterisable, so the name is validated instead of
    # interpolated blindly.
    if not re.fullmatch(r"[A-Za-z0-9_]+", config.DB_NAME):
        raise ValueError(f"Refusing to create database with unsafe name: {config.DB_NAME!r}")
    with connection.cursor("master", autocommit=True) as cur:
        cur.execute(f"CREATE DATABASE [{config.DB_NAME}]")
    return True


def wait_until_ready(attempts: int = 40, delay: float = 0.5) -> None:
    """A freshly created database is briefly unavailable: connections fail
    prelogin while its files initialise. Poll until it reports ONLINE, then
    prove a real connection works."""
    import time

    for _ in range(attempts):
        try:
            row = connection.query_one(
                "SELECT state_desc, user_access_desc FROM sys.databases "
                "WHERE name = ?", (config.DB_NAME,), database="master")
            if row and row["state_desc"] == "ONLINE" and row["user_access_desc"] != "RESTORE_READ_ONLY":
                # Generous budget: this is the step most likely to hit a
                # transient, and it is not on a request path.
                connection.scalar("SELECT 1", database=config.DB_NAME)
                return
        except Exception:
            pass
        time.sleep(delay)
    raise RuntimeError(
        f"{config.DB_NAME} did not become ready after {attempts * delay:.0f}s. "
        f"Check SQL Server is running and reachable at "
        f"{connection.server_clause()}."
    )


def batches() -> list[str]:
    """Split schema.sql on GO, which pyodbc does not understand as a batch
    separator the way sqlcmd does."""
    with open(SCHEMA_PATH, "r", encoding="utf-8") as fh:
        raw = fh.read()
    parts = re.split(r"(?im)^\s*GO\s*$", raw)
    return [p.strip() for p in parts if p.strip()]


def apply_schema() -> int:
    statements = batches()
    applied = 0
    for statement in statements:
        with connection.cursor(attempts=8) as cur:
            cur.execute(statement)
        applied += 1
    return applied


def table_names() -> list[str]:
    return [
        r["name"]
        for r in connection.query(
            "SELECT name FROM sys.tables WHERE name NOT LIKE 'sys%' ORDER BY name")
    ]


# Every index/constraint the app depends on. A missing entry means the apply
# step silently skipped a statement, which is easy to do with GO-separated
# batches and an OBJECT_ID guard that refers to the table created in the
# previous batch.
REQUIRED_INDEXES = {
    "TestGroups": ["PK_TestGroups", "UQ_TestGroups_Name"],
    "ApiTests": ["PK_ApiTests", "UQ_ApiTests_Group_Name", "IX_ApiTests_Group_SortOrder"],
    "TestRuns": ["PK_TestRuns", "IX_TestRuns_TestId_StartedAt"],
    "RunCases": ["PK_RunCases", "IX_RunCases_RunId"],
    "CaseFeedback": ["PK_CaseFeedback", "IX_CaseFeedback_TestId"],
    "GroupVariables": ["PK_GroupVariables"],
}


def audit() -> list[str]:
    """Return a list of human-readable problems; empty means the schema is
    exactly what the repositories assume."""
    present: dict[str, set[str]] = {}
    for row in connection.query(
        "SELECT t.name AS tbl, i.name AS idx FROM sys.indexes i "
        "JOIN sys.tables t ON t.object_id = i.object_id "
        "WHERE t.name NOT LIKE 'sys%' AND i.type > 0"
    ):
        present.setdefault(row["tbl"], set()).add(row["idx"])
    problems = []
    for table, expected in REQUIRED_INDEXES.items():
        have = set(present.get(table, []))
        for name in expected:
            if name not in have:
                problems.append(f"missing index/constraint {table}.{name}")
    return problems


def main() -> int:
    print(f"driver     : {config.DB_DRIVER}")
    print(f"server     : {connection.server_clause()}")
    print(f"auth       : {'Windows integrated' if config.DB_TRUSTED else 'SQL login'}")
    print(f"database   : {config.DB_NAME}")

    try:
        created = create_database()
    except Exception as exc:
        print(f"FAILED to reach SQL Server at {connection.server_clause()}")
        print(f"  {connection.describe(exc)}")
        print("  This instance is Windows-auth only; run as the Windows account")
        print("  that has access. A login timeout means the instance/browser is down.")
        return 1

    print(f"database   : {'CREATED' if created else 'already present'}")
    wait_until_ready()
    print("database   : ONLINE and accepting connections")
    count = apply_schema()
    print(f"schema     : {count} statements applied")
    print(f"tables     : {', '.join(table_names())}")

    problems = audit()
    if problems:
        print("audit      : FAILED")
        for problem in problems:
            print(f"            - {problem}")
        return 2
    print("audit      : all expected indexes and constraints present")

    # Prove the app-facing credentials work, not just the master connection.
    connection.scalar("SELECT 1")
    print("verify     : SELECT 1 OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
