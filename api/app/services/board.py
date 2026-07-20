"""Transport-agnostic facade over the board connection.

Selects the WebSocket or MQTT backend based on ``settings.BOARD_TRANSPORT``.
Both backends expose the same thread-safe interface so the rest of the app
does not care which transport is in use:

    start(sensor_names) -> bool
    stop() -> None
    set_estado(estado) -> None
    get_status() -> dict
    drain() -> list[tuple]
"""

from app.core.config import settings
from app.services import board_mqtt, board_ws

_use_mqtt = settings.BOARD_TRANSPORT.lower() == "mqtt"


def start(sensor_names: list[str]) -> bool:
    if _use_mqtt:
        return board_mqtt.start(sensor_names)
    return board_ws.start(settings.ESP32_WS_URL, sensor_names)


def stop() -> None:
    if _use_mqtt:
        return board_mqtt.stop()
    return board_ws.stop()


def set_estado(estado: str) -> None:
    if _use_mqtt:
        return board_mqtt.set_estado(estado)
    return board_ws.set_estado(estado)


def get_status() -> dict:
    if _use_mqtt:
        return board_mqtt.get_status()
    return board_ws.get_status()


def drain() -> list[tuple]:
    if _use_mqtt:
        return board_mqtt.drain()
    return board_ws.drain()
