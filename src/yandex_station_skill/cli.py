from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Optional

import typer

from .config import AppConfig, load_config, paths, save_config
from .passport_auth import PassportAuth, load_qr_state, qr_url, save_qr_state
from .quasar import Quasar
from .session import AuthError, YandexSession

app = typer.Typer(add_completion=False, no_args_is_help=True)
auth_app = typer.Typer(add_completion=False, no_args_is_help=True)
config_app = typer.Typer(add_completion=False, no_args_is_help=True)
app.add_typer(auth_app, name="auth")
app.add_typer(config_app, name="config")


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


@config_app.command("show")
def config_show():
    """Show current config."""
    cfg = load_config()
    p = paths()
    typer.echo(f"config: {p.config_file}")
    typer.echo(f"max_volume: {cfg.max_volume}")
    typer.echo(f"default_device: {cfg.default_device}")
    typer.echo(f"prefer_local: {cfg.prefer_local}")
    typer.echo(f"local_host: {cfg.local_host}")
    typer.echo(f"local_port: {cfg.local_port}")
    typer.echo(f"local_device_id: {cfg.local_device_id}")
    typer.echo(f"local_platform: {cfg.local_platform}")


@config_app.command("set-max-volume")
def config_set_max_volume(level: int = typer.Argument(..., help="Default max volume for volume command")):
    """Set default max volume cap (stored in config.json)."""
    if level < 0 or level > 100:
        raise typer.BadParameter("level must be 0..100")
    cfg = load_config()
    cfg.max_volume = level
    path = save_config(cfg)
    typer.echo(f"ok: max_volume={level}")
    typer.echo(str(path))


@config_app.command("set-default-device")
def config_set_default_device(needle: str = typer.Argument(..., help="Device name substring or id")):
    """Set default device used when device arg omitted."""
    cfg = load_config()
    cfg.default_device = needle.strip()
    path = save_config(cfg)
    typer.echo(f"ok: default_device={cfg.default_device}")
    typer.echo(str(path))


@config_app.command("clear-default-device")
def config_clear_default_device():
    cfg = load_config()
    cfg.default_device = None
    path = save_config(cfg)
    typer.echo("ok: default_device cleared")
    typer.echo(str(path))


@config_app.command("set-prefer-local")
def config_set_prefer_local(v: bool = typer.Argument(..., help="true/false")):
    cfg = load_config()
    cfg.prefer_local = bool(v)
    path = save_config(cfg)
    typer.echo(f"ok: prefer_local={cfg.prefer_local}")
    typer.echo(str(path))


@config_app.command("set-local-endpoint")
def config_set_local_endpoint(
    host: str = typer.Argument(..., help="Station IP/hostname on LAN (manual override; useful in WSL)") ,
    port: int = typer.Argument(1961, help="Glagol WebSocket port (as seen in mDNS; usually 1961)"),
):
    """Set manual local Glagol endpoint used when mDNS discovery fails."""
    cfg = load_config()
    cfg.local_host = host.strip()
    cfg.local_port = int(port)
    path = save_config(cfg)
    typer.echo(f"ok: local_endpoint={cfg.local_host}:{cfg.local_port}")
    typer.echo(str(path))


@config_app.command("clear-local-endpoint")
def config_clear_local_endpoint():
    """Clear manual local endpoint override."""
    cfg = load_config()
    cfg.local_host = None
    cfg.local_port = None
    path = save_config(cfg)
    typer.echo("ok: local_endpoint cleared")
    typer.echo(str(path))


@config_app.command("set-local-ids")
def config_set_local_ids(
    device_id: str = typer.Argument(..., help="Local deviceId (from mDNS properties: deviceId)"),
    platform: str = typer.Argument(..., help="Local platform (from mDNS properties: platform)"),
):
    """Set manual device_id/platform for Glagol token request (fallback when Quasar config isn't available)."""
    cfg = load_config()
    cfg.local_device_id = device_id.strip()
    cfg.local_platform = platform.strip()
    path = save_config(cfg)
    typer.echo(f"ok: local_ids={cfg.local_device_id} / {cfg.local_platform}")
    typer.echo(str(path))


@config_app.command("clear-local-ids")
def config_clear_local_ids():
    """Clear manual device_id/platform overrides."""
    cfg = load_config()
    cfg.local_device_id = None
    cfg.local_platform = None
    path = save_config(cfg)
    typer.echo("ok: local_ids cleared")
    typer.echo(str(path))


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


@auth_app.command("qr-png")
def auth_qr_png():
    """Start QR auth and write a login QR PNG to ~/.config/yandex-station-skill/qr.png.

    Strategy:
    - try to fetch real QR as SVG directly (no browser)
    - if blocked by captcha -> fallback to Playwright render (if available)
    """
    from .config import paths

    async def run():
        auth = PassportAuth()
        try:
            state = await auth.qr_begin()
            save_qr_state(state)
            url = qr_url(state)
            p = paths()

            # 1) lightweight: fetch SVG directly
            try:
                from .qr_fetch import fetch_magic_qr

                res = fetch_magic_qr(url)
                if res.ok and res.kind == "svg":
                    svg_path = p.config_dir / "qr.svg"
                    p.config_dir.mkdir(parents=True, exist_ok=True)
                    svg_path.write_bytes(res.body)
                    # We still need PNG for chat UX; try cairosvg if present.
                    try:
                        import cairosvg  # type: ignore

                        cairosvg.svg2png(bytestring=res.body, write_to=str(p.qr_file))
                        typer.echo(str(p.qr_file))
                        typer.echo(url)
                        return
                    except Exception:
                        # fallback: return SVG path + url
                        typer.echo(str(svg_path))
                        typer.echo(url)
                        return
            except Exception:
                pass

            # 2) fallback: render page QR via Playwright
            from .qr_render import render_magic_qr_png

            await render_magic_qr_png(url, p.qr_file)
            typer.echo(str(p.qr_file))
            typer.echo(url)
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
def status(
    device: str | None = typer.Argument(None, help="Device name/id (optional if default_device set)"),
    cookie: str = typer.Option(None),
    prefer_local: bool | None = typer.Option(None, help="Override prefer_local (default from config)"),
    local_host: str | None = typer.Option(None, help="Manual local station host/IP (bypass mDNS; overrides config.local_host)"),
    local_port: int | None = typer.Option(None, help="Manual local station port (bypass mDNS; overrides config.local_port)"),
):
    """Best-effort playback status (local Glagol getState when available)."""
    _status(device, cookie, prefer_local=prefer_local, local_host=local_host, local_port=local_port)


@app.command()
def pause(
    device: str | None = typer.Argument(None, help="Device name/id (optional if default_device set)"),
    cookie: str = typer.Option(None),
    prefer_local: bool | None = typer.Option(None, help="Override prefer_local (default from config)"),
    local_host: str | None = typer.Option(None, help="Manual local station host/IP (bypass mDNS; overrides config.local_host)"),
    local_port: int | None = typer.Option(None, help="Manual local station port (bypass mDNS; overrides config.local_port)"),
):
    """Pause on a station."""
    _action(device, "пауза", cookie, prefer_local=prefer_local, local_host=local_host, local_port=local_port)


@app.command()
def resume(
    device: str | None = typer.Argument(None, help="Device name/id (optional if default_device set)"),
    cookie: str = typer.Option(None),
    prefer_local: bool | None = typer.Option(None, help="Override prefer_local (default from config)"),
    local_host: str | None = typer.Option(None, help="Manual local station host/IP (bypass mDNS; overrides config.local_host)"),
    local_port: int | None = typer.Option(None, help="Manual local station port (bypass mDNS; overrides config.local_port)"),
):
    """Resume on a station."""
    _action(device, "продолжить", cookie, prefer_local=prefer_local, local_host=local_host, local_port=local_port)


@app.command()
def next(
    device: str | None = typer.Argument(None, help="Device name/id (optional if default_device set)"),
    cookie: str = typer.Option(None),
    prefer_local: bool | None = typer.Option(None),
    local_host: str | None = typer.Option(None, help="Manual local station host/IP (bypass mDNS; overrides config.local_host)"),
    local_port: int | None = typer.Option(None, help="Manual local station port (bypass mDNS; overrides config.local_port)"),
):
    """Next track."""
    _action(device, "следующий трек", cookie, prefer_local=prefer_local, local_host=local_host, local_port=local_port)


@app.command()
def prev(
    device: str | None = typer.Argument(None, help="Device name/id (optional if default_device set)"),
    cookie: str = typer.Option(None),
    prefer_local: bool | None = typer.Option(None),
    local_host: str | None = typer.Option(None, help="Manual local station host/IP (bypass mDNS; overrides config.local_host)"),
    local_port: int | None = typer.Option(None, help="Manual local station port (bypass mDNS; overrides config.local_port)"),
):
    """Previous track."""
    _action(device, "прошлый трек", cookie, prefer_local=prefer_local, local_host=local_host, local_port=local_port)


@app.command()
def volume(
    device: str | None = typer.Argument(None, help="Device name/id (optional if default_device set)"),
    level: int = typer.Argument(...),
    cookie: str = typer.Option(None),
    prefer_local: bool | None = typer.Option(None),
    max_level: int | None = typer.Option(None, help="Safety cap override (default from config)"),
    local_host: str | None = typer.Option(None, help="Manual local station host/IP (bypass mDNS; overrides config.local_host)"),
    local_port: int | None = typer.Option(None, help="Manual local station port (bypass mDNS; overrides config.local_port)"),
):
    """Set volume 0..100 (capped by max_level, default from config.json)."""
    if level < 0 or level > 100:
        raise typer.BadParameter("level must be 0..100")

    cfg = load_config()
    cap = cfg.max_volume if max_level is None else max_level
    if cap < 0 or cap > 100:
        cap = 70

    if level > cap:
        raise typer.BadParameter(f"level must be <= {cap}")

    _action(
        device,
        f"громкость на {level}",
        cookie,
        prefer_local=prefer_local,
        local_host=local_host,
        local_port=local_port,
    )


@app.command()
def play(
    query: str,
    device: str | None = typer.Option(None, help="Device name/id (optional if default_device set)"),
    cookie: str = typer.Option(None),
    prefer_local: bool | None = typer.Option(None),
    local_host: str | None = typer.Option(None, help="Manual local station host/IP (bypass mDNS; overrides config.local_host)"),
    local_port: int | None = typer.Option(None, help="Manual local station port (bypass mDNS; overrides config.local_port)"),
):
    """Play query on station (best-effort)."""
    _action(device, f"включи {query}", cookie, prefer_local=prefer_local, local_host=local_host, local_port=local_port)


@app.command()
def like(
    device: str | None = typer.Argument(None, help="Device name/id (optional if default_device set)"),
    cookie: str = typer.Option(None),
    prefer_local: bool | None = typer.Option(None),
    local_host: str | None = typer.Option(None, help="Manual local station host/IP (bypass mDNS; overrides config.local_host)"),
    local_port: int | None = typer.Option(None, help="Manual local station port (bypass mDNS; overrides config.local_port)"),
):
    """Like current track (Alice command)."""
    _action(device, "лайк", cookie, prefer_local=prefer_local, local_host=local_host, local_port=local_port)


@app.command()
def dislike(
    device: str | None = typer.Argument(None, help="Device name/id (optional if default_device set)"),
    cookie: str = typer.Option(None),
    prefer_local: bool | None = typer.Option(None),
    local_host: str | None = typer.Option(None, help="Manual local station host/IP (bypass mDNS; overrides config.local_host)"),
    local_port: int | None = typer.Option(None, help="Manual local station port (bypass mDNS; overrides config.local_port)"),
):
    """Dislike current track (Alice command)."""
    _action(device, "не нравится", cookie, prefer_local=prefer_local, local_host=local_host, local_port=local_port)


@app.command()
def stop(
    device: str | None = typer.Argument(None, help="Device name/id (optional if default_device set)"),
    cookie: str = typer.Option(None),
    prefer_local: bool | None = typer.Option(None),
    local_host: str | None = typer.Option(None, help="Manual local station host/IP (bypass mDNS; overrides config.local_host)"),
    local_port: int | None = typer.Option(None, help="Manual local station port (bypass mDNS; overrides config.local_port)"),
):
    """Stop playback."""
    _action(device, "стоп", cookie, prefer_local=prefer_local, local_host=local_host, local_port=local_port)


@app.command()
def louder(
    device: str | None = typer.Argument(None, help="Device name/id (optional if default_device set)"),
    cookie: str = typer.Option(None),
    prefer_local: bool | None = typer.Option(None),
    local_host: str | None = typer.Option(None, help="Manual local station host/IP (bypass mDNS; overrides config.local_host)"),
    local_port: int | None = typer.Option(None, help="Manual local station port (bypass mDNS; overrides config.local_port)"),
):
    """Volume up a bit."""
    _action(device, "громче", cookie, prefer_local=prefer_local, local_host=local_host, local_port=local_port)


@app.command()
def quieter(
    device: str | None = typer.Argument(None, help="Device name/id (optional if default_device set)"),
    cookie: str = typer.Option(None),
    prefer_local: bool | None = typer.Option(None),
    local_host: str | None = typer.Option(None, help="Manual local station host/IP (bypass mDNS; overrides config.local_host)"),
    local_port: int | None = typer.Option(None, help="Manual local station port (bypass mDNS; overrides config.local_port)"),
):
    """Volume down a bit."""
    _action(device, "тише", cookie, prefer_local=prefer_local, local_host=local_host, local_port=local_port)


@app.command("shuffle-on")
def shuffle_on(
    device: str | None = typer.Argument(None, help="Device name/id (optional if default_device set)"),
    cookie: str = typer.Option(None),
    prefer_local: bool | None = typer.Option(None),
    local_host: str | None = typer.Option(None, help="Manual local station host/IP (bypass mDNS; overrides config.local_host)"),
    local_port: int | None = typer.Option(None, help="Manual local station port (bypass mDNS; overrides config.local_port)"),
):
    """Enable shuffle."""
    _action(device, "включи перемешивание", cookie, prefer_local=prefer_local, local_host=local_host, local_port=local_port)


@app.command("shuffle-off")
def shuffle_off(
    device: str | None = typer.Argument(None, help="Device name/id (optional if default_device set)"),
    cookie: str = typer.Option(None),
    prefer_local: bool | None = typer.Option(None),
    local_host: str | None = typer.Option(None, help="Manual local station host/IP (bypass mDNS; overrides config.local_host)"),
    local_port: int | None = typer.Option(None, help="Manual local station port (bypass mDNS; overrides config.local_port)"),
):
    """Disable shuffle."""
    _action(device, "выключи перемешивание", cookie, prefer_local=prefer_local, local_host=local_host, local_port=local_port)


@app.command("repeat-on")
def repeat_on(
    device: str | None = typer.Argument(None, help="Device name/id (optional if default_device set)"),
    cookie: str = typer.Option(None),
    prefer_local: bool | None = typer.Option(None),
    local_host: str | None = typer.Option(None, help="Manual local station host/IP (bypass mDNS; overrides config.local_host)"),
    local_port: int | None = typer.Option(None, help="Manual local station port (bypass mDNS; overrides config.local_port)"),
):
    """Enable repeat."""
    _action(device, "включи повтор", cookie, prefer_local=prefer_local, local_host=local_host, local_port=local_port)


@app.command("repeat-off")
def repeat_off(
    device: str | None = typer.Argument(None, help="Device name/id (optional if default_device set)"),
    cookie: str = typer.Option(None),
    prefer_local: bool | None = typer.Option(None),
    local_host: str | None = typer.Option(None, help="Manual local station host/IP (bypass mDNS; overrides config.local_host)"),
    local_port: int | None = typer.Option(None, help="Manual local station port (bypass mDNS; overrides config.local_port)"),
):
    """Disable repeat."""
    _action(device, "выключи повтор", cookie, prefer_local=prefer_local, local_host=local_host, local_port=local_port)


@app.command()
def cmd(
    text: str = typer.Argument(..., help="Raw Alice command text (sent as text_action)") ,
    device: str | None = typer.Option(None, help="Device name/id (optional if default_device set)"),
    cookie: str = typer.Option(None),
    prefer_local: bool | None = typer.Option(None, help="Prefer local; note: arbitrary cmd likely uses cloud"),
):
    """Send raw command text to station (cloud)."""
    # force cloud for arbitrary commands
    _action(device, text, cookie, prefer_local=False)


def _status(
    device: str | None,
    cookie: str | None,
    *,
    prefer_local: bool | None = None,
    local_host: str | None = None,
    local_port: int | None = None,
):
    cookie = _load_cookie(cookie)

    async def run():
        cfg0 = load_config()
        if prefer_local is None:
            prefer_local_eff = bool(cfg0.prefer_local)
        else:
            prefer_local_eff = bool(prefer_local)

        async for q in _with_quasar(cookie):
            devices = await q.list_devices_raw()

            needle = device
            if needle is None:
                needle = cfg0.default_device
            if not needle:
                raise typer.BadParameter(
                    "no device specified and no default_device set. run: yandex-station-skill config set-default-device <name>"
                )

            d = _match_device(devices, needle)

            did = str(d["id"])
            name = d.get("name")

            if prefer_local_eff:
                try:
                    from .discovery import discover_local_speakers
                    from .glagol import GlagolClient, get_conversation_token
                    from .tokens import get_tokens

                    manual_host = local_host or cfg0.local_host
                    manual_port0 = local_port if local_port is not None else cfg0.local_port
                    manual_port = int(manual_port0) if manual_port0 else 1961

                    locals_ = {s.device_id: s for s in discover_local_speakers(time_s=2.0)}

                    cfg = await q.session.get(f"https://iot.quasar.yandex.ru/m/user/devices/{did}/configuration")
                    quasar_info = cfg.get("quasar_info") or {}
                    local_id = quasar_info.get("device_id") or cfg0.local_device_id
                    platform = quasar_info.get("platform") or cfg0.local_platform

                    host = None
                    port = None
                    if local_id and str(local_id) in locals_:
                        sp = locals_[str(local_id)]
                        host, port = sp.host, sp.port
                    elif manual_host:
                        host, port = manual_host, manual_port

                    if host and port and local_id and platform:
                        tokens = await get_tokens(cookie)
                        conv = await get_conversation_token(
                            device_id=str(local_id),
                            platform=str(platform),
                            music_token=tokens.music_token,
                        )
                        g = GlagolClient(host=str(host), port=int(port), conversation_token=conv)
                        resp = await g.send({"command": "getState"})
                        payload = resp.get("payload")

                        player_state = None
                        if isinstance(payload, dict):
                            if "playerState" in payload:
                                player_state = payload.get("playerState")
                            else:
                                st = payload.get("state")
                                if isinstance(st, dict) and "playerState" in st:
                                    player_state = st.get("playerState")

                        typer.echo(f"ok(local): {name} ({did})")
                        if player_state is not None:
                            typer.echo(json.dumps(player_state, ensure_ascii=False, indent=2))
                        else:
                            typer.echo(json.dumps(payload, ensure_ascii=False, indent=2) if isinstance(payload, (dict, list)) else str(payload))
                        return
                except Exception:
                    pass

            # cloud fallback (no playerState, but show what we can)
            cfg = await q.session.get(f"https://iot.quasar.yandex.ru/m/user/devices/{did}/configuration")
            typer.echo(f"ok(cloud): {name} ({did})")
            qi = cfg.get("quasar_info") or {}
            typer.echo(json.dumps(qi, ensure_ascii=False, indent=2) if qi else "(no quasar_info)")

    try:
        asyncio.run(run())
    except AuthError as e:
        raise typer.Exit(code=2) from e


def _action(
    device: str | None,
    text: str,
    cookie: str | None,
    *,
    prefer_local: bool | None = None,
    local_host: str | None = None,
    local_port: int | None = None,
):
    cookie = _load_cookie(cookie)

    async def run():
        cfg0 = load_config()
        if prefer_local is None:
            prefer_local_eff = bool(cfg0.prefer_local)
        else:
            prefer_local_eff = bool(prefer_local)

        async for q in _with_quasar(cookie):
            devices = await q.list_devices_raw()

            needle = device
            if needle is None:
                needle = cfg0.default_device
            if not needle:
                raise typer.BadParameter(
                    "no device specified and no default_device set. run: yandex-station-skill config set-default-device <name>"
                )

            d = _match_device(devices, needle)

            did = str(d["id"])
            name = d.get("name")

            if prefer_local_eff:
                # try local glagol if we can discover device and get tokens
                try:
                    from .discovery import discover_local_speakers
                    from .glagol import GlagolClient, get_conversation_token
                    from .tokens import get_tokens

                    # manual endpoint overrides (useful when mDNS doesn't work, e.g. WSL)
                    manual_host = local_host or cfg0.local_host
                    manual_port0 = local_port if local_port is not None else cfg0.local_port
                    manual_port = int(manual_port0) if manual_port0 else 1961

                    locals_ = {s.device_id: s for s in discover_local_speakers(time_s=2.0)}

                    # Prefer Quasar-provided ids; fallback to config overrides.
                    cfg = await q.session.get(f"https://iot.quasar.yandex.ru/m/user/devices/{did}/configuration")
                    quasar_info = cfg.get("quasar_info") or {}
                    local_id = quasar_info.get("device_id") or cfg0.local_device_id
                    platform = quasar_info.get("platform") or cfg0.local_platform

                    host = None
                    port = None
                    if local_id and str(local_id) in locals_:
                        sp = locals_[str(local_id)]
                        host, port = sp.host, sp.port
                    elif manual_host:
                        host, port = manual_host, manual_port

                    if host and port and local_id and platform:
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
                            tokens = await get_tokens(cookie)
                            conv = await get_conversation_token(
                                device_id=str(local_id),
                                platform=str(platform),
                                music_token=tokens.music_token,
                            )
                            g = GlagolClient(host=str(host), port=int(port), conversation_token=conv)
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
