"""cURL command -> request parts.

Kept deliberately permissive: the original implementation only needed to
recognise the handful of flags people actually paste out of browser devtools.
"""
import base64
import shlex

from .variables import PLACEHOLDER_RE, placeholders_in


def parse_curl(cmd: str) -> dict:
    tokens = shlex.split(cmd.replace("\\\r\n", " ").replace("\\\n", " "))
    req = {"method": None, "url": None, "headers": {}, "body": None}
    i = 0
    while i < len(tokens):
        t = tokens[i]
        if t in ("-X", "--request"):
            req["method"] = tokens[i + 1].upper(); i += 1
        elif t in ("-H", "--header"):
            k, _, v = tokens[i + 1].partition(":")
            req["headers"][k.strip()] = v.strip(); i += 1
        elif t in ("-d", "--data", "--data-raw", "--data-binary"):
            req["body"] = tokens[i + 1]; i += 1
        elif t in ("-u", "--user"):
            raw = tokens[i + 1].encode()
            req["headers"]["Authorization"] = "Basic " + base64.b64encode(raw).decode()
            i += 1
        elif t.startswith("http"):
            req["url"] = t
        i += 1
    if not req["method"]:
        req["method"] = "POST" if req["body"] else "GET"
    return req


def basic_auth(username: str, password: str) -> str:
    raw = f"{username}:{password}".encode()
    return "Basic " + base64.b64encode(raw).decode()


def bearer_auth(token: str) -> str:
    return f"Bearer {token}"


def required_variables(curl: str) -> list[str]:
    """Placeholder names a saved cURL depends on, e.g. {{token}} -> ['token']."""
    return placeholders_in(curl)
