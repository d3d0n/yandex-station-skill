from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from typing import Any

from zeroconf import ServiceBrowser, ServiceStateChange, Zeroconf


@dataclass(frozen=True)
class LocalSpeaker:
    device_id: str
    platform: str
    host: str
    port: int


class _Listener:
    def __init__(self):
        self.found: dict[str, LocalSpeaker] = {}

    def __call__(
        self,
        zeroconf: Zeroconf,
        service_type: str,
        name: str,
        state_change: ServiceStateChange,
    ):
        try:
            info = zeroconf.get_service_info(service_type, name)
            if not info or not info.addresses:
                return

            props: dict[str, Any] = {
                k.decode(): v.decode() if isinstance(v, (bytes, bytearray)) else v
                for k, v in (info.properties or {}).items()
            }
            device_id = props.get("deviceId")
            platform = props.get("platform")
            if not device_id or not platform:
                return

            host = str(ipaddress.ip_address(info.addresses[0]))
            speaker = LocalSpeaker(device_id=str(device_id), platform=str(platform), host=host, port=int(info.port))
            self.found[speaker.device_id] = speaker
        except Exception:
            return


def discover_local_speakers(*, time_s: float = 2.0) -> list[LocalSpeaker]:
    """Blocking discovery via mDNS (_yandexio._tcp.local.)."""
    zc = Zeroconf()
    listener = _Listener()
    browser = ServiceBrowser(zc, "_yandexio._tcp.local.", handlers=[listener])

    import time

    time.sleep(time_s)

    try:
        browser.cancel()
    except Exception:
        pass
    try:
        zc.close()
    except Exception:
        pass

    return list(listener.found.values())
