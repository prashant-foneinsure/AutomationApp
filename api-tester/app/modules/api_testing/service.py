"""API Testing module service: ties the runner to persistence."""
import time

from ...repositories import groups as groups_repo
from ...repositories import runs as runs_repo
from ...repositories import tests as tests_repo
from ...repositories import variables as variables_repo
from ...services import executor, llm, runner
from ...services.variables import (apply_to_request, missing_for_request,
                                  parse_extractors, suggest_extractors)


def _learned_context(test_id: int) -> tuple[list[dict], str | None]:
    """Accepted cases as few-shot examples, plus a warning about categories
    that have historically been wrong for this endpoint."""
    accepted = runs_repo.accepted_cases_for(test_id)
    rejected = runs_repo.rejected_categories_for(test_id)
    avoid = None
    if rejected:
        avoid = "\n".join(f"- {cat} (rejected {n}x)" for cat, n in rejected.items())
    return accepted, avoid


def _persist(test_id: int, group_id: int, outcome: dict, duration_ms: int,
             group_run_id: int | None = None, run_outcome: str = "completed") -> int:
    run_id = runs_repo.start_run(test_id, run_outcome, group_run_id)
    results = outcome.get("results") or []
    baseline_status = results[0].get("actual_status") if results else None
    runs_repo.finish_run(run_id, baseline_status,
                         outcome.get("passed", 0), outcome.get("total", 0),
                         duration_ms, run_outcome)
    runs_repo.add_cases(run_id, results)
    captured = outcome.get("captured_variables") or []
    if captured:
        variables_repo.upsert_many(group_id, captured, source_test_id=test_id,
                                   source_run_id=run_id)
    return run_id


def run_saved_test(test_id: int, options) -> dict:
    test = tests_repo.get_test(test_id)
    if not test:
        return {"error": f"Test {test_id} not found", "code": "not_found"}
    group_id = test["group_id"]

    available = variables_repo.as_map(group_id)
    accepted, avoid = _learned_context(test_id)
    extractors = parse_extractors(test.get("extractors"))

    started = time.time()
    outcome = runner.run(
        test["curl"],
        method_override=options.method or test.get("http_method") or "",
        instruction=options.instruction,
        token=options.token, username=options.username, password=options.password,
        available=available,
        extractors=extractors if extractors else None,
        learned=accepted or None,
        avoid=avoid,
    )
    duration_ms = int((time.time() - started) * 1000)

    if outcome.get("needs_auth") or outcome.get("blocked"):
        # Nothing was meaningfully executed: don't record a run for it.
        outcome["test_id"] = test_id
        return outcome

    run_id = _persist(test_id, group_id, outcome, duration_ms)
    outcome["run_id"] = run_id
    outcome["test_id"] = test_id
    if not extractors and outcome.get("suggested_extractors"):
        outcome["extractors_suggestion_available"] = True
    return outcome


def run_adhoc(curl: str, method: str, instruction: str, token: str,
              username: str, password: str) -> dict:
    """Unsaved run. Kept for the 'try it before saving' path."""
    started = time.time()
    outcome = runner.run(curl, method_override=method, instruction=instruction,
                         token=token, username=username, password=password,
                         available={}, extractors=None)
    outcome["duration_ms"] = int((time.time() - started) * 1000)
    return outcome


def run_group(group_id: int, request) -> dict:
    """Execute every test in SortOrder, carrying captured values forward.

    A test whose placeholders cannot be resolved is skipped and the chain
    continues, so one broken dependency does not hide the rest. A test that
    fails to produce a 2xx baseline stops the chain when stop_on_failure is
    set, because later tests almost certainly depend on it.
    """
    members = tests_repo.list_tests(group_id)
    steps, stopped, group_run_id = [], False, None

    for test in members:
        test_id = test["test_id"]
        available = variables_repo.as_map(group_id)

        if stopped:
            steps.append({"test_id": test_id, "name": test["name"],
                          "skipped": "chain_stopped"})
            continue

        # Feedback is honoured here too, not just for single runs: judging a
        # case wrong has to affect the very next group execution.
        accepted, avoid = _learned_context(test_id)

        started = time.time()
        outcome = runner.run(
            test["curl"],
            method_override=test.get("http_method") or "",
            instruction=request.instruction,
            token=request.token, username=request.username, password=request.password,
            available=available,
            extractors=parse_extractors(test.get("extractors")) or None,
            learned=accepted or None,
            avoid=avoid,
        )
        duration_ms = int((time.time() - started) * 1000)

        step = {"test_id": test_id, "name": test["name"]}

        if outcome.get("needs_auth"):
            step.update(skipped="needs_auth", error=outcome.get("error"))
            steps.append(step)
            stopped = request.stop_on_failure
            continue

        if outcome.get("blocked"):
            step.update(skipped="blocked", missing_variables=outcome.get("missing_variables"),
                        error=outcome.get("error"))
            steps.append(step)
            continue

        run_id = _persist(test_id, group_id, outcome, duration_ms,
                          group_run_id=group_run_id)
        if group_run_id is None:
            # The first persisted step of this group execution defines the id
            # that every later step shares.
            group_run_id = run_id
            runs_repo.tag_group_run(run_id, run_id)
        baseline = (outcome.get("results") or [{}])[0]
        step.update(run_id=run_id,
                    baseline_status=baseline.get("actual_status"),
                    passed=outcome.get("passed", 0), total=outcome.get("total", 0),
                    captured=[c["name"] for c in (outcome.get("captured_variables") or [])],
                    suggested_extractors=outcome.get("suggested_extractors") or [],
                    error=outcome.get("error"))
        steps.append(step)

        baseline_status = baseline.get("actual_status")
        if baseline_status is None or not (200 <= baseline_status < 300):
            stopped = request.stop_on_failure

    return {"group_id": group_id, "group_run_id": group_run_id, "steps": steps,
            "variables": variables_repo.list_for_group(group_id)}


def propose_extractors(test_id: int, options) -> dict:
    """Ask the model which response values are worth carrying forward, without
    running the generated test suite."""
    test = tests_repo.get_test(test_id)
    if not test:
        return {"error": f"Test {test_id} not found", "code": "not_found"}

    available = variables_repo.as_map(test["group_id"])
    base = runner.build_request(test["curl"],
                                options.method or test.get("http_method") or "",
                                options.token, options.username, options.password)
    if missing_for_request(base, available):
        return {"error": "Test depends on variables that are not available yet",
                "code": "blocked"}
    base = apply_to_request(base, available)

    probe = executor.execute(base, dict(base["headers"]), {"name": "probe"})
    status = probe.get("actual_status")
    if status is None or not (200 <= status < 300):
        return {"error": f"Endpoint returned {status}; cannot inspect a response body",
                "code": "baseline_failed"}

    deterministic = suggest_extractors(probe.get("response_text") or "")
    proposed = llm.suggest_extractors(base, probe)
    merged, seen = [], set()
    for spec in list(proposed) + list(deterministic):
        if spec["name"] not in seen:
            seen.add(spec["name"])
            merged.append(spec)
    return {"extractors": merged, "baseline_status": status}
