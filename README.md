# yandex-station-skill

Control Yandex Station playback (v1). First implementation uses **cloud control** via Quasar scenarios (text commands).

## Quick start (dev)

### Option A (recommended): QR login (no cookie copying)

1) Generate QR URL

```bash
uv run yandex-station-skill auth qr-url
```

2) Open the printed URL on your phone (scan it or just open) and confirm login in Yandex app.

3) Complete and save cookies

```bash
uv run yandex-station-skill auth qr-complete
```

### Option B: manual cookies

1) Get Yandex cookies from a logged-in browser session
- open `https://yandex.ru/quasar`
- DevTools → Application/Storage → Cookies → copy cookies for `yandex.ru`
- paste as a single `Cookie:` header value (e.g. `yandexuid=...; Session_id=...; ...`)

2) Save cookies

```bash
uv run yandex-station-skill setup-cookie "yandexuid=...; Session_id=...; ..."
```

3) List devices

```bash
uv run yandex-station-skill list
```

4) Control

```bash
uv run yandex-station-skill pause "Kitchen"
uv run yandex-station-skill volume "Kitchen" 25
uv run yandex-station-skill next "Kitchen"
uv run yandex-station-skill play "Kitchen" "my music"
```

### Volume safety cap

Default max volume is stored in `~/.config/yandex-station-skill/config.json`.

```bash
uv run yandex-station-skill config show
uv run yandex-station-skill config set-max-volume 70
```

## Notes

- This v1 is **cloud** only (works even if station isn't discoverable on LAN).
- Local LAN (Glagol WebSocket) will be added next.
