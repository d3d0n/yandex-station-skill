from __future__ import annotations

import json
import ssl
import time
import uuid
from dataclasses import dataclass
from typing import Any

import httpx
import websockets


@dataclass
class GlagolClient:
    host: str
    port: int
    conversation_token: str

    @property
    def url(self) -> str:
        return f"wss://{self.host}:{self.port}"

    async def send(self, payload: dict[str, Any], *, timeout_s: float = 5.0) -> dict[str, Any]:
        req_id = str(uuid.uuid4())
        msg = {
            "conversationToken": self.conversation_token,
            "id": req_id,
            "payload": payload,
            "sentTime": int(round(time.time() * 1000)),
        }

        ssl_ctx = ssl.create_default_context()
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode = ssl.CERT_NONE

        async with websockets.connect(self.url, ssl=ssl_ctx) as ws:
            await ws.send(json.dumps(msg, ensure_ascii=False))
            deadline = time.time() + timeout_s
            while time.time() < deadline:
                raw = await ws.recv()
                data = json.loads(raw)
                if data.get("id") == req_id:
                    return data
            return {"error": "timeout"}


async def get_conversation_token(*, device_id: str, platform: str, music_token: str) -> str:
    """GET https://quasar.yandex.net/glagol/token?device_id=...&platform=... with OAuth music_token."""
    async with httpx.AsyncClient(timeout=20.0) as c:
        r = await c.get(
            "https://quasar.yandex.net/glagol/token",
            params={"device_id": device_id, "platform": platform},
            headers={"Authorization": f"OAuth {music_token}"},
        )
        r.raise_for_status()
        resp = r.json()
        if resp.get("status") != "ok":
            raise RuntimeError(resp)
        return str(resp["token"])
