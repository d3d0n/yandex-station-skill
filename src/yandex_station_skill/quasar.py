from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .session import YandexSession

MASK_EN = "0123456789abcdef-"
MASK_RU = "оеаинтсрвлкмдпуяы"


def encode(uid: str) -> str:
    # same trick as AlexxIT/YandexStation: yandex is picky
    return "".join([MASK_RU[MASK_EN.index(s)] for s in uid])


def scenario_speaker_action(name: str, trigger: str, device_id: str, action: str) -> dict[str, Any]:
    return {
        "name": name,
        "icon": "home",
        "triggers": [{"trigger": {"type": "scenario.trigger.voice", "value": trigger}}],
        "steps": [
            {
                "type": "scenarios.steps.actions.v2",
                "parameters": {
                    "items": [
                        {
                            "id": device_id,
                            "type": "step.action.item.device",
                            "value": {
                                "id": device_id,
                                "item_type": "device",
                                "capabilities": [
                                    {
                                        "type": "devices.capabilities.quasar.server_action",
                                        "state": {"instance": "text_action", "value": action},
                                    }
                                ],
                            },
                        }
                    ]
                },
            }
        ],
    }


def scenario_speaker_tts(name: str, trigger: str, device_id: str, text: str) -> dict[str, Any]:
    return {
        "name": name,
        "icon": "home",
        "triggers": [{"trigger": {"type": "scenario.trigger.voice", "value": trigger}}],
        "steps": [
            {
                "type": "scenarios.steps.actions.v2",
                "parameters": {
                    "items": [
                        {
                            "id": device_id,
                            "type": "step.action.item.device",
                            "value": {
                                "id": device_id,
                                "item_type": "device",
                                "capabilities": [
                                    {
                                        "type": "devices.capabilities.quasar",
                                        "state": {"instance": "tts", "value": {"text": text}},
                                    }
                                ],
                            },
                        }
                    ]
                },
            }
        ],
    }


@dataclass
class Quasar:
    session: YandexSession

    async def list_devices_raw(self) -> list[dict[str, Any]]:
        resp = await self.session.get("https://iot.quasar.yandex.ru/m/v3/user/devices")
        devices: list[dict[str, Any]] = []
        for house in resp.get("households", []):
            for d in house.get("all", []):
                devices.append({**d, "house_name": house.get("name")})
        return devices

    async def list_scenarios(self) -> list[dict[str, Any]]:
        resp = await self.session.get("https://iot.quasar.yandex.ru/m/user/scenarios")
        return resp.get("scenarios", [])

    async def add_scenario_dummy(self, device_id: str, trigger: str) -> str:
        payload = scenario_speaker_tts("OC " + device_id, trigger, device_id, "пустышка")
        resp = await self.session.post("https://iot.quasar.yandex.ru/m/v4/user/scenarios", json=payload)
        return str(resp["scenario_id"])

    async def ensure_speaker_scenarios(self, devices: list[dict[str, Any]]) -> dict[str, str]:
        scenarios = await self.list_scenarios()

        hashes: dict[str, str] = {}
        for sc in scenarios:
            try:
                hashes[str(sc["triggers"][0]["value"])] = str(sc["id"])
            except Exception:
                pass

        mapping: dict[str, str] = {}
        for d in devices:
            # skip things without capabilities (modules, etc.)
            if not d.get("capabilities"):
                continue
            did = str(d["id"])
            trig = encode(did)
            sid = hashes.get(trig)
            if not sid:
                sid = await self.add_scenario_dummy(did, trig)
            mapping[did] = sid
        return mapping

    async def run_speaker_action(self, scenario_id: str, device_id: str, action_text: str) -> None:
        name = "OC " + device_id
        trigger = encode(device_id)
        payload = scenario_speaker_action(name, trigger, device_id, action_text)

        await self.session.put(f"https://iot.quasar.yandex.ru/m/v4/user/scenarios/{scenario_id}", json=payload)
        await self.session.post(f"https://iot.quasar.yandex.ru/m/user/scenarios/{scenario_id}/actions")
