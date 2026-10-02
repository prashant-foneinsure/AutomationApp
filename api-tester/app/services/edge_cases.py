"""Deterministic edge case generation by mutating the parsed request.

This does NOT rely on the LLM. It generates edge cases by systematically
mutating body fields, query params, and headers.
"""
import json
import copy
from typing import Any


EDGE_CASE_CATEGORIES = {
    "empty_string": "edge",
    "null_value": "edge",
    "missing_field": "edge",
    "wrong_type": "edge",
    "whitespace_only": "edge",
    "very_long_string": "edge",
    "special_chars": "edge",
    "unicode": "edge",
    "sql_injection": "edge",
    "script_injection": "edge",
    "zero": "edge",
    "negative_number": "edge",
    "huge_number": "edge",
    "boundary_value": "boundary",
    "extra_field": "edge",
    "duplicate_field": "edge",
    "malformed_json": "edge",
    "wrong_content_type": "edge",
    "missing_auth": "auth",
    "invalid_auth": "edge",
    "expired_auth": "edge",
}


def _mutate_body_field(body: str, field_name: str, mutation: str) -> str | None:
    """Apply a specific mutation to a field in the JSON body."""
    try:
        parsed = json.loads(body)
    except (json.JSONDecodeError, TypeError):
        return None

    if not isinstance(parsed, dict) or field_name not in parsed:
        return None

    mutated = copy.deepcopy(parsed)
    original_value = mutated[field_name]

    if mutation == "empty_string":
        mutated[field_name] = ""
    elif mutation == "null_value":
        mutated[field_name] = None
    elif mutation == "missing_field":
        del mutated[field_name]
    elif mutation == "wrong_type":
        if isinstance(original_value, str):
            mutated[field_name] = 123
        elif isinstance(original_value, (int, float)):
            mutated[field_name] = "not_a_number"
        elif isinstance(original_value, bool):
            mutated[field_name] = "not_a_boolean"
        elif isinstance(original_value, list):
            mutated[field_name] = "not_an_array"
        elif isinstance(original_value, dict):
            mutated[field_name] = "not_an_object"
        else:
            mutated[field_name] = "wrong_type"
    elif mutation == "whitespace_only":
        mutated[field_name] = "   \t\n  "
    elif mutation == "very_long_string":
        mutated[field_name] = "x" * 10000
    elif mutation == "special_chars":
        mutated[field_name] = "!@#$%^&*()_+-=[]{}|;':\",./<>?"
    elif mutation == "unicode":
        mutated[field_name] = "测试 🎉 日本語 العربية עברית"
    elif mutation == "sql_injection":
        mutated[field_name] = "' OR '1'='1; --"
    elif mutation == "script_injection":
        mutated[field_name] = "<script>alert('xss')</script>"
    elif mutation == "zero":
        if isinstance(original_value, (int, float)):
            mutated[field_name] = 0
    elif mutation == "negative_number":
        if isinstance(original_value, (int, float)):
            mutated[field_name] = -abs(original_value) - 1
    elif mutation == "huge_number":
        if isinstance(original_value, (int, float)):
            mutated[field_name] = 999999999999999999999
    elif mutation == "boundary_value":
        if isinstance(original_value, int):
            mutated[field_name] = original_value + 1
        elif isinstance(original_value, float):
            mutated[field_name] = original_value + 0.0001
    elif mutation == "extra_field":
        mutated["__extra_unknown_field__"] = "unexpected_value"
    elif mutation == "duplicate_field":
        pass
    else:
        return None

    return json.dumps(mutated, separators=(",", ":"))


def _mutate_query_param(url: str, param_name: str, mutation: str) -> str | None:
    """Apply a mutation to a query parameter in the URL."""
    from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

    try:
        parsed = urlparse(url)
        query_params = parse_qs(parsed.query, keep_blank_values=True)

        if param_name not in query_params:
            return None

        if mutation == "empty_string":
            query_params[param_name] = [""]
        elif mutation == "null_value":
            query_params[param_name] = ["null"]
        elif mutation == "missing_field":
            del query_params[param_name]
        elif mutation == "wrong_type":
            query_params[param_name] = ["not_a_valid_value"]
        elif mutation == "whitespace_only":
            query_params[param_name] = ["   "]
        elif mutation == "very_long_string":
            query_params[param_name] = ["x" * 10000]
        elif mutation == "special_chars":
            query_params[param_name] = ["!@#$%^&*()"]
        elif mutation == "unicode":
            query_params[param_name] = ["测试🎉"]
        elif mutation == "sql_injection":
            query_params[param_name] = ["' OR '1'='1"]
        elif mutation == "script_injection":
            query_params[param_name] = ["<script>alert(1)</script>"]
        elif mutation == "zero":
            query_params[param_name] = ["0"]
        elif mutation == "negative_number":
            query_params[param_name] = ["-1"]
        elif mutation == "huge_number":
            query_params[param_name] = ["999999999999"]
        elif mutation == "boundary_value":
            try:
                val = int(query_params[param_name][0])
                query_params[param_name] = [str(val + 1)]
            except (ValueError, IndexError):
                query_params[param_name] = ["1"]
        else:
            return None

        new_query = urlencode(query_params, doseq=True)
        new_parsed = parsed._replace(query=new_query)
        return urlunparse(new_parsed)
    except Exception:
        return None


def generate_edge_cases(base: dict, baseline: dict) -> list[dict]:
    """Generate deterministic edge cases by mutating the request.

    Returns a list of test case dicts with category "edge" or "boundary".
    """
    cases = []
    body = base.get("body") or ""
    url = base.get("url") or ""
    headers = base.get("headers") or {}

    if not body and not url:
        return cases

    if body and body.strip().startswith("{"):
        try:
            parsed_body = json.loads(body)
            if isinstance(parsed_body, dict):
                for field_name in parsed_body.keys():
                    for mutation_name, category in EDGE_CASE_CATEGORIES.items():
                        if mutation_name in ("duplicate_field",):
                            continue

                        mutated_body = _mutate_body_field(body, field_name, mutation_name)
                        if mutated_body is None:
                            continue

                        exp_status = _expected_status_for_mutation(mutation_name)
                        cases.append({
                            "name": f"{field_name}: {mutation_name.replace('_', ' ').title()}",
                            "category": category,
                            "method": "",
                            "body": mutated_body,
                            "remove_headers": [],
                            "expected_status": exp_status,
                        })
        except json.JSONDecodeError:
            pass

    from urllib.parse import urlparse, parse_qs
    try:
        parsed = urlparse(url)
        query_params = parse_qs(parsed.query, keep_blank_values=True)
        for param_name in query_params.keys():
            for mutation_name, category in EDGE_CASE_CATEGORIES.items():
                if mutation_name in ("duplicate_field", "extra_field"):
                    continue

                mutated_url = _mutate_query_param(url, param_name, mutation_name)
                if mutated_url is None:
                    continue

                exp_status = _expected_status_for_mutation(mutation_name)
                cases.append({
                    "name": f"Query param '{param_name}': {mutation_name.replace('_', ' ').title()}",
                    "category": category,
                    "method": "",
                    "body": "",
                    "remove_headers": [],
                    "expected_status": exp_status,
                })
    except Exception:
        pass

    for header_name in list(headers.keys()):
        if header_name.lower() in ("authorization", "cookie"):
            continue
        for mutation_name in ("empty_string", "missing_field", "wrong_type", "very_long_string", "special_chars"):
            category = EDGE_CASE_CATEGORIES.get(mutation_name, "edge")
            if mutation_name == "empty_string":
                cases.append({
                    "name": f"Header '{header_name}': Empty string",
                    "category": category,
                    "method": "",
                    "body": "",
                    "remove_headers": [header_name],
                    "expected_status": 400,
                })
            elif mutation_name == "missing_field":
                cases.append({
                    "name": f"Header '{header_name}': Missing",
                    "category": category,
                    "method": "",
                    "body": "",
                    "remove_headers": [header_name],
                    "expected_status": 400,
                })
            elif mutation_name == "wrong_type":
                cases.append({
                    "name": f"Header '{header_name}': Wrong type",
                    "category": category,
                    "method": "",
                    "body": "",
                    "remove_headers": [],
                    "expected_status": 400,
                })

    auth_header = headers.get("Authorization") or headers.get("authorization")
    if auth_header:
        cases.append({
            "name": "Auth: Missing Authorization header",
            "category": "auth",
            "method": "",
            "body": "",
            "remove_headers": ["Authorization"],
            "expected_status": 401,
        })
        cases.append({
            "name": "Auth: Invalid token format",
            "category": "edge",
            "method": "",
            "body": "",
            "remove_headers": [],
            "expected_status": 401,
        })

    cases.append({
        "name": "Wrong Content-Type (text/plain)",
        "category": "edge",
        "method": "",
        "body": body,
        "remove_headers": ["Content-Type"],
        "expected_status": 415,
    })

    seen = set()
    unique_cases = []
    for c in cases:
        key = (c.get("method", ""), c.get("body", ""), tuple(sorted(c.get("remove_headers") or [])))
        if key not in seen:
            seen.add(key)
            unique_cases.append(c)

    return unique_cases[:30]


def _expected_status_for_mutation(mutation: str) -> int:
    """Return sensible expected status for a mutation type."""
    if mutation in ("missing_field", "empty_string", "null_value", "wrong_type",
                    "whitespace_only", "special_chars", "unicode", "sql_injection",
                    "script_injection", "extra_field", "duplicate_field",
                    "malformed_json", "wrong_content_type"):
        return 400
    if mutation in ("zero", "negative_number", "huge_number", "boundary_value"):
        return 400
    if mutation in ("missing_auth", "invalid_auth", "expired_auth"):
        return 401
    return 400


def auto_capture_tokens(response_text: str) -> list[dict]:
    """Auto-capture tokens and useful IDs from response. Deterministic, no LLM."""
    if not response_text or not response_text.strip().startswith(("{", "[")):
        return []

    try:
        payload = json.loads(response_text)
    except (json.JSONDecodeError, TypeError):
        return []

    captured = []
    seen = set()

    def walk(node, path=""):
        if isinstance(node, dict):
            for key, value in node.items():
                new_path = f"{path}.{key}" if path else key
                key_lower = key.lower()

                is_token_like = any(k in key_lower for k in (
                    "token", "key", "secret", "jwt", "auth", "session", "credential"
                ))
                is_id_like = any(k in key_lower for k in ("id", "uuid", "guid"))

                if isinstance(value, (str, int, float)) and (is_token_like or is_id_like):
                    if new_path not in seen:
                        seen.add(new_path)
                        var_name = key
                        if var_name in ("id",) and path:
                            var_name = f"{path.split('.')[-1]}_{key}"
                        captured.append({
                            "name": var_name,
                            "value": json.dumps(value) if isinstance(value, (dict, list)) else str(value),
                            "json_value": json.dumps(value),
                            "selector": f"$.{new_path}",
                        })
                walk(value, new_path)
        elif isinstance(node, list):
            for i, item in enumerate(node[:3]):
                walk(item, f"{path}[{i}]")

    walk(payload)
    return captured


def auto_save_credentials(base: dict) -> list[dict]:
    """Auto-save credentials from request body/headers for reuse."""
    saved = []
    body = base.get("body") or ""
    headers = base.get("headers") or {}

    if body and body.strip().startswith("{"):
        try:
            parsed = json.loads(body)
            if isinstance(parsed, dict):
                for key, value in parsed.items():
                    key_lower = key.lower()
                    if key_lower in ("username", "user", "email", "login", "user_id", "userid"):
                        if isinstance(value, str):
                            saved.append({
                                "name": key,
                                "value": value,
                                "json_value": json.dumps(value),
                                "is_secret": False,
                            })
                    elif key_lower in ("password", "passwd", "pwd", "secret", "api_key", "apikey"):
                        if isinstance(value, str):
                            saved.append({
                                "name": key,
                                "value": "***",
                                "json_value": json.dumps(value),
                                "is_secret": True,
                            })
        except json.JSONDecodeError:
            pass

    auth_header = headers.get("Authorization") or headers.get("authorization")
    if auth_header and auth_header.startswith("Basic "):
        import base64
        try:
            decoded = base64.b64decode(auth_header[6:]).decode("utf-8")
            if ":" in decoded:
                username, password = decoded.split(":", 1)
                saved.append({
                    "name": "username",
                    "value": username,
                    "json_value": json.dumps(username),
                    "is_secret": False,
                })
                saved.append({
                    "name": "password",
                    "value": "***",
                    "json_value": json.dumps(password),
                    "is_secret": True,
                })
        except Exception:
            pass

    return saved