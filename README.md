# yandex-station-skill

Control Yandex Station playback (v1). First implementation uses **cloud control** via Quasar scenarios (text commands).

## Quick start (dev)

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
uv run yandex-station-skill volume "Kitchen" 35
uv run yandex-station-skill next "Kitchen"
uv run yandex-station-skill play "Kitchen" "my music"
```

## Notes

- This v1 is **cloud** only (works even if station isn't discoverable on LAN).
- Local LAN (Glagol WebSocket) will be added next.
