from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse

from ..auth import get_hub_base_url, get_service_prefix, require_auth
from ..hub_client import HubAPIError

router = APIRouter()


@router.get("/admin")
async def admin_page(request: Request, session: dict = Depends(require_auth)):
    hub = request.app.state.hub_client
    prefix = get_service_prefix()
    groups = await hub.list_groups()

    classrooms = []
    for g in groups:
        if g["name"] == "teachers":
            continue
        usernames = [u["name"] if isinstance(u, dict) else u for u in g.get("users", [])]
        classrooms.append({
            "name": g["name"],
            "student_count": len(usernames),
            "teacher": g.get("properties", {}).get("teacher", ""),
        })

    # Get admin users
    users = await hub.list_users()
    admins = [u["name"] for u in users if u.get("admin")]

    return request.app.state.templates.TemplateResponse("admin.html", {
        "request": request,
        "classrooms": classrooms,
        "admins": admins,
        "session": session,
        "prefix": prefix,
        "hub_base_url": get_hub_base_url(),
        "flash": request.query_params.get("flash"),
    })


@router.post("/admin/classrooms")
async def create_classroom(
    request: Request,
    name: str = Form(...),
    teacher: str = Form(...),
    session: dict = Depends(require_auth),
):
    hub = request.app.state.hub_client
    prefix = get_service_prefix()
    await hub.create_group(name)
    await hub.set_group_properties(name, {"teacher": teacher})
    flash = f"Created classroom '{name}' with teacher '{teacher}'."
    return RedirectResponse(
        url=f"{prefix}admin?flash={quote(flash)}",
        status_code=303,
    )


@router.post("/admin/admins")
async def add_admin(
    request: Request,
    email: str = Form(...),
    session: dict = Depends(require_auth),
):
    hub = request.app.state.hub_client
    prefix = get_service_prefix()
    try:
        await hub.get_user(email)
    except HubAPIError:
        await hub.create_user(email)
    await hub.set_admin(email, True)
    flash = f"Made '{email}' an admin."
    return RedirectResponse(
        url=f"{prefix}admin?flash={quote(flash)}",
        status_code=303,
    )


@router.post("/admin/admins/{email}/remove")
async def remove_admin(
    email: str,
    request: Request,
    session: dict = Depends(require_auth),
):
    hub = request.app.state.hub_client
    prefix = get_service_prefix()
    if email == session["username"]:
        flash = "You cannot remove yourself as admin."
        return RedirectResponse(
            url=f"{prefix}admin?flash={quote(flash)}",
            status_code=303,
        )
    await hub.set_admin(email, False)
    flash = f"Removed '{email}' as admin."
    return RedirectResponse(
        url=f"{prefix}admin?flash={quote(flash)}",
        status_code=303,
    )
