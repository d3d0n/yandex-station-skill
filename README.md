# yandex-station-skill

Control Yandex Station.

- **Cloud mode** (fallback): Quasar scenarios (text actions)
- **Local mode** (preferred when available): Glagol WebSocket on LAN

## Quick start (dev)

### Option A (recommended): QR login (no cookie copying)

1) Generate QR URL

```bash
uv run yandex-station-skill auth qr-url
```

2) Open the printed URL on your phone and confirm login in Yandex app.

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

## Pick a default device

```bash
uv run yandex-station-skill list
uv run yandex-station-skill config set-default-device "Kitchen"
```

## Control

```bash
uv run yandex-station-skill pause
uv run yandex-station-skill resume
uv run yandex-station-skill next
uv run yandex-station-skill prev
uv run yandex-station-skill volume 25
uv run yandex-station-skill play "lofi"
```

## Local mode notes

Local mode tries to discover stations via mDNS: `_yandexio._tcp.local.`.

### Check mDNS discovery

```bash
uv run yandex-station-skill local
```

### WSL / broken mDNS

If discovery doesn't work (common in WSL), set a manual endpoint (IP/port):

```bash
uv run yandex-station-skill config set-local-endpoint 192.168.1.50 1961
```

You can also override per-command:

```bash
uv run yandex-station-skill pause --local-host 192.168.1.50 --local-port 1961
```

### Status

Best-effort `getState` (local first):

```bash
uv run yandex-station-skill status
```

## Volume safety cap

Default max volume is stored in `~/.config/yandex-station-skill/config.json`.

```bash
uv run yandex-station-skill config show
uv run yandex-station-skill config set-max-volume 70
```
