"""Central configuration.

Defaults reproduce the values that were previously hardcoded in main.py so the
app behaves identically with no environment set. Every value can be overridden
with an env var so other machines / CI do not need code edits.
"""
import os

# api-tester/  -- main.py's StaticFiles mount uses a RELATIVE path, so the
# process must be started from this directory. See AGENTS.md.
APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC_DIR = os.path.join(APP_DIR, "static")

# ---------- database ----------
# The default instance (MSSQLSERVER) is NOT used, deliberately:
#   * its listener is on 127.0.0.1:1434 while its own registry key says
#     TcpPort=1433, so the running config and the registry disagree;
#   * connections to it fail intermittently with a prelogin handshake error
#     (08001 / "forcibly closed by the remote host") affecting pyodbc AND
#     sqlcmd alike, so it is server-side, not a bad connection string.
# Measured: MSSQLSERVER failed ~50% of connects; SQLEXPRESS was 10/10 at
# ~131ms average.
#
# Naming a named instance also means the port is resolved by the SQL Server
# Browser, so the connection keeps working across restarts and port changes.
DB_SERVER = os.environ.get("AA_DB_SERVER", "localhost")
DB_INSTANCE = os.environ.get("AA_DB_INSTANCE", "SQLEXPRESS")
# Only used when DB_INSTANCE is empty (default instance).
DB_PORT = os.environ.get("AA_DB_PORT", "")
DB_NAME = os.environ.get("AA_DB_NAME", "AutomationAppDb")
DB_DRIVER = os.environ.get("AA_DB_DRIVER", "ODBC Driver 17 for SQL Server")
DB_TIMEOUT = int(os.environ.get("AA_DB_TIMEOUT", "10"))

# Windows integrated security. The instance reports IsIntegratedSecurityOnly=1,
# so there are no SQL logins to fall back to -- the app must run as the same
# Windows account that has access to the server.
DB_TRUSTED = os.environ.get("AA_DB_TRUSTED", "1") != "0"
DB_USER = os.environ.get("AA_DB_USER", "")
DB_PASSWORD = os.environ.get("AA_DB_PASSWORD", "")

# ---------- ollama ----------
OLLAMA_URL = os.environ.get("AA_OLLAMA_URL", "http://localhost:11434/api/chat")
OLLAMA_TAGS_URL = os.environ.get("AA_OLLAMA_TAGS_URL", "http://localhost:11434/api/tags")
MODEL = os.environ.get("AA_MODEL", "qwen2.5-coder:3b")

# The LLM writes ~8 test cases; it is deliberately far slower than the calls
# made to the API under test.
LLM_TIMEOUT = int(os.environ.get("AA_LLM_TIMEOUT", "300"))
REQUEST_TIMEOUT = int(os.environ.get("AA_REQUEST_TIMEOUT", "30"))

# ---------- test generation ----------
CASES_REQUESTED = 8
MAX_CASES_AFTER_DEDUPE = 12

# Response text is truncated before being stored/returned, matching the
# original behaviour and keeping RunCases rows small.
MAX_RESPONSE_CHARS = 1500
MAX_PROMPT_RESPONSE_CHARS = 500
