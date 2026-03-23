import logging
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.templating import Jinja2Templates

from . import __version__
from .auth import get_service_prefix, oauth_callback
from .hub_client import HubAPIError, HubClient
from .routers import admin, classrooms, students

logger = logging.getLogger(__name__)


async def _fetch_latest_version() -> str | None:
    """Fetch the latest release tag from GitHub."""
    url = "https://api.github.com/repos/leowilkin/jupyter-classroom/releases/latest"
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, timeout=5)
            resp.raise_for_status()
            tag = resp.json().get("tag_name", "")
            return tag.lstrip("v") if tag else None
    except Exception:
        logger.debug("Failed to check for updates", exc_info=True)
        return None


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.hub_client = HubClient()
    app.state.oauth_states = {}
    latest = await _fetch_latest_version()
    templates.env.globals["latest_version"] = latest
    yield
    await app.state.hub_client.close()


prefix = get_service_prefix().rstrip("/")

app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None)

templates_dir = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(templates_dir))
templates.env.globals["version"] = __version__

static_dir = Path(__file__).parent / "static"


@app.get(f"{prefix}/static/{{filename}}")
async def serve_static(filename: str):
    file_path = static_dir / filename
    if not file_path.is_file():
        raise HTTPException(status_code=404)
    return FileResponse(file_path)


@app.middleware("http")
async def attach_templates(request: Request, call_next):
    request.app.state.templates = templates
    response = await call_next(request)
    return response


# Mount routers under the service prefix
app.include_router(classrooms.router, prefix=prefix)
app.include_router(students.router, prefix=prefix)
app.include_router(admin.router, prefix=prefix)


# OAuth callback
@app.get(f"{prefix}/oauth_callback")
async def _oauth_callback(request: Request):
    return await oauth_callback(request)


@app.exception_handler(HubAPIError)
async def hub_api_error_handler(request: Request, exc: HubAPIError):
    svc_prefix = get_service_prefix()
    return templates.TemplateResponse(
        request,
        "error.html",
        {
            "status_code": exc.status_code,
            "detail": exc.detail,
            "prefix": svc_prefix,
            "session": None,
        },
        status_code=exc.status_code,
    )


@app.exception_handler(500)
async def internal_error_handler(request: Request, exc: Exception):
    svc_prefix = get_service_prefix()
    return templates.TemplateResponse(
        request,
        "error.html",
        {
            "status_code": 500,
            "detail": "An internal error occurred.",
            "prefix": svc_prefix,
            "session": None,
        },
        status_code=500,
    )


def main():
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=10101)


if __name__ == "__main__":
    main()
