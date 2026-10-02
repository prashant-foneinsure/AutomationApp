"""Ollama client: generating test cases, and later, proposing extractors."""
import json
import os

import httpx

from .. import config

# LLM Stub for testing without waiting on the real model
LLM_STUB = os.environ.get("AA_LLM_STUB", "0") == "1"

# Categories are constrained here. Adding one means the UI's filter and this
# enum both have to change, or Ollama can return a value nothing renders.
CATEGORIES = ["negative", "boundary", "method", "positive", "edge"]

SCHEMA = {
    "type": "object",
    "properties": {
        "tests": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "category": {"type": "string", "enum": CATEGORIES},
                    "method": {"type": "string"},
                    "body": {"type": "string"},
                    "remove_headers": {"type": "array", "items": {"type": "string"}},
                    "expected_status": {"type": "integer"},
                },
                "required": ["name", "category", "expected_status"],
            },
        }
    },
    "required": ["tests"],
}


STUB_TESTS = [
    {"name": "Missing required field", "category": "negative", "method": "", "body": "{}", "remove_headers": [], "expected_status": 400},
    {"name": "Empty request body", "category": "negative", "method": "", "body": "", "remove_headers": [], "expected_status": 400},
    {"name": "Invalid JSON", "category": "negative", "method": "", "body": "not json", "remove_headers": [], "expected_status": 400},
    {"name": "Wrong HTTP method", "category": "method", "method": "PUT", "body": "", "remove_headers": [], "expected_status": 405},
    {"name": "Missing Content-Type", "category": "negative", "method": "", "body": "{}", "remove_headers": ["Content-Type"], "expected_status": 415},
]


class LLMError(RuntimeError):
    """Any failure talking to Ollama. Carries a message safe to show a user."""


def chat(prompt: str, schema: dict, temperature: float = 0.2) -> dict:
    if LLM_STUB:
        # Return canned test cases for testing
        return {"tests": STUB_TESTS}
    try:
        r = httpx.post(config.OLLAMA_URL, timeout=config.LLM_TIMEOUT, json={
            "model": config.MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "format": schema, "stream": False,
            "options": {"temperature": temperature},
        })
        r.raise_for_status()
        return json.loads(r.json()["message"]["content"])
    except Exception as e:
        raise LLMError(f"Ollama error: {e}") from e


def is_available() -> bool:
    try:
        httpx.get(config.OLLAMA_TAGS_URL, timeout=3).raise_for_status()
        return True
    except Exception:
        return False


def generation_prompt(base: dict, baseline: dict, instruction: str,
                      learned: list[dict] | None = None,
                      avoid: str | None = None) -> str:
    """Build the test-case generation prompt.

    `learned` injects previously accepted cases as few-shot examples and
    `avoid` injects the categories that have historically been wrong for this
    endpoint. See services/learning.py for where they come from.
    """
    prompt = f"""You are a QA engineer designing API test cases.

Endpoint: {base['method']} {base['url']}
Headers sent: {list(base['headers'].keys())}
Valid request body: {base['body'] or "(no body)"}
The valid request returned HTTP {baseline['actual_status']} with response:
{baseline['response'][:config.MAX_PROMPT_RESPONSE_CHARS]}

User instruction: {instruction or "Cover positive and negative scenarios"}
"""
    if learned:
        examples = "\n".join(
            f"- {c.get('category')} | {c.get('name')} | {c.get('method') or base['method']} "
            f"| body={c.get('body') or '(unchanged)'} | expect={c.get('expected_status')}"
            for c in learned
        )
        prompt += f"""
These cases were previously generated for this endpoint and accepted as correct.
Follow the same conventions and expected-status reasoning:
{examples}
"""
    if avoid:
        prompt += f"""
Cases in these categories have been WRONG for this endpoint before. Be more
careful and do not repeat the same mistake:
{avoid}
"""
    prompt += f"""
Design {config.CASES_REQUESTED} DIFFERENT test cases. Each test changes ONE thing from the valid request:
- "body": a full replacement JSON body string (missing field, empty value, wrong data type, very long value, special characters, boundary value, empty object {{}}). Use the real field names from the valid body.
- "remove_headers": header names to remove (e.g. Content-Type)
- "method": use a different HTTP method
Do NOT create a test for the valid request or for missing credentials; those already exist.
Set expected_status to what a well-built API returns (usually 400, 405 or 415 for invalid requests)."""
    return prompt


def generate_tests(base: dict, baseline: dict, instruction: str,
                   learned: list[dict] | None = None,
                   avoid: str | None = None) -> list:
    payload = chat(generation_prompt(base, baseline, instruction, learned, avoid), SCHEMA)
    tests = payload.get("tests") if isinstance(payload, dict) else None
    if not isinstance(tests, list):
        raise LLMError("Ollama returned no usable 'tests' array")
    return tests


def suggest_extractor_prompt(base: dict, baseline: dict) -> str:
    return f"""An API endpoint was called and returned JSON. Identify the values in the
response that later requests in the same test suite would need, such as an auth
token, an id to use as a path parameter, or a tenant/user key.

Endpoint: {base['method']} {base['url']}
Response ({baseline['actual_status']}):
{baseline['response'][:config.MAX_PROMPT_RESPONSE_CHARS]}

Return JSON mapping each variable name to a JSONPath selector into that response.
Only include genuinely reusable values. Do not include timestamps, counts or
boilerplate fields. If nothing is reusable, return an empty object."""

EXTRACTOR_SCHEMA = {
    "type": "object",
    "additionalProperties": {"type": "string"},
    "patternProperties": {"^.*$": {"type": "string"}},
}


def suggest_extractors(base: dict, baseline: dict) -> list[dict]:
    """Ask the model which values are worth carrying forward. Falls back to an
    empty list rather than failing the run -- extraction is an enhancement."""
    try:
        payload = chat(suggest_extractor_prompt(base, baseline), EXTRACTOR_SCHEMA)
    except LLMError:
        return []
    out = []
    if isinstance(payload, dict):
        for name, selector in payload.items():
            if isinstance(name, str) and isinstance(selector, str) and name and selector:
                out.append({"name": name[:200], "selector": selector[:400]})
    return out[:6]


def dedupe(tests: list) -> list:
    """Drop cases that would send an identical request.

    The seed entry blocks a case with no method, body or header removals --
    that is just the valid request again, which is already the baseline.
    """
    seen, out = {("", "", ())}, []
    for t in tests:
        if not isinstance(t, dict):
            continue
        key = (t.get("method") or "", t.get("body") or "",
               tuple(sorted(t.get("remove_headers") or [])))
        if key not in seen:
            seen.add(key)
            out.append(t)
    return out[:config.MAX_CASES_AFTER_DEDUPE]
