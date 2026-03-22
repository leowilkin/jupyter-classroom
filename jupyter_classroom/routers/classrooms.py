import asyncio
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse

from ..auth import get_hub_base_url, get_service_prefix, require_auth

router = APIRouter()


def _is_owner(group: dict, username: str, is_admin: bool) -> bool:
    if is_admin:
        return True
    teacher = group.get("properties", {}).get("teacher", "")
    return teacher == username


@router.get("/")
async def dashboard(request: Request, session: dict = Depends(require_auth)):
    hub = request.app.state.hub_client
    prefix = get_service_prefix()
    groups = await hub.list_groups()

    classrooms = []
    for g in groups:
        if g["name"] == "teachers":
            continue
        if not _is_owner(g, session["username"], session.get("admin", False)):
            continue

        usernames = [u["name"] if isinstance(u, dict) else u for u in g.get("users", [])]
        running = 0
        if usernames:
            try:
                users = await hub.get_users(usernames)
                for u in users:
                    if isinstance(u, dict) and u.get("servers", {}).get("", {}).get("ready"):
                        running += 1
            except Exception:
                pass

        classrooms.append({
            "name": g["name"],
            "student_count": len(usernames),
            "running_servers": running,
            "teacher": g.get("properties", {}).get("teacher", ""),
        })

    return request.app.state.templates.TemplateResponse("dashboard.html", {
        "request": request,
        "classrooms": classrooms,
        "session": session,
        "prefix": prefix,
        "hub_base_url": get_hub_base_url(),
        "flash": request.query_params.get("flash"),
    })


@router.get("/classrooms/{group_name}")
async def classroom_detail(group_name: str, request: Request, session: dict = Depends(require_auth)):
    hub = request.app.state.hub_client
    prefix = get_service_prefix()
    group = await hub.get_group(group_name)

    if not _is_owner(group, session["username"], session.get("admin", False)):
        from ..hub_client import HubAPIError
        raise HubAPIError(403, "You do not have access to this classroom")

    usernames = [u["name"] if isinstance(u, dict) else u for u in group.get("users", [])]
    students = []
    if usernames:
        users = await hub.get_users(usernames)
        for u in users:
            if not isinstance(u, dict):
                continue
            default_server = u.get("servers", {}).get("", {})
            students.append({
                "username": u["name"],
                "status": "running" if default_server.get("ready") else
                          "pending" if default_server.get("pending") else "stopped",
                "last_activity": default_server.get("last_activity", u.get("last_activity", "")),
            })

    return request.app.state.templates.TemplateResponse("classroom.html", {
        "request": request,
        "group_name": group_name,
        "students": students,
        "teacher": group.get("properties", {}).get("teacher", ""),
        "session": session,
        "prefix": prefix,
        "hub_base_url": get_hub_base_url(),
        "flash": request.query_params.get("flash"),
    })


@router.post("/classrooms/{group_name}/servers/start")
async def start_servers(group_name: str, request: Request, session: dict = Depends(require_auth), username: str = Form(None)):
    hub = request.app.state.hub_client
    prefix = get_service_prefix()
    group = await hub.get_group(group_name)

    if not _is_owner(group, session["username"], session.get("admin", False)):
        from ..hub_client import HubAPIError
        raise HubAPIError(403, "You do not have access to this classroom")

    if username:
        # Start a single student's server
        try:
            await hub.start_server(username)
            flash = f"Started server for '{username}'."
        except Exception:
            flash = f"Failed to start server for '{username}'."
    else:
        # Start all servers
        usernames = [u["name"] if isinstance(u, dict) else u for u in group.get("users", [])]
        results = await asyncio.gather(
            *[hub.start_server(u) for u in usernames],
            return_exceptions=True,
        )
        errors = [str(r) for r in results if isinstance(r, Exception)]
        flash = f"Started servers for {len(usernames)} students."
        if errors:
            flash += f" {len(errors)} failed."

    return RedirectResponse(
        url=f"{prefix}classrooms/{group_name}?flash={quote(flash)}",
        status_code=303,
    )


@router.post("/classrooms/{group_name}/servers/stop")
async def stop_servers(group_name: str, request: Request, session: dict = Depends(require_auth), username: str = Form(None)):
    hub = request.app.state.hub_client
    prefix = get_service_prefix()
    group = await hub.get_group(group_name)

    if not _is_owner(group, session["username"], session.get("admin", False)):
        from ..hub_client import HubAPIError
        raise HubAPIError(403, "You do not have access to this classroom")

    if username:
        # Stop a single student's server
        try:
            await hub.stop_server(username)
            flash = f"Stopped server for '{username}'."
        except Exception:
            flash = f"Failed to stop server for '{username}'."
    else:
        # Stop all servers
        usernames = [u["name"] if isinstance(u, dict) else u for u in group.get("users", [])]
        results = await asyncio.gather(
            *[hub.stop_server(u) for u in usernames],
            return_exceptions=True,
        )
        errors = [str(r) for r in results if isinstance(r, Exception)]
        flash = f"Stopped servers for {len(usernames)} students."
        if errors:
            flash += f" {len(errors)} failed."

    return RedirectResponse(
        url=f"{prefix}classrooms/{group_name}?flash={quote(flash)}",
        status_code=303,
    )
