from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class Paths:
    config_dir: Path
    cookie_file: Path
    config_file: Path
    qr_file: Path


def paths() -> Paths:
    d = Path.home() / ".config" / "yandex-station-skill"
    return Paths(
        config_dir=d,
        cookie_file=d / "cookie.txt",
        config_file=d / "config.json",
        qr_file=d / "qr.png",
    )


@dataclass
class AppConfig:
    # Safety cap for volume command.
    max_volume: int = 70

    # Default target device for commands when user doesn't specify one.
    # May be a substring of name or an exact device id.
    default_device: str | None = None

    # Prefer local control (Glagol WS) when discoverable; fallback to cloud.
    prefer_local: bool = True


def load_config() -> AppConfig:
    p = paths()
    try:
        data = json.loads(p.config_file.read_text(encoding="utf-8"))
        allowed = {"max_volume", "default_device", "prefer_local"}
        payload = {k: v for k, v in data.items() if k in allowed}
        return AppConfig(**payload)
    except FileNotFoundError:
        return AppConfig()
    except Exception:
        return AppConfig()


def save_config(cfg: AppConfig) -> Path:
    p = paths()
    p.config_dir.mkdir(parents=True, exist_ok=True)
    p.config_file.write_text(
        json.dumps(asdict(cfg), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return p.config_file
