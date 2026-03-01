from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Paths:
    config_dir: Path
    cookie_file: Path


def paths() -> Paths:
    d = Path.home() / ".config" / "yandex-station-skill"
    return Paths(config_dir=d, cookie_file=d / "cookie.txt")
