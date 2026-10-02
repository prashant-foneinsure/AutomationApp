"""Placeholder templating and extractor application for interrelated tests.

A saved cURL may contain {{name}} placeholders. They are substituted from the
group's captured variables before the request is sent, so a token obtained by
an earlier "Authentication" test is available to later tests automatically.

If a placeholder cannot be resolved the test is BLOCKED and no request is
issued -- firing a request containing a literal "{{token}}" would produce a
misleading result rather than a clear explanation.
"""
import json
import re

PLACEHOLDER_RE = re.compile(r"\{\{\s*([A-Za-z0-9_.\-]+)\s*\}\}")
# Common placeholder patterns users write in cURL that should map to captured variables
COMMON_PLACEHOLDER_PATTERNS = [
    (re.compile(r"YOUR_ACCESS_TOKEN", re.IGNORECASE), "accessToken"),
    (re.compile(r"YOUR_REFRESH_TOKEN", re.IGNORECASE), "refreshToken"),
    (re.compile(r"TOKEN_HERE", re.IGNORECASE), "token"),
    (re.compile(r"<TOKEN>", re.IGNORECASE), "token"),
    (re.compile(r"<ACCESS_TOKEN>", re.IGNORECASE), "accessToken"),
    (re.compile(r"BEARER_TOKEN", re.IGNORECASE), "token"),
    (re.compile(r"API_KEY_HERE", re.IGNORECASE), "apiKey"),
    (re.compile(r"YOUR_API_KEY", re.IGNORECASE), "apiKey"),
]
# Bound the text we search so a huge body cannot make substitution expensive.
MAX_SCAN_CHARS = 200_000


def placeholders_in(text: str) -> list[str]:
    """Ordered, de-duplicated placeholder names appearing in text."""
    if not text:
        return []
    found, seen = [], set()
    for name in PLACEHOLDER_RE.findall(text[:MAX_SCAN_CHARS]):
        if name not in seen:
            seen.add(name)
            found.append(name)
    return found


def unresolved(text: str, available: dict) -> list[str]:
    return [n for n in placeholders_in(text) if n not in available]


def apply_variables(text: str | None, available: dict) -> str | None:
    """Substitute every known placeholder; leave unknown ones untouched so the
    caller can detect and report them."""
    if not text:
        return text
    return PLACEHOLDER_RE.sub(
        lambda m: str(available.get(m.group(1), m.group(0))), text[:MAX_SCAN_CHARS]
    )


def apply_to_request(base: dict, available: dict) -> dict:
    """Return a copy of a parsed request with placeholders resolved in the
    url, every header value and the body."""
    out = dict(base)
    out["url"] = apply_variables(base.get("url"), available)
    out["headers"] = {k: apply_variables(v, available) for k, v in (base.get("headers") or {}).items()}
    out["body"] = apply_variables(base.get("body"), available)
    return out


def missing_for_request(base: dict, available: dict) -> list[str]:
    """Every placeholder the request needs that the variable store lacks."""
    needed = set(placeholders_in(base.get("url") or ""))
    for value in (base.get("headers") or {}).values():
        needed.update(placeholders_in(value))
    needed.update(placeholders_in(base.get("body") or ""))
    return [n for n in needed if n not in available]


def detect_common_placeholders(base: dict) -> dict[str, str]:
    """
    Scan a parsed request for common placeholder patterns (YOUR_ACCESS_TOKEN, etc.)
    and return a mapping of pattern -> suggested variable name.
    """
    text_parts = []
    if base.get("url"):
        text_parts.append(base["url"])
    for v in (base.get("headers") or {}).values():
        text_parts.append(v)
    if base.get("body"):
        text_parts.append(base["body"])
    full_text = " ".join(text_parts)
    suggestions = {}
    for pattern, var_name in COMMON_PLACEHOLDER_PATTERNS:
        if pattern.search(full_text):
            suggestions[pattern.pattern] = var_name
    return suggestions


def auto_replace_common_placeholders(base: dict, available: dict) -> dict:
    """
    Replace common placeholder patterns (YOUR_ACCESS_TOKEN, etc.) with {{var}} syntax
    if the variable is available. Returns a new request dict with replacements made.
    """
    out = dict(base)
    text_parts = []
    if out.get("url"):
        text_parts.append(out["url"])
    for v in (out.get("headers") or {}).values():
        text_parts.append(v)
    if out.get("body"):
        text_parts.append(out["body"])
    full_text = " ".join(text_parts)
    
    # Check each pattern and replace if variable is available
    for pattern, var_name in COMMON_PLACEHOLDER_PATTERNS:
        if var_name in available and pattern.search(full_text):
            replacement = f"{{{{{var_name}}}}}"
            if out.get("url"):
                out["url"] = pattern.sub(replacement, out["url"])
            out["headers"] = {k: pattern.sub(replacement, v) for k, v in (out.get("headers") or {}).items()}
            if out.get("body"):
                out["body"] = pattern.sub(replacement, out["body"])
            full_text = " ".join([
                out.get("url") or "",
                " ".join((out.get("headers") or {}).values()),
                out.get("body") or ""
            ])
    return out


# ---------- extractors ----------
# A minimal JSONPath subset. Deliberately not a full implementation: it needs
# to cover dotted keys, array indices and a couple of wildcards, which is what
# the auto-suggestion heuristic below can actually find.
_INDEX_RE = re.compile(r"^(\d+)$")
# Lower-case on purpose: compared against key.lower(). A camelCase entry here
# would never match, which is how "userId" went unnoticed.
# Include both snake_case and camelCase variants for common token/id fields.
# All keys must be lowercase since we compare against key.lower().
AUTO_KEYS = frozenset({
    "token", "access_token", "accesstoken", "refresh_token", "refreshtoken",
    "id_token", "idtoken", "id", "userid", "user_id",
    "jwt", "guid", "uuid", "api_key", "apikey",
})


def _lookup(node, parts):
    for part in parts:
        if isinstance(node, dict):
            if part in node:
                node = node[part]
                continue
            # case-insensitive fallback
            lowered = {k.lower(): v for k, v in node.items()}
            if part.lower() in lowered:
                node = lowered[part.lower()]
                continue
            return None, False
        elif isinstance(node, list):
            if part == "*":
                return node, True
            m = _INDEX_RE.match(part)
            if m:
                i = int(m.group(1))
                if 0 <= i < len(node):
                    node = node[i]
                    continue
            return None, False
        else:
            return None, False
    return node, True


def resolve_selector(payload, selector: str):
    """Return (value, found). Supports $.a.b[0].c and a.b forms."""
    if not selector:
        return None, False
    s = selector.strip()
    if s.startswith("$"):
        s = s[1:]
    s = s.strip()
    if s.startswith("."):
        s = s[1:]
    parts: list[str] = []
    for chunk in s.replace("[", ".").replace("]", "").split("."):
        if chunk:
            parts.append(chunk)
    if not parts:
        return None, False
    value, found = _lookup(payload, parts)
    if found and value is None:
        return None, False
    return value, found


def suggest_extractors(payload, limit: int = 6) -> list[dict]:
    """Propose {name, selector} pairs by walking the response for
    token/id-like keys. Deterministic -- no LLM call.

    Accepts either an already-parsed payload or the raw response text. Both
    call sites hold text (the executor's `response_text`), and passing that
    straight in used to walk a string, which finds nothing and silently pushed
    every run onto the LLM fallback.
    """
    if isinstance(payload, (str, bytes)):
        try:
            payload = json.loads(payload)
        except (TypeError, ValueError):
            return []
    if not isinstance(payload, (dict, list)):
        return []

    found: list[dict] = []
    seen: set[str] = set()

    def walk(node, path):
        if len(found) >= limit:
            return
        if isinstance(node, dict):
            for key, value in node.items():
                newpath = f"{path}.{key}" if path else str(key)
                if (key.lower() in AUTO_KEYS and isinstance(value, (str, int, float))
                        and newpath not in seen):
                    seen.add(newpath)
                    found.append({"name": key, "selector": f"$.{newpath}"})
                walk(value, newpath)
        elif isinstance(node, list):
            for i, value in enumerate(node[:3]):
                walk(value, f"{path}[{i}]")

    walk(payload, "")
    return found[:limit]


def parse_extractors(raw) -> list[dict]:
    """Accept the stored JSON text (or an already-parsed list) and return a
    clean [{name, selector}] list. Never raises on bad input."""
    if not raw:
        return []
    if isinstance(raw, (list, tuple)):
        items = raw
    else:
        try:
            items = json.loads(raw)
        except (TypeError, ValueError):
            return []
    if not isinstance(items, list):
        return []
    out = []
    for item in items:
        if isinstance(item, dict) and item.get("name") and item.get("selector"):
            out.append({"name": str(item["name"])[:200], "selector": str(item["selector"])[:400]})
    return out


def run_extractors(extractors: list[dict], response_text: str) -> list[dict]:
    """Apply extractors to a response body. Returns the captured values, and
    silently skips any selector that does not resolve."""
    if not extractors or not response_text:
        return []
    try:
        payload = json.loads(response_text)
    except (TypeError, ValueError):
        return []
    captured = []
    for spec in extractors:
        value, found = resolve_selector(payload, spec["selector"])
        if not found:
            continue
        if isinstance(value, (dict, list)):
            rendered = json.dumps(value)
        else:
            rendered = str(value)
        captured.append({
            "name": spec["name"],
            "value": rendered[:8000],
            "json_value": json.dumps(value)[:8000],
        })
    return captured
