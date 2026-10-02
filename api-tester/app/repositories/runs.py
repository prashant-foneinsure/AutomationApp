"""TestRuns, RunCases and CaseFeedback -- history and the learning signal."""
import json

from ..db import connection
from ..serializers import shape

RUN_COLUMNS = ("RunId", "TestId", "Outcome", "StartedAt", "FinishedAt",
               "BaselineStatus", "PassedCount", "TotalCount", "DurationMs",
               "GroupRunId")
CASE_COLUMNS = ("CaseId", "RunId", "Name", "Category", "Method", "Body",
                "RemoveHeaders", "ExpectedStatus", "ActualStatus", "TimeMs",
                "Passed", "Origin", "RequestJson", "ResponseHeaders", "ResponseBody")

# CaseFeedback is append-only, so judging a case twice leaves two rows. Only the
# newest one reflects the user's current opinion, so the UI and the prompt both
# read through this predicate instead of counting raw history.
_IS_LATEST = ("f.FeedbackId = (SELECT TOP (1) f2.FeedbackId FROM CaseFeedback f2 "
              "WHERE f2.CaseId = f.CaseId "
              "ORDER BY f2.CreatedAt DESC, f2.FeedbackId DESC)")


# ---------- runs ----------
def start_run(test_id: int, outcome: str = "completed", group_run_id: int | None = None) -> int:
    with connection.cursor() as cur:
        cur.execute("INSERT INTO TestRuns (TestId, Outcome, GroupRunId) "
                    "OUTPUT INSERTED.RunId VALUES (?, ?, ?)", (test_id, outcome, group_run_id))
        return int(cur.fetchone()[0])


def finish_run(run_id: int, baseline_status: int | None, passed: int, total: int,
               duration_ms: int, outcome: str = "completed") -> None:
    connection.execute(
        "UPDATE TestRuns SET BaselineStatus = ?, PassedCount = ?, TotalCount = ?, "
        "DurationMs = ?, Outcome = ?, FinishedAt = SYSUTCDATETIME() WHERE RunId = ?",
        (baseline_status, passed, total, duration_ms, outcome, run_id))


def tag_group_run(run_id: int, group_run_id: int) -> None:
    """Point a run at the group execution it belongs to. The first run of a
    group execution is its own GroupRunId, so selecting by it returns the whole
    chain rather than everything but the first step."""
    connection.execute(
        "UPDATE TestRuns SET GroupRunId = ? WHERE RunId = ?", (group_run_id, run_id))


def list_runs(test_id: int, limit: int = 50) -> list[dict]:
    # GroupId is carried so the history page can link back to the test without
    # having to open a run first.
    return shape(connection.query(
        f"SELECT TOP (?) {', '.join('r.' + c for c in RUN_COLUMNS)}, t.GroupId "
        "FROM TestRuns r JOIN ApiTests t ON t.TestId = r.TestId "
        "WHERE r.TestId = ? ORDER BY r.StartedAt DESC, r.RunId DESC", (limit, test_id)))


def get_run(run_id: int) -> dict | None:
    """One run plus its GroupId. The UI needs the group to build a link back to
    the test, since the run row itself only stores TestId."""
    return shape(connection.query_one(
        "SELECT " + ", ".join(f"r.{c}" for c in RUN_COLUMNS) + ", t.GroupId "
        "FROM TestRuns r JOIN ApiTests t ON t.TestId = r.TestId "
        "WHERE r.RunId = ?", (run_id,)))


def recent_runs(limit: int = 25) -> list[dict]:
    """Latest activity across every group, for the landing grid."""
    return shape(connection.query("""
        SELECT TOP (?) r.RunId, r.TestId, t.GroupId, t.Name AS TestName,
               g.Name AS GroupName, r.Outcome, r.StartedAt, r.BaselineStatus,
               r.PassedCount, r.TotalCount, r.DurationMs
          FROM TestRuns r
          JOIN ApiTests t ON t.TestId = r.TestId
          JOIN TestGroups g ON g.GroupId = t.GroupId
         ORDER BY r.StartedAt DESC, r.RunId DESC
    """, (limit,)))


# ---------- cases ----------
def add_cases(run_id: int, results: list[dict]) -> list[int]:
    """Persist the outcome of each case. Returns the new CaseIds in order."""
    if not results:
        return []
    rows = []
    for r in results:
        rows.append((
            run_id,
            (r.get("name") or "case")[:300],
            (r.get("category") or "")[:50],
            (r.get("method") or None),
            r.get("body"),
            json.dumps(r.get("remove_headers")) if r.get("remove_headers") else None,
            r.get("expected_status"),
            r.get("actual_status"),
            int(r.get("time_ms") or 0),
            1 if r.get("passed") else 0,
            json.dumps(r.get("request") or {}),
            json.dumps(r.get("response_headers") or {}),
            r.get("response"),
            (r.get("origin") or "generated")[:20],
        ))
    with connection.cursor() as cur:
        cur.fast_executemany = True
        cur.executemany(
            "INSERT INTO RunCases (RunId, Name, Category, Method, Body, RemoveHeaders, "
            "ExpectedStatus, ActualStatus, TimeMs, Passed, RequestJson, ResponseHeaders, "
            "ResponseBody, Origin) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
        cur.execute("SELECT CaseId FROM RunCases WHERE RunId = ? ORDER BY CaseId", (run_id,))
        return [int(row[0]) for row in cur.fetchall()]


def list_cases(run_id: int) -> list[dict]:
    rows = connection.query(
        f"SELECT {', '.join(CASE_COLUMNS)}, v.Verdict FROM RunCases c "
        "OUTER APPLY (SELECT TOP (1) f.Verdict FROM CaseFeedback f "
        "  WHERE f.CaseId = c.CaseId ORDER BY f.CreatedAt DESC, f.FeedbackId DESC) v "
        "WHERE c.RunId = ? ORDER BY c.CaseId", (run_id,))
    return [_shape_case(r) for r in rows]


def _shape_case(row: dict) -> dict:
    """Parse the JSON columns. The stored text is left as-is when it is not
    valid JSON rather than dropped, so bad data stays visible in the UI."""
    row = shape(row)
    row["request"] = _json_or_text(row.pop("request_json", None))
    row["remove_headers"] = _json_or_text(row.get("remove_headers"))
    return row


def _json_or_text(raw):
    if raw is None or raw == "":
        return None
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return raw


def get_case(case_id: int) -> dict | None:
    return shape(connection.query_one(
        "SELECT CaseId, RunId, Name, Category, Method, Body, RemoveHeaders, "
        "ExpectedStatus, ActualStatus, TimeMs, Passed, Origin "
        "FROM RunCases WHERE CaseId = ?", (case_id,)))


def accepted_cases_for(test_id: int, limit: int = 6) -> list[dict]:
    """Cases a human accepted, for reuse as few-shot examples. Reads through
    _IS_LATEST so a case later rejected is not replayed as accepted."""
    return shape(connection.query(f"""
        SELECT TOP (?) c.Name, c.Category, c.Method, c.Body, c.ExpectedStatus
          FROM CaseFeedback f
          JOIN RunCases c ON c.CaseId = f.CaseId
         WHERE f.TestId = ? AND f.Verdict = 'accepted' AND {_IS_LATEST}
         ORDER BY f.CreatedAt DESC
    """, (limit, test_id)))


def rejected_categories_for(test_id: int) -> dict[str, int]:
    """category -> rejection count, so the prompt can warn about weak spots."""
    rows = connection.query(f"""
        SELECT c.Category, COUNT(*) AS Rejected
          FROM CaseFeedback f
          JOIN RunCases c ON c.CaseId = f.CaseId
         WHERE f.TestId = ? AND f.Verdict = 'rejected' AND {_IS_LATEST}
         GROUP BY c.Category
    """, (test_id,))
    return {r["Category"]: r["Rejected"] for r in rows}


def category_stats_for(test_id: int) -> dict[str, dict]:
    """Per-category pass rate across all stored cases for this test."""
    rows = connection.query("""
        SELECT Category,
               COUNT(*) AS Total,
               SUM(CASE WHEN Passed = 1 THEN 1 ELSE 0 END) AS Passed
          FROM RunCases c
          JOIN TestRuns r ON r.RunId = c.RunId
         WHERE r.TestId = ?
         GROUP BY Category
    """, (test_id,))
    return {r["Category"]: {"total": r["Total"], "passed": r["Passed"] or 0}
            for r in rows}


def learned_case_count(test_id: int) -> int:
    """Cases the user has judged, counted once each however many times they
    clicked. DISTINCT matches the "you have judged this many cases" wording."""
    return connection.scalar(
        "SELECT COUNT(DISTINCT CaseId) FROM CaseFeedback WHERE TestId = ?",
        (test_id,)) or 0


# ---------- feedback ----------
def record_feedback(case_id: int, test_id: int, verdict: str, note: str | None = None) -> int:
    with connection.cursor() as cur:
        cur.execute("INSERT INTO CaseFeedback (CaseId, TestId, Verdict, Note) "
                    "OUTPUT INSERTED.FeedbackId VALUES (?, ?, ?, ?)",
                    (case_id, test_id, verdict, note))
        return int(cur.fetchone()[0])


def feedback_for_case(case_id: int) -> list[dict]:
    return shape(connection.query(
        "SELECT FeedbackId, Verdict, Note, CreatedAt FROM CaseFeedback "
        "WHERE CaseId = ? ORDER BY CreatedAt DESC", (case_id,)))
