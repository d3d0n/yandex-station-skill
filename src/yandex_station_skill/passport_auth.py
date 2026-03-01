from __future__ import annotations

import asyncio
import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from .config import paths


class AuthError(RuntimeError):
    pass


@dataclass
class QrState:
    csrf_token: str
    track_id: str

    def to_json(self) -> dict[str, Any]:
        return {"csrf_token": self.csrf_token, "track_id": self.track_id}

    @staticmethod
    def from_json(d: dict[str, Any]) -> "QrState":
        return QrState(csrf_token=str(d["csrf_token"]), track_id=str(d["track_id"]))


class PassportAuth:
    """Implements the same QR auth flow as AlexxIT/YandexStation.

    Flow:
      1) GET https://passport.yandex.ru/am?app_platform=android -> parse csrf_token
      2) POST https://passport.yandex.ru/registration-validations/auth/password/submit (with_code=1)
         -> returns {csrf_token, track_id}
      3) user opens https://passport.yandex.ru/auth/magic/code/?track_id=<track_id> and confirms in app
      4) we poll POST https://passport.yandex.ru/auth/new/magic/status/
      5) once OK, we should be logged-in in this httpx session cookie jar.

    Then we can export cookie header for yandex.ru/quasar usage.
    """

    def __init__(self, timeout_s: float = 20.0):
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_s),
            headers={"User-Agent": "openclaw-yandex-station-skill/0.1"},
            follow_redirects=True,
        )

    async def aclose(self) -> None:
        await self.client.aclose()

    async def qr_begin(self) -> QrState:
        r = await self.client.get("https://passport.yandex.ru/am?app_platform=android")
        r.raise_for_status()
        m = re.search(r'"csrf_token" value="([^"]+)"', r.text)
        if not m:
            raise RuntimeError("can't parse csrf_token from passport page")
        csrf_token = m.group(1)

        r = await self.client.post(
            "https://passport.yandex.ru/registration-validations/auth/password/submit",
            data={
                "csrf_token": csrf_token,
                "retpath": "https://passport.yandex.ru/profile",
                "with_code": 1,
            },
        )
        r.raise_for_status()
        resp = r.json()
        if resp.get("status") != "ok":
            raise AuthError(f"passport submit failed: {resp}")

        return QrState(csrf_token=str(resp["csrf_token"]), track_id=str(resp["track_id"]))

    async def qr_poll(self, state: QrState) -> bool:
        r = await self.client.post(
            "https://passport.yandex.ru/auth/new/magic/status/",
            data={"csrf_token": state.csrf_token, "track_id": state.track_id},
        )
        r.raise_for_status()
        resp = r.json() if r.text else {}
        return resp.get("status") == "ok"

    async def ensure_quasar_cookie(self) -> None:
        # Hit quasar page to ensure proper yandex.ru cookies are set
        r = await self.client.get("https://yandex.ru/quasar")
        r.raise_for_status()

    def export_cookie_header(self, domain: str = ".yandex.ru") -> str:
        # Build Cookie header string from the session jar.
        # httpx stores cookies as a Cookies object; we can iterate over its jar.
        pairs: list[str] = []
        jar = self.client.cookies.jar
        for c in jar:
            try:
                cdomain = (c.domain or "").lstrip(".")
                want = domain.lstrip(".")
                if cdomain == want or cdomain.endswith("." + want):
                    pairs.append(f"{c.name}={c.value}")
            except Exception:
                continue

        # de-dup by name (keep last)
        dedup: dict[str, str] = {}
        for p in pairs:
            k, v = p.split("=", 1)
            dedup[k] = v
        return "; ".join([f"{k}={v}" for k, v in dedup.items()])


def qr_state_path() -> Path:
    p = paths()
    p.config_dir.mkdir(parents=True, exist_ok=True)
    return p.config_dir / "qr.json"


def save_qr_state(state: QrState) -> Path:
    path = qr_state_path()
    path.write_text(json.dumps(state.to_json(), ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_qr_state() -> QrState:
    path = qr_state_path()
    if not path.exists():
        raise FileNotFoundError(str(path))
    return QrState.from_json(json.loads(path.read_text(encoding="utf-8")))


def qr_url(state: QrState) -> str:
    return f"https://passport.yandex.ru/auth/magic/code/?track_id={state.track_id}"


async def qr_wait(auth: PassportAuth, state: QrState, *, timeout_s: int = 180, poll_s: float = 2.0) -> None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if await auth.qr_poll(state):
            return
        await asyncio.sleep(poll_s)
    raise TimeoutError("QR auth timed out")
