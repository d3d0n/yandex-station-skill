from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Optional

import typer

from .config import paths
from .quasar import Quasar
from .session import AuthError, YandexSession

app = typer.Typer(add_completion=False, no_args_is_help=True)


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


@app.command()
def list(cookie: str = typer.Option(None, help="Cookie string (or set YANDEX_COOKIE)") ):
    """List devices visible in Yandex Quasar account."""
    cookie = _load_cookie(cookie)

    async def run():
        async for q in _with_quasar(cookie):
            devices = await q.list_devices_raw()
            # show speakers first
            devices_sorted = sorted(devices, key=lambda d: (0 if d.get("capabilities") else 1, d.get("house_name",""), d.get("name","")))
            for d in devices_sorted:
                caps = "caps" if d.get("capabilities") else "-"
                typer.echo(f"{d.get('name')}\t{d.get('id')}\t{d.get('house_name','')}\t{caps}")

    try:
        asyncio.run(run())
    except AuthError as e:
        raise typer.Exit(code=2) from e


@app.command()
def pause(device: str, cookie: str = typer.Option(None)):
    """Pause on a station (cloud text command)."""
    _action(device, "пауза", cookie)


@app.command()
def resume(device: str, cookie: str = typer.Option(None)):
    """Resume on a station (cloud text command)."""
    _action(device, "продолжить", cookie)


@app.command()
def next(device: str, cookie: str = typer.Option(None)):
    """Next track (cloud text command)."""
    _action(device, "следующий трек", cookie)


@app.command()
def prev(device: str, cookie: str = typer.Option(None)):
    """Previous track (cloud text command)."""
    _action(device, "прошлый трек", cookie)


@app.command()
def volume(device: str, level: int, cookie: str = typer.Option(None)):
    """Set volume 0..100 (cloud text command)."""
    if level < 0 or level > 100:
        raise typer.BadParameter("level must be 0..100")
    _action(device, f"громкость на {level}", cookie)


@app.command()
def play(device: str, query: str, cookie: str = typer.Option(None)):
    """Play query on station (best-effort, cloud text command)."""
    _action(device, f"включи {query}", cookie)


def _action(device: str, text: str, cookie: str | None):
    cookie = _load_cookie(cookie)

    async def run():
        async for q in _with_quasar(cookie):
            devices = await q.list_devices_raw()
            d = _match_device(devices, device)
            scenario_map = await q.ensure_speaker_scenarios(devices)
            did = str(d["id"])
            sid = scenario_map.get(did)
            if not sid:
                raise typer.BadParameter("device has no capabilities for cloud scenarios (module?)")
            await q.run_speaker_action(sid, did, text)
            typer.echo(f"ok: {d.get('name')} ({did}) <= {text}")

    try:
        asyncio.run(run())
    except AuthError as e:
        raise typer.Exit(code=2) from e


def main() -> None:
    app()
