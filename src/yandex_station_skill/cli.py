from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Optional

import typer

from .config import paths
from .passport_auth import PassportAuth, load_qr_state, qr_url, save_qr_state
from .quasar import Quasar
from .session import AuthError, YandexSession

app = typer.Typer(add_completion=False, no_args_is_help=True)
auth_app = typer.Typer(add_completion=False, no_args_is_help=True)
app.add_typer(auth_app, name="auth")


def _load_cookie(cookie: Optional[str]) -> str:
    if cookie:
        return cookie

    env = os.getenv("YANDEX_COOKIE")
    if env:
        return env

    p = paths().cookie_file
    if p.exists():
        return p.read_text(encoding="utf-8").strip()

    raise typer.BadParameter(
        "no cookies. set YANDEX_COOKIE env or put cookie string into ~/.config/yandex-station-skill/cookie.txt"
    )


def _match_device(devices: list[dict], needle: str) -> dict:
    n = needle.strip().lower()
    # exact id
    for d in devices:
        if str(d.get("id")) == needle:
            return d

    hits = []
    for d in devices:
        name = str(d.get("name", "")).lower()
        hid = str(d.get("id", "")).lower()
        if n in name or n in hid:
            hits.append(d)

    if not hits:
        raise typer.BadParameter(f"device not found: {needle}")
    if len(hits) > 1:
        opts = "\n".join([f"- {h.get('name')} ({h.get('id')}) [{h.get('house_name','')}]" for h in hits[:15]])
        raise typer.BadParameter(f"ambiguous device: {needle}\n{opts}")
    return hits[0]


async def _with_quasar(cookie: str):
    s = YandexSession(cookie=cookie)
    try:
        q = Quasar(session=s)
        yield q
    finally:
        await s.aclose()


@app.command()
def setup_cookie(cookie: str = typer.Argument(..., help="Raw Cookie header value (copied from browser)") ):
    """Save cookie string to ~/.config/yandex-station-skill/cookie.txt"""
    p = paths()
    p.config_dir.mkdir(parents=True, exist_ok=True)
    p.cookie_file.write_text(cookie.strip(), encoding="utf-8")
    typer.echo(str(p.cookie_file))


@auth_app.command("qr-url")
def auth_qr_url():
    """Start QR auth and print URL to scan."""

    async def run():
        auth = PassportAuth()
        try:
            state = await auth.qr_begin()
            save_qr_state(state)
            typer.echo(qr_url(state))
        finally:
            await auth.aclose()

    asyncio.run(run())


@auth_app.command("qr-complete")
def auth_qr_complete(timeout_s: int = typer.Option(180, help="How long to wait for scan confirmation")):
    """Poll QR auth status; on success save cookies to cookie.txt."""

    async def run():
        auth = PassportAuth()
        try:
            state = load_qr_state()
            # poll
            import time as _t

            deadline = _t.time() + timeout_s
            while _t.time() < deadline:
                ok = await auth.qr_poll(state)
                if ok:
                    await auth.ensure_quasar_cookie()
                    cookie = auth.export_cookie_header(".yandex.ru")
                    # save
                    p = paths()
                    p.config_dir.mkdir(parents=True, exist_ok=True)
                    p.cookie_file.write_text(cookie, encoding="utf-8")
                    typer.echo("ok")
                    typer.echo(str(p.cookie_file))
                    return
                await asyncio.sleep(2.0)
            raise TimeoutError("QR auth timed out")
        finally:
            await auth.aclose()

    asyncio.run(run())


@app.command()
def list(cookie: str = typer.Option(None, help="Cookie string (or set YANDEX_COOKIE)") ):
    """List devices visible in Yandex Quasar account."""
    cookie = _load_cookie(cookie)

    async def run():
        async for q in _with_quasar(cookie):
            devices = await q.list_devices_raw()
            # show speakers first
            devices_sorted = sorted(
                devices,
                key=lambda d: (
                    0 if d.get("capabilities") else 1,
                    d.get("house_name", ""),
                    d.get("name", ""),
                ),
            )
            for d in devices_sorted:
                caps = "caps" if d.get("capabilities") else "-"
                dtype = d.get("type") or "?"
                item_type = d.get("item_type") or "?"
                room = d.get("room_name") or ""
                typer.echo(
                    f"{d.get('name')}\t{d.get('id')}\t{d.get('house_name','')}\t{room}\t{item_type}\t{dtype}\t{caps}"
                )

    try:
        asyncio.run(run())
    except AuthError as e:
        raise typer.Exit(code=2) from e


@app.command()
def local(cookie: str = typer.Option(None)):
    """List local speakers discovered via mDNS (_yandexio._tcp.local.)."""
    from .discovery import discover_local_speakers

    speakers = discover_local_speakers(time_s=2.0)
    if not speakers:
        typer.echo("no local speakers discovered (mDNS).")
        raise typer.Exit(code=3)
    for s in speakers:
        typer.echo(f"{s.device_id}\t{s.platform}\t{s.host}:{s.port}")


@app.command()
def pause(device: str, cookie: str = typer.Option(None), prefer_local: bool = typer.Option(True, help="Try local Glagol first when possible")):
    """Pause on a station."""
    _action(device, "пауза", cookie, prefer_local=prefer_local)


@app.command()
def resume(device: str, cookie: str = typer.Option(None), prefer_local: bool = typer.Option(True, help="Try local Glagol first when possible")):
    """Resume on a station."""
    _action(device, "продолжить", cookie, prefer_local=prefer_local)


@app.command()
def next(device: str, cookie: str = typer.Option(None), prefer_local: bool = typer.Option(True)):
    """Next track."""
    _action(device, "следующий трек", cookie, prefer_local=prefer_local)


@app.command()
def prev(device: str, cookie: str = typer.Option(None), prefer_local: bool = typer.Option(True)):
    """Previous track."""
    _action(device, "прошлый трек", cookie, prefer_local=prefer_local)


@app.command()
def volume(
    device: str,
    level: int,
    cookie: str = typer.Option(None),
    prefer_local: bool = typer.Option(True),
    max_level: int = typer.Option(30, help="Safety cap; default 30"),
):
    """Set volume 0..100 (capped by max_level)."""
    if level < 0 or level > 100:
        raise typer.BadParameter("level must be 0..100")
    if level > max_level:
        raise typer.BadParameter(f"level must be <= {max_level}")
    _action(device, f"громкость на {level}", cookie, prefer_local=prefer_local)


@app.command()
def play(device: str, query: str, cookie: str = typer.Option(None), prefer_local: bool = typer.Option(True)):
    """Play query on station (best-effort)."""
    _action(device, f"включи {query}", cookie, prefer_local=prefer_local)


def _action(device: str, text: str, cookie: str | None, *, prefer_local: bool = True):
    cookie = _load_cookie(cookie)

    async def run():
        async for q in _with_quasar(cookie):
            devices = await q.list_devices_raw()
            d = _match_device(devices, device)

            did = str(d["id"])
            name = d.get("name")

            if prefer_local:
                # try local glagol if we can discover device and get tokens
                try:
                    from .discovery import discover_local_speakers
                    from .glagol import GlagolClient, get_conversation_token
                    from .tokens import get_tokens

                    locals_ = {s.device_id: s for s in discover_local_speakers(time_s=2.0)}
                    # we need quasar's device_id/platform mapping
                    cfg = await q.session.get(f"https://iot.quasar.yandex.ru/m/user/devices/{did}/configuration")
                    quasar_info = cfg.get("quasar_info") or {}
                    local_id = quasar_info.get("device_id")
                    platform = quasar_info.get("platform")

                    if local_id and platform and str(local_id) in locals_:
                        sp = locals_[str(local_id)]
                        tokens = await get_tokens(cookie)
                        conv = await get_conversation_token(device_id=str(local_id), platform=str(platform), music_token=tokens.music_token)

                        # map text to local commands where possible
                        cmd_map = {
                            "пауза": {"command": "stop"},
                            "продолжить": {"command": "play"},
                            "следующий трек": {"command": "next"},
                            "прошлый трек": {"command": "prev"},
                        }
                        if text.startswith("громкость на "):
                            try:
                                v = float(text.split()[-1])
                                payload = {"command": "setVolume", "volume": round(v, 1)}
                            except Exception:
                                payload = None
                        else:
                            payload = cmd_map.get(text)

                        if payload:
                            g = GlagolClient(host=sp.host, port=sp.port, conversation_token=conv)
                            resp = await g.send(payload)
                            typer.echo(f"ok(local): {name} ({did}) <= {payload} :: {resp.get('payload', resp)}")
                            return
                except Exception:
                    pass

            # fallback: cloud scenario action
            scenario_map = await q.ensure_speaker_scenarios(devices)
            sid = scenario_map.get(did)
            if not sid:
                raise typer.BadParameter("device has no capabilities for cloud scenarios (module?)")
            await q.run_speaker_action(sid, did, text)
            typer.echo(f"ok(cloud): {name} ({did}) <= {text}")

    try:
        asyncio.run(run())
    except AuthError as e:
        raise typer.Exit(code=2) from e


def main() -> None:
    app()
