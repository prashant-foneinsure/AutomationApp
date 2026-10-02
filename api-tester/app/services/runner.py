"""Orchestration for a single API test run.

Flow (unchanged in intent from the original single-file implementation):

  1. parse the cURL and apply any credential overrides
  2. resolve {{placeholders}} from the supplied variables -- block if missing
  3. probe the endpoint with the unmodified request (the "baseline")
  4. if the baseline is 401/403  -> needs_auth, and the LLM is never called
     if the baseline is not 2xx -> an error, and the LLM is never called
  5. otherwise the baseline defines success, and cases are generated and run
"""
from .. import config
from . import executor, llm, variables, edge_cases
from .curl_parser import basic_auth, bearer_auth, parse_curl

ORIGIN_BASELINE = "baseline"
ORIGIN_GENERATED = "generated"
ORIGIN_AUTH = "auth"
ORIGIN_BLOCKED = "blocked"


def has_authorization(headers: dict) -> bool:
    return any(k.lower() == "authorization" for k in headers)


def build_request(curl: str, method_override: str = "", token: str = "",
                  username: str = "", password: str = "") -> dict:
    """Parse and decorate a cURL command. Credentials supplied in the UI take
    precedence over any Authorization header inside the pasted command."""
    base = parse_curl(curl)
    if method_override:
        base["method"] = method_override.upper()
    if token:
        base["headers"]["Authorization"] = bearer_auth(token)
    elif username:
        base["headers"]["Authorization"] = basic_auth(username, password)
    return base


def run(curl: str, method_override: str = "", instruction: str = "",
        token: str = "", username: str = "", password: str = "",
        available: dict | None = None, extractors: list[dict] | None = None,
        learned: list[dict] | None = None, avoid: str | None = None,
        include_auth_case: bool = True) -> dict:
    """Execute one test. `available` maps placeholder name -> captured value.

    Returns a dict that is always safe to serialise. Exactly one of
    `needs_auth`, `blocked` or `results` is meaningful.
    """
    available = available or {}

    base = build_request(curl, method_override, token, username, password)
    if not base["url"]:
        return {"error": "No URL found. Paste a cURL command that includes the URL.",
                "code": "no_url"}

    # Auto-replace common placeholder patterns (YOUR_ACCESS_TOKEN, etc.) with {{var}}
    # if the corresponding variable is available in the group
    base = variables.auto_replace_common_placeholders(base, available)

    missing = variables.missing_for_request(base, available)
    if missing:
        return {"blocked": True, "missing_variables": missing, "results": [],
                "passed": 0, "total": 0,
                "error": "Missing value for: " + ", ".join(missing) +
                         ". Run the earlier test in this group that produces it."}

    base = variables.apply_to_request(base, available)
    headers = dict(base["headers"])
    authed = has_authorization(headers)

    # ---- step 1: probe with the original request
    baseline = executor.execute(base, headers, {
        "name": "Baseline (valid request)", "category": "positive",
        "origin": ORIGIN_BASELINE})
    status = baseline["actual_status"]

    if status in (401, 403):
        return {"needs_auth": True, "rejected": authed,
                "scheme": baseline["response_headers"].get("www-authenticate", ""),
                "results": [], "passed": 0, "total": 0}

    if status is None or not (200 <= status < 300):
        baseline["expected_status"], baseline["passed"] = None, False
        return {"needs_auth": False, "results": [baseline], "passed": 0, "total": 1,
                "error": f"The original request returned {status}, so tests would be meaningless. "
                         "Check the URL, method and body (click the row for details)."}

    # ---- step 2: the baseline defines "success"
    baseline["expected_status"], baseline["passed"] = status, True

    cases = []
    if authed and include_auth_case:
        cases.append({"name": "Missing credentials", "category": "auth",
                      "remove_auth": True, "expected_status": 401,
                      "origin": ORIGIN_AUTH})

    # Generate deterministic edge cases (no LLM)
    edge_cases_list = edge_cases.generate_edge_cases(base, baseline)
    for ec in edge_cases_list:
        ec["origin"] = ORIGIN_GENERATED
    cases += edge_cases_list

    # LLM cases (limited to ~4 for domain-specific extras)
    llm_cases = llm.dedupe(llm.generate_tests(base, baseline, instruction, learned, avoid))
    for lc in llm_cases[:4]:
        lc["origin"] = ORIGIN_GENERATED
    cases += llm_cases[:4]

    results = [baseline] + [executor.execute(base, headers, t) for t in cases]

    # ---- step 3: carry values forward for later tests in the group
    captured = []
    proposed = []
    response_text = baseline.get("response_text") or ""
    if extractors:
        captured = variables.run_extractors(extractors, response_text)
    if not extractors and response_text.strip().startswith(("{", "[")):
        # Nothing stored yet: propose both a deterministic set and the model's.
        proposed = variables.suggest_extractors(response_text) or \
            llm.suggest_extractors(base, baseline)
        captured = variables.run_extractors(proposed, response_text)

    # ALWAYS auto-capture tokens/ids from response (deterministic, no LLM)
    auto_captured = edge_cases.auto_capture_tokens(response_text)
    for ac in auto_captured:
        if ac["name"] not in [c["name"] for c in captured]:
            captured.append({
                "name": ac["name"],
                "value": ac["value"],
                "json_value": ac["json_value"],
            })

    # ALWAYS auto-save credentials from request (for reuse in later tests)
    auto_creds = edge_cases.auto_save_credentials(base)
    for ac in auto_creds:
        if ac["name"] not in [c["name"] for c in captured]:
            captured.append({
                "name": ac["name"],
                "value": ac["value"],
                "json_value": ac["json_value"],
            })

    return {"needs_auth": False, "results": results,
            "passed": sum(1 for r in results if r["passed"]),
            "total": len(results),
            "captured_variables": captured, "suggested_extractors": proposed}
