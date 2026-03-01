# yandex-station-skill

Control Yandex Station playback (v1): pick a station in your network/account, play/pause/next/prev, set volume, show status.

## Commands (planned)

- `station list` — list available stations/devices
- `station status <device>` — current playback + volume
- `station play <device> <query>` — start playing music on device (best-effort)
- `station pause <device>` / `station resume <device>`
- `station next <device>` / `station prev <device>`
- `station volume <device> <0-100>`

## Auth

TBD (likely QR/cookies/token via Yandex account, plus local mode when on same LAN).

## Dev

This repo is the source of truth. We will later package it as an OpenClaw skill directory under `skills/`.
