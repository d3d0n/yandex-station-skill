from __future__ import annotations

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Paths:
    config_dir: Path
    cookie_file: Path
    config_file: Path


def paths() -> Paths:
    d = Path.home() / ".config" / "yandex-station-skill"
    return Paths(config_dir=d, cookie_file=d / "cookie.txt", config_file=d / "config.json")


@dataclass
class AppConfig:
    # Default safety cap for volume command.
    # User asked to keep it configurable, not hard-coded.
    max_volume: int = 70


def load_config() -> AppConfig:
    p = paths()
    try:
        raw = p.config_file.read_text(encoding="utf-8")
        data = json.loads(raw)
        cfg = AppConfig(**{k: v for k, v in data.items() if k in {"max_volume"}})
        return cfg
    except FileNotFoundError:
        return AppConfig()
    except Exception:
        # If config is corrupted, fall back to defaults.
        return AppConfig()


def save_config(cfg: AppConfig) -> Path:
    p = paths()
    p.config_dir.mkdir(parents=True, exist_ok=True)
    p.config_file.write_text(
        json.dumps({"max_volume": int(cfg.max_volume)}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return p.config_file
