"""Refresh an expired Google OAuth2 access token using the stored refresh token."""
from __future__ import annotations
import time
import httpx

TOKEN_URL = "https://oauth2.googleapis.com/token"


async def get_valid_token(
    *,
    user_id: str,
    tokens: dict,
    client_id: str,
    client_secret: str,
) -> str:
    """Return a valid access token, refreshing if within 5 minutes of expiry."""
    from worker import db as worker_db

    expiry = tokens.get("google_token_expiry") or 0
    now_ms = int(time.time() * 1000)
    if expiry and expiry - now_ms > 5 * 60 * 1000:
        return tokens["google_access_token"]

    refresh_token = tokens.get("google_refresh_token")
    if not refresh_token:
        raise RuntimeError("No refresh token stored — user must re-authenticate with Google")

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": client_id,
                "client_secret": client_secret,
            },
        )
    if resp.status_code != 200:
        raise RuntimeError(f"Token refresh failed ({resp.status_code}): {resp.text[:200]}")

    data = resp.json()
    new_token = data["access_token"]
    new_expiry = now_ms + int(data.get("expires_in", 3600)) * 1000
    await worker_db.update_google_access_token(user_id, new_token, new_expiry)
    return new_token
