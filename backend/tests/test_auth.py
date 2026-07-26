"""Auth flow — registration, login, token refresh, and protected access."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.core.config import settings

PREFIX = f"{settings.API_V1_PREFIX}/auth"

CREDS = {"email": "candidate@example.com", "password": "hunter2secret"}


async def _register(client: AsyncClient, **overrides) -> dict:
    payload = {**CREDS, **overrides}
    return await client.post(f"{PREFIX}/register", json=payload)


async def test_register_returns_user_without_password(client: AsyncClient) -> None:
    resp = await _register(client)
    assert resp.status_code == 201
    body = resp.json()
    assert body["email"] == CREDS["email"]
    assert body["role"] == "candidate"
    assert "hashed_password" not in body and "password" not in body


async def test_duplicate_email_conflicts(client: AsyncClient) -> None:
    await _register(client)
    resp = await _register(client)
    assert resp.status_code == 409


async def test_login_issues_token_pair(client: AsyncClient) -> None:
    await _register(client)
    resp = await client.post(f"{PREFIX}/login", json=CREDS)
    assert resp.status_code == 200
    body = resp.json()
    assert body["access_token"] and body["refresh_token"]
    assert body["token_type"] == "bearer"


async def test_login_wrong_password_rejected(client: AsyncClient) -> None:
    await _register(client)
    resp = await client.post(
        f"{PREFIX}/login", json={**CREDS, "password": "wrongwrong"}
    )
    assert resp.status_code == 401


async def test_me_requires_and_accepts_access_token(client: AsyncClient) -> None:
    await _register(client)
    tokens = (await client.post(f"{PREFIX}/login", json=CREDS)).json()

    unauth = await client.get(f"{PREFIX}/me")
    assert unauth.status_code == 401

    resp = await client.get(
        f"{PREFIX}/me",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert resp.status_code == 200
    assert resp.json()["email"] == CREDS["email"]


async def test_refresh_token_mints_new_pair(client: AsyncClient) -> None:
    await _register(client)
    tokens = (await client.post(f"{PREFIX}/login", json=CREDS)).json()
    resp = await client.post(
        f"{PREFIX}/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert resp.status_code == 200
    assert resp.json()["access_token"]


async def test_access_token_rejected_as_refresh(client: AsyncClient) -> None:
    await _register(client)
    tokens = (await client.post(f"{PREFIX}/login", json=CREDS)).json()
    # Using an access token where a refresh token is required must fail.
    resp = await client.post(
        f"{PREFIX}/refresh", json={"refresh_token": tokens["access_token"]}
    )
    assert resp.status_code == 401


@pytest.mark.parametrize("bad", ["", "short", "1234567"])
async def test_password_min_length_enforced(client: AsyncClient, bad: str) -> None:
    resp = await _register(client, password=bad)
    assert resp.status_code == 422
