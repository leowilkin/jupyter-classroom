import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from hub_client import HubClient, HubAPIError
from auth import oauth_callback, get_service_prefix
from routers import classrooms, students, admin


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.hub_client = HubClient()
    app.state.oauth_states = {}
    yield
    await app.state.hub_client.close()


prefix = get_service_prefix().rstrip("/")

app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None)

templates_dir = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(templates_dir))

static_dir = Path(__file__).parent / "static"

from fastapi.responses import FileResponse

@app.get(f"{prefix}/static/{{filename}}")
async def serve_static(filename: str):
    file_path = static_dir / filename
    if not file_path.is_file():
        from fastapi import HTTPException
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
        "error.html",
        {
            "request": request,
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
        "error.html",
        {
            "request": request,
            "status_code": 500,
            "detail": "An internal error occurred.",
            "prefix": svc_prefix,
            "session": None,
        },
        status_code=500,
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=10101)
