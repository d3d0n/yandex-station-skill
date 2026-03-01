from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from typing import Any

import httpx


class AuthError(RuntimeError):
    pass


@dataclass
class YandexSession:
    cookie: str
    timeout_s: float = 20.0

    def __post_init__(self) -> None:
        # normalize cookie header
        self.cookie = self.cookie.strip()
        if self.cookie.lower().startswith("cookie:"):
            self.cookie = self.cookie.split(":", 1)[1].strip()

        self._csrf_token: str | None = None
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(self.timeout_s),
            headers={
                "User-Agent": "openclaw-yandex-station-skill/0.1",
                "Cookie": self.cookie,
            },
            follow_redirects=True,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _ensure_csrf(self) -> str:
        if self._csrf_token:
            return self._csrf_token

        r = await self._client.get("https://yandex.ru/quasar")
        if r.status_code in (401, 403):
            raise AuthError("cookies invalid/expired (can't load yandex.ru/quasar)")

        raw = r.text
        m = re.search(r'"csrfToken2":"(.+?)"', raw)
        if not m:
            raise RuntimeError("can't parse csrfToken2 from yandex.ru/quasar")

        self._csrf_token = m.group(1)
        return self._csrf_token

    async def request(self, method: str, url: str, *, json: Any | None = None) -> dict:
        # small anti-DDOS delay like HA integration
        await asyncio.sleep(0.15)

        headers = {}
        if method.lower() != "get":
            csrf = await self._ensure_csrf()
            headers["x-csrf-token"] = csrf

        r = await self._client.request(method, url, json=json, headers=headers)

        # retry once on CSRF issues
        if r.status_code == 403 and method.lower() != "get":
            self._csrf_token = None
            csrf = await self._ensure_csrf()
            r = await self._client.request(method, url, json=json, headers={"x-csrf-token": csrf})

        if r.status_code in (401, 403):
            raise AuthError(f"auth failed ({r.status_code}) for {url}")

        r.raise_for_status()
        data = r.json()
        if isinstance(data, dict) and data.get("status") and data.get("status") != "ok":
            raise RuntimeError({"url": url, "status": data.get("status"), "resp": data})
        return data

    async def get(self, url: str) -> dict:
        return await self.request("GET", url)

    async def post(self, url: str, json: Any | None = None) -> dict:
        return await self.request("POST", url, json=json)

    async def put(self, url: str, json: Any | None = None) -> dict:
        return await self.request("PUT", url, json=json)
