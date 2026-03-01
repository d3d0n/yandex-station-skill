---
name: yandex-station
description: Control Yandex Station playback (pause/resume/next/prev/volume/play) with QR login.
metadata: {"openclaw":{"emoji":"🎵","homepage":"https://github.com/d3d0n/yandex-station-skill","requires":{"bins":["uv"]}}}
---

# yandex-station (OpenClaw skill)

this skill is for **end-user voice/chat control** of Yandex Station.

## what the user expects (UX)

user says stuff like:
- “братан, поставь музыку на паузу”
- “включи обратно”
- “следующий трек / прошлый трек”
- “громкость 20% / громче / тише”
- “включи lofi”
- “лайк / не нравится”
- “перемешай / повтор”
- “стоп”

**your job:** do the action with minimal questions.

## happy path (first run)

if user asks for playback control and auth is missing:

1) generate a **login QR PNG** and send it immediately
   - run: `cd {baseDir} && uv run yandex-station-skill auth qr-png`
   - the command prints:
     - line 1: path to png (`~/.config/yandex-station-skill/qr.png`) — this PNG is the *real* QR shown by passport
     - line 2: the login url (fallback)
   - send the PNG to the user (attachment) with a short caption:
     - “отскань в приложении Яндекс и подтверди вход. потом напиши «готово».”

2) wait for user “готово”, then complete login:
   - `cd {baseDir} && uv run yandex-station-skill auth qr-complete --timeout-s 240`

3) detect devices + set default station:
   - `cd {baseDir} && uv run yandex-station-skill list`
   - if there is exactly one station-like device, set it as default:
     - `cd {baseDir} && uv run yandex-station-skill config set-default-device "<device name>"`
   - otherwise ask: “какую станцию сделать дефолтной? (скинь имя из списка)”

4) replay the original user request (pause/resume/etc) now that auth is ready.

## normal operation

prefer **no-device commands** once default is set:
- pause/resume: `... pause` / `... resume`
- next/prev: `... next` / `... prev`
- like/dislike: `... like` / `... dislike`
- stop: `... stop`
- louder/quieter: `... louder` / `... quieter`
- shuffle/repeat: `... shuffle-on` / `... shuffle-off` / `... repeat-on` / `... repeat-off`
- play: `cd {baseDir} && uv run yandex-station-skill play "<query>"`
- raw command: `cd {baseDir} && uv run yandex-station-skill cmd "<alice text>"`

if user specifies a device name, pass it:
- `... pause "kitchen"`

## volume safety

volume is capped by config key `max_volume` (default 70):
- show: `cd {baseDir} && uv run yandex-station-skill config show`
- set: `cd {baseDir} && uv run yandex-station-skill config set-max-volume 70`

when user says “не выше 30%” for the session, respect it even if config allows higher.

## failure modes (what to do)

- auth errors / empty device list:
  - rerun QR flow (qr-png → qr-complete)
  - if still empty: user likely confirmed wrong account

- local mode not available:
  - the tool falls back to cloud automatically
  - local discovery uses mDNS; in WSL it may not work
  - workaround: set manual endpoint:
    - `cd {baseDir} && uv run yandex-station-skill config set-local-endpoint <ip> 1961`
