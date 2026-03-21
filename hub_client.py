from __future__ import annotations

import asyncio
import os

import httpx


class HubAPIError(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"Hub API {status_code}: {detail}")


class HubClient:
    def __init__(self):
        self.api_url = os.environ.get(
            "JUPYTERHUB_API_URL", "http://127.0.0.1:8000/hub/api"
        )
        self.api_token = os.environ["JUPYTERHUB_API_TOKEN"]
        self._client = httpx.AsyncClient(
            base_url=self.api_url,
            headers={"Authorization": f"Bearer {self.api_token}"},
            timeout=30.0,
        )
        self._semaphore = asyncio.Semaphore(10)

    async def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        resp = await self._client.request(method, path, **kwargs)
        if resp.status_code >= 400:
            try:
                detail = resp.json().get("message", resp.text)
            except Exception:
                detail = resp.text
            raise HubAPIError(resp.status_code, detail)
        return resp

    async def list_groups(self) -> list[dict]:
        groups = []
        offset = 0
        limit = 200
        while True:
            resp = await self._client.get(
                "/groups",
                params={"offset": offset, "limit": limit},
                headers={
                    "Accept": "application/jupyterhub-pagination+json",
                },
            )
            if resp.status_code >= 400:
                try:
                    detail = resp.json().get("message", resp.text)
                except Exception:
                    detail = resp.text
                raise HubAPIError(resp.status_code, detail)
            data = resp.json()
            items = data.get("items", data if isinstance(data, list) else [])
            groups.extend(items)
            pagination = data.get("_pagination", {})
            next_info = pagination.get("next")
            if not next_info:
                break
            offset = next_info.get("offset", offset + limit)
        return groups

    async def get_group(self, name: str) -> dict:
        resp = await self._request("GET", f"/groups/{name}")
        return resp.json()

    async def create_group(self, name: str) -> dict:
        resp = await self._request("POST", f"/groups/{name}")
        return resp.json()

    async def set_group_properties(self, name: str, props: dict) -> dict:
        resp = await self._request(
            "PUT", f"/groups/{name}/properties", json=props
        )
        return resp.json()

    async def add_users_to_group(self, name: str, users: list[str]) -> dict:
        resp = await self._request(
            "POST", f"/groups/{name}/users", json={"users": users}
        )
        return resp.json()

    async def remove_users_from_group(self, name: str, users: list[str]) -> dict:
        resp = await self._client.request(
            "DELETE",
            f"{self.api_url}/groups/{name}/users",
            json={"users": users},
            headers={"Authorization": f"Bearer {self.api_token}"},
        )
        if resp.status_code >= 400:
            try:
                detail = resp.json().get("message", resp.text)
            except Exception:
                detail = resp.text
            raise HubAPIError(resp.status_code, detail)
        return resp.json()

    async def create_user(self, username: str) -> dict:
        resp = await self._request("POST", "/users", json={"usernames": [username]})
        return resp.json()

    async def set_admin(self, username: str, admin: bool) -> dict:
        resp = await self._request("PATCH", f"/users/{username}", json={"admin": admin})
        return resp.json()

    async def list_users(self) -> list[dict]:
        resp = await self._request("GET", "/users")
        return resp.json()

    async def get_user(self, username: str) -> dict:
        resp = await self._request("GET", f"/users/{username}")
        return resp.json()

    async def get_users(self, usernames: list[str]) -> list[dict]:
        async def _get(u: str):
            async with self._semaphore:
                return await self.get_user(u)
        return await asyncio.gather(*[_get(u) for u in usernames])

    async def start_server(self, username: str) -> int:
        async with self._semaphore:
            resp = await self._request("POST", f"/users/{username}/server")
            return resp.status_code

    async def stop_server(self, username: str) -> int:
        async with self._semaphore:
            resp = await self._request("DELETE", f"/users/{username}/server")
            return resp.status_code

    async def get_user_by_token(self, token: str) -> dict:
        resp = await self._client.get(
            "/user",
            headers={"Authorization": f"Bearer {token}"},
        )
        if resp.status_code >= 400:
            try:
                detail = resp.json().get("message", resp.text)
            except Exception:
                detail = resp.text
            raise HubAPIError(resp.status_code, detail)
        return resp.json()

    async def close(self):
        await self._client.aclose()
