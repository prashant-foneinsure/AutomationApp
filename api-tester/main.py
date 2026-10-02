"""AutomationApp entrypoint.

Wiring only: build the app, install the module routers, add the SPA fallback,
then mount the static build LAST. See AGENTS.md for why the order matters.
"""
import os

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import config
from app.modules import install
from app.services.llm import LLMError

app = FastAPI(title="AutomationApp")

install(app)


# ---------- expected failure states ----------
# Ollama being stopped, slow, or missing the model is a normal operational state
# for an app that depends on a local model, not a bug. Handled once here rather
# than in each route, so every endpoint reports it the same readable way instead
# of surfacing an opaque 500.
@app.exception_handler(LLMError)
async def model_unavailable(request, exc: LLMError):
    return JSONResponse(status_code=502, content={"detail": (
        f"The local model (Ollama) could not be reached or did not answer in "
        f"time: {exc}. Check that Ollama is running and that the configured "
        f"model has been pulled.")})


# ---------- backwards compatibility ----------
# The pre-restructure UI posted to /api/run. Keep it as a thin alias of the new
# adhoc endpoint so an already-open browser tab does not break mid-migration.
@app.post("/api/run", include_in_schema=False, deprecated=True)
def legacy_run(req: dict):
    from app.modules.api_testing.schemas import AdhocRequest
    from app.modules.api_testing.service import run_adhoc
    from app.modules.api_testing.router import _strip_internals
    try:
        body = AdhocRequest(**req)
    except Exception as exc:
        raise HTTPException(422, f"Invalid request: {exc}")
    return _strip_internals(run_adhoc(
        body.curl, body.method, body.instruction, body.token,
        body.username, body.password))


# ---------- static build + SPA fallback ----------
class SPAStaticFiles(StaticFiles):
    """The built frontend, with history-API fallback to index.html.

    This replaces a separate `/{spa_path:path}` catch-all route. That route was
    registered before the static mount and therefore matched EVERY path,
    including /assets/*.js, so the browser was served index.html with a
    text/html content type and refused the module script. Handling the fallback
    inside the mount means a real file is always served as itself, and only a
    genuinely missing path falls back to the SPA shell.
    """

    async def get_response(self, path, scope):
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code != 404:
                raise
            # StaticFiles builds this with os.path.join, so on Windows it arrives
            # as "api\nope". Normalise before matching, or every guard below is
            # silently skipped and unknown API paths return the SPA shell.
            rel = path.replace("\\", "/")
            # An unknown /api/... path is a real 404, not a client-side route.
            if rel == "api" or rel.startswith("api/"):
                raise HTTPException(404, "Unknown API endpoint") from exc
            # A path naming a file extension is asking for a real asset. Falling
            # back to the shell would make the browser fail with a confusing
            # MIME-type error instead of a clear 404.
            if "." in rel.rsplit("/", 1)[-1]:
                raise
            index = os.path.join(self.directory, "index.html")
            # Checked explicitly: FileResponse defers reading the file until the
            # response is streamed, so a missing build would fail as a bare 500.
            if not os.path.isfile(index):
                raise HTTPException(
                    500,
                    "Frontend build not found. Run `npm install && npm run build` in "
                    "api-tester/frontend/, or use the Vite dev server on :5173."
                ) from exc
            return FileResponse(index)


# Must stay last: this catch-all mount shadows anything registered after it.
# The API routers and the /docs routes are registered earlier, so they win.
app.mount("/", SPAStaticFiles(directory=config.STATIC_DIR, html=True), name="static")
