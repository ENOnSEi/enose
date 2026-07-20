import json
import queue
import threading
from typing import Any

from app.core.config import settings

_queue: queue.Queue = queue.Queue(maxsize=2000)
_running = False
_connected = False
_estado = "base"
_readings_total = 0
_last_error: str | None = None
_sensor_names: list[str] = []
_client: Any = None
_lock = threading.Lock()


def _handle_message(message: str) -> None:
    global _readings_total, _last_error

    try:
        payload = json.loads(message)
    except json.JSONDecodeError:
        _last_error = "invalid json from board"
        return

    if payload.get("type") != "reading":
        return

    values = payload.get("values")
    if not isinstance(values, dict):
        _last_error = "reading without values"
        return

    missing = [name for name in _sensor_names if name not in values]
    if missing:
        _last_error = f"reading missing sensors: {', '.join(missing)}"
        return

    try:
        arduino_ms = int(payload["arduino_ms"])
        parsed_values = {name: int(values[name]) for name in _sensor_names}
    except (KeyError, TypeError, ValueError):
        _last_error = "reading contains invalid numeric data"
        return

    try:
        _queue.put_nowait((arduino_ms, parsed_values, _estado))
        _readings_total += 1
        _last_error = None
    except queue.Full:
        _last_error = "reading queue full"


def _publish_command(command: dict[str, Any]) -> None:
    if _client is None:
        return
    try:
        _client.publish(settings.MQTT_COMMANDS_TOPIC, json.dumps(command))
    except Exception as e:  # noqa: BLE001 - paho raises broad errors while offline
        globals()["_last_error"] = f"publish error: {e}"


def _on_connect(client, userdata, flags, reason_code, properties=None) -> None:
    global _connected, _last_error

    rc = int(getattr(reason_code, "value", reason_code))
    if rc != 0:
        _connected = False
        _last_error = f"mqtt connect failed rc={rc}"
        print(f"[board_mqtt] connect failed rc={rc}")
        return

    _connected = True
    _last_error = None
    client.subscribe(settings.MQTT_READINGS_TOPIC)
    _publish_command({"type": "command", "estado": _estado})
    print(f"[board_mqtt] connected, subscribed to {settings.MQTT_READINGS_TOPIC}")


def _on_disconnect(client, userdata, *args) -> None:
    global _connected
    _connected = False
    if _running:
        print("[board_mqtt] disconnected, will auto-reconnect")


def _on_message(client, userdata, message) -> None:
    try:
        _handle_message(message.payload.decode("utf-8"))
    except Exception as e:  # noqa: BLE001
        globals()["_last_error"] = f"message error: {e}"


def start(sensor_names: list[str]) -> bool:
    global _running, _sensor_names, _last_error, _client

    with _lock:
        if _running:
            return False

        try:
            import paho.mqtt.client as mqtt
        except ModuleNotFoundError as e:
            _last_error = "missing dependency: paho-mqtt"
            print(f"[board_mqtt] {e}")
            return False

        _sensor_names = list(sensor_names)
        _last_error = None

        client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id="enose-api",
            clean_session=True,
        )
        if settings.MQTT_USERNAME:
            client.username_pw_set(settings.MQTT_USERNAME, settings.MQTT_PASSWORD or None)
        client.on_connect = _on_connect
        client.on_disconnect = _on_disconnect
        client.on_message = _on_message
        client.reconnect_delay_set(min_delay=1, max_delay=10)

        _client = client
        _running = True

        try:
            client.connect_async(settings.MQTT_BROKER_HOST, settings.MQTT_BROKER_PORT, keepalive=30)
            client.loop_start()
        except Exception as e:  # noqa: BLE001
            _last_error = str(e)
            _running = False
            _client = None
            print(f"[board_mqtt] start error: {e}")
            return False

        print(f"[board_mqtt] started, broker {settings.MQTT_BROKER_HOST}:{settings.MQTT_BROKER_PORT}")
        return True


def stop() -> None:
    global _running, _connected, _client

    _publish_command({"type": "command", "action": "stop"})
    _running = False

    client = _client
    if client is not None:
        try:
            client.loop_stop()
            client.disconnect()
        except Exception as e:  # noqa: BLE001
            print(f"[board_mqtt] stop error: {e}")
    _connected = False
    _client = None
    print("[board_mqtt] stopped")


def set_estado(estado: str) -> None:
    global _estado
    _estado = estado
    _publish_command({"type": "command", "estado": estado})


def get_status() -> dict:
    return {
        "running": _running,
        "connected": _connected,
        "estado": _estado,
        "readings_queued": _queue.qsize(),
        "readings_total": _readings_total,
        "last_error": _last_error,
        "board_url": f"mqtt://{settings.MQTT_BROKER_HOST}:{settings.MQTT_BROKER_PORT}",
    }


def drain() -> list[tuple]:
    items = []
    while not _queue.empty():
        try:
            items.append(_queue.get_nowait())
        except queue.Empty:
            break
    return items
