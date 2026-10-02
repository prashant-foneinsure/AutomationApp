"""pyodbc connection handling.

One connection per request. pyodbc connections are not safe to share across
threads, and FastAPI runs sync endpoints in a threadpool, so opening per
request is the correct shape here rather than a shared global connection.
"""
import time

import pyodbc

from .. import config


def server_clause() -> str:
    """Named instance -> browser resolves the dynamic port.
    Default instance -> an explicit port may be pinned."""
    if config.DB_INSTANCE:
        return f"{config.DB_SERVER}\\{config.DB_INSTANCE}"
    if config.DB_PORT:
        return f"{config.DB_SERVER},{config.DB_PORT}"
    return config.DB_SERVER


def connection_string(database: str) -> str:
    # NOTE: a "Timeout=" attribute here BREAKS the connection on this server
    # (reproducible: every string containing it failed prelogin with 08001).
    # The login timeout is passed to pyodbc.connect(timeout=...) instead.
    parts = [
        f"DRIVER={{{config.DB_DRIVER}}}",
        f"SERVER={server_clause()}",
        f"DATABASE={database}",
        # ODBC Driver 18 defaults Encrypt=yes; Driver 17 defaults to no.
        # Setting both explicitly keeps the string driver-agnostic.
        "Encrypt=no",
        "TrustServerCertificate=yes",
    ]
    if config.DB_TRUSTED:
        # Mandatory. The instances report IsIntegratedSecurityOnly=1, so
        # there is no SQL login to fall back to and omitting this fails with
        # "Login failed" 28000.
        parts.append("Trusted_Connection=yes")
    else:
        parts.append(f"UID={config.DB_USER};PWD={config.DB_PASSWORD}")
    return ";".join(parts)


# Transient conditions seen on this server, mostly while a freshly created
# database is still initialising: SQL Server aborts the connection during
# prelogin (08001) or the host resets it (10054). Verified to affect both
# pyodbc and sqlcmd, so it is server-side, not a connection-string problem.
TRANSIENT_CODES = {"08001", "08006", "10054", "HY000", "08S01"}
# Kept small on purpose. Each attempt can burn DB_TIMEOUT seconds, so a long
# retry budget turns a transient blip into a multi-minute stall across the
# many short connections a schema apply makes. init_db passes a larger budget
# because it is not on a request path.
CONNECT_ATTEMPTS = 3


def _is_transient(exc: Exception) -> bool:
    args = getattr(exc, "args", ())
    if not args:
        return False
    code = args[0]
    if not isinstance(code, str):
        return False
    return code in TRANSIENT_CODES


def connect(database: str | None = None, autocommit: bool = False,
            attempts: int | None = None) -> pyodbc.Connection:
    """Open a connection, retrying transient prelogin/resets with backoff.

    Without this, opening a connection can fail sporadically -- most visibly
    immediately after CREATE DATABASE, and on a freshly started instance.
    """
    cs = connection_string(database or config.DB_NAME)
    budget = attempts or CONNECT_ATTEMPTS
    delay = 0.3
    for attempt in range(1, budget + 1):
        try:
            conn = pyodbc.connect(cs, timeout=config.DB_TIMEOUT)
            if autocommit:
                conn.autocommit = True
            return conn
        except pyodbc.Error as exc:
            if attempt == budget or not _is_transient(exc):
                raise
            time.sleep(delay)
            delay = min(delay * 2, 2.0)
    raise RuntimeError("unreachable")  # pragma: no cover


class cursor:
    """Context manager yielding a row-as-dict cursor inside a transaction.

    Pass autocommit=True for statements that are illegal inside one, such as
    CREATE DATABASE.
    """

    def __init__(self, database: str | None = None, commit: bool = True,
                 autocommit: bool = False, attempts: int | None = None):
        self._database = database
        self._commit = commit
        self._autocommit = autocommit
        self._attempts = attempts
        self._conn = None

    def __enter__(self) -> pyodbc.Cursor:
        self._conn = connect(self._database, autocommit=self._autocommit,
                             attempts=self._attempts)
        cur = self._conn.cursor()
        cur.fast_executemany = True
        return cur

    def __exit__(self, exc_type, exc, tb):
        try:
            if self._autocommit:
                pass  # driver already committed or rolled back
            elif exc_type is None and self._commit:
                self._conn.commit()
            else:
                self._conn.rollback()
        finally:
            self._conn.close()
        return False


def query(sql: str, params: tuple = (), database: str | None = None) -> list[dict]:
    with cursor(database, commit=False) as cur:
        cur.execute(sql, params)
        columns = [c[0] for c in cur.description] if cur.description else []
        return [dict(zip(columns, row)) for row in cur.fetchall()]


def query_one(sql: str, params: tuple = (), database: str | None = None) -> dict | None:
    rows = query(sql, params, database)
    return rows[0] if rows else None


def scalar(sql: str, params: tuple = (), database: str | None = None):
    row = query_one(sql, params, database)
    if not row:
        return None
    return next(iter(row.values()))


def execute(sql: str, params: tuple = (), database: str | None = None) -> int:
    """Run a DML statement, returning rows affected."""
    with cursor(database) as cur:
        return cur.execute(sql, params).rowcount


# ---------- error translation ----------
# pyodbc puts the SQLSTATE in args[0] (e.g. "23000" for any integrity
# constraint violation); the native SQL Server error number (2601/2627) only
# appears inside the message text. Checking args[0] against 2627 silently
# never matches, so match on SQLSTATE plus the constraint name instead.
SQLSTATE_INTEGRITY = "23000"
SQLSTATE_SYNTAX = "42000"

UNIQUE_CONSTRAINTS = ("UQ_TestGroups_Name", "UQ_ApiTests_Group_Name")


def is_unique_violation(exc: Exception) -> bool:
    """True for a duplicate name on one of our UNIQUE constraints, which the
    routers surface as 409. Narrow on purpose: an integrity error we do not
    recognise is a genuine bug and should not be softened into a 409."""
    args = getattr(exc, "args", ())
    if not args or args[0] != SQLSTATE_INTEGRITY:
        return False
    text = str(exc)
    return any(name in text for name in UNIQUE_CONSTRAINTS)


def describe(exc: Exception) -> str:
    """Compact, log-friendly rendering of a pyodbc error."""
    args = getattr(exc, "args", ())
    head = f"{args[0]}: {args[1]}" if len(args) > 1 else str(exc)
    return head.replace("\n", " ").replace("\r", " ")[:400]
