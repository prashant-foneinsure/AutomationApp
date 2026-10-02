"""Executing a parsed request and comparing it to an expectation."""
import time

import httpx

from .. import config


def drop_header(headers: dict, name: str):
    for k in list(headers):
        if k.lower() == name.lower():
            del headers[k]


def mask(headers: dict) -> dict:
    return {k: ("***" if any(s in k.lower() for s in ("auth", "key", "token")) else v)
            for k, v in headers.items()}


# Response bodies are kept for two different purposes: display (truncated, as
# the original UI did) and variable extraction (needs the real payload). Only
# the display copy is truncated; the stored copy is capped but complete enough
# to parse JSON.
MAX_STORED_RESPONSE = 100_000


def send(method, url, headers, body, timeout: int | None = None) -> dict:
    info = {"method": method, "url": url, "headers": mask(headers), "body": body}
    start = time.time()
    try:
        r = httpx.request(method, url, headers=headers, content=body or None,
                          timeout=timeout or config.REQUEST_TIMEOUT)
        text = r.text
        return {"request": info, "actual_status": r.status_code,
                "time_ms": round((time.time() - start) * 1000),
                "response": text[:config.MAX_RESPONSE_CHARS],
                "response_text": text[:MAX_STORED_RESPONSE],
                "response_headers": dict(r.headers)}
    except Exception as e:
        return {"request": info, "actual_status": None, "time_ms": 0,
                "response": f"ERROR: {e}", "response_text": "", "response_headers": {}}


def execute(base: dict, headers: dict, t: dict) -> dict:
    """Run one test case against the parsed baseline request.

    A case changes at most one thing: the method, the body, or the set of
    headers to drop. An empty/absent override means "use the baseline's".
    """
    h = dict(headers)
    if t.get("remove_auth"):
        drop_header(h, "Authorization")
    for name in t.get("remove_headers") or []:
        drop_header(h, name)
    method = (t.get("method") or base["method"]).upper()
    body = t["body"] if t.get("body") not in (None, "") else base["body"]
    res = send(method, base["url"], h, body)
    exp = t.get("expected_status")
    return {**t, **res,
            "passed": exp is not None and res["actual_status"] == exp}
