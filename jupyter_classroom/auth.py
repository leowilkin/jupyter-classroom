from __future__ import annotations

import os
import secrets

import httpx
from fastapi import Request, HTTPException
from fastapi.responses import RedirectResponse
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired


COOKIE_NAME = "classroom-manager-session"
MAX_AGE = 3600

_crypto_keys = os.environ.get("JUPYTERHUB_CRYPTO_KEY", "dev-secret-key")
_signing_key = _crypto_keys.split(";")[0]
_serializer = URLSafeTimedSerializer(_signing_key)


def get_service_prefix() -> str:
    return os.environ.get("JUPYTERHUB_SERVICE_PREFIX", "/services/classroom-manager/")


def get_hub_base_url() -> str:
    return os.environ.get("JUPYTERHUB_BASE_URL", "/")


def get_session(request: Request) -> dict | None:
    cookie = request.cookies.get(COOKIE_NAME)
    if not cookie:
        return None
    try:
        return _serializer.loads(cookie, max_age=MAX_AGE)
    except (BadSignature, SignatureExpired):
        return None


def set_session(response, data: dict):
    value = _serializer.dumps(data)
    response.set_cookie(
        COOKIE_NAME,
        value,
        max_age=MAX_AGE,
        httponly=True,
        samesite="lax",
        path=get_service_prefix(),
    )


def require_auth(request: Request) -> dict:
    session = get_session(request)
    if session:
        return session
    state = secrets.token_urlsafe(32)
    request.app.state.oauth_states = getattr(request.app.state, "oauth_states", {})
    prefix = get_service_prefix()
    original_url = str(request.url)
    request.app.state.oauth_states[state] = original_url

    hub_base = get_hub_base_url()
    client_id = os.environ.get("JUPYTERHUB_CLIENT_ID", "service-classroom-manager")
    redirect_uri = os.environ.get(
        "JUPYTERHUB_OAUTH_CALLBACK_URL",
        str(request.base_url).rstrip("/") + prefix.rstrip("/") + "/oauth_callback",
    )

    authorize_url = (
        f"{str(request.base_url).rstrip('/')}{hub_base.rstrip('/')}/hub/api/oauth2/authorize"
        f"?client_id={client_id}"
        f"&redirect_uri={redirect_uri}"
        f"&response_type=code"
        f"&state={state}"
    )
    raise HTTPException(status_code=302, headers={"Location": authorize_url})


def require_admin(request: Request) -> dict:
    session = require_auth(request)
    if not session.get("admin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    return session


async def oauth_callback(request: Request):
    code = request.query_params.get("code")
    state = request.query_params.get("state")

    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing code or state parameter")

    oauth_states = getattr(request.app.state, "oauth_states", {})
    original_url = oauth_states.pop(state, None)
    if original_url is None:
        raise HTTPException(status_code=400, detail="Invalid or expired state parameter")

    api_url = os.environ.get("JUPYTERHUB_API_URL", "http://127.0.0.1:8000/hub/api")
    api_token = os.environ["JUPYTERHUB_API_TOKEN"]
    prefix = get_service_prefix()
    redirect_uri = os.environ.get(
        "JUPYTERHUB_OAUTH_CALLBACK_URL",
        str(request.base_url).rstrip("/") + prefix.rstrip("/") + "/oauth_callback",
    )

    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            f"{api_url}/oauth2/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "client_id": os.environ.get("JUPYTERHUB_CLIENT_ID", "service-classroom-manager"),
                "client_secret": api_token,
            },
        )
        if token_resp.status_code != 200:
            raise HTTPException(status_code=502, detail="Failed to exchange OAuth code for token")

        token_data = token_resp.json()
        access_token = token_data["access_token"]

        user_resp = await client.get(
            f"{api_url}/user",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if user_resp.status_code != 200:
            raise HTTPException(status_code=502, detail="Failed to fetch user info")

        user = user_resp.json()

    username = user["name"]
    is_admin = user.get("admin", False)
    groups = [g["name"] if isinstance(g, dict) else g for g in user.get("groups", [])]

    if not is_admin:
        raise HTTPException(status_code=403, detail="Access denied. You must be an admin.")

    session_data = {
        "username": username,
        "admin": is_admin,
        "groups": groups,
    }

    response = RedirectResponse(url=original_url, status_code=302)
    set_session(response, session_data)
    return response
