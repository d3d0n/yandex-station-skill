from __future__ import annotations

from dataclasses import dataclass

import httpx


@dataclass(frozen=True)
class QrFetchResult:
    ok: bool
    kind: str  # svg|captcha|html|error
    final_url: str
    content_type: str | None
    body: bytes


def _headers() -> dict[str, str]:
    return {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept": "image/svg+xml,image/*,*/*;q=0.8",
        "Accept-Language": "ru,en-US;q=0.9,en;q=0.8",
    }


def fetch_magic_qr(url: str, *, timeout_s: float = 20.0) -> QrFetchResult:
    """Best-effort fetch of the *real* QR asset for Yandex Passport magic login.

    In ideal conditions, this endpoint returns `image/svg+xml`.
    In anti-bot conditions, it redirects to `showcaptcha` and returns HTML.
    """
    try:
        with httpx.Client(timeout=timeout_s, follow_redirects=True, headers=_headers()) as c:
            r = c.get(url)
            final = str(r.url)
            ctype = r.headers.get("content-type")
            body = r.content

        if "showcaptcha" in final:
            return QrFetchResult(False, "captcha", final, ctype, body)

        if ctype and "image/svg" in ctype:
            return QrFetchResult(True, "svg", final, ctype, body)

        if ctype and "text/html" in ctype:
            return QrFetchResult(False, "html", final, ctype, body)

        return QrFetchResult(False, "error", final, ctype, body)

    except Exception as e:
        return QrFetchResult(False, "error", url, None, repr(e).encode("utf-8"))
