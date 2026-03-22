from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse

from ..auth import get_service_prefix, require_auth

router = APIRouter()


@router.post("/classrooms/{group_name}/students")
async def add_student(
    group_name: str,
    request: Request,
    username: str = Form(...),
    session: dict = Depends(require_auth),
):
    hub = request.app.state.hub_client
    prefix = get_service_prefix()
    from ..hub_client import HubAPIError
    try:
        await hub.get_user(username)
    except HubAPIError:
        await hub.create_user(username)
    await hub.add_users_to_group(group_name, [username])
    flash = f"Added student '{username}' to {group_name}."
    return RedirectResponse(
        url=f"{prefix}classrooms/{group_name}?flash={quote(flash)}",
        status_code=303,
    )


@router.post("/classrooms/{group_name}/students/{username}/remove")
async def remove_student(
    group_name: str,
    username: str,
    request: Request,
    session: dict = Depends(require_auth),
):
    hub = request.app.state.hub_client
    prefix = get_service_prefix()
    await hub.remove_users_from_group(group_name, [username])
    flash = f"Removed student '{username}' from {group_name}."
    return RedirectResponse(
        url=f"{prefix}classrooms/{group_name}?flash={quote(flash)}",
        status_code=303,
    )
