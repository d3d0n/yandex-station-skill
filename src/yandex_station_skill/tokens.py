from __future__ import annotations

from dataclasses import dataclass

import httpx


@dataclass
class Tokens:
    x_token: str
    music_token: str


async def get_x_token_from_cookies(cookie: str, *, host: str = "passport.yandex.ru") -> str:
    """Equivalent to AlexxIT/YandexStation login_cookies -> token_by_sessionid.

    Uses Ya-Client-Host + Ya-Client-Cookie headers.
    """
    cookie = cookie.strip()
    if cookie.lower().startswith("cookie:"):
        cookie = cookie.split(":", 1)[1].strip()

    async with httpx.AsyncClient(timeout=20.0, headers={"User-Agent": "openclaw-yandex-station-skill/0.1"}) as c:
        r = await c.post(
            "https://mobileproxy.passport.yandex.net/1/bundle/oauth/token_by_sessionid",
            data={
                "client_id": "c0ebe342af7d48fbbbfcf2d2eedb8f9e",
                "client_secret": "ad0a908f0aa341a182a37ecd75bc319e",
            },
            headers={"Ya-Client-Host": host, "Ya-Client-Cookie": cookie},
        )
        r.raise_for_status()
        resp = r.json()
        return str(resp["access_token"])


async def get_music_token_from_x_token(x_token: str) -> str:
    """Equivalent to YandexSession.get_music_token()."""
    async with httpx.AsyncClient(timeout=20.0, headers={"User-Agent": "openclaw-yandex-station-skill/0.1"}) as c:
        r = await c.post(
            "https://oauth.mobile.yandex.net/1/token",
            data={
                "client_secret": "53bc75238f0c4d08a118e51fe9203300",
                "client_id": "23cabbbdc6cd418abb4b39c32c41195d",
                "grant_type": "x-token",
                "access_token": x_token,
            },
        )
        r.raise_for_status()
        resp = r.json()
        return str(resp["access_token"])


async def get_tokens(cookie: str) -> Tokens:
    x = await get_x_token_from_cookies(cookie)
    m = await get_music_token_from_x_token(x)
    return Tokens(x_token=x, music_token=m)
