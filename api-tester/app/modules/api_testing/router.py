"""Routes for the API Testing module. Mounted at /api/modules/api-testing."""
from fastapi import APIRouter, HTTPException

from ...compat import to_dict
from ...db import connection
from ...repositories import groups as groups_repo
from ...repositories import runs as runs_repo
from ...repositories import tests as tests_repo
from ...repositories import variables as variables_repo
from ...services import llm
from ..base import ModuleInfo, TestModule
from . import service
from .schemas import (AdhocRequest, FeedbackRequest, GroupCreate, GroupRunRequest,
                      GroupUpdate, RunOptions, TestCreate, TestUpdate,
                      VariableUpdate)

PREFIX = "/api/modules/api-testing"
VALID_VERDICTS = ("accepted", "rejected", "edited")


def _not_found(what: str) -> HTTPException:
    return HTTPException(404, f"{what} not found")


def _db_error(exc: Exception, what: str) -> HTTPException:
    """Map a DB failure to a response. Duplicate names are the user's problem
    to fix (409); anything else is a bug and must not be softened."""
    if connection.is_unique_violation(exc):
        return HTTPException(409, f"A {what} with that name already exists")
    return HTTPException(500, f"Database error: {connection.describe(exc)}")


router = APIRouter(prefix=PREFIX, tags=["api-testing"])


# ---------- status ----------
@router.get("/status")
def status():
    """What the UI needs before it can do anything useful."""
    return {
        "model": llm.config.MODEL,
        "ollama_available": llm.is_available(),
        "llm_timeout": llm.config.LLM_TIMEOUT,
    }


@router.get("/recent")
def recent(limit: int = 25):
    return runs_repo.recent_runs(limit)


# ---------- groups ----------
@router.get("/groups")
def list_groups():
    return groups_repo.list_groups()


@router.post("/groups", status_code=201)
def create_group(body: GroupCreate):
    try:
        group_id = groups_repo.create_group(body.name.strip(), body.description)
    except Exception as exc:
        raise _db_error(exc, "group") from exc
    return {"group_id": group_id}


@router.get("/groups/{group_id}")
def get_group(group_id: int):
    group = groups_repo.get_group(group_id)
    if not group:
        raise _not_found("Group")
    return group


@router.put("/groups/{group_id}")
def update_group(group_id: int, body: GroupUpdate):
    if not groups_repo.exists(group_id):
        raise _not_found("Group")
    try:
        groups_repo.update_group(group_id, body.name.strip(), body.description)
    except Exception as exc:
        raise _db_error(exc, "group") from exc
    return groups_repo.get_group(group_id)


@router.delete("/groups/{group_id}")
def delete_group(group_id: int):
    if not groups_repo.exists(group_id):
        raise _not_found("Group")
    groups_repo.delete_group(group_id)
    return {"deleted": group_id}


# ---------- tests in a group ----------
@router.get("/groups/{group_id}/tests")
def list_tests(group_id: int):
    if not groups_repo.exists(group_id):
        raise _not_found("Group")
    return tests_repo.list_tests(group_id)


@router.post("/groups/{group_id}/tests", status_code=201)
def create_test(group_id: int, body: TestCreate):
    if not groups_repo.exists(group_id):
        raise _not_found("Group")
    try:
        test_id = tests_repo.create_test(
            group_id, body.name.strip(), body.curl.strip(),
            body.http_method, body.sort_order, body.notes, body.extractors)
    except Exception as exc:
        raise _db_error(exc, "test") from exc
    return {"test_id": test_id}


@router.put("/tests/{test_id}")
def update_test(test_id: int, body: TestUpdate):
    if not tests_repo.exists(test_id):
        raise _not_found("Test")
    payload = to_dict(body, exclude_unset=True)
    if "name" in payload and payload["name"]:
        payload["name"] = payload["name"].strip()
    if "curl" in payload and payload["curl"]:
        payload["curl"] = payload["curl"].strip()
    try:
        tests_repo.update_test(test_id, **payload)
    except Exception as exc:
        raise _db_error(exc, "test") from exc
    return tests_repo.get_test(test_id)


@router.delete("/tests/{test_id}")
def delete_test(test_id: int):
    if not tests_repo.exists(test_id):
        raise _not_found("Test")
    tests_repo.delete_test(test_id)
    return {"deleted": test_id}


# ---------- running ----------
@router.post("/tests/{test_id}/run")
def run_test(test_id: int, body: RunOptions | None = None):
    body = body or RunOptions()
    outcome = service.run_saved_test(test_id, body)
    if outcome.get("code") == "not_found":
        raise _not_found("Test")
    return _strip_internals(outcome)


@router.post("/groups/{group_id}/run")
def run_group(group_id: int, body: GroupRunRequest | None = None):
    if not groups_repo.exists(group_id):
        raise _not_found("Group")
    return service.run_group(group_id, body or GroupRunRequest())


@router.post("/run-adhoc")
def run_adhoc(body: AdhocRequest):
    """Unsaved run, kept so you can try an endpoint before creating a test."""
    return _strip_internals(service.run_adhoc(
        body.curl, body.method, body.instruction, body.token,
        body.username, body.password))


@router.post("/tests/{test_id}/propose-extractors")
def propose_extractors(test_id: int, body: RunOptions | None = None):
    result = service.propose_extractors(test_id, body or RunOptions())
    if result.get("code") == "not_found":
        raise _not_found("Test")
    return result


# ---------- history ----------
@router.get("/tests/{test_id}/runs")
def list_runs(test_id: int, limit: int = 50):
    if not tests_repo.exists(test_id):
        raise _not_found("Test")
    return runs_repo.list_runs(test_id, limit)


@router.get("/runs/{run_id}")
def get_run(run_id: int):
    run = runs_repo.get_run(run_id)
    if not run:
        raise _not_found("Run")
    run["cases"] = runs_repo.list_cases(run_id)
    test = tests_repo.get_test(run["test_id"])
    run["test_name"] = test["name"] if test else None
    return run


@router.post("/runs/{run_id}/cases/{case_id}/feedback")
def feedback(run_id: int, case_id: int, body: FeedbackRequest):
    # Validated here rather than with Field(pattern=...) because that kwarg
    # only exists in pydantic v2 and the installed version is 1.10.
    if body.verdict not in VALID_VERDICTS:
        raise HTTPException(422, f"verdict must be one of {', '.join(VALID_VERDICTS)}")
    case = runs_repo.get_case(case_id)
    if not case or case["run_id"] != run_id:
        raise _not_found("Case")
    run = runs_repo.get_run(run_id)
    feedback_id = runs_repo.record_feedback(case_id, run["test_id"], body.verdict, body.note)
    return {"feedback_id": feedback_id,
            "accepted": runs_repo.accepted_cases_for(run["test_id"])}


@router.get("/tests/{test_id}/insights")
def insights(test_id: int):
    """Per-category accuracy and learned-case count, for the UI."""
    if not tests_repo.exists(test_id):
        raise _not_found("Test")
    return {
        "category_stats": runs_repo.category_stats_for(test_id),
        "rejected_categories": runs_repo.rejected_categories_for(test_id),
        "learned_cases": runs_repo.learned_case_count(test_id),
    }


# ---------- variables ----------
@router.get("/groups/{group_id}/variables")
def list_variables(group_id: int):
    if not groups_repo.exists(group_id):
        raise _not_found("Group")
    return variables_repo.list_for_group(group_id)


@router.put("/groups/{group_id}/variables/{name}")
def update_variable(group_id: int, name: str, body: VariableUpdate):
    # Upsert, so a value can be seeded by hand before any test has captured it.
    if not groups_repo.exists(group_id):
        raise _not_found("Group")
    created = variables_repo.upsert_value(group_id, name, body.value)
    return {"name": name, "value": body.value, "created": created}


@router.delete("/groups/{group_id}/variables/{name}")
def delete_variable(group_id: int, name: str):
    variables_repo.delete(group_id, name)
    return {"deleted": name}


def _strip_internals(outcome: dict) -> dict:
    """response_text holds the full untruncated body for extraction. It is only
    needed inside the run, and shipping it would bloat every response."""
    for case in outcome.get("results") or []:
        case.pop("response_text", None)
    return outcome


class ApiTestingModule(TestModule):
    info = ModuleInfo(
        slug="api-testing",
        title="API Testing",
        description="Group interrelated API tests, capture values between them, "
                    "and generate edge cases with a local model.",
        icon="beaker",
    )

    def router(self) -> APIRouter:
        return router
