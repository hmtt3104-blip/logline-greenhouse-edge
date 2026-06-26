from __future__ import annotations

from greenhouse_bridge.models import Greenhouse1State, ZoneState
from greenhouse_bridge.state_store import StateStore


def test_greenhouse1_mqtt_updates_active_state_after_replace() -> None:
    store = StateStore()
    old_g1 = store.g1

    store.replace_greenhouse1(
        Greenhouse1State(
            router_url="http://greenhouse-device.local",
            zone2=ZoneState(state="ERROR_OLD"),
        )
    )

    assert store.g1 is not old_g1

    assert store.update_from_topic(
        "greenhouse/example/telemetry/greenhouse1/router_url",
        "http://greenhouse-device.local",
    )
    assert store.update_from_topic("greenhouse/example/telemetry/greenhouse1/zone2/temp", "33.1")
    assert store.update_from_topic("greenhouse/example/telemetry/greenhouse1/zone2/humidity", "61.7")
    assert store.update_from_topic("greenhouse/example/telemetry/greenhouse1/zone2/state", "PAUSE_NEW")

    assert store.g1.router_url == "http://greenhouse-device.local"
    assert store.g1.zone2.temp == 33.1
    assert store.g1.zone2.humidity == 61.7
    assert store.g1.zone2.state == "PAUSE_NEW"

    assert old_g1.router_url is None
    assert old_g1.zone2.temp is None
    assert old_g1.zone2.humidity is None
    assert old_g1.zone2.state is None
